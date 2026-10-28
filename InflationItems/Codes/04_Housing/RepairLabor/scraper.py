"""
Home repair labour price scraper (TÜİK 04 Housing, item 0432015 Ev bakım ve onarım işçilik ücreti), requests-only.
Source: Armut.com city price pages ("<city> <service> Fiyatları") for a curated list of home repair services
(``services.json`` next to this file). İstanbul, Ankara and İzmir by default; ``--provinces all`` takes every
province the sitemap lists (~1,600 pages, ~40 min).

Recon (2026-10-28):
- ``https://armut.com/sitemap.xml`` (index) lists ``sitemap/price-arealevel1-<n>.xml``; ``-1`` holds ~45k city
  price pages ``https://armut.com/fiyatlari/{city}-{service-slug}_{serviceId}_{plate}``, e.g.
  ``https://armut.com/fiyatlari/ankara-su-tesisatcisi_193_6``. Not every service has a page in every province.
- Each page is server-rendered Next.js; ``<script id="__NEXT_DATA__">`` → ``props.pageProps.data``:
  ``pricePageInfo`` {serviceId, areaLevel1Id, isAreaLevel1} and ``pricePageData`` with ``minPrice`` /
  ``maxPrice`` (the "Ortalama Fiyat" range shown on the page, e.g. 1.000 TL - 15.000 TL), ``quoteCount``,
  ``proCount``, ``ratingAvg``, ``ratingCount``, ``areaLevel1Name`` and ``monthlyPrices``: the last 12 complete
  months [{month "2026-09-01", avgPrice, minPrice, maxPrice, quoteCount}] of quotes in that city.
- CloudFront, HTTP 200 to curl_cffi, no challenge. robots.txt allows ``/fiyatlari/`` and the sitemaps.

``price`` = ``avgPrice`` of the newest month in ``monthlyPrices`` (mean of that month's quotes, TL); the
midpoint of ``minPrice``-``maxPrice`` when the page has no monthly data (``notes`` says which). Quote means are
noisy (single quotes of 500,000 TL occur), so the range, the month's min/max and quote counts are kept too.

Output: InflationItems/Datas/04_Housing/RepairLabor/YYYY-MM-DD.csv
Columns: product_name, price, category_number (4), sub_category_number (0432015), service, service_id, province,
plate, price_min, price_max, price_avg, avg_month, month_min, month_max, month_quote_count, quote_count,
pro_count, rating_avg, rating_count, notes, source_url, collected_at.

A page that fails is logged and skipped; the rest is written and the run exits with status 1. Nothing is written
when every page fails.

``--backfill`` also writes one CSV per past day covered by the pages' ``monthlyPrices`` (12 complete months,
e.g. 2025-10-01 .. 2026-09-30 on 2026-10-28): every day of a month gets that month's quote mean, with ``notes``
starting "backfill:" and the today-only fields (shown range, totals, rating) empty. Existing daily CSVs are kept.

Examples:
  python scraper.py                                   # 23 services x İstanbul, Ankara, İzmir (~70 requests)
  python scraper.py --backfill                        # same, plus the 12-month history as daily CSVs
  python scraper.py --provinces 6 --services 193 66   # bounded run
  python scraper.py --provinces all                   # every province in the sitemap
"""

import argparse
import calendar
import csv
import json
import logging
import random
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from curl_cffi import requests

SITEMAP_INDEX = "https://armut.com/sitemap.xml"
PAGE_RE = re.compile(r"^https://armut\.com/fiyatlari/[a-z0-9-]+_(\d+)_(\d+)$")
BACKOFF = [2, 5, 10]  # seconds waited after each failed request, then give up
DEFAULT_PROVINCES = [34, 6, 35]

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = REPO_ROOT / "InflationItems" / "Datas" / "04_Housing" / "RepairLabor"
SERVICES_FILE = Path(__file__).resolve().parent / "services.json"

