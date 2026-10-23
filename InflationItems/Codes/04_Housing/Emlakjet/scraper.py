"""
Emlakjet residential rental scraper (TÜİK 04 Housing), requests-only (no browser).

Recon (2026-10-23): ``/kiralik-konut`` listing grids are server-rendered, 30
``article[data-listing-id]`` cards per page, and ``curl_cffi`` with Chrome TLS
impersonation gets them without a browser. Each geographic route is capped at 50
pages (1,500 cards), so a scope above the cap is split: country -> provinces ->
districts -> neighbourhoods (links of the scope page itself). Only ``?sayfa=`` is
used; robots.txt disallows ``?filtreler=*``.

Output: InflationItems/Datas/04_Housing/Emlakjet/YYYY-MM-DD.csv
Columns: product_name ("District / Neighborhood - Rooms"), price (number), category_number (4),
sub_category_number (0411001), then ilanId, District, Rooms, ListingURL, Province,
Neighborhood, PropertyType, AreaM2, Currency, ListingDate, CollectedAt.

Checkpoint (completed scopes, gitignored): InflationItems/Codes/04_Housing/Emlakjet/checkpoints/

Examples:
  python scraper.py                                   # full crawl
  python scraper.py --workers 3                       # 3 parallel streams
  python scraper.py --resume                          # continue today's crawl
  python scraper.py --start-url https://www.emlakjet.com/kiralik-konut/isparta --max-pages-per-scope 3
"""

import argparse
import csv
import json
import logging
import math
import random
import re
import threading
import time
from collections import deque
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests

BASE = "https://www.emlakjet.com"
ROOT_URL = f"{BASE}/kiralik-konut"
PAGE_SIZE = 30
BACKOFF = [2, 4, 6, 8, 10, 15]  # seconds waited after each failed/blocked request, then give up
PAGE_CAP = 50  # the site stops serving pages beyond this per route
NOT_PROVINCES = {"emlakcidan", "sahibinden", "kktc"}  # filters / non-Turkey route on the country page

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = REPO_ROOT / "InflationItems" / "Datas" / "04_Housing" / "Emlakjet"
CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints"

CATEGORY_NUMBER = 4
SUB_CATEGORY_NUMBER = "0411001"  # TÜİK item "Actual rentals paid by tenants" (CPI methodological notes, Appendix 1)
COLUMNS = [
    "product_name", "price", "category_number", "sub_category_number",  # shared first four, as in 08_Communication
    "ilanId", "District", "Rooms", "ListingURL", "Province", "Neighborhood", "PropertyType",
    "AreaM2", "Currency", "ListingDate", "CollectedAt",
]

log = logging.getLogger("emlakjet")


class Blocked(Exception):
    """Site answered with a challenge / rate limit that retries did not clear."""


class Client:
    def __init__(self, delay: float):
        self.delay = delay
        self.session = None
        self._last = 0.0
        self._new_session()

    def _new_session(self):
        self.session = requests.Session(impersonate="chrome")
        # homepage first, like a normal visit (docs/scraping-wiki/concepts/homepage-first-navigation.md)
        try:
            self.session.get(BASE + "/", timeout=30)
        except Exception as exc:  # warm-up failure is not fatal
            log.warning("homepage warm-up failed: %s", exc)

    def get(self, url: str) -> BeautifulSoup:
        for attempt in range(1, len(BACKOFF) + 2):
            wait = self.delay * random.uniform(0.8, 1.4) - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self.session.get(url, timeout=40)
            except Exception as exc:
                log.warning("%s attempt %d: %s", url, attempt, exc)
                resp = None
            self._last = time.monotonic()
            if resp is not None and resp.status_code == 200:
                resp.encoding = "utf-8"
                return BeautifulSoup(resp.text, "lxml")
            status = resp.status_code if resp is not None else "error"
            log.warning("%s attempt %d: HTTP %s", url, attempt, status)
            if status == 404:
                raise Blocked(f"404 for {url}")
            if attempt > len(BACKOFF):
                break
            time.sleep(BACKOFF[attempt - 1])
            if attempt >= 2:
                self._new_session()
        raise Blocked(f"giving up on {url}")


def listing_count(soup: BeautifulSoup) -> int | None:
    m = re.search(r"([\d.]+)\s+ilan bulundu", soup.get_text(" ", strip=True))
    return int(m.group(1).replace(".", "")) if m else None


def scope_links(soup: BeautifulSoup, slug: str) -> list[str]:
    """Child scope URLs: links whose path is `/kiralik-konut/<slug>-<something>`."""
    prefix = f"/kiralik-konut/{slug}-"
    found = {a["href"].split("?")[0] for a in soup.find_all("a", href=True)
             if a["href"].startswith(prefix) and "/" not in a["href"][len(prefix):]}
    return [BASE + h for h in sorted(found)]


