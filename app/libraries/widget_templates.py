"""Готовые виджеты рабочего стола Android (версия 1.29). Без Qt.

Виджет — отдельный экран размером в клетках лаунчера (устройство «Виджет N×M»); содержимое — фрейм на весь
виджет со скруглением 24 dp. В Android переводится в Jetpack Glance (app/exporters/glance.py).
"""

from __future__ import annotations

from app.core.document.model import Node, Screen
from app.libraries.components import _Ctx

# размеры в dp по клеткам лаунчера (примерно как у Pixel Launcher)
SIZES = {"2x1": (152, 72), "2x2": (152, 152), "4x1": (320, 72), "4x2": (320, 152), "4x4": (320, 320)}
DPI = 420


def device_id(size: str) -> str:
    return f"android_widget_{size}"


def blank(size: str, name: str = "Виджет") -> Screen:
    w, h = SIZES[size]
    k = DPI / 160
    return Screen(name=name, platform="android", width=round(w * k), height=round(h * k), device_id=device_id(size),
                  orientation="landscape" if w > h else "portrait")


def _root(c: _Ctx, s: Screen, kids: list[Node], layout: str = "vertical", fill: str = "surfaceContainer", **kw) -> Node:
    kw.setdefault("gap", 6)
    kw.setdefault("pad_l", 16)
    kw.setdefault("pad_r", 16)
    kw.setdefault("pad_t", 14)
    kw.setdefault("pad_b", 14)
    return c.frame("Виджет", layout, kids, x=0, y=0, w=s.width / c.k, h=s.height / c.k, radius=24, fill=c.s[fill],
                   constraint_h="left_right", constraint_v="top_bottom", **kw)


def _t(c: _Ctx, text: str, size: float, color: str, weight: int = 400, name: str = "Текст", **kw) -> Node:
    return c.text(text, size, c.s[color], weight, name, **kw)


