"""
CULTS3D -> INSTAGRAM OTOMASYON SCRIPTI
========================================
YouTube scriptiyle (cults_to_youtube.py) AYNI klasörde durmalı - model
cekme, NSFW filtre, video isleme ve muzik fonksiyonlarini oradan
YENIDEN KULLANIR, kod tekrarlanmaz.

Kendi ayri ilerleme dosyasini (state_instagram.json) tutar - YouTube
tarafini (state.json) hic etkilemez, birbirinden tamamen bagimsizdir.

Instagram'in native "ileri tarihe planla" ozelligi olmadigi icin, bu
script HER CALISTIGINDA 1 video secip HEMEN yayinlar. Gunde birden fazla
kez (orn. saatte bir) GitHub Actions ile tetiklenerek gunluk 10-20
paylasima ulasilir. DAILY_POST_LIMIT gunluk toplam sayiyi sinirlar.

Gereken ortam degiskenleri (GitHub Actions secrets):
  IG_ACCESS_TOKEN  -> Instagram/Meta erisim anahtari
  GH_PAT           -> cults-video-host reposuna yazma izni olan GitHub token

Calistirma:
  python cults_to_instagram.py
"""

import base64
import json
import os
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

DAILY_POST_LIMIT = 25   # Instagram'in Reels/feed icin API ile yayinlamaya izin verdigi gunluk ust sinir
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
    url = f"https://graph.instagram.com/{IG_API_VERSION}/{IG_USER_ID}/media"
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
    url = f"https://graph.instagram.com/{IG_API_VERSION}/{container_id}"
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
    url = f"https://graph.instagram.com/{IG_API_VERSION}/{IG_USER_ID}/media_publish"
    resp = requests.post(url, data={
        "creation_id": container_id,
        "access_token": IG_ACCESS_TOKEN,
    })
    if not resp.ok:
        print(f"   [INSTAGRAM HATASI] {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()["id"]


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
# ANA AKIS
# ============================================================

def main():
    if not IG_ACCESS_TOKEN or not GH_PAT:
        print("[HATA] IG_ACCESS_TOKEN veya GH_PAT ortam degiskeni eksik.")
        return

    print(f"[TOKEN DEBUG] uzunluk={len(IG_ACCESS_TOKEN)} baş={IG_ACCESS_TOKEN[:6]!r} son={IG_ACCESS_TOKEN[-6:]!r}")

    state = load_state()
    if state["today_date"] != today_str():
        state["today_date"] = today_str()
        state["today_count"] = 0

    if state["today_count"] >= DAILY_POST_LIMIT:
        print(f"Bugunku limit ({DAILY_POST_LIMIT}) zaten doldu, bu calistirmada yeni paylasim yapilmayacak.")
        save_state(state)
        return

    print("Modeller cekiliyor...")
    creations = bot.get_all_creations()

    creation = None
    video_url = None
    for c in creations:
        if c.get("url") in state["processed_urls"]:
            continue
        if bot.is_nsfw(c):
            continue
        vurl = bot.get_video_url(c)
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

    print("Instagram konteynerı olusturuluyor...")
    container_id = ig_create_container(raw_url, build_caption(creation, music_track))

    print("Instagram videoyu isliyor, bekleniyor...")
    ok = ig_wait_for_container(container_id)

    if ok:
        print("Yayinlaniyor...")
        media_id = ig_publish_container(container_id)
        print(f"BASARILI -> media_id={media_id}")
        state["processed_urls"].append(creation["url"])
        state["today_count"] += 1
        state["total_posted"] += 1

        print("Facebook sayfasina da yukleniyor...")
        fb_media_id = fb_post_video(raw_url, build_caption(creation, music_track))
        if fb_media_id:
            print(f"FACEBOOK BASARILI -> media_id={fb_media_id}")
        else:
            print("[UYARI] Facebook'a yukleme yapilamadi (Instagram tarafi yine de basarili sayilir).")

        state["history"].append({
            "date": today_str(),
            "title": creation["name"],
            "media_id": media_id,
            "fb_media_id": fb_media_id,
        })
    else:
        print("[HATA] Instagram videoyu isleyemedi (timeout ya da ERROR durumu).")

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
