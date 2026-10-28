# NaturalGas — residential gas price + connection fees (TÜİK 0452101, 0452102)

Fetches the household natural gas retail price for İstanbul (İGDAŞ), Ankara (Başkentgaz) and İzmir
(İzmirgaz), plus the EPDK connection and deposit fee caps. No source publishes all cities, so each city comes
from its own distributor.

```bash
python InflationItems/Codes/04_Housing/NaturalGas/scraper.py
python InflationItems/Codes/04_Housing/NaturalGas/scraper.py --source izmirgaz fees   # bounded run
```

- Requests: ~11 (İGDAŞ fee page + price API; Başkentgaz PDF list + PDF + fee section; İzmirgaz certificate
  check, intermediate certificate, page, tariff fragment, two fee fragments), 1 s apart per host.
  Runtime ~7 s (measured 2026-10-28).
- Output (upstream layout: one CSV per store and day): `InflationItems/Datas/04_Housing/<Store>/<store>_YYYY-MM-DD.csv`
  with Store = `IGDAS`, `Baskentgaz`, `Izmirgaz` (`igdas_`, `baskentgaz_`, `izmirgaz_`), written every run
  (dense time series). The fee rows come from İzmirgaz's site and go to the İzmirgaz file. `--output <path>`
  writes all rows to that one CSV instead of the store files (test runs).
- Gas rows (0452101): Kademe-1 and Kademe-2 per city for the household tier. Kademe-2 applies to the whole
  month's consumption once it passes the city's monthly limit (EPDK, since 04.04.2026). Prices include ÖTV
  (0.1468 TL/m³) and exclude 20 % VAT. `price` = TL/kWh for all three distributors (`unit` = `TL/kWh`): bills are
  in kWh, and the volume prices are not one unit (Başkentgaz quotes TL/Sm³, the others TL/m³). The volume price
  stays in `price_per_m3`. All history files were converted on 2026-10-28.
- Fee rows (0452102): the EPDK caps from İzmirgaz (connection, extra connection per 100 m², connection
  inspection, deposits per appliance), province `Türkiye`, VAT excluded. The run compares the connection fee
  and the kombi deposit with İGDAŞ and Başkentgaz (VAT-included connection fee / 1.2) and logs a warning if
  one differs; on 2026-10-28 all three matched.
- Columns: `product_name, price, category_number, sub_category_number, province, distributor, tier,
  price_per_m3, price_per_kwh, unit, vat_included, components, valid_from, source_url, collected_at`.
  `components` = `gas;ötv;skb` where the source gives them (İzmirgaz).
- A source that fails is logged, the others are still written, and the run exits with status 1. If every
  source fails no CSV is written.

## Sources

| City | Distributor | Endpoint | Format |
|---|---|---|---|
| İstanbul | İGDAŞ | `POST https://api.igdas.istanbul/Sap/Sap/PerakendeSatisFiyati` `{"AYYIL":"MMYYYY"}` | JSON |
| Ankara | Başkentgaz | `GET https://bskapiv1.baskentdogalgaz.com.tr/api/menus/31/sections` → newest `/uploads/<uuid>.pdf` on `www.baskentdogalgaz.com.tr` | text PDF (pypdf) |
| İzmir | İzmirgaz | `GET https://www.izmirgaz.com.tr/pages/musteri_hizmetleri/konut.php` | HTML table |
| fees | İzmirgaz | `.../abone_baglanti.php`, `.../guvence.php` | HTML (EPDK decision text) |

## Backfill

```bash
python InflationItems/Codes/04_Housing/NaturalGas/backfill.py                        # from 2025-01-01
python InflationItems/Codes/04_Housing/NaturalGas/backfill.py --start 2026-01-01 --source igdas
```

Writes `logs/backfill/natural_gas_<start>_<today>.csv` (gitignored, same columns) with one row per tier and
price version (`valid_from`) from `--start` to today, plus the version in force on `--start`. It then writes one
`<Store>/<store>_YYYY-MM-DD.csv` per store and day from `--start` to yesterday, like the daily scraper's files,
holding the version in force that day (recognisable by `collected_at`, the backfill run time, and
`valid_from`). Existing day files are never overwritten, and day files are written only when every source
succeeded (`--no-daily` skips them). Sources (`--source`): `igdas`, `baskentgaz`, `izmirgaz`, `fees`.

Run on 2026-10-28 from 2025-01-01 (all four sources): 129 version rows, 665 day files per store
(2025-01-01 .. 2026-10-27). İGDAŞ 2 rows a day; Başkentgaz 1 row before 04.04.2026, 2 after; İzmirgaz
Kademe-1 plus the fee rows (4 rows a day in 2025, 10 in 2026).

