# Hepsiemlak kiralık konut scraper'ı

Hepsiemlak'taki tüm Türkiye kiralık konut ilanlarını (fiyat, oda, m², il/ilçe/mahalle) günlük olarak toplar
(TÜİK 04, madde 0411001). 81 il dört kişiye bölünmüştür; herkes her gün kendi dosyasını çalıştırır.

| Kişi | Dosya | Başlangıç ili | İl sayısı |
|---|---|---|---|
| Zelal | `hepsiemlak_zelal.py` | İstanbul | 19 |
| Dani | `hepsiemlak_dani.py` | Ankara | 18 |
| Neslihan | `hepsiemlak_neslihan.py` | İzmir | 20 |
| Ekin | `hepsiemlak_ekin.py` | Antalya | 24 |

İllerin tam listesi `shards.json` içinde. Her pay ~17.100 ilan (~715 sayfa), yani toplamın %25'i.

## Kurulum (bir kez)

1. Repoyu klonla, klasörü IDE'de aç.
2. Python **3.10 veya üstü** olmalı.
3. Başka bir şey kurmana gerek yok: ilk çalıştırmada `cloakbrowser` paketi IDE'nin Python'una otomatik
   kurulur, ardından ~200 MB'lık tarayıcı indirilir (birkaç dakika sürebilir, bir kez olur).

## Her gün

1. Kendi dosyanı aç (ör. `hepsiemlak_zelal.py`) ve IDE'de sağ üstteki yeşil **Run** tuşuna bas.
2. Çıktıda "started in the background" yazar. Pencereyi/IDE'yi kapatabilirsin, tarama arka planda sürer.
   Ekranda tarayıcı ya da terminal penceresi **açılmamalı**.
3. Bilgisayar **açık ve internete bağlı** kalmalı, uyku moduna girmemeli. Tarama en az 2–3 saat sürer;
   site yavaşlatırsa daha uzun.
4. Bitince (log'un sonunda `wrote N rows` satırı ve hata yok) sadece kendi CSV'ni commit'le ve pushla:
   `InflationItems/Datas/04_Housing/Hepsiemlak/YYYY-MM-DD_<isim>.csv`

**Run'a tekrar basarsan:**
- Tarama hâlâ sürüyorsa: "already running" der, yeni tarama açmaz.
- Tarama yarıda kaldıysa (bilgisayar kapandı, site engelledi): kaldığı yerden devam eder.
- Bugünün taraması bittiyse: "already complete for today" der, bugünün verisine dokunmaz.

**Önemli:** Dört kişi **farklı internet bağlantılarında** olmalı (aynı ev/ofis = aynı IP). Site, IP başına
istek hızını sınırlıyor; aynı ağdan iki kişi çalıştırırsa ikisi de engellenir.

## Dosyalar nerede

| Ne | Nerede |
|---|---|
| Veri | `InflationItems/Datas/04_Housing/Hepsiemlak/YYYY-MM-DD_<isim>.csv` |
| Log | `checkpoints/hepsiemlak_<isim>_<tarih_saat>.log` (bu klasörde, git'e girmez) |
| İlerleme | `checkpoints/YYYY-MM-DD_<isim>.json` (tarama bitince silinir) |
| Çalışan sürecin pid'i | `checkpoints/hepsiemlak_<isim>.pid` |

CSV sütunları: `product_name, price, category_number, sub_category_number, ilanId, District, Rooms,
ListingURL, Province, Neighborhood, PropertyType, AreaM2, Currency, ListingDate, CollectedAt`
(District = ilçe, Neighborhood = mahalle, AreaM2 = brüt m², ListingDate = ilan kartındaki tarih).

## Sorun giderme

Önce en son log dosyasının sonuna bak.

| Log'da / ekranda | Anlamı | Ne yapmalı |
|---|---|---|
| `Cloudflare challenge passed` | Site bir doğrulama sayfası gösterdi, tarayıcı kendisi geçti | Hiçbir şey, normal |
| `HTTP 429` (ara sıra) | Site hızı sınırlıyor; scraper bekleyip tekrar deniyor | Bekle |
| `retired`, ardından `incomplete ... re-run with --resume` | IP bir süreliğine engellendi, tarama durdu | 30–60 dk sonra Run'a tekrar bas (kaldığı yerden devam eder) |
| `already running` ama tarama ilerlemiyor | Eski bir süreç asılı kalmış olabilir | Görev Yöneticisi'nde o pid'i kapat, Run'a bas |
| `Timeout ... li.listingCard` her sayfada, sayfa `HTTP 200` | Site tasarımı değişmiş, ilan kartları bulunamıyor | Koda bakılmalı (aşağıya bak) |
| Satırlarda boş fiyat/oda/m² | Kart içindeki alanlar değişmiş | Koda bakılmalı |
| `pip install` hatası | Python sürümü/izin sorunu | Python 3.10+ kullan; IDE'nin seçtiği Python'u kontrol et |
| Terminal/tarayıcı penceresi açılıyor | Olmamalı | Pencereyi kapatma (tarama da kapanır); bildir |

**Yapılmaması gerekenler:** bekleme süresini kısaltmak, aynı bilgisayarda birden fazla tarama açmak,
başkasının dosyasını çalıştırmak, `shards.json`'daki illeri kendi başına değiştirmek. Bunların hepsi ya
engeli büyütür ya da bir ilin o gün hiç toplanmamasına yol açar.

## Kod değişikliği gerekirse

Coding agent'ınla çalışıyorsan ona bu klasördeki `AGENTS.md`'yi okut. Kişisel sorunları (kurulum, Python)
kendi bilgisayarında çöz, commit'leme. `scraper.py` / `launcher.py` düzeltmeleri doğrudan
ana branch'e commit'lenip pushlanır, branch/PR açılmaz. Commit'ten hemen önce `git pull --rebase` yap; dört
kişinin aynı dosyayı ayrı ayrı değiştirmesi çakışmaya yol açar.

Test: `python hepsiemlak_<isim>.py --max-listings 100 --output test_<isim>.csv` → log ve CSV'ye bak →
test dosyalarını sil.

Sitenin davranışı ve denenen yöntemlerin geçmişi: `docs/TECH-STACK-SEARCH.md` §3.4.
