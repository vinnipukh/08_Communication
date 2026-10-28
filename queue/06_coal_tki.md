# 06 — Coal (TKİ price list) — semi-manual

- **TÜİK item:** 0454101 Kömür
- **Scraper path:** `InflationItems/Codes/04_Housing/Coal/scraper.py`
- **Output:** `InflationItems/Datas/04_Housing/Coal/YYYY-MM-DD.csv` (+ the downloaded image when it changes)

## Source

- `https://www.tki.gov.tr/komur-fiyatlarips` — the price table is an **image** (webp on
  `https://webim.tki.gov.tr/file/<uuid>`, Last-Modified 2026-10-22).
- Content: TL/ton prices valid from 15.09.2026 for Tunçbilek, Soma and Çan mines, loose and bagged
  (e.g. 6,000 TL/ton + VAT). These are mine-gate (FOB) prices, not city retail prices — note this
  limitation in the README.
- One request; changes a few times a year.

## Approach

1. Fetch the page, take the image URL, download it, compare its hash with the last saved one.
2. If unchanged: log and exit without new rows (or re-emit the last values with today's date — decide
   and document).
3. If changed: save the image and either OCR it (try a local OCR such as Tesseract with Turkish data)
   or write a template CSV for manual entry. Do not invent numbers; leave the row empty when OCR is unsure.

Rejected: Trendyol (Cloudflare 403) and Hepsiburada (captcha) — national prices only, need a browser.

## CSV columns

`product_name, price, category_number (4), sub_category_number (0454101)`, then
`mine, product (e.g. "Tunçbilek torbalı"), unit (TL/ton), vat_included, valid_from, image_sha256,
entry_method (ocr | manual), source_url, collected_at`.
