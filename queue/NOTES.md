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

## 2026-10-28 — 2 Natural gas (İGDAŞ, Başkentgaz, İzmirgaz)
- `www.igdas.istanbul` drops curl_cffi connections; use `igdas.istanbul`. İGDAŞ has no tax footnote; prices
  are ÖTV-incl / VAT-excl by arithmetic (spec updated). İGDAŞ's fee page has no year/VAT, so fees come from
  İzmirgaz; Başkentgaz grosses up connection fees by VAT but not deposits. All three fees matched.
- İzmirgaz omits its intermediate certificate: `izmirgaz_client()` in `NaturalGas/scraper.py` retries with the
  AIA issuer added to the certifi bundle (verification stays on). Copy it for any other host with this problem.
- Python's `"EKİM".lower()` != `"ekim"` (dotted İ). Use the `tr_month()` helper from `NaturalGas/scraper.py`
  for Turkish month names (Electricity's `effective_date()` would hit it only with upper-case names like
  "EKİM"; its sheet uses title case, and its fallback catches a miss). Also reusable there: `tr_number()` for "14,468019" / "₺9.679,20" / "8.066".
- Added `pypdf` (text PDFs) and `certifi` to `requirements.txt`, `pyproject.toml`, `uv.lock`.
- Measured ~7 s for ~11 requests; one bounded run took 36 s (a slow first connection, not reproduced).
- Open: İzmirgaz's intermediate URL is a constant; a CA change needs an update. Başkentgaz split months
  (e.g. April 2026) pick the later PDF only. No schedule yet; monthly is enough (İGDAŞ answers future months).
