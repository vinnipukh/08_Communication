#!/usr/bin/env python3
"""MACFit Gym & Sports Membership Scraper for TÜİK COICOP Group 09.

Scrapes official membership pricing for MACFit, MAC/One, MACStudio, and MACRaw
sports clubs across Turkey directly from Mars Athletic / MACFit portal gateway APIs.

Coverage:
  - 0946201 Payments for sports facilities (Sportif tesislere yapılan ödemeler: üyelik, kiralama vb.)
    Group: 09 (Eğlence, dinlence, spor ve kültür / Recreation, sport and culture)
    Subgroup: 0946 (Eğlence, dinlence ve spor hizmetleri / Recreational and sporting services)
    Class: 09462 (Spor faaliyetlerine katılım / Services associated with the practice of sports)

Pricing Models Collected per Club:
  1. 12 Ay Taahhütlü Aylık Üyelik (12-month committed monthly membership)
  2. Taahhütsüz Aylık Üyelik (Monthly flexible no-commitment membership)
  3. Peşin Yıllık Üyelik - Aylık Karşılığı (Annual upfront membership - monthly equivalent)
  4. Peşin Yıllık Üyelik - Yıllık Toplam Bedel (Annual upfront membership - full annual cost)
  5. Kayıt Bedeli / Giriş Ücreti (One-time club enrollment fee, if applicable)

Output:
  InflationItems/Datas/09_Recreation/MACFit/macfit_YYYY-MM-DD.csv

Columns:
  product_name,price,category_number,sub_category_number
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

import requests

# ── Configuration & Constants ──────────────────────────────────────────────────
CATEGORY_NUMBER = 9
SUB_CATEGORY_NUMBER = "0946201"
CATEGORY_NAME = "Payments for sports facilities (membership, rental, etc.)"
CATEGORY_NAME_TR = "Sportif tesislere yapılan ödemeler (üyelik, kiralama vb.)"

GATEWAY_BASE_URL = "https://portal-gateway.marsathletic.com/"
CLUBS_ENDPOINT = f"{GATEWAY_BASE_URL}Club/get-clubs"
PLAN_RULES_ENDPOINT = f"{GATEWAY_BASE_URL}PaymentPlanRule/new-member-get-renewal-plans"

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://portal.macfit.com",
    "Referer": "https://portal.macfit.com/",
}

# Only the four shared columns are written. Other per-product fields are used inside the run
# (deduplication, naming) but are not saved.
CSV_COLUMNS = ["product_name", "price", "category_number", "sub_category_number"]

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MACFitScraper")


def find_project_root() -> Path:
    """Locate the git repository root directory."""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / ".git").exists() or (parent / "InflationItems").is_dir():
            return parent
    return current.parents[3]


RETRY_STATUSES = (429, 500, 502, 503, 504, 520)
# Eight concurrent plan requests produced repeated gateway HTTP 520 responses in a live run.
DEFAULT_MAX_WORKERS = 1


def request_get_json(
    url: str,
    timeout: int = 15,
    retries: int = 3,
    retry_statuses: Tuple[int, ...] = RETRY_STATUSES,
) -> Optional[Dict[str, Any]]:
    """Execute GET request with retry and JSON response parsing."""
    for attempt in range(1, retries + 1):
        try:
            if curl_requests is not None:
                resp = curl_requests.get(
                    url,
                    headers=COMMON_HEADERS,
                    impersonate="chrome",
                    timeout=timeout,
                )
            else:
                resp = requests.get(
                    url,
                    headers=COMMON_HEADERS,
                    timeout=timeout,
                )

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code in retry_statuses and attempt < retries:
                wait_sec = attempt * 5
                logger.warning("GET %s returned HTTP %d, retrying in %ds...", url, resp.status_code, wait_sec)
                time.sleep(wait_sec)
            else:
                logger.error("GET %s failed with HTTP %d", url, resp.status_code)
                return None
        except Exception as exc:
            if attempt == retries:
                logger.error("GET %s failed after %d attempts: %s", url, retries, exc)
                return None
            time.sleep(attempt * 1.5)
    return None


def request_post_json(url: str, payload: Dict[str, Any], timeout: int = 15, retries: int = 3) -> Optional[Dict[str, Any]]:
    """Execute POST request with retries for transient gateway failures."""
    for attempt in range(1, retries + 1):
        try:
            if curl_requests is not None:
                resp = curl_requests.post(
                    url,
                    headers=COMMON_HEADERS,
                    json=payload,
                    impersonate="chrome",
                    timeout=timeout,
                )
            else:
                resp = requests.post(
                    url,
                    headers=COMMON_HEADERS,
                    json=payload,
                    timeout=timeout,
                )

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404 and attempt < retries:
                wait_sec = random.uniform(3, 4)
                logger.warning(
                    "POST %s returned HTTP 404 for club %s, retry %d/%d in %.1fs...",
                    url, payload.get("clubId"), attempt, retries - 1, wait_sec,
                )
                time.sleep(wait_sec)
                continue
            if resp.status_code in RETRY_STATUSES and attempt < retries:
                wait_sec = attempt * 2
                logger.warning(
                    "POST %s returned HTTP %d for club %s, retrying in %ds...",
                    url, resp.status_code, payload.get("clubId"), wait_sec,
                )
                time.sleep(wait_sec)
                continue
            logger.warning(
                "POST %s failed with HTTP %d for club %s on attempt %d/%d",
                url, resp.status_code, payload.get("clubId"), attempt, retries,
            )
            return None
        except Exception as exc:
            if attempt == retries:
                logger.error("POST %s failed after %d attempts: %s", url, retries, exc)
                return None
            time.sleep(attempt * 1.5)
    return None


def fetch_all_clubs() -> List[Dict[str, Any]]:
    """Retrieve full list of sports clubs from Mars Athletic gateway."""
    # The gateway occasionally answers this endpoint with a transient 404 (seen 2026-10-31,
    # fine a few minutes later), so 404 is retried here as well.
    data = request_get_json(
        CLUBS_ENDPOINT,
        retries=5,
        retry_statuses=RETRY_STATUSES + (404,),
    )
    if not data or not data.get("isValid"):
        logger.error("Failed to fetch clubs list from %s", CLUBS_ENDPOINT)
        return []
    clubs = data.get("data") or []
    logger.info("Retrieved %d total clubs from gateway", len(clubs))
    return clubs


def fetch_plans_for_club(club: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Query pricing rules for a single club across terms and commitment options."""
    cid = club.get("clubID") or club.get("id")
    if not cid:
        return []

    club_name = club.get("name", "").strip()
    city = (club.get("city") or "").strip()
    district = (club.get("district") or "").strip()
    club_type = (club.get("clubType") or "MACFit").strip()
    google_maps_url = club.get("googleMapsUrl") or f"https://www.macfit.com/kulupler"

    items_collected: List[Dict[str, Any]] = []

    # Scenario 1: 12-Month Commitment (Aydan Aya Taahhütlü)
    p_committed = {
        "memberId": None,
        "memberNumber": None,
        "clubId": cid,
        "employeeClubId": cid,
        "status": "New",
        "lang": "tr",
        "terms": [12],
        "hasContract": "1",
        "header": "New",
        "channel": "Portal",
    }
    resp1 = request_post_json(PLAN_RULES_ENDPOINT, p_committed)
    if resp1 is None:
        raise RuntimeError(f"12-month commitment plan request failed for club {cid}")
    if resp1 and resp1.get("isValid") and resp1.get("data"):
        for grp in resp1["data"].get("paymentPlans") or []:
            for it in grp.get("items") or []:
                plan_name = (it.get("paymentPlanName") or "").strip()
                category = (it.get("membershipCategory") or "Standard").strip()
                monthly_fee = it.get("discountedFee") or it.get("membershipFee")
                enrolment_fee = it.get("enrolmentFee") or 0.0

                if monthly_fee and monthly_fee > 0:
                    prod_name = f"{club_type} {city} {club_name} - {plan_name} (12 Ay Taahhütlü Aylık Üyelik)"
                    items_collected.append({
                        "product_name": prod_name,
                        "price": float(monthly_fee),
                        "category_name": CATEGORY_NAME,
                        "sub_category_number": SUB_CATEGORY_NUMBER,
                        "city": city,
                        "district": district,
                        "club_name": club_name,
                        "club_type": club_type,
                        "plan_name": plan_name,
                        "membership_category": category,
                        "commitment_type": "12 Ay Taahhütlü",
                        "term_months": 12,
                        "url": google_maps_url,
                        "category_number": CATEGORY_NUMBER,
                    })

                # Record one-time enrollment fee if applicable
                if enrolment_fee and enrolment_fee > 0:
                    enrol_prod_name = f"{club_type} {city} {club_name} - Kayıt Bedeli (Giriş Ücreti)"
                    items_collected.append({
                        "product_name": enrol_prod_name,
                        "price": float(enrolment_fee),
                        "category_name": CATEGORY_NAME,
                        "sub_category_number": SUB_CATEGORY_NUMBER,
                        "city": city,
                        "district": district,
                        "club_name": club_name,
                        "club_type": club_type,
                        "plan_name": "Kayıt Bedeli",
                        "membership_category": "Enrollment",
                        "commitment_type": "Tek Seferlik",
                        "term_months": 0,
                        "url": google_maps_url,
                        "category_number": CATEGORY_NUMBER,
                    })

    # Scenario 2: Flexible Monthly (Taahhütsüz Aylık) and Upfront Annual (Peşin Yıllık)
    p_flex_upfront = {
        "memberId": None,
        "memberNumber": None,
        "clubId": cid,
        "employeeClubId": cid,
        "status": "New",
        "lang": "tr",
        "terms": [1, 12],
        "hasContract": "0",
        "header": "New",
        "channel": "Portal",
    }
    resp2 = request_post_json(PLAN_RULES_ENDPOINT, p_flex_upfront)
    if resp2 is None:
        raise RuntimeError(f"Flexible/upfront plan request failed for club {cid}")
    if resp2 and resp2.get("isValid") and resp2.get("data"):
        for grp in resp2["data"].get("paymentPlans") or []:
            for it in grp.get("items") or []:
                plan_name = (it.get("paymentPlanName") or "").strip()
                category = (it.get("membershipCategory") or "Standard").strip()
                term = it.get("term")
                discounted_fee = it.get("discountedFee") or it.get("membershipFee")
                enrolment_fee = it.get("enrolmentFee") or 0.0

                if not discounted_fee or discounted_fee <= 0:
                    continue

                if term == 1:
                    prod_name = f"{club_type} {city} {club_name} - {plan_name} (Taahhütsüz Aylık Üyelik)"
                    items_collected.append({
                        "product_name": prod_name,
                        "price": float(discounted_fee),
                        "category_name": CATEGORY_NAME,
                        "sub_category_number": SUB_CATEGORY_NUMBER,
                        "city": city,
                        "district": district,
                        "club_name": club_name,
                        "club_type": club_type,
                        "plan_name": plan_name,
                        "membership_category": category,
                        "commitment_type": "Taahhütsüz Aylık",
                        "term_months": 1,
                        "url": google_maps_url,
                        "category_number": CATEGORY_NUMBER,
                    })
                elif term == 12:
                    # Monthly equivalent rate
                    prod_monthly_equiv = f"{club_type} {city} {club_name} - {plan_name} (Peşin Yıllık Üyelik - Aylık Karşılığı)"
                    items_collected.append({
                        "product_name": prod_monthly_equiv,
                        "price": float(discounted_fee),
                        "category_name": CATEGORY_NAME,
                        "sub_category_number": SUB_CATEGORY_NUMBER,
                        "city": city,
                        "district": district,
                        "club_name": club_name,
                        "club_type": club_type,
                        "plan_name": plan_name,
                        "membership_category": category,
                        "commitment_type": "Peşin Yıllık (Aylık)",
                        "term_months": 12,
                        "url": google_maps_url,
                        "category_number": CATEGORY_NUMBER,
                    })

                    # Total annual sum (12 x monthly discounted rate)
                    total_annual_price = round(float(discounted_fee) * 12.0, 2)
                    prod_total_annual = f"{club_type} {city} {club_name} - {plan_name} (Peşin Yıllık Üyelik - Toplam Bedel)"
                    items_collected.append({
                        "product_name": prod_total_annual,
                        "price": total_annual_price,
                        "category_name": CATEGORY_NAME,
                        "sub_category_number": SUB_CATEGORY_NUMBER,
                        "city": city,
                        "district": district,
                        "club_name": club_name,
                        "club_type": club_type,
                        "plan_name": plan_name,
                        "membership_category": category,
                        "commitment_type": "Peşin Yıllık (Toplam)",
                        "term_months": 12,
                        "url": google_maps_url,
                        "category_number": CATEGORY_NUMBER,
                    })

    return items_collected


