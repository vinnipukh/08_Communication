"""Temiz Mama (temizmama.com) pet food scraper for TÜİK group 09.

Temiz Mama is a Next.js store with about 95 products. The category lists are loaded through
`/api/` (disallowed by robots.txt) and the JSON-LD on a category page holds only the first ten
items, so the scraper takes the product URLs from `sitemap-products.xml` (one request) and
reads each product page. The page embeds every variant (package size) of the product in its
React Server Components payload (`self.__next_f.push`): `variantEcommerceTitle`,
`variantPrice` (selling price including VAT), `variantOldPrice` (list price, 0 when none) and
availability. No `/api/` or `/_next/` URL is requested.

Mapping (from the first segment of the product URL, which is the site category):
  *-mamasi, yas-mamasi, odul-mamasi, atistirmalik-odul, odul-cubugu, cigneme-kemigi -> 0932201
  takviye (pastes, shampoo, cleaners), litter, toys, toilets, accessories               -> 0932204
  anything unknown is dropped and logged

Output: InflationItems/Datas/09_Recreation/TemizMama/temizmama_YYYY-MM-DD.csv
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
from urllib.parse import urlparse

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


BASE_URL = "https://www.temizmama.com"
SITEMAP_URL = BASE_URL + "/sitemap-products.xml"
CATEGORY_NUMBER = "9"
PET_FOOD_CODE = "0932201"
PET_OTHER_CODE = "0932204"

FOOD_SEGMENT_PATTERN = re.compile(r"(mamasi|odul|atistirmalik|cigneme|kemik)")
OTHER_SEGMENT_PATTERN = re.compile(r"(takviye|kum|oyuncak|tuvalet|aksesuar)")

OUTPUT_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "TemizMama"
)

CSV_COLUMNS = [
    "product_name",
    "price",
    "category_number",
    "sub_category_number",
    "list_price",
    "brand",
    "variant",
    "site_category",
    "status",
    "barcode",
    "product_url",
]

HEADERS = {"Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8"}

REQUEST_DELAY = 1.5
REQUEST_TIMEOUT = 40
MAX_RETRIES = 3

FLIGHT_CHUNK_PATTERN = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
VARIANT_START_PATTERN = re.compile(r'\{"productId":\d+,"variantId":\d+')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("TemizMamaScraper")


def normalize(text):
    return " ".join(str(text or "").replace("\xa0", " ").split())


def fetch(session, url):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.text
            if response.status_code == 404:
                return None
            logger.warning(f"HTTP {response.status_code} for {url} (attempt {attempt})")
        except RequestException as error:
            logger.warning(f"Request failed for {url} (attempt {attempt}): {error}")
        time.sleep(REQUEST_DELAY * attempt * 2)
    return None


def product_urls(session):
    text = fetch(session, SITEMAP_URL)
    if not text:
        return []
    return re.findall(r"<loc>\s*(.*?)\s*</loc>", text)


def flight_text(page):
    chunks = []
    for raw in FLIGHT_CHUNK_PATTERN.findall(page):
        try:
            chunks.append(json.loads('"' + raw + '"'))
        except ValueError:
            continue
    return "".join(chunks)


def page_variants(page, detail_path):
    """Variant objects of this product embedded in the page payload, de-duplicated."""
    text = flight_text(page)
    decoder = json.JSONDecoder()
    variants = {}
    for match in VARIANT_START_PATTERN.finditer(text):
        try:
            item, _ = decoder.raw_decode(text[match.start():])
        except ValueError:
            continue
        if item.get("productDetailUrl") != detail_path:
            continue
        variants.setdefault(item["variantId"], item)
    return list(variants.values())


def classify(segment):
    if FOOD_SEGMENT_PATTERN.search(segment):
        return PET_FOOD_CODE
    if OTHER_SEGMENT_PATTERN.search(segment):
        return PET_OTHER_CODE
    return None


def build_rows(url, page):
    detail_path = urlparse(url).path.strip("/")
    segment = detail_path.split("/")[0]
    code = classify(segment)
    if code is None:
        logger.info(f"Dropped (unmapped category '{segment}'): {url}")
        return []

    rows = []
    for variant in page_variants(page, detail_path):
        if not variant.get("variantActive") or not variant.get("variantAvailableForSale"):
            continue
        try:
            price = float(variant["variantPrice"])
        except (KeyError, TypeError, ValueError):
            continue
        if price <= 0:
            continue
        old_price = float(variant.get("variantOldPrice") or 0)
        list_price = old_price if old_price > price else price

        name = normalize(variant.get("variantEcommerceTitle")) or normalize(
            f"{variant.get('productTitle')} {variant.get('variantTitle')}"
        )
        rows.append({
            "product_name": name,
            "price": f"{price:.2f}",
            "category_number": CATEGORY_NUMBER,
            "sub_category_number": code,
            "list_price": f"{list_price:.2f}",
            "brand": normalize(variant.get("variantBrandName")),
            "variant": normalize(variant.get("variantTitle")),
            "site_category": segment,
            "status": normalize(variant.get("variantStatus")),
            "barcode": variant.get("variantBarcode") or "",
            "product_url": url,
        })
    return rows


def scrape(limit):
    session = requests.Session(impersonate="chrome")

    if fetch(session, BASE_URL + "/") is None:
        logger.error("Homepage request failed")
        return []

    time.sleep(REQUEST_DELAY)
    urls = product_urls(session)
    logger.info(f"{len(urls)} product URLs in the sitemap")
    if limit:
        urls = urls[:limit]

    rows = []
    for index, url in enumerate(urls, start=1):
        time.sleep(REQUEST_DELAY)
        page = fetch(session, url)
        if page is None:
            logger.warning(f"Skipping {url}")
            continue
        product_rows = build_rows(url, page)
        if not product_rows:
            logger.info(f"No sellable variants: {url}")
        rows.extend(product_rows)
        if index % 20 == 0 or index == len(urls):
            logger.info(f"{index}/{len(urls)} product pages, {len(rows)} rows")

    return rows


def write_csv(rows, date_text):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"temizmama_{date_text}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main():
    parser = argparse.ArgumentParser(description="Temiz Mama pet food scraper")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Date used in the CSV file name (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=0, help="Read only the first N product pages (bounded run); 0 means all")
    args = parser.parse_args()

    rows = scrape(args.limit)
    if not rows:
        logger.error("No rows scraped; no CSV written")
        return 1

    path = write_csv(rows, args.date)
    food = sum(1 for row in rows if row["sub_category_number"] == PET_FOOD_CODE)
    logger.info(f"Wrote {len(rows)} rows ({food} pet food, {len(rows) - food} other pet products) to {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
