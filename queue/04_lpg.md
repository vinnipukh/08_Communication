# 04 — LPG cylinder (12 kg tüp)

- **TÜİK item:** 0452201 LPG tüp
- **Scraper path:** `InflationItems/Codes/04_Housing/LPG/scraper.py` (one script, one function per brand)
- **Output:** `InflationItems/Datas/04_Housing/LPG/YYYY-MM-DD.csv`
- **Coverage:** all 81 provinces — each brand serves every province through the same endpoint, so the
  scope rule allows it. Istanbul is split Anadolu / Avrupa. Add `--provinces 34,6,35` for bounded runs.
- All four brands answered plain HTTP, no anti-bot, on 2026-10-28.

## Sources

### Aygaz — low–medium
- `GET https://www.aygaz.com.tr/api/session-token` → token.
- `GET https://www.aygaz.com.tr/api/proxy?type=Njg=` with headers `X-CALL-TYPE: 68`, `X-SessionToken: <token>`,
  `X-PARAMS: base64({"cityId":"34","validityDate":"2026-10-02T00:00:00","productId":"1"})`
  (productId 1 = grey 12 kg) → JSON.
- City list and validity dates: `__NEXT_DATA__` on `https://www.aygaz.com.tr/fiyatlar/tupgaz`. Use the
  newest validity date.
- Sample: Istanbul 1700, Ankara 1645, İzmir 1645 TL (deposit 320 TL).

### Milangaz — low
- `POST https://milangaz.com.tr/wp-admin/admin-ajax.php`, form body
  `action=get_city_code&city_code=34&city_type=TUBE` (Istanbul Avrupa = 134) → JSON, all products per call.
- Sample: Istanbul Anadolu 1660, Ankara 1650, İzmir 1660 TL.

### Mogaz — low
- `POST https://www.mogaz.com.tr/processor/GetTupGazPrice`, form body
  `city=34&tubeType=FIYAT12&expiryDate=02.10.2026` → JSON.
- Dates: the select on `https://www.mogaz.com.tr/tupgaz/fiyatlar`.
- Sample: Istanbul Anadolu 1700, Ankara 1645, İzmir 1643 TL.

### İpragaz — low
- `GET https://www.ipragaz.com.tr/evde/tupgaz-fiyatlari-sonuc?city=Ankara` (Turkish names, e.g.
  `İstanbul - Avrupa`) → server-rendered HTML.
- Returned 1680 TL for every city tried (incl. Hakkari) — maybe a single national price. Unverified; if
  confirmed national, fetch once instead of 81 times.

### Likitgaz — skipped
- Connection failed during recon. Optional: retry; drop if still unreachable.

## CSV columns

`product_name, price, category_number (4), sub_category_number (0452201)`, then
`brand, province, province_code, product (e.g. "12 kg tüp"), deposit (if given), valid_from,
source_url, collected_at`. `price` = TL per cylinder.

Politeness: 1 s between requests → ~330 requests ≈ 5–7 min.
