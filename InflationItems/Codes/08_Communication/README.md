# TÜİK 08 — Bilgi ve iletişim scraper'ları

Bu klasördeki scraper'ların TÜİK 08 kalemlerine dağılımı. Sayılar **tek bir günün** (2026-10-10)
CSV'lerinden çıkarılmış **yaklaşık** ürün sayılarıdır. Hizmet kalemlerinde "ürün", bir tarife,
paket, abonelik planı ya da onarım fiyatı satırıdır.

Her scraper'ın kendi README'sinde hangi kalemleri hangi site kategorisinden topladığı yazıyor.

## Ortak CSV kolonları

2026-10-18'den itibaren her 08 scraper'ının CSV'si aynı dört kolonla başlar, scraper'a özel kolonlar
bunlardan sonra gelir:

`product_name, price, category_number, sub_category_number`

- `category_number`: her satırda `8` (TÜİK TÜFE ana grubu 08, Bilgi ve iletişim).
- `sub_category_number`: TÜİK "CPI methodological notes" Ek 1'deki (mal ve hizmet sepeti) 7 haneli kalem
  kodu. 08 sitesinde satılan ama hiçbir 08 kalemine girmeyen ürün (oyun konsolu, küçük ev aleti, yazılım
  lisansı, kargo bedeli, ...) `0` alır.
- `price`: sayı (TL). Vatan da artık `59.999 TL` yerine `59999.0` yazar.

| Kod | Kalem |
|---|---|
| `0812002` | Cep telefonu (Mobile phone) |
| `0813101` | Bilgisayar: masaüstü, dizüstü, tablet (Computer) |
| `0813209` | Bilgisayar çevre birimleri ve sarf malzemeleri (Computer peripherals) |
| `0814001` | Ses ve görüntü ekipmanı (Audio-video equipment) |
| `0814007` | Televizyon (Television) |
| `0819103` | Diğer iletişim cihazları: akıllı saat, bileklik, takip cihazı, telsiz (Other communication devices) |
| `0819201` | Bilgi ve iletişim aksesuarları (Info-communication accessories) |
| `0832001` | Cep telefonu hizmet ücreti: `Telecom/scraper.py` |
| `0833001` | İnternet hizmet ücreti: `Telecom/internet.py` |
| `0835001` | Bilgi ve iletişim ekipmanı bakım/onarım ücreti: `Telecom/repair.py` |
| `0839201` | Dijital içerik platformu aboneliği: `Telecom/streaming.py` |
| `0` | 08 sitesinde ama 08 sepetinde değil |

Kodlar ve sınıflandırma `tuik08.py` içinde. Samsung ve Huawei sitenin kendi kategorisinden birebir
eşlenir. Beymen, D&R, Pozitif ve Vatan için `tuik08.classify(ürün adı, site kategorisi)`
anahtar kelime kurallarını kullanır. Kurallar 2026-10-18 verisinde örneklenerek kontrol edildi ve
ürün adına dayandığı için birkaç yüz üründe hata payı var. `python tuik08.py` kural sırasını kontrol eder.
2026-10-18'de eski dosyalar da bu düzene çevrildi (çevrilmeden önceki hali: `export/datas_08_before_tuik_columns_2026-10-18.tar.gz`, gitignore'da).

## Özet

| Kalem | Scraper sayısı | Scraper'lar | Günlük ürün (yaklaşık) |
|---|---|---|---|
| Cep telefonu | 6 | Vatan, Pozitif, Beymen, Samsung, Huawei, DR | ~840 |
| Bilgisayar | 5 | Vatan, Beymen, Pozitif, Samsung, Huawei | ~1.300 |
| Bilgisayar çevre birimleri | 6 | Vatan, Beymen, Pozitif, DR, Samsung, Huawei | ~2.400 |
| Ses ve görüntü ekipmanı | 6 | Beymen, DR, Vatan, Pozitif, Samsung, Huawei | ~1.900 |
| Televizyon | 3 | Vatan, Beymen, Samsung | ~320 |
| Diğer iletişim cihazları | 6 | Vatan, Beymen, Pozitif, DR, Huawei, Samsung | ~460 |
| Bilgi ve iletişim aksesuarları | 6 | Beymen, Pozitif, Vatan, DR, Samsung, Huawei | ~6.500 |
| Cep telefonu hizmet ücreti | 1 (`Telecom/scraper.py`, 4 operatör) | Turkcell, Türk Telekom, Vodafone, NetGSM | ~760 |
| İnternet hizmet ücreti | 1 (`Telecom/internet.py`, 7 sağlayıcı) | Türk Telekom, Superonline, Kablonet, TurkNet, Vodafone, Milleni, GIBIRNet | ~380 |
| Bilgi ve iletişim ekipmanı bakım / onarım ücreti | 1 (`Telecom/repair.py`, 4 kaynak) | GSM İletişim, Huawei, Apple, Samsung | ~5.800 |
| Dijital içerik / streaming platform aboneliği | 1 (`Telecom/streaming.py`, 12 servis) | YouTube Premium, Disney+, Spotify, Tivibu, TV+, MUBI, Netflix, HBO Max, GAIN, Prime, Apple TV+, Tabii | ~34 |

