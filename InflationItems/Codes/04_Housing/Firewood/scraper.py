"""
Odunal.com firewood price scraper (TÜİK 04 Housing, item 0454201 Yakacak odun), requests-only.

Recon (2026-10-28):
- Odunal.com is a Shopify store of a seller in Ağva/Şile (İstanbul) that ships nationwide; prices are not per
  city. The public catalogue ``https://www.odunal.com/products.json?limit=250`` answered 53 products in one
  page (Cloudflare in front, plain HTTP 200). Each product has ``handle``, ``title``, ``product_type``,
  ``body_html``, ``published_at`` and ``variants[]`` (``title``, ``price``, ``available``, ``grams``).
  ``updated_at`` (product and variant) equals the response time on every product, so it is useless;
  ``published_at`` is written instead.
- Firewood is ``product_type`` "Yakacak Odun" (13) or "Şömine Odunu" (2). "Yakacak Odun" also holds a 25 kg
  kindling (çıra) product, which is skipped. Other types seen and reviewed as not household firewood:
  "Fırın Odunu" (İnce Fırın ve Lahmacun Odunu 1 ton), "Yakacak Odun ve Çıra", "Tahta Parçası / Yakacak",
  "Odun Yarma Baltası", tutuşturmalık types. A new type whose name looks like firewood is logged as a warning.
- ``body_html`` states VAT and delivery per product: "Fiyat: 5.000 TL, KDV dahil", "Kargo ve teslimat: 500 TL",
  "KDV ve kargo dahil" (shipping included). Delivery is 500 TL in İstanbul (Şile and Ağva included) for every
  product that is not "kargo dahil".
- ``https://www.odunal.com/pages/yakacak-odun-fiyatlari`` repeats the list with a "Fiyat kontrol tarihi"
  (21 Ekim 2026 on 2026-10-28); not fetched, the catalogue is the live price.
- The site answered HTTP 429 (``Retry-After: 60``) to one fetcher during recon: one request per run, honour
  ``Retry-After``.

Rows written: one per variant of every firewood product. ``price`` = product price in TL as listed (VAT
included where the text says so), delivery not included unless ``shipping_included`` is true;
``delivery_fee`` is the fee stated in the description (TL). ``weight_kg`` is parsed from the variant or
product title ("10 KG", "1 Ton"); ``price`` = ``price_per_kg`` = package price / weight_kg in TL/kg (``unit``),
so packages of 10 kg to 4 tons are in one unit; ``package_price`` is the listed price. A package without a
weight is skipped. The main CPI series is
"Kuru Meşe Yakacak Odun 1 Ton" (handle ``kuru-mese-yakacak-odun-1-ton``); the other rows are kept so the
series can be rebuilt if that product disappears.

Output: InflationItems/Datas/04_Housing/Odunal/odunal_YYYY-MM-DD.csv (upstream layout: one CSV per store and day)
Columns: product_name, price, category_number (4), sub_category_number (0454201), handle, product_type,
species, weight_kg, price_per_kg, package_price, unit, available, shipping_included, vat_included, delivery_fee,
shopify_published_at, source_url, collected_at. ``vat_included`` is always "true": Odunal's prices include VAT
(confirmed 2026-10-28, also for products whose text does not say so). ``shipping_included`` is "true", "false" or
empty when the text says nothing.

Exit status: 0 = CSV written, 1 = fetch failure or fewer firewood products than expected (nothing written).

Examples:
  python scraper.py
  python scraper.py --output <scratch-dir>/test.csv
"""

import argparse
import csv
import html
import logging
import random
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from curl_cffi import requests

CATALOGUE_URL = "https://www.odunal.com/products.json"
PRODUCT_URL = "https://www.odunal.com/products/{handle}"
PAGE_SIZE = 250  # Shopify's maximum
BACKOFF = [5, 30, 60]  # seconds waited after each failed request, then give up
MAX_RETRY_AFTER = 300
MIN_ROWS = 8  # 15 firewood variants on 2026-10-28; fewer than this means the catalogue changed shape

