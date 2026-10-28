"""
LPG cylinder (12 kg tüp) price scraper (TÜİK 04 Housing, item 0452201 LPG tüp), requests-only.
Four brands, every province each brand lists (the scope rule allows it: same endpoint, no extra code).

Recon (2026-10-28):
- Aygaz: ``https://www.aygaz.com.tr/fiyatlar/tupgaz`` ``__NEXT_DATA__`` → ``props.pageProps.cities`` (value/label;
  "34" İstanbul (Anadolu), "341" İstanbul (Avrupa), plus a duplicate "34" İstanbul) and ``expiryDates``
  (newest first, "2026-10-02T00:00:00"). ``GET /api/session-token`` → ``Data.SessionToken``; then
  ``GET /api/proxy?type=Njg=`` with headers ``X-CALL-TYPE: 68``, ``X-SessionToken``, ``X-PARAMS:
  base64({"cityId","validityDate","productId":"1"})`` → ``Data.Price``, ``Data.DepositPrice`` (320 TL).
- Milangaz: ``https://milangaz.com.tr/tupgaz/fiyatlar/`` ``<select id="iller">`` (zero-padded plate codes,
  "34" İstanbul-Anadolu, "134" İstanbul-Avrupa). ``POST /wp-admin/admin-ajax.php`` form
  ``action=get_city_code&city_code=06&city_type=TUBE`` → JSON list of every cylinder; the 12 kg ones are
  "12 KG TÜPLÜ LPG - VANALI" and "- SİBOPLU" (same price). Unpadded "6" answers ``null``. No date given;
  "KDV dahil tavan satış fiyatı".
- Mogaz: ``https://www.mogaz.com.tr/tupgaz/fiyatlar`` selects ``city`` ("34" Anadolu, "341" Avrupa, "33"
  İÇEL) and ``expiryDate`` ("02.10.2026"); ``POST /processor/GetTupGazPrice`` form
  ``city=06&tubeType=FIYAT12&expiryDate=02.10.2026`` → ``{"StatusMessage":"TRUE","Price":"1645.00"}``.
- İpragaz: ``https://www.ipragaz.com.tr/evde/tupgaz-fiyatlari`` has ``Cities: [...]`` in an inline script
  (84 names incl. "İstanbul-Adalar", "Çanakkale-B.G. Ada", "Afyon", "İçel"); ``GET
  /evde/tupgaz-fiyatlari-sonuc?city=<name>`` → server-rendered "Tüpgaz fiyatları 02.10.2026 tarihinden
  itibaren <city> ilinde geçerli KDV dahil tavan satış fiyatlarıdır ... Ev Tüpü 12 kg ₺1680.0". An unknown
  name answers the page without prices, so the city is looked up; every city tried had the same price.
- Likitgaz: host does not resolve (DNS), skipped.
All four answered curl_cffi with HTTP 200, no anti-bot.

``price`` = TL per 12 kg cylinder, VAT included (each brand's ceiling / recommended retail price).
``province_code`` is the plate number; ``region`` splits İstanbul (Anadolu / Avrupa / Adalar) and Çanakkale
(Bozcaada-Gökçeada) where the brand does; empty otherwise.

Output: InflationItems/Datas/04_Housing/LPG/YYYY-MM-DD.csv
Columns: product_name, price, category_number (4), sub_category_number (0452201), brand, province, region,
province_code, product, deposit, valid_from, source_url, collected_at.

The four brands are four hosts, so they run in parallel threads (one Client each, 1 s apart per host); a
full run takes as long as the slowest brand (Milangaz).

Mogaz answers an empty price for İstanbul Avrupa (code 341; its own form shows nothing either): logged as a
warning, no row. A province that fails is logged and skipped; a brand that fails is logged; the rest is still written and the
run exits with status 1. Nothing is written when every brand fails.

Examples:
  python scraper.py                                  # all brands, all provinces (~340 requests)
  python scraper.py --provinces 34 6 35              # bounded run: İstanbul, Ankara, İzmir
  python scraper.py --brand mogaz --provinces 6
"""

import argparse
import base64
import csv
import json
import logging
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from curl_cffi import requests

