"""
Residential municipal water tariff scraper (TÜİK 04 Housing, item 0441101 Belediye suyu), requests-only.
Istanbul, Ankara, İzmir: no source publishes all cities, so each city comes from its own water utility.

Recon (2026-10-28):
- İSKİ (İstanbul): ``https://iski.istanbul/abone-hizmetleri/abone-rehberi/su-birim-fiyatlari/`` is Nuxt
  server-rendered, but the tariff table is not real HTML: it sits HTML-escaped in the ``source`` attribute of a
  ``<vue-markdown>`` tag ("İSKİ GENEL MÜDÜRLÜĞÜ 2026 SU SATIŞ TARİFELERİ (KDV HARİÇ)"; Konut 0-15 / 16-30 /
  31+ m³/ay, su + atık su = toplam). The table has no month, but prices change monthly. The same markup links
  one PDF per year ("2026 Yılı", ``iskiapi.iski.gov.tr/uploads/2026_aylik_su_ve_atiksu_birim_fiyatlari_<hash>.pdf``)
  with one column per month headed by its effective date (5.01.2026 … 5.10.2026). pypdf scrambles the order of
  the date headers but keeps the month columns in order, so the dates are sorted and paired with the Konut
  1.Kademe triples; the column that equals the HTML's tier 1 gives the effective date.
- ASKİ (Ankara): ``https://www.aski.gov.tr/tr/ucretler.aspx`` links "Güncel Su ve Atıksu Tarifesini PDF İndir"
  → ``/Yukle/Dosya/SuTarifesi.pdf`` (overwritten in place). One-page text PDF: "KONUT ABONELERİ" 0-15 / 16-30 /
  30 m³ üzeri, "SOSYAL YARDIM ALAN KONUT ABONELERİ" 0-10 / 11-15 / 16-30 / 30 m³ üzeri, each SU ATIKSU TOPLAM;
  "05.10.2026 TARİHİ İTİBARIYLA ... (KDV DAHİL DEĞİLDİR)". VAT would be 1 % on water, 10 % on wastewater.
- İZSU (İzmir): ``https://izsu.gov.tr/su-ve-atik-su-tarifesi`` is Next.js; the tariff is an HTML string in a
  ``self.__next_f.push([1, "..."])`` RSC chunk (JSON-decoded, then parsed). First table, "1a KONUT ABONELERİ"
  rows 0~10 / 11~20 / 21~40 / 41~Üstü; "01.06.2026 tarihinden itibaren ... KDV hariç". The "2a ATIKSU KONUT"
  rows (wastewater only, own well) are not taken.
All three answered curl_cffi with HTTP 200 (İSKİ has an F5 ASM script that did not interfere).

Rows written: household (konut) tiers per city, plus ASKİ's sosyal yardım konut tiers. ``tier_to_m3`` is empty
for the open top tier; "30 m³ üzeri" is written as from 31. ``price`` = total = water + wastewater, TL/m³,
VAT and ÇTV excluded.

Output (upstream layout: one CSV per store and day): InflationItems/Datas/04_Housing/<Store>/<store>_YYYY-MM-DD.csv
with Store = ISKI, ASKI, IZSU.
Columns: product_name, price, category_number (4), sub_category_number (0441101), province, utility,
subscriber_type, tier_from_m3, tier_to_m3, water_price, wastewater_price, total, unit, vat_included,
ctv_included, effective_date, source_url, collected_at.

A source that fails is logged; the other sources are still written and the run exits with status 1.
Nothing is written when every source fails.

Examples:
  python scraper.py                  # all sources
  python scraper.py --source izsu    # bounded run
"""

import argparse
import csv
import io
import json
import logging
import random
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests
from pypdf import PdfReader

ISKI_URL = "https://iski.istanbul/abone-hizmetleri/abone-rehberi/su-birim-fiyatlari/"
ASKI_PAGE = "https://www.aski.gov.tr/tr/ucretler.aspx"
ASKI_PDF = "https://www.aski.gov.tr/Yukle/Dosya/SuTarifesi.pdf"  # fallback if the page link moves
IZSU_URL = "https://izsu.gov.tr/su-ve-atik-su-tarifesi"
BACKOFF = [2, 5, 10]  # seconds waited after each failed request, then give up
SOURCES = ["iski", "aski", "izsu"]

