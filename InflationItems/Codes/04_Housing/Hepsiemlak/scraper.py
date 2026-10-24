"""
Hepsiemlak residential rental scraper (TÜİK 04 Housing), real browsers (CloakBrowser, async).

Recon (2026-10-23): ``/<route>?page=N`` listing pages are server-rendered, 24 ``li.listingCard`` per
page, no page cap. ``/kiralik`` = every residential rental in Türkiye (~68k, 2,832 pages);
``/<province>-kiralik`` one province (İstanbul: ~11.7k, 487 pages); a province page links its
districts as ``/<district>-kiralik``. The JSON behind the pages (``/api/realty-list/...``) and, more
slowly, the pages themselves answer HTTP 429 when one IP asks too fast; in a browser that 429 is
Cloudflare's "Just a moment..." managed challenge. See docs/TECH-STACK-SEARCH.md §3.4.

Work units are routes. A seed route (``--route``; ``--route all`` = every province from the sitemap;
``--shard <name>`` = that person's provinces from ``shards.json``) is crawled page by page; a province with more than SPLIT_PAGES pages is split into
its district routes instead (the largest district, Şişli, is ~40 pages). Units sit in one queue and
``--workers`` CloakBrowser sessions (each its own browser, optionally its own proxy) take the next
unit when they finish one, so the load balances itself. Each session visits the homepage first, scrolls every page, and pauses
a normally distributed time after each page (``--delay-min``/``--delay-max``, default 2-4 s:
mean in the middle, sigma = range/4, clipped). A session that stays rate-limited is retired and its
unit, with its progress, goes back to the queue.

Proxies (optional): ``--proxies-file`` with one ``http://user:pass@host:port`` per line, one session
per proxy (keep the file outside git, e.g. under ``checkpoints/``). Credentials are never logged.

Setup (once):  pip install cloakbrowser   (the ~200 MB Chromium build downloads on first launch)

Shards: four people each run a quarter of the provinces (``shards.json``, balanced by listing count),
started through ``hepsiemlak_<name>.py`` -> ``launcher.py``, which runs this file in the background.

Output: InflationItems/Datas/04_Housing/Hepsiemlak/YYYY-MM-DD.csv (``YYYY-MM-DD_<shard>.csv`` with --shard)
Columns: product_name ("District / Neighborhood - Rooms"), price (number), category_number (4),
sub_category_number (0411001), then ilanId, District, Rooms, ListingURL, Province,
Neighborhood, PropertyType, AreaM2, Currency, ListingDate, CollectedAt.
(District = ilçe, Neighborhood = mahalle; AreaM2 is the card's gross m², the card shows no net m²;
ListingDate is the card's date, i.e. last update.) De-duplicated by ilanId.

Checkpoint (finished routes + progress, gitignored): InflationItems/Codes/04_Housing/Hepsiemlak/checkpoints/
The body of the first rate-limited page is saved there too (``blocked-<status>.html``).

Examples:
  python scraper.py --shard zelal                      # one person's provinces
  python scraper.py --shard zelal --max-listings 100   # bounded test: stop after 100 listings
  python scraper.py --route istanbul-kiralik --workers 5 --delay-min 4 --delay-max 6
  python scraper.py --route all --workers 5            # every province
  python scraper.py --route kiralik                    # whole country as one route (no split)
  python scraper.py --route adana-kiralik --limit 3    # bounded test: 3 pages per unit
  python scraper.py ... --resume                       # continue today's crawl
"""

import argparse
import asyncio
import csv
import json
import logging
import random
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from cloakbrowser import launch_async

BASE = "https://www.hepsiemlak.com"
PAGE_SIZE = 24
SPLIT_PAGES = 60  # a province above this many pages is crawled district by district
BACKOFF = [30, 60, 120, 300, 600]  # seconds waited after each blocked page (browser restarted), then retire

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = REPO_ROOT / "InflationItems" / "Datas" / "04_Housing" / "Hepsiemlak"
CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints"
SHARDS_FILE = Path(__file__).resolve().parent / "shards.json"
NOT_TURKIYE = {"kibris"}  # listed among the sitemap's provinces

CATEGORY_NUMBER = 4
SUB_CATEGORY_NUMBER = "0411001"  # TÜİK item "Actual rentals paid by tenants"
COLUMNS = [
    "product_name", "price", "category_number", "sub_category_number",
    "ilanId", "District", "Rooms", "ListingURL", "Province", "Neighborhood", "PropertyType",
    "AreaM2", "Currency", "ListingDate", "CollectedAt",
]

