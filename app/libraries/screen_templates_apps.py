"""Готовые экраны (версия 1.28): банк, доставка, фитнес, путешествия, покупки и сервисные экраны, а также
«готовые приложения» — наборы связанных экранов с нижним меню и переходами. Без Qt.

Те же правила, что у остальных готовых экранов: компоненты Material 3 из галереи (их вид меняется вместе с
поколением Material и темой), содержимое — столбец с прокруткой, панели — в слотах Scaffold при выгрузке.
"""

from __future__ import annotations

from app.core.document import tree
from app.core.document.model import Node, Screen
from app.libraries import components
from app.libraries.components import _Ctx
from app.libraries.screen_templates import _content, _field, _fill, _list_item, _set_text, _text, _top_bar
from app.libraries.screen_templates_more import _big_icon, _centered, _row_center


def _b(s, ap, kind: str) -> Node:
    return components.build(kind, s, ap)


def _glyph(node: Node, glyph: str) -> Node:
    """Заменить первый значок внутри элемента на значок Material Symbols по имени."""
    from app.libraries import symbols
    d = symbols.path(glyph)
    v = next((x for x in tree.descendants(node) if x.type == "vector"), None)
    if d and v is not None:
        v.path, v.vb_w, v.vb_h, v.fill_rule, v.name = d, symbols.VIEWBOX, symbols.VIEWBOX, "nonzero", \
            symbols.russian_name(glyph)
    return node


def _rating(s, ap, caption: str = "") -> Node:
    """Звёзды рейтинга; подпись своя или без неё (число отзывов уже написано рядом)."""
    r = _b(s, ap, "m3_rating")
    cap = next((d for d in r.children if d.type == "text"), None)
    if cap is not None:
        if caption:
            cap.text = caption
        else:
            r.children.remove(cap)
    return r


# нижнее меню по смыслу приложения: (значок, подпись)
NAVS = {
    "bank": [("home", "Главная"), ("receipt_long", "История"), ("send", "Переводы"), ("person", "Профиль")],
    "food": [("home", "Главная"), ("receipt_long", "Заказы"), ("shopping_cart", "Корзина"), ("person", "Профиль")],
    "fit": [("fitness_center", "Сегодня"), ("bar_chart", "Активность"), ("school", "Курсы"), ("person", "Профиль")],
    "travel": [("search", "Поиск"), ("luggage", "Поездки"), ("hotel", "Отели"), ("person", "Профиль")],
    "notes": [("description", "Заметки"), ("checklist", "Задачи"), ("calendar_month", "Календарь"),
              ("person", "Профиль")],
    "home": [("home", "Дом"), ("bolt", "Сценарии"), ("bar_chart", "Энергия"), ("settings", "Настройки")],
    "shop": [("home", "Главная"), ("receipt_long", "Заказы"), ("shopping_cart", "Корзина"), ("person", "Профиль")],
}


def relabel_nav(nav: Node, kind: str, selected: int, ap) -> None:
    """Пункты нижнего меню по смыслу приложения; выбран пункт selected."""
    from app.engines.material.color import scheme
    from app.engines.preview import live
    for it, (glyph, label) in zip(live._items(nav), NAVS[kind]):
        _glyph(it, glyph)
        _set_text(it, "Подпись", label)
    live.restyle(nav, selected, {**scheme(ap.accent, ap.theme != "light"), "__gen": ap.material})


def _nav(s, ap, kind: str, selected: int) -> Node:
    """Нижнее меню со своими пунктами; выбран пункт этого экрана (в выбранном поколении Material)."""
    from app.engines.material.color import scheme
    from app.engines.preview import live
    nav = _b(s, ap, "m3_nav_bar")
    relabel_nav(nav, kind, selected, ap)
    return nav


def _card(c: _Ctx, name: str, kids: list[Node], fill: str = "surfaceContainerLow", **kw) -> Node:
    kw.setdefault("gap", 10)
    return c.frame(name, "vertical", kids, pad_l=16, pad_r=16, pad_t=16, pad_b=16, radius=20,
                   fill=c.s[fill], sizing_h="fill", sizing_v="hug", **kw)


def _photo(c: _Ctx, name: str, glyph: str, h: float = 180, bg: str = "secondaryContainer",
           fg: str = "onSecondaryContainer", radius: float = 20) -> Node:
    """Заглушка фото: цветная плашка со значком (меняется на настоящую картинку через «Картинка…»)."""
    return c.frame(name, "horizontal", [c.icon(56, color=c.s[fg], glyph=glyph)], h=h, radius=radius, fill=c.s[bg],
                   main_align="center", cross_align="center", sizing_h="fill")


def _section(c: _Ctx, t: str, more: str = "") -> Node:
    kids = [_text(c, t, 20, c.s["onSurface"], 500, "Раздел")]
    if more:
        kids.append(c.text(more, 14, c.s["primary"], 500, "Ещё"))
    return c.frame(f"Раздел «{t}»", "horizontal", kids, cross_align="center", sizing_h="fill", sizing_v="hug")


def _button(s, ap, kind: str, label: str, fill: bool = True) -> Node:
    b = _b(s, ap, kind)
    _set_text(b, "Подпись", label)
    return _fill(b) if fill else b


def _row(c: _Ctx, kids: list[Node], name: str = "Ряд", gap: float = 12, **kw) -> Node:
    return c.frame(name, "horizontal", kids, gap=gap, cross_align="center", sizing_h="fill", sizing_v="hug", **kw)


def _col(c: _Ctx, kids: list[Node], name: str = "Столбец", gap: float = 4, **kw) -> Node:
    kw.setdefault("sizing_h", "fill")
    return c.frame(name, "vertical", kids, gap=gap, sizing_v="hug", **kw)


def _icon_box(c: _Ctx, glyph: str, bg: str = "secondaryContainer", fg: str = "onSecondaryContainer",
              side: float = 44) -> Node:
    return c.frame("Значок", "horizontal", [c.icon(side * 0.5, color=c.s[fg], glyph=glyph)], w=side, h=side,
                   radius=side / 2, fill=c.s[bg], main_align="center", cross_align="center")


def _icon_row(c: _Ctx, glyph: str, title: str, sub: str, right: str = "", right_color: str = "onSurface") -> Node:
    kids = [_icon_box(c, glyph),
            _col(c, [_text(c, title, 16, c.s["onSurface"], 500, "Заголовок"),
                     _text(c, sub, 13, c.s["onSurfaceVariant"], name="Подпись")], "Текст", 2)]
    if right:
        kids.append(c.text(right, 15, c.s[right_color], 500, "Справа"))
    return _row(c, kids, f"Строка «{title}»")


def _chips(c: _Ctx, s, ap, labels: list[str], selected=0, wrap: bool = False) -> Node:
    picked = set(selected) if isinstance(selected, (set, list, tuple)) else {selected}
    chips = []
    for i, t in enumerate(labels):
        ch = _b(s, ap, "m3_chip_filter")
        _set_text(ch, "Подпись", t)
        if i not in picked:  # невыбранный фильтр: без галочки и заливки, с рамкой
            ch.fill, ch.stroke, ch.stroke_width = "", c.s["outline"], c.d(1)
            for d in ch.children:
                if d.type == "vector":
                    ch.children.remove(d)
                    break
        chips.append(ch)
    if wrap:
        return c.frame("Метки", "wrap", chips, gap=8, row_gap=8, sizing_h="fill", sizing_v="hug")
    return c.frame("Фильтры", "horizontal", chips, gap=8, sizing_h="fill", sizing_v="hug", scroll="horizontal",
                   clip=True)