REPO_ROOT = Path(__file__).resolve().parents[4]
DATAS_DIR = REPO_ROOT / "InflationItems" / "Datas" / "04_Housing"
STORES = {"İSKİ": "ISKI", "ASKİ": "ASKI", "İZSU": "IZSU"}  # row "utility" -> store folder
BACKFILL_DIR = REPO_ROOT / "logs" / "backfill"  # version histories; Datas holds only one CSV per store and day

CATEGORY_NUMBER = 4
WATER_ITEM = "0441101"  # TÜİK item "Belediye suyu"
COLUMNS = [
    "product_name", "price", "category_number", "sub_category_number",  # shared first four
    "province", "utility", "subscriber_type", "tier_from_m3", "tier_to_m3", "water_price", "wastewater_price",
    "total", "unit", "vat_included", "ctv_included", "effective_date", "source_url", "collected_at",
]

log = logging.getLogger("water")


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


def norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\xa0", " ")).strip()


def tr_number(text: str) -> float:
    """'43,70' / '1.234,56' (Turkish: dot = thousands, comma = decimal)."""
    return float(re.sub(r"[^\d,]", "", text).replace(",", "."))


TR_MONTHS = {m: i for i, m in enumerate(
    ["ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık"], 1)}


def tr_month(name: str) -> int | None:
    """'ARALIK' / 'Ekim' -> month number (str.lower() turns 'İ' into 'i' + a combining dot)."""
    return TR_MONTHS.get(name.replace("İ", "i").replace("I", "ı").lower())


def dmy(text: str) -> str:
    """'5.10.2026' / '05.10.2026' -> '2026-10-05'."""
    d, m, y = (int(x) for x in text.split("."))
    return date(y, m, d).isoformat()


def tier(text: str) -> tuple[int, int | None]:
    """'0 - 15 m³/ay' / '16-30 m³' / '30 m³ üzeri' / '31 ve üzeri m³/ay' / '41~Üstü' -> (from, to)."""
    m = re.match(r"\s*(\d+)\s*[-~–]\s*(\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"\s*(\d+)\s*(m\S*\s*)?(ve\s+)?(üzeri|~\s*üstü)", text, re.I)
    if m:  # "30 m³ üzeri" means above 30; "31 ve üzeri" and "41~Üstü" include the number
        start = int(m.group(1))
        return (start + 1 if m.group(2) and not m.group(3) else start), None
    raise RuntimeError(f"unknown tier label {text!r}")


def water_row(province, utility, subscriber_type, label, water, wastewater, total, effective_date, url) -> dict:
    if abs(water + wastewater - total) > 0.02:
        raise RuntimeError(f"{utility} {subscriber_type} {label!r}: {water} + {wastewater} != {total}")
    lo, hi = tier(label)
    span = f"{lo}-{hi}" if hi is not None else f"{lo}+"
    return {
        "product_name": f"Su {province} {utility} {subscriber_type} {span} m³", "price": total,
        "category_number": CATEGORY_NUMBER, "sub_category_number": WATER_ITEM, "province": province,
        "utility": utility, "subscriber_type": subscriber_type, "tier_from_m3": lo,
        "tier_to_m3": "" if hi is None else hi, "water_price": water, "wastewater_price": wastewater,
        "total": total, "unit": "TL/m³", "vat_included": "false", "ctv_included": "false",
        "effective_date": effective_date, "source_url": url,
    }


# --- İSKİ (İstanbul) --------------------------------------------------------------------------------------

ISKI_PDF_TIERS = {"Konut 1.Kademe": "0-15", "Konut 2.Kademe": "16-30", "Konut 3.Kademe": "31 ve üzeri"}


def iski_pdf_months(client: Client, pdf_url: str) -> list[tuple[str, list[tuple]]]:
    """The yearly PDF as [(effective date, [(tier label, water, wastewater, total) per Konut tier])]."""
    content = client.get(pdf_url).content
    if not content.startswith(b"%PDF"):
        raise RuntimeError(f"{pdf_url} is not a PDF ({content[:40]!r})")
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(content)).pages)
    if "SU SATIŞ TARİFELERİ (KDV HARİÇ)" not in text:
        raise RuntimeError(f"{pdf_url}: not the monthly water tariff PDF (title not found)")
    # headers come out glued and out of order ("5.06.20264.05.2026"); the month columns themselves are in order
    dates = sorted({dmy(m.group(0)) for m in re.finditer(r"\d{1,2}\.\d{2}\.20\d{2}", text)})
    columns = {k: [] for k in ISKI_PDF_TIERS}  # each Konut tier line appears once per block of months
    for line in text.splitlines():
        key = next((k for k in ISKI_PDF_TIERS if line.startswith(k)), None)
        if key:
            nums = [tr_number(n) for n in re.findall(r"\d+,\d{2}", line)]
            columns[key] += [tuple(nums[i:i + 3]) for i in range(0, len(nums) - 2, 3)]
    if not dates or any(len(c) != len(dates) for c in columns.values()):
        raise RuntimeError(f"İSKİ PDF: {len(dates)} month dates but Konut columns "
                           f"{ {k: len(c) for k, c in columns.items()} }")
    return [(d, [(ISKI_PDF_TIERS[k], *columns[k][i]) for k in ISKI_PDF_TIERS]) for i, d in enumerate(dates)]


