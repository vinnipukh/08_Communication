"""Run a group of TÜİK 09 scrapers one after another from a single cron job.

    run_group.py small|medium|shops [--only name[,name]] [--list]

The cron server runs one job at a time, and the 09 scrapers are many and mostly short, so they
are bundled here instead of one cron entry each. Every scraper runs as its own process with
its own time limit; a failing or hung scraper is logged and the next one still runs. The
exit code is 1 when any scraper failed, so the server's status line (log.txt) shows FAILED
and the run log names the scrapers. Output files are written by the scrapers themselves.

DR (about an hour) is its own job and is not part of a group.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (name, script relative to this folder, extra arguments, time limit in minutes). Limits are ~4x
# the durations measured on a developer PC, because the cron server's CPU is slower.
GROUPS = {
    # < 2 min each on a PC
    "small": [
        ("avansas", "Avansas/avansas_scraper.py", [], 20),
        ("diyanet", "Diyanet/diyanet_umre_scraper.py", [], 20),  # OCR, ~1 min, ~0.7 GB RAM
        ("hisar", "HisarTurizm/hisar_turizm.py", [], 15),
        ("macfit", "MACFit/macfit_scraper.py", [], 15),
        ("nezih", "Nezih/nezih_scraper.py", [], 15),
        ("korayspor", "Sports/koraysport_scraper.py", [], 10),
        ("milli_piyango", "Milli_Piyango/milli_piyango_scraper.py", [], 10),
        ("istanbulakvaryum", "IstanbulAkvaryum/istanbulakvaryum_scraper.py", [], 10),
        ("kidzania", "KidZania/kidzania_scraper.py", [], 10),
        ("ankara_vho", "AnkaraVHO/ankara_vho_scraper.py", [], 15),  # OCR, ~15 s, ~0.6 GB RAM
        ("ivho", "IVHO/ivho_scraper.py", [], 10),
        ("vetart", "VetArt/vetart_scraper.py", [], 10),
        ("sporistanbul", "SporIstanbul/sporistanbul_scraper.py", [], 10),
        ("arnavutkoy", "ArnavutkoyBelediyesi/arnavutkoy_scraper.py", [], 10),
        ("grupanya", "Grupanya/grupanya_scraper.py", [], 20),
    ],
    # 3-6 min each on a PC
    "medium": [
        ("kitapyurdu", "Kitapyurdu/kitapyurdu_scraper.py", [], 30),
        ("jollytur", "Jollytur/jolly.py", [], 30),
        ("spx", "Sports/spx_scraper.py", [], 30),
        ("biletinial", "Biletinial/biletinial_scraper.py", [], 40),
        ("dugunbuketi", "DugunBuketi/dugunbuketi_scraper.py", [], 40),
        ("dugun_com", "DugunCom/dugun_com_scraper.py", [], 30),
        ("petchef", "Petchef/petchef_scraper.py", [], 30),
        ("temizmama", "TemizMama/temizmama_scraper.py", [], 30),
    ],
    # 8-15 min each on a PC
    "shops": [
        ("petlebi", "petlebi/petlebi_scraper.py", [], 40),
        ("toyzzshop", "Toyzzshop/toyzzshop_scraper.py", [], 40),
        ("petzzshop", "Petzzshop/petzzshop_scraper.py", [], 45),
        ("decathlon", "Sports/decathlon_scraper.py", [], 60),
        ("zuhal_muzik", "Zuhal_Muzik/zuhal_muzik_scraper.py", [], 60),
    ],
}


def run_one(name, script, args, limit_minutes):
    path = HERE / script
    started = time.time()
    print(f"[group] ---- {name}: start (limit {limit_minutes} min)", flush=True)

    if not path.is_file():
        print(f"[group] {name}: FAILED, {script} not found", flush=True)
        return "missing script", 0

    try:
        result = subprocess.run(
            [sys.executable, "-u", str(path), *args],
            timeout=limit_minutes * 60,
        )
    except subprocess.TimeoutExpired:
        minutes = (time.time() - started) / 60
        print(f"[group] {name}: TIMEOUT after {minutes:.1f} min", flush=True)
        return "timeout", minutes

    minutes = (time.time() - started) / 60

    if result.returncode != 0:
        print(f"[group] {name}: FAILED rc={result.returncode} after {minutes:.1f} min", flush=True)
        return f"rc={result.returncode}", minutes

    print(f"[group] {name}: OK in {minutes:.1f} min", flush=True)
    return None, minutes


def main():
    parser = argparse.ArgumentParser(description="Run a group of TÜİK 09 scrapers in sequence.")
    parser.add_argument("group", choices=sorted(GROUPS))
    parser.add_argument("--only", help="Comma-separated scraper names of the group (bounded test runs).")
    parser.add_argument("--list", action="store_true", help="Print the group and exit.")
    args = parser.parse_args()

    entries = GROUPS[args.group]

    if args.only:
        wanted = {item.strip() for item in args.only.split(",") if item.strip()}
        unknown = wanted - {entry[0] for entry in entries}

        if unknown:
            parser.error(f"not in group {args.group}: {', '.join(sorted(unknown))}")

        entries = [entry for entry in entries if entry[0] in wanted]

    if args.list:
        for name, script, extra, limit in entries:
            print(f"{name}: {script} {' '.join(extra)} (limit {limit} min)")
        return

    started = time.time()
    failures = []

    for name, script, extra, limit in entries:
        problem, _minutes = run_one(name, script, extra, limit)

        if problem:
            failures.append(f"{name} ({problem})")

    total = (time.time() - started) / 60
    print(f"[group] {args.group}: {len(entries) - len(failures)}/{len(entries)} OK in {total:.1f} min", flush=True)

    if failures:
        print(f"[group] failed scrapers: {', '.join(failures)}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
