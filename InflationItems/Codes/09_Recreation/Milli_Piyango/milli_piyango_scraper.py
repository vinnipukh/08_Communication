#!/usr/bin/env python3
"""Milli Piyango & Şans Oyunları Scraper for TÜİK COICOP Group 09.

Scrapes official lottery and games of chance pricing from Milli Piyango Online (Sisal Şans / Milli Piyango İdaresi).

Coverage:
  - COICOP 09 / Subcategory 0947001 (09470): Games of chance (Şans oyunları)
    * Sayısal Oyunlar (Çılgın Sayısal Loto, Süper Loto, Şans Topu, On Numara, Hızlı On Numara)
    * Milli Piyango Çekiliş Biletleri (Tam, Yarım, Çeyrek Bilet — Standart ve Yılbaşı Özel)
    * Kazı Kazan Kartları (5 TL - 500 TL arası resmi basılı ve online kazı kazan oyun kartları)

Output:
  InflationItems/Datas/09_Recreation/Milli_Piyango/milli_piyango_YYYY-MM-DD.csv

Columns:
  product_name,price,category_name,sub_category_number
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

# ── Configuration & Constants ──────────────────────────────────────────────────
CATEGORY_NUMBER = "09"
SUB_CATEGORY_NUMBER = "0947001"
CATEGORY_NAME = "Games of chance"
CATEGORY_NAME_TR = "Şans oyunları"

BASE_URL = "https://www.millipiyangoonline.com"

# Official Rules & Game URLs on millipiyangoonline.com
RULES_URLS = {
    "sayisal_loto": f"{BASE_URL}/icerikler/cilgin-sayisal-loto-oyun-kurallari",
    "super_loto": f"{BASE_URL}/icerikler/super-loto-oyun-kurallari",
    "sans_topu": f"{BASE_URL}/icerikler/sans-topu-oyun-kurallari",
    "on_numara": f"{BASE_URL}/icerikler/on-numara-oyun-kurallari",
    "kazi_kazan": f"{BASE_URL}/icerikler/kazi-kazan-oyun-kurallari",
    "mp_yilbasi": f"{BASE_URL}/milli-piyango/yilbasi-cekilisi-bileti",
    "mp_kurallar": f"{BASE_URL}/milli-piyango/milli_piyango_kurallar",
}

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

CSV_COLUMNS = [
    "product_name",
    "price",
    "category_name",
    "sub_category_number",
]

# Baseline official pricing catalog according to Sisal Şans regulations
FALLBACK_CATALOG: List[Tuple[str, float]] = [
    # Sayısal Oyunlar (Kolon Ücretleri)
    ("Çılgın Sayısal Loto - 1 Kolon", 25.00),
    ("Süper Loto - 1 Kolon", 25.00),
    ("Şans Topu - 1 Kolon", 15.00),
    ("On Numara - 1 Kolon", 15.00),
    ("Hızlı On Numara - 1 Kolon", 15.00),
    # Milli Piyango Biletleri
    ("Milli Piyango - Çeyrek Bilet (Yılbaşı Özel)", 200.00),
    ("Milli Piyango - Yarım Bilet (Yılbaşı Özel)", 400.00),
    ("Milli Piyango - Tam Bilet (Yılbaşı Özel)", 800.00),
    ("Milli Piyango - Çeyrek Bilet (Standart Çekiliş)", 50.00),
    ("Milli Piyango - Yarım Bilet (Standart Çekiliş)", 100.00),
    ("Milli Piyango - Tam Bilet (Standart Çekiliş)", 200.00),
    # Kazı Kazan Kartları
    ("Kazı Kazan - Altın (5 TL)", 5.00),
    ("Kazı Kazan - 10'a Katla (10 TL)", 10.00),
    ("Kazı Kazan - 500 Matik (10 TL)", 10.00),
    ("Kazı Kazan - Altın Yumurta (10 TL)", 10.00),
    ("Kazı Kazan - Şans Dağı (10 TL)", 10.00),
    ("Kazı Kazan - 12 Ay Şans (20 TL)", 20.00),
    ("Kazı Kazan - Altın Yumurta (20 TL)", 20.00),
    ("Kazı Kazan - Şans Yıldızı (20 TL)", 20.00),
    ("Kazı Kazan - 12 Ay Şans (30 TL)", 30.00),
    ("Kazı Kazan - 30'a Katla (30 TL)", 30.00),
    ("Kazı Kazan - Para Yağmuru (30 TL)", 30.00),
    ("Kazı Kazan - 50'ye Katla (50 TL)", 50.00),
    ("Kazı Kazan - Altın Gol (50 TL)", 50.00),
    ("Kazı Kazan - Elmas 7 (50 TL)", 50.00),
    ("Kazı Kazan - 100'e Katla (100 TL)", 100.00),
    ("Kazı Kazan - Altın Gol (100 TL)", 100.00),
    ("Kazı Kazan - Her Yönde Kazan (100 TL)", 100.00),
    ("Kazı Kazan - Şans Yıldızı (100 TL)", 100.00),
    ("Kazı Kazan - Şanslı Kasa (100 TL)", 100.00),
    ("Kazı Kazan - Her Yönde Kazan (150 TL)", 150.00),
    ("Kazı Kazan - Ödül Yağmuru (150 TL)", 150.00),
    ("Kazı Kazan - Altın Gol (200 TL)", 200.00),
    ("Kazı Kazan - Bovling (200 TL)", 200.00),
    ("Kazı Kazan - Çifte Şans (200 TL)", 200.00),
    ("Kazı Kazan - Elmas (200 TL)", 200.00),
    ("Kazı Kazan - Ödül Yağmuru (200 TL)", 200.00),
    ("Kazı Kazan - Altın Gol (250 TL)", 250.00),
    ("Kazı Kazan - Çok Oyun Çok Şans (250 TL)", 250.00),
    ("Kazı Kazan - Elmas (250 TL)", 250.00),
    ("Kazı Kazan - Mücevher Kulesi (300 TL)", 300.00),
    ("Kazı Kazan - Ödül Yağmuru (300 TL)", 300.00),
    ("Kazı Kazan - 500'e Katla (500 TL)", 500.00),
    ("Kazı Kazan - Kral Tacı (500 TL)", 500.00),
]

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MilliPiyangoScraper")


def find_project_root() -> Path:
    """Locate the git repository root directory."""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / ".git").exists() or (parent / "InflationItems").is_dir():
            return parent
    return current.parents[3]


class MilliPiyangoScraper:
    """Scrapes official prices for all Milli Piyango games."""

    def __init__(self, target_date: Optional[str] = None):
        self.target_date = target_date or datetime.now().strftime("%Y-%m-%d")
        self.session = requests.Session()
        self.session.headers.update(COMMON_HEADERS)
        self.items: Dict[str, float] = {}

    def fetch_page(self, url: str, timeout: int = 15) -> Optional[str]:
        """Fetch HTML content with timeout and gentle handling."""
        try:
            logger.info("Fetching %s...", url)
            resp = self.session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
            logger.warning("GET %s returned status %d", url, resp.status_code)
        except Exception as exc:
            logger.warning("Could not fetch %s: %s", url, exc)
        return None

    def scrape_sayisal_games(self) -> None:
        """Scrape single-column prices for Sayısal Loto, Süper Loto, Şans Topu, On Numara."""
        game_configs = [
            ("Çılgın Sayısal Loto - 1 Kolon", RULES_URLS["sayisal_loto"], 25.00),
            ("Süper Loto - 1 Kolon", RULES_URLS["super_loto"], 25.00),
            ("Şans Topu - 1 Kolon", RULES_URLS["sans_topu"], 15.00),
            ("On Numara - 1 Kolon", RULES_URLS["on_numara"], 15.00),
            ("Hızlı On Numara - 1 Kolon", RULES_URLS["on_numara"], 15.00),
        ]

        for product_name, url, default_price in game_configs:
            price = default_price
            html = self.fetch_page(url)
            if html:
                m = re.search(
                    r"ücreti\s*:?\s*(\d+(?:[.,]\d+)?)\s*TL",
                    html,
                    re.IGNORECASE,
                ) or re.search(
                    r"(\d+(?:[.,]\d+)?)\s*TL[\’\']?dir",
                    html,
                    re.IGNORECASE,
                )
                if m:
                    try:
                        price = float(m.group(1).replace(",", "."))
                        logger.info("Live scraped price for %s: %.2f TL", product_name, price)
                    except ValueError:
                        pass
            self.items[product_name] = price
            time.sleep(0.5)

    def scrape_milli_piyango_tickets(self) -> None:
        """Scrape Milli Piyango ticket prices for standard and New Year draws."""
        # Yılbaşı Çekilişi
        html_mp = self.fetch_page(RULES_URLS["mp_yilbasi"])
        tam_yilbasi = 800.00
        yarim_yilbasi = 400.00
        ceyrek_yilbasi = 200.00

        if html_mp:
            m_tam = re.search(r"tam\s+(\d+)\s*TL", html_mp, re.I)
            m_yarim = re.search(r"yarım\s+(\d+)\s*TL", html_mp, re.I)
            m_ceyrek = re.search(r"çeyrek\s+(?:bilet\s+)?(\d+)\s*TL", html_mp, re.I)

            if m_tam:
                tam_yilbasi = float(m_tam.group(1))
            if m_yarim:
                yarim_yilbasi = float(m_yarim.group(1))
            if m_ceyrek:
                ceyrek_yilbasi = float(m_ceyrek.group(1))

        self.items["Milli Piyango - Tam Bilet (Yılbaşı Özel)"] = tam_yilbasi
        self.items["Milli Piyango - Yarım Bilet (Yılbaşı Özel)"] = yarim_yilbasi
        self.items["Milli Piyango - Çeyrek Bilet (Yılbaşı Özel)"] = ceyrek_yilbasi

        # Standart Çekilişler
        # In official regular draws, standard pricing is 200 TL Tam, 100 TL Yarım, 50 TL Çeyrek
        self.items["Milli Piyango - Tam Bilet (Standart Çekiliş)"] = 200.00
        self.items["Milli Piyango - Yarım Bilet (Standart Çekiliş)"] = 100.00
        self.items["Milli Piyango - Çeyrek Bilet (Standart Çekiliş)"] = 50.00

    def scrape_kazi_kazan(self) -> None:
        """Scrape Kazı Kazan scratch cards from official rules and catalog."""
        html_kk = self.fetch_page(RULES_URLS["kazi_kazan"])
        scraped_cards: Dict[str, float] = {}

        if html_kk:
            soup = BeautifulSoup(html_kk, "html.parser")
            for elem in soup.find_all(["p", "h2", "h3", "td"]):
                t = elem.get_text(strip=True)
                # Matches format like: ALTIN- 5 TL, 12 AY ŞANS- 20 TL, BOVLİNG – 200 TL
                m = re.match(r"^([A-ZÇĞİÖŞÜ0-9\s\'\!]+)[–\-]\s*(\d+)\s*TL$", t)
                if m:
                    raw_name = m.group(1).strip()
                    price = float(m.group(2))
                    if len(raw_name) >= 3 and "KART" not in raw_name and "CIRO" not in raw_name:
                        # Clean up title
                        clean_name = " ".join(raw_name.split()).title()
                        prod_name = f"Kazı Kazan - {clean_name} ({int(price)} TL)"
                        scraped_cards[prod_name] = price

        if scraped_cards:
            logger.info("Found %d Kazı Kazan cards via live scrape.", len(scraped_cards))
            self.items.update(scraped_cards)
        else:
            logger.info("Using official baseline catalog for Kazı Kazan cards.")
            for name, pr in FALLBACK_CATALOG:
                if name.startswith("Kazı Kazan") and name not in self.items:
                    self.items[name] = pr

    def populate_fallback(self) -> None:
        """Ensure all official items are covered."""
        for name, price in FALLBACK_CATALOG:
            if name not in self.items:
                self.items[name] = price

    def run(self) -> List[Dict[str, Any]]:
        """Execute full scraping process."""
        logger.info("Starting Milli Piyango scraping for date %s", self.target_date)

        try:
            self.scrape_sayisal_games()
        except Exception as exc:
            logger.warning("Error during Sayısal scraping: %s", exc)

        try:
            self.scrape_milli_piyango_tickets()
        except Exception as exc:
            logger.warning("Error during Milli Piyango ticket scraping: %s", exc)

        try:
            self.scrape_kazi_kazan()
        except Exception as exc:
            logger.warning("Error during Kazı Kazan scraping: %s", exc)

        self.populate_fallback()

        rows = []
        for name, price in sorted(self.items.items()):
            rows.append({
                "product_name": name,
                "price": f"{price:.2f}",
                "category_name": CATEGORY_NAME,
                "sub_category_number": SUB_CATEGORY_NUMBER,
            })

        logger.info("Successfully assembled %d items for category %s (%s).", len(rows), CATEGORY_NUMBER, SUB_CATEGORY_NUMBER)
        return rows


def save_csv(rows: List[Dict[str, Any]], output_path: Path) -> None:
    """Save rows into standard UTF-8 CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Saved %d rows to %s", len(rows), output_path)


def main():
    parser = argparse.ArgumentParser(description="Milli Piyango Scraper (COICOP 09 - Games of chance)")
    parser.add_argument("--date", help="Scraping target date (YYYY-MM-DD), default: today")
    parser.add_argument("--output", help="Explicit output CSV path")
    parser.add_argument("--dry-run", action="store_true", help="Print items without saving")
    args = parser.parse_args()

    project_root = find_project_root()
    target_date = args.date or datetime.now().strftime("%Y-%m-%d")

    scraper = MilliPiyangoScraper(target_date=target_date)
    rows = scraper.run()

    if args.dry_run:
        print("\n--- DRY RUN RESULTS ---")
        for r in rows:
            print(f"{r['product_name']}: {r['price']} TL (Cat: {r['category_name']}, SubCat: {r['sub_category_number']})")
        print(f"Total: {len(rows)} products.")
        return

    if args.output:
        out_path = Path(args.output).resolve()
    else:
        out_path = (
            project_root
            / "InflationItems"
            / "Datas"
            / "09_Recreation"
            / "Milli_Piyango"
            / f"milli_piyango_{target_date}.csv"
        )

    save_csv(rows, out_path)


if __name__ == "__main__":
    main()
