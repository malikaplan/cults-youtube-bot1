import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading, sys, webbrowser, os, re, json
from pathlib import Path

os.chdir(os.path.dirname(os.path.abspath(__file__)))

STATE_FILE = "state.json"
VIDEOS_PER_DAY = 6  # sadece tahmini gün hesaplamak için (asıl değer cults_to_youtube.py'de)

root = tk.Tk()
root.title("Cults3D → YouTube")
root.geometry("640x720")
root.configure(bg="#0f1117")

tk.Label(root, text="📦 Cults3D → YouTube Otomasyonu",
         font=("Segoe UI", 14, "bold"), bg="#0f1117", fg="#e8e8ec").pack(pady=(16, 4))

status_lbl = tk.Label(root, text="Hazır. Başlatmak için bir buton seçin.",
                       font=("Segoe UI", 10), bg="#0f1117", fg="#8a8f9c")
status_lbl.pack(pady=(0, 10))

log_box = scrolledtext.ScrolledText(root, width=70, height=13, bg="#1a1d27",
                                     fg="#e8e8ec", insertbackground="#e8e8ec",
                                     font=("Consolas", 9), borderwidth=0)
log_box.pack(padx=16, pady=6, fill="both", expand=True)

# Model başlığının (adının) yeşil görünmesi için ayrı bir renk etiketi
log_box.tag_configure("title_green", foreground="#3ceb82", font=("Consolas", 9, "bold"))

# Log satırlarında model başlığını yakalayan desenler (en spesifikten en genele)
_TITLE_PATTERNS = [
    re.compile(r"^(\[YÜKLENDİ\] )(.+?)( -> .*)$"),
    re.compile(r"^(   \[HATA\] )(.+?)( yüklenemedi.*)$"),
    re.compile(r"^(   \[UYARI\] Dikeyleştirme başarısız.*: )(.+)$"),
    re.compile(r"^(\[ATLANDI[^\]]*\] )(.+)$"),
]


def _insert_colored_line(line):
    """Bir log satırını, içindeki model başlığı yeşil renkte olacak şekilde ekler."""
    for pat in _TITLE_PATTERNS:
        m = pat.match(line)
        if m:
            groups = m.groups()
            log_box.insert(tk.END, groups[0])
            log_box.insert(tk.END, groups[1], "title_green")
            if len(groups) > 2:
                log_box.insert(tk.END, groups[2])
            log_box.insert(tk.END, "\n")
            return
    log_box.insert(tk.END, line + "\n")


class LogRedirector:
    """print() çıktısını canlı log kutusuna yazar; satır tamamlanınca model
    başlığı kısmını yeşil renkte gösterir (parça parça gelen yazıları
    satır satır biriktirip işler)."""
    def __init__(self):
        self._buffer = ""

    def write(self, msg):
        self._buffer += msg
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            _insert_colored_line(line)
        log_box.see(tk.END)

    def flush(self):
        if self._buffer:
            _insert_colored_line(self._buffer)
            self._buffer = ""
            log_box.see(tk.END)


# ============================================================
# GUI İÇİNE GÖMÜLÜ DURUM PANELİ (artık ayrı tarayıcı sekmesi
# otomatik açılmıyor - özet doğrudan burada, GUI'nin altında görünür)
# ============================================================

status_frame = tk.LabelFrame(root, text=" 📊 Durum ", font=("Segoe UI", 9, "bold"),
                              bg="#0f1117", fg="#8a8f9c", bd=1, relief="solid",
                              labelanchor="n")
status_frame.pack(padx=16, pady=(4, 10), fill="x")

stats_lbl = tk.Label(status_frame, text="Henüz veri yok — ilk çalıştırmadan sonra burada görünecek.",
                      font=("Segoe UI", 9), bg="#0f1117", fg="#e8e8ec",
                      justify="left", anchor="w", wraplength=580)
stats_lbl.pack(fill="x", padx=10, pady=(8, 4))

warn_lbl = tk.Label(status_frame, text="", font=("Segoe UI", 9, "bold"),
                     bg="#0f1117", fg="#e07a7a", justify="left", anchor="w", wraplength=580)