def province_links(soup: BeautifulSoup) -> list[str]:
    paths = {a["href"].split("?")[0] for a in soup.find_all("a", href=True)
             if re.fullmatch(r"/kiralik-konut/[a-z0-9]+", a["href"])}
    return [BASE + p for p in sorted(paths) if p.rsplit("/", 1)[1] not in NOT_PROVINCES]


def parse_cards(soup: BeautifulSoup, province: str | None, level: str, collected_at: str) -> list[dict]:
    rows = []
    for art in soup.select("article[data-listing-id]"):
        ilan_id = art["data-listing-id"]
        link = art.select_one("a.listing-card-title-link") or art.find("a", href=re.compile(r"^/ilan/"))
        metas = [p.get_text("·", strip=True) for p in art.select("p.listing-row-card-meta")]
        price_el = art.select_one(".listing-row-card-price span")
        if not link or len(metas) < 2 or not price_el:
            continue
        place = [x.strip() for x in metas[0].split(",") if x.strip()]
        if level in ("country", "province") and len(place) >= 2:
            prov, place = place[0], place[1:]
        else:
            prov = province or ""
        district = place[0] if place else ""
        neighborhood = place[1] if len(place) > 1 else ""
        details = [x.strip() for x in metas[1].split("·") if x.strip()]
        rooms = details[0] if details else ""
        area = next((re.sub(r"\D", "", d) for d in details if "m²" in d), "")
        listed = next((d for d in details if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", d)), "")
        if listed:
            d, m, y = listed.split(".")
            listed = f"{y}-{m}-{d}"
        price_txt = price_el.get_text(strip=True)
        currency = "TRY" if "₺" in price_txt else ("USD" if "$" in price_txt else "EUR" if "€" in price_txt else "")
        digits = re.sub(r"[^\d,]", "", price_txt).replace(",", ".")
        if not digits:
            continue
        price = float(digits)
        price = int(price) if price.is_integer() else price
        rows.append({
            "product_name": product_name(district, neighborhood, rooms), "price": price, "category_number": CATEGORY_NUMBER,
            "sub_category_number": SUB_CATEGORY_NUMBER,
            "ilanId": ilan_id, "District": district, "Rooms": rooms, "ListingURL": urljoin(BASE, link["href"]), "Province": prov,
            "Neighborhood": neighborhood, "PropertyType": "Konut", "AreaM2": area,
            "Currency": currency, "ListingDate": listed, "CollectedAt": collected_at,
        })
    return rows


def product_name(district: str, neighborhood: str, rooms: str) -> str:
    """"Merkez / Çelebiler - 1+1", the naming of the other 04_Housing province scrapers."""
    place = district
    if neighborhood:
        place += " / " + re.sub(r"\s+Mahallesi$", "", neighborhood)
    return f"{place} - {'Stüdyo (1+0)' if rooms == 'Stüdyo' else rooms}"


def scope_level(slug: str) -> str:
    return "country" if not slug else ("province" if "-" not in slug else "sub")


def province_name(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    text = h1.get_text(" ", strip=True) if h1 else ""
    return re.sub(r"\s+Kiral[ıi]k\s+Ev.*$", "", text).strip()


class Crawler:
    def __init__(self, args):
        self.args = args
        self.day = date.today().isoformat()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        self.csv_path = DATA_DIR / (f"{self.day}.csv" if not args.output else args.output)
        self.ckpt_path = CHECKPOINT_DIR / f"{self.day}.json"
        self.seen: set[str] = set()
        self.done: set[str] = set()
        if args.resume and self.ckpt_path.exists():
            self.done = set(json.loads(self.ckpt_path.read_text(encoding="utf-8")).get("done", []))
            log.info("resuming: %d scopes already done", len(self.done))
        new_file = not self.csv_path.exists() or not args.resume
        if args.resume and self.csv_path.exists():
            with self.csv_path.open(encoding="utf-8", newline="") as fh:
                self.seen = {r["ilanId"] for r in csv.DictReader(fh)}
        self.fh = self.csv_path.open("w" if new_file else "a", encoding="utf-8", newline="")
        self.writer = csv.DictWriter(self.fh, fieldnames=COLUMNS)
        if new_file:
            self.writer.writeheader()
            self.done.clear()
        # shared by the workers: scope queue, open-scope counter, first fatal error
        self.cond = threading.Condition()
        self.queue: deque = deque()
        self.pending = 0
        self.error: Blocked | None = None

    def save_ckpt(self):  # call with self.cond held
        tmp = self.ckpt_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"date": self.day, "done": sorted(self.done)}), encoding="utf-8")
        for _ in range(5):  # Windows may briefly lock the target
            try:
                tmp.replace(self.ckpt_path)
                return
            except PermissionError:
                time.sleep(0.5)

    def run(self, start_url: str):
        self.queue.append((start_url, None))
        self.pending = 1
        threads = []
        for i in range(self.args.workers):
            t = threading.Thread(target=self.worker, args=(i,), name=f"w{i + 1}", daemon=True)
            threads.append(t)
            t.start()
            time.sleep(self.args.delay / self.args.workers)  # stagger the request streams
        for t in threads:
            t.join()
        if self.error:
            raise self.error

    def worker(self, index: int):
        client = Client(self.args.delay)
        while True:
            with self.cond:
                while not self.queue and self.pending > 0 and not self.error:
                    self.cond.wait()
                if self.error or not self.queue:
                    return
                url, province = self.queue.popleft()
            children: list = []
            try:
                children = self.process(client, url, province)
            except Blocked as exc:
                with self.cond:
                    self.error = self.error or exc
                    self.cond.notify_all()
                return
            except Exception as exc:  # one bad scope must not kill the crawl
                log.exception("scope %s failed: %s", url, exc)
            finally:
                with self.cond:
                    self.queue.extendleft(reversed(children))  # finish a province before the next one
                    self.pending += len(children) - 1
                    self.cond.notify_all()

    def process(self, client: Client, url: str, province: str | None) -> list:
        """Crawl one scope; returns child scopes when it had to be split."""
        url = url.split("?")[0].rstrip("/")
        with self.cond:
            if url in self.done:
                return []
            if self.args.limit_scopes and len(self.done) >= self.args.limit_scopes:
                return []
        slug = url[len(ROOT_URL):].lstrip("/")
        level = scope_level(slug)
        soup = client.get(url)
        if level == "province":
            province = province_name(soup) or slug
        count = listing_count(soup)
        pages = math.ceil(count / PAGE_SIZE) if count else 1
        children = []
        if level == "country":
            children = province_links(soup)
        elif count and pages > PAGE_CAP and level in ("province", "sub") and slug.count("-") < 2:
            children = scope_links(soup, slug)
        if children:
            log.info("split %s (%s listings) into %d scopes", url, count, len(children))
            return [(child, province) for child in children]
        if count and pages > PAGE_CAP:
            log.warning("%s has %s listings but the site serves only %d pages", url, count, PAGE_CAP)
        pages = min(pages, PAGE_CAP, self.args.max_pages_per_scope or PAGE_CAP)
        new = 0
        for page in range(1, pages + 1):
            if page > 1:
                soup = client.get(f"{url}?sayfa={page}")
            stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            parsed = parse_cards(soup, province, level, stamp)
            with self.cond:
                rows = [r for r in parsed if r["ilanId"] not in self.seen]
                for r in rows:
                    self.seen.add(r["ilanId"])
                    self.writer.writerow(r)
                self.fh.flush()
                total = len(self.seen)
            new += len(rows)
            log.info("[%s] %s page %d/%d: %d new rows (%d unique total)",
                     threading.current_thread().name, url, page, pages, len(rows), total)
            if not parsed:
                break
        if count is not None and not self.args.max_pages_per_scope and new < count * 0.9:
            log.warning("%s: site says %s listings, collected %d new (rest seen under other scopes or changed mid-crawl)",
                        url, count, new)
        with self.cond:
            self.done.add(url)
            self.save_ckpt()
        return []

    def finish(self, completed: bool):
        self.fh.close()
        if completed and self.args.start_url is None and self.ckpt_path.exists():
            self.ckpt_path.unlink()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start-url", default=None, help="crawl only this scope (default: whole country)")
    ap.add_argument("--max-pages-per-scope", type=int, default=0, help="bound pages per leaf scope (testing)")
    ap.add_argument("--limit-scopes", type=int, default=0, help="stop after N finished scopes (testing)")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between requests (jittered)")
    ap.add_argument("--workers", type=int, default=1, help="parallel request streams; per-IP request rate scales with N")
    ap.add_argument("--resume", action="store_true", help="continue today's CSV/checkpoint")
    ap.add_argument("--output", default=None, help="CSV file name inside the data dir (default: YYYY-MM-DD.csv)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    crawler = Crawler(args)
    completed = False
    try:
        crawler.run(args.start_url or ROOT_URL)
        completed = True
    except Blocked as exc:
        log.error("stopped: %s (re-run with --resume)", exc)
    finally:
        crawler.finish(completed)
    log.info("wrote %d rows to %s", len(crawler.seen), crawler.csv_path)
    raise SystemExit(0 if completed else 1)


if __name__ == "__main__":
    main()
