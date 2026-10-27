"""Иконка программы (packaging/app.ico): рисуется Qt, без сторонних файлов."""

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(size * 0.06, size * 0.06, size * 0.88, size * 0.88)
    p.setBrush(QColor("#0A0A0A"))
    p.setPen(QPen(QColor("#F2F2F2"), max(1.0, size / 24)))
    p.drawRoundedRect(r, size * 0.2, size * 0.2)
    f = QFont("Segoe UI")
    f.setPixelSize(int(size * 0.5))
    f.setWeight(QFont.Weight.Bold)
    p.setFont(f)
    p.setPen(QColor("#F2F2F2"))
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, "A")
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#2F7BFF"))
    p.drawEllipse(QRectF(size * 0.66, size * 0.66, size * 0.14, size * 0.14))
    p.end()
    return img


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    out = Path(__file__).with_name("app.ico")
    if not draw(256).save(str(out), "ICO"):
        raise SystemExit("Qt не смог записать ICO")
    print(out)
