#!/usr/bin/env python3
"""Scrape Zuhal Müzik products that match the configured COICOP-09 subset."""

import argparse
import csv
import html
import random
import re
import time
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import requests

BASE_URL = "https://www.zuhalmuzik.com"
USER_AGENT = "InflationResearchStudy/1.0 (academic product-price research)"
REQUEST_DELAY = 2.0
REQUEST_TIMEOUT = 25
RETRY_BASE_SECONDS = 5
CATEGORY_NUMBER = 9
CSV_COLUMNS = ["product_name", "price", "category_number", "sub_category_number", "category_name"]
ISTANBUL_TIME = ZoneInfo("Europe/Istanbul")

# Only these 24 site categories are visited. No unrelated store categories are crawled.
TARGET_SITE_CATEGORIES = [
    "Müzik Kitapları",
    "Resim ve Heykel Kitapları",
    "Hobi Kitapları",
    "Çocuk Kitapları",
    "Bilim Kitapları",
    "Çizgi Roman",
    "Ekonomi Kitapları",
    "Edebiyat Kitapları",
    "Fotoğrafçılık Kitapları",
    "Mimarlık Kitapları",
    "Psikoloji Kitapları",
    "Sinema Kitapları",
    "Tarih Kitapları",
    "Kamp Malzemeleri",
    "Kalem",
    "Defter",
    "Ofis Malzemeleri",
    "Figür",
    "Kaykay ve Scooter",
    "Puzzle",
    "Eğitici Oyunlar",
    "Oyuncak",
    "Kutu Oyunları",
    "Tasma",
]

# Output labels are COICOP labels, not the category names used by the store.
COICOP_LABELS = {
    "0921204": "Other toys",
    "0922103": "Sports equipment",
    "0932204": "Other pet products",
    "0971901": "Children's books",
    "0971902": "Other books",
    "0974001": "School notebooks",
    "0974003": "Pens and pencils",
    "0974005": "Paper for writing and drawing",
    "0974009": "Other stationery",
}

OTHER_BOOK_CATEGORIES = {
    "muzikkitaplari",
    "resimveheykelkitaplari",
    "hobikitaplari",
    "bilimkitaplari",
    "cizgiroman",
    "ekonomikitaplari",
    "edebiyatkitaplari",
    "fotografcilikkitaplari",
    "mimarlikkitaplari",
    "psikolojikitaplari",
    "sinemakitaplari",
    "tarihkitaplari",
}
GAME_CATEGORIES = {"puzzle", "egiticioyunlar", "kutuoyunlari"}

PEN_PATTERNS = (
    r"\bkalem\b", r"tukenmez kalem", r"kur[sş]un kalem", r"renkli kalem",
    r"dolma kalem", r"marker\b", r"fineliner", r"ballpoint", r"gel pen",
    r"pencil\b", r"fosforlu kalem", r"tukenmez", r"kalem seti",
)
STATIONERY_PATTERNS = (
    r"silgi", r"kalemtras", r"kalemtiras", r"atas", r"paper clip", r"makas",
    r"cetvel", r"yapistirici", r"\buhu\b", r"tipeks", r"daksil", r"zimba",
    r"bantlik", r"bant makinesi", r"kagit bant", r"sticky note", r"yapiskan.*not",
    r"not kagidi", r"notepad", r"page marker", r"sayfa isaretleyici",
    r"kitap ayraci", r"sayfa ayraci", r"kitap icin kalem klipsi", r"klips seti",
    r"klips", r"clipboard", r"dosya\b", r"kirtasiye", r"kalemlik",
    r"kalem kutusu", r"kalem cantasi", r"pencil case", r"pen loop", r"sticker",
    r"etiket", r"karton", r"defter ustu kalemlik", r"ofis kiti", r"office kit",
    r"not defteri", r"defter\b", r"notluk", r"sayfa tab", r"page tab", r"kitap standi",
)
OUTSIDE_OFFICE_PATTERNS = (
    r"\bmouse\b", r"mousepad", r"mouse pad", r"bilek destegi", r"kartvizitlik",
    r"kart standi", r"telefon kilifi", r"kitap kesesi", r"anahtarlik", r"magnet",
    r"bardak altligi", r"motivasyon sis esi", r"odaklanma sis esi", r"termos",
    r"matara", r"buyute[cç]", r"mezura", r"stres topu", r"kamera",
    r"masaustu organizer", r"masa duzenleyici", r"masaustu duzenleyici", r"mug\b",
    r"kupa\b", r"gozluk kutusu", r"tarak", r"ayna\b", r"bileklik", r"kumbar",
)
# Camping-category items that are not recreation equipment (wallets, card holders).
OUTSIDE_CAMPING_PATTERNS = (r"kartlik", r"kart kabi", r"cuzdan", r"wallet", r"rfid")
PET_PRODUCT_PATTERNS = (r"tasma", r"collar", r"leash", r"harness", r"gezdirme")
SKATEBOARD_PATTERNS = (r"kaykay", r"skateboard")
SCHOOL_NOTEBOOK_PATTERNS = (r"okul defteri", r"school notebook", r"school exercise book")
DRAWING_PAPER_PATTERNS = (
    r"resim defteri", r"cizim defteri", r"sketchbook", r"sketch pad", r"drawing pad"
)


