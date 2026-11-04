"""D&R scraper for TÜİK group 09 (stationery, toys, hobby, sport, games, books).

Output: InflationItems/Datas/09_Recreation/DR/dr_YYYY-MM-DD.csv
Columns: product_name, price, category_number, sub_category_number, product_id (D&R source ID)
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

CATEGORY_NUMBER = 9
BASE_URL = "https://www.dr.com.tr"
# The shared four columns stay first; D&R's stable product ID is the source-specific field.
CSV_COLUMNS = ["product_name", "price", "category_number", "sub_category_number", "product_id"]

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
    # Kitap kökü; kitap alt kategorileri aşağıda bir seviye derinliğe kadar taranır.
    ("Kitap", f"{BASE_URL}/kategori/kitap", "0971902"),
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
RETRY_STATUSES = (404, 429, 500, 502, 503, 504, 520)

_HERE = Path(__file__).resolve()
if len(_HERE.parents) > 4 and _HERE.parents[2].name == "Codes":
    OUT_DIR = _HERE.parents[4] / "InflationItems" / "Datas" / "09_Recreation" / "DR"
else:
    OUT_DIR = _HERE.parent / "dr_output"
CHECKPOINT_DIR = _HERE.parent / "checkpoints"

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


def fetch_html(session: requests.Session, url: str) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if attempt == MAX_RETRIES or (status is not None and status not in RETRY_STATUSES):
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

def parse_listing_page(
    soup: BeautifulSoup, name: str, page: int, pages: int
) -> list[dict[str, Any]]:
    products = parse_page(soup)
    if products:
        return products

    cards = soup.select(".prd.js-prd-item")
    unavailable = {"no", "false", "0", "yok", "out of stock"}
    if not cards or any(
        norm_space(str(parse_gtm(card).get("item_stock", ""))).lower() not in unavailable
        for card in cards
    ):
        raise RuntimeError(f"{name} page {page}/{pages} had no parseable products")

    log.info(
        "%s sayfa %d/%d yalnızca stokta olmayan fiyatlanmamış kartlar içeriyor",
        name,
        page,
        pages,
    )
    return []


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


def scrape_category(
    session: requests.Session,
    name: str,
    url: str,
    book: bool,
    page_handler: Callable[[str, str, int, list[dict[str, Any]]], None],
    completed_pages: set[tuple[str, int]],
    progress_lock: threading.Lock,
    stop_event: threading.Event,
    depth: int = 0,
    max_pages: int = MAX_PAGES,
) -> None:
    if stop_event.is_set():
        return

    first_response = fetch_html(session, url)
    url = first_response.url
    first = BeautifulSoup(first_response.text, "lxml")
    pages = min(total_pages(first), max_pages)

    if pages == 0:
        with progress_lock:
            has_completed_pages = any(scope_url == url for scope_url, _ in completed_pages)
        if has_completed_pages:
            raise RuntimeError(f"{name}: checkpointed listing no longer reports products")
        if depth >= 1:
            return
        for link in sub_links(first, url):
            if stop_event.is_set():
                return
            slug = link.rstrip("/").rsplit("/", 1)[-1].lower()
            if book and slug in BOOK_SKIP_SLUGS:
                continue
            time.sleep(PAGE_DELAY)
            scrape_category(
                session,
                f"{name} > {slug[:40]}",
                link,
                book,
                page_handler,
                completed_pages,
                progress_lock,
                stop_event,
                depth + 1,
                max_pages,
            )
        return

    page_one = (url, 1)
    with progress_lock:
        page_one_completed = page_one in completed_pages
    if page_one_completed:
        products = []
    else:
        products = parse_listing_page(first, name, 1, pages)
    if book and products:
        with SEEN_LOCK:
            duplicate_listing = not page_one_completed and all(
                p["product_id"] in SEEN_IDS for p in products
            )
            nonbook_listing = all(nonbook_root(p["path"]) for p in products)
        if duplicate_listing or nonbook_listing:
            log.info("  %s: liste atlandı (kitap dışı veya çakışan)", name)
            return

    if not page_one_completed:
        with SEEN_LOCK:
            SEEN_IDS.update(p["product_id"] for p in products)
        page_handler(name, url, 1, products)
        log.info("%s sayfa 1/%d -> %d ürün", name, pages, len(products))

    for number in range(2, pages + 1):
        key = (url, number)
        with progress_lock:
            already_completed = key in completed_pages
        if already_completed:
            continue
        if stop_event.is_set():
            return
        time.sleep(PAGE_DELAY)
        if stop_event.is_set():
            return
        response = fetch_html(session, page_url(url, number))
        page_soup = BeautifulSoup(response.text, "lxml")
        products = parse_listing_page(page_soup, name, number, pages)
        with SEEN_LOCK:
            SEEN_IDS.update(p["product_id"] for p in products)
        page_handler(name, url, number, products)
        log.info("%s sayfa %d/%d -> %d ürün", name, number, pages, len(products))


def write_csv(rows: list[dict[str, Any]], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_suffix(".csv.part")
    with part.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
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
        "product_id": pid,
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
                product_id = (r.get("product_id") or "").strip()
                if product_id:
                    seen_ids.add(product_id)
                if name and price > 0:
                    key = (norm(name), price)
                    if key not in seen_name_price:
                        seen_name_price.add(key)
                        rows.append({
                            "product_name": name,
                            "product_id": product_id,
                            "price": price,
                            "category_name": cat_name,
                            "sub_category_number": code,
                            "category_number": cat_num,
                        })
        log.info("Önceki çalışmadan %d ürün yüklendi (%s)", len(rows), out_path.name)
    except Exception as exc:
        log.warning("Önceki CSV okunamadı: %s", exc)
    return rows, seen_ids, seen_name_price

class CrawlCheckpoint:
    """SQLite journal for completed product pages; one page and its rows commit together."""

    def __init__(self, path: Path, config: dict[str, Any], seed_rows: list[dict[str, Any]], fresh: bool):
        self.path = path
        self.lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        if fresh:
            for suffix in ("", "-journal", "-wal", "-shm"):
                Path(f"{path}{suffix}").unlink(missing_ok=True)

        self.connection: sqlite3.Connection | None = sqlite3.connect(
            path, timeout=30, check_same_thread=False
        )
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS products (
                normalized_name TEXT NOT NULL,
                price REAL NOT NULL,
                product_name TEXT NOT NULL,
                product_id TEXT NOT NULL,
                category_number INTEGER NOT NULL,
                sub_category_number TEXT NOT NULL,
                PRIMARY KEY (normalized_name, price)
            );
            CREATE TABLE IF NOT EXISTS seen_ids (
                product_id TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS seen_name_prices (
                normalized_name TEXT NOT NULL,
                price REAL NOT NULL,
                PRIMARY KEY (normalized_name, price)
            );
            CREATE TABLE IF NOT EXISTS completed_pages (
                url TEXT NOT NULL,
                page INTEGER NOT NULL,
                PRIMARY KEY (url, page)
            );
            """
        )

        config_json = json.dumps(config, ensure_ascii=False, sort_keys=True)
        saved_config = self.connection.execute(
            "SELECT value FROM metadata WHERE key = 'config'"
        ).fetchone()
        if saved_config and saved_config[0] != config_json:
            self.close()
            raise RuntimeError(
                f"Checkpoint options differ from this run: {path}. "
                "Use --fresh to discard this checkpoint."
            )
        if saved_config is None:
            with self.connection:
                self.connection.execute(
                    "INSERT INTO metadata (key, value) VALUES ('config', ?)",
                    (config_json,),
                )
                self._insert_rows(seed_rows)
                self.connection.executemany(
                    "INSERT OR IGNORE INTO seen_ids VALUES (?)",
                    ((str(row["product_id"]),) for row in seed_rows if row.get("product_id")),
                )
                self.connection.executemany(
                    "INSERT OR IGNORE INTO seen_name_prices VALUES (?, ?)",
                    ((norm(row["product_name"]), float(row["price"])) for row in seed_rows),
                )

    def _insert_rows(self, rows: list[dict[str, Any]]) -> None:
        assert self.connection is not None
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO products
                (normalized_name, price, product_name, product_id, category_number, sub_category_number)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    norm(row["product_name"]),
                    float(row["price"]),
                    row["product_name"],
                    str(row.get("product_id", "")),
                    int(row["category_number"]),
                    str(row["sub_category_number"]),
                )
                for row in rows
            ),
        )

    def load(self) -> tuple[
        list[dict[str, Any]], set[str], set[tuple[str, float]], set[tuple[str, int]]
    ]:
        assert self.connection is not None
        rows = [
            {
                "product_name": name,
                "product_id": product_id,
                "price": price,
                "category_number": category,
                "sub_category_number": subcategory,
            }
            for name, product_id, price, category, subcategory in self.connection.execute(
                """
                SELECT product_name, product_id, price, category_number, sub_category_number
                FROM products ORDER BY rowid
                """
            )
        ]
        seen_ids = {
            row[0] for row in self.connection.execute("SELECT product_id FROM seen_ids")
        }
        seen_name_prices = {
            (row[0], row[1])
            for row in self.connection.execute(
                "SELECT normalized_name, price FROM seen_name_prices"
            )
        }
        completed_pages = {
            (row[0], row[1])
            for row in self.connection.execute("SELECT url, page FROM completed_pages")
        }
        return rows, seen_ids, seen_name_prices, completed_pages

    def save_page(
        self,
        url: str,
        page: int,
        product_ids: list[str],
        rows: list[dict[str, Any]],
        seen_name_prices: list[tuple[str, float]],
    ) -> None:
        assert self.connection is not None
        with self.lock, self.connection:
            self._insert_rows(rows)
            self.connection.executemany(
                "INSERT OR IGNORE INTO seen_ids VALUES (?)",
                ((product_id,) for product_id in product_ids),
            )
            self.connection.executemany(
                "INSERT OR IGNORE INTO seen_name_prices VALUES (?, ?)",
                seen_name_prices,
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO completed_pages VALUES (?, ?)", (url, page)
            )

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None


