# 08_Communication (teknoloji + telecom) ve TÜİK 04 doğal gaz / İSKİ scraper sunucusu

Hedef sunucu: Ubuntu 22.04, 2 vCPU, 1.9 GB RAM, cron. Kod kaynağı:
`InflationItems/Codes/08_Communication/` (upstream `TUGC3/InflationResearchStudy`
commit `9cb747a`, 2026-09-22, sunucu için düzenlendi). 2026-10-28'den beri ayrıca TÜİK 04'ün
GitHub runner IP'lerinden zaman aşımına düşen dört kaynağı: doğal gaz (İGDAŞ, Başkentgaz, İzmirgaz,
`InflationItems/Codes/04_Housing/NaturalGas/`) ve İSKİ suyu (`InflationItems/Codes/04_Housing/Water/`).
Diğer 04 kaynakları GitHub Actions'ta (`scraper_04_utilities.yml`).

## Sunucudaki yapı

`<repo-root>` = repoyu klonladığın dizin. Script'ler kendi konumundan bulur, sabit yol yok.

```
<repo-root>/
  deploy/scraper-server/   setup.sh, crontab.txt, requirements.txt, bin/ (kaynak)
  bin/                     setup.sh'ın kopyaladığı çalışan script'ler:
    run_scraper.sh         tek scraper'ı kilit + timeout + disk kontrolüyle çalıştırır
    cleanup.sh             günlük: 30 günden eski loglar, geçici Chrome profilleri
    export_data.sh         haftalık: CSV'leri tek .tar.gz yapar (--delete ile siler)
    push_data.sh           her işten sonra yeni CSV'leri GitHub'a push'lar (GIT_PUSH=1)
    daily_report.sh        günlük Telegram özeti (log.txt durum satırları + CSV satır sayıları)
  venv/                    Python 3.11 (uv), requirements.txt'teki sabit sürümlü paketler (04 PDF'leri için pypdf dahil)
  .env                     opsiyonel ayarlar
  InflationItems/Codes/08_Communication/...              scraper kodu
  InflationItems/Datas/08_Communication/<Mağaza>/*.csv   çıktı
  InflationItems/Datas/04_Housing/{IGDAS,Baskentgaz,Izmirgaz,ISKI}/*.csv   04 çıktısı
  server_logs/<scraper>_<tarih>.log   her çalıştırmanın tam logu
  log.txt                  her çalıştırma için tek satır: OK / FAILED / TIMEOUT / SKIPPED (+ " · push: …")
```

`bin/`, `venv/`, `server_logs/`, `export/`, `log.txt`, `.env` gitignore'da.

## Kurulum (bir kere)

Sadece gereken iki klasörü çeken sparse clone; repodaki diğer mağazaların verileri inmez
ve sonradan `git pull` scraper çıktılarıyla çakışmaz (`InflationItems/Datas` checkout
dışında kalır):

```bash
apt-get update && apt-get install -y git
git clone --filter=blob:none --no-checkout https://github.com/vinnipukh/08_Communication.git <repo-root>
cd <repo-root>
git sparse-checkout set --cone deploy/scraper-server InflationItems/Codes/08_Communication \
  InflationItems/Codes/04_Housing/NaturalGas InflationItems/Codes/04_Housing/Water
git checkout main
bash deploy/scraper-server/setup.sh
```

`setup.sh` tekrar çalıştırılabilir. Yaptıkları: saat dilimini Europe/Istanbul yapar,
Google Chrome kurar, uv ile Python 3.11 venv oluşturur, sabit sürümlü paketleri
yükler, `bin/` script'lerini kopyalar, crontab'a sadece kendi bloğunu yazar (başka
cron işlerine dokunmaz).

Kontrol: `bin/run_scraper.sh huawei && tail -3 log.txt`

2026-10-11 öncesi kurulmuş sunucu (eski `Codes/TechnologicalProducts` + `Codes/Telecom` düzeni) için
bir kere: önce `bin/export_data.sh` ile eski `Datas/TechnologicalProducts` ve `Datas/Telecom` CSV'lerini
indir (yeni script'ler sadece `Datas/08_Communication`'a bakar), sonra:

```bash
cd <repo-root> && git sparse-checkout set --cone deploy/scraper-server InflationItems/Codes/08_Communication && git pull && bash deploy/scraper-server/setup.sh
```

