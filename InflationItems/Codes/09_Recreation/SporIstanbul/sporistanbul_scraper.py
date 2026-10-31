"""Spor İstanbul (İBB sports company) fee tariff scraper for TÜİK group 09.

Spor İstanbul runs on WordPress. The yearly fee tariff ("İBB SPOR TESİSLERİ ŞUBE MÜDÜRLÜĞÜ
SPOR TESİSLERİ <year> YILI ÜCRET TARİFESİ") is a set of HTML tables on the page
`tesislerimiz/uyelik-bilgileri`, which the WP REST API returns in full:

    GET https://spor.istanbul/wp-json/wp/v2/pages?slug=uyelik-bilgileri&_fields=id,modified,link,content

Rows are mapped to two COICOP items:
    0946203 Sports training fee           (kurs, eğitim, ders, okul, akademi ...)
    0946201 Payments for sports facilities (üyelik, kullanım, hourly rental, serbest seans ...)
Rows that are neither (company/event/league rentals, film shooting, boat racks, offices,
performance tests) are dropped. Tariff prices include VAT for individuals.

The site answers 429 on quick bursts: keep >= 8 s between requests.

Output: InflationItems/Datas/09_Recreation/SporIstanbul/sporistanbul_YYYY-MM-DD.csv
"""

import argparse
import csv
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


BASE_URL = "https://spor.istanbul"
PAGES_API = f"{BASE_URL}/wp-json/wp/v2/pages"
TARIFF_SLUG = "uyelik-bilgileri"
TARIFF_SEARCH = "Ücret Tarifesi"

OUTPUT_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "SporIstanbul"
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
    "tariff_item",
    "section",
    "item",
    "unit",
    "tariff_year",
    "vat_included",
    "page_modified",
    "source_url",
]

CODE_TRAINING = "0946203"
CODE_FACILITY = "0946201"

# Applied to "<section> <item>" in Turkish lower case, in this order.
DROP_PATTERN = re.compile(
    r"reklam|film|çekim|canlı yayın|\bofis|\bstand\b|depo|dolap|konferans|eğitim salonu"
    r"|stüdyo salonu|\braf\b|bağlama|\bpark\b|vinç|bakım|tekne|\bbotu?\b|ölçüm|\btest"
    r"|müsabaka|\bmaç|\blig\b|etkinlik|şirket|ticari|vakıf|dernek|turnuva|organizasyon"
    r"|kulüp|paten kiralama|sezon"
)
TRAINING_PATTERN = re.compile(
    r"özel ders|\bders|\bkurs|eğitim|\bokul|antrenör|hazırlık|akademi|sporcu grubu|senkronize"
)
FACILITY_PATTERN = re.compile(r"üyeli|kullanım|kiralama|\bkira|serbest seans|giriş|abone")
HOURLY_UNITS = {"saat", "90 dakika"}

ITEM_NO = re.compile(r"^\d+\s*[.,]\s*\d+$")
SECTION_NO = re.compile(r"^\d+$")
PRICE_CELL = re.compile(r"^([\d.,]+)\s*(?:₺|TL)?$")

REQUEST_DELAY = 8
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
    """'63.800 ₺' -> 63800.0, '1.250,50 ₺' -> 1250.5"""
    match = PRICE_CELL.match(clean(text))
    if not match:
        return None
    number = match.group(1)
    if "," in number:
        number = number.replace(".", "").replace(",", ".")
    else:
        number = number.replace(".", "")
    try:
        return float(number)
    except ValueError:
        return None


def unit_label(unit):
    lowered = tr_lower(unit)
    usage = re.match(r"kullanım\s*\((\d+)\)", lowered)
    if usage:
        return f"{usage.group(1)} Kullanım"
    labels = {
        "saat": "Saatlik",
        "ay": "Aylık",
        "aylık": "Aylık",
        "gün": "Günlük",
        "günlük": "Günlük",
        "kişi": "Kişi Başı",
        "seans": "Seans Başı",
        "adet": "Adet",
    }
    return labels.get(lowered, unit)


def classify(section, item, unit):
    text = tr_lower(f"{section} {item}")
    if DROP_PATTERN.search(text):
        return None
    if TRAINING_PATTERN.search(text):
        return CODE_TRAINING
    if FACILITY_PATTERN.search(f"{text} {tr_lower(unit)}") or tr_lower(unit) in HOURLY_UNITS:
        return CODE_FACILITY
    return None


def fetch_json(session, params):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                PAGES_API,
                params=params,
                headers={"Accept": "application/json", "Referer": BASE_URL + "/"},
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            logging.warning(f"HTTP {response.status_code} for {PAGES_API} {params} (attempt {attempt})")

        except (RequestException, ValueError) as error:
            logging.warning(f"Request failed for {PAGES_API} {params} (attempt {attempt}): {error}")

        # 429 backs off longer than the normal spacing.
        time.sleep(REQUEST_DELAY * attempt * 2)

    return None


