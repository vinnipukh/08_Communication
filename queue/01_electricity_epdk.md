# 01 — Electricity residential tariff (EPDK)

- **TÜİK item:** 0451001 Elektrik
- **Scraper path:** `InflationItems/Codes/04_Housing/Electricity/scraper.py`
- **Output:** `InflationItems/Datas/04_Housing/Electricity/YYYY-MM-DD.csv`
- **Coverage:** one national residential tariff (national tariff equalisation) — no per-city work.

## Source

- Page: `https://www.epdk.gov.tr/Detay/Icerik/3-1327/elektrik-faturalarina-esas-tarife-tablolari`
  (the list on it is JS-loaded; the HTML is empty).
- List endpoint: `POST https://www.epdk.gov.tr/Detay/GetFastAccessList`, JSON body `{"fId":"1327"}`
  → JSON object `{"Type": 1, "model": [...], "State", "fId", "AllowGet"}`; the entries are in `model`
  (71 on 2026-10-28, newest first; re-checked 2026-10-28: it is not a bare array). Newest: decision 14461,
  02.04.2026, effective 04.04.2026. Per entry: `Number`, `Date`, `DateValue`, `RgDate` (Resmî Gazete),
  `FastAccessDetail[]` = the decision PDF (`IsFileType` 1) and the tariff table (`IsFileType` 2, XLSX).
- File: `GET https://www.epdk.gov.tr/Detay/DownloadDocument?id=<ContentId>` (URL-encode `+` in the id).
  Format: XLSX, one sheet, prices in **kuruş/kWh**, taxes excluded.
- Anti-bot: F5 "TS" cookies only; plain requests worked. No captcha/403 seen.
- Update frequency: on EPDK board decisions (roughly yearly in 2024–2026).

## Extract

From the newest table, residential (mesken) rows, low-voltage, single-time (tek zamanlı) — plus
the multi-time rows if cheap to add:
- active energy charge (enerji bedeli), distribution charge (dağıtım bedeli), total — kuruş/kWh
- tariff effective date and EPDK decision number

Note: households above the annual limit (4,000 kWh) move to the last-resort tariff
(son kaynak tedarik tarifesi), not in this table. Check whether EPDK publishes it in the same list;
take it only if it is in the same file/list.
Checked 2026-10-28: it is not in this file or list (the sheet's note refers to the separate communiqué).
Since 04.04.2026 AG mesken has two rows: "Mesken (8 kWh/gün ve altı)" and "Mesken (8 kWh/gün üstü)".

## CSV columns

`product_name, price, category_number (4), sub_category_number (0451001)`, then
`tariff_group, voltage, time_band, energy_charge, distribution_charge, total, unit (kuruş/kWh),
vat_included (false), effective_date, decision_no, source_url, collected_at`.

`price` = total, converted to TL/kWh. Write a file every run even when the decision is unchanged
(keeps the time series dense).