`inflationstudymirror` klonundan kurulmuş sunucu için bir kere: yeni repo
(`vinnipukh/08_Communication`) ortak geçmişi olmadan başladı, bu yüzden `git pull` yerine:

```bash
cd <repo-root> && git remote set-url origin https://github.com/vinnipukh/08_Communication.git \
  && git fetch origin && git checkout -B main origin/main && bash deploy/scraper-server/setup.sh
```

`InflationItems/Datas` sparse checkout dışında olduğu için sunucudaki CSV'lere dokunulmaz.

2026-10-28 öncesi kurulmuş sunucuda 04 işleri için bir kere (sonra aşağıdaki güncelleme):

```bash
cd <repo-root> && git sparse-checkout add InflationItems/Codes/04_Housing/NaturalGas InflationItems/Codes/04_Housing/Water
```

`InflationItems/Datas/04_Housing` de 08 verisi gibi checkout dışında kalır.

Kod güncellemesi (repoda scraper değişirse):

```bash
cd <repo-root> && git pull && bash deploy/scraper-server/setup.sh
```

Git'siz alternatif: Windows'ta repo kökünde paketi yap, sunucuda `<repo-root>` içine aç,
`bash setup.sh` çalıştır.

```powershell
tar --exclude __pycache__ -czf scraper.tgz -C deploy/scraper-server . -C ../.. InflationItems/Codes/08_Communication
```

## Program (Istanbul saati, her gün)

Süre, ürün sayısı ve tepe bellek 2026-09-28 tarihli tam çalıştırmalardan ölçüldü
(geliştirici PC'si; sunucuda CPU daha yavaş, timeout'lar ~3-4 kat pay bırakır).
Bellek = USS (process'e özel bellek, Chrome alt process'leri dahil).

| Saat | İş | Ölçülen süre | Ürün | Tepe RAM | Timeout | Browser |
|---|---|---|---|---|---|---|
| 00:30 | cleanup | - | - | - | - | - |
| 01:00 | samsung | 1 dk | 412 | 61 MB | 20 dk | yok |
| 01:35 | huawei | 0.5 dk | 108 | 22 MB | 10 dk | yok |
| 01:55 | pozitif | 1 dk | 1.239 | 30 MB | 15 dk | yok |
| 02:20 | dr | 1 dk | 1.345 | ~95 MB | 20 dk | yok |
| 02:50 | naturalgas (TÜİK 04: İGDAŞ, Başkentgaz, İzmirgaz + bağlantı bedelleri) | ~0.5 dk (sunucu, 2026-10-28) | 15 | düşük | 15 dk | yok |
| 03:15 | iski (TÜİK 04: İSKİ su birim fiyatları) | ~0.2 dk (sunucu, 2026-10-28) | 3 | düşük | 10 dk | yok |
| 03:35 | beymen | 10.5 dk | 10.659 | 22 MB | 45 dk | sadece 403 gelirse |
| 04:35 | vatan | ~19 dk (yavaşlatıldı, ~45 dk bekle) | 5.497 | ~105 MB | 120 dk | yok |
| 06:55 | telecom (mobil tarifeler: Turkcell, Vodafone, NetGSM, Türk Telekom) | ~40 dk | ~820 | düşük | 90 dk | yok |
| 08:35 | internet (ev interneti: Superonline, Vodafone, Kablonet, Milleni, TurkNet, Türk Telekom, GIBIRNet) | ~25 dk | ~400 | ~300 MB (kısa Chrome) | 75 dk | TurkNet için tek seferlik headless Chrome (Cloudflare çerezi) |
| 10:00 | streaming (Netflix, Disney+, HBO Max, Amazon Prime, Apple TV+, YouTube Premium, Spotify, MUBI, TV+, Tivibu, GAİN, tabii) | ~1 dk | ~40 | ~300 MB (kısa Chrome) | 15 dk | tabii için tek seferlik headless Chrome |
| 10:25 | repair (onarım: Apple, Samsung, Huawei, GSM İletişim) | ~30 dk | ~2.000 | düşük | 90 dk | yok |

