"""
Residential natural gas price + connection/deposit fee scraper (TÜİK 04 Housing, items 0452101 Doğal gaz
and 0452102 Doğal gaz bağlantı ücreti), requests-only. Istanbul, Ankara, İzmir: no source publishes all
cities, so each city comes from its own distributor.

Recon (2026-10-28):
- İGDAŞ (İstanbul): the price page is client-rendered; the data is ``POST https://api.igdas.istanbul/Sap/Sap/
  PerakendeSatisFiyati`` with ``{"AYYIL": "MMYYYY"}`` → JSON list (``MUSTERI_TIPI``, ``SATIS_FIYATI`` TL/m³,
  ``SATIS_FIYATI_KWH``, ``ABDATUM`` valid from). ``www.igdas.istanbul`` closes the connection for curl_cffi
  and only 301-redirects to ``igdas.istanbul``; the bare host works. No tax note anywhere on the page; the
  figures are ÖTV-included and VAT-excluded (Kademe-1 − 10.625 gas − 0.1468 ÖTV = SKB, like the other two).
  The page fetched first is the fee page (server-rendered), used to cross-check the fees.
- Başkentgaz (Ankara): ``GET https://bskapiv1.baskentdogalgaz.com.tr/api/menus/31/sections`` lists one PDF
  per month (``title`` "2026 Ekim Ayı Değerleri ...", ``imageUrl`` /uploads/<uuid>.pdf, ``rowNumber`` grows
  with time, ``startDate`` set when published ahead). PDFs live on www.baskentdogalgaz.com.tr, not on the API
  host. Text PDF read with pypdf; the "ABONE" row "BASKENT02 0-75.000 K1 TL/Sm³, K1 TL/kWh, K2 TL/Sm³,
  K2 TL/kWh". The PDF says ÖTV included, VAT excluded. Fees (VAT included) in ``menus/42/sections``.
- İzmirgaz (İzmir): HTML fragment ``/pages/musteri_hizmetleri/konut.php``, tables headed "Konut Tüketicileri
  Kademe-1/2 (m³|kwh)" with gas, ÖTV, SKB and VAT-excluded price; fees in ``abone_baglanti.php`` and
  ``guvence.php`` (the EPDK decision text: year, "01/01/2026 tarihinden geçerli", VAT excluded). The server
  sends no intermediate certificate, so verification fails; the client then adds the issuer named in the
  certificate's AIA field (Sectigo DV R36, fetched from crt.sectigo.com) to the CA bundle and keeps verifying.

Rows written: per city, Kademe-1 and Kademe-2 for the household tier (İstanbul "KONUT", Ankara "ABONE"
0–75.000 Sm³/year, İzmir "0-100.000 (K1)" annual band); Kademe-2 applies to the whole monthly consumption once
it passes the city's monthly limit. Fee rows: the EPDK national caps from İzmirgaz (province "Türkiye"),
cross-checked against İGDAŞ and Başkentgaz; a mismatch is logged as a warning.

Output: InflationItems/Datas/04_Housing/NaturalGas/YYYY-MM-DD.csv
Columns: product_name, price, category_number (4), sub_category_number (0452101 | 0452102), province,
distributor, tier, price_per_m3, price_per_kwh, unit, vat_included, components, valid_from, source_url,
collected_at. ``price`` = TL/m³ (TL/Sm³ for Başkentgaz) for gas rows, TL for fee rows.

A source that fails is logged; the other sources are still written and the run exits with status 1.
Nothing is written when every source fails.

Examples:
  python scraper.py                          # all sources
  python scraper.py --source izmirgaz fees   # bounded run
"""

import argparse
import csv
import io
import logging
import random
import re
import ssl
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

import certifi
from bs4 import BeautifulSoup
from curl_cffi import requests
from curl_cffi.requests.exceptions import CertificateVerifyError
from pypdf import PdfReader

