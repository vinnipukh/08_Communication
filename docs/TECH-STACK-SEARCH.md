<!-- maintained-by: agent session (user-requested tech-stack search registry) -->

# Tech Stack Search

Living registry of the **tech-stack search** for building, maintaining, and
modernizing the project's scrapers. Every site the user sends for review is
logged here, and every discovered tool gets a verified entry (metadata pulled
from GitHub API, not vibes). The registry feeds the **skill registry**
section at the bottom, which defines what the coding agent should be able to
do.

Scope: the Emlakjet rental scraper (`InflationItems/Codes/04_Housing/`) and the
technology/telecom scrapers (`InflationItems/Codes/08_Communication/`). Tool
evaluations from 2026-08 mention "sarı site", a rental source that has since
been removed from this repository; they are kept for the tool verdicts.

## Doc map

| Doc | Purpose |
|---|---|
| `docs/TECH-STACK-SEARCH.md` (this file) | Tool/skill catalog with verified metadata + dated status entries |
| `docs/scraping-wiki/` | Tested-technique knowledge base (anti-bot truth) |

---

## 1. Search Log (sites reviewed)

| Date | Site | Type | Verdict | Entry |
|---|---|---|---|---|
| 2026-08-15 | `ScrapeGraphAI/Scrapegraph-ai` @ 27d9d28 | LLM scraping library | No skills; one design pattern worth stealing (self-healing repair loop) | §2.1 |
| 2026-08-15 | `CloakHQ/CloakBrowser` @ main | Stealth Chromium driver | No skills; high-value reference implementation for human-motion emulation + driver candidate | §2.4 |
| 2026-08-15 | `lorien/awesome-web-scraping` @ master (+ linked `HeadlessBrowsers` catalog) | Curated directory | No skills; discovery map → 8 shortlist tools + reference links | §2.2, §2.3 |
| 2026-08-15 | `VoltAgent/awesome-agent-skills` @ main | **Agent-skill list (1,497+ skills)** | ✅ Real SKILL.md skills found — shortlist in §2.6 | §2.6 |
| 2026-08-15 | `ComposioHQ/awesome-claude-skills` @ master | Agent-skill list (★72.5k, 503-line README + in-repo skill dirs) | ✅ Skill finds (incl. 4 novel) — additions in §2.6 | §2.6 |
| 2026-08-15 | Scrapfly (scrapfly.io docs + `github.com/scrapfly` org, 29 repos) | Scraping API platform + OSS repos | ⭐ Open-source gems (scrapfly-scrapers, Antibot-Detector) — skills repo is platform-bound | §2.7 |
| 2026-10-08 | `turkcell.com.tr`, `vodafone.com.tr`, `bireysel.turktelekom.com.tr`, `netgsm.com.tr` | Mobile operator tariff pages | ✅ All plain HTTP (`curl_cffi` chrome124): Turkcell `__NEXT_DATA__`, Vodafone RSC payload + add-on cards, Türk Telekom sitemap→detail JSON-LD (paging XHR is robots-disallowed), NetGSM static cards | `docs/site-analysis/telecom/NOTES.md` |
| 2026-10-08 | `superonline.net`, `vodafone.com.tr/net`, `turksatkablo.com.tr`, `milleni.com.tr`, `turk.net`, `bireysel.turktelekom.com.tr/evde-internet` | Home internet price pages | ✅ Plain HTTP except TurkNet (Cloudflare: curl_cffi 0.15 → 403; one headless undetected-Chrome visit → `__cf_bm` + UA → curl_cffi 200). Kablonet omits its intermediate cert → AIA-completed CA bundle, verify on | `docs/site-analysis/telecom/NOTES.md` |
| 2026-10-09 | Netflix, Disney+, HBO Max, Amazon Prime, Apple TV+, YouTube Premium, Spotify, MUBI, TV+, Tivibu, TOD, GAİN, Exxen, Hepsiburada Premium, tabii, Paramount+ | Streaming subscription price pages | ✅ 12 services plain HTTP (one page each). ❌ Exxen / Hepsiburada Premium (price only after sign-up), tabii Premium (client-side from an authenticated call), Paramount+ (not sold in Türkiye) | `docs/site-analysis/telecom/NOTES.md` |
| 2026-10-09 | `support.apple.com` pricing API, `samsung.com/tr` repair fees, `consumer.huawei.com` spare-part API, `egemek.com.tr`, `gsmiletisim.com` | ICT equipment repair prices | ✅ All plain HTTP: Apple `ols/api/pricing/.../pricing-estimate` JSON (parent tag per device family), Samsung static tables, Huawei `queryNewCommodityList` tree + `cspm/queryMaterialPrice` POST (`timeZone: GMT+03:00`, lv6 SKU), Egemek table, GSM İletişim 112 category pages | `docs/site-analysis/telecom/NOTES.md` |
| 2026-08-17 | `www.emlakjet.com` | Residential rental listing site | ✅ Browser recon: `/kiralik-konut`, 30 cards/page, 50-page geographic-scope cap; province/district/neighborhood routes support coverage without the robots-disallowed page-size filter | §2.9 |
| 2026-08-15 | `ComposioHQ/awesome-claude-skills` @ master | Agent-skill list (★72.5k) | ✅ +8 finds (Chrome Relay, Full-Page Screenshot, article-extractor, TDD, recursive-research, CSV summarizer, Skill Creator/Seekers, LangSmith) | §2.6 |
| 2026-08-15 | `D4Vinci/Scrapling` @ main | Full scraping framework (★74k) | ⭐ Parallel track vs CloakBrowser — adaptive selectors, spiders, official skill | §2.1, §3.1 |
| 2026-08-15 | `autoscrape-labs/pydoll` @ main | CDP browser library (★7k) | ⚠️ Wiki-tested 0% vs strict Turnstile — not in driver benchmark | §2.4 |
| 2026-08-15 | `mcpservers.org/agent-skills/category/web-scraping` | Skill directory | ✅ browser-act (★5.4k) install candidate; antibrow, defuddle, just-scrape, deep-research | §2.6 |
| 2026-08-15 | Ad-hoc evals (jsoup, Buster, ai-captcha-bypass, luminati, Pr0t0ns ×2, NopeCHA, solvecaptcha-python, tjaycodes4you org, OpenAI crawler docs) | Repos/docs | All logged in §2.2–§2.5, §2.8 | — |

---

## 2. Tool Catalog (verified 2026-08-15 via GitHub API)

Legend: ★ = stars · 🪪 = license · ⚙️ = language · 🕒 = last update ·
**verdict** = fit for this project. Skill refs point at §4.

### 2.1 Scraper frameworks & LLM scraping

| Tool | Verdict |
|---|---|
| **crawl4ai** (`unclecode/crawl4ai`) — ★78,227 · Apache-2.0 · Python · 🕒 active | **Not needed** — LLM-friendly crawler framework; huge but browser/JS oriented around content extraction, not protected-site stealth. Monitor only. |
| **Crawlee** (`apify/crawlee-python`) — ★9,432 · Apache-2.0 · Python · 🕒 active | **Pattern source** — production patterns for session pools, per-request retries, resume. Works with Parsel/BS4. Steal concepts for resume-crash-recovery + cookie pool. |
| **Botasaurus** (`omkarcloud/botasaurus`) — ★5,668 · MIT · Python · 🕒 active | **Candidate** — "all-in-one framework to build undefeatable scrapers"; `bypass_cloudflare=True` was **wiki-validated against Indeed's Turnstile**. Evaluate vs rayobrowse flow. |
| **ScrapeGraphAI** (`ScrapeGraphAI/Scrapegraph-ai` @ 27d9d28) — LLM graph pipelines | **Pattern only** — self-healing scraper generation: `generate_scraper_node` + `code_error_correction.py` = 4-stage LLM repair loop (syntax → execution → schema validation → semantic diff vs reference). Use for fragile `#searchResultsTable` selectors. **Never its fetch path** (plain requests + free proxies). |
| **Scrapling** (`D4Vinci/Scrapling`) — ★74,147 · BSD-3-Clause · Python · 🕒 active · ⭐ **major upgrade from wiki candidate status** | **Full framework, now a first-class blueprint candidate.** Components: `StealthyFetcher` (Camoufox-based, **headless Turnstile bypass "through automation, no solvers/APIs"**), `DynamicFetcher` (Playwright), `Fetcher/AsyncFetcher` (static), **adaptive parsing** (`p.css('.product', adaptive=True)` — tracks/relocates elements when the site changes; deterministic alternative to our LLM-self-healing idea), **Spiders** (concurrent multi-session crawls, **pause/resume**, automatic proxy rotation, real-time stats), CLI, Docker, **MCP server**, and an **official installable agent skill** (`agent-skill/Scrapling-Skill/SKILL.md`, v0.4.14, references for fetching/adaptive/spiders) |
| **trafilatura** (`adbar/trafilatura`) — ★6,644 · Apache-2.0 · Python | **Edge utility only** — detail-page description normalization + sitemap discovery. Never its downloader against sarı site. |
| **pipet** (`bjesus/pipet`) — ★4,768 · MIT · Go · 🕒 active | **Agent utility candidate** — curl-pipe + CSS selector CLI (HTML/JSON/JS modes, templates). Quick extraction on non-protected targets; useless on sarı site-class protection. |

