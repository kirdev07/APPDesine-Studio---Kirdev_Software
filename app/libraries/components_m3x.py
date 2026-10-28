"""Варианты компонентов Material 3 (версия 1.8): приподнятые кнопки и карточки, размеры FAB, кнопки-значки
всех видов, группы и раздельные кнопки (Material 3 Expressive), меню FAB, заполненное поле, чипы ввода и
подсказки, карусель, верхние панели «по центру / средняя / большая», нижняя панель приложения, боковая
навигация, вкладки со значками, индикатор загрузки, выбор даты и времени, боковой лист, списки с переключателем.
Без Qt. Цвета — роли схемы Material 3 по цвету оформления; тени — уровни возвышения (эффекты 1.3).
"""

from __future__ import annotations

from app.core.document import tree
from app.core.document.model import Node
from app.libraries.components import ComponentSpec, _button, _Ctx

_A = "android"


def _move(n: Node, x: float, y: float) -> Node:
    """Сдвинуть узел со всем содержимым так, чтобы левый верхний угол встал в (x, y)."""
    dx, dy = x - n.x, y - n.y
    for d, _, _ in tree.walk([n]):
        d.x, d.y = round(d.x + dx, 2), round(d.y + dy, 2)
    return n


# ---------------- кнопки ----------------

def button_elevated(c: _Ctx) -> Node:
    b = _button(c, "Кнопка (приподнятая)", "m3.button_elevated", "Подробнее", c.s["primary"],
                fill=c.s["surfaceContainerLow"])
    b.elevation = 1
    return b


def _fab(c: _Ctx, name: str, role: str, side: float, radius: float, icon: float, kind: str = "primaryContainer"):
    on = "on" + kind[0].upper() + kind[1:]
    f = c.frame(name, "horizontal", [c.icon(icon, color=c.s[on], glyph="add")], w=side, h=side, radius=radius,
                fill=c.s[kind], main_align="center", cross_align="center", role=role)
    f.elevation = 3
    return f


def fab_small(c: _Ctx) -> Node:
    return _fab(c, "Плавающая кнопка (маленькая)", "m3.fab_small", 40, 12, 24)


def fab_large(c: _Ctx) -> Node:
    return _fab(c, "Плавающая кнопка (большая)", "m3.fab_large", 96, 28, 36)


def fab_secondary(c: _Ctx) -> Node:
    return _fab(c, "Плавающая кнопка (вторичная)", "m3.fab", 56, 16, 24, "secondaryContainer")


def _icon_btn(c: _Ctx, name: str, role: str, fill: str, fg: str, stroke: str = "") -> Node:
    return c.frame(name, "horizontal", [c.icon(24, color=fg, glyph="favorite")], w=40, h=40, radius=20, fill=fill,
                   stroke=stroke, stroke_width=1 if stroke else 0, main_align="center", cross_align="center",
                   role=role)


def icon_button_filled(c: _Ctx) -> Node:
    return _icon_btn(c, "Кнопка-значок (заливка)", "m3.icon_button_filled", c.s["primary"], c.s["onPrimary"])


def icon_button_tonal(c: _Ctx) -> Node:
    return _icon_btn(c, "Кнопка-значок (тональная)", "m3.icon_button_tonal", c.s["secondaryContainer"],
                     c.s["onSecondaryContainer"])


def icon_button_outlined(c: _Ctx) -> Node:
    return _icon_btn(c, "Кнопка-значок (контур)", "m3.icon_button_outlined", "", c.s["onSurfaceVariant"],
                     c.s["outline"])


def button_group(c: _Ctx) -> Node:
    """Группа кнопок Material 3 Expressive: соседние кнопки, выбранная — с заливкой и скруглением сильнее."""
    kids = []
    for i, (glyph, t) in enumerate((("format_bold", "Ж"), ("format_italic", "К"), ("format_underlined", "Ч"))):
        sel = i == 0
        kids.append(c.frame(f"Кнопка «{t}»", "horizontal",
                            [c.text(t, 16, c.s["onPrimary"] if sel else c.s["onSecondaryContainer"], 600, "Подпись")],
                            w=56, h=40, radius=20 if sel else 8,
                            fill=c.s["primary"] if sel else c.s["secondaryContainer"], main_align="center",
                            cross_align="center"))
    return c.frame("Группа кнопок", "horizontal", kids, gap=2, sizing_h="hug", sizing_v="hug",
                   role="m3.button_group")


