"""
TKİ coal price list scraper (TÜİK 04 Housing, item 0454101 Kömür), semi-manual, requests-only.

Recon (2026-10-28):
- ``https://www.tki.gov.tr/komur-fiyatlarips`` is a Next.js CMS page (page ``version`` 83, ``publish_at``
  2026-09-15). The price table is a single **image**: the ``Image`` component in ``__NEXT_DATA__``
  ``props.pageProps.page.meta.content`` that is not inside a ``Link`` (the other one is the logo), currently
  ``https://webim.tki.gov.tr/file/6b7dcbd2-...`` (image/webp, 1194×711, no ETag; Last-Modified changes on
  every fetch, so it is useless for change detection — the image hash is used instead).
- The image is "TKİ KÖMÜR SATIŞ FİYATLARI (FOB TESLİM)", "15.09.2026 TARİHİNDEN İTİBAREN GEÇERLİ": 14 products
  from three İşletme Müdürlükleri — GLİ (Kütahya-Tavşanlı, Tunçbilek), ELİ (Manisa-Soma, S.Kısrakdere), ÇLİ
  (Çanakkale-Çan) — each with BİRİM FİYAT, KDV (%20) and KDV'Lİ FİYAT in TL/ton. Mine-gate (FOB) prices,
  not city retail prices.

The numbers cannot be read from HTML, so each distinct image (by SHA-256) is transcribed once into
``transcribed.csv`` next to this script: automatically by OCR when the result is unambiguous, otherwise by a
person from a draft. A run:
1. fetches the page and the price image, and saves the image under ``images/<sha12>.<ext>`` when new;
2. if ``transcribed.csv`` has rows for the image hash, checks them (price × VAT rate = VAT, price + VAT =
   price incl. VAT) and writes today's CSV with them — so an unchanged image re-emits the list in force with
   today's date;
3. otherwise OCRs the image (``rapidocr_onnxruntime``, a project dependency). When every line passes the VAT
   check, the date is read and the lines map one to one, in order, onto the products of the newest reviewed
   list (``auto_transcription()``: same product set, names matched after folding, prices within 60 % of the
   last ones), the rows are appended to ``transcribed.csv`` with the reviewed product names
   (``entry_method`` = ocr-auto) and the run goes on as in 2;
4. otherwise (a new, dropped or renamed product, an unreadable line, no OCR installed) writes
   ``pending_<sha12>.csv``, a draft in the ``transcribed.csv`` format, writes no daily CSV and exits 2. A row whose
   three numbers do not pass the VAT check is left without numbers; without OCR the draft repeats the last
   transcription's products with empty numbers (``entry_method`` = manual). Review the draft against the image,
   fix the product names (OCR drops Turkish letters), append its rows to ``transcribed.csv`` and run again.

Output: InflationItems/Datas/04_Housing/TKI/tki_YYYY-MM-DD.csv (upstream layout: one CSV per store and day).
The inputs (``transcribed.csv``, ``images/``, ``pending_*.csv`` drafts) live in this code folder, not in Datas.
Columns: product_name, price, category_number (4), sub_category_number (0454101), operator, mine, product,
unit, vat_included, vat_rate, price_incl_vat, delivery, valid_from, image_sha256, entry_method, source_url,
image_url, collected_at. ``price`` = BİRİM FİYAT (TL/ton, VAT excluded).

Exit status: 0 = CSV written, 1 = fetch/parse failure or a bad transcription, 2 = new image awaiting review.

Examples:
  python scraper.py
  uv run --with rapidocr-onnxruntime python scraper.py   # with an OCR draft when the image changes
"""

import argparse
import csv
import hashlib
import json
import logging
import random
import re
import sys
import time
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from curl_cffi import requests

PAGE_URL = "https://www.tki.gov.tr/komur-fiyatlarips"
BACKOFF = [2, 5, 10]  # seconds waited after each failed request, then give up

