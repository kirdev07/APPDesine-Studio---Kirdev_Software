"""Строка заголовка окон Windows в цветах программы (Windows 11 — свой цвет, Windows 10 — тёмная тема окна).
Окна по-прежнему системные: перетаскивание, прилипание к краям и кнопки работают как обычно."""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QWidget

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36


def _colorref(color: str) -> ctypes.c_uint:
    c = QColor(color)
    return ctypes.c_uint(c.red() | (c.green() << 8) | (c.blue() << 16))


def paint(widget: QWidget, caption: str, text: str, border: str, dark: bool = True) -> bool:
    """Окраска строки заголовка окна. Не Windows или старая система — ничего не делает (False)."""
    if sys.platform != "win32" or not widget.isWindow():
        return False
    try:
        dwm = ctypes.windll.dwmapi
        hwnd = ctypes.c_void_p(int(widget.winId()))
        flag = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(flag), ctypes.sizeof(flag))
        ok = True
        for attr, value in ((DWMWA_CAPTION_COLOR, caption), (DWMWA_TEXT_COLOR, text), (DWMWA_BORDER_COLOR, border)):
            v = _colorref(value)
            ok = dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v)) == 0 and ok
        return ok  # Windows 10 цвет не принимает — остаётся тёмная тема заголовка
    except (AttributeError, OSError):
        return False


class TitleBarPainter(QObject):
    """Красит строку заголовка каждого окна программы при первом показе (главное окно, диалоги)."""

    def __init__(self, caption: str, text: str, border: str):
        super().__init__()
        self.colors = (caption, text, border)

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow() \
                and not obj.property("ads_titlebar"):
            obj.setProperty("ads_titlebar", True)
            paint(obj, *self.colors)
        return False


def install(app: QApplication, caption: str, text: str, border: str) -> TitleBarPainter:
    f = TitleBarPainter(caption, text, border)
    f.setParent(app)
    app.installEventFilter(f)
    return f
