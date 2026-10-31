# Spor İstanbul (İBB) – sports fees

Source for TÜİK items **0946203** (Sports training fee) and **0946201** (Payments for sports
facilities). Spor İstanbul is the İstanbul Metropolitan Municipality's sports company
(`https://spor.istanbul/`; the old domain `sporistanbul.istanbul` no longer resolves).

## Source

The yearly fee tariff ("İBB SPOR TESİSLERİ ŞUBE MÜDÜRLÜĞÜ SPOR TESİSLERİ 2026 YILI ÜCRET
TARİFESİ", ~185 priced rows in 45 sections) is a set of HTML tables on the WordPress page
`tesislerimiz/uyelik-bilgileri`. The WP REST API returns the whole page:

```
GET https://spor.istanbul/                     (homepage first)
GET https://spor.istanbul/wp-json/wp/v2/pages?slug=uyelik-bilgileri&_fields=id,slug,modified,link,content
```

If that slug ever stops holding the tariff, the scraper searches
`/wp-json/wp/v2/pages?search=Ücret Tarifesi` and takes the first page with a "BİRİM FİYAT"
table. `modified` is written to the CSV (`page_modified`), so a tariff change is visible.

The other price pages were checked on 2026-10-31 and add nothing new: `spor-okullari`
(300 TL term fee = tariff row 29.1) and `paket-uyelikleri` (1,600 / 1,600 / 1,800 / 200 TL =
rows 18.1–18.3 and 44.1). `1tl-spor-yap` and `kadinlara-ozel-1-tlye-spor-destegi` are 1 TL
social campaigns, not list prices.

## Mapping

Each tariff row is classified on "section + item" (Turkish lower case), in this order:

1. **Dropped**: company / foundation / club / league / event / tournament / organisation
   rentals, season fees, film and advertising, offices, stands, lockers, storage, conference
   and training rooms, boat racks, boat parks and hire, cranes, skate hire, performance tests.
2. **0946203**: kurs, eğitim, ders / özel ders, okul, antrenör, hazırlık, akademi, sporcu
   grubu, senkronize (skating/hockey schools, private lessons, sports schools, prep courses,
   group racket training, "Eğitim ve Gelişim" term fee).
3. **0946201**: üyelik, kullanım, kiralama/kira, serbest seans, giriş, abone, or an hourly
   unit (Saat, 90 Dakika): memberships (12 uses), single use, court/pitch/pool/ice hourly
   rentals, free sessions.
4. Anything else is dropped (e.g. velodrome bicycle, 42.1).

2026-10-31 run: 82 rows kept (0946201: 53, 0946203: 29), 103 dropped.

Product name: `Spor İstanbul - <SECTION> - <item> - <unit>`, e.g.
`Spor İstanbul - BUZ PİSTİ(OLİMPİK PİST) SAATLİK GİRİŞ - Hokey Okulu Haftada 2 gün - Aylık`.
Units: `Kullanım (12)` → `12 Kullanım`, `Saat` → `Saatlik`, `Ay`/`Aylık` → `Aylık`,
`Kişi` → `Kişi Başı`.

## Output

`InflationItems/Datas/09_Recreation/SporIstanbul/sporistanbul_YYYY-MM-DD.csv` (UTF-8 with BOM):

`product_name, price, category_number (9), sub_category_number, tariff_item, section, item,
unit, tariff_year, vat_included, page_modified, source_url`

Prices are TRY. Tariff rule 18: prices **include VAT** (VAT is added only for rentals to
companies, which are dropped). Discounts (students, retirees, 65+, İBB staff…) and the 3×
price for foreign passports are not applied.

## Run

```
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/SporIstanbul/sporistanbul_scraper.py
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/SporIstanbul/sporistanbul_scraper.py --limit 5   # bounded run
```

Options: `--limit N` (keep the first N rows), `--date YYYY-MM-DD`. Two requests, ~10 s.
No CSV is written when nothing is parsed.

## Sitemap

`robots.txt` lists `wp-sitemap.xml`. **Not used**: the tariff page is known, and one REST call
returns it (the full page list, 49 pages, is a single `per_page=100` call if discovery is ever
needed). The sitemap would only add requests.

## Caveats

- **Rate limit**: HTTP 429 on quick bursts. The scraper waits 8 s between requests and backs
  off 16 s / 32 s on errors.
- The tariff is yearly (2026); prices change in January or by council decision. The table
  numbering has typos (row "31,1" inside section 34), so `section` comes from the section
  header row, not from the item number.
- Section names are kept as published (upper case), not title-cased, to avoid Turkish
  İ/I mistakes.
