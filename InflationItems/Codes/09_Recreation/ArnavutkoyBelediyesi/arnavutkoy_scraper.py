"""Arnavutköy Belediyesi sports facility and course fee scraper for TÜİK group 09.

The municipality's sports portal (spor.arnavutkoy.bel.tr, linked from www.arnavutkoy.bel.tr
"Spor Faaliyetleri") has one page per facility (`/tesis/<slug>`, listed on `/tesisler`).
Fee tables are static server HTML: each row is "<label> | <price> ₺", rows without a price
are group headers ("Yüzme Kursları (10 Seans)", "ÖZEL DERS TARİFELERİ (ALETLİ PİLATES)").
One facility (Vadipark Halı Sahası) gives its price in a sentence instead of a table.

Rows are mapped to two COICOP items:
    0946203 Sports training fee           (kurs eğitim seansı, ders, akademi ...)
    0946201 Payments for sports facilities (abonelik, serbest/tek kullanım seans, paket üyelik ...)
Prices include VAT (stated under each table and in the 2026 council tariff).

Output: InflationItems/Datas/09_Recreation/ArnavutkoyBelediyesi/arnavutkoy_YYYY-MM-DD.csv
"""

import argparse
import csv
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


BASE_URL = "https://spor.arnavutkoy.bel.tr"
FACILITY_INDEX = f"{BASE_URL}/tesisler"

OUTPUT_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "ArnavutkoyBelediyesi"
)

TODAY = datetime.now().strftime("%Y-%m-%d")

HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8"
}

CSV_COLUMNS = [
    "product_name",
    "price",
    "category_number",
    "sub_category_number",
    "facility",
    "group",
    "item",
    "vat_included",
    "source_url",
]

CODE_TRAINING = "0946203"
CODE_FACILITY = "0946201"

# Applied to "<group> <item>" in Turkish lower case, in this order. "Serbest Seans Havuz Kurs
# Abonelik" and "Tek Kullanım Kurs Seans" are pool/gym use, not lessons, so the facility words
# are checked before the lesson words.
FACILITY_FIRST = re.compile(r"serbest|abone|tek kullanım")
TRAINING_PATTERN = re.compile(r"eğitim|\bders|\bkurs|akademi|\bokul|antrenör")
FACILITY_PATTERN = re.compile(r"paket|üyeli|seans|kiralama|\bkira|giriş|halı saha")

PRICE_PATTERN = re.compile(r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:₺|TL)")
# Sentence form, e.g. "1 Saatlik Halı saha Abonelik Ücreti: 2.940.00 TL"
SENTENCE_PRICE = re.compile(r"([^.:]{3,80}?Ücreti)\s*:\s*([\d.,]+)\s*(?:₺|TL)")

REQUEST_DELAY = 2
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


def tr_lower(text):
    return text.replace("İ", "i").replace("I", "ı").lower()


def clean(text):
    return " ".join(str(text or "").replace("\xa0", " ").split())


def parse_price(text):
    """'2.500,00 ₺' -> 2500.0, '120,00 TL' -> 120.0, '2.940.00' -> 2940.0"""
    number = clean(text).replace("₺", "").replace("TL", "").strip()
    if not re.fullmatch(r"[\d.,]+", number):
        return None
    # The last separator followed by exactly two digits is the decimal mark.
    match = re.fullmatch(r"([\d.,]*?)[.,](\d{2})", number)
    if match:
        whole, decimals = match.group(1), match.group(2)
    else:
        whole, decimals = number, "00"
    whole = whole.replace(".", "").replace(",", "")
    try:
        return float(f"{whole or 0}.{decimals}")
    except ValueError:
        return None


def classify(group, item):
    text = tr_lower(f"{group} {item}")
    if FACILITY_FIRST.search(text):
        return CODE_FACILITY
    if TRAINING_PATTERN.search(text):
        return CODE_TRAINING
    if FACILITY_PATTERN.search(text):
        return CODE_FACILITY
    return None


def fetch_html(session, url, referer):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, headers={"Referer": referer}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.text
            logging.warning(f"HTTP {response.status_code} for {url} (attempt {attempt})")

        except RequestException as error:
            logging.warning(f"Request failed for {url} (attempt {attempt}): {error}")

        time.sleep(REQUEST_DELAY * attempt * 2)

    return None


def facility_links(html):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for anchor in soup.find_all("a", href=True):
        url = urljoin(BASE_URL + "/", anchor["href"]).split("#")[0]
        if re.match(rf"{re.escape(BASE_URL)}/tesis/[\w-]+$", url) and url not in links:
            links.append(url)
    return links


