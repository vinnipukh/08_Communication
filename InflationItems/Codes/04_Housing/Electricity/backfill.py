"""
One-off backfill of the EPDK residential electricity tariff (TÜİK 0451001) from a start date to today: every
tariff decision that took effect in the window, plus the one already in force on the start date.

The tariff list (``POST /Detay/GetFastAccessList``) keeps every decision back to 2022 with its XLSX table.
Tables up to 05.04.2025 use an older layout, read by ``parse_table_2024()`` in scraper.py. Between 2025-01-01
and 2026-10-28 there were two decisions: 13426 (05.04.2025) and 14461 (04.04.2026); 12719 (01.07.2024) was in
force on 2025-01-01.

Output: logs/backfill/epdk_<start>_<today>.csv (one row per tariff row and decision, gitignored), columns as
in scraper.py. Then one Datas/04_Housing/EPDK/epdk_YYYY-MM-DD.csv per day from <start> to yesterday, like the daily
scraper's files, holding the decision in force that day (``effective_date`` / ``decision_no`` show which;
``collected_at`` is the backfill run time). Existing day files are never overwritten. ``--no-daily`` skips them.

Examples:
  python backfill.py                       # from 2025-01-01
  python backfill.py --start 2024-01-01
"""

import argparse
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from scraper import (BACKFILL_DIR, DOWNLOAD_URL, REPO_ROOT, Client, csv_rows, day_path, decisions, effective_date,
                     parse_table, table_file, write_csv)

log = logging.getLogger("electricity_backfill")


def write_daily(rows: list[dict], start: str, collected_at: str) -> tuple[int, int]:
    """One ``epdk_YYYY-MM-DD.csv`` per day from ``start`` to yesterday with the decision in force that day.
    Existing day files (real daily runs) are kept. Returns (written, skipped)."""
    by_date = {}  # effective date -> rows of that decision
    for r in rows:
        by_date.setdefault(r["effective_date"], []).append(r)
    written = skipped = 0
    day, end = date.fromisoformat(start), date.today() - timedelta(days=1)
    while day <= end:
        path = day_path(day.isoformat())
        in_force = max((d for d in by_date if d <= day.isoformat()), default=None)
        if path.exists():
            skipped += 1
        elif in_force:
            write_csv(path, by_date[in_force], collected_at)
            written += 1
        day += timedelta(days=1)
    return written, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2025-01-01", help="first date to cover, YYYY-MM-DD (default: 2025-01-01)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (jittered)")
    ap.add_argument("--no-daily", action="store_true", help="write only the versions file, no per-day files")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    start = date.fromisoformat(args.start).isoformat()
    started = time.monotonic()

    client = Client(args.delay)
    by_date = {}  # effective date from the list title ("5/4/2025’ten itibaren ...") -> decision
    for entry in decisions(client):
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", entry.get("Title", ""))
        if m:  # some entries before 2022 have no date in the title; they are outside any useful window
            by_date.setdefault(date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat(), entry)
    wanted = sorted(d for d in by_date if start <= d <= date.today().isoformat())
    before = [d for d in by_date if d < start]
    wanted = ([max(before)] if before else []) + wanted

    rows = []
    for d in wanted:
        entry = by_date[d]
        url = DOWNLOAD_URL + quote(table_file(entry)["ContentId"], safe="")
        content = client.request("GET", url).content
        if not content.startswith(b"PK"):
            raise RuntimeError(f"{url} did not return an XLSX file ({content[:60]!r})")
        title, tariffs = parse_table(content)
        eff = effective_date(title, entry)
        if eff != d:
            log.warning("decision %s: sheet says %s, list title says %s; using the sheet", entry.get("Number"), eff, d)
        log.info("decision %s, effective %s: %d residential rows", entry.get("Number"), eff, len(tariffs))
        rows += csv_rows(tariffs, eff, entry, url)

    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    csv_path = BACKFILL_DIR / f"epdk_{start}_{date.today().isoformat()}.csv"
    write_csv(csv_path, rows, collected_at)
    log.info("wrote %d rows to %s in %.1f s", len(rows), csv_path.relative_to(REPO_ROOT), time.monotonic() - started)
    if not args.no_daily:
        written, skipped = write_daily(rows, start, collected_at)
        log.info("daily files: %d written, %d already existed (kept)", written, skipped)


if __name__ == "__main__":
    main()
