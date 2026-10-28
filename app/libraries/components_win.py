"""Компоненты Windows 11 (Fluent 2) — версия 1.31. Без Qt.

Приближение к WinUI 3: размеры в пикселях при 96 dpi, скругление 4 (элементы управления) / 8 (окна, карточки),
цвет акцента — цвет бренда проекта. Корневой фрейм несёт роль (win.checkbox, …): по ней Windows-приложение
(PySide6, 1.32) ставит настоящий виджет Qt.
"""

from __future__ import annotations

from app.core.document.model import Node
from app.libraries.components import ComponentSpec, _Ctx, _on_color

W = "windows"


def _acc(c: _Ctx) -> str:
    return c.ap.accent


def _acc_text(c: _Ctx) -> str:
    """Акцент для текста и значков: в тёмной теме — светлый тон, иначе тёмный акцент на тёмном фоне не виден."""
    return c.ap.accent if c.ap.theme == "light" else c.s["primary"]


def _label(c: _Ctx, t: str, color: str | None = None, size: float = 14, weight: int = 400, name: str = "Подпись",
           **kw) -> Node:
    return c.text(t, size, color or c.p["on"], weight, name, **kw)


def checkbox(c: _Ctx) -> Node:
    box = c.frame("Флажок", "horizontal", [c.icon(14, color=_on_color(_acc(c)), glyph="check")], w=20, h=20,
                  radius=4, fill=_acc(c), main_align="center", cross_align="center")
    return c.frame("Флажок с подписью", "horizontal", [box, _label(c, "Запомнить меня")], h=32, gap=8,
                   cross_align="center", sizing_h="hug", role="win.checkbox")


def toggle(c: _Ctx) -> Node:
    knob = c.dot("Бегунок", 12, _on_color(_acc(c)))
    track = c.frame("Дорожка", "horizontal", [knob], w=40, h=20, radius=10, fill=_acc(c), pad_l=4, pad_r=4,
                    main_align="end", cross_align="center")
    return c.frame("Переключатель", "horizontal", [_label(c, "Уведомления", sizing_h="fill"), track,
                                                   _label(c, "Вкл.", name="Состояние")],
                   w=296, h=32, gap=12, cross_align="center", role="win.toggle")


def radio(c: _Ctx) -> Node:
    items = []
    for i, t in enumerate(("Светлая", "Тёмная", "Как в системе")):
        on = i == 2
        ring = c.frame("Кольцо", "horizontal", [c.dot("Точка", 8, _on_color(_acc(c)))] if on else [], w=20, h=20,
                       radius=10, fill=_acc(c) if on else "", stroke="" if on else c.p["muted"], stroke_width=1,
                       main_align="center", cross_align="center")
        items.append(c.frame(f"Вариант «{t}»", "horizontal", [ring, _label(c, t)], h=32, gap=8, cross_align="center",
                             sizing_h="hug"))
    return c.frame("Радиокнопки", "vertical", [_label(c, "Тема", weight=600, name="Заголовок")] + items, w=240,
                   gap=2, sizing_v="hug", role="win.radio")


def slider(c: _Ctx) -> Node:
    fill = c.rect("Пройдено", 180, 4, _acc(c), 2)
    thumb = c.frame("Бегунок", "horizontal", [c.dot("Центр", 12, _acc(c))], w=20, h=20, radius=10,
                    fill=c.p["win_card"], stroke=c.p["win_stroke"], stroke_width=1, main_align="center",
                    cross_align="center")
    rest = c.rect("Осталось", 96, 4, c.p["win_stroke"], 2)
    row = c.frame("Дорожка", "horizontal", [fill, thumb, rest], h=20, cross_align="center", sizing_h="hug")
    return c.frame("Ползунок", "vertical", [_label(c, "Громкость"), row], w=296, gap=6, sizing_v="hug",
                   role="win.slider")


def combobox(c: _Ctx) -> Node:
    box = c.frame("Список", "horizontal", [_label(c, "Русский", sizing_h="fill", name="Значение"),
                                           c.icon(16, color=c.p["muted"], glyph="expand_more")],
                  h=32, pad_l=10, pad_r=10, radius=4, fill=c.p["win_ctrl"], stroke=c.p["win_stroke"], stroke_width=1,
                  cross_align="center", sizing_h="fill")
    return c.frame("Выпадающий список", "vertical", [_label(c, "Язык интерфейса", name="Заголовок"), box], w=296,
                   gap=6, sizing_v="hug", role="win.combobox")


def progress(c: _Ctx) -> Node:
    track = c.frame("Индикатор", "horizontal", [c.rect("Выполнено", 296 * 0.62, 3, _acc(c), 2)], w=296, h=3,
                    radius=2, fill=c.p["win_stroke"])
    return c.frame("Индикатор выполнения", "vertical", [_label(c, "Загрузка обновлений… 62%", c.p["muted"], 12), track],
                   w=296, gap=6, sizing_v="hug", role="win.progress")


