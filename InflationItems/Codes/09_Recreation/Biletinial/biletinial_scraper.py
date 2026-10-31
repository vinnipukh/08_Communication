from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BiletinialTiyatroScraper")

BASE_DIR = Path(__file__).resolve().parent


def find_project_root():
    for candidate in [BASE_DIR, *BASE_DIR.parents]:
        if (candidate / "InflationItems").is_dir():
            return candidate

    for candidate in [BASE_DIR, *BASE_DIR.parents]:
        if (candidate / ".git").exists():
            return candidate

    return BASE_DIR


PROJECT_ROOT = find_project_root()

DATA_DIR = (
    PROJECT_ROOT
    / "InflationItems"
    / "Datas"
    / "09_Recreation"
    / "Biletinial"
)

BASE_URL = "https://biletinial.com"
THEATRE_URL = "https://biletinial.com/tr-tr/tiyatro"
# Infinite-scroll endpoint used by the listing page after its first 50 server-rendered cards.
MORE_ITEMS_URL = "https://biletinial.com/List/GetMoreItems"
MORE_ITEMS_PARAMS = {
    "region": "tr-tr",
    "cityId": "",
    "cityUrl": "",
    "order": 0,
    "isKids": "false",
    "isCampaign": "false",
    "isForeign": "false",
    "organizerUrl": "tiyatro",
}

CATEGORY_NUMBER = "9"
SUBCATEGORY_NUMBER = "0961002"

# Cinema (TÜİK 0961001). Discovery: listing -> film page (event id, cities) ->
# /dynamic/get_seances (cinemas showing the film) -> cinema page /tr-tr/mekan/<slug>,
# whose film cards carry the cinema's "Başlangıç Fiyatı" per film. Prices per ticket
# type only appear after the seat-selection POST, which is Turnstile-protected.
CINEMA_URL = "https://biletinial.com/tr-tr/sinema"
CINEMA_SUBCATEGORY_NUMBER = "0961001"
SEANCES_URL = BASE_URL + "/dynamic/get_seances/{event_id}/{city_id}/{date}/1/tr"
CINEMA_DELAY_SECONDS = 1.5
MAX_CINEMA_FILMS = 30
MAX_CINEMA_VENUES = 150
# "İstanbul (Tümü)" covers the Avrupa (5) and Anadolu (77) city ids.
ISTANBUL_ALL_CITY_ID = "147"
ISTANBUL_SIDE_CITY_IDS = {"5", "77"}

REQUEST_TIMEOUT = 40
MAX_RETRIES = 4
MAX_MORE_PAGES = 60
DETAIL_DELAY_SECONDS = 0.5

HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

MONTHS = (
    "Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|"
    "Temmuz|Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|Aralık|Aralik"
)

SESSION_RE = re.compile(
    rf"(?P<session>"
    rf"\d{{1,2}}\s+(?:{MONTHS})"
    rf"(?:"
    rf"\s+\d{{4}}(?:\s+[A-Za-zÇĞİÖŞÜçğıöşü]+)?"
    rf"|\s+[A-Za-zÇĞİÖŞÜçğıöşü]+(?:\s+\d{{4}})?"
    rf")?"
    rf"\s*·\s*\d{{2}}:\d{{2}}"
    rf")",
    re.IGNORECASE,
)

STARTING_PRICE_RE = re.compile(
    r"Başlangıç\s+Fiyatı\s*"
    r"(?P<price>\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)"
    r"\s*₺",
    re.IGNORECASE,
)

CATEGORY_PRICE_RE = re.compile(
    r"(?P<label>"
    r"(?:"
    r"\d+\.\s*Kategori"
    r"(?:\s+(?:İndirimli|Indirimli|Tam|Öğrenci|Ogrenci|Balkon|VIP|Çocuk|Cocuk|Yetişkin|Yetiskin))?"
    r"|Loca\s+Tam"
    r"|Loca\s+Öğrenci"
    r"|VIP(?:\s+\d+)?"
    r"|Protokol(?:\s+Fiyat)?"
    r"|Tam(?:\s+Bilet)?"
    r"|Öğrenci(?:\s+Bileti)?"
    r"|İndirimli|Indirimli"
    r"|Çocuk(?:\s+Bileti)?"
    r"|Yetişkin(?:\s+Bileti)?"
    r"|Genel(?:\s+Giriş)?"
    r"|Balkon|Parter|Loca"
    r")"
    r")\s+"
    r"(?P<price>\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)"
    r"\s*₺",
    re.IGNORECASE,
)



def normalize_text(value):
    return " ".join(
        str(value or "").replace("\xa0", " ").split()
    ).strip()


