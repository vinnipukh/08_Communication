"""DüğünBuketi wedding-hall prices for TÜİK 09 item 0969006
("Event hall rental for wedding, engagement, and other events").

DüğünBuketi is a Laravel + Inertia site: every listing page
`/p/dugun-salonlari/<city>?page=N` (12 venues) carries its data as JSON in
`<script data-page="app" type="application/json">`. Per venue the JSON has
`min_price` (the card's "Başlangıç Fiyatı") and, for most venues, the per-person
starting menus `weekdaysMenu` / `weekendsMenu` (`max_price`, slug `yemekli-...` or
`kokteyl-...`).

Price types (checked against venue pages on 2026-10-31):
- menus present  -> per-person rows from the menus (hafta içi and hafta sonu);
- menus null     -> `min_price` is the package price ("Yemeksiz paket fiyatı");
- no menu fields (unclaimed venues, prices hidden on the venue page)
                 -> type inferred from the amount (< 10,000 TL = per person).
The `price_type_source` column says which rule was used.

Output: InflationItems/Datas/09_Recreation/DugunBuketi/dugunbuketi_YYYY-MM-DD.csv
"""

import argparse
import csv
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


BASE_URL = "https://dugunbuketi.com"
HOME_URL = "https://www.dugunbuketi.com/"
LISTING_URL = f"{BASE_URL}/p/dugun-salonlari/{{city}}"

CATEGORY_NUMBER = "9"
SUB_CATEGORY_NUMBER = "0969006"

OUTPUT_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "DugunBuketi"
)

TODAY = datetime.now().strftime("%Y-%m-%d")

HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
}

PAGE_JSON_RE = re.compile(
    r'<script data-page="app" type="application/json">(.*?)</script>', re.S
)

# Inferred type for venues without menu data: per-person menus on the site are
# 35-3,000 TL, package prices 15,000-120,000 TL (2026-10-31).
PER_PERSON_MAX = 10000
PER_PERSON_MIN = 100
PACKAGE_MIN = 5000

CSV_COLUMNS = [
    "product_name",
    "price",
    "category_number",
    "sub_category_number",
    "venue_name",
    "city",
    "district",
    "price_type",
    "menu_type",
    "week_period",
    "price_type_source",
    "listing_start_price",
    "max_capacity",
    "membership_type",
    "place_id",
    "source_url",
]

MAX_PAGES = 60
PAGE_DELAY = 1.5
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


def fetch_page_data(session, url, referer):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, headers={"Referer": referer}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                match = PAGE_JSON_RE.search(response.text)
                if match:
                    return json.loads(match.group(1))
                logging.warning(f"No Inertia page data in {url} (attempt {attempt})")
            else:
                logging.warning(f"HTTP {response.status_code} for {url} (attempt {attempt})")

        except (RequestException, ValueError) as error:
            logging.warning(f"Request failed for {url} (attempt {attempt}): {error}")

        time.sleep(PAGE_DELAY * attempt * 2)

    return None


def clean(text):
    return " ".join(str(text or "").split())


def to_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def menu_type(menu):
    slug = (menu or {}).get("slug") or ""
    if slug.startswith("yemekli"):
        return "Yemekli"
    if slug.startswith("kokteyl"):
        return "Kokteyl"
    return ""


