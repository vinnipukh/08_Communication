"""
One-off backfill of firewood prices (TÜİK 0454201) from Wayback Machine copies of the sellers' pages.

None of the sellers keeps a price history. The Wayback Machine (``web.archive.org/cdx``, checked 2026-10-28) has
copies of these pages; each copy is parsed with the same function as the daily scraper:

| --store     | Page                                                         | Copies since 2025 |
|-------------|--------------------------------------------------------------|-------------------|
| komurdeposu | komurdeposu.com.tr/odun-fiyatlari/                           | 3                 |
| odunmarket  | odunmarket.com/yuvarlak-somine-odunu, /yarma-somine-odunu    | 2 + 2             |
| tetik       | tetikyakacak.com/izmir-komur/sobalik-ve-sominelik-mese-odun/ | 6                 |

Ulusoy, Yak Gelsin and Odunal have no copies.

Output: one Datas/04_Housing/<Store>/<store>_YYYY-MM-DD.csv per store and **snapshot day** (no forward fill: a
copy shows the price on that day only), ``source_url`` = the Wayback copy, ``collected_at`` = the copy's
timestamp. Existing day files are never overwritten.

Examples:
  python backfill.py                       # copies from 2025-01-01 on
  python backfill.py --store tetik --start 2024-01-01
"""

import argparse
import logging
import sys
from datetime import date, datetime, timezone

from scraper import (DATA_ROOT, KOMURDEPOSU_URL, ODUNMARKET, Client, day_path, komurdeposu_rows, odunmarket_rows,
                     tetik_rows, write_csv)

CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK_RAW = "https://web.archive.org/web/{ts}id_/{url}"
PAGES = {  # store -> (live page URLs, parser(html, url))
    "komurdeposu": ([KOMURDEPOSU_URL], komurdeposu_rows),
    "odunmarket": ([f"{ODUNMARKET}/yuvarlak-somine-odunu", f"{ODUNMARKET}/yarma-somine-odunu"], odunmarket_rows),
    "tetik": (["https://tetikyakacak.com/izmir-komur/sobalik-ve-sominelik-mese-odun/"], tetik_rows),
}

log = logging.getLogger("firewood_backfill")


def snapshots(client: Client, url: str, start: str) -> list[str]:
    params = {"url": url.split("://", 1)[1], "from": start.replace("-", ""), "collapse": "digest",
              "filter": "statuscode:200", "fl": "timestamp"}
    return client.text(CDX, params).split()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", nargs="+", choices=list(PAGES), default=list(PAGES))
    ap.add_argument("--start", default="2025-01-01", help="first snapshot day (YYYY-MM-DD)")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between requests to archive.org (jittered)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    client = Client(args.delay)
    today = date.today().isoformat()

    for store in args.store:
        urls, parse = PAGES[store]
        by_day: dict[str, tuple[str, list[dict]]] = {}  # day -> (newest timestamp, rows)
        for url in urls:
            for ts in snapshots(client, url, args.start):
                copy = WAYBACK_RAW.format(ts=ts, url=url)
                try:
                    rows = [{**r, "source_url": copy} for r in parse(client.text(copy), url)]
                except Exception as exc:  # a copy without the usual page data
                    log.warning("%s: %s", copy, exc)
                    continue
                day = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
                log.info("%s %s: %d rows", store, copy, len(rows))
                prev_ts, prev_rows = by_day.get(day, ("", []))
                by_day[day] = (max(prev_ts, ts), prev_rows + rows)
        written = 0
        for day, (ts, rows) in sorted(by_day.items()):
            path = day_path(store, day)
            if day >= today or path.exists() or not rows:
                continue
            stamp = datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).isoformat()
            write_csv(path, rows, stamp)
            written += 1
            log.info("wrote %s (%d rows)", path.relative_to(DATA_ROOT), len(rows))
        log.info("%s: %d snapshot days, %d day files written", store, len(by_day), written)


if __name__ == "__main__":
    sys.exit(main())
