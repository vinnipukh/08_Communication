# MACFit Spor Salonu Üyelik Scraper'ı (TÜİK COICOP 09 — Eğlence, Dinlence ve Spor Hizmetleri)

Mars Athletic / MACFit portal gateway API'si üzerinden Türkiye genelindeki tüm aktif MACFit, MAC/One, MACStudio ve MACRaw kulüplerinin resmi ve güncel üyelik paket fiyatlarını toplayan günlük scraper.

## Kapsam ve TÜİK Kalem Eşleşmesi

| TÜİK Kodu | COICOP Kalem Adı | Açıklama |
|---|---|---|
| `0946201` | `Payments for sports facilities (membership, rental, etc.)` | Fitness ve spor salonu aylık, yıllık ve taahhütlü üyelik paket ücretleri ile ilk kayıt bedelleri |

- **Ana Grup:** `09` (Eğlence, dinlence, spor ve kültür)
- **Grup:** `0946` (Eğlence, dinlence ve spor hizmetleri)
- **Sınıf:** `09462` (Spor faaliyetlerine katılım)
- **Alt Kalem:** `0946201` (Sportif tesislere yapılan ödemeler)

## Toplanan Üyelik Modelleri ve Fiyatlandırma

Her kulüp için Mars Athletic gateway üzerinden aşağıdaki paketler çekilir:

1. **12 Ay Taahhütlü Aylık Üyelik:** Aydan aya ödemeli 12 ay taahhütlü aylık bedel (`discountedFee`).
2. **Taahhütsüz Aylık Üyelik:** Taahhüt gerektirmeyen esnek tek aylık üyelik bedeli.
3. **Peşin Yıllık Üyelik (Aylık Karşılığı):** 12 aylık peşin üyelik paketinin aylık birim maliyeti.
4. **Peşin Yıllık Üyelik (Toplam Bedel):** 12 aylık peşin üyelik için tek seferde ödenen yıllık toplam tutar.
5. **Kayıt Bedeli (Giriş Ücreti):** İlk üyelik sırasında kulüp bazında uygulanan tek seferlik katılım/kayıt bedeli (`enrolmentFee`).

Kulüp Konseptleri:
- `MACFit`: Standart kulüpler (Classic, Gold, Platinum paketleri)
- `MAC/One`: Premium kulüpler
- `MACStudio`: Konsept stüdyo kulüpleri
- `MACRaw`: Butik gym konsepti

## Çıktı Dosyası ve Kolon Formatı

Çıktı konumu:
```
InflationItems/Datas/09_Recreation/MACFit/macfit_YYYY-MM-DD.csv
```

Kolonlar:
`product_name,price,category_name,sub_category_number,city,district,club_name,club_type,plan_name,membership_category,commitment_type,term_months,url`

### Kolon Açıklamaları
- `product_name`: Standart ürün adı (Örn: `MACFit Ankara Ankamall - CLASSIC (12 Ay Taahhütlü Aylık Üyelik)`)
- `price`: Fiyat (TL, float)
- `category_name`: `Payments for sports facilities (membership, rental, etc.)`
- `sub_category_number`: `0946201`
- `city`: Kulübün bulunduğu il (İstanbul, Ankara, İzmir, Bursa, Adana vb.)
- `district`: Kulübün bulunduğu ilçe
- `club_name`: Kulüp şube adı
- `club_type`: Konsept türü (`MACFit`, `MAC/One`, `MACStudio`, `MACRaw`)
- `plan_name`: Paket adı (`CLASSIC`, `GOLD`, `PLATINUM`, `Kayıt Bedeli`)
- `membership_category`: Kategori (`Standard`, `Gold`, `MAC All Access`, `Enrollment`)
- `commitment_type`: Taahhüt türü (`12 Ay Taahhütlü`, `Taahhütsüz Aylık`, `Peşin Yıllık (Aylık)`, `Peşin Yıllık (Toplam)`, `Tek Seferlik`)
- `term_months`: Üyelik süresi ay (`12`, `1`, `0`)
- `url`: Kulüp harita / bilgi bağlantısı

## Çalıştırma

Tüm kulüpleri tarama (varsayılan):
```bash
python3 InflationItems/Codes/09_Recreation/MACFit/macfit_scraper.py
```

Belirli bir tarih belirterek çalıştırma:
```bash
python3 InflationItems/Codes/09_Recreation/MACFit/macfit_scraper.py --date 2026-10-26
```

Hızlı test (kulüp limiti ile):
```bash
python3 InflationItems/Codes/09_Recreation/MACFit/macfit_scraper.py --limit 5
```

Konsept veya şehir bazlı filtreleme:
```bash
python3 InflationItems/Codes/09_Recreation/MACFit/macfit_scraper.py --club-type MACFit --city Ankara
```
