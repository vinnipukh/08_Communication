# LPG — 12 kg cylinder price (TÜİK 0452201)

Fetches the household 12 kg LPG cylinder (tüp) price of four brands — Aygaz, Milangaz, Mogaz, İpragaz — for
every province each brand lists. All four answer per province through one endpoint, so all 81 provinces are
taken (the İstanbul / Ankara / İzmir scope rule allows it when no extra code is needed).

```bash
python InflationItems/Codes/04_Housing/LPG/scraper.py
python InflationItems/Codes/04_Housing/LPG/scraper.py --provinces 34 6 35          # bounded run
python InflationItems/Codes/04_Housing/LPG/scraper.py --brand ipragaz --provinces 6
python InflationItems/Codes/04_Housing/LPG/scraper.py --backfill-from 2025-01-01   # Aygaz history + day files
python InflationItems/Codes/04_Housing/LPG/scraper.py --days-from <history.csv>     # day files only, no requests
```

- Requests: ~336 (one city-list page per brand, one Aygaz token, then one per city: Aygaz 82, Milangaz 82,
  Mogaz 82, İpragaz 84), 1 s apart per host. The four brands run at the same time (one thread and one
  session each), so a run lasts as long as the slowest brand, Milangaz (~2.5 s per request). Full run ~3.5 min
  (207 s measured 2026-10-28; 559 s when the brands ran one after another).
- Output (upstream layout: one CSV per store and day): `InflationItems/Datas/04_Housing/<Store>/<store>_YYYY-MM-DD.csv`
  with Store = `Aygaz`, `Milangaz`, `Mogaz`, `Ipragaz` (`aygaz_`, `milangaz_`, `mogaz_`, `ipragaz_`), written
  every run. `--output <path>` writes all rows to that one CSV instead of the store files (test runs).