def split_button(c: _Ctx) -> Node:
    """Раздельная кнопка (Material 3 Expressive): основное действие и стрелка выбора."""
    main = c.frame("Действие", "horizontal", [c.icon(18, color=c.s["onPrimary"], glyph="edit"),
                                              c.label("Изменить", c.s["onPrimary"])],
                   h=40, pad_l=16, pad_r=12, gap=8, radius=20, fill=c.s["primary"], cross_align="center",
                   sizing_h="hug")
    main.radius = c.d(20)
    arrow = c.frame("Выбор", "horizontal", [c.icon(20, color=c.s["onPrimary"], glyph="expand_more")], w=40, h=40,
                    radius=20, fill=c.s["primary"], main_align="center", cross_align="center")
    return c.frame("Раздельная кнопка", "horizontal", [main, arrow], gap=2, sizing_h="hug", sizing_v="hug",
                   role="m3.split_button")


def fab_menu(c: _Ctx) -> Node:
    """Меню плавающей кнопки (Material 3 Expressive): пункты над закрывающей кнопкой."""
    items = []
    for glyph, t in (("photo_camera", "Камера"), ("image", "Галерея"), ("mail", "Письмо")):
        items.append(c.frame(f"Пункт «{t}»", "horizontal", [c.icon(20, color=c.s["onPrimaryContainer"], glyph=glyph),
                                                           c.label(t, c.s["onPrimaryContainer"])],
                             h=48, pad_l=16, pad_r=20, gap=12, radius=24, fill=c.s["primaryContainer"],
                             cross_align="center", sizing_h="hug"))
    close = c.frame("Закрыть", "horizontal", [c.icon(24, color=c.s["onPrimary"], glyph="close")], w=56, h=56,
                    radius=28, fill=c.s["primary"], main_align="center", cross_align="center")
    close.elevation = 3
    return c.frame("Меню плавающей кнопки", "vertical", items + [close], gap=8, cross_align="end", sizing_h="hug",
                   sizing_v="hug", role="m3.fab_menu")


# ---------------- поля и выбор ----------------

def text_field_filled(c: _Ctx) -> Node:
    box = c.frame("Поле", "vertical",
                  [c.text("Имя", 12, c.s["primary"], name="Метка"),
                   c.text("Анна", 16, c.s["onSurface"], name="Значение", sizing_h="fill")],
                  h=56, pad_l=16, pad_r=16, pad_t=8, pad_b=8, gap=2, radius=4, fill=c.s["surfaceContainerHighest"],
                  main_align="center", sizing_h="fill")
    line = c.rect("Линия", 10, 2, c.s["primary"], sizing_h="fill")
    hint = c.text("Как к вам обращаться", 12, c.s["onSurfaceVariant"], name="Подсказка", sizing_h="fill")
    return c.frame("Текстовое поле (заполненное)", "vertical", [box, line, hint], w=320, gap=0, sizing_v="hug",
                   role="m3.text_field_filled")


def input_chip(c: _Ctx) -> Node:
    av = c.frame("Аватар", "horizontal", [c.text("А", 12, c.s["onPrimaryContainer"], 600, "Буква")], w=24, h=24,
                 radius=12, fill=c.s["primaryContainer"], main_align="center", cross_align="center")
    return c.frame("Чип ввода", "horizontal", [av, c.label("Анна", c.s["onSurfaceVariant"]),
                                                c.icon(18, color=c.s["onSurfaceVariant"], glyph="close")],
                   h=32, pad_l=4, pad_r=8, gap=8, radius=16, stroke=c.s["outline"], stroke_width=1,
                   cross_align="center", sizing_h="hug", role="m3.chip_input")


def suggestion_chip(c: _Ctx) -> Node:
    return c.frame("Чип подсказки", "horizontal", [c.label("Где ближайшее кафе?", c.s["onSurfaceVariant"])],
                   h=32, pad_l=16, pad_r=16, radius=8, stroke=c.s["outline"], stroke_width=1, cross_align="center",
                   sizing_h="hug", role="m3.chip_suggestion")


