# RepairLabor — home repair labour prices from Armut (TÜİK 0432015)

Fetches Armut.com's city price pages ("<city> <service> Fiyatları") for 23 home repair / maintenance services
(painter, plumber, electrician, combi boiler service, tiler, parquet, drywall, plasterer, roof repair,
waterproofing, carpenter, PVC windows, glass, locks, kitchen cabinet fitting, general repair, renovation) in
İstanbul, Ankara and İzmir. The service list is `services.json` (Armut service id + label); add or remove
entries there. Other provinces only change the URL, so `--provinces all` takes every province the sitemap lists.

```bash
python InflationItems/Codes/04_Housing/RepairLabor/scraper.py
python InflationItems/Codes/04_Housing/RepairLabor/scraper.py --provinces 6 --services 193 66   # bounded run
python InflationItems/Codes/04_Housing/RepairLabor/scraper.py --provinces all                   # ~1,600 pages
python InflationItems/Codes/04_Housing/RepairLabor/scraper.py --backfill                        # + 12-month history
```

## Backfill

`--backfill` uses the same page fetches (no extra requests) and also writes one CSV per past day that the pages'
12-month history covers. Run on 2026-10-28 it wrote 365 files, `armut_2025-10-01.csv` .. `armut_2026-09-30.csv`. 1–27
October 2026 have no files: the month is not in the history yet, and the daily series starts with the
2026-10-28 run.

- Every day of a month has that month's quote mean (`price` = `price_avg`, month in `avg_month`) plus
  `month_min`, `month_max` and `month_quote_count`. The values are monthly; the day files only repeat them.
- `notes` starts with `backfill:`. `price_min`, `price_max`, `quote_count`, `pro_count`, `rating_avg` and
  `rating_count` are empty, because the page shows them only for today.
- A service × city with no quotes in a month has no row in that month's files, so a day has 65–69 rows
  instead of 69.
- An existing daily CSV is never overwritten, so a real snapshot always wins. To redo a backfilled day, delete
  its file and run again.
- The 365 files take ~7 MB.

- Requests: sitemap index + `price-arealevel1-*` sitemap(s) + one page per service × province; ~71 for the
  default scope, 1 s apart. Default run 83 s (measured 2026-10-28); `--provinces all` ~40 min.
- Output: `InflationItems/Datas/04_Housing/Armut/armut_YYYY-MM-DD.csv` (upstream layout: one CSV per store and
  day, store = Armut), one row per service × province. `--output <path>` writes that CSV instead of the day
  file (test runs).
- `price` = mean of the newest month's quotes in that city (`price_avg`, month in `avg_month`, normally the
  previous calendar month). When a page has no monthly data, the midpoint of `price_min`–`price_max`; `notes`
  says which was used.
- `price_min` / `price_max` = the "Ortalama Fiyat" range shown on the page. For low-volume services the same
  range appears in several cities, so it looks like a national fallback rather than city data.
- The quote mean is noisy: single quotes of 1–10 million TL occur (`month_max`), and some city/months have 1–10
  quotes (`month_quote_count`). Use the stored min/max/counts to filter or weight; do not read `price` alone.
- Columns: `product_name, price, category_number, sub_category_number, service, service_id, province, plate,
  price_min, price_max, price_avg, avg_month, month_min, month_max, month_quote_count, quote_count, pro_count,
  rating_avg, rating_count, notes, source_url, collected_at`.
- A page that fails is logged and skipped; the rest is written and the run exits with status 1. If every page
  fails no CSV is written. A service with no page in a province is a warning (not a failure).

## Source

- Page URLs: `https://armut.com/sitemap.xml` → `sitemap/price-arealevel1-<n>.xml` →
  `https://armut.com/fiyatlari/{city}-{service-slug}_{serviceId}_{plate}`.
- Data: `<script id="__NEXT_DATA__">` → `props.pageProps.data.pricePageData` (`minPrice`, `maxPrice`,
  `quoteCount`, `proCount`, `ratingAvg`, `ratingCount`, `areaLevel1Name`, `monthlyPrices` = last 12 complete
  months of `{month, avgPrice, minPrice, maxPrice, quoteCount}`) and `pricePageInfo` (`serviceId`,
  `areaLevel1Id`), which is checked against the requested service and plate.
- CloudFront, plain HTTP 200 to curl_cffi, no challenge (2026-10-28).

## Troubleshooting

- `no price-arealevel1 sitemap in the sitemap index` — Armut renamed its sitemaps; check `sitemap.xml`.
- `no page for <service> in province NN` — Armut has no city page for that service there; pick another
  service id from the sitemap if it matters.
- `__NEXT_DATA__ not found` / `page is for another service / area` — the page layout or the URL changed.
- `service ids not in services.json` — `--services` takes only ids listed in `services.json`.
- Needs `curl_cffi` (`requirements.txt`).
- Git Bash on Windows garbles Turkish output; set `PYTHONIOENCODING=utf-8`.

## Notes

- Schedule: none yet (no cron or Actions job). Monthly is enough; the data moves once a month.
- No history beyond the 12 months in `monthlyPrices` (checked 2026-10-28).
- The newest month can lag when a month has no quotes (İzmir lock change showed 2026-08 on 2026-10-28). A
  consumer should weight by `month_quote_count` or prefer high-volume services.
- Reusable: the `page_urls()` pattern (sitemap → id-keyed URL map) for any site with id-suffixed URLs; no
  city-slug table is needed.
- Open: the service choice in `services.json` is a judgement call; review it against the TÜİK item definition
  if the index team has one.
