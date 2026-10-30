"""Simple browser fallback: SeleniumBase UC mode, homepage first, then each URL.

usage: uv run python -I -X utf8 sb_probe.py [--headed] URL [URL ...]
Prints one JSON line per URL: title, html size, price hits, challenge guess, and XHR/fetch
JSON endpoints seen via the Performance API (candidate APIs).
"""
import json
import re
import sys
import time
from urllib.parse import urlsplit

from seleniumbase import SB

PRICE_RE = re.compile(r"(\d{1,3}(?:[.\s]\d{3})*,\d{2}\s*(?:TL|₺))|(₺\s*\d[\d.,]*)|(\d[\d.,]*\s*(?:TL|₺|EUR|USD|€))")
CHALLENGE = ["just a moment", "attention required", "access denied", "captcha", "robot", "security check",
             "bir dakika", "pardon our interruption"]
XHR_JS = """return performance.getEntriesByType('resource')
  .filter(e => e.initiatorType === 'xmlhttprequest' || e.initiatorType === 'fetch')
  .map(e => e.name).slice(-60);"""


def main(argv):
    headed = "--headed" in argv
    urls = [a for a in argv if a != "--headed"]
    home = f"{urlsplit(urls[0]).scheme}://{urlsplit(urls[0]).netloc}/"
    with SB(uc=True, headless2=not headed, locale="tr") as sb:
        for i, url in enumerate([home] + urls):
            try:
                sb.uc_open_with_reconnect(url, 4)
                time.sleep(3)
                html = sb.get_page_source()
                title = sb.get_title()[:90]
                xhr = [u for u in sb.execute_script(XHR_JS) if not re.search(
                    r"google|facebook|doubleclick|analytics|hotjar|clarity|criteo|insider|tiktok|yandex|segment", u)]
                rec = {"i": i, "url": url, "title": title, "bytes": len(html),
                       "price_hits": len(PRICE_RE.findall(sb.get_text("body") if sb.is_element_present("body") else "")),
                       "challenged": any(c in title.lower() for c in CHALLENGE), "xhr": xhr[:20]}
            except Exception as e:  # noqa: BLE001
                rec = {"i": i, "url": url, "error": f"{type(e).__name__}: {e}"[:200]}
            print(json.dumps(rec, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
