# D&R Scraper (TÜİK COICOP 09 — Eğlence, Spor, Kültür)

`https://www.dr.com.tr` üzerindeki geniş ürün kataloğundan TÜİK 2026 Tüketici Fiyat Endeksi sepetindeki **09 (Eğlence, dinlence, spor ve kültür)** grubuna giren ürünleri toplayan, temizleyen ve sınıflandıran günlük scraper.

Günde yaklaşık **80.000+** tekil ürün toplayarak sepetin kitap, kırtasiye, oyuncak, konsol ve spor malzemeleri alt kalemlerine derinlik kazandırır.

---

## Kapsam ve TÜİK COICOP Eşleşmesi

Scraper, D&R üzerindeki 5 ana kategoriyi tarar:
1. **Kırtasiye** (`/kategori/kirtasiye`)
2. **Hobi & Oyuncak** (`/kategori/hobi-oyuncak`)
3. **Spor, Outdoor** (`/kategori/Spor-Outdoor`)
4. **Oyun & Konsol** (`/kategori/oyun-konsol`)
5. **Kitap** (`/kategori/Kitap/Ders-Sinav-Kitaplari/grupno=10000000`)

Toplanan ürünler kural tabanlı NLP ve kategori yolu eşlemesiyle aşağıdaki 7 haneli TÜİK COICOP 2018 / 2026 kodlarına atanır:

| TÜİK Kodu | COICOP Kalem Adı | Örnek Ürün Tipleri / Anahtar Kelimeler |
|---|---|---|
| `0921104` | Electronic games (game consoles, etc.) | PlayStation, Xbox, Nintendo Switch, konsol, gamepad, oyun kolları |
| `0921204` | Other toys | Lego, puzzle, kutu oyunları, figürler, arabalar, oyun hamuru |
| `0921207` | Ride-on wheeled toys | Scooter, kaykay, üç tekerlekli bisiklet, akülü araba |
| `0922102` | Home fitness equipment | Dambıl, ağırlık, pilates bandı, yoga matı, direnç lastiği |
| `0922103` | Sports equipment | Raket, futbol/basketbol topu, çadır, uyku tulumu, kamp sandalyesi |
| `0922107` | Special clothing & accessories for sports | Tayt, spor çorap, forma, antrenman kıyafetleri |
| `0971102` | Test books | TYT, AYT, KPSS, ALES, LGS, soru bankası, deneme sınavları |
| `0971103` | Textbooks | Ders kitapları, ilkokul/ortaokul/lise müfredat ve sınıf kitapları |
| `0971901` | Children's books | Çocuk kitapları, masal, bebek ve boyama kitapları |
| `0971902` | Other books | Edebiyat, kurgu, kurgu dışı ve diğer genel kitaplar |
| `0974001` | School notebooks | Okul defterleri, telli/ciltli defterler, bloknotlar |
| `0974003` | Pens and pencils | Kurşun, tükenmez, dolma, keçeli kalemler, fosforlu markerlar |
| `0974004` | Paintings for paints | Sulu boya, akrilik, yağlı boya, guaj, fırçalar, tuvaller |
| `0974005` | Writing and drawing paper | A4 fotokopi kâğıdı, resim kâğıtları, eskiz blokları |
| `0974009` | Other stationery items | Silgi, yapıştırıcı, makas, zımba, dosya, klasör, cetvel |

---

## Veri Filtreleme ve Güvenilirlik Kuralları

- **GTM Veri Katmanı:** DOM görsel metinleri yerine ürün kartlarındaki `data-gtm` JSON nesnesinden (`item_name`, `item_id`, kategori hiyerarşisi) veri okur. Sitenin CSS/HTML tasarım değişikliklerinden etkilenmez.
- **Net Kampanya Fiyatı:** Ürünlerde indirim olduğunda liste fiyatı yerine müşterinin ödediği nihai indirimli fiyatı (`.campaign-price span`) alır.
- **Kapsam Dışı Ürün Ayıklama (Negative Filtering):** 
  - Kulaklık, mouse, klavye vb. çevre birimleri `0` verilerek elenir.
  - Okul/sırt/seyahat çantaları `13_Personal_Care` kapsamına girdiğinden elenir; ancak `"kalem çanta"`, `"boya çantası"` veya `"oyun seti çantası"` gibi 09 ürünleri akıllı istisnalarla (`bag_ok`) korunur.
  - Mobilya, ofis teknolojileri ve seyahat ürünleri (`EXCLUDE_PATH_WORDS`, `EXCLUDE_NAME_WORDS`) otomatik filtrelenir.
- **Vitrin Sayfası Çözümleme (`sub_links`):** Doğrudan ürün listelemeyen üst kategori sayfalarında alt kategorileri otomatik tespit edip bir seviye derinliğe kadar iner.

---

## Mimari ve Dayanıklılık (Fault-Tolerance)

1. **Periyodik ve Atomik Kayıt:** Her kategori tamamlandığında veriler `.csv.part` dosyasına yazılıp atomik olarak hedef CSV'ye taşınır. Tarama yarıda kesilse bile toplanan tüm kategoriler korunur.
2. **Kaldığı Yerden Devam Edebilme:** Hedef günün CSV dosyası mevcutsa, önceden toplanan ürünler belleğe alınır ve mükerrer kayıt oluşturulmadan eksik kategoriler tamamlanır.
3. **Paralel Çalışma:** Kategori bazında `ThreadPoolExecutor` desteği vardır.

---

## Çıktı Dosyası ve Kolon Formatı

Çıktı konumu:
```
InflationItems/Datas/09_Recreation/DR/dr_YYYY-MM-DD.csv
```

Kolonlar:
```csv
product_name,price,category_number,sub_category_number,category_name
```

---

## Kullanım ve Çalıştırma

### 1. Varsayılan Günlük Çalıştırma (Önerilen: 2 worker)
```bash
python3 InflationItems/Codes/09_Recreation/DR/dr_scraper.py --workers 2
```

### 2. Belirli Bir Kategoriyi Hızlıca Test Etme
```bash
# Sadece Kitap kategorisinden ilk 2 sayfayı test et:
python3 InflationItems/Codes/09_Recreation/DR/dr_scraper.py --only Kitap --page-limit 2

# Sadece Kırtasiye kategorisini test et:
python3 InflationItems/Codes/09_Recreation/DR/dr_scraper.py --only Kırtasiye --page-limit 1
```

### 3. Geriye Dönük Belirli Bir Tarih İçin Çalıştırma
```bash
python3 InflationItems/Codes/09_Recreation/DR/dr_scraper.py --date 2026-10-25 --workers 2
```

### 4. Tüm Parametreler
```text
options:
  -h, --help            Yardım mesajını gösterir
  --date DATE           Hedef tarih YYYY-MM-DD (Varsayılan: bugün)
  --output OUTPUT       Özel çıktı dosyası yolu
  --page-limit N        Kategori başına taranacak maksimum sayfa sayısı
  --only KATEGORİ       Sadece adı geçen kategoriyi tara (ör. 'Kitap', 'Kırtasiye')
  --workers N           Eşzamanlı worker sayısı (Varsayılan: 1, önerilen: 2)
```
