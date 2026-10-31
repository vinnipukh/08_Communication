# Sports scrapers (TÜİK 09)

Three scrapers, one CSV per store and day under `InflationItems/Datas/09_Recreation/<Store>/<store>_YYYY-MM-DD.csv`.
Columns: `product_name, price, category_number, sub_category_number, product_url` (`category_number` is `9`).
All use `curl_cffi` with Chrome impersonation and request the homepage first (Cloudflare `__cf_bm`; plain
`requests` gets 403). Run from the repository root:

```
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/Sports/<script>.py
```

## Decathlon (`decathlon_scraper.py`)

Source: category listing HTML, `?from=<offset>&size=40`, `.product-card` parsing, 10 s between pages.
A run merges into an existing same-day CSV (key: product URL + name).

| Group (`--only`) | Listing path | Code | Page cap |
|---|---|---|---|
| fitness | `ekipmanlar/evde-spor-aletleri` | 0922102 | 60 |
| clothing | `tum-sporlar/kosu/kosu-ve-yuruyus-kiyafetleri` | 0922107 | 8 |
| clothing | `tum-sporlar/fitness-kardiyo/tum-fitness-kiyafetleri` | 0922107 | 9 |
| clothing | `tum-sporlar/bisiklet/bisikletci-kiyafetleri` | 0922107 | 4 |
| clothing | `tum-sporlar/yuzme/yuzme-kiyafetleri` | 0922107 | 16 |
| clothing | `tum-sporlar/kayak-snowboard/kayak-snowboard-kiyafet-ve-giyim` | 0922107 | 7 |
| clothing | `tum-sporlar/hiking-trekking-outdoor/giyim` | 0922107 | 12 |
| clothing | `tum-sporlar/yoga/yoga-kiyafetleri` | 0922107 | 2 |

Caps are set just above each listing's size (about 85 pages, roughly 15 minutes per full run).
Listings overlap (the same product can appear under several categories); duplicates are merged by key.
The yüzme and hiking listings include children's items and some accessories (goggles, socks), and
the hiking listing has outdoor trousers and jackets; there is no cleaner per-item filter on the site.

```
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/Sports/decathlon_scraper.py                       # full run
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/Sports/decathlon_scraper.py --only clothing --max-pages 1   # bounded
```

`--only fitness|clothing` selects a group; `--max-pages N` overrides the per-category cap.

Sitemap verdict: `sitemap-index.xml` (listed in `robots.txt`) points to
`sitemap/category-product-listing-0.xml` (about 1,570 category URLs, one request). It is used only to
discover category URLs; it is not used for per-product crawling (a sitemap lists URLs, not
prices, so every product page would need its own request). The site navigation only exposes top-level categories, so the sitemap was faster.

## Korayspor (`koraysport_scraper.py`)

Next.js site behind Cloudflare. Categories `vucut-gelistirme-urunleri` and `pilates-yoga-urunleri`, both
code 0922102 (home fitness equipment). Page count comes from `totalPages` in `__NEXT_DATA__`; up to 50
pages per category, 2 s delay. Output `Korayspor/korayspor_YYYY-MM-DD.csv`. No flags.

## SPX (`spx_scraper.py`)

Akinon storefront; the listing URL returns JSON when requested with `Accept: application/json` and
`X-Requested-With`. Categories: erkek/kadin/cocuk `ekipman` (0922103, sports equipment) and kadin `tayt`
(0922107, the only clothing source for that item besides Decathlon). 2 s delay. Flags: `--max-pages`
(per category), `--date`. Output `SPX/spx_YYYY-MM-DD.csv`.
