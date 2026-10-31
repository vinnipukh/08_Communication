"""İstanbul VHO pet minimum-fee tariff scraper for TÜİK item 0945001 (veterinary services).

The İstanbul Chamber of Veterinary Surgeons (İstanbul Veteriner Hekimleri Odası, ivho.org.tr)
publishes a "Alt Sınır Ücret Tarifesi" booklet (pets and farm animals) as one PDF twice a year.
Only the pet ("Ev Hayvanları") pages are used: a table of service names with two price columns,
Kedi (cat) and Köpek (dog). Prices include VAT ("Tüm fiyatlara KDV dahildir").

The table pages have a PDF text layer, so no OCR is needed. Text boxes are read with their
page coordinates (pypdfium2), a row is a price y-position, the label is the text left of the
prices on that row and the column (x) tells cat from dog.

TLS: ivho.org.tr sends its server certificate without the intermediate (Sectigo) one, so a
plain verification fails (browsers fetch the missing intermediate themselves). Verification is
never switched off. If a plain request fails the certificate check, the intermediate is taken
from the Sectigo CA-issuers URL, its signature is verified against the CA roots shipped in
`certifi`, and only then it is added to a trust bundle that is used for ivho.org.tr alone.

Output: InflationItems/Datas/09_Recreation/IVHO/ivho_YYYY-MM-DD.csv
"""

from __future__ import annotations

import argparse
import atexit
import csv
import html
import logging
import re
import shutil
import statistics
import sys
import tempfile
import time
import unicodedata
import warnings
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("IVHOScraper")


HOST = "ivho.org.tr"
BASE_URL = "https://www.ivho.org.tr/"
# Fallback and floor for the discovery below (the 2026/2 tariff, checked 2026-10-31).
KNOWN_PDF_URL = urljoin(BASE_URL, "assets/docs/IVHO_Alt_Ucret_Tarifesi_2026_2.pdf")

# CA-issuers URL taken from the AIA field of the server certificate (Sectigo DV R36).
INTERMEDIATE_URL = "http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt"
INTERMEDIATE_HOST_SUFFIX = ".sectigo.com"
MAX_INTERMEDIATE_BYTES = 20_000

DATA_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "IVHO"
)

CATEGORY_NUMBER = "9"
SUBCATEGORY_NUMBER = "0945001"
SOURCE_PREFIX = "İVHO"

REQUEST_TIMEOUT = 60
MAX_RETRIES = 3
REQUEST_DELAY = 1.5

# Page geometry in PDF points (A4, 595 x 842), measured on the 2026/2 booklet.
BODY_TOP = 115          # below the blue page header
BODY_BOTTOM = 775       # above the footer line
LABEL_MAX_X = 335       # labels end left of the cat column
# Price column centres are about 373 (cat) and 500 (dog); wide amounts shift a centre by up to
# ~40 points. A cell merged across both columns (e.g. birds and exotic animals) is centred
# between them.
CAT_MAX_CENTER = 412
DOG_MIN_CENTER = 465
SHARED_ANIMAL = "Kedi ve Köpek dışı (ortak hücre)"

PRICE_PATTERN = re.compile(
    r"^(?P<low>\d{1,3}(?:\.\d{3})*)"
    r"(?:\s*[-–/]\s*(?P<high>\d{1,3}(?:\.\d{3})*))?"
    r"\s*₺?\s*TL$"
)
HEADING_SKIP = ("alt sinir", "yili", "kdv", "not:", "www.")


# ----------------------------------------------------------------------------------------
# TLS: plain verification first, then the authenticated intermediate for this host only
# ----------------------------------------------------------------------------------------


def fold_text(value):
    value = str(value or "").replace("ı", "i").replace("İ", "i").casefold()
    value = unicodedata.normalize("NFKD", value)
    return "".join(char for char in value if not unicodedata.combining(char))