def list_switch(c: _Ctx) -> Node:
    sw = c.frame("Дорожка", "horizontal", [c.dot("Бегунок", 24, c.s["onPrimary"])], w=52, h=32, radius=16, pad_l=4,
                 pad_r=4, fill=c.s["primary"], main_align="end", cross_align="center")
    texts = c.frame("Текст", "vertical", [c.text("Wi-Fi", 16, c.s["onSurface"], name="Заголовок", sizing_h="fill"),
                                          c.text("Дом_5G", 14, c.s["onSurfaceVariant"], name="Подпись",
                                                 sizing_h="fill")],
                    gap=2, sizing_h="fill", sizing_v="hug")
    return c.frame("Строка с переключателем", "horizontal",
                   [c.icon(24, color=c.s["onSurfaceVariant"], glyph="wifi"), texts, sw],
                   x=0, w=c.width_dp, min_h=72, pad_l=16, pad_r=24, pad_t=8, pad_b=8, gap=16, cross_align="center",
                   sizing_v="hug", constraint_h="left_right", role="m3.list_switch")


def list_three_line(c: _Ctx) -> Node:
    texts = c.frame("Текст", "vertical",
                    [c.text("Встреча с командой", 16, c.s["onSurface"], name="Заголовок", sizing_h="fill"),
                     c.text("Завтра, 10:00 · Переговорная 3. Обсудим макеты главного экрана и план выпуска.", 14,
                            c.s["onSurfaceVariant"], name="Подпись", sizing_h="fill")],
                    gap=2, sizing_h="fill", sizing_v="hug")
    pic = c.frame("Картинка", "horizontal", [c.icon(28, color=c.s["onSurfaceVariant"], glyph="image")], w=56, h=56,
                  radius=8, fill=c.s["surfaceContainerHighest"], main_align="center", cross_align="center")
    return c.frame("Строка в три линии", "horizontal", [pic, texts, c.text("10:00", 12, c.s["onSurfaceVariant"],
                                                                         name="Время")],
                   x=0, w=c.width_dp, pad_l=16, pad_r=24, pad_t=12, pad_b=12, gap=16, cross_align="start",
                   sizing_v="hug", constraint_h="left_right", role="m3.list_three_line")


# ---------------- карточки ----------------

def card_elevated(c: _Ctx) -> Node:
    from app.libraries.components import m3_card
    card = m3_card(c)
    card.name, card.role, card.fill, card.elevation = "Карточка (приподнятая)", "m3.card_elevated", \
        c.s["surfaceContainerLow"], 1
    return card


def carousel(c: _Ctx) -> Node:
    items = []
    for i, (t, w) in enumerate((("Горы", 180), ("Море", 100), ("Лес", 48))):
        pic = c.frame(f"Слайд «{t}»", "vertical",
                      [c.rect("Отступ", 10, 10, "", sizing_h="fill", sizing_v="fill"),
                       c.text(t, 16, c.s["onPrimaryContainer"], 500, "Подпись")] if w > 100 else [],
                      w=w, h=200, pad_l=16, pad_b=16, radius=28, fill=c.s["primaryContainer"] if i == 0 else
                      c.s["secondaryContainer"] if i == 1 else c.s["tertiaryContainer"], sizing_v="fixed")
        items.append(pic)
    return c.frame("Карусель", "horizontal", items, x=0, w=c.width_dp, h=200, pad_l=16, pad_r=16, gap=8,
                   constraint_h="left_right", scroll="horizontal", role="m3.carousel")


# ---------------- навигация ----------------

