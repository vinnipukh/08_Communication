# TÜİK 09 Recreation, sport and culture: coverage check and new sources

Work done: 2026-10-30 / 2026-10-31. Status: **research only; no new scraper written yet.**

This page records what was done for category 09 so development can continue on another
machine: where the 09 code and data came from, which basket items are covered today, which new
sources were found for every item, and how each new source can be fetched (bot protection,
API vs HTML, pitfalls). The probe scripts used are in `tools/`.

## 1. What was done

1. **Copied category 09 from upstream.** `InflationItems/Codes/09_Recreation/` (26 files) and
   `InflationItems/Datas/09_Recreation/` (155 CSVs, ~284 MB) were copied unchanged from
   `urazkagangunes/InflationResearchStudy` (`master`, 2026-10-30). The audit log
   `InflationItems/Logs/Audit/categories/09_Recreation_daily_status.csv` was deliberately not
   copied.
2. **Added the 2026 TÜFE basket.** `docs/InflationResearchStudy.xlsx` holds only the
   *Categories and Weights* sheet (COICOP 2018 codes, weights, parent codes). The original
   workbook also had contact details and server keys; those sheets were removed before commit.
3. **Coverage check.** Compared the 32 leaf items of 09 in the basket with the
   `sub_category_number` values in the latest CSV of every 09 source, and in the latest CSV of
   every other upstream data folder (other groups also tag some products with 09 codes).
4. **Source search.** For every item, looked for at least 3 well-known Turkish sites that are
   *not* already scraped, and checked each with `tools/cffi_probe.py` (homepage first, then the
   listing/price page, `curl_cffi` Chrome impersonation, prices present in the response).
   Failing candidates were replaced until 3 passed or options ran out.
5. **Deep test of the 47 new sites** with `tools/deep_probe.py` (homepage + ~10 requests incl.
   page 2 and a product page, 2–3 s apart, anti-bot vendor detection, API hints) and
   `tools/sb_probe.py` (SeleniumBase UC headless, used to see the XHR/fetch calls a page makes,
   and as fallback if curl failed; it was never needed as fallback).

## 2. Basket items and current coverage

Item list from `docs/InflationResearchStudy.xlsx` (weights are for the 5-digit parent).

"09 folder" = scrapers in `InflationItems/Codes/09_Recreation/`. "Other groups" = upstream
scrapers in other TÜİK groups whose CSVs already carry the 09 code (01 food markets, 05 home and
hardware stores); see the caution under the table.

| Code | Item | 09 folder (2026-10-29/30 data) | Other upstream groups |
|---|---|---|---|
| 0921104 | Electronic games (consoles, software) | DR | A101 (1), Ereyon (1) |
| 0921204 | Other toys | DR, ToyzzShop, Zuhal Müzik | Ikea, sehzade, Sarıyer, EnglishHome, A101, jysk, Vivense, Bauhaus, Karaca* |
| 0921207 | Ride-on wheeled toys | DR, ToyzzShop | sehzade, Bauhaus, HanCivata (1 each) |
| 0922102 | Home fitness equipment | DR, Decathlon | Karaca, Ereyon, A101, Ikea, sehzade |
| 0922103 | Sports equipment | DR, Zuhal Müzik | Nalburcuk, Ereyon, Bauhaus, Afeks, … (mostly camping, knives) |
| 0922107 | Special sports clothing | DR (5 products) | none |
| 0932201 | Pet food | Petlebi | sehzade, A101, Bauhaus, Arden, Sarıyer, Marketzade, Mopaş, Afeks, Hapeloğlu |
| 0932204 | Other pet products | Petlebi, Zuhal Müzik | Ereyon, Bauhaus, Vivense, Arden, … (Macrocenter*, Karaca*) |
| 0945001 | Veterinary services | **none** | none |
| 0946103 | Recreation and hobby services | **none** | none |
| 0946201 | Sports facility payments | MACFit | none |
| 0946203 | Sports training fee | **none** | none (Armut scraper exists in 04/05/06 but not for 09) |
| 0947001 | Games of chance | Milli Piyango | none |
| 0961001 | Cinema ticket | **none** | none |
| 0961002 | Theatre ticket | Biletinial | none |
| 0969006 | Event hall rental (wedding etc.) | **none** | none |
| 0971102 | Test books | DR, Kitapyurdu | none |
| 0971103 | Textbooks | DR, Kitapyurdu | none |
| 0971901 | Children's books | DR, Kitapyurdu, Zuhal Müzik | none |
| 0971902 | Other books | DR, Kitapyurdu, Zuhal Müzik | none |
| 0974001 | School notebooks | Avansas, DR | sehzade, Mopaş, A101 (Karaca*) |
| 0974003 | Pens and pencils | Avansas, DR, Zuhal Müzik | sehzade, Afeks, Nalburcuk, Bauhaus, Mopaş |
| 0974004 | Paints | Avansas, DR | Bauhaus (979, hobby/decor paints), Nalburcuk, Afeks |
| 0974005 | Writing and drawing paper | Avansas, DR, Zuhal Müzik | sehzade, Bauhaus, Mopaş (few) |
| 0974009 | Other stationery | DR, Zuhal Müzik | Ikea, Bauhaus, sehzade, Karaca* |
| 0980002 | Domestic weekend tours | Hisar Turizm, Jolly | none |
| 0980003 | Other domestic tours | Hisar Turizm, Jolly | none |
| 0980006 | Tours abroad | Hisar Turizm, Jolly | none |
| 0980008 | Umrah fee (Diyanet) | Diyanet | none |
| 0980009 | Umrah fee (agency) | Hisar Turizm | none |