def _hinted(f: Node, hint: str, value: str = "") -> Node:
    """Поле со своей подсказкой под ним (и значением)."""
    texts = [d for d in tree.descendants(f) if d.type == "text"]
    if texts:
        texts[-1].text = hint
        if value and len(texts) > 1:
            texts[0].text = value
    return _fill(f)


def _progress(s, ap, c: _Ctx, share: float, inset_dp: float = 64) -> Node:
    """Полоса прогресса на ширину карточки; закрашенная часть — доля share."""
    p = _b(s, ap, "m3_progress_linear")
    p.w = c.d(c.width_dp - inset_dp)
    if p.children:
        p.children[0].w = round(p.w * max(0.0, min(1.0, share)), 2)
    return p


def _initials(c: _Ctx, text: str, side: float = 40) -> Node:
    """Аватар с буквами вместо пустого кружка."""
    return c.frame("Аватар", "horizontal", [c.text(text, side * 0.38, c.s["onTertiaryContainer"], 600, "Буквы")],
                   w=side, h=side, radius=side / 2, fill=c.s["tertiaryContainer"], main_align="center",
                   cross_align="center")


def _stat(c: _Ctx, value: str, label: str) -> Node:
    return _col(c, [_text(c, value, 22, c.s["onSurface"], 600, "Значение"),
                    _text(c, label, 13, c.s["onSurfaceVariant"], name="Подпись")], f"Показатель «{label}»", 2)


# ---------------- банк ----------------

