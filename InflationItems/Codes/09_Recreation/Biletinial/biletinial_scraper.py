from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


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

CATEGORY_NUMBER = "09"
SUBCATEGORY_NUMBER = "0961002"

REQUEST_TIMEOUT = 40
BROWSER_TIMEOUT_MS = 60000
SCROLL_WAIT_MS = 900
MAX_SCROLL_ROUNDS = 120
STABLE_ROUNDS_TO_STOP = 5
DETAIL_DELAY_SECONDS = 0.15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
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
    session = requests.Session()

    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)

    return session


def collect_event_urls():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright gerekli.\n"
            "pip install playwright\n"
            "playwright install chromium"
        ) from exc

    event_urls = set()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        context = browser.new_context(
            locale="tr-TR",
            viewport={"width": 1440, "height": 1000},
        )

        context.route(
            "**/*",
            lambda route: (
                route.abort()
                if route.request.resource_type in {"image", "media", "font"}
                else route.continue_()
            ),
        )

        page = context.new_page()

        response = page.goto(
            THEATRE_URL,
            wait_until="domcontentloaded",
            timeout=BROWSER_TIMEOUT_MS,
        )

        if response is not None:
            logger.info("Theatre page HTTP status: %s", response.status)

        page.wait_for_timeout(1800)

        previous_count = -1
        stable_rounds = 0

        for round_number in range(1, MAX_SCROLL_ROUNDS + 1):
            hrefs = page.locator(
                "a[href*='/tr-tr/tiyatro/']"
            ).evaluate_all(
                "els => els.map(a => a.href)"
            )

            for href in hrefs:
                url = canonical_url(href)
                path = urlparse(url).path.rstrip("/")

                if path.startswith("/tr-tr/tiyatro/"):
                    event_urls.add(url)

            current_count = len(event_urls)

            logger.info(
                "Load round %d | theatre detail URLs: %d",
                round_number,
                current_count,
            )

            if current_count == previous_count:
                stable_rounds += 1
            else:
                stable_rounds = 0

            previous_count = current_count

            if stable_rounds >= STABLE_ROUNDS_TO_STOP:
                break

            page.evaluate(
                "() => window.scrollTo(0, document.body.scrollHeight)"
            )
            page.wait_for_timeout(SCROLL_WAIT_MS)

        context.close()
        browser.close()

    return sorted(event_urls)


def fetch_html(session, url):
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"

    return response.text


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


def main():
    parser = argparse.ArgumentParser(
        description="Biletinial theatre ticket scraper - 0961002"
    )

    parser.add_argument(
        "--date",
        default=None,
        help="Output date, example: 2026-10-25",
    )

    parser.add_argument(
        "--max-events",
        type=int,
        default=None,
        help="Optional debug limit. Default: no limit.",
    )

    args = parser.parse_args()

    date_str = (
        args.date
        or datetime.today().strftime("%Y-%m-%d")
    )

    event_urls = collect_event_urls()

    if args.max_events is not None:
        event_urls = event_urls[:max(0, args.max_events)]

    logger.info(
        "Total theatre detail URLs: %d",
        len(event_urls),
    )

    if not event_urls:
        logger.error("No theatre event URLs found.")
        sys.exit(1)

    session = build_session()
    rows = []

    try:
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

            except requests.RequestException as exc:
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

    finally:
        session.close()

    rows = dedupe_rows(rows)

    if not rows:
        logger.error("No theatre ticket prices parsed.")
        sys.exit(1)

    output_file = save_csv(rows, date_str)

    print()
    print("------------------------------------------")
    print("Biletinial theatre scraping completed.")
    print("category_number: 09")
    print("sub_category_number: 0961002")
    print("Theatre detail pages:", len(event_urls))
    print("Ticket rows:", len(rows))
    print("File:", output_file)
    print("------------------------------------------")


if __name__ == "__main__":
    main()