IGDAS_FEES_URL = "https://igdas.istanbul/musteri-hizmetleri/fiyat-tarifeleri/baglanti-guvence-ve-hizmet-bedelleri"
IGDAS_PRICE_PAGE = "https://igdas.istanbul/musteri-hizmetleri/fiyat-tarifeleri/perakende-satis-fiyatlari"
IGDAS_API = "https://api.igdas.istanbul/Sap/Sap/PerakendeSatisFiyati"
BASKENT_API = "https://bskapiv1.baskentdogalgaz.com.tr/api/menus/{menu}/sections"
BASKENT_SITE = "https://www.baskentdogalgaz.com.tr"
BASKENT_PRICE_MENU, BASKENT_FEE_MENU = 31, 42
IZMIRGAZ = "https://www.izmirgaz.com.tr"
IZMIRGAZ_PAGE = f"{IZMIRGAZ}/musteri_hizmetleri.php?data=id44"
IZMIRGAZ_KONUT = f"{IZMIRGAZ}/pages/musteri_hizmetleri/konut.php"
IZMIRGAZ_FEES = [f"{IZMIRGAZ}/pages/musteri_hizmetleri/abone_baglanti.php", f"{IZMIRGAZ}/pages/musteri_hizmetleri/guvence.php"]
# issuer of the *.izmirgaz.com.tr certificate (its AIA caIssuers URL); the server does not send it
IZMIRGAZ_INTERMEDIATE = "http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt"
BACKOFF = [2, 5, 10]  # seconds waited after each failed request, then give up
SOURCES = ["igdas", "baskentgaz", "izmirgaz", "fees"]

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = REPO_ROOT / "InflationItems" / "Datas" / "04_Housing" / "NaturalGas"

CATEGORY_NUMBER = 4
GAS_ITEM = "0452101"  # TÜİK item "Doğal gaz"
FEE_ITEM = "0452102"  # TÜİK item "Doğal gaz bağlantı ücreti"
COLUMNS = [
    "product_name", "price", "category_number", "sub_category_number",  # shared first four
    "province", "distributor", "tier", "price_per_m3", "price_per_kwh", "unit", "vat_included",
    "components", "valid_from", "source_url", "collected_at",
]
TR_MONTHS = {m: i for i, m in enumerate(
    ["ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık"], 1)}

log = logging.getLogger("natural_gas")


class Client:
    def __init__(self, delay: float, verify=True):
        self.delay = delay
        self._last = 0.0
        self.session = requests.Session(impersonate="chrome", verify=verify)

    def request(self, method: str, url: str, **kwargs):
        for attempt in range(1, len(BACKOFF) + 2):
            wait = self.delay * random.uniform(0.8, 1.4) - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self.session.request(method, url, timeout=60, **kwargs)
            except CertificateVerifyError:
                raise
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


def norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\xa0", " ")).strip()


def tr_month(name: str) -> int | None:
    """'EKİM' / 'Ekim' -> 10 (str.lower() turns 'İ' into 'i' + a combining dot)."""
    return TR_MONTHS.get(name.replace("İ", "i").replace("I", "ı").lower())