- İGDAŞ: the price API answers past months; a month with a mid-month change lists each tier twice
  (`ABDATUM`). Before 04.04.2026 KONUT and KONUT KADEME-2 carry the same price (both are written).
- Başkentgaz: every monthly PDF since 2018 is listed; split months have one PDF per part ("4.Gün ve Öncesi",
  "2.Gün İçin Geçerli", "3.Gün ve Sonrası"). Before 04.04.2026 the household row has a single price, written
  as `Konut Kademe-1`. The ÖTV in `components` is read from each PDF (0.1187 → 0.1373 on 03.07.2025 → 0.1468
  on 31.12.2025).
- İzmirgaz: the archive fragments `tarifeler_arsiv_konut.php` (TL/m³) and `tarifeler_arsiv_konut_kwh.php`
  (TL/kWh) list every monthly version back to 2021 in annual bands K1..K5; K1 (the household band) is written as
  Kademe-1. Kademe-2 (since 04.04.2026) has no archive (its "Arşiv" link points to the şehit ve gazi archive), so
  İzmir Kademe-2 starts with the daily scraper.
- Fees (0452102, EPDK national caps, VAT excluded, written to the İzmirgaz files): the 2026 caps from
  İzmirgaz's live fee pages, valid from 2026-01-01. No site keeps the 2025 caps and the Wayback Machine has no
  copy, so the three 2025 connection caps (6,154 TL connection, 5,353 TL per extra 100 m², 3,471 TL inspection
  for the first 100 m; effective 01.01.2025) are transcribed in `fees_transcribed.csv` next to the script
  (source: Bloomberg HT, 31.12.2024; YatırımX gives the same figures). The 2025 deposit (güvence) caps were
  found in no second source and are not written, so 2025 day files have no deposit rows.

## Troubleshooting

- `İzmirgaz sends no intermediate certificate` (info) — expected: the server omits the Sectigo DV R36
  intermediate. The scraper adds it from the certificate's AIA URL to a temporary CA bundle and keeps
  verifying. If İzmirgaz renews with another CA, update `IZMIRGAZ_INTERMEDIATE`.
- İGDAŞ connection errors — use `igdas.istanbul`, not `www.igdas.istanbul` (the `www.` host drops
  curl_cffi connections).
- `İGDAŞ MMYYYY: no KONUT / KONUT KADEME-2 price in force` — the API listed only future-dated rows for this
  month; in a month with a mid-month change the daily run takes the row in force today.
- `Başkentgaz PDF period ... does not match` — the period line has had several forms ("YIL: 2026 AY: EKİM",
  "YIL : 2025 AY: 01-04 NİSAN", "02 TEMMUZ 2025 TARİHİ İÇİN GEÇERLİ"); add the new one to `baskent_pdf()`.
- `household (ABONE 0-75.000) row not found` — the PDF layout changed; print
  `PdfReader(...).pages[0].extract_text()` and adjust the regex in `baskent_pdf()`.
- `İzmirgaz konut.php: tariff tables changed` — the "Konut Tüketicileri Kademe-1/2" tables moved or were renamed.
- Needs `curl_cffi`, `beautifulsoup4`, `lxml`, `pypdf`, `certifi` (`requirements.txt`).
- Git Bash on Windows garbles Turkish output; set `PYTHONIOENCODING=utf-8`.

## Notes

- Schedule: not on GitHub Actions — İGDAŞ, Başkentgaz and İzmirgaz time out from runner IPs (every attempt,
  test run 2026-10-28); to be run daily from the cron server (`deploy/scraper-server`), not set up yet.
- İGDAŞ has no tax footnote; its prices are ÖTV-included and VAT-excluded by arithmetic (Kademe-1 − gas − ÖTV
  = SKB, as at the other two). İGDAŞ's fee page has no year or VAT note, so the fee rows come from İzmirgaz.
  Başkentgaz grosses its connection fee up by VAT but not its deposits.
- Reusable: `izmirgaz_client()` (adds a missing intermediate from the AIA URL, verification stays on) for any
  host without an intermediate certificate; `tr_month()` for Turkish month names (`"EKİM".lower()` is not
  `"ekim"` because of the dotted İ); `tr_number()` for "14,468019" / "₺9.679,20" / "8.066".
- `pypdf` and `certifi` were added to `requirements.txt`, `pyproject.toml` and `uv.lock` for this scraper.
- Open: İzmirgaz's intermediate URL is a constant, so a CA change needs a code update. Başkentgaz split months
  (e.g. April 2026) take the later PDF only in the daily run.
