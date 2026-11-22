"""Yerel web sunucusu: arayüzü sunar, işleri arka planda çalıştırır."""
from __future__ import annotations

import io
import json
import logging
import re
import shutil
import threading
import time
import traceback
import uuid
import zipfile
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

from . import config, registry
from .engines import office
from .registry import ToolError, accepts_file
from .util import open_folder

log = logging.getLogger("dosyakit")


class State:
    def __init__(self, token: str, port: int):
        self.token = token
        self.port = port
        self.jobs: dict[str, dict] = {}
        self.preloads: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.shutdown_event = threading.Event()


def _safe_name(name: str) -> str:
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "dosya"


def cleanup_old_jobs():
    hours = config.load_settings().get("keep_jobs_hours", 24)
    limit = time.time() - hours * 3600
    for d in config.WORK_DIR.glob("*"):
        try:
            if d.is_dir() and d.stat().st_mtime < limit:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def create_app(state: State) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = None

    allowed_hosts = {f"127.0.0.1:{state.port}", f"localhost:{state.port}"}

    # ------------------------------------------------------------ güvenlik
    @app.before_request
    def guard():
        # DNS rebinding'e karşı sadece yerel host adlarını kabul et
        if request.host not in allowed_hosts:
            abort(403)
        if request.path.startswith("/api/") and request.path != "/api/ping":
            tok = request.headers.get("X-Token") or request.args.get("t")
            if tok != state.token:
                abort(403)

    # ------------------------------------------------------------ sayfalar
    @app.get("/")
    def index():
        html = (config.WEB_DIR / "index.html").read_text(encoding="utf-8")
        html = html.replace("{{TOKEN}}", state.token).replace("{{VERSION}}", config.VERSION)
        resp = app.response_class(html, mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/static/<path:p>")
    def static_files(p):
        resp = send_from_directory(config.WEB_DIR, p)
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    # ------------------------------------------------------------ bilgi
    @app.get("/api/ping")
    def ping():
        return jsonify(app=config.APP_NAME, ok=True)

    @app.get("/api/tools")
    def tools():
        items = sorted(registry.TOOLS.values(), key=lambda t: (t.category, t.order, t.title))
        return jsonify(
            categories=[{"id": c, "title": t} for c, t in registry.CATEGORIES],
            tools=[t.meta() for t in items],
            load_errors=registry.LOAD_ERRORS,
        )

    @app.get("/api/status")
    def status():
        return jsonify(version=config.VERSION, office=office.status(),
                       settings=config.load_settings(), tools_dir=str(config.APP_DIR / "tools"))

    @app.post("/api/settings")
    def settings():
        return jsonify(config.save_settings(request.get_json(force=True) or {}))

    @app.post("/api/open")
    def open_path():
        what = (request.get_json(force=True) or {}).get("what")
        s = config.load_settings()
        if what == "output":
            p = Path(s["output_dir"])
            p.mkdir(parents=True, exist_ok=True)
        elif what == "tools":
            p = config.APP_DIR / "tools"
        elif what == "log":
            p = config.DATA_DIR
        elif what and what.startswith("job:"):
            job = state.jobs.get(what[4:])
            if not job:
                abort(404)
            p = Path(job["open_dir"])
        else:
            abort(400)
        open_folder(p)
        return jsonify(ok=True)

    @app.post("/api/shutdown")
    def shutdown():
        state.shutdown_event.set()
        return jsonify(ok=True)

    # ------------------------------------------------------------ "Gönder" / sağ tık
    @app.post("/api/preload")
    def preload():
        """Başlatıcı, sağ tıkla seçilen dosyaların yollarını buraya yollar."""
        paths = [Path(p) for p in (request.get_json(force=True) or {}).get("paths", [])]
        files = [{"path": str(p), "name": p.name, "size": p.stat().st_size}
                 for p in paths if p.is_file()]
        now = time.time()
        with state.lock:
            # Explorer çoklu seçimde her dosya için ayrı işlem açar; 2 sn içindekileri birleştir
            for pid, pl in state.preloads.items():
                if now - pl["updated"] < 2.0:
                    known = {f["path"] for f in pl["files"]}
                    pl["files"] += [f for f in files if f["path"] not in known]
                    pl["updated"] = now
                    return jsonify(id=pid, new=False)
            pid = uuid.uuid4().hex[:12]
            state.preloads[pid] = {"files": files, "updated": now}
        return jsonify(id=pid, new=True)

    @app.get("/api/preload/<pid>")
    def get_preload(pid):
        pl = state.preloads.get(pid)
        if not pl:
            abort(404)
        return jsonify(files=[{"ref": f"{pid}:{i}", "name": f["name"], "size": f["size"]}
                              for i, f in enumerate(pl["files"])])

    # ------------------------------------------------------------ işler
    @app.post("/api/run")
    def run():
        tool_id = request.form.get("tool", "")
        t = registry.TOOLS.get(tool_id)
        if not t:
            return jsonify(error="Bilinmeyen araç."), 400
        try:
            opts = json.loads(request.form.get("options") or "{}")
        except ValueError:
            opts = {}
        order = json.loads(request.form.get("order") or "[]")   # ["u:0", "l:pid:3", ...]

        job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        job_dir = config.WORK_DIR / job_id
        in_dir, out_dir = job_dir / "in", job_dir / "out"
        in_dir.mkdir(parents=True)
        out_dir.mkdir()

        uploads = request.files.getlist("files")
        inputs: list[Path] = []
        for ref in order:
            if ref.startswith("u:"):
                fs = uploads[int(ref[2:])]
                name = _safe_name(fs.filename)
                dst = in_dir / name
                k = 2
                while dst.exists():
                    dst = in_dir / f"{Path(name).stem} ({k}){Path(name).suffix}"
                    k += 1
                fs.save(dst)
                inputs.append(dst)
            elif ref.startswith("l:"):
                pid, idx = ref[2:].split(":")
                pl = state.preloads.get(pid)
                if pl:
                    inputs.append(Path(pl["files"][int(idx)]["path"]))
            elif ref.startswith("j:"):          # önceki bir işin sonucu (araç zinciri)
                jid, idx = ref[2:].rsplit(":", 1)
                prev = state.jobs.get(jid)
                if prev and int(idx) < len(prev["results"]):
                    inputs.append(Path(prev["results"][int(idx)]))

        if not inputs:
            shutil.rmtree(job_dir, ignore_errors=True)
            return jsonify(error="Dosya seçilmedi."), 400
        bad = [p.name for p in inputs if not accepts_file(t, p.name)]
        if bad:
            shutil.rmtree(job_dir, ignore_errors=True)
            return jsonify(error=f"Bu araç şu dosyaları kabul etmiyor: {', '.join(bad)}"), 400
        if len(inputs) < t.min_files:
            shutil.rmtree(job_dir, ignore_errors=True)
            return jsonify(error=f"Bu araç için en az {t.min_files} dosya gerekli."), 400

        job = {"id": job_id, "tool": t.id, "title": t.title, "status": "running", "progress": 0.0,
               "message": "Başlıyor…", "results": [], "notes": [], "errors": [],
               "dir": str(job_dir), "open_dir": str(out_dir), "started": time.time()}
        state.jobs[job_id] = job
        threading.Thread(target=_execute, args=(job, t, inputs, out_dir, opts), daemon=True).start()
        return jsonify(job=job_id)

    @app.get("/api/jobs/<jid>")
    def job_status(jid):
        job = state.jobs.get(jid)
        if not job:
            abort(404)
        return jsonify({k: v for k, v in job.items() if k not in ("dir",)} | {
            "results": [{"name": Path(r).name, "size": Path(r).stat().st_size}
                        for r in job["results"] if Path(r).exists()]})

    @app.get("/api/jobs/<jid>/file/<int:i>")
    def job_file(jid, i):
        job = state.jobs.get(jid)
        if not job or i >= len(job["results"]):
            abort(404)
        p = Path(job["results"][i])
        return send_file(p, as_attachment=request.args.get("inline") != "1", download_name=p.name)

    @app.get("/api/jobs/<jid>/zip")
    def job_zip(jid):
        job = state.jobs.get(jid)
        if not job or not job["results"]:
            abort(404)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for r in job["results"]:
                z.write(r, Path(r).name)
        buf.seek(0)
        stem = re.sub(r"\W+", "_", job["title"].lower()).strip("_") or "sonuclar"
        return send_file(buf, mimetype="application/zip", as_attachment=True,
                         download_name=f"dosyakit_{stem}.zip")

    return app


def _execute(job, t: registry.Tool, inputs: list[Path], out_dir: Path, opts: dict):
    batches = [[p] for p in inputs] if t.mode == "each" else [inputs]
    n = len(batches)
    for bi, batch in enumerate(batches):
        def progress(frac, msg="", _bi=bi):
            job["progress"] = min(0.99, (_bi + max(0.0, min(1.0, float(frac)))) / n)
            prefix = f"[{_bi + 1}/{n}] {batch[0].name}: " if n > 1 else ""
            job["message"] = prefix + (msg or "")
        progress(0, "İşleniyor…")
        try:
            res = t.func(batch, out_dir, dict(opts), progress)
            if isinstance(res, dict):
                files, notes = res.get("files", []), res.get("notes", [])
            else:
                files, notes = res or [], []
            job["results"] += [str(f) for f in files]
            prefix = f"{batch[0].name}: " if n > 1 else ""
            job["notes"] += [prefix + x for x in notes]
        except ToolError as e:
            job["errors"].append(f"{batch[0].name}: {e}" if n > 1 else str(e))
        except Exception as e:
            log.error("Araç hatası %s\n%s", t.id, traceback.format_exc())
            job["errors"].append(f"{batch[0].name}: Beklenmeyen hata: {e}")

    # sonuçları kullanıcı klasörüne de kopyala
    s = config.load_settings()
    if job["results"] and s.get("save_copy", True):
        try:
            dest = Path(s["output_dir"])
            dest.mkdir(parents=True, exist_ok=True)
            from .util import out_path
            for r in job["results"]:
                rp = Path(r)
                shutil.copy2(rp, out_path(dest, rp.stem, rp.suffix))
            job["open_dir"] = str(dest)
            job["saved_to"] = str(dest)
        except Exception as e:
            job["notes"].append(f"Çıktı klasörüne kopyalanamadı: {e}")

    job["progress"] = 1.0
    if job["results"]:
        job["status"] = "done"
        job["message"] = "Tamamlandı"
    else:
        job["status"] = "error"
        job["message"] = "Başarısız"
    job["elapsed"] = round(time.time() - job["started"], 1)
