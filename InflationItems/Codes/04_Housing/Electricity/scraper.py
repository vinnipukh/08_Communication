"""
EPDK residential electricity tariff scraper (TÜİK 04 Housing, item 0451001 Elektrik), requests-only.

Recon (2026-10-28): the page ``/Detay/Icerik/3-1327/elektrik-faturalarina-esas-tarife-tablolari``
loads its list with ``POST /Detay/GetFastAccessList`` (JSON body ``{"fId":"1327"}``), which answers
``{"Type": 1, "model": [...], ...}``, one entry per board decision (71 on 2026-10-28, newest first).
Each entry has ``Number`` (decision no), ``Date`` (decision date) and ``FastAccessDetail`` files; the
tariff table is the XLSX file (``IsFileType`` 2), fetched with ``GET /Detay/DownloadDocument?id=<ContentId>``.
The table has one sheet, prices in kuruş/kWh, taxes excluded. National tariff equalisation: one tariff
for the whole country, so there is no per-city work. The last-resort tariff (son kaynak tedarik) for
high-consumption households is not in this table (a note in the sheet refers to its own communiqué).

Rows written: every "Mesken" row of the table (OG çift terim, OG tek terim, AG tek terim; since
04.04.2026 AG mesken is split into "8 kWh/gün ve altı" and "8 kWh/gün üstü"), one row per time band
(tek zamanlı, gündüz, puant, gece) that has a price. ``total`` = energy + distribution charge;
the OG çift terim power charge (kr/kW/ay) is not added. A file is written every run even when the
decision is unchanged, to keep the time series dense.

Output: InflationItems/Datas/04_Housing/EPDK/epdk_YYYY-MM-DD.csv (upstream layout: one CSV per store and day)
Columns: product_name, price (total in TL/kWh), category_number (4), sub_category_number (0451001),
then tariff_group, voltage, time_band, energy_charge, distribution_charge, total (TL/kWh, converted from
EPDK's kuruş/kWh), unit (TL/kWh),
vat_included, effective_date, decision_no, source_url, collected_at.

The parser reads the sheet layout in use since 04.04.2026 (headers "Tek Zamanlı Enerji Bedeli",
"Gündüz/Puant/Gece", "Dağıtım Bedeli"; tariff class in the column left of "Abone / Kullanıcı Grubu") and,
for backfill.py, the layout of 01.07.2024 and 05.04.2025 ("Perakende ... Enerji Bedeli" headers, voltage
and term as heading rows; ``parse_table_2024()``). Any other layout stops the run with an error and no CSV.

Examples:
  python scraper.py                      # newest tariff table
"""

import argparse
import csv
import io
import logging
import random
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

import openpyxl
from curl_cffi import requests

BASE = "https://www.epdk.gov.tr"
PAGE_URL = f"{BASE}/Detay/Icerik/3-1327/elektrik-faturalarina-esas-tarife-tablolari"
LIST_URL = f"{BASE}/Detay/GetFastAccessList"
DOWNLOAD_URL = f"{BASE}/Detay/DownloadDocument?id="
FAST_ACCESS_ID = "1327"
BACKOFF = [2, 5, 10]  # seconds waited after each failed request, then give up

REPO_ROOT = Path(__file__).resolve().parents[4]
STORE = "EPDK"
DATA_DIR = REPO_ROOT / "InflationItems" / "Datas" / "04_Housing" / STORE
BACKFILL_DIR = REPO_ROOT / "logs" / "backfill"  # version histories; Datas holds only one CSV per store and day

CATEGORY_NUMBER = 4
SUB_CATEGORY_NUMBER = "0451001"  # TÜİK item "Elektrik"
COLUMNS = [
    "product_name", "price", "category_number", "sub_category_number",  # shared first four
    "tariff_group", "voltage", "time_band", "energy_charge", "distribution_charge", "total", "unit",
    "vat_included", "effective_date", "decision_no", "source_url", "collected_at",
]
TR_MONTHS = {m: i for i, m in enumerate(
    ["ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık"], 1)}

log = logging.getLogger("electricity")


class Client:
    def __init__(self, delay: float):
        self.delay = delay
        self._last = 0.0
        self.session = requests.Session(impersonate="chrome")
        # page first, like a normal visit (also sets the F5 "TS" cookies)
        self.request("GET", PAGE_URL)

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


