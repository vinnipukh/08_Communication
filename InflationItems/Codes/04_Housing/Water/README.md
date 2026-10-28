# Water — municipal water tariff (TÜİK 0441101)

Fetches the household water + wastewater tariff for İstanbul (İSKİ), Ankara (ASKİ) and İzmir (İZSU). No
source publishes all cities, so each city comes from its own water utility.

```bash
python InflationItems/Codes/04_Housing/Water/scraper.py
python InflationItems/Codes/04_Housing/Water/scraper.py --source izsu   # bounded run
```

- Requests: 5 (İSKİ page + yearly PDF; ASKİ tariff page + PDF; İZSU page), 1 s apart per host.
  Runtime ~3 s (measured 2026-10-28; ~4 s including interpreter start).
- Output: `InflationItems/Datas/04_Housing/Water/YYYY-MM-DD.csv`, written every run (dense time series).
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

## Troubleshooting

- `İSKİ: HTML tier 1 ... is in no month column` — the page and the yearly PDF disagree; open both and check
  which month the page shows. `... month dates but ... Konut 1.Kademe columns` — the PDF layout changed.
- `İSKİ: no '<year> Yılı' PDF link` — in January the new year's PDF may not be linked yet; the run fails for
  İSKİ until it is.
- `ASKİ PDF: expected 3 konut + 4 sosyal konut tiers` — the tier structure changed; print
  `PdfReader(...).pages[0].extract_text()` and adjust the line regex in `aski()`.
- `İZSU: no RSC chunk with the tariff table` — the Next.js page changed; search the page source for
  "KONUT ABONELER".
- Needs `curl_cffi`, `beautifulsoup4`, `lxml`, `pypdf` (`requirements.txt`).
- Git Bash on Windows garbles Turkish output; set `PYTHONIOENCODING=utf-8`.