def main() -> None:
    parser = argparse.ArgumentParser(description="D&R scraper for TÜİK group 09")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Target date YYYY-MM-DD")
    parser.add_argument("--output", type=Path, default=None, help="Explicit output CSV path")
    parser.add_argument("--page-limit", type=int, default=MAX_PAGES, help="Max pages per category/subcategory")
    parser.add_argument("--only", type=str, default=None, help="Filter categories by keyword (e.g. 'Kitap', 'Kırtasiye')")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent category workers (default 1)")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Discard the page checkpoint and start a new crawl (the existing CSV remains a baseline).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    out = args.output if args.output else (OUT_DIR / f"dr_{args.date}.csv")
    categories = list(CATEGORIES)
    if args.only:
        kw = args.only.lower()
        categories = [category for category in CATEGORIES if kw in category[0].lower()]
        if not categories:
            log.warning("Filtreye uyan kategori bulunamadı ('%s'). Mevcutlar: %s", args.only, [c[0] for c in CATEGORIES])
            return

    checkpoint_path = CHECKPOINT_DIR / f"{out.stem}.sqlite3"
    config = {
        "version": 2,
        "date": args.date,
        "output": out.name,
        "categories": categories,
        "page_limit": args.page_limit,
    }
    seed_rows: list[dict[str, Any]] = []
    if args.fresh or not checkpoint_path.exists():
        seed_rows, _, _ = load_existing_csv(out)

    checkpoint = CrawlCheckpoint(checkpoint_path, config, seed_rows, args.fresh)
    rows, seen_ids, seen_name_price, completed_pages = checkpoint.load()
    SEEN_IDS.clear()
    SEEN_IDS.update(seen_ids)
    if completed_pages:
        log.info(
            "Checkpoint resumed: %d pages and %d CSV rows already saved.",
            len(completed_pages),
            len(rows),
        )

    save_lock = threading.Lock()
    stop_event = threading.Event()
    failed_categories: list[str] = []

    def process_page(
        scope_name: str,
        scope_url: str,
        page_number: int,
        products: list[dict[str, Any]],
        book_default: str | None,
    ) -> None:
        with save_lock:
            new_rows: list[dict[str, Any]] = []
            new_name_prices: list[tuple[str, float]] = []
            product_ids = [product["product_id"] for product in products]
            for product in products:
                product["book_default"] = book_default
                old_name_price_count = len(seen_name_price)
                row = process_product(product, seen_ids, seen_name_price)
                if len(seen_name_price) != old_name_price_count:
                    new_name_prices.append(
                        (norm(product["product_name"]), float(product["price"]))
                    )
                if row:
                    new_rows.append(row)

            checkpoint.save_page(
                scope_url, page_number, product_ids, new_rows, new_name_prices
            )
            completed_pages.add((scope_url, page_number))
            rows.extend(new_rows)
            log.info(
                "%s sayfa %d -> %d yeni ürün (checkpoint toplamı: %d)",
                scope_name,
                page_number,
                len(new_rows),
                len(rows),
            )

    def worker_job(name: str, url: str, book_default: str | None) -> None:
        if stop_event.is_set():
            return
        session = requests.Session()
        session.headers.update(HEADERS)

        def save_page(scope_name: str, scope_url: str, page: int, products: list[dict[str, Any]]) -> None:
            process_page(scope_name, scope_url, page, products, book_default)

        try:
            scrape_category(
                session,
                name,
                url,
                book=book_default is not None,
                page_handler=save_page,
                completed_pages=completed_pages,
                progress_lock=save_lock,
                stop_event=stop_event,
                max_pages=args.page_limit,
            )
        except Exception as exc:
            with save_lock:
                failed_categories.append(name)
            log.error("Kategori '%s' hata verdi: %s", name, exc)

    try:
        if args.workers > 1 and len(categories) > 1:
            log.info("Multi-threaded tarama başlatılıyor (workers=%d, kategoriler=%d)...", args.workers, len(categories))
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = [executor.submit(worker_job, name, url, book_default) for name, url, book_default in categories]
                try:
                    for future in as_completed(futures):
                        future.result()
                except KeyboardInterrupt:
                    stop_event.set()
                    for future in futures:
                        future.cancel()
                    raise
        else:
            for name, url, book_default in categories:
                if stop_event.is_set():
                    break
                worker_job(name, url, book_default)
    except KeyboardInterrupt:
        stop_event.set()
        log.warning(
            "Stopped after the last committed page. Progress is saved in %s; rerun the same command to resume.",
            checkpoint_path,
        )
        checkpoint.close()
        raise SystemExit(130)

    try:
        if stop_event.is_set():
            log.warning(
                "Stopped after the last committed page. Progress is saved in %s; rerun the same command to resume.",
                checkpoint_path,
            )
            raise SystemExit(130)
        if failed_categories:
            failed = ", ".join(failed_categories)
            raise SystemExit(
                f"Scrape incomplete; failed categories: {failed}. "
                f"Checkpoint retained at {checkpoint_path}; rerun the same command to resume."
            )
        if not rows:
            log.error("No data collected.")
            raise SystemExit(1)

        checkpoint.close()
        write_csv(rows, out)
        checkpoint_path.unlink(missing_ok=True)
        log.info("Tarama tamamlandı. Toplam %d satır kaydedildi: %s", len(rows), out)
    finally:
        checkpoint.close()


if __name__ == "__main__":
    main()
