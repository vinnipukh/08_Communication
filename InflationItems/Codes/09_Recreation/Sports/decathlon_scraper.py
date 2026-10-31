import argparse
import csv
import logging
import os
import re
import time

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from curl_cffi import requests
from curl_cffi.requests.exceptions import HTTPError, RequestException


BASE_URL = "https://www.decathlon.com.tr"

CATEGORY_NUMBER = "9"

# (group, listing path, COICOP code, page cap). Clothing paths come from the
# category-product-listing sitemap; the cap keeps a full run under ~25 minutes
# (10 s per page): 33 fitness pages + at most 51 clothing pages.
CATEGORIES = [
    ("fitness", "ekipmanlar/evde-spor-aletleri", "0922102", 60),
    ("clothing", "tum-sporlar/kosu/kosu-ve-yuruyus-kiyafetleri", "0922107", 8),
    ("clothing", "tum-sporlar/fitness-kardiyo/tum-fitness-kiyafetleri", "0922107", 9),
    ("clothing", "tum-sporlar/bisiklet/bisikletci-kiyafetleri", "0922107", 4),
    ("clothing", "tum-sporlar/yuzme/yuzme-kiyafetleri", "0922107", 16),
    ("clothing", "tum-sporlar/kayak-snowboard/kayak-snowboard-kiyafet-ve-giyim", "0922107", 7),
    ("clothing", "tum-sporlar/hiking-trekking-outdoor/giyim", "0922107", 12),
    ("clothing", "tum-sporlar/yoga/yoga-kiyafetleri", "0922107", 2),
]

PAGE_SIZE = 40
REQUEST_DELAY = 10
REQUEST_TIMEOUT = 30

# Cloudflare (__cf_bm) answers 403 to python-requests; curl_cffi Chrome impersonation passes.
HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"
}

CSV_COLUMNS = [
    "product_name",
    "price",
    "category_number",
    "sub_category_number",
    "product_url"
]