AYGAZ_PAGE = "https://www.aygaz.com.tr/fiyatlar/tupgaz"
AYGAZ_TOKEN = "https://www.aygaz.com.tr/api/session-token"
AYGAZ_API = "https://www.aygaz.com.tr/api/proxy?type=Njg="  # base64("68")
MILANGAZ_PAGE = "https://milangaz.com.tr/tupgaz/fiyatlar/"
MILANGAZ_API = "https://milangaz.com.tr/wp-admin/admin-ajax.php"
MOGAZ_PAGE = "https://www.mogaz.com.tr/tupgaz/fiyatlar"
MOGAZ_API = "https://www.mogaz.com.tr/processor/GetTupGazPrice"
IPRAGAZ_PAGE = "https://www.ipragaz.com.tr/evde/tupgaz-fiyatlari"
IPRAGAZ_RESULT = "https://www.ipragaz.com.tr/evde/tupgaz-fiyatlari-sonuc"
BACKOFF = [2, 5, 10]  # seconds waited after each failed request, then give up
BRANDS = ["aygaz", "milangaz", "mogaz", "ipragaz"]
PRICE_RANGE = (300, 20000)  # TL per 12 kg cylinder; outside means a parse error

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = REPO_ROOT / "InflationItems" / "Datas" / "04_Housing" / "LPG"

CATEGORY_NUMBER = 4
LPG_ITEM = "0452201"  # TÜİK item "LPG tüp"
COLUMNS = [
    "product_name", "price", "category_number", "sub_category_number",  # shared first four
    "brand", "province", "region", "province_code", "product", "deposit", "valid_from", "source_url",
    "collected_at",
]

PROVINCES = {
    1: "Adana", 2: "Adıyaman", 3: "Afyonkarahisar", 4: "Ağrı", 5: "Amasya", 6: "Ankara", 7: "Antalya",
    8: "Artvin", 9: "Aydın", 10: "Balıkesir", 11: "Bilecik", 12: "Bingöl", 13: "Bitlis", 14: "Bolu",
    15: "Burdur", 16: "Bursa", 17: "Çanakkale", 18: "Çankırı", 19: "Çorum", 20: "Denizli", 21: "Diyarbakır",
    22: "Edirne", 23: "Elazığ", 24: "Erzincan", 25: "Erzurum", 26: "Eskişehir", 27: "Gaziantep", 28: "Giresun",
    29: "Gümüşhane", 30: "Hakkari", 31: "Hatay", 32: "Isparta", 33: "Mersin", 34: "İstanbul", 35: "İzmir",
    36: "Kars", 37: "Kastamonu", 38: "Kayseri", 39: "Kırklareli", 40: "Kırşehir", 41: "Kocaeli", 42: "Konya",
    43: "Kütahya", 44: "Malatya", 45: "Manisa", 46: "Kahramanmaraş", 47: "Mardin", 48: "Muğla", 49: "Muş",
    50: "Nevşehir", 51: "Niğde", 52: "Ordu", 53: "Rize", 54: "Sakarya", 55: "Samsun", 56: "Siirt", 57: "Sinop",
    58: "Sivas", 59: "Tekirdağ", 60: "Tokat", 61: "Trabzon", 62: "Tunceli", 63: "Şanlıurfa", 64: "Uşak",
    65: "Van", 66: "Yozgat", 67: "Zonguldak", 68: "Aksaray", 69: "Bayburt", 70: "Karaman", 71: "Kırıkkale",
    72: "Batman", 73: "Şırnak", 74: "Bartın", 75: "Ardahan", 76: "Iğdır", 77: "Yalova", 78: "Karabük",
    79: "Kilis", 80: "Osmaniye", 81: "Düzce",
}
# İstanbul Avrupa codes per brand (Anadolu keeps 34)
AVRUPA_CODES = {"341", "134"}
# İpragaz city names that are not plain province names
IPRAGAZ_NAMES = {
    "Afyon": (3, ""), "İçel": (33, ""), "İstanbul - Anadolu": (34, "Anadolu"), "İstanbul - Avrupa": (34, "Avrupa"),
    "İstanbul-Adalar": (34, "Adalar"), "Çanakkale-B.G. Ada": (17, "Bozcaada-Gökçeada"),
}

log = logging.getLogger("lpg")


class Client:
    def __init__(self, delay: float):
        self.delay = delay
        self._last = 0.0
        self.session = requests.Session(impersonate="chrome")

    def request(self, method: str, url: str, **kwargs):
        for attempt in range(1, len(BACKOFF) + 2):
            wait = self.delay * random.uniform(0.8, 1.4) - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self.session.request(method, url, timeout=60, **kwargs)
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

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)


def norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\xa0", " ")).strip()


def dmy(text: str) -> str:
    """'02.10.2026' -> '2026-10-02'."""
    d, m, y = (int(x) for x in text.split("."))
    return date(y, m, d).isoformat()


def plate_region(code: str) -> tuple[int, str]:
    """Brand city code -> (plate, region): '341' / '134' -> (34, 'Avrupa'), '34' -> (34, 'Anadolu'), '06' -> (6, '')."""
    if code in AVRUPA_CODES:
        return 34, "Avrupa"
    plate = int(code)
    if plate not in PROVINCES:
        raise RuntimeError(f"unknown city code {code!r}")
    return plate, "Anadolu" if plate == 34 else ""


