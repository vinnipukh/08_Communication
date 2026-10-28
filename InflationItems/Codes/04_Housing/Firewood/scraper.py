"""
Firewood price scraper (TÜİK 04 Housing, item 0454201 Yakacak odun), requests-only. One store per seller:

| --store      | Seller (city)                             | Source                                               |
|--------------|-------------------------------------------|------------------------------------------------------|
| odunal       | Odunal.com (Ağva/Şile, ships nationwide)  | Shopify ``products.json``                            |
| ulusoy       | Ulusoy Kömür (Bornova, İzmir)             | HTML price table "Odun & Tahta Fiyat Listesi"        |
| komurdeposu  | Kömür Deposu / Axon (Bolu)                | HTML price table on "Odun Fiyatları"                 |
| odunmarket   | Odunmarket (ships nationwide, free cargo) | Ticimax category page + ``productDetailModel`` JSON  |
| tetik        | Tetik Yakacak (Bornova, İzmir)            | WooCommerce Store API + product page JSON-LD         |
| yakgelsin    | Yak Gelsin / Özel Ada (Ödemiş, İzmir)     | HTML table "Sobalık Odun Fiyat Tablosu" (Next.js)    |

Recon (2026-10-28; details per seller in README.md):
- Odunal.com: Shopify store; public catalogue ``https://www.odunal.com/products.json?limit=250`` answered 53
  products in one page (Cloudflare in front, plain HTTP 200). Firewood is ``product_type`` "Yakacak Odun" or
  "Şömine Odunu" minus a kindling (çıra) product; other types reviewed and left out (``REVIEWED_OTHER_TYPES``).
  ``body_html`` states VAT and delivery ("KDV dahil", "Kargo ve teslimat: 500 TL", "KDV ve kargo dahil"); every
  price includes VAT. ``updated_at`` equals the response time, so ``published_at`` is written instead. The site
  answered HTTP 429 (``Retry-After: 60``) to one fetcher during recon.
- Ulusoy: one WordPress page with four tables (domestic coal, imported coal, "ODUN & TAHTA", pellet), columns
  "1 TON" and "1 ÇUVAL". The çuval has no stated weight for wood, so only the 1 ton column is written; "TAHTA
  PARÇASI" (wood scraps) is left out like at Odunal. VAT not stated; free delivery in İzmir.
- Kömür Deposu: one table, "1 Ton Odun Fiyatı (TL)" and "Torba Fiyatı" (no torba weight; left out). Dökme rows
  say "Bolu içi" (delivered within Bolu); VAT not stated.
- Odunmarket: Ticimax shop; the category page ``/odun`` lists products, every product page embeds
  ``var productDetailModel = {...}`` with one entry per variant ("Kilogram": 10, 20, "İnce (18kg)"), prices with
  VAT (``kdvDahil``), the sale price ``indirimliFiyatiStr`` is what the buyer pays. Free cargo nationwide. Taken:
  Yuvarlak and Yarma Şömine Odunu; left out: tahta parçası, the bundle "Hazır Şömine Odun Paketi", the Swedish
  torch, Flam Up pressed logs and pellet. Every variant is out of stock since at least 2025-08 (prices unchanged
  since then).
- Tetik: WooCommerce. ``/wp-json/wc/store/v1/products?search=odun`` lists 5 products; only "Meşe Odun 1 TON
  ŞÖMİNELİK VE SOBALIK" states a weight (the 400 TL "Sobalık/Şöminelik Meşe Odun" packages do not; "Pidelik" and
  "Fırınlık" are bakery wood without a unit). The product page JSON-LD gives the price and
  ``valueAddedTaxIncluded: "false"`` (prices exclude VAT).
- Yak Gelsin: Next.js page, first table "Ürün / Seçenek / Fiyat" with "KDV hariç ₺X, KDV dahil ₺Y" per option
  ("Çuvallı — 30 kg", "Dökme — 1 Ton", "1 Ton (Dökme)", "1 Çuval (20-25kg)"). The VAT-included price is
  written; an option with a weight range (20-25 kg) is left out. Delivery is free in İzmir only from 5 tons.

Rows written: one per firewood package with a stated weight. ``price`` = ``price_per_kg`` = package price /
``weight_kg`` in TL/kg (``unit``); ``package_price`` is the listed price. ``vat_included`` / ``shipping_included``
are "true", "false" or empty when the seller does not say. ``province`` is where the price applies: the seller's
province, or "Türkiye" for a seller that ships nationwide at one price (Odunal, Odunmarket).

Output: InflationItems/Datas/04_Housing/<Store>/<store>_YYYY-MM-DD.csv (upstream layout: one CSV per store and day)
Columns: product_name, price, category_number (4), sub_category_number (0454201), handle, product_type,
species, weight_kg, price_per_kg, package_price, unit, available, shipping_included, vat_included, delivery_fee,
shopify_published_at, source_url, collected_at, province.

Exit status: 0 = every store written, 1 = at least one store failed or had fewer rows than expected (nothing
written for that store; the others are still written).

Examples:
  python scraper.py                                  # all stores
  python scraper.py --store tetik yakgelsin
  python scraper.py --store ulusoy --output <scratch-dir>/test.csv
"""

