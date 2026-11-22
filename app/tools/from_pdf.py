"""PDF'ten başka biçimlere dönüştürme araçları."""
from __future__ import annotations

import io
from pathlib import Path

import pymupdf

from ..registry import tool, opt_select, opt_text, opt_check, ToolError
from ..engines import office
from ..util import out_path, open_pdf, flat_pages

RANGE_OPT = opt_text("pages", "Sayfalar", "", placeholder="Tümü (örn. 1-3, 5, 8-)",
                     help="Boş bırakırsanız tüm sayfalar işlenir.")


def _has_text(doc, pages) -> bool:
    return any(doc[p].get_text("text").strip() for p in pages[:10])


# --------------------------------------------------------------------------
@tool(id="pdf_to_word", title="PDF'ten Word'e", category="from_pdf", order=10,
      description="PDF'i düzenlenebilir Word (DOCX) belgesine dönüştürün; tablo ve görseller korunur.",
      accepts=[".pdf"], badge="PDF→W", color="#2b579a", options=[RANGE_OPT])
def pdf_to_word(files, outdir, opts, progress):
    from pdf2docx import Converter
    src = files[0]
    doc = open_pdf(src)
    pages = flat_pages(opts.get("pages", ""), doc.page_count)
    scanned = not _has_text(doc, pages)
    doc.close()
    dst = out_path(outdir, src.stem, ".docx")
    progress(0.05, f"{len(pages)} sayfa çözümleniyor…")
    cv = Converter(str(src))
    try:
        cv.convert(str(dst), pages=pages)
    except Exception as e:
        raise ToolError(f"Word'e dönüştürülemedi: {e}")
    finally:
        cv.close()
    notes = []
    if scanned:
        notes.append("Bu PDF taranmış görünüyor (seçilebilir metin yok). Word dosyasında sayfalar "
                     "görsel olarak yer alır; metni düzenlemek için OCR gerekir.")
    return {"files": [dst], "notes": notes}


# --------------------------------------------------------------------------
@tool(id="pdf_to_ppt", title="PDF'ten PowerPoint'e", category="from_pdf", order=20,
      description="PDF sayfalarını PowerPoint (PPTX) slaytlarına dönüştürün.",
      accepts=[".pdf"], badge="PDF→P", color="#d24726",
      options=[
          opt_select("mode", "Dönüşüm türü", [
              ("image", "Birebir görünüm (her sayfa bir görsel)"),
              ("editable", "Düzenlenebilir metin (LibreOffice gerekir)")]),
          opt_select("dpi", "Görsel kalitesi", [("150", "Normal (150 DPI)"), ("220", "Yüksek (220 DPI)"),
                                               ("300", "Baskı (300 DPI)")]),
          RANGE_OPT,
      ])
def pdf_to_ppt(files, outdir, opts, progress):
    src = files[0]
    dst = out_path(outdir, src.stem, ".pptx")

    if opts.get("mode") == "editable":
        lo = office.find_libreoffice()
        if not lo:
            raise ToolError("Düzenlenebilir mod için LibreOffice gerekiyor. "
                            "'Birebir görünüm' modunu seçin veya LibreOffice kurun.")
        progress(0.1, "LibreOffice ile dönüştürülüyor…")
        _lo_pdf_import(lo, src, dst, "impress_pdf_import", "pptx:Impress MS PowerPoint 2007 XML")
        return [dst]

    from pptx import Presentation
    from pptx.util import Emu
    doc = open_pdf(src)
    pages = flat_pages(opts.get("pages", ""), doc.page_count)
    dpi = int(opts.get("dpi") or 150)
    first = doc[pages[0]].rect
    prs = Presentation()
    # PowerPoint slayt boyutu sınırı: 1-56 inç
    scale = min(1.0, 56 * 72 / max(first.width, first.height))
    prs.slide_width = Emu(int(first.width * scale * 12700))
    prs.slide_height = Emu(int(first.height * scale * 12700))
    blank = prs.slide_layouts[6]
    for i, pno in enumerate(pages):
        progress(i / len(pages), f"Sayfa {pno + 1} işleniyor…")
        page = doc[pno]
        pix = page.get_pixmap(dpi=dpi)
        # yüksek DPI'da PNG çok büyür; JPEG kullan
        img = io.BytesIO(pix.tobytes("jpeg", jpg_quality=88) if dpi > 150 else pix.tobytes("png"))
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(img, 0, 0, width=prs.slide_width, height=prs.slide_height)
        # Sayfadaki metni konuşmacı notlarına ekle (arama/kopyalama için)
        txt = page.get_text("text").strip()
        if txt:
            slide.notes_slide.notes_text_frame.text = txt[:5000]
    doc.close()
    prs.save(str(dst))
    return [dst]


