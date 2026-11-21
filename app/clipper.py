import os, re, subprocess, uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
UPLOADS = DATA / "uploads"
OUTPUTS = DATA / "outputs"
for d in (UPLOADS, OUTPUTS):
    d.mkdir(parents=True, exist_ok=True)

def run(cmd, timeout=600):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[-2000:])
    return r.stdout

def probe_duration(path):
    out = run(f'ffprobe -v error -show_entries format=duration -of csv=p=0 "{path}"')
    return float(out.strip())

def probe_size(path):
    out = run(f'ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "{path}"')
    w, h = out.strip().split(",")
    return int(w), int(h)

# ---------- Deteksi momen: Seru / Menegangkan / Lucu ----------
def _audio_series(path):
    """RMS energi audio per 0.5 detik (numpy dari wav 16kHz mono)."""
    import wave, numpy as np
    wav = f"/tmp/aud-{uuid.uuid4().hex[:8]}.wav"
    run(f'ffmpeg -y -v error -i "{path}" -vn -ac 1 -ar 16000 "{wav}"', timeout=300)
    try:
        w = wave.open(wav)
        n, sr = w.getnframes(), w.getframerate()
        raw = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
        w.close()
    finally:
        Path(wav).unlink(missing_ok=True)
    hop = sr // 2  # 0.5 detik
    count = max(1, len(raw) // hop)
    rms = np.array([np.sqrt(np.mean(raw[i*hop:(i+1)*hop] ** 2) + 1e-9) for i in range(count)])
    return rms  # index i = detik i*0.5

def detect_highlights(path, top_n=3, clip_len=45):
    """
    Skor tiap jendela klip dari pola audio:
    - SERU        : energi rata-rata tinggi & bertahan (aksi ramai)
    - MENEGANGKAN : energi naik terus (build-up) lalu memuncak di akhir jendela
    - LUCU        : banyak ledakan pendek beruntun (pola tawa / reaksi kaget berulang)
    Pilih momen skor tertinggi per kategori dulu (beragam), lalu isi sisa dari skor global.
    """
    import numpy as np
    duration = probe_duration(path)
    if duration <= clip_len:
        return [{"start": 0, "duration": duration, "score": 1.0,
                 "category": "Seru", "label": "Seru — full video"}]
    rms = _audio_series(path)
    step = 2  # jendela geser tiap 1 detik (2 hop)
    win = int(clip_len * 2)
    cands = []
    for s in range(0, max(1, len(rms) - win), step):
        seg = rms[s:s+win]
        if len(seg) < win * 0.8:
            break
        mean_e = float(seg.mean())
        peak_e = float(seg.max())
        # build-up: korelasi energi dengan waktu + puncak di 25% akhir
        x = np.linspace(0, 1, len(seg))
        rise = float(np.corrcoef(x, seg)[0, 1]) if seg.std() > 1e-6 else 0.0
        late_peak = float(seg[int(len(seg)*0.75):].max()) / (peak_e + 1e-9)
        tension = max(0.0, rise) * late_peak * peak_e
        # ledakan pendek: jumlah lonjakan di atas 1.6x median lokal
        thr = max(float(np.median(seg)) * 1.6, 0.02)
        above = (seg > thr).astype(int)
        bursts = int(np.sum(np.diff(above, prepend=0) == 1))
        laugh = bursts * mean_e
        scores = {"Seru": mean_e * (0.5 + 0.5 * (peak_e / (peak_e + 0.05))),
                  "Menegangkan": tension, "Lucu": laugh}
        best_cat = max(scores, key=scores.get)
        start_s = max(0.0, s / 2 - 3)  # mulai sedikit sebelum momen
        cands.append({"start": round(start_s, 1), "duration": clip_len,
                      "scores": scores, "best": best_cat,
                      "global": mean_e + peak_e * 0.5 + tension + laugh})
    if not cands:
        return [{"start": 0, "duration": clip_len, "score": 0, "category": "Seru", "label": "Seru — awal video"}]
    picks, used = [], []
    def try_add(c):
        if any(abs(c["start"] - u) < clip_len * 0.8 for u in used):
            return False
        used.append(c["start"])
        cat = c["best"]
        t = int(c["start"])
        picks.append({"start": c["start"], "duration": clip_len,
                      "score": round(float(c["scores"][cat]), 3), "category": cat,
                      "label": f"{cat} — mulai {t//60}:{t%60:02d}"})
        return True
    # 1) juara tiap kategori dulu
    for cat in ("Lucu", "Menegangkan", "Seru"):
        pool = sorted(cands, key=lambda c: c["scores"][cat], reverse=True)
        for c in pool:
            cc = dict(c); cc["best"] = cat
            if try_add(cc):
                break
        if len(picks) >= top_n:
            break
    # 2) isi sisa dari skor global
    for c in sorted(cands, key=lambda c: c["global"], reverse=True):
        if len(picks) >= top_n:
            break
        try_add(c)
    picks.sort(key=lambda x: x["start"])
    return picks[:top_n]

# ---------- Rekomendasi judul / deskripsi / hashtag / tags ----------
_STOP = set("yang dan di ke dari ini itu saat lagi video full part live streaming - _ . , ! ? ( ) [ ]".split())

def _keywords(text, max_n=6):
    words, out = re.findall(r"[A-Za-z0-9]+", (text or "").lower()), []
    for w in words:
        if len(w) > 2 and w not in _STOP and w not in out:
            out.append(w)
        if len(out) >= max_n:
            break
    return out

def make_metadata(category, source_title="", kind="Vertikal"):
    base = re.sub(r"[<>&\"']", "", (source_title or "Momen Terbaik")).strip()[:70] or "Momen Terbaik"
    kw = _keywords(source_title)
    cat = category if category in ("Seru", "Menegangkan", "Lucu") else "Seru"
    titles = {
        "Lucu": [f"Auto Ngakak! {base} 😂", f"Momen Paling Lucu dari {base} 🤣", f"Ngakak Terus! {base} 😆"],
        "Menegangkan": [f"Detik-Detik Menegangkan! {base} 😱", f"Hampir Saja! {base} 🔥", f"Tegang Banget! {base} 😨"],
        "Seru": [f"Momen Paling Seru! {base} 🔥", f"Gila, Seru Banget! {base} 🤯", f"Highlight Terbaik: {base} ⚡"],
    }[cat]
    if "Facecam" in kind:
        titles = [t + " | Reaksi Facecam" for t in titles]
    tag_base = {
        "Lucu": ["lucu", "ngakak", "momen lucu", "funny moments", "komedi", "hiburan"],
        "Menegangkan": ["menegangkan", "detik detik menegangkan", "jumpscare moment", "tegang", "viral"],
        "Seru": ["momen seru", "highlight", "best moments", "seru banget", "viral", "fyp"],
    }[cat]
    tags = list(dict.fromkeys(tag_base + kw + ["shorts", "youtube shorts", "tiktok", "reels", "clip", "indonesia"]))
    hashtags = ["#shorts", "#fyp", "#viral"] + [f"#{t.replace(' ', '')}" for t in tag_base[:3]] + [f"#{k}" for k in kw[:3]]
    hashtags = list(dict.fromkeys(hashtags))
    desc = (f"{titles[0]}\n\n"
            f"Klip {cat.lower()} pilihan AI dari video: {base}. "
            f"Tonton sampai habis, momen terbaiknya di akhir!\n"
            f"Follow / Subscribe untuk klip seru setiap hari 🔔\n\n"
            + " ".join(hashtags))
    return {"titles": titles, "title": titles[0], "description": desc,
            "hashtags": hashtags, "tags": tags}

def fetch_source_title(url):
    try:
        out = run(f'yt-dlp --no-playlist --print title "{url}"', timeout=60)
        return out.strip().splitlines()[0] if out.strip() else ""
    except Exception:
        return ""

# ---------- Deteksi facecam (wajah statis di posisi tetap) ----------
def detect_facecam(path):
    """
    Sampling frame, deteksi wajah (Haar). Wajah facecam = cluster posisi yang
    PALING SERING muncul & ukurannya konsisten (streamer diam di kotaknya),
    beda dengan wajah di gameplay yang berpindah-pindah.
    Return (x, y, w, h) kotak facecam (diperluas), atau None.
    """
    try:
        import cv2
    except Exception:
        return None
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if cascade.empty():
        return None
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = total / fps if fps else 0
    boxes = []
    t = 1.0
    while t < min(dur, 600):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=6,
                                         minSize=(40, 40))
        for (x, y, w, h) in faces:
            boxes.append((int(x), int(y), int(w), int(h)))
        t += 2.0
    cap.release()
    if len(boxes) < 4:
        return None
    # cluster berdasarkan pusat dekat (jarak < 12% lebar frame)
    W, H = probe_size(path)
    clusters = []
    for b in boxes:
        cx, cy = b[0] + b[2] / 2, b[1] + b[3] / 2
        placed = False
        for cl in clusters:
            mx = sum(x[0] + x[2] / 2 for x in cl) / len(cl)
            my = sum(x[1] + x[3] / 2 for x in cl) / len(cl)
            if abs(cx - mx) < W * 0.12 and abs(cy - my) < H * 0.12:
                cl.append(b); placed = True; break
        if not placed:
            clusters.append([b])
    clusters.sort(key=len, reverse=True)
    best = clusters[0]
    if len(best) < max(4, len(boxes) * 0.3):
        return None
    ax = sum(b[0] for b in best) / len(best); ay = sum(b[1] for b in best) / len(best)
    aw = sum(b[2] for b in best) / len(best); ah = sum(b[3] for b in best) / len(best)
    # perluas kotak wajah jadi kotak kamera (ada bahu + ruang kepala)
    cw, ch = aw * 2.4, ah * 2.6
    cx = max(0, ax + aw / 2 - cw / 2); cy = max(0, ay - ah * 0.35)
    cw = min(cw, W - cx); ch = min(ch, H - cy)
    return (int(cx), int(cy), int(cw), int(ch))

