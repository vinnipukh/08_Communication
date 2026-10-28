#!/usr/bin/env bash
# Run ONE scraper safely from cron:  run_scraper.sh <name>
#
# - global lock: scrapers never run at the same time (a late job waits its turn)
# - hard timeout: a hung scraper cannot block the next day
# - disk guard: skips the run when the disk is nearly full
# - kills any leftover Chrome after the run (RAM)
# - per-run log in server_logs/, one status line per run in log.txt
set -u

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"  # <repo-root>: bin/ lives directly under it
PY="$ROOT/venv/bin/python"
CODES="$ROOT/InflationItems/Codes/08_Communication"
TELECOM="$CODES/Telecom"
LOG_DIR="$ROOT/server_logs"
STATUS_LOG="$ROOT/log.txt"
LOCK=/tmp/scraper.lock
MIN_FREE_MB=1500

NAME="${1:-}"
case "$NAME" in
  samsung)  TIMEOUT=20m;  CMD=("$PY" -u "$CODES/Samsung/scripts/main.py") ;;
  huawei)   TIMEOUT=10m;  CMD=("$PY" -u "$CODES/Huawei/huawei_scraper.py") ;;
  pozitif)  TIMEOUT=15m;  CMD=("$PY" -u "$CODES/PozitifTeknoloji/pozitifTeknoloji_scraper.py") ;;
  beymen)   TIMEOUT=45m;  CMD=("$PY" -u "$CODES/Beymen/scraper.py") ;;
  dr)       TIMEOUT=20m;  CMD=("$PY" -u "$CODES/DR/dr_scraper.py") ;;
  vatan)    TIMEOUT=120m; CMD=("$PY" -u "$CODES/VatanComputer/vatan_comp.py") ;;
  telecom)  TIMEOUT=90m;  CMD=("$PY" -u "$TELECOM/scraper.py") ;;
  internet) TIMEOUT=75m;  CMD=("$PY" -u "$TELECOM/internet.py") ;;
  streaming) TIMEOUT=15m; CMD=("$PY" -u "$TELECOM/streaming.py") ;;
  repair)   TIMEOUT=90m;  CMD=("$PY" -u "$TELECOM/repair.py") ;;
  *) echo "usage: $0 {samsung|huawei|pozitif|beymen|dr|vatan|telecom|internet|streaming|repair}"; exit 2 ;;
esac

cd "$ROOT" || exit 1
mkdir -p "$LOG_DIR"

# cron has no shell environment: load optional settings (e.g. CHROME_VERSION_MAIN)
if [ -f "$ROOT/.env" ]; then
  set -a; . "$ROOT/.env"; set +a
fi
export PYTHONIOENCODING=utf-8 LANG=C.UTF-8 LC_ALL=C.UTF-8

status() { echo "$(date '+%F %T') [$NAME] $*" >> "$STATUS_LOG"; }

free_mb=$(df -Pm "$ROOT" | awk 'NR==2 {print $4}')
if [ "${free_mb:-0}" -lt "$MIN_FREE_MB" ]; then
  status "SKIPPED: only ${free_mb} MB free on disk - upload and delete old data (see README)"
  exit 1
fi

exec 9>"$LOCK"
if ! flock -w 21600 9; then
  status "SKIPPED: another scraper held the lock for 6h"
  exit 1
fi

RUN_LOG="$LOG_DIR/${NAME}_$(date +%F_%H%M).log"
status "start (timeout $TIMEOUT)"
start=$(date +%s)
timeout --kill-after=2m "$TIMEOUT" "${CMD[@]}" >> "$RUN_LOG" 2>&1
rc=$?
dur=$(( ($(date +%s) - start) / 60 ))

# Nothing else on this server uses Chrome, so anything left is an orphan.
pkill -9 -f 'undetected_chromedriver|chromedriver' 2>/dev/null
pkill -9 -f '(google-chrome|chrome).*--headless' 2>/dev/null

case $rc in
  0)       result="OK in ${dur} min" ;;
  124|137) result="TIMEOUT after ${dur} min (see $RUN_LOG)" ;;
  *)       result="FAILED rc=$rc after ${dur} min (see $RUN_LOG)" ;;
esac

# Optional: push the CSVs to GitHub (GIT_PUSH=1 in .env). Still inside the lock,
# so two pushes never overlap; also after a failure (partial data is saved).
# The push result goes on the same status line, after the run result, so the
# last line per scraper in log.txt still starts with OK / FAILED / TIMEOUT.
if [ "${GIT_PUSH:-0}" = 1 ]; then
  if timeout 10m "$ROOT/bin/push_data.sh" "$NAME" >> "$RUN_LOG" 2>&1; then
    result="$result · $(tail -n 1 "$RUN_LOG")"
  else
    result="$result · PUSH FAILED (see $RUN_LOG)"
  fi
fi
status "$result"
exit $rc