def clock_weather(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    left = c.frame("Время", "vertical", [_t(c, "10:24", 44, "onSurface", 400, "Часы"),
                                         _t(c, "Среда, 29 октября", 14, "onSurfaceVariant", name="Дата")],
                   gap=2, sizing_h="fill", sizing_v="hug")
    right = c.frame("Погода", "vertical", [c.icon(40, color=c.s["primary"], glyph="partly_cloudy_day"),
                                           _t(c, "+12°", 22, "onSurface", 500, "Температура"),
                                           _t(c, "Москва", 12, "onSurfaceVariant", name="Город")],
                    gap=2, cross_align="end", sizing_h="hug", sizing_v="hug")
    return [_root(c, s, [left, right], "horizontal", cross_align="center", gap=12)]


def note(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    head = c.frame("Шапка", "horizontal", [c.icon(18, color=c.s["onTertiaryContainer"], glyph="edit_note"),
                                          _t(c, "Покупки", 15, "onTertiaryContainer", 600, "Заголовок", sizing_h="fill")],
                   gap=6, cross_align="center", sizing_h="fill", sizing_v="hug")
    body = _t(c, "Молоко, хлеб, яблоки, сыр, кофе", 13, "onTertiaryContainer", name="Текст", sizing_h="fill")
    return [_root(c, s, [head, body], fill="tertiaryContainer", gap=8)]


def player(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    cover = c.frame("Обложка", "horizontal", [c.icon(24, color=c.s["onPrimaryContainer"], glyph="music_note")],
                    w=44, h=44, radius=12, fill=c.s["primaryContainer"], main_align="center", cross_align="center")
    info = c.frame("Трек", "vertical", [_t(c, "Ночной город", 15, "onSurface", 500, "Название"),
                                        _t(c, "Синтвейв · 3:42", 12, "onSurfaceVariant", name="Исполнитель")],
                   gap=0, sizing_h="fill", sizing_v="hug")
    play = c.frame("Играть", "horizontal", [c.icon(24, color=c.s["onPrimary"], glyph="play_arrow")], w=40, h=40,
                   radius=20, fill=c.s["primary"], main_align="center", cross_align="center")
    nxt = c.icon(28, "Дальше", c.s["onSurfaceVariant"], "skip_next")
    return [_root(c, s, [cover, info, play, nxt], "horizontal", cross_align="center", gap=12, pad_t=12, pad_b=12)]


def steps(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    track = c.frame("Прогресс", "horizontal", [c.rect("Пройдено", 120 * 0.78, 6, c.s["primary"], 3)], w=120, h=6,
                    radius=3, fill=c.s["secondaryContainer"])
    return [_root(c, s, [c.icon(28, color=c.s["primary"], glyph="directions_walk"),
                         _t(c, "7 840", 28, "onSurface", 600, "Шаги"),
                         _t(c, "из 10 000 шагов", 12, "onSurfaceVariant", name="Цель"), track], gap=6)]


def balance(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    info = c.frame("Баланс", "vertical", [_t(c, "Дебетовая •••• 4821", 12, "onPrimaryContainer", name="Карта"),
                                          _t(c, "48 250 ₽", 22, "onPrimaryContainer", 600, "Сумма")],
                   gap=0, sizing_h="fill", sizing_v="hug")
    send = c.frame("Перевести", "horizontal", [c.icon(22, color=c.s["onPrimary"], glyph="send")], w=40, h=40,
                   radius=20, fill=c.s["primary"], main_align="center", cross_align="center")
    return [_root(c, s, [info, send], "horizontal", fill="primaryContainer", cross_align="center", gap=12,
                  pad_t=12, pad_b=12)]


def event(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    date = c.frame("Дата", "vertical", [_t(c, "НОЯ", 12, "onPrimary", 600, "Месяц"),
                                        _t(c, "15", 26, "onPrimary", 600, "День")],
                   w=60, h=64, radius=16, fill=c.s["primary"], main_align="center", cross_align="center", gap=0)
    info = c.frame("Событие", "vertical", [_t(c, "Ближайшее событие", 12, "onSurfaceVariant", name="Подпись"),
                                           _t(c, "Джаз под звёздами", 16, "onSurface", 500, "Название",
                                              sizing_h="fill"),
                                           _t(c, "Сб, 19:00 · «Зарядье»", 13, "onSurfaceVariant", name="Когда")],
                   gap=2, sizing_h="fill", sizing_v="hug")
    return [_root(c, s, [date, info], "horizontal", cross_align="center", gap=14)]


def actions(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)

    def act(glyph, t):
        return c.frame(f"Действие «{t}»", "vertical",
                       [c.frame("Значок", "horizontal", [c.icon(22, color=c.s["onSecondaryContainer"], glyph=glyph)],
                                w=40, h=40, radius=20, fill=c.s["secondaryContainer"], main_align="center",
                                cross_align="center"),
                        _t(c, t, 11, "onSurface", name="Подпись")],
                       gap=2, cross_align="center", sizing_h="fill", sizing_v="hug")
    return [_root(c, s, [act("qr_code_scanner", "Оплатить"), act("send", "Перевести"), act("add", "Пополнить"),
                         act("history", "История")], "horizontal", cross_align="center", gap=0, pad_t=8, pad_b=8)]


# ключ: (название, размер, функция)
WIDGETS = {
    "clock_weather": ("Часы и погода", "4x2", clock_weather), "note": ("Заметка", "2x2", note),
    "player": ("Плеер", "4x1", player), "steps": ("Шаги", "2x2", steps), "balance": ("Баланс", "4x1", balance),
    "event": ("Ближайшее событие", "4x2", event), "actions": ("Быстрые действия", "4x1", actions),
}


def build(key: str, appearance) -> Screen:
    title, size, fn = WIDGETS[key]
    s = blank(size, f"Виджет «{title}»")
    s.nodes = fn(s, appearance)
    return s
