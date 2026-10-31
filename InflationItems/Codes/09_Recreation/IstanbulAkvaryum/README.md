# Istanbul Akvaryum (istanbulakvaryum.com)

TUIK group 09, item 0946103 (Recreation and hobby services): aquarium entry tickets and packages.

## Source and endpoints
Server-rendered HTML `https://www.istanbulakvaryum.com/ziyaretinizi-planlayin/biletal` (homepage fetched
first). Each ticket is a `div.hemenbiletal_paketbox` card: name in `.hemenbiletal_paketbox_kisi strong`,
price in `.hemenbiletal_paketbox_fiyat`. The price is split across elements ("2.750." + "00 TL") and is
reassembled by `parse_try`. No API call.

## Mapping rule
Every card -> `0946103`. A card with a struck-through price yields two rows: `... - liste fiyati`
(`price_type=list`, the struck price) and `... - TC vatandasi kampanya fiyati` (`citizen_campaign`, the
large price, valid for Turkish citizens). A card with a single price yields one `... - TC vatandasi fiyati`
row (`citizen`). Extra columns: ticket_name, price_type, section, ticket_id, product_url.

## Run
```
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/IstanbulAkvaryum/istanbulakvaryum_scraper.py
```
Bounded run: `--limit N` (writes the first N rows). `--date YYYY-MM-DD` sets the output date. Exits 1 and writes
nothing when no prices are found. Output: `InflationItems/Datas/09_Recreation/IstanbulAkvaryum/istanbulakvaryum_YYYY-MM-DD.csv`.
Full run: about 6 s, 26 rows on 2026-10-31 (all 0946103).

## Sitemap verdict
Not used. `sitemap.xml` exists (Screaming Frog export, last modified 2025) but the single ticket page is
known; robots.txt allows `/`.

## Caveats
- Prices are for Turkish citizens; foreign-visitor prices are not published on this page.
- Package names (SILVER/GOLD/...) are site marketing names and may be renamed; the product set is the
  site's current offering.
