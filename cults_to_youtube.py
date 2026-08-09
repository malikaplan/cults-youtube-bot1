"""
CULTS3D -> YOUTUBE OTOMASYON SCRIPTI
====================================
Kurulum (bir kere):
  pip install requests google-auth-oauthlib google-api-python-client Pillow

Doldurulacak alanlar:
  1) CULTS_USERNAME, CULTS_API_KEY   -> config.py içinde (zaten dolu)
  2) CLIENT_SECRET_FILE               -> Google Cloud Console'dan indirilen client_secret.json
  3) logo.png                         -> aynı klasörde, video altına eklenecek logo (şeffaf PNG önerilir)
  4) 8 mp3 dosyanız                   -> aynı klasörde (ana/kök dizin), ayrı bir alt klasör GEREKMİYOR
  5) (opsiyonel) TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID -> her çalıştırmada özet mesaj almak için

Çalıştırma:
  calistir.bat dosyasına çift tıklayın (veya: python cults_to_youtube.py)

Her çalıştırmada state.json'daki kaldığı yerden devam eder, VIDEOS_PER_DAY kadar
video yükler (private + publishAt ile planlı, TÜMÜ AYNI GÜN İÇİNDE), sonraki
çalıştırmada bir sonraki güne geçer.
"""

import json, os, re, random, subprocess, datetime, webbrowser
from pathlib import Path
import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
from PIL import Image, ImageDraw, ImageFont
from config import CULTS_USERNAME, CULTS_API_KEY

# ============ DOLDURUN / AYARLAR ============
CLIENT_SECRET_FILE = "client_secret.json"
VIDEOS_PER_DAY = 6  # YouTube'un ücretsiz günlük kotasında güvenli maksimum budur, değiştirme

# Global (tek ülkeye özel değil) yayın saatleri - UTC olarak yazılı ama Türkiye
# saatinde (UTC+3) AYNI GÜN içinde kalacak şekilde seçildi, gece yarısını geçmiyor:
#   9 UTC  = 12:00 TR / 06:00 New York / 11:00 Londra
#  11 UTC  = 14:00 TR / 08:00 New York / 13:00 Londra
#  13 UTC  = 16:00 TR / 10:00 New York / 15:00 Londra
#  15 UTC  = 18:00 TR / 12:00 New York / 17:00 Londra
#  17 UTC  = 20:00 TR / 14:00 New York / 19:00 Londra
#  19 UTC  = 22:00 TR / 16:00 New York / 21:00 Londra
PUBLISH_HOURS_UTC = [9, 11, 13, 15, 17, 19]

# İlk 6 video hangi tarihte yayına girsin? (YYYY-MM-DD). None -> otomatik bugün/yarın.
START_DATE = "2026-08-01"

LOGO_PATH = "logo.png"          # video altına eklenecek logo
MAX_SHORT_SECONDS = 179          # YouTube Shorts üst sınırı (3 dk), videolar bunu geçemez
CANVAS_W, CANVAS_H = 1080, 1920  # dikey Shorts çözünürlüğü
BAND_HEIGHT = 300                # üst (başlık) şeridinin yüksekliği (px)
LOGO_BAND_HEIGHT = 380           # alt (logo) şeridinin yüksekliği (px) - kare logo
                                  # gerçekten büyüyebilsin diye başlık şeridinden
                                  # daha yüksek tutuldu (300px'te zaten neredeyse
                                  # tıka basa doluyordu, büyütmeye fiziksel yer yoktu)
TITLE_TOP_MARGIN = 230           # başlık şeridinin üstünde bırakılan boşluk - YouTube
                                  # Shorts arayüzü (ses/duraklat/tam ekran/ilerleme
                                  # çubuğu) ile çakışmasın diye şerit ekranın en
                                  # tepesinden aşağı iner (160 yetmedi, artırıldı)

# Her çalıştırma sonunda özet mesajı için (boş bırakırsanız bildirim gönderilmez)
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

# ---------- MÜZİK (arka plan müziği + Spotify tanıtımı) ----------
# mp3 dosyaları bu klasörde olmalı (hem Masaüstü/cults hem GitHub repo kökünde):
# mp3 dosyaları bu klasörde olmalı (hem Masaüstü/cults hem GitHub repo kökünde) -
# "." = script ile aynı klasör (ana/kök dizin), ayrı bir alt klasör GEREKMİYOR:
MUSIC_DIR = "."

# Her video için bu listeden RASTGELE bir şarkı seçilir, şarkının içinde
# RASTGELE bir başlangıç saniyesinden itibaren video süresi kadar kırpılır.
MUSIC_TRACKS = [
    {"file": "Steel Wings.mp3", "title": "Steel Wings",
     "spotify": "https://open.spotify.com/intl-tr/track/6E9u8N5KFI57zWOeRKQJV3?si=c353a5f4446447b9"},
    {"file": "Black Hydraulics.mp3", "title": "Black Hydraulics",
     "spotify": "https://open.spotify.com/intl-tr/track/5uD4nOMWKsS79XLbeM9I7l?si=737419ff45c54d27"},
    {"file": "Short Circuit.mp3", "title": "Short Circuit",
     "spotify": "https://open.spotify.com/intl-tr/track/2heiNPglXZR0CQBtiquSmu?si=5f581054d4f44b3c"},
    {"file": "Night Shift.mp3", "title": "Night Shift",
     "spotify": "https://open.spotify.com/intl-tr/track/1PMEkhE7t8w8kedOkFLV6L?si=799688fd00d44070"},
    {"file": "Engine Room.mp3", "title": "Engine Room",
     "spotify": "https://open.spotify.com/intl-tr/track/4VgVkGZvkhsy2aOlWEgeBs?si=58de1d8261f24cc0"},
    {"file": "Glitch in the Code.mp3", "title": "Glitch in the Code",
     "spotify": "https://open.spotify.com/intl-tr/track/4yLEYeUXS3M2145ad9729r?si=d85b9024ac9d4292"},
    {"file": "System Rage.mp3", "title": "System Rage",
     "spotify": "https://open.spotify.com/intl-tr/track/3o4P239ROD0Rbdq9mRSUy5?si=8720fb662b1c456f"},
    {"file": "The Foundry.mp3", "title": "The Foundry",
     "spotify": "https://open.spotify.com/intl-tr/track/043VQQMoRpRj3OaZqyidbB?si=28134284f5a448fc"},
]
MUSIC_ARTIST_SPOTIFY = "https://open.spotify.com/intl-tr/artist/2Wcd68SGrXGBGzO1BbxKVX?si=77Xbxd55QSS_7f8iv6LkRQ"

# (opsiyonel) ayrı müzik YouTube kanalın için çapraz tanıtım - doldurursan
# her video açıklamasına otomatik eklenir, boş bırakırsan hiç eklenmez:
MUSIC_CHANNEL_NAME = "The Soundscapes"   # örn: "Retro Techno Beats"
MUSIC_CHANNEL_URL = "https://www.youtube.com/@thesoundscapess"    # örn: "https://youtube.com/@kanaladi"
# ==============================================

STATE_FILE = "state.json"
TOKEN_FILE = "token.pickle"
DASHBOARD_FILE = "durum.html"
CULTS_ENDPOINT = "https://cults3d.com/graphql"