Her iş, bir öncekinin timeout'u (+2 dk kill payı) dolduktan en az 8 dk sonra başlar: bir iş timeout'a takılsa bile
sıradaki iş beklemez, kayma olmaz (2026-10-28 telecom/internet timeout zinciri sonrası aralar açıldı).
Tüm işler aynı kilidi (`flock /tmp/scraper.lock`) kullanır, yani biri geç kalırsa
sıradaki bekler; iki scraper asla aynı anda çalışmaz. Her çalıştırmadan sonra
kalan Chrome process'leri öldürülür.

Telecom çıktısı: `InflationItems/Datas/08_Communication/<Operatör>/*.csv` (mobil) ve
`InflationItems/Datas/08_Communication/<Sağlayıcı>/*_internet_*.csv` (ev interneti),
`InflationItems/Datas/08_Communication/<Servis>/*.csv` (dijital platform abonelikleri),
`InflationItems/Datas/08_Communication/<Kaynak>/*_repair_*.csv` (bilgi-iletişim ekipmanı onarım ücretleri). NetGSM tek sayfa,
Türk Telekom ~830 yavaş sayfa olduğu için NetGSM önce çalışır: 2026-10-28'de TT sayfaları 40 sn'lik zaman
aşımlarıyla yavaşladı, iş 90 dk sınırına takıldı ve sonra gelen NetGSM hiç çalışmadı. Süreler 2026-10-08
geliştirici PC'sinde ölçüldü; süreyi Türk Telekom'un sitemap'teki ~490 + ~340 detay sayfası belirler
(sıralı, 1.5-3.5 sn bekleme). Kaynak notları: `docs/site-analysis/telecom/NOTES.md`.

Bu on işin ve iki 04 işinin verisini GitHub'a sunucu push'lar (aşağıda "GitHub'a push"). `.github/workflows/scraper_<isim>.yml`
iş akışlarının artık zamanlaması yok, sadece elle (`workflow_dispatch`) çalışır; `bin/run_scraper.sh` ve
`requirements.txt` dosyalarını doğrudan kullandıkları için bu dosyalardaki bir değişiklik iki tarafı da etkiler.
Emlakjet ve Beymen tech iş akışları ayrıdır ve kendi zamanlamalarıyla çalışmaya devam eder.

04 işleri: `NaturalGas/scraper.py` bir kaynak başarısız olursa da diğerlerini yazar ama 1 ile çıkar (log.txt'de
FAILED). Bağlantı bedeli satırları İzmirgaz dosyasına yazılır. İSKİ yeni yılın PDF'i henüz bağlanmamışsa önceki
yılın Aralık fiyatlarını yazar (uyarı, hata değil).

## Telegram özeti

`bin/daily_report.sh [tech|telecom] [YYYY-MM-DD]` günün `log.txt` satırlarını okur, her işin CSV satırlarını sayar
ve dünküne göre %20+ düşüşü işaretler. `tech` 6 teknoloji işi + `naturalgas` + `iski`, `telecom` 4 telecom işi.
Her işin `log.txt`'deki son satırı OK / FAILED / TIMEOUT ile başlar; push sonucu aynı satırda ` · ` sonrasında gelir
(push başarısızsa ⚠️). `TELEGRAM_BOT_TOKEN` ve `TELEGRAM_CHAT_ID` `.env`'de olmalı. Cron satırları `crontab.txt`'te
değil, sunucuda ayrı bir `telegram-report-local` bloğunda (06:50 tech, 12:10 telecom; işler en kötü durumda bile bittikten sonra).

## Haftalık rutin

```bash
<repo-root>/bin/export_data.sh --delete
```

Arşiv dosyası: `<repo-root>/export/data_<tarih>.tar.gz`. Bugünün dosyaları arşive
girmez (o sırada bir scraper yazıyor olabilir). Windows'ta indir:

```powershell
scp root@SUNUCU_IP:<repo-root>/export/data_*.tar.gz .
```

İndirdikten sonra sunucuda: `rm <repo-root>/export/data_*.tar.gz`

## Durum kontrolü

```bash
tail -30 <repo-root>/log.txt
```

`SKIPPED: only N MB free` görürsen disk dolmuş demektir: export yap, sonra sil.
Disk kontrolü 1.5 GB boş alanın altında scraper çalıştırmaz.
`FAILED` görürsen ilgili `server_logs/<scraper>_<tarih>.log` dosyasına bak.

## Düzenlemeler (upstream'e göre)

