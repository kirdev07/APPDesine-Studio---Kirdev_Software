"""Измерение текста через Qt — тем же способом, каким текст рисуется на холсте."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QTextLayout, QTextOption

from app.engines.layout.engine import PLAIN_LOOK

CASES = {"none": QFont.Capitalization.MixedCase, "upper": QFont.Capitalization.AllUppercase,
         "lower": QFont.Capitalization.AllLowercase, "title": QFont.Capitalization.Capitalize}


def text_font(family: str, size: float, weight: int, look: tuple = PLAIN_LOOK, decoration: str = "none") -> QFont:
    spacing, _line_h, italic, case, _max_lines = look
    f = QFont(family)
    f.setPixelSize(max(1, int(round(size))))
    f.setWeight(QFont.Weight(weight))
    f.setItalic(italic)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    f.setCapitalization(CASES.get(case, QFont.Capitalization.MixedCase))
    f.setUnderline(decoration == "underline")
    f.setStrikeOut(decoration == "strike")
    return f


class TextBlock:
    """Раскладка текста по строкам с заданной высотой строки и пределом строк (последняя — с многоточием)."""

    def __init__(self, text: str, font: QFont, size: float, width: float | None, line_h: float = 0.0,
                 max_lines: int = 0, align=Qt.AlignmentFlag.AlignLeft):
        self.font, self.width = font, width
        src = text if text else " "
        self.layout = QTextLayout(src.replace("\n", "\u2028"), font)
        opt = QTextOption(align)
        opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere if width is not None
                        else QTextOption.WrapMode.NoWrap)
        self.layout.setTextOption(opt)
        fm = QFontMetricsF(font)
        self.step = size * line_h if line_h > 0 else fm.lineSpacing()
        self.lines, y, widest = [], 0.0, 0.0
        self.layout.beginLayout()
        while True:
            ln = self.layout.createLine()
            if not ln.isValid():
                break
            ln.setLineWidth(max(1.0, width) if width is not None else 1e7)
            ln.setPosition(QPointF(0, y + (self.step - ln.height()) / 2))
            self.lines.append(ln)
            widest = max(widest, ln.naturalTextWidth())
            y += self.step
        self.layout.endLayout()
        self.elided = None
        if max_lines and len(self.lines) > max_lines:
            last = self.lines[max_lines - 1]
            rest = src[last.textStart():].replace("\n", " ")
            self.elided = fm.elidedText(rest, Qt.TextElideMode.ElideRight, max(1.0, width or widest))
            self.lines = self.lines[:max_lines]
        self.natural_width = widest
        self.height = len(self.lines) * self.step

    def draw(self, p, rect: QRectF, align) -> None:
        for i, ln in enumerate(self.lines):
            if self.elided is not None and i == len(self.lines) - 1:
                p.drawText(QRectF(rect.x(), rect.y() + ln.y(), rect.width(), ln.height()),
                           align | Qt.AlignmentFlag.AlignTop, self.elided)
            else:
                ln.draw(p, rect.topLeft())


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

    def measure(self, text, family, size, weight, max_width, look=PLAIN_LOOK):
        if look != PLAIN_LOOK:  # интервалы, регистр, высота строки, предел строк — раскладкой, как при отрисовке
            b = TextBlock(text, text_font(family, size, weight, look), size, max_width, look[1], look[4])
            w = b.natural_width if max_width is None else min(b.natural_width, max_width)
            return float(math.ceil(w) + (1 if max_width is None else 0)), float(math.ceil(b.height))
        fm = self._metrics(family, size, weight)
        sample = text if text else " "
        if max_width is None:
            r = fm.boundingRect(QRectF(0, 0, 1e7, 1e7), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, sample)
            # +1 px: ширина «по содержимому» не должна вызывать перенос последнего слова при отрисовке
            return float(math.ceil(r.width()) + 1), float(math.ceil(r.height()))
        r = fm.boundingRect(QRectF(0, 0, max(1.0, max_width), 1e7),
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, sample)
        return float(math.ceil(min(r.width(), max_width))), float(math.ceil(r.height()))
