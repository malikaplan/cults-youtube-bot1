"""
CULTS3D -> INSTAGRAM OTOMASYON SCRIPTI
========================================
YouTube scriptiyle (cults_to_youtube.py) AYNI klasörde durmalı - model
cekme, NSFW filtre, video isleme ve muzik fonksiyonlarini oradan
YENIDEN KULLANIR, kod tekrarlanmaz.

Kendi ayri ilerleme dosyasini (state_instagram.json) tutar - YouTube
tarafini (state.json) hic etkilemez, birbirinden tamamen bagimsizdir.

HER CALISTIRMADA 1 video secip HEMEN yayinlar (eskisi gibi). Kullanici
gun icinde farkli zamanlarda kendisi tetikler, boylece paylasimlar dogal
sekilde saatlere yayilir. DAILY_POST_LIMIT gunluk (takvim gunu bazinda)
toplam sayiyi sinirlar - bu sinira ulasildiginda script YENI PAYLASIM
YAPMAZ, sadece bilgilendirici mesaj basar.

Gereken ortam degiskenleri:
  IG_ACCESS_TOKEN  -> Instagram/Meta erisim anahtari
  GH_PAT           -> cults-video-host reposuna yazma izni olan GitHub token

Calistirma:
  python cults_to_instagram.py
"""

import base64
import json
import os
import re
import time
from pathlib import Path

import requests

import cults_to_youtube as bot

# ============ AYARLAR ============
IG_USER_ID = "17841467127897025"          # makdesign.official hesabinin API kimlik numarasi
IG_API_VERSION = "v21.0"
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")

HOST_REPO = "malikaplan/cults-video-host"  # video barindirma icin gecici genel repo
GH_PAT = os.environ.get("GH_PAT", "")

FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "")                    # Mali Kaplan sayfasinin ID'si
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")  # Sayfa erisim anahtari

DAILY_POST_LIMIT = 24   # gunluk hedef - buna ulasilinca script yeni paylasim yapmaz
MAX_HASHTAGS = 20

STATE_FILE = "state_instagram.json"
bot.STATE_FILE = STATE_FILE  # YouTube'un state.json'una hic dokunmadan kendi dosyasini kullan


# ============================================================
# DURUM (state_instagram.json)
# ============================================================

def load_state():
    if Path(STATE_FILE).exists():
        state = json.loads(Path(STATE_FILE).read_text())
    else:
        state = {}
    state.setdefault("processed_urls", [])
    state.setdefault("today_date", None)
    state.setdefault("today_count", 0)
    state.setdefault("total_posted", 0)
    state.setdefault("history", [])
    state.setdefault("recovered_from_account", False)
    return state


def recover_processed_from_account(state):
    """BİR KEZ ÇALIŞIR: state_instagram.json'daki processed_urls listesi
    önceki bir hata yüzünden eksik kalmış olabilir (video yayınlandı ama
    kayıt hiç yapılamadı). Bu yüzden Instagram hesabındaki GERÇEKTEN
    yayınlanmış reels'lerin caption'larından ("Model: <url>" satırı) model
    linkleri okunup processed_urls'e geri eklenir - böylece zaten
    yayınlanmış hiçbir model bir daha tekrar yüklenmez."""
    if state.get("recovered_from_account"):
        return state

    print("[KURTARMA] Instagram hesabındaki geçmiş paylaşımlar taranıyor (bir kereye mahsus)...")
    recovered = []
    url = f"https://graph.facebook.com/{IG_API_VERSION}/{IG_USER_ID}/media"
    params = {"fields": "caption,permalink,timestamp", "limit": 100, "access_token": IG_ACCESS_TOKEN}
    pages = 0
    while url and pages < 30:
        resp = requests.get(url, params=params)
        if not resp.ok:
            print(f"   [UYARI] Hesap taranamadi: {resp.status_code} {resp.text}")
            break
        data = resp.json()
        for item in data.get("data", []):
            caption = item.get("caption") or ""
            m = re.search(r"Model:\s*(https://cults3d\.com/\S+)", caption)
            if m:
                recovered.append(m.group(1).rstrip(").,"))
        next_url = (data.get("paging") or {}).get("next")
        url = next_url
        params = None
        pages += 1

    added = 0
    for u in recovered:
        if u not in state["processed_urls"]:
            state["processed_urls"].append(u)
            added += 1

    state["recovered_from_account"] = True
    print(f"   [KURTARMA] Hesapta {len(recovered)} eski paylaşım bulundu, {added} tanesi "
          f"processed_urls listesine geri eklendi (artık tekrar yüklenmeyecekler).")
    save_state(state)
    return state


