# Biletinial (TÜİK 0961002 theatre, 0961001 cinema)

One scraper, one daily CSV: `InflationItems/Datas/09_Recreation/Biletinial/biletinial_YYYY-MM-DD.csv`
(`utf-8-sig`, columns `product_name,price,category_number,sub_category_number`, `category_number` = `9`, price in TRY with two decimals).

## Run

```
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/Biletinial/biletinial_scraper.py
```

Options: `--date YYYY-MM-DD` (output file date), `--only theatre|cinema` (the other part already in that day's CSV is kept),
`--max-events N` (theatre debug cap), `--max-films N` (default 30), `--max-cinemas N` (default 150).
A full run takes about 5 minutes (theatre about 30 s, cinema about 4.5 minutes). The CSV is written only if rows exist.

Transport: curl_cffi `Session(impersonate="chrome")`, homepage first, retries on 429/5xx. Theatre uses 0.5 s between
requests, cinema 1.5 s. No browser is needed.

## Theatre (0961002)

`/tr-tr/tiyatro` (first 50 cards server-rendered) then `GET /List/GetMoreItems?organizerUrl=tiyatro&page=N` until it returns no items
(on 2026-10-31 page 2 was empty, so the listing is 50 events). Each event page is parsed for session blocks and ticket types
(Tam, Öğrenci, ...). About 750 rows. Output format is unchanged from the earlier Playwright version.

## Cinema (0961001)

1. `/tr-tr/sinema` lists the films (44 on 2026-10-31) plus one `GetMoreItems` check for a longer listing.
2. Each film page gives the event id and the cities where it plays.
3. `GET /dynamic/get_seances/<event>/<city>/<date>/1/tr` (today, then tomorrow) lists the cinemas showing the film.
4. Each cinema page `/tr-tr/mekan/<slug>` has one card per film with the cinema's "Başlangıç Fiyatı" (starting price).

Rows are named `<film> - <cinema> - Başlangıç Fiyatı`. On 2026-10-31: 36 cinemas, 394 rows, prices 150 to 600 TRY.

Coverage and caps: the first 30 films already surface all 36 cinemas (a run with 60 films, i.e. all 44, found the same 36), so the
default `--max-films 30` loses nothing today. `--max-cinemas 150` was not reached. The cinema set is what Biletinial sells
(mostly independent and mall cinemas); the large chains with their own sites (Paribu Cineverse, Cinemaximum, Cinemarine) are mostly absent.

## sitemap / robots.txt

`sitemap.xml` is an index of `sitemap-home`, `sitemap-event`, `sitemap-event-group`, `sitemap-place`; `sitemap-event.xml` was empty on 2026-10-31
(the event sitemap lives on `cdn.biletinial.com`), so it is not used. robots.txt only disallows `/tr-tr/WebLogin` and `/*/kino/`; the
paths used here (`/tr-tr/tiyatro`, `/tr-tr/sinema`, `/tr-tr/mekan/`, `/List/GetMoreItems`, `/dynamic/get_seances`) are not disallowed.

## Caveats

- The cinema price is the cheapest ticket of a film at a cinema, not Tam/Öğrenci by format. Per-ticket-type prices only appear after the
  seat-selection step, which is Turnstile-protected and is not scraped.
- Film titles in product names change weekly, so the cinema series is a panel of film-cinema pairs, not a fixed basket. Paribu Cineverse
  would give fixed per-cinema Tam/Öğrenci prices, but its robots.txt disallows the ticket-price page, so it is not scraped.
- A cinema page lists only films currently on sale there; cinemas with no film showing today or tomorrow are missed.
