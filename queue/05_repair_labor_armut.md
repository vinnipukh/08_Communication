# 05 — Home repair labour (Armut)

- **TÜİK item:** 0432015 Ev bakım ve onarım işçilik ücreti
- **Scraper path:** `InflationItems/Codes/04_Housing/RepairLabor/scraper.py`
- **Output:** `InflationItems/Datas/04_Housing/RepairLabor/YYYY-MM-DD.csv`
- **Coverage:** Istanbul (34), Ankara (6), İzmir (35). Other provinces only change the URL, but cost
  ~1,600 requests / ~40 min for all 81 — keep to 3 cities by default, allow `--provinces all`.

## Source

- URL pattern: `https://armut.com/fiyatlari/{city}-{service-slug}_{serviceId}_{plate}`
  e.g. `https://armut.com/fiyatlari/ankara-boyaci-boya-badana-ustasi_32_6`.
- Server-rendered (Next.js); the page shows "Ortalama Fiyat" min–max for that city.
  Example plumber (`su-tesisatcisi_193`): Istanbul 1,000–5,500, Ankara 1,000–15,000, İzmir 1,110–8,000 TL.
- Discovery: price sitemaps `sitemap/price-*.xml` (~6,760 services, ~45k city pages nationally).
- CloudFront, no challenge seen on 2026-10-28.

## Service list (curate, ~15–25)

Pick home maintenance/repair labour that matches the TÜİK item, e.g.: boya badana, su tesisatı,
elektrikçi, kombi bakımı/tamiri, fayans/seramik ustası, parke döşeme, alçıpan, sıva, çatı tamiri,
izolasyon, kapı/pencere tamiri, cam/PVC, mutfak dolabı montajı, tadilat. Resolve exact
slugs/serviceIds from the sitemap; keep the list in a small config in the scraper folder.

## Caveat

Ranges are very wide (e.g. painter 3,000–100,000 TL in Istanbul) — a noisy signal. Store min, max and
any other number the page offers (average, sample count) rather than only a midpoint.

## CSV columns

`product_name, price, category_number (4), sub_category_number (0432015)`, then
`service, service_id, province, plate, price_min, price_max, price_avg (if shown), unit/notes,
source_url, collected_at`. `price` = midpoint of min–max unless the page gives an average.
