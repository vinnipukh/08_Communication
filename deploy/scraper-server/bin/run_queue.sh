#!/usr/bin/env bash
# Run the whole daily job list back to back, one after the other:  run_queue.sh [item ...]
#
# - one cron line (00:30) starts it; each job starts the moment the previous one has finished
# - item = a scraper name for run_scraper.sh, "cleanup", or "report:<tech|telecom|recreation>"
# - no items given = DEFAULT_QUEUE below; items given = just those (handy for a test)
# - a failed / timed-out job never stops the queue (run_scraper.sh already logs it and has its own timeout)
# - own lock: a second queue (cron firing while the last one still runs) exits instead of overlapping
# - RUNNER / REPORTER / CLEANER can be overridden to dry-run the queue without scraping
set -u

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"  # <repo-root>: bin/ lives directly under it
STATUS_LOG="$ROOT/log.txt"
LOCK="$ROOT/.queue.lock"
RUNNER="${RUNNER:-$ROOT/bin/run_scraper.sh}"
REPORTER="${REPORTER:-$ROOT/bin/daily_report.sh}"
CLEANER="${CLEANER:-$ROOT/bin/cleanup.sh}"

# Same order as the old cron table; a report follows the jobs it summarises.
DEFAULT_QUEUE=(
  cleanup
  samsung huawei xiaomi pozitif dr naturalgas iski beymen vatan
  report:tech
  telecom internet streaming repair
  report:telecom
  rec_small rec_medium rec_shops rec_dr
  report:recreation
)
if [ $# -gt 0 ]; then QUEUE=("$@"); else QUEUE=("${DEFAULT_QUEUE[@]}"); fi

status() { echo "$(date '+%F %T') [queue] $*" >> "$STATUS_LOG"; }

exec 8>"$LOCK"
if ! flock -n 8; then
  status "SKIPPED: the previous queue is still running"
  exit 1
fi

status "start (${#QUEUE[*]} items)"
start=$(date +%s)
for item in "${QUEUE[@]}"; do
  # 8>&- : children must not inherit the queue lock (an orphaned Chrome would hold it)
  case "$item" in
    cleanup)  "$CLEANER" >> "$STATUS_LOG" 2>&1 8>&- ;;
    report:*) "$REPORTER" "${item#report:}" >> "$STATUS_LOG" 2>&1 8>&- ;;
    *)        "$RUNNER" "$item" >> "$STATUS_LOG" 2>&1 8>&- ;;
  esac
done
status "done in $(( ($(date +%s) - start) / 60 )) min"