def lpg_row(brand, plate, region, product, price, deposit, valid_from, url) -> dict:
    price = float(price)
    if not PRICE_RANGE[0] <= price <= PRICE_RANGE[1]:
        raise RuntimeError(f"{brand} {PROVINCES[plate]} {region}: price {price} outside {PRICE_RANGE}")
    place = f"{PROVINCES[plate]} {region}".strip()
    return {
        "product_name": f"LPG {brand} {product} {place}", "price": price, "category_number": CATEGORY_NUMBER,
        "sub_category_number": LPG_ITEM, "brand": brand, "province": PROVINCES[plate], "region": region,
        "province_code": f"{plate:02d}", "product": product, "deposit": deposit, "valid_from": valid_from,
        "source_url": url,
    }


def per_city(brand: str, cities: list, wanted: set | None, fetch) -> tuple[list[dict], int]:
    """Run fetch(code, plate, region) for each wanted city; a failing city is logged and counted."""
    rows, failures = [], 0
    for code in cities:
        plate, region = code[1], code[2]
        if wanted and plate not in wanted:
            continue
        try:
            rows += fetch(code[0], plate, region)
        except Exception as exc:
            log.error("%s %s %s failed: %s", brand, PROVINCES[plate], region, exc)
            failures += 1
    if not rows:
        raise RuntimeError(f"{brand}: no city returned a price")
    return rows, failures


# --- Aygaz ------------------------------------------------------------------------------------------------

def aygaz(client: Client, wanted: set | None):
    raw = client.get(AYGAZ_PAGE).text
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw, re.S)
    if not m:
        raise RuntimeError("Aygaz: __NEXT_DATA__ not found")
    props = json.loads(m.group(1))["props"]["pageProps"]
    validity = max(d["value"] for d in props["expiryDates"])
    cities = []
    for c in props["cities"]:
        if c["value"] not in [x[0] for x in cities]:  # "34" is listed twice (Anadolu and plain İstanbul)
            cities.append((c["value"], *plate_region(c["value"])))
    token = client.get(AYGAZ_TOKEN).json()["Data"]["SessionToken"]

    def fetch(code, plate, region):
        params = json.dumps({"cityId": code, "validityDate": validity, "productId": "1"})
        headers = {"X-CALL-TYPE": "68", "X-SessionToken": token,
                   "X-PARAMS": base64.b64encode(params.encode()).decode(), "Referer": AYGAZ_PAGE}
        body = client.get(AYGAZ_API, headers=headers).json()
        data = body.get("Data") or {}
        if not body.get("IsSuccess") or not data.get("Price"):
            raise RuntimeError(f"no price ({json.dumps(body, ensure_ascii=False)[:200]})")
        return [lpg_row("Aygaz", plate, region, "12 kg tüp", data["Price"], data.get("DepositPrice", ""),
                        data["ValidityDate"][:10], AYGAZ_PAGE)]

    return per_city("Aygaz", cities, wanted, fetch)


# --- Milangaz ---------------------------------------------------------------------------------------------

def milangaz(client: Client, wanted: set | None):
    page = BeautifulSoup(client.get(MILANGAZ_PAGE).text, "lxml")
    select = page.find("select", id="iller")
    if select is None:
        raise RuntimeError("Milangaz: <select id='iller'> not found")
    cities = [(o["value"], *plate_region(o["value"])) for o in select.find_all("option") if o.get("value")]

    def fetch(code, plate, region):
        products = client.post(MILANGAZ_API, data={"action": "get_city_code", "city_code": code,
                                                   "city_type": "TUBE"}).json()
        if not products:
            raise RuntimeError("empty answer")
        # "12 KG TÜPLÜ LPG - VANALI" -> "12 kg tüp VANALI" (str.lower() mangles the dotted İ in "SİBOPLU")
        rows = [lpg_row("Milangaz", plate, region, "12 kg tüp " + norm(p["productName"]).rsplit(" - ", 1)[-1],
                        p["price"]["value"], "", "", MILANGAZ_PAGE)
                for p in products if norm(p["productName"]).startswith("12 KG")]
        if not rows:
            raise RuntimeError(f"no 12 KG product in {[p['productName'] for p in products]}")
        return rows

    return per_city("Milangaz", cities, wanted, fetch)


# --- Mogaz ------------------------------------------------------------------------------------------------

