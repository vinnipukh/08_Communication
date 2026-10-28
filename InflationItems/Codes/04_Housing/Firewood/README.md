# Firewood — Odunal.com (TÜİK 0454201)

Fetches the firewood prices of Odunal.com, a Shopify store of a seller in Ağva/Şile (İstanbul) that ships
nationwide. Prices are not per city.

```bash
python InflationItems/Codes/04_Housing/Firewood/scraper.py
```

- Requests: 1 (`products.json?limit=250`; a second page only if the catalogue reaches 250 products).
  Runtime 0.7 s inside the script, ~3 s wall including interpreter start (measured 2026-10-28).
- Output: `InflationItems/Datas/04_Housing/Odunal/odunal_YYYY-MM-DD.csv` (upstream layout: one CSV per store and
  day, store = Odunal), 14 rows on 2026-10-28. `--output <path>` writes that CSV instead of the day file (test
  runs).
- Rows: one per variant of every product of type "Yakacak Odun" or "Şömine Odunu", except kindling (title
  contains "çıra"). `price` = TL/kg (package price / weight, `unit` = `TL/kg`), so packages of 10 kg to 4 tons
  share one unit; `package_price` is the listed price. A package without a weight is skipped. The main CPI series is
  **Kuru Meşe Yakacak Odun 1 Ton** (`kuru-mese-yakacak-odun-1-ton`, 7,500 TL = 7.5 TL/kg on 2026-10-28); the other rows
  are kept so the series can be rebuilt if that product disappears.
- Columns: `product_name, price, category_number, sub_category_number, handle, product_type, species,
  weight_kg, price_per_kg, package_price, unit, available, shipping_included, vat_included, delivery_fee, shopify_published_at,
  source_url, collected_at`.
  - `weight_kg` from the variant or product title ("10 KG", "1 Ton"); `price_per_kg` = `price`.
  - `species`: meşe / kayın / gürgen / kocayemiş from the title, empty if none (e.g. Restoran Fırın Odunu).
  - `vat_included`: always "true" (Odunal's prices include VAT; confirmed 2026-10-28).
  - `shipping_included`: "true" when the title or description says "kargo dahil", "false" when a separate
    fee is stated, empty when the text says nothing.
  - `delivery_fee`: the fee stated in the description (500 TL for İstanbul, Şile and Ağva included).
  - `shopify_published_at`: when the product was published. Shopify's `updated_at` is not used: it equals the
    response time on every product.
- Exit status: 0 = CSV written; 1 = fetch failure or fewer than 8 firewood rows (nothing written).
- Rate limiting: the site answered HTTP 429 (`Retry-After: 60`) to one fetcher during recon. The client
  honours `Retry-After` (up to 300 s) and gives up after 3 retries.

## Product types

Taken: "Yakacak Odun", "Şömine Odunu". Reviewed on 2026-10-28 and not taken: "Fırın Odunu" (İnce Fırın ve
Lahmacun Odunu, 1 ton 12,000 TL), "Yakacak Odun ve Çıra", "Tahta Parçası / Yakacak", "Odun Yarma Baltası",
"Soba ve şömine tutuşturmalıkları", "Şömine Aksesuarları". A new type whose name contains odun / yakacak /
şömine is logged as a warning; add it to `FIREWOOD_TYPES` or `REVIEWED_OTHER_TYPES` in `scraper.py`.

## Source

| Endpoint | Format |
|---|---|
| `https://www.odunal.com/products.json?limit=250&page=N` | Shopify public catalogue JSON |
| `https://www.odunal.com/pages/yakacak-odun-fiyatlari` | HTML price list with "Fiyat kontrol tarihi"; not fetched |

No history: the store keeps no archive, the Wayback Machine has no copies (checked 2026-10-28), and most
products were published in Sep–Oct 2026.

## Notes

- Schedule: none yet (no cron or Actions job). Weekly is enough.
- Open: one seller, prices not per city, and the catalogue churns; the main series handle
  `kuru-mese-yakacak-odun-1-ton` may disappear (the run warns then).
- Reusable: the `products.json` paging + `body_html` term parsing in `scraper.py` for any other Shopify store.
- Git Bash on Windows garbles Turkish output; set `PYTHONIOENCODING=utf-8`.
