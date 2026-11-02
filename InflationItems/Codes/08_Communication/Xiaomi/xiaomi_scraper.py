"""
Xiaomi Türkiye (mi.com/tr) scraper (curl_cffi only, no browser).

The product-list pages fill themselves from the store's own JSON endpoint
``go.buy.mi.com/tr/search/product-list`` (found in the page's XHR, 2026-11-02).
The session visits the homepage first (it sets ``xm_geo`` / ``xm_user_bucket``)
and then calls the endpoint with the same Chrome TLS fingerprint. No anti-bot
cookie is needed.

Coverage (2026-11-02): the unfiltered list has ~300 products (pages of at most
20, ``page_index`` from 0). Each product has one or more commodities (colour /
memory variants, ~535); one CSV row per commodity. The category comes from
crawling every leaf of ``/v2/item/category/nav``; products that sit in no leaf
keep an empty category and are classified by name.

Price = commodity ``sales_price`` (the price the site shows).

Output: InflationItems/Datas/08_Communication/Xiaomi/xiaomi_urunler_YYYY-MM-DD.csv
"""

import csv
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from curl_cffi import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tuik08  # noqa: E402  (08_Communication/tuik08.py)

HOME = "https://www.mi.com/tr/"
API = "https://go.buy.mi.com/tr"
LIST_API = f"{API}/search/product-list"
NAV_API = f"{API}/v2/item/category/nav"
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Origin": "https://www.mi.com",
    "Referer": f"{HOME}product-list/",
}
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
PAGE_SIZE = 20  # the endpoint never returns more than 20
MAX_PAGES = 50
DELAY = 0.5
FIELDS = tuik08.COLUMNS + ["Product ID", "Commodity ID"]

# leaf category_tag -> TÜİK item code (other leaves: "0"; no leaf at all: name rules)
TUIK_ITEMS = {
    **dict.fromkeys(["xiaomi", "redmi", "poco-x", "poco-f", "poco-m", "poco-c"], tuik08.MOBILE_PHONE),
    "tablet": tuik08.COMPUTER,
    **dict.fromkeys(["monitor", "flash-drives", "router", "wifi-range-extenders", "keyboard-mouse",
                     "writing-tablet"], tuik08.PERIPHERALS),
    **dict.fromkeys(["tws-earphone", "speakers", "projector", "tvbox-stick", "soundbar"], tuik08.AUDIO_VIDEO),
    "tv": tuik08.TELEVISION,
    **dict.fromkeys(["watch", "band", "smart-tags", "smart-glasses"], tuik08.OTHER_DEVICES),
    **dict.fromkeys(["phone-accessories", "tablets-accessories", "power-banks", "cables",
                     "wireless-chargings", "power-adapters", "selfie-stick"], tuik08.ACCESSORIES),
}

REPO_ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = REPO_ROOT / "InflationItems" / "Datas" / "08_Communication" / "Xiaomi"

log = logging.getLogger("xiaomi")


def get_json(session, url, **params):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            j = r.json()
            if j.get("errno") == 0:
                return j["data"]
            log.warning("%s errno=%s %s", url, j.get("errno"), j.get("errmsg"))
        except (requests.RequestsError, ValueError) as e:
            log.warning("%s attempt %d/%d failed: %s", url, attempt, MAX_RETRIES, e)
        time.sleep(3 * attempt)
    return None


def leaves(nodes, top=""):
    """(category_tag, top-level title, leaf title) for every crawlable leaf of the nav tree."""
    for n in nodes or []:
        title = " ".join(n["title"].split())
        kids = [c for c in n["children"] or [] if c["category_tag"] and c["category_tag"] != n["category_tag"]]
        if kids:
            yield from leaves(kids, top or title)
        elif n["category_tag"]:
            yield n["category_tag"], top or title, title


def product_list(session, tag=""):
    """All products of one category tag ("" = whole catalogue), keyed by product id."""
    products = {}
    for page in range(MAX_PAGES):
        data = get_json(session, LIST_API, version="v4", page_size=PAGE_SIZE, type=2,
                        category_tag=tag, page_index=page, **{"from": "mobile"})
        if data is None:
            log.error("[%s] page %d could not be fetched", tag or "all", page)
            break
        found = data["data_provider"]["data"]["product_list"] or []
        if not found:
            break
        for p in found:
            products[p["product"]["id"]] = p
        time.sleep(DELAY)
    return products


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    out_file = OUT_DIR / f"xiaomi_urunler_{datetime.now():%Y-%m-%d}.csv"

    session = requests.Session(impersonate="chrome")
    session.get(HOME, headers={"Accept-Language": HEADERS["Accept-Language"]}, timeout=REQUEST_TIMEOUT)
    session.headers.update(HEADERS)
    log.info("Homepage cookies: %s", ", ".join(sorted(session.cookies.keys())) or "none")

    catalogue = product_list(session)
    log.info("Catalogue: %d products", len(catalogue))

    category = {}  # product id -> (category tag, top title, leaf title); first leaf wins
    nav = get_json(session, NAV_API, **{"from": "mobile"})
    for tag, top, leaf in leaves((nav or {}).get("children")):
        found = product_list(session, tag)
        for pid, p in found.items():
            category.setdefault(pid, (tag, top, leaf))
            catalogue.setdefault(pid, p)
        log.info("[%s / %s] %d products", top, leaf, len(found))
    log.info("Products with a category: %d of %d", len(category), len(catalogue))

    rows = []
    for pid, p in catalogue.items():
        tag = category.get(pid, ("",))[0]
        for c in p["commodity"] or []:
            price = c.get("raw_sales_price")
            if not price:
                continue
            name = " ".join(c["name"].split())
            item = TUIK_ITEMS.get(tag, tuik08.NOT_IN_BASKET) if tag else tuik08.classify(name)
            rows.append(tuik08.with_category(name, float(price), item, **{"Product ID": pid, "Commodity ID": c["id"]}))

    if not rows:
        log.error("No data collected.")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    log.info("Saved %d commodities of %d products to %s", len(rows), len(catalogue), out_file)


if __name__ == "__main__":
    main()