REPO_ROOT = Path(__file__).resolve().parents[4]
STORE = "TKI"
DATA_DIR = REPO_ROOT / "InflationItems" / "Datas" / "04_Housing" / STORE
CODE_DIR = Path(__file__).resolve().parent  # transcriptions, images and drafts are inputs, not data
TRANSCRIBED = CODE_DIR / "transcribed.csv"
IMAGE_DIR = CODE_DIR / "images"

CATEGORY_NUMBER = 4
COAL_ITEM = "0454101"  # TÜİK item "Kömür"
COLUMNS = [
    "product_name", "price", "category_number", "sub_category_number",  # shared first four
    "operator", "mine", "product", "unit", "vat_included", "vat_rate", "price_incl_vat", "delivery",
    "valid_from", "image_sha256", "entry_method", "source_url", "image_url", "collected_at",
]
TRANSCRIBED_COLUMNS = [
    "image_sha256", "valid_from", "operator", "mine", "product", "price", "vat", "price_incl_vat", "entry_method",
]
OPERATORS = {"GLİ": "Tunçbilek", "ELİ": "Soma", "ÇLİ": "Çan"}  # İşletme Müdürlüğü -> mine name used in rows
IMAGE_EXT = {"image/webp": "webp", "image/png": "png", "image/jpeg": "jpg"}
TR_FOLD = str.maketrans("ıİşŞçÇğĞöÖüÜ", "iIsScCgGoOuU")
AUTO_MIN_SCORE = 0.9  # name similarity (folded, letters and digits only) for an OCR line to match a known product
AUTO_MAX_CHANGE = 0.6  # an OCR price more than 60 % away from the product's last price goes to review

log = logging.getLogger("coal")


class Client:
    def __init__(self, delay: float):
        self.delay = delay
        self._last = 0.0
        self.session = requests.Session(impersonate="chrome")

    def get(self, url: str):
        for attempt in range(1, len(BACKOFF) + 2):
            wait = self.delay * random.uniform(0.8, 1.4) - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self.session.get(url, timeout=60)
            except Exception as exc:
                log.warning("%s attempt %d: %s", url, attempt, exc)
                resp = None
            self._last = time.monotonic()
            if resp is not None and resp.status_code == 200:
                return resp
            status = resp.status_code if resp is not None else "error"
            log.warning("%s attempt %d: HTTP %s", url, attempt, status)
            if attempt > len(BACKOFF):
                break
            retry_after = resp.headers.get("Retry-After") if resp is not None else None
            time.sleep(int(retry_after) if retry_after and retry_after.isdigit() else BACKOFF[attempt - 1])
        raise RuntimeError(f"giving up on {url}")


def price_image_url(html: str) -> str:
    """The page's content Image that is not inside a Link (the Link holds the logo)."""
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError("TKİ: no __NEXT_DATA__ on the page")
    page = json.loads(m.group(1))["props"]["pageProps"]["page"]
    found = []

    def walk(node, in_link):
        if isinstance(node, dict):
            if node.get("component") == "Image" and not in_link:
                found.append(node["options"]["src"])
            for child in node.get("children") or []:
                walk(child, in_link or node.get("component") == "Link")
        elif isinstance(node, list):
            for child in node:
                walk(child, in_link)

    walk(page["meta"]["content"], False)
    if len(found) != 1:
        raise RuntimeError(f"TKİ: expected one price image on the page, found {found}")
    log.info("page version %s, published %s, image %s", page.get("version"), page.get("publish_at"), found[0])
    return found[0]


def check(row: dict) -> str | None:
    """None if price × rate = VAT and price + VAT = price incl. VAT (±0.01), else the reason."""
    try:
        price, vat, incl = (float(row[k]) for k in ("price", "vat", "price_incl_vat"))
    except (TypeError, ValueError):
        return "missing or non-numeric price/vat/price_incl_vat"
    if price <= 0 or abs(price + vat - incl) > 0.01:
        return f"{price} + {vat} != {incl}"
    rate = round(vat / price * 100)
    if rate not in (1, 8, 10, 18, 20) or abs(price * rate / 100 - vat) > 0.01:
        return f"VAT {vat} is no usual rate of {price}"
    return None


