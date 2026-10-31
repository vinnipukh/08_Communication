# TÜİK 09 Recreation, sport and culture: coverage check and new sources

Work done: 2026-10-30 / 2026-10-31. Status: **existing 09 scrapers made browser-free and fixed
(§11); SPX added; no other new source written yet.**

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
Bold = recommended first three. Marketplaces (Hepsiburada, n11, Amazon) are listed as
backups; at least one non-marketplace per item.

| Code | Recommended new sources | Backups |
|---|---|---|
| 0921104 | **Teknosa, MediaMarkt, Vatan** | Hepsiburada, Amazon |
| 0921204 | **Joker, Babymall** | MediaMarkt, Hepsiburada |
| 0921207 | **Babymall, Joker** (bikes, scooters) | MediaMarkt (kids' e-scooters) |
| 0922102 | **Voit, Teknosa, MediaMarkt** | Korayspor, Intersport, SPX, Hepsiburada, Amazon |
| 0922103 | **Intersport, SPX, Korayspor** | Teknosa, MediaMarkt, Hepsiburada |
| 0922107 | **SPX, Intersport, Korayspor** | Hepsiburada |
| 0932201 | **Petzzshop, Petburada, CarrefourSA** | Hepsiburada |
| 0932204 | **Petzzshop, Petburada, CarrefourSA** | Hepsiburada |
| 0945001 | **Ankara VHO tariff PDF, Leylek Vet, VetArt** | Remedy Veteriner |
| 0946103 | **İstanbul Akvaryum, KidZania İstanbul, Grupanya** | — |
| 0946201 | **Spor İstanbul (İBB), Arnavutköy Belediyesi, Kocaeli BB tariff PDF** | Grupanya |
| 0946203 | **Armut, Spor İstanbul, Grupanya** | Arnavutköy Belediyesi |
| 0947001 | **TJK** (only 1) | — |
| 0961001 | **Biletinial cinema section, Paribu Cineverse** (only 2) | — |
| 0961002 | **Biletix, Mobilet, İBB Şehir Tiyatroları** | — |
| 0969006 | **Düğün.com, DüğünBuketi, Armut** | DüğünYardımcısı, KonyaDüğün |
| 0971102 | **Kitapsec, BKM Kitap, Kitapsepeti** | Amazon, Hepsiburada, n11 |
| 0971103 | **Kitapsec, BKM Kitap, Kitapsepeti** | marketplaces |
| 0971901 | **BKM Kitap, Kitapsepeti, Kitapsec** | marketplaces |
| 0971902 | **BKM Kitap, Kitapsepeti, Kitapsec** | Ofix, marketplaces |
| 0974001 | **BKM Kitap, Ofix, Migros** | Amazon, marketplaces |
| 0974003 | **BKM Kitap, Ofix, Migros** | Keskin Color, marketplaces |
| 0974004 | **BKM Kitap, Ofix, Migros** | marketplaces |
| 0974005 | **BKM Kitap, Ofix, Migros** | Teknosa (Navigator brand page) |
| 0974009 | **BKM Kitap, Ofix, Migros** | marketplaces |
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

All 47 new sites (43 after the 2026-10-31 removals, see §11) passed the sustained `curl_cffi` test with the default `chrome` profile
(homepage first, then ~10 requests at 2–3 s). No site needed another profile or a browser.

| Class | Sites |
|---|---|
| **Active challenge** | Only the **Amazon.com.tr homepage** (AWS WAF, HTTP 202 challenge page). Search pages passed 10/10; start the session on a search URL, not the homepage. |
| **Passive bot management** (sets cookies, did not block us) | Akamai Bot Manager (`_abck`, `bm_sz`): Hepsiburada, Tatilbudur, Setur. Cloudflare `__cf_bm`: Teknosa, n11, Petzzshop, Petburada, Keskin Color, Korayspor (plus Huawei Cloud WAF cookies). F5 BIG-IP (`TS01…` cookies): Paribu Cineverse, Kocaeli BB. |
| **Rate limit** | Spor İstanbul: 429 on quick bursts; fine with ≥8 s between requests. |
| **None / CDN only** | All others (Cloudflare CDN without bot cookie, CloudFront, NetScaler, plain servers). |

The passive vendors may tighten on large daily runs; keep delays and re-check with a bounded
live run (`--limit`) when a scraper is written.

## 5. Sources with an API (17)

| Site | Endpoint | Notes |
|---|---|---|
| Teknosa | `GET /<slug>-c-<id>/results?s=%3Arelevance&page=N` + `Accept: application/json`, `X-Requested-With` | JSON `results`, `pagination`. 0-based pages, 20 per page. Without `s=%3Arelevance` the page is ignored. |
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
- Next.js `buildId` (Korayspor) changes on deploy; read it each run.
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

1. ~~Fix the existing 09 data~~ done 2026-10-31 (§11). Still open: the stray
   `Datas/09_Recreation/Nezih/beymen_enflasyon_2026-10-02.csv`.
2. Write scrapers for the five items with no source, highest weight first: 0946203 + 0946201
   (Spor İstanbul wp-json, Armut, Grupanya API), 0946103, 0945001 (AVHO PDF), 0969006
   (Düğün.com API), 0961001 (Paribu chain + Biletinial cinema).
3. Add the cheap API sources for thin items: Akinon (Intersport; SPX done) for 0922107, Mobilet and
   Biletix for 0961002, Tatilbudur/Tatilsepeti/Etstur JSON-LD for tours.
4. Extend upstream MediaMarkt, Vatan, Migros, CarrefourSA scrapers with 09 categories (§11.2: none
   of them collects 09 today).
5. Decide whether other-group 09 tags count, after fixing their mapping rules.

## 11. Automation preparation (2026-10-31)

### 11.1 Fetch method per scraper

All 09 scrapers now run without a browser. `curl_cffi` means Chrome TLS impersonation
(`impersonate="chrome"`) with the homepage requested first.

| Scraper | HTTP client | Data source | Change on 2026-10-31 |
|---|---|---|---|
| Avansas, Petlebi, Jollytur | `requests` | Server HTML | none |
| Kitapyurdu | `requests` | Server HTML `index.php?route=product/list` | an empty page after page 1 now ends the category (it was retried 3× per page up to page 20); history CSVs moved out of the nested `Kitapyurdu/Kitapyurdu/` folder |
| Diyanet | `requests` | Brochure PDF + TCMB XML | **OCR added** (see below) |
| DR | `requests` | HTML (`data-gtm` JSON on cards) | upstream `category_number` column copied |
| MACFit | `curl_cffi` (fallback `requests`) | JSON API `portal-gateway.marsathletic.com` | upstream `category_number` column copied; the club list is retried on 404 (a transient 404 stopped a full run on 2026-10-31) |
| Zuhal Müzik | `requests` | AJAX `/urun?category=&page=` (JSON with an HTML fragment) | upstream `category_number`; parent codes `09212`/`0922` replaced by `0921204`/`0922103` |
| Nezih | `requests`, `curl_cffi` fallback | `PRODUCT_DATA` JSON in the HTML (T-Soft) | four required columns added in front; COICOP code from the site category path |
| **Toyzzshop** | `curl_cffi` | JSON API `core.toyzzshop.com/api/categories/<id>/products?limit=48&order=ocd&page=N` | **Playwright removed** (the site is a JS app; its HTML has no products) |
| **Biletinial** | `curl_cffi` | Listing HTML (50 server-rendered cards) + `/List/GetMoreItems` JSON; event pages HTML | **Playwright scroll removed** |
| **Hisar Turizm** | `curl_cffi` | `var tourFrontend = {...}` JSON in the page + `admin-ajax.php` `action=filter_tours` (POST, nonce from the page) | **Playwright fallback removed**. The static HTML never had cards, so the browser ran every day and saw only page 1 (20 of 556 umrah tours) |
| Milli Piyango | `curl_cffi` | Rules pages HTML | was `requests`, which times out on this site, so every row came from a hard-coded fallback. Fallback and the unsourced "Standart Çekiliş" rows removed; no CSV is written when nothing is scraped |
| Decathlon | `curl_cffi` | HTML `?from=&size=40` | was `requests` with a custom UA, which gets a Cloudflare 403; `--max-pages` added |
| Korayspor | `curl_cffi` | HTML + `__NEXT_DATA__` `totalPages` | upstream scraper copied (the file was empty here); Cloudflare-safe client and pagination added |
| **SPX** (new) | `curl_cffi` | Akinon listing JSON (`Accept: application/json`, `X-Requested-With`) | new `Sports/spx_scraper.py`: ekipman (0922103), kadın tayt (0922107) |
| Sportive | — | — | empty placeholder removed: the site is an Akinon Next.js storefront without a JSON listing, and it is not in §3 |

Verified by bounded live runs on 2026-10-31 (one page per category, or `--limit`); names and
prices matched the previous day's CSVs. Hisar Turizm now writes about 1,250 umrah rows (all 556
tours, 2/3/4-person rooms for economy packages, sold-out tours skipped) instead of about 30.

