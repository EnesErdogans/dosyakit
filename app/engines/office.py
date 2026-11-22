"""
Ofis belgelerini dönüştürme motoru.

Öncelik sırası (ayar "auto" iken):
  1) Microsoft Office (Word / PowerPoint / Excel) - en iyi biçim korunumu, sadece Windows
  2) LibreOffice (ücretsiz, Windows/Linux/macOS)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from ..registry import ToolError
from .. import config

_LOCK = threading.Lock()   # Office COM aynı anda tek iş yapsın

WORD_EXT = {".doc", ".docx", ".docm", ".odt", ".rtf", ".txt", ".dot", ".dotx", ".wpd", ".html", ".htm"}
PPT_EXT = {".ppt", ".pptx", ".pptm", ".odp", ".pps", ".ppsx", ".pot", ".potx"}
XLS_EXT = {".xls", ".xlsx", ".xlsm", ".ods", ".csv", ".xlsb"}

# Microsoft Office FileFormat sabitleri
_WORD_FMT = {".pdf": 17, ".docx": 16, ".doc": 0, ".odt": 23, ".rtf": 6, ".txt": 7, ".html": 10}
_PPT_FMT = {".pdf": 32, ".pptx": 24, ".ppt": 1, ".odp": 35}
_XLS_FMT = {".xlsx": 51, ".xls": 56, ".ods": 60, ".csv": 62}


# --------------------------------------------------------------------------
# Motor tespiti
# --------------------------------------------------------------------------

def find_libreoffice() -> str | None:
    custom = config.load_settings().get("libreoffice_path")
    if custom and Path(custom).exists():
        return custom
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            p = Path(base) / "LibreOffice" / "program" / "soffice.exe"
            if p.exists():
                return str(p)
    elif sys.platform == "darwin":
        p = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        if p.exists():
            return str(p)
    return None


def _ms_app_registered(prog_id: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id + r"\CLSID"))
        return True
    except OSError:
        return False


def msoffice_status() -> dict:
    ok_com = True
    try:
        import win32com.client  # noqa: F401
    except Exception:
        ok_com = False
    return {
        "word": ok_com and _ms_app_registered("Word.Application"),
        "powerpoint": ok_com and _ms_app_registered("PowerPoint.Application"),
        "excel": ok_com and _ms_app_registered("Excel.Application"),
    }


def status() -> dict:
    ms = msoffice_status()
    lo = find_libreoffice()
    return {"msoffice": ms, "libreoffice": lo,
            "available": bool(lo) or any(ms.values())}


def _kind(ext: str) -> str:
    ext = ext.lower()
    if ext in WORD_EXT:
        return "word"
    if ext in PPT_EXT:
        return "powerpoint"
    if ext in XLS_EXT:
        return "excel"
    raise ToolError(f"Desteklenmeyen ofis dosyası: {ext}")


# --------------------------------------------------------------------------
# Microsoft Office (COM)
# --------------------------------------------------------------------------

def _ms_convert(src: Path, dst: Path, kind: str):
    import pythoncom
    import win32com.client

    target = dst.suffix.lower()
    pythoncom.CoInitialize()
    app = None
    try:
        if kind == "word":
            if target not in _WORD_FMT:
                raise ToolError(f"Word bu biçime kaydedemiyor: {target}")
            app = win32com.client.DispatchEx("Word.Application")
            app.Visible = False
            app.DisplayAlerts = 0
            doc = app.Documents.Open(str(src), ConfirmConversions=False, ReadOnly=True,
                                     AddToRecentFiles=False, Visible=False)
            try:
                doc.SaveAs2(str(dst), FileFormat=_WORD_FMT[target])
            finally:
                doc.Close(False)
        elif kind == "powerpoint":
            if target not in _PPT_FMT:
                raise ToolError(f"PowerPoint bu biçime kaydedemiyor: {target}")
            app = win32com.client.DispatchEx("PowerPoint.Application")
            pres = app.Presentations.Open(str(src), ReadOnly=True, Untitled=False, WithWindow=False)
            try:
                pres.SaveAs(str(dst), _PPT_FMT[target])
            finally:
                pres.Close()
        else:
            app = win32com.client.DispatchEx("Excel.Application")
            app.Visible = False
            app.DisplayAlerts = False
            wb = app.Workbooks.Open(str(src), ReadOnly=True, UpdateLinks=0)
            try:
                if target == ".pdf":
                    wb.ExportAsFixedFormat(0, str(dst))
                elif target in _XLS_FMT:
                    wb.SaveAs(str(dst), FileFormat=_XLS_FMT[target])
                else:
                    raise ToolError(f"Excel bu biçime kaydedemiyor: {target}")
            finally:
                wb.Close(False)
    finally:
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


# --------------------------------------------------------------------------
# LibreOffice
# --------------------------------------------------------------------------

_LO_FILTER = {
    # hedef uzantı -> --convert-to argümanı
    ".pdf": "pdf", ".docx": "docx:MS Word 2007 XML", ".doc": "doc:MS Word 97",
    ".odt": "odt", ".rtf": "rtf", ".txt": "txt:Text (encoded):UTF8", ".html": "html",
    ".pptx": "pptx:Impress MS PowerPoint 2007 XML", ".ppt": "ppt", ".odp": "odp",
    ".xlsx": "xlsx:Calc MS Excel 2007 XML", ".xls": "xls", ".ods": "ods", ".csv": "csv",
}


def _lo_convert(src: Path, dst: Path, soffice: str):
    target = dst.suffix.lower()
    if target not in _LO_FILTER:
        raise ToolError(f"LibreOffice bu biçime dönüştüremiyor: {target}")
    with tempfile.TemporaryDirectory(prefix="dk_lo_") as tmp:
        profile = Path(tmp) / "profile"
        outdir = Path(tmp) / "out"
        outdir.mkdir()
        cmd = [soffice, f"-env:UserInstallation={profile.as_uri()}", "--headless",
               "--norestore", "--nolockcheck", "--convert-to", _LO_FILTER[target],
               "--outdir", str(outdir), str(src)]
        kw = {}
        if sys.platform == "win32":
            kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, **kw)
        except subprocess.TimeoutExpired:
            raise ToolError("LibreOffice dönüşümü zaman aşımına uğradı.")
        produced = list(outdir.iterdir())
        if not produced:
            raise ToolError("LibreOffice dosyayı dönüştüremedi.\n" + (r.stderr or r.stdout)[-500:])
        shutil.move(str(produced[0]), dst)


# --------------------------------------------------------------------------

def convert(src: Path, dst: Path):
    """src dosyasını dst'nin uzantısındaki biçime dönüştürür."""
    kind = _kind(src.suffix)
    engine = config.load_settings().get("office_engine", "auto")
    ms_ok = msoffice_status().get(kind, False)
    lo = find_libreoffice()

    order = []
    if engine in ("auto", "msoffice") and ms_ok:
        order.append("ms")
    if engine in ("auto", "libreoffice") and lo:
        order.append("lo")
    if not order:
        raise ToolError(
            "Bu dönüşüm için Microsoft Office veya LibreOffice gerekiyor ama ikisi de bulunamadı. "
            "Ücretsiz LibreOffice'i libreoffice.org adresinden kurabilirsiniz.")

    last = None
    for e in order:
        try:
            with _LOCK:
                if e == "ms":
                    _ms_convert(src, dst, kind)
                else:
                    _lo_convert(src, dst, lo)
            if dst.exists():
                return dst
        except ToolError as ex:
            last = ex
        except Exception as ex:
            last = ToolError(f"{'Microsoft Office' if e == 'ms' else 'LibreOffice'} hatası: {ex}")
    raise last or ToolError("Dönüştürme başarısız.")