### 2.2 Parsing & data normalization

| Tool | Verdict |
|---|---|
| **price-parser** (`scrapinghub/price-parser`) — ★346 · BSD-3-Clause · Python · 🕒 active | ⭐ **Direct fix for the price-drift pain point** (`4.500 TL` vs `16000.0`). Parses amount + currency from raw text. → skill #6. |
| **dateparser** (`scrapinghub/dateparser`) — ★2,851 · BSD-3-Clause · Python · 🕒 active | ⭐ **Parses Turkish dates** (`10 Ağustos 2026`) — i18n human-readable dates. → skill #4/#6. |
| **parsel** (`scrapy/parsel`) — ★1,349 · BSD-3-Clause · Python | XPath + CSS selector layer (Scrapy's engine) — drop-in alternative to hand-rolled BS4 selector code. → skill #4. |
| **selectolax** (`rushter/selectolax`) — ★1,664 · MIT · Cython · 🕒 active | Fast HTML5 parser (Modest/Lexbor engines) — speed class of scrapling's 1735x claim; keep as parsing-speed option. → skill #4. |
| **chompjs** (`Nykakin/chompjs`) — ★222 · MIT · C | Parse JS objects embedded in `<script>` tags — useful when site inlines JSON state. → skill #4. |
| **BeautifulSoup** (current) | Keep for now; consider parsel/selectolax only if parse speed matters (it doesn't at ~1–3k rows/city/day). |
| **jsoup** (`jhy/jsoup`) — ★11,387 · MIT · Java · 🕒 active | **Not adopted — language mismatch** (Java; stack is Python). Reference value only: (1) gold-standard selector-API design to cite in skill #4; (2) WHATWG-spec compliance — parses to browser-grade DOM; lesson: BS4's default `html.parser` is not fully spec-compliant, `html5lib` backend or parsel/selectolax gets closer. ⚠️ Never its built-in `Jsoup.connect()` fetch against sarı site (plain HTTP, no fingerprint/cookies). |

### 2.3 Anti-bot & captcha services

| Tool | Verdict |
|---|---|
| **unicaps** (`sergey-scat/unicaps`) — ★234 · Apache-2.0 · Python | ⚠️ **Corrected 2026-08-16 (research report): NO Turnstile support** — matrix lists image/text, reCAPTCHA v2/v3, FunCaptcha, KeyCAPTCHA, GeeTest v3/v4, hCaptcha, Capy. Fine for those types only; **do not use as the Turnstile abstraction**. → skill #7 (non-Turnstile types only). |
| **captcha_solver** (`lorien/captcha_solver`) — API to solving services | Same category as unicaps; author is the awesome-list maintainer. Pick one (unicaps, Apache, more maintained). |
| **solvecaptcha-python** (`solvercaptcha/solvecaptcha-python`) — ★161 · MIT | ⚠️ **Vendor correction (research report): this is the solvecaptcha.com client — NOT the official 2Captcha client.** Official is `2captcha/2captcha-python`. Does support Turnstile + proxies; correct naming before any integration code |
| **cloudscraper** (`venomous/cloudscraper`) | ⚠️ **Caution — do not adopt.** JS-challenge solver, obsolete against modern Cloudflare (Turnstile/`cf_clearance`). Wiki documents this class of failure. |
| **2captcha.com** (listed in awesome README) | Service, not a tool — budget consideration only. |
| **Buster** (`dessant/buster`) — ★9,256 · GPL-3.0 · JS · 🕒 active (2026-08-14) | **Not applicable.** Solves **reCAPTCHA v2 audio only** via speech recognition; our blockers are Turnstile (explicit-render, login) + PerimeterX (behavioral) — neither has that modality. Human-in-the-loop by design; GPL-3.0 license friction. Keep the *technique* (audio+speech-to-text) as a last-resort note in skill #7's toolbox. |
| **NopeCHA** (`NopeCHALLC/nopecha-extension`) — ★10,960 · MIT (extension) · 🕒 active (0.6.1, 2026-06) | ⭐ **Turnstile + PerimeterX support verified as vendor capability** (free 100 req/day/IP; paid from US$4.99/mo for 2,000 solves/day). ⚠️ **Corrections 2026-08-16**: (1) May 2026 issue #278 — PX stuck after press-and-hold ⇒ "supports PX" ≠ deterministic on every variant; (2) the 90k/$1 + "2captcha lacks Turnstile" comparison table is **stale (Jan 2025)** — do not use for 2026 selection; (3) repo is docs-only. Keep as optional login fallback, not a production dependency |
| **ai-captcha-bypass** (`aydinnyunus/ai-captcha-bypass`) — ★1,187 · license NOASSERTION (custom/unclear) · Python · 🕒 active | **Not applicable directly; technique worth noting.** Multimodal-LLM (GPT-4o/Gemini) vision solving via Selenium+Firefox for text/reCAPTCHA-v2-image/puzzle/audio challenges (tested on 2captcha demo pages). **No Turnstile/PerimeterX support** (our blockers); demo/benchmark-grade (small codebase, GIF recordings), not production; Selenium ≠ our Playwright/CDP stack; license unclear. Skill #7 toolbox note: LLM-vision solving is a legitimate last-resort technique family for image challenges; benchmark-against-2captcha-demo pattern is a good harness idea. |
| **perimeterx-captcha-solver** (`luminati-io/perimeterx-captcha-solver`) — ★4 · no license · no code (README + image only) · 2026-04 | **Marketing-only repo** for Bright Data's paid solver — BUT contains one valuable pattern: the **captcha-detection selector table** (see below). Take the *pattern*, not the *values* (unverified/marketing-grade). |

### 2.4 Browser drivers (driver-lifecycle matrix)

| Driver | Type | License/binary | Verdict |
|---|---|---|---|
| **rayobrowse** (legacy, v0.2.1) | Patched Chromium daemon (Docker, CDP) | **Closed-source beta** | Legacy path — kept for compat; superseded by the selenium engine below |
| **engine_selenium.py** (in-repo, 2026-08-16) | **undetected-chromedriver + persistent `--user-data-dir` profile** + manual solve-retry loop + adaptive pacing — the friend-tactics pattern (urazkagangunes IstanbulAvrupa, 3 months daily, 24.5k rows/day) | OSS deps (selenium, undetected-chromedriver) | ⭐ **New primary driver path.** The profile carries `cf_clearance`/`_px3` across daily runs = cookie-saving trust strategy; day-1 manual solve, then warm sessions. No live test yet (site cooldown — IP flagged after today's tests); offline-verified (parse/extract/URL/split) |
| **CloakBrowser** (`CloakHQ/CloakBrowser`) — ❌ **FAILED G0 TEST 2026-08-16 — NOT ADOPTED** | Stealth Chromium fork (ungoogled base), 71 claimed C++ patches | MIT wrapper, **proprietary binary** (BINARY-LICENSE v1.3) | **G0 result (cold session, sarı site)**: every launch hit the `/cs/tloading` enterprise-Turnstile interstitial; human checkbox click failed with **"Doğrulama Başarısız"** on BOTH the forced-render flow AND the zero-manipulation vanilla flow; listing nav then redirected to login. **Version correction**: the keyless free binary is **Chromium v146** (NOT v150 — corrects the research report); v150 needs a GitHub-sign-in key (1 concurrent session). Vendor claims (71 patches/30/30/0.9 reCAPTCHA) remain unproven and are now suspect. **Verdict: replaced by nothing — keep rayobrowse; next candidate = Scrapling StealthyFetcher. ⚠️ Open question: is the failure browser-identity or IP-reputation? (uncontrolled control test — vanilla Playwright — suggested but not run)** |
| **Camoufox** (wiki) | Firefox-based anti-detect (OSS) | OSS | Best open-source Cloudflare performer per wiki; fallback if rayobrowse dies. |
| **wavexis** (`MathiasPaulenko/wavexis`) — ★2 | CLI wrapper around cdpwave/bidiwave | MIT | **Demoted** — the awesome-list description overstated it ("stealth mode"); reality: 2 stars, thin CLI wrapper, no Chromium download. Not worth pursuing. |
| **Pydoll** (`autoscrape-labs/pydoll`) — ★7,020 · MIT · Python · 🕒 active · single maintainer (bus-factor risk) | CDP-over-WebSocket library, no WebDriver; `apply_fingerprint()` (UA/Client-Hints/navigator/WebGL/canvas/screen/fonts/timezone — survives `toString`, propagates to workers, claims 0 detections on CreepJS/SannySoft/BrowserScan/BrowserLeaks); human Bezier mouse/typing/scroll; network intercept/monitor + **authenticated HTTP requests inheriting the browser session**; closed shadow-DOM + cross-origin iframes; **Pydantic `tab.extract()`** structured extraction | **⚠️ Wiki tested result: 0% against Indeed's strict Turnstile (46 KB block pages, incomplete rendering)** — same tier as JS-patch approaches; NOT in our benchmark shortlist for the driver slot. Features worth stealing: worker-propagating fingerprint injection, session-inheriting HTTP requests (hybrid-scraping idea), Pydantic extract (ties to #6). No agent skill in repo |
| `dhamaniasad/HeadlessBrowsers` catalog | ~50 browsers, PhantomJS-era | — | Historical; confirms Playwright-class CDP drivers are the right category. |

### 2.5 Reference links (for skill authors)

- **OpenAI crawler operations** (openai.com, 2026-08-15) — how the "ultimate scraper company" runs its own bots: (1) UA format = real Chrome UA + `; compatible; OAI-SearchBot/1.4; +https://openai.com/searchbot` (bot token + owner URL); (2) **separate UA marker for robots.txt fetches** (`...; robots.txt; ...`) so logs distinguish robots.txt from content — a log-hygiene trick we can adopt; (3) published IP ranges (searchbot.json); (4) ~24h grace after robots.txt changes; (5) per-use-case bot separation (search vs training vs ads vs user-initiated). Maps to: crawler etiquette for any legit-crawler mode, and per-identity separation (mirrors our per-jar cookie pool).
- **OpenAI community: LLM-extraction economics** (forum thread 869294, 2026-08-15) — consensus pattern for LLM-based extraction: (1) clean/minimize markup in code first (strip header/footer); (2) **HTML→Markdown** to cut tokens; (3) **use the LLM only for small tasks** (category mapping, short summaries) — not bulk extraction; (4) **generate a static scraping script once** with AI instead of per-page LLM calls (validates ScrapeGraphAI script-creator pattern); (5) schema-first output → vector DB (pgvector). Directly informs skill #4 (html-parsing) + the LLM self-healing refinement.

- **High Performance Browser Networking** (hpbn.co): HTTP/1.x, HTTP/2, TCP, **TLS** → cite in tls-impersonation skill.
- **WHATWG specs**: HTML, URL, Encoding, WebSocket.
- **OWASP Web Security Testing Guide** → security-aware scraping.
- **Little Book of Semaphores** → concurrency patterns.
- **scraping-wiki** (`docs/scraping-wiki/`) — local snapshot; the tested-truth source for anti-bot technique.

### 2.6 Agent skills — shortlist from VoltAgent/awesome-agent-skills (2026-08-15)

List verified: 1,497+ skills, hand-picked (official teams + community). SKILL.md files verified to exist for the picks below. **No stealth/captcha skills exist here** (mainstream/legit-focused — that knowledge stays in the scraping-wiki).

| Skill | Repo (verified) | Maps to | Notes |
|---|---|---|---|
| **playwright** | `openai/skills` (★24,965, active) | #1 | Official OpenAI: browser automation for navigation, forms, scraping. `skills/.curated/playwright/SKILL.md` verified |
| **webapp-testing** | `anthropics/skills` (★169,552, active) | #8 | Official Anthropic: **Python** Playwright testing toolkit — decision tree, `with_server.py` lifecycle helper, screenshots/logs. SKILL.md verified |
| **modern-python** | `trailofbits/skills` | #5 | Official ToB: uv/ruff/ty/pytest best practices + reference pack (pyproject, ruff-config, testing, uv-commands). SKILL.md + references verified |
| **mongodb-schema-design** + **mongodb-connection** | `mongodb/agent-skills` (★168, official, active) | #2 | Schema design w/ validation+indexing; connection pool tuning. The exact MongoDB modernization targets |
| **playwright-skill** | `testdino-hq/playwright-skill` | #1, #8 | 70+ production-tested patterns: E2E, POM, CI/CD, migrations, CLI |
| **playwright-skill** | `testmu-ai/playwright-skill` (LambdaTest) | #1, #8 | Multi-language Playwright E2E generation (TS/JS/Python/Java/C#) |
| **pytest-skill** | `testmu-ai/pytest-skill` | #5, testing | pytest with fixtures, parametrize, mocking — fixes the zero-tests pain point |
| **cookie-sync** | `browserbase` (official) | #3 | Export cookies from local Chrome into persistent context — cookie-factory pattern reference |
| **firecrawl-build-*** | `firecrawl` (official) | #4 | Scrape/search/extract integration patterns (SaaS behind it — patterns transfer, service doesn't) |
| **screenshots** | `Shpigford/skills` | #8 | Marketing screenshots via Playwright — simple reusable pattern |
| **superpowers** (brainstorming / writing-plans / executing-plans) | `obra/superpowers` | meta | Plan-execute loop skills — useful for structuring the modernization work |
| **finding-unknowns-skills** | `Neeeophytee/finding-unknowns-skills` | meta | 8 meta-skills (blindspot pass, reference hunt, pre-merge quiz) for coding-agent quality |

**Notable gaps (as expected):** zero anti-detection/stealth/captcha skills in the mainstream lists — that domain is covered by `docs/scraping-wiki/` + our own authoring. Observability options exist (Sentry skills) but plain structured logging fits better.

**Table 2.6a — ComposioHQ/awesome-claude-skills (2026-08-15, ★72.5k):**

| Skill | Source | Maps to | Notes |
|---|---|---|---|
| **Chrome Relay** | `chrome-relay.kushalsm.com` (npx + Chrome extension; **no GitHub repo — unverified**) | #8 | Drives the user's already-open Chrome session (cookies, SSO, extensions, localhost) via local CLI bridge — no Playwright fixtures. Conceptually matches our browser-use/CDP e2e approach |
| **Full-Page Screenshot** | `LewisLiu007/full-page-screenshot` (★12, verified) | #8 | Zero-dependency CDP full-page screenshots — tiny utility for verification evidence |
| **article-extractor** | `michalparkola/tapestry-skills-for-claude-code` | #4 | Extract full article text + metadata from web pages — complements trafilatura for detail-page prose |
| **test-driven-development** | `obra/superpowers` | #5 | TDD-before-implementation discipline — fixes the zero-tests pain point |
| **recursive-research** | `Anjos2/recursive-research` | #10 (concept) | Disk checkpointing to survive context compaction — resume pattern reference |
| **CSV Data Summarizer** | `coffeefuelbump/csv-data-summarizer-claude-skill` | #6 (utility) | Auto-analyzes CSV with visualizations — our current output format; handy for QA of scraped data |
| **Skill Creator / Skill Seekers** | in-repo `./skill-creator/` + `yusufkaraaslan/Skill_Seekers` | meta | Authoring guidance + auto-convert docs→skills — directly useful for the 4 skills we must author |
| **LangSmith Fetch** | in-repo `./langsmith-fetch/` | observability | Fetch/analyze LangChain traces — agent observability reference |

Confirmed-again (already in the main §2.6 table): `lackeyjb/playwright-skill`, anthropics `webapp-testing`. Not relevant from both lists: Composio 78-app automation pack (CRM/comms), postgres skill (we're MongoDB), aws-skills, OKX crypto skills.

**Table 2.6b — mcpservers.org web-scraping category (2026-08-15):**

| Skill | Source (verified) | Maps to | Notes |
|---|---|---|---|
| **browser-act** ⭐ | `browser-act/skills` (★5,385 · MIT · 🕒 active 2026-08-15) | #1, #7, #8, #9 | CLI browser automation with **3 progressive anti-bot layers**: environment (stealth fingerprints + TLS rotation + proxy switching) → execution (`solve-captcha`, `stealth-extract`) → human (`remote-assist` — live URL takeover, agent continues after). **Three modes**: `chrome` (CDP-attach to real Chrome / profile import), `stealth` privacy (fresh fingerprint per session), `stealth` fixed identity (stable fingerprint+IP — = our per-jar model). Install: `uv tool install browser-act-cli` + `npx skills add browser-act/skills`. Cloud mode = paid; local skill mode is MIT. `remote-assist` maps directly onto our manual-solve flow |
| **anti-detect-browser** | `antibrow/anti-detect-browser-skills` (★8, small) | #9 | SDK (Python + Node) launching Chromium with **real-device fingerprints frozen at creation, replayed byte-for-byte** per profile — coherent identity, honest about limits ("not a guaranteed bypass"); explicit acceptable-use policy. Small project — evaluate only if driver benchmark needs a fallback |
| **defuddle** | `kepano/defuddle` (★8,979, TS) | #4 | Extract main page content as clean Markdown — token-saving extraction, complements trafilatura for detail-page prose; also a CLI |
| **just-scrape** | `scrapegraphai/just-scrape` (★48) | patterns | Official ScrapeGraphAI CLI skill — wraps paid API/credits. Patterns only (consistent with §2.1 verdict) |
| **agent-browser** | `inference.sh` skill (3 copies listed: 101-skills/qu-skills/halt-catch-fire) | #8 | Cloud-based browser automation via inference.sh — paid inference; note only |
| **firecrawl-*** (18 skills) | `firecrawl` official | patterns | SaaS skills (company dirs, lead-gen, monitor, SEO audit…) — paid API; patterns only |
| **deep-research** | `samber/deep-research` | meta | Parallel web search + multi-source validation + cited reports — **useful companion for the deep-research agent prompt** (original prompt not retained) |
| **audit-website** | `squirrelscan` | QA | Site audit CLI (SEO/perf/security/accessibility) — not for sarı site; QA-adjacent only |
| **develop-userscripts / use-my-browser** | `xixu-me` | #8 | Tampermonkey userscript dev + drive user's own browser — context |

**Quality standards worth adopting for our own authored skills** (from the VoltAgent list's §Skill Quality Standards): 3rd-person descriptions with match keywords · progressive disclosure (frontmatter <100 tokens, body <500 lines, load refs on demand) · no absolute paths · scoped tool declarations (no blanket `tools: ["*"]`).

**CLI-skill benchmark reference:** `RunMintOn/Agent-Browser-Bench` compares agent-browser / playwright-cli / browser-act — read before picking among these.

**Recommended install set** (into `~/.pi/agent/skills/`, priority order):

| Pri | Skill | Source | Covers |
|---|---|---|---|
| 1 | playwright | `openai/skills` → `skills/.curated/playwright/` | #1 core automation |
| 2 | webapp-testing | `anthropics/skills` → `skills/webapp-testing/` | #8 e2e verification |
| 3 | modern-python | `trailofbits/skills` → `plugins/modern-python/skills/modern-python/` | #5 tooling + testing |
| 4 | mongodb-schema-design, mongodb-connection | `mongodb/agent-skills` | #2 storage migration |
| 5 | pytest | `testmu-ai/agent-skills` → `pytest-skill/` | zero-tests fix |
| 6 | playwright-skill (70+ patterns) | `testdino-hq/playwright-skill` | #1/#8 depth when needed |
| 7 | **scrapling-official** | `D4Vinci/Scrapling` → `agent-skill/Scrapling-Skill/` (**v0.4.8** — corrected 2026-08-16; requires `--ai-targeted` for CLI) | #3/#4/#10 — anti-bot fetch, adaptive selectors, spiders |
| 8 | **browser-act** (candidate) | ~~`browser-act/skills` (★5.4k, MIT)~~ — **SCRAPPED 2026-08-16**: engine is account-gated (API key required even for local chrome-direct); user declined service signups. Skill + CLI uninstalled | ❌ removed |

**Gaps to author ourselves (no existing skills):** anti-detection-stealth (#3), captcha-challenge-handling (#7), browser-driver-lifecycle (#9), resume-crash-recovery (#10) — draw on scraping-wiki + CloakBrowser `human/` + Crawlee patterns. **+ per research report (2026-08-16):** scraper-operations (leases, scheduler, checkpoints, retries, run manifests), inventory/data-quality (snapshots, first/last seen, reconciliation, anomaly thresholds), observability (structured events, metrics, alerts, evidence bundles) — these outrank another stealth skill.

### 2.7 Scrapfly evaluation (2026-08-15)

**Platform** (scrapfly.io — paid SaaS, NOT adopted; project avoids paid scraping APIs): Web Scraping API with `asp` (anti-scraping-protection bypass), Extraction API (rules/templates/LLM extraction), Cloud Browser (CDP, captcha solver, session resume, human-in-the-loop), Crawler API, Screenshot API, MCP server, agentic CLI. **Transferable patterns** (not the service): session-ID reuse + sticky proxy, block-detection/Classify layer, captcha-solver fallback, human-in-the-loop, session resume.

| OSS item | Verdict |
|---|---|
| **scrapfly/skills** (12 SKILL.md: scraper/browser/crawler/extraction/rpa/screenshot/alerting/cli/sdk-*) | **Platform-bound** — every skill wraps the paid API. Not installable for us. Exemplary format though (frontmatter + when-to-use + API reference tables) — matches the adopted quality standards. **Per-skill mining value** (see below) |
| **scrapfly/scrapfly-scrapers** (★1,062, Python, active) | ⭐ **Reference implementation** — 74 open-source scrapers; real-estate cluster (rightmove, zoopla, zillow, realtor, redfin, seloger, leboncoin, immowelt…) is structurally closest to sarı site (listing grid + price filters + pagination). **No sarı site / no Turkish sites.** Mine for pagination, rate-limit, and anti-bot handling patterns |
| **scrapfly/Antibot-Detector** (★362, JS/MV3 Chrome ext) | ⭐ **Detection-layer reference** — identifies CAPTCHAs (reCAPTCHA/hCaptcha/FunCaptcha/GeeTest/**Turnstile**) and anti-bot systems (Cloudflare, Akamai, DataDome, **PerimeterX**, Shape, AWS WAF, Imperva, Kasada) + fingerprint techniques. **Corrected 2026-08-16**: accuracy unverified (no TP/FP benchmark); installs JS hooks at `document_start` → **separate diagnostic profile only**, never in the production path; licence **NPOSL-3.0** — review before any bundling |
| **scrapfly/fingerprint-generator** (★148) | Browser fingerprint data generator — reference for #3 anti-detection (our fingerprint patching) |
| **scrapfly/creepjs** (★1) | Creepy device/browser fingerprinting test site — **diagnostic only** (2026-08-16 correction: not a pass/fail gate; use "fingerprint values internally coherent and stable where intended" instead) |
| **scrapfly/ja3** (Go) | JA3 TLS fingerprint package — reference for the tls-impersonation skill |
| SDKs (python/ts/go/rust), scrapfly-cli, scrapfly-mcp | Platform wrappers — patterns only |

**Per-skill breakdown (all read, 2026-08-15):**

| Skill (lines) | What it contains | Mining value for us |
|---|---|---|
| scrapfly-agent-rules (131) | ⭐ Best content: soft-block recovery flow (`web_scrape` → `check_if_blocked` → retry `asp=true` → escalate `browser_unblock`), stateless-vs-browser decision rules, snapshot-after-DOM-mutation, alert threshold grounding | Directly transferable to our block-recovery logic (`is_login_page` + Turnstile retry ladder); one-tool-per-turn discipline for CDP agents |
| scrapfly-alerting (288) | Threshold alerts on account metrics: discover→preview→create flow, 0–2 fires/day calibration rule | Alert-design principles for our observability gap |
| scrapfly-scraper (327) | ScrapeConfig: `asp`, `session` reuse, `session_sticky_proxy`, country pools, `render_js`, JS scenarios | Session+sticky-proxy pattern for our cookie pool (#3) |
| scrapfly-extraction (387) | 3 extraction methods (prompt/model/template), inline vs saved templates w/ version history + URL scoping | Template-based extraction design for `parse_page()`; versioned template pattern for selector configs |
| scrapfly-browser (387) | Cloud Browser via Python Playwright: session resume, human-in-the-loop, debug mode | Browser lifecycle patterns (#9) |
| scrapfly-crawler (336) / rpa (220) / screenshot (202) / cli (427) / sdk-* (~110 each) | API references for platform products | Low direct value (platform-bound) |

**Captcha-detection pattern extracted (from luminati-io README snippet):** per-provider DOM selector table + success-selector verification:

```js
DataDome: { selector: '#datadome-captcha', success_selector: '#captcha-success' },
reCAPTCHA: { selector: '.g-recaptcha', success_selector: '.recaptcha-success' },
hCaptcha: { selector: '.h-captcha', success_selector: '.hcaptcha-success' },
PerimeterX: { selector: '#px-captcha', success_selector: '#px-success' },
CloudflareTurnstile: { selector: '.cf-turnstile', success_selector: '.cf-success' },
FunCaptcha: { selector: '.funcaptcha', success_selector: '.funcaptcha-success' },
GeeTest: { selector: '.geetest-captcha', success_selector: '.geetest-success' }, ...
```

Apply to our block-detection upgrade: detect via container selector → solve → **poll success selector** (`check_timeout` interval) to confirm. ⚠️ Values are marketing-grade/unverified — for sarı site use the verified recon facts instead: Turnstile = explicit-render (`#cloudflareTurnStileSiteKey`, iframe from challenges.cloudflare.com), PX = `window.PX` API + `_px3` cookie (no `#px-captcha` observed on browse pages).

**Captcha-service ladder (updated 2026-08-15, service-based options):**
1. **NopeCHA** — Turnstile (Token API) + PerimeterX + all majors; free daily tier; works via extension + API
2. **2captcha** — official client `2captcha/2captcha-python` (NOT solvecaptcha-python — that's the solvecaptcha.com vendor). Turnstile supported at **US$1.45/1,000** (2026); standalone widgets + Cloudflare Challenge pages; Challenge flow requires the returned User-Agent |
3. **unicaps** — gateway for 2captcha/anticaptcha; **no Turnstile** (corrected 2026-08-16) |
4. capmonster direct — Turnstile per its docs unverified (NopeCHA table said no) |

**Turnstile token semantics (corrected 2026-08-16):** tokens are **single-use and valid 300 s** (Cloudflare docs). The "UA-bound" claim was **overstated** — no universal UA-binding rule; the narrower rule: 2Captcha's Cloudflare-Challenge flow requires the returned UA, and passing the session's UA is still good practice. Token integration: `sitekey` (read live from `#cloudflareTurnStileSiteKey`) + `pageurl` + optional `action`/`data` → inject into Turnstile hidden input/callback.

**Captcha-solving technique toolbox (skill #7):** prevention (warm session, homepage-first) · **challenge on index page = stop/degrade signal (default stance)** · manual solve (current flow) · service API (2captcha-python / NopeCHA — login-only, optional, permission-dependent) · audio-transcription (Buster technique) · LLM-vision (ai-captcha-bypass technique) · selector-table detection + success-selector polling (luminati pattern) · PX mechanics (Pr0t0ns: `_pxhd` whitelist token, VM-obfuscated challenge, per-profile fingerprint binding).

**PerimeterX reverse-engineering research (Pr0t0ns, 2026-08-15):**

| Repo | What it is | Learnings |
|---|---|---|
| **PerimeterX-Reverse** (`Pr0t0ns/PerimeterX-Reverse`) — ★67 · GPL-3.0 · JS · 🕒 active | Progress log of reversing the PX challenge (up to v8.9.6), request-only goal | ⭐ **Best PX mechanics documentation**: `PxAPPID` = site's PX key; challenge script is **obfuscated + VM-protected** (function/variable names change every load, 9k+ lines) — explains why PX is hard to patch; the solve request **whitelists `_pxhd`** (the captcha token) and `_px3` is the session token; payload is encrypted/base64; device fingerprint hash is unique ~1 in 200,000 (CPU, GPU, WebGL/CanvasFP, screen, UA, extensions, timezone) |
| **PerimeterX-Solver** (`Pr0t0ns/PerimeterX-Solver`) — ★100 · GPL-3.0 · Python · 🕒 active | Working solver for PX **v6.7.9**: `solve.py` + `fingerprint.py` + `key_map.json` generate valid `_px3` cookies | Proof that PX cookie generation is automatable; hardcoded WEBGL fingerprint values (incomplete reverse); newer versions sold via Telegram. **Not for us**: GPL-3.0, ToS-grey, and our warm-browser path already gets `_px3` silently (recon-verified) — solver only matters if PX starts challenging |

**Operational guidance extracted (validates wiki + recon):** (1) residential/high-quality IPs reduce PX prompts; (2) "undetected" webdriver libs (selenium/playwright/puppeteer variants) are ~99% detectable by PX — our rayobrowse/CloakBrowser real-Chromium approach is the right layer; (3) unflagged TLS + consistent device fingerprint across requests (matches cookie-factory + TLS findings); (4) PX binds fingerprint to profile → cookie pools must stay per-profile.

### 2.8 tjaycodes4you (`TJ Oludemi`, Oakville CA, motionlabs.ng) — reverse-engineering goldmine (2026-08-15)

61 public repos, Python/Go/Rust. Background: "billions of requests/week" scale systems. Repo-level finds, most valuable first. **Note: no Google-Maps-bars repo found** — closest is `google-automation` (keyword-result screenshots, unrelated); the bars story may be a different person/tutorial.

| Repo | What it contains | Value for us |
|---|---|---|
| **cookie-api** (Go) | PX + Akamai cookie-generation API (configs dead; docs intact). `doc/PX.md` = ⭐ **PX fingerprint field map**: `bake\|_px3` action format, `_pxde` device-error events, field numbers — PX59–66 (UA parts), PX91–93 (screen res), PX185/186 (window), PX231/232 (outer dims), PX821–823 (jsHeap memory), PX851 (`performance.now`), PX982/983/986/943 (`sts`/`cls`/`wcs`), PX1054/1055 (script start/end timestamps) | Deepens the Pr0t0ns PX mechanics in §2.3 — exact fingerprint inputs PX reads; checklist for our fingerprint patching (#3, #7) |
| **datadome-documented** (Python) | DataDome solver (worked 2023-07) + archived **unobfuscated** DD script + full check list: screen size, exec-time, webdriver/eval-lib checks, timezone, plugins, `eva` length check, audio/video support, browser-specific elements, USB | ⭐ Check list = template for our anti-detection verification matrix; "search the unobfuscated script for the variable" = reverse-engineering method |
| **ghostwire** (Python) — **original: `sofianeelhor/ghostwire` ★89 · MIT · created 2026-06 · active (tjay's repo is a fork)** | Stealth runtime instrumentation: hooks via `Debugger.setBreakpointOnFunctionCall` (invisible to `fn.toString`/monkeypatch checks), CDP over `--remote-debugging-pipe` (no discoverable debug port), `gw_verify` loop — verify your reimplementation against captured ground truth + fresh inputs until diff empty. Full package: `deob` (runtime-rotated string arrays + bytecode VMs), `heap` (search/diff), `dataflow`, `crypto` interception, `origin` tracing, `probes` (network/scripts), **MCP server included** (agent-driven), 13 examples (live_patch, deob_vm, heap_search, oracle_demo…). CLI: `python3 -m ghostwire URL --seconds 5 --grep token --out trace.json`. `evaluateOnCallFrame` reads the actual closure (not an isolated world); flat-mode auto-attach follows workers + OOPIFs; zero-dep core | Research tool for hostile JS (PX/init.js) if we ever need deep reversal; also a pattern for our own detection-hook needs; MCP mode = agent-integratable |
| **rnet** (Rust, fork of wreq-python) | HTTP client with **customizable TLS, JA3/JA4, HTTP/2 fingerprints** (BoringSSL), async+blocking, cookie store, proxies | Alternative to curl_cffi for hybrid-scraping/tls-impersonation; `requestSpeedTest` (★80) proves 20k RPS |
| **ReCaptcha-VM** | reCAPTCHA VM-payload sandbox approach: `/anchor` bytecodes (base64+XOR), VM = value gen + encryption, outside = encoding/ordering/encryption; targets `/reload` + `/userverify` | reCAPTCHA internals — not our blocker; reference depth for skill #7 |
| **Geetest-Analysis** + **geeTestSolver** (Go, ★11) | Geetest challenge flow notes (slide/icon-crusher/gobang), request-based + solver | Not our blocker; pattern reference |
| **awswaf-solver-api** | AWS WAF reverse + FastAPI wrapper | Not our blocker; API-wrapper pattern |
| **aboutYouM** (Python, ★7) | **API-discovery tactic**: found internal aboutyou domain endpoint returning millions of product JSONs in one request (patched next day) | ⭐ Tactic for modernization: hunt sarı site's internal/mobile API before scraping HTML (server-rendered per recon, but app/mobile API may exist) |
| **kasada**, **SlideCaptcha**, **basic-loader** (CF cookie loader), **TLS-Fingerprint-API** (Go, CycleTLS), **utls** fork, **bot-detector**, **powhttp-mcp**, **visiblev8** | Kasada reverse (incomplete), slide solver, headless CF cookie harvester, clienthello spoofing, UaTLS fork, detection playground, HTTP-debug MCP, instrumented V8 | Context/reference; basic-loader ≈ our cookie-pool warmup concept |

**Net impact:** (1) PX field map + DataDome check list → concrete inputs for anti-detection verification matrix in skill #3; (2) ghostwire → the tool to reach for if PX/Turnstile behavior needs ground-truth analysis; (3) aboutYouM API-discovery tactic → check for sarı site internal API during modernization; (4) rnet/wreq → curl_cffi alternative for TLS impersonation.

**Deep-dive: the Rust HTTP client family (upstream = `0x676e67/wreq` ★974 Apache-2.0 + `wreq-python` ★1,424, both active 2026-08-15; tjay's `rnet` is a fork):**
- ⭐ **Modern TLS emulation, not string spoofing**: "JA3/JA4/Akamai cannot be reliably emulated with simple fingerprint strings… wreq provides fine-grained control over TLS and HTTP/2 extensions and settings" — extension-level emulation (the BrowserForge-class approach), with **100+ maintained browser device profiles** (e.g. `Emulation.Chrome149`).
- Full Python feature set: async+blocking clients, cookie store, redirect policy, proxy rotation, pooling, streaming, WebSocket, BoringSSL, mTLS, free-threaded safety.
- **Why it was thought to be the key (hybrid scraping)**: browser does clearance → wreq bulk-fetches with a matching Chrome profile + cookies → correct TLS fingerprint without a browser per request. ⚠️ **Corrected 2026-08-16 (research report)**: predefined profiles are **Chrome146–149 only — no 150/151** ⇒ **no exact match for CloakBrowser v150**; "149 ≈ 150" is unverified and must be measured (full ClientHello/ALPN/H2-settings/headers, not JA3 alone). **wreq is DEMOTED from the default path** — browser-only first; hybrid only after a runtime-SLO miss and a one-request G2b identity experiment. (rayobrowse-Chromium-146 ↔ wreq-Chrome146 remains the one potentially exact match.)
- Cost: Rust toolchain needed to build (sdist installs via rustup); Apache-2.0 permissive. Benchmarked 20k RPS (requestSpeedTest).

---

### 2.9 Emlakjet residential rental recon — live browser (2026-08-17)

- **Emlakjet:** `https://www.emlakjet.com/kiralik-konut` rendered roughly 41k listings, 30 `article[data-listing-id]` cards per page, and a visible 50-page cap per geographic route. The country/province pages expose province and district/neighborhood rental URLs; large scopes must be subdivided to avoid silently collecting only the first 1,500 cards. The robots policy disallows `?filtreler=*`, so the scraper uses only `?sayfa=`.
- **Operational policy:** the adapter uses a normal visible browser, homepage-first navigation, serial pacing, ID deduplication, dated CSV/checkpoint files, and a stop signal for challenge pages. It does not solve/bypass CAPTCHA, open detail pages, or export advertiser/contact/photo fields. Cards marked explicitly `satılık`/`satlik` are rejected defensively even when found on a rental route.

## 4. Skill Registry (what the coding agent should be able to do)

### Top 10 Skills Needed

| # | Skill | Why / tool anchors |
|---|-------|--------------------|
| 1 | **playwright-automation** | Core driver: async API, selectors, waits, CDP-over-WebSocket (rayobrowse) |
| 2 | **mongodb-persistence** | Replace CSVs: upsert on `ilanId`, TTL/indexes, schema |
| 3 | **anti-detection-stealth** | Fingerprint patching, human motion (**CloakBrowser `human/` as template**), cookie factories |
| 4 | **html-parsing-extraction** | Selector hardening (**parsel/selectolax/chompjs**), recover ilan ID/link (**dateparser** for dates) |
| 5 | **python-refactoring** | Split the monolith into modules, type hints |
| 6 | **data-validation-schema** | Pydantic models, **price-parser** (drift fix), dedup |
| 7 | **captcha-challenge-handling** | Turnstile explicit-render solver, manual fallback, **2captcha-python (official) / NopeCHA** service fallback (login-only, permission-dependent; tokens single-use/300 s), selector-table detection |
| 8 | **e2e-browser-testing-computer-use** | Verify scrapers against live site (browser-use / replay) |
| 9 | **browser-driver-lifecycle** | Driver matrix (rayobrowse / CloakBrowser / camoufox), Docker, CDP session mgmt, version pinning |
| 10 | **resume-crash-recovery** | Idempotent checkpoint/resume, per-listing `ilanId` tracking (**Crawlee** patterns) |

### Honorable Mentions
Observability/structured logging · Scheduling (daily runs; celery/RQ/huey) · Async-python · Docker deployment.

### Related Recommendation Set (three-skill skeleton)
1. **`playwright-scraper`** — Playwright + anti-detection + pagination → structured JSON/NDJSON
2. **`mongodb-loader`** — upsert/dedup/schema (pymongo/mongoose)
3. **`browser-use-tester`** / **`computer-use-tester`** — verify scrapers: run flow, screenshot-assert, replay actions

### Search Keywords
Scraping: `playwright`, `puppeteer`, `selenium`, `beautifulsoup`, `scrapy`, `web-scraping`, `anti-bot`, `stealth`, `cloudflare`, `turnstile`
Storage: `mongodb`, `pymongo`, `mongo-upsert`, `deduplication`
Drivers: `webdriver-manager`, `chromedriver`, `selenium-grid`, `docker-selenium`, `standalone-chrome`, `browser-profile`, `headless-browser`, `browser-pool`
Computer use: `computer-use`, `browser-use`, `ui-tars`, `skyvern`, `steel-browser`, `vision-based-automation`, `gui-agent`
Testing: `playwright-test`, `pytest-playwright`, `visual-regression`, `screenshot-testing`, `e2e-testing`, `action-replay`, `llm-e2e`
MCP/skills: `playwright-mcp`, `browser-mcp`, `SKILL.md`, `agent-skills`, `opencode-skills`, `awesome-claude-skills`
GitHub topics: `topic:web-scraping`, `topic:computer-use`, `topic:agent-skills`, `topic:playwright`; search `"SKILL.md" <tool>`.

### Suggested skill refinements from research

| Skill | Refinement |
|---|---|
| **anti-detection-stealth** | Adopt CloakBrowser `human/` parameter catalog (Bézier mouse, mistype keyboard, scroll physics); cookie-factory details (profile binding, DisableCookieTransport) |
| **html-parsing-extraction** | Evaluate parsel/selectolax; LLM self-healing repair loop (ScrapeGraphAI pattern: syntax→exec→schema→semantic) |
| **browser-driver-lifecycle** | Driver risk matrix: rayobrowse (closed-source beta) vs CloakBrowser (proprietary binary) vs camoufox (OSS) |
| **NEW: hybrid-scraping** | Browser-for-clearance + **wreq/curl_cffi** for bulk; TLS fingerprint must match the clearing browser (rayobrowse Chromium 146 → matching wreq profile); cookie handoff from browser session |
| **NEW: tls-impersonation** | **wreq** (extension-level TLS/HTTP2 emulation, 100+ profiles) or curl_cffi; JA3/JA4 basics; cite HPBN TLS chapter |
| **NEW: inventory-tracking** | Listing time-series in MongoDB (requires ilanId extraction) |

---

## 5. Status

- [x] Registry created (2026-08-15) + renamed to TECH-STACK-SEARCH.md (2026-08-15)
- [x] Site 1: ScrapeGraphAI — evaluated, pattern extracted
- [x] Site 2: CloakBrowser — evaluated, human/ template + driver candidate → **G0 FAILED 2026-08-16 (Turnstile "Doğrulama Başarısız" even on vanilla flow; free binary = v146 not v150); NOT ADOPTED**
- [x] Site 3: awesome-web-scraping — evaluated, 8 shortlist tools + reference links
- [x] Site 4: VoltAgent/awesome-agent-skills — evaluated, 12 skill picks verified (SKILL.md confirmed)
- [x] Site 5: ComposioHQ/awesome-claude-skills — evaluated, +8 additions (4 novel: Chrome Relay, Full-Page Screenshot, article-extractor, TDD)
- [x] Site 6: Scrapfly — evaluated (docs + org): skills repo platform-bound; gems = scrapfly-scrapers (74 OSS scrapers) + Antibot-Detector + fingerprint-generator
- [x] Ad-hoc evaluations: jsoup (§2.2, not adopted — Java), Buster (§2.3, not applicable — reCAPTCHA-audio only), CloakBrowser `human/` (driver + anti-detection template)
- [x] Ad-hoc evaluation: ai-captcha-bypass (§2.3 — LLM-vision captcha technique noted; not adopted: no Turnstile/PX support, Selenium, unclear license)
- [x] Ad-hoc evaluation: luminati-io/perimeterx-captcha-solver (§2.3 — marketing-only repo; extracted captcha-detection selector-table pattern)
- [x] Ad-hoc evaluation: Pr0t0ns PerimeterX-Solver + PerimeterX-Reverse (§2.3 — PX mechanics doc: `_pxhd` whitelist token, VM obfuscation, fingerprint uniqueness; solver exists for v6.7.9 but not adopted)
- [x] Ad-hoc evaluation: NopeCHA (§2.3 — top service-based captcha option: Turnstile+PX support; 2captcha/capmonster lack Turnstile; repo is docs-only)
- [x] Reference: OpenAI crawler ops + LLM-extraction economics (§2.5 — UA/robots.txt hygiene patterns; LLM-only-for-small-tasks rule)
- [x] Ad-hoc evaluation: solvecaptcha-python (§2.3 — official 2captcha client, **Turnstile verified in code**, corrects NopeCHA table; token-injection pattern)
- [x] Goldmine deep-dive: tjaycodes4you (§2.8 — PX field map via cookie-api, DataDome check list, ghostwire instrumentation, rnet TLS client, API-discovery tactic)
- [x] Deep-dive: wreq/wreq-python (§2.8 — upstream ★1,424 Apache-2.0; extension-level TLS emulation + 100+ profiles; prime hybrid-scraping client; profile must match rayobrowse Chromium 146)
- [x] Integration blueprint: §3.1 — CloakBrowser + wreq bulk + NopeCHA/solvecaptcha auto-solve + verification matrix (Antibot-Detector/creepjs/DD checklist/PX field map) + ghostwire for deep RE; migration order + risks listed
- [x] Site 7: Scrapling (§2.1 + §3.1 parallel track — ★74k; adaptive selectors, spiders pause/resume, official agent skill; head-to-head benchmark vs CloakBrowser+wreq)
- [x] Site 8: Pydoll (§2.4 — ★7k MIT; wiki-tested 0% vs strict Turnstile; features noted: worker-propagating fingerprints, session HTTP, Pydantic extract; not in driver benchmark)
- [x] Site 9: mcpservers.org web-scraping category (§2.6 — browser-act ★5.4k install candidate w/ 3-layer anti-bot + remote-assist human handoff; antibrow; defuddle; just-scrape; deep-research; Agent-Browser-Bench reference)
- [x] Tool metadata verified via GitHub API (stars/license/lang/activity)
- [ ] More sites from user (search log grows)
- [x] **Beymen tech scraper audit + repair (2026-08-18)** — verdict: **scraper WAS broken (silent truncation)**: `InflationItems/Codes/Technology/scraper.py` hard-capped at `range(1, 201)` (200 pages × 48 = 9,600 rows). Catalog outgrew the cap on ~Jun 17 (rows: 8.5–9.4k in May/early Jun → exactly 9,600 every day since) — API reports `totalPageCount=222`/`totalItemCount=10,614` and the site itself displays “10614 Ürün”; ~1,056 products (~10%) were silently missed daily, incl. e.g. `LOQ 15AHP10 … 24GB` @ 60,209 TL (live site search confirmed present). Fix: (1) **dynamic pagination** — read `data.totalPageCount` from page-1 response, loop until last reported page (hard safety cap 500, empty-page break kept); (2) **in-memory dedup by `productId`** (never by name — distinct variants legitimately share name+price; a fast API pass has 0 repeated productIds, but the ~10-min crawl with 1.5–3.5 s sleeps lets the live catalog shift so one product can reappear on a later page; verified 214+ same-name/same-price pairs in pages 1–200 are *different* productIds). CSV schema unchanged (`product-name,product-price`, utf-8-sig) — `Inflations/Codes/Technology/inflation.py` + downstream readers unaffected. (3) **seleniumbase UC port-9222 collision fix**: seleniumbase's undetected launcher probes `127.0.0.1:9222` and treats non-200 as “port free”, so a user Chrome with remote debugging (e.g. chrome-relay) breaks cookie fetch (“cannot connect to chrome at 127.0.0.1:9222”); `get_stealth_cookies` now detects that case and fakes a 200 probe so seleniumbase picks a random free port (restored in `finally`; 9222-free path untouched). Verified end-to-end twice (full runs): ~10,5xx–10,614 rows, 0 true duplicates, 0 variant loss, previously-missing products present. Verification script: `scripts/verify_beymen_pagination.py` (removed 2026-09-07 in the verify-script cleanup; scraper verification went back to running the scraper. It bypassed the cookie step via empty cookies — API serves cookieless today, may change). NOTE: Aug-13 file has 9,408 rows = 196 pages — early stop (403/error mid-run), by-design partial save.
- [ ] Skills to be installed into `~/.pi/agent/skills/` — install set defined in §2.6 (6 installs + 4 to author)
- [x] Skills installed so far: **playwright, webapp-testing, modern-python, mongodb-schema-design, mongodb-connection, playwright-skill (testdino), full-page-screenshot, test-driven-development + 11 meta-skills** (agent-interface-design, blindspot-pass, brainstorm-prototypes, change-quiz, context-audit, implementation-notes, implementation-plan, interview-me, pitch-packager, progressive-disclosure, reference-hunt) — remaining: pytest (testmu-ai), scrapling-official
- [x] **browser-act SCRAPPED (2026-08-16)**: account-gated engine (API key required even for local chrome-direct) — user declined service signups; skill + CLI uninstalled. ⚠️ cookie-sync similarly requires BROWSERBASE_API_KEY (paid) — dormant unless Browserbase is adopted
- [ ] Skill set validated against a live modernization run
- [x] **Telecom tariff scraper (2026-10-08)** — new `InflationItems/Codes/Telecom/scraper.py` (cron server job `telecom`, `deploy/scraper-server/`) for TÜİK `0832001` (Cep telefonu görüşme ücreti): Turkcell, Vodafone, Türk Telekom, NetGSM; all tariffs + add-ons, commitment price and no-commitment `list_price`. Stateless path only (no browser). Türk Telekom listing pages render 12 cards and page through the robots-disallowed `/_layouts/…/CardFilter` XHR, so its URLs come from `sitemap.xml` and prices from detail-page JSON-LD. Calculator-compatible header (`product_name`, `price`); not yet wired into `turkey_inflation.py`. Recon + selectors: `docs/site-analysis/telecom/NOTES.md`.
- [x] **Repair price scraper (2026-10-09)** — `InflationItems/Codes/Telecom/repair.py` (cron server job `repair`) for TÜİK "Bilgi ve iletişim ekipmanı bakım / onarım ücreti": Apple (official out-of-warranty estimate API, iPhone/iPad/Watch/AirPods), Samsung (official recommended fees), Huawei (official spare-part price API), GSM İletişim (independent shop). Collects everything each source lists until the basket is decided.
- [x] **Streaming subscription scraper (2026-10-09)** — `InflationItems/Codes/Telecom/streaming.py` (cron server job `streaming`) for TÜİK "Dijital içerik / streaming platform aboneliği": 12 services, one public page each, plain HTTP with a Turkish `Accept-Language` (YouTube/MUBI localise plan names and prices). Trial/first-month promos (Spotify "İlk 1 ay ₺0", TOD "İlk Ay 9₺") are skipped in favour of the regular price. tabii Premium is read from the rendered page with one headless Chrome visit (its price is filled client-side). Not collected: Exxen, Hepsiburada Premium, Paramount+.
- [x] **Home internet scraper (2026-10-08)** — `InflationItems/Codes/Telecom/internet.py` (cron server job `internet`) for TÜİK `0833001`: Superonline (sitemap → `GetCampaignDetail.offers[]`), Vodafone Net cards, Kablonet tables (turksatkablo.com.tr; AIA intermediate added to the certifi bundle because the server sends only its leaf cert), Milleni card data-attributes, TurkNet `/tarifelerimiz` via cookie factory (headless undetected-Chrome → `__cf_bm` + UA → curl_cffi; the TLS fingerprint decides: every curl_cffi 0.15 profile gets 403, the 0.16 newest `chrome` profile passes cookieless), Türk Telekom `evde-internet` sitemap detail pages. Closed TT offers ("müşteri alımına kapatılmıştır") and expired Superonline campaigns are skipped.
- [x] **08_Communication layout (2026-10-11)** — tech + telecom scrapers follow the upstream TÜİK 01-13 layout: code `InflationItems/Codes/08_Communication/<Retailer>/` (telecom code `08_Communication/Telecom/`), data flat `InflationItems/Datas/08_Communication/<Retailer>/*.csv` (no Internet/Streaming/Repair sub-folders). Home internet and repair files carry a kind suffix (`vodafone_internet_*`, `huawei_repair_*`) because they share retailer folders with mobile tariffs / tech products. `turkey_inflation.py` reads the sector as `08_Communication` and keeps telecom CSVs (`operator` column) out of the pool.

---

## 2.10 Agent-environment browser/search evaluation (2026-09-02)

Evaluation for the *agent's own* web workflow (Exa + browser routing), not the scraper stack — logged per AGENTS.md convention.

| Tool | Verdict (agent use) | Evidence |
|---|---|---|
| **Exa API** (`api.exa.ai/search`, Bearer auth) | ⭐ Primary search — semantic, structured, cheapest | Verified live; ~$0.007/search; highlights/text modes; free $20 + $10/mo credits |
| **Obscura** (`h4ckf0r0day/obscura`, Rust, Apache-2.0, ★24k) | ⭐ Primary browser for page reads — zero-dep binary, markdown dumps, built-in stealth | Installed `~/.local/bin` v0.2.1; stealth fingerprint verified (webdriver=false, Chrome/143 UA); **emlakjet.com/kiralik-konut passed with stealth (real listings, 42k ads)**; sahibinden.com still Cloudflare-walled; young engine (2026-04), long-tail CSS risk |
| **camoufox-cli** (`Bin-Huang/camoufox-cli`, MIT, ★340) | Candidate specialist for hard anti-bot walls (sahibinden-class) | Camoufox engine proven (wiki + DEV article: Turnstile green check ~7s); Firefox-class runs in WSL with local-lib fix; not yet installed |
| **playwright-cli** (chromium/firefox) | Backup browser | Works from WSL; vanilla = detectable on protected sites |

**Routing:** Exa → search · Obscura(--stealth) → pages · camoufox-cli → hard walls (pending) · playwright-cli → backup · curl → plain fetches.


---

## 3.1 Emlakjet CI hardening (2026-09-02)

Fix for the Emlakjet rental scraper failing on GitHub Actions (`ReadTimeoutError` on
the Selenium wire at `localhost:<port>` after ~4 min, i.e. Chrome stopped answering).

Root causes observed:
- Brute symptom: browser hang → Selenium's default **120 s wire read timeout** kills
  the job; no recovery path existed.
- Container/chromedriver flags missing on the runner: no `--disable-dev-shm-usage`
  (tiny `/dev/shm` crashes Chrome) and no `--no-sandbox`.
- `pageLoadStrategy=normal` lets `driver.get()` block indefinitely on slow
  trackers/subresources.
- Checkpoints lived under `InflationItems/Codes/HousesRent/Emlakjet/checkpoints/` = gitignored and
  the workflow never passed `--resume` → every run crawled from scratch, and any
  mid-run session death wasted the whole crawl.

Applied (files):
- `InflationItems/Codes/HousesRent/browser.py`:
  - stability args (`--disable-dev-shm-usage`, `--no-sandbox`, `--disable-gpu`,
    background/extension/sync off) for launched drivers;
  - `pageLoadStrategy=eager` for launched (non-attach) sessions;
  - wire command timeout lowered to 90 s (`_configure_driver`), script timeout 45 s;
  - `_run_bounded()` watchdog (daemon thread + deadline, raises `DriverStall`);
  - `BrowserSession` — owns the driver, runs each page under the watchdog, discards
    the dead session, starts a fresh driver via factory, retries the page up to
    `max_retries` (default 3); `ChallengeDetected` is never retried.
- `InflationItems/Codes/HousesRent/Emlakjet/scraper.py`:
  - `scrape()` now takes `driver_factory`/`max_page_retries`/`page_timeout` and uses
    `BrowserSession`; legacy `driver`+`load_page` injection still supported (tests);
  - CLI: `--max-page-retries`, `--page-timeout`; launched drivers use a fresh temp
    profile (`fresh_profile=True`) so restarts never hit profile locks;
  - default checkpoint moved to `InflationItems/Datas/HousesRent/Emlakjet/state/checkpoint.json`
    (tracked; `checkpoints/` dir name stays gitignored), stamped with
    `checkpoint_date`; `--resume` ignores stale (previous-day) checkpoints and the
    file is deleted after a completed crawl.
- `.github/workflows/emlakjet_scraper.yml`: runs `--resume`; commits the whole
  `InflationItems/Datas/HousesRent/Emlakjet/` dir (CSV + state).
- Per project principle (AGENTS.md), scraper code carries NO unit/smoke tests;
  verification is by running it: headless bounded run 2026-09-02
  (`--start-url /kiralik-konut/isparta --max-pages-per-scope 8`) crawled 8 live
  pages with page-load retries + checkpoint resume intact.

ETL note: emlakjet listing grid is server-rendered (31 `article[data-listing-id]`
cards in raw HTML) — parser checked against live pages 2026-09-02 (30 rows/page,
Isparta total 225 → 8 pages).

---

## 3.2 Shared TÜİK 08 columns + Windows checkpoint rename (2026-10-18)

- Every 08_Communication scraper now writes `product_name, price, category_number,
  sub_category_number` as its first four columns. `category_number` is `8`.
  `sub_category_number` is the 7-digit TÜİK item code from "CPI methodological notes",
  Appendix 1, or `0` for products outside the 08 basket.
- `InflationItems/Codes/08_Communication/tuik08.py` holds the codes and `classify(name, hint)`.
  It uses ordered keyword rules: out-of-basket first, then accessories, then devices.
  Samsung and Huawei map their own site categories instead. Telecom scrapers pass one fixed code
  per scraper through `run(..., sub_category)`. Vatan moved from headerless `name;price` text
  prices to a comma CSV with a header and numeric prices.
- Rules were tuned against the 2026-10-18 Beymen, D&R, Pozitif and Vatan CSVs. Per-bucket random
  samples were checked by hand, for example camera "VR" lenses, the colour "Koyu Kahve", SteelSeries
  "Nova" headsets, and OLED monitors/laptops vs TVs. Expect a few hundred misclassified products per
  day.
- Verified by live runs: full Samsung, Huawei, Pozitif, D&R, streaming, Beymen and BeymenTech runs,
  plus `--limit` runs of mobile, internet and repair, and a Vatan run limited to the TV category.
- `04_Housing/common.py save_checkpoint` retries `os.replace` on `PermissionError`. On Windows the
  rename failed twice mid-crawl (WinError 5) while another process briefly held the checkpoint.
- Emlakjet `--workers N` (default 1): N BrowserSessions run in threads. They share the scope
  queue, `CsvSink` and checkpoint under one `threading.Condition`. A worker with an empty queue
  waits while another worker may still split a scope into children. Each worker visits the
  homepage first and keeps `--delay`, so the per-IP request rate scales with N. The checkpoint now
  records `active_scopes` (list); the old `active_scope` key is still read on `--resume`. Fixed in
  the same change: a province `--start-url` above the page cap was split using the country-level
  province list, which returned only the province itself, so bounded runs collected 0 rows.
  Verified with `--start-url .../isparta --max-pages-per-scope 3 --workers 2`: 13 districts plus
  65 Merkez neighbourhoods, 243 rows / 243 unique ilanIds (site count 243), checkpoint removed on
  completion. The full 2026-10-18 crawl was then resumed with `--workers 2`.

## 3.3 Emlakjet removed (2026-10-18)

The Emlakjet rental scraper (`InflationItems/Codes/04_Housing/`: `Emlakjet/scraper.py`, `browser.py`,
`common.py`) and `.github/workflows/emlakjet_scraper.yml` were removed from the repository on request.
§3.1 and the `--workers` note in §3.2 describe code that no longer exists here. Collected data stays
under `InflationItems/Datas/04_Housing/Emlakjet/`.

## 3.4 Old 08 CSVs converted to the shared columns (2026-10-18)

All 552 older 08_Communication CSVs (13 legacy layouts, 2026-05-02 to 2026-10-18) were rewritten in
place to the `product_name, price, category_number, sub_category_number` layout. Item codes came from
the same `tuik08.classify` and Samsung/Huawei category maps the scrapers use, so converted and freshly
scraped files agree. Old name/price columns were renamed (`UrunAdi`/`FiyatFloat`, `product-name`/
`product-price`, `Product Name`/`Price`, `name`). Other columns were kept in their original order after
the four. Vatan's headerless `name;59.999 TL` files got a header, commas and numeric prices. A row-by-row
check against the pre-conversion backup confirmed identical row counts, names and prices in all 570
finished files. The backup is `export/datas_08_before_tuik_columns_2026-10-18.tar.gz` (gitignored, local
only). The one-off conversion script was not added to the repository.