def normalize_text(value):
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def build_trust_bundle():
    """Path of a PEM bundle = certifi roots + the Sectigo intermediate, verified against a root."""
    import certifi
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    host = urlparse(INTERMEDIATE_URL).hostname or ""

    if not host.endswith(INTERMEDIATE_HOST_SUFFIX):
        raise RuntimeError(f"Refusing to fetch an intermediate certificate from {host}")

    response = requests.get(INTERMEDIATE_URL, timeout=30, allow_redirects=False)

    if response.status_code != 200 or not 0 < len(response.content) <= MAX_INTERMEDIATE_BYTES:
        raise RuntimeError(f"Unexpected answer for the intermediate certificate: {response.status_code}")

    data = response.content
    intermediate = (
        x509.load_pem_x509_certificate(data)
        if data.startswith(b"-----")
        else x509.load_der_x509_certificate(data)
    )

    now = datetime.now(timezone.utc)

    if not intermediate.not_valid_before_utc <= now <= intermediate.not_valid_after_utc:
        raise RuntimeError("The intermediate certificate is not currently valid")

    if not intermediate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise RuntimeError("The downloaded certificate is not a CA certificate")

    roots_pem = Path(certifi.where()).read_bytes()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # a few roots have a non-positive serial number
        roots = x509.load_pem_x509_certificates(roots_pem)

    # The intermediate is only trusted when a root already trusted by certifi signed it;
    # otherwise whoever answered the download could add their own CA.
    for root in (item for item in roots if item.subject == intermediate.issuer):
        try:
            intermediate.verify_directly_issued_by(root)
        except Exception:
            continue

        logger.info(
            "Intermediate %s verified against root %s",
            intermediate.subject.rfc4514_string(),
            root.subject.rfc4514_string(),
        )
        break
    else:
        raise RuntimeError("The intermediate certificate is not signed by a certifi root; not trusting it")

    folder = Path(tempfile.mkdtemp(prefix="ivho_trust_"))
    atexit.register(shutil.rmtree, folder, ignore_errors=True)
    bundle = folder / "bundle.pem"
    bundle.write_bytes(
        roots_pem + b"\n" + intermediate.public_bytes(serialization.Encoding.PEM)
    )

    return str(bundle)


def is_certificate_error(error):
    text = str(error).lower()
    return "certificate" in text or "ssl" in text or "(60)" in text


class IVHOClient:
    """curl_cffi session for ivho.org.tr that never disables certificate verification."""

    def __init__(self):
        self.session = requests.Session(impersonate="chrome")
        self.verify = True

    def get(self, url, referer=None):
        if urlparse(url).hostname not in (HOST, f"www.{HOST}"):
            raise RuntimeError(f"Refusing to request {url}: not an ivho.org.tr address")

        headers = {"Referer": referer} if referer else None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Redirects are not followed: the trust bundle is for this host only.
                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                    verify=self.verify,
                    allow_redirects=False,
                )
            except RequestException as error:
                if self.verify is True and is_certificate_error(error):
                    logger.warning(
                        "Certificate chain of %s is incomplete (%s); adding its authenticated intermediate",
                        HOST,
                        str(error).splitlines()[0][:120],
                    )
                    self.verify = build_trust_bundle()
                    continue

                logger.warning("Request failed for %s (attempt %d): %s", url, attempt, error)
                time.sleep(3 * attempt)
                continue

            if response.status_code == 200:
                return response

            logger.warning("HTTP %s for %s (attempt %d)", response.status_code, url, attempt)
            time.sleep(3 * attempt)

        raise RuntimeError(f"Could not fetch {url}")


# ----------------------------------------------------------------------------------------
# Tariff PDF
# ----------------------------------------------------------------------------------------

# The İVHO home page is a script-rendered page without links, so the current PDF is looked
# up on pages that link it directly: VetArt's price page and Atakent Vet's tariff page.
DISCOVERY_PAGES = (
    "https://vetart.com.tr/veteriner-ucretleri/",
    "https://www.atakentvet.com/poliklinigimizde-ivho-alt-sinir-ucret-tarifesi-uygulanmaktadir-h21",
)
PDF_LINK_PATTERN = re.compile(
    r"https?://(?:www\.)?ivho\.org\.tr/assets/docs/[^\"'\s<>]+\.pdf", re.IGNORECASE
)
PERIOD_PATTERN = re.compile(r"(?P<year>20\d{2})(?:[_-](?P<half>\d))?")


def period_of(url):
    match = PERIOD_PATTERN.search(url.rsplit("/", 1)[-1])
    return (int(match.group("year")), int(match.group("half") or 0)) if match else (0, 0)


