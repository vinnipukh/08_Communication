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
   - Milli Piyango - Çeyrek Bilet (Standart Çekiliş)
   - Milli Piyango - Yarım Bilet (Standart Çekiliş)
   - Milli Piyango - Tam Bilet (Standart Çekiliş)
   - Milli Piyango - Çeyrek Bilet (Yılbaşı Özel)
   - Milli Piyango - Yarım Bilet (Yılbaşı Özel)
   - Milli Piyango - Tam Bilet (Yılbaşı Özel)

3. **Kazı Kazan Kartları (5 TL – 500 TL):**
   - Altın, Şans Dağı, 10'a Katla, 500 Matik, 12 Ay Şans, Altın Yumurta, Şans Yıldızı, Para Yağmuru, 30'a Katla, Elmas 7, Altın Gol, 50'ye Katla, Her Yönde Kazan, Şanslı Kasa, 100'e Katla, Ödül Yağmuru, Elmas, Çifte Şans, Bovling, Çok Oyun Çok Şans, Mücevher Kulesi, Kral Tacı, 500'e Katla vb.

---

## Çıktı Dosyası ve Kolon Formatı

Çıktı dizini:
```
InflationItems/Datas/09_Recreation/Milli_Piyango/milli_piyango_YYYY-MM-DD.csv
```

Kolonlar:
```csv
product_name,price,category_name,sub_category_number
```

Örnek veri:
```csv
product_name,price,category_name,sub_category_number
Çılgın Sayısal Loto - 1 Kolon,25.00,Games of chance,0947001
Süper Loto - 1 Kolon,25.00,Games of chance,0947001
Şans Topu - 1 Kolon,15.00,Games of chance,0947001
On Numara - 1 Kolon,15.00,Games of chance,0947001
Milli Piyango - Çeyrek Bilet (Yılbaşı Özel),200.00,Games of chance,0947001
Milli Piyango - Tam Bilet (Yılbaşı Özel),800.00,Games of chance,0947001
Kazı Kazan - 100'e Katla (100 TL),100.00,Games of chance,0947001
Kazı Kazan - Kral Tacı (500 TL),500.00,Games of chance,0947001
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
