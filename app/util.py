"""Araçların ortak kullandığı yardımcılar."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .registry import ToolError


def out_path(outdir: Path, stem: str, ext: str) -> Path:
    """Çakışmayan bir çıktı yolu üretir: ad.pdf, ad (2).pdf, ..."""
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip() or "dosya"
    p = outdir / f"{stem}{ext}"
    i = 2
    while p.exists():
        p = outdir / f"{stem} ({i}){ext}"
        i += 1
    return p


def parse_ranges(spec: str, page_count: int) -> list[list[int]]:
    """
    "1-3, 5, 8-" -> [[0,1,2],[4],[7,...,son]]  (0 tabanlı sayfa indeksleri)
    Boş ise tek grup: tüm sayfalar.
    """
    spec = (spec or "").replace(" ", "")
    if not spec:
        return [list(range(page_count))]
    groups = []
    for part in spec.split(","):
        if not part:
            continue
        m = re.fullmatch(r"(\d*)-(\d*)|(\d+)", part)
        if not m:
            raise ToolError(f"Geçersiz sayfa aralığı: '{part}'. Örnek: 1-3, 5, 8-")
        if m.group(3):
            a = b = int(m.group(3))
        else:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else page_count
        if a < 1 or b > page_count or a > b:
            raise ToolError(f"Sayfa aralığı belge dışında: '{part}' (belge {page_count} sayfa)")
        groups.append(list(range(a - 1, b)))
    if not groups:
        raise ToolError("Sayfa aralığı boş.")
    return groups


def flat_pages(spec: str, page_count: int) -> list[int]:
    seen, out = set(), []
    for g in parse_ranges(spec, page_count):
        for p in g:
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


_FONT_CANDIDATES = [
    # Türkçe karakter (ğ, ş, ı, İ) destekleyen yazı tipleri
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"),
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def unicode_font_file() -> str | None:
    for f in _FONT_CANDIDATES:
        if os.path.exists(f):
            return f
    return None


def hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = (h or "#000000").lstrip("#")
    if len(h) != 6:
        return (0, 0, 0)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def open_folder(path: Path):
    path = Path(path)
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa
    elif sys.platform == "darwin":
        os.system(f'open "{path}"')
    else:
        os.system(f'xdg-open "{path}" >/dev/null 2>&1 &')


def open_pdf(path: Path, password: str = ""):
    import pymupdf
    try:
        doc = pymupdf.open(str(path))
    except Exception as e:
        raise ToolError(f"'{path.name}' açılamadı: bozuk veya PDF değil ({e})")
    if doc.needs_pass:
        if not password or not doc.authenticate(password):
            doc.close()
            raise ToolError(f"'{path.name}' şifreli. Önce 'Şifre Kaldır' aracını kullanın.")
    return doc
