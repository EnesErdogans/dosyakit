"""
Araç kayıt sistemi.

Yeni bir araç eklemek için app/tools/ klasörüne bir .py dosyası koyup
@tool(...) dekoratörüyle bir fonksiyon tanımlamanız yeterli. Uygulama
açılışta bu klasördeki tüm modülleri otomatik yükler (adı "_" ile
başlayanlar hariç). Örnek için tools/_ornek_arac.py dosyasına bakın.
"""
from __future__ import annotations

import importlib
import pkgutil
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# --------------------------------------------------------------------------
# Seçenek tanımları (arayüzde otomatik form alanına dönüşür)
# --------------------------------------------------------------------------

def opt_select(name, label, choices, default=None, help=""):
    """choices: [(değer, etiket), ...]"""
    return {"name": name, "label": label, "type": "select",
            "choices": [{"value": v, "label": l} for v, l in choices],
            "default": default if default is not None else choices[0][0], "help": help}


def opt_number(name, label, default=0, min=None, max=None, step=1, help=""):
    return {"name": name, "label": label, "type": "number", "default": default,
            "min": min, "max": max, "step": step, "help": help}


def opt_text(name, label, default="", placeholder="", help=""):
    return {"name": name, "label": label, "type": "text", "default": default,
            "placeholder": placeholder, "help": help}


def opt_password(name, label, help=""):
    return {"name": name, "label": label, "type": "password", "default": "", "help": help}


def opt_check(name, label, default=False, help=""):
    return {"name": name, "label": label, "type": "checkbox", "default": default, "help": help}


def opt_color(name, label, default="#d32f2f", help=""):
    return {"name": name, "label": label, "type": "color", "default": default, "help": help}


# --------------------------------------------------------------------------

class ToolError(Exception):
    """Kullanıcıya olduğu gibi gösterilecek hata."""


@dataclass
class Tool:
    id: str
    title: str
    description: str
    category: str
    accepts: list[str]               # [".pdf"] gibi; ["*"] = her şey
    func: Callable
    mode: str = "each"               # "each": her dosya ayrı iş | "all": tüm dosyalar tek iş
    options: list[dict] = field(default_factory=list)
    badge: str = ""                  # kartta görünen kısa etiket (ör. "PDF→W")
    color: str = "#e5322d"
    min_files: int = 1
    requires: str = ""               # "office" -> MS Office veya LibreOffice gerekir
    order: int = 100

    def meta(self) -> dict:
        return {
            "id": self.id, "title": self.title, "description": self.description,
            "category": self.category, "accepts": self.accepts, "mode": self.mode,
            "options": self.options, "badge": self.badge, "color": self.color,
            "min_files": self.min_files, "requires": self.requires, "order": self.order,
        }


CATEGORIES = [
    ("to_pdf", "PDF'e Dönüştür"),
    ("from_pdf", "PDF'ten Dönüştür"),
    ("organize", "PDF Düzenle"),
    ("security", "Güvenlik"),
    ("other", "Diğer Dönüşümler"),
]

TOOLS: dict[str, Tool] = {}
LOAD_ERRORS: list[str] = []


def tool(*, id, title, description, category, accepts, mode="each", options=None,
         badge="", color="#e5322d", min_files=1, requires="", order=100):
    """
    Dekoratör. Sarılan fonksiyonun imzası:

        def run(files: list[Path], outdir: Path, opts: dict, progress) -> list[Path]

    - mode="each" ise files her zaman tek elemanlıdır.
    - progress(oran: float 0..1, mesaj: str) ile ilerleme bildirilebilir.
    - Oluşturduğunuz dosyaları outdir içine yazıp yollarını döndürün.
    - Kullanıcıya hata göstermek için ToolError fırlatın.
    """
    def wrap(fn):
        if id in TOOLS:
            raise ValueError(f"Araç kimliği tekrar kullanılmış: {id}")
        TOOLS[id] = Tool(id=id, title=title, description=description, category=category,
                         accepts=[a.lower() for a in accepts], func=fn, mode=mode,
                         options=options or [], badge=badge, color=color,
                         min_files=min_files, requires=requires, order=order)
        return fn
    return wrap


def load_tools():
    """app/tools içindeki tüm modülleri içe aktarır."""
    from . import tools as pkg
    for m in pkgutil.iter_modules(pkg.__path__):
        if m.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{pkg.__name__}.{m.name}")
        except Exception:
            LOAD_ERRORS.append(f"{m.name}: {traceback.format_exc(limit=3)}")
    return TOOLS


def accepts_file(t: Tool, name: str) -> bool:
    if "*" in t.accepts:
        return True
    return Path(name).suffix.lower() in t.accepts