def _lo_pdf_import(soffice, src: Path, dst: Path, infilter: str, convert_to: str):
    import subprocess, sys, tempfile, shutil
    with tempfile.TemporaryDirectory(prefix="dk_lo_") as tmp:
        out = Path(tmp) / "out"
        out.mkdir()
        cmd = [soffice, f"-env:UserInstallation={(Path(tmp) / 'p').as_uri()}", "--headless",
               "--norestore", f"--infilter={infilter}", "--convert-to", convert_to,
               "--outdir", str(out), str(src)]
        kw = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        with office._LOCK:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, **kw)
        produced = list(out.iterdir())
        if not produced:
            raise ToolError("LibreOffice dönüştüremedi: " + (r.stderr or r.stdout)[-400:])
        shutil.move(str(produced[0]), dst)


# --------------------------------------------------------------------------
@tool(id="pdf_to_excel", title="PDF'ten Excel'e", category="from_pdf", order=30,
      description="PDF içindeki tabloları Excel (XLSX) çalışma sayfalarına aktarın.",
      accepts=[".pdf"], badge="PDF→X", color="#217346",
      options=[
          opt_select("layout", "Yerleşim", [("per_table", "Her tablo ayrı sayfada"),
                                           ("single", "Tüm tablolar tek sayfada alt alta")]),
          opt_check("text_fallback", "Tablo bulunamazsa metni satır/sütun olarak aktar", True),
          RANGE_OPT,
      ])
def pdf_to_excel(files, outdir, opts, progress):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    src = files[0]
    doc = open_pdf(src)
    pages = flat_pages(opts.get("pages", ""), doc.page_count)
    wb = Workbook()
    wb.remove(wb.active)
    single = opts.get("layout") == "single"
    ws_all = wb.create_sheet("Tablolar") if single else None
    row_ptr = 1
    found = 0

    def write(ws, rows, start_row, title=None):
        r = start_row
        if title:
            ws.cell(r, 1, title).font = Font(bold=True, color="666666")
            r += 1
        for ri, row in enumerate(rows):
            for ci, val in enumerate(row):
                if val is None:
                    continue
                val = _num(str(val).replace("\n", " ").strip())
                c = ws.cell(r, ci + 1, val)
                if ri == 0:
                    c.font = Font(bold=True)
            r += 1
        return r

    for i, pno in enumerate(pages):
        progress(i / len(pages), f"Sayfa {pno + 1} taranıyor…")
        page = doc[pno]
        try:
            tabs = page.find_tables().tables
        except Exception:
            tabs = []
        for k, t in enumerate(tabs):
            rows = _table_rows(page, t)
            if not rows:
                continue
            found += 1
            if single:
                row_ptr = write(ws_all, rows, row_ptr, f"Sayfa {pno + 1} - Tablo {k + 1}") + 1
            else:
                ws = wb.create_sheet(f"S{pno + 1}-T{k + 1}"[:31])
                write(ws, rows, 1)

    notes = []
    if not found:
        if not opts.get("text_fallback", True):
            raise ToolError("PDF'te tablo bulunamadı.")
        notes.append("Belirgin tablo bulunamadı; metin satır ve sütunlara bölünerek aktarıldı.")
        for pno in pages:
            rows = _text_grid(doc[pno])
            if rows:
                ws = wb.create_sheet(f"Sayfa {pno + 1}"[:31])
                write(ws, rows, 1)
        if not wb.sheetnames:
            raise ToolError("PDF'te metin bulunamadı (taranmış belge olabilir).")
    doc.close()

    for ws in wb.worksheets:   # sütun genişliklerini ayarla
        for col in ws.columns:
            width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(width + 2, 8), 60)

    dst = out_path(outdir, src.stem, ".xlsx")
    wb.save(str(dst))
    return {"files": [dst], "notes": notes}


def _num(s: str):
    """'1.234,56' veya '1,234.56' gibi sayıları gerçek sayıya çevir."""
    t = s.replace(" ", "").replace("₺", "").replace("TL", "").replace("%", "")
    if not t or not any(ch.isdigit() for ch in t) or any(ch.isalpha() for ch in t):
        return s
    try:
        if "," in t and "." in t:
            t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
        elif "," in t:
            t = t.replace(",", ".") if len(t.split(",")[-1]) != 3 else t.replace(",", "")
        v = float(t)
        return int(v) if v.is_integer() and "." not in t else v
    except ValueError:
        return s


