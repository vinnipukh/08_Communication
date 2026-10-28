# 02 — Natural gas residential price + connection fee

- **TÜİK items:** 0452101 Doğal gaz, 0452102 Doğal gaz bağlantı ücreti
- **Scraper path:** `InflationItems/Codes/04_Housing/NaturalGas/scraper.py` (one script, three distributors + fees)
- **Output:** `InflationItems/Datas/04_Housing/NaturalGas/YYYY-MM-DD.csv`
- **Coverage:** Istanbul, Ankara, İzmir. No aggregated per-city source exists (EPDK/BOTAŞ publish only
  decisions and the national wholesale tariff); each distributor shows only its own city.

Retail price = BOTAŞ wholesale + ÖTV (0.1468 TL/m³) + distributor SKB (system usage fee).

## Sources

### İGDAŞ (Istanbul) — low
- Page `https://igdas.istanbul/musteri-hizmetleri/fiyat-tarifeleri/perakende-satis-fiyatlari` is Nuxt
  client-rendered (no prices in HTML). **Changed (re-checked 2026-10-28):** `www.igdas.istanbul` closes the
  connection for curl_cffi (every impersonation profile) and only 301-redirects to the bare host for httpx;
  use `igdas.istanbul` (no `www.`) for the pages.
- Data: `POST https://api.igdas.istanbul/Sap/Sap/PerakendeSatisFiyati`, JSON body `{"AYYIL":"102026"}`
  (MMYYYY) → JSON, TL/m³ and TL/kWh. Oct 2026: KONUT 13.807908 TL/m³, KONUT KADEME-2 21.182908.
- Monthly. F5 cookies, plain request worked.
- No tax footnote anywhere on the page (in a browser the page showed "Fiyat bilgileri şu anda
  görüntülenemiyor"). Figures are ÖTV-included, VAT-excluded by arithmetic: Kademe-1 13.807908 − gas 10.625 −
  ÖTV 0.1468 = SKB 3.036; Kademe-2 − Kademe-1 = 7.375 = 18.0 − 10.625 gas, as in Ankara and İzmir.
- `AYYIL` for a future month already answers (Nov 2026 returned Oct's prices with `ABDATUM` 2026-11-01).

### Başkentgaz (Ankara) — medium (PDF)
- Real domain `baskentdogalgaz.com.tr` (React); `baskentgaz.com.tr` timed out.
- List: `GET https://bskapiv1.baskentdogalgaz.com.tr/api/menus/31/sections` → entries with `imageUrl`.
- PDFs: `https://www.baskentdogalgaz.com.tr/uploads/<uuid>.pdf` (NOT on the API host — 404 there).
- Text PDF, TL/Sm³ and TL/kWh. Household tier 0–75,000 = 14.468019; Kademe-2 = 21.843019.
- Monthly (sometimes two PDFs in a month — take the newest by its validity date). Titles: "2026 Ekim Ayı
  Değerleri için tıklayınız.", split months "2026 Nisan Ayı Değerleri (04.Gün ve Sonrası İçin Geçerli)";
  `rowNumber` grows with time; `startDate` is set when a PDF is posted ahead of its month.
- PDF (pypdf text): household row "BASKENT02 0-75.000 <K1 Sm³> <K1 kWh> <K2 Sm³> <K2 kWh>" (ABONE); notes
  "0,1468 TL/Sm3 ÖTV bedeli dahildir", "%20 KDV dahil değildir"; header "YIL: 2026 AY: EKİM".

### İzmirgaz (İzmir) — low
- `https://www.izmirgaz.com.tr/musteri_hizmetleri.php?data=id44` loads the fragment
  `https://www.izmirgaz.com.tr/pages/musteri_hizmetleri/konut.php` → plain HTML table, TL/m³ and TL/kWh,
  VAT excluded. Oct 2026 K1 = 15.650179 (gas 10.625 + ÖTV 0.1468 + SKB 4.878379); Kademe-2 = 23.025179.
- **Changed (re-checked 2026-10-28):** the server sends only its leaf certificate (`*.izmirgaz.com.tr`, issuer
  Sectigo Public Server Authentication CA DV R36), so curl_cffi and httpx fail verification. The issuer is at
  the certificate's AIA URL `http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt`; adding it to
  the certifi bundle makes verification pass. "K1" in "0-100.000 (K1)" is the annual SKB band, not Kademe-1.
- Archive: `tarifeler_arsiv_konut.php` (useful for backfill, optional).

## Connection / deposit fees (0452102)

- National caps set yearly by EPDK board decision (2026, effective 01.01.2026, VAT excl.):
  abone bağlantı bedeli 8,066 TL; ek bağlantı 7,016 TL / 100 m²; güvence: kombi 4,097, soba 3,599, ocak 249 TL.
- Scrape from one place; all three show it:
  - İGDAŞ HTML `.../fiyat-tarifeleri/baglanti-guvence-ve-hizmet-bedelleri`
  - İzmirgaz fragments `pages/musteri_hizmetleri/abone_baglanti.php`, `guvence.php`
  - Başkentgaz API `menus/42/sections` (VAT-included: 9,679.20 = 8,066 × 1.2)
- Prefer İGDAŞ or İzmirgaz (plain HTML). Write per-city rows only if the three actually differ.
- Re-checked 2026-10-28: İGDAŞ's fee page (server-rendered HTML) has no year or VAT note; İzmirgaz's fragments
  carry the decision text (year, "01/01/2026 tarihinden geçerli", "Katma Değer Vergisi dâhil değildir"), so the
  scraper takes the fees from İzmirgaz. Başkentgaz's deposits (güvence) are not VAT-grossed (Kombi 4,097), only
  the connection fees are. All three matched.

## CSV columns

`product_name, price, category_number (4), sub_category_number (0452101 | 0452102)`, then
`province, distributor, tier (e.g. "Konut K1 0–75,000 kWh"), price_per_m3, price_per_kwh, unit,
vat_included, components (gas/ötv/skb if given), valid_from, source_url, collected_at`.
`price` = TL/m³ for gas rows, TL for fee rows.
