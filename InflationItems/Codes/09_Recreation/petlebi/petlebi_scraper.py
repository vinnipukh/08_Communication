import argparse
import csv
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("PetlebiScraper")

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = next((p for p in BASE_DIR.parents if (p / ".git").exists()), BASE_DIR)
DATA_DIR = PROJECT_ROOT / "InflationItems" / "Datas" / "09_Recreation" / "Petlebi"

BASE_URL = "https://www.petlebi.com"
CATEGORY_NUMBER = "9"
PET_FOOD_SUB_CATEGORY_NUMBER = "0932201"
OTHER_PET_PRODUCTS_SUB_CATEGORY_NUMBER = "0932204"

DEFAULT_FOOD_LIMIT = 5000
DEFAULT_OTHER_LIMIT = 5000
DEFAULT_FOOD_SCAN_LIMIT_PER_CATEGORY = 1000
DEFAULT_OTHER_SCAN_LIMIT_PER_CATEGORY = 1000
DEFAULT_MAX_PAGES = 100
DEFAULT_DELAY = 0.65
DEFAULT_MIN_PRICE = 30.0

FOOD_CATEGORIES = {
    "cat_dry_food": "https://www.petlebi.com/kedi-mamasi",
    "cat_wet_food": "https://www.petlebi.com/kedi-konserve-mamasi",
    "cat_treats": "https://www.petlebi.com/kedi-odul-mamasi",
    "dog_dry_food": "https://www.petlebi.com/kopek-mamasi",
    "dog_wet_food": "https://www.petlebi.com/kopek-konserve-mamasi",
    "dog_treats": "https://www.petlebi.com/kopek-odul-mamasi",
    "dog_bones": "https://www.petlebi.com/kopek-kemigi",
    "fish_food": "https://www.petlebi.com/balik-yemleri",
    "shrimp_food": "https://www.petlebi.com/karides-yemi",
    "turtle_food": "https://www.petlebi.com/kaplumbaga-yemleri",
    "bird_food": "https://www.petlebi.com/kus-yemleri",
    "bird_treats": "https://www.petlebi.com/kus-krakeri-ve-odulleri",
    "rabbit_food": "https://www.petlebi.com/tavsan-yemi",
    "hamster_food": "https://www.petlebi.com/hamster-yemi",
    "guinea_pig_food": "https://www.petlebi.com/guinea-pig-yemi"
}


OTHER_CATEGORIES = {

    "cat_litter": "https://www.petlebi.com/kedi-kumu",
    "cat_toys": "https://www.petlebi.com/kedi-oyuncaklari",
    "cat_care": "https://www.petlebi.com/kedi-bakim-urunleri",
    "cat_bowls": "https://www.petlebi.com/kedi-mama-ve-su-kabi",
    "cat_toilets": "https://www.petlebi.com/kedi-tuvaleti",
    "cat_grooming": "https://www.petlebi.com/kedi-tarak-ve-fircalari",
    "cat_scratchers": "https://www.petlebi.com/kedi-tirmalama-tahtasi",
    "cat_collars": "https://www.petlebi.com/kedi-tasmasi",
    "cat_carriers": "https://www.petlebi.com/kedi-tasima-cantasi",
    "cat_beds": "https://www.petlebi.com/kedi-yataklari",


    "dog_care": "https://www.petlebi.com/kopek-bakim-urunleri",
    "dog_toys": "https://www.petlebi.com/kopek-oyuncaklari",
    "dog_bowls": "https://www.petlebi.com/kopek-mama-ve-su-kabi",
    "dog_collars": "https://www.petlebi.com/kopek-tasmalari-kayislari",
    "dog_beds": "https://www.petlebi.com/kopek-yataklari",
    "dog_carriers": "https://www.petlebi.com/kopek-tasima-cantasi",
    "dog_grooming": "https://www.petlebi.com/kopek-tarak-ve-fircasi",
    "dog_clothes": "https://www.petlebi.com/kopek-elbiseleri",
    "dog_training": "https://www.petlebi.com/egitim-ekipmani",
    "dog_car": "https://www.petlebi.com/kopek-araba-urunleri",


    "aquarium_filters": "https://www.petlebi.com/akvaryum-filtreleri",
    "aquarium_motors": "https://www.petlebi.com/akvaryum-motorlari",
    "aquarium_equipment": "https://www.petlebi.com/akvaryum-ekipmanlari",
    "aquarium_accessories": "https://www.petlebi.com/akvaryum-aksesuarlari-ve-kumlari",
    "aquarium_chemistry": "https://www.petlebi.com/akvaryum-kimyasi-ve-bakimi",


    "bird_toys": "https://www.petlebi.com/kus-oyuncaklari",
    "bird_cage_equipment": "https://www.petlebi.com/kus-kafesi-ekipmanlari",
    "bird_care": "https://www.petlebi.com/kus-bakim-urunleri",


    "hamster_cage_equipment": "https://www.petlebi.com/hamster-kafes-ve-ekipmanlari",
    "guinea_pig_cage_equipment": "https://www.petlebi.com/guinea-pig-kafes-ve-ekipmanlari",
}

