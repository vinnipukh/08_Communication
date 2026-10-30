import csv
import logging
import os
import re
import time

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.decathlon.com.tr"

CATEGORY_URL = (
    "https://www.decathlon.com.tr/"
    "ekipmanlar/evde-spor-aletleri"
)

CATEGORY_NUMBER = "09"
CATEGORY_CODE = "0922102"

PAGE_SIZE = 40
MAX_PAGES = 60
REQUEST_DELAY = 10
REQUEST_TIMEOUT = 30

HEADERS = {
    "User-Agent": "DecathlonPriceScraper/1.0"
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


def extract_product(card):
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
        "sub_category_number": CATEGORY_CODE,
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


def fetch_page(session, page_number):
    offset = (page_number - 1) * PAGE_SIZE

    logger.info(
        "Fetching page %s | Offset: %s",
        page_number,
        offset
    )

    try:
        response = session.get(
            CATEGORY_URL,
            params={
                "from": offset,
                "size": PAGE_SIZE
            },
            timeout=REQUEST_TIMEOUT
        )

    except requests.RequestException as error:
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

    except requests.HTTPError as error:
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
        product = extract_product(card)

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


def scrape():
    all_products = load_existing_products()

    products_by_key = {
        product_key(product): product
        for product in all_products
    }

    if len(products_by_key) != len(all_products):
        raise ValueError(
            "Existing CSV contains duplicate product keys."
        )

    session = requests.Session()
    session.headers.update(HEADERS)

    total_cards = 0
    pages_completed = 0
    duplicates = 0
    stop_reason = "maximum_pages"
    previous_page_keys = None

    try:
        for page_number in range(1, MAX_PAGES + 1):
            products, status = fetch_page(
                session,
                page_number
            )

            if status != "success":
                stop_reason = status
                break

            if not products:
                stop_reason = "empty_page"

                logger.info(
                    "No products found on page %s.",
                    page_number
                )

                break

            current_page_keys = {
                product_key(product)
                for product in products
            }

            if current_page_keys == previous_page_keys:
                stop_reason = "repeated_page"

                logger.warning(
                    "Page %s repeats the previous page.",
                    page_number
                )

                break

            previous_page_keys = current_page_keys

            total_cards += len(products)
            pages_completed += 1

            new_products = 0

            for product in products:
                key = product_key(product)

                if key in products_by_key:
                    duplicates += 1
                    products_by_key[key].update(product)

                else:
                    products_by_key[key] = product
                    all_products.append(product)
                    new_products += 1

            save_csv(all_products)

            logger.info(
                "Page %s completed | New: %s | Total: %s",
                page_number,
                new_products,
                len(all_products)
            )

            if len(products) < PAGE_SIZE:
                logger.info(
                    "Page %s has %s products. "
                    "Checking the next page.",
                    page_number,
                    len(products)
                )

            if page_number < MAX_PAGES:
                time.sleep(REQUEST_DELAY)

    finally:
        session.close()

    logger.info("----------------------------------")
    logger.info("Decathlon scraping finished")
    logger.info("Pages completed: %s", pages_completed)
    logger.info("Product cards: %s", total_cards)
    logger.info("Duplicate occurrences: %s", duplicates)
    logger.info("CSV rows: %s", len(all_products))
    logger.info("Stop reason: %s", stop_reason)
    logger.info("Output: %s", OUTPUT_FILE)


def main():
    logger.info("Decathlon Home Equipment Scraper")
    logger.info("Category: %s", CATEGORY_CODE)
    logger.info("Maximum pages: %s", MAX_PAGES)

    scrape()


if __name__ == "__main__":
    main()
