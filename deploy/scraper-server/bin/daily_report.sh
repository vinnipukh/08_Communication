#!/usr/bin/env bash
# Send a Telegram summary of one day's scraper runs:  daily_report.sh [tech|telecom|recreation] [YYYY-MM-DD]
#
# - tech (default): the 6 tech product scrapers and the TÜİK 04 server jobs, one line each
# - telecom: the telecom/internet/streaming/repair jobs, one line each with the
#   row total of all their sources, plus a line per source that is missing or dropped
# - recreation: the four TÜİK 09 jobs (rec_small, rec_medium, rec_shops, rec_dr), same layout as telecom
# - reads the status lines run_scraper.sh wrote to log.txt (default: today)
# - counts the rows in each CSV and flags a big drop vs the day before
# - needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
# - one status line per run in log.txt ("OK in N min · push: …"); the push result never hides the run result
set -u

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"  # <repo-root>: bin/ lives directly under it
DATAS="$ROOT/InflationItems/Datas"
TECH_DATA="$DATAS/08_Communication"
STATUS_LOG="$ROOT/log.txt"
LOCK=/tmp/scraper.lock
DROP_PCT=20   # warn when a CSV has this many % fewer rows than the day before

if [ -f "$ROOT/.env" ]; then
  set -a; . "$ROOT/.env"; set +a
fi

GROUP=tech
case "${1:-}" in tech|telecom|recreation) GROUP=$1; shift ;; esac
DAY="${1:-$(date +%F)}"
PREV=$(date -d "$DAY -1 day" +%F)

status() { echo "$(date '+%F %T') [report] $*" >> "$STATUS_LOG"; }

# <run_scraper.sh name>:<space-separated CSV path prefixes under DATAS> (rows are summed)
TECH=(
  samsung:08_Communication/Samsung/samsung
  huawei:08_Communication/Huawei/huawei
  pozitif:08_Communication/PozitifTeknoloji/pozitifTeknoloji
  dr:08_Communication/DR/dr
  beymen:08_Communication/Beymen/beymen
  vatan:08_Communication/VatanComputer/vatan_computer
  "naturalgas:04_Housing/IGDAS/igdas 04_Housing/Baskentgaz/baskentgaz 04_Housing/Izmirgaz/izmirgaz"
  iski:04_Housing/ISKI/iski
)
# Flat 08 layout: every source has its own folder under TECH_DATA; internet and repair files
# share folders with other jobs and carry an _internet_ / _repair_ infix.
# <run_scraper.sh name>:<space-separated CSV path prefixes under TECH_DATA>
TELECOM=(
  "telecom:Turkcell/turkcell Vodafone/vodafone TurkTelekom/turktelekom NetGSM/netgsm"
  "internet:Kablonet/kablonet_internet Milleni/milleni_internet Superonline/superonline_internet TurkNet/turknet_internet TurkTelekom/turktelekom_internet Vodafone/vodafone_internet"
  "streaming:AmazonPrime/prime AppleTVPlus/appletv DisneyPlus/disney GAIN/gain HBOMax/hbomax MUBI/mubi Netflix/netflix Spotify/spotify TVPlus/tvplus Tabii/tabii Tivibu/tivibu YouTubePremium/youtube"
  "repair:Apple/apple_repair Samsung/samsung_repair Huawei/huawei_repair GSMIletisim/gsmiletisim_repair"
)

# TÜİK 09: one source folder per store under Datas/09_Recreation, file <prefix>_<day>.csv.
# The run_group.py bundles (small / medium / shops) and DR are the run_scraper.sh jobs rec_*.
# <run_scraper.sh name>:<space-separated CSV path prefixes under Datas/09_Recreation>
RECREATION=(
  "rec_small:Avansas/avansas Diyanet/diyanet HisarTurizm/hisar_turizm MACFit/macfit Nezih/nezih Korayspor/korayspor Milli_Piyango/milli_piyango IstanbulAkvaryum/istanbulakvaryum KidZania/kidzania AnkaraVHO/ankara_vho IVHO/ivho VetArt/vetart SporIstanbul/sporistanbul ArnavutkoyBelediyesi/arnavutkoy Grupanya/grupanya"
  "rec_medium:Kitapyurdu/kitapyurdu Jolly/jolly SPX/spx Biletinial/biletinial DugunBuketi/dugunbuketi DugunCom/dugun_com Petchef/petchef TemizMama/temizmama"
  "rec_shops:Petlebi/petlebi ToyzzShop/toyzzshop Petzzshop/petzzshop Decathlon/decathlon Zuhal_Muzik/zuhal_muzik"
  "rec_dr:DR/dr"
)

rows() { [ -f "$1" ] && echo $(( $(wc -l < "$1") - 1 )); }  # minus the header

# a source's CSV for one day: <prefix>_<day>.csv (bounded test runs write *_limit.csv, never counted)
day_csv() { [ -f "$BASE/$1_$2.csv" ] && echo "$BASE/$1_$2.csv"; }

# summed rows of <day> over the prefixes under DATAS; empty when none of the CSVs exists
sum_rows() {
  local day=$1 p n total=""; shift
  for p in "$@"; do
    n=$(rows "$DATAS/${p}_$day.csv") && total=$(( ${total:-0} + n ))
  done
  echo "$total"
}

dropped() {  # now before -> true when now is DROP_PCT % or more below before
  [ -n "$2" ] && [ "$2" -gt 0 ] && [ $(( $1 * 100 )) -lt $(( $2 * (100 - DROP_PCT) )) ]
}