def choose_tariff_pdf():
    """Newest "Alt Ücret Tarifesi" PDF linked on the discovery pages; the known URL is the floor."""
    candidates = {KNOWN_PDF_URL}
    session = requests.Session(impersonate="chrome")

    for page_url in DISCOVERY_PAGES:
        try:
            origin = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}/"
            session.get(origin, timeout=30)
            time.sleep(REQUEST_DELAY)
            text = session.get(page_url, timeout=30).text
        except RequestException as error:
            logger.warning("Could not read %s: %s", page_url, error)
            continue

        for url in PDF_LINK_PATTERN.findall(html.unescape(text)):
            url = url.replace("http://", "https://", 1)
            name = fold_text(url.rsplit("/", 1)[-1])

            if "tarife" in name and "ciftlik" not in name:
                candidates.add(url)

        time.sleep(REQUEST_DELAY)

    url = max(candidates, key=period_of)
    year, half = period_of(url)
    logger.info("Tariff PDF candidates: %s", sorted(candidates))
    return url, f"{year}/{half}"


# ----------------------------------------------------------------------------------------
# Text boxes and rows
# ----------------------------------------------------------------------------------------


def page_boxes(page):
    """Text runs of a page's text layer: text, x0, x1, y (from the top), height, in points."""
    _left, _bottom, _right, top = page.get_cropbox()
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
                or abs(y_center - current["y"]) > current["h"] * 0.6
                or x0 - current["x1"] > max(current["h"], height) * 2
                or x0 < current["x1"] - current["h"]
            ):
                current = {"text": "", "x0": x0, "x1": x1, "y": y_center, "h": height}
                boxes.append(current)

            current["text"] += char
            current["x1"] = max(current["x1"], x1)
            current["h"] = max(current["h"], height)
    finally:
        textpage.close()

    result = []

    for box in boxes:
        text = normalize_text(box["text"])

        if text:
            result.append(
                {
                    "text": text,
                    "x0": box["x0"],
                    "x1": box["x1"],
                    "y": top - box["y"],
                    "h": box["h"],
                }
            )

    return result


def parse_price(text):
    match = PRICE_PATTERN.match(normalize_text(text).replace("₺TL", "TL"))

    if not match:
        return None

    low = int(match.group("low").replace(".", ""))
    high = int(match.group("high").replace(".", "")) if match.group("high") else low
    return min(low, high), max(low, high)


def is_heading(text):
    folded = fold_text(text)
    letters = [char for char in normalize_text(text) if char.isalpha()]

    if len(letters) < 6 or any(word in folded for word in HEADING_SKIP):
        return False

    upper = sum(1 for char in letters if char.isupper())
    return upper / len(letters) > 0.85


def is_pet_page(boxes):
    text = fold_text(" ".join(box["text"] for box in boxes))
    return "ev hayvanlari" in text and "ciftlik hayvanlari" not in text


def parse_page(boxes, heading):
    """(rows, last heading) of one pet tariff page."""
    body = [box for box in boxes if BODY_TOP <= box["y"] <= BODY_BOTTOM]
    prices = []

    for box in body:
        value = parse_price(box["text"])

        if value:
            prices.append({**box, "value": value})

    if not prices:
        return [], heading

    ys = sorted({round(box["y"], 1) for box in prices})
    row_ys = []

    for y in ys:
        if row_ys and y - row_ys[-1] < 6:
            continue

        row_ys.append(y)

    pitch = statistics.median(b - a for a, b in zip(row_ys, row_ys[1:])) if len(row_ys) > 1 else 22
    half = max(pitch * 0.5, 9)

    def nearest(y):
        row = min(row_ys, key=lambda item: abs(item - y))
        return row, abs(row - y)

    labels = {row: [] for row in row_ys}
    headings = []

    for box in body:
        if parse_price(box["text"]) or box["x0"] > LABEL_MAX_X or box["text"].startswith("*"):
            continue

        row, distance = nearest(box["y"])

        if distance <= half - 1:
            labels[row].append(box)
        elif is_heading(box["text"]):
            headings.append(box)

    events = [(box["y"], "heading", box) for box in headings] + [(row, "row", None) for row in row_ys]
    rows = []

    for y, kind, box in sorted(events, key=lambda item: item[0]):
        if kind == "heading":
            heading = normalize_text(box["text"])
            continue

        parts = sorted(labels[y], key=lambda item: (round(item["y"] / 4), item["x0"]))
        parts = [
            item
            for item in parts
            if abs(item["y"] - y) <= 8 and not (item["text"].endswith(".") and len(item["text"]) > 40)
        ]
        label = normalize_text(" ".join(item["text"] for item in parts))

        if not label:
            continue

        for price_box in (item for item in prices if abs(item["y"] - y) < 6):
            center = (price_box["x0"] + price_box["x1"]) / 2
            low, high = price_box["value"]
            if center < CAT_MAX_CENTER:
                animal = "Kedi"
            elif center > DOG_MIN_CENTER:
                animal = "Köpek"
            else:
                animal = SHARED_ANIMAL

            rows.append(
                {
                    "heading": heading,
                    "label": label,
                    "animal": animal,
                    "price": low,
                    "price_max": high,
                    "price_text": price_box["text"],
                    "center": round(center),
                }
            )

    return rows, heading


