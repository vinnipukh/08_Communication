# queue — notes between runs

Each agent that works an item appends a short entry here (newest at the bottom): what it found that the
specs do not say, shared code it created that later items should reuse, problems left open. Keep entries
short; no absolute paths, usernames or cookies.

<!-- Entry format:
## YYYY-MM-DD — <item #> <name>
- ...
-->

## 2026-10-28 — 1 Electricity (EPDK)
- `GetFastAccessList` answers an object; entries are under `model`, not a bare array (spec updated).
  Files per decision: `IsFileType` 1 = decision PDF, 2 = XLSX table. 3 requests per run (page + list + file).
- Since 04.04.2026 AG mesken is split into ≤8 and >8 kWh/gün rows (only tek zamanlı differs; the
  multi-time prices are the same in both). The 2025 XLSX has a different layout; the parser handles only
  the current one and fails loudly otherwise, so history is not backfillable without more code.
- Last-resort tariff: not in this list or file.
- Added `openpyxl` to `requirements.txt`, `pyproject.toml` and `uv.lock`; later XLSX sources can use it.
- Reusable pattern: the `Client` class in `Electricity/scraper.py` (curl_cffi Chrome session, page-first,
  jittered ~1 s delay, `Retry-After`, fail after 3 backoffs) is small enough to copy for items 2–7.
- Git Bash on Windows garbles Turkish characters in Python output; set `PYTHONIOENCODING=utf-8` when reading logs.
- Not done: no schedule (cron/Actions) yet for the 04 utilities scrapers.

## 2026-10-28 — 2 Natural gas (İGDAŞ, Başkentgaz, İzmirgaz)
- `www.igdas.istanbul` drops curl_cffi connections; use `igdas.istanbul`. İGDAŞ has no tax footnote; prices
  are ÖTV-incl / VAT-excl by arithmetic (spec updated). İGDAŞ's fee page has no year/VAT, so fees come from
  İzmirgaz; Başkentgaz grosses up connection fees by VAT but not deposits. All three fees matched.
- İzmirgaz omits its intermediate certificate: `izmirgaz_client()` in `NaturalGas/scraper.py` retries with the
  AIA issuer added to the certifi bundle (verification stays on). Copy it for any other host with this problem.
- Python's `"EKİM".lower()` != `"ekim"` (dotted İ). Use the `tr_month()` helper from `NaturalGas/scraper.py`
  for Turkish month names (Electricity's `effective_date()` would hit it only with upper-case names like
  "EKİM"; its sheet uses title case, and its fallback catches a miss). Also reusable there: `tr_number()` for "14,468019" / "₺9.679,20" / "8.066".
- Added `pypdf` (text PDFs) and `certifi` to `requirements.txt`, `pyproject.toml`, `uv.lock`.
- Measured ~7 s for ~11 requests; one bounded run took 36 s (a slow first connection, not reproduced).
- Open: İzmirgaz's intermediate URL is a constant; a CA change needs an update. Başkentgaz split months
  (e.g. April 2026) pick the later PDF only. No schedule yet; monthly is enough (İGDAŞ answers future months).

## 2026-10-28 — 3 Water (İSKİ, ASKİ, İZSU)
- İSKİ's table is escaped inside a `<vue-markdown source='...'>` attribute, not a real `<table>`; the month
  question is solved by matching the page's tier 1 against the yearly PDF's month columns (spec updated).
  The page also has a KSUB "<year> Yılı" link list; the first link per year is the water PDF.
