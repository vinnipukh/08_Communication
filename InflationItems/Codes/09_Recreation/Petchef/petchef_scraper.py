"""PetChef (petchef.com.tr) fresh/raw pet food scraper for TÜİK group 09.

PetChef is a T-Soft store with about 180 products. Listing pages show only the default variant
of each product and cap the list (pagination uses `?pg=`, which robots.txt disallows), so the
scraper takes the product URLs from the product sitemap (one request) and reads each product
page, which carries every variant (weight) with its price in `data-*` attributes plus the
`PRODUCT_DATA` JSON.

Prices: T-Soft `data-price` is without VAT; the selling price including VAT is
`data-price * (1 + data-vat / 100)`.

Mapping:
  food, treats, cakes, pate, soups, diet food               -> 0932201 (pet food)
  bowls, supplements (oils, calcium, collagen)             -> 0932204 (other pet products)
  books and baking moulds                                  -> dropped

Output: InflationItems/Datas/09_Recreation/Petchef/petchef_YYYY-MM-DD.csv
"""

import argparse
import csv
import html
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


BASE_URL = "https://www.petchef.com.tr"
SITEMAP_URL = BASE_URL + "/xml/sitemap/product.xml"
CATEGORY_NUMBER = "9"
PET_FOOD_CODE = "0932201"
PET_OTHER_CODE = "0932204"
BRAND = "PetChef"

DROP_PATTERN = re.compile(r"\b(kitap|book|kal[ıi]b[ıi]?|kal[ıi]p)\b", re.IGNORECASE)
BOWL_PATTERN = re.compile(r"\b(mama kasesi|mama kab[ıi]|kase|kap)\b", re.IGNORECASE)
SUPPLEMENT_PATTERN = re.compile(
    r"(\by[aâ][ğg][ıi]\b|kalsiyum|takviye|vitamin)", re.IGNORECASE
)

OUTPUT_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "Petchef"
)

CSV_COLUMNS = [
    "product_name",
    "price",
    "category_number",
    "sub_category_number",
    "list_price",
    "brand",
    "menu",
    "variant",
    "category",
    "sku",
    "product_url",
]

HEADERS = {"Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8"}

REQUEST_DELAY = 1.5
REQUEST_TIMEOUT = 40
MAX_RETRIES = 3

PRODUCT_DATA_PATTERN = re.compile(r"PRODUCT_DATA\.push\(JSON\.parse\('((?:[^'\\]|\\.)*)'\)\)")
VARIANT_TAG_PATTERN = re.compile(r"<a\b[^>]*data-subproduct-id=[^>]*>", re.IGNORECASE)
ATTRIBUTE_PATTERN = re.compile(r'(data-[\w-]+)="([^"]*)"')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("PetchefScraper")


def normalize(text):
    return " ".join(html.unescape(str(text or "")).replace("\xa0", " ").split())


def fold(text):
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return re.sub(r"[^a-z0-9]+", "", normalize(text).translate(table).lower())


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


def parse_product_data(text, url):
    """Return the PRODUCT_DATA entry of the product itself (not the related-product sliders)."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    entries = []
    for match in PRODUCT_DATA_PATTERN.finditer(text):
        raw = re.sub(r"\\([\"\\'])", r"\1", match.group(1))
        try:
            entries.append(json.loads(raw))
        except ValueError:
            continue
    for entry in entries:
        if entry.get("url") == slug:
            return entry
    return entries[0] if entries else None


def parse_variants(text, product_id):
    variants = []
    for tag in VARIANT_TAG_PATTERN.findall(text):
        attrs = dict(ATTRIBUTE_PATTERN.findall(tag))
        if attrs.get("data-pid") and str(attrs["data-pid"]) != str(product_id):
            continue
        variants.append(attrs)
    return variants


def classify(name, category):
    label = f"{name} {category}"
    if DROP_PATTERN.search(label):
        return None
    if BOWL_PATTERN.search(name):
        return PET_OTHER_CODE
    if SUPPLEMENT_PATTERN.search(name):
        return PET_OTHER_CODE
    return PET_FOOD_CODE


def with_vat(amount, vat):
    return float(amount) * (1 + float(vat) / 100)


def build_rows(url, text):
    data = parse_product_data(text, url)
    if not data:
        logger.warning(f"No PRODUCT_DATA on {url}")
        return []

    name = normalize(data.get("name"))
    category = normalize(data.get("category"))
    code = classify(name, category)
    if code is None:
        return []

    menu = normalize(data.get("brand"))
    sku = data.get("supplier_code") or data.get("code") or ""
    vat_default = data.get("vat") or 0

    full_name = name if fold(BRAND) in fold(name) else f"{BRAND} {name}"

    entries = []
    for attrs in parse_variants(text, data.get("id")):
        if attrs.get("data-instock") == "0" or attrs.get("data-stock") == "0":
            continue
        try:
            vat = attrs.get("data-vat") or vat_default
            price = with_vat(attrs["data-price"], vat)
            list_price = with_vat(attrs.get("data-not-discounted") or attrs["data-price"], vat)
        except (KeyError, ValueError):
            continue
        entries.append((normalize(attrs.get("data-type")), price, list_price, attrs.get("data-barcode") or sku))

    if not entries:
        # Product without variants: the page-level data holds the single price.
        try:
            price = float(data["total_sale_price"])
            list_price = float(data.get("total_base_price") or price)
        except (KeyError, TypeError, ValueError):
            return []
        if (data.get("quantity") or 0) <= 0:
            return []
        entries.append(("", price, list_price, sku))

    rows = []
    for label, price, list_price, entry_sku in entries:
        if price <= 0:
            continue
        row_name = full_name
        if label and fold(label) not in fold(row_name):
            row_name = f"{row_name} {label}"
        rows.append({
            "product_name": row_name,
            "price": f"{price:.2f}",
            "category_number": CATEGORY_NUMBER,
            "sub_category_number": code,
            "list_price": f"{list_price:.2f}",
            "brand": BRAND,
            "menu": menu,
            "variant": label,
            "category": category,
            "sku": entry_sku,
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
        text = fetch(session, url)
        if text is None:
            logger.warning(f"Skipping {url}")
            continue
        rows.extend(build_rows(url, text))
        if index % 20 == 0 or index == len(urls):
            logger.info(f"{index}/{len(urls)} product pages, {len(rows)} rows")

    return rows


def write_csv(rows, date_text):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"petchef_{date_text}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main():
    parser = argparse.ArgumentParser(description="PetChef pet food scraper")
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
