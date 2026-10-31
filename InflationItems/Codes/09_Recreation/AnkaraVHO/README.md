# Ankara VHO pet tariff scraper (TÜİK 0945001)

Source for CPI item **0945001 "Veterinary services"**: the minimum fee tariff for pets
("Ev Hayvanları Alt Sınır / Asgari Ücret Tarifesi") of the Ankara Chamber of Veterinary Surgeons
(Ankara Veteriner Hekimleri Odası, `https://www.avho.org.tr/`). Chamber members may not charge
below it (Law 6343), so it is the price floor for vet services in Ankara. A new tariff is published
twice a year (January and July).

Output: `InflationItems/Datas/09_Recreation/AnkaraVHO/ankara_vho_YYYY-MM-DD.csv`

## Run

From the repository root:

```bash
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/AnkaraVHO/ankara_vho_scraper.py
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/AnkaraVHO/ankara_vho_scraper.py --extract text
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/AnkaraVHO/ankara_vho_scraper.py --date 2026-10-31
```

| Flag | Meaning |
|---|---|
| `--extract ocr` (default) | OCR the page(s) with RapidOCR and check them against the PDF text layer (see below). |
| `--extract text` | PDF text layer only, no OCR. |
| `--date` | Date in the output file name (default: today). |
| `--allow-older` | Accept an older one-page table when the newest period has only a booklet (see caveats). |

Run time on 2026-10-31: about 4 s with `--extract text`, about 15 s with `--extract ocr`
(one page rendered at scale 3). One HTML page and one 0.7 MB PDF are downloaded.

## How the PDF is chosen

1. `curl_cffi` session with `impersonate="chrome"`, homepage first, then
   `/asgari-ucret-tarifeleri/`. No browser is needed (no challenge seen).
2. Every link to `/wp-content/uploads/YYYY/MM/*.pdf` on that page is a candidate. Links whose text
   or file name says "Çiftlik" (farm animals) are dropped; the link text must say "Ev Hayvanları".
3. The tariff period comes from the link text ("2026-2 Yılı", "2025/2 Yılı", "2026 Yılı" = first
   half). Only the one-page table ("Tablo" in the link text or file name, e.g. "A3 Tablo") is used:
   the multi-page booklet of the same period has a different layout and is not parsed.
   The newest period wins, then the newest upload folder.
4. The chosen PDF is logged and written to the `source_url` column; `tariff_period` holds the
   period (e.g. `2026/2`).

On 2026-10-31 this picks
`https://www.avho.org.tr/wp-content/uploads/2026/07/20262-Asgari-Ucret-Tablosu.pdf`
("2026-2 Yılı Ev Hayvanları Asgari Ücret Tarifesi (A3 Tablo)").

**sitemap.xml verdict:** `robots.txt` points to `/wp-sitemap.xml`, the WordPress core sitemap
(posts, pages, categories, tags). It does not list media/PDF attachments, so it cannot find the
tariff; the tariff page itself is one request and lists every PDF. Not used. (`/sitemap_index.xml`
is 404; wp-json is disabled.)

## Table parsing, OCR and text layer

The table is a one-page A3 sheet with two tables side by side; each has a service column and two
price columns, **Kedi** (cat) and **Köpek** (dog) (header icons, no text). Sections are red bands
("A) MUAYENE", "B) AŞILAR VE ENJEKSİYONLAR", ... "H) DİĞER MUAYENE VE UYGULAMALAR").

Rows are found from geometry, the same way for both text sources:

- The page is rendered with `pypdfium2` (scale 3). Pixel rows where more than 60% of the table width
  is dark are table rules or red section bands; a table row is the band between two rules. Text
  inside a red band is the section name.
- Text boxes come from the PDF text layer (pypdfium2 character boxes merged into runs) or from
  RapidOCR (`rapidocr_onnxruntime`). Boxes are placed in rule bands by their y; a box that is a whole
  price cell (`1.700`, `-`, `750 / 900 / 1.000`, `24.500 - 28.500`) in the right part of a table is a
  price, and the largest x-gap between price boxes splits the cat column from the dog column.
- A band with a label and no price is a heading ("1-OVARİOHİSTEREKTOMİ (DİŞİ KISIRLAŞTIRMA)");
  following priced rows without an item number ("Küçük Irk", "Büyük Irk", "Ret", "Operasyon") are
  named `<heading> - <row>`. Multi-line labels stay in one band and are joined.
- Item numbers ("1-", OCR often reads "1-KLİNİKTE" as "1KLiNiKTE") are stripped from names.

`--extract ocr` (default): every page is OCR'd. Where the page has a text layer, the text-layer
values are written and OCR is compared row by row (same rule band): every price cell or label that
differs is logged as a warning. A page without a text layer (scanned tariff) is written from OCR;
then `value_source` is `ocr` and names may lack Turkish letters (OCR reads "Küçük" as "Kucuk",
"İ" as "i"), so labels are compared accent-folded.

OCR accuracy on the 2026/2 table (2026-10-31): **155 of 155 price cells** and 82 of 83 row labels
agree with the text layer (the one label miss is a parenthesis OCR could not read). The OCR-only
output (text layer ignored) also gives 155 rows with the same prices, names without accents. The
2025/2 table parses with the same code (154 rows; OCR 153/154 cells, one dog price not read).
`--extract text` and `--extract ocr` write identical CSVs while the PDF has a text layer.

## CSV

`utf-8-sig`, one row per service and animal (a "-" cell means the service is not offered for that
animal and is skipped). 155 rows on 2026-10-31.

| Column | Content |
|---|---|
| `product_name` | `Ankara VHO - <section> - <service> - <Kedi/Köpek>`, e.g. `Ankara VHO - MUAYENE - KLİNİKTE - Kedi` |
| `price` | TRY, dot decimal, 2 decimals; minimum when the cell has several values |
| `category_number` | `9` |
| `sub_category_number` | `0945001` for every row |
| `price_max` | maximum of the cell (equals `price` for a single value) |
| `price_text` | the cell as published, e.g. `750 / 900 / 1.000` (weight classes) or `24.500 - 28.500` (range) |
| `animal` | `Kedi` or `Köpek` |
| `section`, `service` | table section and service name as published |
| `tariff_period` | e.g. `2026/2` |
| `kdv_included` | `1`: prices include VAT (see below) |
| `value_source` | `text` (PDF text layer) or `ocr` |
| `source_url` | the tariff PDF |

**KDV:** prices include VAT. The one-page table does not say so, but the booklet of the same
period (`20262-Ev-Hayvanlari-Asgari-Ucret-Tarifesi.pdf`) states "Tüm fiyatlara KDV dahildir" and
heads its price column "%10 KDV DAHİL FİYAT (TL)", with the same prices (e.g. muayene 1.700).

## Caveats

- These are chamber minimum fees, not observed clinic prices. They change only twice a year, so
  daily CSVs repeat the same values between tariffs.
- The booklet notes that the examination fee is added to every procedure; the table rows are the
  procedure fees alone.
- Labels are as published, including typos ("UYGULAMALALAR", "KISIRLARŞTIRMA") and the section
  "F) EKSTİRPASYONU", which actually holds sedation/anaesthesia rows. Product names will change if
  the chamber fixes them.
- 2026/1 was published only as a booklet (no one-page table). If the newest period again has no
  table, the scraper stops with an error rather than writing the older table under today's date;
  `--allow-older` overrides that (the `tariff_period` column then shows the older period). Parsing
  the booklet would need a separate parser.
- Column order Kedi, Köpek is taken from the header icons and is fixed in the code (`ANIMALS`).
