"""Düğün.com wedding-hall prices for TÜİK 09 item 0969006
("Event hall rental for wedding, engagement, and other events").

The public listing pages `https://dugun.com/dugun-salonlari/<city>?page=N` are
server-rendered. Each page carries a schema.org `ItemList` (JSON-LD) whose venues
have a `makesOffer` object: `price` (TRY), `name` (`Kişi Başı` = per person or
`Paket` = package) and `priceValidUntil`. The HTML cards add the struck-through
list price (`<del>`) when a venue is discounted and the provider id.
The `/api/*` endpoints are disallowed by robots.txt and are NOT used.

Per-person and package prices are never mixed: the price type goes into
`product_name` and the `price_type` column.

Output: InflationItems/Datas/09_Recreation/DugunCom/dugun_com_YYYY-MM-DD.csv
"""

import argparse
import csv
import html
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


BASE_URL = "https://dugun.com"
HOME_URL = BASE_URL + "/"
LISTING_URL = f"{BASE_URL}/dugun-salonlari"
EXCLUDED_CITY_SLUGS = {"kibris"}  # Northern Cyprus is outside the Turkish CPI

CATEGORY_NUMBER = "9"
SUB_CATEGORY_NUMBER = "0969006"

OUTPUT_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "DugunCom"
)

TODAY = datetime.now().strftime("%Y-%m-%d")

HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
}

PRICE_TYPES = {
    "Kişi Başı": "per_person",
    "Paket": "package",
}

CITY_LINK_RE = re.compile(r'href="https://dugun\.com/dugun-salonlari/([a-z0-9-]+)"')
JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
CARD_TITLE_RE = re.compile(
    r'class="c-provider-card-horizontal__title">\s*<a href="([^"]+)"', re.S
)
BEFORE_PRICE_RE = re.compile(r'<del[^>]*>\s*([\d.,]+)\s*</del>')
PROVIDER_ID_RE = re.compile(r'data-provider-id="(\d+)"')
NEXT_RE = re.compile(r'<link rel="next" href="([^"]+)"')

CSV_COLUMNS = [
    "product_name",
    "price",
    "category_number",
    "sub_category_number",
    "venue_name",
    "city",
    "district",
    "price_type",
    "list_price",
    "price_valid_until",
    "provider_id",
    "source_url",
]

MAX_PAGES = 40
PAGE_DELAY = 1.5
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


def fetch_html(session, url, referer):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, headers={"Referer": referer}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.text
            logging.warning(f"HTTP {response.status_code} for {url} (attempt {attempt})")
        except RequestException as error:
            logging.warning(f"Request failed for {url} (attempt {attempt}): {error}")

        time.sleep(PAGE_DELAY * attempt * 2)

    return None


def clean(text):
    return " ".join(html.unescape(str(text or "")).split())


