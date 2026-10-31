from __future__ import annotations

import argparse
import csv
import html
import logging
import re
import sys
import time
from collections import OrderedDict
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
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("JollyTourScraper")


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = next(
    (p for p in BASE_DIR.parents if (p / ".git").exists()),
    BASE_DIR,
)

DATA_DIR = (
    PROJECT_ROOT
    / "InflationItems"
    / "Datas"
    / "09_Recreation"
    / "Jolly"
)

BASE_URL = "https://www.jollytur.com"

CATEGORY_NUMBER = "9"

DOMESTIC_WEEKEND = "0980002"
DOMESTIC_OTHER = "0980003"
INTERNATIONAL_TOUR = "0980006"

WEEKEND_URL = f"{BASE_URL}/hafta-sonu-turlari"
DOMESTIC_INDEX_URL = f"{BASE_URL}/kultur-turlari"
INTERNATIONAL_URL = f"{BASE_URL}/2026-yurt-disi-turlari"

REQUEST_TIMEOUT = 40
REQUEST_DELAY = 0.35
MAX_DISCOVERED_PAGES_PER_SOURCE = 100

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Referer": BASE_URL + "/",
}



DOMESTIC_SOURCE_NAMES = [
    "Tüm Kültür Turları",
    "Erken Rezervasyon Kültür Turları",
    "29 Ekim Turları",
    "Kasım Ara Tatili",
    "Trenli Turlar",
    "Konya Şeb-i Arus",
    "Ege Akdeniz Turları",
    "Likya Turları",
    "Turistik Doğu Ekspresi Turları",
    "Bozcaada Turları",
    "Kuzey Ege Turları",
    "Kapadokya Turları",
    "GAP Turları",
    "Karadeniz Turları",
    "Kıbrıs Turları",
    "İstanbul Turları",
    "Mardin Turları",
    "Doğu Anadolu Turları",
    "Eskişehir",
    "Batı Karadeniz Turları",
    "Uçaklı Turlar",
    "Günübirlik Turlar",
    "Festival Turları",
    "Cumalıkızık Turları",
    "Yedigöller Turları",
    "Maşukiye Turları",
    "Deneyim Turları",
    "Batum Turları",
    "Göbeklitepe Turları",
    "Salda Gölü Turları",
]


DOMESTIC_EXCLUDED_LABELS = {
    "Hafta Sonu Turları",
    "30 Ağustos Kültür Turları",
}


TL_PATTERN = re.compile(
    r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*TL",
    re.IGNORECASE,
)


ACTIVE_TL_PATTERN = re.compile(
    r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)"
    r"\s*\)?\s*TL\s*['’]?\s*d[ae]n\s+başlayan\s+fiyatlar",
    re.IGNORECASE,
)

FOREIGN_TOUR_WORDS = {
    "batum",
    "tiflis",
    "gürcistan",
    "ermenistan",
    "bakü",
    "azerbaycan",
    "belgrad",
    "saraybosna",
    "sofya",
    "selanik",
    "yunanistan",
    "bulgaristan",
    "makedonya",
    "karadağ",
    "kosova",
    "arnavutluk",
    "dubrovnik",
    "balkan",
}

TOTAL_PATTERN = re.compile(
    r"([\d.]+)\s*tur\s*bulundu",
    re.IGNORECASE,
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
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=10,
        pool_maxsize=10,
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)

    return session


def normalize_text(value):
    return " ".join(
        str(value or "")
        .replace("\xa0", " ")
        .split()
    ).strip()


def clean_name(value):
    return html.unescape(
        normalize_text(value)
    )


def canonical_key(value):
    value = clean_name(value).casefold()

    value = re.sub(
        r"[^\w]+",
        " ",
        value,
        flags=re.UNICODE,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def normalize_url(href):
    if not href:
        return None

    absolute = urljoin(
        BASE_URL,
        href,
    )

    parts = urlsplit(absolute)

    if parts.netloc.casefold() not in {
        "jollytur.com",
        "www.jollytur.com",
    }:
        return None

    path = parts.path.rstrip("/")

    if not path:
        return None


    return urlunsplit(
        (
            "https",
            "www.jollytur.com",
            path,
            parts.query,
            "",
        )
    )


def normalize_product_url(href):
    url = normalize_url(href)

    if not url:
        return None

    parts = urlsplit(url)


    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            "",
            "",
        )
    )


