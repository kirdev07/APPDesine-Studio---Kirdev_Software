"""Готовые экраны (версия 1.19): календарь, карта, статистика с графиками, лента соцсети. Без Qt.

Те же правила, что у остальных готовых экранов: содержимое — столбец с прокруткой под верхней панелью,
компоненты Material 3 и графики из галереи; при выгрузке в Android — Scaffold, Column, Box и Canvas.
"""

from __future__ import annotations

from app.core.document.model import Node, Screen
from app.libraries import charts, components
from app.libraries.components import _Ctx
from app.libraries.screen_templates import _content, _fill, _list_item, _set_text, _text, _top_bar


def _b(s, ap, kind: str) -> Node:
    return components.build(kind, s, ap)


def _card(c: _Ctx, name: str, kids: list[Node], **kw) -> Node:
    kw.setdefault("gap", 12)
    return c.frame(name, "vertical", kids, pad_l=16, pad_r=16, pad_t=16, pad_b=16, radius=20,
                   fill=c.s["surfaceContainerLow"], sizing_h="fill", sizing_v="hug", **kw)


# ---------------- календарь ----------------

def calendar(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    week = c.frame("Дни недели", "grid", [c.text(d, 12, c.s["onSurfaceVariant"], 500, f"День «{d}»",
                                                 align="center", sizing_h="fill")
                                          for d in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")],
                   grid_columns=7, sizing_h="fill", sizing_v="hug")
    cells = []
    events = {4, 12, 18, 25}
    for i in range(42):  # шесть недель: 1 ноября — воскресенье, 30-е — в шестой
        day = i - 6 + 1  # ноябрь 2026 начинается с воскресенья
        today = day == 28
        label = str(day) if 1 <= day <= 30 else ""
        kids = [c.text(label, 14, c.s["onPrimary"] if today else c.s["onSurface"], 600 if today else 400,
                       "Число", align="center")]
        # место точки есть у каждого дня (без события — прозрачная): числа в ряду стоят на одной линии
        kids.append(c.dot("Событие", 5, (c.s["onPrimary"] if today else c.s["primary"]) if day in events else ""))
        cells.append(c.frame(f"День {label or '—'}", "vertical", kids, h=44, radius=22 if today else 0,
                             fill=c.s["primary"] if today else "", main_align="center", cross_align="center",
                             gap=2, sizing_h="fill"))
    month = c.frame("Месяц", "grid", cells, grid_columns=7, row_gap=4, sizing_h="fill", sizing_v="hug")
    head = c.frame("Заголовок месяца", "horizontal",
                   [_text(c, "Ноябрь 2026", 22, c.s["onSurface"], 500, "Месяц"),
                    c.icon(24, color=c.s["onSurfaceVariant"], glyph="chevron_left"),
                    c.icon(24, color=c.s["onSurfaceVariant"], glyph="chevron_right")],
                   gap=16, cross_align="center", sizing_h="fill", sizing_v="hug")
    plans = [_list_item(s, ap, t, d) for t, d in (("Созвон с командой", "10:00 – 10:30 · Видеовстреча"),
                                                  ("Йога", "19:00 · Зал на Лесной"))]
    add = _b(s, ap, "m3_fab")
    add.x, add.y = s.width - add.w - c.d(16), s.height - add.h - c.d(96)
    kids = [head, week, month, c.rect("Разделитель", 10, 1, c.s["outlineVariant"], sizing_h="fill"),
            _text(c, "Сегодня, 28 ноября", 16, c.s["primary"], 500, "Раздел")] + plans
    return [_top_bar(s, ap, "Календарь"), _content(c, s, kids, 64, 80, gap=12), add, _b(s, ap, "m3_nav_bar")]


# ---------------- карта ----------------

def map_screen(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    w = c.width_dp - 32
    streets = [c.rect(f"Улица {i + 1}", w, 10, c.s["surfaceContainerHighest"], x=0, y=c.d(y))
               for i, y in enumerate((70, 190, 300))]
    streets += [c.rect(f"Проезд {i + 1}", 10, 380, c.s["surfaceContainerHighest"], x=c.d(x), y=0)
                for i, x in enumerate((60, 200, 300))]
    park = c.rect("Парк", 110, 90, "#B7E1B0" if ap.theme == "light" else "#2D4A31", radius=24, x=c.d(210),
                  y=c.d(85))
    pins = []
    for i, (x, y, color) in enumerate(((120, 140, c.s["primary"]), (250, 230, c.s["tertiary"]),
                                       (40, 250, c.s["primary"]))):
        p = c.icon(44, f"Метка {i + 1}", color, "location_on")
        p.x, p.y = c.d(x), c.d(y)
        pins.append(p)
    me = c.dot("Я здесь", 18, "#1A73E8")
    me.x, me.y, me.stroke, me.stroke_width = c.d(160), c.d(320), "#FFFFFF", c.d(3)
    for n in streets + [park]:
        n.constraint_h = n.constraint_v = "scale"   # улицы и парк тянутся вместе с картой
    for n in pins + [me]:
        n.constraint_h = n.constraint_v = "center"  # метки и точка — свой размер, не сплющиваются
    m = c.frame("Карта", "none", streets + [park] + pins + [me], w=w, h=380, radius=24, fill=c.s["surfaceContainer"],
                clip=True, sizing_h="fill")
    search = _fill(_b(s, ap, "m3_search_bar"))
    _set_text(search, "Плейсхолдер", "Куда поедем?")
    place = _card(c, "Место", [
        _text(c, "Кофейня «Зерно»", 20, c.s["onSurface"], 500, "Название"),
        _text(c, "★ 4,8 · 350 м · открыто до 22:00", 14, c.s["onSurfaceVariant"], name="Подробности"),
        c.frame("Кнопки", "horizontal", [_fill(_b(s, ap, "m3_button_filled")), _fill(_b(s, ap, "m3_button_tonal"))],
                gap=12, sizing_h="fill", sizing_v="hug")])
    _set_text(place.children[-1].children[0], "Подпись", "Маршрут")
    _set_text(place.children[-1].children[1], "Подпись", "Звонок")
    for b in place.children[-1].children:
        b.sizing_h = "fill"
    return [_content(c, s, [search, m, place], 24, gap=16)]


# ---------------- статистика ----------------

def stats(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    period = _fill(_b(s, ap, "m3_segmented"))
    for i, t in enumerate(("Неделя", "Месяц", "Год")):
        _set_text(period, "Подпись", t, i)
    k1, k2 = _b(s, ap, "chart_kpi"), _b(s, ap, "chart_kpi")
    for k in (k1, k2):
        k.sizing_h = "fill"
    _set_text(k2, "Подпись", "Заказы")
    _set_text(k2, "Число", "1 284")
    _set_text(k2, "Процент", "+4%")
    kpis = c.frame("Показатели", "horizontal", [k1, k2], gap=12, sizing_h="fill", sizing_v="hug")
    line = _b(s, ap, "chart_line")
    bars = _b(s, ap, "chart_bar")
    for g in (line, bars):
        g.sizing_h = "fill"
    days = c.frame("Подписи дней", "horizontal",
                   [c.text(d, 12, c.s["onSurfaceVariant"], name=f"День «{d}»", align="center", sizing_h="fill")
                    for d in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")], sizing_h="fill", sizing_v="hug")
    donut = _b(s, ap, "chart_donut")
    names = ("Еда", "Транспорт", "Покупки", "Другое")
    cols = [n.fill for n in donut.children]
    shares = c.frame("Доли", "horizontal", [donut, charts.legend(c, list(zip(names, cols)))], gap=24,
                     cross_align="center", sizing_h="fill", sizing_v="hug")
    kids = [period, kpis,
            _card(c, "Выручка", [_text(c, "Выручка за неделю", 16, c.s["onSurface"], 500, "Заголовок"), line]),
            _card(c, "Заказы по дням", [_text(c, "Заказы по дням", 16, c.s["onSurface"], 500, "Заголовок"), bars,
                                        days]),
            _card(c, "Расходы", [_text(c, "Куда уходят деньги", 16, c.s["onSurface"], 500, "Заголовок"), shares])]
    return [_top_bar(s, ap, "Статистика"), _content(c, s, kids, 64, 80, gap=16), _b(s, ap, "m3_nav_bar")]


# ---------------- лента соцсети ----------------

def social(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)

    def story(name: str, own: bool = False) -> Node:
        ring = c.frame("Кольцо", "horizontal", [c.dot("Фото", 56, c.s["secondaryContainer"])], w=64, h=64,
                       radius=32, stroke=c.s["outlineVariant"] if own else c.s["primary"], stroke_width=2.5,
                       main_align="center", cross_align="center")
        return c.frame(f"История «{name}»", "vertical", [ring, c.text(name, 12, c.s["onSurface"], name="Имя")],
                       gap=6, cross_align="center", sizing_h="hug", sizing_v="hug")
    stories = c.frame("Истории", "horizontal", [story("Вы", True), story("Аня"), story("Миша"), story("Катя"),
                                                story("Олег")],
                      gap=14, sizing_h="fill", sizing_v="hug", scroll="horizontal", clip=True)

    def post(author: str, when: str, text: str, likes: str, comments: str, glyph: str) -> Node:
        head = c.frame("Автор", "horizontal",
                       [c.dot("Аватар", 40, c.s["tertiaryContainer"]),
                        c.frame("Имя и время", "vertical", [_text(c, author, 15, c.s["onSurface"], 600, "Имя"),
                                                            _text(c, when, 12, c.s["onSurfaceVariant"], name="Время")],
                                sizing_h="fill", sizing_v="hug"),
                        c.icon(24, color=c.s["onSurfaceVariant"], glyph="more_vert")],
                       gap=12, cross_align="center", sizing_h="fill", sizing_v="hug")
        photo = c.frame("Фото поста", "horizontal", [c.icon(56, color=c.s["onSecondaryContainer"], glyph=glyph)],
                        h=240, radius=16, fill=c.s["secondaryContainer"], main_align="center", cross_align="center",
                        sizing_h="fill")

        def act(g: str, n: str) -> Node:
            return c.frame(f"Действие «{g}»", "horizontal", [c.icon(22, color=c.s["onSurfaceVariant"], glyph=g)]
                           + ([c.text(n, 14, c.s["onSurfaceVariant"], name="Число")] if n else []),
                           gap=6, cross_align="center", sizing_h="hug", sizing_v="hug")
        actions = c.frame("Действия", "horizontal", [act("favorite", likes), act("chat_bubble", comments),
                                                      act("share", ""), c.rect("Отступ", 10, 10, "", sizing_h="fill"),
                                                      act("bookmark", "")],
                          gap=20, cross_align="center", sizing_h="fill", sizing_v="hug")
        return c.frame(f"Пост {author}", "vertical",
                       [head, _text(c, text, 15, c.s["onSurface"], name="Текст"), photo, actions],
                       gap=12, sizing_h="fill", sizing_v="hug")
    kids = [stories, c.rect("Разделитель", 10, 1, c.s["outlineVariant"], sizing_h="fill"),
            post("Анна Смирнова", "2 ч назад", "Наконец-то добралась до гор — виды невероятные!", "128", "24",
                 "landscape"),
            post("Миша Петров", "вчера", "Новый рецепт: паста с грибами за 15 минут", "56", "8", "restaurant")]
    return [_top_bar(s, ap, "Лента"), _content(c, s, kids, 64, 80, gap=16), _b(s, ap, "m3_nav_bar")]


TEMPLATES = {
    "calendar": ("Календарь", calendar), "map": ("Карта", map_screen), "stats": ("Статистика", stats),
    "social": ("Лента соцсети", social),
}
