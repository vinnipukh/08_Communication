# Xiaomi Türkiye scraper

Upstream `urazkagangunes/InflationResearchStudy` deposundan (`Codes/08_Communication/Xiomi/`) 2026-11-02'de
alındı ve aynı gün tarayıcısız (curl_cffi + sitenin JSON ucu) olarak yeniden yazıldı. Upstream'in eski
Selenium sürümü `Kategori, Ürün Adı, Fiyat, URL` yazıyordu. Upstream'den gelen 2026-05 CSV'lerinde ise sadece
`product_name, price` var ve fiyat metin (`64.999 TL`). Bu dosyalar olduğu gibi bırakıldı.

## TÜİK 08 kalemleri

| Kalem | Ürün var mı | Kaynak (sitedeki kategori, 2026-11-02 verisi, varyant satırı) |
|---|---|---|
| Cep telefonu | ✅ | Xiaomi / REDMI / POCO serileri (179) |
| Bilgisayar | ✅ | Tabletler (28) |
| Bilgisayar çevre birimleri | ✅ | Monitör, Wi-Fi Modemi, Sinyal güçlendirici, Flash Bellek, Klavye ve Fare, Yazı Tableti (39) |
| Ses ve görüntü ekipmanı | ✅ | Kulaklıklar, Hoparlör, Soundbar, Projektör, TV Box/TV Stick (63) |
| Televizyon | ✅ | Televizyon (8) |
| Diğer iletişim cihazları | ✅ | Akıllı Saatler, Akıllı Bileklikler, Takip Cihazı, Akıllı Gözlük (37) |
| Bilgi ve iletişim aksesuarları | ✅ | Telefon / Tablet Aksesuarları, Powerbank, Kablo, Güç Adaptörü, Selfie Çubuğu (57) |

Kapsam dışı (`0`, 124 satır): süpürge, hava temizleyici, ısıtıcı, mutfak aletleri, kişisel bakım, aydınlatma,
güvenlik kamerası, alet ve benzerleri. Eşleme `xiaomi_scraper.py` içindeki `TUIK_ITEMS` sözlüğünde, sitenin
yaprak kategori etiketine (`category_tag`) göre yapılır. Hiçbir yaprak kategoride görünmeyen birkaç ürün
(2026-11-02'de 3 ürün) `tuik08.classify` ile ürün adından sınıflanır.

## Nasıl çalışır

Tarayıcı kullanmaz. `curl_cffi` (Chrome TLS) oturumu önce `https://www.mi.com/tr/` ana sayfasını açar. Ana
sayfa `xm_geo` ve `xm_user_bucket` cookie'lerini bırakır, oturum bunları sonraki isteklerde kullanır. Anti-bot
cookie'si gerekmiyor. Ürün listeleme sayfaları verisini kendi çağırdığı şu uçlardan alır, scraper da onları çağırır:

- `https://go.buy.mi.com/tr/search/product-list?version=v4&type=2&page_size=20&page_index=N&category_tag=<etiket>&from=mobile`.
  Sayfa boyutu en fazla 20, `page_index` 0'dan başlar, boş liste gelince durulur. `category_tag` boşken tüm
  katalog gelir (~300 ürün, 16 sayfa).
- `https://go.buy.mi.com/tr/v2/item/category/nav?from=mobile`: kategori ağacı. Her yaprak etiket ayrıca taranır
  ve ürüne kategori bu yoldan atanır.

Her ürünün bir veya birkaç `commodity` kaydı (renk / bellek varyantı) vardır. Her varyant bir satırdır
(~535 satır). `price` = `raw_sales_price` (sitede gösterilen fiyat). Stokta olmayan varyantlar da yazılır.

Bir tam çalışma ~120 istek (her biri arasında 0,5 sn) ve ~2,5 dakika sürer.

Bilinen fark: listeleme sayfası "Tüm Ürünler (302)" diyor, API sayfaları 298 benzersiz ürün döndürüyor.

## Çalıştırma

```bash
python InflationItems/Codes/08_Communication/Xiaomi/xiaomi_scraper.py
```

Sunucuda her gün 00:30 kuyruğuyla çalışır (`bin/run_scraper.sh xiaomi`, kuyrukta huawei'den sonra, 15 dk timeout);
CSV'yi sunucu GitHub'a push'lar. GitHub Actions'ta `scraper_xiaomi.yml` sadece elle çalıştırılır.

## Çıktı

`InflationItems/Datas/08_Communication/Xiaomi/xiaomi_urunler_YYYY-MM-DD.csv`

`product_name, price, category_number, sub_category_number, Product ID, Commodity ID`. İlk dört kolon ortak
(bkz. `../README.md`). `Product ID` bir ürünün bütün varyantlarında aynıdır; kalıcı satır anahtarı
`Commodity ID`. Ad tek başına yetmez: 2026-11-02'de Redmi Note 14'ün üç varyantı ikişer kez aynı adla geliyor.
