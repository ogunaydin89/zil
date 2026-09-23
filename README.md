# Zil — Okul Zil ve Tören Sistemi (v3)

Masaüstü uygulaması + tepsi (system tray) simgesi. Arayüz, Windows 11'in
WebView2 bileşeniyle **kendi uygulama penceresinde** açılır — tarayıcı yok,
adres çubuğu yok. Zil motoru Python tarafında çalışır:
**pencere kapalıyken de ziller çalar.**

Pencereyi kapatmak uygulamadan çıkmaz, tepsiye indirir. Çıkmak için tepsi
menüsünden **Çıkış**.

---

## Çalıştırma

| İşlem | Komut |
|---|---|
| Başlat (tepsiye, pencere gizli) | `pythonw zil.pyw` |
| Başlat + pencereyi aç | `Zil v3.lnk` (masaüstü) veya `pythonw zil.pyw --panel` |
| Pencere yerine tarayıcı kullan | `pythonw zil.pyw --browser` |
| Durum | `python autostart.py status` |
| Açılışta başlat | `python autostart.py enable` |
| Açılıştan kaldır | `python autostart.py disable` |

Tepsi simgesine çift tıklamak paneli açar. Sağ tık menüsü: panel, **tüm sesleri
durdur**, zil sistemini aç/kapat, yapılandırmayı yeniden yükle, çıkış.

## Klasör yapısı

```
Zil/
  zil.pyw          giriş noktası (pythonw = konsol penceresi yok)
  autostart.py     başlangıç / masaüstü kısayolu yönetimi
  core/            motor
    store.py       ayar + program + kayıt dosyaları
    audio.py       öncelikli ses motoru
    scheduler.py   duvar saati zamanlayıcı
    server.py      127.0.0.1 kontrol paneli sunucusu
    app.py         pencere + tepsi + bağlantılar
    window.py      yerel uygulama penceresi (WebView2)
    migrate.py     eski config.js → JSON dönüştürücü
  ui/              kontrol paneli (HTML/CSS/JS)
  audio/           bells/ anthems/ sirens/
  data/            settings.json, schedule.json, ring-log.jsonl,
                   fired-today.json (bugün çalan ziller)
  lib/             gömülü bağımlılıklar (pygame, pystray, Pillow, pywebview)
```

Tüm yapılandırma `data/` içindedir. Klasörü kopyalarsanız sistem taşınır —
tarayıcı `localStorage`'ına bağımlılık yoktur.

---

## Tasarım kararları

**Ses önceliği.** `acil durum (3) > tören (2) > ders zili (1)`. Düşük öncelikli
bir ses, yüksek öncelikli olanı **kesemez**. Yangın sireni çalarken 10:05 çıkış
zili gelirse zil engellenir, siren biter bitmez (tolerans süresi içindeyse) çalar.
**TÜM SESLERİ DURDUR** her zaman önceliklidir.

**Gecikme toleransı.** Ziller tam `HH:MM` eşleşmesiyle değil, geçen süreyle
çalar. Bir kontrol adımı atlanırsa (uyku, yoğunluk) zil `catchup_seconds`
(varsayılan 90 sn) içinde hâlâ çalar. Her zil günde en fazla bir kez çalar.

**%0 gerçekten sessizdir.** v2'de `(değer || 100)` ifadesi 0'ı 100'e çeviriyordu.

**Çift çalma koruması.** Çalan ziller `data/fired-today.json` dosyasına yazılır.
Uygulama bir zilden hemen sonra yeniden başlarsa (çökme, güncelleme, yeniden
başlatma) o zil ikinci kez çalmaz. Gün değişince liste sıfırlanır.

**Güvenlik.** Sunucu yalnızca `127.0.0.1`'e bağlanır ve değişiklik yapan her
istek, sayfaya çalışma anında gömülen oturum anahtarını taşımak zorundadır.
Aksi hâlde tarayıcıdaki herhangi bir sayfa okul zilini çaldırabilirdi.

