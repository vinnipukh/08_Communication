#!/usr/bin/env bash
# One-time (re-runnable) setup of a Hepsiemlak shard server (Ubuntu 22.04/24.04, run as root):
#   bash deploy/hepsiemlak-server/setup.sh
# Layout: <repo-root>/{deploy/hepsiemlak-server, InflationItems/Codes/04_Housing/Hepsiemlak}, either a git
# checkout or the tarball described in deploy/hepsiemlak-server/README.md. Installs no cron job (see README).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CODE="$ROOT/InflationItems/Codes/04_Housing/Hepsiemlak"
[ -f "$CODE/scraper.py" ] || { echo "scraper not found under $ROOT"; exit 1; }
cd "$ROOT"

# As root: time zone and system packages. As a normal user (no sudo): both are skipped; the browser
# libraries and xvfb must already be installed (checked below), everything else lives under <repo-root>.
if [ "$(id -u)" -eq 0 ]; then
  echo "== 1/4 time zone -> Europe/Istanbul"
  timedatectl set-timezone Europe/Istanbul || true

  echo "== 2/4 system packages (browser libraries, xvfb as a headed fallback)"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q
  apt-get install -y -q curl ca-certificates cron util-linux procps coreutils xvfb \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 libgbm1 libxcomposite1 libxdamage1 \
    libxrandr2 libxfixes3 libpango-1.0-0 libcairo2 libxshmfence1 fonts-liberation
  apt-get install -y -q libasound2 2>/dev/null || apt-get install -y -q libasound2t64
else
  echo "== 1-2/4 not root: skipping time zone and apt; checking browser libraries"
  for l in libnss3 libatk-bridge-2.0 libcups libxkbcommon libgbm libasound libpango-1.0; do
    ldconfig -p | grep -q "$l" || echo "WARNING: $l missing (ask an admin to install the packages listed in this script)"
  done
fi

echo "== 3/4 Python 3.11 venv + cloakbrowser (uv)"
UV="$HOME/.local/bin/uv"
[ -x "$UV" ] || curl -LsSf https://astral.sh/uv/install.sh | sh
[ -x venv/bin/python ] || "$UV" venv --python 3.11 venv
REQ="$(grep -o 'cloakbrowser==[0-9.]*' "$CODE/launcher.py" | head -1)"
"$UV" pip install --python venv/bin/python "$REQ"

echo "== 4/4 run script"
mkdir -p "$ROOT/bin" "$ROOT/server_logs" "$ROOT/InflationItems/Datas/04_Housing/Hepsiemlak"
cp "$HERE/run_shard.sh" "$ROOT/bin/run_shard.sh"
sed -i 's/\r$//' "$ROOT/bin/run_shard.sh"
chmod +x "$ROOT/bin/run_shard.sh"

echo
echo "Setup done. Public IP: $(curl -fsS https://api.ipify.org || echo '?')"
free -m | head -2
df -h "$ROOT" | tail -1
echo "Bounded test:  bin/run_shard.sh <zelal|dani|neslihan|ekin> --max-listings 100 --output test.csv"