REPO_ROOT = Path(__file__).resolve().parents[4]
STORE = "Odunal"
DATA_DIR = REPO_ROOT / "InflationItems" / "Datas" / "04_Housing" / STORE

CATEGORY_NUMBER = 4
FIREWOOD_ITEM = "0454201"  # TÜİK item "Yakacak odun"
MAIN_HANDLE = "kuru-mese-yakacak-odun-1-ton"
FIREWOOD_TYPES = {"Yakacak Odun", "Şömine Odunu"}
REVIEWED_OTHER_TYPES = {  # looked at on 2026-10-28: not household firewood
    "Fırın Odunu", "Yakacak Odun ve Çıra", "Tahta Parçası / Yakacak", "Odun Yarma Baltası",
    "Soba ve şömine tutuşturmalıkları", "Şömine Aksesuarları",
}
SPECIES = ["meşe", "kayın", "gürgen", "kocayemiş"]
COLUMNS = [
    "product_name", "price", "category_number", "sub_category_number",  # shared first four
    "handle", "product_type", "species", "weight_kg", "price_per_kg", "package_price", "unit", "available",
    "shipping_included",
    "vat_included", "delivery_fee", "shopify_published_at", "source_url", "collected_at",
]

log = logging.getLogger("firewood")


class Client:
    def __init__(self, delay: float):
        self.delay = delay
        self._last = 0.0
        self.session = requests.Session(impersonate="chrome")

    def get(self, url: str, params: dict | None = None):
        for attempt in range(1, len(BACKOFF) + 2):
            wait = self.delay * random.uniform(0.8, 1.4) - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self.session.get(url, params=params, timeout=60)
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
            if retry_after and retry_after.isdigit() and int(retry_after) > MAX_RETRY_AFTER:
                break  # the site wants us gone for longer than a run should wait
            time.sleep(int(retry_after) if retry_after and retry_after.isdigit() else BACKOFF[attempt - 1])
        raise RuntimeError(f"giving up on {url}")


def norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\xa0", " ")).strip()


def tr_lower(text: str) -> str:
    """Turkish lower case (str.lower() turns 'İ' into 'i' + a combining dot and 'I' into 'i')."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def tr_number(text: str) -> float:
    """'5.000' / '1.250,50' (Turkish: dot = thousands, comma = decimal)."""
    return float(text.replace(".", "").replace(",", "."))


def weight_kg(text: str) -> float | None:
    """First '10 KG' / '1 Ton' / '2,5 ton' in the text, in kg."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|ton)\b", tr_lower(text))
    if not m:
        return None
    value = float(m.group(1).replace(",", "."))
    return value * 1000 if m.group(2) == "ton" else value


def plain(body_html: str) -> str:
    return norm(html.unescape(re.sub(r"<[^>]+>", " ", body_html or "")))


def terms(title: str, body: str, price: float) -> tuple[str, str, str]:
    """(vat_included, shipping_included, delivery_fee) from the title and description text."""
    text = tr_lower(f"{title} {body}")
    dahil = r"d[aâ]hil"
    vat = "true"  # every Odunal price includes VAT, whether or not the product text says "KDV dahil"
    if re.search(rf"kargo\s+(ve\s+kdv\s+)?{dahil}|kdv\s+ve\s+kargo\s+{dahil}", text):
        return vat, "true", ""
    fees = [tr_number(m.group(1)) for m in re.finditer(r"(?:kargo|teslimat)[^.]{0,80}?(\d{1,3}(?:\.\d{3})+|\d+)\s*tl",
                                                         text)]
    fees = [f for f in fees if f != price]
    if not fees:
        return vat, "", ""
    if len(set(fees)) > 1:
        log.warning("%s: several delivery fees %s, taking %s", title, sorted(set(fees)), fees[0])
    return vat, "false", f"{fees[0]:g}"