def bank_home(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    dark = ap.theme != "light"

    def bank_card(name, num, bal, a, b):
        fg = c.s["onPrimaryContainer"] if dark else "#FFFFFF"
        card = c.frame(f"Карта «{name}»", "vertical",
                       [_row(c, [_text(c, name, 15, fg, 500, "Название"), c.icon(28, color=fg, glyph="contactless")],
                             "Шапка"),
                        c.rect("Отступ", 10, 28, "", sizing_h="fill"),
                        _text(c, bal, 26, fg, 600, "Баланс"), _text(c, num, 14, fg, name="Номер")],
                       w=280, h=170, pad_l=20, pad_r=20, pad_t=18, pad_b=18, gap=4, radius=24,
                       fill=c.s["primaryContainer"] if dark else a)
        if not dark:
            card.gradient, card.fill2, card.grad_angle = "linear", b, 135
        return card
    cards = c.frame("Карты", "horizontal",
                    [bank_card("Дебетовая", "•••• 4821", "48 250 ₽", c.s["primary"], c.s["tertiary"]),
                     bank_card("Кредитная", "•••• 1190", "120 000 ₽", "#1E3A5F", "#3E6E9E"),
                     bank_card("Накопления", "5,5% годовых", "312 400 ₽", "#2E7D32", "#66BB6A")],
                    gap=12, sizing_h="fill", sizing_v="hug", scroll="horizontal", clip=True)

    def quick(glyph, t):
        return _col(c, [_icon_box(c, glyph, side=56), c.text(t, 12, c.s["onSurface"], name="Подпись")],
                    f"Действие «{t}»", 6, cross_align="center")
    actions = _row(c, [quick("send", "Перевести"), quick("qr_code_scanner", "Оплатить"),
                       quick("add_card", "Пополнить"), quick("receipt_long", "Счета")], "Быстрые действия", 0)
    ops = [_icon_row(c, g, t, d, v, "primary" if v.startswith("+") else "onSurface") for g, t, d, v in (
        ("local_cafe", "Кофейня «Зерно»", "Сегодня, 9:12", "−240 ₽"),
        ("person", "Иван П.", "Перевод · вчера", "+5 000 ₽"),
        ("local_taxi", "Такси", "Вчера, 23:40", "−560 ₽"),
        ("shopping_bag", "Маркет", "27 октября", "−2 130 ₽"))]
    kids = [_text(c, "Добрый день, Анна", 24, c.s["onSurface"], 500, "Приветствие"), cards, actions,
            _section(c, "Последние операции", "Все")] + ops
    return [_top_bar(s, ap, "Банк"), _content(c, s, kids, 64, 80, gap=16), _nav(s, ap, "bank", 0)]


def transfer(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    amount = _col(c, [_centered(c, "Сумма перевода", 14, c.s["onSurfaceVariant"], name="Подпись"),
                      _centered(c, "1 500 ₽", 44, c.s["onSurface"], 600, "Сумма"),
                      _centered(c, "Без комиссии до 100 000 ₽ в месяц", 13, c.s["primary"], name="Комиссия")],
                  "Сумма", 6, cross_align="center")
    fast = _chips(c, s, ap, ["500 ₽", "1 000 ₽", "1 500 ₽", "5 000 ₽"], 2)
    kids = [_field(c, s, ap, "Телефон или номер карты", "Перевод по номеру телефона — через СБП"),
            _icon_row(c, "person", "Иван Петров", "+7 900 ••• 12 34 · Т-Банк"),
            c.rect("Разделитель", 10, 1, c.s["outlineVariant"], sizing_h="fill"), amount, fast,
            _field(c, s, ap, "Сообщение получателю"), c.rect("Отступ", 10, 8, "", sizing_h="fill"),
            _button(s, ap, "m3_button_filled", "Перевести 1 500 ₽")]
    return [_top_bar(s, ap, "Перевод", back=True), _content(c, s, kids, 64, 0, gap=16)]


def history(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    seg = _fill(_b(s, ap, "m3_segmented"))
    for i, t in enumerate(("Все", "Траты", "Доходы")):
        _set_text(seg, "Подпись", t, i)
    kids = [seg, _text(c, "Сегодня", 14, c.s["primary"], 500, "Дата")]
    kids += [_icon_row(c, g, t, d, v, "primary" if v.startswith("+") else "onSurface") for g, t, d, v in (
        ("local_cafe", "Кофейня «Зерно»", "Кафе и рестораны", "−240 ₽"),
        ("directions_bus", "Метро", "Транспорт", "−62 ₽"))]
    kids.append(_text(c, "Вчера", 14, c.s["primary"], 500, "Дата"))
    kids += [_icon_row(c, g, t, d, v, "primary" if v.startswith("+") else "onSurface") for g, t, d, v in (
        ("person", "Иван П.", "Перевод", "+5 000 ₽"), ("local_taxi", "Такси", "Транспорт", "−560 ₽"),
        ("movie", "Кинотеатр", "Развлечения", "−1 100 ₽"), ("work", "Зарплата", "Пополнение", "+86 000 ₽"))]
    return [_top_bar(s, ap, "История"), _content(c, s, kids, 64, 80, gap=14), _nav(s, ap, "bank", 1)]


def payment_success(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    receipt = _card(c, "Чек", [_row(c, [_text(c, "Получатель", 14, c.s["onSurfaceVariant"], name="Что"),
                                        c.text("Иван Петров", 14, c.s["onSurface"], 500, "Значение")]),
                               _row(c, [_text(c, "Сумма", 14, c.s["onSurfaceVariant"], name="Что"),
                                        c.text("1 500 ₽", 14, c.s["onSurface"], 500, "Значение")]),
                               _row(c, [_text(c, "Комиссия", 14, c.s["onSurfaceVariant"], name="Что"),
                                        c.text("0 ₽", 14, c.s["onSurface"], 500, "Значение")])])
    kids = [c.rect("Отступ", 10, 64, "", sizing_h="fill"),
            _row_center(c, [_big_icon(c, "check", "primaryContainer", "onPrimaryContainer", 120, 64)]),
            _centered(c, "Перевод отправлен", 28, c.s["onSurface"], 500, "Заголовок"),
            _centered(c, "Деньги придут в течение минуты", 16, c.s["onSurfaceVariant"], name="Описание"),
            receipt, c.rect("Отступ", 10, 24, "", sizing_h="fill"),
            _button(s, ap, "m3_button_filled", "Готово"), _button(s, ap, "m3_button_outlined", "Поделиться чеком")]
    return [_content(c, s, kids, 0, gap=16)]


# ---------------- доставка еды ----------------

def _rest_card(c: _Ctx, name: str, cuisine: str, rating: str, time: str, glyph: str) -> Node:
    info = _row(c, [c.icon(16, color=c.s["primary"], glyph="star"), c.text(rating, 13, c.s["onSurface"], 500, "Рейтинг"),
                    c.text(f"· {cuisine} · {time}", 13, c.s["onSurfaceVariant"], name="Детали")], "Детали", 4)
    return _col(c, [_photo(c, "Фото", glyph, 150), _text(c, name, 17, c.s["onSurface"], 500, "Название"), info],
                f"Ресторан «{name}»", 8)


def restaurants(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    search = _fill(_b(s, ap, "m3_search_bar"))
    _set_text(search, "Плейсхолдер", "Ресторан или блюдо")
    kids = [_row(c, [c.icon(20, color=c.s["primary"], glyph="location_on"),
                     _text(c, "ул. Лесная, 12", 15, c.s["onSurface"], 500, "Адрес"),
                     c.icon(20, color=c.s["onSurfaceVariant"], glyph="expand_more")], "Адрес", 6),
            search, _chips(c, s, ap, ["Все", "Пицца", "Суши", "Бургеры", "Здоровое", "Десерты"]),
            _section(c, "Рядом с вами", "Все"),
            _rest_card(c, "Додо Пицца", "пицца", "4,8", "25–35 мин", "local_pizza"),
            _rest_card(c, "Суши Мастер", "японская", "4,7", "30–40 мин", "set_meal"),
            _rest_card(c, "Бургер Клаб", "бургеры", "4,6", "20–30 мин", "lunch_dining")]
    return [_top_bar(s, ap, "Доставка"), _content(c, s, kids, 64, 80, gap=16), _nav(s, ap, "food", 0)]


def restaurant(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)

    def dish(name, desc, price, glyph):
        add = _glyph(_b(s, ap, "m3_icon_button_filled"), "add")
        return _row(c, [_col(c, [_text(c, name, 16, c.s["onSurface"], 500, "Название"),
                                 _text(c, desc, 13, c.s["onSurfaceVariant"], name="Состав"),
                                 _text(c, price, 15, c.s["onSurface"], 600, "Цена")], "Описание", 4),
                        c.frame("Фото блюда", "horizontal", [c.icon(32, color=c.s["onTertiaryContainer"], glyph=glyph)],
                                w=88, h=88, radius=16, fill=c.s["tertiaryContainer"], main_align="center",
                                cross_align="center"), add], f"Блюдо «{name}»")
    kids = [_photo(c, "Обложка", "local_pizza", 180),
            _text(c, "Додо Пицца", 26, c.s["onSurface"], 500, "Название"),
            _row(c, [_rating(s, ap), _text(c, "4,8 · 2 100 отзывов · 25–35 мин", 13, c.s["onSurfaceVariant"],
                                            name="Детали")], "Рейтинг", 8),
            dish("Маргарита", "Томаты, моцарелла, базилик", "590 ₽", "local_pizza"),
            dish("Пепперони", "Пикантная пепперони, сыр", "690 ₽", "local_pizza"),
            dish("Четыре сыра", "Моцарелла, чеддер, пармезан, дорблю", "790 ₽", "local_pizza"),
            dish("Морс клюквенный", "0,5 л", "190 ₽", "local_drink"),
            c.rect("Отступ под корзину", 10, 72, "", sizing_h="fill")]
    cart = _glyph(_b(s, ap, "m3_fab_extended"), "shopping_cart")
    _set_text(cart, "Подпись", "Корзина · 1 470 ₽")
    cart.x, cart.y = c.d(16), s.height - c.d(88)
    return [_top_bar(s, ap, "Ресторан", back=True), _content(c, s, kids, 64, 0, gap=16), cart]


def orders(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    tabs = _fill(_b(s, ap, "m3_segmented"))
    for i, t in enumerate(("Активные", "Завершённые")):
        _set_text(tabs, "Подпись", t, i)
    if len([x for x in tabs.children if x.is_frame]) > 2:  # третий сегмент не нужен
        last = [x for x in tabs.children if x.is_frame][-1]
        idx = tabs.children.index(last)
        del tabs.children[idx - 1:idx + 1]

    def order(num, what, status, when, glyph, active):
        chip = c.frame("Статус", "horizontal", [c.text(status, 12, c.s["onPrimaryContainer" if active else
                                                                      "onSurfaceVariant"], 500, "Текст")],
                       pad_l=10, pad_r=10, pad_t=4, pad_b=4, radius=12,
                       fill=c.s["primaryContainer" if active else "surfaceContainerHighest"], sizing_h="hug",
                       sizing_v="hug")
        return _card(c, f"Заказ {num}", [_row(c, [_icon_box(c, glyph), _col(c, [
            _text(c, what, 16, c.s["onSurface"], 500, "Что"), _text(c, f"Заказ {num} · {when}", 13,
                                                                    c.s["onSurfaceVariant"], name="Номер")], "Текст", 2),
            chip], "Шапка")])
    kids = [tabs, order("№ 4821", "Додо Пицца", "В пути", "сегодня", "shopping_bag", True),
            order("№ 4790", "Бургер Клаб", "Готовится", "сегодня", "shopping_bag", True),
            order("№ 4655", "Суши Мастер", "Доставлен", "24 октября", "shopping_bag", False)]
    return [_top_bar(s, ap, "Мои заказы"), _content(c, s, kids, 64, 80, gap=12), _nav(s, ap, "food", 1)]


# ---------------- фитнес ----------------

def workout(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    ring = c.frame("Кольцо цели", "vertical", [_centered(c, "7 840", 32, c.s["onSurface"], 600, "Шаги"),
                                             _centered(c, "из 10 000 шагов", 13, c.s["onSurfaceVariant"], name="Цель")],
                   w=180, h=180, radius=90, stroke=c.s["primary"], stroke_width=12, stroke_align="inside",
                   main_align="center", cross_align="center")
    stats = _row(c, [_stat(c, "412", "ккал"), _stat(c, "5,6 км", "дистанция"), _stat(c, "48 мин", "активность")],
                 "Показатели", 8)

    def ex(glyph, t, d):
        play = _glyph(_b(s, ap, "m3_icon_button_tonal"), "play_arrow")
        return _row(c, [_icon_box(c, glyph, "tertiaryContainer", "onTertiaryContainer", 52),
                        _col(c, [_text(c, t, 16, c.s["onSurface"], 500, "Название"),
                                 _text(c, d, 13, c.s["onSurfaceVariant"], name="Детали")], "Текст", 2), play],
                    f"Упражнение «{t}»")
    kids = [_row_center(c, [ring]), stats, _section(c, "Тренировка на сегодня", "Изменить"),
            ex("directions_run", "Разминка", "10 мин · лёгкая"), ex("fitness_center", "Силовая", "25 мин · средняя"),
            ex("self_improvement", "Растяжка", "10 мин · лёгкая"), _button(s, ap, "m3_button_filled", "Начать")]
    return [_top_bar(s, ap, "Сегодня"), _content(c, s, kids, 64, 80, gap=16), _nav(s, ap, "fit", 0)]


def activity(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    bars = _b(s, ap, "chart_bar")
    bars.sizing_h = "fill"
    k1, k2 = _b(s, ap, "chart_kpi"), _b(s, ap, "chart_kpi")
    for k, (lab, num, pct) in zip((k1, k2), (("Шаги в среднем", "8 120", "+12%"), ("Сон", "7,3 ч", "+5%"))):
        k.sizing_h = "fill"
        _set_text(k, "Подпись", lab)
        _set_text(k, "Число", num)
        _set_text(k, "Процент", pct)
    kids = [_chips(c, s, ap, ["Неделя", "Месяц", "Год"]), _row(c, [k1, k2], "Показатели"),
            _card(c, "Шаги", [_text(c, "Шаги по дням", 16, c.s["onSurface"], 500, "Заголовок"), bars]),
            _icon_row(c, "favorite", "Пульс в покое", "Норма", "62 уд/мин"),
            _icon_row(c, "water_drop", "Вода", "Цель 2 л", "1,4 л")]
    return [_top_bar(s, ap, "Активность"), _content(c, s, kids, 64, 80, gap=16), _nav(s, ap, "fit", 1)]


# ---------------- путешествия ----------------

def trip_search(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    seg = _fill(_b(s, ap, "m3_segmented"))
    for i, t in enumerate(("Авиа", "Ж/Д", "Отели")):
        _set_text(seg, "Подпись", t, i)

    def dest(city, price, glyph):
        return _col(c, [_photo(c, "Фото", glyph, 110, "tertiaryContainer", "onTertiaryContainer", 16),
                        _text(c, city, 15, c.s["onSurface"], 500, "Город"),
                        _text(c, price, 13, c.s["onSurfaceVariant"], name="Цена")], f"Направление «{city}»", 6,
                    sizing_h="fill")
    kids = [seg, _field(c, s, ap, "Откуда: Москва"), _field(c, s, ap, "Куда: Санкт-Петербург"),
            _row(c, [_hinted(_b(s, ap, "m3_date_field"), "Туда"),
                     _hinted(_b(s, ap, "m3_dropdown_field"), "Пассажиры", "1 взрослый")], "Даты", 12),
            _button(s, ap, "m3_button_filled", "Найти билеты"), _section(c, "Популярные направления"),
            _row(c, [dest("Сочи", "от 4 200 ₽", "beach_access"), dest("Казань", "от 3 100 ₽", "mosque")],
                 "Направления")]
    return [_top_bar(s, ap, "Путешествия"), _content(c, s, kids, 64, 80, gap=14), _nav(s, ap, "travel", 0)]


def hotel(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    amen = _chips(c, s, ap, ["Wi-Fi", "Завтрак", "Бассейн", "Парковка", "Спа", "Трансфер"], -1, wrap=True)
    price = _row(c, [_col(c, [_text(c, "12 400 ₽", 22, c.s["onSurface"], 600, "Цена"),
                              _text(c, "за 2 ночи", 13, c.s["onSurfaceVariant"], name="Период")], "Цена", 2),
                     _button(s, ap, "m3_button_filled", "Забронировать", False)], "Бронь")
    kids = [_photo(c, "Фото отеля", "hotel", 220),
            _text(c, "Гранд Отель «Европа»", 24, c.s["onSurface"], 500, "Название"),
            _row(c, [_rating(s, ap), _text(c, "4,9 · 1 240 отзывов", 13, c.s["onSurfaceVariant"],
                                            name="Отзывы")], "Рейтинг", 8),
            _icon_row(c, "location_on", "Невский проспект, 1", "5 минут до метро"),
            _section(c, "Удобства"), amen,
            _text(c, "Исторический отель в центре города: просторные номера, ресторан с видом на Неву и "
                     "спа-центр.", 15, c.s["onSurfaceVariant"], name="Описание"), price]
    return [_top_bar(s, ap, "Отель", back=True), _content(c, s, kids, 64, 0, gap=14)]


def boarding_pass(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)

    def city(code, name, time, align):
        return _col(c, [c.text(code, 32, c.s["onSurface"], 600, "Код", align=align, sizing_h="fill"),
                        c.text(name, 13, c.s["onSurfaceVariant"], name="Город", align=align, sizing_h="fill"),
                        c.text(time, 18, c.s["onSurface"], 500, "Время", align=align, sizing_h="fill")],
                    f"Город «{code}»", 2)
    route = _row(c, [city("SVO", "Москва", "08:40", "left"), c.icon(28, color=c.s["primary"], glyph="flight"),
                     city("LED", "Санкт-Петербург", "10:05", "right")], "Маршрут")
    details = _row(c, [_stat(c, "A3", "выход"), _stat(c, "14C", "место"), _stat(c, "08:00", "посадка")],
                   "Детали", 8)
    qr = _row_center(c, [c.frame("QR-код", "horizontal", [c.icon(120, color=c.s["onSurface"], glyph="qr_code_2")],
                                 w=180, h=180, radius=12, fill=c.s["surface"], main_align="center",
                                 cross_align="center")])
    ticket = _card(c, "Талон", [_text(c, "Аэрофлот · SU 30", 14, c.s["primary"], 500, "Рейс"), route,
                                c.rect("Линия отрыва", 10, 1, c.s["outlineVariant"], sizing_h="fill"), details, qr,
                                _centered(c, "Анна Смирнова · эконом", 13, c.s["onSurfaceVariant"], name="Пассажир")],
                   "surfaceContainerHigh", gap=16)
    kids = [ticket, _button(s, ap, "m3_button_tonal", "В Google Кошелёк")]
    return [_top_bar(s, ap, "Посадочный талон", back=True), _content(c, s, kids, 64, 0, gap=16)]


# ---------------- покупки и оплата ----------------

def catalog(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    search = _fill(_b(s, ap, "m3_search_bar"))
    _set_text(search, "Плейсхолдер", "Найти товар")
    cards = []
    for name, price in (("Наушники Pro", "2 990 ₽"), ("Умные часы", "7 490 ₽"), ("Колонка", "3 290 ₽"),
                        ("Чехол", "590 ₽")):
        card = _b(s, ap, "m3_product_card")
        texts = [d for d in tree.descendants(card) if d.type == "text"]
        if texts:
            texts[0].text = name
        prices = [t for t in texts if "₽" in t.text]
        if prices:
            prices[0].text = price
        card.sizing_h, card.constraint_h = "fill", "left"
        cards.append(card)
    grid = c.frame("Товары", "grid", cards, grid_columns=2, gap=12, row_gap=12, sizing_h="fill", sizing_v="hug")
    kids = [search, _chips(c, s, ap, ["Все", "Аудио", "Часы", "Аксессуары", "Акции"]), _section(c, "Популярное", "Все"),
            grid]
    return [_top_bar(s, ap, "Магазин"), _content(c, s, kids, 64, 80, gap=16), _nav(s, ap, "shop", 0)]


def interests(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    tags = _chips(c, s, ap, ["Музыка", "Кино", "Путешествия", "Спорт", "Книги", "Кулинария", "Фото", "Игры",
                             "Наука", "Искусство", "Мода", "Технологии", "Природа"], {0, 2, 5}, wrap=True)
    kids = [c.rect("Отступ", 10, 24, "", sizing_h="fill"),
            _text(c, "Что вам интересно?", 28, c.s["onSurface"], 400, "Заголовок"),
            _text(c, "Выберите хотя бы три темы — подберём ленту под вас", 15, c.s["onSurfaceVariant"],
                  name="Описание"), tags, c.rect("Отступ", 10, 24, "", sizing_h="fill"),
            _button(s, ap, "m3_button_filled", "Продолжить")]
    return [_content(c, s, kids, 0, gap=16)]


def paywall(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)

    def plan(name, price, note, best):
        radio = c.frame("Отметка", "horizontal", [c.dot("Точка", 10, c.s["primary"])] if best else [],
                        w=22, h=22, radius=11, stroke=c.s["primary" if best else "outline"], stroke_width=2,
                        main_align="center", cross_align="center")
        card = _card(c, f"Тариф «{name}»", [_row(c, [radio, _col(c, [
            _text(c, name, 16, c.s["onSurface"], 500, "Название"),
            _text(c, note, 13, c.s["onSurfaceVariant"], name="Заметка")], "Текст", 2),
            c.text(price, 16, c.s["onSurface"], 600, "Цена")], "Строка")],
            "secondaryContainer" if best else "surfaceContainerLow")
        if best:
            card.stroke, card.stroke_width = c.s["primary"], c.d(2)
        return card

    def perk(t):
        return _row(c, [c.icon(22, color=c.s["primary"], glyph="check_circle"),
                        _text(c, t, 15, c.s["onSurface"], name="Текст")], f"Плюс «{t}»", 10)
    kids = [_row_center(c, [_big_icon(c, "workspace_premium", "tertiaryContainer", "onTertiaryContainer", 96, 48)]),
            _centered(c, "Премиум", 28, c.s["onSurface"], 500, "Заголовок"),
            perk("Без рекламы"), perk("Офлайн-режим"), perk("Все курсы и подборки"), perk("Поддержка 24/7"),
            plan("Год", "2 990 ₽", "249 ₽ в месяц · выгода 40%", True), plan("Месяц", "399 ₽", "Отмена в любой момент",
                                                                         False),
            _button(s, ap, "m3_button_filled", "7 дней бесплатно"),
            _centered(c, "Затем 2 990 ₽ в год. Отменить можно в настройках.", 12, c.s["onSurfaceVariant"],
                      name="Условия")]
    return [_top_bar(s, ap, "", back=True), _content(c, s, kids, 64, 0, gap=14)]


def payment_methods(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)

    def method(glyph, t, d, on):
        radio = c.frame("Отметка", "horizontal", [c.dot("Точка", 10, c.s["primary"])] if on else [],
                        w=22, h=22, radius=11, stroke=c.s["primary" if on else "outline"], stroke_width=2,
                        main_align="center", cross_align="center")
        return _card(c, f"Способ «{t}»", [_row(c, [_icon_box(c, glyph), _col(c, [
            _text(c, t, 16, c.s["onSurface"], 500, "Название"), _text(c, d, 13, c.s["onSurfaceVariant"],
                                                                      name="Детали")], "Текст", 2), radio])])
    kids = [method("credit_card", "Visa •••• 4821", "Основная карта", True),
            method("credit_card", "Мир •••• 1190", "Истекает 08/27", False),
            method("account_balance", "СБП", "Оплата по QR и номеру телефона", False),
            method("payments", "Наличными", "Курьеру при получении", False),
            _button(s, ap, "m3_button_outlined", "Добавить карту"), c.rect("Отступ", 10, 16, "", sizing_h="fill"),
            _button(s, ap, "m3_button_filled", "Оплатить 1 280 ₽")]
    return [_top_bar(s, ap, "Оплата", back=True), _content(c, s, kids, 64, 0, gap=12)]


def reviews(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)

    def bar(n, share):
        track = c.frame("Шкала", "horizontal", [c.rect("Доля", 10, 6, c.s["primary"], 3)], h=6, radius=3,
                        fill=c.s["surfaceContainerHighest"], sizing_h="fill")
        track.children[0].w = c.d(140 * share)  # доля от дорожки (самая узкая — на маленьком телефоне)
        return _row(c, [c.text(str(n), 13, c.s["onSurfaceVariant"], name="Звёзды"), track], f"Оценка {n}", 8)
    summary = _row(c, [_col(c, [c.text("4,8", 48, c.s["onSurface"], 500, "Средняя"), _rating(s, ap),
                                c.text("2 100 отзывов", 13, c.s["onSurfaceVariant"], name="Всего")], "Итог", 4,
                            sizing_h="hug"),
                       _col(c, [bar(5, .8), bar(4, .12), bar(3, .05), bar(2, .02), bar(1, .01)], "Шкалы", 6)],
                   "Сводка", 20)

    def review(name, when, text):
        return _col(c, [_row(c, [_initials(c, name[:1], 36),
                                 _col(c, [_text(c, name, 15, c.s["onSurface"], 500, "Имя"),
                                          _text(c, when, 12, c.s["onSurfaceVariant"], name="Когда")], "Автор", 2),
                                 _rating(s, ap)], "Шапка"), _text(c, text, 15, c.s["onSurface"], name="Текст")],
                    f"Отзыв {name}", 8)
    kids = [summary, _chips(c, s, ap, ["Все", "С фото", "5 звёзд", "Критические"]),
            review("Анна", "2 дня назад", "Пицца горячая, доставили за 20 минут. Буду заказывать ещё!"),
            review("Олег", "неделю назад", "Вкусно, но курьер не нашёл подъезд — позвонил, всё решили."),
            review("Мария", "2 недели назад", "Любимое место: всегда стабильно и вежливые курьеры.")]
    return [_top_bar(s, ap, "Отзывы", back=True), _content(c, s, kids, 64, 0, gap=16)]


def edit_profile(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    avatar = c.frame("Фото профиля", "horizontal",
                     [c.icon(48, color=c.s["onPrimaryContainer"], glyph="person")], w=112, h=112, radius=56,
                     fill=c.s["primaryContainer"], main_align="center", cross_align="center")
    kids = [_row_center(c, [avatar]), _row_center(c, [_button(s, ap, "m3_button_text", "Изменить фото", False)]),
            _field(c, s, ap, "Имя: Анна"), _field(c, s, ap, "Фамилия: Смирнова"),
            _field(c, s, ap, "Электронная почта", "На неё придут чеки"), _fill(_b(s, ap, "m3_phone_field")),
            _hinted(_b(s, ap, "m3_date_field"), "Дата рождения", "12.04.1995"),
            c.rect("Отступ", 10, 12, "", sizing_h="fill"),
            _button(s, ap, "m3_button_filled", "Сохранить")]
    return [_top_bar(s, ap, "Профиль", back=True), _content(c, s, kids, 64, 0, gap=14)]


# ---------------- сервисные ----------------

def help_center(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    search = _fill(_b(s, ap, "m3_search_bar"))
    _set_text(search, "Плейсхолдер", "Поиск по вопросам")
    qa = []
    for q, a in (("Как вернуть заказ?", "Оформите возврат в разделе «Заказы» в течение 14 дней — курьер заберёт товар."),
                 ("Когда придут деньги?", "Возврат на карту — от 1 до 5 рабочих дней."),
                 ("Как сменить адрес?", "Откройте «Профиль → Адреса» и выберите основной.")):
        acc = _b(s, ap, "m3_accordion")
        acc.sizing_h = "fill"
        texts = [d for d in tree.descendants(acc) if d.type == "text"]
        if texts:
            texts[0].text = q
        if len(texts) > 1:
            texts[1].text = a
        qa.append(acc)
    kids = [_text(c, "Чем помочь?", 26, c.s["onSurface"], 400, "Заголовок"), search,
            _section(c, "Частые вопросы")] + qa + [
        _section(c, "Связаться с нами"),
        _icon_row(c, "chat", "Чат с поддержкой", "Ответим за 2 минуты"),
        _icon_row(c, "call", "8 800 555-35-35", "Бесплатно по России")]
    return [_top_bar(s, ap, "Помощь", back=True), _content(c, s, kids, 64, 0, gap=14)]


def notes(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    colors = ("primaryContainer", "secondaryContainer", "tertiaryContainer", "surfaceContainerHigh")
    items = []
    for i, (t, body) in enumerate((("Покупки", "Молоко, хлеб, яблоки, сыр"), ("Идеи", "Приложение для заметок с "
                                                                                          "голосовым вводом"),
                                    ("Встреча", "Пятница, 15:00 — обсудить макеты"), ("Книги", "«Дюна», «Солярис»"),
                                    ("Спорт", "Пн, Ср, Пт — зал"), ("Путешествие", "Билеты в Казань на май"))):
        items.append(c.frame(f"Заметка «{t}»", "vertical",
                             [_text(c, t, 16, c.s["onSurface"], 500, "Заголовок"),
                              _text(c, body, 13, c.s["onSurfaceVariant"], name="Текст")],
                             pad_l=14, pad_r=14, pad_t=14, pad_b=14, gap=6, radius=16, fill=c.s[colors[i % 4]],
                             sizing_h="fill", sizing_v="hug"))
    grid = c.frame("Заметки", "grid", items, grid_columns=2, gap=12, row_gap=12, sizing_h="fill", sizing_v="hug")
    search = _fill(_b(s, ap, "m3_search_bar"))
    _set_text(search, "Плейсхолдер", "Найти заметку")
    fab = _b(s, ap, "m3_fab")
    fab.x, fab.y = s.width - c.d(16 + 56), s.height - c.d(80 + 16 + 56)
    return [_top_bar(s, ap, "Заметки"), _content(c, s, [search, grid], 64, 80, gap=16), fab,
            _nav(s, ap, "notes", 0)]


def tasks(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    prog = _progress(s, ap, c, 3 / 7)
    head = _card(c, "Прогресс", [_text(c, "3 из 7 задач выполнено", 16, c.s["onSurface"], 500, "Заголовок"), prog],
                 "secondaryContainer")
    items = []
    for t, done in (("Позвонить в банк", True), ("Отправить макеты", True), ("Купить подарок", True),
                    ("Записаться к врачу", False), ("Оплатить интернет", False), ("Прочитать главу книги", False),
                    ("Разобрать почту", False)):
        cb = _b(s, ap, "m3_checkbox")
        _set_text(cb, "Подпись", t)
        cb.sizing_h = "fill"
        for d in tree.descendants(cb):  # длинная подпись переносится, а не вылезает
            if d.type == "text":
                d.sizing_h = "fill"
        if not done:  # невыполненная: пустой квадрат без галочки
            for d in [x for x, _, _ in tree.walk([cb])]:
                if d.type == "vector":
                    d.visible = False
                if d.is_frame and d.fill and d is not cb:
                    d.fill, d.stroke, d.stroke_width = "", c.s["onSurfaceVariant"], c.d(2)
        items.append(cb)
    fab = _b(s, ap, "m3_fab")
    fab.x, fab.y = s.width - c.d(16 + 56), s.height - c.d(80 + 16 + 56)
    return [_top_bar(s, ap, "Задачи"), _content(c, s, [head, _section(c, "Сегодня")] + items, 64, 80, gap=4),
            fab, _nav(s, ap, "notes", 1)]


def weather(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)

    def hour(t, deg, glyph):
        return c.frame(f"Час {t}", "vertical", [c.text(t, 13, c.s["onSurfaceVariant"], name="Время"),
                                                c.icon(28, color=c.s["primary"], glyph=glyph),
                                                c.text(deg, 15, c.s["onSurface"], 500, "Градусы")],
                       pad_l=12, pad_r=12, pad_t=12, pad_b=12, gap=6, radius=20, fill=c.s["surfaceContainerLow"],
                       cross_align="center", sizing_h="hug", sizing_v="hug")
    hours = c.frame("По часам", "horizontal", [hour(t, d, g) for t, d, g in (
        ("Сейчас", "+12°", "wb_sunny"), ("15:00", "+13°", "wb_sunny"), ("16:00", "+12°", "partly_cloudy_day"),
        ("17:00", "+10°", "cloud"), ("18:00", "+9°", "rainy"), ("19:00", "+8°", "rainy"))],
                    gap=8, sizing_h="fill", sizing_v="hug", scroll="horizontal", clip=True)
    days = [_icon_row(c, g, d, w, t) for d, w, t, g in (
        ("Завтра", "Облачно", "+11° / +5°", "cloud"), ("Пятница", "Дождь", "+9° / +4°", "rainy"),
        ("Суббота", "Солнечно", "+14° / +6°", "wb_sunny"), ("Воскресенье", "Переменная облачность", "+13° / +7°",
                                                            "partly_cloudy_day"))]
    kids = [_centered(c, "Москва", 20, c.s["onSurface"], 500, "Город"),
            _row_center(c, [c.icon(96, color=c.s["primary"], glyph="wb_sunny")]),
            _centered(c, "+12°", 72, c.s["onSurface"], 300, "Температура"),
            _centered(c, "Ясно · ощущается как +10°", 15, c.s["onSurfaceVariant"], name="Описание"),
            hours, _section(c, "На неделю")] + days
    return [_content(c, s, kids, 24, 0, gap=14)]


def article(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    author = _row(c, [_initials(c, "МИ", 40),
                      _col(c, [_text(c, "Мария Иванова", 15, c.s["onSurface"], 500, "Автор"),
                               _text(c, "28 октября · 6 мин чтения", 13, c.s["onSurfaceVariant"], name="Дата")],
                           "Автор", 2), _glyph(_b(s, ap, "m3_icon_button"), "bookmark")], "Автор")
    para = ("Хороший интерфейс незаметен: человек решает свою задачу и не думает о кнопках. Для этого важны "
            "понятные подписи, достаточные размеры касания и честные состояния — загрузка, пусто, ошибка.")
    kids = [_chips(c, s, ap, ["Дизайн"], 0), _text(c, "Как сделать приложение, которым приятно пользоваться", 26,
                                                     c.s["onSurface"], 500, "Заголовок"),
            author, _photo(c, "Иллюстрация", "palette", 200), _text(c, para, 16, c.s["onSurface"], name="Абзац"),
            _text(c, "Начните с главного сценария", 20, c.s["onSurface"], 500, "Подзаголовок"),
            _text(c, "Опишите, что человек делает чаще всего, и сделайте этот путь самым коротким. Остальное — "
                     "во вторую очередь.", 16, c.s["onSurface"], name="Абзац")]
    return [_top_bar(s, ap, "Статья", back=True), _content(c, s, kids, 64, 0, gap=16)]


def course(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    prog = _progress(s, ap, c, 3 / 12)

    def lesson(n, t, d, state):
        glyph, bg = {"done": ("check", "primaryContainer"), "next": ("play_arrow", "primary"),
                     "lock": ("lock", "surfaceContainerHighest")}[state]
        fg = {"done": "onPrimaryContainer", "next": "onPrimary", "lock": "onSurfaceVariant"}[state]
        return _row(c, [_icon_box(c, glyph, bg, fg), _col(c, [
            _text(c, f"{n}. {t}", 16, c.s["onSurface" if state != "lock" else "onSurfaceVariant"], 500, "Название"),
            _text(c, d, 13, c.s["onSurfaceVariant"], name="Длительность")], "Текст", 2)], f"Урок {n}")
    kids = [_photo(c, "Обложка", "school", 170, "primaryContainer", "onPrimaryContainer"),
            _text(c, "Основы дизайна интерфейсов", 24, c.s["onSurface"], 500, "Название"),
            _text(c, "12 уроков · 4 часа · сертификат", 14, c.s["onSurfaceVariant"], name="Детали"),
            _card(c, "Прогресс", [_text(c, "Пройдено 3 из 12", 15, c.s["onSurface"], 500, "Текст"), prog]),
            _section(c, "Уроки"),
            lesson(1, "Что такое интерфейс", "12 мин", "done"), lesson(2, "Сетки и отступы", "18 мин", "done"),
            lesson(3, "Цвет и контраст", "21 мин", "done"), lesson(4, "Типографика", "16 мин", "next"),
            lesson(5, "Компоненты", "24 мин", "lock"), _button(s, ap, "m3_button_filled", "Продолжить урок 4")]
    return [_top_bar(s, ap, "Курс", back=True), _content(c, s, kids, 64, 0, gap=14)]


def smart_home(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)

    def device(glyph, t, st, on):
        sw = _b(s, ap, "m3_switch")
        label = next((d for d in sw.children if d.type == "text"), None)
        if label is not None:
            sw.children.remove(label)
        sw.sizing_h, sw.w = "hug", c.d(52)
        if not on:
            from app.engines.preview import live
            live._switch(sw, False, c.s, c.k)
            for d in tree.descendants(sw):  # бегунок прижат к началу дорожки (раскладка не вернёт его вправо)
                if d.is_frame and d.children and d.children[0].type == "ellipse":
                    d.main_align = "start"
        return c.frame(f"Устройство «{t}»", "vertical",
                       [_row(c, [_icon_box(c, glyph, "primaryContainer" if on else "surfaceContainerHighest",
                                           "onPrimaryContainer" if on else "onSurfaceVariant"),
                                 c.rect("Отступ", 10, 10, "", sizing_h="fill"), sw], "Шапка"),
                        _text(c, t, 16, c.s["onSurface"], 500, "Название"),
                        _text(c, st, 13, c.s["onSurfaceVariant"], name="Состояние")],
                       pad_l=14, pad_r=14, pad_t=14, pad_b=14, gap=8, radius=20,
                       fill=c.s["secondaryContainer" if on else "surfaceContainerLow"], sizing_h="fill",
                       sizing_v="hug")
    grid = c.frame("Устройства", "grid", [device("lightbulb", "Свет", "Включён · 80%", True),
                                          device("thermostat", "Отопление", "22°", True),
                                          device("tv", "Телевизор", "Выключен", False),
                                          device("air", "Очиститель", "Авто", True),
                                          device("lock", "Замок", "Закрыт", False),
                                          device("speaker", "Колонка", "Выключена", False)],
                   grid_columns=2, gap=12, row_gap=12, sizing_h="fill", sizing_v="hug")
    kids = [_text(c, "Мой дом", 26, c.s["onSurface"], 400, "Заголовок"),
            _row(c, [_stat(c, "22°", "в доме"), _stat(c, "45%", "влажность"), _stat(c, "3", "включено")],
                 "Сводка", 8), _chips(c, s, ap, ["Все", "Гостиная", "Спальня", "Кухня"]), grid]
    return [_top_bar(s, ap, "Дом"), _content(c, s, kids, 64, 80, gap=16), _nav(s, ap, "home", 0)]


def permission(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    kids = [c.rect("Отступ", 10, 96, "", sizing_h="fill"),
            _row_center(c, [_big_icon(c, "notifications_active", "secondaryContainer", "onSecondaryContainer",
                                      160, 80)]),
            c.rect("Отступ", 10, 16, "", sizing_h="fill"),
            _centered(c, "Не пропускайте важное", 26, c.s["onSurface"], 400, "Заголовок"),
            _centered(c, "Разрешите уведомления — сообщим о статусе заказа и личных скидках. Отключить можно "
                         "в любой момент.", 15, c.s["onSurfaceVariant"], name="Описание"),
            c.rect("Отступ", 10, 32, "", sizing_h="fill"),
            _button(s, ap, "m3_button_filled", "Разрешить"), _button(s, ap, "m3_button_text", "Не сейчас")]
    return [_content(c, s, kids, 0, gap=12)]


def event(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    price = _row(c, [_col(c, [_text(c, "от 1 800 ₽", 22, c.s["onSurface"], 600, "Цена"),
                              _text(c, "осталось 42 билета", 13, c.s["error"], name="Наличие")], "Цена", 2),
                     _button(s, ap, "m3_button_filled", "Купить билет", False)], "Билеты")
    kids = [_photo(c, "Афиша", "music_note", 220, "tertiaryContainer", "onTertiaryContainer"),
            _chips(c, s, ap, ["Концерт"], 0),
            _text(c, "Джаз под звёздами", 26, c.s["onSurface"], 500, "Название"),
            _icon_row(c, "calendar_month", "15 ноября, суббота", "Начало в 19:00"),
            _icon_row(c, "location_on", "Концертный зал «Зарядье»", "ул. Варварка, 6"),
            _icon_row(c, "group", "Пойдут 1 240 человек", "Среди них 3 ваших друга"),
            _text(c, "Вечер классического джаза под открытым небом: квартет Игоря Бутмана и гости.", 15,
                  c.s["onSurfaceVariant"], name="Описание"), price]
    return [_top_bar(s, ap, "Событие", back=True), _content(c, s, kids, 64, 0, gap=14)]


TEMPLATES = {
    "catalog": ("Каталог", catalog), "bank_home": ("Банк", bank_home), "transfer": ("Перевод", transfer), "history": ("История операций", history),
    "payment_success": ("Оплата прошла", payment_success), "restaurants": ("Рестораны", restaurants),
    "restaurant": ("Ресторан", restaurant), "orders": ("Мои заказы", orders), "workout": ("Тренировка", workout),
    "activity": ("Активность", activity), "trip_search": ("Поиск билетов", trip_search), "hotel": ("Отель", hotel),
    "boarding_pass": ("Посадочный талон", boarding_pass), "interests": ("Интересы", interests),
    "paywall": ("Подписка", paywall), "payment_methods": ("Способы оплаты", payment_methods),
    "reviews": ("Отзывы", reviews), "edit_profile": ("Редактирование профиля", edit_profile),
    "help": ("Помощь", help_center), "notes": ("Заметки", notes), "tasks": ("Задачи", tasks),
    "weather": ("Погода", weather), "article": ("Статья", article), "course": ("Курс", course),
    "smart_home": ("Умный дом", smart_home), "permission": ("Разрешение", permission), "event": ("Событие", event),
}

# Готовые приложения: (название, экраны по порядку, вид меню, экран каждого пункта меню (None — без перехода),
# переходы по нажатию: (экран, что нажать, куда)). «Что нажать» — имя элемента, «text:подпись» (кнопка или
# элемент с этой надписью) или «role:роль» (первый компонент этой роли).
APPS = {
    "food": ("Доставка еды", ["restaurants", "restaurant", "cart", "checkout", "tracking", "orders", "profile"],
             "food", [0, 5, 2, 6],
             [(0, "Ресторан «Додо Пицца»", 1), (1, "role:m3.fab_extended", 2), (2, "text:Оформить заказ", 3),
              (3, "text:Далее", 4)]),
    "bank": ("Банк", ["bank_home", "transfer", "payment_success", "history", "profile"], "bank", [0, 3, 1, 4],
             [(0, "Действие «Перевести»", 1), (1, "text:Перевести 1 500 ₽", 2), (2, "text:Готово", 0)]),
    "travel": ("Путешествия", ["trip_search", "hotel", "payment_methods", "boarding_pass", "profile"], "travel",
               [0, 3, 1, 4],
               [(0, "Направление «Сочи»", 1), (1, "text:Забронировать", 2), (2, "text:Оплатить 12 400 ₽", 3)]),
    "fitness": ("Фитнес", ["workout", "activity", "course", "profile"], "fit", [0, 1, 2, 3],
                [(0, "text:Начать", 2)]),
    "shop": ("Магазин", ["catalog", "product", "cart", "checkout", "orders", "profile"], "shop", [0, 4, 2, 5],
             [(0, "role:m3.product_card", 1), (1, "text:В корзину — 2 990 ₽", 2), (2, "text:Оформить заказ", 3),
              (3, "text:Далее", 4)]),
}


# надписи под тему приложения на общих экранах (корзина и оформление взяты из магазина)
TEXTS = {
    "food": {"cart": {"Наушники": "Маргарита", "Чехол": "Пепперони", "Кабель USB-C": "Морс клюквенный",
                      "2 990 ₽": "590 ₽", "590 ₽": "690 ₽", "690 ₽": "190 ₽", "4 270 ₽": "1 470 ₽"},
             "checkout": {"4 270 ₽": "1 470 ₽", "Дата доставки": "Время доставки", "12.11.2026": "Как можно скорее"}},
    "shop": {"orders": {"Додо Пицца": "Беспроводные наушники Pro", "Бургер Клаб": "Чехол для телефона",
                        "Суши Мастер": "Кабель USB-C"}},
    "fitness": {"course": {"Курс": "Программа", "Основы дизайна интерфейсов": "Сильная спина за 4 недели",
                           "12 уроков · 4 часа · сертификат": "12 тренировок · 4 недели · дома без инвентаря",
                           "Уроки": "Тренировки", "1. Что такое интерфейс": "1. Знакомство и разминка",
                           "2. Сетки и отступы": "2. Мышцы кора", "3. Цвет и контраст": "3. Растяжка спины",
                           "4. Типографика": "4. Планка и баланс", "5. Компоненты": "5. Силовая база",
                           "Продолжить урок 4": "Продолжить тренировку 4", "__icons__": {"Обложка": "fitness_center"}}},
    "travel": {"trip_search": {"Куда: Санкт-Петербург": "Куда: Сочи"},
               "hotel": {"Гранд Отель «Европа»": "Отель «Морской бриз»", "Невский проспект, 1": "Курортный проспект, 75",
                         "5 минут до метро": "2 минуты до моря",
                         "Исторический отель в центре города: просторные номера, ресторан с видом на Неву и "
                         "спа-центр.": "Отель у моря: номера с балконами, ресторан на набережной и открытый бассейн."},
               "payment_methods": {"Оплатить 1 280 ₽": "Оплатить 12 400 ₽", "Наличными": "При заселении",
                                   "Курьеру при получении": "Оплата на стойке отеля"},
               "boarding_pass": {"LED": "AER", "Санкт-Петербург": "Сочи", "10:05": "11:20",
                                 "Аэрофлот · SU 30": "Аэрофлот · SU 1120"}},
}


def localize(screen: Screen, app_key: str, template_key: str) -> None:
    """Заменить надписи экрана под приложение (каждая надпись — один раз, без цепочек замен)."""
    table = TEXTS.get(app_key, {}).get(template_key)
    if not table:
        return
    icons = table.get("__icons__", {})
    for n, _, _ in tree.walk(screen.nodes):
        if n.type == "text" and n.text in table:
            n.text = table[n.text]
        elif n.name in icons:
            _glyph(n, icons[n.name])



def find_target(screen: Screen, what: str) -> Node | None:
    """Элемент для перехода по описанию из APPS: имя, «text:надпись» или «role:роль»."""
    nodes = [n for n, _, _ in tree.walk(screen.nodes)]
    if what.startswith("role:"):
        return next((n for n in nodes if n.role == what[5:]), None)
    if what.startswith("text:"):
        label = what[5:]
        for n in nodes:  # кнопка или другой элемент, внутри которого эта надпись (самый внутренний)
            if n.is_container and n.role and any(d.type == "text" and d.text == label for d in tree.descendants(n)):
                inner = [x for x in tree.descendants(n) if x.is_container and x.role and
                         any(d.type == "text" and d.text == label for d in tree.descendants(x))]
                return inner[-1] if inner else n
        return next((n for n in nodes if n.type == "text" and n.text == label), None)
    return next((n for n in nodes if n.name == what), None)
