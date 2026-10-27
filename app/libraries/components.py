"""Базовые компоненты (заготовки) из фреймов с Auto Layout.

Android — приближение Material 3 (размеры в dp пересчитываются в пиксели экрана по плотности устройства).
Windows — приближение Fluent (пиксели при 96 dpi). Это стартовые макеты, а не точная копия системных
компонентов: точность отрисовки Compose/WinUI не гарантируется. Повторно используемые мастер-компоненты
с экземплярами и переопределениями — этап 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.core.document.model import Appearance, Node, Screen
from app.libraries.catalog import device

LOREM_RU = ("Карточка группирует связанную информацию. Длинный текст переносится по словам и увеличивает "
            "высоту карточки, если её высота задана «по содержимому».")


@dataclass(frozen=True)
class ComponentSpec:
    kind: str
    name: str
    platform: str
    category: str
    builder: Callable


def _palette(theme: str) -> dict:
    if theme == "light":
        return {"surface": "#F7F2FA", "surface2": "#ECE6F0", "on": "#1D1B20", "muted": "#49454F", "outline": "#79747E",
                "win_surface": "#FBFBFB", "win_card": "#FFFFFF", "win_stroke": "#E5E5E5", "win_ctrl": "#FDFDFD"}
    return {"surface": "#1D1B20", "surface2": "#2B2930", "on": "#E6E0E9", "muted": "#CAC4D0", "outline": "#938F99",
            "win_surface": "#202020", "win_card": "#2B2B2B", "win_stroke": "#3A3A3A", "win_ctrl": "#2D2D2D"}


def _on_color(hex_color: str) -> str:
    v = hex_color.lstrip("#")
    r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    return "#000000" if 0.299 * r + 0.587 * g + 0.114 * b > 160 else "#FFFFFF"


class _Ctx:
    def __init__(self, screen: Screen, ap: Appearance):
        self.screen, self.ap = screen, ap
        self.p = _palette(ap.theme)
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

    def text(self, t: str, size: float, color: str, weight: int = 400, name: str = "Текст", **kw) -> Node:
        kw.setdefault("sizing_h", "hug")
        kw.setdefault("sizing_v", "hug")
        return Node(type="text", name=name, text=t, font_size=self.d(size), font_weight=weight, text_color=color,
                    font_family=self.font, fill="", w=self.d(100), h=self.d(size * 1.4), **kw)

    def frame(self, name: str, layout: str, children: list[Node], **kw) -> Node:
        for key in ("gap", "row_gap", "pad_t", "pad_r", "pad_b", "pad_l", "radius", "stroke_width",
                    "w", "h", "min_w", "max_w", "min_h", "max_h"):
            if key in kw:
                kw[key] = self.d(kw[key])
        kw.setdefault("fill", "")
        return Node(type="frame", name=name, layout=layout, children=children, **kw)

    def icon(self, size: float = 24, name: str = "Значок", color: str | None = None) -> Node:
        return Node(type="ellipse", name=name, w=self.d(size), h=self.d(size), fill=color or self.p["muted"])


# ---------------- Android / Material 3 ----------------

def m3_button_filled(c: _Ctx) -> Node:
    acc = c.ap.accent
    return c.frame("Кнопка", "horizontal", [c.text("Продолжить", 14, _on_color(acc), 500, "Подпись")],
                   h=40, pad_l=24, pad_r=24, gap=8, radius=20, fill=acc, main_align="center", cross_align="center",
                   sizing_h="hug", sizing_v="fixed")


def m3_button_outlined(c: _Ctx) -> Node:
    return c.frame("Кнопка (контур)", "horizontal", [c.text("Отмена", 14, c.ap.accent, 500, "Подпись")],
                   h=40, pad_l=24, pad_r=24, radius=20, stroke=c.p["outline"], stroke_width=1, main_align="center",
                   cross_align="center", sizing_h="hug")


def m3_text_field(c: _Ctx) -> Node:
    box = c.frame("Поле", "horizontal", [c.text("Введите имя", 16, c.p["muted"], name="Плейсхолдер",
                                               sizing_h="fill")],
                  h=56, pad_l=16, pad_r=16, radius=4, stroke=c.p["outline"], stroke_width=1, cross_align="center",
                  sizing_h="fill")
    hint = c.text("Подсказка: имя увидят ваши контакты", 12, c.p["muted"], name="Подсказка", sizing_h="fill")
    return c.frame("Текстовое поле", "vertical", [box, hint], w=320, gap=4, sizing_v="hug")


def m3_card(c: _Ctx) -> Node:
    acc = c.ap.accent
    actions = c.frame("Действия", "horizontal",
                      [c.frame("Кнопка", "horizontal", [c.text("Открыть", 14, _on_color(acc), 500, "Подпись")],
                               h=40, pad_l=24, pad_r=24, radius=20, fill=acc, main_align="center",
                               cross_align="center", sizing_h="hug")],
                      main_align="end", sizing_h="fill", sizing_v="hug")
    return c.frame("Карточка", "vertical",
                   [c.text("Заголовок карточки", 22, c.p["on"], 400, "Заголовок", sizing_h="fill"),
                    c.text(LOREM_RU, 14, c.p["muted"], name="Описание", sizing_h="fill"), actions],
                   w=340, pad_t=16, pad_r=16, pad_b=16, pad_l=16, gap=8, radius=12, fill=c.p["surface"],
                   sizing_v="hug")


def m3_top_app_bar(c: _Ctx) -> Node:
    s = c.screen
    return c.frame("Верхняя панель", "horizontal",
                   [c.icon(24, "Меню", c.p["on"]), c.text("Заголовок экрана", 22, c.p["on"], name="Заголовок",
                                                          sizing_h="fill"), c.icon(24, "Действие", c.p["on"])],
                   x=0, y=0, w=s.width / c.k, h=64, pad_l=16, pad_r=16, gap=16, cross_align="center",
                   fill=c.p["surface"], constraint_h="left_right", constraint_v="top")


def m3_nav_bar(c: _Ctx) -> Node:
    s = c.screen
    items = []
    for i, label in enumerate(["Главная", "Чаты", "Звонки", "Профиль"]):
        active = i == 0
        pill = Node(type="rect", name="Индикатор", w=c.d(64), h=c.d(32), radius=c.d(16),
                    fill=c.p["surface2"] if active else "")
        items.append(c.frame(f"Пункт «{label}»", "vertical",
                             [pill, c.text(label, 12, c.p["on"] if active else c.p["muted"], 600 if active else 500,
                                           "Подпись")],
                             gap=4, cross_align="center", main_align="center", sizing_h="fill", sizing_v="fill"))
    h = 80  # dp; x и y задаются в пикселях экрана
    return c.frame("Нижняя навигация", "horizontal", items, x=0, y=s.height - c.d(h), w=s.width / c.k, h=h,
                   pad_t=12, pad_b=12, gap=8, fill=c.p["surface"], cross_align="stretch",
                   constraint_h="left_right", constraint_v="bottom")


def m3_list_item(c: _Ctx) -> Node:
    s = c.screen
    texts = c.frame("Текст", "vertical",
                    [c.text("Анна Смирнова", 16, c.p["on"], name="Заголовок", sizing_h="fill"),
                     c.text("Увидимся завтра в десять, не забудь документы", 14, c.p["muted"], name="Подпись",
                            sizing_h="fill")],
                    gap=2, sizing_h="fill", sizing_v="hug")
    return c.frame("Элемент списка", "horizontal", [c.icon(40, "Аватар"), texts],
                   x=0, w=s.width / c.k, h=72, pad_l=16, pad_r=24, gap=16, cross_align="center",
                   constraint_h="left_right", sizing_v="hug", min_h=72, pad_t=8, pad_b=8)


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


SPECS: tuple[ComponentSpec, ...] = (
    ComponentSpec("m3_button_filled", "Кнопка", "android", "Кнопки", m3_button_filled),
    ComponentSpec("m3_button_outlined", "Кнопка (контур)", "android", "Кнопки", m3_button_outlined),
    ComponentSpec("m3_text_field", "Текстовое поле", "android", "Поля", m3_text_field),
    ComponentSpec("m3_card", "Карточка", "android", "Карточки", m3_card),
    ComponentSpec("m3_list_item", "Элемент списка", "android", "Карточки", m3_list_item),
    ComponentSpec("m3_top_app_bar", "Верхняя панель", "android", "Навигация", m3_top_app_bar),
    ComponentSpec("m3_nav_bar", "Нижняя навигация", "android", "Навигация", m3_nav_bar),
    ComponentSpec("win_button_accent", "Кнопка", "windows", "Кнопки", win_button_accent),
    ComponentSpec("win_button", "Кнопка (обычная)", "windows", "Кнопки", win_button),
    ComponentSpec("win_textbox", "Текстовое поле", "windows", "Поля", win_textbox),
    ComponentSpec("win_card", "Карточка", "windows", "Карточки", win_card),
    ComponentSpec("win_command_bar", "Панель команд", "windows", "Навигация", win_command_bar),
    ComponentSpec("win_nav_pane", "Панель навигации", "windows", "Навигация", win_nav_pane),
)


def specs_for(platform: str) -> list[ComponentSpec]:
    return [s for s in SPECS if s.platform == platform]


def build(kind: str, screen: Screen, appearance: Appearance) -> Node:
    spec = next((s for s in SPECS if s.kind == kind), None)
    if spec is None:
        raise KeyError(kind)
    c = _Ctx(screen, appearance)
    node = spec.builder(c)
    # компоненты не на всю ширину ставятся с отступом 16 dp от левого края, по центру по высоте
    if node.constraint_h != "left_right" and node.x == 0 and node.y == 0 and kind != "win_nav_pane":
        node.x = c.d(16)
        node.y = round(screen.height * 0.35, 2)
    return node
