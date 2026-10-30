from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path

import requests
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("DiyanetUmreScraper")


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
    / "Diyanet"
)

CATEGORY_NUMBER = "09"
SUBCATEGORY_NUMBER = "0980008"


PDF_URL = (
    "https://hacumre.diyanet.gov.tr/Documents/"
    "2026-2027%202.%20D%C3%96NEM%20UMRE%20TURLARI%20BRO%C5%9E%C3%9CR.pdf"
)

TCMB_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"

REQUEST_TIMEOUT = 45

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

ROOM_BY_CODE_SUFFIX = {
    "D": "4 Kişilik Oda",
    "C": "3 Kişilik Oda",
    "B": "2 Kişilik Oda",
}

PROGRAM_PATTERNS = [
    re.compile(
        r"Servisli\s+Normal\s+Konaklama\s+(\d+)\s+Günlük\s+Umre\s+Programı",
        re.IGNORECASE,
    ),
    re.compile(
        r"Yürüme\s+Normal\s+Konaklama\s+(\d+)\s+Günlük\s+Umre\s+Programı",
        re.IGNORECASE,
    ),
    re.compile(
        r"Yakın\s+Mesafe\s+Konaklama\s+Türü\s+(\d+)\s+Günlük\s+Umre\s+Programı",
        re.IGNORECASE,
    ),
]

TOUR_PATTERN = re.compile(
    r"(?P<tour>\d+)\.\s*TUR\s+"
    r"(?P<deadline>\d{2}\.\d{2}\.\d{4})\s+"
    r"(?P<body>.*?)"
    r"(?=(?:\d+\.\s*TUR)|(?:2\.\s*DÖNEM)|$)",
    re.IGNORECASE | re.DOTALL,
)

PRICE_CODE_PATTERN = re.compile(
    r"(?P<usd>\d{3,4})\s+"
    r"(?P<code>[A-Z]\d+[BCD])",
    re.IGNORECASE,
)


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


def normalize_text(value):
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def get_usd_try(session, override=None):
    if override is not None:
        rate = Decimal(str(override))
        logger.info("Using manual USD/TRY rate: %s", rate)
        return rate

    response = session.get(
        TCMB_URL,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)

    usd = root.find(".//Currency[@CurrencyCode='USD']")

    if usd is None:
        raise RuntimeError("USD rate was not found in TCMB XML.")

    value = (
        usd.findtext("ForexSelling")
        or usd.findtext("BanknoteSelling")
    )

    if not value:
        raise RuntimeError("TCMB USD selling rate is empty.")

    rate = Decimal(value.replace(",", "."))

    logger.info(
        "TCMB USD/TRY selling rate: %s",
        rate,
    )

    return rate


def download_pdf(session):
    logger.info("Downloading official Diyanet brochure...")

    response = session.get(
        PDF_URL,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(
            "Diyanet response is not a PDF. "
            "The official brochure URL may have changed."
        )

    return response.content


def detect_program_name(page_text):
    flat = normalize_text(page_text)

    for pattern in PROGRAM_PATTERNS:
        match = pattern.search(flat)

        if match:
            duration = match.group(1)

            if pattern is PROGRAM_PATTERNS[0]:
                return f"Servisli Normal Konaklama {duration} Günlük"

            if pattern is PROGRAM_PATTERNS[1]:
                return f"Yürüme Normal Konaklama {duration} Günlük"

            return f"Yakın Mesafe Konaklama {duration} Günlük"

    return None


def usd_to_try(usd_amount, usd_try_rate):
    value = (
        Decimal(str(usd_amount))
        * usd_try_rate
    )

    return value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def parse_brochure(
    pdf_bytes,
    usd_try_rate,
    include_expired=False,
):
    reader = PdfReader(
        BytesIO(pdf_bytes)
    )

    today = datetime.today().date()

    rows = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        raw_text = page.extract_text() or ""

        program_name = detect_program_name(
            raw_text
        )

        if not program_name:
            continue

        flat = normalize_text(
            raw_text
        )

        page_rows = 0

        for tour_match in TOUR_PATTERN.finditer(
            flat
        ):
            tour_number = int(
                tour_match.group("tour")
            )

            deadline_text = tour_match.group(
                "deadline"
            )

            deadline = datetime.strptime(
                deadline_text,
                "%d.%m.%Y",
            ).date()

            if (
                not include_expired
                and deadline < today
            ):
                continue

            body = tour_match.group(
                "body"
            )

            price_pairs = list(
                PRICE_CODE_PATTERN.finditer(
                    body
                )
            )

            for price_match in price_pairs:
                usd_price = Decimal(
                    price_match.group("usd")
                )

                bank_code = price_match.group(
                    "code"
                ).upper()

                room_type = ROOM_BY_CODE_SUFFIX.get(
                    bank_code[-1]
                )

                if not room_type:
                    continue

                product_name = (
                    f"Diyanet {program_name} - "
                    f"{tour_number}. Tur - "
                    f"{room_type} - "
                    f"Banka Kodu {bank_code}"
                )

                price_try = usd_to_try(
                    usd_price,
                    usd_try_rate,
                )

                rows.append(
                    {
                        "product_name": product_name,
                        "price": price_try,
                        "category_number": CATEGORY_NUMBER,
                        "sub_category_number": SUBCATEGORY_NUMBER,
                    }
                )

                page_rows += 1

        if page_rows:
            logger.info(
                "Page %d | %s | %d price variants",
                page_number,
                program_name,
                page_rows,
            )


    unique = {}

    for row in rows:
        unique[row["product_name"]] = row

    return list(unique.values())


def save_csv(rows, date_str):
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        DATA_DIR
        / f"diyanet_{date_str}.csv"
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
            key=lambda item: item[
                "product_name"
            ].casefold(),
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
            "Diyanet official Umrah scraper - "
            "CPI subcategory 0980008"
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
        help=(
            "Manual USD/TRY rate. If omitted, "
            "TCMB ForexSelling is used."
        ),
    )

    parser.add_argument(
        "--include-expired",
        action="store_true",
        help=(
            "Also include brochure tours whose "
            "application deadline has passed."
        ),
    )

    args = parser.parse_args()

    date_str = (
        args.date
        or datetime.today().strftime(
            "%Y-%m-%d"
        )
    )

    session = build_session()

    try:
        usd_try_rate = get_usd_try(
            session,
            args.usd_try,
        )

        pdf_bytes = download_pdf(
            session
        )

    finally:
        session.close()

    rows = parse_brochure(
        pdf_bytes,
        usd_try_rate,
        include_expired=args.include_expired,
    )

    if not rows:
        logger.error(
            "No current Diyanet Umrah prices were parsed."
        )
        sys.exit(1)

    output_file = save_csv(
        rows,
        date_str,
    )

    print()
    print("------------------------------------------")
    print("Diyanet Umrah scraping completed.")
    print("subcategory_number: 0980008")
    print("Rows:", len(rows))
    print("USD/TRY:", usd_try_rate)
    print("File:", output_file)
    print("------------------------------------------")


if __name__ == "__main__":
    main()
