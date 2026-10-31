"""Ankara VHO pet minimum-fee tariff scraper for TÜİK item 0945001 (veterinary services).

The Ankara Chamber of Veterinary Surgeons (Ankara Veteriner Hekimleri Odası, avho.org.tr)
publishes a minimum fee tariff for pets twice a year as PDFs linked from
`/asgari-ucret-tarifeleri/`. The newest one-page pet table ("A3 Tablo") is chosen from that
page; every service row and animal column (Kedi, Köpek) becomes one CSV row.

The table is read from box geometry: each page is rendered with pypdfium2 and the horizontal
table rules are found in the image, so a row is the band between two rules. Text boxes come
from the PDF text layer (`--extract text`) or from RapidOCR (`--extract ocr`, default); with
OCR the text layer, where present, stays the reference and every OCR difference is logged.

Output: InflationItems/Datas/09_Recreation/AnkaraVHO/ankara_vho_YYYY-MM-DD.csv
"""

from __future__ import annotations

import argparse
import csv
import difflib
import html
import logging
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AnkaraVHOScraper")


BASE_URL = "https://www.avho.org.tr/"
LISTING_URL = urljoin(BASE_URL, "asgari-ucret-tarifeleri/")

DATA_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "AnkaraVHO"
)

CATEGORY_NUMBER = "9"
SUBCATEGORY_NUMBER = "0945001"
SOURCE_PREFIX = "Ankara VHO"

# Column order of the pet table (cat and dog icons in the header).
ANIMALS = ("Kedi", "Köpek")

# The pet tariff booklet of the same period says "Tüm fiyatlara KDV dahildir" and
# "%10 KDV DAHİL FİYAT"; the one-page table repeats its prices without a VAT note.
KDV_INCLUDED = "1"

REQUEST_TIMEOUT = 60
MAX_RETRIES = 3

HEADERS = {
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
}

CSV_COLUMNS = [
    "product_name",
    "price",
    "category_number",
    "sub_category_number",
    "price_max",
    "price_text",
    "animal",
    "section",
    "service",
    "tariff_period",
    "kdv_included",
    "value_source",
    "source_url",
]

