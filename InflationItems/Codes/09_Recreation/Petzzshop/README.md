# Petzzshop (petzzshop.com)

TÜİK 09 sources for pet food (0932201) and other pet products (0932204). ikas storefront,
curl_cffi only, no browser.

## Source

- Homepage first (`GET /`), which sets the Cloudflare `__cf_bm` cookie (passive, never challenged us).
- The homepage holds `window.__IKAS_DATA__`; its `storefrontConfig` gives the public API settings
  (`apiUrl`, `apiKey` JWT, `storefrontId`, `storefrontRoutingId`). They are read at run time, never stored in code.
- `POST https://api.myikas.com/api/sf/graphql/searchProducts` with headers `x-api-key`, `x-sfid`, `x-sfrid`
  and body `{"input": {"locale": "tr", "page": N, "showStockOption": "SHOW_ALL"}}`.
  Without `categoryIdList` the API returns the whole catalogue (about 9,900 products, 100 per page, 99 pages), each
  product with all variants, prices, stock and categories. HTML pages ignore `?page=`, so this API is the only way past
  page 1. A `categoryIdList` filter also works and includes sub-categories (top-level ids: Kedi `9c9e2b1a-…`,
  Köpek `1440806e-…`, Kuş `0d5ab5b1-…`, Balık `cf6b516c-…`, Kemirgen `a93771c7-…`, Sürüngen `24213d7a-…`), but it is
  not needed.
- robots.txt (checked): the generic `User-agent: *` group only disallows `/admin`, `/cart`, `/checkout`, `/account`,
  `/_next/data/*` and `/search`; the API host has no robots.txt. The Cloudflare-managed block disallows named AI
  crawlers, not browsers.

## Price

`discountPrice` is the current selling price including VAT (it equals the JSON-LD `offers.price` on the product page);
`sellPrice` is the list price (kept as `list_price`). Order-level campaigns (fixed amount or percentage at checkout)
are not in the listing and are ignored.

## Stock

Only variants with stock (`stocks[].stockCount` summed, or `sellIfOutOfStock`) are written, matching the product page
availability. About 84 % of the catalogue's variants are out of stock, so rows are about 3,500 of about 22,000 variants.

## Mapping

Decided from the product's category slugs at any level of its category path:

| Condition | Code |
|---|---|
| a slug in `kedi-mamasi`, `konserve-kedi-mamasi`, `kedi-odul-mamasi`, `kopek-mamasi`, `konserve-kopek-mamasi`, `kopek-odul-mamasi`, `kus-yemleri`, `kus-odul-ve-krakerleri`, `kemirgen-yemleri`, `balik-yemleri`; reptile products whose name says `yem`/`pellet` | `0932201` |
| any other product under Kedi, Köpek, Kuş, Balık, Kemirgen, Sürüngen (litter, toys, bowls, collars, beds, care, vitamins and supplements, aquarium equipment) | `0932204` |
| products outside these categories | dropped |

The `animal` column (kedi/kopek/kus/balik/kemirgen/surungen) lets users keep only cat and dog food. Vitamins and
supplements (`*-vitamin-ve-ek-besinleri`) go to 0932204.

## Columns

`product_name, price, category_number, sub_category_number` first (`category_number` is `9`), then `list_price, brand,
variant, animal, category_path, sku, barcode, product_url`. The name is product name, with the brand added if missing
and the variant option (for example `15 Kg`) added if it is not already in the name.

## Run

```
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/Petzzshop/petzzshop_scraper.py
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/Petzzshop/petzzshop_scraper.py --max-pages 2 --date test
```

`--max-pages` is the bounded-run flag (100 products per page). 1.5 s between requests, 3 retries; no CSV is written
when nothing is scraped. Output: `InflationItems/Datas/09_Recreation/Petzzshop/petzzshop_YYYY-MM-DD.csv`.

## Sitemap verdict

`sitemap.xml` lists `products.xml`, `collections.xml`, `pages.xml`, `blogs.xml`. Product URLs carry no prices and would
need one request per product (about 10,000), so the API (99 requests for everything) is much faster. Not used.

## Caveats

- The API key and ids are read from the homepage each run; if ikas changes the `searchProducts` input type the run
  logs the GraphQL error and stops without writing a CSV.
- Aquarium equipment (filters, pumps) is included as 0932204 because it sits under the pet categories; filter by
  `animal` and `category_path` if a narrower basket is needed.
- Names such as "Kedi ve Köpek …" products sit in several categories; `animal` then reads `kedi/kopek`.
