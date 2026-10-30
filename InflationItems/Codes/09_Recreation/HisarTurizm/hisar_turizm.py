from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("HisarTurizmScraper")


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
    / "HisarTurizm"
)

CULTURE_URL = "https://hisarturizm.com.tr/kultur-turlari/"
UMRAH_URL = "https://hisarturizm.com.tr/umre-turlari/"
TCMB_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"

CATEGORY_NUMBER = "09"

DOMESTIC_WEEKEND = "0980002"
DOMESTIC_OTHER = "0980003"
INTERNATIONAL_PACKAGE = "0980006"
UMRAH_AGENCY = "0980009"

REQUEST_TIMEOUT = 45
BROWSER_TIMEOUT_MS = 60000
SCROLL_WAIT_MS = 700
MAX_SCROLL_ROUNDS = 100
STABLE_SCROLL_ROUNDS = 4

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

TOUR_CODE_RE = re.compile(r"\bTR\d{7}\b", re.IGNORECASE)

DATE_RE = re.compile(
    r"Gidiş\s*:\s*(\d{2}\.\d{2}\.\d{4}).*?"
    r"Dönüş\s*:\s*(\d{2}\.\d{2}\.\d{4})",
    re.IGNORECASE | re.DOTALL,
)

DURATION_RE = re.compile(
    r"(\d+)\s*Gece\s*/?\s*(\d+)\s*Gün",
    re.IGNORECASE,
)

ROOM_PRICE_RE = re.compile(

    r"(?P<room>[234])\s*['’]?\s*l[ıiuü]\s+Oda"
    r".{0,120}?"
    r"(?:(?P<tl>TL)\s*|(?P<usd>\$)\s*|(?P<eur>€)\s*)"
    r"(?P<price>\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)",
    re.IGNORECASE | re.DOTALL,
)

STATUS_RE = re.compile(
    r"\b(?:"
    r"Son\s+\d+\s+kişi|"
    r"\d+\s+kontenjan|"
    r"DOLU"
    r")\b",
    re.IGNORECASE,
)

TITLE_CODE_RE = re.compile(
    r"(?P<title>.+?)\s+"
    r"(?:(?:Son\s+\d+\s+kişi|\d+\s+kontenjan|DOLU)\s+)?"
    r"(?P<code>TR\d{7})\b",
    re.IGNORECASE,
)

FOREIGN_WORDS = {
    "kudüs",
    "amman",
    "ürdün",
    "balkan",
    "kosova",
    "saraybosna",
    "bosna",
    "sırbistan",
    "makedonya",
    "arnavutluk",
    "karadağ",
    "mısır",
    "kahire",
    "hindistan",
    "delhi",
    "fas",
    "marakeş",
    "tangier",
    "kazablanka",
    "dubai",
    "abu dhabi",
    "avrupa",
    "italya",
    "fransa",
    "almanya",
    "ispanya",
    "yunanistan",
    "bulgaristan",
    "romanya",
    "gürcistan",
    "batum",
    "tiflis",
    "azerbaycan",
    "bakü",
    "özbekistan",
    "japonya",
    "kore",
    "tayland",
    "singapur",
    "endonezya",
    "amerika",
    "ingiltere",
    "londra",
    "rusya",
    "moskova",
    "malta",
    "kıbrıs",
    "filistin",
}


def normalize_text(value):
    return " ".join(
        str(value or "")
        .replace("\xa0", " ")
        .split()
    ).strip()