PUBLIC_PRICE_URL = "https://www.macfit.com/fiyat-listesi"


def fetch_public_price_list() -> List[Dict[str, Any]]:
    """Fallback while the portal gateway is down: the "from" monthly price per concept.

    www.macfit.com/fiyat-listesi shows only the cheapest club price of each concept
    (MACRaw, MACFit, MAC/One, MACStudio), not the per-club plans of the gateway.
    """
    try:
        if curl_requests is not None:
            resp = curl_requests.get(
                PUBLIC_PRICE_URL, headers=COMMON_HEADERS, impersonate="chrome", timeout=30
            )
        else:
            resp = requests.get(PUBLIC_PRICE_URL, headers=COMMON_HEADERS, timeout=30)
        if resp.status_code != 200:
            logger.error("GET %s failed with HTTP %d", PUBLIC_PRICE_URL, resp.status_code)
            return []
        html_text = resp.content.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.error("GET %s failed: %s", PUBLIC_PRICE_URL, exc)
        return []

    import re

    records: List[Dict[str, Any]] = []
    for card in re.finditer(
        r"<h3>\s*([^<]+?)\s*</h3>.*?class=\"newprice[^\"]*\"[^>]*>\s*<span class=\"price\">\s*([\d.,]+)\s*TL",
        html_text,
        re.S,
    ):
        concept = card.group(1).strip()
        price = float(card.group(2).replace(".", "").replace(",", "."))
        records.append(
            {
                "product_name": f"{concept} en ucuz kulüp - Aylık Üyelik (web sitesi başlangıç fiyatı)",
                "price": price,
                "category_number": CATEGORY_NUMBER,
                "sub_category_number": SUB_CATEGORY_NUMBER,
            }
        )
    return records


