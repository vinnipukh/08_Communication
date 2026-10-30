"""Sustained curl_cffi test + anti-bot vendor detection + API hints.

usage:
  uv run python -I -X utf8 deep_probe.py [--n 10] [--delay 2] [--impersonate chrome] URL [URL ...]
  uv run python -I -X utf8 deep_probe.py --api URL [URL ...]     # test JSON/XHR endpoints

Visits the homepage of the first URL's host first, then cycles through the URLs until
--n requests are made. Prints one JSON line per request and a summary line per host.
"""
import json
import re
import sys
import time
from urllib.parse import urlsplit

from curl_cffi import requests

PRICE_RE = re.compile(
    r"(\d{1,3}(?:[.\s]\d{3})*,\d{2}\s*(?:TL|₺))|(₺\s*\d[\d.,]*)|(\d[\d.,]*\s*(?:TL|₺|EUR|USD|€|\$))"
    r"|(\"(?:price|salePrice|lowPrice|shownPrice|sellingPrice|discountedPrice)\"\s*:\s*\"?\d)"
)
CHALLENGE_TITLES = ["just a moment", "attention required", "access denied", "erişim engellendi",
                    "request unsuccessful", "pardon our interruption", "robot", "captcha", "security check",
                    "bir dakika", "lütfen bekleyin"]

# (vendor, where, pattern) where in {"cookie", "header", "html"}
VENDOR_RULES = [
    ("Cloudflare", "header", r"^cf-ray$"),
    ("Cloudflare Bot Mgmt", "cookie", r"^__cf_bm$"),
    ("Cloudflare challenge", "cookie", r"^cf_clearance$"),
    ("Cloudflare challenge", "header", r"^cf-mitigated$"),
    ("Cloudflare Turnstile", "html", r"challenges\.cloudflare\.com/turnstile"),
    ("Akamai Bot Manager", "cookie", r"^(_abck|bm_sz|ak_bmsc|bm_sv|bm_mi)$"),
    ("Akamai CDN", "header", r"^(x-akamai-.*|akamai-grn|x-check-cacheable)$"),
    ("AWS WAF", "cookie", r"^aws-waf-token$"),
    ("AWS WAF", "html", r"token\.awswaf\.com|awswaf\.com/.*challenge"),
    ("AWS CloudFront", "header", r"^x-amz-cf-id$"),
    ("DataDome", "cookie", r"^datadome$"),
    ("DataDome", "header", r"^x-datadome.*$"),
    ("PerimeterX/HUMAN", "cookie", r"^_px.*$"),
    ("PerimeterX/HUMAN", "html", r"px-captcha|/px/client|perimeterx"),
    ("Imperva/Incapsula", "cookie", r"^(incap_ses_.*|visid_incap_.*|nlbi_.*|reese84)$"),
    ("Imperva/Incapsula", "header", r"^x-iinfo$"),
    ("Kasada", "header", r"^x-kpsdk-.*$"),
    ("Sucuri", "header", r"^x-sucuri-.*$"),
    ("F5/Shape", "html", r"_imp_apg_r_|shape-security"),
    ("reCAPTCHA (script)", "html", r"google\.com/recaptcha|recaptcha/api\.js"),
    ("hCaptcha (script)", "html", r"hcaptcha\.com/1/api\.js"),
]
API_HINTS = [
    ("Next.js __NEXT_DATA__", r"__NEXT_DATA__"),
    ("Next.js RSC", r"self\.__next_f\.push"),
    ("Nuxt state", r"window\.__NUXT__|__NUXT_DATA__"),
    ("INITIAL_STATE", r"__INITIAL_STATE__|__PRELOADED_STATE__|window\.__APOLLO_STATE__"),
    ("Shopify (/products.json)", r"cdn\.shopify\.com|Shopify\.theme"),
    ("T-Soft (product-loader)", r"product-loader|tsoftstatic|T-Soft"),
    ("Ticimax", r"ticimax|ticiCDN"),
    ("IdeaSoft", r"ideasoft|myideasoft"),
    ("WooCommerce / wp-json", r"wp-json|woocommerce"),
    ("Magento", r"Magento_|mage/cookies"),
    ("SAP Hybris/OCC", r"/occ/v2/|hybris"),
    ("Algolia", r"algolia(net)?\.(net|com)|algoliasearch"),
    ("GraphQL", r"/graphql"),
    ("JSON-LD", r"application/ld\+json"),
]
URL_HINT_RE = re.compile(r"""["'](/(?:api|rest|srv|ajax|service|services|graphql|_next/data|ws|v\d)/[^"'\s<>]{2,120})["']""", re.I)