CATEGORY_NUMBER = 4
REPAIR_ITEM = "0432015"  # TÜİK item "Ev bakım ve onarım işçilik ücreti"
COLUMNS = [
    "product_name", "price", "category_number", "sub_category_number",  # shared first four
    "service", "service_id", "province", "plate", "price_min", "price_max", "price_avg", "avg_month",
    "month_min", "month_max", "month_quote_count", "quote_count", "pro_count", "rating_avg", "rating_count",
    "notes", "source_url", "collected_at",
]

log = logging.getLogger("repair_labor")


class Client:
    def __init__(self, delay: float):
        self.delay = delay
        self._last = 0.0
        self.session = requests.Session(impersonate="chrome")

    def get(self, url: str, **kwargs):
        for attempt in range(1, len(BACKOFF) + 2):
            wait = self.delay * random.uniform(0.8, 1.4) - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self.session.get(url, timeout=60, **kwargs)
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


def page_urls(client: Client) -> dict[tuple[int, int], str]:
    """(serviceId, plate) -> city price page URL, from every price-arealevel1 sitemap."""
    index = re.findall(r"<loc>(.*?)</loc>", client.get(SITEMAP_INDEX).text)
    sitemaps = [u for u in index if re.search(r"/sitemap/price-arealevel1-\d+\.xml$", u)]
    if not sitemaps:
        raise RuntimeError("no price-arealevel1 sitemap in the sitemap index")
    urls = {}
    for sitemap in sitemaps:
        for url in re.findall(r"<loc>(.*?)</loc>", client.get(sitemap).text):
            m = PAGE_RE.match(url.strip())
            if m:
                urls[(int(m.group(1)), int(m.group(2)))] = url.strip()
    log.info("%d city price pages in %d sitemap(s)", len(urls), len(sitemaps))
    if not urls:
        raise RuntimeError("price sitemaps list no city page")
    return urls


def fetch_page(client: Client, url: str, service: dict, plate: int) -> tuple[list[dict], dict]:
    """One price page -> (the page's monthlyPrices sorted oldest first, today's row)."""
    raw = client.get(url).text
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw, re.S)
    if not m:
        raise RuntimeError("__NEXT_DATA__ not found")
    data = json.loads(m.group(1))["props"]["pageProps"]["data"]
    info, page = data["pricePageInfo"], data["pricePageData"]
    if (info.get("serviceId"), info.get("areaLevel1Id"), info.get("isAreaLevel1")) != (
            service["service_id"], plate, True):
        raise RuntimeError(f"page is for another service / area ({info})")
    lo, hi = page.get("minPrice"), page.get("maxPrice")
    months = sorted(page.get("monthlyPrices") or [], key=lambda x: x["month"])
    last = months[-1] if months else {}
    if last.get("avgPrice"):
        price, notes = round(last["avgPrice"], 2), f"price = mean of {last['month'][:7]} quotes"
    elif lo and hi:
        price, notes = (lo + hi) / 2, "price = midpoint of min-max (no monthly data)"
    else:
        raise RuntimeError("no price range and no monthly data")
    if price <= 0:
        raise RuntimeError(f"price {price} is not positive")
    province = page.get("areaLevel1Name") or str(plate)
    return months, {
        "product_name": f"{service['service']} {province}", "price": price, "category_number": CATEGORY_NUMBER,
        "sub_category_number": REPAIR_ITEM, "service": service["service"], "service_id": service["service_id"],
        "province": province, "plate": f"{plate:02d}", "price_min": lo, "price_max": hi,
        "price_avg": round(last["avgPrice"], 2) if last.get("avgPrice") else "",
        "avg_month": last.get("month", "")[:7], "month_min": last.get("minPrice", ""),
        "month_max": last.get("maxPrice", ""), "month_quote_count": last.get("quoteCount", ""),
        "quote_count": page.get("quoteCount", ""), "pro_count": page.get("proCount", ""),
        "rating_avg": page.get("ratingAvg", ""), "rating_count": page.get("ratingCount", ""), "notes": notes,
        "source_url": url,
    }