def tr_number(text: str) -> float:
    """'14,468019' / '₺9.679,20' / '8.066' (Turkish: dot = thousands, comma = decimal)."""
    t = re.sub(r"[^\d.,]", "", text)
    if "," in t:
        return float(t.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        return float(t.replace(".", ""))
    return float(t)


def gas_row(province, distributor, tier, per_m3, per_kwh, unit, components, valid_from, url) -> dict:
    return {
        "product_name": f"Doğal gaz {province} {distributor} {tier}", "price": per_m3,
        "category_number": CATEGORY_NUMBER, "sub_category_number": GAS_ITEM, "province": province,
        "distributor": distributor, "tier": tier, "price_per_m3": per_m3, "price_per_kwh": per_kwh, "unit": unit,
        "vat_included": "false", "components": components, "valid_from": valid_from, "source_url": url,
    }


# --- İGDAŞ (İstanbul) -------------------------------------------------------------------------------------

def igdas(client: Client, today: date) -> tuple[list[dict], dict]:
    """Household rows for this month, and the fee table (label -> TL) from the fee page."""
    fees = {}
    soup = BeautifulSoup(client.request("GET", IGDAS_FEES_URL).text, "lxml")
    for tr in soup.select("table tr"):
        cells = [norm(c.get_text(" ")) for c in tr.find_all(["td", "th"])]
        if len(cells) == 2 and re.search(r"\d", cells[1]):
            fees[cells[0]] = tr_number(cells[1])
    rows = igdas_month(client, today)
    # a month with a mid-month change has two rows per tier; take the one in force today
    latest = {}
    for r in sorted(rows, key=lambda r: r["valid_from"]):
        if r["valid_from"] <= today.isoformat():
            latest[r["tier"]] = r
    if len(latest) != 2:
        raise RuntimeError(f"İGDAŞ {today:%m%Y}: no KONUT / KONUT KADEME-2 price in force on {today}")
    return list(latest.values()), fees


def igdas_month(client: Client, month: date) -> list[dict]:
    """Every household row the API lists for the month (one per tier and ABDATUM valid-from date)."""
    ayyil = f"{month.month:02d}{month.year}"
    data = client.request("POST", IGDAS_API, json={"AYYIL": ayyil},
                          headers={"Origin": "https://igdas.istanbul", "Referer": IGDAS_PRICE_PAGE}).json()
    rows = []
    for d in data if isinstance(data, list) else []:
        kind = norm(d.get("MUSTERI_TIPI")).upper()
        if kind == "KONUT":
            tier = "Konut Kademe-1"
        elif kind.startswith("KONUT KADEME-2"):
            tier = "Konut Kademe-2"
        else:
            continue
        rows.append(gas_row("İstanbul", "İGDAŞ", tier, d["SATIS_FIYATI"], d["SATIS_FIYATI_KWH"], "TL/m³", "",
                            d.get("ABDATUM", ""), IGDAS_PRICE_PAGE))
    if {r["tier"] for r in rows} != {"Konut Kademe-1", "Konut Kademe-2"}:
        raise RuntimeError(f"İGDAŞ {ayyil}: expected KONUT and KONUT KADEME-2, got {str(data)[:300]}")
    return rows


# --- Başkentgaz (Ankara) ----------------------------------------------------------------------------------

def baskent_month(title: str) -> date | None:
    """Valid-from date of a monthly tariff PDF: '2026 Nisan Ayı Değerleri (04.Gün ve Sonrası İçin Geçerli)' ->
    2026-04-04; '(2.Gün İçin Geçerli)' / '(31.Gün Geçerli)' -> that day; '(30.Gün ve Öncesi ...)' or none -> 1st."""
    m = re.match(r"\s*(\d{4})\s+(\S+)\s+Ayı", title)
    if not m or not tr_month(m.group(2)):
        return None
    day = re.search(r"\((\d{1,2})\.\s*Gün", title)
    return date(int(m.group(1)), tr_month(m.group(2)), int(day.group(1)) if day and "Öncesi" not in title else 1)


def baskentgaz(client: Client) -> list[dict]:
    sections = client.request("GET", BASKENT_API.format(menu=BASKENT_PRICE_MENU)).json()["sections"]
    now = datetime.now()
    live = [s for s in sections if s.get("isActive") and not s.get("isDeleted") and baskent_month(s.get("title", ""))
            and (s.get("imageUrl") or "").endswith(".pdf")
            and not (s.get("startDate") and datetime.fromisoformat(s["startDate"][:19]) > now)]
    if not live:
        raise RuntimeError(f"Başkentgaz: no monthly tariff PDF in {len(sections)} sections")
    sec = max(live, key=lambda s: (baskent_month(s["title"]), s.get("rowNumber", 0)))
    rows = baskent_pdf(client, sec)
    if len(rows) != 2:
        raise RuntimeError(f"Başkentgaz {sec['title']!r}: expected Kademe-1 and Kademe-2, got {len(rows)} rows")
    log.info("Başkentgaz: %s (%s)", norm(sec["title"]), rows[0]["source_url"])
    return rows


def baskent_pdf(client: Client, sec: dict) -> list[dict]:
    """Household rows of one monthly tariff PDF: Kademe-1 and Kademe-2 since 04.04.2026, one price before."""
    valid_from = baskent_month(sec["title"])
    url = BASKENT_SITE + sec["imageUrl"]
    content = client.request("GET", url).content
    if not content.startswith(b"%PDF"):
        raise RuntimeError(f"{url} is not a PDF ({content[:40]!r})")
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(content)).pages)
    # "YIL: 2026 AY: EKİM", split months "YIL : 2025 AY: 01-04 NİSAN" / "31 ARALIK", July 2025 only
    # "02 TEMMUZ 2025 TARİHİ İÇİN GEÇERLİ" / "03-31 TEMMUZ 2025 TARİHLERİ ARASI GEÇERLİ"
    m = re.search(r"YIL\s*:\s*(\d{4})\s+AY:\s*(?:[\d-]+\s+)?(\S+)", text)
    period = (int(m.group(1)), tr_month(m.group(2))) if m else None
    if not m and (m := re.search(r"[\d-]+ (\S+) (\d{4}) TARİH(?:İ İÇİN|LERİ ARASI) GEÇERLİ", text)):
        period = (int(m.group(2)), tr_month(m.group(1)))
    if period != (valid_from.year, valid_from.month):
        raise RuntimeError(f"Başkentgaz PDF period {m.group(0) if m else None!r} does not match {sec['title']!r}")
    otv = re.search(r"([\d,]+) TL/Sm3 ÖTV bedeli dahildir", text)  # 0,1187 in 2025, 0,1468 since
    if not otv or not re.search(r"KDV dahil değildir", text):
        raise RuntimeError("Başkentgaz PDF: ÖTV/KDV note changed; check what the prices include")
    # ABONE household row: K1 Sm³, K1 kWh[, K2 Sm³, K2 kWh]; the şehit/gazi row above it lacks "ABONE BASKENT01"
    m = re.search(r"ABONE\s+BASKENT01\s*BASKENT02\s+0-75\.000\s+([\d,]+)\s+([\d,]+)(?:\s+([\d,]+)\s+([\d,]+))?", text)
    if not m:
        raise RuntimeError("Başkentgaz PDF: household (ABONE 0-75.000) row not found")
    prices = [(1, tr_number(m.group(1)), tr_number(m.group(2)))]
    if m.group(3):
        prices.append((2, tr_number(m.group(3)), tr_number(m.group(4))))
    return [gas_row("Ankara", "Başkentgaz", f"Konut Kademe-{k} (abone 0-75.000 Sm³/yıl)", m3, kwh, "TL/Sm³",
                    f"ötv={tr_number(otv.group(1))} (dahil)", valid_from.isoformat(), url) for k, m3, kwh in prices]


