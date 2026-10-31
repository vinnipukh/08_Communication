# PetChef (petchef.com.tr)

TÜİK 09 source for fresh, raw and cooked pet food (0932201) and a few accessories (0932204). T-Soft storefront,
curl_cffi only, no browser.

## Source

- Homepage first, then `GET /xml/sitemap/product.xml` (181 product URLs), then each product page.
- Each product page carries all variants (weights) as `<a data-subproduct-id data-type="6 KG" data-price data-vat
  data-not-discounted data-instock …>` and the product's `PRODUCT_DATA` JSON (name, brand/menu, category, VAT, stock).
- T-Soft's `data-price` is without VAT. Price written = `data-price * (1 + data-vat / 100)` (checked: 2887.50 at
  20 % = 3465.00, the price on the page; a few products have 1 % VAT). `list_price` uses `data-not-discounted`.
- Products without variants use `PRODUCT_DATA.total_sale_price` (VAT included).
- Only in-stock variants are written.
- robots.txt (checked): everything is allowed except `/ajax.php`, `*?pg*` (pagination), `*sort*`, `*arama*`, `*stock*`,
  `*?price*`. The scraper requests only the homepage, the sitemap and product pages.

## Mapping

| Product | Code |
|---|---|
| fresh, raw, cooked, galantine, pate, soup, ratatouille, diet (`Healthy Pet Food`, `Redüksiyon`) food, treats, cookies, chips, dog cakes (pastry) | `0932201` |
| bowls (`Mama Kasesi`), supplements (oil `Yağ`, calcium powder, collagen supplement) | `0932204` |
| the book and the silicone baking mould | dropped |

`menu` is the site's sub-brand (for example `Chef's Cooked Menü`); `brand` is always `PetChef`, which is prepended to the
name when it is missing. Dog cakes (`Fresh … Köpek Pastası`, about 1,250-1,550 TL) are treated as treats.

## Columns

`product_name, price, category_number, sub_category_number` first (`category_number` is `9`), then `list_price, brand,
menu, variant, category, sku, product_url`.

## Run

```
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/Petchef/petchef_scraper.py
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/Petchef/petchef_scraper.py --limit 6 --date test
```

`--limit` reads only the first N product pages (bounded run). 1.5 s between requests, 3 retries; no CSV is written when
nothing is scraped. Output: `InflationItems/Datas/09_Recreation/Petchef/petchef_YYYY-MM-DD.csv`. A full run is about
181 requests plus the homepage and sitemap.

## Sitemap verdict

Used, for discovery only. Category pages show the default variant only and some lists stop at 32 products, and their
pagination (`?pg=`) is disallowed by robots.txt. The product sitemap lists all 181 products in one request (the union
of 42 category pages gave the same 181), and product pages are needed anyway for the variants. The sitemap holds no
prices.

## Caveats

- The product page selects the default variant; the other variants are read from the anchors. A product with two
  variant dimensions would list the options of both groups.
- Several products show stock counts like 9,999 (unlimited); stock is only tested for 0.
- Product names occasionally contain stray spaces or `&` without a space on the site (`Cookies &Sebzeli`); kept as is.
