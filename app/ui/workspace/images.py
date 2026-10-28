"""Картинки и фото: чтение файлов (PNG, JPEG, WebP) с проверкой и фото-заглушки для макетов.

Заглушки рисуются программой (свои рисунки, без чужих фото) в цветах схемы проекта: пейзаж, город, еда,
человек, товар, абстракция. Их можно свободно использовать и распространять; для настоящего приложения
замените на свои фото («Картинка…» на панели выделения).
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QLinearGradient, QPainter, QPainterPath, QRadialGradient

from app.core.document.model import Asset

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_SIDE = 8192
FORMATS = ("png", "jpeg", "jpg", "webp")
FILE_FILTER = "Изображения (*.png *.jpg *.jpeg *.webp)"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def read_image(data: bytes, name: str = "") -> tuple[str, int, int]:
    """Проверить картинку: (расширение, ширина, высота). ValueError — с понятным текстом."""
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"«{name}»: файл больше 20 МБ")
    buf = QBuffer()
    buf.setData(QByteArray(data))
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buf)
    fmt = bytes(reader.format()).decode().lower()
    size = reader.size()
    if fmt not in FORMATS:
        raise ValueError(f"«{name}»: формат не поддерживается (нужен PNG, JPEG или WebP)")
    if size.width() <= 0 or size.width() > MAX_SIDE or size.height() > MAX_SIDE:
        raise ValueError(f"«{name}»: картинка должна быть до {MAX_SIDE} px по стороне")
    if reader.read().isNull():
        raise ValueError(f"«{name}»: файл повреждён")
    return {"jpeg": "jpg"}.get(fmt, fmt), size.width(), size.height()


def asset_from_file(path: str | Path) -> tuple[Asset, bytes, tuple[int, int]]:
    p = Path(path)
    data = p.read_bytes()
    ext, w, h = read_image(data, p.name)
    a = Asset(kind="image", name=p.stem, ext=ext, sha256=hashlib.sha256(data).hexdigest(), size=len(data),
              source=p.name, redistribution="unknown")
    return a, data, (w, h)


# ---------------- фото-заглушки ----------------

PLACEHOLDERS = {"landscape": "Пейзаж", "city": "Город", "food": "Еда", "person": "Человек", "product": "Товар",
                "abstract": "Абстракция"}


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def placeholder_image(kind: str, sch: dict, w: int = 960, h: int = 720) -> QImage:
    """Рисунок-заглушка в цветах схемы Material 3 (sch — роли цвета)."""
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    prim, sec, ter = QColor(sch["primary"]), QColor(sch["secondary"]), QColor(sch["tertiary"])
    pc, tc = QColor(sch["primaryContainer"]), QColor(sch["tertiaryContainer"])
    light, dark = QColor("#FFFFFF"), QColor("#101418")
    if kind == "landscape":
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, _mix(pc, light, 0.35))
        g.setColorAt(1, _mix(tc, light, 0.15))
        p.fillRect(0, 0, w, h, g)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_mix(ter, light, 0.3))
        p.drawEllipse(QPointF(w * 0.72, h * 0.28), h * 0.11, h * 0.11)
        for k, (col, base, peaks) in enumerate(((_mix(sec, light, 0.25), 0.62, (0.0, 0.3, 0.55, 0.8, 1.0)),
                                                (_mix(prim, dark, 0.2), 0.75, (0.0, 0.2, 0.45, 0.7, 1.0)))):
            path = QPainterPath(QPointF(0, h))
            for i, x in enumerate(peaks):
                y = h * (base - (0.22 if i % 2 else 0.05) + 0.04 * k)
                path.lineTo(w * x, y)
            path.lineTo(w, h)
            path.closeSubpath()
            p.setBrush(col)
            p.drawPath(path)
    elif kind == "city":
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, _mix(prim, dark, 0.55))
        g.setColorAt(1, _mix(ter, dark, 0.2))
        p.fillRect(0, 0, w, h, g)
        p.setPen(Qt.PenStyle.NoPen)
        x, i = 0.0, 0
        while x < w:
            bw = w * (0.08 + 0.05 * ((i * 37) % 5) / 4)
            bh = h * (0.3 + 0.45 * ((i * 53) % 7) / 6)
            p.setBrush(_mix(dark, prim, 0.15 + 0.1 * (i % 3)))
            p.drawRect(QRectF(x, h - bh, bw - 4, bh))
            p.setBrush(_mix(pc, light, 0.4))
            for r in range(int(bh // 34)):
                for c in range(int((bw - 10) // 22)):
                    if (r * 7 + c * 3 + i) % 4:
                        p.drawRect(QRectF(x + 8 + c * 22, h - bh + 14 + r * 34, 10, 14))
            x += bw
            i += 1
    elif kind == "food":
        p.fillRect(0, 0, w, h, _mix(tc, light, 0.45))
        p.setPen(Qt.PenStyle.NoPen)
        c = QPointF(w / 2, h / 2)
        p.setBrush(QColor("#FAFAFA"))
        p.drawEllipse(c, h * 0.4, h * 0.4)
        p.setBrush(_mix(QColor("#FAFAFA"), sec, 0.15))
        p.drawEllipse(c, h * 0.3, h * 0.3)
        for k, col in enumerate((ter, prim, QColor("#E8A33D"), QColor("#7CB342"))):
            a = k * math.pi / 2 + 0.4
            p.setBrush(_mix(col, light, 0.1))
            p.drawEllipse(QPointF(c.x() + h * 0.12 * math.cos(a), c.y() + h * 0.12 * math.sin(a)), h * 0.09,
                          h * 0.07)
    elif kind == "person":
        g = QRadialGradient(QPointF(w / 2, h * 0.35), w * 0.8)
        g.setColorAt(0, _mix(pc, light, 0.4))
        g.setColorAt(1, _mix(sec, dark, 0.1))
        p.fillRect(0, 0, w, h, g)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_mix(prim, dark, 0.25))
        p.drawEllipse(QPointF(w / 2, h * 0.4), h * 0.17, h * 0.19)
        body = QPainterPath()
        body.addEllipse(QRectF(w / 2 - h * 0.36, h * 0.66, h * 0.72, h * 0.6))
        p.drawPath(body)
    elif kind == "product":
        p.fillRect(0, 0, w, h, _mix(pc, light, 0.6))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(QPointF(w / 2, h * 0.8), w * 0.22, h * 0.04)
        box = QRectF(w * 0.33, h * 0.22, w * 0.34, h * 0.56)
        g = QLinearGradient(box.topLeft(), box.bottomRight())
        g.setColorAt(0, _mix(prim, light, 0.15))
        g.setColorAt(1, _mix(prim, dark, 0.35))
        p.setBrush(g)
        p.drawRoundedRect(box, 28, 28)
        p.setBrush(_mix(pc, light, 0.5))
        p.drawRoundedRect(QRectF(box.x() + box.width() * 0.2, box.y() + box.height() * 0.35, box.width() * 0.6,
                                 box.height() * 0.12), 12, 12)
    else:  # abstract
        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0, prim)
        g.setColorAt(0.55, ter)
        g.setColorAt(1, sec)
        p.fillRect(0, 0, w, h, g)
        p.setPen(Qt.PenStyle.NoPen)
        for i, (fx, fy, r, a) in enumerate(((0.2, 0.25, 0.32, 70), (0.75, 0.7, 0.4, 60), (0.6, 0.15, 0.18, 90))):
            p.setBrush(QColor(255, 255, 255, a))
            p.drawEllipse(QPointF(w * fx, h * fy), w * r, w * r)
    p.end()
    return img


def placeholder_asset(kind: str, sch: dict) -> tuple[Asset, bytes, tuple[int, int]]:
    img = placeholder_image(kind, sch)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    data = bytes(buf.data())
    a = Asset(kind="image", name=f"Заглушка — {PLACEHOLDERS[kind].lower()}", ext="png",
              sha256=hashlib.sha256(data).hexdigest(), size=len(data), source="App Design Studio (рисунок-заглушка)",
              author="App Design Studio", license="Свободная (заглушка программы)", redistribution="allowed")
    return a, data, (img.width(), img.height())
