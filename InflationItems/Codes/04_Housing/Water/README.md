# Water — municipal water tariff (TÜİK 0441101)

Fetches the household water + wastewater tariff for İstanbul (İSKİ), Ankara (ASKİ) and İzmir (İZSU). No
source publishes all cities, so each city comes from its own water utility.

```bash
python InflationItems/Codes/04_Housing/Water/scraper.py
python InflationItems/Codes/04_Housing/Water/scraper.py --source izsu   # bounded run
```

- Requests: 5 (İSKİ page + yearly PDF; ASKİ tariff page + PDF; İZSU page), 1 s apart per host.
  Runtime ~3 s (measured 2026-10-28; ~4 s including interpreter start).
- Output (upstream layout: one CSV per store and day): `InflationItems/Datas/04_Housing/<Store>/<store>_YYYY-MM-DD.csv`
  with Store = `ISKI`, `ASKI`, `IZSU` (`iski_`, `aski_`, `izsu_`), written every run (dense time series).
  `--output <path>` writes all rows to that one CSV instead of the store files (test runs).
- Rows: every konut (household) tier per city, plus ASKİ's "sosyal yardım alan konut" tiers
  (`subscriber_type` = `sosyal konut`). `price` = `total` = water + wastewater, TL/m³, VAT and ÇTV excluded.
  `tier_to_m3` is empty for the open top tier; ASKİ's "30 m³ üzeri" is written as from 31.
- `effective_date`: İSKİ from the yearly PDF's month column that matches the page (prices change monthly),
  ASKİ from the PDF text, İZSU from the page notice. İSKİ logs a warning if the page lags the PDF.
- Columns: `product_name, price, category_number, sub_category_number, province, utility, subscriber_type,
  tier_from_m3, tier_to_m3, water_price, wastewater_price, total, unit, vat_included, ctv_included,
  effective_date, source_url, collected_at`.
- A source that fails is logged, the others are still written, and the run exits with status 1. If every
  source fails no CSV is written.

## Sources

| City | Utility | Endpoint | Format |
|---|---|---|---|
| İstanbul | İSKİ | `https://iski.istanbul/abone-hizmetleri/abone-rehberi/su-birim-fiyatlari/` + "<year> Yılı" PDF (`iskiapi.iski.gov.tr/uploads/...`) | HTML inside a `<vue-markdown source='...'>` attribute; text PDF (pypdf) |
| Ankara | ASKİ | `https://www.aski.gov.tr/tr/ucretler.aspx` → `/Yukle/Dosya/SuTarifesi.pdf` | text PDF (pypdf) |
| İzmir | İZSU | `https://izsu.gov.tr/su-ve-atik-su-tarifesi` | HTML string in a Next.js `self.__next_f.push` chunk |

## Backfill

```bash
python InflationItems/Codes/04_Housing/Water/backfill.py                        # from 2025-01-01
python InflationItems/Codes/04_Housing/Water/backfill.py --start 2026-01-01 --source iski
```

Writes `logs/backfill/water_<start>_<today>.csv` (gitignored, same columns) with one row per tier and tariff version from `--start`
to today, plus the version in force on `--start`; `source_url` names the PDF, Wayback snapshot or image each
row came from. It then writes one `<Store>/<store>_YYYY-MM-DD.csv` per store and day from `--start` to
yesterday, like the daily scraper's files, holding per city the version in force that day. A backfilled day file is recognisable by
`collected_at` (the backfill run time, not that day) and `effective_date`. Existing day files are never
overwritten, and day files are written only when every source succeeded (`--no-daily` skips them). Run on
2026-10-28 from 2025-01-01: 132 version rows, 665 day files per store (13–14 rows a day across the three), ~80 s (Wayback requests are 2 s
apart).

Because of the ASKİ gap below, Ankara's day files from 2025-01-01 to 2025-11-30 carry the 03.12.2024 tariff
(26.88 TL/m³ first tier), although ASKİ probably changed its tariff during 2025 (it was 46.53 by December).
Check `effective_date` before relying on Ankara rows in that period.

| City | History source | Versions 2025-01-01 → 2026-10-28 | Gaps |
|---|---|---|---|
| İstanbul | yearly İSKİ PDFs, one column per month | 22 (every month) | none |
| Ankara | Wayback Machine copies of `SuTarifesi.pdf` + live PDF | 7 (2024-12-03 … 2026-10-05) | nothing archived between 03.12.2024 and Dec 2025, so 2025 changes are missing; the Dec 2025 and Mar 2026 copies give only "ARALIK 2025" / "MART 2026", written as the 1st of the month |
| İzmir | Wayback copies of the page (2026), live page, and `izsu_transcribed.csv` (in this code folder) | 5 (2025-01-01, 2025-05-05, 2025-12-01, 2026-05-01, 2026-06-01) | none known |

`izsu_transcribed.csv`, next to `backfill.py`, holds the konut rows of İZSU's 01.01.2025 and 05.05.2025 tariffs, which exist only as
images on İZSU's history list. They were typed in by hand on 2026-10-28 (image URL per row); every row passes
the water + wastewater = total check. İZSU's konut tiers changed on 05.05.2025 (0~4 / 5~10 / 11~20 / 21+ →
0~10 / 11~20 / 21+) and again on 01.06.2026 (four tiers).

## Troubleshooting

- `İSKİ: HTML tier 1 ... is in no month column` — the page and the yearly PDF disagree; open both and check
  which month the page shows. `... month dates but ... Konut 1.Kademe columns` — the PDF layout changed.
- `İSKİ: no <year> PDF yet; writing the <year-1> PDF's last month` (warning) — in January the new year's PDF
  may not be linked yet; until it is, İSKİ rows carry the previous year's last month (e.g. the 03.12 prices,
  `effective_date` shows which, `source_url` is that PDF). The PDF is a text PDF, so no OCR is needed.
- `ASKİ PDF: expected 3 konut + 4 sosyal konut tiers` — the tier structure changed; print
  `PdfReader(...).pages[0].extract_text()` and adjust the line regex in `aski()`.
- `İZSU: no RSC chunk with the tariff table` — the Next.js page changed; search the page source for
  "KONUT ABONELER".
- Needs `curl_cffi`, `beautifulsoup4`, `lxml`, `pypdf` (`requirements.txt`).
- Git Bash on Windows garbles Turkish output; set `PYTHONIOENCODING=utf-8`.

## Notes

- Schedule: ASKİ and İZSU daily 09:00 Istanbul on GitHub Actions (`scraper_04_utilities.yml`, `--source aski izsu`).
  İSKİ times out from runner IPs (test run 2026-10-28) and is to run from the cron server (`--source iski`), not set
  up yet.
- The İSKİ page also has a KSUB "<year> Yılı" link list; the first link per year is the water PDF.
- ASKİ's page links the PDF with a relative `../Yukle/...` path, and some links on that page use backslashes:
  replace `\` with `/`, then `urljoin`. İZSU's "2a ATIKSU KONUT" rows (own well, wastewater only) are skipped.
- Reusable: the RSC-chunk extraction in `izsu()` for any Next.js site (`self.__next_f.push(...)` →
  `json.loads` → BeautifulSoup); the PDF month-column pairing in `iski_month()`. For a site that keeps no
  archive, check the Wayback CDX (`web.archive.org/cdx/search/cdx?url=...&collapse=digest`) early.
- Early in a year, until the new year's PDF is linked, İSKİ writes the previous PDF's last month (see above).