def read_transcribed() -> list[dict]:
    if not TRANSCRIBED.exists():
        return []
    with TRANSCRIBED.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# --- draft for a new image ----------------------------------------------------------------------------------

def tr_amount(text: str) -> float:
    """'6.000,00' / '6.000.00' (OCR mixes up the separators; there are always two decimals) -> 6000.0."""
    return int(re.sub(r"\D", "", text)) / 100


def ocr_draft(image: bytes, sha: str) -> list[dict] | None:
    """Draft rows OCR'd from the image, or None when no OCR engine is installed."""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return None
    result, _ = RapidOCR()(image)
    tokens = sorted(((box[0][1] + box[2][1]) / 2, box[0][0], text) for box, text, _ in result or [])
    amount = re.compile(r"\d{1,3}(?:[.,]\d{3})*[.,]\d{2}")
    dated = next((m.group(0) for _, _, t in tokens if (m := re.search(r"\d{2}\.\d{2}\.20\d{2}", t))), None)
    valid_from = datetime.strptime(dated, "%d.%m.%Y").date().isoformat() if dated else ""
    # the amounts form three columns (BİRİM FİYAT, KDV, KDV'Lİ FİYAT): split them at the two widest x gaps and pair
    # the columns top to bottom; grouping tokens into lines by y alone merged or split close lines
    nums = sorted((x, y, t) for y, x, t in tokens if amount.fullmatch(t.strip()))
    cuts = sorted(sorted(range(1, len(nums)), key=lambda i: nums[i][0] - nums[i - 1][0])[-2:]) if len(nums) >= 3 else []
    cols = [sorted(c, key=lambda n: n[1]) for c in (nums[:cuts[0]], nums[cuts[0]:cuts[1]], nums[cuts[1]:])] \
        if len(cuts) == 2 else []
    if not cols or len({len(c) for c in cols}) != 1:
        log.warning("OCR amounts do not form three equal price columns")
        return []
    ys = [n[1] for n in cols[0]]
    half = min((b - a for a, b in zip(ys, ys[1:])), default=40) / 2  # half the tightest row spacing
    priced = []
    for row in zip(*cols):
        y = sum(n[1] for n in row) / 3
        if max(n[1] for n in row) - min(n[1] for n in row) > half:
            log.warning("OCR price columns are out of step near y=%.0f", y)
            return []
        cells = sorted((x, t) for ty, x, t in tokens if abs(ty - y) < half and x < row[0][0])
        priced.append((y, cells, [(n[0], n[2]) for n in row]))
    if not priced:
        log.warning("OCR found no line with three amounts")
        return []
    # product names start in one column; mine labels sit left of it
    name_x = sorted(cells[0][0] for _, cells, _ in priced)[len(priced) // 2]
    # mine label blocks ("KÜTAHYA- / TAVŞANLI / (GLİ)") are centred on their rows; find each block's centre
    blocks = []
    for y, x, t in tokens:
        if x < name_x - 20:
            if blocks and y - blocks[-1][-1][0] < 40:
                blocks[-1].append((y, t))
            else:
                blocks.append([(y, t)])
    labels = []  # (centre y, operator); OCR drops the Turkish letters of "(GLİ)" / "(ELİ)" / "(ÇLİ)"
    for block in blocks:
        for _, t in block:
            if m := re.fullmatch(r"\(\s*([GEÇC])\s*L\s*[İI1l]\s*\)", t.strip()):
                labels.append((sum(y for y, _ in block) / len(block), {"G": "GLİ", "E": "ELİ"}.get(m.group(1), "ÇLİ")))
    rows = []
    for y, cells, nums in priced:
        product = " ".join(t for x, t in cells if name_x - 20 <= x < nums[0][0])
        operator = min(labels, key=lambda lab: abs(lab[0] - y))[1] if labels else ""
        row = {"image_sha256": sha, "valid_from": valid_from, "operator": operator,
               "mine": OPERATORS.get(operator, ""), "product": product, "entry_method": "ocr"}
        row.update(zip(("price", "vat", "price_incl_vat"), (tr_amount(t) for _, t in nums)))
        if reason := check(row):
            log.warning("OCR line %r failed the VAT check (%s); numbers left empty", product, reason)
            row.update(price="", vat="", price_incl_vat="")
        rows.append(row)
    return rows


def name_key(text: str) -> str:
    """Product name folded for matching OCR text: OCR drops or mangles Turkish letters and spaces."""
    folded = text.translate(TR_FOLD).lower()
    return re.sub(r"[^a-z0-9]", "", folded)


def auto_transcription(draft: list[dict] | None, transcribed: list[dict]) -> list[dict] | None:
    """Reviewed rows for a new image straight from its OCR draft, or None when a person must review it.

    Accepted only when every OCR line passed the VAT check, the date was read, and the lines map one to one, in
    order, onto the products of the newest reviewed list: by name (``AUTO_MIN_SCORE``), or a line OCR read no name
    for that sits between two matched lines with exactly one product between them. A new, dropped or renamed
    product, a line OCR missed, a missing number or a price that moved more than ``AUTO_MAX_CHANGE`` from the
    product's last price sends the draft to review."""
    if not draft or not transcribed or any(not r["price"] or not r["valid_from"] for r in draft):
        return None
    # newest list: latest valid_from; of two lists with the same date, the one transcribed later
    newest = max(enumerate(transcribed), key=lambda ir: (ir[1]["valid_from"], ir[0]))[1]["image_sha256"]
    prev = [r for r in transcribed if r["image_sha256"] == newest]
    if len(draft) != len(prev):
        return None
    keys = [name_key(r["product"]) for r in prev]
    match, last = [None] * len(draft), -1
    for i, r in enumerate(draft):
        key = name_key(r["product"])
        scores = [(SequenceMatcher(None, key, keys[j]).ratio(), j) for j in range(last + 1, len(prev))] if key else []
        if scores and max(scores)[0] >= AUTO_MIN_SCORE:
            last = max(scores)[1]
            match[i] = last
    for i in range(len(draft)):  # one unnamed line between two matched lines with one product between them
        if match[i] is None and not name_key(draft[i]["product"]):
            lo = match[i - 1] if i > 0 else -1
            hi = match[i + 1] if i + 1 < len(draft) else len(prev)
            if lo is not None and hi is not None and hi - lo == 2:
                match[i] = lo + 1
    if any(m is None for m in match):
        return None
    rows = []
    for r, m in zip(draft, match):
        old = float(prev[m]["price"])
        if not (1 - AUTO_MAX_CHANGE) * old <= float(r["price"]) <= (1 + AUTO_MAX_CHANGE) * old:
            return None
        rows.append({**r, "operator": prev[m]["operator"], "mine": prev[m]["mine"], "product": prev[m]["product"],
                     "entry_method": "ocr-auto"})
    return rows


def append_transcribed(rows: list[dict]):
    new = not TRANSCRIBED.exists()
    with TRANSCRIBED.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=TRANSCRIBED_COLUMNS)
        if new:
            writer.writeheader()
        writer.writerows(rows)