def facility_name(soup, url):
    title = clean(soup.title.get_text()) if soup.title else ""
    if " - " in title:
        return title.rsplit(" - ", 1)[1]
    heading = soup.find(["h1", "h2"])
    if heading and clean(heading.get_text()):
        return clean(heading.get_text())
    return url.rsplit("/", 1)[1].replace("-", " ").title()


def strip_inline_price(label):
    """'Eğitim Seansı 800.00 TL' -> 'Eğitim Seansı' (some tables repeat the price in the label)."""
    return clean(PRICE_PATTERN.sub("", label))


def table_caption(table, content, facility):
    """'Arnavutköy Spor Kompleksi Fıtness Ücret Tarifesi' above a table -> 'Fıtness'."""
    tag = table.find_previous(
        lambda t: t.name in ("p", "span", "strong", "h2", "h3", "h4", "h5")
        and "tarife" in tr_lower(t.get_text())
    )
    if tag is None or content not in tag.parents:
        return ""
    caption = clean(tag.get_text(" "))
    caption = re.sub(re.escape(facility), "", caption, flags=re.IGNORECASE)
    caption = re.sub(r"ücret tarifeleri|ücret tarifesi|Ücret Tarifeleri|Ücret Tarifesi", "", caption)
    return clean(caption)


def parse_facility(html, url):
    soup = BeautifulSoup(html, "html.parser")
    facility = facility_name(soup, url)
    content = soup.select_one(".page-content__description") or soup
    entries = []

    for table in content.find_all("table"):
        caption = table_caption(table, content, facility)
        group = ""
        for tr in table.find_all("tr"):
            cells = [clean(cell.get_text(" ")) for cell in tr.find_all(["td", "th"])]
            cells = [cell for cell in cells if cell]
            if not cells:
                continue

            price = parse_price(cells[-1]) if len(cells) >= 2 else None
            if price is None:
                # Header row of a group (or the table caption / column titles).
                if len(cells) <= 2 and not re.search(r"tarife konusu", tr_lower(cells[0])):
                    group = cells[0]
                continue

            label = strip_inline_price(" ".join(cells[:-1]))
            if price > 0 and label:
                entries.append((group or caption, label, price))

    # Prices given in a sentence outside the tables.
    for table in content.find_all("table"):
        table.decompose()
    text = clean(content.get_text(" "))
    for match in SENTENCE_PRICE.finditer(text):
        price = parse_price(match.group(2))
        if price and price > 0:
            entries.append(("", clean(match.group(1)), price))

    products = []
    for group, label, price in entries:
        code = classify(group, label)
        if code is None:
            logging.info(f"Dropped (no mapping): {facility} | {group} | {label}")
            continue
        products.append({
            "product_name": " - ".join(part for part in [
                "Arnavutköy Belediyesi", facility, group, label] if part),
            "price": f"{price:.2f}",
            "category_number": "9",
            "sub_category_number": code,
            "facility": facility,
            "group": group,
            "item": label,
            "vat_included": "true",
            "source_url": url,
        })
    return facility, products


def save_to_csv(products, output_file):
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(products)

    logging.info(f"Saved {len(products)} rows to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Arnavutköy Belediyesi training fees (0946203) and facility fees (0946201) scraper"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Fetch only the first N facility pages (default: all); use for a bounded live run.",
    )
    parser.add_argument("--date", default=TODAY, help="Output date (default: today)")
    args = parser.parse_args()

    all_products = []
    seen = set()

    with requests.Session(impersonate="chrome") as session:
        session.headers.update(HEADERS)

        # Homepage first, then the facility list and the facility pages.
        homepage = fetch_html(session, BASE_URL + "/", BASE_URL + "/")
        time.sleep(REQUEST_DELAY)

        index = fetch_html(session, FACILITY_INDEX, BASE_URL + "/")
        links = facility_links(index or "") or facility_links(homepage or "")
        if not links:
            logging.error("No facility links found. Existing CSV was not overwritten.")
            return
        if args.limit > 0:
            links = links[:args.limit]
        logging.info(f"{len(links)} facility pages")

        for url in links:
            time.sleep(REQUEST_DELAY)
            html = fetch_html(session, url, FACILITY_INDEX)
            if html is None:
                logging.error(f"Giving up on {url}")
                continue

            facility, products = parse_facility(html, url)
            logging.info(f"{facility}: {len(products)} rows")
            for product in products:
                if product["product_name"] not in seen:
                    seen.add(product["product_name"])
                    all_products.append(product)

    if all_products:
        save_to_csv(all_products, OUTPUT_DIR / f"arnavutkoy_{args.date}.csv")
    else:
        logging.warning("No rows collected. Existing CSV was not overwritten.")

    by_code = {}
    for product in all_products:
        by_code[product["sub_category_number"]] = by_code.get(product["sub_category_number"], 0) + 1
    logging.info(f"Scraping completed. Rows per code: {by_code}")


if __name__ == "__main__":
    main()
