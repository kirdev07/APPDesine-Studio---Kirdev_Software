"""Шрифты проекта: проверка файлов, регистрация в Qt, доступность семейств и покрытие символов."""

from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics

log = logging.getLogger(__name__)

MAX_FONT_BYTES = 25 * 1024 * 1024
MAGIC = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf")
CYRILLIC = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя"
LATIN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
DIGITS = "0123456789.,:;!?«»—–-()\"'%₽$€"


class FontError(ValueError):
    pass


def check_font_file(data: bytes) -> str:
    """Проверка до передачи в парсер Qt: размер и сигнатура TrueType/OpenType. Возвращает расширение."""
    if len(data) > MAX_FONT_BYTES:
        raise FontError("Файл шрифта больше 25 МБ")
    if len(data) < 12 or data[:4] not in MAGIC:
        raise FontError("Файл не похож на шрифт TrueType/OpenType")
    if data[:4] == b"ttcf":
        raise FontError("Коллекции шрифтов (.ttc) не поддерживаются — импортируйте отдельный .ttf/.otf")
    return "otf" if data[:4] == b"OTTO" else "ttf"


class FontRegistry:
    def __init__(self):
        self._by_asset: dict[str, list[str]] = {}
        self._system: set[str] | None = None

    def register(self, asset_id: str, data: bytes) -> list[str]:
        if asset_id in self._by_asset:
            return self._by_asset[asset_id]
        check_font_file(data)
        fid = QFontDatabase.addApplicationFontFromData(QByteArray(data))
        if fid < 0:
            raise FontError("Qt не смог прочитать файл шрифта (файл повреждён или формат не поддерживается)")
        fams = QFontDatabase.applicationFontFamilies(fid)
        self._by_asset[asset_id] = list(fams)
        self._system = None
        log.info("Зарегистрирован шрифт проекта: %s", ", ".join(fams))
        return list(fams)

    def register_document(self, doc) -> list[str]:
        problems = []
        for a in doc.assets:
            if a.kind == "font" and a.id in doc.asset_data:
                try:
                    self.register(a.id, doc.asset_data[a.id])
                except FontError as exc:
                    problems.append(f"{a.name}: {exc}")
        return problems

    def families(self) -> set[str]:
        if self._system is None:
            self._system = set(QFontDatabase.families())
        return self._system

    def available(self, family: str) -> bool:
        fams = self.families()
        # пустая база шрифтов (например, платформа offscreen без шрифтов) — проверить нельзя, не предупреждаем
        return not fams or family in fams

    def missing_chars(self, family: str, text: str) -> str:
        if not text or not self.families():
            return ""
        fm = QFontMetrics(QFont(family))
        miss = []
        for ch in dict.fromkeys(text):
            if ch.isspace() or ord(ch) < 32:
                continue
            if not fm.inFontUcs4(ord(ch)):
                miss.append(ch)
            if len(miss) >= 40:
                break
        return "".join(miss)

    def coverage(self, family: str) -> dict[str, tuple[int, int]]:
        res = {}
        for name, chars in (("Кириллица", CYRILLIC), ("Латиница", LATIN), ("Цифры и знаки", DIGITS)):
            miss = self.missing_chars(family, chars)
            res[name] = (len(chars) - len(miss), len(chars))
        return res


REGISTRY = FontRegistry()
