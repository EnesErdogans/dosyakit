"""PDF düzenleme araçları: birleştir, böl, sıkıştır, döndür, sil, sırala, filigran, numara."""
from __future__ import annotations

import pymupdf

from ..registry import tool, opt_select, opt_number, opt_text, opt_check, opt_color, ToolError
import math

from ..util import out_path, open_pdf, parse_ranges, flat_pages, unicode_font_file, hex_to_rgb


def _save(doc, dst):
    doc.save(str(dst), garbage=3, deflate=True)
    doc.close()
    return dst


# --------------------------------------------------------------------------
@tool(id="merge", title="PDF Birleştir", category="organize", order=10, mode="all", min_files=2,
      description="Birden fazla PDF'i istediğiniz sırada tek dosyada birleştirin.",
      accepts=[".pdf"], badge="⧉", color="#e5322d",
      options=[opt_text("name", "Çıktı dosya adı", "birlestirilmis"),
               opt_check("bookmarks", "Her dosya için yer imi ekle", True)])
def merge(files, outdir, opts, progress):
    out = pymupdf.open()
    toc = []
    for i, f in enumerate(files):
        progress(i / len(files), f"{f.name} ekleniyor…")
        d = open_pdf(f)
        start = out.page_count
        out.insert_pdf(d)
        if opts.get("bookmarks", True):
            toc.append([1, f.stem, start + 1])
            for lvl, title, page, *_ in d.get_toc():
                toc.append([lvl + 1, title, start + page])
        d.close()
    if toc:
        try:
            out.set_toc(toc)
        except Exception:
            pass
    return [_save(out, out_path(outdir, opts.get("name") or "birlestirilmis", ".pdf"))]


# --------------------------------------------------------------------------
@tool(id="split", title="PDF Böl", category="organize", order=20,
      description="PDF'i sayfa aralıklarına, sabit parçalara veya tek tek sayfalara ayırın.",
      accepts=[".pdf"], badge="✂", color="#e5322d",
      options=[
          opt_select("mode", "Bölme şekli", [("ranges", "Aralıklara göre"), ("every", "Her N sayfada bir"),
                                             ("each", "Her sayfa ayrı dosya")]),
          opt_text("ranges", "Aralıklar", "", placeholder="örn. 1-3, 4-10, 11-",
                   help="Aralıklara göre modunda: her aralık ayrı bir dosya olur."),
          opt_number("n", "N (sayfa)", 2, min=1),
      ])
def split(files, outdir, opts, progress):
    src = files[0]
    doc = open_pdf(src)
    n_pages = doc.page_count
    mode = opts.get("mode", "ranges")
    if mode == "each":
        groups = [[i] for i in range(n_pages)]
    elif mode == "every":
        n = max(1, int(opts.get("n") or 1))
        groups = [list(range(i, min(i + n, n_pages))) for i in range(0, n_pages, n)]
    else:
        if not (opts.get("ranges") or "").strip():
            raise ToolError("Bölmek için en az bir aralık girin (örn. 1-3, 4-).")
        groups = parse_ranges(opts["ranges"], n_pages)
    out = []
    for i, g in enumerate(groups):
        progress(i / len(groups), f"Parça {i + 1}/{len(groups)}")
        part = pymupdf.open()
        part.insert_pdf(doc, from_page=g[0], to_page=g[-1])   # gruplar hep ardışık
        label = f"{g[0] + 1}" if len(g) == 1 else f"{g[0] + 1}-{g[-1] + 1}"
        out.append(_save(part, out_path(outdir, f"{src.stem}_s{label}", ".pdf")))
    doc.close()
    return out


# --------------------------------------------------------------------------
@tool(id="extract_pages", title="Sayfa Çıkar", category="organize", order=30,
      description="Seçtiğiniz sayfaları yeni bir PDF olarak alın.",
      accepts=[".pdf"], badge="⇱", color="#e5322d",
      options=[opt_text("pages", "Alınacak sayfalar", "", placeholder="örn. 1, 3-5, 9")])
def extract_pages(files, outdir, opts, progress):
    src = files[0]
    if not (opts.get("pages") or "").strip():
        raise ToolError("Hangi sayfaların alınacağını yazın.")
    doc = open_pdf(src)
    pages = flat_pages(opts["pages"], doc.page_count)
    doc.select(pages)
    return [_save(doc, out_path(outdir, f"{src.stem}_secilen", ".pdf"))]


@tool(id="delete_pages", title="Sayfa Sil", category="organize", order=40,
      description="İstemediğiniz sayfaları PDF'ten kaldırın.",
      accepts=[".pdf"], badge="🗑", color="#e5322d",
      options=[opt_text("pages", "Silinecek sayfalar", "", placeholder="örn. 2, 5-7")])
