from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import unicodedata
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

CATEGORY_NUMBER = "9"
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

# OCR. Every bank code in the brochure is letter + 6 digits + room letter, and its 6th-7th
# characters are the tour number (N021310D = tour 10), so a code read by OCR carries its own
# tour and a misread digit count is rejected. OCR often reads 0 as O inside codes.
OCR_SCALE = 3.0
OCR_CODE_PATTERN = re.compile(r"^([A-Z])([0-9O]{6})([BCD])$")
OCR_PRICE_PATTERN = re.compile(r"^\d{3,4}$")
OCR_TOUR_PATTERN = re.compile(r"(\d{1,2})\s*\.\s*TUR\b", re.IGNORECASE)
OCR_DATE_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")

# Program headings matched on accent-folded OCR text ("Günlük" is often read as "Gunluk").
OCR_PROGRAM_PATTERNS = [
    (re.compile(r"servisli\s*normal\s*konaklama\s*(\d+)\s*gunluk"), "Servisli Normal Konaklama {} Günlük"),
    (re.compile(r"yurume\s*normal\s*konaklama\s*(\d+)\s*gunluk"), "Yürüme Normal Konaklama {} Günlük"),
    (re.compile(r"yakin\s*mesafe\s*konaklama\s*turu\s*(\d+)\s*gunluk"), "Yakın Mesafe Konaklama {} Günlük"),
]


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


def text_layer_entries(raw_text):
    """(program, {bank_code: (tour, deadline_text, usd)}) from a page's PDF text layer."""
    program_name = detect_program_name(
        raw_text
    )

    entries = {}

    if not program_name:
        return None, entries

    flat = normalize_text(
        raw_text
    )

    for tour_match in TOUR_PATTERN.finditer(
        flat
    ):
        for price_match in PRICE_CODE_PATTERN.finditer(
            tour_match.group("body")
        ):
            entries[price_match.group("code").upper()] = (
                int(tour_match.group("tour")),
                tour_match.group("deadline"),
                price_match.group("usd"),
            )

    return program_name, entries


def fold_text(value):
    value = str(value or "").replace("ı", "i").replace("İ", "i").casefold()
    value = unicodedata.normalize("NFKD", value)
    return "".join(char for char in value if not unicodedata.combining(char))


def ocr_tokens(ocr_result):
    """Split each OCR box into whitespace tokens with an estimated x-range and the box's y."""
    tokens = []

    for box, text, _score in ocr_result or []:
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        x0, x1 = min(xs), max(xs)
        y_center = (min(ys) + max(ys)) / 2
        height = max(ys) - min(ys)
        text = normalize_text(text)

        if not text:
            continue

        char_width = (x1 - x0) / len(text)

        for match in re.finditer(r"\S+", text):
            tokens.append(
                {
                    "text": match.group(0),
                    "box_text": text,
                    "x0": x0 + match.start() * char_width,
                    "x1": x0 + match.end() * char_width,
                    "y": y_center,
                    "h": height,
                }
            )

    return tokens


