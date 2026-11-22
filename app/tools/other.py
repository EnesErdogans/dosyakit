"""Ofis biçimleri arası ve görsel biçimleri arası dönüşümler."""
from __future__ import annotations

from PIL import Image, ImageOps

from ..registry import tool, opt_select, opt_number, ToolError
from ..engines import office
from ..util import out_path

_TARGETS = {
    "word": [(".docx", "Word (DOCX)"), (".doc", "Word 97-2003 (DOC)"), (".odt", "OpenDocument (ODT)"),
             (".rtf", "Zengin Metin (RTF)"), (".txt", "Düz metin (TXT)"), (".html", "Web sayfası (HTML)")],
    "powerpoint": [(".pptx", "PowerPoint (PPTX)"), (".ppt", "PowerPoint 97-2003 (PPT)"),
                   (".odp", "OpenDocument (ODP)")],
    "excel": [(".xlsx", "Excel (XLSX)"), (".xls", "Excel 97-2003 (XLS)"), (".ods", "OpenDocument (ODS)"),
              (".csv", "CSV (ilk sayfa)")],
}


@tool(id="office_convert", title="Ofis Biçimi Dönüştür", category="other", order=10,
      description="DOC↔DOCX, ODT, RTF; XLS↔XLSX, ODS, CSV; PPT↔PPTX, ODP gibi dönüşümler.",
      accepts=sorted((office.WORD_EXT | office.PPT_EXT | office.XLS_EXT) - {".html", ".htm"}),
      badge="DOC⇄", color="#5c6bc0", requires="office",
      options=[
          # "when_ext": arayüz bu seçeneği sadece ilgili türde dosya varsa gösterir
          {**opt_select("word", "Word belgeleri →", _TARGETS["word"]), "when_ext": sorted(office.WORD_EXT)},
          {**opt_select("powerpoint", "Sunumlar →", _TARGETS["powerpoint"]), "when_ext": sorted(office.PPT_EXT)},
          {**opt_select("excel", "Tablolar →", _TARGETS["excel"]), "when_ext": sorted(office.XLS_EXT)},
      ])
def office_convert(files, outdir, opts, progress):
    src = files[0]
    kind = office._kind(src.suffix)
    target = opts.get(kind) or _TARGETS[kind][0][0]
    if src.suffix.lower() == target:
        raise ToolError(f"'{src.name}' zaten {target} biçiminde.")
    progress(0.1, "Dönüştürülüyor…")
    dst = out_path(outdir, src.stem, target)
    office.convert(src, dst)
    return [dst]


_IMG_IN = [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".ico"]


@tool(id="image_convert", title="Görsel Dönüştür", category="other", order=20,
      description="JPG, PNG, WEBP, BMP, ICO arasında dönüştürün; isterseniz yeniden boyutlandırın.",
      accepts=_IMG_IN, badge="IMG⇄", color="#f0a30a",
      options=[
          opt_select("fmt", "Hedef biçim", [("png", "PNG"), ("jpg", "JPG"), ("webp", "WEBP"),
                                             ("bmp", "BMP"), ("ico", "ICO (simge)")]),
          opt_number("max_side", "En uzun kenar (px)", 0, min=0, help="0 = boyutu değiştirme"),
          opt_number("quality", "Kalite (JPG/WEBP)", 90, min=10, max=100, step=5),
      ])
def image_convert(files, outdir, opts, progress):
    src = files[0]
    fmt = opts.get("fmt", "png")
    try:
        im = ImageOps.exif_transpose(Image.open(src))
    except Exception as e:
        raise ToolError(f"'{src.name}' açılamadı: {e}")
    m = int(opts.get("max_side") or 0)
    if m > 0:
        im.thumbnail((m, m), Image.LANCZOS)
    q = int(opts.get("quality") or 90)
    dst = out_path(outdir, src.stem, "." + fmt)
    if fmt in ("jpg", "bmp") and im.mode not in ("RGB", "L"):
        bg = Image.new("RGB", im.size, "white")       # saydamlığı beyaza bas
        im = im.convert("RGBA")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    if fmt == "jpg":
        im.save(dst, "JPEG", quality=q, optimize=True)
    elif fmt == "webp":
        im.save(dst, "WEBP", quality=q)
    elif fmt == "ico":
        im.save(dst, "ICO", sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256) if s <= max(im.size)])
    else:
        im.save(dst, fmt.upper())
    return [dst]