# Sets icon/note from the last log.txt status line of job $1 (icon empty when it ended OK).
# The line is "<result>[ · <push result>]", result = OK in … / FAILED … / TIMEOUT … / SKIPPED … / start …
job_status() {
  local last push
  last=$(grep -E "^$DAY [0-9:]+ \[$1\] " "$STATUS_LOG" 2>/dev/null | tail -n 1 | cut -d' ' -f4-)
  push=""
  [[ "$last" == *" · "* ]] && { push=${last#* · }; last=${last%% · *}; }
  icon=""; note=""; took=""; pushfail=""
  [[ "$push" == *FAILED* ]] && pushfail=1
  case "$last" in
    "OK in"*)
      took=${last#OK in }
      [ -n "$pushfail" ] && took+=" · PUSH FAILED" ;;
    "")
      icon="❌"; note="did not run" ;;
    start*)
      if flock -n "$LOCK" true 2>/dev/null; then
        icon="❌"; note="started but never finished (killed?)"
      else
        icon="⏳"; note="still running"
      fi ;;
    *)
      icon="❌"; note="${last%% (see*}"   # FAILED / TIMEOUT / SKIPPED
      # telecom scrapers log the sources that failed in their run log
      local runlog=${last##*(see }; runlog=${runlog%)}
      local failed
      failed=$(grep -ho 'failed operators: .*' "$runlog" 2>/dev/null | tail -n 1)
      [ -n "$failed" ] && note+=" · $failed"
      [ -n "$pushfail" ] && note+=" · PUSH FAILED" ;;
  esac
}

ok=0
body=""
BASE="$TECH_DATA"   # where day_csv looks (telecom): flat 08 layout
[ "$GROUP" = recreation ] && BASE="$DATAS/09_Recreation"

if [ "$GROUP" = tech ]; then
  title="Scrapers"
  total=${#TECH[@]}
  for entry in "${TECH[@]}"; do
    name=${entry%%:*}
    job_status "$name"
    if [ -z "$icon" ]; then
      now=$(sum_rows "$DAY" ${entry#*:})
      before=$(sum_rows "$PREV" ${entry#*:})
      if [ -z "$now" ] || [ "$now" -le 0 ]; then
        icon="❌"; note="OK but the CSV is empty or missing"
      elif [ -n "$pushfail" ] || dropped "$now" "$before"; then
        icon="⚠️"; note="$now rows (yesterday $before) · $took"
      else
        icon="✅"; note="$now rows · $took"; ok=$(( ok + 1 ))
      fi
    fi
    body+="$icon $name: $note"$'\n'
  done
else
  # telecom and recreation: one line per job with the row total of all its sources, plus a line
  # for each source that is missing or dropped
  if [ "$GROUP" = recreation ]; then
    title="Recreation (09)"; JOBS=("${RECREATION[@]}")
  else
    title="Telecom"; JOBS=("${TELECOM[@]}")
  fi
  total=${#JOBS[@]}
  for entry in "${JOBS[@]}"; do
    name=${entry%%:*}
    job_status "$name"
    sum=0; n=0; problems=""
    for prefix in ${entry#*:}; do
      src=${prefix%%/*}
      # a source counts as expected when it wrote a CSV in the last 7 days
      expected=""
      for i in 0 1 2 3 4 5 6 7; do
        [ -n "$(day_csv "$prefix" "$(date -d "$DAY -$i day" +%F)")" ] && { expected=1; break; }
      done
      [ -n "$expected" ] || continue
      now=$(rows "$(day_csv "$prefix" "$DAY")")
      before=$(rows "$(day_csv "$prefix" "$PREV")")
      if [ -z "$now" ] || [ "$now" -le 0 ]; then
        problems+="    ❌ $src: no rows today"$'\n'
      else
        sum=$(( sum + now )); n=$(( n + 1 ))
        dropped "$now" "$before" && problems+="    ⚠️ $src: $now rows (yesterday $before)"$'\n'
      fi
    done
    if [ -z "$icon" ]; then
      if [ "$n" -eq 0 ]; then
        icon="❌"; note="OK but no CSV written"
      elif [ -n "$problems" ] || [ -n "$pushfail" ]; then
        icon="⚠️"; note="$sum rows from $n sources · $took"
      else
        icon="✅"; note="$sum rows from $n sources · $took"; ok=$(( ok + 1 ))
      fi
    elif [ "$n" -gt 0 ]; then
      note+=" · $sum rows from $n sources"
    fi
    body+="$icon $name: $note"$'\n'"$problems"
  done
fi

head="✅"; [ "$ok" -lt "$total" ] && head="⚠️"
disk=$(grep -E "^$DAY [0-9:]+ \[cleanup\] " "$STATUS_LOG" 2>/dev/null | tail -n 1 | sed -n 's/.*free \([0-9]*\) MB.*/\1/p')
msg="$head $title $DAY: $ok/$total OK"$'\n\n'"$body"
[ -n "$disk" ] && msg+=$'\n'"💾 free disk: $(( disk / 1024 )) GB"

# REPORT_DRY_RUN=1: print the message instead of sending it (to check a report by hand)
if [ -n "${REPORT_DRY_RUN:-}" ]; then
  echo "$msg"
  exit 0
fi

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
  status "NOT SENT: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
  exit 1
fi

resp=$(curl -sS -m 30 --retry 3 --retry-delay 10 \
  --data-urlencode "chat_id=$TELEGRAM_CHAT_ID" \
  --data-urlencode "text=$msg" \
  "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" 2>&1)
if [[ "$resp" == *'"ok":true'* ]]; then
  status "$GROUP sent ($ok/$total OK)"
else
  status "$GROUP NOT SENT: ${resp:0:200}"
  exit 1
fi