def detect(resp, body):
    found = set()
    headers = {k.lower(): v for k, v in resp.headers.items()}
    cookies = list(resp.cookies.keys())
    for vendor, where, pat in VENDOR_RULES:
        rx = re.compile(pat, re.I)
        if where == "header" and any(rx.match(h) for h in headers):
            found.add(vendor)
        elif where == "cookie" and any(rx.match(c) for c in cookies):
            found.add(vendor)
        elif where == "html" and rx.search(body):
            found.add(vendor)
    server = headers.get("server", "")
    if "akamaighost" in server.lower():
        found.add("Akamai CDN")
    if "cloudflare" in server.lower():
        found.add("Cloudflare")
    return found


def one(session, url):
    t = time.time()
    try:
        r = session.get(url, timeout=30, allow_redirects=True)
    except Exception as e:  # noqa: BLE001
        return {"url": url, "error": f"{type(e).__name__}: {e}"[:160]}, None, ""
    body = r.text or ""
    title = (re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I) or [None, ""])[1].strip()[:90]
    challenged = (r.status_code in (202, 403, 405, 429, 503) and len(body) < 60000) or \
        any(c in title.lower() for c in CHALLENGE_TITLES) or "cf-mitigated" in {k.lower() for k in r.headers}
    rec = {
        "url": url, "status": r.status_code, "bytes": len(r.content), "secs": round(time.time() - t, 1),
        "ctype": r.headers.get("content-type", "")[:40], "title": title,
        "price_hits": len(PRICE_RE.findall(body)), "challenged": challenged,
    }
    return rec, r, body


def main(argv):
    n, delay, imp, api_mode = 10, 2.0, "chrome", False
    args = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--n":
            n = int(argv[i + 1]); i += 2; continue
        if a == "--delay":
            delay = float(argv[i + 1]); i += 2; continue
        if a == "--impersonate":
            imp = argv[i + 1]; i += 2; continue
        if a == "--api":
            api_mode = True; i += 1; continue
        args.append(a); i += 1
    if not args:
        sys.exit(__doc__)

    s = requests.Session(impersonate=imp)
    s.headers.update({"Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"})
    host = urlsplit(args[0]).netloc
    home = f"{urlsplit(args[0]).scheme}://{host}/"
    vendors, hints, url_hints = set(), set(), set()
    results = []

    seq = [home] + [args[k % len(args)] for k in range(n)] if not api_mode else [home] + args
    for idx, url in enumerate(seq):
        rec, r, body = one(s, url)
        rec["i"] = idx
        if r is not None:
            vendors |= detect(r, body)
            if "html" in rec["ctype"] or body.lstrip().startswith("<"):
                for name, pat in API_HINTS:
                    if re.search(pat, body, re.I):
                        hints.add(name)
                for m in URL_HINT_RE.findall(body):
                    url_hints.add(m)
            if api_mode and idx > 0:
                try:
                    data = r.json()
                    rec["json"] = True
                    rec["json_keys"] = list(data.keys())[:12] if isinstance(data, dict) else f"list[{len(data)}]"
                except Exception:  # noqa: BLE001
                    rec["json"] = False
        results.append(rec)
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        time.sleep(delay)

    ok = [x for x in results[1:] if x.get("status") == 200 and not x.get("challenged")]
    first_block = next((x["i"] for x in results if x.get("challenged") or x.get("error")), None)
    print(json.dumps({
        "SUMMARY": host, "impersonate": imp, "requests": len(results), "ok_after_home": f"{len(ok)}/{len(results) - 1}",
        "first_block_at": first_block, "vendors": sorted(vendors), "api_hints": sorted(hints),
        "url_hints": sorted(url_hints)[:25], "cookies": list(s.cookies.keys())[:20],
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