def parse_price(value):
    value = normalize_text(value)

    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    elif "." in value:
        parts = value.split(".")
        if len(parts) > 1 and len(parts[-1]) == 3:
            value = "".join(parts)

    return float(value)


def normalize_ticket_label(label):
    label = normalize_text(label)


    label = re.sub(
        r"^(\d+)\.\s*Kategori",
        lambda m: f"{m.group(1)}. Kategori",
        label,
        flags=re.IGNORECASE,
    )

    label = re.sub(
        r"^Vip\b",
        "VIP",
        label,
        flags=re.IGNORECASE,
    )

    label = re.sub(
        r"\bIndirimli\b",
        "İndirimli",
        label,
        flags=re.IGNORECASE,
    )

    return label


def canonical_url(url):
    absolute = urljoin(BASE_URL, url)
    parsed = urlparse(absolute)
    clean = parsed._replace(query="", fragment="")
    return urlunparse(clean).rstrip("/")


def build_session():
    session = requests.Session(impersonate="chrome")
    session.headers.update(HEADERS)

    return session


def get_with_retry(session, url, **kwargs):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT, **kwargs)
            if response.status_code not in (429, 500, 502, 503, 504):
                response.raise_for_status()
                return response
            logger.warning("HTTP %s for %s (attempt %d)", response.status_code, url, attempt)
        except RequestException as exc:
            if attempt == MAX_RETRIES:
                raise
            logger.warning("Request failed for %s (attempt %d): %s", url, attempt, exc)
        time.sleep(2 ** attempt)
    raise RequestException(f"Giving up on {url} after {MAX_RETRIES} attempts")


def add_event_url(event_urls, href):
    url = canonical_url(href)
    path = urlparse(url).path.rstrip("/")

    if path.startswith("/tr-tr/tiyatro/"):
        event_urls.add(url)


def collect_event_urls(session):
    event_urls = set()

    # Homepage first, then the listing page (first 50 cards are server-rendered).
    get_with_retry(session, BASE_URL + "/tr-tr")
    response = get_with_retry(session, THEATRE_URL)
    logger.info("Theatre page HTTP status: %s", response.status_code)

    soup = BeautifulSoup(response.text, "html.parser")
    for link in soup.select("a[href*='/tr-tr/tiyatro/']"):
        add_event_url(event_urls, link.get("href"))

    logger.info("Listing page | theatre detail URLs: %d", len(event_urls))

    ajax_headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": THEATRE_URL,
    }

    for page_number in range(2, MAX_MORE_PAGES + 1):
        response = get_with_retry(
            session,
            MORE_ITEMS_URL,
            params={**MORE_ITEMS_PARAMS, "page": page_number},
            headers=ajax_headers,
        )
        items = (response.json() or {}).get("items") or []

        for item in items:
            if item.get("seoUrl"):
                add_event_url(
                    event_urls,
                    f"/tr-tr/{item.get('organizerUrl') or 'tiyatro'}/{item['seoUrl']}",
                )

        logger.info(
            "More items page %d | items: %d | theatre detail URLs: %d",
            page_number,
            len(items),
            len(event_urls),
        )

        if not items:
            break

        time.sleep(DETAIL_DELAY_SECONDS)

    return sorted(event_urls)


def fetch_html(session, url):
    return get_with_retry(session, url).text


def split_session_blocks(page_text):

    matches = list(SESSION_RE.finditer(page_text))
    blocks = []

    for index, match in enumerate(matches):
        block_start = match.start()
        block_end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(page_text)
        )

        block_text = normalize_text(page_text[block_start:block_end])
        session_text = normalize_text(match.group("session"))
        blocks.append((session_text, block_text))

    return blocks


def extract_venue(block_text, session_text):
    position = block_text.find(session_text)

    if position < 0:
        return ""

    after = block_text[position + len(session_text):]

    stop_words = [
        "Organizasyon:",
        "Başlangıç Fiyatı",
        "Bilet Fiyatları",
        "BİLETİNİ AL",
        "TÜKENDİ",
    ]

    positions = []

    for word in stop_words:
        pos = after.find(word)
        if pos >= 0:
            positions.append(pos)

    if positions:
        after = after[:min(positions)]

    return normalize_text(after).strip(" ·|-")


