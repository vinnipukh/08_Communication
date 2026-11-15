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
import ipaddress
import json
import logging
import os
import re
import shutil
import socket
import ssl
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

# Fallback CA-issuers URL if the server leaf certificate AIA cannot be read dynamically.
INTERMEDIATE_URL = "http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt"
MAX_INTERMEDIATE_BYTES = 20_000

DATA_DIR = (
    Path(__file__).resolve().parents[3]
    / "Datas"
    / "09_Recreation"
    / "IVHO"
)
# Gitignored local cache (InflationItems/Codes/**/checkpoints/) for conditional GET (304).
CACHE_DIR = Path(__file__).resolve().parent / "checkpoints"
CACHE_PDF_PATH = CACHE_DIR / "tariff.pdf"
CACHE_META_PATH = CACHE_DIR / "tariff_meta.json"

CATEGORY_NUMBER = "9"
SUBCATEGORY_NUMBER = "0945001"
SOURCE_PREFIX = "İVHO"

CONNECT_TIMEOUT = 20
READ_TIMEOUT = 60
# Streamed PDF reads trigger curl's low-speed timer (connect + read = 40s < 1 B/s).
PDF_STREAM_TIMEOUT = (15, 25)
PDF_TOTAL_DEADLINE = 420
PDF_MAX_BYTES = 100_000_000
MAX_RETRIES = 4
MAX_RESUMES = 16
RETRY_BACKOFFS = (5, 15, 30)
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


def _is_public_ca_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme not in ("http", "https") or not host:
        return False
    if host == "localhost" or host.endswith((".local", ".internal")):
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True
    return False


def _fetch_leaf_certificate(host):
    """Fetch the peer leaf certificate to read its AIA caIssuers URL (never skips HTTP TLS verify)."""
    from cryptography import x509

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, 443), timeout=CONNECT_TIMEOUT) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls_sock:
            der = tls_sock.getpeercert(binary_form=True)
    return x509.load_der_x509_certificate(der)


def _discover_intermediate_url(host):
    """Return (ca_issuers_url, leaf_cert_or_None) from the live leaf cert's AIA extension."""
    from cryptography import x509
    from cryptography.x509.oid import AuthorityInformationAccessOID, ExtensionOID

    try:
        leaf = _fetch_leaf_certificate(host)
    except Exception as error:
        logger.warning("Could not inspect peer certificate for %s (%s); using fallback AIA URL", host, error)
        return INTERMEDIATE_URL, None

    try:
        aia = leaf.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
    except x509.ExtensionNotFound:
        return INTERMEDIATE_URL, leaf

    for desc in aia:
        if desc.access_method == AuthorityInformationAccessOID.CA_ISSUERS and isinstance(
            desc.access_location, x509.UniformResourceIdentifier
        ):
            url = desc.access_location.value
            if _is_public_ca_url(url):
                return url, leaf

    return INTERMEDIATE_URL, leaf


def _download_intermediate_bytes(url):
    """Download the CA intermediate certificate with Chrome TLS impersonation and retries."""
    if not _is_public_ca_url(url):
        raise RuntimeError(f"Refusing to fetch an intermediate certificate from {url}")

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                url,
                impersonate="chrome",
                timeout=(CONNECT_TIMEOUT, 30),
                allow_redirects=False,
            )
            if response.status_code == 200 and 0 < len(response.content) <= MAX_INTERMEDIATE_BYTES:
                return response.content
            last_error = f"HTTP {response.status_code}, {len(response.content)} bytes"
        except RequestException as error:
            last_error = str(error)

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFFS[min(attempt - 1, len(RETRY_BACKOFFS) - 1)])

    raise RuntimeError(f"Unexpected answer for the intermediate certificate ({url}): {last_error}")


def build_trust_bundle(host=f"www.{HOST}"):
    """Path of a PEM bundle = certifi roots + the AIA intermediate, verified against a root."""
    import certifi
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    ca_url, leaf = _discover_intermediate_url(host)
    data = _download_intermediate_bytes(ca_url)
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

    if leaf is not None and leaf.issuer != intermediate.subject:
        raise RuntimeError("The downloaded intermediate does not match the server certificate issuer")

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