def convert_price(value):
    value = normalize_text(value)

    value = re.sub(
        r"[^\d,.]",
        "",
        value,
    )

    if not value:
        return None

    if "," in value:
        value = (
            value
            .replace(".", "")
            .replace(",", ".")
        )

    elif value.count(".") > 1:
        value = value.replace(".", "")

    elif "." in value:
        left, right = value.rsplit(".", 1)

        if len(right) == 3:
            value = left + right

    try:
        price = float(value)
    except ValueError:
        return None

    return price if price > 0 else None


def fetch_html(session, url):
    response = session.get(
        url,
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code == 403:
        raise RuntimeError(
            f"Jolly returned HTTP 403 for {url}. "
            "The site may be temporarily blocking automated requests."
        )

    response.raise_for_status()

    if (
        not response.encoding
        or response.encoding.lower() == "iso-8859-1"
    ):
        response.encoding = (
            response.apparent_encoding
            or "utf-8"
        )

    return response.text


def extract_reported_total(soup):
    text = clean_name(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    match = TOTAL_PATTERN.search(
        text
    )

    if not match:
        return None

    return int(
        match.group(1).replace(".", "")
    )


def extract_current_tl_price(text):

    text = clean_name(text)

    exact_matches = list(
        ACTIVE_TL_PATTERN.finditer(text)
    )

    if exact_matches:
        price = convert_price(
            exact_matches[-1].group(1)
        )

        if price is not None:
            return price


    marker = re.search(
        r"başlayan\s+fiyatlar",
        text,
        flags=re.IGNORECASE,
    )

    if marker:
        window = text[
            max(0, marker.start() - 90):
            marker.start()
        ]


        window = re.sub(
            r"\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?\s*TL['’]?\s*ye\s+Varan\s+Bonus\s+Fırsatı",
            " ",
            window,
            flags=re.IGNORECASE,
        )

        matches = TL_PATTERN.findall(window)

        for raw in reversed(matches):
            price = convert_price(raw)

            if price is not None:
                return price

    return None


def looks_like_tour_detail_url(href):
    url = normalize_product_url(href)

    if not url:
        return False

    path = urlsplit(url).path.casefold().rstrip("/")

    if not path or path == "":
        return False

    excluded = {
        "/tur",
        "/kultur-turlari",
        "/hafta-sonu-turlari",
        "/yurtdisi-turlar",
        "/2026-yurt-disi-turlari",
        "/gemi-turlari",
        "/yardim-merkezi",
        "/iletisim",
        "/kampanyalar",
    }

    if path in excluded:
        return False


    if (
        path.endswith("-turlari")
        or path.endswith("-turlar")
        or path.endswith("-cikisli-turlar")
    ):
        return False

    return True


def candidate_name_from_link(link):
    candidates = []

    for attr in (
        "title",
        "aria-label",
    ):
        value = clean_name(
            link.get(attr)
        )

        if value:
            candidates.append(value)

    image = link.find("img")

    if image:
        value = clean_name(
            image.get("alt")
        )

        if value:
            candidates.append(value)

    text = clean_name(
        link.get_text(
            " ",
            strip=True,
        )
    )

    if text:
        candidates.append(text)

    cleaned = []

    for candidate in candidates:
        lower = candidate.casefold()

        if len(candidate) < 8:
            continue

        if "turu incele" in lower:
            continue

        if TL_PATTERN.search(candidate):
            candidate = TL_PATTERN.split(
                candidate,
                maxsplit=1,
            )[0].strip()

        if len(candidate) >= 8:
            cleaned.append(candidate)

    return list(
        dict.fromkeys(cleaned)
    )


def find_tour_container(link):
    current = link

    for _ in range(12):
        current = current.parent

        if current is None:
            break

        text = clean_name(
            current.get_text(
                " ",
                strip=True,
            )
        )

        lower = text.casefold()

        if "başlayan fiyatlar" not in lower:
            continue

        if extract_current_tl_price(text) is None:
            continue

        detail_urls = set()

        for child in current.find_all(
            "a",
            href=True,
        ):
            if not looks_like_tour_detail_url(
                child.get("href")
            ):
                continue

            normalized = normalize_product_url(
                child.get("href")
            )

            if normalized:
                detail_urls.add(normalized)


        if len(detail_urls) == 1:
            return current

    return None


def extract_name_from_container(
    container,
    product_url,
):
    names = []

    for link in container.find_all(
        "a",
        href=True,
    ):
        normalized = normalize_product_url(
            link.get("href")
        )

        if normalized != product_url:
            continue

        names.extend(
            candidate_name_from_link(
                link
            )
        )

    for tag in container.find_all(
        ["h2", "h3", "h4"],
    ):
        value = clean_name(
            tag.get_text(
                " ",
                strip=True,
            )
        )

        if len(value) >= 8:
            names.append(value)

    names = [
        clean_name(name)
        for name in names
        if clean_name(name)
    ]

    if not names:
        return None


    return max(
        list(dict.fromkeys(names)),
        key=len,
    )


def parse_tours(html_text):
    soup = BeautifulSoup(
        html_text,
        "html.parser",
    )

    items = OrderedDict()


    for link in soup.find_all(
        "a",
        href=True,
    ):
        href = link.get("href")

        if not looks_like_tour_detail_url(
            href
        ):
            continue

        product_url = normalize_product_url(
            href
        )

        if not product_url:
            continue

        if product_url in items:
            continue

        container = find_tour_container(
            link
        )

        if container is None:
            continue

        container_text = clean_name(
            container.get_text(
                " ",
                strip=True,
            )
        )

        price = extract_current_tl_price(
            container_text
        )

        if price is None:
            continue

        name = extract_name_from_container(
            container,
            product_url,
        )

        if not name:
            continue


        if name.casefold() in {
            "turu incele",
            "kültür turları",
            "yurt dışı turları",
            "hafta sonu turları",
        }:
            continue

        items[product_url] = {
            "product_name": name,
            "price": price,
            "_product_url": product_url,
        }

    return (
        list(items.values()),
        extract_reported_total(soup),
    )


def discover_pagination_urls(
    first_url,
    html_text,
):

    soup = BeautifulSoup(
        html_text,
        "html.parser",
    )

    first_parts = urlsplit(
        first_url
    )

    found = OrderedDict()

    for link in soup.find_all(
        "a",
        href=True,
    ):
        href = link.get("href")
        candidate = normalize_url(href)

        if not candidate:
            continue

        parts = urlsplit(
            candidate
        )

        if parts.path.rstrip("/") != first_parts.path.rstrip("/"):
            continue

        query = dict(
            parse_qsl(
                parts.query,
                keep_blank_values=True,
            )
        )

        lower_keys = {
            key.casefold()
            for key in query
        }

        link_text = clean_name(
            link.get_text(
                " ",
                strip=True,
            )
        )

        has_page_param = any(
            key in {
                "page",
                "p",
                "sayfa",
                "pagenumber",
                "pageindex",
            }
            for key in lower_keys
        )

        numeric_link = link_text.isdigit()

        if not (
            has_page_param
            or numeric_link
        ):
            continue

        if candidate == first_url:
            continue

        found[candidate] = None

        if len(found) >= MAX_DISCOVERED_PAGES_PER_SOURCE:
            break

    return list(found.keys())


def is_umrah_tour(name):

    value = clean_name(name).casefold()
    return "umre" in value


def is_cyprus_destination_tour(name):


    value = clean_name(name).casefold()
    return (
        "kıbrıs turu" in value
        or "kibris turu" in value
        or "kıbrıs paket tur" in value
        or "kibris paket tur" in value
    )


def build_page_url(url, page_number):

    if page_number <= 1:
        return url

    parts = urlsplit(url)
    query = dict(
        parse_qsl(
            parts.query,
            keep_blank_values=True,
        )
    )


    for key in list(query):
        if key.casefold() == "sayfa":
            query.pop(key, None)

    query["Sayfa"] = str(page_number)

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


def looks_like_foreign_tour(name):
    key = canonical_key(name)

    return any(
        canonical_key(word) in key
        for word in FOREIGN_TOUR_WORDS
    )


def scrape_listing(
    session,
    source_name,
    source_url,
):
    logger.info(
        "Starting source: %s",
        source_name,
    )

    all_items = OrderedDict()
    reported_total = None
    page_number = 1

    while page_number <= MAX_DISCOVERED_PAGES_PER_SOURCE:
        page_url = build_page_url(
            source_url,
            page_number,
        )

        try:
            page_html = fetch_html(
                session,
                page_url,
            )
        except Exception as exc:
            logger.warning(
                "%s page %d failed: %s",
                source_name,
                page_number,
                exc,
            )
            break

        page_items, page_reported_total = parse_tours(
            page_html
        )

        if reported_total is None and page_reported_total is not None:
            reported_total = page_reported_total

        if not page_items:
            logger.info(
                "%s page %d: no products, stopping",
                source_name,
                page_number,
            )
            break

        new_count = 0

        for item in page_items:
            product_url = item[
                "_product_url"
            ]

            if product_url in all_items:
                continue

            all_items[
                product_url
            ] = item

            new_count += 1

        logger.info(
            "%s page %d: parsed=%d new=%d total=%d%s",
            source_name,
            page_number,
            len(page_items),
            new_count,
            len(all_items),
            (
                f"/{reported_total}"
                if reported_total is not None
                else ""
            ),
        )

        if (
            reported_total is not None
            and len(all_items) >= reported_total
        ):
            break


        if new_count == 0:
            break

        page_number += 1
        time.sleep(REQUEST_DELAY)

    result = list(
        all_items.values()
    )

    logger.info(
        "%s: extracted %d unique tours%s",
        source_name,
        len(result),
        (
            f" / site reports {reported_total}"
            if reported_total is not None
            else ""
        ),
    )

    return result


def discover_domestic_sources(
    session,
):

    page_html = fetch_html(
        session,
        DOMESTIC_INDEX_URL,
    )

    soup = BeautifulSoup(
        page_html,
        "html.parser",
    )

    by_label = {}

    for link in soup.find_all(
        "a",
        href=True,
    ):
        label = clean_name(
            link.get_text(
                " ",
                strip=True,
            )
        )

        if not label:
            continue

        url = normalize_url(
            link.get("href")
        )

        if not url:
            continue

        by_label.setdefault(
            canonical_key(label),
            (label, url),
        )

    sources = OrderedDict()

    for wanted_name in DOMESTIC_SOURCE_NAMES:
        wanted_key = canonical_key(
            wanted_name
        )

        match = by_label.get(
            wanted_key
        )

        if match is None:

            for key, value in by_label.items():
                if (
                    len(wanted_key) >= 8
                    and (
                        wanted_key in key
                        or key in wanted_key
                    )
                ):
                    match = value
                    break

        if match is None:
            logger.warning(
                "Domestic source not discovered: %s",
                wanted_name,
            )
            continue

        label, url = match

        if label in DOMESTIC_EXCLUDED_LABELS:
            continue

        if url in {
            DOMESTIC_INDEX_URL,
            WEEKEND_URL,
        }:
            continue

        sources[label] = url

    logger.info(
        "Discovered %d domestic Jolly source categories",
        len(sources),
    )

    return sources


def dedupe_by_url_and_name(
    items,
):
    result = []

    seen_urls = set()
    seen_names = set()

    for item in items:
        product_url = item.get(
            "_product_url"
        )

        name_key = canonical_key(
            item.get(
                "product_name",
                "",
            )
        )

        if product_url and product_url in seen_urls:
            continue

        if not name_key or name_key in seen_names:
            continue

        if product_url:
            seen_urls.add(
                product_url
            )

        seen_names.add(
            name_key
        )

        result.append(
            item
        )

    return result


def remove_weekend_from_domestic(
    domestic_items,
    weekend_items,
):
    weekend_urls = {
        item["_product_url"]
        for item in weekend_items
        if item.get("_product_url")
    }

    weekend_names = {
        canonical_key(
            item["product_name"]
        )
        for item in weekend_items
    }

    result = []

    for item in domestic_items:
        if item.get("_product_url") in weekend_urls:
            continue

        if canonical_key(
            item["product_name"]
        ) in weekend_names:
            continue

        result.append(
            item
        )

    return result


def add_subcategory(
    items,
    subcategory_number,
):
    return [
        {
            "product_name": item["product_name"],
            "price": item["price"],
            "category_number": CATEGORY_NUMBER,
            "sub_category_number": subcategory_number,
        }
        for item in items
    ]


def final_dedupe(
    rows,
):
    result = []
    seen = set()

    for row in rows:
        key = (
            row[
                "sub_category_number"
            ],
            canonical_key(
                row[
                    "product_name"
                ]
            ),
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            row
        )

    return result


def save_to_csv(
    rows,
    date_str,
):
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        DATA_DIR
        / f"jolly_{date_str}.csv"
    )

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.writer(
            file
        )

        writer.writerow(
            [
                "product_name",
                "price",
                "category_number",
                "sub_category_number",
            ]
        )

        for row in sorted(
            rows,
            key=lambda item: (
                item["sub_category_number"],
                item["product_name"].casefold(),
            ),
        ):
            writer.writerow(
                [
                    row["product_name"],
                    f'{row["price"]:.2f}',
                    row["category_number"],
                    row["sub_category_number"],
                ]
            )

    logger.info(
        "Saved %d rows to %s",
        len(rows),
        output_file,
    )

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Jolly Category 09 tour scraper "
            "(0980002, 0980003, 0980006)"
        )
    )

    parser.add_argument(
        "--date",
        type=str,
        default=None,
    )

    parser.add_argument(
        "--weekend-only",
        action="store_true",
        help="Smoke test: scrape only 0980002.",
    )

    args = parser.parse_args()

    date_str = (
        args.date
        or datetime.today().strftime(
            "%Y-%m-%d"
        )
    )

    session = build_session()

    try:
        weekend = scrape_listing(
            session,
            "domestic_weekend",
            WEEKEND_URL,
        )

        if args.weekend_only:
            domestic_other = []
            international = []

        else:
            domestic_sources = discover_domestic_sources(
                session
            )

            domestic_candidates = []

            for (
                source_name,
                source_url,
            ) in domestic_sources.items():
                try:
                    source_items = scrape_listing(
                        session,
                        source_name,
                        source_url,
                    )
                except Exception as exc:
                    logger.warning(
                        "Domestic source %s failed: %s",
                        source_name,
                        exc,
                    )
                    continue

                domestic_candidates.extend(
                    source_items
                )

                time.sleep(
                    REQUEST_DELAY
                )

            domestic_candidates = dedupe_by_url_and_name(
                domestic_candidates
            )


            cross_border = [
                item
                for item in domestic_candidates
                if (
                    looks_like_foreign_tour(
                        item["product_name"]
                    )
                    or is_cyprus_destination_tour(
                        item["product_name"]
                    )
                )
            ]

            domestic_candidates = [
                item
                for item in domestic_candidates
                if not (
                    looks_like_foreign_tour(
                        item["product_name"]
                    )
                    or is_cyprus_destination_tour(
                        item["product_name"]
                    )
                )
            ]

            domestic_other = remove_weekend_from_domestic(
                domestic_candidates,
                weekend,
            )

            international = scrape_listing(
                session,
                "international_2026",
                INTERNATIONAL_URL,
            )

            international.extend(
                cross_border
            )


            international = [
                item
                for item in international
                if not is_umrah_tour(
                    item["product_name"]
                )
            ]

            international = dedupe_by_url_and_name(
                international
            )

    finally:
        session.close()

    rows = []

    rows.extend(
        add_subcategory(
            weekend,
            DOMESTIC_WEEKEND,
        )
    )

    rows.extend(
        add_subcategory(
            domestic_other,
            DOMESTIC_OTHER,
        )
    )

    rows.extend(
        add_subcategory(
            international,
            INTERNATIONAL_TOUR,
        )
    )

    rows = final_dedupe(
        rows
    )

    if not rows:
        logger.error(
            "No Jolly tour data was scraped."
        )
        sys.exit(1)

    output_file = save_to_csv(
        rows,
        date_str,
    )

    counts = {}

    for row in rows:
        code = row[
            "sub_category_number"
        ]

        counts[code] = (
            counts.get(code, 0)
            + 1
        )

    print()
    print("------------------------------------------")
    print("Jolly scraping completed.")
    print(
        "0980002 | Yurtiçi hafta sonu paket turu:",
        counts.get(DOMESTIC_WEEKEND, 0),
    )
    print(
        "0980003 | Diğer yurtiçi paket turlar:",
        counts.get(DOMESTIC_OTHER, 0),
    )
    print(
        "0980006 | Yurtdışı paket turu:",
        counts.get(INTERNATIONAL_TOUR, 0),
    )
    print()
    print(
        "Total rows:",
        len(rows),
    )
    print(
        "File:",
        output_file,
    )
    print("------------------------------------------")


if __name__ == "__main__":
    main()