def extract_category_prices(block_text):
    match_section = re.search(
        r"Bilet\s+Fiyatları",
        block_text,
        flags=re.IGNORECASE,
    )

    if match_section:
        section = block_text[match_section.end():]
    else:
        section = block_text


    for pattern in (
        r"\bYorumlar\b",
        r"\bKadro\b",
        r"\bGaleri\b",
        r"\bGenel Satış:",
        r"\bSatışa Açılma",
        r"\bEtkinlik Hakkında\b",
    ):
        stop_match = re.search(
            pattern,
            section,
            flags=re.IGNORECASE,
        )

        if stop_match:
            section = section[:stop_match.start()]

    result = []
    seen_labels = set()

    for match in CATEGORY_PRICE_RE.finditer(section):
        label = normalize_ticket_label(
            match.group("label")
        )

        price = parse_price(
            match.group("price")
        )

        if price <= 0:
            continue

        label_key = label.casefold()


        if label_key in seen_labels:
            continue

        seen_labels.add(label_key)

        result.append(
            (
                label,
                price,
            )
        )

    if result:
        return result

    start_match = STARTING_PRICE_RE.search(
        block_text
    )

    if start_match:
        return [
            (
                "Başlangıç Fiyatı",
                parse_price(
                    start_match.group("price")
                ),
            )
        ]

    return []


def parse_event_page(html_text, url):
    soup = BeautifulSoup(html_text, "html.parser")

    h1 = soup.find("h1")
    if h1 is None:
        return []

    event_name = normalize_text(h1.get_text(" ", strip=True))
    page_text = normalize_text(soup.get_text(" ", strip=True))

    if "Bilet ve Seanslar" not in page_text:
        return []

    ticket_start = page_text.find("Bilet ve Seanslar")
    ticket_text = page_text[ticket_start:]

    rows = []

    for session_text, block_text in split_session_blocks(ticket_text):
        if (
            "Bilet Fiyatları" not in block_text
            and "Başlangıç Fiyatı" not in block_text
        ):
            continue

        venue = extract_venue(block_text, session_text)
        category_prices = extract_category_prices(block_text)

        for ticket_type, price in category_prices:
            parts = [event_name, session_text]

            if venue:
                parts.append(venue)

            parts.append(ticket_type)

            rows.append({
                "product_name": " - ".join(
                    normalize_text(part)
                    for part in parts
                    if normalize_text(part)
                ),
                "price": price,
                "category_number": CATEGORY_NUMBER,
                "sub_category_number": SUBCATEGORY_NUMBER,
                "_source_url": url,
            })

    return rows


def collect_cinema_films(session):
    films = []
    seen = set()

    response = get_with_retry(session, CINEMA_URL)
    logger.info("Cinema page HTTP status: %s", response.status_code)

    soup = BeautifulSoup(response.text, "html.parser")
    for link in soup.select("a[href*='/tr-tr/sinema/']"):
        url = canonical_url(link.get("href"))
        if url in seen or not urlparse(url).path.startswith("/tr-tr/sinema/"):
            continue
        seen.add(url)
        films.append(url)

    # The listing has been complete on the first page (GetMoreItems -> hasMore false);
    # check once so a longer listing is not silently cut.
    time.sleep(CINEMA_DELAY_SECONDS)
    response = get_with_retry(
        session,
        MORE_ITEMS_URL,
        params={**MORE_ITEMS_PARAMS, "organizerUrl": "sinema", "page": 2},
        headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": CINEMA_URL,
        },
    )
    for item in (response.json() or {}).get("items") or []:
        if item.get("seoUrl"):
            url = canonical_url(f"/tr-tr/sinema/{item['seoUrl']}")
            if url not in seen:
                seen.add(url)
                films.append(url)

    logger.info("Cinema listing | film URLs: %d", len(films))
    return films


def parse_film_page(html_text):
    match = re.search(r"var\s+eventId\s*=\s*(\d+)", html_text)
    if not match:
        return None, []

    soup = BeautifulSoup(html_text, "html.parser")
    city_ids = []
    for link in soup.select(".cList .scrollList a[data-val]"):
        city_id = link.get("data-val")
        if city_id and city_id not in city_ids:
            city_ids.append(city_id)

    if ISTANBUL_ALL_CITY_ID in city_ids:
        city_ids = [c for c in city_ids if c not in ISTANBUL_SIDE_CITY_IDS]

    return match.group(1), city_ids