def _parse_int(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


CONTENT_RANGE_PATTERN = re.compile(
    r"^bytes\s+(?P<start>\d+)-(?P<end>\d+)/(?P<total>\d+|\*)$", re.IGNORECASE
)


def _parse_content_range(header_value):
    match = CONTENT_RANGE_PATTERN.match((header_value or "").strip())
    if not match:
        return None
    total = match.group("total")
    return (
        int(match.group("start")),
        int(match.group("end")),
        None if total == "*" else int(total),
    )


class IVHOClient:
    """curl_cffi session for ivho.org.tr that never disables certificate verification."""

    def __init__(self):
        self.session = requests.Session(impersonate="chrome")
        self.verify = True

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

    def close(self):
        self.session.close()

    def _validate_host(self, url):
        host = urlparse(url).hostname
        if host not in (HOST, f"www.{HOST}"):
            raise RuntimeError(f"Refusing to request {url}: not an ivho.org.tr address")
        return host

    def _bootstrap_trust_if_needed(self, host, error):
        if self.verify is True and is_certificate_error(error):
            logger.warning(
                "Certificate chain of %s is incomplete (%s); adding its authenticated intermediate",
                HOST,
                str(error).splitlines()[0][:120],
            )
            self.verify = build_trust_bundle(host)
            # Pause briefly after the aborted TLS handshake so the origin does not throttle us.
            time.sleep(REQUEST_DELAY)
            return True
        return False

    def _retry_sleep(self, attempt, response=None, deadline=None):
        retry_after = response.headers.get("retry-after") if response is not None else None
        if retry_after and retry_after.strip().isdigit():
            wait = min(int(retry_after.strip()), 60)
        else:
            wait = RETRY_BACKOFFS[min(attempt - 1, len(RETRY_BACKOFFS) - 1)]
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            wait = min(wait, remaining)
        if wait > 0:
            time.sleep(wait)
        return True

    def get(self, url, referer=None):
        host = self._validate_host(url)
        headers = {"Referer": referer} if referer else None
        attempt = 0

        while attempt < MAX_RETRIES:
            try:
                # Redirects are not followed: the trust bundle is for this host only.
                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                    verify=self.verify,
                    allow_redirects=False,
                )
            except RequestException as error:
                if self._bootstrap_trust_if_needed(host, error):
                    continue
                attempt += 1
                logger.warning("Request failed for %s (attempt %d/%d): %s", url, attempt, MAX_RETRIES, error)
                if attempt < MAX_RETRIES:
                    self._retry_sleep(attempt)
                continue

            if response.status_code == 200:
                return response

            attempt += 1
            logger.warning(
                "HTTP %s for %s (attempt %d/%d)", response.status_code, url, attempt, MAX_RETRIES
            )
            if attempt < MAX_RETRIES:
                self._retry_sleep(attempt, response=response)

        raise RuntimeError(f"Could not fetch {url}")

    def download_pdf(self, url, referer=None, cached_meta=None, cached_bytes=None):
        """Stream the tariff PDF with conditional GET (304) and HTTP Range resume.

        Using stream=True switches curl_cffi from a total-transfer timeout to a connect + low-speed
        inactivity timeout, preventing 60s cutoffs on slow 13+ MB PDF transfers.
        """
        host = self._validate_host(url)
        deadline = time.monotonic() + PDF_TOTAL_DEADLINE
        buf = bytearray()
        active_meta = {}
        expected_total = None
        attempt = 0
        resumes = 0

        while attempt < MAX_RETRIES and resumes <= MAX_RESUMES and time.monotonic() < deadline:
            bytes_before = len(buf)
            req_headers = {"Referer": referer} if referer else {}
            if buf:
                req_headers["Range"] = f"bytes={len(buf)}-"
                if active_meta.get("etag"):
                    req_headers["If-Range"] = active_meta["etag"]
                elif active_meta.get("last_modified"):
                    req_headers["If-Range"] = active_meta["last_modified"]
            elif cached_bytes and cached_meta:
                if cached_meta.get("etag"):
                    req_headers["If-None-Match"] = cached_meta["etag"]
                if cached_meta.get("last_modified"):
                    req_headers["If-Modified-Since"] = cached_meta["last_modified"]

            response = None
            try:
                response = self.session.get(
                    url,
                    headers=req_headers,
                    timeout=PDF_STREAM_TIMEOUT,
                    verify=self.verify,
                    allow_redirects=False,
                    stream=True,
                )

                if response.status_code == 304 and not buf and cached_bytes:
                    logger.info("Tariff PDF unchanged (304 Not Modified); using cached copy")
                    return cached_bytes, cached_meta, True

                if response.status_code == 416 and buf:
                    logger.warning("Server returned 416 for Range offset %d; restarting download", len(buf))
                    buf.clear()
                    active_meta = {}
                    expected_total = None
                    continue

                if response.status_code == 200:
                    if buf:
                        logger.info("Server returned 200 instead of 206; restarting PDF download")
                        buf.clear()
                        bytes_before = 0
                    expected_total = _parse_int(response.headers.get("content-length"))
                    active_meta = {
                        "url": url,
                        "etag": response.headers.get("etag"),
                        "last_modified": response.headers.get("last-modified"),
                        "content_length": expected_total,
                    }
                elif response.status_code == 206 and buf:
                    cr = _parse_content_range(response.headers.get("content-range"))
                    resp_etag = response.headers.get("etag")
                    if (
                        cr is None
                        or cr[0] != len(buf)
                        or (expected_total is not None and cr[2] is not None and cr[2] != expected_total)
                        or (active_meta.get("etag") and resp_etag and resp_etag != active_meta["etag"])
                    ):
                        logger.warning("Incompatible 206 Content-Range (%s); restarting download", response.headers.get("content-range"))
                        buf.clear()
                        active_meta = {}
                        expected_total = None
                        attempt += 1
                        if attempt < MAX_RETRIES:
                            self._retry_sleep(attempt, response=response, deadline=deadline)
                        continue
                    if expected_total is None and cr[2] is not None:
                        expected_total = cr[2]
                        active_meta["content_length"] = expected_total
                else:
                    attempt += 1
                    logger.warning(
                        "HTTP %s for %s (attempt %d/%d)", response.status_code, url, attempt, MAX_RETRIES
                    )
                    if attempt < MAX_RETRIES:
                        self._retry_sleep(attempt, response=response, deadline=deadline)
                    continue

                if expected_total is not None and expected_total > PDF_MAX_BYTES:
                    raise RuntimeError(f"Refusing oversized PDF ({expected_total} bytes): {url}")

                for chunk in response.iter_content():
                    if not chunk:
                        continue
                    if len(buf) + len(chunk) > PDF_MAX_BYTES:
                        raise RuntimeError(f"PDF download exceeded {PDF_MAX_BYTES} bytes: {url}")
                    buf.extend(chunk)
                    if time.monotonic() >= deadline:
                        raise RequestException(f"Exceeded total PDF deadline ({PDF_TOTAL_DEADLINE}s)")

                if expected_total is not None and len(buf) < expected_total:
                    raise RequestException(
                        f"Incomplete PDF transfer ({len(buf)}/{expected_total} bytes)"
                    )

                if not buf.startswith(b"%PDF"):
                    raise RuntimeError(f"Response is not a PDF: {url}")

                active_meta["content_length"] = len(buf)
                return bytes(buf), active_meta, False

            except RequestException as error:
                if self._bootstrap_trust_if_needed(host, error):
                    continue
                has_validator = bool(active_meta.get("etag") or active_meta.get("last_modified"))
                if len(buf) > bytes_before and has_validator and resumes < MAX_RESUMES:
                    resumes += 1
                    # Progress on the partial transfer resets zero-progress retry count.
                    attempt = 0
                    total_suffix = f"/{expected_total}" if expected_total is not None else ""
                    logger.warning(
                        "PDF stream interrupted for %s at %d%s bytes (%s); resuming (%d/%d)",
                        url,
                        len(buf),
                        total_suffix,
                        error,
                        resumes,
                        MAX_RESUMES,
                    )
                    wait = min(RETRY_BACKOFFS[0], max(0.0, deadline - time.monotonic()))
                    if wait > 0:
                        time.sleep(wait)
                    continue
                attempt += 1
                logger.warning(
                    "PDF download failed for %s (%d bytes received, attempt %d/%d): %s",
                    url,
                    len(buf),
                    attempt,
                    MAX_RETRIES,
                    error,
                )
                # Discard partial data if we lack a strong validator to safely resume with If-Range.
                if buf and not has_validator:
                    buf.clear()
                    active_meta = {}
                    expected_total = None
                if attempt < MAX_RETRIES:
                    self._retry_sleep(attempt, deadline=deadline)
            finally:
                if response is not None:
                    response.close()

        raise RuntimeError(f"Could not fetch {url}")


