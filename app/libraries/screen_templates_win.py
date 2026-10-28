"""Готовые экраны Windows 11 (версия 1.31): настройки, панель мониторинга, файлы, вход, редактор документа. Без Qt.

Окно 1280×800 (или размер текущего экрана Windows): заголовок окна, панель навигации слева, содержимое справа;
компоненты Fluent (app/libraries/components_win.py) — в Windows-приложении (1.32) это настоящие виджеты Qt.
"""

from __future__ import annotations

from app.core.document import tree
from app.core.document.model import Node, Screen
from app.libraries import components
from app.libraries.components import _Ctx


def _b(s, ap, kind: str) -> Node:
    return components.build(kind, s, ap)


def _place(n: Node, x: float, y: float) -> Node:
    dx, dy = x - n.x, y - n.y
    for d, _, _ in tree.walk([n]):
        d.x, d.y = round(d.x + dx, 2), round(d.y + dy, 2)
    return n


def _set(node: Node, name: str, text: str, nth: int = 0) -> None:
    found = [d for d in tree.descendants(node) if d.type == "text" and d.name == name]
    if len(found) > nth:
        found[nth].text = text


def _nav(s, ap, active: int, labels: list[str]) -> Node:
    pane = _b(s, ap, "win_nav_pane")
    items = [c for c in pane.children if c.is_frame]
    c = _Ctx(s, ap)
    acc = c.ap.accent if c.ap.theme == "light" else c.s["primary"]
    for i, (it, t) in enumerate(zip(items, labels)):
        _set(it, "Подпись", t)
        on = i == active
        it.fill = c.p["win_select"] if on else ""
        for d in it.children:
            if d.type == "text":
                d.font_weight = 600 if on else 400
            elif d.type == "rect" and d.name == "Метка":
                d.fill = acc if on else ""
    pane.y, pane.h = 32, s.height - 32
    for d, _, _ in tree.walk(pane.children):
        d.y += 32
    return pane


def _content(c: _Ctx, s: Screen, kids: list[Node], left: float = 280) -> Node:
    return c.frame("Содержимое", "vertical", kids, x=left, y=32, w=s.width - left, h=s.height - 32, pad_l=32,
                   pad_r=32, pad_t=24, pad_b=24, gap=12, fill=c.p["win_surface"], constraint_h="left_right",
                   constraint_v="top_bottom", cross_align="stretch", scroll="vertical", clip=True)


def _title(c: _Ctx, t: str) -> Node:
    return c.text(t, 28, c.p["on"], 600, "Заголовок страницы", sizing_h="fill")


