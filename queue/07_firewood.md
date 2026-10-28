# 07 — Firewood (yakacak odun) — Odunal.com

- **TÜİK item:** 0454201 Yakacak odun
- **Scraper path:** `InflationItems/Codes/04_Housing/Firewood/scraper.py`
- **Output:** `InflationItems/Datas/04_Housing/Firewood/YYYY-MM-DD.csv`
- **Source chosen by the user (2026-10-28):** `https://www.odunal.com/pages/yakacak-odun-fiyatlari`
- **Coverage:** one online seller based in Ağva/Şile (Istanbul), delivering nationwide; prices are not
  per city. Istanbul local delivery and per-product shipping are listed separately from the product price.

## Source

- Shopify store. Use the public catalogue JSON instead of parsing HTML:
  `GET https://www.odunal.com/products.json?limit=250` → 53 products on 2026-10-28 (one page; paginate with
  `&page=2` if it ever reaches 250). Each product has `handle`, `title`, `product_type`, `body_html`,
  `variants[].price`, `variants[].available`, `updated_at`.
- Filter `product_type` in {"Yakacak Odun", "Şömine Odunu"} (the store also sells furniture, decor,
  charcoal and kindling — exclude those). Check the type list each run; log unknown firewood-like types.
- The pricing page itself (`/pages/yakacak-odun-fiyatlari`) is plain HTML with a "Fiyat kontrol tarihi"
  and a table of product price + delivery fee (e.g. 500 TL); optional second source for the delivery fee.
- **Rate limiting:** the site returned HTTP 429 (`Retry-After: 60`) to one fetcher during recon, while a
  plain curl got 200. One request per run; honour `Retry-After`, do not retry aggressively.

## Products seen (2026-10-28, TL, product price)

| Product | Price |
|---|---|
| Ağva 10 kg ince gürgen | 600 |
| Kuru meşe 20 kg çuval | 750 |
| Kuru meşe 40 kg çuval | 1,250 |
| 100 kg meşe şömine odunu (gift charcoal) | 3,500 |
| 250 kg meşe (kargo + KDV dahil) | 2,500 |
| 500 kg kuru meşe | 5,000 |
| Kuru meşe 1 ton | 7,500 |
| Şöminelik kayın 1 ton | 7,500 |
| Restoran fırın odunu 1 ton | 8,000 |
| 2 / 3 / 4 ton kuru meşe | 15,000 / 24,000 / 32,000 |

## Extract

- Parse net weight from title/handle (`10 kg`, `500 kg`, `1 ton`, …) → `weight_kg`; compute `price_per_kg`.
- Wood species from title (meşe / kayın / gürgen / kocayemiş).
- Whether shipping/KDV are included (title or body says "kargo dahil", "KDV dahil").
- The main CPI series: household firewood per ton (e.g. "Kuru meşe yakacak odun 1 ton"); keep all
  firewood rows so the series can be rebuilt if a product disappears.

## CSV columns

`product_name, price, category_number (4), sub_category_number (0454201)`, then
`handle, product_type, species, weight_kg, price_per_kg, available, shipping_included,
vat_included, shopify_updated_at, source_url, collected_at`. `price` = product price in TL.
