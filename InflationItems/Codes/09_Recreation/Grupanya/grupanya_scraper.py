"""Grupanya (grupanya.com) deal scraper for TÜİK group 09.

Recreation and hobby services (0946103) and sports training fees (0946203) from
the deal site's activity and course categories.

Every category listing answers `GET <category-path>?handler=MoreDeals&p=N` with
JSON `deals[]` (title, dealPrice, dealValue, categoryName, locationName, ...),
`hasMore` and `isFallback`. A deal is mapped by its own `categoryName` (plus a
few title keywords), not by the listing it was found in, because the parent
listings also carry breakfast, spa and tour deals.

Output: InflationItems/Datas/09_Recreation/Grupanya/grupanya_YYYY-MM-DD.csv
"""

import argparse
import csv
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


BASE_URL = "https://www.grupanya.com"

CITIES = {
    "istanbul": "İstanbul",
    "ankara": "Ankara",
    "izmir": "İzmir",
}

# Parent listings first, then the subcategory listings (they add deals that the
# parent listing can miss). A city/subcategory combination without deals
# returns `isFallback: true` with unrelated deals; those pages are skipped.
CATEGORY_SLUGS = [
    "aktivite-eglence",
    "spor-egitim-kurs",
    "eglence-merkezi",
    "akvaryum-tema-park",
    "sanal-gerceklik-kacis",
    "poligon-paintball",
    "binicilik-parkur",
    "rafting-yamac-parasutu",
    "su-sporlari",
    "atolye",
    "pilates",
    "fitness-gym",
    "yoga-nefes-terapisi",
    "dans-muzik",
]

RECREATION = "0946103"
SPORTS_TRAINING = "0946203"

# Grupanya `categoryName` -> sub_category_number. Categories not listed here
# (breakfast, spa, massage, pool/beach day passes, online/vocational courses,
# tours, discount vouchers, ...) are dropped.
CATEGORY_MAP = {
    "Eğlence Merkezi": RECREATION,
    "Akvaryum - Tema Park": RECREATION,
    "Sanal Gerçeklik - Kaçış": RECREATION,
    "Poligon - Paintball": RECREATION,
    "Binicilik - Parkur": RECREATION,
    "Rafting - Yamaç Paraşütü": RECREATION,
    "Su Sporları": RECREATION,
    "Atölye": RECREATION,
    "Dans - Müzik": RECREATION,
    "Pilates": SPORTS_TRAINING,
    "Fitness - Gym": SPORTS_TRAINING,
    "Fitness": SPORTS_TRAINING,
    "Yoga - Nefes Terapisi": SPORTS_TRAINING,
}

# Dance lessons in "Dans - Müzik" are sports training; music lessons stay hobby.
DANCE_RE = re.compile(r"dans|dance|zumba|bale|salsa|tango|bachata|hip ?hop|k-pop", re.IGNORECASE)

# A sports lesson/course inside a recreation category (riding, cycling, diving ...).
SPORT_LESSON_RE = re.compile(
    r"(binicilik|at binme|bisiklet|yüzme|dalış|sörf|surf|kayak|tenis|boks|karate|judo|"
    r"taekwondo|okçuluk|kick ?boks|muay thai)\w*(?:\W+\w+){0,4}?\W+(eğitim|ders|kurs)",
    re.IGNORECASE,
)

OUTPUT_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "Grupanya"
)

TODAY = datetime.now().strftime("%Y-%m-%d")

HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8"
}

JSON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
}

CSV_COLUMNS = [
    "product_name",
    "price",
    "category_number",
    "sub_category_number",
    "list_price",
    "grupanya_category",
    "merchant",
    "location",
    "city",
    "deal_id",
    "product_url",
]

MAX_PAGES = 20
PAGE_DELAY = 2
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


def clean(text):
    return " ".join(str(text or "").split())


def fetch_page(session, url, page):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                url,
                params={"handler": "MoreDeals", "p": page},
                headers={**JSON_HEADERS, "Referer": url},
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                logging.info(f"HTTP 404 for {url} (no such listing)")
                return None
            logging.warning(f"HTTP {response.status_code} for {url} page {page} (attempt {attempt})")

        except (RequestException, ValueError) as error:
            logging.warning(f"Request failed for {url} page {page} (attempt {attempt}): {error}")

        time.sleep(PAGE_DELAY * attempt * 2)

    return None


def sub_category_for(deal):
    code = CATEGORY_MAP.get(clean(deal.get("categoryName")))
    if code is None:
        return None

    title = clean(deal.get("title"))
    if deal.get("categoryName") == "Dans - Müzik" and DANCE_RE.search(title):
        return SPORTS_TRAINING
    if code == RECREATION and SPORT_LESSON_RE.search(title):
        return SPORTS_TRAINING
    return code


def in_city(location, city_label):
    """True when the deal is located in the scraped city.

    `locationName` is "District / Province", a bare district/city name, or a
    comma-separated list of departure cities (tours, transfers); the list form
    and other provinces are rejected.
    """
    location = clean(location)
    if not location:
        return True
    if "," in location:
        return False
    if "/" in location:
        return location.rsplit("/", 1)[1].strip() == city_label
    return True