log = logging.getLogger("hepsiemlak")

# runs in the page: one dict per listing card
EXTRACT_JS = """() => [...document.querySelectorAll('li.listingCard article')].map(a => {
  const q = s => a.querySelector(s), t = s => (q(s) || {}).textContent || '';
  const specs = {};
  a.querySelectorAll('.listingCard__spec-item').forEach(i => {
    const k = (i.querySelector('dt') || {}).textContent, v = (i.querySelector('dd') || {}).textContent;
    if (k) specs[k.trim()] = (v || '').trim();
  });
  const link = q('a.listingCard__content-link');
  return {id: a.id, href: link ? link.getAttribute('href') : '', price: t('.listingCard__price'),
          date: t('time'), location: t('.listingCard__location address'), specs};
})"""

# runs in the page: listing count, last page number, child "<x>-kiralik" route links
SCOPE_JS = """() => {
  const m = document.body.innerText.match(/([\\d.]+)\\s+ilan/);
  const hrefs = [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href'));
  const pages = hrefs.map(h => (h.match(/[?&]page=(\\d+)/) || [])[1]).filter(Boolean).map(Number);
  return {count: m ? Number(m[1].replace(/\\./g, '')) : 0, pages: pages.length ? Math.max(...pages) : 1,
          links: [...new Set(hrefs.filter(h => /^\\/[a-z0-9-]+-kiralik$/.test(h)).map(h => h.slice(1)))]};
}"""


class Blocked(Exception):
    """Site kept answering with a block / rate limit."""


class Delay:
    low, high = 2.0, 4.0

    @classmethod
    def draw(cls) -> float:
        mean, sigma = (cls.low + cls.high) / 2, (cls.high - cls.low) / 4
        return min(cls.high, max(cls.low, random.gauss(mean, sigma)))


async def pause():
    await asyncio.sleep(Delay.draw())


def parse_proxy(line: str) -> dict:
    u = urlparse(line.strip())
    proxy = {"server": f"{u.scheme}://{u.hostname}:{u.port}"}
    if u.username:
        proxy["username"], proxy["password"] = unquote(u.username), unquote(u.password or "")
    return proxy