def mogaz(client: Client, wanted: set | None):
    page = BeautifulSoup(client.get(MOGAZ_PAGE).text, "lxml")
    city_sel, date_sel = page.find("select", id="city"), page.find("select", id="expiryDate")
    if city_sel is None or date_sel is None:
        raise RuntimeError("Mogaz: city / expiryDate select not found")
    expiry = max((o["value"] for o in date_sel.find_all("option") if o.get("value")), key=dmy)
    cities = [(o["value"], *plate_region(o["value"])) for o in city_sel.find_all("option") if o.get("value")]

    def fetch(code, plate, region):
        body = client.post(MOGAZ_API, data={"city": code, "tubeType": "FIYAT12", "expiryDate": expiry}).json()
        if body.get("StatusMessage") != "TRUE":
            raise RuntimeError(f"no price ({body})")
        if not body.get("Price"):  # the site's own form shows nothing either (İstanbul Avrupa, 2026-10-28)
            log.warning("Mogaz lists no price for %s %s", PROVINCES[plate], region)
            return []
        return [lpg_row("Mogaz", plate, region, "12 kg tüp", body["Price"], "", dmy(expiry), MOGAZ_PAGE)]

    return per_city("Mogaz", cities, wanted, fetch)


# --- İpragaz ----------------------------------------------------------------------------------------------

def ipragaz(client: Client, wanted: set | None):
    m = re.search(r"Cities: (\[.*?\])", client.get(IPRAGAZ_PAGE).text)
    if not m:
        raise RuntimeError("İpragaz: 'Cities: [...]' list not found")
    by_name = {v.casefold(): k for k, v in PROVINCES.items()}
    cities = []
    for name in json.loads(m.group(1)):
        plate, region = IPRAGAZ_NAMES.get(name) or (by_name.get(name.casefold()), "")
        if plate is None:
            raise RuntimeError(f"İpragaz: unknown city name {name!r}")
        cities.append((name, plate, region))

    def fetch(name, plate, region):
        resp = client.get(IPRAGAZ_RESULT, params={"city": name})
        text = norm(BeautifulSoup(resp.text, "lxml").get_text(" "))
        when = re.search(r"Tüpgaz fiyatları (\d{2}\.\d{2}\.\d{4}) tarihinden itibaren .{0,60}? ilinde geçerli "
                         r"KDV dahil tavan satış fiyatlarıdır", text)
        price = re.search(r"Ev Tüpü 12 kg ₺\s*([\d.]+)", text)
        if not when or not price:
            raise RuntimeError("date / 'Ev Tüpü 12 kg' price not found")
        return [lpg_row("İpragaz", plate, region, "12 kg tüp", price.group(1), "", dmy(when.group(1)), resp.url)]

    return per_city("İpragaz", cities, wanted, fetch)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brand", nargs="+", choices=BRANDS, default=BRANDS, help="brands to fetch (default: all)")
    ap.add_argument("--provinces", nargs="+", type=int, default=None,
                    help="plate codes to fetch, e.g. 34 6 35 (default: every province a brand lists)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests to one host (jittered)")
    ap.add_argument("--output", default=None, help="CSV file name inside the data dir (default: YYYY-MM-DD.csv)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    started = time.monotonic()
    wanted = set(args.provinces) if args.provinces else None

    steps = {"aygaz": ("Aygaz", aygaz), "milangaz": ("Milangaz", milangaz), "mogaz": ("Mogaz", mogaz),
             "ipragaz": ("İpragaz", ipragaz)}

    def run(brand):
        name, fetch = steps[brand]
        t0 = time.monotonic()
        got, failures = fetch(Client(args.delay), wanted)  # own Client per brand: 1 s delay per host still holds
        log.info("%s: %d rows in %.1f s, valid from %s", name, len(got), time.monotonic() - t0,
                 got[0]["valid_from"] or "(not given)")
        return got, failures

    # each brand is a different host, so the brands run at the same time; rows keep BRANDS order
    selected = [b for b in BRANDS if b in args.brand]
    rows, failed = [], []
    with ThreadPoolExecutor(max_workers=len(selected)) as pool:
        futures = {b: pool.submit(run, b) for b in selected}
        for brand, future in futures.items():
            name = steps[brand][0]
            try:
                got, failures = future.result()
                rows += got
                if failures:
                    failed.append(f"{name} ({failures} cities)")
            except Exception as exc:
                log.error("%s failed: %s", name, exc)
                failed.append(name)

    if not rows:
        log.error("every brand failed; no CSV written")
        sys.exit(1)
    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = DATA_DIR / (args.output or f"{date.today().isoformat()}.csv")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "collected_at": collected_at})
    log.info("wrote %d rows to %s in %.1f s", len(rows), csv_path, time.monotonic() - started)
    if failed:
        log.error("incomplete run, failed: %s", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