def baskentgaz_fees(client: Client) -> dict:
    """Fee table (label -> TL, VAT included) from the fee section's HTML."""
    fees = {}
    for sec in client.request("GET", BASKENT_API.format(menu=BASKENT_FEE_MENU)).json()["sections"]:
        for tr in BeautifulSoup(sec.get("detail") or "", "lxml").find_all("tr"):
            cells = [norm(c.get_text(" ")) for c in tr.find_all("td")]
            if len(cells) == 2 and "₺" in cells[1]:
                fees[cells[0]] = tr_number(cells[1])
    return fees


# --- İzmirgaz (İzmir) -------------------------------------------------------------------------------------

def izmirgaz_client(delay: float) -> Client:
    """Normal verification first; if the server still omits its intermediate, add it from the AIA URL."""
    client = Client(delay)
    try:
        client.request("GET", IZMIRGAZ_PAGE)
        return client
    except CertificateVerifyError:
        log.info("İzmirgaz sends no intermediate certificate; adding %s to the CA bundle", IZMIRGAZ_INTERMEDIATE)
    der = Client(delay).request("GET", IZMIRGAZ_INTERMEDIATE).content
    bundle = Path(tempfile.mkdtemp(prefix="natural_gas_ca_")) / "ca.pem"
    bundle.write_text(Path(certifi.where()).read_text(encoding="utf-8") + "\n" + ssl.DER_cert_to_PEM_cert(der),
                      encoding="utf-8")
    client = Client(delay, verify=str(bundle))
    client.request("GET", IZMIRGAZ_PAGE)
    return client