import argparse
import csv
import html
import json
import logging
import random
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from curl_cffi import requests

BACKOFF = [5, 30, 60]  # seconds waited after each failed request, then give up
MAX_RETRY_AFTER = 300

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_ROOT = REPO_ROOT / "InflationItems" / "Datas" / "04_Housing"

CATEGORY_NUMBER = 4
FIREWOOD_ITEM = "0454201"  # TÜİK item "Yakacak odun"
SPECIES = ["meşe", "kayın", "gürgen", "kocayemiş", "zeytin", "çam"]
NOT_FIREWOOD = re.compile(r"tahta|kömür|pelet|çıra|briket|paket|isveç|flam up|talaş")
COLUMNS = [
    "product_name", "price", "category_number", "sub_category_number",  # shared first four
    "handle", "product_type", "species", "weight_kg", "price_per_kg", "package_price", "unit", "available",
    "shipping_included",
    "vat_included", "delivery_fee", "shopify_published_at", "source_url", "collected_at", "province",
]

# Odunal.com
ODUNAL_CATALOGUE = "https://www.odunal.com/products.json"
ODUNAL_PRODUCT = "https://www.odunal.com/products/{handle}"
PAGE_SIZE = 250  # Shopify's maximum
ODUNAL_MAIN = "kuru-mese-yakacak-odun-1-ton"
FIREWOOD_TYPES = {"Yakacak Odun", "Şömine Odunu"}
REVIEWED_OTHER_TYPES = {  # looked at on 2026-10-28: not household firewood
    "Fırın Odunu", "Yakacak Odun ve Çıra", "Tahta Parçası / Yakacak", "Odun Yarma Baltası",
    "Soba ve şömine tutuşturmalıkları", "Şömine Aksesuarları",
}

ULUSOY_URL = "https://ulusoykomur.com.tr/izmir-odun-ve-komur-fiyatlari/"
KOMURDEPOSU_URL = "https://www.komurdeposu.com.tr/odun-fiyatlari/"
ODUNMARKET = "https://www.odunmarket.com"
TETIK = "https://tetikyakacak.com"
TETIK_STORE_API = f"{TETIK}/wp-json/wc/store/v1/products"
YAKGELSIN_URL = "https://www.yakgelsin.com/tr/urunler/sobalik-odun"

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

    def text(self, url: str, params: dict | None = None) -> str:
        return self.get(url, params).content.decode("utf-8", errors="replace")


def norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\xa0", " ")).strip()