def collect_cinema_venues(session, film_urls, dates):
    venues = {}

    for index, film_url in enumerate(film_urls, start=1):
        time.sleep(CINEMA_DELAY_SECONDS)
        try:
            event_id, city_ids = parse_film_page(fetch_html(session, film_url))
        except RequestException as exc:
            logger.warning("[film %d/%d] request failed: %s", index, len(film_urls), exc)
            continue

        if not event_id:
            logger.warning("[film %d/%d] no event id: %s", index, len(film_urls), film_url)
            continue

        headers = {"X-Requested-With": "XMLHttpRequest", "Referer": film_url}

        for city_id in city_ids:
            for date in dates:
                time.sleep(CINEMA_DELAY_SECONDS)
                try:
                    response = get_with_retry(
                        session,
                        SEANCES_URL.format(event_id=event_id, city_id=city_id, date=date),
                        headers=headers,
                    )
                except RequestException as exc:
                    logger.warning("Seances failed for %s city %s: %s", film_url, city_id, exc)
                    continue

                found = 0
                soup = BeautifulSoup(response.text, "html.parser")
                for link in soup.select(".yn_cinema_info_title a[href*='/tr-tr/mekan/']"):
                    url = canonical_url(link.get("href"))
                    venues.setdefault(url, normalize_text(link.get_text(" ", strip=True)))
                    found += 1

                if found:
                    break

        logger.info(
            "[film %d/%d] %s | cities: %d | cinemas so far: %d",
            index,
            len(film_urls),
            film_url.rsplit("/", 1)[-1],
            len(city_ids),
            len(venues),
        )

    return venues


def parse_cinema_page(html_text, url, fallback_name):
    soup = BeautifulSoup(html_text, "html.parser")
    h1 = soup.find("h1")
    cinema_name = normalize_text(h1.get_text(" ", strip=True)) if h1 else fallback_name

    rows = []
    for card in soup.select("li.hpv2-event-card"):
        link = card.select_one("h3 a[href]")
        price_el = card.select_one(".hpv2-event-card__price strong")
        if link is None or price_el is None:
            continue
        if not urlparse(urljoin(BASE_URL, link.get("href"))).path.startswith("/tr-tr/sinema/"):
            continue

        price_text = normalize_text(price_el.get_text()).replace("₺", "").strip()
        try:
            price = parse_price(price_text)
        except ValueError:
            continue
        if price <= 0:
            continue

        film_name = normalize_text(link.get_text(" ", strip=True))
        rows.append({
            "product_name": f"{film_name} - {cinema_name} - Başlangıç Fiyatı",
            "price": price,
            "category_number": CATEGORY_NUMBER,
            "sub_category_number": CINEMA_SUBCATEGORY_NUMBER,
            "_source_url": url,
        })

    return rows


def scrape_cinema(session, max_films, max_venues):
    # Homepage first (also when the theatre part ran before in the same session).
    get_with_retry(session, BASE_URL + "/tr-tr")
    time.sleep(CINEMA_DELAY_SECONDS)
    film_urls = collect_cinema_films(session)[:max(0, max_films)]

    today = datetime.today()
    dates = [
        today.strftime("%Y-%m-%d"),
        (today + timedelta(days=1)).strftime("%Y-%m-%d"),
    ]
    venues = collect_cinema_venues(session, film_urls, dates)
    venue_items = sorted(venues.items())[:max(0, max_venues)]

    logger.info("Total cinema pages: %d (cap %d)", len(venue_items), max_venues)

    rows = []
    for index, (url, name) in enumerate(venue_items, start=1):
        time.sleep(CINEMA_DELAY_SECONDS)
        try:
            venue_rows = parse_cinema_page(fetch_html(session, url), url, name)
        except RequestException as exc:
            logger.warning("[cinema %d/%d] request failed: %s", index, len(venue_items), exc)
            continue
        rows.extend(venue_rows)
        logger.info(
            "[cinema %d/%d] %s | %d rows",
            index,
            len(venue_items),
            url.rsplit("/", 1)[-1],
            len(venue_rows),
        )

    return film_urls, venue_items, rows


def load_existing_rows(date_str, keep_subcategories):
    """Rows of the parts not scraped in this run, so `--only` keeps the other part."""
    output_file = DATA_DIR / f"biletinial_{date_str}.csv"
    if not keep_subcategories or not output_file.exists():
        return []

    with output_file.open(newline="", encoding="utf-8-sig") as file:
        return [
            {
                "product_name": row["product_name"],
                "price": float(row["price"]),
                "category_number": row["category_number"],
                "sub_category_number": row["sub_category_number"],
            }
            for row in csv.DictReader(file)
            if row.get("sub_category_number") in keep_subcategories
        ]


