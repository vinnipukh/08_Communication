# Vatan Bilgisayar scraper

## TÜİK 08 kalemleri

| Kalem | Ürün var mı | Kaynak (kök kategori, 2026-10-10 verisinden örnek) |
|---|---|---|
| Cep telefonu | ✅ | `cep-telefonu-modelleri`: akıllı telefonlar ve tuşlu telefonlar |
| Bilgisayar | ✅ | `bilgisayar`: dizüstü (MacBook, Vivobook, Ideapad…), tablet, iMac |
| Bilgisayar çevre birimleri | ✅ | `bilgisayar-bilesenleri`, `aksesuarlar`, `ofis-malzemeleri`: monitör, klavye, mouse, SSD, yazıcı, modem |
| Ses ve görüntü ekipmanı | ✅ | `fotograf-makinesi-video-kamera`: kamera, fotoğraf makinesi; kulaklık, hoparlör |
| Televizyon | ✅ | `televizyon`: Smart / QLED TV'ler |
| Diğer iletişim cihazları | ✅ | Akıllı saatler (Apple Watch, Huawei Watch) |
| Bilgi ve iletişim aksesuarları | ✅ | `aksesuarlar`: kılıf, şarj cihazı, kablo |
| Cep telefonu hizmet ücreti | — | |
| İnternet hizmet ücreti | — | |
| Bilgi ve iletişim ekipmanı bakım / onarım ücreti | — | |
| Dijital içerik / streaming platform aboneliği | — | |

Kapsam dışı (aynı CSV'ye yazılır): `ev-mutfak`, `kisisel-bakim-urunleri`, `iklimlendirme`,
`oyun-hobi`, `outlet` kök kategorilerinden gelen ürünler. Bunlar `sub_category_number = 0` alır
(ürün adı + taranan kategori URL'sinden `tuik08.classify`).

## Nasıl çalışır

12 kök kategori URL'sinden başlar. Bir sayfa ürün listesi değil de alt kategori vitriniyse,
en fazla 3 seviye derinliğe kadar alt kategori linklerini izler (sayfa başına en fazla 80 alt
kategori). Ürün listelerinde sayfa başına 24 ürünle `?page=N` sayfalama yapar.

## Çalıştırma

```bash
python InflationItems/Codes/08_Communication/VatanComputer/vatan_comp.py
```

Sunucuda `bin/run_scraper.sh vatan` ile her gün 04:00'te çalışır (`deploy/scraper-server/`).

## Çıktı

`InflationItems/Datas/08_Communication/VatanComputer/vatan_computer_YYYY-MM-DD.csv`

Başlıklı, virgül ayraçlı: `product_name, price, category_number, sub_category_number` (ortak 08 kolonları, bkz. `../README.md`), ardından `product_code, product_url`. Fiyat sayıdır (`59.999 TL` → `59999.0`). Upstream formatı (başlıksız `ürün adı;fiyat`) ile yazılmış eski dosyalar 2026-10-18'de bu düzene çevrildi.

- `product_name` ürün kartındaki `.product-list__product-name h3` metnidir; `product_code` kartın
  `.product-list__product-code` metnidir (üretici kodu, outlet ürünlerinde `MG2P4TU/A outlet 49257`).
  2026-10-30'a kadar ad kartın tüm metninden kesiliyordu ve rozetler, puan ve kod ada karışıyordu
  (`YENİ ÜRÜN 0,0 …`, `PRO Z790-P WIFI outlet 47664 MSI …`, `… Sepette`; o günkü dosyada adların ~%25'i).
  Bu rozetler günden güne değiştiği için aynı ürün farklı adla görünüyordu. Bu yüzden 2026-10-30 öncesi
  dosyalarla ad üzerinden eşleştirme yapılırken bu ekler temizlenmelidir. Kart dışı linklerde eski
  metin ayıklama (`extract_name`) yedek olarak kalır.
- Ürün kimliği olarak `product_url` kullanılır (taramada da tekilleştirme anahtarı odur).
- `price` kart metnindeki ilk TL tutarıdır; sepette indirim varsa o tutar gelir (davranış değişmedi).
