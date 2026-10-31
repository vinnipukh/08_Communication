# KidZania Istanbul (kidzania.com.tr -> istanbul.kidzania.com)

TUIK group 09, item 0946103 (Recreation and hobby services): KidZania entry tickets.

## Source and endpoints
Homepage session (`https://www.kidzania.com.tr/` redirects to `https://istanbul.kidzania.com/`):
1. Homepage "Giris Ucretleri" table (`section#opening-prices table`): entry and experience packages. Only this
   table is read; the holiday promotion text and opening-hours blocks next to it are ignored.
2. Ticket shop category "Bireysel Giris" (id 1): `POST /online-ticket-select-date` with
   `{"category_id": 1, "date": "YYYY-MM-DD"}` and the CSRF token from the homepage (same call the purchase
   widget makes; nothing is added to a cart). Returns the 4-14 and 2-3 age tickets and the 3-month/annual cards.

A table row whose price equals a ticket-shop price (the general entry) is not written twice.

## Mapping rule
All rows -> `0946103`. Product names: `KidZania Istanbul - Bireysel Giris - <ticket>` (shop) and
`KidZania Istanbul - <row name>` (table). Extra columns: list_price, ticket_name, source, ticket_id, product_url.

## Run
```
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/KidZania/kidzania_scraper.py
```
Bounded run: `--table-only` (skips the ticket-shop call). `--date YYYY-MM-DD` sets the output date (the shop date
is always today unless a past/future date is given). Exits 1 and writes nothing when no prices are found.
Output: `InflationItems/Datas/09_Recreation/KidZania/kidzania_YYYY-MM-DD.csv`.
Full run: about 7 s, 6 rows on 2026-10-31 (all 0946103).

## Sitemap verdict
Not used. robots.txt allows `/`; a plain `sitemap.xml` request returned a Cloudflare challenge page, and the
prices are on the homepage anyway.

## Caveats
- Ticket prices may vary by date (weekend/holiday); the shop call uses the run date.
- Cloudflare protects the host; curl_cffi Chrome impersonation with homepage-first passes at the current
  request volume (2 requests).