def dedupe_rows(rows):
    unique = []
    seen = set()

    for row in rows:
        key = (
            normalize_text(row["product_name"]).casefold(),
            round(float(row["price"]), 2),
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(row)

    return unique


def save_csv(rows, date_str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    output_file = (
        DATA_DIR
        / f"biletinial_{date_str}.csv"
    )

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.writer(file)

        writer.writerow(
            [
                "product_name",
                "price",
                "category_number",
                "sub_category_number",
            ]
        )

        for row in sorted(
            rows,
            key=lambda item: (
                item["product_name"].casefold(),
                item["price"],
            ),
        ):
            writer.writerow(
                [
                    row["product_name"],
                    f'{row["price"]:.2f}',
                    row["category_number"],
                    row["sub_category_number"],
                ]
            )

    return output_file


def scrape_theatre(session, max_events):
    event_urls = collect_event_urls(session)

    if max_events is not None:
        event_urls = event_urls[:max(0, max_events)]

    logger.info(
        "Total theatre detail URLs: %d",
        len(event_urls),
    )

    if not event_urls:
        logger.error("No theatre event URLs found.")
        return event_urls, []

    rows = []

    for index, url in enumerate(event_urls, start=1):
        try:
            html_text = fetch_html(session, url)

            event_rows = parse_event_page(
                html_text,
                url,
            )

            rows.extend(event_rows)

            logger.info(
                "[%d/%d] %s | %d rows",
                index,
                len(event_urls),
                url.rsplit("/", 1)[-1],
                len(event_rows),
            )

        except RequestException as exc:
            logger.warning(
                "[%d/%d] request failed: %s",
                index,
                len(event_urls),
                exc,
            )

        except Exception as exc:
            logger.warning(
                "[%d/%d] parse failed: %s",
                index,
                len(event_urls),
                exc,
            )

        if DETAIL_DELAY_SECONDS > 0:
            time.sleep(DETAIL_DELAY_SECONDS)

    return event_urls, rows


def main():
    parser = argparse.ArgumentParser(
        description="Biletinial theatre (0961002) and cinema (0961001) ticket scraper"
    )

    parser.add_argument(
        "--date",
        default=None,
        help="Output date, example: 2026-10-25",
    )

    parser.add_argument(
        "--only",
        choices=("theatre", "cinema"),
        default=None,
        help=(
            "Scrape only one part. Rows of the other part already in the same "
            "day's CSV are kept. Default: both."
        ),
    )

    parser.add_argument(
        "--max-events",
        type=int,
        default=None,
        help="Optional debug limit for theatre events. Default: no limit.",
    )

    parser.add_argument(
        "--max-films",
        type=int,
        default=MAX_CINEMA_FILMS,
        help=f"Cinema: films used to discover cinemas. Default: {MAX_CINEMA_FILMS}.",
    )

    parser.add_argument(
        "--max-cinemas",
        type=int,
        default=MAX_CINEMA_VENUES,
        help=f"Cinema: cinema pages read. Default: {MAX_CINEMA_VENUES}.",
    )

    args = parser.parse_args()

    date_str = (
        args.date
        or datetime.today().strftime("%Y-%m-%d")
    )

    run_theatre = args.only in (None, "theatre")
    run_cinema = args.only in (None, "cinema")

    session = build_session()
    rows = []
    event_urls = []
    film_urls = []
    venue_items = []
    theatre_rows = []
    cinema_rows = []

    try:
        if run_theatre:
            event_urls, theatre_rows = scrape_theatre(session, args.max_events)

            if not theatre_rows:
                logger.error("No theatre ticket prices parsed.")
                if args.only == "theatre":
                    sys.exit(1)

        if run_cinema:
            try:
                film_urls, venue_items, cinema_rows = scrape_cinema(
                    session,
                    args.max_films,
                    args.max_cinemas,
                )
            except RequestException as exc:
                logger.error("Cinema scrape failed: %s", exc)

            if not cinema_rows:
                logger.error("No cinema prices parsed.")

    finally:
        session.close()

    rows = dedupe_rows(theatre_rows) + dedupe_rows(cinema_rows)

    if not rows:
        logger.error("No ticket prices parsed.")
        sys.exit(1)

    keep = set()
    if not run_theatre:
        keep.add(SUBCATEGORY_NUMBER)
    if not run_cinema:
        keep.add(CINEMA_SUBCATEGORY_NUMBER)
    kept_rows = load_existing_rows(date_str, keep)

    output_file = save_csv(kept_rows + rows, date_str)

    print()
    print("------------------------------------------")
    print("Biletinial scraping completed.")
    print("category_number: 9")
    if run_theatre:
        print("Theatre (0961002) detail pages:", len(event_urls))
        print("Theatre ticket rows:", len(dedupe_rows(theatre_rows)))
    if run_cinema:
        print("Cinema (0961001) films / cinema pages:", len(film_urls), "/", len(venue_items))
        print("Cinema price rows:", len(dedupe_rows(cinema_rows)))
    if kept_rows:
        print("Rows kept from the existing CSV:", len(kept_rows))
    print("File:", output_file)
    print("------------------------------------------")


if __name__ == "__main__":
    main()