def write_draft(image: bytes, sha: str, transcribed: list[dict], rows: list[dict] | None) -> Path:
    """``rows``: the OCR draft (``ocr_draft()``), None without OCR."""
    if rows is None:
        log.warning("rapidocr_onnxruntime not installed; the draft repeats the last products without numbers")
        last = [r for r in transcribed if r["image_sha256"] == transcribed[-1]["image_sha256"]] if transcribed else []
        rows = [{**r, "image_sha256": sha, "valid_from": "", "price": "", "vat": "", "price_incl_vat": "",
                 "entry_method": "manual"} for r in last]
    path = CODE_DIR / f"pending_{sha[:12]}.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=TRANSCRIBED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def csv_rows(entries: list[dict], image_url: str, source_url: str, collected_at: str) -> list[dict]:
    """Output rows from the reviewed transcription rows of one image."""
    rows = []
    for r in entries:
        price, vat = float(r["price"]), float(r["vat"])
        rows.append({
            "product_name": f"Kömür {r['product'] if r['mine'] in r['product'] else r['mine'] + ' ' + r['product']}",
            "price": price, "category_number": CATEGORY_NUMBER,
            "sub_category_number": COAL_ITEM, "operator": r["operator"], "mine": r["mine"],
            "product": r["product"], "unit": "TL/ton", "vat_included": "false", "vat_rate": round(vat / price * 100),
            "price_incl_vat": float(r["price_incl_vat"]), "delivery": "FOB", "valid_from": r["valid_from"],
            "image_sha256": r["image_sha256"], "entry_method": r["entry_method"], "source_url": source_url,
            "image_url": image_url, "collected_at": collected_at,
        })
    return rows


