# Nezih Scraper

Daily books and stationery scraper for `https://www.nezih.com.tr/`.

Scope:
- collects the assigned `Kitap` and `Kirtasiye` categories
- reads Nezih's embedded `PRODUCT_DATA` payloads instead of scraping visual text
- paginates through `?pg=N` listing pages
- writes daily CSVs to `InflationItems/Datas/09_Recreation/Nezih/`
- since 2026-10-31 the CSV starts with the four required columns `product_name, price,
  category_number, sub_category_number`, followed by the original Nezih columns. The TÜİK item code
  comes from the site category path (`_coicop_code`); bags, bottles, calculators and musical
  instruments are dropped as outside group 09. Mapping table: `docs/site-analysis/recreation/README.md` §11.1.

Run:

```bash
uv run python InflationItems/Codes/09_Recreation/Nezih/nezih_scraper.py
```

From inside the scraper directory, this also works:

```bash
cd InflationItems/Codes/09_Recreation/Nezih
uv run python -m scripts.run_scraper
```

Useful smoke-test flags:

```bash
uv run python InflationItems/Codes/09_Recreation/Nezih/nezih_scraper.py --page-limit 1 --output /tmp/nezih_smoke.csv
uv run python InflationItems/Codes/09_Recreation/Nezih/nezih_scraper.py --only kitap --page-limit 2
```