# ----------------------------------------------------------------------------------------
# Tariff PDF & cache
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


def load_cached_pdf(pdf_url):
    """Return (pdf_bytes, meta) if a valid cached PDF matches pdf_url, else (None, None)."""
    if not CACHE_META_PATH.is_file() or not CACHE_PDF_PATH.is_file():
        return None, None
    try:
        meta = json.loads(CACHE_META_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None

    if meta.get("url") != pdf_url or not (meta.get("etag") or meta.get("last_modified")):
        return None, None

    try:
        pdf_bytes = CACHE_PDF_PATH.read_bytes()
    except OSError:
        return None, None

    expected_len = meta.get("content_length")
    if not pdf_bytes.startswith(b"%PDF") or (
        isinstance(expected_len, int) and len(pdf_bytes) != expected_len
    ):
        return None, None

    return pdf_bytes, meta


def save_cached_pdf(pdf_url, pdf_bytes, meta):
    """Atomically store the verified PDF and its HTTP validators for future 304 checks."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pdf_tmp = CACHE_DIR / f"{CACHE_PDF_PATH.name}.{os.getpid()}.tmp"
    meta_tmp = CACHE_DIR / f"{CACHE_META_PATH.name}.{os.getpid()}.tmp"
    payload = {
        "url": pdf_url,
        "etag": meta.get("etag"),
        "last_modified": meta.get("last_modified"),
        "content_length": len(pdf_bytes),
    }
    try:
        pdf_tmp.write_bytes(pdf_bytes)
        os.replace(pdf_tmp, CACHE_PDF_PATH)
        meta_tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(meta_tmp, CACHE_META_PATH)
    except OSError as error:
        logger.warning("Could not write PDF cache (%s); continuing without cache", error)
        pdf_tmp.unlink(missing_ok=True)
        meta_tmp.unlink(missing_ok=True)


def clear_cached_pdf():
    CACHE_PDF_PATH.unlink(missing_ok=True)
    CACHE_META_PATH.unlink(missing_ok=True)


def period_of(url):
    match = PERIOD_PATTERN.search(url.rsplit("/", 1)[-1])
    return (int(match.group("year")), int(match.group("half") or 0)) if match else (0, 0)


def choose_tariff_pdf():
    """Newest "Alt Ücret Tarifesi" PDF linked on the discovery pages; the known URL is the floor."""
    candidates = {KNOWN_PDF_URL}

    with requests.Session(impersonate="chrome") as session:
        for page_url in DISCOVERY_PAGES:
            try:
                origin = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}/"
                session.get(origin, timeout=30)
                time.sleep(REQUEST_DELAY)
                resp = session.get(page_url, timeout=30)
                if resp.status_code != 200:
                    logger.warning("HTTP %s for %s", resp.status_code, page_url)
                    continue
                text = resp.text
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


# Only the four shared columns are written. Other per-product fields are used inside the run
# (deduplication, naming) but are not saved.
CSV_COLUMNS = ["product_name", "price", "category_number", "sub_category_number"]


def save_csv(rows, date_str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_file = DATA_DIR / f"ivho_{date_str}.csv"

    with output_file.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS, extrasaction="ignore")
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

    with IVHOClient() as client:
        if args.pdf_url:
            pdf_url, period = args.pdf_url, "manual"
        else:
            # Homepage first, then the tariff PDF.
            client.get(BASE_URL)
            time.sleep(REQUEST_DELAY)
            pdf_url, period = choose_tariff_pdf()

        logger.info("Tariff PDF: %s", pdf_url)
        cached_bytes, cached_meta = load_cached_pdf(pdf_url)
        pdf_bytes, meta, from_cache = client.download_pdf(
            pdf_url,
            referer=BASE_URL,
            cached_meta=cached_meta,
            cached_bytes=cached_bytes,
        )

        rows, kdv_pages = [], 0
        try:
            rows, kdv_pages = extract_rows(pdf_bytes)
        except Exception as error:
            if not from_cache:
                raise
            logger.warning("Cached PDF parse failed (%s); re-downloading fresh copy", error)

        if from_cache and not rows:
            logger.warning("Cached PDF yielded no rows; clearing cache and re-downloading")
            clear_cached_pdf()
            pdf_bytes, meta, from_cache = client.download_pdf(pdf_url, referer=BASE_URL)
            rows, kdv_pages = extract_rows(pdf_bytes)

    if not rows:
        logger.error("No pet tariff prices were parsed from %s", pdf_url)
        sys.exit(1)

    if not from_cache:
        save_cached_pdf(pdf_url, pdf_bytes, meta)

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
