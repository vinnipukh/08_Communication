# Milli Piyango & Şans Oyunları Scraper'ı (TÜİK COICOP 09 — Eğlence ve Kültür)

Milli Piyango Online (`millipiyangoonline.com` / Sisal Şans - Milli Piyango İdaresi) üzerinden resmi sayısal loto, süper loto, şans topu, on numara, milli piyango çekiliş biletleri ve kazı kazan oyun kartı fiyatlarını toplayan günlük scraper.

## Kapsam ve TÜİK Kalem Eşleşmesi

| TÜİK Kodu | COICOP Kalem Adı | Açıklama |
|---|---|---|
| `0947001` (COICOP `09470`) | `Games of chance` (Şans oyunları) | Sayısal loto, süper loto, şans topu, on numara kolon bedelleri, Milli Piyango çeyrek/yarım/tam biletleri ve kazı kazan kartları |

- **Ana Harcama Grubu:** `09` (Eğlence, dinlence, spor ve kültür)
- **Grup:** `094` (Eğlence ve dinlence hizmetleri)
- **Sınıf:** `09470` (Şans oyunları)
- **Alt Kalem:** `0947001` (Şans oyunları ve piyango biletleri)

---

## Toplanan Ürün ve Fiyatlandırma Grupları

1. **Sayısal Şans Oyunları (Tek Kolon Bedelleri):**
   - Çılgın Sayısal Loto - 1 Kolon
   - Süper Loto - 1 Kolon
   - Şans Topu - 1 Kolon
   - On Numara - 1 Kolon
   - Hızlı On Numara - 1 Kolon

2. **Milli Piyango Çekiliş Biletleri:**
   - Milli Piyango - Çeyrek Bilet (Yılbaşı Özel)
   - Milli Piyango - Yarım Bilet (Yılbaşı Özel)
   - Milli Piyango - Tam Bilet (Yılbaşı Özel)

3. **Kazı Kazan Kartları (5 TL – 500 TL):**
   - Altın, Şans Dağı, 10'a Katla, 500 Matik, 12 Ay Şans, Altın Yumurta, Şans Yıldızı, Para Yağmuru, 30'a Katla, Elmas 7, Altın Gol, 50'ye Katla, Her Yönde Kazan, Şanslı Kasa, 100'e Katla, Ödül Yağmuru, Elmas, Çifte Şans, Bovling, Çok Oyun Çok Şans, Mücevher Kulesi, Kral Tacı, 500'e Katla vb.

---

## Veri Kaynağı ve Hata Davranışı (2026-10-31)

- Site düz `requests` bağlantılarını cevapsız bırakıyor (read timeout); istekler `curl_cffi`
  (Chrome TLS) ile atılır.
- Yalnızca sayfada canlı bulunan fiyatlar yazılır. Bulunamayan kalem loglanır ve atlanır; hiçbir
  fiyat bulunamazsa CSV yazılmaz (çıkış kodu 1). Eskiden koddaki sabit "yedek" fiyatlar sessizce
  yazılıyordu ve `requests` her seferinde zaman aşımına düştüğü için bütün satırlar bu sabitlerden geliyordu.
- "Standart Çekiliş" biletleri kaldırıldı: güncel fiyatları sitede yayınlanmıyor (kurallar sayfası
  hâlâ eski 24/12/6 TL fiyatlarını gösteriyor).

---

## Çıktı Dosyası ve Kolon Formatı

Çıktı dizini:
```
InflationItems/Datas/09_Recreation/Milli_Piyango/milli_piyango_YYYY-MM-DD.csv
```

Kolonlar (dört zorunlu kolon + `product_id`, `product_url`; `category_number` her satırda `9`):
```csv
product_name,price,category_number,sub_category_number,product_id,product_url
```

`product_id`: Site ürün ID'si yayınlamadığı için oyunun/biletin sabit slug'ıdır (ör. `cilgin-sayisal-loto-1-kolon`,
`kazi-kazan-12-ay-sans-20-tl`). Kazı kazanda kartın nominal değeri ID'nin parçasıdır (aynı oyunun 20 TL ve 30 TL kartı
farklı ürünlerdir); ID'ye fiyat değişimi değil, isim yazımı ve nominal değer etki eder. Kaynakta `Bovling` ve `Bovlİng`
yazımlarıyla iki 200 TL kart aynı slug'ı üretir (2026-11-04 canlı denemesi: 59 satır, 58 benzersiz ID).
`product_url`: değerin okunduğu kural sayfası.

Örnek veri (ilk dört kolon):
```csv
product_name,price,category_number,sub_category_number
Çılgın Sayısal Loto - 1 Kolon,25.00,9,0947001
Süper Loto - 1 Kolon,25.00,9,0947001
Şans Topu - 1 Kolon,15.00,9,0947001
On Numara - 1 Kolon,15.00,9,0947001
Milli Piyango - Çeyrek Bilet (Yılbaşı Özel),200.00,9,0947001
Milli Piyango - Tam Bilet (Yılbaşı Özel),800.00,9,0947001
Kazı Kazan - 100'e Katla (100 TL),100.00,9,0947001
Kazı Kazan - Kral Tacı (500 TL),500.00,9,0947001
```

---

## Çalıştırma

Bugünün tarihiyle çalıştırma:
```bash
python InflationItems/Codes/09_Recreation/Milli_Piyango/milli_piyango_scraper.py
```

Farklı bir tarih için çalıştırma:
```bash
python InflationItems/Codes/09_Recreation/Milli_Piyango/milli_piyango_scraper.py --date 2026-10-26
```

Kaydetmeden test etme (Dry-run):
```bash
python InflationItems/Codes/09_Recreation/Milli_Piyango/milli_piyango_scraper.py --dry-run
```
