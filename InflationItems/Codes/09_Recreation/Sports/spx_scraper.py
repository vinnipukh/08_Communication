"""SPX (spx.com.tr) sports equipment and sports clothing scraper for TÜİK group 09.

SPX runs on Akinon: a listing URL requested with `Accept: application/json` and
`X-Requested-With: XMLHttpRequest` returns `products[]` and `pagination` as JSON.

Output: InflationItems/Datas/09_Recreation/SPX/spx_YYYY-MM-DD.csv
"""

import argparse
import csv
import logging
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


BASE_URL = "https://www.spx.com.tr"

CATEGORIES = [
    {"url": f"{BASE_URL}/erkek/ekipman/", "category_number": "9", "sub_category_number": "0922103"},
    {"url": f"{BASE_URL}/kadin/ekipman/", "category_number": "9", "sub_category_number": "0922103"},
    {"url": f"{BASE_URL}/cocuk/ekipman/", "category_number": "9", "sub_category_number": "0922103"},
    {"url": f"{BASE_URL}/kadin/tayt/", "category_number": "9", "sub_category_number": "0922107"},
]

OUTPUT_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "SPX"
)

TODAY = datetime.now().strftime("%Y-%m-%d")

HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8"
}

JSON_HEADERS = {
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
}

CSV_COLUMNS = [
    "product_name",
    "price",
    "category_number",
    "sub_category_number",
    "product_url"
]

MAX_PAGES = 60
PAGE_DELAY = 2
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


def fetch_json(session, url, page):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                url,
                params={"page": page},
                headers={**JSON_HEADERS, "Referer": url},
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            logging.warning(f"HTTP {response.status_code} for {url} page {page} (attempt {attempt})")

        except (RequestException, ValueError) as error:
            logging.warning(f"Request failed for {url} page {page} (attempt {attempt}): {error}")

        time.sleep(PAGE_DELAY * attempt * 2)

    return None


def parse_products(payload, category):
    products = []

    for item in payload.get("products") or []:
        name = " ".join(str(item.get("name") or "").split())

        try:
            price = float(item.get("price"))
        except (TypeError, ValueError):
            continue

        if not name or price <= 0:
            continue

        products.append({
            "product_name": name,
            "price": f"{price:.2f}",
            "category_number": category["category_number"],
            "sub_category_number": category["sub_category_number"],
            "product_url": urljoin(BASE_URL, item.get("absolute_url") or "")
        })

    return products


def scrape_category(session, category, max_pages):
    url = category["url"]
    products = []
    pages = 1
    page = 1

    while page <= min(pages, max_pages):
        payload = fetch_json(session, url, page)
        if payload is None:
            logging.error(f"Giving up on {url} at page {page}")
            break

        pagination = payload.get("pagination") or {}
        pages = int(pagination.get("num_pages") or 1)

        page_products = parse_products(payload, category)
        logging.info(
            f"{url} page {page}/{pages}: {len(page_products)} products "
            f"(site total {pagination.get('total_count')})"
        )

        if not page_products:
            break

        products.extend(page_products)
        page += 1
        time.sleep(PAGE_DELAY)

    return products


def save_to_csv(products, output_file):
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(products)

    logging.info(f"Saved {len(products)} products to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="SPX sports equipment (0922103) and sports clothing (0922107) scraper"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_PAGES,
        help=f"Pages per category (default: {MAX_PAGES}); use 1 for a bounded live run.",
    )
    parser.add_argument("--date", default=TODAY, help="Output date (default: today)")
    args = parser.parse_args()

    all_products = []
    seen_urls = set()

    with requests.Session(impersonate="chrome") as session:
        session.headers.update(HEADERS)

        # Homepage first, then the JSON listing calls.
        try:
            session.get(BASE_URL + "/", timeout=REQUEST_TIMEOUT)
        except RequestException as error:
            logging.warning(f"Homepage request failed: {error}")
        time.sleep(PAGE_DELAY)

        for category in CATEGORIES:
            for product in scrape_category(session, category, args.max_pages):
                key = product["product_url"] or product["product_name"]
                if key not in seen_urls:
                    seen_urls.add(key)
                    all_products.append(product)

    if all_products:
        save_to_csv(all_products, OUTPUT_DIR / f"spx_{args.date}.csv")
    else:
        logging.warning("No products collected. Existing CSV was not overwritten.")

    logging.info(f"Scraping completed. Total unique products: {len(all_products)}")


if __name__ == "__main__":
    main()