def iski_month(client: Client, pdf_url: str, tier1: tuple[float, float, float]) -> str:
    """Effective date of the yearly PDF's month column whose Konut 1.Kademe equals the HTML's tier 1."""
    months = iski_pdf_months(client, pdf_url)
    dates = [d for d, _ in months]
    matches = [d for d, tiers in months if tuple(tiers[0][1:]) == tier1]
    if not matches:
        raise RuntimeError(f"İSKİ: HTML tier 1 {tier1} is in no month column of {pdf_url}")
    if matches[-1] != dates[-1]:
        log.warning("İSKİ: the HTML shows the %s prices, the PDF already has %s", matches[-1], dates[-1])
    return matches[-1]


def iski_markup(client: Client) -> BeautifulSoup:
    page = BeautifulSoup(client.get(ISKI_URL).content.decode("utf-8"), "lxml")
    # the content is HTML-escaped inside <vue-markdown source='...'>; parse each source as its own document
    return BeautifulSoup("".join(v.get("source", "") for v in page.find_all("vue-markdown")), "lxml")


def iski_pdf_links(markup: BeautifulSoup) -> dict[int, str]:
    pdfs = {}  # "Su Birim Fiyatları" links come first; a later "KSUB Birim Fiyatları" list reuses "<year> Yılı"
    for a in markup.find_all("a", href=True):
        if (m := re.fullmatch(r"(20\d{2}) Yılı", norm(a.get_text()))) and ".pdf" in a["href"]:
            pdfs.setdefault(int(m.group(1)), a["href"])
    return pdfs