def fetch_products(client: Client) -> list[dict]:
    products, page = [], 1
    while True:
        resp = client.get(CATALOGUE_URL, params={"limit": PAGE_SIZE, "page": page})
        batch = resp.json().get("products")
        if batch is None:
            raise RuntimeError(f"{resp.url}: no 'products' key in the answer")
        products += batch
        if len(batch) < PAGE_SIZE:
            return products
        page += 1


def firewood_rows(products: list[dict]) -> list[dict]:
    rows = []
    for p in products:
        ptype, title = norm(p.get("product_type")), norm(p.get("title"))
        if ptype not in FIREWOOD_TYPES:
            if ptype not in REVIEWED_OTHER_TYPES and re.search(r"odun|yakacak|şömine", tr_lower(ptype)):
                log.warning("unknown firewood-like product type %r (%s): not taken, review FIREWOOD_TYPES", ptype, title)
            continue
        if "çıra" in tr_lower(title):
            log.info("skipping kindling: %s", title)
            continue
        body = plain(p.get("body_html"))
        species = next((s for s in SPECIES if s in tr_lower(title)), "")
        for v in p.get("variants") or []:
            variant = norm(v.get("title"))
            named = variant and variant not in ("Default Title", "Default")
            name = f"{title} ({variant})" if named and variant not in title else title
            price = float(v["price"])
            kg = (weight_kg(variant) if named else None) or weight_kg(title)
            if not kg:  # price is TL/kg, so a package without a weight cannot be written
                log.warning("%s: no weight in the title, row skipped", name)
                continue
            if v.get("grams") and abs(v["grams"] / 1000 - kg) > 0.01:
                log.warning("%s: title says %g kg, Shopify weight %g kg; using the title", name, kg, v["grams"] / 1000)
            vat, shipping, fee = terms(title, body, price)
            rows.append({
                "product_name": name, "price": f"{price / kg:.4g}", "category_number": CATEGORY_NUMBER,
                "sub_category_number": FIREWOOD_ITEM, "handle": p["handle"], "product_type": ptype,
                "species": species, "weight_kg": f"{kg:g}", "price_per_kg": f"{price / kg:.4g}",
                "package_price": f"{price:g}", "unit": "TL/kg",
                "available": str(bool(v.get("available"))).lower(), "shipping_included": shipping,
                "vat_included": vat, "delivery_fee": fee, "shopify_published_at": p.get("published_at") or "",
                "source_url": PRODUCT_URL.format(handle=p["handle"]),
            })
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (jittered; only when paging)")
    ap.add_argument("--output", default=None, help="write this CSV path instead of the store's day file (test runs)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    started = time.monotonic()

    try:
        products = fetch_products(Client(args.delay))
        rows = firewood_rows(products)
    except Exception as exc:
        log.error("Odunal failed: %s; no CSV written", exc)
        sys.exit(1)
    log.info("%d products in the catalogue, %d firewood rows", len(products), len(rows))
    if len(rows) < MIN_ROWS:
        log.error("expected at least %d firewood rows, got %d; no CSV written", MIN_ROWS, len(rows))
        sys.exit(1)
    main_row = next((r for r in rows if r["handle"] == MAIN_HANDLE), None)
    if main_row:
        log.info("main series: %s = %s TL (%s TL/kg)", main_row["product_name"], main_row["price"],
                 main_row["price_per_kg"])
    else:
        log.warning("main series product %s is gone; rebuild the series from the other 1 ton meşe rows", MAIN_HANDLE)

    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    csv_path = Path(args.output) if args.output else DATA_DIR / f"{STORE.lower()}_{date.today().isoformat()}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "collected_at": collected_at})
    log.info("wrote %d rows to %s in %.1f s", len(rows), csv_path, time.monotonic() - started)


if __name__ == "__main__":
    main()
