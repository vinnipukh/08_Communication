# queue — scraper queue (TÜİK 04 utilities, fuels, repair labour)

Work the queue top to bottom, one item per change. Each file is a spec: source, endpoints, what to
extract, output schema, and open questions. Recon was done live on 2026-10-28 with plain HTTP
(no Playwright needed anywhere so far); re-check endpoints before coding, they may have moved.

Scope rule: Istanbul, Ankara and İzmir only. If a source returns other provinces through the same
endpoint with no extra code, take them all; never add work just to cover other provinces.

| # | Spec | TÜİK items | Est. requests / run | Est. runtime | Status |
|---|---|---|---|---|---|
| 1 | [01_electricity_epdk.md](01_electricity_epdk.md) | 0451001 | 3 | ~4 s (measured) | done (2026-10-28) |
| 2 | [02_natural_gas.md](02_natural_gas.md) | 0452101, 0452102 | ~11 | ~7 s (measured) | done (2026-10-28) |
| 3 | [03_water.md](03_water.md) | 0441101 | ~4 | ~15 s | todo |
| 4 | [04_lpg.md](04_lpg.md) | 0452201 | ~330 (81 provinces × 4 brands) | ~5–7 min | todo |
| 5 | [05_repair_labor_armut.md](05_repair_labor_armut.md) | 0432015 | ~60 | ~1–2 min | todo |
| 6 | [06_coal_tki.md](06_coal_tki.md) | 0454101 | 1 | ~5 s | todo (semi-manual) |
| 7 | [07_firewood.md](07_firewood.md) | 0454201 | 1 | ~5 s | todo (source: Odunal.com) |

Full run of 1–7: ~8–10 min with 1 s politeness delay. Most prices change monthly or less often,
so a monthly (or weekly) schedule is enough.

Statuses: `todo` → `in progress (<date>)` when you start → `done (<date>)` or `blocked: <reason>`.
Read [NOTES.md](NOTES.md) before starting an item and append to it when you finish.