Kapsam her mağazada sitemap / sitenin kendi ürün sayısıyla kontrol edildi (2026-09-28).

- **Huawei** (68 → 108): Selenium kaldırıldı. Tam e-ticaret kataloğu
  (`/.rest/service/ecommerce/v1/products/tr`, ~290 ID) + fiyat API'si
  (`queryMinPriceAndInv`); sadece fiyatı olanlar (satışta) yazılır. İsim kategori
  sayfalarının JSON'undan; aksesuarlar hiçbir sayfada listelenmiyor, onların adı URL'den
  üretilir ve `listed_on_site=False` olur. Garanti/test (`offer`) ürünleri hariç.
- **Pozitif** (507 → 1.239): kategori sayfası taraması yerine WooCommerce Store API
  (`/wp-json/wc/store/v1/products`, tüm katalog). Stokta olmayan ve outlet ürünler artık
  atılmıyor; `in_stock`, `is_outlet` sütunları var.
- **Beymen** (9.600 → 10.659): sabit 200 sayfa limiti ~1.000 ürünü kesiyordu; artık API'nin
  `totalPageCount` değeri kullanılıyor, ürün ID ile tekilleştiriliyor. Önce browser'sız
  (`curl_cffi`, Chrome TLS); 403 gelirse tek seferlik headless Chrome ile Akamai cookie'si.
- **Samsung** (405 → 412): upstream `KeyError: 'sku'` ile çöküyordu, düzeltildi; `id` ve
  `category` sütunları. Lifestyle TV (The Frame) kategorisi eklendi. Kategori taramasından
  sonra b2c sitemap'indeki tüm model kodları kartvizit API'sine sorulur, fiyatlı olup
  eksik kalanlar eklenir (sitemap'teki ~950 model satıştan kalkmış, fiyatsız).
- **DR** (1.345): değişiklik yok; sitede görünen kategori sayılarıyla uyumlu. Paralellik 1.
- **Vatan** (5.497): çıktı `Datas/` altına. 2026-10-18'den beri başlıklı, virgül ayraçlı ortak 08
  formatı (`product_name, price, category_number, sub_category_number`, fiyat sayı); eski upstream
  formatındaki (başlıksız `isim;fiyat`) dosyalar da bu düzene çevrildi. Aynı gün tekrarlanan taramalardan sonra Cloudflare IP'yi
  30+ dk banladı (Error 1015); bekleme süreleri 1.5-3 sn'ye çıkarıldı, ban sürerse
  tarama durur, veri kaydedilir ve `log.txt`'de FAILED görünür.

## .env (opsiyonel)

```
CHROME_VERSION_MAIN=153   # Chrome sürüm algılama bir gün bozulursa sabitle
```
GIT_PUSH=1                # her scraper'dan sonra CSV'leri GitHub'a push'la (bin/push_data.sh)
```

## GitHub'a push

`GIT_PUSH=1` iken `run_scraper.sh` her işten sonra (kilit içindeyken) `bin/push_data.sh <isim>` çalıştırır:
son başarılı push'tan (`.last_push`) beri yazılan CSV'leri (sadece `InflationItems/Datas/08_Communication/` ve
`InflationItems/Datas/04_Housing/{IGDAS,Baskentgaz,Izmirgaz,ISKI}/`; diğer 04_Housing klasörlerini Actions veya
kişiler yazar, sunucu onlara dokunmaz) güncel `origin/main`'in üstüne geçici bir index ile
commit'ler ve push'lar. Çalışma dizinine, sparse checkout'a ve yerel `main`'e dokunmaz; silmeleri hiç
commit'lemez (`export_data.sh --delete` sadece sunucudan siler). Push başarısız olursa dosyalar bir sonraki
işte tekrar denenir. Push sonucu ayrı satıra değil, çalıştırma sonucunun aynı satırına eklenir
(`OK in 3 min · push: 1 file(s) -> main abc1234` veya `… · PUSH FAILED`), böylece her scraper'ın
`log.txt`'deki son satırı hep OK / FAILED / TIMEOUT ile başlar.

Kimlik doğrulama: repo'ya yazma yetkili deploy key (`~/.ssh/github_08comm`, `~/.ssh/config`'te
`Host github-08comm`), remote `git@github-08comm:vinnipukh/08_Communication.git`. Test:
`ssh -T github-08comm`.
