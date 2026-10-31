import argparse
import html
import csv
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from curl_cffi import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("ToyzzShopScraper")

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = next((p for p in BASE_DIR.parents if (p / ".git").exists()), BASE_DIR)
DATA_DIR = PROJECT_ROOT / "InflationItems" / "Datas" / "09_Recreation" / "ToyzzShop"

BASE_URL = "https://www.toyzzshop.com"
# The storefront is a JS app; listings come from this JSON API (same calls the site makes).
API_URL = "https://core.toyzzshop.com/api/categories/{category_id}/products"
API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": BASE_URL,
    "Referer": BASE_URL + "/",
}
CATEGORY_NUMBER = "9"
OTHER_TOYS_SUB_CATEGORY_NUMBER = "0921204"
WHEELED_TOYS_SUB_CATEGORY_NUMBER = "0921207"

# category_id comes from https://core.toyzzshop.com/api/categories/menu (id <-> slug).
CATEGORIES = {
    "board_games": {
        "slug": "kutu-oyunlari",
        "category_id": 90,
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "hobby_toys": {
        "slug": "hobi-oyuncaklari",
        "category_id": 62,
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "plush_toys": {
        "slug": "pelus-oyuncaklar",
        "category_id": 11,
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "dolls": {
        "slug": "oyuncak-bebekler-ve-aksesuarlari",
        "category_id": 6,
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "building_toys": {
        "slug": "yapim-oyuncaklari-lego",
        "category_id": 5,
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "baby_toys": {
        "slug": "bebek-oyuncaklari",
        "category_id": 30,
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "educational_toys": {
        "slug": "egitici-oyuncaklar",
        "category_id": 19,
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "model_toy_cars": {
        "slug": "oyuncak-araba/model-arabalar-ve-araclar",
        "category_id": 52,
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "remote_control_toys": {
        "slug": "oyuncak-araba/kumandali-arabalar",
        "category_id": 53,
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "scooters": {
        "slug": "scooter",
        "category_id": 96,
        "sub_category_number": WHEELED_TOYS_SUB_CATEGORY_NUMBER
    },
    "battery_vehicles": {
        "slug": "akulu-araclar",
        "category_id": 93,
        "sub_category_number": WHEELED_TOYS_SUB_CATEGORY_NUMBER
    },
    "pedal_vehicles": {
        "slug": "pedalli-araclar",
        "category_id": 94,
        "sub_category_number": WHEELED_TOYS_SUB_CATEGORY_NUMBER
    },
    "ride_on_vehicles": {
        "slug": "pedalsiz-surmeli-araclar",
        "category_id": 98,
        "sub_category_number": WHEELED_TOYS_SUB_CATEGORY_NUMBER
    },
    "three_wheel_bikes": {
        "slug": "bisiklet/3-tekerlekli-bisiklet",
        "category_id": 1204,
        "sub_category_number": WHEELED_TOYS_SUB_CATEGORY_NUMBER
    },
    "skates_skateboards": {
        "slug": "kaykay-paten",
        "category_id": 97,
        "sub_category_number": WHEELED_TOYS_SUB_CATEGORY_NUMBER
    }
}

MAX_PAGES = 120
PAGE_SIZE = 48
REQUEST_DELAY = 1.5
REQUEST_TIMEOUT = 40
MAX_RETRIES = 3


DEFAULT_OTHER_TOYS_LIMIT = 15000
DEFAULT_WHEELED_TOYS_LIMIT = 15000


DEFAULT_SCAN_LIMIT_PER_CATEGORY = 1500

BADGE_PATTERNS = [
    r"^Sadece Toyzz Shop'ta\s*",
    r"^İnternete Özel Fiyat\s*",
    r"^İnternette Tükendi\s*",
    r"^Yeni\s*",
    r"^Fırsat\s*"
]


def normalize_text(text):
    value = " ".join(text.replace("\xa0", " ").split())
    value = re.sub(r"\s*([.,])\s*(?=\d)", r"\1", value)
    return value.strip()


def clean_name(text):
    value = normalize_text(text)


    for _ in range(5):
        decoded = html.unescape(value)
        if decoded == value:
            break
        value = decoded

    for _ in range(6):
        previous = value
        for pattern in BADGE_PATTERNS:
            value = re.sub(pattern, "", value, flags=re.IGNORECASE).strip()
        if value == previous:
            break

    value = re.sub(r"\s*%\s*\d+\s*$", "", value).strip()
    return value


def canonical_product_key(name):

    value = clean_name(name).casefold()
    value = value.replace("_", " ")
    value = re.sub(r"(?<=\d)\s*[,]\s*(?=\d)", ".", value)
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def new_session():
    session = requests.Session(impersonate="chrome")
    # Homepage first, so the API calls come from a session that loaded the site.
    response = session.get(BASE_URL + "/", timeout=REQUEST_TIMEOUT)
    logger.info("Homepage HTTP status: %s", response.status_code)
    return session


def fetch_products_page(session, category_id, page_number):
    url = API_URL.format(category_id=category_id)
    params = {"limit": PAGE_SIZE, "order": "ocd", "page": page_number}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, params=params, headers=API_HEADERS, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.json()
            logger.warning("API HTTP %s for category %s page %d (attempt %d)",
                           response.status_code, category_id, page_number, attempt)
        except Exception as exc:
            logger.warning("API request failed for category %s page %d (attempt %d): %s",
                           category_id, page_number, attempt, exc)
        time.sleep(REQUEST_DELAY * attempt * 2)
    return None


def parse_products(payload, sub_category_number):
    items = []
    for product in (payload.get("payload") or {}).get("products") or []:
        name = clean_name(product.get("title") or product.get("product_name") or "")
        price = (product.get("price") or {}).get("original")
        serial_id = product.get("serial_id")
        if not name or len(name) < 3 or not isinstance(price, (int, float)) or price <= 0:
            continue
        items.append({
            "product_name": name,
            "price": float(price),
            "category_number": CATEGORY_NUMBER,
            "sub_category_number": sub_category_number,
            "_product_url": f"{BASE_URL}/{product.get('slug', '')}?serial={serial_id}"
        })
    return items


def scrape_category(session, category_name, category_id, sub_category_number, max_pages, limit_per_category=0):
    results = []
    seen_urls = set()
    logger.info("Starting category: %s (id %s)", category_name, category_id)
    page_count = max_pages
    for page_number in range(1, max_pages + 1):
        if page_number > page_count:
            break
        payload = fetch_products_page(session, category_id, page_number)
        if payload is None:
            logger.warning("%s page %d: no API response, stopping category", category_name, page_number)
            break
        pagination = payload.get("pagination") or {}
        if page_number == 1:
            page_count = min(max_pages, int(pagination.get("pageCount") or 1))
            logger.info("%s: site reports %s products on %d pages",
                        category_name, pagination.get("total"), page_count)
        products = parse_products(payload, sub_category_number)
        if not products:
            logger.warning("%s page %d: parsed 0 products", category_name, page_number)
            break
        new_count = 0
        for product in products:
            if limit_per_category > 0 and len(results) >= limit_per_category:
                break
            product_url = product["_product_url"]
            if product_url in seen_urls:
                continue
            seen_urls.add(product_url)
            results.append(product)
            new_count += 1
        logger.info("%s page %d/%d: %d products, %d new, total=%d",
                    category_name, page_number, page_count, len(products), new_count, len(results))
        if limit_per_category > 0 and len(results) >= limit_per_category:
            logger.info("%s: reached scan limit %d", category_name, limit_per_category)
            break
        if new_count == 0:
            break
        time.sleep(REQUEST_DELAY)
    logger.info("%s: extracted %d unique products", category_name, len(results))
    return results


def round_robin_unique(category_results, total_limit, global_urls=None, global_keys=None):

    global_urls = global_urls if global_urls is not None else set()
    global_keys = global_keys if global_keys is not None else set()

    selected = []
    local_urls = set()
    local_keys = set()

    category_names = list(category_results.keys())
    positions = {name: 0 for name in category_names}

    active = list(category_names)

    while active:
        progressed = False
        next_active = []

        for category_name in active:
            items = category_results[category_name]
            pos = positions[category_name]

            while pos < len(items):
                item = items[pos]
                pos += 1

                product_url = item.get("_product_url")
                product_key = canonical_product_key(item.get("product_name", ""))

                if not product_key:
                    continue

                if product_url and (
                    product_url in global_urls or product_url in local_urls
                ):
                    continue

                if product_key in global_keys or product_key in local_keys:
                    continue

                selected.append(item)

                if product_url:
                    local_urls.add(product_url)
                local_keys.add(product_key)

                progressed = True
                break

            positions[category_name] = pos

            if pos < len(items):
                next_active.append(category_name)

            if total_limit > 0 and len(selected) >= total_limit:
                global_urls.update(local_urls)
                global_keys.update(local_keys)
                return selected

        if not progressed:
            break

        active = next_active

    global_urls.update(local_urls)
    global_keys.update(local_keys)
    return selected


def dedupe_rows(data):
    unique = []
    seen_urls = set()
    seen_keys = set()

    for item in data:
        product_url = item.get("_product_url")
        product_key = canonical_product_key(item.get("product_name", ""))

        if product_url and product_url in seen_urls:
            continue
        if not product_key or product_key in seen_keys:
            continue

        if product_url:
            seen_urls.add(product_url)
        seen_keys.add(product_key)
        unique.append(item)

    return unique


def save_to_csv(data, date_str):
    data = dedupe_rows(data)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_file = DATA_DIR / f"toyzzshop_{date_str}.csv"
    with open(output_file, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["product_name", "price", "category_number", "sub_category_number"])
        for item in sorted(data, key=lambda x: (x["sub_category_number"], clean_name(x["product_name"]).casefold())):
            final_name = clean_name(item["product_name"])

            writer.writerow([
                final_name,
                f'{item["price"]:.2f}',
                item["category_number"],
                item["sub_category_number"]
            ])
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Toyzz Shop balanced scraper (JSON API via curl_cffi)"
    )
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)

    parser.add_argument(
        "--other-limit",
        type=int,
        default=DEFAULT_OTHER_TOYS_LIMIT,
        help=f"Maximum final products for {OTHER_TOYS_SUB_CATEGORY_NUMBER} "
             f"(default: {DEFAULT_OTHER_TOYS_LIMIT})",
    )
    parser.add_argument(
        "--wheeled-limit",
        type=int,
        default=DEFAULT_WHEELED_TOYS_LIMIT,
        help=f"Maximum final products for {WHEELED_TOYS_SUB_CATEGORY_NUMBER} "
             f"(default: {DEFAULT_WHEELED_TOYS_LIMIT})",
    )
    parser.add_argument(
        "--scan-limit-per-category",
        type=int,
        default=DEFAULT_SCAN_LIMIT_PER_CATEGORY,
        help=(
            "Maximum candidate products scraped from each Toyzz Shop source "
            f"category before balancing (default: {DEFAULT_SCAN_LIMIT_PER_CATEGORY}; "
            "0 = no source-category cap)"
        ),
    )

    parser.add_argument(
        "--limit-per-category",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    if args.other_limit < 0 or args.wheeled_limit < 0:
        parser.error("--other-limit and --wheeled-limit must be >= 0")
    if args.max_pages < 1:
        parser.error("--max-pages must be >= 1")
    if args.scan_limit_per_category < 0:
        parser.error("--scan-limit-per-category must be >= 0")
    if args.limit_per_category is not None and args.limit_per_category < 0:
        parser.error("--limit-per-category must be >= 0")

    scan_limit = (
        args.limit_per_category
        if args.limit_per_category is not None
        else args.scan_limit_per_category
    )

    date_str = args.date or datetime.today().strftime("%Y-%m-%d")


    candidates = {
        OTHER_TOYS_SUB_CATEGORY_NUMBER: {},
        WHEELED_TOYS_SUB_CATEGORY_NUMBER: {},
    }

    session = new_session()

    for category_name, category in CATEGORIES.items():
        items = scrape_category(
            session=session,
            category_name=category_name,
            category_id=category["category_id"],
            sub_category_number=category["sub_category_number"],
            max_pages=args.max_pages,
            limit_per_category=scan_limit,
        )

        candidates[
            category["sub_category_number"]
        ][category_name] = items
        time.sleep(REQUEST_DELAY)


    global_urls = set()
    global_keys = set()

    other_selected = round_robin_unique(
        candidates[OTHER_TOYS_SUB_CATEGORY_NUMBER],
        args.other_limit,
        global_urls=global_urls,
        global_keys=global_keys,
    )

    wheeled_selected = round_robin_unique(
        candidates[WHEELED_TOYS_SUB_CATEGORY_NUMBER],
        args.wheeled_limit,
        global_urls=global_urls,
        global_keys=global_keys,
    )

    selected = other_selected + wheeled_selected
    selected = dedupe_rows(selected)

    if not selected:
        logger.error("No products scraped")
        sys.exit(1)


    output_file = save_to_csv(selected, date_str)

    print()
    print("----------------------------")
    print("Scraping completed.")
    print("Other toys:", len(other_selected))
    print("Wheeled toys:", len(wheeled_selected))
    print("Total unique products:", len(selected))
    print("Other output limit:", args.other_limit)
    print("Wheeled output limit:", args.wheeled_limit)
    print("Source scan limit/category:", scan_limit if scan_limit > 0 else "none")
    print("File:", output_file)
    print("----------------------------")


if __name__ == "__main__":
    main()
