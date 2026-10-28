# Coal — TKİ coal price list (TÜİK 0454101)

Fetches the coal price list of TKİ (Türkiye Kömür İşletmeleri). TKİ publishes it only as an **image**, so each new
image is transcribed once into `transcribed.csv` — automatically by OCR when the result is unambiguous, otherwise
from a draft a person reviews — and every run after that re-emits the list with today's date while the image
stays the same.

```bash
python InflationItems/Codes/04_Housing/Coal/scraper.py
```

- Requests: 2 (page + image), 1 s apart. Runtime 1.7–3.5 s inside the script, ~3 s wall including interpreter
  start (measured 2026-10-28, three runs). With OCR on a new image: ~12 s (model load + recognition).
- Output: `InflationItems/Datas/04_Housing/TKI/tki_YYYY-MM-DD.csv` (upstream layout: one CSV per store and day,
  store = TKI), 14 rows on 2026-10-28. `--output <path>` writes that CSV instead of the day file (test runs).
- Rows: every product on the list. `price` = BİRİM FİYAT, TL/ton, VAT excluded; `price_incl_vat` and
  `vat_rate` (20) are from the same list. **These are mine-gate (FOB) prices** at three TKİ İşletme
  Müdürlükleri (GLİ Tunçbilek / Kütahya-Tavşanlı, ELİ Soma / Manisa, ÇLİ Çan / Çanakkale), not city retail
  prices: nothing here is specific to İstanbul, Ankara or İzmir, and transport and dealer margins are missing.
- Columns: `product_name, price, category_number, sub_category_number, operator, mine, product, unit,
  vat_included, vat_rate, price_incl_vat, delivery, valid_from, image_sha256, entry_method, source_url,
  image_url, collected_at`.
- Exit status: 0 = CSV written (also after an automatic OCR transcription of a new image); 1 = fetch or parse
  failure, or a transcription that fails the VAT check; 2 = a new image is waiting for review (no CSV written).

## Data files

The inputs live in this code folder (`InflationItems/Codes/04_Housing/Coal/`), not in Datas.

| File | Tracked | Role |
|---|---|---|
| `InflationItems/Datas/04_Housing/TKI/tki_YYYY-MM-DD.csv` | yes | daily output |
| `transcribed.csv` | yes | reviewed price lists, one row per product per image hash; the source of every daily row |
| `images/<sha12>.webp` | yes | every distinct price image seen (~190 KB each; the list changes a few times a year) |
| `pending_<sha12>.csv` | until reviewed | draft for an image that has no transcription; deleted by the first successful run |

## When the image changes

The run saves the new image and OCRs it (`rapidocr-onnxruntime`, a project dependency; ~12 s with model load).
`auto_transcription()` accepts the OCR result without a person when all of these hold:

- every line passes the VAT check (price × VAT rate = VAT, price + VAT = price incl. VAT) and the
  "… TARİHİNDEN İTİBAREN GEÇERLİ" date was read;
- the lines map one to one, in order, onto the products of the newest reviewed list: OCR name and reviewed name
  agree after folding Turkish letters and dropping spaces/punctuation (similarity ≥ 0.9), or a line OCR read no
  name for sits alone between two matched lines;
- no price moved more than 60 % from the product's last price.

The rows are then appended to `transcribed.csv` with the reviewed product names, `entry_method` = `ocr-auto`, and
the day file is written as usual (exit 0). Replayed on the eight lists of 2024–2026 (each against the lists before
it), 5 of 7 were accepted and matched the hand-checked transcription exactly; the other two went to review because
products were dropped (2025-05-15) or renamed (+25-100 mm → +25 mm, 2026-06-02). The amounts are paired by
splitting them into the three price columns and reading the columns top to bottom, which found every row of all
eight images.

Otherwise the run writes `pending_<sha12>.csv`, logs an error and exits 2:

1. Open the draft next to `images/<sha12>.webp`. With `rapidocr-onnxruntime` installed the draft is OCR'd
   (`entry_method` = `ocr`): numbers whose three values do not pass the check (price × VAT rate = VAT,
   price + VAT = price incl. VAT) are left empty, and product names come without Turkish letters
   ("Tuncbilekyikanmis"). Without OCR the draft repeats the last list's products with empty numbers
   (`entry_method` = `manual`).
