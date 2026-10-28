"""Показ на весь экран: экраны проекта по очереди, как слайды (заказчику, на созвоне)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from app.ui.workspace.render_export import render_screen

NEXT = {Qt.Key.Key_Right, Qt.Key.Key_Space, Qt.Key.Key_PageDown, Qt.Key.Key_Return, Qt.Key.Key_Enter,
        Qt.Key.Key_Down}
PREV = {Qt.Key.Key_Left, Qt.Key.Key_Backspace, Qt.Key.Key_PageUp, Qt.Key.Key_Up}


class Presentation(QWidget):
    def __init__(self, screens, doc, color: str, start: int = 0, parent=None):
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("Показ")
        self.screens, self.doc, self.color = list(screens), doc, color
        self.index = max(0, min(start, len(self.screens) - 1))
        self._cache: dict[int, QPixmap] = {}
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def pixmap(self, i: int) -> QPixmap:
        if i not in self._cache:
            s = self.screens[i]
            k = min(1.0, 2400 / max(s.width, s.height))  # хватает для любого монитора, без лишней памяти
            self._cache[i] = QPixmap.fromImage(render_screen(s, self.doc, self.color, k))
        return self._cache[i]

    def go(self, i: int) -> None:
        self.index = max(0, min(i, len(self.screens) - 1))
        self.update()

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self.close()
        elif k in NEXT:
            self.go(self.index + 1)
        elif k in PREV:
            self.go(self.index - 1)
        elif k == Qt.Key.Key_Home:
            self.go(0)
        elif k == Qt.Key.Key_End:
            self.go(len(self.screens) - 1)
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e):
        self.go(self.index + (1 if e.position().x() > self.width() / 3 else -1))  # левая треть — назад

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#000000"))
        if not self.screens:
            return
        pm = self.pixmap(self.index)
        cap = 44
        avail = QRectF(24, 24, self.width() - 48, self.height() - 48 - cap)
        k = min(avail.width() / pm.width(), avail.height() / pm.height())
        w, h = pm.width() * k, pm.height() * k
        target = QRectF(avail.x() + (avail.width() - w) / 2, avail.y() + (avail.height() - h) / 2, w, h)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(target, pm, QRectF(pm.rect()))
        f = QFont()
        f.setPixelSize(15)
        p.setFont(f)
        p.setPen(QColor("#8A8A8A"))
        p.drawText(QRectF(0, self.height() - cap, self.width(), cap), Qt.AlignmentFlag.AlignCenter,
                   f"{self.screens[self.index].name}   ·   {self.index + 1} / {len(self.screens)}   ·   "
                   "← → листать, Esc — выход")
