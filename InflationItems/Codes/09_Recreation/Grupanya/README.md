# Grupanya (grupanya.com)

TUIK group 09, items 0946103 (Recreation and hobby services) and 0946203 (Sports training fee).

## Source and endpoints
Deal marketplace. Each category listing `https://www.grupanya.com/<category-slug>/<city-slug>`
answers `GET <listing>?handler=MoreDeals&p=N` with JSON: `deals[]` (title, dealPrice, dealValue,
categoryName, locationName, merchantName, detailUrl, ...), `sponsoredDeals[]`, `hasMore`, `isFallback`.
Cities: istanbul, ankara, izmir. 14 category slugs (2 parents + 12 subcategories, see `CATEGORY_SLUGS`).
A city/category without deals returns `isFallback: true` with unrelated deals; those pages are skipped.

## Mapping rule
A deal is mapped by its own `categoryName` (not by the listing it was found in):
- Eglence Merkezi, Akvaryum - Tema Park, Sanal Gerceklik - Kacis, Poligon - Paintball, Binicilik - Parkur,
  Rafting - Yamac Parasutu, Su Sporlari, Atolye, Dans - Muzik -> `0946103`
- Pilates, Fitness - Gym, Yoga - Nefes Terapisi -> `0946203`
- Dance lessons (title matches dans/zumba/bale/salsa/...) and sports lessons in recreation categories
  (riding, swimming, diving, ... + egitim/ders/kurs) -> `0946203`
- All other categories (breakfast, spa, tours, vouchers, online courses, ...) are dropped.

Also dropped: sold-out/inactive deals, deals without a real price (`dealValue` 0 = token booking fee),
deals located in another province or with a comma-separated departure-city list. Deals are de-duplicated by id.

`price` = `dealPrice` (or voucher discounted price); `list_price` = `dealValue`. Product names are
`Grupanya <City>: <deal title>`. Extra columns: list_price, grupanya_category, merchant, location, city,
deal_id, product_url.

## Run
```
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/Grupanya/grupanya_scraper.py
```
Bounded run: `--cities istanbul --categories 2 --max-pages 1`. `--date YYYY-MM-DD` sets the output date.
Output: `InflationItems/Datas/09_Recreation/Grupanya/grupanya_YYYY-MM-DD.csv` (only written when rows exist).
Full run: about 100 s (about 45 requests, 2 s apart), 76 rows on 2026-10-31 (60 x 0946103, 16 x 0946203).

## Sitemap verdict
Not used. `sitemap.xml` exists but lists category/landing pages only, which are already known; the JSON
handler is the fast path. The robots.txt `*` group does not disallow the category listings or the handler
(it disallows account, search and `tum-firsatlar/c/*,*` paths).

## Caveats
- Deals are time-limited campaigns; the basket changes daily and a deal's price is a promotional price,
  so row counts and the product set vary. List price equals price for some deals (no discount).
- Some deals are multi-person or multi-session bundles (title says "2 Kisi", "5 Ders"); the title is kept in
  `product_name` so the unit is visible, but prices are not normalised per unit.
- Mapping by category name depends on the site's taxonomy; new category names are dropped silently.