def ocr_entries(ocr_result):
    """(program, {bank_code: (tour, deadline_text, usd)}) from RapidOCR boxes of one page.

    Prices are paired with the code printed right after them on the same row; the tour comes
    from the code itself and the deadline from the "N. TUR dd.mm.yyyy" cell of that tour.
    """
    tokens = ocr_tokens(
        ocr_result
    )

    folded = fold_text(
        " ".join(token["text"] for token in tokens)
    )

    program_name = None

    for pattern, template in OCR_PROGRAM_PATTERNS:
        match = pattern.search(folded)

        if match:
            program_name = template.format(match.group(1))
            break

    entries = {}

    if not program_name:
        return None, entries

    anchors = {}

    for token in tokens:
        for match in OCR_TOUR_PATTERN.finditer(token["box_text"]):
            anchors.setdefault(int(match.group(1)), token)

    dates = [
        token
        for token in tokens
        if OCR_DATE_PATTERN.match(token["text"])
    ]

    deadlines = {}

    for tour_number, anchor in anchors.items():
        candidates = [
            token
            for token in dates
            if token["x0"] >= anchor["x0"]
            and abs(token["y"] - anchor["y"]) < anchor["h"]
        ]

        if candidates:
            deadlines[tour_number] = min(
                candidates,
                key=lambda token: token["x0"],
            )["text"]

    prices = [
        token
        for token in tokens
        if OCR_PRICE_PATTERN.match(token["text"])
    ]

    for token in tokens:
        match = OCR_CODE_PATTERN.match(
            token["text"].upper()
        )

        if not match:
            continue

        code = match.group(1) + match.group(2).replace("O", "0") + match.group(3)
        tour_number = int(code[5:7])

        if tour_number not in deadlines:
            continue

        left_prices = [
            price
            for price in prices
            if price["x1"] <= token["x0"] + token["h"]
            and abs(price["y"] - token["y"]) < max(price["h"], token["h"]) * 0.7
        ]

        if not left_prices:
            continue

        usd = max(
            left_prices,
            key=lambda price: price["x1"],
        )["text"]

        entries[code] = (
            tour_number,
            deadlines[tour_number],
            usd,
        )

    return program_name, entries


def render_page_images(pdf_bytes):
    import numpy as np
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(
        pdf_bytes
    )

    try:
        for index in range(len(document)):
            image = document[index].render(
                scale=OCR_SCALE
            ).to_pil().convert("RGB")

            yield np.array(image)
    finally:
        document.close()


def parse_brochure(
    pdf_bytes,
    usd_try_rate,
    include_expired=False,
    extract="ocr",
):
    reader = PdfReader(
        BytesIO(pdf_bytes)
    )

    page_texts = [
        page.extract_text() or ""
        for page in reader.pages
    ]

    if extract == "ocr":
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR()
        page_images = render_page_images(
            pdf_bytes
        )
    else:
        page_images = (None for _ in page_texts)

    today = datetime.today().date()

    rows = []
    mismatches = 0

    for page_number, (raw_text, image) in enumerate(
        zip(page_texts, page_images),
        start=1,
    ):
        program_name, entries = text_layer_entries(
            raw_text
        )

        if image is not None:
            ocr_result, _ = engine(image)

            ocr_program, ocr_found = ocr_entries(
                ocr_result
            )

            # The text layer, when the page has one, is exact; OCR fills pages without it
            # and every difference is logged so a misreading brochure is noticed.
            for code, value in ocr_found.items():
                if code not in entries:
                    if entries:
                        logger.warning(
                            "Page %d | OCR-only code %s %s not in the text layer; skipped",
                            page_number,
                            code,
                            value,
                        )
                        mismatches += 1
                    continue

                if entries[code] != value:
                    logger.warning(
                        "Page %d | %s: text layer %s, OCR %s; using text layer",
                        page_number,
                        code,
                        entries[code],
                        value,
                    )
                    mismatches += 1

            if not entries and ocr_found:
                program_name = ocr_program
                entries = ocr_found
                logger.info(
                    "Page %d | no text layer; using %d OCR price variants",
                    page_number,
                    len(entries),
                )
            elif entries:
                logger.info(
                    "Page %d | OCR read %d of %d text-layer price variants",
                    page_number,
                    sum(1 for code in entries if code in ocr_found),
                    len(entries),
                )

        page_rows = 0

        for bank_code, (tour_number, deadline_text, usd_text) in entries.items():
            deadline = datetime.strptime(
                deadline_text,
                "%d.%m.%Y",
            ).date()

            if (
                not include_expired
                and deadline < today
            ):
                continue

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
                Decimal(usd_text),
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
                "Page %d | %s | %d current price variants",
                page_number,
                program_name,
                page_rows,
            )

    if extract == "ocr":
        logger.info(
            "OCR check: %d difference(s) against the text layer",
            mismatches,
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

    parser.add_argument(
        "--extract",
        choices=["ocr", "text"],
        default="ocr",
        help=(
            "ocr (default): OCR every brochure page with RapidOCR, checked against the "
            "PDF text layer where one exists; text: PDF text layer only (no OCR)."
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
        extract=args.extract,
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
