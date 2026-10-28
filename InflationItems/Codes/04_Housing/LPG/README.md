# LPG — 12 kg cylinder price (TÜİK 0452201)

Fetches the household 12 kg LPG cylinder (tüp) price of four brands — Aygaz, Milangaz, Mogaz, İpragaz — for
every province each brand lists. All four answer per province through one endpoint, so all 81 provinces are
taken (the İstanbul / Ankara / İzmir scope rule allows it when no extra code is needed).

```bash
python InflationItems/Codes/04_Housing/LPG/scraper.py
python InflationItems/Codes/04_Housing/LPG/scraper.py --provinces 34 6 35          # bounded run
python InflationItems/Codes/04_Housing/LPG/scraper.py --brand ipragaz --provinces 6
```

- Requests: ~336 (one city-list page per brand, one Aygaz token, then one per city: Aygaz 82, Milangaz 82,
  Mogaz 82, İpragaz 84), 1 s apart per host. The four brands run at the same time (one thread and one
  session each), so a run lasts as long as the slowest brand, Milangaz (~2.5 s per request). Full run ~3.5 min
  (207 s measured 2026-10-28; 559 s when the brands ran one after another).
- Output: `InflationItems/Datas/04_Housing/LPG/YYYY-MM-DD.csv`, written every run.
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

## Sources

| Brand | City list | Price endpoint |
|---|---|---|
| Aygaz | `__NEXT_DATA__` on `https://www.aygaz.com.tr/fiyatlar/tupgaz` | `GET /api/session-token`, then `GET /api/proxy?type=Njg=` with `X-CALL-TYPE: 68`, `X-SessionToken`, `X-PARAMS` = base64 JSON `{cityId, validityDate, productId: "1"}` |
| Milangaz | `<select id="iller">` on `https://milangaz.com.tr/tupgaz/fiyatlar/` | `POST /wp-admin/admin-ajax.php` `action=get_city_code&city_code=06&city_type=TUBE` |
| Mogaz | `city` / `expiryDate` selects on `https://www.mogaz.com.tr/tupgaz/fiyatlar` | `POST /processor/GetTupGazPrice` `city=06&tubeType=FIYAT12&expiryDate=02.10.2026` |
| İpragaz | `Cities: [...]` in an inline script on `https://www.ipragaz.com.tr/evde/tupgaz-fiyatlari` | `GET /evde/tupgaz-fiyatlari-sonuc?city=<name>` (HTML) |

İstanbul Avrupa codes: Aygaz and Mogaz `341`, Milangaz `134`. Likitgaz was dropped (host does not resolve).

## Troubleshooting

- `Mogaz lists no price for İstanbul Avrupa` (warning) — Mogaz answers an empty price for code 341; its own
  form shows nothing either. Not a failure; check the site if it persists after a price change.
- `Aygaz: __NEXT_DATA__ not found` / `Milangaz: <select id='iller'> not found` / `Mogaz: city / expiryDate
  select not found` / `İpragaz: 'Cities: [...]' list not found` — the brand's price page changed.
- `İpragaz: unknown city name` — İpragaz added a name that is not a province; add it to `IPRAGAZ_NAMES`.
- `unknown city code` — a brand added a city code that is not a plate; extend `AVRUPA_CODES` or `plate_region()`.
- Needs `curl_cffi`, `beautifulsoup4`, `lxml` (`requirements.txt`).
- Git Bash on Windows garbles Turkish output; set `PYTHONIOENCODING=utf-8`.
