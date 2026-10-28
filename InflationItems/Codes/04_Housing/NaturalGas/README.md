# NaturalGas — residential gas price + connection fees (TÜİK 0452101, 0452102)

Fetches the household natural gas retail price for İstanbul (İGDAŞ), Ankara (Başkentgaz) and İzmir
(İzmirgaz), plus the EPDK connection and deposit fee caps. No source publishes all cities, so each city comes
from its own distributor.

```bash
python InflationItems/Codes/04_Housing/NaturalGas/scraper.py
python InflationItems/Codes/04_Housing/NaturalGas/scraper.py --source izmirgaz fees   # bounded run
```

- Requests: ~11 (İGDAŞ fee page + price API; Başkentgaz PDF list + PDF + fee section; İzmirgaz certificate
  check, intermediate certificate, page, tariff fragment, two fee fragments), 1 s apart per host.
  Runtime ~7 s (measured 2026-10-28).
- Output: `InflationItems/Datas/04_Housing/NaturalGas/YYYY-MM-DD.csv`, written every run (dense time series).
- Gas rows (0452101): Kademe-1 and Kademe-2 per city for the household tier. Kademe-2 applies to the whole
  month's consumption once it passes the city's monthly limit (EPDK, since 04.04.2026). Prices include ÖTV
  (0.1468 TL/m³) and exclude 20 % VAT; `price` = TL/m³ (Başkentgaz quotes TL/Sm³).
- Fee rows (0452102): the EPDK caps from İzmirgaz (connection, extra connection per 100 m², connection
  inspection, deposits per appliance), province `Türkiye`, VAT excluded. The run compares the connection fee
  and the kombi deposit with İGDAŞ and Başkentgaz (VAT-included connection fee / 1.2) and logs a warning if
  one differs; on 2026-10-28 all three matched.
- Columns: `product_name, price, category_number, sub_category_number, province, distributor, tier,
  price_per_m3, price_per_kwh, unit, vat_included, components, valid_from, source_url, collected_at`.
  `components` = `gas;ötv;skb` where the source gives them (İzmirgaz).
- A source that fails is logged, the others are still written, and the run exits with status 1. If every
  source fails no CSV is written.

## Sources

| City | Distributor | Endpoint | Format |
|---|---|---|---|
| İstanbul | İGDAŞ | `POST https://api.igdas.istanbul/Sap/Sap/PerakendeSatisFiyati` `{"AYYIL":"MMYYYY"}` | JSON |
| Ankara | Başkentgaz | `GET https://bskapiv1.baskentdogalgaz.com.tr/api/menus/31/sections` → newest `/uploads/<uuid>.pdf` on `www.baskentdogalgaz.com.tr` | text PDF (pypdf) |
| İzmir | İzmirgaz | `GET https://www.izmirgaz.com.tr/pages/musteri_hizmetleri/konut.php` | HTML table |
| fees | İzmirgaz | `.../abone_baglanti.php`, `.../guvence.php` | HTML (EPDK decision text) |

## Troubleshooting

- `İzmirgaz sends no intermediate certificate` (info) — expected: the server omits the Sectigo DV R36
  intermediate. The scraper adds it from the certificate's AIA URL to a temporary CA bundle and keeps
  verifying. If İzmirgaz renews with another CA, update `IZMIRGAZ_INTERMEDIATE`.
- İGDAŞ connection errors — use `igdas.istanbul`, not `www.igdas.istanbul` (the `www.` host drops
  curl_cffi connections).
- `Başkentgaz PDF period ... does not match` / `household (ABONE 0-75.000) row not found` — the PDF layout
  changed; print `PdfReader(...).pages[0].extract_text()` and adjust the regex.
- `İzmirgaz konut.php: tariff tables changed` — the "Konut Tüketicileri Kademe-1/2" tables moved or were renamed.
- Needs `curl_cffi`, `beautifulsoup4`, `lxml`, `pypdf`, `certifi` (`requirements.txt`).
- Git Bash on Windows garbles Turkish output; set `PYTHONIOENCODING=utf-8`.