def venue_rows(place, city_name):
    """Return (rows, skipped) for one venue card."""
    name = clean(place.get("name"))
    if not name or not place.get("has_display_price"):
        return [], 1

    city_name = clean((place.get("city") or {}).get("name")) or city_name
    district = clean((place.get("district") or {}).get("name"))
    location = f"{city_name}/{district}" if district else city_name
    start_price = to_number(place.get("min_price"))

    base = {
        "category_number": CATEGORY_NUMBER,
        "sub_category_number": SUB_CATEGORY_NUMBER,
        "venue_name": name,
        "city": city_name,
        "district": district,
        "listing_start_price": f"{start_price:.2f}" if start_price else "",
        "max_capacity": place.get("max_capacity") or "",
        "membership_type": place.get("membership_type", ""),
        "place_id": place.get("id") or "",
        "source_url": f"{BASE_URL}/fiyati/{place.get('slug')}" if place.get("slug") else "",
    }

    def row(price, price_type, label, menu="", period="", source=""):
        return {
            "product_name": f"{name} - {location} - {label}",
            "price": f"{price:.2f}",
            "price_type": price_type,
            "menu_type": menu,
            "week_period": period,
            "price_type_source": source,
            **base,
        }

    rows = []
    has_menu_fields = "weekdaysMenu" in place or "weekendsMenu" in place
    menus = [
        ("Hafta İçi", place.get("weekdaysMenu")),
        ("Hafta Sonu", place.get("weekendsMenu")),
    ]

    if any(menu for _, menu in menus):
        for period, menu in menus:
            price = to_number((menu or {}).get("max_price"))
            if price is None or price < PER_PERSON_MIN:
                continue
            kind = menu_type(menu)
            label = f"Kişi Başı {period}" + (f" ({kind})" if kind else "")
            rows.append(row(price, "per_person", label, kind, period, "menu"))
    elif start_price is not None:
        if has_menu_fields:
            if start_price >= PACKAGE_MIN:
                rows.append(row(start_price, "package", "Paket (Yemeksiz)", "Yemeksiz", "", "no_menu"))
        elif start_price < PER_PERSON_MAX:
            if start_price >= PER_PERSON_MIN:
                rows.append(row(start_price, "per_person", "Kişi Başı", "", "", "inferred"))
        else:
            rows.append(row(start_price, "package", "Paket", "", "", "inferred"))

    return rows, 0 if rows else 1


def scrape_city(session, city, max_pages, stats, first_page=None):
    rows = []
    page = 1
    url = LISTING_URL.format(city=city["slug"])
    referer = BASE_URL + "/"

    while page <= max_pages:
        page_url = url if page == 1 else f"{url}?page={page}"
        data = first_page if (page == 1 and first_page) else fetch_page_data(session, page_url, referer)
        if data is None:
            logging.error(f"Giving up on {city['slug']} at page {page}")
            stats["failed_pages"] += 1
            break

        props = data.get("props") or {}
        places = props.get("places") or {}
        items = places.get("data") or []

        page_rows = []
        for place in items:
            venue, skipped = venue_rows(place, city["name"])
            page_rows.extend(venue)
            stats["skipped"] += skipped

        logging.info(
            f"{city['name']} page {page}: {len(items)} venues, {len(page_rows)} rows "
            f"(site total {places.get('total')})"
        )
        rows.extend(page_rows)

        if not items or not places.get("next_page_url"):
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
        description="DüğünBuketi wedding-hall prices (0969006)"
    )
    parser.add_argument(
        "--cities",
        default="",
        help="Comma-separated city slugs (e.g. istanbul,ankara); default: all cities the site lists.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_PAGES,
        help=f"Listing pages of 12 venues per city (default: {MAX_PAGES}); use 1 for a bounded live run.",
    )
    parser.add_argument("--date", default=TODAY, help="Output date (default: today)")
    args = parser.parse_args()

    wanted = [slug.strip() for slug in args.cities.split(",") if slug.strip()]
    stats = {"skipped": 0, "failed_pages": 0}
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

        # The İstanbul listing page also carries the site's city list.
        first_city = wanted[0] if wanted else "istanbul"
        first_data = fetch_page_data(session, LISTING_URL.format(city=first_city), BASE_URL + "/")
        if first_data is None:
            logging.error("First listing page failed. Existing CSV was not overwritten.")
            return

        site_cities = ((first_data.get("props") or {}).get("shared") or {}).get("cities") or []
        city_names = {city.get("slug"): clean(city.get("name")) for city in site_cities}
        slugs = wanted or [city.get("slug") for city in site_cities if city.get("slug")]
        logging.info(f"{len(slugs)} cities to scrape")
        time.sleep(PAGE_DELAY)

        for slug in slugs:
            city = {"slug": slug, "name": city_names.get(slug, slug)}
            first_page = first_data if slug == first_city else None
            for row in scrape_city(session, city, args.max_pages, stats, first_page):
                key = (row["place_id"], row["price_type"], row["week_period"])
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
            time.sleep(PAGE_DELAY)

    per_person = sum(1 for row in rows if row["price_type"] == "per_person")
    logging.info(
        f"Rows: {len(rows)} ({per_person} per person, {len(rows) - per_person} package); "
        f"venues skipped without a usable price: {stats['skipped']}; failed pages: {stats['failed_pages']}"
    )

    if rows:
        save_to_csv(rows, OUTPUT_DIR / f"dugunbuketi_{args.date}.csv")
    else:
        logging.warning("No venues collected. Existing CSV was not overwritten.")


if __name__ == "__main__":
    main()