\* **Mis-tagged.** A sample of product names showed wrong 09 codes in some other groups: Karaca
"toys" are Christmas decorations, Macrocenter "pet products" are glasses and peelers. Ereyon (pet
houses) and Bauhaus (hobby paints) looked right. Do not count other-group 09 rows until their
mapping rules are checked or filtered.

**Data quality issues in the 09 folder (as copied):**

- `Datas/09_Recreation/Nezih/`: ~12k rows/day but no `category_number` / `sub_category_number`
  columns, so it counts for no item. The folder also holds a stray `beymen_enflasyon_2026-10-02.csv`.
- `DR`, `MACFit`, `Milli_Piyango`, `Zuhal_Muzik` CSVs have no `category_number` column.
- `Zuhal_Muzik` writes parent codes (`09212`, `0922`) on ~300 rows instead of item codes.
- `Codes/09_Recreation/Sports/koraysport_scraper.py`, `sportive_scraper.py`, `spx_scraper.py` are
  empty (0 bytes). Korayspor's domain is `korayspor.com` (not `koraysport.com`).

## 3. New sources per item

All sites below passed the quick probe (200, no challenge page, prices in the response).
Bold = recommended first three. Marketplaces (Trendyol, Hepsiburada, n11, Amazon) are listed as
backups; at least one non-marketplace per item.

