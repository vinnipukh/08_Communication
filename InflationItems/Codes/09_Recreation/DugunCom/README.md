# Düğün.com wedding halls (TÜİK 0969006)

Prices for "Event hall rental for wedding, engagement, and other events" (category `9`, sub-category `0969006`).

## Source
- Listing pages `https://dugun.com/dugun-salonlari/<city>?page=N` (server-rendered, 40 venues per page, `rel="next"` ends the paging).
- Each page has a schema.org `ItemList` (JSON-LD). Per venue: `makesOffer.price` (TRY), `makesOffer.name` (`Kişi Başı` or `Paket`), `priceValidUntil`, address (district, city). The HTML cards add the struck-through list price (`<del>`) and the provider id.
- City slugs come from the links on the Istanbul listing page (the `/dugun-salonlari` index only links ~29 big cities); Istanbul district pages and Kıbrıs are excluded.
- `/api/*` is disallowed in robots.txt, so the JSON search API is not used.

## Coverage
All provinces linked there, every listing page of each. Request count per run is printed at the end of the log (`listing requests`), about 105 on 2026-10-31 (75 cities), 1.5 s pause between requests, about 3.5 minutes. Most venues (about 1,940 of 2,170 on 2026-10-31) publish no price and are skipped, so only about 18 cities yield rows (about 230 rows).

## Price types
Per-person and package prices are never mixed. `product_name` ends with `Kişi Başı` or `Paket`, and the `price_type` column is `per_person` or `package`. Compare only within one type. `price` is the current (discounted) price; `list_price` is the struck-through price when present.

## Output
`InflationItems/Datas/09_Recreation/DugunCom/dugun_com_YYYY-MM-DD.csv` (`utf-8-sig`). First columns: `product_name,price,category_number,sub_category_number`; then `venue_name, city, district, price_type, list_price, price_valid_until, provider_id, source_url`. The CSV is only written if rows exist.

## Run
```
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/DugunCom/dugun_com_scraper.py
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/DugunCom/dugun_com_scraper.py --cities istanbul --max-pages 1   # bounded
```
Options: `--cities slug,slug`, `--max-pages N`, `--date YYYY-MM-DD`.

## Sitemap
Checked; not used. It lists venue detail pages and guides but the listing pages already carry the prices at 40 venues per request.

## Caveats
- Listings are sorted by the site; unpriced venues are interleaved, so row counts per page vary.
- Some venues publish implausible prices (e.g. a "per person" price in the tens of thousands); they are kept as published.
- The price unit (guest count the price is based on) is not on the listing page.
