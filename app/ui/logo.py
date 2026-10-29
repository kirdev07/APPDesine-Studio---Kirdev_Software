"""Логотип App Design Studio: окно Windows и телефон Android на скруглённом квадрате (синий → фиолетовый).
Рисуется Qt — без файлов картинок; тот же рисунок — значок окна и app.ico сборки."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)
    m = s * 0.04
    plate = QRectF(m, m, s - 2 * m, s - 2 * m)
    g = QLinearGradient(plate.topLeft(), plate.bottomRight())
    g.setColorAt(0.0, QColor("#2F7BFF"))
    g.setColorAt(1.0, QColor("#7A3CF0"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(plate, s * 0.22, s * 0.22)
    white = QColor("#FFFFFF")
    if size <= 20:  # мелкий значок (заголовок, панель задач): толстая рамка окна и сплошной телефон — без мелочей
        p.setPen(QPen(white, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        u = s / 16.0  # окно справа и телефон слева — рядом, без наложения (на 16 px иначе сливаются)
        p.drawRect(QRectF(8 * u, 5 * u, 5 * u, 6 * u))
        p.fillRect(QRectF(7 * u, 4 * u, 7 * u, 2 * u), white)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(white)
        p.drawRoundedRect(QRectF(2.5 * u, 4 * u, 3.5 * u, 8 * u), 0.8 * u, 0.8 * u)
        p.end()
        return img
    line = max(1.0, s * 0.055)
    # окно Windows: справа сверху, полоса заголовка залита
    win = QRectF(s * 0.30, s * 0.22, s * 0.50, s * 0.40)
    p.setBrush(QColor(255, 255, 255, 40))
    p.setPen(QPen(white, line, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawRoundedRect(win, s * 0.05, s * 0.05)
    bar = QPainterPath()
    bar.addRoundedRect(QRectF(win.x(), win.y(), win.width(), s * 0.10), s * 0.05, s * 0.05)
    p.fillPath(bar, white)
    # телефон Android: слева снизу, поверх окна (подложка цвета плашки — окно под ним не просвечивает)
    phone = QRectF(s * 0.20, s * 0.40, s * 0.24, s * 0.40)
    under = QLinearGradient(plate.topLeft(), plate.bottomRight())
    under.setColorAt(0.0, QColor("#4A62F8"))
    under.setColorAt(1.0, QColor("#6A45F2"))
    p.setBrush(under)
    p.drawRoundedRect(phone, s * 0.06, s * 0.06)
    if size >= 32:  # динамик и кнопка «домой» — только на крупных размерах
        p.setPen(QPen(white, line * 0.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cx = phone.center().x()
        p.drawLine(QPointF(cx - s * 0.035, phone.y() + s * 0.06), QPointF(cx + s * 0.035, phone.y() + s * 0.06))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(white)
        p.drawEllipse(QPointF(cx, phone.bottom() - s * 0.065), s * 0.025, s * 0.025)
    p.end()
    return img


def icon() -> QIcon:
    ic = QIcon()
    for n in ICON_SIZES:
        ic.addPixmap(QPixmap.fromImage(draw(n)))
    return ic


def ico_bytes() -> bytes:
    """Файл .ico со всеми размерами (картинки PNG внутри — так понимает Windows Vista и новее)."""
    import struct

    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    pngs = []
    for n in ICON_SIZES:
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        draw(n).save(buf, "PNG")
        pngs.append((n, bytes(data)))
    head = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for n, png in pngs:
        entries += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        blobs += png
    return head + entries + blobs