| Code | Recommended new sources | Backups |
|---|---|---|
| 0921104 | **Teknosa, MediaMarkt, Vatan** | Idefix, Hepsiburada, Trendyol, Amazon |
| 0921204 | **Joker, Babymall, Idefix** | MediaMarkt, Hepsiburada |
| 0921207 | **Babymall, Joker, Idefix** (bikes, scooters) | MediaMarkt (kids' e-scooters), Trendyol (akülü araç) |
| 0922102 | **Voit, Teknosa, MediaMarkt** | Korayspor, Intersport, SPX, Hepsiburada, Amazon |
| 0922103 | **Intersport, SPX, Korayspor** | Teknosa, MediaMarkt, Hepsiburada |
| 0922107 | **SPX, Intersport, Korayspor** | Hepsiburada, Trendyol |
| 0932201 | **Petzzshop, Petburada, CarrefourSA** | Trendyol, Hepsiburada |
| 0932204 | **Petzzshop, Petburada, CarrefourSA** | Trendyol, Hepsiburada |
| 0945001 | **Ankara VHO tariff PDF, Leylek Vet, VetArt** | Remedy Veteriner |
| 0946103 | **İstanbul Akvaryum, KidZania İstanbul, Grupanya** | — |
| 0946201 | **Spor İstanbul (İBB), Arnavutköy Belediyesi, Kocaeli BB tariff PDF** | Grupanya |
| 0946203 | **Armut, Spor İstanbul, Grupanya** | Arnavutköy Belediyesi |
| 0947001 | **Bilyoner help centre, iddaa.com, TJK** | — |
| 0961001 | **Biletinial cinema section, Paribu Cineverse** (only 2) | — |
| 0961002 | **Biletix, Mobilet, İBB Şehir Tiyatroları** | — |
| 0969006 | **Düğün.com, DüğünBuketi, Armut** | DüğünYardımcısı, KonyaDüğün |
| 0971102 | **Kitapsec, BKM Kitap, Kitapsepeti** | Idefix, Amazon, Trendyol, Hepsiburada, n11 |
| 0971103 | **Kitapsec, BKM Kitap, Kitapsepeti** | Idefix, marketplaces |
| 0971901 | **BKM Kitap, Kitapsepeti, Kitapsec** | Idefix, marketplaces |
| 0971902 | **BKM Kitap, Kitapsepeti, Kitapsec** | Idefix, Ofix, marketplaces |
| 0974001 | **BKM Kitap, Ofix, Migros** | Idefix, Amazon, marketplaces |
| 0974003 | **BKM Kitap, Ofix, Migros** | Idefix, Keskin Color, marketplaces |
| 0974004 | **BKM Kitap, Ofix, Migros** | Idefix, marketplaces |
| 0974005 | **BKM Kitap, Ofix, Idefix** | Migros, Teknosa (Navigator brand page) |
| 0974009 | **BKM Kitap, Ofix, Migros** | Idefix, marketplaces |
| 0980002 | **Tatilbudur, Tatilsepeti, Gezi Tutkunları** | — |
| 0980003 | **Tatilbudur, Tatilsepeti, Setur** | Gezi Tutkunları |
| 0980006 | **Etstur, Setur, Tatilbudur** (EUR) | Tatilsepeti, Gezi Tutkunları |
| 0980008 | no new source: Diyanet is the only publisher of this fee | — |
| 0980009 | **Tatilsepeti, Rehber Turizm, THY Holidays\*** (USD) | — |

\* THY Holidays' JSON feed is priced for the US market; see §5.

**Already scraped elsewhere upstream** (extend their category lists instead of a new scraper):
MediaMarkt (`05_Furnishings/HomeGoods`), Vatan (`08_Communication/VatanComputer`), Migros and
CarrefourSA (`01_Food`), Armut (`04_Housing`, `05_Furnishings`, `06_Health`;
`Codes/04_Housing/RepairLabor/scraper.py` here uses the same `fiyatlari` pages).

## 4. Bot protection (deep test, 2026-10-30)

All 47 new sites passed the sustained `curl_cffi` test with the default `chrome` profile
(homepage first, then ~10 requests at 2–3 s). No site needed another profile or a browser.

| Class | Sites |
|---|---|
| **Active challenge** | Only the **Amazon.com.tr homepage** (AWS WAF, HTTP 202 challenge page). Search pages passed 10/10; start the session on a search URL, not the homepage. |
| **Passive bot management** (sets cookies, did not block us) | Akamai Bot Manager (`_abck`, `bm_sz`): Hepsiburada, Tatilbudur, Setur. Cloudflare `__cf_bm`: Teknosa, Trendyol, n11, Petzzshop, Petburada, Keskin Color, Bilyoner, Korayspor (plus Huawei Cloud WAF cookies). F5 BIG-IP (`TS01…` cookies): Paribu Cineverse, Kocaeli BB, iddaa.com, Idefix. |
| **Rate limit** | Spor İstanbul: 429 on quick bursts; fine with ≥8 s between requests. |
| **None / CDN only** | All others (Cloudflare CDN without bot cookie, CloudFront, NetScaler, plain servers). |

The passive vendors may tighten on large daily runs; keep delays and re-check with a bounded
live run (`--limit`) when a scraper is written.

## 5. Sources with an API (21)

| Site | Endpoint | Notes |
|---|---|---|
| Teknosa | `GET /<slug>-c-<id>/results?s=%3Arelevance&page=N` + `Accept: application/json`, `X-Requested-With` | JSON `results`, `pagination`. 0-based pages, 20 per page. Without `s=%3Arelevance` the page is ignored. |
| Idefix | `GET /_next/data/<buildId>/<slug>.json?sayfa=N` + `x-nextjs-data: 1` | Read `buildId` from `__NEXT_DATA__` each run. `/search` returned 511; use category URLs. |
| Trendyol | `GET https://apigw.trendyol.com/discovery-sfint-search-service/api/search/products/?channelId=1&pi=N&pageSize=36&pathModel=<slug>` (or `pathModel=sr&q=<query>`) | Needs `Origin`/`Referer: https://www.trendyol.com` and a session that loaded the site; bare requests get 418. `products[].price.{current,originalPrice,discountedPrice}`. |
| Joker | Shopify `GET /collections/<handle>/products.json?limit=250&page=N` | `variants[].price`. Stop on empty `products`. |
| Korayspor | `GET /_next/data/<buildId>/<slug>.json?slug=<slug>&page=N` | `salesPrice`, `discountPrice`, `totalPages`. 26 per page. |
| Intersport, SPX | Listing URL + `Accept: application/json`, `X-Requested-With: XMLHttpRequest` (Akinon) | `products[]{name, sku, price, retail_price}` and `pagination`. One scraper covers both. 72 / 24 per page. |
| Petzzshop | `POST https://api.myikas.com/api/sf/graphql/searchProducts` (ikas) | Headers `x-api-key` (public JWT in the page's `__IKAS_DATA__`), `x-sfid`, `x-sfrid`. HTML ignores `?page=`, so the API is the only way past page 1. Confirm the category id. |
| Petburada | `GET /api/product/GetProductList?...&PagingJson={"PageNumber":N,...}` (Ticimax) | Category id from inline `productsModel.targetId`. `productSellPrice` is **without VAT**; use `productSellPriceStr`. HTML `?sayfa=N` also works. |
| BKM Kitap | `GET /srv/service/content-v5/product-loader/300?link=<slug>&pg=N&language=tr&currency=TL` (T-Soft) | HTML fragment; `span.product-price`. An empty body ends the list. Invalid slugs silently return a default list. |
| Kitapsepeti | same T-Soft endpoint with block id `337` | 32 per call. |
| Ofix | `POST https://apiv4.ofix.com/catalog-gate/v1/Catalog/onlyProductsForCatalog` | Needs a guest token (`/auth-gate/v1/user/clientToken`, hash of the public `appSecret`) and breadcrumb names in `categoryList`. Fragile: prefer server HTML `?page=N` with the `window.__NUXT__` data. |
| Migros | `GET https://www.migros.com.tr/rest/search/screens/<slug>` | `shownPrice` in kuruş. Upstream `01_Food/Migros` already uses this API. |
| Grupanya | `GET <category-path>?handler=MoreDeals&p=N` | JSON `deals[]{title, dealPrice, dealValue, …}`, `hasMore`. No cookies. Small categories (fitness 2, pilates 4 in İstanbul). |
| Spor İstanbul | `GET /wp-json/wp/v2/pages?slug=<slug>&_fields=id,modified,link,content` | Full price tables in `content.rendered`; `modified` signals changes. ≥8 s spacing. |
| Bilyoner | `GET https://yardim.bilyoner.com/api/v2/help_center/tr/articles.json?per_page=100&page=N` (Zendesk) | Prices are free text in article bodies (e.g. "Her bir kolonun fiyatı ise 10,00 TL"); regex per article id; `updated_at` as change signal. |
| iddaa.com | `GET /_next/data/<buildId>/yardim/detay/<slug>.json?url=<slug>` | Help text, e.g. "bir kolonun fiyatı 1 TL, minimum … 50 TL". HTML-entity encoded. |
| Düğün.com | `GET https://dugun.com/api/providers/search?categoryId=77&cityId=<id>&limit=24&page=N` | No auth. `mainPrice{price, type: per_person/package, unit, catalogType}`, `discountPriceBefore/After`. İstanbul: 498 venues. `/api/cities` gives ids. |
| Paribu Cineverse | `POST /Film/GetAllowedSalesFilmsByFilter` → `POST /Cinema/GetCinemaListsByFilter` → `POST /Film/GetFilmSessions` → `GET /biletleme/~step~ticket~code~<cinema>~session~<id>` | `GetFilmSessions` must be **form-encoded** (`FilmIds[]`, `CinemaIds[]`, `Dates[]`); JSON gets an F5 "Request Rejected". Needs `X-Requested-With`, Referer, Origin. Ticket page shows TAM / ÖĞRENCİ prices. Never go past the ticket-type step. |
| Biletix | Event list: `GET /solr/tr/select/?q=*:*&fq=type:"event"&fq=subcategory:"tiyatro$ART"&wt=json&rows=50&start=N`; prices: `GET /wbtxapi/api/v1/bxcached/event/getPerformanceList/<eventId>/INTERNET/tr` | `minPrice` in kuruş; only the minimum price, not per category. |
| Mobilet | `GET https://cms.mobilet.com/api/events?locale=tr&populate[eventTickets]=*&filters[eventDate][$gte]=<date>&pagination[pageSize]=100&pagination[page]=N` (Strapi) | No auth. Per-ticket `name`, `eventProductPrice`, currency. Cleanest ticket source. |
| THY Holidays | `GET https://holidays.turkishairlines.com/current/en-US/TKHOENUS/merchandising/UMRAH.json` | Works, but the en-US feed is priced from US departures; the `tr-WW` feed returned 403. Not usable for TR CPI as is. |

## 6. HTML-only sources (26)

| Site | How prices appear | Notes |
|---|---|---|
| Hepsiburada | Server HTML + JSON-LD, `?sayfa=N` | Slow (4–5 s, 2.4 MB per page). |
| Amazon.com.tr | Search page HTML, `&page=N` | Do not hit the homepage (AWS WAF). An earlier run got 503 on repeated searches; pace slowly. |
| n11 | HTML + JSON-LD, `&pg=N` | Some pages take ~7 s. |
| Babymall | `PRODUCT_DATA.push(JSON.parse('…'))` blocks (escaped JSON, `total_sale_price`), `?pg=N` | T-Soft, no product API. |
| Voit | `div.actual-price`, `?pagenumber=N` | ~100 per page. |
| Kitapsec | `<font class="satis">` / `piyasa`; pagination `/…/{page}-6-0a0-0-0-0-0-0.xhtml` | Charset **iso-8859-9**. |
| Keskin Color | `span.discountPriceSpan` (Ticimax); follow `<link rel="next">` | Only shop with `__cf_bm` among books/stationery. |
| Ankara VHO | Tariff PDFs linked from `/asgari-ucret-tarifeleri/` (`/wp-content/uploads/YYYY/MM/*.pdf`) | Text PDF (pypdf). New tariff twice a year (Jan, Jul). wp-json is disabled. |
| Leylek Vet, VetArt, Remedy | Static price pages | Repeat the İstanbul chamber tariff, so not independent prices. İstanbul VHO's own PDF failed with an SSL chain error. |
| İstanbul Akvaryum | HTML; price split across elements ("2.900" + ".00 ₺") | List price + citizen campaign price. |
| KidZania İstanbul | Homepage "Giriş Ücretleri" table | A holiday promo block sits next to it. |
| Arnavutköy Belediyesi | Static price table | Links to other municipal tariff pages. |
| Kocaeli BB | 103-page tariff PDF from `/belediye-vergi-ve-ucret-tarifeleri.html` | Prices **excl. VAT**, VAT rate column. Has `Last-Modified`/`ETag`; use conditional GET. |
| TJK | Static page, "(Birim fiyat 1 TL.)" per bet type | Horse betting: COICOP games of chance, not one of the listed example products. |
| DüğünBuketi | Cards "₺500,00 Başlangıç Fiyatı"; `/p/dugun-salonlari/<city>?page=N` until empty | |
| DüğünYardımcısı | Use `https://dugunyardimcisi.com` (`www` returns 526); `/bolge/<city>/page/N` | Mixed vendor types, odd old prices. Weakest source. |
| KonyaDüğün | `/salonlar`: all 118 venues on one page | Konya only. |
| İBB Şehir Tiyatroları | Static table `/sayfa/bilet-fiyatlari` | Official tariff, not per show. |
| Tatilbudur | JSON-LD ItemList (TouristTrip offers), `?page=N` | |
| Tatilsepeti | JSON-LD + HTML, `?sayfa=N` | JSON-LD labels USD/EUR prices as TRY; read currency from `.price-currency`. |
| Gezi Tutkunları | JSON-LD, `?page=N` | |
| Setur | Next.js RSC stream (`self.__next_f.push`), `pricing{selling, discounted, currency}` | No JSON-LD; not every tour has pricing in SSR. |
| Etstur | JSON-LD ItemList (all tours of a category on one page) | EUR. Domestic culture-tour page has no static prices. |
| Rehber Turizm | Plain HTML, single page | USD in inconsistent formats ("999 $", "1,550.000 USD"). |

## 7. Rejected candidates (main ones)

| Site | Reason |
|---|---|
| e-bebek | AWS WAF challenge after ~5 requests, every URL. |
| Columbia TR | Prices loaded client-side; API not found. |
| Passo, Devlet Tiyatroları, Babil, Bubilet (theatre path) | JS shell, no prices in HTML. |
| Cinemapink, Cinetime, Cinetech, Avşar, Prestige | TLS mismatch, login gate, dynamic sessions or no working domain. |
| Nesine, Misli, Oley, Birebin | SPA shells; no published prices. |
| Vialand/Isfanbul, Sea Life, Legoland, Miniatürk | Timeouts, 404, or no prices. |
| Faber-Castell, Adel, Gıpta | Manufacturer catalogues without prices. |
| Zooplus TR, Mopet, Petshoponline, Sporium, Coral Travel | Domain does not resolve. |
| Prontotour, Gezinomi | Listing prices loaded by JS (detail pages have prices). |
| Antalya, Konya, Denizli, Eskişehir vet chambers; Enka; sportoto.gov.tr | Prices only in images (OCR needed). |

## 8. Pitfalls to remember

- Currency: Tatilsepeti JSON-LD (TRY label on USD/EUR), Biletix and Migros prices in kuruş,
  tours abroad in EUR, umrah in USD.
- VAT: Petburada `productSellPrice` and Kocaeli tariff are without VAT.
- Next.js `buildId` (Idefix, Korayspor, iddaa) changes on deploy; read it each run.
- Games-of-chance prices are free text; alert when the article changes.
- The probe's `price_hits` regex misses some formats (₺ after the number split by tags); a 0 there
  is not proof of no prices.
- On Windows, run the probes with `python -I -X utf8` (cp1254 console crashes on emoji titles;
  `-I` ignores `PYTHONIOENCODING`).

## 9. Tools

Run from the repo root so the project environment (`curl_cffi`, `seleniumbase`) is used:

```bash
uv run python -I -X utf8 docs/site-analysis/recreation/tools/cffi_probe.py <homepage-or-listing-url> <listing-url>
```

```bash
uv run python -I -X utf8 docs/site-analysis/recreation/tools/deep_probe.py --n 10 --delay 2 <listing-url> <page-2-url> <product-url>
```

```bash
uv run python -I -X utf8 docs/site-analysis/recreation/tools/sb_probe.py <listing-url>
```

- `cffi_probe.py`: one request per URL after the homepage; status, size, block markers, price hits.
- `deep_probe.py`: sustained test, anti-bot vendor detection from headers/cookies/HTML, API hints;
  `--api URL…` tests JSON endpoints; `--impersonate firefox135|safari|chrome124`.
- `sb_probe.py`: SeleniumBase UC headless; title, price hits, XHR/fetch URLs (API discovery).

These are recon tools, not scrapers. Per `AGENTS.md`, a new scraper is verified by a bounded live
run and its CSV output, not by these probes.

## 10. Next steps

1. Fix the existing 09 data: codes for Nezih, `category_number` for DR/MACFit/Milli_Piyango/
   Zuhal_Muzik, Zuhal parent codes, empty Sports scrapers.
2. Write scrapers for the five items with no source, highest weight first: 0946203 + 0946201
   (Spor İstanbul wp-json, Armut, Grupanya API), 0946103, 0945001 (AVHO PDF), 0969006
   (Düğün.com API), 0961001 (Paribu chain + Biletinial cinema).
3. Add the cheap API sources for thin items: Akinon (Intersport + SPX) for 0922107, Mobilet and
   Biletix for 0961002, Tatilbudur/Tatilsepeti/Etstur JSON-LD for tours.
4. Extend upstream MediaMarkt, Vatan, Migros, CarrefourSA scrapers with 09 categories.
5. Decide whether other-group 09 tags count, after fixing their mapping rules.
