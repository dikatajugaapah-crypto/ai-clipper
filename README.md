# 🎬 AI Clipper

Tools potong video panjang jadi klip vertikal 9:16 (Shorts / Reels / TikTok) otomatis.

**Cara kerja (tanpa API key berbayar):**
1. Input link YouTube/TikTok **atau** upload file video
2. Sistem sampling loudness tiap 5 detik (ffmpeg `volumedetect`) — momen paling keras biasanya reaksi, punchline, atau klimaks
3. Momen terbaik dipotong, di-crop tengah ke 1080×1920, hook/judul dibakar di atas video
4. Download hasil .mp4, siap upload

## Deploy ke Railway

Repo: https://github.com/dikatajugaapah-crypto/ai-clipper

Cara A — dari dashboard:
1. Buka https://railway.com → **New Project → Deploy from GitHub repo** → pilih `ai-clipper`
2. Railway otomatis memakai `Dockerfile` + `railway.json` (healthcheck `/health`)
3. Di service → **Settings → Networking → Generate Domain** untuk dapat URL publik `https://ai-clipper-production-xxxx.up.railway.app`

Cara B — dari CLI:
```bash
railway login
railway init --name ai-clipper
railway up
railway domain
```

> Railway tidak lagi punya free tier permanen — ada trial credit untuk akun baru, setelah itu plan Hobby ±$5/bln (usage-based). File hasil clip hilang saat redeploy/restart (filesystem ephemeral).

## Jalan lokal

```bash
pip install -r requirements.txt
# butuh ffmpeg terinstall
python -m app.main
# buka http://localhost:5000
```

## API

- `GET /health` → `{"status":"ok"}`
- `POST /api/clip` (multipart form): `url` *atau* `file`, `title`, `clip_len` (15–90), `top_n` (1–5)
- `GET /outputs/<file.mp4>` → download klip

## Roadmap (opsional, tinggal tambah)

- [ ] Auto-caption dari Whisper (`pip install openai-whisper`) — saat ini hook manual
- [ ] Deteksi scene change (`ffmpeg select='gt(scene,0.4)'`) gabung skor loudness
- [ ] Kirim langsung ke YouTube Shorts via YouTube API
- [ ] Antrian job (Celery/Redis) kalau trafik naik

## Lisensi & hak cipta
Gunakan hanya untuk video milik sendiri atau yang kamu punya hak potong/unggah ulangnya.
