# Inflation Study Data

Price scrapers and raw price data for the Inflation Study project: technology retailers and telecom/streaming services (TÜİK 08).

The Svelte dashboard, Falcon API and SQLite serving layer live in the sibling `inflationstudymirror-web` repository.

## Repository structure

```text
InflationItems/
  Codes/
    08_Communication/           # Beymen, BeymenTech, DR, Huawei, PozitifTeknoloji,
                                # Samsung, VatanComputer, Telecom
  Datas/
    04_Housing/Emlakjet/        # old rental CSVs; the Emlakjet scraper was removed on 2026-10-18
    08_Communication/<Source>/  # daily price CSVs per retailer/operator/service
.github/workflows/              # scheduled jobs for every scraper
deploy/scraper-server/          # cron setup for the 08_Communication server
docs/                           # scraping wiki, tool registry, telecom recon
SCRAPER_TIMETABLE.md            # daily schedule
```

## Install

```bash
uv sync
```

or

```bash
python -m pip install -r requirements.txt
```

Chrome is needed for the browser-backed scrapers (Beymen fallback, BeymenTech, TurkNet, tabii).

## Run scrapers

```bash
python InflationItems/Codes/08_Communication/BeymenTech/scraper.py
python InflationItems/Codes/08_Communication/Samsung/scripts/main.py
python InflationItems/Codes/08_Communication/Telecom/scraper.py
```

Every scraper is listed with its script and output in `SCRAPER_TIMETABLE.md`; each 08 source has its own README under `InflationItems/Codes/08_Communication/`.

Before touching a protected or browser-backed scraper, read `docs/scraping-wiki/README.md`. Start with bounded options and inspect the generated CSV/checkpoint outputs.

## Automation

- GitHub Actions: `beymen.yml` (BeymenTech), daily, committing only its data path.
- GitHub Actions: `scraper_<name>.yml` for the other ten 08_Communication scrapers, via `_communication_scraper.yml`.
- Self-hosted cron server: the same ten scrapers, see `deploy/scraper-server/README.md`.

## Testing policy

Scrapers are verified by bounded live runs and inspection of their real outputs. Do not add mock/synthetic scraper tests.
