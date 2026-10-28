# Electricity — EPDK residential tariff (TÜİK 0451001 Elektrik)

Fetches the newest EPDK "elektrik faturalarına esas tarife tabloları" XLSX and writes its residential
(mesken) rows. One national tariff (national tariff equalisation), so there are no per-city rows.

```bash
python InflationItems/Codes/04_Housing/Electricity/scraper.py
```

- Requests: 3 (tariff page, `POST /Detay/GetFastAccessList` with `{"fId":"1327"}`, XLSX download),
  1 s apart. Runtime ~4 s (measured 2026-10-28).
- Output: `InflationItems/Datas/04_Housing/Electricity/YYYY-MM-DD.csv`, written every run even when the
  decision has not changed (dense time series).
- Rows: every `Mesken` row of the table (OG çift terim, OG tek terim, AG tek terim ≤8 and >8 kWh/gün),
  one per time band (tek zamanlı, gündüz, puant, gece). The household tariff for the CPI is
  `AG Tek Terim` / `tek zamanlı`; the ≤8 kWh/gün tier applies to the first 8 kWh/day of a bill.
- Columns: `product_name, price, category_number, sub_category_number, tariff_group, voltage, time_band,
  energy_charge, distribution_charge, total, unit, vat_included, effective_date, decision_no, source_url,
  collected_at`. Charges are kuruş/kWh without taxes; `price` = `total` in TL/kWh. The OG çift terim power
  charge (kr/kW/ay) is not in `total`.
- Not covered: the last-resort tariff (son kaynak tedarik) for households above the annual limit; EPDK
  publishes it under a separate communiqué, not in this table.

## Troubleshooting

- `tariff sheet layout changed, missing headers: ...` — EPDK changed the XLSX layout (the 2025 table
  had another one). Update `parse_table()`; no CSV is written for that run.
- `tariff list is empty or changed shape` — the list endpoint's JSON changed; re-check it in the browser's
  network tab on the tariff page.
- Needs `curl_cffi` and `openpyxl` (`requirements.txt`).