def infobar(c: _Ctx) -> Node:
    return c.frame("Информационная панель", "horizontal",
                   [c.icon(16, color=_acc_text(c), glyph="info"),
                    _label(c, "Доступно обновление", weight=600, name="Заголовок"),
                    _label(c, "Перезапустите приложение, чтобы установить.", c.p["muted"], sizing_h="fill",
                           name="Текст"),
                    c.icon(16, "Закрыть", c.p["muted"], "close")],
                   w=560, h=48, pad_l=16, pad_r=12, gap=10, radius=4, fill=c.p["win_card"], stroke=c.p["win_stroke"],
                   stroke_width=1, cross_align="center", role="win.infobar")


def tabs(c: _Ctx) -> Node:
    items = []
    for i, t in enumerate(("Общие", "Учётная запись", "Конфиденциальность")):
        on = i == 0
        kids = [_label(c, t, weight=600 if on else 400), c.rect("Индикатор", 16, 3, _acc(c) if on else "", 2)]
        items.append(c.frame(f"Вкладка «{t}»", "vertical", kids, h=40, pad_l=12, pad_r=12, gap=4,
                             main_align="end", cross_align="center", sizing_h="hug"))
    return c.frame("Вкладки", "horizontal", items, h=40, gap=4, sizing_h="hug", role="win.tabs")


def dialog(c: _Ctx) -> Node:
    ok = c.frame("Кнопка «Удалить»", "horizontal", [_label(c, "Удалить", _on_color(_acc(c)))], h=32, pad_l=12,
                 pad_r=12, radius=4, fill=_acc(c), main_align="center", cross_align="center", sizing_h="fill")
    no = c.frame("Кнопка «Отмена»", "horizontal", [_label(c, "Отмена")], h=32, pad_l=12, pad_r=12, radius=4,
                 fill=c.p["win_ctrl"], stroke=c.p["win_stroke"], stroke_width=1, main_align="center",
                 cross_align="center", sizing_h="fill")
    body = c.frame("Содержимое", "vertical",
                   [_label(c, "Удалить файл?", size=20, weight=600, name="Заголовок"),
                    _label(c, "Файл «Отчёт.docx» будет перемещён в корзину.", c.p["muted"], sizing_h="fill",
                           name="Текст")], pad_l=24, pad_r=24, pad_t=24, pad_b=24, gap=12, sizing_h="fill",
                   sizing_v="hug")
    foot = c.frame("Кнопки", "horizontal", [ok, no], pad_l=24, pad_r=24, pad_t=24, pad_b=24, gap=8,
                   fill=c.p["win_surface"], sizing_h="fill", sizing_v="hug")
    return c.frame("Диалог", "vertical", [body, foot], w=440, radius=8, fill=c.p["win_card"], stroke=c.p["win_stroke"],
                   stroke_width=1, clip=True, elevation=3, sizing_v="hug", role="win.dialog")


def list_view(c: _Ctx) -> Node:
    rows = []
    for i, (glyph, t, d) in enumerate((("description", "Отчёт.docx", "Сегодня, 10:24"),
                                       ("image", "Обложка.png", "Вчера"), ("folder", "Проекты", "12 элементов"))):
        rows.append(c.frame(f"Строка «{t}»", "horizontal",
                            [c.icon(20, color=_acc_text(c), glyph=glyph),
                             c.frame("Текст", "vertical", [_label(c, t, name="Название"),
                                                           _label(c, d, c.p["muted"], 12, name="Детали")],
                                     gap=0, sizing_h="fill", sizing_v="hug")],
                            h=48, pad_l=12, pad_r=12, gap=12, radius=4, cross_align="center", sizing_h="fill",
                            fill=c.p["win_ctrl"] if i == 0 else ""))
    return c.frame("Список", "vertical", rows, w=360, gap=2, sizing_v="hug", role="win.list")


def menu_bar(c: _Ctx) -> Node:
    items = [c.frame(f"Меню «{t}»", "horizontal", [_label(c, t)], h=32, pad_l=10, pad_r=10, radius=4,
                     cross_align="center", sizing_h="hug") for t in ("Файл", "Правка", "Вид", "Справка")]
    return c.frame("Строка меню", "horizontal", items, x=0, y=32, w=c.screen.width, h=40, pad_l=4, gap=2,
                   cross_align="center", constraint_h="left_right", role="win.menubar")


