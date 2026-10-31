#!/usr/bin/env bash
# Push this server's new/changed CSVs to GitHub:  push_data.sh [label]
#
# - commits on top of the latest origin/main through a throwaway index, so the
#   sparse working tree, local main and other writers' commits are never touched
# - only adds/updates CSVs written since the last successful push (.last_push);
#   never commits deletions (export_data.sh --delete / disk cleanup stay local)
# - retries when another writer (Emlakjet / Beymen tech workflows) pushed first
# Called by run_scraper.sh when GIT_PUSH=1 in .env (needs the deploy key, see README).
set -u

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"  # <repo-root>: bin/ lives directly under it
# Only the folders this server writes; the other 04_Housing stores come from Actions or people.
DATA=(
  InflationItems/Datas/08_Communication
  InflationItems/Datas/09_Recreation
  InflationItems/Datas/04_Housing/IGDAS
  InflationItems/Datas/04_Housing/Baskentgaz
  InflationItems/Datas/04_Housing/Izmirgaz
  InflationItems/Datas/04_Housing/ISKI
)
STAMP="$ROOT/.last_push"
BRANCH=main
LABEL="${1:-manual}"

cd "$ROOT" || exit 1
export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=30"
[ -f "$STAMP" ] || touch -d '1 day ago' "$STAMP"

# taken before the scan: a CSV written while we push is picked up next time
WORK=$(mktemp -d "${TMPDIR:-/tmp}/push_data.XXXXXX")
trap 'rm -rf "$WORK"' EXIT
NEXT="$WORK/stamp"
touch "$NEXT"
INDEX="$WORK/index"  # must not exist yet: git rejects an empty index file

mapfile -t DIRS < <(for d in "${DATA[@]}"; do [ -d "$d" ] && echo "$d"; done)
mapfile -t FILES < <([ ${#DIRS[@]} -gt 0 ] && find "${DIRS[@]}" -type f -name '*.csv' -newer "$STAMP" | sort)
if [ ${#FILES[@]} -eq 0 ]; then
  echo "push: no new CSVs since $(date -r "$STAMP" '+%F %T')"
  exit 0
fi

for attempt in 1 2 3; do
  if git fetch -q origin "$BRANCH"; then
    base=$(git rev-parse "origin/$BRANCH")
    rm -f "$INDEX"
    GIT_INDEX_FILE="$INDEX" git read-tree "$base"
    GIT_INDEX_FILE="$INDEX" git -c core.safecrlf=false update-index --add -- "${FILES[@]}"   # applies .gitattributes (CSV stored with LF)
    tree=$(GIT_INDEX_FILE="$INDEX" git write-tree --missing-ok)       # blob:none clone: don't fetch every old blob
    if [ "$tree" = "$(git rev-parse "$base^{tree}")" ]; then
      echo "push: ${#FILES[@]} CSV(s) already identical on origin"
      mv "$NEXT" "$STAMP"
      exit 0
    fi
    commit=$(git commit-tree "$tree" -p "$base" -m "chore(data): $LABEL scrape $(date +%F) (server)")
    if git push -q origin "$commit:refs/heads/$BRANCH"; then
      echo "push: $(git diff-tree --no-commit-id --name-only -r "$commit" | wc -l) file(s) -> $BRANCH ${commit:0:7}"
      mv "$NEXT" "$STAMP"
      exit 0
    fi
  fi
  sleep $((attempt * 20))
done
echo "push: FAILED after 3 attempts (${#FILES[@]} CSV(s) kept for the next run)"
exit 1