Diyanet OCR (`--extract ocr`, the default): every brochure page is rendered with `pypdfium2`
(scale 3) and read with RapidOCR (`rapidocr-onnxruntime`); both are pip packages, no system
install. OCR text is unreliable in table order (multi-line cells), Turkish letters ("Günlük" →
"Gunluk") and 0/O in codes, so the parser works on box geometry: a price is the 3–4 digit token
directly left of a bank code on the same row, and the tour comes from the code itself (all 300 codes
are letter + 6 digits + B/C/D, digits 5–6 = tour number), so a code with a dropped digit is rejected.
Where a page has a PDF text layer, it is used for the values and OCR is checked against it;
OCR-only values are used for pages without text. 2026-10-31 brochure (16 pages, ~1 min):
OCR read 294 of 300 price/code pairs, 0 differed from the text layer; the 6 missed pairs are
cells where the price and the code are on different lines. `--extract text` skips OCR.
The drop from 122 rows (10-29) to 104 is tours whose application deadline has passed
(`--include-expired` gives all 300).

Nezih code mapping (`_coicop_code` in `nezih_scraper.py`): Kitap › Ders & Sınav › Sınav Kitapları
→ 0971102, other Ders & Sınav → 0971103, Çocuk Kitapları → 0971901, other books → 0971902;
Defter → 0974001 (Resim Defterleri → 0974005), Kalemler → 0974003 (silgi, kalemtraş, silici,
mürekkep → 0974009), Boyalar → 0974004, Kağıt → 0974005 (etiket, sticker, zarf, evrak → 0974009),
oyun hamuru, Kırtasiye Hobi and Puzzle → 0921204, Kalem Kutuları → 0974009, other stationery →
0974009. Dropped as outside 09: bags and bottles, calculators, musical instruments.