def canonical_key(value):
    value = normalize_text(value).casefold()

    value = re.sub(
        r"[^\w]+",
        " ",
        value,
        flags=re.UNICODE,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def clean_tour_title(value):
    value = normalize_text(value)


    value = re.sub(
        r"\bSezon\s+Sezonu\b",
        "Sezon",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value


def is_sold_out_for_code(text, code):

    value = normalize_text(text)

    match = re.search(
        re.escape(code),
        value,
        flags=re.IGNORECASE,
    )

    if not match:
        return False


    before = value[
        max(0, match.start() - 90):
        match.start()
    ]

    return bool(
        re.search(
            r"\bDOLU\b",
            before,
            flags=re.IGNORECASE,
        )
    )


STATUS_BY_CODE_RE = re.compile(
    r"(?P<status>"
    r"DOLU|"
    r"Son\s+\d+\s+kişi|"
    r"\d+\s+kontenjan"
    r")\s+"
    r"(?P<code>TR\d{7})\b",
    re.IGNORECASE,
)


def extract_status_by_code(html_text):

    soup = BeautifulSoup(
        html_text,
        "html.parser",
    )

    page_text = normalize_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    statuses = {}

    for match in STATUS_BY_CODE_RE.finditer(
        page_text
    ):
        code = match.group(
            "code"
        ).upper()

        status = normalize_text(
            match.group(
                "status"
            )
        )

        statuses[
            code
        ] = status

    return statuses



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

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=10,
        pool_maxsize=10,
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)

    return session


def fetch_requests_html(session, url):
    response = session.get(
        url,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    if (
        not response.encoding
        or response.encoding.lower() == "iso-8859-1"
    ):
        response.encoding = (
            response.apparent_encoding
            or "utf-8"
        )

    return response.text


def count_tour_codes(html_text):
    return len(
        set(
            code.upper()
            for code in TOUR_CODE_RE.findall(
                BeautifulSoup(
                    html_text,
                    "html.parser",
                ).get_text(
                    " ",
                    strip=True,
                )
            )
        )
    )


def fetch_browser_html(url):

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "The Hisar page is dynamic on this run, but Playwright is not installed. "
            "Run: pip install playwright && playwright install chromium"
        ) from exc

    logger.info(
        "Requests did not expose tour cards; using browser fallback."
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
        )

        context = browser.new_context(
            locale="tr-TR",
            viewport={
                "width": 1440,
                "height": 1000,
            },
        )


        context.route(
            "**/*",
            lambda route: (
                route.abort()
                if route.request.resource_type
                in {"image", "media", "font"}
                else route.continue_()
            ),
        )

        page = context.new_page()

        response = page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=BROWSER_TIMEOUT_MS,
        )

        if response is not None:
            logger.info(
                "Browser HTTP status: %s",
                response.status,
            )


        page.wait_for_timeout(1500)

        stable_rounds = 0
        previous_count = -1

        for round_number in range(
            1,
            MAX_SCROLL_ROUNDS + 1,
        ):
            body_text = page.locator(
                "body"
            ).inner_text(
                timeout=10000
            )

            code_count = len(
                set(
                    code.upper()
                    for code in TOUR_CODE_RE.findall(
                        body_text
                    )
                )
            )

            logger.info(
                "Browser load round %d | visible tour codes: %d",
                round_number,
                code_count,
            )

            if code_count == previous_count:
                stable_rounds += 1
            else:
                stable_rounds = 0

            previous_count = code_count

            if stable_rounds >= STABLE_SCROLL_ROUNDS:
                break

            page.evaluate(
                "() => window.scrollTo(0, document.body.scrollHeight)"
            )

            page.wait_for_timeout(
                SCROLL_WAIT_MS
            )

        html_text = page.content()

        context.close()
        browser.close()

    return html_text


def fetch_full_html(session, url):
    html_text = fetch_requests_html(
        session,
        url,
    )

    soup = BeautifulSoup(
        html_text,
        "html.parser",
    )

    page_text = normalize_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    total_match = re.search(
        r"(\d+)\s+tur\s+bulundu",
        page_text,
        flags=re.IGNORECASE,
    )

    reported_total = (
        int(total_match.group(1))
        if total_match
        else None
    )

    card_count = len(
        extract_tour_cards(
            html_text
        )
    )

    logger.info(
        "Requests HTML tour cards: %d%s",
        card_count,
        (
            f" / site reports {reported_total}"
            if reported_total is not None
            else ""
        ),
    )

    if (
        card_count > 0
        and (
            reported_total is None
            or card_count >= reported_total
        )
    ):
        return html_text

    return fetch_browser_html(
        url
    )


def parse_decimal(number_text):
    value = normalize_text(
        number_text
    )

    if "," in value:
        value = (
            value
            .replace(".", "")
            .replace(",", ".")
        )

    elif value.count(".") > 1:
        value = value.replace(".", "")

    elif "." in value:
        left, right = value.rsplit(
            ".",
            1,
        )

        if len(right) == 3:
            value = left + right

    return Decimal(value)