def delete_pages(files, outdir, opts, progress):
    src = files[0]
    if not (opts.get("pages") or "").strip():
        raise ToolError("Silinecek sayfaları yazın.")
    doc = open_pdf(src)
    remove = set(flat_pages(opts["pages"], doc.page_count))
    keep = [p for p in range(doc.page_count) if p not in remove]
    if not keep:
        raise ToolError("Tüm sayfalar silinemez.")
    doc.select(keep)
    return [_save(doc, out_path(outdir, f"{src.stem}_duzenlenmis", ".pdf"))]


@tool(id="reorder", title="Sayfaları Sırala", category="organize", order=50,
      description="Sayfa sırasını değiştirin veya tersine çevirin.",
      accepts=[".pdf"], badge="⇅", color="#e5322d",
      options=[opt_select("mode", "İşlem", [("custom", "Özel sıra"), ("reverse", "Ters çevir")]),
               opt_text("order", "Yeni sıra", "", placeholder="örn. 3, 1, 2, 4-",
                        help="Yazılmayan sayfalar sona eklenmez; sadece yazdıklarınız kalır.")])
def reorder(files, outdir, opts, progress):
    src = files[0]
    doc = open_pdf(src)
    if opts.get("mode") == "reverse":
        order = list(range(doc.page_count - 1, -1, -1))
    else:
        if not (opts.get("order") or "").strip():
            raise ToolError("Yeni sayfa sırasını yazın.")
        order = [p for g in parse_ranges(opts["order"], doc.page_count) for p in g]
    doc.select(order)
    return [_save(doc, out_path(outdir, f"{src.stem}_sirali", ".pdf"))]


# --------------------------------------------------------------------------
@tool(id="rotate", title="PDF Döndür", category="organize", order=60,
      description="Tüm sayfaları veya seçili sayfaları döndürün.",
      accepts=[".pdf"], badge="↻", color="#e5322d",
      options=[opt_select("angle", "Açı", [("90", "90° sağa"), ("270", "90° sola"), ("180", "180°")]),
               opt_text("pages", "Sayfalar", "", placeholder="Tümü")])
def rotate(files, outdir, opts, progress):
    src = files[0]
    doc = open_pdf(src)
    angle = int(opts.get("angle") or 90)
    for p in flat_pages(opts.get("pages", ""), doc.page_count):
        page = doc[p]
        page.set_rotation((page.rotation + angle) % 360)
    return [_save(doc, out_path(outdir, f"{src.stem}_dondurulmus", ".pdf"))]


# --------------------------------------------------------------------------
_COMPRESS = {
    # seviye: (görsel eşik DPI, hedef DPI, JPEG kalitesi)
    "low": None,
    "medium": (150, 120, 75),
    "high": (100, 72, 50),
}


@tool(id="compress", title="PDF Sıkıştır", category="organize", order=5,
      description="Kaliteyi koruyarak PDF dosya boyutunu küçültün.",
      accepts=[".pdf"], badge="⇲", color="#2e7d32",
      options=[opt_select("level", "Sıkıştırma seviyesi", [
          ("medium", "Önerilen (iyi kalite, iyi sıkıştırma)"),
          ("low", "Az (kalite kaybı yok)"),
          ("high", "Yüksek (en küçük dosya, düşük kalite)")]),
          opt_check("gray", "Görselleri siyah-beyaza çevir", False)])
def compress(files, outdir, opts, progress):
    src = files[0]
    before = src.stat().st_size
    doc = open_pdf(src)
    progress(0.2, "Görseller yeniden kodlanıyor…")
    lvl = _COMPRESS.get(opts.get("level", "medium"))
    if lvl or opts.get("gray"):
        thr, tgt, q = lvl or (10_000, 0, 0)
        try:
            doc.rewrite_images(dpi_threshold=thr if lvl else None, dpi_target=tgt if lvl else 0,
                               quality=q if lvl else 0, set_to_gray=bool(opts.get("gray")))
        except Exception:
            pass  # bazı egzotik görseller yeniden yazılamayabilir; temel sıkıştırma yine yapılır
    try:
        doc.subset_fonts()
    except Exception:
        pass
    progress(0.7, "Kaydediliyor…")
    dst = out_path(outdir, f"{src.stem}_sikistirilmis", ".pdf")
    doc.save(str(dst), garbage=4, deflate=True, deflate_images=True, deflate_fonts=True,
             clean=True, use_objstms=1)
    doc.close()
    after = dst.stat().st_size
    if after >= before:
        dst.unlink()
        import shutil
        shutil.copy2(src, dst)
        return {"files": [dst], "notes": ["Dosya zaten iyi sıkıştırılmış; daha fazla küçültülemedi."]}
    pct = 100 * (before - after) / before
    return {"files": [dst], "notes": [f"{_fmt(before)} → {_fmt(after)}  (%{pct:.0f} küçüldü)"]}