def decisions(client: Client) -> list[dict]:
    resp = client.request("POST", LIST_URL, json={"fId": FAST_ACCESS_ID})
    data = resp.json()
    entries = data.get("model") if isinstance(data, dict) else data
    if not entries:
        raise RuntimeError(f"tariff list is empty or changed shape: {str(data)[:200]}")
    return entries


def table_file(entry: dict) -> dict:
    """The XLSX tariff table among a decision's files (the other one is the decision PDF)."""
    files = entry.get("FastAccessDetail") or []
    tables = [f for f in files if f.get("IsFileType") == 2] or [f for f in files if "tablo" in f.get("Title", "").lower()]
    if not tables:
        raise RuntimeError(f"decision {entry.get('Number')} has no tariff table file: {[f.get('Title') for f in files]}")
    return tables[0]


def effective_date(sheet_title: str, entry: dict) -> str:
    """'4 Nisan 2026 Tarihinden İtibaren ...' in the sheet, else '4/4/2026' in the list title."""
    m = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", sheet_title or "")
    if m and m.group(2).lower().replace("I", "ı") in TR_MONTHS:
        return date(int(m.group(3)), TR_MONTHS[m.group(2).lower().replace("I", "ı")], int(m.group(1))).isoformat()
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", entry.get("Title", ""))
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    log.warning("no effective date found; using the Resmî Gazete date %s", entry.get("RgDate"))
    d, mo, y = entry["RgDate"].split(".")
    return f"{y}-{mo}-{d}"


def norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def parse_table(content: bytes) -> tuple[str, list[dict]]:
    """Mesken rows of the tariff sheet as dicts of kuruş/kWh charges per time band."""
    ws = openpyxl.load_workbook(io.BytesIO(content), data_only=True).worksheets[0]
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    title = next((norm(v) for r in rows[:4] for v in r if v and "Tarife" in str(v)), "")
    if any(norm(v).startswith("Perakende Tek Zamanlı") for r in rows[:8] for v in r):
        return title, parse_table_2024(rows)
    # header cells -> column index (header text spans rows 3-5, merged)
    cols = {}
    for r in rows[:8]:
        for i, v in enumerate(r):
            t = norm(v).lower()
            if t.startswith("tek zamanlı enerji"):
                cols["tek zamanlı"] = i
            elif t in ("gündüz", "puant", "gece"):
                cols[t] = i
            elif t.startswith("dağıtım bedeli"):
                cols["dağıtım"] = i
            elif t.startswith("abone"):
                cols["group"] = i
    missing = {"tek zamanlı", "gündüz", "puant", "gece", "dağıtım", "group"} - cols.keys()
    if missing:
        raise RuntimeError(f"tariff sheet layout changed, missing headers: {sorted(missing)}")
    g = cols["group"]
    out, voltage = [], ""
    for r in rows:
        if g >= 1 and r[g - 1]:  # tariff class column (merged, so only its first row has a value)
            voltage = norm(r[g - 1])
        group = norm(r[g])
        if not group.lower().startswith("mesken"):
            continue
        dist = r[cols["dağıtım"]]
        for band in ("tek zamanlı", "gündüz", "puant", "gece"):
            energy = r[cols[band]]
            if isinstance(energy, (int, float)) and isinstance(dist, (int, float)):
                out.append({"tariff_group": group, "voltage": voltage, "time_band": band,
                            "energy_charge": round(energy, 4), "distribution_charge": round(dist, 4),
                            "total": round(energy + dist, 4)})
    if not any(o["voltage"].startswith("AG") and o["time_band"] == "tek zamanlı" for o in out):
        raise RuntimeError("no AG single-time residential row in the tariff sheet")
    return title, out