FOOD_NAME_WORDS = (
    "mama",
    "yem",
    "konserve",
    "kraker",
    "ödül",
    "odul",
    "kuru yonca",
    "kemik",
    "çiğneme kemiği",
    "cigneme kemigi"
)

NON_FOOD_CONTEXT_WORDS = (
    "mama kab",
    "mama ve su kab",
    "mama su kab",
    "mama ölçü",
    "mama olcu",
    "mama saklama",
    "mama kaşı",
    "mama kasi",
    "mama mat",
    "mama stand",
    "mama hazne",
    "mama dispenser",
    "mama kutu",
    "mama oyunc",
    "mama taşıma",
    "mama tasima",
    "ödül oyunc",
    "odul oyunc",
    "kemik oyunc",
    "oyuncak kemik",
    "kauçuk kemik",
    "kaucuk kemik",
    "plastik kemik",
    "su kab",
    "yem kab",
    "yemlik",
    "yemliğ",
    "yem hazne",
    "yem dispenser"
)

CARD_MARKERS = (
    "sepete ekle",
    "stokta yok",
    "gelince haber ver"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Cache-Control": "no-cache"
}

PRICE_PATTERN = re.compile(r"\d[\d.]*?(?:,\d{1,2})?\s*TL", re.IGNORECASE)
PRODUCT_PATH_PATTERN = re.compile(
    r"/(?:kedi|kopek|akvaryum|kus|kemirgen)-urunleri/[^?#]+\.html$",
    re.IGNORECASE
)


def build_session():
    session = requests.Session()
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    return session


def add_page_number(url, page_number):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if page_number > 1:
        query["page"] = str(page_number)
    else:
        query.pop("page", None)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def fetch_html(session, url, timeout=40):
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def normalize_text(text):
    return " ".join(str(text).replace("\xa0", " ").split()).strip()


def canonical_product_key(name):
    text = normalize_text(name).casefold()
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    text = text.replace("_", " ")
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\b(\d+(?:\s+\d+)?)\s*(kg|gr|g|ml|lt|l)\b", r"\1\2", text)
    return text


def looks_like_food(name):
    text = normalize_text(name).casefold()
    if any(word in text for word in NON_FOOD_CONTEXT_WORDS):
        return False
    return any(word in text for word in FOOD_NAME_WORDS)


