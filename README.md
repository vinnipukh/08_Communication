# Inflation Study Data

Price scrapers and raw price data for the Inflation Study project: technology retailers and telecom/streaming services (TÜİK 08).

The Svelte dashboard, Falcon API and SQLite serving layer live in the sibling `inflationstudymirror-web` repository.

## Repository structure

```text
InflationItems/
  Codes/
    08_Communication/           # Beymen, DR, Huawei, PozitifTeknoloji,
                                # Samsung, VatanComputer, Telecom
  Datas/
    04_Housing/Emlakjet/        # rental CSVs; scraper rewritten 2026-10-23 (Codes/04_Housing/Emlakjet)
    08_Communication/<Source>/  # daily price CSVs per retailer/operator/service
.github/workflows/              # Emlakjet schedule + manual runs of the server scrapers
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

Chrome is needed for the browser-backed scrapers (Beymen fallback, TurkNet, tabii).

## Run scrapers

```bash
python InflationItems/Codes/08_Communication/Beymen/scraper.py
python InflationItems/Codes/08_Communication/Samsung/scripts/main.py
python InflationItems/Codes/08_Communication/Telecom/scraper.py
```

Every scraper is listed with its script and output in `SCRAPER_TIMETABLE.md`; each 08 source has its own README under `InflationItems/Codes/08_Communication/`.

Before touching a protected or browser-backed scraper, read `docs/scraping-wiki/README.md`. Start with bounded options and inspect the generated CSV/checkpoint outputs.

## Automation

- Self-hosted cron server: the ten 08_Communication scrapers, daily; it pushes their CSVs to `main` itself
  (`deploy/scraper-server/bin/push_data.sh`), see `deploy/scraper-server/README.md`.
- GitHub Actions: `scraper_<name>.yml` for the same ten, manual runs only (via `_communication_scraper.yml`).
- GitHub Actions: `scraper_emlakjet.yml`, daily.

## Testing policy

Scrapers are verified by bounded live runs and inspection of their real outputs. Do not add mock/synthetic scraper tests.