# Windows'ta ffmpeg her çağrıldığında görünür siyah pencere açmasın diye:
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://cults3d.com/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Connection": "keep-alive",
}

def _fetch_page_via_seleniumbase(url):
    """Model sayfasini SeleniumBase'in UC Mode'u (undetected-chromedriver)
    ile acar - Cloudflare Turnstile dogrulamasini asmak icin ozellesmis
    bir teknik. Ayri bir program/uygulama GEREKMEZ, sadece
    'pip install seleniumbase' yeterli, kendi Chrome'unu kullanir.
    Basarisiz olursa None doner."""
    try:
        from seleniumbase import SB
        with SB(uc=True, headless=False, incognito=True) as sb:
            sb.uc_open_with_reconnect(url, reconnect_time=4)
            try:
                sb.uc_gui_click_captcha()
            except Exception:
                pass
            sb.sleep(2)
            html = sb.get_page_source()
            return 200, html
    except Exception as e:
        print(f"   [HATA] SeleniumBase istegi basarisiz: {e}")
        return None, None


# ============================================================
# CULTS3D
# ============================================================

def cults_query(query, max_retries=8):
    """Cults3D ara sira gecici 403 verebiliyor (bilinen, kisa sureli bir
    sorun). Bu yuzden basarisiz olursa birkac kez, artan bekleme
    sureleriyle (10s, 20s, 40s, 60s, 90s, 120s, 180s, 240s) otomatik
    tekrar dener - boylece elle 'Re-run' yapmaya gerek kalmaz."""
    import time
    delays = [10, 20, 40, 60, 90, 120, 180, 240]
    last_error = None
    for attempt in range(max_retries):
        try:
            r = requests.post(CULTS_ENDPOINT, json={"query": query},
                               auth=(CULTS_USERNAME, CULTS_API_KEY),
                               headers=BROWSER_HEADERS)
            r.raise_for_status()
            data = r.json()
            if "errors" in data:
                raise RuntimeError(data["errors"])
            return data["data"]
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = delays[min(attempt, len(delays) - 1)]
                print(f"   [UYARI] Cults3D istegi basarisiz ({e}), {wait} saniye sonra tekrar denenecek "
                      f"(deneme {attempt + 1}/{max_retries})...")
                time.sleep(wait)
            else:
                print(f"   [HATA] Cults3D {max_retries} denemeden sonra hala cevap vermedi, vazgeciliyor.")
    raise last_error


CREATIONS_CACHE_FILE = "creations_cache.json"
CREATIONS_CACHE_MAX_AGE_HOURS = 168  # bu sureden taze onbellek varsa API'ye hic gidilmez