Scraper'lar listede o kalemdeki ürün sayısına göre büyükten küçüğe sıralı.

## Ürün ve cihaz kalemleri: scraper başına

| Scraper | Cep telefonu | Bilgisayar | Çevre birimleri | Ses ve görüntü | Televizyon | Diğer iletişim | Aksesuar | Kapsam dışı | Toplam |
|---|---|---|---|---|---|---|---|---|---|
| Beymen (sunucu) | ~130 | ~430 | ~440 | ~1.200 | ~100 | ~110 | ~5.100 | ~3.500 | ~10.900 |
| VatanComputer | ~500 | ~490 | ~1.700 | ~130 | ~170 | ~190 | ~430 | ~1.800 | ~5.400 |
| PozitifTeknoloji | ~140 | ~380 | ~140 | ~100 | — | 98 | ~440 | 23 | ~1.300 |
| DR | 3 | — | 89 | ~480 | — | 30 | ~370 | ~430 | ~1.400 |
| Samsung | 61 | 22 | 32 | 16 | 52 | 10 | ~100 | 92 | ~390 |
| Huawei | 12 | 15 | 9 | 13 | — | 27 | 40 | — | 116 |

Nasıl sayıldı:

- **Site kategorisinden** (daha güvenilir): DR (`Category` / `Subcategory`), Huawei (`Category`),
  Samsung (`category`), PozitifTeknoloji (`category`; "Fırsatlar" / "Outlet" gibi karışık
  kategorilerde ürün adından).
- **Ürün adındaki anahtar kelimelerden** (daha kaba): Beymen ve VatanComputer. Bu
  CSV'lerde kategori kolonu yok. Kılıf, kordon ve şarj cihazı gibi aksesuarlar önce ayrılır
  (örneğin "iPhone 17 uyumlu kılıf" telefon sayılmaz), sonra telefon, bilgisayar, TV, saat,
  çevre birimi ve ses/görüntü kelimeleri aranır. Hata payı birkaç yüz ürün mertebesinde.
- Eşleme tercihleri: tabletler **Bilgisayar**, akıllı saat ve bileklikler **Diğer iletişim
  cihazları**, bilgisayar bileşenleri (SSD, RAM, anakart, kasa) **Bilgisayar çevre birimleri**,
  Apple TV ve HomePod **Ses ve görüntü ekipmanı** altında.

**Kapsam dışı**: aynı CSV'lere düşen ama 08'e girmeyen ürünler. Oyun konsolları, VR gözlükleri,
küçük ev aletleri, beyaz eşya, kişisel bakım cihazları ve yazılım lisansları.

## Hizmet kalemleri: kaynak başına

| Kalem | Scraper | Kaynak başına satır (2026-10-10) | Toplam |
|---|---|---|---|
| Cep telefonu hizmet ücreti | `Telecom/scraper.py` | Türk Telekom ~420, Turkcell ~220, Vodafone ~110, NetGSM 8 | ~760 |
| İnternet hizmet ücreti | `Telecom/internet.py` | Türk Telekom ~200, Superonline 92, Kablonet 27, TurkNet 14, Vodafone 11, Milleni 7, GIBIRNet 22 | ~380 |
| Bilgi ve iletişim ekipmanı bakım / onarım ücreti | `Telecom/repair.py` | GSM İletişim ~4.500, Huawei ~600, Apple ~530, Samsung ~170 | ~5.800 |
| Dijital içerik / streaming platform aboneliği | `Telecom/streaming.py` | YouTube Premium 5, Disney+ 4, Spotify 4, Tivibu 4, TV+ 4, MUBI 3, Netflix 3, HBO Max 2, GAIN 2, Prime 1, Apple TV+ 1, Tabii 1 | 34 |

- Mobil tarifelerde faturalı ve faturasız tarifeler ile ek paketler ayrı satırdır.
- Onarımda her model + hizmet (örneğin "iPhone 15 ekran değişimi") bir satırdır. Sepet henüz
  belirlenmedi, kaynakların yayımladığı her şey toplanıyor.
- Streaming'de her plan ve periyot (aylık / yıllık) bir satırdır. `streaming.py` TOD'u da
  destekliyor (2026-10-09 yerel çalıştırmada 8 satır), ama sunucunun 2026-10-10 çıktısında TOD dosyası
  yok; sunucu logunda kontrol edilmeli.
