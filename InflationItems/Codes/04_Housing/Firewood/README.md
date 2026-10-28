# Firewood (TÜİK 0454201 Yakacak odun)

Fetches firewood prices from six sellers, one store folder each. `price` is TL/kg for every store.

```bash
python InflationItems/Codes/04_Housing/Firewood/scraper.py                       # all stores
python InflationItems/Codes/04_Housing/Firewood/scraper.py --store tetik yakgelsin
```

| Store (`--store`) | Seller, city | Source | Requests | Rows on 2026-10-28 |
|---|---|---|---|---|
| `Odunal` (`odunal`) | Odunal.com, Ağva/Şile (İstanbul), ships nationwide | Shopify `products.json` | 1 | 14 |
| `Ulusoy` (`ulusoy`) | Ulusoy Kömür, Bornova (İzmir) | HTML price table | 1 | 2 |
| `Komurdeposu` (`komurdeposu`) | Kömür Deposu (Axon), Bolu | HTML price table | 1 | 4 |
| `Odunmarket` (`odunmarket`) | Odunmarket, free cargo nationwide | Ticimax page JSON | 3 | 5 |
| `Tetik` (`tetik`) | Tetik Yakacak, Bornova (İzmir) | WooCommerce Store API + JSON-LD | 2 | 1 |
| `Yakgelsin` (`yakgelsin`) | Yak Gelsin (Özel Ada), Ödemiş (İzmir) | HTML price table (Next.js) | 1 | 11 |

- Output: `InflationItems/Datas/04_Housing/<Store>/<store>_YYYY-MM-DD.csv` (upstream layout: one CSV per store and
  day). `--output <path>` writes all rows of the chosen stores to that CSV instead (test runs).
- Runtime: all six stores in ~13 s wall (1 s jittered delay between requests; measured 2026-10-28).
- Exit status: 0 = every store written; 1 = at least one store failed or had fewer rows than its minimum
  (`STORES` in `scraper.py`). Nothing is written for that store, but the others are.
- Rate limiting: the client honours `Retry-After` (up to 300 s) and gives up after 3 retries. Odunal answered
  HTTP 429 (`Retry-After: 60`) to one fetcher during recon.

## Columns

`product_name, price, category_number, sub_category_number, handle, product_type, species, weight_kg,
price_per_kg, package_price, unit, available, shipping_included, vat_included, delivery_fee,
shopify_published_at, source_url, collected_at, province`

- `price` = `price_per_kg` = `package_price` / `weight_kg`, `unit` = `TL/kg`. Packages of 10 kg to 4 tons are
  in one unit. `package_price` is the listed price.
- A package without a single stated weight is left out. That covers the sellers' "1 çuval" / "torba" columns with
  no weight, Yak Gelsin's "1 Çuval (20-25kg)" range, and Tetik's 400 TL bags. Nothing is converted from ster or
  çeki: no seller uses them.
- `handle`: the Shopify handle (Odunal), or a slug of product + package (other stores). Use it to follow a
  series.