def iski(client: Client) -> list[dict]:
    markup = iski_markup(client)
    table = next((t for t in markup.find_all("table") if "SU SATIŞ TARİFELERİ" in t.get_text()), None)
    if table is None:
        raise RuntimeError("İSKİ: 'SU SATIŞ TARİFELERİ' table not found")
    heading = norm(table.find("tr").get_text(" "))
    year = re.search(r"(20\d{2}) SU SATIŞ TARİFELERİ \(KDV HARİÇ\)", heading)
    if not year:
        raise RuntimeError(f"İSKİ: table heading changed ({heading!r}); check year and VAT")
    tiers, in_konut = [], False
    for tr in table.find_all("tr")[2:]:
        cells = [norm(c.get_text(" ")) for c in tr.find_all("td")]
        if len(cells) == 5:  # first row of a group carries the group name (rowspan)
            in_konut = cells[0] == "Konut"
            cells = cells[1:]
        if in_konut and len(cells) == 4:
            tiers.append((cells[0], *(tr_number(c) for c in cells[1:])))
        elif len(cells) != 4:
            in_konut = False
    if len(tiers) != 3:
        raise RuntimeError(f"İSKİ: expected 3 Konut tiers, got {tiers}")
    pdfs = iski_pdf_links(markup)
    if int(year.group(1)) not in pdfs:
        # early in a year the new year's PDF is not linked yet: write the last month of the newest earlier PDF
        last = max((y for y in pdfs if y < int(year.group(1))), default=None)
        if last is None:
            raise RuntimeError(f"İSKİ: no '{year.group(1)} Yılı' PDF link and no earlier one (found {sorted(pdfs)})")
        effective, last_tiers = iski_pdf_months(client, pdfs[last])[-1]
        log.warning("İSKİ: no %s PDF yet; writing the %s PDF's last month (%s)", year.group(1), last, effective)
        return [water_row("İstanbul", "İSKİ", "konut", *t, effective, pdfs[last]) for t in last_tiers]
    effective = iski_month(client, pdfs[int(year.group(1))], tiers[0][1:])
    return [water_row("İstanbul", "İSKİ", "konut", *t, effective, ISKI_URL) for t in tiers]


# --- ASKİ (Ankara) ----------------------------------------------------------------------------------------

def aski(client: Client) -> list[dict]:
    page = BeautifulSoup(client.get(ASKI_PAGE).content.decode("utf-8"), "lxml")
    link = next((a["href"] for a in page.find_all("a", href=True) if "Güncel Su ve Atıksu" in a.get_text()), None)
    url = urljoin(ASKI_PAGE, link.replace("\\", "/")) if link else ASKI_PDF
    if not link:
        log.warning("ASKİ: 'Güncel Su ve Atıksu Tarifesi' link not found; trying %s", ASKI_PDF)
    return aski_parse(client.get(url).content, url)


def aski_parse(content: bytes, url: str) -> list[dict]:
    if not content.startswith(b"%PDF"):
        raise RuntimeError(f"{url} is not a PDF ({content[:40]!r})")
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(content)).pages)
    # "05.10.2026 TARİHİ İTİBARIYLA SU VE ..." now, "03.12.2024 TARİHLİ SU VE ..." and
    # "ARALIK 2025 TARİHLİ SU VE ..." / "MART 2026 SU VE ..." (month only; the 1st is used) in older copies
    m = re.search(r"(\d{2}\.\d{2}\.\d{4}|[A-ZÇĞİÖŞÜ]+ \d{4})(?: TARİH(?:İ İTİBARIYLA|Lİ))? SU VE ATIKSU TARİFESİ",
                  text)
    if not m or "KDV DAHİL DEĞİLDİR" not in text:
        raise RuntimeError("ASKİ PDF: effective date or 'KDV DAHİL DEĞİLDİR' note not found")
    if m.group(1)[0].isdigit():
        effective = dmy(m.group(1))
    else:
        month, year = m.group(1).split()
        if not tr_month(month):
            raise RuntimeError(f"ASKİ PDF: unknown month in {m.group(0)!r}")
        effective = date(int(year), tr_month(month), 1).isoformat()
        log.warning("ASKİ PDF %s gives only the month (%s); effective_date set to %s", url, m.group(1), effective)
    groups = {"KONUT ABONELERİ": "konut", "SOSYAL YARDIM ALAN KONUT ABONELERİ": "sosyal konut"}
    rows, current = [], None
    for line in text.splitlines():
        line = norm(line)
        if line in groups:
            current = groups[line]
            continue
        t = re.fullmatch(r"(\d+-\d+ m\S*|\d+ m\S* üzeri) ([\d,]+) ([\d,]+) ([\d,]+)", line)
        if current and t:
            rows.append(water_row("Ankara", "ASKİ", current, t.group(1), *(tr_number(g) for g in t.groups()[1:]),
                                  effective, url))
        else:
            current = None
    counts = [sum(r["subscriber_type"] == s for r in rows) for s in ("konut", "sosyal konut")]
    if counts != [3, 4]:
        raise RuntimeError(f"ASKİ PDF: expected 3 konut + 4 sosyal konut tiers, got {counts}")
    return rows


