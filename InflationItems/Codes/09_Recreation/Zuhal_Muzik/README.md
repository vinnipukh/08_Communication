# Zuhal Müzik Scraper (TÜİK COICOP 09 — Eğlence ve Kültür)

`https://www.zuhalmuzik.com` üzerindeki müzik kitapları, sanat/hobi yayınları, çizgi romanlar, figürler, kırtasiye, puzzle ve kamp ekipmanlarını toplayan günlük scraper.

Akademik ve etik veri toplama kurallarına (`robots.txt`, dinamik rate limiting, `User-Agent` beyanı) tam uyumlu olarak tasarlanmıştır.

---

## Sepet Bütünlüğü ve Kapsam Stratejisi

Zuhal Müzik geniş bir müzik aleti (elektro gitar, amfi, piyano vb.) envanterine sahiptir. Bu enstrümanların kontrolsüz çekilmesi, 09 grubunun genel tüketim sepeti dengesini bozabileceğinden, scraper **yalnızca önceden belirlenmiş ve COICOP-09 sepetine doğrudan giren 24 kategoriye** odaklanır.

### Taranan 24 Hedef Kategori:
- **Kitaplar (13 kategori):** Müzik Kitapları, Resim ve Heykel Kitapları, Hobi Kitapları, Çocuk Kitapları, Bilim Kitapları, Çizgi Roman, Ekonomi Kitapları, Edebiyat Kitapları, Fotoğrafçılık Kitapları, Mimarlık Kitapları, Psikoloji Kitapları, Sinema Kitapları, Tarih Kitapları.
- **Kırtasiye & Ofis (3 kategori):** Kalem, Defter, Ofis Malzemeleri.
- **Oyun, Hobi & Oyuncak (5 kategori):** Figür, Puzzle, Eğitici Oyunlar, Oyuncak, Kutu Oyunları.
- **Spor, Outdoor & Pet (3 kategori):** Kamp Malzemeleri, Kaykay ve Scooter, Tasma.

---

## TÜİK COICOP Eşleşme Tablosu

| TÜİK Kodu | COICOP Kalem Adı | Zuhal Müzik Kapsamı / Eşleşen Ürünler |
|---|---|---|
| `0971901` | Children's books | Çocuk kitapları |
| `0971902` | Other books | Müzik, sanat, hobi, bilim, edebiyat, tarih ve çizgi roman kitapları |
| `09212` | Games, toys and hobby-related goods | Puzzle, eğitici oyunlar, kutu oyunları, figürler |
| `0921204` | Other toys | Oyuncak kategorisindeki ürünler |
| `0922` | Sporting, camping and open-air recreation equipment | Kamp malzemeleri |
| `0922103` | Sports equipment | Kaykay ve scooter ürünleri |
| `0932204` | Other pet products | Tasma ve evcil hayvan gezdirme aksesuarları |
| `0974001` | School notebooks | Okul defterleri |
| `0974003` | Pens and pencils | Kalemler, tükenmezler, markerlar, finelinerlar |
| `0974005` | Paper for writing and drawing | Resim ve çizim defterleri (sketchbook, drawing pad) |
| `0974009` | Other stationery | Silgi, kalemtraş, ataş, zımba, dosya, klips, yapışkan notlar |

---

## Teknik Özellikler ve Mimari

1. **Robots.txt Saygısı:** `urllib.robotparser.RobotFileParser` ile her kategori URL'si ve arka plan AJAX endpoint'i taranmadan önce kontrol edilir.
2. **Hafif AJAX Ayrıştırma (Reverse Engineering):** Sayfa HTML'i yerine doğrudan `/urun?category=...&page=...` endpoint'ine istek atılarak `ProductParser(HTMLParser)` ile `data-name` ve `data-price` attribute'ları okunur; CPU ve bellek kullanımı minimumda tutulur.
3. **Akıllı Rate Limiting ve 429 Yönetimi:** 
   - İstekler arasında en az 2 saniye bekleme (`REQUEST_DELAY = 2.0`) uygulanır.
   - HTTP 429 yanıtlarında sunucunun gönderdiği `Retry-After` başlığı dinamik olarak okunup bekletilir.
4. **Cloudflare / Doğrulama Koruması:** Siteden doğrulama sayfası (`"just a moment..."` / `"cf-chl-"`) dönerse tarama güvenle durdurulur ve o ana kadar toplanan veriler korunur.
5. **Atomik ve Kademeli Kayıt:** Her sayfa ve kategori çekildiğinde veriler `.tmp` dosyası üzerinden atomik kaydedilir.

---

## Çıktı Dosyası ve Kolon Formatı

Çıktı konumu:
```
InflationItems/Datas/09_Recreation/Zuhal_Muzik/zuhal_muzik_YYYY-MM-DD.csv
```

Kolonlar:
```csv
product_name,price,category_name,sub_category_number
```

---

## Kullanım ve Çalıştırma

### 1. Varsayılan Tam Tarama
```bash
python3 InflationItems/Codes/09_Recreation/Zuhal_Muzik/zuhal_muzik_scraper.py
```

### 2. Hızlı Rastgele Test Modu
3 rastgele kategoriyi yalnızca ilk sayfalarıyla test eder:
```bash
python3 InflationItems/Codes/09_Recreation/Zuhal_Muzik/zuhal_muzik_scraper.py --test-random
```

### 3. Sayfa Sınırı Belirterek Çalıştırma
```bash
# Her kategoriden en fazla 2 sayfa çekerek hızlı kontrol:
python3 InflationItems/Codes/09_Recreation/Zuhal_Muzik/zuhal_muzik_scraper.py --page-limit 2
```

### 4. Geriye Dönük veya Özel Çıktı Belirterek Çalıştırma
```bash
python3 InflationItems/Codes/09_Recreation/Zuhal_Muzik/zuhal_muzik_scraper.py --date 2026-10-25
```
