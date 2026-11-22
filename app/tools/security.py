"""PDF şifreleme / şifre kaldırma."""
from __future__ import annotations

import pymupdf

from ..registry import tool, opt_password, opt_check, ToolError
from ..util import out_path


@tool(id="protect", title="PDF Şifrele", category="security", order=10,
      description="PDF'i AES-256 ile şifreleyin; açmak için parola gereksin.",
      accepts=[".pdf"], badge="🔒", color="#37474f",
      options=[opt_password("pw", "Parola"),
               opt_password("pw2", "Parola (tekrar)"),
               opt_check("no_print", "Yazdırmayı engelle", False),
               opt_check("no_copy", "Metin kopyalamayı engelle", False)])
def protect(files, outdir, opts, progress):
    src = files[0]
    pw = opts.get("pw") or ""
    if len(pw) < 4:
        raise ToolError("Parola en az 4 karakter olmalı.")
    if pw != (opts.get("pw2") or ""):
        raise ToolError("Parolalar eşleşmiyor.")
    doc = pymupdf.open(str(src))
    if doc.needs_pass:
        raise ToolError("Bu PDF zaten şifreli.")
    perm = pymupdf.PDF_PERM_ACCESSIBILITY | pymupdf.PDF_PERM_MODIFY | pymupdf.PDF_PERM_ANNOTATE | \
        pymupdf.PDF_PERM_FORM | pymupdf.PDF_PERM_ASSEMBLE
    if not opts.get("no_print"):
        perm |= pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ
    if not opts.get("no_copy"):
        perm |= pymupdf.PDF_PERM_COPY
    dst = out_path(outdir, f"{src.stem}_sifreli", ".pdf")
    import secrets
    doc.save(str(dst), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=pw,
             owner_pw=pw + secrets.token_hex(8), permissions=perm, garbage=3, deflate=True)
    doc.close()
    return [dst]


@tool(id="unlock", title="Şifre Kaldır", category="security", order=20,
      description="Parolasını bildiğiniz bir PDF'in şifresini kaldırın.",
      accepts=[".pdf"], badge="🔓", color="#37474f",
      options=[opt_password("pw", "PDF parolası", help="Sadece kısıtlama varsa boş bırakabilirsiniz.")])
def unlock(files, outdir, opts, progress):
    src = files[0]
    doc = pymupdf.open(str(src))
    if doc.needs_pass and not doc.authenticate(opts.get("pw") or ""):
        doc.close()
        raise ToolError("Parola yanlış.")
    dst = out_path(outdir, f"{src.stem}_sifresiz", ".pdf")
    doc.save(str(dst), encryption=pymupdf.PDF_ENCRYPT_NONE, garbage=3, deflate=True)
    doc.close()
    return [dst]