def tr_lower(text: str) -> str:
    """Turkish lower case (str.lower() turns 'İ' into 'i' + a combining dot and 'I' into 'i')."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def tr_number(text: str) -> float:
    """'5.000' / '1.250,50' (Turkish: dot = thousands, comma = decimal)."""
    return float(text.replace(".", "").replace(",", "."))


def tl_amount(text: str) -> float | None:
    """First TL amount in '8.000 TL Bolu içi' / '₺459,00' / '13.000,00 ₺'."""
    m = re.search(r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)", text)
    return tr_number(m.group(1)) if m else None


def weight_kg(text: str) -> float | None:
    """First '10 KG' / '1 Ton' / '2,5 ton' / '(18kg)' in the text, in kg; None for a range such as '20-25kg'."""
    text = tr_lower(text)
    if re.search(r"\d\s*[-–]\s*\d+(?:[.,]\d+)?\s*(kg|ton)\b", text):
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|ton)\b", text)
    if not m:
        return None
    value = float(m.group(1).replace(",", "."))
    return value * 1000 if m.group(2) == "ton" else value


def slug(text: str) -> str:
    text = tr_lower(text).translate(str.maketrans("çğıöşüâî", "cgiosuai"))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def species_of(name: str) -> str:
    return next((s for s in SPECIES if s in tr_lower(name)), "")


def row(name: str, package_price: float, kg: float, *, handle: str, product_type: str, source_url: str,
        province: str, available="", shipping="", vat="", delivery_fee="", published_at="") -> dict:
    per_kg = f"{package_price / kg:.4g}"
    return {
        "product_name": name, "price": per_kg, "category_number": CATEGORY_NUMBER,
        "sub_category_number": FIREWOOD_ITEM, "handle": handle, "product_type": product_type,
        "species": species_of(name), "weight_kg": f"{kg:g}", "price_per_kg": per_kg,
        "package_price": f"{package_price:g}", "unit": "TL/kg", "available": available,
        "shipping_included": shipping, "vat_included": vat, "delivery_fee": delivery_fee,
        "shopify_published_at": published_at, "source_url": source_url, "province": province,
    }


# --- Odunal.com (Shopify) -----------------------------------------------------------------------------------------

def plain(body_html: str) -> str:
    return norm(html.unescape(re.sub(r"<[^>]+>", " ", body_html or "")))


def odunal_terms(title: str, body: str, price: float) -> tuple[str, str, str]:
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


def odunal(client: Client) -> list[dict]:
    products, page = [], 1
    while True:
        resp = client.get(ODUNAL_CATALOGUE, params={"limit": PAGE_SIZE, "page": page})
        batch = resp.json().get("products")
        if batch is None:
            raise RuntimeError(f"{resp.url}: no 'products' key in the answer")
        products += batch
        if len(batch) < PAGE_SIZE:
            break
        page += 1
    log.info("Odunal: %d products in the catalogue", len(products))
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
            vat, shipping, fee = odunal_terms(title, body, price)
            rows.append(row(name, price, kg, handle=p["handle"], product_type=ptype,
                            source_url=ODUNAL_PRODUCT.format(handle=p["handle"]), province="Türkiye",
                            available=str(bool(v.get("available"))).lower(), shipping=shipping, vat=vat,
                            delivery_fee=fee, published_at=p.get("published_at") or ""))
    main_row = next((r for r in rows if r["handle"] == ODUNAL_MAIN), None)
    if main_row:
        log.info("Odunal main series: %s = %s TL/kg", main_row["product_name"], main_row["price"])
    else:
        log.warning("Odunal main series product %s is gone; rebuild the series from the other 1 ton meşe rows",
                    ODUNAL_MAIN)
    return rows


# --- Price tables: Ulusoy, Kömür Deposu ---------------------------------------------------------------------------

def price_table_rows(page: str, url: str, product_type: str, province: str, shipping="", vat="") -> list[dict]:
    """Rows of every HTML table whose first column names a firewood and whose column header (or cell) states a
    weight: '1 TON' -> 1000 kg, a cell '375 TL (25 kg)' -> 25 kg. A column without a weight ('1 ÇUVAL',
    'Torba Fiyatı') is skipped."""
    rows = []
    for table in BeautifulSoup(page, "lxml").find_all("table"):
        trs = [[norm(c.get_text(" ")) for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]
        if len(trs) < 2:
            continue
        header = trs[0]
        for cells in trs[1:]:
            name = cells[0] if cells else ""
            if "odun" not in tr_lower(name) or NOT_FIREWOOD.search(tr_lower(name)):
                continue
            for j, cell in enumerate(cells[1:], start=1):
                col = header[j] if j < len(header) else ""
                kg = weight_kg(cell) or weight_kg(col)
                price = tl_amount(cell)
                if not price:
                    continue
                if not kg:
                    log.info("%s / %s (%s): no weight, not written", name, col, cell)
                    continue
                note = norm(re.sub(r"[\d.,]+\s*(TL|₺)?", "", cell, count=1))  # e.g. "Bolu içi"
                label = f"{kg / 1000:g} ton" if kg >= 1000 else f"{kg:g} kg"
                full = f"{name} ({label}{', ' + note if note else ''})"
                rows.append(row(full, price, kg, handle=slug(f"{name} {label}"), product_type=product_type,
                                source_url=url, province=province, shipping=shipping, vat=vat))
    return rows


def ulusoy_rows(page: str, url: str = ULUSOY_URL) -> list[dict]:
    # "Bölgedeki müşterilerimize ... ücretsiz nakliye": delivery included in İzmir; VAT not stated
    return price_table_rows(page, url, "Odun & Tahta", "İzmir", shipping="true")


def ulusoy(client: Client) -> list[dict]:
    return ulusoy_rows(client.text(ULUSOY_URL))


def komurdeposu_rows(page: str, url: str = KOMURDEPOSU_URL) -> list[dict]:
    return price_table_rows(page, url, "Odun Fiyatları", "Bolu")


def komurdeposu(client: Client) -> list[dict]:
    return komurdeposu_rows(client.text(KOMURDEPOSU_URL))


# --- Odunmarket (Ticimax) -----------------------------------------------------------------------------------------

def embedded_json(page: str, var: str) -> dict:
    key = f"var {var} = "
    start = page.find(key)
    if start < 0:
        raise RuntimeError(f"no '{var}' in the page")
    return json.JSONDecoder().raw_decode(page, start + len(key))[0]


def odunmarket_rows(page: str, url: str) -> list[dict]:
    model = embedded_json(page, "productDetailModel")
    options = {v["urunID"]: v for v in model.get("productVariantData") or []}
    rows = []
    for p in model.get("products") or [model["product"]]:
        name = norm(p["urunAdi"])
        opt = options.get(p["id"])
        label = norm(opt["tanim"]) if opt else ""
        if opt and opt.get("ekSecenekTipiTanim") == "Kilogram" and re.fullmatch(r"\d+(?:[.,]\d+)?", label):
            label += " kg"
        kg = weight_kg(label) or weight_kg(name)
        full = f"{name} ({label})" if label else name
        if not kg:
            log.warning("Odunmarket %s: no weight, not written", full)
            continue
        stock = opt.get("stokAdedi") if opt else p.get("stokAdedi")
        rows.append(row(full, tl_amount(p["indirimliFiyatiStr"]), kg,
                        handle=slug(f"{url.rstrip('/').rsplit('/', 1)[-1]} {label}"), product_type="Şömine Odunu",
                        source_url=url, province="Türkiye", available=str(bool(stock)).lower(), shipping="true",
                        vat=str(bool(p.get("kdvDahil"))).lower()))
    return rows


def odunmarket(client: Client) -> list[dict]:
    listing = client.text(f"{ODUNMARKET}/odun")
    links = dict(re.findall(r"""detailUrl" data-id="\d+" title="([^"]+)" href='(/[^']+)'""", listing))
    if not links:
        raise RuntimeError("Odunmarket: no products on the category page")
    rows = []
    for name, path in links.items():
        if NOT_FIREWOOD.search(tr_lower(name)) or "odun" not in tr_lower(name):
            log.info("Odunmarket: not firewood, skipped: %s", name)
            continue
        url = ODUNMARKET + path
        rows += odunmarket_rows(client.text(url), url)
    return rows


