"""Готовые экраны (версия 1.9): приветствие, главная со сводкой, товар, оформление заказа, поиск, плеер,
уведомления, кошелёк, заставка, нет интернета, отслеживание заказа. Без Qt.

Те же правила, что у первых готовых экранов: компоненты Material 3 и варианты из галереи, содержимое —
контейнер столбцом с прокруткой, панели — в слотах Scaffold при выгрузке в Android.
"""

from __future__ import annotations

from app.core.document import tree
from app.core.document.model import Node, Screen
from app.libraries import components
from app.libraries.components import _Ctx
from app.libraries.screen_templates import _content, _fill, _list_item, _set_text, _text, _top_bar


def _b(s, ap, kind: str) -> Node:
    return components.build(kind, s, ap)


def _place(n: Node, x: float, y: float) -> Node:
    dx, dy = x - n.x, y - n.y
    for d, _, _ in tree.walk([n]):
        d.x, d.y = round(d.x + dx, 2), round(d.y + dy, 2)
    return n


def _centered(c: _Ctx, t: str, size: float, color: str, weight: int = 400, name: str = "Текст") -> Node:
    n = _text(c, t, size, color, weight, name)
    n.align = "center"
    return n


def _big_icon(c: _Ctx, glyph: str, bg: str, fg: str, side: float = 120, icon: float = 56) -> Node:
    return c.frame("Иллюстрация", "horizontal", [c.icon(icon, color=c.s[fg], glyph=glyph)], w=side, h=side,
                   radius=side / 2, fill=c.s[bg], main_align="center", cross_align="center")


def _row_center(c: _Ctx, kids: list[Node], name: str = "Ряд") -> Node:
    return c.frame(name, "horizontal", kids, main_align="center", cross_align="center", sizing_h="fill",
                   sizing_v="hug")