def _table_rows(page, t):
    """
    Hücre metnini kelimelerden kendimiz topluyoruz; bazı PDF üreticilerinde
    (ör. LibreOffice) yerleşik hücre metni karakter sırasını bozabiliyor.
    """
    words = page.get_text("words")
    rows = []
    for row in t.rows:
        r = []
        for cell in row.cells:
            if cell is None:
                r.append(None)
                continue
            x0, y0, x1, y1 = cell
            ws = [w for w in words if x0 <= (w[0] + w[2]) / 2 <= x1 and y0 <= (w[1] + w[3]) / 2 <= y1]
            ws.sort(key=lambda w: (w[5], w[6], w[7]))
            r.append(" ".join(w[4] for w in ws))
        rows.append(r)
    # Kenarlıksız tablolarda sütun sınırları kayabilir: başlığı dolu ama gövdesi boş
    # sütun varsa tabloyu kelime boşluklarına göre yeniden kur.
    if len(rows) > 2:
        body = rows[1:]
        for c in range(len(rows[0])):
            if rows[0][c] and sum(1 for r in body if c < len(r) and r[c]) < len(body) * 0.2:
                return _text_grid(page, clip=pymupdf.Rect(t.bbox))
    return rows


def _text_grid(page, clip=None):
    """Kelimeleri satırlara, büyük boşluklara göre hücrelere ayırır."""
    words = page.get_text("words", sort=True, clip=clip)
    lines: list[list] = []
    for w in words:
        x0, y0, x1, y1, txt = w[:5]
        cy = (y0 + y1) / 2
        if lines and abs(lines[-1][0] - cy) < (y1 - y0) * 0.5:
            lines[-1][1].append((x0, x1, txt))
        else:
            lines.append([cy, [(x0, x1, txt)]])
    rows = []
    for _, ws in lines:
        ws.sort()
        cells, cur, last_x1 = [], [], None
        for x0, x1, txt in ws:
            if last_x1 is not None and x0 - last_x1 > 12:
                cells.append(" ".join(cur))
                cur = []
            cur.append(txt)
            last_x1 = x1
        cells.append(" ".join(cur))
        rows.append(cells)
    return rows


# --------------------------------------------------------------------------
@tool(id="pdf_to_image", title="PDF'ten Görsele", category="from_pdf", order=40,
      description="Her PDF sayfasını JPG veya PNG görsele dönüştürün.",
      accepts=[".pdf"], badge="PDF→JPG", color="#f0a30a",
      options=[
          opt_select("fmt", "Biçim", [("jpg", "JPG"), ("png", "PNG")]),
          opt_select("dpi", "Çözünürlük", [("150", "150 DPI (ekran)"), ("300", "300 DPI (baskı)"),
                                           ("96", "96 DPI (küçük)"), ("600", "600 DPI (çok yüksek)")]),
          RANGE_OPT,
      ])
def pdf_to_image(files, outdir, opts, progress):
    src = files[0]
    doc = open_pdf(src)
    pages = flat_pages(opts.get("pages", ""), doc.page_count)
    dpi = int(opts.get("dpi") or 150)
    fmt = opts.get("fmt", "jpg")
    out = []
    width = len(str(doc.page_count))
    for i, pno in enumerate(pages):
        progress(i / len(pages), f"Sayfa {pno + 1}…")
        pix = doc[pno].get_pixmap(dpi=dpi, alpha=False)
        dst = out_path(outdir, f"{src.stem}_s{pno + 1:0{width}d}", "." + fmt)
        if fmt == "jpg":
            pix.save(str(dst), jpg_quality=90)
        else:
            pix.save(str(dst))
        out.append(dst)
    doc.close()
    return out


# --------------------------------------------------------------------------
@tool(id="pdf_to_text", title="PDF'ten Metne", category="from_pdf", order=50,
      description="PDF içindeki tüm metni düz metin (TXT) dosyasına çıkarın.",
      accepts=[".pdf"], badge="PDF→TXT", color="#607d8b",
      options=[opt_check("page_marks", "Sayfa ayraçları ekle", True), RANGE_OPT])
def pdf_to_text(files, outdir, opts, progress):
    src = files[0]
    doc = open_pdf(src)
    pages = flat_pages(opts.get("pages", ""), doc.page_count)
    parts = []
    for pno in pages:
        t = doc[pno].get_text("text", sort=True)
        if opts.get("page_marks", True):
            parts.append(f"===== Sayfa {pno + 1} =====\n{t}")
        else:
            parts.append(t)
    doc.close()
    text = "\n".join(parts)
    dst = out_path(outdir, src.stem, ".txt")
    dst.write_text(text, encoding="utf-8-sig")  # BOM: Not Defteri Türkçe karakterleri doğru göstersin
    notes = [] if text.strip(" =\nSayfa0123456789") else \
        ["Metin bulunamadı; belge taranmış (görsel) olabilir."]
    return {"files": [dst], "notes": notes}
