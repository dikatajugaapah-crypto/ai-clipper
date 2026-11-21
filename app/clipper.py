import os, re, subprocess, uuid, json, shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
UPLOADS = DATA / "uploads"
OUTPUTS = DATA / "outputs"
for d in (UPLOADS, OUTPUTS):
    d.mkdir(parents=True, exist_ok=True)

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[-2000:])
    return r.stdout

def probe_duration(path):
    out = run(f'ffprobe -v error -show_entries format=duration -of csv=p=0 "{path}"')
    return float(out.strip())

def detect_highlights(path, top_n=3, clip_len=45):
    """
    AI sederhana tanpa API key:
    1. Ambil loudness per detik via ffmpeg astats/volumedetect sampling
    2. Momen paling keras = biasanya reaksi / punchline / klimaks
    3. Kembalikan timestamp tengah momen itu
    Fallback: bagi video jadi segmen merata.
    """
    duration = probe_duration(path)
    if duration <= clip_len:
        return [{"start": 0, "duration": duration, "score": 1.0, "label": "Full video"}]
    # Sample volume tiap 5 detik
    scores = []
    step = 5
    t = 0.0
    while t < duration - 5:
        try:
            out = subprocess.run(
                f'ffmpeg -ss {t} -t 5 -i "{path}" -af volumedetect -f null /dev/null',
                shell=True, capture_output=True, text=True, timeout=30).stderr
            m = re.search(r"mean_volume:\s*([-\d.]+)", out)
            vol = float(m.group(1)) if m else -50
        except Exception:
            vol = -50
        scores.append((vol, t))
        t += step
    scores.sort(reverse=True)
    picks, used = [], []
    for vol, start in scores:
        center = max(0, start - clip_len/2 + 2.5)
        if any(abs(center-u) < clip_len for u in used):
            continue
        used.append(center)
        picks.append({"start": round(center,1), "duration": clip_len,
                      "score": round(float(vol),1), "label": f"Momen keras {vol:.1f} dB @ {int(center//60)}:{int(center%60):02d}"})
        if len(picks) >= top_n:
            break
    picks.sort(key=lambda x: x["start"])
    return picks or [{"start": 0, "duration": clip_len, "score": 0, "label": "Awal video"}]

def make_vertical_clip(src, start, duration, title="", out_name=None):
    out_name = out_name or f"clip-{uuid.uuid4().hex[:8]}.mp4"
    out = OUTPUTS / out_name
    # Crop tengah 9:16, scale 1080x1920, burn judul di atas (drawtext aman)
    safe_title = (title or "").replace("'", "").replace(":", " ")[:60]
    draw = ""
    if safe_title:
        draw = f",drawtext=text='{safe_title}':fontcolor=white:fontsize=52:borderw=3:bordercolor=black:x=(w-text_w)/2:y=80"
    vf = f"crop=ih*9/16:ih,scale=1080:1920{draw}"
    run(f'ffmpeg -y -ss {start} -i "{src}" -t {duration} -vf "{vf}" '
        f'-c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -movflags +faststart "{out}"')
    return out

def download_youtube(url, job_id):
    out_tmpl = str(UPLOADS / f"{job_id}.%(ext)s")
    run(f'yt-dlp -f "bv*[height<=720]+ba/b[height<=720]" --merge-output-format mp4 -o "{out_tmpl}" "{url}"')
    for f in UPLOADS.glob(f"{job_id}.*"):
        return f
    raise RuntimeError("Download gagal")
