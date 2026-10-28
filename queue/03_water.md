# 03 — Municipal water tariff (İSKİ, ASKİ, İZSU)

- **TÜİK item:** 0441101 Belediye suyu
- **Scraper path:** `InflationItems/Codes/04_Housing/Water/scraper.py`
- **Output:** `InflationItems/Datas/04_Housing/Water/YYYY-MM-DD.csv`
- **Coverage:** Istanbul, Ankara, İzmir. No regularly updated multi-city source exists (only one-off
  news comparisons) — do not chase one.
- All three answered plain requests (HTTP 200, no captcha/Cloudflare/403) on 2026-10-28.

## Sources

### İSKİ (Istanbul) — low
- `https://iski.istanbul/abone-hizmetleri/abone-rehberi/su-birim-fiyatlari/` — server-rendered, but the
  table is not real HTML: it is HTML-escaped inside `<vue-markdown source='...'>` (parse the attribute as its
  own document; re-checked 2026-10-28). Heading "2026 SU SATIŞ TARİFELERİ (KDV HARİÇ)".
- Konut: 3 tiers (0–15, 16–30, 31+ m³), each su / atık su / toplam. Tier 1 = 43.70 + 21.82 = 65.52.
- Prices change **monthly** ((TÜFE + Yİ-ÜFE)/2). The HTML table has no month label. The yearly PDF (hashed
  filename; take its link from the HTML, e.g. `iskiapi.iski.gov.tr/uploads/2026_aylik_su_ve_atiksu_birim_fiyatlari_...pdf`)
  has one column per month. Resolved 2026-10-28: pypdf does extract the date headers (5.01.2026 … 5.10.2026),
  but glued and out of order, while the Konut 1.Kademe values stay in column order; sort the dates and pair
  them. The HTML matched the newest column (5.10.2026). The page has a second "<year> Yılı" link list (KSUB
  prices) after the water one — take the first link per year.
- F5 BIG-IP ASM script present; did not block plain requests.

### ASKİ (Ankara) — low
- `https://www.aski.gov.tr/tr/ucretler.aspx` links "Güncel" → `https://www.aski.gov.tr/Yukle/Dosya/SuTarifesi.pdf`
  (fixed URL, overwritten in place; Last-Modified 2026-10-06). One-page text PDF (pypdf parses it).
- Konut: 0–15 = 38.75 + 19.38 = 58.13; 16–30 = 81.41; 30+ = 105.24. Sosyal yardım konut rows are separate.
- Effective date in text ("05.10.2026 TARİHİ İTİBARIYLA… KDV DAHİL DEĞİLDİR"). KDV: su 1 %, atıksu 10 %.
- Changes irregularly.

### İZSU (İzmir) — low–medium
- `https://izsu.gov.tr/su-ve-atik-su-tarifesi` (old `/tr/AboneIslemleri/SuTarifeleri` is an empty shell).
- Next.js: the tariff is an HTML table embedded as an escaped string in `self.__next_f.push(...)` RSC payload.
  Unescape and parse — no browser needed. API base `api.izsu.gov.tr/api`, endpoint not found (optional).
- Konut: 4 tiers: 0–10 = 40.00 + 20.00 = 60.00; 11–20 = 99.83; 21–40 = 145.00; 41+ = 201.90.
- "01.06.2026 tarihinden itibaren… KDV hariç" → effective date. 1–2 changes a year.

## CSV columns

`product_name, price, category_number (4), sub_category_number (0441101)`, then
`province, utility, subscriber_type (konut / sosyal konut), tier_from_m3, tier_to_m3, water_price,
wastewater_price, total, unit (TL/m³), vat_included (false), ctv_included (false), effective_date,
source_url, collected_at`. `price` = total.