def get_tcmb_rates(
    session,
    usd_override=None,
    eur_override=None,
):
    if (
        usd_override is not None
        and eur_override is not None
    ):
        return {
            "USD": Decimal(str(usd_override)),
            "EUR": Decimal(str(eur_override)),
        }

    response = session.get(
        TCMB_URL,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    root = ET.fromstring(
        response.content
    )

    rates = {}

    for code, override in (
        ("USD", usd_override),
        ("EUR", eur_override),
    ):
        if override is not None:
            rates[code] = Decimal(
                str(override)
            )
            continue

        currency = root.find(
            f".//Currency[@CurrencyCode='{code}']"
        )

        if currency is None:
            raise RuntimeError(
                f"{code} rate was not found in TCMB XML."
            )

        value = (
            currency.findtext(
                "ForexSelling"
            )
            or currency.findtext(
                "BanknoteSelling"
            )
        )

        if not value:
            raise RuntimeError(
                f"TCMB {code} selling rate is empty."
            )

        rates[code] = Decimal(
            value.replace(",", ".")
        )

    logger.info(
        "TCMB rates | USD/TRY=%s | EUR/TRY=%s",
        rates["USD"],
        rates["EUR"],
    )

    return rates


def convert_to_try(
    amount,
    currency,
    rates,
):
    if currency == "TRY":
        value = amount

    elif currency == "USD":
        value = amount * rates["USD"]

    elif currency == "EUR":
        value = amount * rates["EUR"]

    else:
        raise ValueError(
            f"Unsupported currency: {currency}"
        )

    return value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def find_card_for_code(code_element, code):
    current = code_element

    for _ in range(12):
        current = current.parent

        if current is None:
            break

        text = normalize_text(
            current.get_text(
                " ",
                strip=True,
            )
        )

        codes = {
            item.upper()
            for item in TOUR_CODE_RE.findall(
                text
            )
        }

        if codes != {code.upper()}:
            continue

        lower = text.casefold()

        if (
            "gidiş:" in lower
            and "dönüş:" in lower
            and "oda" in lower
        ):
            return current

    return None


def find_title_and_status(
    card,
    code,
):
    candidates = []

    for tag in card.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "strong",
            "p",
            "div",
            "span",
        ]
    ):
        text = normalize_text(
            tag.get_text(
                " ",
                strip=True,
            )
        )

        if code.casefold() not in text.casefold():
            continue


        if len(text) <= 250:
            candidates.append(text)

    candidates.sort(
        key=len
    )

    for text in candidates:
        match = TITLE_CODE_RE.search(
            text
        )

        if not match:
            continue

        title = normalize_text(
            match.group("title")
        )


        title = re.sub(
            r"^(?:Tur Programı|PDF)\s+",
            "",
            title,
            flags=re.IGNORECASE,
        )

        sold_out = bool(
            re.search(
                r"\bDOLU\b",
                text,
                flags=re.IGNORECASE,
            )
        )

        return clean_tour_title(title), sold_out

    full_text = normalize_text(
        card.get_text(
            " ",
            strip=True,
        )
    )

    code_index = full_text.casefold().find(
        code.casefold()
    )

    if code_index < 0:
        return code, False

    prefix = full_text[
        max(0, code_index - 180):
        code_index
    ].strip()

    prefix = STATUS_RE.sub(
        " ",
        prefix,
    )

    prefix = normalize_text(
        prefix
    )


    title = prefix[-120:].strip(
        " -|"
    )

    sold_out = bool(
        re.search(
            r"\bDOLU\b",
            full_text[:code_index + len(code)],
            flags=re.IGNORECASE,
        )
    )

    return clean_tour_title(title or code), sold_out


def parse_card_dates(text):
    match = DATE_RE.search(
        text
    )

    if not match:
        return None, None

    start = datetime.strptime(
        match.group(1),
        "%d.%m.%Y",
    ).date()

    end = datetime.strptime(
        match.group(2),
        "%d.%m.%Y",
    ).date()

    return start, end


def parse_duration(text):
    match = DURATION_RE.search(
        text
    )

    if not match:
        return None

    nights = int(
        match.group(1)
    )

    days = int(
        match.group(2)
    )

    return nights, days


def parse_room_prices(text):
    result = []

    for match in ROOM_PRICE_RE.finditer(
        text
    ):
        room_count = int(
            match.group("room")
        )

        amount = parse_decimal(
            match.group("price")
        )

        if match.group("tl"):
            currency = "TRY"

        elif match.group("usd"):
            currency = "USD"

        elif match.group("eur"):
            currency = "EUR"

        else:
            continue

        result.append(
            {
                "room_count": room_count,
                "amount": amount,
                "currency": currency,
            }
        )

    return result


