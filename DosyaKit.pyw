"""DosyaKit başlatıcısı (pythonw ile konsol penceresi açmadan çalışır)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# pythonw'da konsol yok; stdout/stderr'e yazan kütüphaneler çökmesin
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from app.main import main  # noqa: E402

if __name__ == "__main__":
    main()
