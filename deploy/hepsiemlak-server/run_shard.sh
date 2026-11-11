#!/usr/bin/env bash
# Run one Hepsiemlak shard unattended:  run_shard.sh <zelal|dani|neslihan|ekin> [extra scraper args]
#
# - one run per shard at a time (flock), also across cron and manual starts
# - scraper.py exits 1 when the site blocked it or routes were lost: wait, then `--resume`, until it
#   finishes or the deadline passes (default 20 h after the start)
# - each attempt has a hard timeout; leftover browsers are killed between attempts
# - at the end, one status line in log.txt: OK / LOW / INCOMPLETE with row count against the sitemap
#   count in shards.json (checked, not assumed). Nothing is pushed anywhere.
# Extra args (e.g. `--max-listings 100 --output test.csv`) are passed to scraper.py; a run with --output
# or --max-listings is a test: one attempt, no retry loop, no status check.
set -u

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
CODE="$ROOT/InflationItems/Codes/04_Housing/Hepsiemlak"
DATA="$ROOT/InflationItems/Datas/04_Housing/Hepsiemlak"
PY="$ROOT/venv/bin/python"
LOG_DIR="$ROOT/server_logs"
STATUS_LOG="$ROOT/log.txt"
ATTEMPT_TIMEOUT="${ATTEMPT_TIMEOUT:-8h}"
RETRY_WAIT="${RETRY_WAIT:-1800}"          # seconds between attempts after an incomplete one
DEADLINE_H="${DEADLINE_H:-20}"
MIN_FREE_MB=1000

SHARD="${1:-}"; shift || true
case "$SHARD" in zelal|dani|neslihan|ekin) ;; *) echo "usage: $0 {zelal|dani|neslihan|ekin} [scraper args]"; exit 2 ;; esac
EXTRA=("$@")
TEST=0
for a in "${EXTRA[@]}"; do case "$a" in --output|--max-listings|--limit) TEST=1 ;; esac; done

[ -f "$ROOT/.env" ] && { set -a; . "$ROOT/.env"; set +a; }
export PYTHONIOENCODING=utf-8 LANG=C.UTF-8 LC_ALL=C.UTF-8
mkdir -p "$LOG_DIR" "$DATA"
status() { echo "$(date '+%F %T') [hepsiemlak_$SHARD] $*" >> "$STATUS_LOG"; }

free_mb=$(df -Pm "$ROOT" | awk 'NR==2 {print $4}')
if [ "${free_mb:-0}" -lt "$MIN_FREE_MB" ]; then status "SKIPPED: only ${free_mb} MB free"; exit 1; fi

exec 9>"/tmp/hepsiemlak_$SHARD.lock"
if ! flock -n 9; then status "SKIPPED: already running"; exit 0; fi

DAY="$(date +%F)"                          # fixed at the start, so a run crossing midnight keeps one file
OUT="${DAY}_${SHARD}.csv"
for ((i = 0; i < ${#EXTRA[@]}; i++)); do [ "${EXTRA[i]}" = "--output" ] && OUT="${EXTRA[i+1]}"; done
CSV="$DATA/$OUT"; CKPT="$CODE/checkpoints/${OUT%.csv}.json"
RUN_LOG="$LOG_DIR/hepsiemlak_${SHARD}_$(date +%F_%H%M).log"

if [ "$TEST" = 0 ] && [ -f "$CSV" ] && [ ! -f "$CKPT" ] && [ "$(wc -l < "$CSV")" -gt 1 ]; then
  status "already complete today ($(( $(wc -l < "$CSV") - 1 )) rows)"; exit 0
fi

killbrowsers() { pkill -9 -f 'cloakbrowser|chrome' 2>/dev/null; }   # dedicated box: anything left is ours

start=$(date +%s); deadline=$(( start + DEADLINE_H * 3600 )); attempt=0; rc=1
status "start (attempts until ${DEADLINE_H} h, each at most $ATTEMPT_TIMEOUT)"
while :; do
  attempt=$((attempt + 1))
  ARGS=(--shard "$SHARD" --output "$OUT" "${EXTRA[@]}")
  # (a caller's own --output repeats the same value; argparse takes the last one)
  [ -f "$CKPT" ] && [ -f "$CSV" ] && ARGS+=(--resume)
  echo "=== attempt $attempt $(date '+%F %T')" >> "$RUN_LOG"
  ( cd "$CODE" && timeout --kill-after=2m "$ATTEMPT_TIMEOUT" "$PY" -u scraper.py "${ARGS[@]}" ) >> "$RUN_LOG" 2>&1
  rc=$?
  killbrowsers
  [ "$rc" = 0 ] && break
  [ "$TEST" = 1 ] && break
  if [ $(( $(date +%s) + RETRY_WAIT )) -ge "$deadline" ]; then break; fi
  status "attempt $attempt ended rc=$rc, retrying in $((RETRY_WAIT / 60)) min"
  sleep "$RETRY_WAIT"
done
dur=$(( ($(date +%s) - start) / 60 ))

rows=$(( $( [ -f "$CSV" ] && wc -l < "$CSV" || echo 1 ) - 1 ))
if [ "$TEST" = 1 ]; then status "TEST rc=$rc rows=$rows in ${dur} min (see $RUN_LOG)"; exit $rc; fi

# row count against the sitemap-based count of this shard (shards.json), and share of rows with a missing field
read -r expected empty < <("$PY" -I - "$CODE/shards.json" "$CSV" "$SHARD" <<'PY'
import csv, json, sys
shards, path, name = sys.argv[1:4]
exp = json.load(open(shards, encoding="utf-8"))["counts_2026_10_23"][name]
rows = list(csv.DictReader(open(path, encoding="utf-8", newline=""))) if path else []
bad = sum(1 for r in rows if not (r["price"] and r["Rooms"] and r["AreaM2"]))
print(exp, f"{100 * bad / len(rows):.1f}" if rows else "100.0")
PY
)
pct=$(( rows * 100 / expected ))
lost=$(grep -c 'LOST after' "$RUN_LOG")
if [ "$rc" != 0 ]; then verdict="INCOMPLETE rc=$rc"
elif [ "$pct" -lt 70 ]; then verdict="LOW"
else verdict="OK"; fi
status "$verdict rows=$rows expected~$expected (${pct}%) empty-field=${empty}% lost-routes-logged=$lost attempts=$attempt in ${dur} min (see $RUN_LOG)"
exit $rc