def _top_bar(c: _Ctx, name: str, role: str, title_size: float, h: float, centered: bool = False,
             two_rows: bool = False) -> Node:
    on = c.s["onSurface"]
    menu = c.icon(24, "Назад", on, "arrow_back")
    act = c.icon(24, "Действие", c.s["onSurfaceVariant"], "more_vert")
    title = c.text("Заголовок экрана", title_size, on, name="Заголовок", sizing_h="fill")
    if centered:
        title.align = "center"
    if two_rows:
        row = c.frame("Значки", "horizontal", [menu, c.rect("Пусто", 10, 10, "", sizing_h="fill"), act], h=56,
                      cross_align="center", sizing_h="fill")
        return c.frame(name, "vertical", [row, title], x=0, y=0, w=c.width_dp, h=h, pad_l=16, pad_r=16, pad_b=16,
                       fill=c.s["surface"], main_align="space_between", constraint_h="left_right",
                       constraint_v="top", role=role)
    return c.frame(name, "horizontal", [menu, title, act], x=0, y=0, w=c.width_dp, h=h, pad_l=16, pad_r=16, gap=16,
                   cross_align="center", fill=c.s["surface"], constraint_h="left_right", constraint_v="top",
                   role=role)


def top_bar_center(c: _Ctx) -> Node:
    return _top_bar(c, "Верхняя панель (по центру)", "m3.top_app_bar_center", 22, 64, centered=True)


def top_bar_medium(c: _Ctx) -> Node:
    return _top_bar(c, "Верхняя панель (средняя)", "m3.top_app_bar_medium", 24, 128, two_rows=True)


def top_bar_large(c: _Ctx) -> Node:
    return _top_bar(c, "Верхняя панель (большая)", "m3.top_app_bar_large", 32, 152, two_rows=True)


def bottom_app_bar(c: _Ctx) -> Node:
    icons = [c.icon(24, color=c.s["onSurfaceVariant"], glyph=g) for g in ("check", "edit", "mic", "image")]
    row = c.frame("Действия", "horizontal", icons, gap=24, cross_align="center", sizing_h="fill", sizing_v="hug")
    fab = _fab(c, "Плавающая кнопка", "m3.fab", 56, 16, 24)
    fab.elevation = 0
    h = 80
    return c.frame("Нижняя панель приложения", "horizontal", [row, fab], x=0, y=c.screen.height - c.d(h),
                   w=c.width_dp, h=h, pad_l=16, pad_r=16, gap=16, cross_align="center",
                   fill=c.s["surfaceContainer"], constraint_h="left_right", constraint_v="bottom",
                   role="m3.bottom_app_bar")


def nav_rail(c: _Ctx) -> Node:
    items = []
    for i, (glyph, t) in enumerate((("home", "Главная"), ("search", "Поиск"), ("notifications", "События"),
                                    ("person", "Профиль"))):
        on = i == 0
        pill = c.frame("Индикатор", "horizontal", [c.icon(24, color=c.s["onSecondaryContainer"] if on else
                                                          c.s["onSurfaceVariant"], glyph=glyph)],
                       w=56, h=32, radius=16, fill=c.s["secondaryContainer"] if on else "", main_align="center",
                       cross_align="center")
        items.append(c.frame(f"Пункт «{t}»", "vertical", [pill, c.text(t, 12, c.s["onSurface"] if on else
                                                                        c.s["onSurfaceVariant"], 500, "Подпись")],
                             gap=4, cross_align="center", sizing_h="fill", sizing_v="hug"))
    fab = _fab(c, "Плавающая кнопка", "m3.fab", 56, 16, 24)
    fab.elevation = 0
    return c.frame("Боковая навигация", "vertical", [fab] + items, x=0, y=0, w=80, h=c.screen.height / c.k,
                   pad_t=16, gap=12, cross_align="center", fill=c.s["surface"], constraint_v="top_bottom",
                   role="m3.nav_rail")


def tabs_icons(c: _Ctx) -> Node:
    tabs = []
    for i, (glyph, t) in enumerate((("flight", "Перелёты"), ("hotel", "Отели"), ("directions_car", "Авто"))):
        sel = i == 0
        col = c.s["primary"] if sel else c.s["onSurfaceVariant"]
        tabs.append(c.frame(f"Вкладка «{t}»", "vertical",
                            [c.icon(24, color=col, glyph=glyph), c.label(t, col),
                             c.rect("Индикатор", 10, 3, c.s["primary"] if sel else "", 3, sizing_h="fill")],
                            gap=4, main_align="end", cross_align="center", sizing_h="fill", sizing_v="fill"))
    return c.frame("Вкладки со значками", "horizontal", tabs, x=0, y=c.d(64), w=c.width_dp, h=72,
                   fill=c.s["surface"], cross_align="stretch", constraint_h="left_right", constraint_v="top",
                   role="m3.tabs")