def load_proxies(path: str | None) -> list[dict]:
    if not path:
        return []
    lines = [l for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return [parse_proxy(l) for l in lines]


def parse_card(c: dict, collected_at: str) -> dict | None:
    price_txt = re.sub(r"\s+", " ", c.get("price") or "").strip()
    digits = re.sub(r"[^\d,]", "", price_txt.split("TL")[0].split("$")[0].split("€")[0]).replace(",", ".")
    if not digits or not c.get("href") or not c.get("id"):
        return None
    price = float(digits)
    price = int(price) if price.is_integer() else price
    currency = "USD" if "$" in price_txt else "EUR" if "€" in price_txt else "TRY"
    place = [p.strip() for p in (c.get("location") or "").split("/")]
    province, district = (place + ["", ""])[:2]
    neighborhood = re.sub(r"\s+Mah\.?$", "", place[2]) if len(place) > 2 else ""
    specs = c.get("specs") or {}
    rooms = re.sub(r"\s+", "", specs.get("Oda Sayısı", ""))
    area = re.sub(r"\D", "", specs.get("Brüt m²", ""))
    listed = (c.get("date") or "").strip()
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", listed):
        d, m, y = listed.split("/")
        listed = f"{y}-{m}-{d}"
    ptype = re.sub(r"^Kiralık\s+", "", specs.get("Kategori", "")) or c["href"].split("/")[2]
    name = district + (f" / {neighborhood}" if neighborhood else "")
    return {
        "product_name": f"{name} - {rooms}" if rooms else name, "price": price,
        "category_number": CATEGORY_NUMBER, "sub_category_number": SUB_CATEGORY_NUMBER,
        "ilanId": c["id"], "District": district, "Rooms": rooms, "ListingURL": BASE + c["href"],
        "Province": province, "Neighborhood": neighborhood, "PropertyType": ptype,
        "AreaM2": area, "Currency": currency, "ListingDate": listed, "CollectedAt": collected_at,
    }


class Session:
    """One browser that browses like a visitor: homepage first, then listing pages."""

    def __init__(self, name: str, headless: bool, proxy: dict | None):
        self.name, self.headless, self.proxy = name, headless, proxy
        self.browser = self.page = None

    async def open(self):
        kwargs = {"headless": self.headless, "humanize": True, "locale": "tr-TR"}
        if self.proxy:
            kwargs.update(proxy=self.proxy, geoip=True)  # timezone/locale follow the proxy exit IP
        else:
            kwargs["timezone"] = "Europe/Istanbul"
        self.browser = await launch_async(**kwargs)
        self.page = await self.browser.new_page()
        # homepage first (docs/scraping-wiki/concepts/homepage-first-navigation.md)
        await self.page.goto(BASE + "/", wait_until="domcontentloaded", timeout=90000)
        await self.behave()
        await pause()

    async def close(self):
        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass
        self.browser = self.page = None

    async def behave(self):
        """A few scroll steps with mouse movement, as a visitor reading the page."""
        try:
            for _ in range(random.randint(2, 4)):
                await self.page.mouse.move(random.randint(100, 1100), random.randint(100, 650))
                await self.page.mouse.wheel(0, random.randint(250, 700))
                await asyncio.sleep(random.uniform(0.2, 0.6))
        except Exception as exc:  # cosmetic; never fail a page on it
            log.debug("[%s] behave: %s", self.name, exc)

    async def fetch(self, route: str, page_no: int, crawler: "Crawler") -> tuple[list[dict], dict]:
        url = f"{BASE}/{route}" + (f"?page={page_no}" if page_no > 1 else "")
        for attempt in range(1, len(BACKOFF) + 2):
            status = None
            try:
                if self.page is None:
                    await self.open()
                resp = await self.page.goto(url, wait_until="domcontentloaded", timeout=90000)
                status = resp.status if resp else None
                if status != 200 and "Just a moment" in await self.page.title():
                    # Cloudflare managed challenge (served as 429/403): a real browser solves it in
                    # place and keeps cf_clearance, so wait for the listing instead of restarting
                    crawler.save_block(status, await self.page.content())
                    try:
                        await self.page.wait_for_selector("li.listingCard", timeout=45000)
                        crawler.challenges["passed"] += 1
                        log.info("[%s] Cloudflare challenge passed on %s", self.name, url)
                        status = 200
                    except Exception:
                        crawler.challenges["failed"] += 1
                if status == 200:
                    # (a challenge redirect may swap the document, so no element handles kept)
                    await self.page.wait_for_selector("li.listingCard", timeout=15000)
                    await self.behave()
                    cards = await self.page.evaluate(EXTRACT_JS)
                    scope = await self.page.evaluate(SCOPE_JS) if page_no == 1 else {}
                    await pause()
                    return cards, scope
                if status:
                    crawler.save_block(status, await self.page.content())
            except Exception as exc:
                log.warning("[%s] %s attempt %d: %s", self.name, url, attempt, str(exc).splitlines()[0][:160])
            log.warning("[%s] %s attempt %d: HTTP %s", self.name, url, attempt, status)
            if attempt > len(BACKOFF):
                break
            await self.close()
            await asyncio.sleep(BACKOFF[attempt - 1] * random.uniform(0.8, 1.2))
        raise Blocked(f"giving up on {url}")


class Crawler:
    def __init__(self, args, csv_path: Path, ckpt_path: Path):
        self.args, self.csv_path, self.ckpt_path = args, csv_path, ckpt_path
        self.seen: set[str] = set()
        self.done: set[str] = set()        # finished routes
        self.progress: dict[str, int] = {}  # route -> last finished page
        self.sizes: dict[str, int] = {}     # route -> listing count reported by the site
        self.queue: list[tuple[int, str]] = []  # (priority, route), highest taken first
        self.active = 0
        self.blocked_saved = False
        self.challenges = {"passed": 0, "failed": 0}
        self.written = 0      # rows written by this run
        self.capped = False   # --max-listings reached
        self.started = time.monotonic()
        resuming = args.resume and csv_path.exists()
        if resuming:
            with csv_path.open(encoding="utf-8", newline="") as fh:
                self.seen = {r["ilanId"] for r in csv.DictReader(fh)}
            if ckpt_path.exists():
                ck = json.loads(ckpt_path.read_text(encoding="utf-8"))
                self.done, self.progress = set(ck.get("done", [])), ck.get("progress", {})
                self.queue = [tuple(x) for x in ck.get("queue", [])]
                for route in self.progress:  # routes a stopped session was in the middle of
                    self.push(route, 10**6)
            log.info("resuming: %d routes done, %d in progress, %d listings in %s",
                     len(self.done), len(self.progress), len(self.seen), csv_path.name)
        self.fh = csv_path.open("a" if resuming else "w", encoding="utf-8", newline="")
        self.writer = csv.DictWriter(self.fh, fieldnames=COLUMNS)
        if not resuming:
            self.writer.writeheader()
            self.fh.flush()

    def save_ckpt(self):
        self.ckpt_path.write_text(json.dumps({
            "date": date.today().isoformat(), "done": sorted(self.done), "progress": self.progress,
            "queue": sorted(self.queue, reverse=True)}), encoding="utf-8")

    def save_block(self, status, html: str):
        if not self.blocked_saved and status:
            self.blocked_saved = True
            (CHECKPOINT_DIR / f"blocked-{status}.html").write_text(html, encoding="utf-8")

    def push(self, route: str, est_pages: int):
        if route not in self.done and all(r != route for _, r in self.queue):
            self.queue.append((est_pages, route))
            self.queue.sort()

    def pop(self) -> str | None:
        return self.queue.pop()[1] if self.queue else None

    def write(self, cards: list[dict]) -> int:
        stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        new = 0
        for c in cards:
            if self.args.max_listings and self.written >= self.args.max_listings:
                break
            row = parse_card(c, stamp)
            if row and row["ilanId"] not in self.seen:
                self.seen.add(row["ilanId"])
                self.writer.writerow(row)
                new += 1
                self.written += 1
        self.fh.flush()
        if self.args.max_listings and self.written >= self.args.max_listings and not self.capped:
            self.capped = True
            log.info("reached --max-listings %d, stopping", self.args.max_listings)
        return new

    async def crawl_route(self, s: Session, route: str):
        """Crawl one route, or split it; raises Blocked with progress saved."""
        page = self.progress.get(route, 0) + 1
        total = None
        while total is None or page <= total:
            if self.args.limit and page > self.args.limit:
                break
            if self.capped:
                return  # route stays in progress
            cards, scope = await s.fetch(route, page, self)
            if page == 1:
                total = scope.get("pages", 1)
                self.sizes[route] = scope.get("count", 0)
                children = [l for l in scope.get("links", []) if l != route and "sezonluk" not in l]
                if total > SPLIT_PAGES and children and self.is_province(route):
                    for child in children:
                        self.push(child, 10**5 + 1)  # finish this province before the next seed
                    self.done.add(route)
                    self.save_ckpt()
                    log.info("[%s] %s: %d listings, %d pages -> split into %d districts",
                             s.name, route, self.sizes[route], total, len(children))
                    return
                log.info("[%s] %s: %d listings, %d pages", s.name, route, self.sizes[route], total)
            elif total is None:
                total = 10**6  # resumed mid-route: stop at the first empty page
            new = self.write(cards)
            self.progress[route] = page
            self.save_ckpt()
            if page % 10 == 0 or self.args.limit:
                log.info("[%s] %s page %d/%s: %d cards, %d new (%d unique total)",
                         s.name, route, page, total if total < 10**6 else "?", len(cards), new, len(self.seen))
            if not cards:
                break
            page += 1
        if self.capped:
            return  # --max-listings may have cut the last page short; the route is not finished
        self.progress.pop(route, None)
        self.done.add(route)
        self.save_ckpt()
        log.info("[%s] %s done (%d unique total, %.0f min elapsed)", s.name, route, len(self.seen),
                 (time.monotonic() - self.started) / 60)

    def is_province(self, route: str) -> bool:
        return route in self.seeds and route != "kiralik"

    async def worker(self, idx: int, proxy: dict | None):
        await asyncio.sleep(idx * random.uniform(3, 6))  # stagger the sessions
        s = Session(f"w{idx + 1}", self.args.headless, proxy)
        try:
            while not self.capped:
                route = self.pop()
                if route is None:
                    if self.active == 0:
                        return
                    await asyncio.sleep(2)  # another worker may still split a province
                    continue
                self.active += 1
                try:
                    await self.crawl_route(s, route)
                except Blocked as exc:
                    log.error("[%s] retired: %s", s.name, exc)
                    self.push(route, 10**6)  # hand it to another session first
                    self.save_ckpt()
                    return
                except Exception as exc:  # one bad route must not kill the crawl
                    log.exception("[%s] %s failed: %s", s.name, route, exc)
                finally:
                    self.active -= 1
        finally:
            await s.close()

    async def run(self, seeds: list[str], proxies: list[dict]) -> bool:
        self.seeds = set(seeds)
        if not self.queue:
            for i, r in enumerate(seeds):
                self.push(r, 10**5 - i)  # taken in the given order (shards list the largest first)
        n = len(proxies) or self.args.workers
        log.info("%d session(s) on %s, pause %.1f-%.1f s, %d routes queued",
                 n, "proxies" if proxies else "the local IP", Delay.low, Delay.high, len(self.queue))
        await asyncio.gather(*(self.worker(i, proxies[i] if proxies else None) for i in range(n)))
        self.fh.close()
        return self.capped or (not self.queue and not self.progress)


async def province_seeds() -> list[str]:
    """Province routes from the sitemap (``iller-*.xml`` lists ``/<province>`` URLs)."""
    from curl_cffi import requests  # sitemap is static XML; a plain TLS-impersonating client is enough
    s = requests.Session(impersonate="chrome")
    index = s.get(f"{BASE}/sitemap/index.xml", timeout=60).text
    seeds = []
    for sm in (m for m in re.findall(r"<loc>(.*?)</loc>", index) if "/iller-" in m):
        await pause()
        seeds += [u.rstrip("/").rsplit("/", 1)[1] for u in re.findall(r"<loc>(.*?)</loc>", s.get(sm, timeout=60).text)]
    return [p + "-kiralik" for p in seeds if p not in NOT_TURKIYE]


def shard_names() -> list[str]:
    return [k for k in json.loads(SHARDS_FILE.read_text(encoding="utf-8")) if not k.startswith(("_", "counts"))]


def shard_seeds(name: str) -> list[str]:
    return [p + "-kiralik" for p in json.loads(SHARDS_FILE.read_text(encoding="utf-8"))[name]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--route", nargs="+", default=["all"], help="seed routes, e.g. istanbul-kiralik; 'all' = every province")
    ap.add_argument("--shard", choices=shard_names(), default=None, help="crawl this person's provinces (shards.json)")
    ap.add_argument("--max-listings", type=int, default=0, help="stop after writing N listings (testing)")
    ap.add_argument("--workers", type=int, default=1, help="browser sessions without proxies (all on the local IP)")
    ap.add_argument("--proxies-file", default=None, help="one proxy URL per line; one session per proxy")
    ap.add_argument("--delay-min", type=float, default=2.0, help="pause after each page, seconds")
    ap.add_argument("--delay-max", type=float, default=4.0)
    ap.add_argument("--limit", type=int, default=0, help="at most N pages per route (testing)")
    ap.add_argument("--resume", action="store_true", help="continue today's CSV from the checkpoint")
    ap.add_argument("--headed", action="store_true", help="show the browser windows")
    ap.add_argument("--output", default=None, help="CSV file name inside the data dir (default: YYYY-MM-DD.csv)")
    args = ap.parse_args()
    args.headless = not args.headed
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    Delay.low, Delay.high = args.delay_min, args.delay_max

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    name = args.output or f"{date.today().isoformat()}{'_' + args.shard if args.shard else ''}.csv"
    csv_path = DATA_DIR / name
    ckpt_path = CHECKPOINT_DIR / (Path(name).stem + ".json")
    if args.shard:
        log.info("shard %s: %d provinces -> %s", args.shard, len(shard_seeds(args.shard)), csv_path.name)

    async def go() -> bool:
        if args.shard:
            seeds = shard_seeds(args.shard)
        else:
            seeds = await province_seeds() if args.route == ["all"] else args.route
        crawler = Crawler(args, csv_path, ckpt_path)
        try:
            return await crawler.run(seeds, load_proxies(args.proxies_file))
        finally:
            log.info("wrote %d rows to %s; Cloudflare challenges passed %d, failed %d", len(crawler.seen), csv_path,
                     crawler.challenges["passed"], crawler.challenges["failed"])
            for route, count in sorted(crawler.sizes.items()):
                log.debug("site count %s: %d", route, count)

    completed = asyncio.run(go())
    if completed and not args.limit and not args.max_listings and ckpt_path.exists():
        ckpt_path.unlink()
    if not completed:
        log.error("incomplete (blocked or stopped); re-run with --resume")
    raise SystemExit(0 if completed else 1)


if __name__ == "__main__":
    main()
