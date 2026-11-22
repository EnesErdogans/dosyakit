"""
ÖRNEK ARAÇ ŞABLONU
==================
Yeni bir araç eklemek için:
  1. Bu dosyayı kopyalayın ve adını "_" ile BAŞLAMAYAN bir şey yapın (ör. benim_aracim.py).
     ("_" ile başlayan dosyalar yüklenmez; bu dosya o yüzden görünmüyor.)
  2. Aşağıdaki @tool bilgilerini ve fonksiyonu düzenleyin.
  3. DosyaKit'i kapatıp yeniden açın (arayüzde sağ üstteki "Kapat", sonra masaüstü kısayolu).
     Araç ana sayfada kendiliğinden belirir; seçenekler otomatik form olur.

Gerekli yeni bir kütüphane varsa requirements.txt'ye ekleyip kurulumu tekrar çalıştırın.
"""
from __future__ import annotations

import pymupdf

from ..registry import tool, opt_text, opt_select, opt_number, opt_check, ToolError
from ..util import out_path, open_pdf


@tool(
    id="ornek_metadata",                 # benzersiz kimlik
    title="PDF Bilgilerini Düzenle",      # kartta görünen başlık
    description="PDF'in başlık ve yazar bilgisini değiştirin.",
    category="organize",                 # to_pdf | from_pdf | organize | security | other
    accepts=[".pdf"],                    # kabul edilen uzantılar (["*"] = hepsi)
    mode="each",                         # each: her dosya ayrı | all: hepsi tek işte (birleştirme gibi)
    badge="ℹ",                           # kart rozeti (kısa metin/emoji)
    color="#00897b",
    options=[
        opt_text("title", "Başlık", ""),
        opt_text("author", "Yazar", ""),
    ],
)
def run(files, outdir, opts, progress):
    src = files[0]
    doc = open_pdf(src)
    progress(0.5, "Bilgiler yazılıyor…")
    meta = doc.metadata
    if opts.get("title"):
        meta["title"] = opts["title"]
    if opts.get("author"):
        meta["author"] = opts["author"]
    doc.set_metadata(meta)
    dst = out_path(outdir, src.stem, ".pdf")
    doc.save(str(dst))
    doc.close()
    # Liste döndürebilir ya da kullanıcıya not göstermek için:
    #   return {"files": [dst], "notes": ["Bilgi notu"]}
    return [dst]
