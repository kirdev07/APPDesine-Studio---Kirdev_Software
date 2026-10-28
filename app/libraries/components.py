"""Базовые компоненты (заготовки) из фреймов с Auto Layout.

Android — Material 3: размеры в dp пересчитываются в пиксели экрана по плотности устройства, цвета — роли
схемы Material 3 по цвету оформления; корневой фрейм несёт роль (m3.switch, …), по которой экспорт создаёт
настоящий компонент Compose. Windows — приближение Fluent (пиксели при 96 dpi). Это стартовые макеты, а не
точная копия системных компонентов: точность отрисовки Compose/WinUI не гарантируется.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from app.core.document import tree
from app.core.document.model import Appearance, Node, Screen
from app.core.document.pathdata import normalize
from app.engines.material.color import scheme
from app.libraries.catalog import device
from app.libraries.m3_icons import ICONS

LOREM_RU = ("Карточка группирует связанную информацию. Длинный текст переносится по словам и увеличивает "
            "высоту карточки, если её высота задана «по содержимому».")


@dataclass(frozen=True)
class ComponentSpec:
    kind: str
    name: str
    platform: str
    category: str
    builder: Callable


def _palette(theme: str, accent: str = "#2F7BFF") -> dict:
    """Android — роли схемы Material 3 по цвету оформления; Windows — приближение Fluent."""
    s = scheme(accent, theme != "light")
    p = {"surface": s["surfaceContainerLow"], "surface2": s["secondaryContainer"], "on": s["onSurface"],
         "muted": s["onSurfaceVariant"], "outline": s["outline"]}
    if theme == "light":
        return p | {"win_surface": "#FBFBFB", "win_card": "#FFFFFF", "win_stroke": "#E5E5E5", "win_ctrl": "#FDFDFD"}
    return p | {"win_surface": "#202020", "win_card": "#2B2B2B", "win_stroke": "#3A3A3A", "win_ctrl": "#2D2D2D"}


def _on_color(hex_color: str) -> str:
    v = hex_color.lstrip("#")
    r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    return "#000000" if 0.299 * r + 0.587 * g + 0.114 * b > 160 else "#FFFFFF"


class _Ctx:
    def __init__(self, screen: Screen, ap: Appearance):
        self.screen, self.ap = screen, ap
        self.p = _palette(ap.theme, ap.accent)
        self.s = scheme(ap.accent, ap.theme != "light")  # роли Material 3
        dpi = 160
        if screen.platform == "android":
            try:
                dpi = device(screen.device_id).dpi
            except KeyError:
                dpi = max(160, round(screen.width / 411 * 160))
            self.k = dpi / 160
        else:
            self.k = 1.0
        self.font = ap.font_family

    def d(self, v: float) -> float:
        return round(v * self.k, 2)

    @property
    def width_dp(self) -> float:
        return self.screen.width / self.k

    def text(self, t: str, size: float, color: str, weight: int = 400, name: str = "Текст", **kw) -> Node:
        kw.setdefault("sizing_h", "hug")
        kw.setdefault("sizing_v", "hug")
        return Node(type="text", name=name, text=t, font_size=self.d(size), font_weight=weight, text_color=color,
                    font_family=self.font, fill="", w=self.d(100), h=self.d(size * 1.4), **kw)

    def label(self, t: str, color: str, name: str = "Подпись", **kw) -> Node:
        return self.text(t, 14, color, 500, name, **kw)

    def frame(self, name: str, layout: str, children: list[Node], **kw) -> Node:
        for key in ("gap", "row_gap", "pad_t", "pad_r", "pad_b", "pad_l", "radius", "stroke_width",
                    "w", "h", "min_w", "max_w", "min_h", "max_h"):
            if key in kw:
                kw[key] = self.d(kw[key])
        kw.setdefault("fill", "")
        return Node(type="frame", name=name, layout=layout, children=children, **kw)

    def icon(self, size: float = 24, name: str = "Значок", color: str | None = None, glyph: str = "") -> Node:
        """Значок из набора m3_icons; без glyph — круглая заглушка (аватар)."""
        if glyph and glyph not in ICONS:  # любой значок Material Symbols по имени
            from app.libraries import symbols
            d = symbols.path(glyph)
            if d:
                return Node(type="vector", name=symbols.russian_name(glyph) if name == "Значок" else name,
                            w=self.d(size), h=self.d(size), path=d, vb_w=symbols.VIEWBOX, vb_h=symbols.VIEWBOX,
                            fill=color or self.p["muted"])
            glyph = "star"
        if glyph:
            ru, path, rule = ICONS[glyph]
            return Node(type="vector", name=ru if name == "Значок" else name, w=self.d(size), h=self.d(size),
                        path=path, vb_w=24, vb_h=24, fill=color or self.p["muted"], fill_rule=rule)
        return Node(type="ellipse", name=name, w=self.d(size), h=self.d(size), fill=color or self.p["muted"])

    def rect(self, name: str, w: float, h: float, fill: str, radius: float = 0, **kw) -> Node:
        return Node(type="rect", name=name, w=self.d(w), h=self.d(h), fill=fill, radius=self.d(radius), **kw)

    def dot(self, name: str, size: float, fill: str) -> Node:
        return Node(type="ellipse", name=name, w=self.d(size), h=self.d(size), fill=fill)


# ---------------- Android / Material 3 ----------------

def _button(c: _Ctx, name: str, role: str, label: str, fg: str, glyph: str = "", **kw) -> Node:
    kids = ([c.icon(18, color=fg, glyph=glyph)] if glyph else []) + [c.label(label, fg)]
    kw.setdefault("pad_l", 16 if glyph else 24)
    kw.setdefault("pad_r", 24)
    return c.frame(name, "horizontal", kids, h=40, gap=8, radius=20, main_align="center", cross_align="center",
                   sizing_h="hug", sizing_v="fixed", role=role, **kw)


def m3_button_filled(c: _Ctx) -> Node:
    return _button(c, "Кнопка", "m3.button_filled", "Продолжить", c.s["onPrimary"], fill=c.s["primary"])


def m3_button_tonal(c: _Ctx) -> Node:
    return _button(c, "Кнопка (тональная)", "m3.button_tonal", "Сохранить", c.s["onSecondaryContainer"],
                   fill=c.s["secondaryContainer"])


def m3_button_outlined(c: _Ctx) -> Node:
    return _button(c, "Кнопка (контур)", "m3.button_outlined", "Отмена", c.s["primary"], stroke=c.s["outline"],
                   stroke_width=1)


def m3_button_text(c: _Ctx) -> Node:
    return _button(c, "Кнопка (текстовая)", "m3.button_text", "Подробнее", c.s["primary"], pad_l=12, pad_r=12)


def m3_button_icon(c: _Ctx) -> Node:
    return _button(c, "Кнопка со значком", "m3.button_filled", "Добавить", c.s["onPrimary"], "add",
                   fill=c.s["primary"])


def m3_icon_button(c: _Ctx) -> Node:
    return c.frame("Кнопка-значок", "horizontal", [c.icon(24, color=c.s["onSurfaceVariant"], glyph="favorite")],
                   w=48, h=48, radius=24, main_align="center", cross_align="center", role="m3.icon_button")


def m3_fab(c: _Ctx) -> Node:
    return c.frame("Плавающая кнопка", "horizontal", [c.icon(24, color=c.s["onPrimaryContainer"], glyph="add")],
                   w=56, h=56, radius=16, fill=c.s["primaryContainer"], main_align="center", cross_align="center",
                   role="m3.fab")


def m3_fab_extended(c: _Ctx) -> Node:
    fg = c.s["onPrimaryContainer"]
    return c.frame("Плавающая кнопка с текстом", "horizontal",
                   [c.icon(24, color=fg, glyph="edit"), c.label("Написать", fg)],
                   h=56, pad_l=16, pad_r=20, gap=12, radius=16, fill=c.s["primaryContainer"], cross_align="center",
                   sizing_h="hug", role="m3.fab_extended")


def m3_segmented(c: _Ctx) -> Node:
    segs = []
    for i, t in enumerate(("День", "Неделя", "Месяц")):
        if i:
            segs.append(c.rect("Разделитель", 1, 40, c.s["outline"], sizing_v="fill"))
        sel = i == 0
        fg = c.s["onSecondaryContainer"] if sel else c.s["onSurface"]
        kids = ([c.icon(18, color=fg, glyph="check")] if sel else []) + [c.label(t, fg)]
        segs.append(c.frame(f"Сегмент «{t}»", "horizontal", kids, gap=8, pad_l=16, pad_r=16, main_align="center",
                            cross_align="center", sizing_h="hug", sizing_v="fill", min_w=72,
                            fill=c.s["secondaryContainer"] if sel else ""))
    return c.frame("Сегментированные кнопки", "horizontal", segs, h=40, sizing_h="hug", radius=20, stroke=c.s["outline"],
                   stroke_width=1, cross_align="stretch", role="m3.segmented")


def m3_switch(c: _Ctx) -> Node:
    track = c.frame("Дорожка", "horizontal", [c.dot("Бегунок", 24, c.s["onPrimary"])],
                    w=52, h=32, radius=16, pad_l=4, pad_r=4, fill=c.s["primary"], main_align="end",
                    cross_align="center")
    return c.frame("Переключатель", "horizontal",
                   [c.text("Уведомления", 16, c.s["onSurface"], name="Подпись", sizing_h="fill"), track],
                   w=320, h=48, gap=16, cross_align="center", role="m3.switch")


def m3_checkbox(c: _Ctx) -> Node:
    box = c.frame("Флажок", "horizontal", [c.icon(14, color=c.s["onPrimary"], glyph="check")],
                  w=18, h=18, radius=2, fill=c.s["primary"], main_align="center", cross_align="center")
    target = c.frame("Область нажатия", "horizontal", [box], w=48, h=48, main_align="center", cross_align="center")
    return c.frame("Флажок с подписью", "horizontal",
                   [target, c.text("Запомнить меня", 16, c.s["onSurface"], name="Подпись")],
                   h=48, gap=4, cross_align="center", sizing_h="hug", role="m3.checkbox")


def m3_radio(c: _Ctx) -> Node:
    rows = []
    for i, t in enumerate(("Курьером", "Экспресс", "Самовывоз")):
        sel = i == 0
        col = c.s["primary"] if sel else c.s["onSurfaceVariant"]
        ring = c.frame("Кружок", "horizontal", [c.dot("Отметка", 10, col)] if sel else [],
                       w=20, h=20, radius=10, stroke=col, stroke_width=2, main_align="center", cross_align="center")
        target = c.frame("Область нажатия", "horizontal", [ring], w=48, h=48, main_align="center",
                         cross_align="center")
        rows.append(c.frame(f"Вариант «{t}»", "horizontal", [target, c.text(t, 16, c.s["onSurface"], name="Подпись")],
                            h=48, gap=4, cross_align="center", sizing_h="fill"))
    return c.frame("Радиокнопки", "vertical", rows, w=320, sizing_v="hug", role="m3.radio_group")


def m3_slider(c: _Ctx) -> Node:
    w = 320
    return c.frame("Ползунок", "horizontal",
                   [c.rect("Активная часть", (w - 20) * 0.4, 4, c.s["primary"], 2),
                    c.dot("Бегунок", 20, c.s["primary"]),
                    c.rect("Неактивная часть", 10, 4, c.s["secondaryContainer"], 2, sizing_h="fill")],
                   w=w, h=44, cross_align="center", role="m3.slider")


def m3_chip_assist(c: _Ctx) -> Node:
    return c.frame("Чип действия", "horizontal",
                   [c.icon(18, color=c.s["primary"], glyph="calendar"), c.label("В календарь", c.s["onSurface"])],
                   h=32, pad_l=8, pad_r=16, gap=8, radius=8, stroke=c.s["outline"], stroke_width=1,
                   cross_align="center", sizing_h="hug", role="m3.chip_assist")


def m3_chip_filter(c: _Ctx) -> Node:
    fg = c.s["onSecondaryContainer"]
    return c.frame("Чип фильтра", "horizontal", [c.icon(18, color=fg, glyph="check"), c.label("Без мяса", fg)],
                   h=32, pad_l=8, pad_r=16, gap=8, radius=8, fill=c.s["secondaryContainer"], cross_align="center",
                   sizing_h="hug", role="m3.chip_filter")


def m3_text_field(c: _Ctx) -> Node:
    box = c.frame("Поле", "horizontal", [c.text("Введите имя", 16, c.p["muted"], name="Плейсхолдер",
                                               sizing_h="fill")],
                  h=56, pad_l=16, pad_r=16, radius=4, stroke=c.p["outline"], stroke_width=1, cross_align="center",
                  sizing_h="fill")
    hint = c.text("Подсказка: имя увидят ваши контакты", 12, c.p["muted"], name="Подсказка", sizing_h="fill")
    return c.frame("Текстовое поле", "vertical", [box, hint], w=320, gap=4, sizing_v="hug", role="m3.text_field")


def m3_search_bar(c: _Ctx) -> Node:
    return c.frame("Строка поиска", "horizontal",
                   [c.icon(24, color=c.s["onSurface"], glyph="search"),
                    c.text("Найти в сообщениях", 16, c.s["onSurfaceVariant"], name="Плейсхолдер", sizing_h="fill"),
                    c.icon(30, "Аватар", c.s["primaryContainer"])],
                   x=c.d(16), w=c.width_dp - 32, h=56, radius=28, pad_l=16, pad_r=16, gap=16,
                   fill=c.s["surfaceContainerHigh"], cross_align="center", constraint_h="left_right",
                   role="m3.search_bar")


def m3_card(c: _Ctx) -> Node:
    btn = m3_button_filled(c)
    btn.children[0].text = "Открыть"
    actions = c.frame("Действия", "horizontal", [btn], main_align="end", sizing_h="fill", sizing_v="hug")
    return c.frame("Карточка", "vertical",
                   [c.text("Заголовок карточки", 22, c.s["onSurface"], 400, "Заголовок", sizing_h="fill"),
                    c.text(LOREM_RU, 14, c.s["onSurfaceVariant"], name="Описание", sizing_h="fill"), actions],
                   w=340, pad_t=16, pad_r=16, pad_b=16, pad_l=16, gap=8, radius=12,
                   fill=c.s["surfaceContainerHighest"], sizing_v="hug", role="m3.card")


def m3_card_outlined(c: _Ctx) -> Node:
    card = m3_card(c)
    card.name, card.role, card.fill = "Карточка (контур)", "m3.card_outlined", c.s["surface"]
    card.stroke, card.stroke_width = c.s["outlineVariant"], c.d(1)
    return card


def m3_list_item(c: _Ctx) -> Node:
    texts = c.frame("Текст", "vertical",
                    [c.text("Анна Смирнова", 16, c.s["onSurface"], name="Заголовок", sizing_h="fill"),
                     c.text("Увидимся завтра в десять, не забудь документы", 14, c.s["onSurfaceVariant"],
                            name="Подпись", sizing_h="fill")],
                    gap=2, sizing_h="fill", sizing_v="hug")
    return c.frame("Элемент списка", "horizontal", [c.icon(40, "Аватар", c.s["primaryContainer"]), texts],
                   x=0, w=c.width_dp, h=72, pad_l=16, pad_r=24, gap=16, cross_align="center",
                   constraint_h="left_right", sizing_v="hug", min_h=72, pad_t=8, pad_b=8, role="m3.list_item")


def m3_divider(c: _Ctx) -> Node:
    return c.frame("Разделитель", "none", [], x=c.d(16), w=c.width_dp - 32, h=1, fill=c.s["outlineVariant"],
                   constraint_h="left_right", role="m3.divider")


def m3_progress_linear(c: _Ctx) -> Node:
    return c.frame("Индикатор (линейный)", "horizontal", [c.rect("Выполнено", 320 * 0.6, 4, c.s["primary"], 2)],
                   w=320, h=4, radius=2, fill=c.s["secondaryContainer"], role="m3.progress_linear")


def _ring_arc(r_out: float, r_in: float, sweep: float, size: float) -> str:
    """Кольцевой сектор от 12 часов по часовой стрелке."""
    cx = cy = size / 2
    a0, a1 = math.radians(-90), math.radians(-90 + sweep)
    large = 1 if sweep > 180 else 0

    def p(r, a):
        return f"{cx + r * math.cos(a):.3f} {cy + r * math.sin(a):.3f}"
    return normalize(f"M{p(r_out, a0)} A{r_out} {r_out} 0 {large} 1 {p(r_out, a1)} L{p(r_in, a1)} "
                     f"A{r_in} {r_in} 0 {large} 0 {p(r_in, a0)} Z")


def m3_progress_circular(c: _Ctx) -> Node:
    arc = Node(type="vector", name="Дуга", w=c.d(40), h=c.d(40), path=_ring_arc(20, 16, 270, 40), vb_w=40, vb_h=40,
               fill=c.s["primary"])
    return c.frame("Индикатор (круговой)", "horizontal", [arc], w=48, h=48, main_align="center",
                   cross_align="center", role="m3.progress_circular")


def m3_badge(c: _Ctx) -> Node:
    ico = c.icon(24, color=c.s["onSurfaceVariant"], glyph="notifications")
    ico.x, ico.y = c.d(12), c.d(12)
    badge = c.frame("Счётчик", "horizontal", [c.text("3", 11, c.s["onError"], 500, "Число")],
                    h=16, min_w=16, pad_l=4, pad_r=4, radius=8, fill=c.s["error"], main_align="center",
                    cross_align="center", sizing_h="hug")
    badge.x, badge.y = c.d(26), c.d(6)
    badge.children[0].x, badge.children[0].y = badge.x + c.d(4), badge.y
    return c.frame("Значок со счётчиком", "none", [ico, badge], w=48, h=48, clip=False, role="m3.badge")


def m3_snackbar(c: _Ctx) -> Node:
    return c.frame("Всплывающее сообщение", "horizontal",
                   [c.text("Фото удалено", 14, c.s["inverseOnSurface"], name="Сообщение", sizing_h="fill"),
                    c.label("Отменить", c.s["inversePrimary"], name="Действие")],
                   x=c.d(16), w=c.width_dp - 32, h=48, pad_l=16, pad_r=16, gap=8, radius=4,
                   fill=c.s["inverseSurface"], cross_align="center", constraint_h="left_right", role="m3.snackbar")


def m3_dialog(c: _Ctx) -> Node:
    btns = [_button(c, "Кнопка «Отмена»", "m3.button_text", "Отмена", c.s["primary"], pad_l=12, pad_r=12),
            _button(c, "Кнопка «Удалить»", "m3.button_text", "Удалить", c.s["primary"], pad_l=12, pad_r=12)]
    return c.frame("Диалог", "vertical",
                   [c.text("Удалить черновик?", 24, c.s["onSurface"], name="Заголовок", sizing_h="fill"),
                    c.text("Черновик письма будет удалён без возможности восстановления.", 14,
                           c.s["onSurfaceVariant"], name="Текст", sizing_h="fill"),
                    c.frame("Действия", "horizontal", btns, gap=8, main_align="end", sizing_h="fill",
                            sizing_v="hug")],
                   w=312, pad_t=24, pad_r=24, pad_b=24, pad_l=24, gap=16, radius=28,
                   fill=c.s["surfaceContainerHigh"], sizing_v="hug", role="m3.dialog")


def _menu_row(c: _Ctx, glyph: str, t: str, active: bool = False, h: float = 48, **kw) -> Node:
    fg = c.s["onSecondaryContainer"] if active else c.s["onSurfaceVariant"]
    return c.frame(f"Пункт «{t}»", "horizontal",
                   [c.icon(24, color=fg, glyph=glyph),
                    c.label(t, c.s["onSecondaryContainer"] if active else c.s["onSurface"], sizing_h="fill")],
                   h=h, gap=12, cross_align="center", sizing_h="fill",
                   fill=c.s["secondaryContainer"] if active else "", **kw)


def m3_menu(c: _Ctx) -> Node:
    rows = [_menu_row(c, g, t, pad_l=12, pad_r=12) for g, t in
            (("edit", "Изменить"), ("share", "Поделиться"), ("delete", "Удалить"))]
    return c.frame("Меню", "vertical", rows, w=200, pad_t=8, pad_b=8, radius=4, fill=c.s["surfaceContainer"],
                   sizing_v="hug", role="m3.menu")


def m3_bottom_sheet(c: _Ctx) -> Node:
    handle = c.frame("Ручка", "horizontal", [c.rect("Полоска", 32, 4, c.s["onSurfaceVariant"], 2)],
                     h=22, main_align="center", cross_align="center", sizing_h="fill")
    rows = [_menu_row(c, g, t, h=56, pad_l=8, pad_r=8) for g, t in
            (("share", "Поделиться"), ("edit", "Изменить"), ("delete", "Удалить"))]
    h = 260
    return c.frame("Нижний лист", "vertical",
                   [handle, c.text("Действия с файлом", 22, c.s["onSurface"], name="Заголовок")] + rows,
                   x=0, y=c.screen.height - c.d(h), w=c.width_dp, h=h, pad_l=16, pad_r=16, pad_b=16, gap=4,
                   radius=28, fill=c.s["surfaceContainerLow"], constraint_h="left_right", constraint_v="bottom",
                   role="m3.bottom_sheet")


def m3_nav_drawer(c: _Ctx) -> Node:
    rows = [_menu_row(c, g, t, i == 0, h=56, radius=28, pad_l=16, pad_r=24)
            for i, (g, t) in enumerate((("home", "Входящие"), ("star", "Помеченные"), ("chat", "Чаты"),
                                        ("settings", "Настройки")))]
    title = c.frame("Заголовок", "horizontal", [c.label("Почта", c.s["onSurfaceVariant"])], h=56, pad_l=16,
                    cross_align="center", sizing_h="fill")
    return c.frame("Боковое меню", "vertical", [title] + rows, x=0, y=0, w=300, h=c.screen.height / c.k, pad_l=12,
                   pad_r=12, pad_t=12, radius=16, fill=c.s["surfaceContainerLow"], constraint_v="top_bottom",
                   role="m3.nav_drawer")


def m3_top_app_bar(c: _Ctx) -> Node:
    on = c.s["onSurface"]
    return c.frame("Верхняя панель", "horizontal",
                   [c.icon(24, "Меню", on, "menu"),
                    c.text("Заголовок экрана", 22, on, name="Заголовок", sizing_h="fill"),
                    c.icon(24, "Действие", c.s["onSurfaceVariant"], "more_vert")],
                   x=0, y=0, w=c.width_dp, h=64, pad_l=16, pad_r=16, gap=16, cross_align="center",
                   fill=c.s["surface"], constraint_h="left_right", constraint_v="top", role="m3.top_app_bar")


def m3_tabs(c: _Ctx) -> Node:
    tabs = []
    for i, t in enumerate(("Чаты", "Статусы", "Звонки")):
        sel = i == 0
        tabs.append(c.frame(f"Вкладка «{t}»", "vertical",
                            [c.rect("Отступ", 10, 3, "", sizing_h="fill"),
                             c.label(t, c.s["primary"] if sel else c.s["onSurfaceVariant"]),
                             c.rect("Индикатор", 10, 3, c.s["primary"] if sel else "", 3, sizing_h="fill")],
                            main_align="space_between", cross_align="center", sizing_h="fill", sizing_v="fill"))
    return c.frame("Вкладки", "horizontal", tabs, x=0, y=c.d(64), w=c.width_dp, h=48, fill=c.s["surface"],
                   cross_align="stretch", constraint_h="left_right", constraint_v="top", role="m3.tabs")


def m3_nav_bar(c: _Ctx) -> Node:
    s = c.screen
    items = []
    for i, (glyph, label) in enumerate((("home", "Главная"), ("chat", "Чаты"), ("call", "Звонки"),
                                        ("person", "Профиль"))):
        active = i == 0
        pill = c.frame("Индикатор", "horizontal",
                       [c.icon(24, color=c.s["onSecondaryContainer"] if active else c.s["onSurfaceVariant"],
                               glyph=glyph)],
                       w=64, h=32, radius=16, fill=c.s["secondaryContainer"] if active else "",
                       main_align="center", cross_align="center")
        items.append(c.frame(f"Пункт «{label}»", "vertical",
                             [pill, c.text(label, 12, c.s["onSurface"] if active else c.s["onSurfaceVariant"],
                                           600 if active else 500, "Подпись")],
                             gap=4, cross_align="center", main_align="center", sizing_h="fill", sizing_v="fill"))
    h = 80  # dp; x и y задаются в пикселях экрана
    return c.frame("Нижняя навигация", "horizontal", items, x=0, y=s.height - c.d(h), w=c.width_dp, h=h,
                   pad_t=12, pad_b=12, gap=8, fill=c.s["surfaceContainer"], cross_align="stretch",
                   constraint_h="left_right", constraint_v="bottom", role="m3.nav_bar")


def _icon_builder(glyph: str) -> Callable:
    def build_icon(c: _Ctx) -> Node:
        return c.icon(24, color=c.s["onSurface"], glyph=glyph)
    return build_icon


# ---------------- Windows / Fluent ----------------

def win_button_accent(c: _Ctx) -> Node:
    acc = c.ap.accent
    return c.frame("Кнопка", "horizontal", [c.text("Сохранить", 14, _on_color(acc), 400, "Подпись")],
                   h=32, pad_l=12, pad_r=12, radius=4, fill=acc, main_align="center", cross_align="center",
                   sizing_h="hug", min_w=120)


def win_button(c: _Ctx) -> Node:
    return c.frame("Кнопка (обычная)", "horizontal", [c.text("Отмена", 14, c.p["on"], 400, "Подпись")],
                   h=32, pad_l=12, pad_r=12, radius=4, fill=c.p["win_ctrl"], stroke=c.p["win_stroke"],
                   stroke_width=1, main_align="center", cross_align="center", sizing_h="hug", min_w=120)


def win_textbox(c: _Ctx) -> Node:
    box = c.frame("Поле", "horizontal", [c.text("Введите адрес", 14, c.p["muted"], name="Плейсхолдер",
                                               sizing_h="fill")],
                  h=32, pad_l=10, pad_r=10, radius=4, fill=c.p["win_ctrl"], stroke=c.p["win_stroke"], stroke_width=1,
                  cross_align="center", sizing_h="fill")
    return c.frame("Текстовое поле", "vertical", [c.text("Адрес сервера", 14, c.p["on"], name="Заголовок"), box],
                   w=296, gap=6, sizing_v="hug")


def win_card(c: _Ctx) -> Node:
    return c.frame("Карточка", "vertical",
                   [c.text("Заголовок карточки", 20, c.p["on"], 600, "Заголовок", sizing_h="fill"),
                    c.text(LOREM_RU, 14, c.p["muted"], name="Описание", sizing_h="fill")],
                   w=360, pad_t=16, pad_r=16, pad_b=16, pad_l=16, gap=8, radius=8, fill=c.p["win_card"],
                   stroke=c.p["win_stroke"], stroke_width=1, sizing_v="hug")


def win_nav_pane(c: _Ctx) -> Node:
    s = c.screen
    items = []
    for i, label in enumerate(["Главная", "Система", "Мониторинг", "Устройства", "Настройки"]):
        items.append(c.frame(f"Пункт «{label}»", "horizontal",
                             [c.text(label, 14, c.p["on"], 600 if i == 0 else 400, "Подпись", sizing_h="fill")],
                             h=36, pad_l=12, pad_r=12, radius=4, cross_align="center", sizing_h="fill",
                             fill=c.p["win_ctrl"] if i == 0 else ""))
    return c.frame("Панель навигации", "vertical", items, x=0, y=0, w=280, h=s.height, pad_t=8, pad_r=8, pad_b=8,
                   pad_l=8, gap=4, fill=c.p["win_surface"], constraint_v="top_bottom")


def win_command_bar(c: _Ctx) -> Node:
    btns = [c.frame(f"Команда «{t}»", "horizontal", [c.text(t, 14, c.p["on"], name="Подпись")], h=32, pad_l=12,
                    pad_r=12, radius=4, cross_align="center", sizing_h="hug")
            for t in ("Создать", "Изменить", "Удалить")]
    return c.frame("Панель команд", "horizontal", btns, h=48, pad_l=8, pad_r=8, gap=4, radius=8,
                   fill=c.p["win_card"], stroke=c.p["win_stroke"], stroke_width=1, cross_align="center",
                   sizing_h="hug")


_A = "android"
SPECS: tuple[ComponentSpec, ...] = (
    ComponentSpec("m3_button_filled", "Кнопка", _A, "Кнопки", m3_button_filled),
    ComponentSpec("m3_button_tonal", "Кнопка (тональная)", _A, "Кнопки", m3_button_tonal),
    ComponentSpec("m3_button_outlined", "Кнопка (контур)", _A, "Кнопки", m3_button_outlined),
    ComponentSpec("m3_button_text", "Кнопка (текстовая)", _A, "Кнопки", m3_button_text),
    ComponentSpec("m3_button_icon", "Кнопка со значком", _A, "Кнопки", m3_button_icon),
    ComponentSpec("m3_icon_button", "Кнопка-значок", _A, "Кнопки", m3_icon_button),
    ComponentSpec("m3_fab", "Плавающая кнопка (FAB)", _A, "Кнопки", m3_fab),
    ComponentSpec("m3_fab_extended", "Плавающая кнопка с текстом", _A, "Кнопки", m3_fab_extended),
    ComponentSpec("m3_segmented", "Сегментированные кнопки", _A, "Кнопки", m3_segmented),
    ComponentSpec("m3_switch", "Переключатель", _A, "Выбор", m3_switch),
    ComponentSpec("m3_checkbox", "Флажок", _A, "Выбор", m3_checkbox),
    ComponentSpec("m3_radio", "Радиокнопки", _A, "Выбор", m3_radio),
    ComponentSpec("m3_slider", "Ползунок", _A, "Выбор", m3_slider),
    ComponentSpec("m3_chip_assist", "Чип действия", _A, "Выбор", m3_chip_assist),
    ComponentSpec("m3_chip_filter", "Чип фильтра", _A, "Выбор", m3_chip_filter),
    ComponentSpec("m3_text_field", "Текстовое поле", _A, "Поля", m3_text_field),
    ComponentSpec("m3_search_bar", "Строка поиска", _A, "Поля", m3_search_bar),
    ComponentSpec("m3_card", "Карточка", _A, "Карточки", m3_card),
    ComponentSpec("m3_card_outlined", "Карточка (контур)", _A, "Карточки", m3_card_outlined),
    ComponentSpec("m3_list_item", "Элемент списка", _A, "Карточки", m3_list_item),
    ComponentSpec("m3_divider", "Разделитель", _A, "Карточки", m3_divider),
    ComponentSpec("m3_top_app_bar", "Верхняя панель", _A, "Навигация", m3_top_app_bar),
    ComponentSpec("m3_tabs", "Вкладки", _A, "Навигация", m3_tabs),
    ComponentSpec("m3_nav_bar", "Нижняя навигация", _A, "Навигация", m3_nav_bar),
    ComponentSpec("m3_nav_drawer", "Боковое меню", _A, "Навигация", m3_nav_drawer),
    ComponentSpec("m3_progress_linear", "Индикатор (линейный)", _A, "Обратная связь", m3_progress_linear),
    ComponentSpec("m3_progress_circular", "Индикатор (круговой)", _A, "Обратная связь", m3_progress_circular),
    ComponentSpec("m3_badge", "Значок со счётчиком", _A, "Обратная связь", m3_badge),
    ComponentSpec("m3_snackbar", "Всплывающее сообщение", _A, "Обратная связь", m3_snackbar),
    ComponentSpec("m3_dialog", "Диалог", _A, "Окна", m3_dialog),
    ComponentSpec("m3_bottom_sheet", "Нижний лист", _A, "Окна", m3_bottom_sheet),
    ComponentSpec("m3_menu", "Меню", _A, "Окна", m3_menu),
    *(ComponentSpec(f"m3_icon_{g}", f"Значок «{ru}»", _A, "Значки", _icon_builder(g))
      for g, (ru, _, _) in ICONS.items()),
    ComponentSpec("win_button_accent", "Кнопка", "windows", "Кнопки", win_button_accent),
    ComponentSpec("win_button", "Кнопка (обычная)", "windows", "Кнопки", win_button),
    ComponentSpec("win_textbox", "Текстовое поле", "windows", "Поля", win_textbox),
    ComponentSpec("win_card", "Карточка", "windows", "Карточки", win_card),
    ComponentSpec("win_command_bar", "Панель команд", "windows", "Навигация", win_command_bar),
    ComponentSpec("win_nav_pane", "Панель навигации", "windows", "Навигация", win_nav_pane),
)


_ALL: tuple[ComponentSpec, ...] | None = None
CATEGORY_ORDER = ("Кнопки", "Поля", "Выбор", "Вход и регистрация", "Карточки", "Профиль и люди", "Магазин",
                  "Навигация", "Обратная связь", "Состояния", "Окна")


def all_specs() -> tuple[ComponentSpec, ...]:
    """Все заготовки в порядке галереи: Material 3, дополнительные (вход, формы, магазин…), значки, Windows."""
    global _ALL
    if _ALL is None:
        from app.libraries.components_m3x import SPECS as M3X  # модули используют _Ctx отсюда
        from app.libraries.components_more import SPECS as MORE
        android = [s for s in SPECS if s.platform == _A and s.category != "Значки"] + list(M3X) + list(MORE)
        order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
        android.sort(key=lambda s: order.get(s.category, len(order)))  # одна категория — подряд
        icons = [s for s in SPECS if s.category == "Значки"]
        _ALL = tuple(android + icons + [s for s in SPECS if s.platform != _A])
    return _ALL


def specs_for(platform: str) -> list[ComponentSpec]:
    return [s for s in all_specs() if s.platform == platform]


def build(kind: str, screen: Screen, appearance: Appearance) -> Node:
    spec = next((s for s in all_specs() if s.kind == kind), None)
    if spec is None:
        raise KeyError(kind)
    c = _Ctx(screen, appearance)
    node = spec.builder(c)
    # компоненты ставятся на трети высоты экрана, не на всю ширину — с отступом 16 dp от левого края;
    # растянутые по ширине с полями (строка поиска, разделитель) сохраняют свой отступ
    full_width = node.constraint_h == "left_right" and node.x == 0
    if node.y == 0 and not full_width and kind not in ("win_nav_pane", "m3_nav_drawer"):
        dx, dy = (0 if node.x else c.d(16)), round(screen.height * 0.35, 2)
        for n, _, _ in tree.walk([node]):  # координаты абсолютные: сдвигается всё содержимое
            n.x, n.y = round(n.x + dx, 2), round(n.y + dy, 2)
    return node
