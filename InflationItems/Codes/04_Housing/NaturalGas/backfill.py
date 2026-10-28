"""
One-off backfill of the household natural gas price (TÜİK 0452101) from a start date to today, one row per tier
and price version (valid-from date). The version already in force on the start date is included.

Sources (checked 2026-10-28):
- İGDAŞ: the price API answers past months (``{"AYYIL": "MMYYYY"}``); a month with a mid-month change lists
  each tier twice with different ``ABDATUM``. Before 04.04.2026 KONUT and KONUT KADEME-2 have the same price.
- Başkentgaz: the monthly PDF list (``menus/31/sections``) goes back to 2018; split months have one PDF per
  part ("4.Gün ve Öncesi", "5.Gün ve Sonrası", "2.Gün İçin Geçerli"). Before 04.04.2026 the household row
  has one price, written as Kademe-1. ÖTV was 0.1187 TL/Sm³ in 2025.
- İzmirgaz: the archive fragments ``tarifeler_arsiv_konut.php`` (TL/m³) and ``tarifeler_arsiv_konut_kwh.php``
  (TL/kWh) list every monthly version back to 2021, annual bands K1..K5; K1 (the household band) is written as
  Kademe-1. Kademe-2 (since 04.04.2026) has no archive (its "Arşiv" link points to the şehit ve gazi archive),
  so İzmir Kademe-2 starts with the daily scraper.
- Connection fees (0452102, EPDK national caps, VAT excluded, written to the İzmirgaz files like the daily run):
  the 2026 caps from İzmirgaz's fee pages (valid from 2026-01-01). No site keeps the 2025 caps and the Wayback
  Machine has no copy, so the three connection caps of 2025 (effective 01.01.2025, Bloomberg HT 31.12.2024 and
  YatırımX give the same figures) are transcribed in ``fees_transcribed.csv`` next to this script. The 2025
  deposit (güvence) caps were found in no second source and are not written.

Output: logs/backfill/natural_gas_<start>_<today>.csv (one row per tier and version, gitignored), columns as in
scraper.py. Then one Datas/04_Housing/<Store>/<store>_YYYY-MM-DD.csv per store (IGDAS, Baskentgaz, Izmirgaz) and day from
<start> to yesterday, like the daily scraper's files, holding the version in force that day (``valid_from`` shows
which; ``collected_at`` is the backfill run time). Existing day files
are never overwritten.
``--no-daily`` skips the day files.

Examples:
  python backfill.py                       # from 2025-01-01
  python backfill.py --start 2026-01-01 --source igdas
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone

import csv
import re
from pathlib import Path

from scraper import (BACKFILL_DIR, BASKENT_API, BASKENT_PRICE_MENU, CATEGORY_NUMBER, FEE_ITEM, IZMIRGAZ, REPO_ROOT,
                     STORES, Client, baskent_month, baskent_pdf, gas_row, igdas_month, izmirgaz_client,
                     izmirgaz_fees, norm, write_csv, write_store_csvs)

SOURCES = ["igdas", "baskentgaz", "izmirgaz", "fees"]
FEES_TRANSCRIBED = Path(__file__).resolve().parent / "fees_transcribed.csv"
IZMIRGAZ_ARCHIVE = f"{IZMIRGAZ}/pages/musteri_hizmetleri/tarifeler_arsiv_konut{{unit}}.php"  # "" = TL/m³, "_kwh" = TL/kWh

log = logging.getLogger("natural_gas_backfill")


def in_window(versions: dict[str, list[dict]], start: str) -> list[dict]:
    """Rows of every version from ``start`` on, plus the newest version before it (in force on ``start``)."""
    before = [d for d in versions if d < start]
    keep = sorted(d for d in versions if d >= start) + ([max(before)] if before else [])
    return [r for d in sorted(keep) for r in versions[d]]


def months(first: date, last: date):
    y, m = first.year, first.month
    while (y, m) <= (last.year, last.month):
        yield date(y, m, 1)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def igdas_history(client: Client, start: str) -> list[dict]:
    versions = {}
    first = date.fromisoformat(start)
    first = date(first.year - 1, 12, 1) if first.month == 1 else date(first.year, first.month - 1, 1)
    for month in months(first, date.today()):
        for row in igdas_month(client, month):
            if row["valid_from"] <= date.today().isoformat():
                versions.setdefault(row["valid_from"], {})[row["tier"]] = row
    return in_window({d: list(rows.values()) for d, rows in versions.items()}, start)


def baskentgaz_history(client: Client, start: str) -> list[dict]:
    sections = client.request("GET", BASKENT_API.format(menu=BASKENT_PRICE_MENU)).json()["sections"]
    now = datetime.now()
    live = {}  # valid-from date -> newest section (highest rowNumber) for it
    for s in sections:
        valid_from = baskent_month(s.get("title", ""))
        if (s.get("isActive") and not s.get("isDeleted") and valid_from and (s.get("imageUrl") or "").endswith(".pdf")
                and not (s.get("startDate") and datetime.fromisoformat(s["startDate"][:19]) > now)):
            key = valid_from.isoformat()
            if key not in live or s.get("rowNumber", 0) > live[key].get("rowNumber", 0):
                live[key] = s
    wanted = [d for d in live if d >= start] + [max((d for d in live if d < start), default=None)]
    versions = {}
    for d in sorted(x for x in wanted if x):
        versions[d] = baskent_pdf(client, live[d])
    return in_window(versions, start)


def izmirgaz_archive(client: Client, unit: str) -> dict[str, tuple[str, list[str]]]:
    """valid-from date -> (annual band, cells) of the K1 row. The fragment's rows often miss their ``<tr>``,
    so the ``<td>`` cells are read in order, six per row (band, date, gas, ÖTV, SKB, sales price)."""
    html = client.request("GET", IZMIRGAZ_ARCHIVE.format(unit=unit)).content.decode("utf-8")
    cells = [norm(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", html, re.S)]
    out = {}
    for i in range(0, len(cells) - 5):
        band, when = cells[i], cells[i + 1]
        if band.endswith("(K1)") and re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", when):
            d, m, y = when.split(".")
            out.setdefault(f"{y}-{m}-{d}", (re.sub(r"\s*\(K1\)", "", band), cells[i + 2:i + 6]))
    if not out:
        raise RuntimeError(f"İzmirgaz archive{unit}: no K1 rows found")
    return out


def izmirgaz_history(client: Client, start: str) -> list[dict]:
    client = izmirgaz_client(client.delay)
    m3, kwh = izmirgaz_archive(client, ""), izmirgaz_archive(client, "_kwh")
    versions = {}
    for d, (band, (gas, otv, skb, price)) in m3.items():
        if d not in kwh:  # price is TL/kWh; a version without it cannot be written
            log.warning("İzmirgaz archive: %s has no TL/kWh price, skipped", d)
            continue
        url = IZMIRGAZ_ARCHIVE.format(unit="")
        versions[d] = [gas_row("İzmir", "İzmirgaz", f"Konut Kademe-1 ({band} m³/yıl)", float(price),
                               float(kwh[d][1][3]), f"gas={gas};ötv={otv};skb={skb}", d, url)]
    return in_window(versions, start)


def fees_history(client: Client, start: str) -> list[dict]:
    versions = {}
    for r in izmirgaz_fees(izmirgaz_client(client.delay)):
        versions.setdefault(r["valid_from"], []).append(r)
    with FEES_TRANSCRIBED.open(encoding="utf-8", newline="") as fh:
        for t in csv.DictReader(fh):
            versions.setdefault(t["valid_from"], []).append({
                "product_name": f"Doğal gaz {t['label']}", "price": float(t["price"]),
                "category_number": CATEGORY_NUMBER, "sub_category_number": FEE_ITEM, "province": "Türkiye",
                "distributor": "EPDK üst sınır (İzmirgaz)", "tier": t["label"], "price_per_m3": "",
                "price_per_kwh": "", "unit": "TL", "vat_included": "false", "components": "",
                "valid_from": t["valid_from"], "source_url": t["source_url"]})
    return in_window(versions, start)


def write_daily(rows: list[dict], start: str, collected_at: str) -> tuple[int, int]:
    """One ``<store>_YYYY-MM-DD.csv`` per store and day from ``start`` to yesterday with the version in force that
    day. Existing day files (real daily runs) are kept. Returns (written, skipped) file counts."""
    versions = {}  # (province, distributor) -> valid-from date -> rows
    for r in rows:
        versions.setdefault((r["province"], r["distributor"]), {}).setdefault(r["valid_from"], []).append(r)
    written = skipped = 0
    day, end = date.fromisoformat(start), date.today() - timedelta(days=1)
    while day <= end:
        out = []
        for by_date in versions.values():
            in_force = max((d for d in by_date if d <= day.isoformat()), default=None)
            out += by_date[in_force] if in_force else []
        stores = {STORES[r["distributor"]] for r in out}
        new = write_store_csvs(out, day.isoformat(), collected_at, keep_existing=True)
        written += len(new)
        skipped += len(stores) - len(new)
        day += timedelta(days=1)
    return written, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2025-01-01", help="first date to cover, YYYY-MM-DD (default: 2025-01-01)")
    ap.add_argument("--source", nargs="+", choices=SOURCES, default=SOURCES, help="sources to fetch (default: all)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests to one host (jittered)")
    ap.add_argument("--no-daily", action="store_true", help="write only the versions file, no per-day files")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    start = date.fromisoformat(args.start).isoformat()
    started = time.monotonic()

    steps = {"igdas": ("İGDAŞ", igdas_history), "baskentgaz": ("Başkentgaz", baskentgaz_history),
             "izmirgaz": ("İzmirgaz", izmirgaz_history), "fees": ("fees", fees_history)}
    rows, failed = [], []
    for src in [s for s in SOURCES if s in args.source]:
        name, fetch = steps[src]
        try:
            got = fetch(Client(args.delay), start)
            dates = sorted({r["valid_from"] for r in got})
            log.info("%s: %d rows, %d versions: %s", name, len(got), len(dates), ", ".join(dates))
            rows += got
        except Exception as exc:
            log.error("%s failed: %s", name, exc)
            failed.append(name)

    if not rows:
        log.error("every source failed; no CSV written")
        sys.exit(1)
    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    csv_path = BACKFILL_DIR / f"natural_gas_{start}_{date.today().isoformat()}.csv"
    write_csv(csv_path, rows, collected_at)
    log.info("wrote %d rows to %s in %.1f s", len(rows), csv_path.relative_to(REPO_ROOT), time.monotonic() - started)
    if args.no_daily:
        pass
    elif failed or set(args.source) != set(SOURCES):  # day files are never rewritten, so only from complete runs
        log.warning("daily files not written: needs every source to succeed")
    else:
        written, skipped = write_daily(rows, start, collected_at)
        log.info("daily files: %d written, %d already existed (kept)", written, skipped)
    if failed:
        log.error("incomplete run, failed: %s", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
