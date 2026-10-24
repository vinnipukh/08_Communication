"""
Start the Hepsiemlak scraper for one person (shard) as a detached background process.

Used by hepsiemlak_<name>.py: pressing Run on that file in any IDE (or ``python hepsiemlak_<name>.py``)
starts ``scraper.py --shard <name>`` headless in the background with the same Python interpreter and
returns right away; the crawl keeps running after the IDE run / terminal ends. Extra command-line
arguments are passed through (e.g. ``--max-listings 100`` for a test).

- Installs CloakBrowser into that interpreter if it is missing (the ~200 MB browser build then downloads
  on the scraper's first launch).
- Refuses to start a second crawl for the same person while one is still running (pid file).
- Pressing Run again the same day continues an interrupted crawl (adds ``--resume`` when today's
  checkpoint exists) and refuses to restart a finished one (today's CSV exists, checkpoint gone), so a
  second click never overwrites the day's data.
- Log: checkpoints/hepsiemlak_<name>_<timestamp>.log (gitignored), next to the scraper checkpoint.
"""

import importlib.util
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE_DIR = HERE / "checkpoints"
DATA_DIR = HERE.parents[2] / "Datas" / "04_Housing" / "Hepsiemlak"
REQUIREMENT = "cloakbrowser==0.6.3"


def _alive(pid: int) -> bool:
    """True when ``pid`` is a running Python process (guards against a reused pid)."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:  # STILL_ACTIVE
                return False
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buf))
            kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
            return "python" in Path(buf.value).name.lower()
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _has_rows(csv_path: Path) -> bool:
    with open(csv_path, encoding="utf-8") as fh:
        return len(fh.readlines(64 * 1024)) > 1


def _ensure_cloakbrowser():
    if importlib.util.find_spec("cloakbrowser") is None:
        print(f"Installing {REQUIREMENT} into {sys.executable} ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", REQUIREMENT])


def _spawn(cmd: list[str], log_file) -> subprocess.Popen:
    kwargs = dict(cwd=HERE, stdin=subprocess.DEVNULL, stdout=log_file, stderr=subprocess.STDOUT, close_fds=True)
    if os.name != "nt":
        return subprocess.Popen(cmd, start_new_session=True, **kwargs)
    # CREATE_NO_WINDOW, not DETACHED_PROCESS: the scraper gets its own hidden console, which the browser
    # driver and browser inherit; with no console at all Windows opens a visible one for them
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    try:  # leave the IDE's / terminal's job object so closing it does not kill the crawl
        return subprocess.Popen(cmd, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kwargs)
    except OSError:  # job does not allow breakaway
        return subprocess.Popen(cmd, creationflags=flags, **kwargs)


def start(shard: str, extra_args: list[str] | None = None) -> int:
    args = sys.argv[1:] if extra_args is None else extra_args
    STATE_DIR.mkdir(exist_ok=True)
    pid_file = STATE_DIR / f"hepsiemlak_{shard}.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().split()[0])
        except (ValueError, IndexError):
            pid = 0
        if pid and _alive(pid):
            print(f"Hepsiemlak ({shard}) is already running (pid {pid}); not starting another one.")
            return pid
    # same file names as scraper.py: <output>.csv in DATA_DIR, <output stem>.json in STATE_DIR
    output = args[args.index("--output") + 1] if "--output" in args[:-1] else f"{date.today().isoformat()}_{shard}.csv"
    csv_path, ckpt_path = DATA_DIR / output, STATE_DIR / (Path(output).stem + ".json")
    if "--resume" not in args:
        if ckpt_path.exists() and csv_path.exists():
            print(f"Continuing the interrupted crawl in {csv_path.name}.")
            args = [*args, "--resume"]
        elif csv_path.exists() and _has_rows(csv_path):  # header-only = killed before the first page
            print(f"{csv_path.name} is already complete for today; not starting again.")
            print("(To redo the day on purpose, delete or rename that file first.)")
            return 0
    _ensure_cloakbrowser()
    log_path = STATE_DIR / f"hepsiemlak_{shard}_{datetime.now():%Y-%m-%d_%H%M%S}.log"
    cmd = [sys.executable, "-u", str(HERE / "scraper.py"), "--shard", shard, *args]
    with open(log_path, "ab") as log_file:
        proc = _spawn(cmd, log_file)
    pid_file.write_text(str(proc.pid))
    print(f"Hepsiemlak ({shard}) started in the background (pid {proc.pid}).")
    print(f"Log:    {log_path}")
    print("Output: InflationItems/Datas/04_Housing/Hepsiemlak/ (today's file for this person)")
    print("You can close this window; the crawl keeps running.")
    return proc.pid