def extract_rows(pdf_bytes):
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(pdf_bytes)
    rows = []
    heading = ""
    kdv_pages = 0

    try:
        for index in range(len(document)):
            boxes = page_boxes(document[index])

            if not boxes or not is_pet_page(boxes):
                continue

            page_rows, heading = parse_page(boxes, heading)

            if any("kdv dahildir" in fold_text(box["text"]) for box in boxes):
                kdv_pages += 1

            for row in page_rows:
                rows.append({**row, "page": index + 1})

            if page_rows:
                logger.info("Page %d | %d price cells", index + 1, len(page_rows))
    finally:
        document.close()

    return rows, kdv_pages


# ----------------------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------------------


def build_output(rows, source_url, tariff_period, kdv_pages):
    output = []
    seen = {}

    for row in rows:
        parts = [SOURCE_PREFIX]

        if row["heading"]:
            parts.append(row["heading"])

        parts += [row["label"], row["animal"]]
        name = " - ".join(parts)
        seen[name] = seen.get(name, 0) + 1

        if seen[name] > 1:
            name = f"{name} (sayfa {row['page']})"

        output.append(
            {
                "product_name": name,
                "price": f"{row['price']:.2f}",
                "category_number": CATEGORY_NUMBER,
                "sub_category_number": SUBCATEGORY_NUMBER,
                "price_max": f"{row['price_max']:.2f}",
                "price_text": row["price_text"],
                "animal": row["animal"],
                "section": row["heading"],
                "service": row["label"],
                "page": row["page"],
                "tariff_period": tariff_period,
                "kdv_included": 1 if kdv_pages else "",
                "source_url": source_url,
            }
        )

    return output


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
    "page",
    "tariff_period",
    "kdv_included",
    "source_url",
]


def save_csv(rows, date_str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_file = DATA_DIR / f"ivho_{date_str}.csv"

    with output_file.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="İstanbul VHO pet minimum fee tariff scraper - CPI subcategory 0945001"
    )
    parser.add_argument("--date", default=None, help="Output date, e.g. 2026-10-31.")
    parser.add_argument("--pdf-url", default=None, help="Use this tariff PDF (an ivho.org.tr address).")
    args = parser.parse_args()

    date_str = args.date or datetime.today().strftime("%Y-%m-%d")
    client = IVHOClient()

    if args.pdf_url:
        pdf_url, period = args.pdf_url, "manual"
    else:
        # Homepage first, then the tariff PDF.
        client.get(BASE_URL)
        time.sleep(REQUEST_DELAY)
        pdf_url, period = choose_tariff_pdf()

    logger.info("Tariff PDF: %s", pdf_url)
    response = client.get(pdf_url, referer=BASE_URL)

    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(f"Response is not a PDF: {pdf_url}")

    rows, kdv_pages = extract_rows(response.content)

    if not rows:
        logger.error("No pet tariff prices were parsed from %s", pdf_url)
        sys.exit(1)

    if not kdv_pages:
        logger.warning("The pages do not say 'KDV dahildir'; kdv_included left empty")

    if period == "manual":
        year, half = period_of(pdf_url)
        period = f"{year}/{half}"

    output = build_output(rows, pdf_url, period, kdv_pages)
    output_file = save_csv(output, date_str)

    counts = {}

    for row in output:
        counts[row["animal"]] = counts.get(row["animal"], 0) + 1

    print()
    print("------------------------------------------")
    print("İVHO tariff scraping completed.")
    print("subcategory_number:", SUBCATEGORY_NUMBER)
    print("Rows:", len(output), counts)
    print("Tariff period:", period)
    print("File:", output_file)
    print("------------------------------------------")


if __name__ == "__main__":
    main()