# --- Tetik Yakacak (WooCommerce) ----------------------------------------------------------------------------------

def tetik_rows(page: str, url: str) -> list[dict]:
    """The product of a Tetik product page (JSON-LD), if its name states a weight."""
    for script in BeautifulSoup(page, "lxml").find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        for item in data.get("@graph", [data]) if isinstance(data, dict) else data:
            if not isinstance(item, dict) or item.get("@type") != "Product":
                continue
            name = norm(item["name"])
            kg = weight_kg(name)
            if not kg:
                log.info("Tetik %s: no weight in the name, not written", name)
                return []
            offer = item["offers"][0] if isinstance(item["offers"], list) else item["offers"]
            spec = offer.get("priceSpecification") or {}
            spec = spec[0] if isinstance(spec, list) else spec
            vat = {"true": "true", "false": "false"}.get(str(spec.get("valueAddedTaxIncluded", "")).lower(), "")
            return [row(name, float(offer["price"]), kg, handle=slug(url.rstrip("/").rsplit("/", 1)[-1]),
                        product_type="Odun", source_url=url, province="İzmir",
                        available=str("InStock" in str(offer.get("availability", ""))).lower(), vat=vat)]
    raise RuntimeError(f"{url}: no Product JSON-LD")


def tetik(client: Client) -> list[dict]:
    products = client.get(TETIK_STORE_API, params={"per_page": 100, "search": "odun"}).json()
    rows = []
    for p in products:
        name = norm(html.unescape(p["name"]))
        if NOT_FIREWOOD.search(tr_lower(name)):
            continue
        if not weight_kg(name):  # the 400 TL bags and bakery wood state no weight
            log.info("Tetik %s (%s TL): no weight in the name, not written", name,
                     int(p["prices"]["price"]) / 10 ** p["prices"]["currency_minor_unit"])
            continue
        rows += tetik_rows(client.text(p["permalink"]), p["permalink"])
    return rows


