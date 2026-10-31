# DüğünBuketi wedding halls (TÜİK 0969006)

Prices for "Event hall rental for wedding, engagement, and other events" (category `9`, sub-category `0969006`).

## Source
- Listing pages `https://www.dugunbuketi.com/p/dugun-salonlari/<city>?page=N` (12 venues per page). The site is Laravel + Inertia: the data sits as JSON in `<script data-page="app" type="application/json">`, so no card HTML parsing is needed.
- City list comes from the same JSON (`props.shared.cities`). robots.txt allows everything.

## Coverage
All cities the site lists, every listing page until `next_page_url` is empty (cap 60 pages per city). The log ends with the venue and row totals; 1.5 s pause between requests.

## Price types
Never mixed. The type is part of `product_name` (`Kişi Başı ...` or `Paket ...`); it is not a separate column.
- Venue has starting menus (`weekdaysMenu` / `weekendsMenu`): one `per_person` row per menu (hafta içi / hafta sonu; Yemekli or Kokteyl), named `Kişi Başı <Hafta İçi|Hafta Sonu> (<menu>)`.
- Menu fields present but empty: `min_price` is the "Yemeksiz" package price, named `Paket (Yemeksiz)`.
- No menu fields at all (unclaimed venues): type inferred from the amount (< 10,000 TL per person, otherwise package), named plain `Kişi Başı` or `Paket`. Treat these rows with care; the CSV does not mark them as inferred (a plain `Kişi Başı` / `Paket` name without menu or `(Yemeksiz)` is the only hint).
- Venues without a displayable price are skipped.

## Output
`InflationItems/Datas/09_Recreation/DugunBuketi/dugunbuketi_YYYY-MM-DD.csv` (`utf-8-sig`). Exactly four columns: `product_name,price,category_number,sub_category_number` (`category_number` is `9`). `product_name` is `<venue> - <city/district> - <label>`, so venue, location, price type and menu/week period are only in the name. Not saved: listing start price, capacity, membership type, place id, source URL. Written only if rows exist.

## Run
```
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/DugunBuketi/dugunbuketi_scraper.py
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/DugunBuketi/dugunbuketi_scraper.py --cities istanbul --max-pages 1   # bounded
```
Options: `--cities slug,slug`, `--max-pages N`, `--date YYYY-MM-DD`.

## Sitemap
Checked; not used. `sitemap.xml/places` lists one URL per venue (thousands of requests); the listing pages deliver 12 venues with prices per request.

## Caveats
- Prices are "starting" prices, not quotes for a specific date.
- The type inference for unclaimed venues is a heuristic.
