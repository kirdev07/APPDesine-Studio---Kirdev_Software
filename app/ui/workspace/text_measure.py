"""Измерение текста через Qt — тем же способом, каким текст рисуется на холсте."""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QFontMetricsF


class QtTextMeasurer:
    def __init__(self):
        self._fonts: dict = {}

    def _metrics(self, family: str, size: float, weight: int) -> QFontMetricsF:
        key = (family, size, weight)
        fm = self._fonts.get(key)
        if fm is None:
            f = QFont(family)
            f.setPixelSize(max(1, int(round(size))))
            f.setWeight(QFont.Weight(weight))
            fm = self._fonts[key] = QFontMetricsF(f)
        return fm

    def measure(self, text, family, size, weight, max_width):
        fm = self._metrics(family, size, weight)
        sample = text if text else " "
        if max_width is None:
            r = fm.boundingRect(QRectF(0, 0, 1e7, 1e7), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, sample)
            # +1 px: ширина «по содержимому» не должна вызывать перенос последнего слова при отрисовке
            return float(math.ceil(r.width()) + 1), float(math.ceil(r.height()))
        r = fm.boundingRect(QRectF(0, 0, max(1.0, max_width), 1e7),
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, sample)
        return float(math.ceil(min(r.width(), max_width))), float(math.ceil(r.height()))
