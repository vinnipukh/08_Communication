# Arnavutköy Belediyesi – sports facility and course fees

Source for TÜİK items **0946203** (Sports training fee) and **0946201** (Payments for sports
facilities). Arnavutköy is an İstanbul district municipality; its sports portal
`https://spor.arnavutkoy.bel.tr/` is linked from `www.arnavutkoy.bel.tr` ("Spor Faaliyetleri",
"Spor Randevu").

## Source

Static server HTML, no bot protection seen (LiteSpeed). Requests:

```
GET https://spor.arnavutkoy.bel.tr/              (homepage first)
GET https://spor.arnavutkoy.bel.tr/tesisler      (facility list -> /tesis/<slug> links)
GET https://spor.arnavutkoy.bel.tr/tesis/<slug>  (12 facility pages)
```

Each facility page has fee tables in `.page-content__description`: rows are
`<label> | <price> ₺`, rows without a price are group headers ("Yüzme Kursları (10 Seans)",
"ÖZEL DERS TARİFELERİ (ALETLİ PİLATES)", "YENİ SPOR KOMPLEKSİ 1 AYLIK PAKET"). A table without a
group header takes its caption above the table ("… Fıtness Ücret Tarifesi" → `Fıtness`).
Vadipark Halı Sahası gives its price in a sentence ("1 Saatlik Halı saha Abonelik Ücreti:
2.940.00 TL"), which is read with a regex. The four stadiums and the indoor hall have no
prices on their pages (2026-10-31).

Not used:

- `/kurs/<slug>` pages (yüzme, fitness, aletli pilates, paket üyelik, kadın kültür merkezi):
  they repeat the facility tables with **older, lower prices** (e.g. package 2,500 TL vs 3,250
  TL), so they are stale.
- `www.arnavutkoy.bel.tr/tesis/<slug>`: copies of the portal facility pages.
- The council tariff PDF (`www.arnavutkoy.bel.tr/tarife/ucret-tarifeleri`, "2026 Yılı Harç ve
  Ücret Tarifesi", 20 pages): its sports section matches the HTML prices (800 / 650 / 500 / 120
  TL, 2,940 TL pitch) and also lists hall rentals (1,500 TL/hour …), outdoor pitch (2,300 TL)
  and tennis court (1,300 TL/hour) that are not in the HTML. Not parsed (text PDF, layout
  changes yearly); a possible extension for more 0946201 rows.

## Mapping

On "group + label" in Turkish lower case, in this order:

1. `serbest`, `abone`, `tek kullanım` → **0946201** (free-swim subscription, single use,
   fitness subscription, pitch subscription; these labels contain "Kurs" but are not lessons).
2. `eğitim`, `ders`, `kurs`, `akademi`, `okul`, `antrenör` → **0946203** (swimming course
   10 sessions, academy monthly fee, reformer pilates group/private lessons).
3. `paket`, `üyelik`, `seans`, `kiralama`, `giriş`, `halı saha` → **0946201** (1/3/6/12-month
   packages).
4. Otherwise dropped (logged).

2026-10-31 run: 27 rows (0946201: 19, 0946203: 8) from 7 facilities.

Product name: `Arnavutköy Belediyesi - <facility> - <group or caption> - <label>`, e.g.
`Arnavutköy Belediyesi - Hadımköy Spor Kompleksi - Yüzme Kursları (10 Seans) - Eğitim Seansı`.

## Output

`InflationItems/Datas/09_Recreation/ArnavutkoyBelediyesi/arnavutkoy_YYYY-MM-DD.csv`
(UTF-8 with BOM):

`product_name, price, category_number (9), sub_category_number, facility, group, item,
vat_included, source_url`

Prices are TRY and **include VAT** ("Yukarıdaki ücretlere KDV dahildir" under the tables and in
the council tariff). Discounts (students 60 %, retirees / 60+ / public staff 15 %) are not
applied.

## Run

```
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/ArnavutkoyBelediyesi/arnavutkoy_scraper.py
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/ArnavutkoyBelediyesi/arnavutkoy_scraper.py --limit 2   # bounded run
```

Options: `--limit N` (first N facility pages), `--date YYYY-MM-DD`. 14 requests at 2 s, ~30 s.
No CSV is written when nothing is parsed.

## Sitemap

`robots.txt` and `sitemap.xml` do not exist (`www`: 404; portal: "Controller bulunamadı!"
page). **Not used**: `/tesisler` lists every facility in one request.

## Caveats

- Fees are set once a year by the council (decision of 2025-12-04 for 2026); daily rows will
  mostly repeat.
- The same tariff applies to several facilities, so equal prices appear once per facility.
- The Kadın Kültür ve Sanat Merkezi table still says "2024 YILI" in a header cell, but its
  prices (120 / 650 TL) are the 2026 council tariff values.