2. Fix the product names to the image's wording, fill or confirm every number and `valid_from`
   ("… TARİHİNDEN İTİBAREN GEÇERLİ"), check `operator`/`mine`. Never guess a number; a product that cannot be
   read stays out.
3. Append the rows to `transcribed.csv` and run the scraper again. It rejects rows that fail the VAT check.

`entry_method` says how the numbers got in: `ocr-auto` (accepted automatically, see above), `ocr` (OCR, checked
against the image by a person) or `manual` (typed in). The
first list (valid from 2026-09-15) was OCR'd on 2026-10-28; all 42 numbers matched a reading of the image.

`rapidocr-onnxruntime` (with onnxruntime) is a project dependency (`requirements.txt`, `pyproject.toml`) so the
scheduled run can transcribe a new list without a person.

## Backfill

```bash
python InflationItems/Codes/04_Housing/Coal/backfill.py                                  # from 2025-01-01
python InflationItems/Codes/04_Housing/Coal/backfill.py   # new images: automatic OCR, or drafts for review
```

TKİ's page keeps only the current image, but the Wayback Machine has copies of it
(`web.archive.org/cdx` for `www.tki.gov.tr/komur-fiyatlarips`). For each copy the backfill finds the price image
with the scraper's `price_image_url()`, downloads it from `webim.tki.gov.tr` (Wayback's copy as fallback), and
puts every distinct image through the same flow as the daily run: saved under `images/`, transcribed once into
`transcribed.csv` (a `pending_<sha12>.csv` draft and exit 2 for an image without rows; review it, append it and
run again), checked with the VAT arithmetic. It then writes one `TKI/tki_YYYY-MM-DD.csv` per day from `--start`
to yesterday holding the list in force that day (newest `valid_from` on or before it; `source_url` = the Wayback
copy the image was found on, `collected_at` = the backfill run time). Existing day files are never overwritten.
There is no versions file.

Run on 2026-10-28 from 2025-01-01: 665 day files (2025-01-01 .. 2026-10-27). Lists valid from 2024-05-31,
2025-01-01, 2025-05-15, 2025-07-01, 2025-10-01, 2026-01-01, 2026-06-02 and 2026-09-15. Two images say "valid from
01.01.2025": the later one, without the ara ürün / şist rows (14 instead of 17 products), takes over from its first
Wayback copy (2025-05-15). All transcriptions were OCR'd with RapidOCR (`uv run --with rapidocr-onnxruntime`) and
checked against each image by eye (`entry_method` = `ocr`).

## Source

| Endpoint | Format |
|---|---|
| `https://www.tki.gov.tr/komur-fiyatlarips` | Next.js CMS page; `__NEXT_DATA__` → `props.pageProps.page.meta.content`, the `Image` component that is not inside a `Link` (the other one is the logo) |
| `https://webim.tki.gov.tr/file/<uuid>` | image/webp, 1194×711, table "TKİ KÖMÜR SATIŞ FİYATLARI (FOB TESLİM)" |

Change detection uses the image's SHA-256: the server sends no ETag, and its `Last-Modified` changes from one
fetch to the next for the same bytes. The image URL (uuid) may also change when TKİ uploads a new list; both
cases end up as a new hash.

Rejected: Trendyol (Cloudflare 403) and Hepsiburada (captcha) sell bagged coal at national prices but need a
browser.

## Troubleshooting

- `expected one price image on the page` — the page layout changed; look at the `Image` components in
  `__NEXT_DATA__`.
- `... is not an image` — the file host answered something else (an error page); rerun later.
- `transcription of <sha> fails the VAT check` — a typo in `transcribed.csv`.
- Needs `curl_cffi` and `rapidocr-onnxruntime` (`requirements.txt`).
- Git Bash on Windows garbles Turkish output; set `PYTHONIOENCODING=utf-8`.

## Notes

- Schedule: none yet (no cron or Actions job). Weekly is enough.
- RapidOCR reads the amounts right but mixes `.` and `,`, so amounts are parsed as digits / 100.
- Reusable for any image price list: `ocr_draft()` in `scraper.py` (amounts split into three price columns and
  paired top to bottom, label blocks by vertical gaps), `check()` (VAT arithmetic as the OCR trust test) and
  `auto_transcription()` (accept OCR only when it maps onto a known product list).
- Open: the "repeat last products" draft branch (no OCR, an earlier transcription exists) has not run live yet;
  it will on the next image change without OCR.