PDF_LINK_PATTERN = re.compile(
    r'<a[^>]+href="(?P<href>[^"]*/wp-content/uploads/(?P<year>\d{4})/(?P<month>\d{2})/[^"]+\.pdf)"[^>]*>'
    r"(?P<text>.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
# "2026-2 Yılı", "2025/2 Yılı", "2026 Yılı" (no half = first half of the year).
PERIOD_PATTERN = re.compile(r"(20\d{2})\s*(?:[-/]\s*([12]))?\s*yil")

OCR_SCALE = 3.0
# A pixel row is a table rule when more than this share of the table width is dark.
RULE_DARK_LEVEL = 150
RULE_MIN_SHARE = 0.6

AMOUNT_PATTERN = re.compile(r"\d{1,3}(?:[.,]\d{3})+|\d+")
# A whole price cell: "1.700", "-", "750 / 900 / 1.000", "24.500 - 28.500" (OCR may drop
# the dash between two amounts, so plain whitespace also separates them).
PRICE_CELL_PATTERN = re.compile(
    r"^(?:[-–—]|\d{1,3}(?:[.,]\d{3})*(?:(?:\s*[/\-–—]\s*|\s+)\d{1,3}(?:[.,]\d{3})*)*)$"
)
SECTION_PATTERN = re.compile(r"^[A-ZÇĞİÖŞÜ]\s*\)\s*\S")
# "1-KLİNİKTE", "10- DİŞ ..."; OCR often drops the dash ("6APSE SAGALTIMI").
ITEM_NUMBER_PATTERN = re.compile(r"^\s*\d{1,2}\s*[-–.]?\s*(?=[^\W\d_])")


# ----------------------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------------------


def get(session, url, referer=None):
    headers = {"Referer": referer} if referer else None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                return response

            logger.warning("HTTP %s for %s (attempt %d)", response.status_code, url, attempt)
        except RequestException as error:
            logger.warning("Request failed for %s (attempt %d): %s", url, attempt, error)

        time.sleep(3 * attempt)

    raise RuntimeError(f"Could not fetch {url}")


def fold_text(value):
    value = str(value or "").replace("ı", "i").replace("İ", "i").casefold()
    value = unicodedata.normalize("NFKD", value)
    return "".join(char for char in value if not unicodedata.combining(char))


def normalize_text(value):
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def choose_tariff_pdf(listing_html, allow_older=False):
    """Newest pet ("Ev Hayvanları") one-page table linked on the tariff page.

    Farm-animal ("Çiftlik") files are excluded. Candidates are ranked by tariff period from the
    link text, then by being the one-page table ("Tablo" in the text or file name), then by the
    upload folder; only tables are accepted because the multi-page booklet has another layout.
    """
    candidates = []

    for match in PDF_LINK_PATTERN.finditer(listing_html):
        url = urljoin(BASE_URL, html.unescape(match.group("href")))
        text = normalize_text(html.unescape(re.sub(r"<[^>]+>", " ", match.group("text"))))
        folded = fold_text(f"{text} {url.rsplit('/', 1)[-1]}")

        if "ciftlik" in folded or "ev hayvan" not in fold_text(text):
            continue

        period = PERIOD_PATTERN.search(fold_text(text))
        year = int(period.group(1)) if period else int(match.group("year"))
        half = int(period.group(2) or 1) if period else 0
        is_table = "tablo" in folded

        candidates.append(
            {
                "url": url,
                "text": text,
                "period": f"{year}/{half}",
                "is_table": is_table,
                "rank": (year, half, int(match.group("year")), int(match.group("month"))),
            }
        )

    if not candidates:
        raise RuntimeError("No pet tariff PDF link found on the tariff page.")

    newest = max(candidate["rank"][:2] for candidate in candidates)
    tables = [candidate for candidate in candidates if candidate["is_table"]]

    if not tables:
        raise RuntimeError("No one-page pet tariff table found on the tariff page.")

    chosen = max(tables, key=lambda candidate: candidate["rank"])

    if chosen["rank"][:2] != newest:
        message = (
            f"Newest pet tariff period {newest[0]}/{newest[1]} has no one-page table; "
            f"newest table is {chosen['period']} ({chosen['url']})"
        )

        # Writing an older tariff under today's date would look like unchanged prices.
        if not allow_older:
            raise RuntimeError(message + ". Rerun with --allow-older to use it anyway.")

        logger.warning("%s; --allow-older given, using it", message)

    return chosen


def download_pdf(session, url):
    response = get(session, url, referer=LISTING_URL)

    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(f"Response is not a PDF: {url}")

    return response.content


# ----------------------------------------------------------------------------------------
# Boxes (text layer and OCR), all in rendered-pixel coordinates at OCR_SCALE
# ----------------------------------------------------------------------------------------


def text_layer_boxes(page):
    """Text runs of a page's PDF text layer, split where characters change line or leave a gap."""
    left, _bottom, _right, top = page.get_cropbox()
    textpage = page.get_textpage()
    boxes = []
    current = None

    try:
        for index in range(textpage.count_chars()):
            char = textpage.get_text_range(index, 1)

            if not char or char in "\r\n":
                current = None
                continue

            if char.isspace():
                if current is not None:
                    current["text"] += " "
                continue

            x0, y0, x1, y1 = textpage.get_charbox(index)
            height = max(y1 - y0, 1.0)
            y_center = (y0 + y1) / 2

            if (
                current is None
                or abs(y_center - current["_y"]) > current["_h"] * 0.6
                or x0 - current["_x1"] > max(current["_h"], height) * 2
                or x0 < current["_x1"] - current["_h"]
            ):
                current = {"text": "", "_x0": x0, "_x1": x1, "_y": y_center, "_h": height}
                boxes.append(current)

            current["text"] += char
            current["_x1"] = max(current["_x1"], x1)
            current["_h"] = max(current["_h"], height)
    finally:
        textpage.close()

    return [
        {
            "text": normalize_text(box["text"]),
            "x0": (box["_x0"] - left) * OCR_SCALE,
            "x1": (box["_x1"] - left) * OCR_SCALE,
            "y": (top - box["_y"]) * OCR_SCALE,
            "h": box["_h"] * OCR_SCALE,
        }
        for box in boxes
        if normalize_text(box["text"])
    ]


def ocr_boxes(ocr_result):
    boxes = []

    for box, text, _score in ocr_result or []:
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        text = normalize_text(text)

        if text:
            boxes.append(
                {
                    "text": text,
                    "x0": min(xs),
                    "x1": max(xs),
                    "y": (min(ys) + max(ys)) / 2,
                    "h": max(ys) - min(ys),
                }
            )

    return boxes


# ----------------------------------------------------------------------------------------
# Table geometry
# ----------------------------------------------------------------------------------------


def table_rules(gray, x0, x1):
    """(start, end) pixel-row runs that are table rules or filled header bands in [x0, x1)."""
    import numpy as np

    strip = gray[:, max(int(x0), 0):max(int(x1), 1)]
    dark_rows = np.where((strip < RULE_DARK_LEVEL).mean(axis=1) > RULE_MIN_SHARE)[0]
    runs = []

    for y in dark_rows:
        if runs and y - runs[-1][1] <= 1:
            runs[-1][1] = int(y)
        else:
            runs.append([int(y), int(y)])

    return runs


def is_price_cell(text):
    return bool(PRICE_CELL_PATTERN.match(normalize_text(text)))


def tidy_cell(text):
    """Spaces around separators: "12.000 /14.000" -> "12.000 / 14.000"."""
    return normalize_text(
        re.sub(
            r"\s*([/–—]|(?<=\d)\s*-\s*(?=\d))\s*",
            lambda match: f" {match.group(1).strip()} ",
            text,
        )
    )


def amounts(text):
    return [int(re.sub(r"[.,]", "", value)) for value in AMOUNT_PATTERN.findall(text)]


def join_lines(boxes):
    """Boxes of one cell → text, line by line (y) and left to right (x)."""
    lines = []

    for box in sorted(boxes, key=lambda item: item["y"]):
        if lines and abs(box["y"] - lines[-1][0]["y"]) < box["h"] * 0.5:
            lines[-1].append(box)
        else:
            lines.append([box])

    return normalize_text(
        " ".join(
            " ".join(item["text"] for item in sorted(line, key=lambda item: item["x0"]))
            for line in lines
        )
    )


def split_columns(price_boxes):
    """Largest x-gap between price-cell centers splits the cat column from the dog column."""
    centers = sorted((box["x0"] + box["x1"]) / 2 for box in price_boxes)

    if len(centers) < 2:
        return None

    gaps = [(centers[i + 1] - centers[i], i) for i in range(len(centers) - 1)]
    _gap, index = max(gaps)
    return (centers[index] + centers[index + 1]) / 2


def parse_half(boxes, gray, x_from, x_to):
    """Rows of one table (half page): {key, section, item, sub, label, cells{animal: text}}."""
    if not boxes:
        return []

    # Rules are searched in the middle half of each half page, which every table row spans
    # (title and footer boxes reach across both halves, so box extents are not used).
    width = x_to - x_from
    runs = table_rules(gray, x_from + width * 0.25, x_to - width * 0.25)

    if len(runs) < 3:
        return []

    def run_of(y):
        for index, (start, end) in enumerate(runs):
            if start - 2 <= y <= end + 2:
                return index, None
            if index + 1 < len(runs) and end < y < runs[index + 1][0]:
                return None, index
        return None, None

    price_boxes = [
        box
        for box in boxes
        if is_price_cell(box["text"]) and (box["x0"] + box["x1"]) / 2 > x_from + width * 0.45
    ]
    column_split = split_columns(price_boxes)
    price_ids = {id(box) for box in price_boxes}

    sections = {}
    bands = {}

    for box in boxes:
        run_index, band_index = run_of(box["y"])

        if run_index is not None:
            sections.setdefault(run_index, []).append(box)
        elif band_index is not None:
            bands.setdefault(band_index, []).append(box)

    rows = []
    section = ""
    heading = ""

    for index in range(len(runs)):
        if index in sections:
            text = join_lines(sections[index])

            if SECTION_PATTERN.match(text) or SECTION_PATTERN.match(fold_text(text).upper()):
                section = re.sub(r"^\S\s*\)\s*", "", text).strip()
                heading = ""

        band = bands.get(index)

        if not band:
            continue

        label_boxes = [box for box in band if id(box) not in price_ids]
        cell_boxes = [box for box in band if id(box) in price_ids]
        label = join_lines(label_boxes)

        if not section:
            continue

        if not cell_boxes:
            if label and ITEM_NUMBER_PATTERN.match(label):
                heading = label
            continue

        cells = {animal: [] for animal in ANIMALS}

        for box in cell_boxes:
            center = (box["x0"] + box["x1"]) / 2
            cells[ANIMALS[0] if column_split is None or center < column_split else ANIMALS[1]].append(box)

        cell_text = {animal: tidy_cell(join_lines(items)) for animal, items in cells.items()}

        if ITEM_NUMBER_PATTERN.match(label) or not heading:
            item, sub = label, ""
            heading = ""
        else:
            item, sub = heading, label

        rows.append(
            {
                "key": (x_from, index),
                "section": section,
                "item": ITEM_NUMBER_PATTERN.sub("", item).strip(),
                "sub": sub,
                "label": label,
                "cells": cell_text,
            }
        )

    return rows


def parse_page(boxes, gray):
    width = gray.shape[1]
    rows = []

    for x_from, x_to in ((0, width / 2), (width / 2, width)):
        half = [box for box in boxes if x_from <= (box["x0"] + box["x1"]) / 2 < x_to]
        rows.extend(parse_half(half, gray, x_from, x_to))

    return rows


def label_key(row):
    return re.sub(r"[^a-z0-9]", "", fold_text(f"{row['section']} {row['item']} {row['sub']}"))


def cell_values(text):
    values = amounts(text or "")
    return tuple(values)


# ----------------------------------------------------------------------------------------
# Extraction
# ----------------------------------------------------------------------------------------


def render_pages(pdf_bytes):
    import numpy as np
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(pdf_bytes)

    try:
        for index in range(len(document)):
            page = document[index]
            image = page.render(scale=OCR_SCALE).to_pil().convert("RGB")
            yield page, np.array(image), np.array(image.convert("L"))
    finally:
        document.close()


def compare_rows(page_number, text_rows, ocr_rows):
    """Log every OCR difference against the text layer; returns (cells_ok, cells_total, labels_ok)."""
    ocr_by_key = {row["key"]: row for row in ocr_rows}
    cells_ok = cells_total = labels_ok = 0

    for row in text_rows:
        other = ocr_by_key.get(row["key"])

        if other is None:
            logger.warning("Page %d | OCR missed row %r", page_number, row["label"])
            cells_total += sum(1 for text in row["cells"].values() if cell_values(text))
            continue

        ratio = difflib.SequenceMatcher(None, label_key(row), label_key(other)).ratio()

        if ratio >= 0.9:
            labels_ok += 1
        else:
            logger.warning(
                "Page %d | label: text layer %r, OCR %r (%.2f)",
                page_number,
                row["label"],
                other["label"],
                ratio,
            )

        for animal in ANIMALS:
            expected = cell_values(row["cells"][animal])

            if not expected:
                continue

            cells_total += 1
            found = cell_values(other["cells"][animal])

            if found == expected:
                cells_ok += 1
            else:
                logger.warning(
                    "Page %d | %s / %s: text layer %r, OCR %r; using text layer",
                    page_number,
                    row["label"],
                    animal,
                    row["cells"][animal],
                    other["cells"][animal],
                )

    text_keys = {row["key"] for row in text_rows}

    for row in ocr_rows:
        if row["key"] not in text_keys:
            logger.warning("Page %d | OCR-only row %r %r; skipped", page_number, row["label"], row["cells"])

    return cells_ok, cells_total, labels_ok


def extract_rows(pdf_bytes, extract):
    engine = None

    if extract == "ocr":
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR()

    rows = []
    totals = [0, 0, 0, 0]

    for page_number, (page, image, gray) in enumerate(render_pages(pdf_bytes), start=1):
        text_rows = parse_page(text_layer_boxes(page), gray)
        source = "text"
        page_rows = text_rows

        if engine is not None:
            ocr_result, _ = engine(image)
            ocr_rows = parse_page(ocr_boxes(ocr_result), gray)

            if text_rows:
                cells_ok, cells_total, labels_ok = compare_rows(page_number, text_rows, ocr_rows)
                totals[0] += cells_ok
                totals[1] += cells_total
                totals[2] += labels_ok
                totals[3] += len(text_rows)
                logger.info(
                    "Page %d | OCR: %d/%d price cells and %d/%d row labels match the text layer",
                    page_number,
                    cells_ok,
                    cells_total,
                    labels_ok,
                    len(text_rows),
                )
            elif ocr_rows:
                source = "ocr"
                page_rows = ocr_rows
                logger.info("Page %d | no text layer; using %d OCR rows", page_number, len(ocr_rows))

        logger.info("Page %d | %d table rows (%s)", page_number, len(page_rows), source)

        for row in page_rows:
            row["value_source"] = source

        rows.extend(page_rows)

    if engine is not None and totals[1]:
        logger.info(
            "OCR check: %d of %d price cells (%.1f%%) and %d of %d row labels agree with the text layer",
            totals[0],
            totals[1],
            100 * totals[0] / totals[1],
            totals[2],
            totals[3],
        )

    return rows


def build_output(rows, chosen):
    output = {}

    for row in rows:
        service = row["item"] if not row["sub"] else f"{row['item']} - {row['sub']}"

        for animal in ANIMALS:
            text = row["cells"][animal]
            values = cell_values(text)

            if not values or min(values) <= 0:
                continue

            name = f"{SOURCE_PREFIX} - {row['section']} - {service} - {animal}"

            if name in output:
                logger.warning("Duplicate product name %r; keeping the first", name)
                continue

            output[name] = {
                "product_name": name,
                "price": f"{min(values):.2f}",
                "category_number": CATEGORY_NUMBER,
                "sub_category_number": SUBCATEGORY_NUMBER,
                "price_max": f"{max(values):.2f}",
                "price_text": text,
                "animal": animal,
                "section": row["section"],
                "service": service,
                "tariff_period": chosen["period"],
                "kdv_included": KDV_INCLUDED,
                "value_source": row["value_source"],
                "source_url": chosen["url"],
            }

    return list(output.values())


def save_csv(rows, date_str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_file = DATA_DIR / f"ankara_vho_{date_str}.csv"

    with output_file.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Ankara VHO pet minimum-fee tariff scraper - CPI item 0945001"
    )
    parser.add_argument("--date", default=None, help="Output date, e.g. 2026-10-31.")
    parser.add_argument(
        "--extract",
        choices=["ocr", "text"],
        default="ocr",
        help=(
            "ocr (default): OCR every page with RapidOCR, checked against the PDF text layer "
            "where one exists; text: PDF text layer only (no OCR)."
        ),
    )
    parser.add_argument(
        "--allow-older",
        action="store_true",
        help=(
            "Use the newest one-page table even when a newer tariff period was published "
            "only as a booklet (default: stop with an error)."
        ),
    )
    args = parser.parse_args()

    started = time.perf_counter()
    date_str = args.date or datetime.today().strftime("%Y-%m-%d")

    session = requests.Session(impersonate="chrome")
    session.headers.update(HEADERS)

    try:
        get(session, BASE_URL)
        listing = get(session, LISTING_URL, referer=BASE_URL)
        chosen = choose_tariff_pdf(listing.text, allow_older=args.allow_older)
        logger.info("Tariff %s: %s (%s)", chosen["period"], chosen["text"], chosen["url"])
        pdf_bytes = download_pdf(session, chosen["url"])
    finally:
        session.close()

    rows = build_output(extract_rows(pdf_bytes, args.extract), chosen)

    if not rows:
        logger.error("No tariff rows were parsed; no CSV written.")
        sys.exit(1)

    output_file = save_csv(rows, date_str)

    print()
    print("------------------------------------------")
    print("Ankara VHO pet tariff scraping completed.")
    print("sub_category_number:", SUBCATEGORY_NUMBER)
    print("Tariff:", chosen["period"], chosen["url"])
    print("Rows:", len(rows))
    print("Extract:", args.extract)
    print(f"Time: {time.perf_counter() - started:.1f} s")
    print("File:", output_file)
    print("------------------------------------------")


if __name__ == "__main__":
    main()