def title_bar(c: _Ctx) -> Node:
    btns = [c.frame(f"Кнопка окна «{t}»", "horizontal", [c.icon(14, color=c.p["on"], glyph=g)], w=46, h=32,
                    main_align="center", cross_align="center") for t, g in (("Свернуть", "remove"),
                                                                           ("Развернуть", "crop_square"),
                                                                           ("Закрыть", "close"))]
    return c.frame("Заголовок окна", "horizontal",
                   [c.icon(16, color=_acc_text(c), glyph="apps"), _label(c, "Моё приложение", c.p["on"], 12, name="Название",
                                                                    sizing_h="fill")] + btns,
                   x=0, y=0, w=c.screen.width, h=32, pad_l=12, gap=10, cross_align="center",
                   fill=c.p["win_surface"], constraint_h="left_right", role="win.titlebar")


def search_box(c: _Ctx) -> Node:
    return c.frame("Поиск", "horizontal", [_label(c, "Поиск", c.p["muted"], sizing_h="fill", name="Плейсхолдер"),
                                           c.icon(16, color=c.p["muted"], glyph="search")],
                   w=320, h=32, pad_l=10, pad_r=10, radius=4, fill=c.p["win_ctrl"], stroke=c.p["win_stroke"],
                   stroke_width=1, cross_align="center", role="win.search")


def expander(c: _Ctx) -> Node:
    head = c.frame("Шапка", "horizontal", [c.icon(20, color=c.p["on"], glyph="tune"),
                                          c.frame("Текст", "vertical", [_label(c, "Дополнительные параметры",
                                                                               name="Заголовок"),
                                                                        _label(c, "Прокси, порты, журнал", c.p["muted"],
                                                                               12, name="Описание")],
                                                  gap=0, sizing_h="fill", sizing_v="hug"),
                                          c.icon(16, color=c.p["muted"], glyph="expand_more")],
                   h=64, pad_l=16, pad_r=16, gap=16, cross_align="center", sizing_h="fill")
    return c.frame("Раскрывающийся блок", "vertical", [head], w=560, radius=4, fill=c.p["win_card"],
                   stroke=c.p["win_stroke"], stroke_width=1, sizing_v="hug", role="win.expander")


def settings_card(c: _Ctx) -> Node:
    knob = c.dot("Бегунок", 12, _on_color(_acc(c)))
    track = c.frame("Дорожка", "horizontal", [knob], w=40, h=20, radius=10, fill=_acc(c), pad_l=4, pad_r=4,
                    main_align="end", cross_align="center")
    return c.frame("Карточка параметра", "horizontal",
                   [c.icon(20, color=c.p["on"], glyph="dark_mode"),
                    c.frame("Текст", "vertical", [_label(c, "Тёмный режим", name="Заголовок"),
                                                  _label(c, "Тёмные цвета окон и приложений", c.p["muted"], 12,
                                                         name="Описание")],
                            gap=0, sizing_h="fill", sizing_v="hug"),
                    _label(c, "Вкл.", name="Состояние"), track],
                   w=560, h=64, pad_l=16, pad_r=16, gap=16, radius=4, fill=c.p["win_card"], stroke=c.p["win_stroke"],
                   stroke_width=1, cross_align="center", role="win.settings_card")


def hyperlink(c: _Ctx) -> Node:
    t = _label(c, "Подробнее о лицензии", _acc_text(c), name="Ссылка")
    t.decoration = "underline"
    return c.frame("Ссылка", "horizontal", [t], h=24, cross_align="center", sizing_h="hug", role="win.link")


SPECS: tuple[ComponentSpec, ...] = (
    ComponentSpec("win_checkbox", "Флажок", W, "Выбор", checkbox),
    ComponentSpec("win_toggle", "Переключатель", W, "Выбор", toggle),
    ComponentSpec("win_radio", "Радиокнопки", W, "Выбор", radio),
    ComponentSpec("win_slider", "Ползунок", W, "Выбор", slider),
    ComponentSpec("win_combobox", "Выпадающий список", W, "Поля", combobox),
    ComponentSpec("win_search", "Поиск", W, "Поля", search_box),
    ComponentSpec("win_link", "Ссылка", W, "Кнопки", hyperlink),
    ComponentSpec("win_progress", "Индикатор выполнения", W, "Состояние", progress),
    ComponentSpec("win_infobar", "Информационная панель", W, "Состояние", infobar),
    ComponentSpec("win_dialog", "Диалог", W, "Окна", dialog),
    ComponentSpec("win_tabs", "Вкладки", W, "Навигация", tabs),
    ComponentSpec("win_menubar", "Строка меню", W, "Навигация", menu_bar),
    ComponentSpec("win_titlebar", "Заголовок окна", W, "Навигация", title_bar),
    ComponentSpec("win_list", "Список", W, "Списки", list_view),
    ComponentSpec("win_expander", "Раскрывающийся блок", W, "Карточки", expander),
    ComponentSpec("win_settings_card", "Карточка параметра", W, "Карточки", settings_card),
)
