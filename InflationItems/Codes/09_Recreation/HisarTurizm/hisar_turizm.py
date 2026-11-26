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

from bs4 import BeautifulSoup
from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


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

CULTURE_URL = "https://hisarturizm.com.tr/tum-kultur-turlari"
UMRAH_URL = "https://hisarturizm.com.tr/umre-turlari"
TCMB_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"

CATEGORY_NUMBER = "9"

DOMESTIC_WEEKEND = "0980002"
DOMESTIC_OTHER = "0980003"
INTERNATIONAL_PACKAGE = "0980006"
UMRAH_AGENCY = "0980009"

REQUEST_TIMEOUT = 45
MAX_RETRIES = 4
PAGE_DELAY_SECONDS = 1.0
MAX_PAGES = 100

HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

CURRENCY_SYMBOLS = {
    "$": "USD",
    "€": "EUR",
    "₺": "TRY",
}

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



def build_session():
    session = requests.Session(
        impersonate="chrome",
    )

    session.headers.update(HEADERS)

    return session


def request_with_retry(session, method, url, **kwargs):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.request(
                method,
                url,
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            )

            if response.status_code not in (429, 500, 502, 503, 504):
                response.raise_for_status()
                return response

            logger.warning(
                "HTTP %s for %s (attempt %d)",
                response.status_code,
                url,
                attempt,
            )

        except RequestException as exc:
            if attempt == MAX_RETRIES:
                raise

            logger.warning(
                "Request failed for %s (attempt %d): %s",
                url,
                attempt,
                exc,
            )

        time.sleep(2 ** attempt)

    raise RequestException(
        f"Giving up on {url} after {MAX_RETRIES} attempts"
    )


def parse_price_text(text):
    # "$1.725" / "€1.350" / "₺12.500" -> (Decimal, currency); None for "Dolu", "$-" etc.
    text = normalize_text(text)

    if not text or text[0] not in CURRENCY_SYMBOLS:
        return None

    number = text[1:].strip()

    if not re.fullmatch(r"[\d.,]+", number):
        return None

    amount = parse_decimal(number)

    if amount <= 0:
        return None

    return amount, CURRENCY_SYMBOLS[text[0]]


def parse_card(card):
    # One <article class="tl-card"> on the listing pages of the 2026-11 site
    # (Laravel; the old WordPress `tourFrontend` JSON / admin-ajax is gone).
    code = (card.get("data-stats-tour") or "").strip().upper()

    if not code:
        return None

    def text_of(selector):
        node = card.select_one(selector)
        return normalize_text(node.get_text(" ")) if node else ""

    title_link = card.select_one(".tl-title-link")

    date_node = card.select_one("time.tl-date")

    nights_match = re.search(
        r"(\d+)\s*gece\s*[·.]\s*(\d+)\s*g[üu]n",
        text_of(".tl-meta"),
        re.IGNORECASE,
    )

    if nights_match:
        duration = (int(nights_match.group(1)), int(nights_match.group(2)))

    else:
        nights = re.search(r"\d+", text_of(".tl-date-nights"))
        duration = (
            (int(nights.group()), int(nights.group()) + 1)
            if nights
            else None
        )

    # room count -> (amount, currency)
    prices = {}

    label = re.search(r"(\d+)\s*ki[şs]ilik", text_of(".tl-offer-label"))
    main = parse_price_text(text_of(".tl-price-amount"))

    if label and main:
        prices[int(label.group(1))] = main

    for other in card.select(".tl-offer-others > span"):
        other_count = re.match(r"\s*(\d+)", other.get_text())
        strong = other.find("strong")
        other_price = (
            parse_price_text(strong.get_text())
            if strong
            else None
        )

        if other_count and other_price:
            prices[int(other_count.group(1))] = other_price

    stops = " ".join(
        normalize_text(span.get_text())
        for span in card.select(".tl-stops span")
    )

    return {
        "id": code,
        "title": normalize_text(title_link.get_text()) if title_link else code,
        "concept": text_of(".tl-chip-concept"),
        "is_full": "is-full" in (card.get("class") or []),
        "departure": (
            parse_iso_date(date_node.get("datetime")) if date_node else None
        ),
        "duration": duration,
        "route": f"{text_of('.tl-meta')} {stops}",
        "prices": prices,
    }


def parse_iso_date(value):
    try:
        return datetime.strptime(
            normalize_text(value),
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return None


def fetch_tours(session, url):
    tours = {}
    page = 1

    while page <= MAX_PAGES:
        if page > 1:
            time.sleep(PAGE_DELAY_SECONDS)

        response = request_with_retry(
            session,
            "GET",
            url,
            params={"sayfa": page} if page > 1 else None,
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        cards = soup.select("article.tl-card")

        for card in cards:
            tour = parse_card(card)

            if tour:
                tours[tour["id"]] = tour

        logger.info(
            "%s page %d | cards: %d | unique tours: %d",
            url,
            page,
            len(cards),
            len(tours),
        )

        if not cards or not soup.select_one(
            ".tl-pages a[rel='next']"
        ):
            break

        page += 1

    if not tours:
        raise RuntimeError(
            f"No tour cards found on {url}; the Hisar page layout has changed."
        )

    return list(tours.values())


def tour_room_prices(tour):
    # Economy packages publish 2/3/4-person rooms, others only the 2-person room.
    room_counts = (
        (2, 3, 4)
        if canonical_key(tour.get("concept")) == "ekonomik"
        else (2,)
    )

    return [
        {
            "room_count": room_count,
            "amount": tour["prices"][room_count][0],
            "currency": tour["prices"][room_count][1],
        }
        for room_count in room_counts
        if room_count in tour["prices"]
    ]


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


def parse_tours(
    tours,
    listing_type,
    rates,
    include_sold_out=False,
):
    logger.info(
        "%s listing: %d unique tours found",
        listing_type,
        len(tours),
    )

    rows = []

    for tour in tours:
        code = tour["id"].upper()

        title = clean_tour_title(
            tour.get("title") or code
        )

        if tour.get("is_full") and not include_sold_out:
            logger.info(
                "%s is sold out (DOLU); skipped",
                code,
            )
            continue

        start_date = tour.get("departure")

        duration = tour.get("duration")

        end_date = (
            start_date + timedelta(days=duration[1] - 1)
            if start_date and duration
            else None
        )

        room_prices = tour_room_prices(
            tour
        )

        if not room_prices:
            logger.warning(
                "%s has no published room price; skipped",
                code,
            )
            continue

        if listing_type == "umrah":
            subcategory = UMRAH_AGENCY
            source_label = "Umre"

        else:
            text = tour.get("route") or ""

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

            culture_tours = fetch_tours(
                session,
                CULTURE_URL,
            )

            culture_rows = parse_tours(
                culture_tours,
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

            umrah_tours = fetch_tours(
                session,
                UMRAH_URL,
            )

            umrah_rows = parse_tours(
                umrah_tours,
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
