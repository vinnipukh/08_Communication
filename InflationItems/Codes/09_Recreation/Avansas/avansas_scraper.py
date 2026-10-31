import argparse
import csv
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("AvansasScraper")


BASE_DIR = Path(__file__).resolve().parent

PROJECT_ROOT = next(
    (p for p in BASE_DIR.parents if (p / ".git").exists()),
    BASE_DIR
)

DATA_DIR = (
    PROJECT_ROOT
    / "InflationItems"
    / "Datas"
    / "09_Recreation"
    / "Avansas"
)


BASE_URL = "https://www.avansas.com"
CATEGORY_NUMBER = "9"


CATEGORIES = {
    "school_notebooks": {
        "url": "https://www.avansas.com/okul-defterleri-c-500144",
        "sub_category_number": "0974001"
    },
    "art_supplies": {
        "url": "https://www.avansas.com/boyama-urunleri-c-515888",
        "sub_category_number": "0974004"
    },
    "writing_drawing_paper": {
        "url": "https://www.avansas.com/fotokopi-kagitlari-c-69",
        "sub_category_number": "0974005"
    },
    "pens": {
        "url": "https://www.avansas.com/kalemler-c-3",
        "sub_category_number": "0974003"
    }
}

MAX_PAGES = 100
REQUEST_DELAY = 1.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def build_session():
    session = requests.Session()

    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )

    session.mount(
        "https://",
        HTTPAdapter(max_retries=retry)
    )

    session.headers.update(HEADERS)

    return session


def add_page_number(url, page_number):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))

    if page_number > 1:
        query["sayfa"] = str(page_number)
    else:
        query.pop("sayfa", None)

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment
        )
    )


def fetch_html(session, url, timeout=30):
    response = session.get(
        url,
        timeout=timeout
    )

    response.raise_for_status()
    return response.text


def convert_price(price_text):
    price_text = (
        price_text
        .replace(".", "")
        .replace(",", ".")
        .strip()
    )

    return float(price_text)


def extract_current_price(text):

    matches = re.findall(
        r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*TL\s*KDV\s*Dahil",
        text,
        flags=re.IGNORECASE
    )

    if matches:
        return convert_price(matches[-1])


    matches = re.findall(
        r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*TL",
        text,
        flags=re.IGNORECASE
    )

    if matches:
        return convert_price(matches[-1])

    return None


def normalize_product_url(href):
    if not href:
        return None

    absolute_url = urljoin(BASE_URL, href)
    parts = urlsplit(absolute_url)


    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            "",
            ""
        )
    )


def get_name_candidates(link):
    candidates = []

    text = link.get_text(
        " ",
        strip=True
    )

    if text:
        candidates.append(text)

    title = link.get("title")

    if title:
        candidates.append(title.strip())

    aria_label = link.get("aria-label")

    if aria_label:
        candidates.append(aria_label.strip())

    image = link.find("img")

    if image:
        alt = image.get("alt")

        if alt:
            candidates.append(alt.strip())

    clean_candidates = []

    for candidate in candidates:
        if not candidate:
            continue

        lower = candidate.lower()

        if "tl" in lower:
            continue

        if candidate.isdigit():
            continue

        if len(candidate) < 4:
            continue

        clean_candidates.append(candidate)

    return clean_candidates


def find_product_container(link):

    current = link

    for _ in range(8):
        current = current.parent

        if current is None:
            break

        text = current.get_text(
            " ",
            strip=True
        )

        if "TL" not in text:
            continue

        product_links = current.select(
            'a[href*="-p-"]'
        )

        unique_urls = {
            normalize_product_url(
                product_link.get("href")
            )
            for product_link in product_links
            if product_link.get("href")
        }

        unique_urls.discard(None)


        if len(unique_urls) <= 1:
            return current

    return None



def extract_total_results(html):

    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    match = re.search(
        r"Toplam\s+([\d.]+)\s+sonuç",
        page_text,
        flags=re.IGNORECASE
    )

    if not match:
        return None

    return int(match.group(1).replace(".", ""))

def parse_products(html, sub_category_number):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )



    start_text = soup.find(
        string=re.compile(
            r"Toplam\s+[\d.]+\s+sonuç",
            flags=re.IGNORECASE
        )
    )

    if start_text is None:
        logger.warning(
            "Category result marker was not found in HTML."
        )
        return []

    links_by_url = {}

    for element in start_text.next_elements:


        if isinstance(element, str):
            clean_text = " ".join(
                element.split()
            ).lower()

            if (
                "aradığınız ürünü bulamadınız mı" in clean_text
                or "aradiginiz urunu bulamadiniz mi" in clean_text
            ):
                break

            continue

        if getattr(element, "name", None) != "a":
            continue

        href = element.get("href") or ""

        if "-p-" not in href:
            continue

        product_url = normalize_product_url(
            href
        )

        if not product_url:
            continue

        links_by_url.setdefault(
            product_url,
            []
        ).append(element)

    results = []

    for product_url, links in links_by_url.items():

        name_candidates = []

        for link in links:
            name_candidates.extend(
                get_name_candidates(link)
            )

        if not name_candidates:
            continue

        name = max(
            name_candidates,
            key=len
        ).strip()

        container = None

        sorted_links = sorted(
            links,
            key=lambda x: len(
                x.get_text(" ", strip=True)
            ),
            reverse=True
        )

        for link in sorted_links:
            container = find_product_container(
                link
            )

            if container is not None:
                break

        if container is None:
            continue

        container_text = container.get_text(
            " ",
            strip=True
        )

        price = extract_current_price(
            container_text
        )

        if price is None or price <= 0:
            continue

        results.append(
            {
                "product_name": name,
                "price": price,
                "category_number": CATEGORY_NUMBER,
                "sub_category_number": sub_category_number,
                "_product_url": product_url
            }
        )

    return results


