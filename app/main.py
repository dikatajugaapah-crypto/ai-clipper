import os, uuid
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException
from .clipper import DATA, UPLOADS, OUTPUTS, detect_highlights, make_vertical_clip, make_facecam_clip, detect_facecam, download_youtube, probe_duration, make_metadata, fetch_source_title

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB

@app.errorhandler(Exception)
def handle_error(e):
    # API selalu balas JSON — jangan pernah HTML, supaya frontend tidak crash parse
    if request.path.startswith("/api/"):
        if isinstance(e, HTTPException):
            msg = "File terlalu besar (maks 500MB)" if e.code == 413 else (e.description or str(e))
            return jsonify(error=msg), e.code or 500
        return jsonify(error=str(e)[:800]), 500
    if isinstance(e, HTTPException):
        return e
    return jsonify(error=str(e)[:800]), 500

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-clipper"}

@app.post("/api/clip")
def clip():
    try:
        job_id = uuid.uuid4().hex[:10]
        clip_len = min(int(request.form.get("clip_len") or 45), 90)
        top_n = min(int(request.form.get("top_n") or 3), 5)
        src = None

        url = (request.form.get("url") or "").strip()
        source_title = ""
        if url:
            if not any(x in url for x in ("youtube.com", "youtu.be", "tiktok.com")):
                return jsonify(error="URL hanya YouTube / TikTok"), 400
            source_title = fetch_source_title(url)
            src = download_youtube(url, job_id)
        elif "file" in request.files and request.files["file"].filename:
            f = request.files["file"]
            name = secure_filename(f.filename) or "video.mp4"
            source_title = Path(name).stem.replace("-", " ").replace("_", " ")
            src = UPLOADS / f"{job_id}-{name}"
            f.save(src)
        else:
            return jsonify(error="Isi URL atau upload file video dulu"), 400

        duration = probe_duration(src)
        moments = detect_highlights(str(src), top_n=top_n, clip_len=clip_len)
        cam = detect_facecam(str(src))
        clips = []
        for i, m in enumerate(moments, 1):
            out = make_vertical_clip(str(src), m["start"], m["duration"])
            clips.append({"file": out.name, "download": f"/outputs/{out.name}",
                          "start": m["start"], "label": m["label"], "score": m["score"],
                          "category": m.get("category", ""), "kind": "Vertikal",
                          "metadata": make_metadata(m.get("category", ""), source_title, "Vertikal")})
            if cam:
                out2 = make_facecam_clip(str(src), m["start"], m["duration"], cam)
                clips.append({"file": out2.name, "download": f"/outputs/{out2.name}",
                              "start": m["start"], "label": m["label"] + " — versi Facecam Split",
                              "score": m["score"], "category": m.get("category", ""),
                              "kind": "Facecam Split (gameplay atas + facecam bawah)",
                              "metadata": make_metadata(m.get("category", ""), source_title, "Facecam Split")})
        return jsonify(job_id=job_id, duration=round(duration), facecam=bool(cam), clips=clips)
    except Exception as e:
        return jsonify(error=str(e)[:800]), 500

@app.get("/outputs/<path:name>")
def outputs(name):
    return send_from_directory(OUTPUTS, name, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
