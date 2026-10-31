# Temiz Mama (temizmama.com)

TÜİK 09 source for BonaCibo/Micho/Mito/Kennel/Kucho dry and wet cat and dog food (0932201) and other pet products
(0932204). Next.js storefront, curl_cffi only, no browser.

## Source

- Homepage first, then `GET /sitemap-products.xml` (94 product URLs), then each product page.
- A product page embeds all its variants (package sizes) in the React Server Components payload
  (`self.__next_f.push([1,"…"])`) as objects `{"productId", "variantId", "productDetailUrl", "variantEcommerceTitle",
  "variantTitle", "variantPrice", "variantOldPrice", "variantActive", "variantAvailableForSale", "variantStatus",
  "variantBarcode", …}`. `variantPrice` is the selling price including VAT (equals the JSON-LD `offers.price`);
  `variantOldPrice` is the list price (0 when there is none) and goes to `list_price`.
- Variants that are not active or not available for sale are skipped. Status `Üretimde` (in production, ships a few
  days later) is still orderable and is kept; the `status` column shows it.
- robots.txt (checked): `/api/` and `/_next/` are disallowed, so the category-list API (infinite scroll) and the Next
  data routes are not used. Only the homepage, the sitemap and product pages (all allowed) are requested; the
  payload is read from the page HTML. The JSON-LD on category pages holds only 10 items and the HTML cards 19, so
  category pages cannot list the catalogue.

## Mapping

By the first segment of the product URL (the site category):

| Segment contains | Code |
|---|---|
| `mamasi` (incl. `yas-mamasi`, `sivi-odul-mamasi`), `odul`, `atistirmalik`, `cigneme`, `kemik` | `0932201` |
| `takviye` (malt pastes, liquid vitamins, shampoo, ear/eye cleaners), `kum`, `oyuncak`, `tuvalet`, `aksesuar` | `0932204` |
| anything else | dropped and logged |

## Columns

`product_name, price, category_number, sub_category_number` first (`category_number` is `9`), then `list_price, brand,
variant, site_category, status, barcode, product_url`. `product_name` is the site's own variant title (brand + product +
size, for example `BonaCibo Tavuklu Yavru Kedi Maması 5 kg`). Multipacks (`2 kg x 2 Adet`) are separate rows, as on the
site.

## Run

```
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/TemizMama/temizmama_scraper.py
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/TemizMama/temizmama_scraper.py --limit 3 --date test
```

`--limit` reads only the first N product pages (bounded run). 1.5 s between requests, 3 retries; no CSV is written
when nothing is scraped. Output: `InflationItems/Datas/09_Recreation/TemizMama/temizmama_YYYY-MM-DD.csv`.

## Sitemap verdict

Used, for discovery only: it lists all 94 products in one request, while category pages are incomplete (see above) and
their API is disallowed. The sitemap holds no prices.

## Caveats

- The variant payload format belongs to the Next.js build; if the page structure changes the scraper finds no
  variants and writes no CSV.
- The same barcode appears on a pack and its multipack (they share a product); it is not a unique key.
