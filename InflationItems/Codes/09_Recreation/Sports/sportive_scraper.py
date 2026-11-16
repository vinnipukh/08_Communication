"""Sportive (sportive.com.tr) sports clothing and sports equipment scraper for TÜİK group 09.

Sportive is a Next.js (app router) storefront on Akinon. The category HTML embeds the listing
as JSON inside the `self.__next_f.push([1, "..."])` flight chunks: a `{"data":{"pagination":...,
"products":[...]}}` object with 48 products per page. There is no separate JSON endpoint, so the
HTML page is requested (homepage first, curl_cffi Chrome impersonation) and that object is parsed.

robots.txt: only `/list/*`, `?p=`, `?order=`, `?marka=`, `?renk=`, `?category_ids=` and similar
filter URLs are disallowed; plain category URLs and `?page=N` are allowed and are all this uses.

Output: InflationItems/Datas/09_Recreation/Sportive/sportive_YYYY-MM-DD.csv
Columns: product_name, price, category_number, sub_category_number (the product URL is not saved).
Exit code 1 when any category fails or nothing is collected; no CSV is written then.
"""

import argparse
import csv
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


BASE_URL = "https://www.sportive.com.tr"

CLOTHING = "0922107"   # special sports clothing
EQUIPMENT = "0922103"  # sports equipment

# Leaf categories only (parents such as /kadin-giyim/ are mostly everyday wear and would also repeat
# every leaf). Sport-specific clothing goes to 0922107, equipment to 0922103. A product that appears in
# several listings is kept once (by the site's product id), under the first category that listed it. Equipment listings are filtered by product name (EQUIPMENT_RE).
CATEGORIES = [
    ("clothing", "/sporlar-fitness-kiyafetleri/", CLOTHING),
    ("clothing", "/sporlar-kosu-kiyafetleri/", CLOTHING),
    ("clothing", "/sporlar-trail-kiyafetleri/", CLOTHING),
    ("clothing", "/sporlar-tenis-kiyafetleri/", CLOTHING),
    ("clothing", "/erkek-tayt/", CLOTHING),
    ("clothing", "/kadin-tayt/", CLOTHING),
    ("clothing", "/cocuk-tayt/", CLOTHING),
    ("clothing", "/kadin-sporcu-sutyeni/", CLOTHING),
    ("clothing", "/erkek-mayo/", CLOTHING),
    ("clothing", "/kadin-mayo/", CLOTHING),
    ("clothing", "/cocuk-mayo/", CLOTHING),
    ("clothing", "/erkek-forma/", CLOTHING),
    ("clothing", "/kadin-forma/", CLOTHING),
    ("clothing", "/takim-sporlari-forma/", CLOTHING),
    ("clothing", "/takim-sporlari-kaleci-formasi/", CLOTHING),
    ("clothing", "/takim-sporlari-antrenman-tayti/", CLOTHING),
    ("equipment", "/sporlar-fitness-aletleri/", EQUIPMENT),
    ("equipment", "/sporlar-fitness-aksesuarlari/", EQUIPMENT),
    ("equipment", "/sporlar-fitness-eldiveni/", EQUIPMENT),
    ("equipment", "/sporlar-outdoor-ekipmanlari/", EQUIPMENT),
    ("equipment", "/sporlar-kamp-sandalyesi-ve-masasi/", EQUIPMENT),
    ("equipment", "/sporlar-masa-tenisi-raketi/", EQUIPMENT),
    ("equipment", "/sporlar-masa-tenisi-topu/", EQUIPMENT),
    ("equipment", "/sporlar-paten-kaykay/", EQUIPMENT),
    ("equipment", "/sporlar-scooter/", EQUIPMENT),
    ("equipment", "/sporlar-boks/", EQUIPMENT),
    ("equipment", "/sporlar-hentbol/", EQUIPMENT),
    ("equipment", "/sporlar-voleybol/", EQUIPMENT),
    ("equipment", "/sporlar-snorkel/", EQUIPMENT),
    ("equipment", "/sporlar-diger-ekipmanlar/", EQUIPMENT),
]

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "Datas" / "09_Recreation" / "Sportive"
TODAY = datetime.now().strftime("%Y-%m-%d")

CSV_COLUMNS = ["product_name", "price", "category_number", "sub_category_number"]

HEADERS = {"Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8"}

MAX_PAGES = 30
PAGE_DELAY = 2
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

