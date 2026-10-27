"""Общие элементы интерфейса."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from app.ui.themes.fusion_amoled import TOKENS

PLATFORM_NAMES = {"android": "Android", "windows": "Windows"}


def platforms_text(platforms: list[str]) -> str:
    return " + ".join(PLATFORM_NAMES.get(p, p) for p in platforms)


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def stage_badge(stage: int) -> QLabel:
    return label(f"Этап {stage}", "Stage")


def separator() -> QFrame:
    f = QFrame()
    f.setObjectName("Separator")
    return f


def panel(parent: QWidget | None = None, margins: int = 14) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(parent)
    frame.setObjectName("Panel")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(8)
    return frame, lay


def format_date(iso: str) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%d.%m.%Y, %H:%M")
    except ValueError:
        return iso


def format_size(size: int) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
        size /= 1024
    return str(size)


def thumbnail(platforms: list[str], title: str, w: int = 200, h: int = 120, missing: bool = False) -> QPixmap:
    """Условная миниатюра: силуэты устройств. Настоящие превью экранов появятся с холстом (этап 2)."""
    pm = QPixmap(w, h)
    pm.fill(QColor(TOKENS["surface_2"]))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(TOKENS["text_disabled"] if missing else "#8A8A8A"), 2)
    p.setPen(pen)
    k = h / 120
    pw, ph, ww, wh, gap = 42 * k, 82 * k, 88 * k, 64 * k, 14 * k
    shapes = [s for s, plat in (("win", "windows"), ("phone", "android")) if plat in platforms]
    total = sum(ww if s == "win" else pw for s in shapes) + gap * (len(shapes) - 1)
    x = (w - total) / 2
    for s in shapes:
        if s == "phone":
            r = QRectF(x, (h - ph) / 2, pw, ph)
            p.drawRoundedRect(r, 7 * k, 7 * k)
            p.drawLine(int(r.center().x() - 6 * k), int(r.bottom() - 6 * k),
                       int(r.center().x() + 6 * k), int(r.bottom() - 6 * k))
            x += pw + gap
        else:
            r = QRectF(x, (h - wh) / 2, ww, wh)
            p.drawRoundedRect(r, 4 * k, 4 * k)
            p.drawLine(int(r.left()), int(r.top() + 10 * k), int(r.right()), int(r.top() + 10 * k))
            x += ww + gap
    if missing:
        p.setPen(QColor(TOKENS["danger"]))
        p.setFont(QFont(TOKENS["font"], 9))
        p.drawText(pm.rect().adjusted(0, 0, 0, -6), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                   "файл недоступен")
    p.end()
    return pm


# Глифы системного шрифта значков Windows (Segoe Fluent Icons / Segoe MDL2 Assets). Шрифт не поставляется
# с программой — используется установленный в системе; если его нет, рисуется первая буква подписи.
GLYPHS = {
    "projects": "", "project": "", "components": "", "icons": "", "fonts": "",
    "colors": "", "animations": "", "logic": "", "devices": "", "layers": "",
    "resources": "", "validate": "", "export": "", "ai": "", "settings": "",
    "edit": "", "grid": "", "list": "", "add": "", "folder": "",
}


def _icon_font() -> str | None:
    families = set(QFontDatabase.families())
    for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
        if name in families:
            return name
    return None


def glyph_icon(key: str, size: int = 20, color: str = "#F2F2F2", fallback: str = "?") -> QIcon:
    icon = QIcon()
    family = _icon_font()
    for mode, col in ((QIcon.Mode.Normal, color), (QIcon.Mode.Disabled, TOKENS["text_disabled"]),
                      (QIcon.Mode.Active, color), (QIcon.Mode.Selected, color)):
        pm = QPixmap(size * 2, size * 2)
        pm.setDevicePixelRatio(2)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setPen(QColor(col))
        f = QFont(family or TOKENS["font"])
        f.setPixelSize(int(size * 0.8))
        f.setBold(family is None)
        p.setFont(f)
        p.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, GLYPHS[key] if family else fallback[:1])
        p.end()
        icon.addPixmap(pm, mode)
    return icon


def pixmap_icon(pm: QPixmap) -> QIcon:
    """Иконка без синего тонирования в выделенном состоянии."""
    icon = QIcon(pm)
    icon.addPixmap(pm, QIcon.Mode.Selected)
    return icon
