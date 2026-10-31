# İVHO (İstanbul Veteriner Hekimleri Odası) — TÜİK 0945001 veterinary services

Source: the chamber's "Ev Hayvanları, Çiftlik Hayvanları Hekimliği — Alt Sınır Ücret Tarifesi" booklet
(PDF, 56 pages, updated twice a year; 2026/2 valid from 1 July 2026). Only the pet pages (16–39: examination,
vaccines, laboratory, imaging, surgery, dentistry) are read; farm-animal pages (40 onwards) and the
advertisement pages are skipped. Prices include VAT ("Tüm fiyatlara KDV dahildir", read from the pages).

Output: `InflationItems/Datas/09_Recreation/IVHO/ivho_YYYY-MM-DD.csv`, 695 rows on 2026-10-31.
Columns: `product_name, price, category_number, sub_category_number` (`9`, `0945001`), then `price_max, price_text,
animal, section, service, page, tariff_period, kdv_included, source_url`. One row per service and animal column
(Kedi / Köpek); a cell merged across both columns (birds and exotic animals) is one row with
`animal = "Kedi ve Köpek dışı (ortak hücre)"`. Services priced for one animal only (cat or dog vaccines, dog weight
classes) have one row. A range cell ("A - B") gives the minimum as `price` and the maximum in `price_max`.

Run (from the repository root):

```
uv run python -I -X utf8 InflationItems/Codes/09_Recreation/IVHO/ivho_scraper.py
```

`--date YYYY-MM-DD` sets the file date, `--pdf-url <ivho.org.tr PDF>` forces a PDF.

## How the PDF is found

ivho.org.tr's home page is script-rendered without links, so the scraper reads the pages that link the PDF
directly (VetArt's price page and Atakent Vet's tariff page; both answer with a valid certificate), collects the
`ivho.org.tr/assets/docs/*tarife*.pdf` links and takes the newest period from the file name
(`IVHO_Alt_Ucret_Tarifesi_2026_2.pdf` → 2026/2). The 2026/2 URL is built in as the floor. A tariff whose file name
does not follow this pattern would be missed; check the chamber's tariff after each January/July.

## Parsing (no OCR)

All table pages have a PDF text layer, so the text is read directly (pypdfium2, character boxes). A row is a
price y-position; the label is the text to the left on that row; the x position of the price tells cat from dog. The
section is the last upper-case heading above the row (page headings carry over). OCR was checked and is not
needed: the pages without text are advertisements. The Ankara VHO scraper has the OCR route
(`../AnkaraVHO/`) if a future tariff ships as images.

## TLS: the server omits its intermediate certificate

`ivho.org.tr` sends only its own certificate, not the Sectigo intermediate, so plain verification fails
("unable to get local issuer certificate"); browsers fetch the intermediate themselves. Verification is never
disabled. If the first request fails the certificate check, the scraper:

1. downloads the intermediate from the CA-issuers URL of the certificate (`crt.sectigo.com`, host checked, size capped),
2. checks that it is a valid CA certificate and **that its signature verifies against a root shipped in `certifi`**
   (without this step a tampered download would become a trusted CA),
3. writes certifi roots + that intermediate to a temporary bundle and uses it only for requests to
   ivho.org.tr (other hosts are refused, redirects are not followed). The bundle is deleted at exit.

If the chamber fixes its server, step 1–3 are skipped automatically. If the intermediate changes (new certificate
issuer), the signature check or the download URL fails and the run stops instead of weakening anything.
Needs `cryptography` (already in `requirements.txt`).

## sitemap.xml

Not used. The tariff is a single PDF; the home page has no sitemap links to it.

## Caveats

- These are the chamber's **minimum fees** for clinics in İstanbul and Yalova, not clinic prices; the values only
  change in January and July, so daily CSVs repeat. Every procedure also takes the examination fee on top.
- Labels are copied as published; section names come from the PDF headings and can change with the layout.
- A few two-line labels may lose a note line; prices are never guessed (rows without a recognisable price are skipped).