def save_state(state):
    Path(STATE_FILE).write_text(json.dumps(state, indent=2, ensure_ascii=False))


def today_str():
    import datetime
    return datetime.date.today().isoformat()


# ============================================================
# GECICI VIDEO BARINDIRMA (cults-video-host reposu uzerinden)
# ============================================================

def push_to_host_repo(local_path, remote_name):
    """Videoyu gecici barindirma reposuna yukler, herkese acik raw linkini
    ve dosyanin 'sha' degerini (sonradan silmek icin) dondurur."""
    with open(local_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    url = f"https://api.github.com/repos/{HOST_REPO}/contents/{remote_name}"
    headers = {"Authorization": f"token {GH_PAT}", "Accept": "application/vnd.github+json"}
    resp = requests.put(url, headers=headers, json={
        "message": f"add {remote_name}",
        "content": content_b64,
    })
    resp.raise_for_status()
    sha = resp.json()["content"]["sha"]
    raw_url = f"https://raw.githubusercontent.com/{HOST_REPO}/main/{remote_name}"
    return raw_url, sha


def delete_from_host_repo(remote_name, sha):
    """Yayinlandiktan sonra videoyu barindirma reposundan siler (temizlik)."""
    url = f"https://api.github.com/repos/{HOST_REPO}/contents/{remote_name}"
    headers = {"Authorization": f"token {GH_PAT}", "Accept": "application/vnd.github+json"}
    try:
        requests.delete(url, headers=headers, json={
            "message": f"remove {remote_name}",
            "sha": sha,
        })
    except Exception as e:
        print(f"   [UYARI] Barindirma reposundan silme basarisiz (onemli degil): {e}")


# ============================================================
# INSTAGRAM GRAPH API
# ============================================================

def ig_create_container(video_url, caption):
    url = f"https://graph.facebook.com/{IG_API_VERSION}/{IG_USER_ID}/media"
    resp = requests.post(url, data={
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN,
    })
    if not resp.ok:
        print(f"   [INSTAGRAM HATASI] {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()["id"]


def ig_wait_for_container(container_id, timeout_seconds=300, poll_every=10):
    url = f"https://graph.facebook.com/{IG_API_VERSION}/{container_id}"
    waited = 0
    while waited < timeout_seconds:
        resp = requests.get(url, params={
            "fields": "status_code",
            "access_token": IG_ACCESS_TOKEN,
        })
        resp.raise_for_status()
        status = resp.json().get("status_code")
        if status == "FINISHED":
            return True
        if status == "ERROR":
            return False
        time.sleep(poll_every)
        waited += poll_every
    return False


def ig_publish_container(container_id):
    url = f"https://graph.facebook.com/{IG_API_VERSION}/{IG_USER_ID}/media_publish"
    resp = requests.post(url, data={
        "creation_id": container_id,
        "access_token": IG_ACCESS_TOKEN,
    })
    if not resp.ok:
        print(f"   [INSTAGRAM HATASI] {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()["id"]


def ig_add_comment(media_id, text):
    """Yayinlanan Instagram gonderisine, tikla-git yapabilsinler diye
    Cults3D model linkini yorum olarak ekler."""
    url = f"https://graph.facebook.com/{IG_API_VERSION}/{media_id}/comments"
    resp = requests.post(url, data={
        "message": text,
        "access_token": IG_ACCESS_TOKEN,
    })
    if not resp.ok:
        print(f"   [YORUM HATASI] {resp.status_code}: {resp.text}")
        return None
    return resp.json().get("id")


# ============================================================
# FACEBOOK SAYFASINA PAYLASIM
# ============================================================

def fb_post_video(video_url, caption):
    """Ayni videoyu Facebook sayfasina (Mali Kaplan) yukler. Instagram'in
    otomatik "profiller arasi paylasim" ozelligi API ile yuklenen
    icerikte calismadigi icin bu adim ayrica gerekiyor."""
    if not FB_PAGE_ID or not FB_PAGE_ACCESS_TOKEN:
        print("   [FACEBOOK] FB_PAGE_ID veya FB_PAGE_ACCESS_TOKEN eksik, atlaniyor.")
        return None

    url = f"https://graph.facebook.com/{IG_API_VERSION}/{FB_PAGE_ID}/videos"
    resp = requests.post(url, data={
        "file_url": video_url,
        "description": caption,
        "access_token": FB_PAGE_ACCESS_TOKEN,
    })
    if not resp.ok:
        print(f"   [FACEBOOK HATASI] {resp.status_code}: {resp.text}")
        return None
    resp.raise_for_status()
    return resp.json().get("id")


# ============================================================
# ACIKLAMA / HASHTAG URETIMI
# ============================================================

def build_caption(creation, music_track):
    desc = bot.clean_description(creation.get("description"))
    parts = [creation["name"]]
    if desc:
        parts.append(desc)
    parts.append(f"Model: {creation['url']}")

    tags = bot.build_seo_tags(creation)[:MAX_HASHTAGS]
    hashtags = " ".join("#" + t.replace(" ", "").replace("-", "") for t in tags if t.strip())
    if hashtags:
        parts.append(hashtags)

    music_credit = bot.build_music_credit(music_track)
    if music_credit:
        parts.append(music_credit.strip())

    return "\n\n".join(parts)[:2200]  # Instagram caption karakter siniri


# ============================================================
# ANA AKIS - HER CALISTIRMADA 1 VIDEO
# ============================================================

def main():
    if not IG_ACCESS_TOKEN or not GH_PAT:
        print("[HATA] IG_ACCESS_TOKEN veya GH_PAT ortam degiskeni eksik.")
        return

    print(f"[TOKEN DEBUG] uzunluk={len(IG_ACCESS_TOKEN)} baş={IG_ACCESS_TOKEN[:6]!r} son={IG_ACCESS_TOKEN[-6:]!r}")

    state = load_state()
    state = recover_processed_from_account(state)
    if state["today_date"] != today_str():
        state["today_date"] = today_str()
        state["today_count"] = 0
        save_state(state)

    if state["today_count"] >= DAILY_POST_LIMIT:
        print(f"[LIMIT DOLDU] Bugun ({state['today_date']}) zaten {state['today_count']}/{DAILY_POST_LIMIT} "
              f"paylasim yapildi. Bu calistirmada YENI PAYLASIM YAPILMAYACAK. "
              f"Limiti asmamak icin yarina kadar beklemen gerekiyor.")
        return

    print(f"[DURUM] Bugun {state['today_count']}/{DAILY_POST_LIMIT} paylasim yapilmis, "
          f"{DAILY_POST_LIMIT - state['today_count']} hakkin kaldi.")

    print("Modeller cekiliyor...")
    creations = bot.get_all_creations()
    print(f"   [DEBUG] Toplam model: {len(creations)}, su ana kadar islenmis: {len(state['processed_urls'])}")

    ordered_creations = bot.get_priority_order(creations, "seen_urls_instagram.json")

    creation = None
    video_url = None
    for c in ordered_creations:
        if c.get("url") in state["processed_urls"]:
            continue
        if bot.is_nsfw(c):
            continue
        vurl = bot.get_video_url(c, debug=True)
        if not vurl or vurl == "RETRY_LATER":
            # RETRY_LATER: Cults3D o an sayfayi vermedi (gecici blok) -
            # bu model "islenmis" SAYILMIYOR, bir sonraki calistirmada
            # (ya da bu calistirmada bir sonraki aday olarak) tekrar
            # denenecek, gercek video linki sanilip indirilmeye calisilmiyor.
            continue
        creation, video_url = c, vurl
        break

    if not creation:
        print("Islenecek yeni model bulunamadi (hepsi islenmis ya da videosuz/NSFW).")
        save_state(state)
        return

    print(f"Secilen model: {creation['name']}")

    tag = str(int(time.time()))
    tmp_path = f"ig_tmp_{tag}.mp4"
    vertical_path = f"ig_vertical_{tag}.mp4"
    remote_name = f"ig_{tag}.mp4"

    print("Video indiriliyor...")
    bot.download_temp(video_url, tmp_path)

    print("Dikey + muzikli hale getiriliyor...")
    music_track = bot.make_vertical(tmp_path, vertical_path, creation["name"])
    print(f"   [MUZIK] {music_track['title'] if music_track else 'bulunamadi'}")

    print("Gecici barindirma reposuna yukleniyor...")
    raw_url, sha = push_to_host_repo(vertical_path, remote_name)

    try:
        print("Instagram konteynerı olusturuluyor...")
        container_id = ig_create_container(raw_url, build_caption(creation, music_track))

        print("Instagram videoyu isliyor, bekleniyor...")
        ok = ig_wait_for_container(container_id)

        if ok:
            print("Yayinlaniyor...")
            media_id = ig_publish_container(container_id)
            print(f"BASARILI -> media_id={media_id}")

            print("Model linki yorum olarak ekleniyor...")
            comment_id = ig_add_comment(media_id, creation["url"])
            if comment_id:
                print(f"   [YORUM] Eklendi -> {creation['url']}")
            else:
                print("   [UYARI] Yorum eklenemedi (paylasim yine de basarili sayilir).")

            # ONEMLI: video yayinlanir yayinlanmaz HEMEN kaydet (asagida
            # Facebook adimi veya temizlik hata verse bile bu video bir
            # daha ASLA tekrar secilmesin - "kaldigi yerden devam" hatasi
            # buradan kaynaklaniyordu, kayit calistirmanin en sonuna
            # birakilmisti).
            state["processed_urls"].append(creation["url"])
            state["today_count"] += 1
            state["total_posted"] += 1
            state["history"].append({
                "date": today_str(),
                "title": creation["name"],
                "media_id": media_id,
                "fb_media_id": None,
            })
            save_state(state)
            print(f"   [KAYIT] state_instagram.json guncellendi -> bugun {state['today_count']}/{DAILY_POST_LIMIT}")

            print("Facebook sayfasina da yukleniyor...")
            fb_media_id = fb_post_video(raw_url, build_caption(creation, music_track))
            if fb_media_id:
                print(f"FACEBOOK BASARILI -> media_id={fb_media_id}")
                state["history"][-1]["fb_media_id"] = fb_media_id
                save_state(state)
            else:
                print("[UYARI] Facebook'a yukleme yapilamadi (Instagram tarafi yine de basarili sayilir).")
        else:
            print("[HATA] Instagram videoyu isleyemedi (timeout ya da ERROR durumu). Bu model tekrar denenecek.")
    finally:
        print("Barindirma reposundan temizleniyor...")
        delete_from_host_repo(remote_name, sha)
        for p in (tmp_path, vertical_path):
            try:
                os.remove(p)
            except OSError:
                pass
        save_state(state)


if __name__ == "__main__":
    main()