def extract_tour_cards(html_text):
    soup = BeautifulSoup(
        html_text,
        "html.parser",
    )

    cards = {}

    for text_node in soup.find_all(
        string=TOUR_CODE_RE,
    ):
        parent = text_node.parent

        if parent is None:
            continue

        text = normalize_text(
            parent.get_text(
                " ",
                strip=True,
            )
        )

        match = TOUR_CODE_RE.search(
            text
        )

        if not match:
            continue

        code = match.group(0).upper()

        if code in cards:
            continue

        card = find_card_for_code(
            parent,
            code,
        )

        if card is not None:
            cards[code] = card

    return cards


def range_contains_full_weekend(
    start_date,
    end_date,
):
    if not start_date or not end_date:
        return False

    current = start_date
    has_saturday = False
    has_sunday = False

    while current <= end_date:
        if current.weekday() == 5:
            has_saturday = True

        elif current.weekday() == 6:
            has_sunday = True

        current += timedelta(
            days=1
        )

    return (
        has_saturday
        and has_sunday
    )


def looks_international(
    title,
    text,
    room_prices,
):

    if any(
        item["currency"] in {
            "USD",
            "EUR",
        }
        for item in room_prices
    ):
        return True

    haystack = canonical_key(
        f"{title} {text}"
    )

    return any(
        canonical_key(word) in haystack
        for word in FOREIGN_WORDS
    )


def classify_culture_tour(
    title,
    text,
    start_date,
    end_date,
    duration,
    room_prices,
):
    if looks_international(
        title,
        text,
        room_prices,
    ):
        return INTERNATIONAL_PACKAGE

    days = (
        duration[1]
        if duration
        else (
            (end_date - start_date).days + 1
            if start_date and end_date
            else None
        )
    )

    if (
        days is not None
        and days <= 4
        and range_contains_full_weekend(
            start_date,
            end_date,
        )
    ):
        return DOMESTIC_WEEKEND

    return DOMESTIC_OTHER


def make_product_name(
    source_label,
    title,
    code,
    start_date,
    duration,
    room_count,
):
    parts = [
        f"Hisar Turizm {source_label}",
        title,
    ]

    if start_date:
        parts.append(
            start_date.strftime(
                "%d.%m.%Y"
            )
        )

    if duration:
        parts.append(
            f"{duration[0]} Gece {duration[1]} Gün"
        )

    parts.append(
        f"{room_count} Kişilik Oda"
    )

    parts.append(
        code
    )

    return " - ".join(
        parts
    )


def parse_listing(
    html_text,
    listing_type,
    rates,
    include_sold_out=False,
):
    cards = extract_tour_cards(
        html_text
    )

    status_by_code = extract_status_by_code(
        html_text
    )

    logger.info(
        "%s listing: %d unique tour cards found",
        listing_type,
        len(cards),
    )

    logger.info(
        "%s listing: %d exact status labels found",
        listing_type,
        len(status_by_code),
    )

    rows = []

    for code, card in cards.items():
        text = normalize_text(
            card.get_text(
                " ",
                strip=True,
            )
        )

        title, _ = find_title_and_status(
            card,
            code,
        )


        exact_status = status_by_code.get(
            code
        )

        sold_out = (
            exact_status is not None
            and exact_status.casefold() == "dolu"
        )

        if sold_out and not include_sold_out:
            logger.info(
                "%s is sold out (%s); skipped",
                code,
                exact_status,
            )
            continue

        if exact_status is None:
            logger.warning(
                "%s has no exact availability label; keeping because a numeric price exists",
                code,
            )

        start_date, end_date = parse_card_dates(
            text
        )

        duration = parse_duration(
            text
        )

        room_prices = parse_room_prices(
            text
        )

        if not room_prices:
            logger.warning(
                "%s has no published numeric room price (e.g. $-); skipped",
                code,
            )
            continue

        if listing_type == "umrah":
            subcategory = UMRAH_AGENCY
            source_label = "Umre"

        else:
            subcategory = classify_culture_tour(
                title,
                text,
                start_date,
                end_date,
                duration,
                room_prices,
            )
            source_label = "Kültür Turu"

        for price_item in room_prices:
            price_try = convert_to_try(
                price_item["amount"],
                price_item["currency"],
                rates,
            )

            product_name = make_product_name(
                source_label,
                title,
                code,
                start_date,
                duration,
                price_item["room_count"],
            )

            rows.append(
                {
                    "product_name": product_name,
                    "price": price_try,
                    "category_number": CATEGORY_NUMBER,
                    "sub_category_number": subcategory,
                }
            )

    return rows


