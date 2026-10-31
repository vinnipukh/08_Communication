# VetArt veterinary fee scraper (TÜİK 0945001)

Source for CPI item **0945001 "Veterinary services"**: the fee page of the VetArt clinic
(`https://vetart.com.tr/veteriner-ucretleri/`). The page is a static WordPress page that repeats a
short extract of the **İstanbul Chamber of Veterinary Surgeons minimum fee tariff** (2026) in two
HTML tables: examination (Kedi / Köpek / Kafes Kuşlar) and vaccines plus antiparasitic treatment
(Kedi / Köpek). These are chamber minimum fees, not VetArt's own prices, so the data is not
independent of the İstanbul tariff. The page links to the full tariff PDF on `www.ivho.org.tr`,
which cannot be fetched with TLS verification (the server sends no intermediate certificate, so
curl fails with error 60 `unable to get local issuer certificate`), so VetArt is the only reachable copy of an İstanbul tariff extract.

Output: `InflationItems/Datas/09_Recreation/VetArt/vetart_YYYY-MM-DD.csv`

## Run

```bash
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/VetArt/vetart_scraper.py
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/VetArt/vetart_scraper.py --date 2026-10-31
```

Run time about 2 s: the homepage and the price page (two requests, 1.5 s apart), `curl_cffi`
`impersonate="chrome"`, no browser.

## Parsing

Every `<table>` on the page is read; the section is the last heading before it (the "(Alt Sınır) 2026"
suffix is dropped). The first row gives the animal columns, each later row is a service. An empty cell
(the page leaves it empty when a vaccine is for one species only) is skipped. Prices are `₺1750` or
`₺1.750` (dot = thousands separator). The tariff period is read from "Ocak 2026 itibari" (`2026/1`).
No CSV is written when no rows are parsed. 21 rows on 2026-10-31.

## CSV

`utf-8-sig`; first columns `product_name, price, category_number, sub_category_number`.

| Column | Content |
|---|---|
| `product_name` | `VetArt - <section> - <service> - <animal>` |
| `price` | TRY, dot decimal, 2 decimals |
| `category_number` / `sub_category_number` | `9` / `0945001` |
| `price_max` | equals `price` (the page has no ranges) |
| `price_text` | the cell as published |
| `animal` | `Kedi`, `Köpek` or `Kafes Kuşlar` (cage birds) |
| `section`, `service` | as published |
| `tariff_period` | `2026/1` |
| `kdv_included` | empty: the page does not say whether VAT is included |
| `source_url` | the price page |

## robots.txt and sitemap

`robots.txt` disallows only `/wp-admin/`; the price page is allowed. `sitemap.xml` (All in One SEO)
only lists posts and pages, no prices, and the price page URL is known, so **the sitemap is not used**.

## Caveats

- The table is a hand-picked extract (2 examination rows, 12 vaccine/parasite rows), not the whole tariff.
- Values change once a year (January); daily CSVs repeat them. The page was edited for 2026, so the
  parser checks the table layout only: a changed layout or new headings change product names.
- The service label "Köpek Karma Aşıları (DHPPİ+L – DHPL – DP)" keeps the en dashes as published.