SCRIPT_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = (
    SCRIPT_DIR.parent.parent.parent
    / "Datas"
    / "09_Recreation"
    / "Decathlon"
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / f"decathlon_{datetime.now():%Y-%m-%d}.csv"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("decathlon")


def normalize_price(text):
    if not text:
        return None

    match = re.search(
        r"₺\s*([\d.,]+)",
        text
    )

    if not match:
        return None

    value = match.group(1)

    if "," in value:
        value = value.replace(".", "").replace(",", ".")

    elif "." in value:
        parts = value.split(".")

        if len(parts[-1]) == 3:
            value = value.replace(".", "")

    try:
        price = Decimal(value)

        if not price.is_finite() or price < 0:
            return None

        return f"{price:.2f}"

    except InvalidOperation:
        return None


def normalize_url(href):
    url = urljoin(BASE_URL, href)

    parsed = urlsplit(url)

    return urlunsplit((
        parsed.scheme,
        parsed.netloc.lower(),
        parsed.path.rstrip("/"),
        "",
        ""
    ))


def extract_product(card, category_code):
    heading = card.select_one("h2")

    if heading is None:
        return None

    name = heading.get_text(" ", strip=True)

    if not name:
        return None

    link = heading.select_one("a[href]")

    if link is None:
        link = card.select_one("a[href]")

    if link is None:
        return None

    product_url = normalize_url(link["href"])

    if not product_url.startswith(BASE_URL + "/"):
        return None

    price_label = card.find(
        "span",
        class_="sr-only",
        string=lambda text: (
            text is not None
            and "güncel fiyat" in text.casefold()
        )
    )

    if price_label is None:
        return None

    price_text = price_label.parent.get_text(
        " ",
        strip=True
    )

    price = normalize_price(price_text)

    if price is None:
        return None

    return {
        "product_name": name,
        "price": price,
        "category_number": CATEGORY_NUMBER,
        "sub_category_number": category_code,
        "product_url": product_url
    }


def product_key(product):
    return (
        product["product_url"],
        product["product_name"].strip().casefold()
    )


def load_existing_products():
    if not OUTPUT_FILE.exists():
        return []

    with open(
        OUTPUT_FILE,
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as file:
        reader = csv.DictReader(file)

        if reader.fieldnames != CSV_COLUMNS:
            raise ValueError(
                "Today's CSV uses an older format. "
                "It has not been modified. "
                "The required columns are: "
                + ", ".join(CSV_COLUMNS)
            )

        products = list(reader)

    for product in products:
        if not all(
            str(product.get(column, "")).strip()
            for column in CSV_COLUMNS
        ):
            raise ValueError(
                "Existing CSV contains incomplete records."
            )

    return products


def save_csv(products):
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    temporary_file = OUTPUT_FILE.with_name(
        OUTPUT_FILE.name + ".tmp"
    )

    try:
        with open(
            temporary_file,
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=CSV_COLUMNS
            )

            writer.writeheader()
            writer.writerows(products)

            file.flush()
            os.fsync(file.fileno())

        os.replace(
            temporary_file,
            OUTPUT_FILE
        )

    finally:
        if temporary_file.exists():
            temporary_file.unlink()


def fetch_page(session, category_url, category_code, page_number):
    offset = (page_number - 1) * PAGE_SIZE

    logger.info(
        "Fetching page %s | Offset: %s",
        page_number,
        offset
    )

    try:
        response = session.get(
            category_url,
            params={
                "from": offset,
                "size": PAGE_SIZE
            },
            timeout=REQUEST_TIMEOUT
        )

    except RequestException as error:
        logger.error(
            "Request failed: %s",
            error
        )

        return None, "request_error"

    logger.info(
        "HTTP %s | %s",
        response.status_code,
        response.url
    )

    if response.status_code == 429:
        logger.warning(
            "Rate limited. Retry-After: %s",
            response.headers.get(
                "Retry-After",
                "not provided"
            )
        )

        return None, "rate_limited"

    if response.status_code == 403:
        logger.error("Access forbidden.")
        return None, "forbidden"

    try:
        response.raise_for_status()

    except HTTPError as error:
        logger.error(
            "HTTP error: %s",
            error
        )

        return None, "http_error"

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    cards = soup.select(".product-card")

    products = []
    failed = 0

    for card in cards:
        product = extract_product(card, category_code)

        if product is None:
            failed += 1
        else:
            products.append(product)

    logger.info(
        "Cards: %s | Extracted: %s | Failed: %s",
        len(cards),
        len(products),
        failed
    )

    if failed:
        logger.error(
            "Page %s has %s extraction failures.",
            page_number,
            failed
        )

        return None, "extraction_incomplete"

    return products, "success"


def scrape_category(session, url, code, max_pages, all_products, products_by_key):
    stats = {"pages": 0, "cards": 0, "new": 0, "duplicates": 0}
    stop_reason = "maximum_pages"
    previous_page_keys = None

    for page_number in range(1, max_pages + 1):
        products, status = fetch_page(session, url, code, page_number)

        if status != "success":
            return stats, status

        if not products:
            return stats, "empty_page"

        current_page_keys = {product_key(p) for p in products}

        if current_page_keys == previous_page_keys:
            logger.warning("Page %s repeats the previous page.", page_number)
            return stats, "repeated_page"

        previous_page_keys = current_page_keys

        stats["cards"] += len(products)
        stats["pages"] += 1

        for product in products:
            key = product_key(product)

            if key in products_by_key:
                stats["duplicates"] += 1
                products_by_key[key].update(product)
            else:
                products_by_key[key] = product
                all_products.append(product)
                stats["new"] += 1

        save_csv(all_products)

        logger.info(
            "Page %s completed | Total: %s",
            page_number,
            len(all_products)
        )

        if page_number < max_pages:
            time.sleep(REQUEST_DELAY)

    return stats, stop_reason


def scrape(categories, max_pages=None):
    all_products = load_existing_products()

    products_by_key = {
        product_key(product): product
        for product in all_products
    }

    if len(products_by_key) != len(all_products):
        raise ValueError(
            "Existing CSV contains duplicate product keys."
        )

    session = requests.Session(impersonate="chrome")
    session.headers.update(HEADERS)

    # Homepage first so the Cloudflare cookies are set before the listing requests.
    try:
        session.get(BASE_URL + "/", timeout=REQUEST_TIMEOUT)
        time.sleep(2)
    except RequestException as error:
        logger.warning("Homepage request failed: %s", error)

    summary = []

    try:
        for index, (group, path, code, cap) in enumerate(categories):
            if index:
                time.sleep(REQUEST_DELAY)

            pages = max_pages if max_pages else cap
            url = f"{BASE_URL}/{path}"

            logger.info("Category %s | %s | code %s | max pages %s", group, path, code, pages)

            stats, reason = scrape_category(
                session, url, code, pages, all_products, products_by_key
            )

            summary.append((path, code, stats, reason))

            if reason in ("forbidden", "rate_limited"):
                logger.error("Stopping the run: %s", reason)
                break

    finally:
        session.close()

    logger.info("----------------------------------")
    logger.info("Decathlon scraping finished")

    for path, code, stats, reason in summary:
        logger.info(
            "%s (%s): pages %s | cards %s | new %s | duplicates %s | stop: %s",
            path,
            code,
            stats["pages"],
            stats["cards"],
            stats["new"],
            stats["duplicates"],
            reason
        )

    logger.info("CSV rows: %s", len(all_products))
    logger.info("Output: %s", OUTPUT_FILE)


def main():
    parser = argparse.ArgumentParser(
        description="Decathlon scraper: home fitness equipment (0922102) "
        "and sports clothing (0922107)"
    )
    parser.add_argument(
        "--only",
        choices=["fitness", "clothing"],
        help="Scrape one group only (default: both).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Pages per category, overriding the built-in caps; "
        "use 1-2 for a bounded live run.",
    )
    args = parser.parse_args()

    if args.max_pages is not None and args.max_pages < 1:
        parser.error("--max-pages must be >= 1")

    categories = [
        category for category in CATEGORIES
        if args.only is None or category[0] == args.only
    ]

    logger.info("Decathlon Scraper | categories: %s", len(categories))

    scrape(categories, max_pages=args.max_pages)


if __name__ == "__main__":
    main()