def deal_prices(deal):
    """Return (paid price, list price) or None for deals without a real price.

    A deal with `dealValue` 0 sells a token booking fee (e.g. 19.90 TL), not the
    service, unless voucher pricing carries the real amounts.
    """
    try:
        price = float(deal.get("dealPrice") or 0)
        list_price = float(deal.get("dealValue") or 0)
    except (TypeError, ValueError):
        return None

    if deal.get("hasVoucherPricing"):
        try:
            voucher_price = float(deal.get("voucherDiscountedPrice") or 0)
            voucher_base = float(deal.get("voucherBasePrice") or 0)
        except (TypeError, ValueError):
            voucher_price = voucher_base = 0
        if voucher_price > 0:
            return voucher_price, voucher_base or None

    if deal.get("hideDealPrice") or price <= 0 or list_price <= 0:
        return None
    return price, list_price


def parse_deal(deal, city_slug):
    if deal.get("isSoldOut") or deal.get("isActive") is False:
        return None

    code = sub_category_for(deal)
    if code is None:
        return None

    city_label = CITIES[city_slug]
    if not in_city(deal.get("locationName"), city_label):
        return None

    prices = deal_prices(deal)
    if prices is None:
        return None
    price, list_price = prices

    title = clean(deal.get("title"))
    if not title:
        return None

    detail_url = deal.get("detailUrl") or ""
    return {
        "product_name": f"Grupanya {city_label}: {title}",
        "price": f"{price:.2f}",
        "category_number": "9",
        "sub_category_number": code,
        "list_price": f"{list_price:.2f}" if list_price else "",
        "grupanya_category": clean(deal.get("categoryName")),
        "merchant": clean(deal.get("merchantName")),
        "location": clean(deal.get("locationName")),
        "city": city_label,
        "deal_id": deal.get("id"),
        "product_url": f"{BASE_URL}{detail_url}" if detail_url.startswith("/") else detail_url,
    }


def scrape_listing(session, city_slug, category_slug, max_pages):
    url = f"{BASE_URL}/{category_slug}/{city_slug}"
    deals = []
    page = 1

    while page <= max_pages:
        payload = fetch_page(session, url, page)
        time.sleep(PAGE_DELAY)
        if payload is None:
            break

        if payload.get("isFallback"):
            logging.info(f"{url}: no deals of its own (fallback list), skipped")
            break

        page_deals = (payload.get("deals") or []) + (payload.get("sponsoredDeals") or [])
        logging.info(
            f"{url} page {page}: {len(page_deals)} deals (site total {payload.get('totalCount')})"
        )
        if not page_deals:
            break

        deals.extend(page_deals)
        if not payload.get("hasMore"):
            break
        page += 1

    return deals


def save_to_csv(rows, output_file):
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    logging.info(f"Saved {len(rows)} rows to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Grupanya recreation/hobby (0946103) and sports training (0946203) deal scraper"
    )
    parser.add_argument(
        "--cities",
        default=",".join(CITIES),
        help=f"Comma-separated city slugs (default: {','.join(CITIES)})",
    )
    parser.add_argument(
        "--categories",
        type=int,
        default=len(CATEGORY_SLUGS),
        help="Use only the first N category listings per city (bounded live run, e.g. 2).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_PAGES,
        help=f"Pages per listing (default: {MAX_PAGES}); use 1 for a bounded live run.",
    )
    parser.add_argument("--date", default=TODAY, help="Output date (default: today)")
    args = parser.parse_args()

    cities = [c.strip() for c in args.cities.split(",") if c.strip()]
    unknown = [c for c in cities if c not in CITIES]
    if unknown:
        parser.error(f"Unknown city slug(s): {', '.join(unknown)}")

    rows = []
    seen_ids = set()
    started = time.time()

    with requests.Session(impersonate="chrome") as session:
        session.headers.update(HEADERS)

        # Homepage first, then the JSON listing calls.
        try:
            session.get(BASE_URL + "/", timeout=REQUEST_TIMEOUT)
        except RequestException as error:
            logging.warning(f"Homepage request failed: {error}")
        time.sleep(PAGE_DELAY)

        for city_slug in cities:
            for category_slug in CATEGORY_SLUGS[: args.categories]:
                for deal in scrape_listing(session, city_slug, category_slug, args.max_pages):
                    deal_id = deal.get("id")
                    if deal_id in seen_ids:
                        continue
                    row = parse_deal(deal, city_slug)
                    if row is None:
                        continue
                    seen_ids.add(deal_id)
                    rows.append(row)

    if rows:
        save_to_csv(rows, OUTPUT_DIR / f"grupanya_{args.date}.csv")
    else:
        logging.warning("No deals collected. Existing CSV was not overwritten.")

    counts = {}
    for row in rows:
        counts[row["sub_category_number"]] = counts.get(row["sub_category_number"], 0) + 1
    logging.info(f"Scraping completed in {time.time() - started:.0f} s. Rows per code: {counts}")


if __name__ == "__main__":
    main()
