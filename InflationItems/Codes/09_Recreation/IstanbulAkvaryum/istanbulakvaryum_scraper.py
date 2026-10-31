"""İstanbul Akvaryum (istanbulakvaryum.com) ticket price scraper for TÜİK group 09.

Recreation and hobby services (0946103): aquarium entry tickets and packages.

The ticket page `/ziyaretinizi-planlayin/biletal` is server HTML. Every ticket is
a `div.hemenbiletal_paketbox` card with the ticket name in
`.hemenbiletal_paketbox_kisi strong` and the price in
`.hemenbiletal_paketbox_fiyat`. The price is split across elements
("2.750." in <strong> + "00 ₺" in <span>). When a card shows a struck-through
price (<del>), that is the list price and the large price is the campaign price
for Turkish citizens; both are written as separate rows.

Output: InflationItems/Datas/09_Recreation/IstanbulAkvaryum/istanbulakvaryum_YYYY-MM-DD.csv
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


BASE_URL = "https://www.istanbulakvaryum.com"
TICKET_URL = f"{BASE_URL}/ziyaretinizi-planlayin/biletal"

SUB_CATEGORY = "0946103"

OUTPUT_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "IstanbulAkvaryum"
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
    "ticket_name",
    "price_type",
    "section",
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
    """'2.750.00 ₺' / '1.000.00 ₺' -> 2750.0 (dot thousands, last dot = decimals)."""
    digits = re.sub(r"[^\d.,]", "", text or "")
    match = re.fullmatch(r"([\d.]*?)[.,](\d{2})", digits)
    if match:
        whole = match.group(1).replace(".", "").replace(",", "")
        if not whole:
            return None
        return float(f"{whole}.{match.group(2)}")
    whole = digits.replace(".", "").replace(",", "")
    return float(whole) if whole else None


def fetch(session, url, referer=None):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            headers = {"Referer": referer} if referer else None
            response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.text
            logging.warning(f"HTTP {response.status_code} for {url} (attempt {attempt})")
        except RequestException as error:
            logging.warning(f"Request failed for {url} (attempt {attempt}): {error}")
        time.sleep(PAGE_DELAY * attempt * 2)
    return None


def parse_tickets(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for container in soup.select("div.hemenbiletal_paketler"):
        header = container.find_previous("h2")
        section = clean(header.get_text(" ")) if header else ""

        for card in container.select("div.hemenbiletal_paketbox"):
            name_tag = card.select_one(".hemenbiletal_paketbox_kisi strong")
            price_box = card.select_one(".hemenbiletal_paketbox_fiyat")
            if not name_tag or not price_box:
                continue

            name = clean(name_tag.get_text(" "))
            ticket_id = ""
            button = card.select_one("a[onclick*=addToBasket]")
            if button:
                match = re.search(r"addToBasket\('(\d+)'", button.get("onclick", ""))
                ticket_id = match.group(1) if match else ""

            list_price = None
            old = price_box.find("del")
            if old:
                list_price = parse_try(old.get_text(""))
                old.extract()
            current = parse_try(price_box.get_text(""))

            if not name or not current or current <= 0:
                logging.warning(f"No price for ticket card {name!r}")
                continue

            base = {
                "category_number": "9",
                "sub_category_number": SUB_CATEGORY,
                "ticket_name": name,
                "section": section,
                "ticket_id": ticket_id,
                "product_url": TICKET_URL,
            }
            if list_price and list_price > 0:
                rows.append({
                    **base,
                    "product_name": f"İstanbul Akvaryum - {name} - liste fiyatı",
                    "price": f"{list_price:.2f}",
                    "price_type": "list",
                })
                rows.append({
                    **base,
                    "product_name": f"İstanbul Akvaryum - {name} - TC vatandaşı kampanya fiyatı",
                    "price": f"{current:.2f}",
                    "price_type": "citizen_campaign",
                })
            else:
                # No struck-through price: the card shows one price, which the
                # site labels as the campaign price for Turkish citizens.
                rows.append({
                    **base,
                    "product_name": f"İstanbul Akvaryum - {name} - TC vatandaşı fiyatı",
                    "price": f"{current:.2f}",
                    "price_type": "citizen",
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
        description="İstanbul Akvaryum ticket price scraper (0946103)"
    )
    parser.add_argument("--date", default=TODAY, help="Output date (default: today)")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Write only the first N rows (bounded live run); 0 = all.",
    )
    args = parser.parse_args()

    started = time.time()
    with requests.Session(impersonate="chrome") as session:
        session.headers.update(HEADERS)

        # Homepage first, then the ticket page.
        try:
            session.get(BASE_URL + "/", timeout=REQUEST_TIMEOUT)
        except RequestException as error:
            logging.warning(f"Homepage request failed: {error}")
        time.sleep(PAGE_DELAY)

        html = fetch(session, TICKET_URL, referer=BASE_URL + "/")

    rows = parse_tickets(html) if html else []
    if args.limit:
        rows = rows[: args.limit]

    if not rows:
        logging.error("No ticket prices found. Existing CSV was not overwritten.")
        sys.exit(1)

    save_to_csv(rows, OUTPUT_DIR / f"istanbulakvaryum_{args.date}.csv")
    logging.info(f"Scraping completed in {time.time() - started:.0f} s. Rows: {len(rows)}")


if __name__ == "__main__":
    main()