- ASKİ's page link uses a relative `../Yukle/...` path (some links on that page use backslashes); `urljoin` after
  replacing `\` with `/`. ASKİ also has "sosyal yardım alan konut" tiers (0–10 at 1.00 TL/m³) — written as
  `subscriber_type` `sosyal konut`. İZSU's "2a ATIKSU KONUT" (own-well, wastewater only) rows are skipped.
- 5 requests, ~3 s. No new dependency. Reusable: the RSC-chunk extraction in `izsu()` for any Next.js site
  (`self.__next_f.push(...)` → `json.loads` → BeautifulSoup); the PDF month-column pairing in `iski_month()`.
- Open: in January İSKİ fails until the new year's PDF is linked (a fallback to the HTML without a date was
  not added). No schedule yet; monthly is enough (İSKİ changes around the 3rd–5th of each month).

## 2026-10-28 — 4 LPG (Aygaz, Milangaz, Mogaz, İpragaz)
- City codes differ per brand: Aygaz unpadded plates (`6`), Milangaz/Mogaz zero-padded (`06`; Milangaz answers
  `null` to `6`). İstanbul Avrupa is `341` (Aygaz, Mogaz) but `134` (Milangaz). Aygaz lists `34` twice. Spec updated.
- Mogaz answers `Price: ""` for İstanbul Avrupa; its own form sends the same request. Logged as a warning, no row.
- Milangaz has two 12 kg products (VANALI, SİBOPLU, same price): both are written, so Milangaz has 2 rows per city.
- İpragaz: 1680 TL in all 84 cities on 2026-10-28, but an unknown city name answers with no prices, so the
  lookup is real; kept per-city instead of one fetch. Likitgaz: DNS does not resolve, dropped.
- Brands run in parallel (ThreadPoolExecutor, one Client per brand/host, 1 s delay per host kept): 207 s for
  ~336 requests, bounded by Milangaz (~2.5 s per request); sequential was 559 s. Same pattern fits any later
  item with several hosts. One Aygaz HTTP 500 was retried fine.
- Reusable: the `PROVINCES` plate→name table and `plate_region()` in `LPG/scraper.py` for any per-province
  source; `Client.request()` there adds POST to the usual Client.
- Open: no schedule yet. Milangaz gives no validity date (`valid_from` empty).

## 2026-10-28 — 5 Home repair labour (Armut)
- Data is in `__NEXT_DATA__` (`pricePageData`), not only the visible range: `monthlyPrices` gives 12 complete
  months of quote avg/min/max/count per city, so `price` = newest month's mean (spec updated). The month can lag
  (İzmir lock change: 2026-08 on 2026-10-28) when a month has no quotes. A 12-month backfill is possible from one
  run's pages but is not written (one row per service × province only).
- Means are outlier-heavy (quotes of 1–10 million TL; some months have 1 quote). The shown min–max range repeats
  across cities for low-volume services (e.g. Sıvacı 5,000–520,000 in Ankara and İzmir): looks like a national
  fallback. A consumer should weight by `month_quote_count` or prefer high-volume services.
- Page URLs are resolved from `sitemap/price-arealevel1-*.xml` (+2 requests), so no city-slug table was needed and
  `--provinces all` works. 23 services in `services.json`; 71 requests, 83 s measured. No new dependency.
- Reusable: `page_urls()` pattern (sitemap → id-keyed URL map) for any site with id-suffixed URLs.
- Open: no schedule yet; monthly is enough (data moves once a month). The service choice is a judgement call —
  review `services.json` against the TÜİK item definition if the index team has one.
- Backfill done (2026-10-28, `--backfill`): 365 daily CSVs 2025-10-01 .. 2026-09-30, each day = its month's
  quote mean (monthly data repeated per day, marked `backfill:` in `notes`). 1–27 Oct 2026 have no file. A
  service × city month with zero quotes has no row (65–69 rows/day). Existing day files are never overwritten.

## 2026-10-28 — backfill 2025-01-01 → today (items 1–3)
- `backfill.py` in Electricity, NaturalGas and Water; outputs `backfill_2025-01-01_2026-10-28.csv` (48 / 89 /
  132 rows). Per-source coverage and gaps are in each README's "Backfill" section.
- Correction to the item 1 note: the ≤8 / >8 kWh/gün AG mesken split already existed in 2024 (decision 12719);
  only the prices changed on 04.04.2026. The 2024–2025 layout is now parsed (`parse_table_2024()`).
- İGDAŞ: months with a mid-month change list each tier twice; the daily scraper failed on those (e.g. April 2026)
  and now takes the row in force today. Başkentgaz: a single household price before 04.04.2026 (written as
  Kademe-1), ÖTV 0.1187 → 0.1373 (03.07.2025) → 0.1468 (31.12.2025).
- ASKİ history only via the Wayback Machine: nothing archived between 03.12.2024 and Dec 2025, and two copies
  give only a month (written as the 1st). İZSU 01.01.2025 and 05.05.2025 exist only as images, transcribed into
  `InflationItems/Datas/04_Housing/Water/izsu_transcribed.csv`.
- Open: İzmir gas and the gas connection fees have no history source; for later items, check the Wayback CDX
  (`web.archive.org/cdx/search/cdx?url=...&collapse=digest`) early when a site keeps no archive.
- Day files added: 665 `YYYY-MM-DD.csv` per item (2025-01-01 .. 2026-10-27), version in force per city per day,
  daily schema, marked by `collected_at` = backfill run time (no `notes` column, unlike Armut's `backfill:` mark).
  Ankara water days in Jan–Nov 2025 carry the 03.12.2024 tariff because of the Wayback gap.
