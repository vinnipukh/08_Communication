import csv
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


BASE_URL = "https://www.korayspor.com"

CATEGORIES = [
    {
        "url": "https://www.korayspor.com/vucut-gelistirme-urunleri/",
        "category_number": "9",
        "sub_category_number": "0922102"
    },
    {
        "url": "https://www.korayspor.com/pilates-yoga-urunleri/",
        "category_number": "9",
        "sub_category_number": "0922102"
    }
]

OUTPUT_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "Korayspor"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TODAY = datetime.now().strftime("%Y-%m-%d")
OUTPUT_FILE = OUTPUT_DIR / f"korayspor_{TODAY}.csv"

# Site sits behind Cloudflare (__cf_bm); use Chrome TLS impersonation.
HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8"
}

MAX_PAGES = 50
PAGE_DELAY = 2

CSV_COLUMNS = [
    "product_name",
    "price",
    "category_number",
    "sub_category_number",
    "product_url"
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


def clean_price(price_text):
    price = price_text.replace("TL", "").replace("₺", "").strip()
    price = price.replace(" ", "")

    if "," in price:
        price = price.replace(".", "").replace(",", ".")

    return price


def total_pages(soup):
    # Next.js listing: totalPages lives in the __NEXT_DATA__ page props.
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return 1

    def find(node):
        if isinstance(node, dict):
            if isinstance(node.get("totalPages"), int):
                return node["totalPages"]
            node = list(node.values())
        if isinstance(node, list):
            for value in node:
                found = find(value)
                if found:
                    return found
        return None

    return find(json.loads(script.string)) or 1


def scrape_category(session, category):
    products = []
    pages = 1
    page = 1

    while page <= min(pages, MAX_PAGES):
        url = category["url"] if page == 1 else f"{category['url']}?page={page}"

        logging.info(f"Scraping category page {page}: {url}")

        try:
            response = session.get(
                url,
                headers=HEADERS,
                timeout=30
            )
            response.raise_for_status()

        except RequestException as error:
            logging.error(f"Request failed: {error}")
            break

        soup = BeautifulSoup(response.text, "html.parser")

        if page == 1:
            pages = total_pages(soup)
            logging.info(f"Category has {pages} page(s)")

        page_products = parse_cards(soup, category)
        if not page_products:
            break

        products.extend(page_products)
        page += 1
        time.sleep(PAGE_DELAY)

    logging.info(f"Extracted {len(products)} products")

    return products


def parse_cards(soup, category):
    cards = soup.select("li[data-productid]")

    logging.info(f"Found {len(cards)} product cards")

    products = []

    for card in cards:
        link = card.select_one("a[title][href]")
        brand = card.select_one(
            '[data-test-id^="product_card_name_"]'
        )
        description = card.select_one("h3")
        price_element = card.select_one(".sales-price")

        if not link or not price_element:
            continue

        brand_text = (
            brand.get_text(" ", strip=True)
            if brand else ""
        )

        description_text = (
            description.get_text(" ", strip=True)
            if description else ""
        )

        product_name = " ".join(
            part for part in [brand_text, description_text]
            if part
        )

        if not product_name:
            product_name = link.get("title", "").strip()

        price_text = price_element.get_text(" ", strip=True)
        price = clean_price(price_text)

        product_url = urljoin(
            BASE_URL,
            link["href"]
        )

        if not product_name or not price:
            continue

        products.append({
            "product_name": product_name,
            "price": price,
            "category_number": category["category_number"],
            "sub_category_number": category["sub_category_number"],
            "product_url": product_url
        })

    return products


def save_to_csv(products):
    with open(
        OUTPUT_FILE,
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

    logging.info(
        f"Saved {len(products)} products to {OUTPUT_FILE}"
    )


def main():
    all_products = []
    seen_urls = set()

    with requests.Session(impersonate="chrome") as session:

        # Homepage first so the Cloudflare cookie is set before category pages.
        try:
            session.get(BASE_URL + "/", headers=HEADERS, timeout=30)
        except RequestException as error:
            logging.warning(f"Homepage request failed: {error}")
        time.sleep(PAGE_DELAY)

        for category in CATEGORIES:
            products = scrape_category(session, category)

            for product in products:
                if product["product_url"] not in seen_urls:
                    seen_urls.add(product["product_url"])
                    all_products.append(product)

            time.sleep(2)

    if all_products:
        save_to_csv(all_products)
    else:
        logging.warning(
            "No products collected. Existing CSV was not overwritten."
        )

    logging.info(
        f"Scraping completed. Total unique products: {len(all_products)}"
    )


if __name__ == "__main__":
    main()