# --- Yak Gelsin (Next.js) -----------------------------------------------------------------------------------------

def yakgelsin_rows(page: str, url: str = YAKGELSIN_URL) -> list[dict]:
    soup = BeautifulSoup(page, "lxml")
    links = {}
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "ItemList":
            links = {norm(i["name"]): i["url"] for i in data.get("itemListElement", [])}
    table = next((t for t in soup.find_all("table")
                  if [norm(c.get_text(" ")) for c in t.find_all("th")][:3] == ["Ürün", "Seçenek", "Fiyat"]), None)
    if table is None:
        raise RuntimeError("Yak Gelsin: no 'Ürün / Seçenek / Fiyat' table")
    rows, product = [], ""
    for tr in table.find_all("tr")[1:]:
        cells = [norm(c.get_text(" ")) for c in tr.find_all("td")]
        if len(cells) < 3:
            continue
        product = cells[0] or product
        option, price_text = cells[1], cells[2]
        m = re.search(r"KDV dahil ₺\s*([\d.,]+)", price_text)
        if not m:
            continue  # "Fiyat için WhatsApp"
        kg = weight_kg(option)
        name = f"{product} ({option})"
        if not kg:
            log.info("Yak Gelsin %s: no single weight, not written", name)
            continue
        source = links.get(product, url)
        rows.append(row(name, tr_number(m.group(1)), kg, handle=slug(f"{source.rsplit('/', 1)[-1]} {option}"),
                        product_type="Sobalık Odun", source_url=source, province="İzmir",
                        shipping="false", vat="true"))  # free delivery in İzmir only from 5 tons
    return rows


def yakgelsin(client: Client) -> list[dict]:
    return yakgelsin_rows(client.text(YAKGELSIN_URL))


# store key -> (data folder, fetch, fewest rows a healthy run writes; counts on 2026-10-28 in the comments)
STORES = {
    "odunal": ("Odunal", odunal, 8),            # 14
    "ulusoy": ("Ulusoy", ulusoy, 2),            # 2
    "komurdeposu": ("Komurdeposu", komurdeposu, 2),  # 4
    "odunmarket": ("Odunmarket", odunmarket, 3),  # 5
    "tetik": ("Tetik", tetik, 1),               # 1
    "yakgelsin": ("Yakgelsin", yakgelsin, 6),   # 10
}


def day_path(store: str, day: str) -> Path:
    folder = STORES[store][0]
    return DATA_ROOT / folder / f"{folder.lower()}_{day}.csv"


def write_csv(path: Path, rows: list[dict], collected_at: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow({**r, "collected_at": r.get("collected_at") or collected_at})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", nargs="+", choices=list(STORES), default=list(STORES), help="stores (default: all)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (jittered)")
    ap.add_argument("--output", default=None, help="write all rows to this CSV path instead of the store day files "
                                                   "(test runs)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    client = Client(args.delay)
    failed, test_rows = [], []

    for store in args.store:
        started = time.monotonic()
        _, fetch, min_rows = STORES[store]
        try:
            rows = fetch(client)
        except Exception as exc:
            log.error("%s failed: %s; no CSV written", store, exc)
            failed.append(store)
            continue
        if len(rows) < min_rows:
            log.error("%s: expected at least %d firewood rows, got %d; no CSV written", store, min_rows, len(rows))
            failed.append(store)
            continue
        collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        if args.output:
            test_rows += [{**r, "collected_at": collected_at} for r in rows]
            path = args.output
        else:
            path = day_path(store, date.today().isoformat())
            write_csv(path, rows, collected_at)
        per_kg = sorted(float(r["price"]) for r in rows)
        log.info("%s: wrote %d rows (%.2f-%.2f TL/kg) to %s in %.1f s", store, len(rows), per_kg[0], per_kg[-1],
                 path, time.monotonic() - started)
    if args.output and test_rows:
        write_csv(Path(args.output), test_rows, "")
    if failed:
        log.error("failed: %s", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
