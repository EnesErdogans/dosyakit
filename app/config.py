"""Klasörler ve kullanıcı ayarları."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "DosyaKit"
VERSION = "1.0.0"
DEFAULT_PORT = 8765

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"

if sys.platform == "win32":
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
else:
    DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME

WORK_DIR = DATA_DIR / "work"          # geçici iş klasörleri
RUNTIME_FILE = DATA_DIR / "runtime.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
LOG_FILE = DATA_DIR / "dosyakit.log"


def _default_output() -> str:
    docs = Path.home() / "Documents"
    if not docs.exists():
        docs = Path.home()
    return str(docs / APP_NAME)


DEFAULT_SETTINGS = {
    "output_dir": _default_output(),     # sonuçların kopyalandığı klasör
    "save_copy": True,                   # sonuçları output_dir'e de kaydet
    "office_engine": "auto",             # auto | msoffice | libreoffice
    "libreoffice_path": "",              # boşsa otomatik bulunur
    "keep_jobs_hours": 24,               # geçici işler kaç saat saklansın
}


def ensure_dirs():
    for d in (DATA_DIR, WORK_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    try:
        s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return s


def save_settings(new: dict) -> dict:
    s = load_settings()
    for k in DEFAULT_SETTINGS:
        if k in new:
            s[k] = new[k]
    ensure_dirs()
    SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    return s