**Neden .exe değil?** Bu makinede **Smart App Control** etkin (zorunlu kip).
Yeni derlenmiş, imzasız bir `.exe` engellenirdi — nitekim Electron'un yerel
modülü bu yüzden engellendi. Zaten imzalı ve güvenilen `pythonw.exe` üzerinden
çalışmak bu sorunu tamamen ortadan kaldırır.

---

## Zil sesini değiştirme

1. Ses dosyasını doğru klasöre kopyalayın:

   | Ne için | Klasör |
   |---|---|
   | Ders zilleri (öğrenci / öğretmen / çıkış) | `audio\bells\` |
   | Törenler (İstiklal Marşı, saygı duruşu) | `audio\anthems\` |
   | Acil durum sirenleri | `audio\sirens\` |

2. **Ayarlar** sekmesini açın — yeni dosya listede belirir.
3. İlgili zilin açılır listesinden dosyayı seçin, **KAYDET**'e basın.
4. **Panel**'deki manuel düğmeyle dinleyin.

`.wav`, `.mp3` ve `.ogg` desteklenir. Uygulama çalışırken dosya kopyalayabilir,
hatta mevcut bir dosyanın üzerine yazabilirsiniz — çalma bitince dosya serbest
bırakılır.

Dosya adı yanlışsa zil çalmaz; panelde kırmızı uyarı çıkar ve **Kayıt**
sekmesine `error` olarak düşer.

---

## Özel günler

- **Tatiller** — o tarihte ders zili çalmaz. *Bitiş* sütunu doldurulursa aralık
  olur (tek satırda tüm sömestr/yaz tatili). *Yarım gün* saati girilirse o saate
  kadar ziller normal çalar, sonrasında susar — arefe günleri için.
  Aralıklar çakışırsa tam tatil yarım günü ezer.
- **Gün değişimi** — belirli bir tarihte başka bir günün programı uygulanır.
- **Planlı törenler** — tarih + saat + ses. **Tatillerde de çalar** (29 Ekim'de
  zil çalmasın ama İstiklal Marşı çalsın senaryosu için).

---

## Yüklü takvim (2026-2027)

MEB çalışma takvimi ve resmî tatiller **Özel Günler** sekmesinde hazır:

| Tarih | |
|---|---|
| 28.10.2026 | Cumhuriyet Bayramı Arifesi — **yarım gün**, 13:00 sonrası zil yok |
| 29.10.2026 | Cumhuriyet Bayramı |
| 16–20.11.2026 | 1. Dönem Ara Tatili |
| 01.01.2027 | Yılbaşı |
| 25.01–05.02.2027 | Yarıyıl (Sömestr) Tatili |
| 08–12.03.2027 | 2. Dönem Ara Tatili *(Ramazan Bayramı'nı da kapsar)* |
| 23.04.2027 | Ulusal Egemenlik ve Çocuk Bayramı |
| 01.05.2027 | Emek ve Dayanışma Günü |
| 15.05.2027 | Kurban Bayramı Arifesi — **yarım gün**, 13:00 sonrası zil yok |
| 16–19.05.2027 | Kurban Bayramı (19 Mayıs aynı zamanda Gençlik ve Spor Bayramı) |
| 26.06–31.08.2027 | Yaz Tatili |

> **Eylül 2027 kasıtlı olarak boş bırakıldı.** Yaz tatili 31 Ağustos'ta bitiyor;
> 2027-2028 takvimi açıklandığında *Bitiş* tarihini okulun açılış gününe kadar
> uzatın. O güne kadar Eylül 2027'de zil çalar.

Öğretim yılı 14.09.2026 – 25.06.2027. Bu takvimle yıl boyunca **5.074 zil** çalıyor.

---

## Sorun giderme

| Belirti | Bakılacak yer |
|---|---|
| Hiç zil çalmıyor | Panelde durum rozeti *DURAKLATILDI* mı? |
| Ses gelmiyor | Ayarlar → Ses Seviyesi %0 olabilir |
| Panel açılmıyor | Tepsi simgesi duruyor mu? Port 8765 meşgulse 8766+ denenir |
| Ne zaman çaldığını görmek | **Kayıt** sekmesi (`data/ring-log.jsonl`) |
| Ses aygıtı hatası | Panelde kırmızı uyarı şeridi çıkar |