def history_rows(row: dict, months: list[dict]) -> dict[str, list[dict]]:
    """Spread the page's 12 monthly quote means over daily files: 'YYYY-MM-DD' -> rows (days before today only).
    Fields that only exist for today (shown range, totals, rating) stay empty."""
    today, by_day = date.today(), {}
    for m in months:
        if not m.get("avgPrice"):
            continue
        first = date.fromisoformat(m["month"][:10])
        hist = {**{k: "" for k in COLUMNS}, **{k: row[k] for k in (
            "product_name", "category_number", "sub_category_number", "service", "service_id", "province", "plate",
            "source_url")}}
        hist.update(price=round(m["avgPrice"], 2), price_avg=round(m["avgPrice"], 2), avg_month=m["month"][:7],
                    month_min=m.get("minPrice", ""), month_max=m.get("maxPrice", ""),
                    month_quote_count=m.get("quoteCount", ""),
                    notes=f"backfill: mean of {m['month'][:7]} quotes, same value for every day of the month")
        for day in range(1, calendar.monthrange(first.year, first.month)[1] + 1):
            d = first.replace(day=day)
            if d < today:
                by_day.setdefault(d.isoformat(), []).append(hist)
    return by_day


def write_csv(csv_path: Path, rows: list[dict], collected_at: str):
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "collected_at": collected_at})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provinces", nargs="+", default=[str(p) for p in DEFAULT_PROVINCES],
                    help="plate codes, e.g. 34 6 35 (default), or 'all' for every province in the sitemap")
    ap.add_argument("--services", nargs="+", type=int, default=None,
                    help="Armut service ids from services.json (default: all of them)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (jittered)")
    ap.add_argument("--output", default=None, help="CSV file name inside the data dir (default: YYYY-MM-DD.csv)")
    ap.add_argument("--backfill", action="store_true",
                    help="also write one CSV per past day from the pages' 12-month history (existing files are kept)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    started = time.monotonic()

    services = json.loads(SERVICES_FILE.read_text(encoding="utf-8"))
    if args.services:
        unknown = set(args.services) - {s["service_id"] for s in services}
        if unknown:
            ap.error(f"service ids not in services.json: {sorted(unknown)}")
        services = [s for s in services if s["service_id"] in args.services]

    client = Client(args.delay)
    urls = page_urls(client)
    if args.provinces == ["all"]:
        provinces = sorted({plate for _, plate in urls})
    else:
        provinces = [int(p) for p in args.provinces]

    rows, history, failures, missing = [], {}, 0, 0
    for plate in provinces:
        for service in services:
            url = urls.get((service["service_id"], plate))
            if url is None:
                log.warning("no page for %s in province %02d", service["service"], plate)
                missing += 1
                continue
            try:
                months, row = fetch_page(client, url, service, plate)
                rows.append(row)
                for day, day_rows in history_rows(row, months).items():
                    history.setdefault(day, []).extend(day_rows)
            except Exception as exc:
                log.error("%s failed: %s", url, exc)
                failures += 1
    log.info("%d rows, %d pages failed, %d service/province pairs without a page", len(rows), failures, missing)

    if not rows:
        log.error("every page failed; no CSV written")
        sys.exit(1)
    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = DATA_DIR / (args.output or f"{date.today().isoformat()}.csv")
    write_csv(csv_path, rows, collected_at)
    log.info("wrote %d rows to %s", len(rows), csv_path)
    if args.backfill:
        written = kept = 0
        for day, day_rows in sorted(history.items()):
            path = DATA_DIR / f"{day}.csv"
            if path.exists():  # never replace a real daily snapshot with backfilled values
                kept += 1
                continue
            write_csv(path, day_rows, collected_at)
            written += 1
        log.info("backfill: wrote %d daily CSVs (%s .. %s), kept %d existing", written,
                 min(history, default="-"), max(history, default="-"), kept)
    log.info("done in %.1f s", time.monotonic() - started)
    if failures:
        log.error("incomplete run: %d pages failed", failures)
        sys.exit(1)


if __name__ == "__main__":
    main()
