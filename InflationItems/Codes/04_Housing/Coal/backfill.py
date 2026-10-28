"""
One-off backfill of the TKİ coal price list (TÜİK 0454101) from a start date to yesterday.

TKİ's page keeps only the current price image, but the Wayback Machine has copies of the page
(``web.archive.org/cdx`` for ``www.tki.gov.tr/komur-fiyatlarips``) and every image they point to is still served
by ``webim.tki.gov.tr`` (Wayback's copy is the fallback). Each distinct image goes through the same review as in
scraper.py: saved under ``images/``, transcribed once into ``transcribed.csv`` (a ``pending_<sha12>.csv`` draft
is written for an image without rows; review it, append it and run again), and checked with the VAT arithmetic.

Then one Datas/04_Housing/TKI/tki_YYYY-MM-DD.csv per day from <start> to yesterday holding the list in force that
day (newest ``valid_from`` on or before it; ``source_url`` is the Wayback copy the image was found on,
``collected_at`` is the backfill run time). Existing day files are never overwritten.

Examples:
  python backfill.py                       # from 2025-01-01
  uv run --with rapidocr-onnxruntime python backfill.py   # OCR the drafts of new images
"""

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone

from scraper import (IMAGE_DIR, IMAGE_EXT, PAGE_URL, TRANSCRIBED, Client, append_transcribed, auto_transcription,
                     check, csv_rows, day_path, ocr_draft, price_image_url, read_transcribed, write_csv, write_draft)

CDX = "https://web.archive.org/cdx/search/cdx?url=www.tki.gov.tr/komur-fiyatlarips&from={year}&output=json" \
      "&collapse=digest&filter=statuscode:200"
WAYBACK_RAW = "https://web.archive.org/web/{ts}id_/{url}"

log = logging.getLogger("coal_backfill")


def snapshot_images(client: Client, start: str) -> dict[str, str]:
    """Price image URL -> Wayback copy of the page it was first seen on, from the year before ``start`` on
    (so the list already in force on ``start`` is included)."""
    rows = json.loads(client.get(CDX.format(year=int(start[:4]) - 1)).content)[1:]
    before = [r for r in rows if r[1][:8] < start.replace("-", "")]
    rows = before[-1:] + [r for r in rows if r not in before]  # the last copy before start shows the list in force
    images = {}
    for row in rows:
        page = WAYBACK_RAW.format(ts=row[1], url=PAGE_URL)
        try:
            url = price_image_url(client.get(page).content.decode("utf-8"))
        except Exception as exc:  # a copy without the usual page data
            log.warning("%s: %s", page, exc)
            continue
        images.setdefault(url, page)
    images.setdefault(price_image_url(client.get(PAGE_URL).content.decode("utf-8")), PAGE_URL)  # the live list
    return images


def fetch_image(client: Client, url: str, page: str) -> bytes:
    sources = [url] + ([WAYBACK_RAW.format(ts=page.split("/web/")[1].split("id_")[0], url=url)] if "/web/" in page else [])
    for source in sources:
        try:
            resp = client.get(source)
        except Exception as exc:
            log.warning("%s: %s", source, exc)
            continue
        if resp.headers.get("content-type", "").split(";")[0] in IMAGE_EXT:
            return resp.content
    raise RuntimeError(f"{url}: no image from TKİ or the Wayback Machine")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2025-01-01", help="first date to cover, YYYY-MM-DD (default: 2025-01-01)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (jittered)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    start = date.fromisoformat(args.start).isoformat()
    started = time.monotonic()

    client = Client(args.delay)
    images = snapshot_images(client, start)
    log.info("%d distinct price images in the Wayback copies", len(images))
    transcribed = read_transcribed()
    versions, pending = {}, []  # valid_from -> rows; images still to transcribe
    for url, page in images.items():
        image = fetch_image(client, url, page)
        sha = hashlib.sha256(image).hexdigest()
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        image_path = IMAGE_DIR / f"{sha[:12]}.webp"
        if not image_path.exists():
            image_path.write_bytes(image)
        entries = [r for r in transcribed if r["image_sha256"] == sha]
        if not entries:
            draft_rows = ocr_draft(image, sha)
            entries = auto_transcription(draft_rows, transcribed) or []
            if entries:
                append_transcribed(entries)
                transcribed += entries
            else:
                pending.append(write_draft(image, sha, transcribed, draft_rows).name)
                continue
        bad = [(r["product"], reason) for r in entries if (reason := check(r))]
        if bad:
            log.error("transcription of %s fails the VAT check: %s", sha[:12], bad)
            sys.exit(1)
        key = entries[0]["valid_from"]
        if key in versions and "/web/" in page:  # a later image with the same date (e.g. products dropped):
            ts = page.split("/web/")[1][:8]      # it takes over from its first Wayback copy
            key = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
        versions[key] = (entries, url, page)
    if pending:
        log.error("no transcription yet for %s; review the drafts, append them to %s and run again",
                  ", ".join(pending), TRANSCRIBED.name)
        sys.exit(2)

    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    written = kept = 0
    day, end = date.fromisoformat(start), date.today() - timedelta(days=1)
    while day <= end:
        in_force = max((d for d in versions if d <= day.isoformat()), default=None)
        path = day_path(day.isoformat())
        if path.exists():
            kept += 1
        elif in_force:
            entries, url, page = versions[in_force]
            write_csv(path, csv_rows(entries, url, page, collected_at))
            written += 1
        day += timedelta(days=1)
    log.info("lists valid from %s; day files: %d written, %d already existed (kept), %.1f s",
             ", ".join(sorted(versions)), written, kept, time.monotonic() - started)


if __name__ == "__main__":
    main()