def _fmt(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


# --------------------------------------------------------------------------
@tool(id="watermark", title="Filigran Ekle", category="organize", order=70,
      description="Sayfalara çapraz veya düz metin filigranı ekleyin.",
      accepts=[".pdf"], badge="©", color="#8e24aa",
      options=[
          opt_text("text", "Filigran metni", "GİZLİ"),
          opt_select("pos", "Konum", [("diag", "Çapraz (ortada)"), ("center", "Ortada düz"),
                                      ("top", "Üstte"), ("bottom", "Altta")]),
          opt_number("size", "Yazı boyutu", 60, min=6, max=200),
          opt_number("opacity", "Opaklık (%)", 25, min=5, max=100, step=5),
          opt_color("color", "Renk", "#d32f2f"),
          opt_text("pages", "Sayfalar", "", placeholder="Tümü"),
      ])
def watermark(files, outdir, opts, progress):
    src = files[0]
    text = (opts.get("text") or "").strip()
    if not text:
        raise ToolError("Filigran metni boş olamaz.")
    doc = open_pdf(src)
    font, fname, ffile = _font()
    size = float(opts.get("size") or 60)
    opacity = float(opts.get("opacity") or 25) / 100
    color = hex_to_rgb(opts.get("color"))
    pos = opts.get("pos", "diag")
    for p in flat_pages(opts.get("pages", ""), doc.page_count):
        page = doc[p]
        r = page.rect                             # görünen (döndürülmüş) sayfa ölçüsü
        fs = size
        tw_len = font.text_length(text, fontsize=fs)
        limit = (r.width ** 2 + r.height ** 2) ** 0.5 * 0.8 if pos == "diag" else r.width * 0.9
        if tw_len > limit:                        # sayfaya sığdır
            fs = size * limit / tw_len
            tw_len = limit
        cx, cy = r.width / 2, r.height / 2
        y = {"top": 30 + fs, "bottom": r.height - 30}.get(pos, cy + fs * 0.35)
        angle = math.degrees(math.atan2(r.height, r.width)) if pos == "diag" else 0
        _draw(page, (cx - tw_len / 2, y), text, fs, fname, ffile, color, opacity,
              angle=angle, pivot=(cx, cy))
    return [_save(doc, out_path(outdir, f"{src.stem}_filigranli", ".pdf"))]


# --------------------------------------------------------------------------
@tool(id="page_numbers", title="Sayfa Numarası Ekle", category="organize", order=80,
      description="PDF sayfalarına sayfa numarası ekleyin.",
      accepts=[".pdf"], badge="#", color="#8e24aa",
      options=[
          opt_select("pos", "Konum", [("bc", "Alt orta"), ("br", "Alt sağ"), ("bl", "Alt sol"),
                                      ("tc", "Üst orta"), ("tr", "Üst sağ"), ("tl", "Üst sol")]),
          opt_select("fmt", "Biçim", [("{n}", "1"), ("{n} / {t}", "1 / 10"), ("Sayfa {n}", "Sayfa 1"),
                                      ("Sayfa {n} / {t}", "Sayfa 1 / 10"), ("- {n} -", "- 1 -")]),
          opt_number("start", "Başlangıç numarası", 1, min=0),
          opt_number("skip", "İlk kaç sayfa atlansın", 0, min=0, help="Kapak sayfası için 1 yapın."),
          opt_number("size", "Yazı boyutu", 11, min=6, max=40),
      ])
def page_numbers(files, outdir, opts, progress):
    src = files[0]
    doc = open_pdf(src)
    font, fname, ffile = _font()
    size = float(opts.get("size") or 11)
    skip = int(opts.get("skip") or 0)
    start = int(opts.get("start") if opts.get("start") not in (None, "") else 1)
    pos = opts.get("pos", "bc")
    total = doc.page_count - skip + start - 1
    margin = 28
    for i in range(skip, doc.page_count):
        page = doc[i]
        r = page.rect
        label = opts.get("fmt", "{n}").format(n=start + i - skip, t=total)
        w = font.text_length(label, fontsize=size)
        x = {"l": margin, "c": (r.width - w) / 2, "r": r.width - margin - w}[pos[1]]
        y = margin + size if pos[0] == "t" else r.height - margin
        _draw(page, (x, y), label, size, fname, ffile, (0.2, 0.2, 0.2), 1.0)
    return [_save(doc, out_path(outdir, f"{src.stem}_numarali", ".pdf"))]


# --------------------------------------------------------------------------
def _font():
    """(Font nesnesi, ad, dosya) - Türkçe karakterli yazı tipi varsa onu kullanır."""
    ff = unicode_font_file()
    if ff:
        return pymupdf.Font(fontfile=ff), "dkfont", ff
    return pymupdf.Font("helv"), "helv", None


def _draw(page, point, text, size, fname, ffile, color, opacity, angle=0.0, pivot=None):
    """
    Metni GÖRÜNEN sayfa koordinatlarında yazar; sayfa döndürülmüş olsa bile
    metin okuyucuya düz görünür.
    """
    m = page.derotation_matrix
    morph = None
    if angle:
        morph = (pymupdf.Point(pivot) * m, pymupdf.Matrix(angle))
    page.insert_text(pymupdf.Point(point) * m, text, fontsize=size, fontname=fname, fontfile=ffile,
                     color=color, fill_opacity=opacity, rotate=page.rotation, morph=morph)
