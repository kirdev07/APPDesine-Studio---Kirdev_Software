"""Сведения о шрифте прямо из файла TrueType / OpenType (таблица OS/2): насыщенность и курсив. Без Qt."""

from __future__ import annotations

import struct


def weight_italic(data: bytes) -> tuple[int, bool]:
    """(насыщенность 100…900, курсив). Не удалось прочитать — (400, False)."""
    try:
        if len(data) < 12:
            return 400, False
        num = struct.unpack(">H", data[4:6])[0]
        for i in range(num):
            rec = 12 + 16 * i
            tag = data[rec:rec + 4]
            if tag == b"OS/2":
                off = struct.unpack(">I", data[rec + 8:rec + 12])[0]
                weight = struct.unpack(">H", data[off + 4:off + 6])[0]
                fs_selection = struct.unpack(">H", data[off + 62:off + 64])[0]
                weight = min(900, max(100, int(round(weight / 100.0)) * 100)) if weight else 400
                return weight, bool(fs_selection & 1)
    except (struct.error, IndexError):
        pass
    return 400, False
