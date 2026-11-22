"""
Başlatıcı.

  DosyaKit.pyw                 -> uygulamayı açar (zaten açıksa tarayıcıda gösterir)
  DosyaKit.pyw dosya1 dosya2   -> dosyaları yükleyip uygun araçları gösterir (sağ tık / Gönder)
  DosyaKit.pyw --no-browser    -> sadece sunucuyu başlatır (geliştirme için)
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import config


def _read_runtime():
    try:
        return json.loads(config.RUNTIME_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _call(rt, path, data=None, timeout=2.0):
    url = f"http://127.0.0.1:{rt['port']}{path}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if body else "GET",
                                 headers={"X-Token": rt["token"], "Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # sistem proxy'sini atla
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _alive(rt) -> bool:
    if not rt:
        return False
    try:
        return _call(rt, "/api/ping", timeout=1.0).get("app") == config.APP_NAME
    except Exception:
        return False


def _open_ui(rt, preload_id=None):
    url = f"http://127.0.0.1:{rt['port']}/"
    if preload_id:
        url += f"?preload={preload_id}"
    webbrowser.open(url)


def _send_to_running(rt, paths, open_browser=True):
    if paths:
        r = _call(rt, "/api/preload", {"paths": paths})
        if r.get("new") and open_browser:
            _open_ui(rt, r["id"])
    elif open_browser:
        _open_ui(rt)


def _bind(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform == "win32":
        s.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", 0) or socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port))
    return s


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    no_browser = "--no-browser" in argv
    paths = [str(Path(a).resolve()) for a in argv if not a.startswith("--") and Path(a).exists()]

    config.ensure_dirs()
    logging.basicConfig(filename=str(config.LOG_FILE), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)   # her isteği kaydetme

    # 1) Zaten çalışan bir örnek varsa ona devret
    rt = _read_runtime()
    if _alive(rt):
        _send_to_running(rt, paths, not no_browser)
        return

    # 2) Portu kilit gibi kullan: aynı anda açılan diğer örnekler bağlanamaz, bekleyip devreder
    port = config.DEFAULT_PORT
    sock = None
    try:
        sock = _bind(port)
    except OSError:
        for _ in range(30):                 # başka bir örnek açılıyor olabilir
            time.sleep(0.25)
            rt = _read_runtime()
            if _alive(rt):
                _send_to_running(rt, paths, not no_browser)
                return
        sock = _bind(0)                     # port başka bir programda; boş port seç
        port = sock.getsockname()[1]

    from . import registry
    from .server import State, cleanup_old_jobs, create_app
    from werkzeug.serving import make_server

    registry.load_tools()
    for err in registry.LOAD_ERRORS:
        logging.error("Araç yüklenemedi: %s", err)
    cleanup_old_jobs()

    state = State(token=secrets.token_urlsafe(24), port=port)
    app = create_app(state)
    sock.listen(64)
    srv = make_server("127.0.0.1", port, app, threaded=True, fd=sock.fileno())

    config.RUNTIME_FILE.write_text(json.dumps({"port": port, "token": state.token, "pid": os.getpid()}),
                                   encoding="utf-8")
    logging.info("DosyaKit %s başladı, port %s", config.VERSION, port)

    pid = None
    if paths:   # ilk açılışta gelen dosyalar
        pid = "start"
        state.preloads[pid] = {"files": [{"path": p, "name": Path(p).name, "size": Path(p).stat().st_size}
                                         for p in paths], "updated": time.time()}

    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    if not no_browser:
        _open_ui({"port": port}, pid)
    else:
        print(f"DosyaKit çalışıyor: http://127.0.0.1:{port}/")

    try:
        while not state.shutdown_event.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass
    srv.shutdown()
    try:
        if (_read_runtime() or {}).get("pid") == os.getpid():
            config.RUNTIME_FILE.unlink()
    except OSError:
        pass
    logging.info("DosyaKit kapandı")


if __name__ == "__main__":
    main()