warn_lbl.pack(fill="x", padx=10, pady=(0, 4))

tk.Label(status_frame, text="Bugün yüklenenler (çift tıkla → videoyu tarayıcıda aç):",
         font=("Segoe UI", 8), bg="#0f1117", fg="#8a8f9c", anchor="w").pack(fill="x", padx=10)

uploads_list = tk.Listbox(status_frame, height=5, bg="#1a1d27", fg="#e8e8ec",
                           selectbackground="#2a2f3d", font=("Consolas", 9),
                           borderwidth=0, highlightthickness=0)
uploads_list.pack(fill="x", padx=10, pady=(2, 10))
_uploads_links = []


def _on_upload_double_click(_event):
    sel = uploads_list.curselection()
    if sel and sel[0] < len(_uploads_links) and _uploads_links[sel[0]]:
        webbrowser.open(_uploads_links[sel[0]])


uploads_list.bind("<Double-Button-1>", _on_upload_double_click)


def _read_state():
    try:
        return json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
    except Exception:
        return None


def refresh_status_panel():
    """state.json'u okuyup GUI içindeki özet paneli günceller (tarayıcı AÇMAZ)."""
    state = _read_state()
    if not state:
        stats_lbl.config(text="Henüz veri yok — ilk çalıştırmadan sonra burada görünecek.")
        uploads_list.delete(0, tk.END)
        warn_lbl.config(text="")
        return

    last = state.get("last_run") or {}
    total_models = state.get("total_models") or 0
    next_index = state.get("next_index", 0)
    remaining = max(total_models - next_index, 0)
    est_days = -(-remaining // VIDEOS_PER_DAY) if VIDEOS_PER_DAY else 0

    stats_lbl.config(text=(
        f"📅 Gün {last.get('day_number', '-')}   |   "
        f"✅ Toplam yüklenen: {state.get('total_uploaded', 0)} / {total_models or '?'}   |   "
        f"⏳ Kalan: {remaining} model (~{est_days} gün)   |   "
        f"🕓 Son çalışma: {last.get('date', '-')}"
    ))

    uploads_list.delete(0, tk.END)
    _uploads_links.clear()
    uploaded = last.get("uploaded") or []
    if uploaded:
        for u in uploaded:
            uploads_list.insert(tk.END, f"  {u.get('title', '?')}   →   {u.get('publish_at', '?')}")
            _uploads_links.append(u.get("link"))
    else:
        uploads_list.insert(tk.END, "  Bugün henüz yeni video yüklenmedi.")
        _uploads_links.append(None)

    errors = last.get("errors") or []
    skipped_nsfw = last.get("skipped_nsfw", 0)
    skipped_no_video = last.get("skipped_no_video", 0)
    parts = []
    if errors:
        parts.append(f"❌ {len(errors)} video yüklenemedi (otomatik olarak tekrar denenecek)")
    if skipped_nsfw or skipped_no_video:
        parts.append(f"⚠️ {skipped_nsfw} NSFW + {skipped_no_video} video-linksiz model atlandı")
    warn_lbl.config(text="   ".join(parts))


def _set_buttons_running(running):
    state = "disabled" if running else "normal"
    restart_btn.config(state=state)
    resume_btn.config(state=state)
    panel_btn.config(state="disabled" if running else "normal")


def run_upload(reset_first=False):
    _set_buttons_running(True)
    if reset_first:
        resume_btn.config(text="▶ Kaldığı Yerden Başlat")
        restart_btn.config(text="Sıfırlanıyor...")
        status_lbl.config(text="Baştan başlatılıyor (ilerleme sıfırlanıyor)...")
    else:
        restart_btn.config(text="🔄 En Baştan Başlat")
        resume_btn.config(text="Çalışıyor...")
        status_lbl.config(text="Kaldığı yerden devam ediyor...")

    sys.stdout = LogRedirector()
    sys.stderr = LogRedirector()
    crash_msg = None
    try:
        if reset_first:
            if Path(STATE_FILE).exists():
                Path(STATE_FILE).unlink()
            print("== İlerleme sıfırlandı, en baştan başlanıyor ==\n")

        import cults_to_youtube
        cults_to_youtube.main()
        status_lbl.config(text="✅ Bitti. Aşağıdaki Durum panelinde özet var.")
    except Exception as e:
        status_lbl.config(text="❌ Beklenmeyen hata oluştu, aşağıya bakın.")
        log_box.insert(tk.END, f"\nHATA: {e}\n")
        crash_msg = str(e)
    finally:
        restart_btn.config(state="normal", text="🔄 En Baştan Başlat")
        resume_btn.config(state="normal", text="▶ Kaldığı Yerden Başlat")
        panel_btn.config(state="normal")
        refresh_status_panel()

        if crash_msg:
            # Program tamamen çöktüyse ASLA sessiz kalma - açık bir pencereyle bildir
            messagebox.showerror(
                "Beklenmeyen Hata",
                "Program çalışırken beklenmeyen bir hata oluştu:\n\n"
                f"{crash_msg}\n\n"
                "'▶ Kaldığı Yerden Başlat' ile tekrar deneyebilirsiniz."
            )
        else:
            state = _read_state()
            last = (state or {}).get("last_run") or {}
            errors = last.get("errors") or []
            if errors:
                # Bir/birkaç video yüklenemediyse ASLA sessiz kalma - açık bir pencereyle bildir
                detail = "\n".join(f"• {e}" for e in errors)
                messagebox.showwarning(
                    "Yüklenemeyen Video(lar) Var",
                    f"{len(errors)} video bu çalıştırmada YÜKLENEMEDİ:\n\n{detail}\n\n"
                    "Endişelenmeyin: bir sonraki '▶ Kaldığı Yerden Başlat' çalıştırmasında "
                    "otomatik olarak tekrar denenecek."
                )


def start_resume():
    threading.Thread(target=run_upload, kwargs={"reset_first": False}, daemon=True).start()


def start_restart():
    if not messagebox.askyesno(
        "En Baştan Başlat",
        "İlerleme sıfırlanacak ve modeller index 0'dan itibaren tekrar "
        "işlenecek.\n\nDaha önce YouTube'a yüklenmiş videolar SİLİNMEZ, "
        "ama aynı modeller tekrar işlenip yeniden yüklenebilir.\n\n"
        "Devam etmek istiyor musunuz?"
    ):
        return
    threading.Thread(target=run_upload, kwargs={"reset_first": True}, daemon=True).start()


def open_panel():
    """Detaylı (zengin) HTML durum panelini tarayıcıda AÇIKÇA istenirse açar
    (artık her çalıştırma sonunda OTOMATİK açılmıyor)."""
    path = os.path.abspath("durum.html")
    if os.path.exists(path):
        webbrowser.open(f"file://{path}")
    else:
        log_box.insert(tk.END, "\nHenüz durum.html oluşmadı, önce bir kere çalıştırın.\n")


btn_frame = tk.Frame(root, bg="#0f1117")
btn_frame.pack(pady=(0, 10))

restart_btn = tk.Button(btn_frame, text="🔄 En Baştan Başlat", font=("Segoe UI", 10, "bold"),
                         bg="#e07a7a", fg="#0f1117", relief="flat", padx=12, pady=8,
                         command=start_restart)
restart_btn.pack(side="left", padx=6)

resume_btn = tk.Button(btn_frame, text="▶ Kaldığı Yerden Başlat", font=("Segoe UI", 10, "bold"),
                        bg="#7c9cff", fg="#0f1117", relief="flat", padx=12, pady=8,
                        command=start_resume)
resume_btn.pack(side="left", padx=6)

panel_btn = tk.Button(btn_frame, text="📊 Detaylı Paneli Tarayıcıda Aç", font=("Segoe UI", 9),
                       bg="#1a1d27", fg="#e8e8ec", relief="flat", padx=12, pady=8,
                       command=open_panel)
panel_btn.pack(side="left", padx=6)

refresh_status_panel()  # GUI açılır açılmaz, varsa önceki durumu hemen göster

root.mainloop()