def get_all_creations(force_refresh=False):
    """Kendi profilinizdeki tüm modelleri (isim, açıklama, etiket) çeker.

    Cults3D'ye gunde onlarca kez (Instagram scripti gunde 25 kez tetikleniyor)
    ayni listeyi bastan sona sayfalayarak sormak, Cults3D'nin gecici 403
    korumasini tetikliyordu. Bu yuzden sonuc bir dosyada (creations_cache.json)
    onbellege alinir; CREATIONS_CACHE_MAX_AGE_HOURS saatten taze bir onbellek
    varsa API'ye HIC gidilmez, dogrudan onbellekten donulur. Onbellek repoya
    commit edilip GitHub Actions calistirmalari arasinda da tasindigi icin
    gunluk gercek API istegi ~450'den ~1 sefere duser."""
    if not force_refresh and Path(CREATIONS_CACHE_FILE).exists():
        try:
            cache = json.loads(Path(CREATIONS_CACHE_FILE).read_text(encoding="utf-8"))
            fetched_at = datetime.datetime.fromisoformat(cache["fetched_at"])
            age_hours = (datetime.datetime.utcnow() - fetched_at).total_seconds() / 3600
            if age_hours < CREATIONS_CACHE_MAX_AGE_HOURS:
                print(f"   [CACHE] Model listesi onbellekten kullanildi (yasi: {age_hours:.1f} saat, "
                      f"{len(cache['creations'])} model).")
                return cache["creations"]
            else:
                print(f"   [CACHE] Onbellek eskimis ({age_hours:.1f} saat), API'den yeniden cekilecek.")
        except Exception as e:
            print(f"   [UYARI] Onbellek okunamadi, API'den yeniden cekilecek: {e}")

    max_fetch_attempts = 3
    for fetch_attempt in range(1, max_fetch_attempts + 1):
        creations = []
        offset = 0
        limit = 50
        reported_total = None
        while True:
            q = f"""
            {{
              myself {{
                creationsBatch(limit: {limit}, offset: {offset}) {{
                  total
                  results {{
                    name(locale: EN)
                    url(locale: EN)
                    shortUrl
                    description(locale: EN)
                    tags(locale: EN)
                    illustrationImageUrl
                  }}
                }}
              }}
            }}
            """
            data = cults_query(q)
            reported_total = data["myself"]["creationsBatch"]["total"]
            batch = data["myself"]["creationsBatch"]["results"]
            if not batch:
                break
            creations.extend(batch)
            offset += limit
            if offset >= reported_total:
                break

        # Cults3D bazen 403 vermeden, normal (200) ama BOS/EKSIK bir sayfa
        # donduruyor - bu durumda "liste bitti" sanip yariminda kalmis bir
        # listeyi hem KULLANMAK hem ONBELLEGE YAZMAK cok tehlikeli olurdu
        # (butun gun boyunca bozuk/eksik liste kullanilirdi). Bu yuzden
        # gelen liste, API'nin bildirdigi "total" degerinden belirgin
        # sekilde kisaysa (glitch isareti), bunu KABUL ETMEYIP tekrar
        # deniyoruz.
        if reported_total and len(creations) < reported_total * 0.9:
            print(f"   [UYARI] Cults3D eksik/bozuk liste dondurdu "
                  f"({len(creations)}/{reported_total} model geldi) - "
                  f"onbellege yazilmadan tekrar denenecek "
                  f"(deneme {fetch_attempt}/{max_fetch_attempts}).")
            if fetch_attempt < max_fetch_attempts:
                import time
                time.sleep(15)
                continue
            else:
                print("   [HATA] Tekrar denemeler de eksik geldi, mevcut (eksik) onbellek "
                      "DOKUNULMADAN birakiliyor, bu calistirmada eski onbellek varsa o kullanilacak.")
                if Path(CREATIONS_CACHE_FILE).exists():
                    cache = json.loads(Path(CREATIONS_CACHE_FILE).read_text(encoding="utf-8"))
                    return cache["creations"]
                return creations  # hic onbellek yoksa elimizdeki eksik listeyle devam et

        Path(CREATIONS_CACHE_FILE).write_text(
            json.dumps({"fetched_at": datetime.datetime.utcnow().isoformat(), "creations": creations},
                       ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"   [CACHE] Model listesi API'den cekildi ve onbellege yazildi ({len(creations)} model).")
        return creations


# ------------------------------------------------------------------
# GUNLUK ISTEK KOTASI (Cults3D'nin belgelenen limiti: ~60 istek/30sn,
# ~500 istek/gun). Bu limiti asmak account'u gecici olarak
# bloke ediyor (403). Bu sayac hem YouTube hem Instagram scriptleri
# arasinda PAYLASILIR (ayni dosyaya yazar) - ikisi toplam gunluk
# kotayi asmasin diye.
# ------------------------------------------------------------------
_BUDGET_FILE = "request_budget.json"
_DAILY_REQUEST_CAP = 350  # 500'un altinda, guvenlik payi birakilmis

def _check_and_use_budget():
    """Gunluk paylasimli istek kotasindan 1 hak dusurur. Kota bittiyse
    False doner (o gun icin sayfa cekmeyi durdurmak gerekir)."""
    import time
    today = datetime.date.today().isoformat()
    data = {"date": today, "count": 0}
    if os.path.exists(_BUDGET_FILE):
        try:
            with open(_BUDGET_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if saved.get("date") == today:
                data = saved
        except Exception:
            pass
    if data["count"] >= _DAILY_REQUEST_CAP:
        return False
    data["count"] += 1
    with open(_BUDGET_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return True


def get_video_url(creation, debug=False):
    """
    Modelin herkese açık sayfasını indirip, video dosyasının orijinal
    linkini (fbi.cults3d.com/.../....mp4) bulur. Bulamazsa herhangi bir
    .mp4/.webm/.mov linkine geri döner. debug=True ise nedenini yazdırır.

    Cults3D'nin GUNLUK ISTEK KOTASI var (~500/gun). Once bu script
    tekrar tekrar (4 kez) deniyordu - bu kotayi hizla tuketip sorunu
    BUYUTUYORDU. Artik: 403 gelince TEK seferde vazgecilip bir sonraki
    modele gecilir (kota bosa harcanmaz), ve paylasimli gunluk sayac
    dolduysa sayfa cekme hic denenmez.
    """
    import time
    page_url = creation.get("url")
    if not page_url:
        if debug:
            print("   [DEBUG] creation'da 'url' alanı yok")
        return None

    if not _check_and_use_budget():
        if debug:
            print("   [DEBUG] gunluk istek kotasi doldu - bu calistirmada "
                  "sayfa cekmeye devam edilmiyor, yarin tekrar denenecek.")
        return "RETRY_LATER"

    try:
        # Cok hizli art arda istek atmamak icin bekleme.
        time.sleep(random.uniform(1.0, 2.0))
        status, html = _fetch_page_via_seleniumbase(page_url)
        if html is None:
            # FlareSolverr'a hic ulasilamadi (kapali/kurulu degil) -
            # bu modeli "videosuz" saymadan bir sonraki calistirmaya birak.
            return "RETRY_LATER"
        if status == 403:
            if debug:
                print("   [DEBUG] status=403 (FlareSolverr da asamadi) - bu model "
                      "'videosuz' SAYILMAYACAK, bir sonraki calistirmada tekrar denenecek.")
            return "RETRY_LATER"
        if debug:
            print(f"   [DEBUG] status={status} html_uzunluk={len(html)} "
                  f"'mp4' geciyor mu={'mp4' in html} 'fbi.cults3d.com' geciyor mu={'fbi.cults3d.com' in html}")
        match = re.search(r'https?://fbi\.cults3d\.com/[^\s"\'<>]+\.mp4', html, re.IGNORECASE)
        if match:
            return match.group(0)
        match = re.search(r'https?://[^\s"\'<>]+\.(?:mp4|webm|mov)', html, re.IGNORECASE)
        return match.group(0) if match else None
    except Exception as e:
        if debug:
            print(f"   [DEBUG] hata: {e}")
        return None


def build_music_credit(music_track):
    """Videoda kullanılan müzik için açıklamaya eklenecek kredi/tanıtım
    bloğunu oluşturur. music_track None ise (müzik bulunamadıysa) boş
    string döner."""
    if not music_track:
        return ""
    lines = [f"\n\n🎵 Music: {music_track['title']} — Listen on Spotify: {music_track['spotify']}"]
    if MUSIC_ARTIST_SPOTIFY:
        lines.append(f"More music: {MUSIC_ARTIST_SPOTIFY}")
    if MUSIC_CHANNEL_NAME and MUSIC_CHANNEL_URL:
        lines.append(f"More tracks like this on {MUSIC_CHANNEL_NAME}: {MUSIC_CHANNEL_URL}")
    return "\n".join(lines)


def clean_description(desc):
    """Cults açıklamasındaki link/reklam satırlarını temizler (kendi modelinizin
    linkini zaten ayrıca ekliyoruz, tekrar/istenmeyen link kalmasın)."""
    if not desc:
        return ""
    cleaned = []
    for line in desc.splitlines():
        l = line.strip()
        if not l:
            continue
        if l.lower().startswith("http") or "cults3d.com" in l.lower():
            continue
        cleaned.append(l)
    return "\n".join(cleaned).strip()


# ============================================================
# DURUM (state.json) VE PANEL (durum.html)
# ============================================================

def load_state():
    if Path(STATE_FILE).exists():
        state = json.loads(Path(STATE_FILE).read_text())
    else:
        state = {"next_index": 0, "next_publish_date": None}
    state.setdefault("run_count", 0)
    state.setdefault("total_uploaded", 0)
    state.setdefault("total_models", None)
    state.setdefault("start_date", None)
    state.setdefault("last_run", None)
    state.setdefault("history", [])
    # Modeller artık sıra numarasına (next_index) DEĞİL, her modelin kendi
    # linkine göre takip ediliyor. Böylece Cults'a yeni model eklendiğinde
    # (ki bu mevcut sıralamayı kaydırabilir) hiçbir model atlanmaz ya da
    # yanlışlıkla tekrar yüklenmez.
    state.setdefault("processed_urls", [])
    # Video yayına girdiğinde (private+publishAt planlaması nedeniyle YouTube
    # henüz yayınlanmamış videoya yorum eklemeyi reddedebiliyor) atılamayan
    # model-linki yorumları burada bekletilir, her çalıştırmada tekrar denenir.
    state.setdefault("pending_comments", [])
    return state


def save_state(state):
    Path(STATE_FILE).write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _hour_tr(h):
    return (h + 3) % 24


def _open_dashboard(path):
    """Tarayıcı yoksa (ör. GitHub Actions/bulut ortamı) sessizce geçer, hata vermez."""
    try:
        webbrowser.open(f"file://{path}")
    except Exception:
        pass


def build_dashboard(state, total_models):
    last = state.get("last_run") or {}
    history = state.get("history") or []

    hours_list = ", ".join(f"{_hour_tr(h):02d}:00" for h in PUBLISH_HOURS_UTC)

    uploaded_rows = "".join(
        f"<tr><td>{u['title']}</td><td>{u['publish_at']}</td>"
        f"<td><a href='{u['link']}' target='_blank'>Videoyu aç</a></td></tr>"
        for u in last.get("uploaded", [])
    ) or "<tr><td colspan='3'>Bugün yeni video yüklenmedi.</td></tr>"

    remaining = max(total_models - state["next_index"], 0)
    est_days_left = max(-(-remaining // VIDEOS_PER_DAY), 0)  # yukarı yuvarlama

    next_pub = state.get("next_publish_date")
    if next_pub:
        next_pub_date = datetime.datetime.fromisoformat(next_pub).date()
        next_pub_str = next_pub_date.strftime("%d.%m.%Y")
        finish_date = (next_pub_date + datetime.timedelta(days=max(est_days_left - 1, 0))).strftime("%d.%m.%Y")
    else:
        next_pub_str, finish_date = "-", "-"

    errors = last.get("errors") or []
    error_html = ""
    if errors:
        items = "".join(f"<li>{e}</li>" for e in errors)
        error_html = (f"<div class='err'>❌ Bugün {len(errors)} video yüklenemedi — "
                       f"bir sonraki çalıştırmada otomatik tekrar denenecek:<ul>{items}</ul></div>")

    skip_html = ""
    if last.get("skipped_nsfw") or last.get("skipped_no_video"):
        skip_html = (f"<div class='warn'>⚠️ Bugün {last.get('skipped_nsfw',0)} NSFW ve "
                      f"{last.get('skipped_no_video',0)} video-linksiz model atlandı.</div>")

    history_rows = "".join(
        f"<tr><td>Gün {h['day_number']} ({h['date']})</td><td>{len(h.get('uploaded', []))}</td>"
        f"<td>{h.get('skipped_nsfw', 0)}</td><td>{h.get('skipped_no_video', 0)}</td>"
        f"<td>{len(h.get('errors') or [])}</td></tr>"
        for h in list(reversed(history))[:5]
    ) or "<tr><td colspan='5'>Henüz geçmiş yok.</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="UTF-8">
<title>Cults → YouTube Durum Paneli</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; background:#0f1117; color:#e8e8ec; margin:0; padding:32px; }}
  .wrap {{ max-width: 820px; margin: 0 auto; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  h3 {{ margin-top: 30px; }}
  .sub {{ color:#8a8f9c; margin-bottom:20px; }}
  .cards {{ display:flex; gap:14px; flex-wrap:wrap; margin-bottom:22px; }}
  .card {{ background:#1a1d27; border-radius:12px; padding:16px 20px; flex:1; min-width:130px; }}
  .card .num {{ font-size:24px; font-weight:700; color:#7c9cff; }}
  .card .lbl {{ color:#8a8f9c; font-size:12px; margin-top:4px; }}
  table {{ width:100%; border-collapse: collapse; background:#1a1d27; border-radius:12px; overflow:hidden; }}
  th, td {{ text-align:left; padding:9px 14px; font-size:13px; border-bottom:1px solid #262a38; }}
  th {{ color:#8a8f9c; font-weight:600; }}
  a {{ color:#7c9cff; text-decoration:none; }}
  .warn {{ background:#2a1f1a; color:#e0a458; padding:12px 16px; border-radius:10px; margin-bottom:14px; font-size:13px; }}
  .err {{ background:#2a1a1a; color:#e07a7a; padding:12px 16px; border-radius:10px; margin-bottom:14px; font-size:13px; }}
  .info {{ background:#161a24; color:#a9b0c0; padding:14px 18px; border-radius:12px; font-size:13px; line-height:1.7; margin-bottom:22px; }}
</style></head>
<body><div class="wrap">
  <h1>📦 Cults3D → YouTube Otomasyonu</h1>
  <div class="sub">Son çalışma: {last.get('date', '-')}</div>

  <div class="cards">
    <div class="card"><div class="num">{last.get('day_number', '-')}</div><div class="lbl">Gün</div></div>
    <div class="card"><div class="num">{state['total_uploaded']}</div><div class="lbl">Toplam yüklenen</div></div>
    <div class="card"><div class="num">{total_models}</div><div class="lbl">Toplam model</div></div>
    <div class="card"><div class="num">{remaining}</div><div class="lbl">Kalan model</div></div>
    <div class="card"><div class="num">~{est_days_left}</div><div class="lbl">Tahmini kalan gün</div></div>
  </div>

  <div class="info">
    🗓️ <b>Bir sonraki yayın günü:</b> {next_pub_str} &nbsp;·&nbsp;
    🏁 <b>Tahmini bitiş:</b> {finish_date}<br>
    ⏰ <b>Günlük yayın saatleri (TR):</b> {hours_list} &nbsp;·&nbsp; günde {VIDEOS_PER_DAY} video
  </div>

  {error_html}
  {skip_html}

  <h3>Bugün yüklenenler</h3>
  <table>
    <tr><th>Model</th><th>Yayın zamanı (UTC)</th><th></th></tr>
    {uploaded_rows}
  </table>

  <h3>Son 5 gün özeti</h3>
  <table>
    <tr><th>Gün</th><th>Yüklenen</th><th>NSFW atlanan</th><th>Video yok</th><th>Hata</th></tr>
    {history_rows}
  </table>
</div></body></html>"""
    Path(DASHBOARD_FILE).write_text(html, encoding="utf-8")
    return Path(DASHBOARD_FILE).resolve()


# ============================================================
# YOUTUBE
# ============================================================

def add_youtube_comment(youtube, video_id, text):
    """Videoya, izleyicilerin tıklayıp Cults3D modeline gidebilmesi için
    link yorum olarak eklenir. Video henüz yayınlanmamışsa (private+
    publishAt ile planlı) YouTube bu isteği reddedebilir - bu durumda
    False döner, çağıran taraf yorumu 'pending_comments' kuyruğuna alıp
    video gerçekten yayına girdiğinde tekrar dener."""
    try:
        youtube.commentThreads().insert(
            part="snippet",
            body={"snippet": {"videoId": video_id,
                               "topLevelComment": {"snippet": {"textOriginal": text}}}}
        ).execute()
        return True
    except Exception as e:
        print(f"   [YORUM] Şimdilik eklenemedi (video henüz yayında olmayabilir), sonra tekrar denenecek: {e}")
        return False


def retry_pending_comments(youtube, state):
    """Önceki çalıştırmalarda videonun henüz yayında olmaması yüzünden
    atılamamış yorumları tekrar dener; başarılı olanları kuyruktan çıkarır."""
    if not state.get("pending_comments"):
        return
    still_pending = []
    for item in state["pending_comments"]:
        ok = add_youtube_comment(youtube, item["video_id"], item["text"])
        if ok:
            print(f"   [YORUM] Bekleyen yorum artık eklendi -> {item['text']}")
        else:
            still_pending.append(item)
    state["pending_comments"] = still_pending


def get_priority_order(creations, seen_urls_file):
    """Modelleri normalde eskiden beri bilinen sırayla (backlog) döndürür,
    ANCAK Cults3D hesabına bu çalıştırmadan önce YENİ eklenmiş modeller
    varsa onları listenin en başına koyar - böylece yeni yüklenen bir
    model, eski sıradaki modeller bitmeden hemen işlenir."""
    current_urls = [(c.get("shortUrl") or c["url"]) for c in creations]
    if Path(seen_urls_file).exists():
        try:
            seen = set(json.loads(Path(seen_urls_file).read_text(encoding="utf-8")))
        except Exception:
            seen = set(current_urls)
    else:
        seen = set(current_urls)  # ilk çalıştırma: mevcut tüm liste "bilinen" sayılır

    new_ones = [c for c in creations if (c.get("shortUrl") or c["url"]) not in seen]
    rest = [c for c in creations if (c.get("shortUrl") or c["url"]) in seen]

    Path(seen_urls_file).write_text(json.dumps(current_urls, ensure_ascii=False), encoding="utf-8")

    if new_ones:
        names = ", ".join(c["name"] for c in new_ones[:5])
        print(f"   [YENİ MODEL] {len(new_ones)} yeni model tespit edildi, öncelik verilecek: {names}"
              + ("..." if len(new_ones) > 5 else ""))
    return new_ones + rest


def get_youtube_service():
    creds = None
    if Path(TOKEN_FILE).exists():
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE,
                ["https://www.googleapis.com/auth/youtube.upload"])
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
    return build("youtube", "v3", credentials=creds)


def upload_video(youtube, video_path, title, description, tags, publish_at):
    body = {
        "snippet": {"title": title[:100], "description": description[:5000], "tags": tags[:500]},
        "status": {"privacyStatus": "private", "publishAt": publish_at, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
    return response["id"]


# ============================================================
# SEO ETİKET (TAG) TAMAMLAYICI
# ============================================================
# YouTube etiket alanı toplamda ~500 karaktere kadar izin veriyor.
# Cults'tan gelen orijinal etiketler her zaman ÖNCELİKLİ kullanılır;
# eğer alanda boşluk kalırsa, o boşluk (a) başlıktan türetilen anahtar
# kelimelerle ve (b) 3D baskı/Shorts nişine özel, arama hacmi yüksek
# jenerik Google SEO kelimeleriyle dolduruluyor. Sınır asla aşılmaz.

TAG_STOPWORDS = {
    "for", "the", "a", "an", "of", "and", "or", "with", "to", "in", "on",
    "your", "you", "by", "is", "at", "from", "&",
}

EVERGREEN_SEO_TAGS = [
    "3d print", "3d printing", "3d printed", "3d model", "3d printable",
    "stl file", "stl download", "3d printer", "diy 3d print",
    "3d printing ideas", "3d design", "3d printing hobby",
    "how to 3d print", "3d printed parts", "3d printed gadget",
    "3d print tutorial", "makerspace", "3d printing at home",
    "cool 3d prints", "3d printed tool", "print in place",
    "shorts", "3d shorts", "maker", "3d printing project",
    "cults3d", "replacement part 3d print", "spare part 3d printed",
]


def _title_keyword_candidates(title):
    """Başlıktan anlamlı kelime/kelime öbeklerini SEO etiket adayı olarak
    çıkarır (stopword'leri ve çok kısa parçaları atlar)."""
    words = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]+", title)
    words = [w for w in words if len(w) > 2 and w.lower() not in TAG_STOPWORDS]
    candidates = []
    if title.strip() and len(title.strip()) <= 90:
        candidates.append(title.strip())
    for i in range(len(words) - 1):
        candidates.append(f"{words[i]} {words[i + 1]}")
    candidates.extend(words)
    return candidates


def build_seo_tags(creation, max_total_chars=460, max_tag_len=30):
    """Cults'tan gelen orijinal etiketleri korur, ardından etiket alanında
    kalan boşluğu başlıktan türetilmiş + nişe özel SEO anahtar kelimeleriyle
    doldurur. YouTube'un toplam karakter sınırını hiçbir zaman aşmaz."""
    title = creation.get("name") or ""
    original = [t.strip() for t in (creation.get("tags") or []) if t and t.strip()]

    pool = original + _title_keyword_candidates(title) + EVERGREEN_SEO_TAGS

    final, seen, total_len = [], set(), 0
    for tag in pool:
        key = tag.lower()
        if not tag or key in seen or len(tag) > max_tag_len:
            continue
        added_len = len(tag) + (2 if final else 0)  # ", " ayırıcı payı
        if total_len + added_len > max_total_chars:
            continue
        final.append(tag)
        seen.add(key)
        total_len += added_len

    return final


# ============================================================
# GÖRSEL: BAŞLIK BANDI + LOGO BANDI + DİKEYLEŞTİRME
# ============================================================

_WINDIR = os.environ.get("WINDIR", "C:/Windows")
FONT_CANDIDATES = [
    os.path.join(_WINDIR, "Fonts", "arialbd.ttf"),
    os.path.join(_WINDIR, "Fonts", "Arial.ttf"),
    os.path.join(_WINDIR, "Fonts", "segoeuib.ttf"),
    "arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf",
]


def get_font(size):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap_text(draw, text, font, max_width, max_lines=5):
    words = text.split()
    lines, current = [], ""
    leftover_words = []
    for i, w in enumerate(words):
        trial = (current + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = w
            if len(lines) >= max_lines:
                # kalan kelimeler sığmadı - bunları not al, aşağıda son satıra
                # gerçek "…" ile işaretleyeceğiz (SESSİZCE KIRPMIYORUZ)
                leftover_words = words[i:]
                current = ""
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    elif current:
        leftover_words = [current] + leftover_words

    fixed = []
    for idx, line in enumerate(lines[:max_lines]):
        is_last = (idx == len(lines[:max_lines]) - 1) and bool(leftover_words)
        # tek kelime/satır bile sığmıyorsa (çok uzun kelime), harf bazlı kısalt
        # VE gerçekten "…" ekle (önceki hata: karakter siliniyordu ama "…"
        # hiç eklenmiyordu, örn. "Hinge" sessizce "Hing" oluyordu)
        if draw.textlength(line, font=font) > max_width:
            while draw.textlength(line + "…", font=font) > max_width and len(line) > 1:
                line = line[:-1]
            line = line + "…"
        elif is_last:
            while draw.textlength(line + "…", font=font) > max_width and len(line) > 1:
                line = line[:-1]
            line = line + "…"
        fixed.append(line)
    return fixed if fixed else [text[:1]]


def fit_text_lines(text, max_width, max_height, max_lines=5, start_size=78, min_size=10):
    dummy = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    for size in range(start_size, min_size - 1, -2):
        font = get_font(size)
        lines = _wrap_text(dummy, text, font, max_width, max_lines=max_lines)
        bbox = font.getbbox("Ağİ")
        line_h = (bbox[3] - bbox[1]) * 1.35
        total_h = line_h * len(lines)
        max_line_w = max((dummy.textlength(l, font=font) for l in lines), default=0)
        if total_h <= max_height and max_line_w <= max_width:
            return font, lines, line_h
    # en küçük boyutta da sığmazsa, olduğu gibi döndür (zaten "…" ile işaretlendi)
    font = get_font(min_size)
    lines = _wrap_text(dummy, text, font, max_width, max_lines=max_lines)
    bbox = font.getbbox("Ağİ")
    line_h = (bbox[3] - bbox[1]) * 1.35
    return font, lines, line_h


def make_title_bar(text, out_path, width=CANVAS_W, height=BAND_HEIGHT):
    """Üst şerit: TAMAMEN OPAK koyu kutu + konturlu (outline) başlık yazısı.
    Kutu artık videonun arka fonundan (siyah/beyaz fark etmez) tamamen
    bağımsız ve her zaman koyu; yazı da siyah konturlu olduğu için hangi
    zemin olursa olsun garanti okunuyor."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 16
    draw.rounded_rectangle([margin, margin, width - margin, height - margin],
                            radius=24, fill=(8, 9, 14, 255))  # tam opak - video arkasından hiç etkilenmez

    pad_x, pad_y = 34, 14
    max_w, max_h = width - 2 * pad_x, height - 2 * pad_y
    font, lines, line_h = fit_text_lines(text, max_w, max_h, max_lines=5,
                                          start_size=78, min_size=10)

    TITLE_COLOR = (255, 205, 40, 255)   # altın sarısı - siyah/beyaz her zeminde okunur
    OUTLINE_COLOR = (0, 0, 0, 255)      # siyah kontur - garanti okunabilirlik

    total_h = line_h * len(lines)
    y = (height - total_h) / 2
    for line in lines:
        w = draw.textlength(line, font=font)
        x = (width - w) / 2
        draw.text((x, y), line, font=font, fill=TITLE_COLOR,
                   stroke_width=4, stroke_fill=OUTLINE_COLOR)
        y += line_h
    img.save(out_path)
    return out_path


_LOGO_PULSE_DIR = Path("_logo_pulse_frames")
LOGO_PULSE_FPS = 12          # yanıp sönme animasyonunun kare hızı
LOGO_PULSE_FRAMES = 24       # bir döngüdeki kare sayısı (24/12fps = 2 sn döngü)
LOGO_MIN_OPACITY = 0.55      # en soluk (sönük) an
LOGO_MAX_OPACITY = 1.00      # en parlak (yanık) an
LOGO_SIZE_BOOST = 1.15 * 1.20  # kümülatif: önce %15, şimdi ek %20 daha büyük (~%38 toplam)
LOGO_UP_SHIFT_RATIO = 0.20 + 0.15  # kümülatif: önce %20, şimdi ek %15 daha yukarı (bant yüksekliğinin %35'i)


def get_logo_pulse_frames(width=CANVAS_W, height=LOGO_BAND_HEIGHT):
    """Alt şerit için logonun SABİT boyutta, sadece opaklığı (parlaklığı)
    dalgalanan bir kare dizisini üretir - yani logo YERİNDE durur, hiç
    büyüyüp küçülmez / hareket etmez, sadece yanar-söner gibi parlar.
    Bir kez üretilir, sonraki videolarda diskten tekrar kullanılır."""
    if _LOGO_PULSE_DIR.exists() and any(_LOGO_PULSE_DIR.glob("frame_*.png")):
        return _LOGO_PULSE_DIR
    _LOGO_PULSE_DIR.mkdir(exist_ok=True)

    if not Path(LOGO_PATH).exists():
        # Logo yoksa boş (tamamen şeffaf) tek kare üret ki ffmpeg akışı bozulmasın
        Image.new("RGBA", (width, height), (0, 0, 0, 0)).save(_LOGO_PULSE_DIR / "frame_000.png")
        return _LOGO_PULSE_DIR

    import math
    from PIL import ImageFilter
    base_logo = Image.open(LOGO_PATH).convert("RGBA")
    # Alt şeridin (siyah kutunun) tamamına göre, kümülatif büyütme uygulanmış boyut
    max_w, max_h = width - 40, height - 12
    base_ratio = min(max_w / base_logo.width, max_h / base_logo.height) * LOGO_SIZE_BOOST
    size = (max(1, int(base_logo.width * base_ratio)), max(1, int(base_logo.height * base_ratio)))
    # Oranı ASLA bozma; sadece gerçekten şeridin dışına taşacaksa, oranlı şekilde küçült
    safety = min(1.0, (width - 8) / size[0], (height - 8) / size[1])
    if safety < 1.0:
        size = (max(1, int(size[0] * safety)), max(1, int(size[1] * safety)))
    logo_base = base_logo.resize(size, Image.LANCZOS)
    # logo yatayda (x) TAM ortada kalır - sağdan/soldan dokunulmadı.
    # dikeyde (y): şeridin (bandın) yüksekliğinin %35'i kadar yukarı kaydırıldı,
    # üstten taşıp kırpılmasın diye 0'ın altına inmeyecek şekilde sınırlandı.
    x = (width - size[0]) // 2
    y_centered = (height - size[1]) // 2
    y_shift = int(height * LOGO_UP_SHIFT_RATIO)
    y = max(0, y_centered - y_shift)
    y_shift = y_centered - y  # glow'u da (varsa taşma sınırıyla) aynı miktarda kaydır

    for i in range(LOGO_PULSE_FRAMES):
        t = i / LOGO_PULSE_FRAMES
        pulse = (math.sin(t * 2 * math.pi) + 1) / 2  # 0 -> 1 -> 0 yumuşak dalga (yanma-sönme)
        opacity = LOGO_MIN_OPACITY + (LOGO_MAX_OPACITY - LOGO_MIN_OPACITY) * pulse

        r, g, b, a = logo_base.split()
        a = a.point(lambda p, op=opacity: int(p * op))
        logo = Image.merge("RGBA", (r, g, b, a))

        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        # Yumuşak parlama halesi (glow), opaklıkla birlikte yanıp söner - konumu SABİT
        glow = logo.copy()
        glow = glow.resize((int(size[0] * 1.18), int(size[1] * 1.18)), Image.LANCZOS)
        glow = glow.filter(ImageFilter.GaussianBlur(14))
        gr, gg, gb, ga = glow.split()
        ga = ga.point(lambda p, op=opacity: int(p * 0.5 * op))
        glow = Image.merge("RGBA", (gr, gg, gb, ga))
        gx, gy = (width - glow.width) // 2, (height - glow.height) // 2 - y_shift
        canvas.paste(glow, (gx, max(0, gy)), glow)

        canvas.paste(logo, (x, y), logo)
        canvas.save(_LOGO_PULSE_DIR / f"frame_{i:03d}.png")

    return _LOGO_PULSE_DIR


def probe_duration(path):
    """Bir medya dosyasının (video/ses) saniye cinsinden süresini döndürür,
    okunamazsa None döner."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, check=True, creationflags=_NO_WINDOW)
        return float(r.stdout.strip())
    except Exception:
        return None


def pick_music_segment(target_duration):
    """MUSIC_TRACKS'ten rastgele bir şarkı seçer, şarkının süresi yeterliyse
    içinde rastgele bir başlangıç saniyesi de seçer (şarkı kısaysa 0'dan
    başlar, ffmpeg tarafında zaten döngüye alınıp video süresine tamamlanır).
    MUSIC_TRACKS boşsa veya klasör/mp3'ler bulunamazsa (None, None, 0) döner."""
    available = [t for t in MUSIC_TRACKS if Path(MUSIC_DIR, t["file"]).exists()]
    if not available:
        return None, None, 0.0
    track = random.choice(available)
    path = str(Path(MUSIC_DIR, track["file"]))
    song_duration = probe_duration(path)
    if song_duration and song_duration > target_duration:
        start = random.uniform(0, song_duration - target_duration)
    else:
        start = 0.0
    return track, path, start


def make_vertical(input_path, output_path, title_text):
    """
    Yatay videoyu 1080x1920 dikey Shorts formatına çevirir:
    - Arka plan: düz siyah (blur KALDIRILDI, kullanıcı isteği üzerine)
    - Orta: orijinal video, oranı bozulmadan, ortada net
    - Üst şerit: model başlığı (otomatik sığdırılmış, asla taşmaz)
    - Alt şerit: logonuz (nabız atışı gibi animasyonlu)
    - Ses: MUSIC_TRACKS'ten rastgele seçilmiş bir şarkının rastgele bir
      bölümü (video sessiz olduğu için baştan sona bu müzik duyulur)
    - Süre: en fazla MAX_SHORT_SECONDS ile sınırlanır (Shorts kuralı)

    Dönüş: (music_track dict veya None) - hangi şarkının kullanıldığı,
    YouTube açıklamasına kredi/Spotify linki eklemek için.
    """
    # YouTube Shorts'un kendi arayüzü (ses simgesi, duraklat, ilerleme çubuğu)
    # ekranın en tepesinde durur; başlık şeridi tam y=0'da başlarsa onun
    # altında kalıp okunmuyor. Bu yüzden şeridin üstüne bir güvenlik boşluğu
    # bırakıyoruz, şerit biraz aşağıdan başlıyor.
    title_bar_path = "_title_bar_tmp.png"
    make_title_bar(title_text, title_bar_path)
    logo_frame_dir = get_logo_pulse_frames()
    logo_pattern = str(logo_frame_dir / "frame_%03d.png")

    # Nihai video süresini önceden belirle (müzik başlangıcını ve fade-out
    # zamanlamasını buna göre ayarlayabilmek için)
    src_duration = probe_duration(input_path) or MAX_SHORT_SECONDS
    target_duration = min(src_duration, MAX_SHORT_SECONDS)
    music_track, music_path, music_start = pick_music_segment(target_duration)
    fade_out_start = max(0.0, target_duration - 1.5)

    top_offset = TITLE_TOP_MARGIN + BAND_HEIGHT
    mid_h = CANVAS_H - top_offset - LOGO_BAND_HEIGHT
    filter_complex = (
        f"[0:v]scale={CANVAS_W}:{mid_h}:force_original_aspect_ratio=decrease,"
        f"pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:{top_offset}+(oh-{top_offset + LOGO_BAND_HEIGHT}-ih)/2:color=black[vfull];"
        f"[vfull][1:v]overlay=0:{TITLE_TOP_MARGIN}[v2];"
        f"[v2][2:v]overlay=0:{CANVAS_H - LOGO_BAND_HEIGHT}:shortest=1[v]"
    )

    cmd = [
        "ffmpeg", "-y", "-i", input_path, "-i", title_bar_path,
        "-stream_loop", "-1", "-framerate", str(LOGO_PULSE_FPS), "-i", logo_pattern,
    ]
    if music_path:
        # -stream_loop -1: şarkı video süresinden kısa kalırsa baştan tekrar
        # döner, hiçbir zaman sessiz kalınan an olmaz.
        cmd += ["-stream_loop", "-1", "-ss", f"{music_start:.2f}", "-i", music_path]
        filter_complex += (
            f";[3:a]afade=t=in:st=0:d=1,afade=t=out:st={fade_out_start:.2f}:d=1.5[aout]"
        )
        audio_map = ["-map", "[aout]"]
    else:
        # Müzik dosyaları bulunamadıysa eskisi gibi sessiz devam et (script durmasın)
        audio_map = ["-map", "0:a?"]

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[v]", *audio_map,
        "-t", str(target_duration),
        "-c:v", "libx264", "-c:a", "aac", "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True, creationflags=_NO_WINDOW)
    try:
        os.remove(title_bar_path)
    except OSError:
        pass
    return music_track


# ============================================================
# NSFW FİLTRESİ
# ============================================================

NSFW_KEYWORDS = [
    "nsfw", "hentai", "naughty", "topless", "nude", "nudity", "sexy",
    "erotic", "porn", "xxx", "18+", "adult only", "lewd", "waifu nude",
    "ecchi", "r18", "bikini bottom", "lingerie figure", "boudoir",
    "seductive", "fetish", "kinky", "big boobs", "big breast",
]

EXCLUDED_SLUGS = {
    "hentai-punk-girl-topless",
    "sarah-nsfw-3d-print",
    "scarlet-nsfw-3d-print",
    "rebecca-doggy-toy-3d-print",
    "brave-girl-ji-woo-collectible-figure",
    "connectable-anal-plug",
    "female-bodybuilder-3d-printable-figure",
    "shara-and-eira-3d-printable-duo-figure",
    "sexy-warrior-girl-3d-printable-figure",
    "impressive-and-sexy-witch-3d-printable-figure",
    "naked-sexy-woman-on-skateboard-3d-printable-figure",
    "sexy-witch-3d-printable-figure",
    "sasha-enchanting-and-captivating-3d-figure-statue",
    "lara-figure-3d-printable-model",
}


def is_nsfw(creation):
    url = (creation.get("url") or "").lower()
    if any(slug in url for slug in EXCLUDED_SLUGS):
        return True
    text = (
        (creation.get("name") or "") + " " +
        (creation.get("description") or "") + " " +
        " ".join(creation.get("tags") or [])
    ).lower()
    return any(kw in text for kw in NSFW_KEYWORDS)


def download_temp(url, dest):
    r = requests.get(url, stream=True, headers=BROWSER_HEADERS, timeout=60)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    return dest


def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, creationflags=_NO_WINDOW)
        return True
    except Exception:
        return False


def notify_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print(f"   [UYARI] Telegram bildirimi gönderilemedi: {e}")


# ============================================================
# ANA AKIŞ
# ============================================================

def main():
    if not check_ffmpeg():
        print("=" * 60)
        print("HATA: ffmpeg bulunamadı. Videolar Shorts formatına")
        print("çevrilemez, bu yüzden script DURDURULDU (yatay video")
        print("yüklenmesini önlemek için).")
        print()
        print("Çözüm: PowerShell'de şunu çalıştır:")
        print("   winget install ffmpeg")
        print("Kurulum bitince PowerShell'i KAPAT, yeniden AÇ,")
        print("sonra bu script'i tekrar çalıştır.")
        print("=" * 60)
        return

    state = load_state()
    if not state.get("start_date"):
        state["start_date"] = datetime.date.today().isoformat()

    creations = get_all_creations()
    processed = set(state.get("processed_urls") or [])

    # TEK SEFERLİK GEÇİŞ: eski sürüm ilerlemeyi sadece "next_index" (sıra
    # numarası) olarak tutuyordu. Bu state.json'da processed_urls hiç yoksa
    # ama eski bir next_index varsa, o kadar modeli (o ANKİ sıralamaya göre)
    # "işlenmiş" say. Böylece güncelleme sonrası daha önce yüklenmiş modeller
    # tekrar YouTube'a yüklenmez. Bu migrasyon sadece bir kez çalışır.
    if not processed and not state.get("migrated_to_url_tracking") and state.get("next_index"):
        old_next_index = min(state["next_index"], len(creations))
        for c in creations[:old_next_index]:
            processed.add(c.get("shortUrl") or c["url"])
        print(f"[GEÇİŞ] Eski next_index={state['next_index']} temel alınarak "
              f"{len(processed)} model 'daha önce işlenmiş' olarak işaretlendi.")
    state["migrated_to_url_tracking"] = True

    remaining_count = sum(1 for c in creations if (c.get("shortUrl") or c["url"]) not in processed)
    print(f"Toplam model: {len(creations)} | İşlenmiş: {len(processed)} | Kalan: {remaining_count}")
    state["total_models"] = len(creations)
    save_state(state)

    if state["next_publish_date"]:
        next_day = datetime.datetime.fromisoformat(state["next_publish_date"])
        # Art arda birden fazla calistirma (ayni gun icinde test vs.) yuzunden
        # saklanan tarih gercek "yarin"dan daha ileriye kaymis olabilir - kullanici
        # her calistirdiginda hep GERCEK bugunun bir sonraki gunune planlanmasini
        # istiyor, o yuzden ileri kaymisi gercek yarina geri cekiyoruz.
        real_tomorrow = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) \
            + datetime.timedelta(days=1)
        if next_day > real_tomorrow:
            print(f"   [TARİH DÜZELTME] Kayıtlı yayın tarihi ({next_day.date()}) gerçek yarından "
                  f"({real_tomorrow.date()}) ileriydi, geri çekildi.")
            next_day = real_tomorrow
    elif START_DATE:
        next_day = datetime.datetime.strptime(START_DATE, "%Y-%m-%d")
    else:
        next_day = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        first_slot = next_day.replace(hour=PUBLISH_HOURS_UTC[0])
        if first_slot <= datetime.datetime.utcnow():
            next_day += datetime.timedelta(days=1)

    if remaining_count == 0:
        print("Tüm modeller işlendi. 🎉")
        build_dashboard(state, len(creations))
        return

    youtube = get_youtube_service()

    retry_pending_comments(youtube, state)
    save_state(state)

    uploaded, skipped_nsfw, skipped_no_video, skipped_blocked, errors = [], 0, 0, 0, []
    stopped_early = False
    scanned = 0
    scan_limit = VIDEOS_PER_DAY * 6  # aşırı taramaya karşı sınır (işlenmemiş model sayısı üzerinden)

    ordered_creations = get_priority_order(creations, "seen_urls_youtube.json")

    for creation in ordered_creations:
        if len(uploaded) >= VIDEOS_PER_DAY or scanned >= scan_limit:
            break

        # Her modelin kendi linki (shortUrl / url) benzersiz kimliği olarak kullanılıyor.
        # Cults'a yeni model eklenip sıralama kaysa bile bu key değişmediği için
        # daha önce işlenmiş bir model YANLIŞLIKLA tekrar işlenmez.
        key = creation.get("shortUrl") or creation["url"]
        if key in processed:
            continue

        scanned += 1

        if is_nsfw(creation):
            print(f"[ATLANDI - NSFW/yetişkin içerik] {creation['name']}")
            skipped_nsfw += 1
            processed.add(key)
            continue

        video_url = get_video_url(creation, debug=True)
        if video_url == "RETRY_LATER":
            # Cults3D o an bu sayfayi vermedi (gecici blok) - bu model
            # "videosuz" SAYILMIYOR ve processed'a EKLENMIYOR, boylece bir
            # sonraki calistirmada bastan tekrar denenecek.
            print(f"[ATLANDI - gecici erisim engeli, sonraki calistirmada tekrar denenecek] {creation['name']}")
            skipped_blocked += 1
            continue
        if not video_url:
            print(f"[ATLANDI - video yok] {creation['name']}")
            skipped_no_video += 1
            processed.add(key)
            continue

        tmp_path = "tmp_video.mp4"
        tmp_vertical_path = "tmp_video_vertical.mp4"
        try:
            download_temp(video_url, tmp_path)
            music_track = None
            try:
                music_track = make_vertical(tmp_path, tmp_vertical_path, creation["name"])
                upload_path = tmp_vertical_path
            except Exception as e:
                print(f"   [UYARI] Dikeyleştirme başarısız, yatay yüklenecek: {e}")
                upload_path = tmp_path
            if music_track:
                print(f"   [MÜZİK] {music_track['title']}")

            hour = PUBLISH_HOURS_UTC[len(uploaded) % len(PUBLISH_HOURS_UTC)]
            publish_dt = next_day.replace(hour=hour, minute=0, second=0, microsecond=0)
            publish_at_str = publish_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            vid_id = upload_video(
                youtube, upload_path,
                title=creation["name"] + " #Shorts",
                description=clean_description(creation.get("description")) + f"\n\nModel: {creation['url']}\n#Shorts" + build_music_credit(music_track),
                tags=build_seo_tags(creation),
                publish_at=publish_at_str,
            )
            print(f"[YÜKLENDİ] {creation['name']} -> https://youtu.be/{vid_id} | yayın: {publish_at_str}")
            uploaded.append({"title": creation["name"], "publish_at": publish_at_str,
                              "link": f"https://youtu.be/{vid_id}"})

            print("   Model linki yorum olarak ekleniyor...")
            comment_ok = add_youtube_comment(youtube, vid_id, creation["url"])
            if comment_ok:
                print(f"   [YORUM] Eklendi -> {creation['url']}")
            else:
                state["pending_comments"].append({"video_id": vid_id, "text": creation["url"]})

            os.remove(tmp_path)
            if os.path.exists(tmp_vertical_path):
                os.remove(tmp_vertical_path)
            processed.add(key)

        except Exception as e:
            print(f"   [HATA] {creation['name']} yüklenemedi, bir sonraki çalıştırmada tekrar denenecek: {e}")
            errors.append(f"{creation['name']}: {e}")
            stopped_early = True
            break

    state["run_count"] += 1
    state["total_uploaded"] += len(uploaded)
    run_info = {
        "date": datetime.date.today().isoformat(),
        "day_number": state["run_count"],
        "uploaded": uploaded,
        "skipped_nsfw": skipped_nsfw,
        "skipped_no_video": skipped_no_video,
        "skipped_blocked": skipped_blocked,
        "errors": errors,
    }
    state["last_run"] = run_info
    history = state.get("history") or []
    history.append(run_info)
    state["history"] = history[-10:]

    state["processed_urls"] = sorted(processed)
    # Eski "next_index" alanı artık kullanılmıyor ama panelde/geri uyumlulukta
    # bir tahmin olarak gösterilmeye devam edebilir.
    state["next_index"] = len(processed)
    if not stopped_early:
        state["next_publish_date"] = (next_day + datetime.timedelta(days=1)).isoformat()
    save_state(state)

    build_dashboard(state, len(creations))

    summary = (f"Gün {state['run_count']}: {len(uploaded)} video yüklendi, "
               f"{skipped_nsfw} NSFW atlandı, {skipped_no_video} video-linksiz atlandı, "
               f"{skipped_blocked} gecici erisim engeline takilip ertelendi.")
    if errors:
        summary += f" ⚠️ {len(errors)} hata oluştu, tekrar denenecek."
    notify_telegram(summary)


if __name__ == "__main__":
    main()