# --- İZSU (İzmir) -----------------------------------------------------------------------------------------

def izsu(client: Client) -> list[dict]:
    return izsu_parse(client.get(IZSU_URL).content.decode("utf-8"), IZSU_URL)


def izsu_parse(raw: str, url: str) -> list[dict]:
    html = None
    for chunk in re.findall(r"self\.__next_f\.push\((\[.*?\])\)</script>", raw, re.S):
        payload = json.loads(chunk)
        if len(payload) > 1 and isinstance(payload[1], str) and "KONUT ABONELER" in payload[1]:
            html = payload[1]
            break
    if html is None:
        raise RuntimeError("İZSU: no RSC chunk with the tariff table")
    soup = BeautifulSoup(html, "lxml")
    m = re.search(r"(\d{2}\.\d{2}\.\d{4}) tarihinden itibaren faturalandırılmak üzere geçerli olan KDV hariç",
                  norm(soup.get_text(" ")))
    if not m:
        raise RuntimeError("İZSU: effective date / 'KDV hariç' note not found")
    effective = dmy(m.group(1))
    rows = []
    for tr in soup.find("table").find_all("tr"):
        cells = [norm(c.get_text(" ")) for c in tr.find_all("td")]
        if len(cells) == 6 and cells[0] == "1a" and cells[1] == "KONUT ABONELERİ":
            rows.append(water_row("İzmir", "İZSU", "konut", cells[2], *(tr_number(c) for c in cells[3:]),
                                  effective, url))
    if not 3 <= len(rows) <= 4:  # 4 tiers since 01.06.2026, 3 before (0~10, 11~20, 21~Üstü)
        raise RuntimeError(f"İZSU: expected 3-4 '1a KONUT ABONELERİ' tiers, got {len(rows)}")
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", nargs="+", choices=SOURCES, default=SOURCES, help="sources to fetch (default: all)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests to one host (jittered)")
    ap.add_argument("--output", default=None, help="write all rows to this CSV path instead of the store files (test runs)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    started = time.monotonic()

    rows, failed = [], []
    steps = {"iski": ("İSKİ", iski), "aski": ("ASKİ", aski), "izsu": ("İZSU", izsu)}
    for src in [s for s in SOURCES if s in args.source]:
        name, fetch = steps[src]
        try:
            got = fetch(Client(args.delay))
            log.info("%s: %d rows, effective %s", name, len(got), got[0]["effective_date"])
            rows += got
        except Exception as exc:
            log.error("%s failed: %s", name, exc)
            failed.append(name)

    if not rows:
        log.error("every source failed; no CSV written")
        sys.exit(1)
    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if args.output:
        write_csv(Path(args.output), rows, collected_at)
        paths = [args.output]
    else:
        paths = write_store_csvs(rows, date.today().isoformat(), collected_at)
    log.info("wrote %d rows to %s in %.1f s", len(rows), ", ".join(map(str, paths)), time.monotonic() - started)
    if failed:
        log.error("incomplete run, failed: %s", ", ".join(failed))
        sys.exit(1)


def write_csv(path: Path, rows: list[dict], collected_at: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "collected_at": collected_at})


def write_store_csvs(rows: list[dict], day: str, collected_at: str, keep_existing=False) -> list[Path]:
    """One ``Datas/04_Housing/<Store>/<store>_<day>.csv`` per store; ``keep_existing`` skips files already there."""
    by_store = {}
    for r in rows:
        by_store.setdefault(STORES[r["utility"]], []).append(r)
    paths = []
    for store, store_rows in by_store.items():
        path = DATAS_DIR / store / f"{store.lower()}_{day}.csv"
        if not (keep_existing and path.exists()):
            write_csv(path, store_rows, collected_at)
            paths.append(path)
    return paths


if __name__ == "__main__":
    main()