def table_rows(table) -> list[list[str]]:
    for sup in table.find_all("sup"):  # "m<sup>2</sup>" -> "m²"
        sup.replace_with({"2": "²", "3": "³"}.get(sup.get_text(strip=True), sup.get_text()))
    table.smooth()  # merge "m" and "²" into one string so get_text(" ") does not split them
    return [[norm(c.get_text(" ")) for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]


def izmirgaz(client: Client) -> list[dict]:
    soup = BeautifulSoup(client.request("GET", IZMIRGAZ_KONUT).content.decode("utf-8"), "lxml")
    tables = {}  # (kademe, "m3" | "kwh") -> first data row as {header: value}
    for table in soup.find_all("table"):
        # heading "<b>Konut Tüketicileri Kademe-2 <p>(m³)</p></b>": lxml cuts the unit off the <b>, so the
        # unit comes from the table's own "Gaz Alım Fiyatı (TL/m³ )" / "(TL/Kwh)" header
        heading = table.find_previous(string=re.compile(r"Konut Tüketicileri\s+Kademe-\d"))
        rows = table_rows(table)
        unit = next((re.search(r"TL\s*/\s*(m³|kwh)", h, re.I) for h in rows[0] if h.startswith("Gaz Alım")), None)
        if not heading or not unit or len(rows) < 2:
            continue
        key = (int(re.search(r"Kademe-(\d)", heading).group(1)), "m3" if unit.group(1) == "m³" else "kwh")
        tables.setdefault(key, dict(zip(rows[0], rows[1])))
    if set(tables) != {(1, "m3"), (1, "kwh"), (2, "m3"), (2, "kwh")}:
        raise RuntimeError(f"İzmirgaz konut.php: tariff tables changed, found {sorted(tables)}")

    def col(row: dict, prefix: str) -> str:
        return next(v for k, v in row.items() if k.startswith(prefix))

    out = []
    for k in (1, 2):
        m3, kwh = tables[(k, "m3")], tables[(k, "kwh")]
        band = re.sub(r"\s*\(K\d\)", "", col(m3, "Yıllık Tüketim"))  # "0-100.000 (K1)": K1 = annual band
        if not band.startswith("0-"):
            raise RuntimeError(f"İzmirgaz Kademe-{k}: first row is {band!r}, expected the lowest annual band")
        d, mo, y = col(m3, "Geçerlilik").split(".")
        components = f"gas={col(m3, 'Gaz Alım')};ötv={col(m3, 'ÖTV')};skb={col(m3, 'SKB')}"
        out.append(gas_row("İzmir", "İzmirgaz", f"Konut Kademe-{k} ({band} m³/yıl)", float(col(m3, "Satış Fiyatı")),
                           float(col(kwh, "Satış Fiyatı")), "TL/m³", components, f"{y}-{mo}-{d}", IZMIRGAZ_KONUT))
    return out


def izmirgaz_fees(client: Client) -> list[dict]:
    """EPDK connection and deposit fee caps (VAT excluded) as published by İzmirgaz."""
    rows, valid_from = [], None
    for url in IZMIRGAZ_FEES:
        soup = BeautifulSoup(client.request("GET", url).content.decode("utf-8"), "lxml")
        text = norm(soup.get_text(" "))
        if url == IZMIRGAZ_FEES[0] and not re.search(r"Katma Değer Vergisi dâhil değildir", text):
            raise RuntimeError(f"{url}: VAT note not found; check what the fees include")
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})\s*tarihinden geçerli", text)
        if m:
            valid_from = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        for table in soup.find_all("table"):
            for cells in table_rows(table):
                if len(cells) == 2 and re.fullmatch(r"[\d.,]+", cells[1]):
                    rows.append({"label": cells[0], "price": tr_number(cells[1]), "url": url})
    if not valid_from or not any(r["label"].startswith("Abone Bağlantı Bedeli") for r in rows):
        raise RuntimeError(f"İzmirgaz fee pages changed: valid_from={valid_from}, rows={[r['label'] for r in rows]}")
    return [{
        "product_name": f"Doğal gaz {r['label']}", "price": r["price"], "category_number": CATEGORY_NUMBER,
        "sub_category_number": FEE_ITEM, "province": "Türkiye", "distributor": "EPDK üst sınır (İzmirgaz)",
        "tier": r["label"], "price_per_m3": "", "price_per_kwh": "", "unit": "TL", "vat_included": "false",
        "components": "", "valid_from": valid_from, "source_url": r["url"],
    } for r in rows]


