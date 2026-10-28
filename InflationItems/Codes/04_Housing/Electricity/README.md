# Electricity — EPDK residential tariff (TÜİK 0451001 Elektrik)

Fetches the newest EPDK "elektrik faturalarına esas tarife tabloları" XLSX and writes its residential
(mesken) rows. One national tariff (national tariff equalisation), so there are no per-city rows.

```bash
python InflationItems/Codes/04_Housing/Electricity/scraper.py
```

- Requests: 3 (tariff page, `POST /Detay/GetFastAccessList` with `{"fId":"1327"}`, XLSX download),
  1 s apart. Runtime ~4 s (measured 2026-10-28).
- Output: `InflationItems/Datas/04_Housing/EPDK/epdk_YYYY-MM-DD.csv` (upstream layout: one CSV per store and
  day, store = EPDK), written every run even when the decision has not changed (dense time series).
  `--output <path>` writes all rows to that CSV instead of the day file (test runs).
- Rows: every `Mesken` row of the table (OG çift terim, OG tek terim, AG tek terim ≤8 and >8 kWh/gün),
  one per time band (tek zamanlı, gündüz, puant, gece). The household tariff for the CPI is
  `AG Tek Terim` / `tek zamanlı`; the ≤8 kWh/gün tier applies to the first 8 kWh/day of a bill.
- Columns: `product_name, price, category_number, sub_category_number, tariff_group, voltage, time_band,
  energy_charge, distribution_charge, total, unit, vat_included, effective_date, decision_no, source_url,
  collected_at`. Charges, `total` and `price` are TL/kWh without taxes (EPDK publishes kuruş/kWh; divided by 100), `unit` = `TL/kWh`; `price` = `total`. The OG çift terim power
  charge (kr/kW/ay) is not in `total`.
- Not covered: the last-resort tariff (son kaynak tedarik) for households above the annual limit; EPDK
  publishes it under a separate communiqué, not in this table.

## Backfill

```bash
python InflationItems/Codes/04_Housing/Electricity/backfill.py                      # from 2025-01-01
python InflationItems/Codes/04_Housing/Electricity/backfill.py --start 2024-01-01
```

Writes `logs/backfill/epdk_<start>_<today>.csv` (gitignored, same columns) with every decision that took effect from `--start` to
today, plus the one in force on `--start`. It then writes one `InflationItems/Datas/04_Housing/EPDK/epdk_YYYY-MM-DD.csv` per day from
`--start` to yesterday, like the daily scraper's files, holding the decision in force that day (recognisable by
`collected_at`, the backfill run time, and `effective_date`); existing day files are never overwritten
(`--no-daily` skips them). Run on 2026-10-28 from 2025-01-01: 48 rows, decisions 12719 (01.07.2024), 13426
(05.04.2025), 14461 (04.04.2026), 665 day files of 16 rows, 4 requests, ~6 s. Tables up to 05.04.2025 use an older
layout (`parse_table_2024()`); the ≤8 / >8 kWh/gün AG mesken split already existed in 2024. Decisions before
2024 are untested.

## Troubleshooting

- `tariff sheet layout changed, missing headers: ...` — EPDK changed the XLSX layout (tables up to 05.04.2025
  are read by `parse_table_2024()`). Update the parser; no CSV is written for that run.
- `tariff list is empty or changed shape` — the list endpoint's JSON changed; re-check it in the browser's
  network tab on the tariff page.
- Needs `curl_cffi` and `openpyxl` (`requirements.txt`, `pyproject.toml`, `uv.lock`).
- Git Bash on Windows garbles Turkish output; set `PYTHONIOENCODING=utf-8`.

## Notes

- Schedule: daily 09:00 Istanbul on GitHub Actions (`.github/workflows/scraper_04_utilities.yml`, since 2026-10-28).
- `GetFastAccessList` answers an object; the decisions are under `model`, not a bare array. Per decision,
  `IsFileType` 1 = decision PDF, 2 = XLSX table.
- Reusable: the `Client` class in `scraper.py` (curl_cffi Chrome session, page first, jittered ~1 s delay,
  honours `Retry-After`, fails after 3 backoffs) is the pattern the other 04 utility scrapers copied.