def settings(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    cards = []
    for glyph, t, d, state in (("dark_mode", "Тёмный режим", "Тёмные цвета окон и приложений", "Вкл."),
                               ("notifications", "Уведомления", "Звук, баннеры и центр уведомлений", "Вкл."),
                               ("energy_savings_leaf", "Экономия заряда", "Ограничить фоновые задачи", "Выкл.")):
        card = _b(s, ap, "win_settings_card")
        card.sizing_h = "fill"
        _set(card, "Заголовок", t)
        _set(card, "Описание", d)
        _set(card, "Состояние", state)
        from app.libraries import symbols
        v = next(x for x in tree.descendants(card) if x.type == "vector")
        if symbols.path(glyph):  # значок параметра (контур и его система координат)
            v.path, v.vb_w, v.vb_h, v.fill_rule = symbols.path(glyph), symbols.VIEWBOX, symbols.VIEWBOX, "nonzero"
        if state == "Выкл.":  # выключенный переключатель: пустая дорожка с рамкой, бегунок слева
            track = next(x for x in tree.descendants(card) if x.is_frame and x.name == "Дорожка")
            track.fill, track.stroke, track.stroke_width, track.main_align = "", c.p["muted"], 1, "start"
            track.children[0].fill = c.p["muted"]
        cards.append(card)
    exp = _b(s, ap, "win_expander")
    exp.sizing_h = "fill"
    kids = [_title(c, "Система"), c.text("Экран, звук, уведомления и питание", 14, c.p["muted"], name="Описание")]
    kids += cards + [exp]
    return [_b(s, ap, "win_titlebar"), _nav(s, ap, 1, ["Главная", "Система", "Сеть", "Персонализация", "Обновления"]),
            _content(c, s, kids)]


def dashboard(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)

    def tile(t, v, d):
        return c.frame(f"Показатель «{t}»", "vertical",
                       [c.text(t, 14, c.p["muted"], name="Подпись"), c.text(v, 28, c.p["on"], 600, "Значение"),
                        c.text(d, 12, c.p["muted"], name="Изменение")],
                       pad_l=16, pad_r=16, pad_t=16, pad_b=16, gap=4, radius=8, fill=c.p["win_card"],
                       stroke=c.p["win_stroke"], stroke_width=1, sizing_h="fill", sizing_v="hug")
    tiles = c.frame("Показатели", "horizontal", [tile("Процессор", "23%", "4 ядра · 3,2 ГГц"),
                                                 tile("Память", "9,4 ГБ", "из 16 ГБ"),
                                                 tile("Диск", "312 ГБ", "свободно из 512"),
                                                 tile("Сеть", "48 Мбит/с", "Wi-Fi 6")],
                    gap=12, sizing_h="fill", sizing_v="hug")
    kids = [_title(c, "Мониторинг"), tiles]
    info = _b(s, ap, "win_infobar")
    info.sizing_h = "fill"
    kids.append(info)
    lst = _b(s, ap, "win_list")
    lst.sizing_h = "fill"
    kids += [c.text("Последние события", 20, c.p["on"], 600, "Раздел"), lst]
    return [_b(s, ap, "win_titlebar"), _nav(s, ap, 2, ["Главная", "Система", "Мониторинг", "Устройства", "Настройки"]),
            _content(c, s, kids)]


def files(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    bar = _b(s, ap, "win_command_bar")
    for i, t in enumerate(("Создать", "Копировать", "Удалить")):
        _set(bar, "Подпись", t, i)
    search = _b(s, ap, "win_search")
    head = c.frame("Панель", "horizontal", [bar, c.rect("Отступ", 10, 10, "", sizing_h="fill"), search], gap=12,
                   cross_align="center", sizing_h="fill", sizing_v="hug")
    lst = _b(s, ap, "win_list")
    lst.sizing_h = "fill"
    tabs = _b(s, ap, "win_tabs")
    for i, t in enumerate(("Недавние", "Избранное", "Общие")):
        _set(tabs, "Подпись", t, i)
    return [_b(s, ap, "win_titlebar"), _nav(s, ap, 0, ["Главная", "Документы", "Загрузки", "Изображения", "Музыка"]),
            _content(c, s, [_title(c, "Главная"), head, tabs, lst])]


def login(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    email, pwd = _b(s, ap, "win_textbox"), _b(s, ap, "win_textbox")
    _set(email, "Заголовок", "Электронная почта")
    _set(email, "Плейсхолдер", "name@example.com")
    _set(pwd, "Заголовок", "Пароль")
    _set(pwd, "Плейсхолдер", "••••••••")
    for f in (email, pwd):
        f.sizing_h = "fill"
    btn = _b(s, ap, "win_button_accent")
    _set(btn, "Подпись", "Войти")
    btn.sizing_h = "fill"
    remember = _b(s, ap, "win_checkbox")
    card = c.frame("Карточка входа", "vertical",
                   [c.icon(40, color=c.ap.accent if c.ap.theme == "light" else c.s["primary"], glyph="account_circle"),
                    c.text("Вход в учётную запись", 24, c.p["on"], 600, "Заголовок", sizing_h="fill"),
                    email, pwd, remember, btn, _b(s, ap, "win_link")],
                   w=400, pad_l=32, pad_r=32, pad_t=32, pad_b=32, gap=14, radius=8, fill=c.p["win_card"],
                   stroke=c.p["win_stroke"], stroke_width=1, elevation=2, sizing_v="hug")
    _place(card, (s.width - card.w) / 2, max(64.0, s.height * 0.16))
    card.constraint_h, card.constraint_v = "center", "center"
    return [_b(s, ap, "win_titlebar"), card]


def editor(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    page = c.frame("Страница", "vertical",
                   [c.text("Отчёт за октябрь", 28, "#1B1B1B", 600, "Заголовок", sizing_h="fill"),
                    c.text("Продажи выросли на 12% по сравнению с сентябрём. Основной рост дали новые клиенты "
                           "из приложения: заказы через телефон заняли 64% выручки.", 15, "#1B1B1B", name="Абзац",
                           sizing_h="fill"),
                    c.text("Планы на ноябрь", 20, "#1B1B1B", 600, "Подзаголовок", sizing_h="fill"),
                    c.text("Запустить программу лояльности и обновить каталог к зимнему сезону.", 15, "#1B1B1B",
                           name="Абзац", sizing_h="fill")],
                   w=720, pad_l=64, pad_r=64, pad_t=56, pad_b=56, gap=14, fill="#FFFFFF", stroke=c.p["win_stroke"],
                   stroke_width=1, elevation=1, sizing_v="hug")
    _place(page, (s.width - page.w) / 2, 32 + 40 + 32)
    page.constraint_h = "center"
    back = c.frame("Фон документа", "vertical", [], x=0, y=72, w=s.width, h=s.height - 72, fill=c.p["win_surface"],
                   constraint_h="left_right", constraint_v="top_bottom")
    return [_b(s, ap, "win_titlebar"), _b(s, ap, "win_menubar"), back, page]


TEMPLATES = {
    "win_settings": ("Настройки (Windows)", settings), "win_dashboard": ("Мониторинг (Windows)", dashboard),
    "win_files": ("Файлы (Windows)", files), "win_login": ("Вход (Windows)", login),
    "win_editor": ("Редактор документа (Windows)", editor),
}


def build(key: str, like: Screen, appearance) -> Screen:
    title, fn = TEMPLATES[key]
    s = Screen(name=title.replace(" (Windows)", ""), platform="windows", width=like.width, height=like.height,
               device_id=like.device_id)
    s.nodes = fn(s, appearance)
    return s
