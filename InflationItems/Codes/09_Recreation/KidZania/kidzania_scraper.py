"""KidZania İstanbul (kidzania.com.tr -> istanbul.kidzania.com) price scraper for TÜİK group 09.

Recreation and hobby services (0946103): KidZania entry tickets.

Two sources, both from the homepage session:

1. The homepage "Giriş Ücretleri" table (`section#opening-prices table`):
   KidZania entry and the experience packages. Only this table is read; the
   holiday/campaign text and opening-hours blocks next to it are ignored.
2. The ticket shop's "Bireysel Giriş" category (id 1), the same call the
   homepage purchase widget makes: `POST /online-ticket-select-date` with
   `{"category_id": 1, "date": "YYYY-MM-DD"}` and the page's CSRF token. It
   lists the age-band tickets (4-14, 2-3) and the 3-month/annual cards.
   Nothing is added to the cart. A table row whose price equals one of these
   tickets (the general entry) is not written twice.

Output: InflationItems/Datas/09_Recreation/KidZania/kidzania_YYYY-MM-DD.csv
"""

import argparse
import csv
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


START_URL = "https://www.kidzania.com.tr/"
BASE_URL = "https://istanbul.kidzania.com"
TICKET_API = f"{BASE_URL}/online-ticket-select-date"
INDIVIDUAL_CATEGORY_ID = 1

SUB_CATEGORY = "0946103"

OUTPUT_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "KidZania"
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
    "list_price",
    "ticket_name",
    "source",
    "ticket_id",
    "product_url",
]

PAGE_DELAY = 2
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


def clean(text):
    return " ".join(str(text or "").split())


def parse_try(text):
    """'3.590₺' -> 3590.0, '3.590,00' -> 3590.0, '8140.000000' -> 8140.0."""
    text = clean(text).replace("₺", "").replace("TL", "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d+\.\d+", text) and not re.fullmatch(r"\d{1,3}(\.\d{3})+", text):
        return float(text)  # machine format, e.g. fake_price "8140.000000"
    text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def get_homepage(session):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(START_URL, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response
            logging.warning(f"HTTP {response.status_code} for {START_URL} (attempt {attempt})")
        except RequestException as error:
            logging.warning(f"Homepage request failed (attempt {attempt}): {error}")
        time.sleep(PAGE_DELAY * attempt * 2)
    return None


def parse_table(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("section#opening-prices table")
    if table is None:
        logging.warning("'Giriş Ücretleri' table not found on the homepage")
        return []

    rows = []
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue
        name = clean(cells[0].get_text(" "))
        price_cell = cells[1]
        new_price = price_cell.select_one(".new-price")
        old_price = price_cell.select_one(".old-price, del")
        price = parse_try(new_price.get_text() if new_price else price_cell.get_text())
        list_price = parse_try(old_price.get_text()) if old_price else None
        if not name or not price or price <= 0:
            continue
        rows.append({
            "product_name": f"KidZania İstanbul - {name}",
            "price": f"{price:.2f}",
            "category_number": "9",
            "sub_category_number": SUB_CATEGORY,
            "list_price": f"{list_price:.2f}" if list_price else "",
            "ticket_name": name,
            "source": "homepage_table",
            "ticket_id": "",
            "product_url": page_url,
        })
    return rows


def fetch_individual_tickets(session, html, page_url, date):
    match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    if not match:
        logging.warning("CSRF token not found; ticket shop prices skipped")
        return []

    headers = {
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRF-TOKEN": match.group(1),
        "Origin": BASE_URL,
        "Referer": page_url,
    }
    payload = {"category_id": INDIVIDUAL_CATEGORY_ID, "date": date, "ticketDateControl": "false"}

    tickets = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.post(TICKET_API, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                tickets = response.json()
                break
            logging.warning(f"HTTP {response.status_code} for {TICKET_API} (attempt {attempt})")
        except (RequestException, ValueError) as error:
            logging.warning(f"Ticket request failed (attempt {attempt}): {error}")
        time.sleep(PAGE_DELAY * attempt * 2)

    if not isinstance(tickets, list):
        logging.warning("Ticket shop returned no ticket list")
        return []

    rows = []
    for ticket in tickets:
        name = clean(ticket.get("name"))
        price = parse_try(str(ticket.get("price") or ticket.get("real_price") or ""))
        fake = parse_try(str(ticket.get("fake_price") or ""))
        if not name or not price or price <= 0:
            continue
        rows.append({
            "product_name": f"KidZania İstanbul - Bireysel Giriş - {name}",
            "price": f"{price:.2f}",
            "category_number": "9",
            "sub_category_number": SUB_CATEGORY,
            "list_price": f"{fake:.2f}" if fake and fake > price else "",
            "ticket_name": name,
            "source": "ticket_shop",
            "ticket_id": ticket.get("id") or "",
            "product_url": f"{BASE_URL}/tr/satin-al",
        })
    return rows


def save_to_csv(rows, output_file):
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    logging.info(f"Saved {len(rows)} rows to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="KidZania İstanbul ticket price scraper (0946103)"
    )
    parser.add_argument("--date", default=TODAY, help="Output date (default: today)")
    parser.add_argument(
        "--table-only",
        action="store_true",
        help="Read only the homepage table (bounded live run; skips the ticket shop call).",
    )
    args = parser.parse_args()

    started = time.time()
    with requests.Session(impersonate="chrome") as session:
        session.headers.update(HEADERS)

        # Homepage first (kidzania.com.tr redirects to istanbul.kidzania.com).
        response = get_homepage(session)
        if response is None:
            logging.error("Homepage not reachable. Existing CSV was not overwritten.")
            sys.exit(1)
        html, page_url = response.text, str(response.url)

        table_rows = parse_table(html, page_url)
        shop_rows = []
        if not args.table_only:
            time.sleep(PAGE_DELAY)
            shop_date = TODAY if args.date == TODAY or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date) else args.date
            shop_rows = fetch_individual_tickets(session, html, page_url, shop_date)

    shop_prices = {row["price"] for row in shop_rows}
    rows = shop_rows + [row for row in table_rows if row["price"] not in shop_prices]
    skipped = len(table_rows) + len(shop_rows) - len(rows)
    if skipped:
        logging.info(f"{skipped} homepage table row(s) duplicate a ticket shop price; not written twice")

    if not rows:
        logging.error("No ticket prices found. Existing CSV was not overwritten.")
        sys.exit(1)

    save_to_csv(rows, OUTPUT_DIR / f"kidzania_{args.date}.csv")
    logging.info(f"Scraping completed in {time.time() - started:.0f} s. Rows: {len(rows)}")


if __name__ == "__main__":
    main()