# ---------- Render klip ----------
def make_vertical_clip(src, start, duration, out_name=None):
    out_name = out_name or f"clip-{uuid.uuid4().hex[:8]}.mp4"
    out = OUTPUTS / out_name
    vf = "crop=ih*9/16:ih,scale=1080:1920"
    run(f'ffmpeg -y -ss {start} -i "{src}" -t {duration} -vf "{vf}" '
        f'-c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -movflags +faststart "{out}"')
    return out

def make_facecam_clip(src, start, duration, cam, out_name=None):
    """Split seperti contoh: gameplay di atas (1080x960), facecam diperbesar di bawah (1080x960)."""
    out_name = out_name or f"clip-{uuid.uuid4().hex[:8]}.mp4"
    out = OUTPUTS / out_name
    x, y, w, h = cam
    fc = (f'[0:v]split=2[g][c];'
          f'[g]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[top];'
          f'[c]crop={w}:{h}:{x}:{y},scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[bot];'
          f'[top][bot]vstack=inputs=2[v]')
    run(f'ffmpeg -y -ss {start} -i "{src}" -t {duration} -filter_complex "{fc}" -map "[v]" -map 0:a? '
        f'-c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -movflags +faststart "{out}"')
    return out

def download_youtube(url, job_id, cookies_path=None):
    """Coba berurutan beberapa strategi client — YouTube sering menolak satu client tapi menerima client lain."""
    out_tmpl = str(UPLOADS / f"{job_id}.%(ext)s")
    fmt = 'bv*[height<=720]+ba/b[height<=720]/b[height<=720]/b'
    cookie_arg = f' --cookies "{cookies_path}"' if cookies_path else ""
    import shutil
    js_arg = "--js-runtimes node" if shutil.which("node") else ("--js-runtimes deno" if shutil.which("deno") else "")
    strategies = [
        f'--extractor-args "youtube:player_client=android,web"',
        f'--extractor-args "youtube:player_client=web_safari,mweb" --impersonate chrome',
        f'--extractor-args "youtube:player_client=ios,tv"',
        f'--extractor-args "youtube:player_client=default" --impersonate chrome',
        '',
    ]
    last_err = ""
    for s in strategies:
        try:
            run(f'yt-dlp -f "{fmt}" --merge-output-format mp4 --no-playlist --retries 2 '
                f'{js_arg} {s}{cookie_arg} -o "{out_tmpl}" "{url}"', timeout=420)
        except RuntimeError as e:
            last_err = str(e)
            for f in UPLOADS.glob(f"{job_id}.*"):
                f.unlink(missing_ok=True)
            continue
        for f in UPLOADS.glob(f"{job_id}.*"):
            return f
    if any(k in last_err for k in ("Precondition check failed", "Sign in to confirm", "only images are available",
                                   "Requested format is not available", "bot")):
        raise RuntimeError("YouTube tetap menolak semua cara download dari server (proteksi bot). "
                           "Dua solusi: (1) isi kolom Cookies YouTube di halaman ini (file cookies.txt dari browser kamu yang sedang login YouTube), "
                           "atau (2) download videonya di HP/komputer lalu pakai Upload File.")
    raise RuntimeError("Download dari link gagal: " + last_err[-400:])
