# Hepsiemlak shard sunucuları

Dört kişinin elle çalıştırdığı Hepsiemlak taramasını (`InflationItems/Codes/04_Housing/Hepsiemlak/`) dört ayrı
sunucuya koyar: **her sunucu bir shard, her shard ayrı IP** (site IP başına hızı sınırlıyor; sunucu başına tek
oturum, bekleme süreleri aynı, proxy/parmak izi döndürme yok). Shard adları ve il listeleri `shards.json`'da
aynen kalır; çıktı `InflationItems/Datas/04_Housing/Hepsiemlak/YYYY-MM-DD_<shard>.csv`.

Şimdiki aşama: **çalışıyor mu testi.** Otomatik GitHub push'u ve cron henüz yok; veri sunucuda kalır.

| Shard |
|---|
| zelal |
| dani |
| neslihan |
| ekin |

(Sunucu IP atamaları repoda değil, sahibinin sunucu Excel'indeki "Sunucu" sayfasında tutulur.)

## Kurulum (her sunucuda bir kere, root)

Git'siz paket (repo kökünde, Windows):

```powershell
tar --exclude checkpoints --exclude __pycache__ -czf hepsiemlak_server.tgz deploy/hepsiemlak-server InflationItems/Codes/04_Housing/Hepsiemlak
scp hepsiemlak_server.tgz root@<sunucu-ip>:/root/
```

Sunucuda:

```bash
mkdir -p /root/hepsiemlak && tar -xzf /root/hepsiemlak_server.tgz -C /root/hepsiemlak && cd /root/hepsiemlak
bash deploy/hepsiemlak-server/setup.sh
```

`setup.sh` saat dilimini ayarlar, tarayıcı kütüphanelerini ve xvfb'yi kurar, uv ile Python 3.11 venv ve
`cloakbrowser` kurar, `bin/run_shard.sh`'yi koyar. Cron kurmaz. Tarayıcı (~200 MB) ilk çalıştırmada iner.

## Sınırlı test

```bash
cd /root/hepsiemlak && bin/run_shard.sh zelal --max-listings 100 --output test_zelal.csv
tail -5 log.txt; tail -20 server_logs/hepsiemlak_zelal_*.log
```

Beklenen: log'da `wrote 100 rows`, hata yok, CSV'de 100 satır ve boş fiyat/oda/m² yok. `--output`/`--max-listings`
içeren çalıştırma testtir: tek deneme, yeniden deneme yok. Test dosyalarını sonra sil
(`InflationItems/Datas/04_Housing/Hepsiemlak/test_*.csv`, `Codes/04_Housing/Hepsiemlak/checkpoints/test_*.json`).

Tam çalıştırma: `bin/run_shard.sh <shard>`.

## `run_shard.sh` ne yapar

- Shard başına tek çalışma (`flock`). Bugünün dosyası tamamsa "already complete" der ve çıkar.
- `scraper.py` 1 ile çıkarsa (site engelledi, route kayboldu) 30 dk bekler ve `--resume` ile devam eder;
  başlangıçtan 20 saat sonrasına kadar dener. Her deneme en fazla 8 saat sürer; arada kalan tarayıcılar öldürülür.
- Bitişte `log.txt`'ye tek satır: `OK` / `LOW` (satır sayısı `shards.json`'daki sitemap sayısının %70'inin altında)
  / `INCOMPLETE`, satır sayısı, boş alan oranı, kayıp route sayısı.
- Ayarlar (ortam değişkeni veya `.env`): `ATTEMPT_TIMEOUT`, `RETRY_WAIT`, `DEADLINE_H`.

`scraper.py` artık beklenmedik bir hatada route'u taze tarayıcıyla en fazla 3 kez dener; yine olmazsa route'u
`lost` olarak checkpoint'e yazar, çalışma "tamamlandı" sayılmaz ve bir sonraki `--resume` onu yeniden dener
(eskiden böyle bir route sessizce o gün eksik kalıyordu).