def onboarding(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    nxt = _fill(_b(s, ap, "m3_button_filled"))
    _set_text(nxt, "Подпись", "Далее")
    skip = _b(s, ap, "m3_button_text")
    _set_text(skip, "Подпись", "Пропустить")
    kids = [c.rect("Отступ", 10, 72, "", sizing_h="fill"),
            _row_center(c, [_big_icon(c, "rocket_launch", "primaryContainer", "onPrimaryContainer", 200, 96)]),
            c.rect("Отступ", 10, 24, "", sizing_h="fill"),
            _centered(c, "Всё под рукой", 28, c.s["onSurface"], 400, "Заголовок"),
            _centered(c, "Заказывайте, отслеживайте доставку и получайте бонусы — в одном приложении", 16,
                      c.s["onSurfaceVariant"], name="Описание"),
            _row_center(c, [_b(s, ap, "m3_page_dots")]), c.rect("Отступ", 10, 24, "", sizing_h="fill"), nxt,
            _row_center(c, [skip])]
    return [_content(c, s, kids, 0, gap=16)]


def home(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    hello = c.frame("Приветствие", "horizontal",
                    [c.frame("Текст", "vertical", [_text(c, "Доброе утро,", 14, c.s["onSurfaceVariant"], name="Строка"),
                                                   _text(c, "Анна", 24, c.s["onSurface"], 500, "Имя")],
                             gap=0, sizing_h="fill", sizing_v="hug"), _b(s, ap, "m3_avatar")],
                    cross_align="center", sizing_h="fill", sizing_v="hug")
    search = _fill(_b(s, ap, "m3_search_bar"))

    def tile(glyph, t, v, bg, fg):
        return c.frame(f"Плитка «{t}»", "vertical",
                       [c.icon(24, color=c.s[fg], glyph=glyph), c.text(v, 22, c.s[fg], 600, "Значение"),
                        c.text(t, 12, c.s[fg], name="Подпись")],
                       pad_l=16, pad_r=16, pad_t=16, pad_b=16, gap=6, radius=20, fill=c.s[bg], sizing_h="fill",
                       sizing_v="hug")
    tiles = c.frame("Сводка", "horizontal", [tile("directions_walk", "Шаги", "8 420", "primaryContainer",
                                                  "onPrimaryContainer"),
                                             tile("local_fire_department", "Ккал", "512", "tertiaryContainer",
                                                  "onTertiaryContainer")],
                    gap=12, sizing_h="fill", sizing_v="hug")
    chips = c.frame("Быстрые действия", "horizontal", [_b(s, ap, "m3_chip_suggestion"), _b(s, ap, "m3_chip_assist")],
                    gap=8, sizing_h="fill", sizing_v="hug")
    _set_text(chips.children[0], "Подпись", "Кафе рядом")
    _set_text(chips.children[1], "Подпись", "План")
    title = _text(c, "Рекомендации", 22, c.s["onSurface"], name="Раздел")
    kids = [hello, search, tiles, chips, title, _fill(_b(s, ap, "m3_carousel")),
            _list_item(s, ap, "Утренняя пробежка", "Завтра, 7:00 · 5 км")]
    return [_content(c, s, kids, 0, 80, gap=16), _b(s, ap, "m3_nav_bar")]


def product(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    photo = c.frame("Фото товара", "horizontal", [c.icon(72, color=c.s["onSurfaceVariant"], glyph="headphones")],
                    h=280, radius=28, fill=c.s["surfaceContainerHighest"], main_align="center", cross_align="center",
                    sizing_h="fill")
    seg = _b(s, ap, "m3_segmented")
    for i, t in enumerate(("Чёрный", "Белый", "Синий")):
        _set_text(seg, "Подпись", t, i)
    buy = _fill(_b(s, ap, "m3_button_filled"))
    _set_text(buy, "Подпись", "В корзину — 2 990 ₽")
    kids = [photo, _row_center(c, [_b(s, ap, "m3_page_dots")]),
            _text(c, "Беспроводные наушники Pro", 24, c.s["onSurface"], name="Название"),
            _b(s, ap, "m3_rating"), _b(s, ap, "m3_price"), seg,
            _text(c, "Активное шумоподавление, 30 часов работы, быстрая зарядка за 10 минут.", 14,
                  c.s["onSurfaceVariant"], name="Описание"),
            _fill(_b(s, ap, "m3_accordion")), buy]
    return [_top_bar(s, ap, "Товар", back=True), _content(c, s, kids, 64, gap=14)]


def checkout(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    steps = _fill(_b(s, ap, "m3_steps"))
    addr = _fill(_b(s, ap, "m3_text_field"))
    _set_text(addr, "Плейсхолдер", "Адрес доставки")
    _set_text(addr, "Подсказка", "Улица, дом, квартира")
    date = _fill(_b(s, ap, "m3_date_field"))
    radio = _fill(_b(s, ap, "m3_radio"))
    for i, t in enumerate(("Картой онлайн", "Наличными курьеру", "СБП")):
        _set_text(radio, "Подпись", t, i)
    total = c.frame("Итого", "horizontal", [_text(c, "К оплате", 18, c.s["onSurface"], 500, "Подпись"),
                                             c.text("3 680 ₽", 22, c.s["onSurface"], 600, "Сумма")],
                    cross_align="center", sizing_h="fill", sizing_v="hug")
    kids = [steps, _text(c, "Доставка", 16, c.s["primary"], 500, "Раздел"), addr, date,
            _text(c, "Оплата", 16, c.s["primary"], 500, "Раздел"), radio, _fill(_b(s, ap, "m3_divider")), total]
    return [_top_bar(s, ap, "Оформление", back=True), _content(c, s, kids, 64, 72, gap=12),
            _b(s, ap, "m3_bottom_actions")]


def search(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    bar = _fill(_b(s, ap, "m3_search_bar"))
    _set_text(bar, "Плейсхолдер", "Кроссовки")
    chips = c.frame("Фильтры", "horizontal", [_b(s, ap, "m3_chip_filter"), _b(s, ap, "m3_chip_assist"),
                                              _b(s, ap, "m3_chip_suggestion")],
                    gap=8, sizing_h="fill", sizing_v="hug", scroll="horizontal")
    _set_text(chips.children[0], "Подпись", "До 5 000 ₽")
    _set_text(chips.children[1], "Подпись", "Рядом")
    _set_text(chips.children[2], "Подпись", "Со скидкой")
    found = _text(c, "Найдено 128 товаров", 14, c.s["onSurfaceVariant"], name="Итог")
    grid = c.frame("Результаты", "horizontal", [_b(s, ap, "m3_product_card"), _b(s, ap, "m3_product_card")],
                   gap=12, sizing_h="fill", sizing_v="hug")
    for card in grid.children:
        card.sizing_h = "fill"
    return [_content(c, s, [bar, chips, found, grid], 0, 80, gap=12), _b(s, ap, "m3_nav_bar")]


def player(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    cover = c.frame("Обложка", "horizontal", [c.icon(96, color=c.s["onPrimaryContainer"], glyph="music_note")],
                    h=320, radius=28, fill=c.s["primaryContainer"], main_align="center", cross_align="center",
                    sizing_h="fill")
    slider = _fill(_b(s, ap, "m3_slider"))
    times = c.frame("Время", "horizontal", [c.text("1:24", 12, c.s["onSurfaceVariant"], name="Прошло"),
                                           c.text("3:41", 12, c.s["onSurfaceVariant"], name="Всего")],
                    main_align="space_between", sizing_h="fill", sizing_v="hug")

    def ctrl(glyph, size, big=False):
        if big:
            return c.frame("Пауза", "horizontal", [c.icon(36, color=c.s["onPrimary"], glyph=glyph)], w=72, h=72,
                           radius=24, fill=c.s["primary"], main_align="center", cross_align="center")
        return c.icon(size, color=c.s["onSurface"], glyph=glyph)
    controls = _row_center(c, [ctrl("shuffle", 24), ctrl("skip_previous", 32), ctrl("pause", 0, True),
                               ctrl("skip_next", 32), ctrl("repeat", 24)], "Управление")
    controls.gap = c.d(24)
    kids = [cover, _text(c, "Ночной город", 24, c.s["onSurface"], 500, "Трек"),
            _text(c, "Северное сияние", 16, c.s["onSurfaceVariant"], name="Исполнитель"), slider, times, controls]
    return [_top_bar(s, ap, "Сейчас играет", back=True), _content(c, s, kids, 64, gap=12)]


def notifications(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    tabs = _b(s, ap, "m3_segmented")
    for i, t in enumerate(("Все", "Заказы", "Акции")):
        _set_text(tabs, "Подпись", t, i)
    items = []
    for t, d, ago in (("Заказ передан курьеру", "Привезём сегодня с 18:00 до 20:00", "5 мин назад"),
                      ("Скидка 20% на обувь", "Только до воскресенья", "1 ч назад"),
                      ("Новый вход в аккаунт", "Москва, Android", "вчера")):
        n = _fill(_b(s, ap, "m3_notification_item"))
        n.pad_l = n.pad_r = 0
        _set_text(n, "Заголовок", t)
        _set_text(n, "Подпись", d)
        _set_text(n, "Время", ago)
        items.append(n)
    return [_top_bar(s, ap, "Уведомления", back=True), _content(c, s, [tabs] + items, 64, gap=8)]


def wallet(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    card = c.frame("Баланс", "vertical",
                   [_text(c, "Баланс", 14, c.s["onPrimary"], name="Подпись"),
                    _text(c, "48 250,00 ₽", 32, c.s["onPrimary"], 600, "Сумма"),
                    _text(c, "•••• 4821", 14, c.s["onPrimary"], name="Карта")],
                   pad_l=20, pad_r=20, pad_t=20, pad_b=20, gap=6, radius=24, fill=c.s["primary"], sizing_h="fill",
                   sizing_v="hug")
    card.gradient, card.fill2, card.grad_angle, card.elevation = "linear", c.s["tertiary"], 135, 2

    def action(glyph, t):
        return c.frame(f"Действие «{t}»", "vertical",
                       [c.frame("Значок", "horizontal", [c.icon(24, color=c.s["onSecondaryContainer"], glyph=glyph)],
                                w=56, h=56, radius=28, fill=c.s["secondaryContainer"], main_align="center",
                                cross_align="center"),
                        c.text(t, 12, c.s["onSurface"], name="Подпись")],
                       gap=6, cross_align="center", sizing_h="fill", sizing_v="hug")
    actions = c.frame("Действия", "horizontal", [action("send", "Перевести"), action("add", "Пополнить"),
                                                  action("qr_code_scanner", "Оплатить"), action("history", "История")],
                      sizing_h="fill", sizing_v="hug")
    ops = [_list_item(s, ap, t, d) for t, d in (("Кофейня «Зерно»", "−240 ₽ · сегодня"),
                                                ("Перевод от Ивана", "+5 000 ₽ · вчера"),
                                                ("Такси", "−560 ₽ · вчера"))]
    kids = [card, actions, _text(c, "Операции", 20, c.s["onSurface"], name="Раздел")] + ops
    return [_top_bar(s, ap, "Кошелёк"), _content(c, s, kids, 64, 80, gap=16), _b(s, ap, "m3_nav_bar")]


def splash(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    logo = _big_icon(c, "bolt", "primary", "onPrimary", 120, 64)
    logo.radius = c.d(36)
    load = _b(s, ap, "m3_loading_indicator")
    kids = [c.rect("Отступ", 10, 10, "", sizing_h="fill", sizing_v="fill"), _row_center(c, [logo]),
            _centered(c, "Молния", 32, c.s["onSurface"], 600, "Название"),
            _centered(c, "Быстрая доставка за 15 минут", 14, c.s["onSurfaceVariant"], name="Слоган"),
            c.rect("Отступ", 10, 10, "", sizing_h="fill", sizing_v="fill"), _row_center(c, [load])]
    return [_content(c, s, kids, 0, gap=12)]


def offline(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    retry = _b(s, ap, "m3_button_filled")
    _set_text(retry, "Подпись", "Повторить")
    kids = [c.rect("Отступ", 10, 10, "", sizing_h="fill", sizing_v="fill"),
            _row_center(c, [_big_icon(c, "wifi_off", "errorContainer", "onErrorContainer")]),
            _centered(c, "Нет подключения", 24, c.s["onSurface"], 500, "Заголовок"),
            _centered(c, "Проверьте Wi-Fi или мобильный интернет и попробуйте ещё раз", 14,
                      c.s["onSurfaceVariant"], name="Текст"),
            _row_center(c, [retry]), c.rect("Отступ", 10, 10, "", sizing_h="fill", sizing_v="fill")]
    return [_content(c, s, kids, 0, gap=16)]


def tracking(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    mp = c.frame("Карта", "horizontal", [c.icon(56, color=c.s["onSecondaryContainer"], glyph="map")], h=220,
                 radius=24, fill=c.s["secondaryContainer"], main_align="center", cross_align="center",
                 sizing_h="fill")
    eta = c.frame("Прибытие", "vertical", [_text(c, "Курьер будет через", 14, c.s["onSurfaceVariant"], name="Подпись"),
                                           _text(c, "12 минут", 32, c.s["onSurface"], 600, "Время")],
                  gap=2, sizing_h="fill", sizing_v="hug")
    steps = _fill(_b(s, ap, "m3_steps"))
    for i, t in enumerate(("Собран", "В пути", "Доставлен")):
        _set_text(steps, "Подпись", t, i)
    courier = _fill(_b(s, ap, "m3_profile_header"))
    courier.pad_l = courier.pad_r = 0
    _set_text(courier, "Имя", "Курьер Максим")
    _set_text(courier, "Почта", "Электросамокат · ★ 4,9")
    call = _fill(_b(s, ap, "m3_button_tonal"))
    _set_text(call, "Подпись", "Позвонить курьеру")
    return [_top_bar(s, ap, "Заказ №4821", back=True), _content(c, s, [mp, eta, steps, courier, call], 64, gap=16)]


TEMPLATES = {
    "onboarding": ("Приветствие", onboarding), "home": ("Главная со сводкой", home), "product": ("Товар", product),
    "checkout": ("Оформление заказа", checkout), "search": ("Поиск с фильтрами", search),
    "player": ("Музыкальный плеер", player), "notifications": ("Уведомления", notifications),
    "wallet": ("Кошелёк", wallet), "splash": ("Заставка", splash), "offline": ("Нет интернета", offline),
    "tracking": ("Отслеживание заказа", tracking),
}
