"""VetArt veterinary fee page scraper for TÜİK item 0945001 (veterinary services).

https://vetart.com.tr/veteriner-ucretleri/ is a static WordPress page that repeats a short
extract of the İstanbul Chamber of Veterinary Surgeons minimum fee tariff in two HTML tables
(examination; vaccines and antiparasitic treatment) with Kedi / Köpek (/ Kafes Kuşlar) columns.
Every priced cell becomes one CSV row.

Output: InflationItems/Datas/09_Recreation/VetArt/vetart_YYYY-MM-DD.csv
"""

from __future__ import annotations

import argparse
import csv
import html
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("VetArtScraper")


BASE_URL = "https://vetart.com.tr/"
PAGE_URL = BASE_URL + "veteriner-ucretleri/"

DATA_DIR = Path(__file__).resolve().parents[3] / "Datas" / "09_Recreation" / "VetArt"

CATEGORY_NUMBER = "9"
SUBCATEGORY_NUMBER = "0945001"
SOURCE_PREFIX = "VetArt"

REQUEST_TIMEOUT = 60
REQUEST_DELAY = 1.5
MAX_RETRIES = 3

HEADERS = {"Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8"}

CSV_COLUMNS = [
    "product_name",
    "price",
    "category_number",
    "sub_category_number",
    "price_max",
    "price_text",
    "animal",
    "section",
    "service",
    "tariff_period",
    "kdv_included",
    "source_url",
]

# The page does not say whether VAT is included, so the column is left empty.
KDV_INCLUDED = ""

TABLE_PATTERN = re.compile(r"<table[^>]*>(.*?)</table>", re.IGNORECASE | re.DOTALL)
ROW_PATTERN = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
CELL_PATTERN = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
HEADING_PATTERN = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.IGNORECASE | re.DOTALL)
AMOUNT_PATTERN = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?")
PERIOD_PATTERN = re.compile(r"(Ocak|Temmuz)\s+(20\d{2})\s+itibari")


def clean(fragment):
    text = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(text).replace("﻿", "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def get(session, url, referer=None):
    headers = {"Referer": referer} if referer else None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                return response

            logger.warning("HTTP %s for %s (attempt %d)", response.status_code, url, attempt)
        except RequestException as error:
            logger.warning("Request failed for %s (attempt %d): %s", url, attempt, error)

        time.sleep(3 * attempt)

    raise RuntimeError(f"Could not fetch {url}")


def parse_amount(text):
    """Return the TRY amount of a cell such as '₺1750' or '₺1.750' (dot = thousands)."""
    match = AMOUNT_PATTERN.search(text)

    if not match:
        return None

    return float(match.group().replace(".", "").replace(",", "."))


def parse_page(page_html):
    period_match = PERIOD_PATTERN.search(clean(page_html))
    period = f"{period_match.group(2)}/{'1' if period_match.group(1) == 'Ocak' else '2'}" if period_match else ""

    rows = []

    for table_match in TABLE_PATTERN.finditer(page_html):
        # The section is the last heading before the table.
        headings = HEADING_PATTERN.findall(page_html[: table_match.start()])
        section = clean(headings[-1]) if headings else ""
        section = re.sub(r"\s*\(Alt Sınır\)\s*20\d{2}\s*$", "", section)

        table_rows = [
            [clean(cell) for cell in CELL_PATTERN.findall(row)]
            for row in ROW_PATTERN.findall(table_match.group(1))
        ]

        if len(table_rows) < 2:
            continue

        animals = table_rows[0][1:]

        for cells in table_rows[1:]:
            service = cells[0]

            for animal, cell in zip(animals, cells[1:]):
                price = parse_amount(cell)

                if not service or not animal or price is None:
                    continue

                rows.append(
                    {
                        "product_name": f"{SOURCE_PREFIX} - {section} - {service} - {animal}",
                        "price": f"{price:.2f}",
                        "category_number": CATEGORY_NUMBER,
                        "sub_category_number": SUBCATEGORY_NUMBER,
                        "price_max": f"{price:.2f}",
                        "price_text": cell,
                        "animal": animal,
                        "section": section,
                        "service": service,
                        "tariff_period": period,
                        "kdv_included": KDV_INCLUDED,
                        "source_url": PAGE_URL,
                    }
                )

    return rows


def save_csv(rows, date_str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_file = DATA_DIR / f"vetart_{date_str}.csv"

    with output_file.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="VetArt veterinary fee page scraper - CPI item 0945001"
    )
    parser.add_argument("--date", default=None, help="Output date, e.g. 2026-10-31.")
    args = parser.parse_args()

    started = time.perf_counter()
    date_str = args.date or datetime.today().strftime("%Y-%m-%d")

    session = requests.Session(impersonate="chrome")
    session.headers.update(HEADERS)

    try:
        get(session, BASE_URL)
        time.sleep(REQUEST_DELAY)
        page = get(session, PAGE_URL, referer=BASE_URL)
    finally:
        session.close()

    rows = parse_page(page.text)

    if not rows:
        logger.error("No price rows were parsed; no CSV written.")
        sys.exit(1)

    output_file = save_csv(rows, date_str)

    print()
    print("------------------------------------------")
    print("VetArt veterinary fee scraping completed.")
    print("sub_category_number:", SUBCATEGORY_NUMBER)
    print("Rows:", len(rows))
    print(f"Time: {time.perf_counter() - started:.1f} s")
    print("File:", output_file)
    print("------------------------------------------")


if __name__ == "__main__":
    main()