def has_tariff(page):
    html = (page.get("content") or {}).get("rendered") or ""
    return "BİRİM FİYAT" in html and "<table" in html


def find_tariff_page(session):
    fields = "id,slug,modified,link,content"
    pages = fetch_json(session, {"slug": TARIFF_SLUG, "_fields": fields})
    for page in pages or []:
        if has_tariff(page):
            return page

    logging.warning(f"No tariff table on slug '{TARIFF_SLUG}'; searching pages for '{TARIFF_SEARCH}'")
    time.sleep(REQUEST_DELAY)
    pages = fetch_json(session, {"search": TARIFF_SEARCH, "per_page": 100, "_fields": fields})
    for page in pages or []:
        if has_tariff(page):
            return page
    return None


def parse_tariff(page):
    soup = BeautifulSoup(page["content"]["rendered"], "html.parser")
    year = ""
    section = ""
    rows = []

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [clean(cell.get_text(" ")) for cell in tr.find_all(["td", "th"])]
            cells = [cell for cell in cells if cell]
            if not cells:
                continue

            year_match = re.search(r"(\d{4}) YILI ÜCRET TARİFESİ", " ".join(cells))
            if year_match:
                year = year_match.group(1)
                continue

            if len(cells) == 2 and SECTION_NO.match(cells[0]):
                section = cells[1]
                continue

            if len(cells) < 4 or not ITEM_NO.match(cells[0]):
                continue

            price = parse_price(cells[-1])
            if price is None or price <= 0:
                continue

            item = " ".join(cells[1:-2])
            unit = cells[-2]
            rows.append({
                "tariff_item": re.sub(r"\s*,\s*", ".", cells[0]),
                "section": section,
                "item": item,
                "unit": unit,
                "price": price,
            })

    return year, rows


def build_products(page, year, rows):
    products = []
    dropped = 0

    for row in rows:
        code = classify(row["section"], row["item"], row["unit"])
        if code is None:
            dropped += 1
            continue

        name = " - ".join(part for part in [
            "Spor İstanbul",
            row["section"],
            row["item"],
            unit_label(row["unit"]),
        ] if part)

        products.append({
            "product_name": name,
            "price": f"{row['price']:.2f}",
            "category_number": "9",
            "sub_category_number": code,
            "tariff_item": row["tariff_item"],
            "section": row["section"],
            "item": row["item"],
            "unit": row["unit"],
            "tariff_year": year,
            "vat_included": "true",
            "page_modified": page.get("modified", ""),
            "source_url": page.get("link", ""),
        })

    # Same section, item and unit twice: keep both, tell them apart by the tariff number.
    counts = {}
    for product in products:
        counts[product["product_name"]] = counts.get(product["product_name"], 0) + 1
    for product in products:
        if counts[product["product_name"]] > 1:
            product["product_name"] += f" ({product['tariff_item']})"

    logging.info(f"Tariff rows: {len(rows)}, kept: {len(products)}, dropped: {dropped}")
    return products


def save_to_csv(products, output_file):
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(products)

    logging.info(f"Saved {len(products)} rows to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Spor İstanbul training fees (0946203) and facility fees (0946201) scraper"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Keep only the first N output rows (default: all); use for a bounded live run.",
    )
    parser.add_argument("--date", default=TODAY, help="Output date (default: today)")
    args = parser.parse_args()

    with requests.Session(impersonate="chrome") as session:
        session.headers.update(HEADERS)

        # Homepage first, then the REST call.
        try:
            session.get(BASE_URL + "/", timeout=REQUEST_TIMEOUT)
        except RequestException as error:
            logging.warning(f"Homepage request failed: {error}")
        time.sleep(REQUEST_DELAY)

        page = find_tariff_page(session)

    if page is None:
        logging.error("Tariff page not found. Existing CSV was not overwritten.")
        return

    year, rows = parse_tariff(page)
    logging.info(f"Tariff page {page.get('link')} (modified {page.get('modified')}), year {year or '?'}")
    products = build_products(page, year, rows)

    if args.limit > 0:
        products = products[:args.limit]

    if products:
        save_to_csv(products, OUTPUT_DIR / f"sporistanbul_{args.date}.csv")
    else:
        logging.warning("No rows collected. Existing CSV was not overwritten.")

    by_code = {}
    for product in products:
        by_code[product["sub_category_number"]] = by_code.get(product["sub_category_number"], 0) + 1
    logging.info(f"Scraping completed. Rows per code: {by_code}")


if __name__ == "__main__":
    main()