# ---------------- обратная связь и окна ----------------

def loading_indicator(c: _Ctx) -> Node:
    """Индикатор загрузки Material 3 Expressive: меняющая форму фигура в контейнере."""
    shape = Node(type="vector", name="Фигура", w=c.d(28), h=c.d(28), fill=c.s["primary"], vb_w=24, vb_h=24,
                 path=_flower())
    return c.frame("Индикатор загрузки", "horizontal", [shape], w=48, h=48, radius=24,
                   fill=c.s["primaryContainer"], main_align="center", cross_align="center",
                   role="m3.loading_indicator")


def _flower() -> str:
    import math
    from app.core.document.pathdata import normalize
    pts = []
    for i in range(64):  # «цветок» из 8 лепестков — одна из форм Material 3 Expressive
        a = 2 * math.pi * i / 64
        r = 9 + 2.6 * math.cos(8 * a)
        pts.append((12 + r * math.cos(a), 12 + r * math.sin(a)))
    return normalize("M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in pts) + " Z")


def date_picker(c: _Ctx) -> Node:
    head = c.frame("Заголовок", "horizontal", [c.text("Ноябрь 2026", 16, c.s["onSurface"], 500, "Месяц",
                                                      sizing_h="fill"),
                                               c.icon(24, color=c.s["onSurfaceVariant"], glyph="chevron_left"),
                                               c.icon(24, color=c.s["onSurfaceVariant"], glyph="chevron_right")],
                   gap=16, cross_align="center", sizing_h="fill", sizing_v="hug")
    week = c.frame("Дни недели", "horizontal", [c.text(d, 12, c.s["onSurfaceVariant"], 500, "День") for d in
                                               ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")],
                   main_align="space_between", sizing_h="fill", sizing_v="hug")
    rows = []
    day = -5
    for r in range(5):
        cells = []
        for col in range(7):
            day += 1
            sel = day == 12
            txt = str(day) if 1 <= day <= 30 else ""
            cells.append(c.frame(f"День {txt}", "horizontal", [c.text(txt or " ", 14,
                                                                     c.s["onPrimary"] if sel else c.s["onSurface"],
                                                                     500 if sel else 400, "Число")],
                                 w=36, h=36, radius=18, fill=c.s["primary"] if sel else "", main_align="center",
                                 cross_align="center"))
        rows.append(c.frame(f"Неделя {r + 1}", "horizontal", cells, main_align="space_between", sizing_h="fill",
                            sizing_v="hug"))
    return c.frame("Выбор даты", "vertical", [head, week] + rows, w=328, pad_t=16, pad_r=12, pad_b=16, pad_l=12,
                   gap=6, radius=16, fill=c.s["surfaceContainerHigh"], sizing_v="hug", role="m3.date_picker")


def time_picker(c: _Ctx) -> Node:
    def box(t, sel):
        return c.frame(f"Поле «{t}»", "horizontal", [c.text(t, 45, c.s["onPrimaryContainer"] if sel else c.s["onSurface"],
                                                            400, "Цифры")],
                       w=96, h=80, radius=8, fill=c.s["primaryContainer"] if sel else c.s["surfaceContainerHighest"],
                       main_align="center", cross_align="center")
    row = c.frame("Время", "horizontal", [box("10", True), c.text(":", 45, c.s["onSurface"], name="Двоеточие"),
                                         box("30", False)],
                  gap=8, cross_align="center", sizing_h="hug", sizing_v="hug")
    return c.frame("Выбор времени", "vertical", [c.text("Укажите время", 12, c.s["onSurfaceVariant"], 500,
                                                         "Заголовок"), row],
                   pad_t=20, pad_r=20, pad_b=20, pad_l=20, gap=16, radius=28, fill=c.s["surfaceContainerHigh"],
                   sizing_h="hug", sizing_v="hug", role="m3.time_picker")


def side_sheet(c: _Ctx) -> Node:
    head = c.frame("Заголовок", "horizontal", [c.text("Фильтры", 22, c.s["onSurface"], name="Заголовок",
                                                      sizing_h="fill"),
                                               c.icon(24, color=c.s["onSurfaceVariant"], glyph="close")],
                   h=56, cross_align="center", sizing_h="fill")
    from app.libraries.components import m3_chip_filter
    chip = m3_chip_filter(c)
    w = 280
    sheet = c.frame("Боковой лист", "vertical", [head, c.text("Цена, бренд и наличие", 14, c.s["onSurfaceVariant"],
                                                             name="Описание", sizing_h="fill"), chip],
                    x=c.screen.width - c.d(w), y=0, w=w, h=c.screen.height / c.k, pad_l=24, pad_r=24, pad_t=12,
                    gap=12, radius=16, fill=c.s["surfaceContainerLow"], constraint_h="right",
                    constraint_v="top_bottom", role="m3.side_sheet")
    return sheet


SPECS: tuple[ComponentSpec, ...] = (
    ComponentSpec("m3_button_elevated", "Кнопка (приподнятая)", _A, "Кнопки", button_elevated),
    ComponentSpec("m3_fab_small", "Плавающая кнопка (маленькая)", _A, "Кнопки", fab_small),
    ComponentSpec("m3_fab_large", "Плавающая кнопка (большая)", _A, "Кнопки", fab_large),
    ComponentSpec("m3_fab_secondary", "Плавающая кнопка (вторичная)", _A, "Кнопки", fab_secondary),
    ComponentSpec("m3_icon_button_filled", "Кнопка-значок (заливка)", _A, "Кнопки", icon_button_filled),
    ComponentSpec("m3_icon_button_tonal", "Кнопка-значок (тональная)", _A, "Кнопки", icon_button_tonal),
    ComponentSpec("m3_icon_button_outlined", "Кнопка-значок (контур)", _A, "Кнопки", icon_button_outlined),
    ComponentSpec("m3_button_group", "Группа кнопок", _A, "Кнопки", button_group),
    ComponentSpec("m3_split_button", "Раздельная кнопка", _A, "Кнопки", split_button),
    ComponentSpec("m3_fab_menu", "Меню плавающей кнопки", _A, "Кнопки", fab_menu),
    ComponentSpec("m3_text_field_filled", "Текстовое поле (заполненное)", _A, "Поля", text_field_filled),
    ComponentSpec("m3_chip_input", "Чип ввода", _A, "Выбор", input_chip),
    ComponentSpec("m3_chip_suggestion", "Чип подсказки", _A, "Выбор", suggestion_chip),
    ComponentSpec("m3_list_switch", "Строка с переключателем", _A, "Карточки", list_switch),
    ComponentSpec("m3_list_three_line", "Строка в три линии", _A, "Карточки", list_three_line),
    ComponentSpec("m3_card_elevated", "Карточка (приподнятая)", _A, "Карточки", card_elevated),
    ComponentSpec("m3_carousel", "Карусель", _A, "Карточки", carousel),
    ComponentSpec("m3_top_bar_center", "Верхняя панель (по центру)", _A, "Навигация", top_bar_center),
    ComponentSpec("m3_top_bar_medium", "Верхняя панель (средняя)", _A, "Навигация", top_bar_medium),
    ComponentSpec("m3_top_bar_large", "Верхняя панель (большая)", _A, "Навигация", top_bar_large),
    ComponentSpec("m3_bottom_app_bar", "Нижняя панель приложения", _A, "Навигация", bottom_app_bar),
    ComponentSpec("m3_nav_rail", "Боковая навигация (планшет)", _A, "Навигация", nav_rail),
    ComponentSpec("m3_tabs_icons", "Вкладки со значками", _A, "Навигация", tabs_icons),
    ComponentSpec("m3_loading_indicator", "Индикатор загрузки (Expressive)", _A, "Обратная связь", loading_indicator),
    ComponentSpec("m3_date_picker", "Выбор даты", _A, "Окна", date_picker),
    ComponentSpec("m3_time_picker", "Выбор времени", _A, "Окна", time_picker),
    ComponentSpec("m3_side_sheet", "Боковой лист", _A, "Окна", side_sheet),
)