CSV format (all 16 scrapers, from 2026-10-31): the first four columns are
`product_name, price, category_number, sub_category_number` in this order, and `category_number`
is `9` without a leading zero, like this repo's 04/08 data (`4`, `8`) and upstream's shared
`InflationItems/Codes/price_csv.py` (`str(group)`). Upstream `AGENTS.md` rule 4 only requires the
four columns; its inflation code reads `category_number` with `zfill(2)`, so `9` and `09` both
parse. Source-specific columns (DR/Zuhal/Milli Piyango `category_name`, MACFit club fields, Nezih
store fields, `product_url`) follow after the four. CSVs written before this date keep `09`
(12 sources) or the old DR/MACFit/Milli Piyango/Zuhal order with `category_number` last.

### 11.2 Do the upstream stores in other groups already collect 09?

Latest upstream CSVs (`urazkagangunes/InflationResearchStudy`, 2026-10-30/31), counted by
`category_number` and `sub_category_number`:

| Store (upstream folder) | Rows | `category_number` | 09 rows |
|---|---|---|---|
| CarrefourSA (`01_Food`) | 4,801 | 1 | 0 |
| Migros (`01_Food`) | 3,438 | 01 (a few 0, 05, 09, 13, 04) | 3, all mis-tagged (yoghurt with a toy gift, honey, cat-tongue chocolate) |
| KarekodMigros (`02_Alcohol_Tobacco`) | 749 | 02 | 0 |
| Armut (`04_Housing`, `05`, `06`) | 69 / 15 / 16 | 4 / 05 / 06 | 0 |
| MediaMarkt (`05_Furnishings/HomeGoods`) | 520 | 05 | 0 |
| VatanComputer (`08_Communication`, also in this repo) | 5,534 | 8 | 0 |

None of them covers group 09, so step 4 of §10 is still needed.

### 11.4 Scrapers for the five uncovered items (2026-10-31)

