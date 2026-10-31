"""Petzzshop (petzzshop.com) pet food and pet products scraper for TÜİK group 09.

Petzzshop runs on ikas. The product list is loaded from the storefront GraphQL API that the
site itself calls (`searchProducts`). The API key, storefront id and routing id are public and
are read from `window.__IKAS_DATA__` on the homepage. Without a category filter the API returns
the whole catalogue, 100 products per page, each with all its variants and prices.

Mapping (from the product's category slugs):
  food, treats, wet food, bird seed, fish food, rodent food  -> 0932201 (pet food)
  everything else in a pet category (litter, toys, collars, bowls, care) -> 0932204
  products outside the pet categories are dropped

Output: InflationItems/Datas/09_Recreation/Petzzshop/petzzshop_YYYY-MM-DD.csv
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


BASE_URL = "https://www.petzzshop.com"
CATEGORY_NUMBER = "9"
PET_FOOD_CODE = "0932201"
PET_OTHER_CODE = "0932204"

# Category slugs (any level of a product's category path) that make a product pet food.
FOOD_SLUGS = {
    "kedi-mamasi",
    "konserve-kedi-mamasi",
    "kedi-odul-mamasi",
    "kopek-mamasi",
    "konserve-kopek-mamasi",
    "kopek-odul-mamasi",
    "kus-yemleri",
    "kus-odul-ve-krakerleri",
    "kemirgen-yemleri",
    "balik-yemleri",
}

# Top-level category slug -> animal. Products outside these are dropped.
ANIMALS = {
    "kedi": "kedi",
    "kopek": "kopek",
    "kus": "kus",
    "balik": "balik",
    "kemirgen": "kemirgen",
    "surungen": "surungen",
}

# The reptile category has no sub-categories; its food is recognised by name.
REPTILE_FOOD_PATTERN = re.compile(r"\b(yem|yemi|yemleri|cricket|mealworm|pellet)\b", re.IGNORECASE)

# Safety net: some food is filed only under care/toy categories; recognise it by name unless the
# name also says it is a container, toy or accessory.
FOOD_NAME_PATTERN = re.compile(r"(ödül maması|odul mamasi|maması|mamasi|konservesi|yemi)", re.IGNORECASE)
NON_FOOD_NAME_PATTERN = re.compile(
    r"(kabı|kabi|kap|oyuncağ|oyuncak|saklama|kovası|matı|hazneli|kase|biberon|fırça|yatak|dispenser|besleyici|makinesi)",
    re.IGNORECASE,
)

OUTPUT_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "Petzzshop"
)

CSV_COLUMNS = [
    "product_name",
    "price",
    "category_number",
    "sub_category_number",
    "list_price",
    "brand",
    "variant",
    "animal",
    "category_path",
    "sku",
    "barcode",
    "product_url",
]

HEADERS = {"Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8"}

PAGE_DELAY = 1.5
REQUEST_TIMEOUT = 60
MAX_RETRIES = 3
DEFAULT_MAX_PAGES = 200

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("PetzzshopScraper")


def normalize(text):
    return " ".join(str(text or "").replace("\xa0", " ").split())


def fold(text):
    """Lower-case, accent-free form used only to test whether a label is already in the name."""
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return re.sub(r"[^a-z0-9]+", "", normalize(text).translate(table).lower())


def fetch_with_retry(call, description):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = call()
            if response.status_code == 200:
                return response
            logger.warning(f"HTTP {response.status_code} for {description} (attempt {attempt})")
        except (RequestException, ValueError) as error:
            logger.warning(f"Request failed for {description} (attempt {attempt}): {error}")
        time.sleep(PAGE_DELAY * attempt * 2)
    return None


def load_storefront_config(session):
    """Homepage first (cookies), then read the public API settings from __IKAS_DATA__."""
    response = fetch_with_retry(
        lambda: session.get(BASE_URL + "/", headers=HEADERS, timeout=REQUEST_TIMEOUT),
        "homepage"
    )
    if response is None:
        return None

    marker = "__IKAS_DATA__ = "
    start = response.text.find(marker)
    if start < 0:
        logger.error("__IKAS_DATA__ not found on the homepage")
        return None

    try:
        data, _ = json.JSONDecoder().raw_decode(response.text[start + len(marker):])
        config = data["storefrontConfig"]
        return {
            "api_url": config["apiUrl"],
            "headers": {
                "Content-Type": "application/json",
                "x-api-key": config["apiKey"],
                "x-sfid": config["storefrontId"],
                "x-sfrid": config["storefrontRoutingId"],
                "Origin": BASE_URL,
                "Referer": BASE_URL + "/",
            },
        }
    except (ValueError, KeyError) as error:
        logger.error(f"Could not read the storefront config: {error}")
        return None


def search_page(session, config, page):
    body = {"input": {"locale": "tr", "page": page, "showStockOption": "SHOW_ALL"}}

    def call():
        return session.post(
            config["api_url"] + "/searchProducts",
            headers=config["headers"],
            data=json.dumps(body),
            timeout=REQUEST_TIMEOUT
        )

    response = fetch_with_retry(call, f"searchProducts page {page}")
    if response is None:
        return None

    payload = response.json()
    if payload.get("errors"):
        logger.warning(f"GraphQL errors on page {page}: {str(payload['errors'])[:200]}")
        return None
    return (payload.get("data") or {}).get("searchProducts")


def classify(product):
    """Return (sub_category_number, animal, category_path) or None when the product is dropped."""
    slugs = set()
    animals = []
    paths = []
    food_paths = []

    for category in product.get("categories") or []:
        chain = list(category.get("path") or []) + [category]
        names = [item.get("name") for item in chain if item.get("name")]
        paths.append(" > ".join(names))
        if any(item.get("slug") in FOOD_SLUGS for item in chain):
            food_paths.append(paths[-1])
        for item in chain:
            if item.get("slug"):
                slugs.add(item["slug"])
        top = (chain[0].get("slug") or "")
        if top in ANIMALS and ANIMALS[top] not in animals:
            animals.append(ANIMALS[top])

    if not animals:
        return None

    if slugs & FOOD_SLUGS:
        code = PET_FOOD_CODE
    elif animals == ["surungen"] and REPTILE_FOOD_PATTERN.search(product.get("name") or ""):
        code = PET_FOOD_CODE
    elif FOOD_NAME_PATTERN.search(product.get("name") or "") and not NON_FOOD_NAME_PATTERN.search(product.get("name") or ""):
        code = PET_FOOD_CODE
    else:
        code = PET_OTHER_CODE

    chosen = (food_paths if code == PET_FOOD_CODE and food_paths else paths)
    return code, "/".join(animals), chosen[0] if chosen else ""


def variant_label(product, variant):
    """Variant option names (for example '15 Kg') for this variant."""
    values = {}
    for variant_type in product.get("productVariantTypes") or []:
        for value in (variant_type.get("variantType") or {}).get("values") or []:
            values[value.get("id")] = normalize(value.get("name"))

    labels = [
        values[item.get("variantValueId")]
        for item in variant.get("variantValues") or []
        if values.get(item.get("variantValueId"))
    ]
    return " ".join(labels)


def in_stock(variant):
    if variant.get("sellIfOutOfStock"):
        return True
    return sum((stock.get("stockCount") or 0) for stock in variant.get("stocks") or []) > 0


def format_price(value):
    return f"{float(value):.2f}"


def parse_products(results, seen_variants):
    rows = []

    for product in results:
        classification = classify(product)
        if classification is None:
            continue
        code, animal, category_path = classification

        name = normalize(product.get("name"))
        brand = normalize((product.get("brand") or {}).get("name"))
        slug = ((product.get("metaData") or {}).get("slug")) or ""

        for variant in product.get("variants") or []:
            variant_id = variant.get("id")
            if variant_id in seen_variants:
                continue
            seen_variants.add(variant_id)

            if variant.get("deleted") or variant.get("isActive") is False or not in_stock(variant):
                continue

            prices = [item for item in variant.get("prices") or [] if not item.get("priceListId")]
            if not prices:
                continue
            sell_price = prices[0].get("sellPrice")
            current = prices[0].get("discountPrice")
            if current is None:
                current = sell_price
            try:
                current = float(current)
                list_price = float(sell_price if sell_price is not None else current)
            except (TypeError, ValueError):
                continue
            if current <= 0:
                continue

            label = variant_label(product, variant)
            full_name = name
            if brand and fold(brand) not in fold(full_name):
                full_name = f"{brand} {full_name}"
            if label and fold(label) not in fold(full_name):
                full_name = f"{full_name} {label}"

            barcodes = variant.get("barcodeList") or []
            url = f"{BASE_URL}/{slug}" if slug else BASE_URL
            if slug and variant_id:
                url += f"?vid={variant_id}"

            rows.append({
                "product_name": full_name,
                "price": format_price(current),
                "category_number": CATEGORY_NUMBER,
                "sub_category_number": code,
                "list_price": format_price(list_price),
                "brand": brand,
                "variant": label,
                "animal": animal,
                "category_path": category_path,
                "sku": variant.get("sku") or "",
                "barcode": barcodes[0] if barcodes else "",
                "product_url": url,
            })

    return rows


def scrape(max_pages):
    session = requests.Session(impersonate="chrome")

    config = load_storefront_config(session)
    if config is None:
        return []

    rows = []
    seen_variants = set()
    page = 1
    total_pages = None
    seen_products = 0

    while page <= min(total_pages or max_pages, max_pages):
        time.sleep(PAGE_DELAY)
        result = search_page(session, config, page)
        if result is None:
            logger.error(f"Giving up on page {page}")
            break

        products = result.get("results") or []
        if not products:
            break

        limit = result.get("limit") or 100
        total_pages = -(-int(result.get("totalCount") or 0) // limit) or 1
        seen_products += len(products)
        rows.extend(parse_products(products, seen_variants))
        logger.info(
            f"Page {page}/{total_pages}: {len(products)} products, {len(rows)} rows kept so far"
        )
        page += 1

    logger.info(f"Read {seen_products} products")
    return rows


def write_csv(rows, date_text):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"petzzshop_{date_text}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main():
    parser = argparse.ArgumentParser(description="Petzzshop pet food and pet products scraper")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Date used in the CSV file name (YYYY-MM-DD)")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="Maximum API pages (100 products each); use a small value for a bounded run")
    args = parser.parse_args()

    rows = scrape(args.max_pages)
    if not rows:
        logger.error("No rows scraped; no CSV written")
        return 1

    path = write_csv(rows, args.date)
    food = sum(1 for row in rows if row["sub_category_number"] == PET_FOOD_CODE)
    logger.info(f"Wrote {len(rows)} rows ({food} pet food, {len(rows) - food} other pet products) to {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