def scrape_macfit(
    target_date: str,
    output_path: Optional[Path] = None,
    club_limit: Optional[int] = None,
    club_type_filter: Optional[str] = None,
    city_filter: Optional[str] = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> Tuple[Path, int]:
    """Execute complete MACFit scraping run across all clubs and save CSV."""
    root = find_project_root()

    if output_path is None:
        out_dir = root / "InflationItems" / "Datas" / "09_Recreation" / "MACFit"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"macfit_{target_date}.csv"
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    all_clubs = fetch_all_clubs()
    if not all_clubs:
        logger.error("No clubs retrieved from the gateway; falling back to %s", PUBLIC_PRICE_URL)
        records = fetch_public_price_list()
        if not records:
            logger.error("Fallback price list is empty, aborting scrape.")
            return output_path, 0
        tmp_path = output_path.with_suffix(".csv.tmp")
        with open(tmp_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)
        tmp_path.replace(output_path)
        logger.warning("Gateway down: saved %d fallback concept prices to %s", len(records), output_path)
        return output_path, len(records)

    # Filter active clubs and exclude virtual ones (e.g. MAC+ Dijital)
    clubs_to_scrape = [
        c for c in all_clubs
        if c.get("status") == "active"
        and not c.get("isDeleted", False)
        and c.get("name", "").lower() != "mac+ dijital"
    ]

    if club_type_filter and club_type_filter.lower() != "all":
        clubs_to_scrape = [
            c for c in clubs_to_scrape
            if (c.get("clubType") or "").lower() == club_type_filter.lower()
        ]

    if city_filter:
        clubs_to_scrape = [
            c for c in clubs_to_scrape
            if city_filter.lower() in (c.get("city") or "").lower()
        ]

    if club_limit and club_limit > 0:
        clubs_to_scrape = clubs_to_scrape[:club_limit]

    logger.info(
        "Starting MACFit scrape: %d clubs (workers=%d, target_date=%s)...",
        len(clubs_to_scrape),
        max_workers,
        target_date,
    )

    all_items: List[Dict[str, Any]] = []
    completed_count = 0
    failed_clubs: List[str] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_club = {
            executor.submit(fetch_plans_for_club, club): club
            for club in clubs_to_scrape
        }

        for future in as_completed(future_to_club):
            club = future_to_club[future]
            club_title = f"{club.get('city')} - {club.get('name')}"
            try:
                records = future.result()
                if records:
                    all_items.extend(records)
                completed_count += 1
                if completed_count % 25 == 0 or completed_count == len(clubs_to_scrape):
                    logger.info("Progress: %d/%d clubs processed (%d items collected)", completed_count, len(clubs_to_scrape), len(all_items))
            except Exception as exc:
                logger.error("Error scraping club %s: %s", club_title, exc)
                failed_clubs.append(club_title)
                for pending in future_to_club:
                    pending.cancel()
                break

    if failed_clubs:
        raise RuntimeError(
            f"Plan requests failed for {', '.join(failed_clubs)}; stopping the crawl and "
            f"refusing to write an incomplete CSV at {output_path}."
        )

    # Deduplicate records by unique product_name
    seen_names: set = set()
    deduped: List[Dict[str, Any]] = []
    for item in all_items:
        pname = item["product_name"]
        if pname not in seen_names:
            seen_names.add(pname)
            deduped.append(item)

    # Deterministic sorting
    deduped.sort(key=lambda x: (x["city"], x["club_name"], x["commitment_type"], x["plan_name"]))

    # Write atomically via .tmp file
    tmp_path = output_path.with_suffix(".csv.tmp")
    with open(tmp_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(deduped)

    tmp_path.replace(output_path)
    logger.info("Successfully saved %d items to %s", len(deduped), output_path)

    return output_path, len(deduped)


def main():
    parser = argparse.ArgumentParser(
        description="MACFit Sports & Fitness Club Membership Scraper (TÜİK COICOP 09)"
    )
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Target date string YYYY-MM-DD (defaults to today)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Custom output CSV file path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of clubs to scrape (for testing)",
    )
    parser.add_argument(
        "--club-type",
        choices=["all", "MACFit", "MAC/One", "MACStudio", "MACRaw"],
        default="all",
        help="Filter by club concept/brand type",
    )
    parser.add_argument(
        "--city",
        type=str,
        default=None,
        help="Filter by Turkish city name (e.g. Ankara, İstanbul, İzmir)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=f"Number of concurrent worker threads (default {DEFAULT_MAX_WORKERS})",
    )

    args = parser.parse_args()

    out_file, count = scrape_macfit(
        target_date=args.date,
        output_path=args.output,
        club_limit=args.limit,
        club_type_filter=args.club_type,
        city_filter=args.city,
        max_workers=args.max_workers,
    )

    if count == 0:
        logger.warning("Scraper finished with 0 records.")
        sys.exit(1)

    print(f"DONE: {count} membership products written to {out_file}")


if __name__ == "__main__":
    main()