def final_dedupe(rows):
    result = []
    seen = set()

    for row in rows:
        key = (
            canonical_key(
                row["product_name"]
            ),
            row["sub_category_number"],
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            row
        )

    return result


def save_csv(
    rows,
    date_str,
):
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        DATA_DIR
        / f"hisar_turizm_{date_str}.csv"
    )

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.writer(
            file
        )

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
                item["sub_category_number"],
                item["product_name"].casefold(),
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
        description=(
            "Hisar Turizm Category 09 scraper: "
            "0980002, 0980003, 0980006, 0980009"
        )
    )

    parser.add_argument(
        "--date",
        default=None,
        help="Output date, e.g. 2026-10-24.",
    )

    parser.add_argument(
        "--usd-try",
        type=float,
        default=None,
        help="Manual USD/TRY rate; otherwise TCMB ForexSelling is used.",
    )

    parser.add_argument(
        "--eur-try",
        type=float,
        default=None,
        help="Manual EUR/TRY rate; otherwise TCMB ForexSelling is used.",
    )

    parser.add_argument(
        "--include-sold-out",
        action="store_true",
        help="Include Hisar tours marked DOLU.",
    )

    parser.add_argument(
        "--culture-only",
        action="store_true",
        help="Scrape only culture tours.",
    )

    parser.add_argument(
        "--umrah-only",
        action="store_true",
        help="Scrape only Umrah tours.",
    )

    args = parser.parse_args()

    if (
        args.culture_only
        and args.umrah_only
    ):
        parser.error(
            "--culture-only and --umrah-only cannot be used together."
        )

    date_str = (
        args.date
        or datetime.today().strftime(
            "%Y-%m-%d"
        )
    )

    session = build_session()

    rows = []

    try:
        rates = get_tcmb_rates(
            session,
            usd_override=args.usd_try,
            eur_override=args.eur_try,
        )

        if not args.umrah_only:
            logger.info(
                "Starting Hisar culture tours..."
            )

            culture_html = fetch_full_html(
                session,
                CULTURE_URL,
            )

            culture_rows = parse_listing(
                culture_html,
                "culture",
                rates,
                include_sold_out=args.include_sold_out,
            )

            rows.extend(
                culture_rows
            )

        if not args.culture_only:
            logger.info(
                "Starting Hisar Umrah tours..."
            )

            umrah_html = fetch_full_html(
                session,
                UMRAH_URL,
            )

            umrah_rows = parse_listing(
                umrah_html,
                "umrah",
                rates,
                include_sold_out=args.include_sold_out,
            )

            rows.extend(
                umrah_rows
            )

    finally:
        session.close()

    rows = final_dedupe(
        rows
    )

    if not rows:
        logger.error(
            "No Hisar Turizm rows were scraped."
        )
        sys.exit(1)

    output_file = save_csv(
        rows,
        date_str,
    )

    counts = {}

    for row in rows:
        code = row[
            "sub_category_number"
        ]

        counts[code] = (
            counts.get(code, 0)
            + 1
        )

    print()
    print("------------------------------------------")
    print("Hisar Turizm scraping completed.")
    print(
        "0980002 | Yurtiçi hafta sonu paket turu:",
        counts.get(DOMESTIC_WEEKEND, 0),
    )
    print(
        "0980003 | Diğer yurtiçi paket turlar:",
        counts.get(DOMESTIC_OTHER, 0),
    )
    print(
        "0980006 | Yurtdışı paket turu:",
        counts.get(INTERNATIONAL_PACKAGE, 0),
    )
    print(
        "0980009 | Umre paket ücreti (acente):",
        counts.get(UMRAH_AGENCY, 0),
    )
    print()
    print(
        "Total rows:",
        len(rows),
    )
    print(
        "File:",
        output_file,
    )
    print("------------------------------------------")


if __name__ == "__main__":
    main()