def day_path(day: str) -> Path:
    return DATA_DIR / f"{STORE.lower()}_{day}.csv"


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (jittered)")
    ap.add_argument("--output", default=None, help="write this CSV path instead of the store's day file (test runs)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    started = time.monotonic()

    client = Client(args.delay)
    try:
        image_url = price_image_url(client.get(PAGE_URL).content.decode("utf-8"))
        resp = client.get(image_url)
    except Exception as exc:
        log.error("fetch failed: %s", exc)
        sys.exit(1)
    content_type = resp.headers.get("content-type", "").split(";")[0]
    if content_type not in IMAGE_EXT:
        log.error("%s is not an image (%s)", image_url, content_type)
        sys.exit(1)
    image = resp.content
    sha = hashlib.sha256(image).hexdigest()
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    image_path = IMAGE_DIR / f"{sha[:12]}.{IMAGE_EXT[content_type]}"
    if not image_path.exists():
        image_path.write_bytes(image)
        log.info("new price image saved to %s", image_path.relative_to(REPO_ROOT).as_posix())

    transcribed = read_transcribed()
    entries = [r for r in transcribed if r["image_sha256"] == sha]
    if not entries:
        draft_rows = ocr_draft(image, sha)
        entries = auto_transcription(draft_rows, transcribed) or []
        if entries:
            append_transcribed(entries)
            log.info("image %s transcribed by OCR automatically (%d products, valid from %s)", sha[:12],
                     len(entries), entries[0]["valid_from"])
    if not entries:
        draft = write_draft(image, sha, transcribed, draft_rows)
        log.error("image %s has no transcription; review %s against %s, append its rows to %s and run again",
                  sha[:12], draft.name, image_path.name, TRANSCRIBED.name)
        sys.exit(2)
    bad = [(r["product"], reason) for r in entries if (reason := check(r))]
    if bad:
        log.error("transcription of %s fails the VAT check: %s", sha[:12], bad)
        sys.exit(1)

    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = csv_rows(entries, image_url, PAGE_URL, collected_at)
    csv_path = Path(args.output) if args.output else day_path(date.today().isoformat())
    write_csv(csv_path, rows)
    (CODE_DIR / f"pending_{sha[:12]}.csv").unlink(missing_ok=True)  # the reviewed draft is in transcribed.csv now
    log.info("wrote %d rows (valid from %s) to %s in %.1f s", len(rows), rows[0]["valid_from"], csv_path,
             time.monotonic() - started)


if __name__ == "__main__":
    main()
