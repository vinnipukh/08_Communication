"""D&R scraper for TÜİK group 09 (stationery, toys, hobby, sport, games, books).

Output: InflationItems/Datas/09_Recreation/DR/dr_YYYY-MM-DD.csv
Columns: product_name, price, category_number, sub_category_number, category_name
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

CATEGORY_NUMBER = 9
BASE_URL = "https://www.dr.com.tr"
CSV_COLUMNS = ["product_name", "price", "category_number", "sub_category_number", "category_name"]

# TÜİK 2026 CPI (COICOP 2018) kod -> ad eşlemesi (belgedeki İngilizce adlar)
CATEGORY_NAMES = {
    "0921104": "Electronic games (game consoles, etc.)",
    "0921204": "Other toys",
    "0921207": "Ride-on wheeled toys",
    "0922102": "Home fitness equipment",
    "0922103": "Sports equipment",
    "0922107": "Special clothing and accessories for sporting activities",
    "0971102": "Test books",
    "0971103": "Textbooks",
    "0971901": "Children's books",
    "0971902": "Other books",
    "0974001": "School notebooks",
    "0974003": "Pens and pencils",
    "0974004": "Paintings for paints",
    "0974005": "Writing and drawing paper",
    "0974009": "Other stationery items",
}

CATEGORIES = [
    ("Kırtasiye", f"{BASE_URL}/kategori/kirtasiye", None),
    ("Hobi & Oyuncak", f"{BASE_URL}/kategori/hobi-oyuncak", None),
    ("Spor, Outdoor", f"{BASE_URL}/kategori/Spor-Outdoor", None),
    ("Oyun & Konsol", f"{BASE_URL}/kategori/oyun-konsol", None),
    # Kitaplar: son alan varsayılan kod; çocuk / test / ders kitabı book_code() ile ayrılır
    ("Kitap", f"{BASE_URL}/kategori/Kitap/Ders-Sinav-Kitaplari/grupno=10000000", "0971902"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": f"{BASE_URL}/",
}

REQUEST_TIMEOUT = 30
MAX_RETRIES = 4
RETRY_BACKOFF = 2.0
PAGE_DELAY = 0.5
MAX_PAGES = 5000
MAX_SUBLINKS = 40

_HERE = Path(__file__).resolve()
if len(_HERE.parents) > 4 and _HERE.parents[2].name == "Codes":
    OUT_DIR = _HERE.parents[4] / "InflationItems" / "Datas" / "09_Recreation" / "DR"
else:
    OUT_DIR = _HERE.parent / "dr_output"

log = logging.getLogger("dr09")
SEEN_IDS: set[str] = set()
SEEN_LOCK = threading.Lock()

# gtm kategori yolunda geçenler 09 dışıdır (mobilya 05, çanta 13, ayakkabı 03, 08'in kapsamı)
EXCLUDE_PATH_WORDS = ["ofis teknolojileri", "bavul", "valiz", "ofis mobilya", "mobilya", "ayakkabi",
                      "sirt cantalari", "bel cantasi", "beslenme cantasi", "termos mataralar"]

# ürün adında geçenler 09 dışıdır (termos/saklama kabı 05, çanta 13, giyim 03, ...); "mont " tam kelime
EXCLUDE_NAME_WORDS = ["termos", "matara", "saklama kab", "bardak ", "mug", "ayakkabi", "canta", "aveo",
                      "beslenme kutusu", "stanley", "tumbler", "bottle", "food jar", "victorinox", "caki",
                      "swisscard", "arac yikama", "bayrak", "bayrag", "kazak", "mont ", "yagmurluk", "tulum",
                      "hesap makine", "cerceve"]

BOOK_EXCLUDE_WORDS = ["dergi", "ajanda", "takvim", "album", "defter", "kartpostal", "poster", "puzzle", "oyun karti"]
BOOK_TEST_WORDS = ["test", "deneme", "soru banka", "tyt", "ayt", "kpss", "ales", "yds", "lgs", "yaprak test"]
# kitap vitrini site menüsünü de listeler; bu bağlantılar ve kökler kitap değildir
BOOK_SKIP_SLUGS = ("kitap", "elektronik", "hobi-oyuncak", "kirtasiye", "ev-yasam", "spor-outdoor", "muzik",
                   "ekitap", "oyun-konsol", "ofis-teknolojileri", "outdoor", "kozmetik", "anne-bebek")
BOOK_NONBOOK_ROOTS = ("elektronik", "hobi", "oyuncak", "kirtasiye", "ev ", "spor", "muzik", "oyun", "ofis",
                      "outdoor", "kozmetik", "anne")

# Sırayla denenir, ilk eşleşen yazılır; "0" = TÜİK koduna oturmaz (satır atılır)
SUBCAT_RULES = [
    ("lego", "0921204"), ("puzzle", "0921204"), ("yapboz", "0921204"),
    # oyun & konsol: konsol/oyun/kol 0921104, çevre birimleri ve mobilya kodsuz
    ("kulakli", "0"), ("mouse", "0"), ("klavye", "0"), ("direksiyon", "0"), ("hoparlor", "0"),
    ("mikrofon", "0"), ("webcam", "0"), ("koltu", "0"), ("sogutma", "0"), ("temizleme", "0"),
    ("oyuncu masa", "0"), ("dpi", "0"), ("gateron", "0"), ("sarj istasyon", "0"), ("sarj stand", "0"),
    ("charging", "0"),
    ("konsol", "0921104"), ("oyun kolu", "0921104"), ("gamepad", "0921104"), ("joystick", "0921104"),
    ("playstation", "0921104"), ("ps5", "0921104"), ("ps4", "0921104"), ("xbox", "0921104"),
    ("nintendo", "0921104"), ("switch", "0921104"), ("xsx", "0921104"),
    # tekerlekli oyuncak
    ("scooter", "0921207"), ("kaykay", "0921207"), ("uc tekerlekli", "0921207"),
    ("ride on", "0921207"), ("akulu araba", "0921207"), ("pedalli", "0921207"),
    # spor
    ("dambil", "0922102"), ("agirlik", "0922102"), ("pilates", "0922102"),
    ("yoga", "0922102"), ("direnc lastigi", "0922102"), ("fitness", "0922102"),
    ("egzersiz", "0922102"), ("step tahtasi", "0922102"),
    ("tayt", "0922107"), ("spor corap", "0922107"), ("antrenman", "0922107"),
    ("raket", "0922103"), ("futbol", "0922103"), ("basketbol", "0922103"),
    ("voleybol", "0922103"), ("masa tenisi", "0922103"), ("kamp sandalye", "0922103"),
    ("cadir", "0922103"), ("uyku tulumu", "0922103"),
    # kırtasiye
    ("defter", "0974001"),
    ("kalem canta", "0974009"), ("kalemtiras", "0974009"), ("kalem kutusu", "0974009"), ("kalemlik", "0974009"),
    ("kursun kalem", "0974003"), ("tukenmez", "0974003"), ("dolma kalem", "0974003"),
    ("roller kalem", "0974003"), ("keceli kalem", "0974003"), ("marker", "0974003"),
    ("kalem", "0974003"),
    ("suluboya", "0974004"), ("guaj", "0974004"), ("akrilik boya", "0974004"),
    ("yagli boya", "0974004"), ("pastel boya", "0974004"), ("boya", "0974004"),
    ("resim kagidi", "0974005"), ("fotokopi kagidi", "0974005"), ("a4 kagit", "0974005"),
    ("kagit", "0974005"),
    ("silgi", "0974009"), ("makas", "0974009"),
    ("yapistirici", "0974009"), ("klasor", "0974009"), ("dosya", "0974009"),
    ("cetvel", "0974009"),
    # oyuncak / hobi
    ("kutu oyunu", "0921204"), ("zeka oyunu", "0921204"), ("oyuncak", "0921204"),
    ("oyun hamuru", "0921204"),
    ("forma", "0922107"), ("legging", "0922107"),
    ("pergel", "0974009"), ("ajanda", "0974009"), ("kirtasiye seti", "0974009"),
    ("yazi tahtasi", "0974009"),
    ("firca", "0974004"), ("flip chart", "0974005"), ("kagid", "0974005"),
    ("hot wheels", "0921204"), ("maisto", "0921204"), ("mini gt", "0921204"),
    ("silverlit", "0921204"), ("ooshies", "0921204"), ("surprizamals", "0921204"),
    ("kumandali", "0921204"), ("araba", "0921204"), ("figur", "0921204"),
    ("robot", "0921204"), ("robo alive", "0921204"), ("dino", "0921204"),
    ("surpriz", "0921204"), ("monopoly", "0921204"), ("scrabble", "0921204"),
    ("uno", "0921204"), ("domino", "0921204"), ("salincak", "0921204"),
    ("kart oyunu", "0921204"), ("oyun seti", "0921204"), ("oyunu", "0921204"),
    ("oyun", "0921204"),
    ("bloknot", "0974001"),
    ("mantar pano", "0974009"), ("pano", "0974009"), ("zimba", "0974009"), ("delgec", "0974009"),
    ("bantlik", "0974009"), ("zarf acacagi", "0974009"), ("calisma pedi", "0974009"),
    ("masa aks", "0974009"), ("ofis seti", "0974009"), ("cubbie", "0974009"),
    ("perfore", "0974009"), ("delikli", "0974009"), ("para kasasi", "0974009"),
    ("sovale", "0974009"), ("tuval", "0974004"),
    ("mozaik", "0921204"), ("tebesirli", "0921204"), ("blok", "0921204"), ("block", "0921204"),
    ("collectibles", "0921204"), ("gobrix", "0921204"), ("dede", "0921204"), ("star wars", "0921204"),
    ("spider", "0921204"), ("kapsul", "0921204"), ("1 64", "0921204"), ("1 18", "0921204"),
    ("1 24", "0921204"), ("mikroskop", "0921204"),
    ("kickboard", "0922103"), ("yuzme", "0922103"), ("durbun", "0922103"), ("kulak burun", "0922103"),
    ("bralet", "0922107"), ("crop top", "0922107"),
    ("kosu bandi", "0922102"), ("kondisyon", "0922102"), ("atlama ipi", "0922102"),
    ("el yayi", "0922102"), ("titresimli", "0922102"),
    ("campout", "0922103"), ("kamp lamba", "0922103"), ("sisme yatak", "0922103"), ("piknik", "0922103"),
    ("magnetic", "0921204"), ("manyetik", "0921204"), ("knex", "0921204"), ("transformers", "0921204"),
    ("hotwheels", "0921204"), ("cca 1", "0921204"), ("cars", "0921204"), ("road rippers", "0921204"),
    ("avengers", "0921204"), ("stranger things", "0921204"), ("soktak", "0921204"), ("yapi seti", "0921204"),
    ("kimmon", "0921204"), ("blaster", "0921204"),
]


def norm_space(value: str | None) -> str:
    return " ".join((value or "").split())


def norm(s: str | None) -> str:
    """Türkçe karakterleri sadeleştirip küçük harfe çevirir."""
    s = (s or "").replace("I", "ı").replace("İ", "i").lower()
    for a, b in zip("çğıöşüâî", "cgiosuai"):
        s = s.replace(a, b)
    return " ".join(re.split(r"[^a-z0-9]+", s)).strip()


def parse_price(text: str | None) -> float | None:
    raw = norm_space(text).replace("TL", "").replace("₺", "").replace(" ", "")
    raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def fetch_html(session: requests.Session, url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.text
        except requests.RequestException as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if attempt == MAX_RETRIES or (status is not None and 400 <= status < 500 and status != 429):
                break
            wait = RETRY_BACKOFF * attempt
            log.warning("%s deneme %d/%d başarısız: %s (%.0fs sonra tekrar)", url, attempt, MAX_RETRIES, exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"Could not fetch {url}: {last_error}")


def page_url(category_url: str, page: int) -> str:
    if page <= 1:
        return category_url
    split = urlsplit(category_url)
    params = dict(parse_qsl(split.query, keep_blank_values=True))
    params["Page"] = str(page)
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(params), split.fragment))


def total_pages(soup: BeautifulSoup) -> int:
    pages = [int(a["data-number"]) for a in soup.select(".pagination a[data-number]")
             if a.get("data-number", "").strip().isdigit()]
    if pages:
        return max(pages)
    return 1 if soup.select(".prd.js-prd-item") else 0


def _match(text: str) -> str:
    padded = f" {norm(text)} "
    for kw, code in SUBCAT_RULES:
        if all(f" {part}" in padded for part in kw.split("+")):
            return code
    return "0"


def assign_subcategory(name: str, sub_text: str = "") -> str:
    """Önce ürün adına, eşleşme yoksa alt kategori adlarına bakar."""
    code = _match(name)
    return code if code != "0" else _match(sub_text)


def name_excluded(name: str, path: str = "") -> bool:
    n = f" {norm(name)} "
    p = f" {norm(path)} "
    # oyuncak seti, kalem, kamp, boya çantaları 09'da kalır; okul/sırt/bel çantası (13) dışlanır
    bag_ok = (" oyuncak" in p or " oyun set" in p or " kalem" in n or " kalem" in p
              or " kamp" in n or " kamp" in p or " boya" in n or " pastel" in n)
    toy_ok = any(f" {k}" in n for k in ("oyun", "puzzle", "lego", "figur", "barbie", "hot wheels"))
    # fotoğraf çerçevesi (05) dışlanır; pano / tahta / mozaik / defter / kalem seti kalır
    frame_ok = any(f" {k}" in n for k in ("pano", "tahta", "mozaik", "defter", "ciltli", "ypr", "yaprak",
                                           "sayfa", "kalem"))

    def skip(w: str) -> bool:
        return ((w == "canta" and bag_ok) or (w == "cerceve" and frame_ok)
                or (w in ("canta", "bardak ", "tumbler", "mug") and toy_ok))

    return any(f" {w}" in n for w in EXCLUDE_NAME_WORDS if not skip(w))


def nonbook_root(path: str) -> bool:
    root = norm(path.split(" > ")[0]) + " "
    return any(root.startswith(b) for b in BOOK_NONBOOK_ROOTS)


def book_excluded(name: str) -> bool:
    n = f" {norm(name)} "
    return any(f" {w}" in n for w in BOOK_EXCLUDE_WORDS)


def book_code(name: str, path: str, default: str) -> str:
    n = f" {norm(name)} {norm(path)} "
    if any(f" {w}" in n for w in ("cocuk", "genclik", "masal", "boyama", "bebek")):
        return "0971901"
    if any(f" {w}" in n for w in BOOK_TEST_WORDS):
        return "0971102"
    if any(f" {w}" in n for w in ("ders kitab", "okul", "ilkokul", "ortaokul", "lise", "egitim")) \
            or re.search(r"(?<!cilt )(?<!sayi )(?<!vol )\b\d{1,2}\.? ?sinif", n):
        return "0971103"
    return default


def parse_gtm(card: Any) -> dict[str, Any]:
    try:
        return json.loads(card.get("data-gtm") or "")
    except json.JSONDecodeError:
        return {}


def extract_price(card: Any) -> float | None:
    campaign = card.select_one(".campaign-price-badge")
    if campaign:
        old = campaign.select_one(".campaign-price-old")
        old_price = parse_price(old.get_text(" ", strip=True)) if old else None
        for span in reversed(campaign.select(".campaign-price span")):
            if "campaign-price-old" in (span.get("class") or []):
                continue
            price = parse_price(span.get_text(" ", strip=True))
            if price is not None:
                return price
        return old_price
    price_el = card.select_one(".prd-price[data-price]")
    if price_el is not None:
        try:
            return float(price_el.get("data-price", "").strip())
        except ValueError:
            return parse_price(price_el.get_text(" ", strip=True))
    return None


def parse_card(card: Any) -> dict[str, Any] | None:
    gtm = parse_gtm(card)
    price = extract_price(card)

    name = norm_space(str(gtm.get("item_name", "")))
    if not name:
        img = card.select_one("img[alt]")
        name = norm_space(img.get("alt")) if img is not None else ""
    if not name:
        name = norm_space(card.get_text(" ", strip=True))

    pid = str(card.get("data-id") or gtm.get("item_id") or "").strip()
    if not pid or price is None or not name:
        return None

    parts = [norm_space(str(gtm.get(k, ""))) for k in ("item_category", "item_category2", "item_category3")]
    return {
        "product_id": pid,
        "product_name": name,
        "price": price,
        "path": " > ".join(p for p in parts if p),
        "sub_text": " ".join(p for p in parts[1:] if p),
    }


def parse_page(soup: BeautifulSoup) -> list[dict[str, Any]]:
    parsed = (parse_card(card) for card in soup.select(".prd.js-prd-item"))
    return [p for p in parsed if p is not None]


def sub_links(soup: BeautifulSoup, current_url: str) -> list[str]:
    """Vitrin sayfasındaki alt kategori bağlantıları."""
    cur = urlsplit(current_url).path.rstrip("/").lower()
    found: list[str] = []
    for sel in ("a.dr-flex-between[href]", "a[href^='/kategori/']"):
        for a in soup.select(sel):
            href = a.get("href", "").strip()
            if not href.startswith("/kategori/"):
                continue
            path = urlsplit(href).path.rstrip("/").lower()
            full = BASE_URL + href
            if path == cur or full in found:
                continue
            found.append(full)
        if found:
            break
    return found[:MAX_SUBLINKS]


def scrape_category(session: requests.Session, name: str, url: str, book: bool = False,
                    depth: int = 0, max_pages: int = MAX_PAGES) -> list[dict[str, Any]]:
    first = BeautifulSoup(fetch_html(session, url), "lxml")
    pages = min(total_pages(first), max_pages)

    if pages == 0:
        # vitrin sayfası: alt kategorilere in (en fazla bir seviye)
        if depth >= 1:
            return []
        out: list[dict[str, Any]] = []
        for link in sub_links(first, url):
            slug = link.rstrip("/").rsplit("/", 1)[-1].lower()
            if book and slug in BOOK_SKIP_SLUGS:
                continue
            time.sleep(PAGE_DELAY)
            try:
                out.extend(scrape_category(session, f"{name} > {slug[:40]}", link, book, depth + 1, max_pages=max_pages))
            except Exception as exc:
                log.error("%s hata verdi: %s", link, exc)
        return out

    products = parse_page(first)
    log.info("%s sayfa 1/%d -> %d ürün", name, pages, len(products))
    if book and products:
        with SEEN_LOCK:
            # kitap dışı ya da ilk sayfası tamamen daha önce alınmış liste atlanır
            if all(nonbook_root(p["path"]) for p in products) or all(p["product_id"] in SEEN_IDS for p in products):
                log.info("  liste atlandı (kitap dışı veya çakışan)")
                return []
    with SEEN_LOCK:
        SEEN_IDS.update(p["product_id"] for p in products)

    for n in range(2, pages + 1):
        time.sleep(PAGE_DELAY)
        try:
            got = parse_page(BeautifulSoup(fetch_html(session, page_url(url, n)), "lxml"))
        except RuntimeError as exc:
            log.error("%s sayfa %d atlandı: %s", name, n, exc)
            continue
        log.info("%s sayfa %d/%d -> %d ürün", name, n, pages, len(got))
        products.extend(got)
        with SEEN_LOCK:
            SEEN_IDS.update(p["product_id"] for p in got)
    return products


def write_csv(rows: list[dict[str, Any]], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_suffix(".csv.part")
    with part.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(part, out)


def process_product(
    p: dict[str, Any],
    seen_ids: set[str],
    seen_name_price: set[tuple[str, float]],
) -> dict[str, Any] | None:
    pid = p.get("product_id", "")
    if pid in seen_ids:
        return None
    seen_ids.add(pid)

    is_book = p.get("book_default") is not None
    if is_book:
        if book_excluded(p["product_name"]) or nonbook_root(p["path"]):
            return None
    elif (any(w in norm(p["path"]) for w in EXCLUDE_PATH_WORDS)
          or name_excluded(p["product_name"], p["path"])):
        return None

    # aynı ad + aynı fiyat (satıcı varyantları) tek satır
    key = (norm(p["product_name"]), p["price"])
    if key in seen_name_price:
        return None
    seen_name_price.add(key)

    code = (book_code(p["product_name"], p["path"], p["book_default"]) if is_book
            else assign_subcategory(p["product_name"], p["sub_text"]))
    if code == "0":
        return None

    return {
        "product_name": p["product_name"],
        "price": p["price"],
        "category_name": CATEGORY_NAMES.get(code, ""),
        "sub_category_number": code,
        "category_number": CATEGORY_NUMBER,
    }


def load_existing_csv(out_path: Path) -> tuple[list[dict[str, Any]], set[str], set[tuple[str, float]]]:
    rows: list[dict[str, Any]] = []
    seen_name_price: set[tuple[str, float]] = set()
    seen_ids: set[str] = set()
    if not out_path.exists() or out_path.stat().st_size == 0:
        return rows, seen_ids, seen_name_price
    try:
        with out_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                name = (r.get("product_name") or "").strip()
                try:
                    price = float(r.get("price", "0"))
                except ValueError:
                    continue
                code = (r.get("sub_category_number") or "").strip()
                cat_name = (r.get("category_name") or "").strip()
                cat_num = r.get("category_number") or CATEGORY_NUMBER
                if name and price > 0:
                    key = (norm(name), price)
                    if key not in seen_name_price:
                        seen_name_price.add(key)
                        rows.append({
                            "product_name": name,
                            "price": price,
                            "category_name": cat_name,
                            "sub_category_number": code,
                            "category_number": cat_num,
                        })
        log.info("Önceki çalışmadan %d ürün yüklendi (%s)", len(rows), out_path.name)
    except Exception as exc:
        log.warning("Önceki CSV okunamadı: %s", exc)
    return rows, seen_ids, seen_name_price


def main() -> None:
    parser = argparse.ArgumentParser(description="D&R scraper for TÜİK group 09")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Target date YYYY-MM-DD")
    parser.add_argument("--output", type=Path, default=None, help="Explicit output CSV path")
    parser.add_argument("--page-limit", type=int, default=MAX_PAGES, help="Max pages per category/subcategory")
    parser.add_argument("--only", type=str, default=None, help="Filter categories by keyword (e.g. 'Kitap', 'Kırtasiye')")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent category workers (default 1)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    out = args.output if args.output else (OUT_DIR / f"dr_{args.date}.csv")
    rows, seen_ids, seen_name_price = load_existing_csv(out)

    categories = CATEGORIES
    if args.only:
        kw = args.only.lower()
        categories = [c for c in CATEGORIES if kw in c[0].lower()]
        if not categories:
            log.warning("Filtreye uyan kategori bulunamadı ('%s'). Mevcutlar: %s", args.only, [c[0] for c in CATEGORIES])
            return

    save_lock = threading.Lock()

    def process_and_save(got_products: list[dict[str, Any]], cat_name: str):
        with save_lock:
            added = 0
            for p in got_products:
                row = process_product(p, seen_ids, seen_name_price)
                if row:
                    rows.append(row)
                    added += 1
            if rows:
                write_csv(rows, out)
            log.info("Kategori '%s' bitti -> +%d yeni ürün eklendi (Toplam kaydedilen: %d satır)", cat_name, added, len(rows))

    def worker_job(name: str, url: str, book_default: str | None):
        session = requests.Session()
        session.headers.update(HEADERS)
        try:
            got = scrape_category(session, name, url, book=book_default is not None, max_pages=args.page_limit)
            for p in got:
                p["book_default"] = book_default
            process_and_save(got, name)
        except Exception as exc:
            log.error("Kategori '%s' hata verdi: %s", name, exc)

    if args.workers > 1 and len(categories) > 1:
        log.info("Multi-threaded tarama başlatılıyor (workers=%d, kategoriler=%d)...", args.workers, len(categories))
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(worker_job, name, url, bdef) for name, url, bdef in categories]
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as exc:
                    log.error("Worker hatası: %s", exc)
    else:
        for name, url, book_default in categories:
            worker_job(name, url, book_default)

    if not rows:
        log.error("No data collected.")
        sys.exit(1)

    log.info("Tarama tamamlandı. Toplam %d satır kaydedildi: %s", len(rows), out)


if __name__ == "__main__":
    main()
