# Scraper Timetable

Daily schedule of all scrapers: GitHub Actions workflows in `.github/workflows/` and the self-hosted cron server.

All times in **Istanbul time (UTC+3)**. Türkiye uses UTC+3 year-round (no daylight saving since 2016).

| Istanbul Time (UTC+3) | UTC  | Scraper        | Workflow File         | Script                                   | Output Data                      |
|-----------------------|------|----------------|-----------------------|------------------------------------------|----------------------------------|
| 13:00                | 10:00 | Beymen         | `beymen.yml`          | `InflationItems/Codes/08_Communication/BeymenTech/scraper.py`             | `InflationItems/Datas/08_Communication/Beymen/ (beymen_tech_*)`              |

## Notes

- All workflows run **daily** (`* * *` in cron) and can also be triggered manually via `workflow_dispatch`.
- All workflows use `ubuntu-latest`, commit output CSVs via the `github-actions[bot]`, and skip commits when there are no changes.

## Self-hosted cron server (08_Communication: tech + telecom)

Six technology-retail scrapers and the four Telecom scrapers run on a separate low-RAM Ubuntu server via cron.
Setup, measured durations and operations: `deploy/scraper-server/README.md`. Jobs share one lock, so they never overlap.

The same ten scrapers also have GitHub Actions workflows (`scraper_<name>.yml`) at the same Istanbul times. Each one
calls `_communication_scraper.yml`. That workflow installs `deploy/scraper-server/requirements.txt`, runs the server's
own `bin/run_scraper.sh <name>` (the same script map and timeouts) with `TZ=Europe/Istanbul`, then commits
`InflationItems/Datas/08_Communication/` even when the run fails, so partial Telecom/Vatan results are kept. It retries
`git pull --rebase` + push because the workflows share one branch. Runner IPs are datacenter IPs. Cloudflare/Akamai
sources (Vatan, TurkNet, the Beymen fallback) may be blocked there when they work from the server. If one keeps
failing, disable only that workflow.

| Istanbul Time (UTC+3) | UTC | Scraper | Workflow / `run_scraper.sh` name | Script | Output Data |
|---|---|---|---|---|---|
| 01:00 | 22:00 | Samsung | `scraper_samsung.yml` / `samsung` | `InflationItems/Codes/08_Communication/Samsung/scripts/main.py` | `InflationItems/Datas/08_Communication/Samsung/*.csv` |
| 01:10 | 22:10 | Huawei | `scraper_huawei.yml` / `huawei` | `InflationItems/Codes/08_Communication/Huawei/huawei_scraper.py` | `InflationItems/Datas/08_Communication/Huawei/*.csv` |
| 01:20 | 22:20 | Pozitif Teknoloji | `scraper_pozitif.yml` / `pozitif` | `InflationItems/Codes/08_Communication/PozitifTeknoloji/pozitifTeknoloji_scraper.py` | `InflationItems/Datas/08_Communication/PozitifTeknoloji/*.csv` |
| 01:30 | 22:30 | D&R | `scraper_dr.yml` / `dr` | `InflationItems/Codes/08_Communication/DR/dr_scraper.py` | `InflationItems/Datas/08_Communication/DR/*.csv` |
| 02:00 | 23:00 | Beymen | `scraper_beymen.yml` / `beymen` | `InflationItems/Codes/08_Communication/Beymen/scraper.py` | `InflationItems/Datas/08_Communication/Beymen/*.csv` |
| 04:00 | 01:00 | Vatan | `scraper_vatan.yml` / `vatan` | `InflationItems/Codes/08_Communication/VatanComputer/vatan_comp.py` | `InflationItems/Datas/08_Communication/VatanComputer/*.csv` |
| 06:00 | 03:00 | Telecom — mobile tariffs (Turkcell, Vodafone, Türk Telekom, NetGSM) | `scraper_telecom.yml` / `telecom` | `InflationItems/Codes/08_Communication/Telecom/scraper.py` | `InflationItems/Datas/08_Communication/<Operator>/*.csv` |
| 07:30 | 04:30 | Telecom — home internet (Superonline, Vodafone, Kablonet, Milleni, TurkNet, Türk Telekom) | `scraper_internet.yml` / `internet` | `InflationItems/Codes/08_Communication/Telecom/internet.py` | `InflationItems/Datas/08_Communication/<Provider>/*_internet_*.csv` |
| 08:45 | 05:45 | Telecom — streaming subscriptions (12 services) | `scraper_streaming.yml` / `streaming` | `InflationItems/Codes/08_Communication/Telecom/streaming.py` | `InflationItems/Datas/08_Communication/<Service>/*.csv` |
| 09:00 | 06:00 | Telecom — ICT equipment repair prices (Apple, Samsung, Huawei, GSM İletişim) | `scraper_repair.yml` / `repair` | `InflationItems/Codes/08_Communication/Telecom/repair.py` | `InflationItems/Datas/08_Communication/<Source>/*_repair_*.csv` |

Beymen is also scraped by the `beymen.yml` workflow (`InflationItems/Codes/08_Communication/BeymenTech/scraper.py`,
same technology category) into `InflationItems/Datas/08_Communication/Beymen/ (beymen_tech_*)`; the server copy writes a
separate dataset.
