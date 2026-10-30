import argparse
import html
import csv
import logging
import re
import sys
import time
import math
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("ToyzzShopScraper")

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = next((p for p in BASE_DIR.parents if (p / ".git").exists()), BASE_DIR)
DATA_DIR = PROJECT_ROOT / "InflationItems" / "Datas" / "09_Recreation" / "ToyzzShop"

BASE_URL = "https://www.toyzzshop.com"
CATEGORY_NUMBER = "09"
OTHER_TOYS_SUB_CATEGORY_NUMBER = "0921204"
WHEELED_TOYS_SUB_CATEGORY_NUMBER = "0921207"

CATEGORIES = {
    "board_games": {
        "url": "https://www.toyzzshop.com/kutu-oyunlari",
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "hobby_toys": {
        "url": "https://www.toyzzshop.com/hobi-oyuncaklari",
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "plush_toys": {
        "url": "https://www.toyzzshop.com/pelus-oyuncaklar",
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "dolls": {
        "url": "https://www.toyzzshop.com/oyuncak-bebekler-ve-aksesuarlari/",
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "building_toys": {
        "url": "https://www.toyzzshop.com/yapim-oyuncaklari-lego",
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "baby_toys": {
        "url": "https://www.toyzzshop.com/bebek-oyuncaklari",
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "educational_toys": {
        "url": "https://www.toyzzshop.com/egitici-oyuncaklar",
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "model_toy_cars": {
        "url": "https://www.toyzzshop.com/oyuncak-araba/model-arabalar-ve-araclar",
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "remote_control_toys": {
        "url": "https://www.toyzzshop.com/oyuncak-araba/kumandali-arabalar",
        "sub_category_number": OTHER_TOYS_SUB_CATEGORY_NUMBER
    },
    "scooters": {
        "url": "https://www.toyzzshop.com/scooter",
        "sub_category_number": WHEELED_TOYS_SUB_CATEGORY_NUMBER
    },
    "battery_vehicles": {
        "url": "https://www.toyzzshop.com/akulu-araclar",
        "sub_category_number": WHEELED_TOYS_SUB_CATEGORY_NUMBER
    },
    "pedal_vehicles": {
        "url": "https://www.toyzzshop.com/pedalli-araclar",
        "sub_category_number": WHEELED_TOYS_SUB_CATEGORY_NUMBER
    },
    "ride_on_vehicles": {
        "url": "https://www.toyzzshop.com/pedalsiz-surmeli-araclar",
        "sub_category_number": WHEELED_TOYS_SUB_CATEGORY_NUMBER
    },
    "three_wheel_bikes": {
        "url": "https://www.toyzzshop.com/bisiklet/3-tekerlekli-bisiklet",
        "sub_category_number": WHEELED_TOYS_SUB_CATEGORY_NUMBER
    },
    "skates_skateboards": {
        "url": "https://www.toyzzshop.com/kaykay-paten",
        "sub_category_number": WHEELED_TOYS_SUB_CATEGORY_NUMBER
    }
}

MAX_PAGES = 120
REQUEST_DELAY = 1.0


DEFAULT_OTHER_TOYS_LIMIT = 15000
DEFAULT_WHEELED_TOYS_LIMIT = 15000


DEFAULT_SCAN_LIMIT_PER_CATEGORY = 1500

PRICE_PATTERN = re.compile(
    r"\d{1,3}(?:\s*\.\s*\d{3})*(?:\s*,\s*\d{2})?\s*(?:TL|TRY|₺)",
    re.IGNORECASE
)

BADGE_PATTERNS = [
    r"^Sadece Toyzz Shop'ta\s*",
    r"^İnternete Özel Fiyat\s*",
    r"^İnternette Tükendi\s*",
    r"^Yeni\s*",
    r"^Fırsat\s*"
]


def add_page_number(url, page_number):
    if page_number <= 1:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["q"] = f"page/{page_number}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def normalize_text(text):
    value = " ".join(text.replace("\xa0", " ").split())
    value = re.sub(r"\s*([.,])\s*(?=\d)", r"\1", value)
    return value.strip()


def convert_price(text):
    value = normalize_text(text)
    value = re.sub(r"[^\d.,]", "", value)
    if not value:
        return None
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", value):
        value = value.replace(".", "")
    try:
        return float(value)
    except ValueError:
        return None


def clean_name(text):
    value = normalize_text(text)


    for _ in range(5):
        decoded = html.unescape(value)
        if decoded == value:
            break
        value = decoded

    for _ in range(6):
        previous = value
        for pattern in BADGE_PATTERNS:
            value = re.sub(pattern, "", value, flags=re.IGNORECASE).strip()
        if value == previous:
            break

    value = re.sub(r"\s*%\s*\d+\s*$", "", value).strip()
    return value


def canonical_product_key(name):

    value = clean_name(name).casefold()
    value = value.replace("_", " ")
    value = re.sub(r"(?<=\d)\s*[,]\s*(?=\d)", ".", value)
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def is_product_href(href):
    if not href:
        return False
    absolute = urljoin(BASE_URL, href)
    parts = urlsplit(absolute)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    return bool(query.get("serial"))


def normalize_product_url(href):
    if not is_product_href(href):
        return None
    absolute = urljoin(BASE_URL, href)
    parts = urlsplit(absolute)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    serial = query.get("serial")
    return urlunsplit(("https", "www.toyzzshop.com", parts.path.rstrip("/"), urlencode({"serial": serial}), ""))


def extract_current_price(text):
    value = normalize_text(text)
    before_basket = re.split(r"\bSepette\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
    matches = list(PRICE_PATTERN.finditer(before_basket))
    if not matches:
        return None
    for match in reversed(matches):
        price = convert_price(match.group(0))
        if price is not None and price > 0:
            return price
    return None


def extract_name_from_link(link):
    candidates = []
    for attribute in ["title", "aria-label"]:
        value = link.get(attribute)
        if value:
            candidates.append(value)
    image = link.find("img")
    if image and image.get("alt"):
        candidates.append(image.get("alt"))
    text = normalize_text(link.get_text(" ", strip=True))
    if text:
        first_price = PRICE_PATTERN.search(text)
        if first_price:
            text = text[:first_price.start()].strip()
        candidates.append(text)
    cleaned = []
    for candidate in candidates:
        candidate = clean_name(candidate)
        if len(candidate) >= 3 and not PRICE_PATTERN.search(candidate):
            cleaned.append(candidate)
    return max(cleaned, key=len) if cleaned else None


def product_urls_in(container):
    urls = set()
    for link in container.find_all("a", href=True):
        normalized = normalize_product_url(link.get("href"))
        if normalized:
            urls.add(normalized)
    return urls


def find_product_container(link):
    current = link
    for _ in range(14):
        current = current.parent
        if current is None:
            break
        text = normalize_text(current.get_text(" ", strip=True))
        if extract_current_price(text) is None:
            continue
        urls = product_urls_in(current)
        if len(urls) == 1:
            return current
    return None


def extract_name_from_container(container, product_url):
    names = []
    for link in container.find_all("a", href=True):
        if normalize_product_url(link.get("href")) != product_url:
            continue
        name = extract_name_from_link(link)
        if name:
            names.append(name)
    for selector in ["h2", "h3", "h4", "[class*='name']", "[class*='title']"]:
        for element in container.select(selector):
            text = clean_name(element.get_text(" ", strip=True))
            first_price = PRICE_PATTERN.search(text)
            if first_price:
                text = text[:first_price.start()].strip()
            if len(text) >= 3:
                names.append(text)
    return max(names, key=len) if names else None


def extract_total_results(html):
    soup = BeautifulSoup(html, "html.parser")
    text = normalize_text(soup.get_text(" ", strip=True))
    patterns = [
        r"Filtrele\s*([\d.]+)\s*Ürün\s*Listeleniyor",
        r"([\d.]+)\s*Ürün\s*Sırala",
        r"([\d.]+)\s*Ürün"
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return int(match.group(1).replace(".", ""))
            except ValueError:
                pass
    return None


def parse_products(html, sub_category_number):
    soup = BeautifulSoup(html, "html.parser")
    product_links = [link for link in soup.find_all("a", href=True) if is_product_href(link.get("href"))]
    items = {}
    for link in product_links:
        product_url = normalize_product_url(link.get("href"))
        if not product_url or product_url in items:
            continue
        container = find_product_container(link)
        if container is None:
            continue
        price = extract_current_price(container.get_text(" ", strip=True))
        if price is None or price <= 0:
            continue
        name = extract_name_from_container(container, product_url) or extract_name_from_link(link)
        if not name or len(name) < 3:
            continue
        items[product_url] = {
            "product_name": name,
            "price": price,
            "category_number": CATEGORY_NUMBER,
            "sub_category_number": sub_category_number,
            "_product_url": product_url
        }
    return list(items.values()), len(product_links)


def fetch_rendered_html(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_selector('a[href*="serial="]', timeout=10000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(200)
    return page.content()


def scrape_category(page, category_name, category_url, sub_category_number, max_pages, limit_per_category=0):
    results = []
    seen_urls = set()
    expected_total = None
    page_limit = max_pages
    logger.info("Starting category: %s", category_name)
    for page_number in range(1, max_pages + 1):
        if page_number > page_limit:
            break
        url = add_page_number(category_url, page_number)
        logger.info("%s - page %d", category_name, page_number)
        try:
            html = fetch_rendered_html(page, url)
        except Exception as exc:
            logger.warning("%s page %d failed: %s", category_name, page_number, exc)
            break
        if expected_total is None:
            expected_total = extract_total_results(html)
            if expected_total is not None:
                logger.info("%s: site reports %d products", category_name, expected_total)
        products, link_count = parse_products(html, sub_category_number)
        if not products:
            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            visible = normalize_text(soup.get_text(" ", strip=True))[:180]
            logger.warning(
                "%s page %d: parsed 0 products | html=%d chars | product_links=%d | title=%s | text=%s",
                category_name,
                page_number,
                len(html),
                link_count,
                title,
                visible
            )
            break
        if page_number == 1 and expected_total is not None and products:
            target_total = expected_total
            if limit_per_category > 0:
                target_total = min(target_total, limit_per_category)
            page_limit = min(max_pages, max(1, math.ceil(target_total / len(products)) + 2))
            logger.info("%s: page limit set to %d", category_name, page_limit)
        new_count = 0
        target_total = expected_total
        if limit_per_category > 0:
            target_total = limit_per_category if target_total is None else min(target_total, limit_per_category)
        for product in products:
            if target_total is not None and len(results) >= target_total:
                break
            product_url = product["_product_url"]
            if product_url in seen_urls:
                continue
            seen_urls.add(product_url)
            results.append(product)
            new_count += 1
        logger.info(
            "%s page %d: %d products, %d new, total=%d%s",
            category_name,
            page_number,
            len(products),
            new_count,
            len(results),
            f"/{target_total}" if target_total is not None else ""
        )
        if target_total is not None and len(results) >= target_total:
            logger.info("%s: reached target total %d", category_name, target_total)
            break
        if new_count == 0:
            break
        time.sleep(REQUEST_DELAY)
    logger.info("%s: extracted %d unique products", category_name, len(results))
    return results


def round_robin_unique(category_results, total_limit, global_urls=None, global_keys=None):

    global_urls = global_urls if global_urls is not None else set()
    global_keys = global_keys if global_keys is not None else set()

    selected = []
    local_urls = set()
    local_keys = set()

    category_names = list(category_results.keys())
    positions = {name: 0 for name in category_names}

    active = list(category_names)

    while active:
        progressed = False
        next_active = []

        for category_name in active:
            items = category_results[category_name]
            pos = positions[category_name]

            while pos < len(items):
                item = items[pos]
                pos += 1

                product_url = item.get("_product_url")
                product_key = canonical_product_key(item.get("product_name", ""))

                if not product_key:
                    continue

                if product_url and (
                    product_url in global_urls or product_url in local_urls
                ):
                    continue

                if product_key in global_keys or product_key in local_keys:
                    continue

                selected.append(item)

                if product_url:
                    local_urls.add(product_url)
                local_keys.add(product_key)

                progressed = True
                break

            positions[category_name] = pos

            if pos < len(items):
                next_active.append(category_name)

            if total_limit > 0 and len(selected) >= total_limit:
                global_urls.update(local_urls)
                global_keys.update(local_keys)
                return selected

        if not progressed:
            break

        active = next_active

    global_urls.update(local_urls)
    global_keys.update(local_keys)
    return selected


def dedupe_rows(data):
    unique = []
    seen_urls = set()
    seen_keys = set()

    for item in data:
        product_url = item.get("_product_url")
        product_key = canonical_product_key(item.get("product_name", ""))

        if product_url and product_url in seen_urls:
            continue
        if not product_key or product_key in seen_keys:
            continue

        if product_url:
            seen_urls.add(product_url)
        seen_keys.add(product_key)
        unique.append(item)

    return unique


def save_to_csv(data, date_str):
    data = dedupe_rows(data)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_file = DATA_DIR / f"toyzzshop_{date_str}.csv"
    with open(output_file, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["product_name", "price", "category_number", "sub_category_number"])
        for item in sorted(data, key=lambda x: (x["sub_category_number"], clean_name(x["product_name"]).casefold())):
            final_name = clean_name(item["product_name"])

            writer.writerow([
                final_name,
                f'{item["price"]:.2f}',
                item["category_number"],
                item["sub_category_number"]
            ])
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Toyzz Shop balanced rendered HTML scraper"
    )
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)

    parser.add_argument(
        "--other-limit",
        type=int,
        default=DEFAULT_OTHER_TOYS_LIMIT,
        help=f"Maximum final products for {OTHER_TOYS_SUB_CATEGORY_NUMBER} "
             f"(default: {DEFAULT_OTHER_TOYS_LIMIT})",
    )
    parser.add_argument(
        "--wheeled-limit",
        type=int,
        default=DEFAULT_WHEELED_TOYS_LIMIT,
        help=f"Maximum final products for {WHEELED_TOYS_SUB_CATEGORY_NUMBER} "
             f"(default: {DEFAULT_WHEELED_TOYS_LIMIT})",
    )
    parser.add_argument(
        "--scan-limit-per-category",
        type=int,
        default=DEFAULT_SCAN_LIMIT_PER_CATEGORY,
        help=(
            "Maximum candidate products scraped from each Toyzz Shop source "
            f"category before balancing (default: {DEFAULT_SCAN_LIMIT_PER_CATEGORY}; "
            "0 = no source-category cap)"
        ),
    )

    parser.add_argument(
        "--limit-per-category",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    if args.other_limit < 0 or args.wheeled_limit < 0:
        parser.error("--other-limit and --wheeled-limit must be >= 0")
    if args.max_pages < 1:
        parser.error("--max-pages must be >= 1")
    if args.scan_limit_per_category < 0:
        parser.error("--scan-limit-per-category must be >= 0")
    if args.limit_per_category is not None and args.limit_per_category < 0:
        parser.error("--limit-per-category must be >= 0")

    scan_limit = (
        args.limit_per_category
        if args.limit_per_category is not None
        else args.scan_limit_per_category
    )

    date_str = args.date or datetime.today().strftime("%Y-%m-%d")


    candidates = {
        OTHER_TOYS_SUB_CATEGORY_NUMBER: {},
        WHEELED_TOYS_SUB_CATEGORY_NUMBER: {},
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        context = browser.new_context(
            locale="tr-TR",
            viewport={"width": 1440, "height": 1000},
        )

        context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in {"image", "media", "font"}
            else route.continue_(),
        )

        page = context.new_page()

        for category_name, category in CATEGORIES.items():
            items = scrape_category(
                page=page,
                category_name=category_name,
                category_url=category["url"],
                sub_category_number=category["sub_category_number"],
                max_pages=args.max_pages,
                limit_per_category=scan_limit,
            )

            candidates[
                category["sub_category_number"]
            ][category_name] = items

        context.close()
        browser.close()


    global_urls = set()
    global_keys = set()

    other_selected = round_robin_unique(
        candidates[OTHER_TOYS_SUB_CATEGORY_NUMBER],
        args.other_limit,
        global_urls=global_urls,
        global_keys=global_keys,
    )

    wheeled_selected = round_robin_unique(
        candidates[WHEELED_TOYS_SUB_CATEGORY_NUMBER],
        args.wheeled_limit,
        global_urls=global_urls,
        global_keys=global_keys,
    )

    selected = other_selected + wheeled_selected
    selected = dedupe_rows(selected)

    if not selected:
        logger.error("No products scraped")
        sys.exit(1)


    output_file = save_to_csv(selected, date_str)

    print()
    print("----------------------------")
    print("Scraping completed.")
    print("Other toys:", len(other_selected))
    print("Wheeled toys:", len(wheeled_selected))
    print("Total unique products:", len(selected))
    print("Other output limit:", args.other_limit)
    print("Wheeled output limit:", args.wheeled_limit)
    print("Source scan limit/category:", scan_limit if scan_limit > 0 else "none")
    print("File:", output_file)
    print("----------------------------")


if __name__ == "__main__":
    main()