- Rows: one per brand × province (× İstanbul side). Milangaz writes two 12 kg products ("VANALI" and
  "SİBOPLU", same price); filter on `product` if one row per brand is needed. `price` = TL per cylinder,
  VAT included (each brand's ceiling / recommended retail price). `deposit` (cylinder deposit) only from Aygaz.
- `province_code` is the 2-digit plate. `region` is `Anadolu` / `Avrupa` / `Adalar` for İstanbul and
  `Bozcaada-Gökçeada` for İpragaz's "Çanakkale-B.G. Ada"; empty otherwise.
- `valid_from`: Aygaz and Mogaz from their newest validity date, İpragaz from the result page text; Milangaz
  gives none (empty).
- Columns: `product_name, price, category_number, sub_category_number, brand, province, region,
  province_code, product, deposit, valid_from, source_url, collected_at`.
- A province that fails is logged and skipped, a brand that fails is logged; the rest is written and the run
  exits with status 1. If every brand fails no CSV is written. A price outside 300–20 000 TL fails that
  province (parse guard).

## Backfill (history)

Only Aygaz serves past prices: the validity-date list on its price page goes back to 2013-01-04 and the
price API answers any listed date. Mogaz answers an empty price for past dates; Milangaz and İpragaz take
no date at all. `--backfill-from YYYY-MM-DD` runs Aygaz only, for every validity date from that day on, and
writes `logs/backfill/aygaz_<from>_<today>.csv` (gitignored; one row per city and validity date;
`valid_from` is the historical date, `collected_at` the run time), then one `Aygaz/aygaz_YYYY-MM-DD.csv` per day from
<from> to yesterday with the Aygaz prices in force that day, like items 1–3. Existing day files are never
overwritten, so past days hold Aygaz only (82 rows) and real daily runs hold all four brands.
`--days-from <history.csv>` writes only the day files from a saved history CSV, without requests. `deposit` is what the API returns for that date
(320 TL for every date since 2025). The backfill from 2025-01-01 (22 dates × 82 cities = 1 804 requests to one
host) took 2 278 s (~38 min) on 2026-10-28; for İstanbul, Ankara and İzmir only (`--provinces 34 6 35`) it is
88 requests, ~2 min. Its history is `logs/backfill/aygaz_2025-01-01_2026-10-28.csv`
(the old `Datas/04_Housing/LPG/backfill/` folder is gone); the 665 day files 2025-01-01 .. 2026-10-27 were
written from it with `--days-from`. Coverage jumps from Aygaz only to four brands on 2026-10-28. Ask before
running a full-province backfill (thousands of requests to one host). Aygaz gave 12 transient HTTP 500s in
~1 800 requests, all fixed by the retry. Some listed dates carry unchanged 12 kg prices (e.g. 2025-03-27 … 2025-06-05); the date
list is shared with other Aygaz products.

## Sources

| Brand | City list | Price endpoint |
|---|---|---|
| Aygaz | `__NEXT_DATA__` on `https://www.aygaz.com.tr/fiyatlar/tupgaz` | `GET /api/session-token`, then `GET /api/proxy?type=Njg=` with `X-CALL-TYPE: 68`, `X-SessionToken`, `X-PARAMS` = base64 JSON `{cityId, validityDate, productId: "1"}` |
| Milangaz | `<select id="iller">` on `https://milangaz.com.tr/tupgaz/fiyatlar/` | `POST /wp-admin/admin-ajax.php` `action=get_city_code&city_code=06&city_type=TUBE` |
| Mogaz | `city` / `expiryDate` selects on `https://www.mogaz.com.tr/tupgaz/fiyatlar` | `POST /processor/GetTupGazPrice` `city=06&tubeType=FIYAT12&expiryDate=02.10.2026` |
| İpragaz | `Cities: [...]` in an inline script on `https://www.ipragaz.com.tr/evde/tupgaz-fiyatlari` | `GET /evde/tupgaz-fiyatlari-sonuc?city=<name>` (HTML) |

İstanbul Avrupa codes: Aygaz and Mogaz `341`, Milangaz `134`.

## Troubleshooting

- `Aygaz page attempt N: empty expiryDates / cities` — the Aygaz price page is sometimes served with empty
  lists (2026-10-30: the run died with `list index out of range`, no `aygaz_2026-10-30.csv`); the page is
  fetched again after 2 / 5 / 10 s, then the brand fails with `price page lists no validity dates / cities`.
- Mogaz İstanbul Avrupa (code 341) is not requested: Mogaz always answered an empty price for it (its own form
  shows nothing either), so Mogaz İstanbul is Anadolu only (`MOGAZ_SKIP` in scraper.py).
- `Aygaz: __NEXT_DATA__ not found` / `Milangaz: <select id='iller'> not found` / `Mogaz: city / expiryDate
  select not found` / `İpragaz: 'Cities: [...]' list not found` — the brand's price page changed.
- `İpragaz: unknown city name` — İpragaz added a name that is not a province; add it to `IPRAGAZ_NAMES`.
- `unknown city code` — a brand added a city code that is not a plate; extend `AVRUPA_CODES` or `plate_region()`.
- Needs `curl_cffi`, `beautifulsoup4`, `lxml` (`requirements.txt`).
- Git Bash on Windows garbles Turkish output; set `PYTHONIOENCODING=utf-8`.

## Notes

- Schedule: daily 09:00 Istanbul on GitHub Actions (`.github/workflows/scraper_04_utilities.yml`, since 2026-10-28).
- No history for the other brands (checked 2026-10-28): Milangaz has no Wayback copies; Mogaz's Wayback copies
  have no prices (they load by XHR) and its API answers empty prices for past dates; İpragaz has scattered
  Wayback copies, not of the three cities.
- City codes differ per brand: Aygaz unpadded plates (`6`), Milangaz and Mogaz zero-padded (`06`; Milangaz
  answers `null` to `6`). Aygaz lists `34` twice.
- İpragaz showed 1680 TL in all 84 cities on 2026-10-28, but an unknown city name answers with no prices, so
  the per-city lookup is real and is kept.
- Reusable: the `PROVINCES` plate → name table and `plate_region()` for any per-province source;
  `Client.request()` adds POST to the usual client; the one-thread-per-host pattern for sources on several
  hosts.
- Open: Milangaz gives no validity date (`valid_from` empty).