def fold_text(value: str) -> str:
    """Lowercase and remove accents so Turkish product names compare consistently."""
    value = html.unescape(value or "").strip().casefold().replace("ı", "i")
    value = unicodedata.normalize("NFKD", value)
    return "".join(char for char in value if not unicodedata.combining(char))


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", fold_text(value))


def has_any(text: str, patterns) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def slugify(category: str) -> str:
    table = str.maketrans({
        "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
        "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    })
    value = unicodedata.normalize("NFKD", category.translate(table)).lower()
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def classify_coicop(category: str, product_name: str):
    """Return (COICOP category label, code), or None when the product is excluded."""
    site_category = normalize(category)
    name = fold_text(product_name)
    code = None

    if site_category == "cocukkitaplari":
        code = "0971901"
    elif site_category in OTHER_BOOK_CATEGORIES:
        code = "0971902"
    elif site_category in GAME_CATEGORIES or site_category in {"figur", "oyuncak"}:
        # Games, puzzles and figures are item 0921204 (same as DR), not the 09212 parent.
        code = "0921204"
    elif site_category == "kampmalzemeleri":
        if not has_any(name, OUTSIDE_CAMPING_PATTERNS):
            code = "0922103"
    elif site_category == "kaykayvescooter":
        if has_any(name, SKATEBOARD_PATTERNS):
            code = "0922103"
    elif site_category == "kalem":
        # These specific items were resolved by the previous review rules.
        if "lamy al-star mango metal kutu" in name:
            code = "0974009"
        elif "copic ciao" in name and "layer mix set" in name and "natural palette" in name:
            code = "0974003"
        elif has_any(name, PEN_PATTERNS) and not has_any(
            name, (r"kalemlik", r"kalem kutusu", r"kalem cantasi", r"pen loop")
        ):
            code = "0974003"
    elif site_category == "defter":
        if has_any(name, SCHOOL_NOTEBOOK_PATTERNS):
            code = "0974001"
        elif has_any(name, DRAWING_PAPER_PATTERNS):
            code = "0974005"
        else:
            code = "0974009"
    elif site_category == "tasma":
        if has_any(name, PET_PRODUCT_PATTERNS):
            code = "0932204"
    elif site_category == "ofismalzemeleri":
        if has_any(name, OUTSIDE_OFFICE_PATTERNS):
            if has_any(name, (
                r"kitap ayraci", r"sayfa ayraci", r"page marker",
                r"kitap icin kalem klipsi", r"yapiskan.*not", r"sticky note",
            )):
                code = "0974009"
        elif has_any(name, PEN_PATTERNS) and not has_any(
            name, (r"kalemlik", r"kalem kutusu", r"kalem cantasi", r"pen loop")
        ):
            code = "0974003"
        elif has_any(name, STATIONERY_PATTERNS):
            ambiguous_paper = (
                r"yapiskan.*not", r"sticky note", r"not kagidi", r"notepad",
                r"not defteri", r"notebook", r"defter\b", r"notluk",
            )
            if not has_any(name, ambiguous_paper):
                code = "0974009"

    if code is None:
        return None
    return COICOP_LABELS[code], code


class ProductParser(HTMLParser):
    """Read product name and price attributes from the site's AJAX HTML fragment."""
    def __init__(self):
        super().__init__()
        self.items = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        name = attributes.get("data-name")
        price = attributes.get("data-price")
        if name and price:
            self.items.append((html.unescape(name).strip(), price.strip()))


def parse_price(raw_price):
    try:
        value = Decimal(
            str(raw_price).replace("₺", "").replace("TL", "").replace(" ", "").replace(",", ".")
        )
        return f"{value:.2f}" if value > 0 else None
    except (InvalidOperation, ValueError):
        return None


def get_category_metadata(page_html: str):
    patterns = {
        "category_id": (
            r"categorybar_id\s*=\s*['\"](\d+)['\"]",
            r"categorybar_id\s*[:=]\s*(\d+)",
            r"category_id\s*[:=]\s*['\"]?(\d+)['\"]?",
        ),
        "page_size": (
            r"products_count\s*=\s*Number\(\s*['\"]?(\d+)['\"]?\s*\)",
            r"products_count\s*[:=]\s*['\"]?(\d+)['\"]?",
        ),
        "total": (
            r"products_total\s*=\s*Number\(\s*['\"]?(\d+)['\"]?\s*\)",
            r"products_total\s*[:=]\s*['\"]?(\d+)['\"]?",
        ),
    }
    found = {}
    for key, alternatives in patterns.items():
        found[key] = None
        for pattern in alternatives:
            match = re.search(pattern, page_html, re.IGNORECASE)
            if match:
                found[key] = int(match.group(1))
                break
    return found["category_id"], found["page_size"], found["total"]


def extract_items(response: requests.Response):
    payload = response.json()
    fragment = payload.get("view", "") if isinstance(payload, dict) else ""
    parser = ProductParser()
    if isinstance(fragment, str) and fragment:
        parser.feed(fragment)
    try:
        count = int(payload.get("count")) if isinstance(payload, dict) and payload.get("count") is not None else None
    except (TypeError, ValueError):
        count = None
    return parser.items, count


def find_output_directory(script_path: Path) -> Path:
    for parent in script_path.resolve().parents:
        if (parent / "InflationItems").is_dir():
            return parent / "InflationItems" / "Datas" / "09_Recreation" / "Zuhal_Muzik"

    usual_repo = Path.home() / "Documents" / "InflationResearchStudy"
    if (usual_repo / "InflationItems").is_dir():
        return usual_repo / "InflationItems" / "Datas" / "09_Recreation" / "Zuhal_Muzik"

    for parent in (Path.cwd().resolve(), *Path.cwd().resolve().parents):
        if (parent / "InflationItems").is_dir():
            return parent / "InflationItems" / "Datas" / "09_Recreation" / "Zuhal_Muzik"

    return Path.home() / "Downloads" / "Zuhal_Muzik_09"


def main():
    parser = argparse.ArgumentParser(
        description="Scrape only Zuhal Müzik categories selected for the COICOP-09 subset."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Target date for the CSV filename (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Explicit output path for the CSV",
    )
    parser.add_argument(
        "--page-limit",
        type=int,
        default=None,
        help="Max pages to fetch per category (for testing)",
    )
    parser.add_argument(
        "--test-random",
        action="store_true",
        help="Test three random target categories, fetching only the first product page of each.",
    )
    args = parser.parse_args()

    now = datetime.now(ISTANBUL_TIME)
    today = args.date if args.date else now.date().isoformat()
    if args.output:
        output_path = args.output
        output_dir = output_path.parent
    elif args.test_random:
        output_dir = Path.home() / "Downloads" / "Zuhal_Muzik_Random_Test"
        output_path = output_dir / f"zuhal_muzik_test_{today}_{now.strftime('%H-%M-%S')}.csv"
    else:
        output_dir = find_output_directory(Path(__file__))
        output_path = output_dir / f"zuhal_muzik_{today}.csv"
    output_dir.mkdir(parents=True, exist_ok=True)

    categories = TARGET_SITE_CATEGORIES.copy()
    if args.test_random:
        categories = random.sample(categories, k=min(3, len(categories)))

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
    })
    last_request_started = 0.0

    def retry_after_seconds(response, fallback):
        value = response.headers.get("Retry-After", "").strip()
        if value.isdigit():
            return max(int(value), fallback)
        if value:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return max(
                    int((retry_at - datetime.now(timezone.utc)).total_seconds()), fallback
                )
            except (TypeError, ValueError, OverflowError):
                pass
        return fallback

    def polite_get(url, **kwargs):
        nonlocal last_request_started
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        attempt = 1
        while True:
            pause = REQUEST_DELAY - (time.monotonic() - last_request_started)
            if pause > 0:
                time.sleep(pause)
            try:
                response = session.get(url, **kwargs)
                last_request_started = time.monotonic()
            except requests.RequestException as error:
                last_request_started = time.monotonic()
                wait = RETRY_BASE_SECONDS + attempt - 1
                print(f"  Connection/timeout error (attempt {attempt}): {error}")
                print(f"  Waiting {wait} seconds before retrying; no attempt limit.")
                time.sleep(wait)
                attempt += 1
                continue

            status = response.status_code
            if status == 429 or status in (408, 425) or 500 <= status <= 599:
                fallback = RETRY_BASE_SECONDS + attempt - 1
                wait = retry_after_seconds(response, fallback)
                reason = "rate limit" if status == 429 else f"temporary HTTP {status} error"
                print(f"  {reason} (attempt {attempt}); waiting {wait} seconds and retrying.")
                response.close()
                time.sleep(wait)
                attempt += 1
                continue
            return response

    # Reuse same-day output, migrating legacy rows to the four-column format and
    # dropping rows that do not belong to the configured COICOP-09 subset.
    products = {}
    removed_existing_rows = 0
    if not args.test_random and output_path.exists() and output_path.stat().st_size:
        try:
            with output_path.open("r", newline="", encoding="utf-8-sig") as existing_file:
                for row in csv.DictReader(existing_file):
                    name = (row.get("product_name") or "").strip()
                    price = parse_price(row.get("price"))
                    stored_category = (row.get("category_name") or row.get("category") or "").strip()
                    stored_code = (row.get("sub_category_number") or row.get("coicop_code") or "").strip()
                    key = normalize(name)
                    if not name or not price or not key or key in products:
                        continue

                    cat_num = row.get("category_number") or CATEGORY_NUMBER
                    if stored_code in COICOP_LABELS and stored_category == COICOP_LABELS[stored_code]:
                        products[key] = {
                            "product_name": name,
                            "price": price,
                            "category_name": stored_category,
                            "sub_category_number": stored_code,
                            "category_number": cat_num,
                        }
                    else:
                        # Legacy CSV stored the store category in the category column.
                        mapping = classify_coicop(stored_category, name)
                        if mapping:
                            label, code = mapping
                            products[key] = {
                                "product_name": name,
                                "price": price,
                                "category_name": label,
                                "sub_category_number": code,
                                "category_number": cat_num,
                            }
                        else:
                            removed_existing_rows += 1
        except (OSError, csv.Error, UnicodeError) as error:
            print(f"Could not read the existing CSV; the next save will replace it: {error}")
            products = {}

    print(f"COICOP-09 target site categories configured: {len(TARGET_SITE_CATEGORIES)}")
    print(f"Categories selected for this run: {len(categories)}")
    print(
        "TEST MODE: three random categories; only the first product page from each will be fetched."
        if args.test_random else
        "FULL MODE: all product pages in the configured target categories will be fetched."
    )
    print(f"CSV: {output_path}")
    print(f"At least {REQUEST_DELAY:.0f} seconds will separate request starts.")
    print("Temporary connection/server errors and HTTP 429 are retried with increasing waits.")
    print("HTTP 403 pages/categories are skipped; duplicate product names are not added.")
    print(f"Unique products loaded from the existing CSV: {len(products)}")
    print("CSV columns: product_name, price, category_number, sub_category_number, category_name (COICOP label).\n")

    robots = RobotFileParser()
    robots.set_url(f"{BASE_URL}/robots.txt")
    try:
        robots_response = polite_get(f"{BASE_URL}/robots.txt", headers={"Accept": "text/plain,*/*;q=0.8"})
    except requests.RequestException as error:
        print(f"Could not verify robots.txt; crawl not started: {error}")
        return

    if robots_response.status_code == 200:
        robots.parse(robots_response.text.splitlines())
        print("robots.txt rules loaded.")
    elif robots_response.status_code == 404:
        robots.parse([])
        print("robots.txt was not found (404); no published robots rules were provided.")
    else:
        print(f"robots.txt returned HTTP {robots_response.status_code}; permissions could not be verified.")
        return

    def allowed_by_robots(url):
        return robots.can_fetch(USER_AGENT, url)

    def save_products():
        temp_path = output_path.with_name(output_path.name + ".tmp")
        with temp_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(products.values())
        temp_path.replace(output_path)

    filtered_product_count = 0

    def keep_products(items, site_category):
        nonlocal filtered_product_count
        added = 0
        for name, raw_price in items:
            name = html.unescape(name or "").strip()
            price = parse_price(raw_price)
            if not name or not price:
                continue
            mapping = classify_coicop(site_category, name)
            if mapping is None:
                filtered_product_count += 1
                continue
            label, code = mapping
            key = normalize(name)
            if not key or key in products:
                continue
            products[key] = {
                "product_name": name,
                "price": price,
                "category_name": label,
                "sub_category_number": code,
                "category_number": CATEGORY_NUMBER,
            }
            added += 1
        return added

    completed_categories = 0
    stopped_by_challenge = False

    for category_index, category in enumerate(categories, start=1):
        category_url = f"{BASE_URL}/{slugify(category)}"
        print(f"[{category_index}/{len(categories)}] {category} -> {category_url}")
        if not allowed_by_robots(category_url):
            print("  robots.txt disallows this category URL; skipped.")
            continue

        try:
            category_response = polite_get(category_url)
        except requests.RequestException as error:
            print(f"  Request failed; category skipped: {error}")
            continue

        if category_response.status_code == 403:
            print("  HTTP 403 (access denied); category skipped.")
            continue
        if category_response.status_code != 200:
            print(f"  HTTP {category_response.status_code}; category skipped.")
            continue
        lowered_html = category_response.text.lower()
        if "just a moment..." in lowered_html or "cf-chl-" in lowered_html:
            print("  Verification/challenge page returned; stopping requests.")
            stopped_by_challenge = True
            break

        category_id, declared_page_size, total_products = get_category_metadata(category_response.text)
        if category_id is None or total_products is None:
            print("  Could not find category ID or product count; category skipped.")
            continue
        if total_products <= 0:
            print("  No products listed.")
            completed_categories += 1
            continue

        endpoint = f"{BASE_URL}/urun"
        ajax_headers = {
            "Referer": category_url,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
        }
        first_url = requests.Request(
            "GET", endpoint, params={"category": category_id, "page": 1}
        ).prepare().url
        if not allowed_by_robots(first_url):
            print("  robots.txt disallows product endpoint; category skipped.")
            continue
        try:
            first_response = polite_get(
                endpoint,
                params={"category": category_id, "page": 1},
                headers=ajax_headers,
            )
        except requests.RequestException as error:
            print(f"  Product request failed; category skipped: {error}")
            continue
        if first_response.status_code == 403:
            print("  Product endpoint returned HTTP 403; category skipped.")
            continue
        if first_response.status_code != 200:
            print(f"  Product endpoint returned HTTP {first_response.status_code}; category skipped.")
            continue
        try:
            first_items, api_count = extract_items(first_response)
        except (ValueError, TypeError) as error:
            print(f"  Could not parse product response ({error}); category skipped.")
            continue

        added_total = keep_products(first_items, category)
        save_products()
        page_size = declared_page_size or api_count or len(first_items)
        if not page_size:
            print("  Could not determine page size; category skipped.")
            continue

        total_pages = (total_products + page_size - 1) // page_size
        if args.test_random:
            pages_to_fetch = min(total_pages, 1)
        elif args.page_limit is not None:
            pages_to_fetch = min(total_pages, args.page_limit)
        else:
            pages_to_fetch = total_pages
        category_incomplete = False

        for page_number in range(2, pages_to_fetch + 1):
            page_url = requests.Request(
                "GET", endpoint, params={"category": category_id, "page": page_number}
            ).prepare().url
            if not allowed_by_robots(page_url):
                print(f"  robots.txt disallows page {page_number}; remaining pages skipped.")
                category_incomplete = True
                break
            try:
                response = polite_get(
                    endpoint,
                    params={"category": category_id, "page": page_number},
                    headers=ajax_headers,
                )
            except requests.RequestException as error:
                print(f"  Request failed on page {page_number}; category incomplete: {error}")
                category_incomplete = True
                break
            if response.status_code == 403:
                print(f"  Page {page_number} returned HTTP 403; remaining pages skipped.")
                category_incomplete = True
                break
            if response.status_code != 200:
                print(f"  Page {page_number} returned HTTP {response.status_code}; remaining pages skipped.")
                category_incomplete = True
                break
            try:
                items, _ = extract_items(response)
            except (ValueError, TypeError) as error:
                print(f"  Could not parse page {page_number}; remaining pages skipped: {error}")
                category_incomplete = True
                break
            added_total += keep_products(items, category)
            save_products()
            if not items:
                break

        completed_categories += 1
        pages_label = f"{pages_to_fetch}/{total_pages}" if args.test_random else str(pages_to_fetch)
        suffix = " (category incomplete)" if category_incomplete else ""
        print(
            f"  Product count: {total_products}, pages fetched/total: {pages_label}, "
            f"new unique products: {added_total}{suffix}"
        )

    save_products()
    if args.test_random and not stopped_by_challenge:
        print("\nTest run complete.")
    elif stopped_by_challenge:
        print("\nCrawl stopped after a verification page; collected products were saved.")
    else:
        print("\nCrawl complete.")
    print(f"Categories completed: {completed_categories}")
    print(f"Unique products kept in COICOP-09 subset: {len(products)}")
    print(f"Out-of-scope/uncertain products skipped from fetched pages: {filtered_product_count}")
    print(f"Out-of-scope rows removed from the existing daily CSV: {removed_existing_rows}")
    print(f"CSV: {output_path}")


if __name__ == "__main__":
    main()
