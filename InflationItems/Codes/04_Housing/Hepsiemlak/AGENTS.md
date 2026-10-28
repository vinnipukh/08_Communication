# AGENTS.md — Hepsiemlak scraper

Instructions for coding agents (Antigravity, Codex, Cursor, Claude Code, …) helping one of the four people
who run this scraper. Read this file, `README.md` in this folder, and `docs/TECH-STACK-SEARCH.md` §3.4
before changing anything. The repository-wide rules in the root `AGENTS.md` and
`InflationItems/Codes/AGENTS.md` also apply (wiki reading, no mock tests, no machine paths in commits).

## How it fits together

| File | Role |
|---|---|
| `hepsiemlak_<name>.py` | One per person (zelal, dani, neslihan, ekin). Calls `launcher.start("<name>")`. Run from an IDE. |
| `launcher.py` | Starts `scraper.py --shard <name>` as a hidden background process with the same interpreter; installs `cloakbrowser` if missing; pid guard; auto `--resume`; refuses to redo a finished day. |
| `scraper.py` | The crawler: CloakBrowser (patched Chromium) via `launch_async`, one session by default. |
| `shards.json` | Which provinces belong to which person. Balanced by listing count. Shared by all four. |
| `checkpoints/` | Gitignored: logs, pid files, progress JSON, `blocked-<status>.html` (first block page). |

Inside `scraper.py`:

- Routes: `/<province>-kiralik?page=N` lists one province's residential rentals, 24 `li.listingCard` per
  page, server-rendered. A province above `SPLIT_PAGES` (60) pages is split into the `/<district>-kiralik`
  links found on its first page (`SCOPE_JS`).
- `EXTRACT_JS` reads each card (id, link, price, date, location, spec list); `parse_card` turns it into a CSV
  row. These two are what break when the site changes its markup.
- `Session.fetch` loads a page; a Cloudflare "Just a moment..." page (served as HTTP 429) is waited on for
  45 s, because a real browser usually solves it in place. Persistent 429 → browser restart with 30–600 s
  backoffs → `Blocked` → the session retires and the run ends as incomplete (the launcher resumes it on the
  next Run).
- `Crawler` holds the route queue, de-duplicates by `ilanId`, writes the CSV, saves the checkpoint
  (`done`, `progress` = last finished page per unfinished route, `pages` = that route's page count, `queue`).
  Past the last page the site does not return an empty page, it repeats listings: a resumed route stops at
  its saved page count, or, for a checkpoint without `pages`, at the first page with no new `ilanId`.

## Site facts (2026-10-23/24, verify before relying on them)

- Protection is Cloudflare. The limiting factor is **requests per IP**, not browser fingerprint: Camoufox,
  invisible_playwright and CloakBrowser all loaded the pages and all got 429 once the IP went over the
  limit; curl_cffi and the JSON API (`/api/realty-list/...`) hit it after ~10 requests.
- One session with a 2–4 s pause ran ~100 pages before a long block on 2026-10-23; five sessions on one IP
  were blocked within ~1.5 min. Short single challenges clear by themselves.
- The site has no page cap; İstanbul ≈ 487 pages, Ankara ≈ 479.

## Rules

1. **Personal-machine problems** (Python version, pip, IDE interpreter, antivirus, sleep settings): fix on
   that machine, do not commit anything for them.
2. **Code changes** are committed and pushed directly to `master`. Do not create branches or pull requests.
   Run `git pull --rebase` right before committing and pushing so four people's agents editing `scraper.py`
   do not overwrite each other; the commit message says what broke, what changed and the live test result.
3. **Do not work around the rate limit.** Do not lower `--delay-min`/`--delay-max` defaults, add parallel
   sessions on one IP, add CAPTCHA solvers, rotate fingerprints or add proxies without the repository owner
   asking for it. If the log shows 429/`retired`, the answer is to wait and run again, not a code change.
4. **Keep shared contracts stable:** the CSV columns (`COLUMNS`) and their meaning, output file names,
   `shards.json` (only the owner rebalances it, for all four at once), and the other people's files.
5. **Never commit** `checkpoints/`, logs, pid files, cookies, browser profiles, test CSVs, proxy lists or
   absolute paths/usernames. The only data file a person commits is their own
   `InflationItems/Datas/04_Housing/Hepsiemlak/YYYY-MM-DD_<name>.csv`.
6. **Update the docs** in the same change: `README.md` here for user-visible behaviour,
   `docs/TECH-STACK-SEARCH.md` §3.4 for site findings and scraper behaviour.

## Diagnosing

Start from the newest `checkpoints/hepsiemlak_<name>_*.log`, then `checkpoints/YYYY-MM-DD_<name>.json`
(done routes, per-route page progress, queue) and, if present, `checkpoints/blocked-*.html`.

| Symptom | Likely cause | Where to look |
|---|---|---|
| `Timeout ... li.listingCard` on HTTP 200 pages | Card markup/class names changed | Open a listing page, update the selector in `fetch` and `EXTRACT_JS` |
| Rows with empty price/rooms/area, or `could not parse` | Card fields changed | `EXTRACT_JS`, `parse_card` |
| A big province crawled without `split into N districts` | District links changed | `SCOPE_JS` (link pattern `^/[a-z0-9-]+-kiralik$`) |
| `HTTP 429` / `retired` / `Cloudflare challenge ... failed` | Per-IP rate limit | Not a code bug (rule 3) |
| Launcher says `already running` with nothing running | Stale pid that matches a live python process | `launcher._alive`; delete the pid file |
| A console window appears | Child process flags | `launcher._spawn` must keep `CREATE_NO_WINDOW` (not `DETACHED_PROCESS`) |

## Verifying a change

No unit tests, mocks or saved HTML fixtures (repository rule). Run it for real, bounded:

```
python hepsiemlak_<name>.py --max-listings 100 --output test_<name>.csv
```

Wait for the background process to exit, then check the log (no tracebacks, `wrote 100 rows`) and the CSV
(100 rows, the person's first province, no empty price/rooms/area). Delete `test_<name>.csv` from the data
folder and `checkpoints/test_<name>.json` afterwards.
