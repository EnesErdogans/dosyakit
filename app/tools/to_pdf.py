"""Başka biçimlerden PDF'e dönüştürme araçları."""
from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from ..registry import tool, opt_select, opt_number, ToolError
from ..engines import office
from ..util import out_path


def _office_to_pdf(files, outdir, opts, progress):
    src = files[0]
    progress(0.1, "Dönüştürülüyor…")
    dst = out_path(outdir, src.stem, ".pdf")
    office.convert(src, dst)
    return [dst]


tool(id="word_to_pdf", title="Word'den PDF'e", category="to_pdf", order=10,
     description="DOC, DOCX, ODT, RTF belgelerini PDF'e dönüştürün.",
     accepts=[".doc", ".docx", ".docm", ".odt", ".rtf", ".dotx"],
     badge="W→PDF", color="#2b579a", requires="office")(_office_to_pdf)

tool(id="ppt_to_pdf", title="PowerPoint'ten PDF'e", category="to_pdf", order=20,
     description="PPT, PPTX, ODP sunumlarını PDF'e dönüştürün.",
     accepts=[".ppt", ".pptx", ".pptm", ".odp", ".pps", ".ppsx"],
     badge="P→PDF", color="#d24726", requires="office")(_office_to_pdf)

tool(id="excel_to_pdf", title="Excel'den PDF'e", category="to_pdf", order=30,
     description="XLS, XLSX, ODS tablolarını PDF'e dönüştürün.",
     accepts=[".xls", ".xlsx", ".xlsm", ".ods", ".csv"],
     badge="X→PDF", color="#217346", requires="office")(_office_to_pdf)


IMG_EXT = [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp"]

_PAGE_SIZES = {"a4": pymupdf.paper_rect("a4"), "letter": pymupdf.paper_rect("letter")}


@tool(id="image_to_pdf", title="Görselden PDF'e", category="to_pdf", order=40,
      description="JPG, PNG ve diğer görselleri tek bir PDF'te birleştirin. Sırayı sürükleyerek ayarlayın.",
      accepts=IMG_EXT, mode="all", badge="JPG→PDF", color="#f0a30a",
      options=[
          opt_select("page", "Sayfa boyutu", [("fit", "Görsel boyutunda"), ("a4", "A4"), ("letter", "Letter")]),
          opt_select("orient", "Yön", [("auto", "Otomatik"), ("portrait", "Dikey"), ("landscape", "Yatay")]),
          opt_number("margin", "Kenar boşluğu (mm)", 0, min=0, max=50),
          opt_number("quality", "JPEG kalitesi", 90, min=30, max=100, step=5,
                     help="Düşük değer = daha küçük dosya"),
      ])
def image_to_pdf(files, outdir, opts, progress):
    out = pymupdf.open()
    margin = float(opts.get("margin") or 0) * 72 / 25.4
    quality = int(opts.get("quality") or 90)
    for i, f in enumerate(files):
        progress(i / len(files), f"{f.name} ekleniyor…")
        try:
            im = Image.open(f)
            im = ImageOps.exif_transpose(im)
            frames = []
            for k in range(getattr(im, "n_frames", 1)):  # çok sayfalı TIFF
                im.seek(k)
                frames.append(im.convert("RGB") if im.mode not in ("RGB", "L") else im.copy())
                if f.suffix.lower() == ".gif":
                    break
        except Exception as e:
            raise ToolError(f"'{f.name}' görsel olarak açılamadı: {e}")
        for fr in frames:
            buf = io.BytesIO()
            fr.save(buf, "JPEG", quality=quality)
            data = buf.getvalue()
            w, h = fr.size
            if opts.get("page") in _PAGE_SIZES:
                r = _PAGE_SIZES[opts["page"]]
                pw, ph = r.width, r.height
                o = opts.get("orient", "auto")
                if (o == "landscape") or (o == "auto" and w > h):
                    pw, ph = ph, pw
            else:
                pw, ph = w * 72 / 96 + 2 * margin, h * 72 / 96 + 2 * margin
            page = out.new_page(width=pw, height=ph)
            rect = pymupdf.Rect(margin, margin, pw - margin, ph - margin)
            page.insert_image(rect, stream=data, keep_proportion=True)
    name = files[0].stem if len(files) == 1 else "gorseller"
    dst = out_path(outdir, name, ".pdf")
    out.save(str(dst), garbage=3, deflate=True)
    out.close()
    return [dst]
