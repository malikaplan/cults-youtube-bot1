# Cults3D → YouTube Otomasyon Projesi — Durum Özeti

## Ne yapılıyor?
Cults3D hesabındaki (kullanıcı adı: **MakDesign**) ~1270 model tek tek otomatik
olarak işleniyor: başlık, açıklama, etiket ve video Cults'tan çekiliyor,
video dikey (Shorts) formata çevrilip YouTube kanalına (**retrotechnoretro**)
günde 6 video olacak şekilde, ileri tarihe planlanmış (private + publishAt)
olarak yükleniyor.

## Dosyalar (hepsi aynı klasörde: Masaüstü/cults)
- `cults_to_youtube.py` — ana script, her gün çalıştırılır
- `config.py` — Cults kullanıcı adı + API key (bir kere dolduruldu, dokunulmuyor)
- `client_secret.json` — Google OAuth kimlik bilgisi (Google Cloud projesi:
  cultsyoutube, proje no: 1080471726498, malikaplan@gmail.com hesabında açıldı)
- `token.pickle` — YouTube'a giriş yetkisi (otomatik oluştu, silinmemeli)
- `state.json` — kaldığı yeri hatırlayan ilerleme dosyası (otomatik oluştu)

## Şu ana kadar çözülen sorunlar
1. Cults GraphQL alan adı `creations` değil `creationsBatch` → düzeltildi
   (limit/offset + results yapısı, `name(locale: EN)` gibi locale parametreli)
2. YouTube OAuth "access_denied" hatası → Google Cloud Console'da
   **retrotechnoretro@gmail.com** test users listesine eklendi
3. Video linki API'de yoktu → model sayfası (creation.url) scrape edilerek
   `fbi.cults3d.com/.../....mp4` linki regex ile otomatik bulunuyor
   (tarayıcı User-Agent header'ı şart, yoksa engellenebiliyordu)
4. "YouTube Data API v3 has not been used" hatası → Google Cloud Console'da
   API etkinleştirildi
5. Videolar yatay geliyordu, Shorts olmuyordu → ffmpeg ile otomatik
   1080x1920 dikey formata (bulanık arka plan doldurmalı) çevriliyor artık,
   başlığa/açıklamaya otomatik #Shorts ekleniyor
6. **ÖNEMLİ:** Cults hesabında NSFW/yetişkin içerikli modeller de var
   (örn. "Hentai Punk Girl Topless", "Sarah NSFW 3D Print"). Bunlar YouTube
   kurallarını ihlal eder, kanal kapatılmasına yol açabilir. Script'e
   otomatik NSFW filtresi eklendi (`is_nsfw()` fonksiyonu, anahtar kelime
   bazlı) — bu tür modeller artık otomatik atlanıyor.
   ⚠️ Daha önce yüklenmiş 2 NSFW video YouTube Studio'dan ELLE silinmeli
   (silindiyse bu satırı yok sayın).

## Günlük kullanım
Her gün (istediğiniz saatte) klasörde şunu çalıştırın:
```
python cults_to_youtube.py
```
Bir sonraki 6 model işlenir (NSFW olanlar hariç), videolar yüklenir,
bir sonraki güne otomatik planlanır. Elle başka bir şey yapmaya gerek yok.

## Bilinen kısıtlar
- Günde maksimum 6 video (YouTube'un varsayılan API kotası). 1270 model
  ≈ 212 gün sürer. Google'a kota artışı başvurusu yapılırsa hızlanabilir.
- ffmpeg bilgisayarda kurulu olmalı (`winget install ffmpeg`)

## Sohbet devam ederse Claude'a not
Yeni bir sohbette bu dosyayı yükleyip "kaldığımız yerden devam" denirse:
yukarıdaki bağlamla script'in mevcut halini (varsa hata mesajıyla birlikte)
inceleyip aynı şekilde adım adım, jargon kullanmadan, kullanıcıyı gereksiz
kopyala-yapıştıra zorlamadan yardımcı olunmalı. Kullanıcı teknik detaylarla
uğraşmak istemiyor, doğrudan çalışan çözüm istiyor.