def parse_table_2024(rows: list[list]) -> list[dict]:
    """Mesken rows of the layout used up to 05.04.2025 (decisions 12719, 13426): one header row per user type
    ("Perakende Tek Zamanlı Enerji Bedeli", ..., "Dağıtım Bedeli", then the same as totals), and the voltage and
    term written as heading rows ("Orta Gerilim", "Çift Terimli") in the group column."""
    header = next((r for r in rows if any(norm(v).startswith("Dağıtım Sistemi Kullanıcıları") for v in r)
                   and any(norm(v).startswith("Perakende Tek Zamanlı") for v in r)), None)
    if header is None:
        raise RuntimeError("2024 tariff sheet layout: 'Dağıtım Sistemi Kullanıcıları' header row not found")
    cols = {}
    for i, v in enumerate(header):
        t = norm(v).lower()
        for band in ("tek zamanlı", "gündüz", "puant", "gece"):
            if t == f"perakende {band} enerji bedeli":
                cols.setdefault(band, i)
        if t == "dağıtım bedeli":
            cols.setdefault("dağıtım", i)
    if len(cols) != 5:
        raise RuntimeError(f"2024 tariff sheet layout changed, found columns {sorted(cols)}")
    g = cols["tek zamanlı"] - 1  # group / heading column, left of the first price column
    out, level, term = [], "", ""
    for r in rows[rows.index(header) + 1:]:
        label = norm(r[g])
        if label in ("Orta Gerilim", "Alçak Gerilim"):
            level, term = {"Orta Gerilim": "OG", "Alçak Gerilim": "AG"}[label], ""
        elif label in ("Çift Terimli", "Tek Terimli"):
            term = label[:-2]  # "Çift Terim" / "Tek Terim", as in the newer sheet
        elif label.lower().startswith("mesken") and level and term:
            dist = r[cols["dağıtım"]]
            for band in ("tek zamanlı", "gündüz", "puant", "gece"):
                energy = r[cols[band]]
                if isinstance(energy, (int, float)) and isinstance(dist, (int, float)):
                    out.append({"tariff_group": label, "voltage": f"{level} {term}", "time_band": band,
                                "energy_charge": round(energy, 4), "distribution_charge": round(dist, 4),
                                "total": round(energy + dist, 4)})
    if not any(o["voltage"] == "AG Tek Terim" and o["time_band"] == "tek zamanlı" for o in out):
        raise RuntimeError("no AG single-time residential row in the 2024 tariff sheet")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (jittered)")
    ap.add_argument("--output", default=None, help="write this CSV path instead of the store's day file (test runs)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    started = time.monotonic()

    client = Client(args.delay)
    entries = decisions(client)
    log.info("tariff list: %d decisions, newest %s (%s)", len(entries), entries[0].get("Number"), entries[0].get("Date"))
    entry = max(entries, key=lambda e: int(re.sub(r"\D", "", e.get("DateValue") or "") or 0))
    f = table_file(entry)
    url = DOWNLOAD_URL + quote(f["ContentId"], safe="")
    content = client.request("GET", url).content
    if not content.startswith(b"PK"):
        raise RuntimeError(f"{url} did not return an XLSX file ({content[:60]!r})")
    title, tariffs = parse_table(content)
    eff = effective_date(title, entry)
    log.info("decision %s, effective %s: %d residential rows (%s)", entry.get("Number"), eff, len(tariffs), title)

    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    csv_path = Path(args.output) if args.output else day_path(date.today().isoformat())
    write_csv(csv_path, csv_rows(tariffs, eff, entry, url), collected_at)
    log.info("wrote %d rows to %s in %.1f s", len(tariffs), csv_path, time.monotonic() - started)


def day_path(day: str) -> Path:
    return DATA_DIR / f"{STORE.lower()}_{day}.csv"


def write_csv(path: Path, rows: list[dict], collected_at: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "collected_at": collected_at})


def csv_rows(tariffs: list[dict], eff: str, entry: dict, url: str) -> list[dict]:
    """Output rows; EPDK's kuruş/kWh charges are written in TL/kWh, the unit of ``price``."""
    return [{
        "product_name": f"Elektrik {t['voltage']} {t['tariff_group']} - {t['time_band']}",
        "price": round(t["total"] / 100, 6), "category_number": CATEGORY_NUMBER,
        "sub_category_number": SUB_CATEGORY_NUMBER, **t,
        **{k: round(t[k] / 100, 6) for k in ("energy_charge", "distribution_charge", "total")},
        "unit": "TL/kWh", "vat_included": "false",
        "effective_date": eff, "decision_no": entry.get("Number"), "source_url": url,
    } for t in tariffs]


if __name__ == "__main__":
    main()