# The "sporlar-*" equipment listings are mostly accessories (bottles, bags, hats, laces, everyday gloves,
# some clothing). Only products whose name is clearly sports gear are kept from them.
EQUIPMENT_RE = re.compile(
    r"topu\b|top pompası|dizlik|kolluk|(fitness|boks|ağırlık|kaleci|koşu) eldiven|şnorkel|raket",
    re.IGNORECASE,
)

# Text of an empty category page (seasonal stock; sitemap still lists the category).
EMPTY_MARKER = "aramanız için ürün bulunamadı"

CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.S)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


def extract_listing(html):
    """Return the listing object (pagination, products) embedded in the page, or None."""
    text = "".join(json.loads(f'"{chunk}"') for chunk in CHUNK_RE.findall(html))
    start = text.find('{"data":{"pagination"')
    if start < 0:
        return {"pagination": {}, "products": []} if EMPTY_MARKER in text else None
    return json.JSONDecoder().raw_decode(text[start:])[0].get("data")


def fetch_listing(session, path, page):
    url = BASE_URL + path
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                url, params={"page": page} if page > 1 else None, timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                listing = extract_listing(response.text)
                if listing is not None:
                    return listing
                logging.warning(f"No listing data in {path} page {page} (attempt {attempt})")
            else:
                logging.warning(f"HTTP {response.status_code} for {path} page {page} (attempt {attempt})")
        except (RequestException, ValueError) as error:
            logging.warning(f"Request failed for {path} page {page} (attempt {attempt}): {error}")
        time.sleep(PAGE_DELAY * attempt * 2)
    return None


def scrape_category(session, path, sub_category, max_pages, name_filter=None):
    """Return (products, ok); ok is False when a page could not be read."""
    products = []
    page, pages = 1, 1
    while page <= min(pages, max_pages):
        listing = fetch_listing(session, path, page)
        if listing is None:
            logging.error(f"Giving up on {path} at page {page}")
            return products, False

        pagination = listing.get("pagination") or {}
        pages = int(pagination.get("num_pages") or 1)

        count = 0
        for item in listing.get("products") or []:
            name = " ".join(str(item.get("name") or "").split())
            try:
                price = float(item.get("price"))
            except (TypeError, ValueError):
                continue
            if not name or price <= 0:
                continue
            if name_filter and not name_filter.search(name):
                continue
            products.append({
                "id": str(item.get("pk") or name),
                "product_name": name,
                "price": f"{price:.2f}",
                "category_number": "9",
                "sub_category_number": sub_category,
            })
            count += 1

        logging.info(f"{path} page {page}/{pages}: {count} products (site total {pagination.get('total_count')})")
        if not listing.get("products"):
            break
        page += 1
        time.sleep(PAGE_DELAY)
    return products, True


def save_to_csv(products, output_file):
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(products)
    logging.info(f"Saved {len(products)} products to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Sportive sports clothing (0922107) and equipment (0922103)")
    parser.add_argument("--only", choices=["clothing", "equipment"], help="One group only")
    parser.add_argument("--category", help="One category path, e.g. /sporlar-boks/ (bounded run)")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES, help=f"Pages per category (default {MAX_PAGES})")
    parser.add_argument("--date", default=TODAY, help="Output date (default: today)")
    args = parser.parse_args()

    categories = [c for c in CATEGORIES if (not args.only or c[0] == args.only)
                  and (not args.category or c[1] == args.category)]
    if not categories:
        logging.error("No category selected")
        return 1

    products, seen, failed = [], set(), []
    with requests.Session(impersonate="chrome") as session:
        session.headers.update(HEADERS)
        # Homepage first (same as a browser visit), then the listings.
        try:
            session.get(BASE_URL + "/", timeout=REQUEST_TIMEOUT)
        except RequestException as error:
            logging.warning(f"Homepage request failed: {error}")
        time.sleep(PAGE_DELAY)

        for group, path, sub_category in categories:
            found, ok = scrape_category(
                session, path, sub_category, args.max_pages,
                EQUIPMENT_RE if group == "equipment" else None,
            )
            if not ok:
                failed.append(path)
            for product in found:
                if product["id"] not in seen:
                    seen.add(product["id"])
                    products.append(product)
            time.sleep(PAGE_DELAY)

    if failed:
        logging.error(f"Failed categories: {', '.join(failed)}. CSV not written.")
        return 1
    if not products:
        logging.error("No products collected. CSV not written.")
        return 1

    save_to_csv(products, OUTPUT_DIR / f"sportive_{args.date}.csv")
    logging.info(f"Done. Unique products: {len(products)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