def cross_check_fees(fee_rows: list[dict], igdas_fees: dict, baskent_fees: dict):
    """Warn when İstanbul or Ankara charge something other than the national cap."""
    def find(fees: dict, *words) -> float | None:
        return next((v for k, v in fees.items() if all(w.lower() in k.lower() for w in words)), None)

    for row in fee_rows:
        label = row["tier"]
        words = ("Abone Bağlantı",) if label.startswith("Abone Bağlantı") else \
                ("Güvence", "Kombi") if "Kombi" in label else None
        if not words:
            continue
        for name, fees in (("İGDAŞ", igdas_fees), ("Başkentgaz", baskent_fees)):
            vat = 1.2 if name == "Başkentgaz" and "Bağlantı" in label else 1.0  # Başkentgaz: VAT on fees, not deposits
            if words == ("Güvence", "Kombi") and name == "Başkentgaz":
                found = next((v for k, v in fees.items() if k == "Kombi"), None)  # under a "GÜVENCE" heading
            else:
                found = find(fees, *words)
            if found is None and fees:
                log.warning("fee check: %s has no %r row", name, label)
            elif found is not None and abs(found / vat - row["price"]) > 0.5:
                log.warning("fee check: %s %r = %s (VAT ×%s) differs from the cap %s", name, label, found, vat, row["price"])
            elif found is not None:
                log.info("fee check: %s %r matches the cap %s", name, label, row["price"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", nargs="+", choices=SOURCES, default=SOURCES, help="sources to fetch (default: all)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests to one host (jittered)")
    ap.add_argument("--output", default=None, help="CSV file name inside the data dir (default: YYYY-MM-DD.csv)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    started = time.monotonic()
    today = date.today()

    rows, failed, igdas_fees, baskent_fees = [], [], {}, {}
    steps = {"igdas": "İGDAŞ", "baskentgaz": "Başkentgaz", "izmirgaz": "İzmirgaz", "fees": "fees"}
    izmir_client = None
    for src in [s for s in SOURCES if s in args.source]:
        try:
            if src == "igdas":
                got, igdas_fees = igdas(Client(args.delay), today)
            elif src == "baskentgaz":
                got = baskentgaz(Client(args.delay))
            elif src == "izmirgaz":
                izmir_client = izmir_client or izmirgaz_client(args.delay)
                got = izmirgaz(izmir_client)
            else:
                izmir_client = izmir_client or izmirgaz_client(args.delay)
                got = izmirgaz_fees(izmir_client)
                baskent_fees = baskentgaz_fees(Client(args.delay))
                cross_check_fees(got, igdas_fees, baskent_fees)
            log.info("%s: %d rows", steps[src], len(got))
            rows += got
        except Exception as exc:
            log.error("%s failed: %s", steps[src], exc)
            failed.append(steps[src])

    if not rows:
        log.error("every source failed; no CSV written")
        sys.exit(1)
    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = DATA_DIR / (args.output or f"{today.isoformat()}.csv")
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