All 30 basket items now have at least one source. New scrapers (curl_cffi, homepage first, four
standard columns first, `category_number` 9; details in each folder's README):

| Item | Scraper | Source / method | Rows 2026-10-31 |
|---|---|---|---|
| 0946203 (+0946201) | `SporIstanbul/` | `spor.istanbul` wp-json page `uyelik-bilgileri` (2026 tariff), ≥8 s between requests | 29 + 53 |
| 0946203 (+0946201) | `ArnavutkoyBelediyesi/` | `spor.arnavutkoy.bel.tr` facility pages (HTML tables) | 8 + 19 |
| 0946103 (+0946203) | `Grupanya/` | `?handler=MoreDeals&p=N` JSON | 60 + 16 |
| 0946103 | `IstanbulAkvaryum/` | ticket page HTML (list + İstanbullu price) | 26 |
| 0946103 | `KidZania/` | homepage "Giriş Ücretleri" table | 6 |
| 0945001 | `AnkaraVHO/` | newest "Ev Hayvanları" one-page tariff PDF; OCR (pypdfium2 + RapidOCR) checked against the text layer: 155/155 cells equal | 155 |
| 0969006 | `DugunCom/` | listing pages `/dugun-salonlari/<city>` JSON-LD (the `/api` is disallowed by robots.txt); most venues hide prices | 230 |
| 0969006 | `DugunBuketi/` | Inertia JSON in `/p/dugun-salonlari/<city>?page=N`; 203 rows have an inferred price type | 1,744 |
| 0961001 | `Biletinial/` (extended) | `/tr-tr/sinema`: cheapest ticket per film and cinema, same daily CSV as theatre, `--only theatre/cinema` | 394 |

Second round (2026-10-31, sites chosen by the user), all curl_cffi, four standard columns first:

| Item | Scraper | Source / method | Rows |
|---|---|---|---|
| 0932201 (+0932204) | `Petzzshop/` | ikas storefront API (same call the site makes) | 2,341 + 1,143 |
| 0932201 (+0932204) | `Petchef/` | product sitemap (181 URLs; category pagination is disallowed by robots.txt) + product pages | 326 + 18 |
| 0932201 (+0932204) | `TemizMama/` | product sitemap (94 URLs; their API is disallowed) + product pages | 190 + 44 |
| 0945001 | `VetArt/` | static price table (an extract of the İstanbul chamber tariff, 2026/1; KDV not stated) | 21 |
| 0922107 | `Sports/decathlon_scraper.py` (extended) | 7 clothing listings (run, fitness, cycling, swimming, ski, outdoor, yoga) into the same daily CSV as home fitness; `--only fitness/clothing`, page caps, ~15 min per full run | 1,834 (+1,285 fitness) |

| 0945001 | `IVHO/` | İstanbul chamber tariff booklet (`ivho.org.tr`, 2026/2), text layer read with pypdfium2 (no OCR needed); KDV included | 695 (322 cat, 371 dog, 2 shared cells) |

Petchef and TemizMama are the only 09 scrapers that use a sitemap: there it is the only allowed way to
list all products. **İVHO** needed a TLS workaround: the server sends no intermediate certificate, so
plain verification fails (browsers fetch it themselves). Verification is never disabled: the scraper
downloads the Sectigo intermediate from the certificate's own CA-issuers URL, **verifies its signature
against a `certifi` root** (an unauthenticated download must not become a trusted CA), and uses the
resulting bundle for ivho.org.tr only. The current PDF is found through VetArt's and Atakent Vet's
pages (the clinic page lists no prices itself; its images are only the booklet cover). Needs
`cryptography`. Details: `InflationItems/Codes/09_Recreation/IVHO/README.md`.

Not written: Armut (already scraped in 04/05/06), Leylek Vet/VetArt/Remedy (repeat the İstanbul
chamber tariff), DüğünYardımcısı (weak), KonyaDüğün (down). Paribu Cineverse: a scraper was written and a
3-cinema run worked (fixed per-cinema Tam/Öğrenci prices, e.g. Bolu 2D 325/300 TL), but robots.txt disallows
`/biletleme/`, the only page with ticket prices, so it was dropped on 2026-10-31 and its folder moved to the
Recycle Bin (the endpoint chain is in §5). It has no data.
sitemap.xml was checked for every new site and used by none: no sitemap carries prices, and the
listing pages / APIs return many priced items per request.

### 11.3 Removed candidates

Idefix, Trendyol, Bilyoner and iddaa.com were dropped from the source list on 2026-10-31.
0947001 now has one new candidate (TJK) next to the existing Milli Piyango scraper.