def convert_price(text):
    raw = re.sub(r"[^\d.,]", "", normalize_text(text))
    if not raw:
        return None
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    elif "." in raw:
        left, right = raw.rsplit(".", 1)
        if len(right) == 3:
            raw = left + right
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def normalize_product_url(href):
    if not href:
        return None
    absolute = urljoin(BASE_URL, href)
    parts = urlsplit(absolute)
    if parts.netloc.casefold() not in {"www.petlebi.com", "petlebi.com"}:
        return None
    path = parts.path.rstrip("/")
    if not PRODUCT_PATH_PATTERN.search(path):
        return None
    return urlunsplit(("https", "www.petlebi.com", path, "", ""))


def product_urls_in(container):
    urls = set()
    for link in container.find_all("a", href=True):
        url = normalize_product_url(link.get("href"))
        if url:
            urls.add(url)
    return urls


def extract_name_from_link(link):
    candidates = []
    for attr in ("title", "aria-label"):
        value = link.get(attr)
        if value:
            candidates.append(normalize_text(value))
    image = link.find("img")
    if image and image.get("alt"):
        candidates.append(normalize_text(image.get("alt")))
    text = normalize_text(link.get_text(" ", strip=True))
    if text:
        candidates.append(text)
    cleaned = []
    for value in candidates:
        if len(value) < 4:
            continue
        if PRICE_PATTERN.search(value):
            continue
        low = value.casefold()
        if low in {"hızlı teslimat", "kargo bedava", "çok satan", "sepete ekle"}:
            continue
        cleaned.append(value)
    if not cleaned:
        return None
    return max(cleaned, key=len)


def extract_name(container, product_url):
    best = None
    for link in container.find_all("a", href=True):
        if normalize_product_url(link.get("href")) != product_url:
            continue
        candidate = extract_name_from_link(link)
        if candidate and (best is None or len(candidate) > len(best)):
            best = candidate
    if best:
        return best
    for selector in ("h2", "h3", "h4", "[class*='product-name']", "[class*='product-title']"):
        for element in container.select(selector):
            value = normalize_text(element.get_text(" ", strip=True))
            if len(value) >= 4 and not PRICE_PATTERN.search(value):
                return value
    return None


def extract_price(container):
    text = normalize_text(container.get_text(" ", strip=True))
    matches = PRICE_PATTERN.findall(text)
    prices = []
    for match in matches:
        value = convert_price(match)
        if value is not None and value not in prices:
            prices.append(value)
    if not prices:
        return None
    return min(prices)


def find_product_container(link):
    current = link
    for _ in range(14):
        current = current.parent
        if current is None:
            return None
        text = normalize_text(current.get_text(" ", strip=True))
        low = text.casefold()
        if "tl" not in low:
            continue
        if not any(marker in low for marker in CARD_MARKERS):
            continue
        urls = product_urls_in(current)
        if len(urls) != 1:
            continue
        if len(text) > 2500:
            continue
        return current
    return None


def extract_total_results(html):
    soup = BeautifulSoup(html, "html.parser")
    text = normalize_text(soup.get_text(" ", strip=True))
    match = re.search(r"için\s*([\d.]+)\s*ürün\s*listeleniyor", text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1).replace(".", ""))
    except ValueError:
        return None


def parse_products(html):
    soup = BeautifulSoup(html, "html.parser")
    items = {}
    card_ids = set()
    candidate_links = 0

    for link in soup.find_all("a", href=True):
        product_url = normalize_product_url(link.get("href"))
        if not product_url:
            continue
        candidate_links += 1
        if product_url in items:
            continue
        container = find_product_container(link)
        if container is None:
            continue
        container_id = id(container)
        if container_id in card_ids and product_url in items:
            continue
        name = extract_name(container, product_url)
        price = extract_price(container)
        if not name or price is None:
            continue
        card_ids.add(container_id)
        items[product_url] = {
            "product_name": name,
            "price": price,
            "_product_url": product_url
        }

    return list(items.values()), candidate_links