def to_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def parse_tr_amount(text):
    """'1.200' / '1.200,50' -> 1200.0 / 1200.5"""
    try:
        return float(text.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def city_slugs(page_html):
    slugs = []
    for slug in CITY_LINK_RE.findall(page_html):
        # Istanbul district pages end in a numeric id; they are covered by "istanbul".
        if re.search(r"-\d+$", slug) or slug in EXCLUDED_CITY_SLUGS or slug in slugs:
            continue
        slugs.append(slug)
    return slugs


def item_list(page_html):
    for block in JSON_LD_RE.findall(page_html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for node in data.get("@graph", []) if isinstance(data, dict) else []:
            if node.get("@type") == "ItemList":
                return node.get("itemListElement") or []
    return []


def card_details(page_html):
    """url -> (list_price, provider_id) from the HTML cards."""
    details = {}
    matches = list(CARD_TITLE_RE.finditer(page_html))
    for index, match in enumerate(matches):
        url = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(page_html)
        segment = page_html[match.end():end]
        before = BEFORE_PRICE_RE.search(segment)
        provider = PROVIDER_ID_RE.search(segment)
        details.setdefault(url, (
            parse_tr_amount(before.group(1)) if before else None,
            provider.group(1) if provider else "",
        ))
    return details


def parse_venue(element, details, city_name):
    venue = element.get("item") or {}
    offer = venue.get("makesOffer") or {}
    price = to_number(offer.get("price"))
    price_type = PRICE_TYPES.get(clean(offer.get("name")))

    if price is None or price_type is None or offer.get("priceCurrency") != "TRY":
        return None

    name = clean(venue.get("name"))
    if not name:
        return None

    address = venue.get("address") or {}
    district = clean(address.get("addressLocality"))
    city = clean(address.get("addressRegion")) or city_name
    location = f"{city}/{district}" if district and district != city else city
    label = "Kişi Başı" if price_type == "per_person" else "Paket"

    url = venue.get("url") or ""
    list_price, provider_id = details.get(url, (None, ""))

    return {
        "product_name": f"{name} - {location} - {label}",
        "price": f"{price:.2f}",
        "category_number": CATEGORY_NUMBER,
        "sub_category_number": SUB_CATEGORY_NUMBER,
        "venue_name": name,
        "city": city,
        "district": district,
        "price_type": price_type,
        "list_price": f"{list_price:.2f}" if list_price and list_price > price else "",
        "price_valid_until": str(offer.get("priceValidUntil") or "")[:10],
        "provider_id": provider_id,
        "source_url": url,
    }


def scrape_city(session, slug, max_pages, stats, first_html=None):
    rows = []
    page = 1
    url = f"{LISTING_URL}/{slug}"
    referer = LISTING_URL

    while page <= max_pages:
        page_url = url if page == 1 else f"{url}?page={page}"
        page_html = first_html if (page == 1 and first_html) else fetch_html(session, page_url, referer)
        if page_html is None:
            logging.error(f"Giving up on {slug} at page {page}")
            stats["failed_pages"] += 1
            break
        stats["requests"] += 0 if (page == 1 and first_html) else 1

        elements = item_list(page_html)
        details = card_details(page_html)

        page_rows = []
        for element in elements:
            row = parse_venue(element, details, slug)
            if row:
                page_rows.append(row)
            else:
                stats["skipped_no_price"] += 1

        logging.info(f"{slug} page {page}: {len(elements)} venues, {len(page_rows)} with a TRY price")
        rows.extend(page_rows)

        if not elements or not NEXT_RE.search(page_html):
            break
        referer = page_url
        page += 1
        time.sleep(PAGE_DELAY)

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
        description="Düğün.com wedding-hall prices (0969006)"
    )
    parser.add_argument(
        "--cities",
        default="",
        help="Comma-separated city slugs (e.g. istanbul,ankara); default: all provinces.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_PAGES,
        help=f"Listing pages per city (default: {MAX_PAGES}); use 1 for a bounded live run.",
    )
    parser.add_argument("--date", default=TODAY, help="Output date (default: today)")
    args = parser.parse_args()

    wanted = [slug.strip() for slug in args.cities.split(",") if slug.strip()]
    stats = {"skipped_no_price": 0, "failed_pages": 0, "requests": 0}
    rows = []
    seen = set()

    with requests.Session(impersonate="chrome") as session:
        session.headers.update(HEADERS)

        # Homepage first.
        try:
            session.get(HOME_URL, timeout=REQUEST_TIMEOUT)
        except RequestException as error:
            logging.warning(f"Homepage request failed: {error}")
        time.sleep(PAGE_DELAY)

        # The /dugun-salonlari index only links the biggest cities; the Istanbul
        # listing page links every province, so it doubles as the city list.
        first_slug = wanted[0] if wanted else "istanbul"
        first_html = fetch_html(session, f"{LISTING_URL}/{first_slug}", HOME_URL)
        if first_html is None:
            logging.error("First listing page failed. Existing CSV was not overwritten.")
            return
        stats["requests"] += 1
        slugs = wanted or city_slugs(first_html)
        logging.info(f"{len(slugs)} cities to scrape")
        time.sleep(PAGE_DELAY)

        for slug in slugs:
            for row in scrape_city(session, slug, args.max_pages, stats, first_html if slug == first_slug else None):
                key = row["source_url"] or row["product_name"]
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
            time.sleep(PAGE_DELAY)

    per_person = sum(1 for row in rows if row["price_type"] == "per_person")
    logging.info(
        f"Rows: {len(rows)} ({per_person} per person, {len(rows) - per_person} package); "
        f"skipped without a TRY price: {stats['skipped_no_price']}; "
        f"failed pages: {stats['failed_pages']}; listing requests: {stats['requests']}"
    )

    if rows:
        save_to_csv(rows, OUTPUT_DIR / f"dugun_com_{args.date}.csv")
    else:
        logging.warning("No venues collected. Existing CSV was not overwritten.")


if __name__ == "__main__":
    main()
