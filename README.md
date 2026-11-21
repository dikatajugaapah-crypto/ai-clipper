# 🎬 AI Clipper

Tools potong video panjang jadi klip vertikal 9:16 (Shorts / Reels / TikTok) otomatis.

**Cara kerja (tanpa API key berbayar):**
1. Input link YouTube/TikTok **atau** upload file video
2. Sistem sampling loudness tiap 5 detik (ffmpeg `volumedetect`) — momen paling keras biasanya reaksi, punchline, atau klimaks
3. Momen terbaik dipotong, di-crop tengah ke 1080×1920, hook/judul dibakar di atas video
4. Download hasil .mp4, siap upload

## Deploy ke Render.com (gratis, ±5 menit)

1. Push repo ini ke GitHub kamu:
   ```bash
   git init && git add . && git commit -m "AI Clipper v1"
   git branch -M main
   git remote add origin https://github.com/USERNAME/ai-clipper.git
   git push -u origin main
   ```
2. Buka https://dashboard.render.com → **New + → Blueprint** → pilih repo ini
   (Render otomatis membaca `render.yaml` + `Dockerfile`), atau **New Web Service → Docker**.
3. Klik **Apply / Create** → tunggu build selesai → buka URL `https://ai-clipper-xxxx.onrender.com`

> Free tier: service sleep setelah ±15 menit idle, file hasil hilang saat restart. Cukup untuk demo & pemakaian pribadi ringan.

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