def scrape_category(session, category_name, category_url, scan_limit, max_pages, delay):
    results = []
    seen_urls = set()
    expected_total = None

    logger.info(
        "Starting category: %s | scan_limit=%s | max_pages=%d",
        category_name,
        scan_limit if scan_limit > 0 else "none",
        max_pages
    )

    for page_number in range(1, max_pages + 1):
        url = add_page_number(category_url, page_number)
        logger.info("%s - page %d", category_name, page_number)

        try:
            html = fetch_html(session, url)
        except Exception as exc:
            logger.warning("%s page %d failed: %s", category_name, page_number, exc)
            break

        if expected_total is None:
            expected_total = extract_total_results(html)
            if expected_total is not None:
                logger.info("%s: site reports %d products", category_name, expected_total)

        products, candidate_links = parse_products(html)

        if candidate_links > 0 and not products:
            logger.warning(
                "%s page %d: found %d product-like links but no valid product cards; page structure may have changed",
                category_name,
                page_number,
                candidate_links
            )
            break

        if not products:
            logger.info("%s page %d: no listing products found, stopping", category_name, page_number)
            break

        new_count = 0
        for product in products:
            product_url = product["_product_url"]
            if product_url in seen_urls:
                continue
            seen_urls.add(product_url)
            results.append(product)
            new_count += 1
            if scan_limit > 0 and len(results) >= scan_limit:
                break

        logger.info(
            "%s page %d: listing_products=%d, new=%d, scanned=%d%s",
            category_name,
            page_number,
            len(products),
            new_count,
            len(results),
            f"/{expected_total}" if expected_total is not None else ""
        )

        if scan_limit > 0 and len(results) >= scan_limit:
            break
        if expected_total is not None and len(seen_urls) >= expected_total:
            break
        if new_count == 0:
            break

        time.sleep(delay)

    logger.info("%s: collected %d unique listing products", category_name, len(results))
    return results


def round_robin_unique(
    category_results,
    total_limit,
    exclude_urls=None,
    exclude_keys=None,
    exclude_food_names=False,
    min_price=0.0
):
    exclude_urls = exclude_urls or set()
    exclude_keys = exclude_keys or set()
    selected = []
    seen_urls = set()
    seen_keys = set()
    positions = {name: 0 for name in category_results}
    names = list(category_results)

    while names:
        progressed = False
        next_names = []

        for category_name in names:
            items = category_results[category_name]
            pos = positions[category_name]

            while pos < len(items):
                item = items[pos]
                pos += 1
                product_url = item["_product_url"]

                if product_url in exclude_urls or product_url in seen_urls:
                    continue
                if exclude_food_names and looks_like_food(item["product_name"]):
                    continue
                if float(item["price"]) < min_price:
                    continue

                dedupe_key = canonical_product_key(item["product_name"])
                if not dedupe_key:
                    continue
                if dedupe_key in exclude_keys or dedupe_key in seen_keys:
                    continue

                seen_urls.add(product_url)
                seen_keys.add(dedupe_key)
                selected.append(item)
                progressed = True
                break

            positions[category_name] = pos
            if pos < len(items):
                next_names.append(category_name)

            if total_limit > 0 and len(selected) >= total_limit:
                return selected

        if not progressed:
            break
        names = next_names

    return selected


def dedupe_rows(data):
    unique = []
    seen_urls = set()
    seen_keys = set()

    for item in data:
        product_url = item.get("_product_url")
        product_key = canonical_product_key(item["product_name"])

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
    output_file = DATA_DIR / f"petlebi_{date_str}.csv"
    with open(output_file, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["product_name", "price", "category_number", "sub_category_number"])
        for item in sorted(data, key=lambda x: (x["sub_category_number"], x["product_name"].casefold())):
            writer.writerow([
                item["product_name"],
                f'{item["price"]:.2f}',
                item["category_number"],
                item["sub_category_number"]
            ])
    return output_file