def scrape_category(
    session,
    category_name,
    category_url,
    sub_category_number,
    max_pages
):
    results = []
    seen_urls = set()
    expected_total = None

    logger.info(
        "Starting category: %s (%s)",
        category_name,
        sub_category_number
    )

    for page_number in range(
        1,
        max_pages + 1
    ):

        url = add_page_number(
            category_url,
            page_number
        )

        logger.info(
            "%s - page %d",
            category_name,
            page_number
        )

        try:
            html = fetch_html(
                session,
                url
            )
        except Exception as exc:
            logger.warning(
                "%s page %d failed: %s",
                category_name,
                page_number,
                exc
            )
            break

        if expected_total is None:
            expected_total = extract_total_results(html)

            if expected_total is not None:
                logger.info(
                    "%s: site reports %d total results",
                    category_name,
                    expected_total
                )

        products = parse_products(
            html,
            sub_category_number
        )

        if not products:
            logger.info(
                "%s: no products on page %d, stopping.",
                category_name,
                page_number
            )
            break

        new_count = 0

        for product in products:
            if (
                expected_total is not None
                and len(results) >= expected_total
            ):
                break

            product_url = product[
                "_product_url"
            ]

            if product_url in seen_urls:
                continue

            seen_urls.add(
                product_url
            )

            results.append(
                product
            )

            new_count += 1

        logger.info(
            "%s page %d: %d products, %d new",
            category_name,
            page_number,
            len(products),
            new_count
        )

        if (
            expected_total is not None
            and len(results) >= expected_total
        ):
            logger.info(
                "%s: reached reported total (%d), stopping.",
                category_name,
                expected_total
            )
            break


        if new_count == 0:
            logger.info(
                "%s: repeated page detected, stopping.",
                category_name
            )
            break

        time.sleep(
            REQUEST_DELAY
        )

    logger.info(
        "%s: extracted %d unique products",
        category_name,
        len(results)
    )

    return results


def save_to_csv(data, date_str):
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    output_file = (
        DATA_DIR
        / f"avansas_{date_str}.csv"
    )

    with open(
        output_file,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.writer(
            file
        )

        writer.writerow([
            "product_name",
            "price",
            "category_number",
            "sub_category_number"
        ])

        for item in sorted(
            data,
            key=lambda x: (
                x["sub_category_number"],
                x["product_name"].lower()
            )
        ):

            writer.writerow([
                item["product_name"],
                f'{item["price"]:.2f}',
                item["category_number"],
                item["sub_category_number"]
            ])

    logger.info(
        "Saved %d products to %s",
        len(data),
        output_file
    )

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Avansas Stationery Scraper"
    )

    parser.add_argument(
        "--date",
        type=str,
        default=None
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_PAGES
    )

    args = parser.parse_args()

    date_str = (
        args.date
        or datetime.today().strftime(
            "%Y-%m-%d"
        )
    )

    session = build_session()

    all_items = []
    global_seen_urls = set()

    for category_name, category in CATEGORIES.items():

        items = scrape_category(
            session=session,
            category_name=category_name,
            category_url=category["url"],
            sub_category_number=category[
                "sub_category_number"
            ],
            max_pages=args.max_pages
        )

        for item in items:

            product_url = item[
                "_product_url"
            ]

            if product_url in global_seen_urls:
                continue

            global_seen_urls.add(
                product_url
            )

            clean_item = {
                "product_name": item[
                    "product_name"
                ],
                "price": item["price"],
                "category_number": item[
                    "category_number"
                ],
                "sub_category_number": item[
                    "sub_category_number"
                ]
            }

            all_items.append(
                clean_item
            )

    if not all_items:
        logger.error(
            "No products scraped. "
            "Avansas HTML structure may have changed."
        )
        sys.exit(1)

    output_file = save_to_csv(
        all_items,
        date_str
    )

    print()
    print("----------------------------")
    print("Scraping completed.")
    print(
        "Total unique products:",
        len(all_items)
    )
    print("File:", output_file)
    print("----------------------------")


if __name__ == "__main__":
    main()
