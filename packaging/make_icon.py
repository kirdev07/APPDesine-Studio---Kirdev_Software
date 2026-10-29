"""Иконка программы (packaging/app.ico): логотип app/ui/logo.py, все размеры от 16 до 256."""

import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.ui import logo  # noqa: E402

if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    out = Path(__file__).with_name("app.ico")
    out.write_bytes(logo.ico_bytes())
    print(out)
