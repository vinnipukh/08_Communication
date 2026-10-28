# queue — notes between runs

Each agent that works an item appends a short entry here (newest at the bottom): what it found that the
specs do not say, shared code it created that later items should reuse, problems left open. Keep entries
short; no absolute paths, usernames or cookies.

<!-- Entry format:
## YYYY-MM-DD — <item #> <name>
- ...
-->

## 2026-10-28 — 1 Electricity (EPDK)
- `GetFastAccessList` answers an object; entries are under `model`, not a bare array (spec updated).
  Files per decision: `IsFileType` 1 = decision PDF, 2 = XLSX table. 3 requests per run (page + list + file).
- Since 04.04.2026 AG mesken is split into ≤8 and >8 kWh/gün rows (only tek zamanlı differs; the
  multi-time prices are the same in both). The 2025 XLSX has a different layout; the parser handles only
  the current one and fails loudly otherwise, so history is not backfillable without more code.
- Last-resort tariff: not in this list or file.
- Added `openpyxl` to `requirements.txt`, `pyproject.toml` and `uv.lock`; later XLSX sources can use it.
- Reusable pattern: the `Client` class in `Electricity/scraper.py` (curl_cffi Chrome session, page-first,
  jittered ~1 s delay, `Retry-After`, fail after 3 backoffs) is small enough to copy for items 2–7.
- Git Bash on Windows garbles Turkish characters in Python output; set `PYTHONIOENCODING=utf-8` when reading logs.
- Not done: no schedule (cron/Actions) yet for the 04 utilities scrapers.
