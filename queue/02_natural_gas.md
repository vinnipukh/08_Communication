# 02 — Natural gas residential price + connection fee

- **TÜİK items:** 0452101 Doğal gaz, 0452102 Doğal gaz bağlantı ücreti
- **Scraper path:** `InflationItems/Codes/04_Housing/NaturalGas/scraper.py` (one script, three distributors + fees)
- **Output:** `InflationItems/Datas/04_Housing/NaturalGas/YYYY-MM-DD.csv`
- **Coverage:** Istanbul, Ankara, İzmir. No aggregated per-city source exists (EPDK/BOTAŞ publish only
  decisions and the national wholesale tariff); each distributor shows only its own city.

Retail price = BOTAŞ wholesale + ÖTV (0.1468 TL/m³) + distributor SKB (system usage fee).

## Sources

### İGDAŞ (Istanbul) — low
- Page `https://www.igdas.istanbul/musteri-hizmetleri/fiyat-tarifeleri/perakende-satis-fiyatlari` is Nuxt
  client-rendered (no prices in HTML).
- Data: `POST https://api.igdas.istanbul/Sap/Sap/PerakendeSatisFiyati`, JSON body `{"AYYIL":"102026"}`
  (MMYYYY) → JSON, TL/m³ and TL/kWh. Oct 2026: KONUT 13.807908 TL/m³, KONUT KADEME-2 21.182908.
- Monthly. F5 cookies, plain request worked.
- Unverified: whether İGDAŞ figures include ÖTV / exclude VAT — confirm from the page footnote.

### Başkentgaz (Ankara) — medium (PDF)
- Real domain `baskentdogalgaz.com.tr` (React); `baskentgaz.com.tr` timed out.
- List: `GET https://bskapiv1.baskentdogalgaz.com.tr/api/menus/31/sections` → entries with `imageUrl`.
- PDFs: `https://www.baskentdogalgaz.com.tr/uploads/<uuid>.pdf` (NOT on the API host — 404 there).
- Text PDF, TL/Sm³ and TL/kWh. Household tier 0–75,000 = 14.468019; Kademe-2 = 21.843019.
- Monthly (sometimes two PDFs in a month — take the newest by its validity date).

### İzmirgaz (İzmir) — low
- `https://www.izmirgaz.com.tr/musteri_hizmetleri.php?data=id44` loads the fragment
  `https://www.izmirgaz.com.tr/pages/musteri_hizmetleri/konut.php` → plain HTML table, TL/m³ and TL/kWh,
  VAT excluded. Oct 2026 K1 = 15.650179 (gas 10.625 + ÖTV 0.1468 + SKB 4.878379); Kademe-2 = 23.025179.
- Archive: `tarifeler_arsiv_konut.php` (useful for backfill, optional).

## Connection / deposit fees (0452102)

- National caps set yearly by EPDK board decision (2026, effective 01.01.2026, VAT excl.):
  abone bağlantı bedeli 8,066 TL; ek bağlantı 7,016 TL / 100 m²; güvence: kombi 4,097, soba 3,599, ocak 249 TL.
- Scrape from one place; all three show it:
  - İGDAŞ HTML `.../fiyat-tarifeleri/baglanti-guvence-ve-hizmet-bedelleri`
  - İzmirgaz fragments `pages/musteri_hizmetleri/abone_baglanti.php`, `guvence.php`
  - Başkentgaz API `menus/42/sections` (VAT-included: 9,679.20 = 8,066 × 1.2)
- Prefer İGDAŞ or İzmirgaz (plain HTML). Write per-city rows only if the three actually differ.

## CSV columns

`product_name, price, category_number (4), sub_category_number (0452101 | 0452102)`, then
`province, distributor, tier (e.g. "Konut K1 0–75,000 kWh"), price_per_m3, price_per_kwh, unit,
vat_included, components (gas/ötv/skb if given), valid_from, source_url, collected_at`.
`price` = TL/m³ for gas rows, TL for fee rows.