def main():
    parser = argparse.ArgumentParser(description="Petlebi balanced scraper")
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--food-limit", type=int, default=DEFAULT_FOOD_LIMIT)
    parser.add_argument("--other-limit", type=int, default=DEFAULT_OTHER_LIMIT)
    parser.add_argument(
        "--food-scan-limit-per-category",
        type=int,
        default=DEFAULT_FOOD_SCAN_LIMIT_PER_CATEGORY
    )
    parser.add_argument(
        "--other-scan-limit-per-category",
        type=int,
        default=DEFAULT_OTHER_SCAN_LIMIT_PER_CATEGORY
    )
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--min-price", type=float, default=DEFAULT_MIN_PRICE)
    args = parser.parse_args()

    if args.food_limit < 0 or args.other_limit < 0:
        parser.error("--food-limit and --other-limit must be >= 0")
    if args.food_scan_limit_per_category < 0 or args.other_scan_limit_per_category < 0:
        parser.error("scan limits must be >= 0")
    if args.max_pages < 1:
        parser.error("--max-pages must be >= 1")
    if args.delay < 0:
        parser.error("--delay must be >= 0")
    if args.min_price < 0:
        parser.error("--min-price must be >= 0")

    date_str = args.date or datetime.today().strftime("%Y-%m-%d")
    session = build_session()

    food_by_category = {}
    for category_name, category_url in FOOD_CATEGORIES.items():
        food_by_category[category_name] = scrape_category(
            session,
            category_name,
            category_url,
            args.food_scan_limit_per_category,
            args.max_pages,
            args.delay
        )

    food_registry = {
        item["_product_url"]
        for items in food_by_category.values()
        for item in items
    }
    food_registry_keys = {
        canonical_product_key(item["product_name"])
        for items in food_by_category.values()
        for item in items
        if canonical_product_key(item["product_name"])
    }

    food_selected = round_robin_unique(
        food_by_category,
        args.food_limit,
        min_price=args.min_price
    )

    other_by_category = {}
    for category_name, category_url in OTHER_CATEGORIES.items():
        other_by_category[category_name] = scrape_category(
            session,
            category_name,
            category_url,
            args.other_scan_limit_per_category,
            args.max_pages,
            args.delay
        )

    other_selected = round_robin_unique(
        other_by_category,
        args.other_limit,
        exclude_urls=food_registry,
        exclude_keys=food_registry_keys,

        exclude_food_names=False,
        min_price=args.min_price
    )

    rows = []

    for item in food_selected:
        rows.append({
            "product_name": item["product_name"],
            "price": item["price"],
            "category_number": CATEGORY_NUMBER,
            "sub_category_number": PET_FOOD_SUB_CATEGORY_NUMBER,
            "_product_url": item["_product_url"]
        })

    for item in other_selected:
        rows.append({
            "product_name": item["product_name"],
            "price": item["price"],
            "category_number": CATEGORY_NUMBER,
            "sub_category_number": OTHER_PET_PRODUCTS_SUB_CATEGORY_NUMBER,
            "_product_url": item["_product_url"]
        })

    rows_before_dedupe = len(rows)
    rows = dedupe_rows(rows)
    duplicates_removed = rows_before_dedupe - len(rows)

    if not rows:
        logger.error("No products scraped")
        sys.exit(1)

    output_file = save_to_csv(rows, date_str)

    print()
    print("----------------------------")
    print("Scraping completed.")
    print("Pet food:", len(food_selected))
    print("Other pet products:", len(other_selected))
    print("Total unique products:", len(rows))
    print("Final duplicates removed:", duplicates_removed)
    print("Food registry URLs:", len(food_registry))
    print("Food registry product keys:", len(food_registry_keys))
    print("Food output limit:", args.food_limit)
    print("Other output limit:", args.other_limit)
    print("Other source categories:", len(OTHER_CATEGORIES))
    print("Other raw category products:", sum(len(items) for items in other_by_category.values()))
    print("Minimum accepted price:", f"{args.min_price:.2f} TL")
    print("File:", output_file)
    print("----------------------------")


if __name__ == "__main__":
    main()