- `species`: meşe / kayın / gürgen / kocayemiş / zeytin / çam from the name, empty if the name has none.
- `available`, `shipping_included`, `vat_included`: "true", "false" or empty when the seller does not say.
- `delivery_fee`: only Odunal states one (500 TL in İstanbul).
- `shopify_published_at`: Odunal only (Shopify's `updated_at` equals the response time, so it is not used).
- `province` (added 2026-10-28 with the new sellers): where the price applies. That is the seller's province, or
  "Türkiye" for a seller that ships nationwide at one price (Odunal, Odunmarket).

## Sellers

**Odunal.com** (`odunal`). Products of type "Yakacak Odun" or "Şömine Odunu", except kindling (title contains
"çıra"). All prices include VAT. `shipping_included` and the fee come from `body_html` ("kargo dahil" /
"Kargo ve teslimat: 500 TL"). Main series: **Kuru Meşe Yakacak Odun 1 Ton** (`kuru-mese-yakacak-odun-1-ton`, 7.5
TL/kg on 2026-10-28). Reviewed and left out: "Fırın Odunu", "Yakacak Odun ve Çıra", "Tahta Parçası / Yakacak",
axes, kindling, accessories. A new type whose name contains odun / yakacak / şömine is logged as a warning; add it
to `FIREWOOD_TYPES` or `REVIEWED_OTHER_TYPES`.

**Ulusoy Kömür** (`ulusoy`, <https://ulusoykomur.com.tr/izmir-odun-ve-komur-fiyatlari/>). The page has four
tables ("2026-2027 Sezonu"); the firewood table has columns "1 TON" and "1 ÇUVAL". Written: MEŞE ODUNU SOBALIK and
MEŞE ODUN ŞÖMİNELİK, 1 ton (13,000 TL = 13 TL/kg). Left out: the çuval price (450 TL, no weight), TAHTA PARÇASI
(wood scraps, also left out at Odunal), coal and pellet. VAT is not stated. `shipping_included` = true: the page
promises free delivery ("ücretsiz nakliye") to İzmir customers.

**Kömür Deposu** (`komurdeposu`, <https://www.komurdeposu.com.tr/odun-fiyatlari/>). This is a Bolu seller, not one
of the three big cities. One table: meşe and kayın, dökme (bulk, "Bolu içi") 8,000 TL/ton and torbalı (bagged)
9,000 TL/ton. Left out: "Torba Fiyatı" (875 TL, no bag weight). VAT is not stated.

**Odunmarket** (`odunmarket`, <https://www.odunmarket.com/odun>). Ticimax shop; product pages embed
`var productDetailModel = {...}` with one entry per variant (option "Kilogram": 10, 20, "İnce (18kg)"). The written
price is `indirimliFiyatiStr`, the sale price the buyer pays, VAT included (`kdvDahil`). Free cargo nationwide.
Written: Yuvarlak and Yarma Şömine Odunu. Left out: Tahta Parçası, Hazır Şömine Odun Paketi (bundle with kindling
and matches), İsveç Ateşi, Flam Up pressed logs, pellet. **Every variant has been out of stock (`available` =
false) since at least 2025-08, and its price has not changed since then. Treat it as a list price, not a market
price.**

**Tetik Yakacak** (`tetik`, <https://tetikyakacak.com/odun-fiyatlari-izmir-toptan-odun-komur-satisi-izmir/>).
WooCommerce. `wp-json/wc/store/v1/products?search=odun` lists the products, and the product page JSON-LD gives
price and stock. Only **Meşe Odun 1 TON ŞÖMİNELİK VE SOBALIK** states a weight (13,000 TL = 13 TL/kg). Left out:
"Sobalık / Şöminelik Meşe Odun" (400 TL, no weight), "Pidelik" and "Fırınlık Odun" (bakery wood, no unit).
`vat_included`: the JSON-LD said `valueAddedTaxIncluded: "false"` up to the 2026-06-17 copy. The live page no
longer states it, so the field is empty from 2026-10-28.

**Yak Gelsin** (`yakgelsin`, <https://www.yakgelsin.com/tr/urunler/sobalik-odun>). Table "Ürün / Seçenek /
Fiyat" with "KDV hariç ₺X, KDV dahil ₺Y" per option. The VAT-included price is written (`vat_included` = true).
Written: Sarı Meşe and Kızıl Meşe Sobalık Odun (çuvallı 30 / 28 kg, çuvallı 1 ton, dökme 500 kg, dökme 1 ton), and
the 1 ton dökme of Meşe Odunu (Kuru), Meşe Odunu (6 Aylık) and Sarı Meşe Odunu (6 Aylık). Left out: "1 Çuval
(20-25kg)" (weight range), Kayın and Briket (no price, "Fiyat için WhatsApp"). `shipping_included` = false:
delivery is free in İzmir only from 5 tons. Meşe Odunu (Kuru) 1 ton dökme is 6,600 TL (6.6 TL/kg), half the
other 1 ton prices. The site's own kg table shows the same figure.

## History (`backfill.py`)

```bash
python InflationItems/Codes/04_Housing/Firewood/backfill.py                 # Wayback copies from 2025-01-01
```

No seller keeps a price history. The Wayback Machine has copies of three of them; each copy is parsed with the
daily parser. Like the other 04 backfills, every day from the first copy to yesterday gets a file holding the
newest copy on or before it (`source_url` = that Wayback copy, `collected_at` = its timestamp, so a filled day
has a `collected_at` date before the file date). Existing day files are never overwritten. Written on 2026-10-28:
Komurdeposu 2025-11-12 .. (350 days), Odunmarket 2025-08-07 .. (447), Tetik 2025-05-13 .. (533). Copy days:

| Store | Days | Prices |
|---|---|---|
| Komurdeposu | 2025-11-12, 2026-02-12, 2026-06-16 | unchanged: 8,000 dökme / 9,000 torbalı TL/ton |
| Odunmarket | 2025-08-07 (yarma), 2025-08-28 (yuvarlak), 2026-05-13 | same as today, out of stock |
| Tetik | 2025-05-13, 2025-09-07, 2025-11-09, 2026-01-20, 2026-03-14, 2026-06-17 | 8,000 → 9,500 (2025-11) → 13,000 TL/ton today |

Earlier copies exist (Tetik 1 kg at 5.5 TL in 2024-05 and 7 TL in 2024-12; Odunmarket 2024) and can be written with
`--start 2024-01-01`. No copies: Ulusoy, Yak Gelsin, Odunal.

## Notes

- Schedule: none yet (no cron or Actions job). Weekly is enough; the table sellers change prices a few times a
  season.
- Cities: İzmir (Ulusoy, Tetik, Yak Gelsin), Bolu (Kömür Deposu), nationwide (Odunal, Odunmarket). No Ankara
  seller yet.
- Git Bash on Windows garbles Turkish output; set `PYTHONIOENCODING=utf-8`.
