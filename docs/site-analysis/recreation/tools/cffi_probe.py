"""curl_cffi scrapeability probe: homepage-first, then each target URL.

usage: uv run --project <repo> python -I cffi_probe.py URL [URL ...] [--impersonate chrome]
Prints one JSON line per URL.
"""
import json
import re
import sys
import time
from urllib.parse import urlsplit

from curl_cffi import requests

BLOCK_MARKERS = [
    "just a moment", "cf-chl", "challenge-platform", "attention required",
    "captcha", "datadome", "px-captcha", "perimeterx", "access denied",
    "request unsuccessful", "incapsula", "akamai", "bot detection",
    "erişiminiz engellendi", "robot olmadığınızı",
]
PRICE_RE = re.compile(
    r"(\d{1,3}(?:[.\s]\d{3})*,\d{2}\s*(?:TL|₺))|(₺\s*\d[\d.,]*)|(\d[\d.,]*\s*TL\b)"
    r"|(\"price\"\s*:\s*\"?\d)|(\"salePrice\"\s*:\s*\d)|(\"lowPrice\"\s*:\s*\"?\d)"
)


def probe(session, url):
    t = time.time()
    try:
        r = session.get(url, timeout=30, allow_redirects=True)
    except Exception as e:  # noqa: BLE001
        return {"url": url, "error": f"{type(e).__name__}: {e}"[:200]}
    body = r.text or ""
    low = body.lower()
    return {
        "url": url,
        "status": r.status_code,
        "final_url": str(r.url),
        "bytes": len(r.content),
        "secs": round(time.time() - t, 1),
        "server": r.headers.get("server"),
        "cf_mitigated": r.headers.get("cf-mitigated"),
        "block_markers": [m for m in BLOCK_MARKERS if m in low][:5],
        "price_hits": len(PRICE_RE.findall(body)),
        "jsonld_offers": low.count('"offers"'),
        "next_data": "__next_data__" in low or "__nuxt" in low,
        "title": (re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I) or [None, ""])[1].strip()[:100],
    }


def main(argv):
    imp = "chrome"
    if "--impersonate" in argv:
        i = argv.index("--impersonate")
        imp = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    sessions = {}
    for url in argv:
        host = urlsplit(url).netloc
        if host not in sessions:
            s = requests.Session(impersonate=imp)
            s.headers.update({"Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"})
            home = f"{urlsplit(url).scheme}://{host}/"
            res = probe(s, home)
            res["homepage"] = True
            print(json.dumps(res, ensure_ascii=False), flush=True)
            sessions[host] = s
            time.sleep(1.5)
            if home == url:
                continue
        print(json.dumps(probe(sessions[host], url), ensure_ascii=False), flush=True)
        time.sleep(1.5)


if __name__ == "__main__":
    main(sys.argv[1:])
