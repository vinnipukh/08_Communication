"""
One-off backfill of the municipal water tariff (TÜİK 0441101) from a start date to today, one row per tier and
tariff version (effective date). The version already in force on the start date is included.

Sources (checked 2026-10-28):
- İSKİ: the yearly monthly-tariff PDFs linked on the tariff page ("<year> Yılı"), one column per month.
- ASKİ: keeps no history (the PDF is overwritten in place), so old copies come from the Wayback Machine
  (``web.archive.org/cdx`` for ``aski.gov.tr/Yukle/Dosya/SuTarifesi.pdf``), plus the live PDF. Versions that
  were never archived are missing (2025 has none between 03.12.2024 and the December 2025 copy).
- İZSU: Wayback copies of the tariff page (2026 only), plus the live page. Older tariffs are images on İZSU's
  history list; their konut rows are transcribed by hand in
  ``izsu_transcribed.csv`` next to this script (source image URL per row, totals checked).

Output: logs/backfill/water_<start>_<today>.csv (one row per tier and version, gitignored), columns as in
scraper.py; ``source_url`` is the PDF, Wayback snapshot or image the row came from. Then one
Datas/04_Housing/<Store>/<store>_YYYY-MM-DD.csv per store (ISKI, ASKI, IZSU) and day from <start> to yesterday,
like the daily scraper's files, holding the version in force that day (``effective_date`` shows which; ``collected_at`` is the backfill run time). Existing day files
are never overwritten. ``--no-daily`` skips the day files.

Examples:
  python backfill.py                       # from 2025-01-01
  python backfill.py --start 2026-01-01 --source aski
"""

import argparse
import csv
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone

from pathlib import Path

from scraper import (ASKI_PDF, BACKFILL_DIR, IZSU_URL, REPO_ROOT, Client, aski, aski_parse, iski, iski_markup,
                     iski_pdf_links, iski_pdf_months, izsu, izsu_parse, water_row, write_csv, write_store_csvs)

WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx?url={url}&output=json&collapse=digest&from={year}"
WAYBACK_RAW = "https://web.archive.org/web/{ts}id_/{url}"
TRANSCRIBED = Path(__file__).resolve().parent / "izsu_transcribed.csv"
SOURCES = ["iski", "aski", "izsu"]

log = logging.getLogger("water_backfill")


def in_window(versions: dict[str, list[dict]], start: str) -> list[dict]:
    """Rows of every version from ``start`` on, plus the newest version before it (in force on ``start``)."""
    before = [d for d in versions if d < start]
    keep = sorted(d for d in versions if d >= start) + ([max(before)] if before else [])
    return [r for d in sorted(keep) for r in versions[d]]


def wayback_snapshots(client: Client, url: str, start: str) -> list[str]:
    """Wayback raw-content URLs of the distinct captures of ``url`` from the year before ``start`` on."""
    rows = client.get(WAYBACK_CDX.format(url=url, year=int(start[:4]) - 1)).json()
    return [WAYBACK_RAW.format(ts=r[1], url=r[2]) for r in rows[1:] if r[4] == "200"]


def iski_history(client: Client, start: str) -> list[dict]:
    links = iski_pdf_links(iski_markup(client))
    versions = {}
    for year in range(int(start[:4]), date.today().year + 1):
        if year not in links:
            log.warning("İSKİ: no %d PDF link", year)
            continue
        for effective, tiers in iski_pdf_months(client, links[year]):
            versions[effective] = [water_row("İstanbul", "İSKİ", "konut", *t, effective, links[year]) for t in tiers]
    if not versions or min(versions) > start:  # the version in force on ``start`` is in last year's PDF
        try:  # older PDFs have other layouts (2024: tier lines split differently)
            prev = int(start[:4]) - 1
            last = iski_pdf_months(client, links[prev])[-1]
            versions[last[0]] = [water_row("İstanbul", "İSKİ", "konut", *t, last[0], links[prev]) for t in last[1]]
        except Exception as exc:
            log.warning("İSKİ: no version in force on %s (%s)", start, exc)
    current = iski(client)  # the page itself, in case the PDF lags it
    versions.setdefault(current[0]["effective_date"], current)
    return in_window(versions, start)


def aski_history(client: Client, wayback: Client, start: str) -> list[dict]:
    versions = {}
    for snap in wayback_snapshots(wayback, ASKI_PDF.split("//", 1)[1], start):
        try:
            rows = aski_parse(wayback.get(snap).content, snap)
        except Exception as exc:
            log.warning("ASKİ %s: %s", snap, exc)
            continue
        versions.setdefault(rows[0]["effective_date"], rows)
    current = aski(client)
    versions[current[0]["effective_date"]] = current  # prefer the live copy's URL for the current version
    return in_window(versions, start)


def izsu_history(client: Client, wayback: Client, start: str) -> list[dict]:
    versions = {}
    with TRANSCRIBED.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            versions.setdefault(r["effective_date"], []).append(water_row(
                "İzmir", "İZSU", "konut", r["tier"], float(r["water_price"]), float(r["wastewater_price"]),
                float(r["total"]), r["effective_date"], r["source_url"]))
    for snap in wayback_snapshots(wayback, IZSU_URL.split("//", 1)[1], start):
        try:
            rows = izsu_parse(wayback.get(snap).content.decode("utf-8"), snap)
        except Exception as exc:
            log.warning("İZSU %s: %s", snap, exc)
            continue
        versions.setdefault(rows[0]["effective_date"], rows)
    current = izsu(client)
    versions[current[0]["effective_date"]] = current
    return in_window(versions, start)


def write_daily(rows: list[dict], start: str, collected_at: str) -> tuple[int, int]:
    """One ``<store>_YYYY-MM-DD.csv`` per store and day from ``start`` to yesterday with the version in force that
    day. Existing day files (real daily runs) are kept. Returns (written, skipped) file counts."""
    versions = {}  # (province, utility) -> effective date -> rows
    for r in rows:
        versions.setdefault((r["province"], r["utility"]), {}).setdefault(r["effective_date"], []).append(r)
    written = skipped = 0
    day, end = date.fromisoformat(start), date.today() - timedelta(days=1)
    while day <= end:
        out = []
        for by_date in versions.values():
            in_force = max((d for d in by_date if d <= day.isoformat()), default=None)
            out += by_date[in_force] if in_force else []
        stores = {r["utility"] for r in out}
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

    wayback = Client(max(args.delay, 2.0))  # archive.org asks for gentle crawling
    steps = {"iski": ("İSKİ", lambda: iski_history(Client(args.delay), start)),
             "aski": ("ASKİ", lambda: aski_history(Client(args.delay), wayback, start)),
             "izsu": ("İZSU", lambda: izsu_history(Client(args.delay), wayback, start))}
    rows, failed = [], []
    for src in [s for s in SOURCES if s in args.source]:
        name, fetch = steps[src]
        try:
            got = fetch()
            dates = sorted({r["effective_date"] for r in got})
            log.info("%s: %d rows, %d versions: %s", name, len(got), len(dates), ", ".join(dates))
            rows += got
        except Exception as exc:
            log.error("%s failed: %s", name, exc)
            failed.append(name)

    if not rows:
        log.error("every source failed; no CSV written")
        sys.exit(1)
    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    csv_path = BACKFILL_DIR / f"water_{start}_{date.today().isoformat()}.csv"
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
