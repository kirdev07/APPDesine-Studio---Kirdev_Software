"""Дополнительные заготовки Android (Material 3), версия 1.7: вход и регистрация, формы, профиль и люди,
магазин, состояния и подсказки. Без Qt.

Кнопки «Войти через …» — нейтральные: буква сервиса в кружке вместо логотипа (логотипы и фирменные цвета
сервисов в проект добавляет команда по их правилам). Корни заготовок несут роль m3.*: для поля пароля экспорт
создаёт настоящее OutlinedTextField с кнопкой «показать», остальное переводится раскладкой (Column / Row).
"""

from __future__ import annotations

from app.core.document.model import Node
from app.libraries.components import ComponentSpec, _button, _Ctx

_A = "android"


def _field_box(c: _Ctx, kids: list[Node], name: str = "Поле", **kw) -> Node:
    kw.setdefault("h", 56)
    return c.frame(name, "horizontal", kids, pad_l=16, pad_r=12, gap=12, radius=4, stroke=c.s["outline"],
                   stroke_width=1, cross_align="center", sizing_h="fill", **kw)


def _labelled(c: _Ctx, name: str, role: str, box: Node, hint: str = "") -> Node:
    kids = [box] + ([c.text(hint, 12, c.s["onSurfaceVariant"], name="Подсказка", sizing_h="fill")] if hint else [])
    return c.frame(name, "vertical", kids, w=320, gap=4, sizing_v="hug", role=role)


# ---------------- вход и регистрация ----------------

def password_field(c: _Ctx) -> Node:
    box = _field_box(c, [c.text("Пароль", 16, c.s["onSurfaceVariant"], name="Плейсхолдер", sizing_h="fill"),
                         c.icon(24, color=c.s["onSurfaceVariant"], glyph="visibility")])
    return _labelled(c, "Поле пароля", "m3.password_field", box, "Не меньше 8 символов")


def phone_field(c: _Ctx) -> Node:
    code = c.frame("Код страны", "horizontal", [c.text("+7", 16, c.s["onSurface"], name="Код"),
                                                c.icon(18, color=c.s["onSurfaceVariant"], glyph="expand_more")],
                   gap=2, cross_align="center", sizing_h="hug", sizing_v="hug")
    sep = c.rect("Черта", 1, 24, c.s["outlineVariant"])
    box = _field_box(c, [code, sep, c.text("Номер телефона", 16, c.s["onSurfaceVariant"], name="Плейсхолдер",
                                           sizing_h="fill")])
    return _labelled(c, "Поле телефона", "m3.phone_field", box, "Отправим код в SMS")


def otp_code(c: _Ctx) -> Node:
    cells = []
    for i, d in enumerate(("4", "7", "", "")):
        cells.append(c.frame(f"Цифра {i + 1}", "horizontal", [c.text(d or " ", 24, c.s["onSurface"], name="Цифра")],
                             w=52, h=60, radius=8, stroke=c.s["primary"] if i == 2 else c.s["outline"],
                             stroke_width=2 if i == 2 else 1, main_align="center", cross_align="center"))
    row = c.frame("Ячейки", "horizontal", cells, gap=12, sizing_h="hug", sizing_v="hug")
    return c.frame("Код из SMS", "vertical",
                   [c.text("Введите код из SMS", 16, c.s["onSurface"], name="Заголовок"), row,
                    c.text("Отправить снова через 0:42", 14, c.s["onSurfaceVariant"], name="Таймер")],
                   gap=12, sizing_h="hug", sizing_v="hug", role="m3.otp_code")


def _service(c: _Ctx, service: str) -> Node:
    badge = c.frame("Значок сервиса", "horizontal", [c.text(service[0], 13, c.s["onSecondaryContainer"], 600,
                                                            "Буква")],
                    w=24, h=24, radius=12, fill=c.s["secondaryContainer"], main_align="center", cross_align="center")
    text = "Войти по номеру телефона" if service == "телефон" else f"Войти через {service}"
    return c.frame(text, "horizontal", [badge, c.label(text, c.s["onSurface"])],
                   x=c.d(16), w=c.width_dp - 32, h=48, gap=12, radius=24, stroke=c.s["outline"], stroke_width=1,
                   main_align="center", cross_align="center", constraint_h="left_right", role="m3.sign_in_service")


def sign_in_google(c: _Ctx) -> Node:
    return _service(c, "Google")


def sign_in_apple(c: _Ctx) -> Node:
    return _service(c, "Apple")


def sign_in_vk(c: _Ctx) -> Node:
    return _service(c, "VK ID")


def sign_in_phone(c: _Ctx) -> Node:
    b = _service(c, "телефон")
    b.children[0] = c.icon(20, color=c.s["primary"], glyph="smartphone")
    return b


def or_divider(c: _Ctx) -> Node:
    line = lambda: c.rect("Линия", 10, 1, c.s["outlineVariant"], sizing_h="fill")  # noqa: E731
    return c.frame("Разделитель «или»", "horizontal", [line(), c.text("или", 14, c.s["onSurfaceVariant"],
                                                                         name="Текст"), line()],
                   w=320, h=24, gap=12, cross_align="center", role="m3.or_divider")


# ---------------- формы ----------------

def dropdown_field(c: _Ctx) -> Node:
    box = _field_box(c, [c.text("Москва", 16, c.s["onSurface"], name="Значение", sizing_h="fill"),
                         c.icon(24, color=c.s["onSurfaceVariant"], glyph="expand_more")])
    return _labelled(c, "Выпадающий список", "m3.dropdown_field", box, "Город доставки")


def date_field(c: _Ctx) -> Node:
    box = _field_box(c, [c.text("12.11.2026", 16, c.s["onSurface"], name="Дата", sizing_h="fill"),
                         c.icon(24, color=c.s["onSurfaceVariant"], glyph="calendar")])
    return _labelled(c, "Поле даты", "m3.date_field", box, "Дата рождения")


def text_area(c: _Ctx) -> Node:
    box = c.frame("Поле", "vertical", [c.text("Расскажите подробнее…", 16, c.s["onSurfaceVariant"],
                                              name="Плейсхолдер", sizing_h="fill")],
                  h=120, pad_l=16, pad_r=16, pad_t=14, pad_b=14, radius=4, stroke=c.s["outline"], stroke_width=1,
                  sizing_h="fill")
    count = c.text("0 / 500", 12, c.s["onSurfaceVariant"], name="Счётчик")
    count.align = "right"
    foot = c.frame("Низ", "horizontal", [count], main_align="end", sizing_h="fill", sizing_v="hug")
    return c.frame("Многострочное поле", "vertical", [box, foot], w=320, gap=4, sizing_v="hug",
                   role="m3.text_area")


def quantity_stepper(c: _Ctx) -> Node:
    def btn(glyph, name):
        return c.frame(name, "horizontal", [c.icon(20, color=c.s["onSurface"], glyph=glyph)], w=40, h=40, radius=20,
                       main_align="center", cross_align="center", fill=c.s["surfaceContainerHighest"])
    return c.frame("Количество", "horizontal",
                   [btn("remove", "Меньше"), c.text("2", 18, c.s["onSurface"], 500, "Число"), btn("add", "Больше")],
                   h=48, gap=16, cross_align="center", sizing_h="hug", role="m3.quantity")


# ---------------- профиль и люди ----------------

def avatar(c: _Ctx) -> Node:
    return c.frame("Аватар", "horizontal", [c.text("АС", 20, c.s["onPrimaryContainer"], 500, "Инициалы")],
                   w=56, h=56, radius=28, fill=c.s["primaryContainer"], main_align="center", cross_align="center",
                   role="m3.avatar")


def avatar_group(c: _Ctx) -> Node:
    kids = []
    for i, (t, bg, fg) in enumerate((("АС", "primaryContainer", "onPrimaryContainer"),
                                     ("ИП", "secondaryContainer", "onSecondaryContainer"),
                                     ("+5", "tertiaryContainer", "onTertiaryContainer"))):
        a = c.frame(f"Аватар {i + 1}", "horizontal", [c.text(t, 14, c.s[fg], 500, "Инициалы")], w=40, h=40,
                    radius=20, fill=c.s[bg], stroke=c.s["surface"], stroke_width=2, main_align="center",
                    cross_align="center")
        a.x, a.y = c.d(i * 28), 0
        for ch in a.children:
            ch.x, ch.y = a.x, a.y
        kids.append(a)
    return c.frame("Группа аватаров", "none", kids, w=40 + 2 * 28, h=40, clip=False, role="m3.avatar_group")


def profile_header(c: _Ctx) -> Node:
    texts = c.frame("Текст", "vertical", [c.text("Анна Смирнова", 20, c.s["onSurface"], 500, "Имя", sizing_h="fill"),
                                          c.text("anna@mail.ru", 14, c.s["onSurfaceVariant"], name="Почта",
                                                 sizing_h="fill")],
                    gap=2, sizing_h="fill", sizing_v="hug")
    return c.frame("Шапка профиля", "horizontal", [avatar(c), texts, c.icon(24, color=c.s["onSurfaceVariant"],
                                                                            glyph="edit")],
                   x=0, w=c.width_dp, pad_l=16, pad_r=16, pad_t=16, pad_b=16, gap=16, cross_align="center",
                   sizing_v="hug", constraint_h="left_right", role="m3.profile_header")


def stats_row(c: _Ctx) -> Node:
    cols = []
    for v, t in (("128", "Публикации"), ("4,2 тыс.", "Подписчики"), ("312", "Подписки")):
        cols.append(c.frame(f"Показатель «{t}»", "vertical",
                            [c.text(v, 20, c.s["onSurface"], 600, "Число"), c.text(t, 12, c.s["onSurfaceVariant"],
                                                                                     name="Подпись")],
                            gap=2, cross_align="center", sizing_h="fill", sizing_v="hug"))
    return c.frame("Статистика", "horizontal", cols, w=c.width_dp - 32, gap=8, sizing_v="hug", role="m3.stats_row")


def settings_row(c: _Ctx) -> Node:
    return c.frame("Строка настройки", "horizontal",
                   [c.icon(24, color=c.s["onSurfaceVariant"], glyph="lock"),
                    c.frame("Текст", "vertical", [c.text("Конфиденциальность", 16, c.s["onSurface"], name="Заголовок",
                                                         sizing_h="fill"),
                                                  c.text("Кто видит профиль", 14, c.s["onSurfaceVariant"],
                                                         name="Подпись", sizing_h="fill")],
                            gap=2, sizing_h="fill", sizing_v="hug"),
                    c.icon(24, color=c.s["onSurfaceVariant"], glyph="chevron_right")],
                   x=0, w=c.width_dp, min_h=56, pad_l=16, pad_r=16, pad_t=8, pad_b=8, gap=16, cross_align="center",
                   sizing_v="hug", constraint_h="left_right", role="m3.settings_row")


def notification_item(c: _Ctx) -> Node:
    dot = c.dot("Новое", 8, c.s["primary"])
    return c.frame("Уведомление", "horizontal",
                   [c.frame("Значок", "horizontal", [c.icon(20, color=c.s["onSecondaryContainer"], glyph="shopping_bag")],
                            w=40, h=40, radius=20, fill=c.s["secondaryContainer"], main_align="center",
                            cross_align="center"),
                    c.frame("Текст", "vertical", [c.text("Заказ передан курьеру", 16, c.s["onSurface"],
                                                         name="Заголовок", sizing_h="fill"),
                                                  c.text("Привезём сегодня с 18:00 до 20:00", 14,
                                                         c.s["onSurfaceVariant"], name="Подпись", sizing_h="fill"),
                                                  c.text("5 мин назад", 12, c.s["onSurfaceVariant"], name="Время")],
                            gap=2, sizing_h="fill", sizing_v="hug"), dot],
                   x=0, w=c.width_dp, pad_l=16, pad_r=16, pad_t=12, pad_b=12, gap=16, sizing_v="hug",
                   constraint_h="left_right", role="m3.notification_item")


# ---------------- магазин ----------------

def rating(c: _Ctx, caption: str = "4,0 · 128 отзывов") -> Node:
    stars = [c.icon(18, f"Звезда {i + 1}", c.s["primary"], "star" if i < 4 else "star_border") for i in range(5)]
    return c.frame("Рейтинг", "horizontal", stars + [c.text(caption, 14, c.s["onSurfaceVariant"],
                                                          name="Подпись")],
                   gap=2, cross_align="center", sizing_h="hug", sizing_v="hug", role="m3.rating")


def price_tag(c: _Ctx) -> Node:
    old = c.text("3 490 ₽", 14, c.s["onSurfaceVariant"], name="Старая цена")
    chip = c.frame("Скидка", "horizontal", [c.text("−14%", 12, c.s["onErrorContainer"], 600, "Процент")],
                   pad_l=6, pad_r=6, pad_t=2, pad_b=2, radius=4, fill=c.s["errorContainer"], sizing_h="hug",
                   sizing_v="hug")
    return c.frame("Цена со скидкой", "horizontal", [c.text("2 990 ₽", 22, c.s["onSurface"], 600, "Цена"), old, chip],
                   gap=8, cross_align="center", sizing_h="hug", sizing_v="hug", role="m3.price")


def product_card(c: _Ctx) -> Node:
    photo = c.frame("Фото", "horizontal", [c.icon(40, color=c.s["onSurfaceVariant"], glyph="image")], h=140,
                    radius=12, fill=c.s["surfaceContainerHighest"], main_align="center", cross_align="center",
                    sizing_h="fill")
    fav = c.icon(24, color=c.s["onSurfaceVariant"], glyph="favorite_border")
    title_row = c.frame("Название", "horizontal", [c.text("Беспроводные наушники", 16, c.s["onSurface"],
                                                          name="Название", sizing_h="fill"), fav],
                        gap=8, cross_align="start", sizing_h="fill", sizing_v="hug")
    buy = _button(c, "Кнопка «В корзину»", "m3.button_filled", "В корзину", c.s["onPrimary"], fill=c.s["primary"],
                  pad_l=12, pad_r=12)
    buy.sizing_h = "fill"
    return c.frame("Карточка товара", "vertical",
                   [photo, title_row, rating(c, "4,0"), c.text("2 990 ₽", 20, c.s["onSurface"], 600, "Цена"), buy],
                   w=220, pad_t=8, pad_r=8, pad_b=12, pad_l=8, gap=8, radius=16, fill=c.s["surfaceContainerLow"],
                   sizing_v="hug", role="m3.product_card")


# ---------------- состояния и подсказки ----------------

def empty_state(c: _Ctx) -> Node:
    circle = c.frame("Значок", "horizontal", [c.icon(40, color=c.s["onSecondaryContainer"], glyph="shopping_cart")],
                     w=88, h=88, radius=44, fill=c.s["secondaryContainer"], main_align="center", cross_align="center")
    t1 = c.text("Корзина пуста", 22, c.s["onSurface"], name="Заголовок", sizing_h="fill")
    t1.align = "center"
    t2 = c.text("Добавьте товары из каталога — они появятся здесь", 14, c.s["onSurfaceVariant"], name="Текст",
                sizing_h="fill")
    t2.align = "center"
    btn = _button(c, "Кнопка", "m3.button_filled", "В каталог", c.s["onPrimary"], fill=c.s["primary"])
    return c.frame("Пустое состояние", "vertical", [circle, t1, t2, btn], w=300, gap=12, cross_align="center",
                   sizing_v="hug", role="m3.empty_state")


def _banner(c: _Ctx, kind: str, glyph: str, title: str, text: str, bg: str, fg: str) -> Node:
    body = c.frame("Текст", "vertical", [c.text(title, 16, c.s[fg], 500, "Заголовок", sizing_h="fill"),
                                         c.text(text, 14, c.s[fg], name="Текст", sizing_h="fill")],
                   gap=2, sizing_h="fill", sizing_v="hug")
    return c.frame(f"Баннер «{kind}»", "horizontal", [c.icon(24, color=c.s[fg], glyph=glyph), body],
                   w=c.width_dp - 32, pad_l=16, pad_r=16, pad_t=12, pad_b=12, gap=12, radius=12, fill=c.s[bg],
                   sizing_v="hug", role="m3.banner")


def banner_info(c: _Ctx) -> Node:
    return _banner(c, "сведения", "info", "Новая версия", "Обновите приложение, чтобы получить новые функции",
                   "secondaryContainer", "onSecondaryContainer")


def banner_error(c: _Ctx) -> Node:
    return _banner(c, "ошибка", "error", "Нет подключения", "Проверьте интернет и попробуйте снова",
                   "errorContainer", "onErrorContainer")


def banner_success(c: _Ctx) -> Node:
    return _banner(c, "успех", "check_circle", "Оплата прошла", "Чек отправлен на почту",
                   "tertiaryContainer", "onTertiaryContainer")


def steps(c: _Ctx) -> Node:
    kids = []
    for i, t in enumerate(("Данные", "Доставка", "Оплата")):
        done, cur = i < 1, i == 1
        circ = c.frame(f"Шаг {i + 1}", "horizontal",
                       [c.icon(16, color=c.s["onPrimary"], glyph="check") if done else
                        c.text(str(i + 1), 14, c.s["onPrimary"] if cur else c.s["onSurfaceVariant"], 600, "Номер")],
                       w=28, h=28, radius=14, fill=c.s["primary"] if (done or cur) else "",
                       stroke="" if (done or cur) else c.s["outline"], stroke_width=0 if (done or cur) else 1,
                       main_align="center", cross_align="center")
        kids.append(c.frame(f"Этап «{t}»", "vertical", [circ, c.text(t, 12, c.s["onSurface"] if (done or cur) else
                                                                        c.s["onSurfaceVariant"], name="Подпись")],
                            gap=4, cross_align="center", sizing_h="hug", sizing_v="hug"))
        if i < 2:
            kids.append(c.rect("Линия", 10, 2, c.s["primary"] if done else c.s["outlineVariant"], sizing_h="fill"))
    return c.frame("Шаги", "horizontal", kids, w=320, gap=8, cross_align="center", sizing_v="hug", role="m3.steps")


def page_dots(c: _Ctx) -> Node:
    dots = [c.rect("Текущая", 24, 8, c.s["primary"], 4)] + [c.dot(f"Точка {i + 2}", 8, c.s["outlineVariant"])
                                                           for i in range(3)]
    return c.frame("Точки страниц", "horizontal", dots, gap=8, cross_align="center", sizing_h="hug", sizing_v="hug",
                   role="m3.page_dots")


def accordion(c: _Ctx) -> Node:
    head = c.frame("Заголовок", "horizontal", [c.text("Как вернуть товар?", 16, c.s["onSurface"], 500, "Вопрос",
                                                      sizing_h="fill"),
                                               c.icon(24, color=c.s["onSurfaceVariant"], glyph="expand_less")],
                   gap=12, cross_align="center", sizing_h="fill", sizing_v="hug")
    return c.frame("Раскрывающийся пункт", "vertical",
                   [head, c.text("Оформите возврат в разделе «Заказы» в течение 14 дней — курьер заберёт товар.", 14,
                                 c.s["onSurfaceVariant"], name="Ответ", sizing_h="fill")],
                   w=c.width_dp - 32, pad_l=16, pad_r=16, pad_t=14, pad_b=14, gap=8, radius=12,
                   fill=c.s["surfaceContainerLow"], sizing_v="hug", role="m3.accordion")


def tooltip(c: _Ctx) -> Node:
    return c.frame("Подсказка", "horizontal", [c.text("Нажмите, чтобы добавить в избранное", 12,
                                                      c.s["inverseOnSurface"], name="Текст")],
                   pad_l=8, pad_r=8, pad_t=4, pad_b=4, radius=4, fill=c.s["inverseSurface"], sizing_h="hug",
                   sizing_v="hug", role="m3.tooltip")


def bottom_actions(c: _Ctx) -> Node:
    back = _button(c, "Кнопка «Назад»", "m3.button_outlined", "Назад", c.s["primary"], stroke=c.s["outline"],
                   stroke_width=1)
    nxt = _button(c, "Кнопка «Далее»", "m3.button_filled", "Далее", c.s["onPrimary"], fill=c.s["primary"])
    back.sizing_h = nxt.sizing_h = "fill"
    h = 72
    return c.frame("Кнопки внизу", "horizontal", [back, nxt], x=0, y=c.screen.height - c.d(h), w=c.width_dp, h=h,
                   pad_l=16, pad_r=16, gap=12, cross_align="center", fill=c.s["surfaceContainer"],
                   constraint_h="left_right", constraint_v="bottom", role="m3.bottom_actions")


SPECS: tuple[ComponentSpec, ...] = (
    ComponentSpec("m3_password_field", "Поле пароля", _A, "Вход и регистрация", password_field),
    ComponentSpec("m3_phone_field", "Поле телефона", _A, "Вход и регистрация", phone_field),
    ComponentSpec("m3_otp_code", "Код из SMS", _A, "Вход и регистрация", otp_code),
    ComponentSpec("m3_sign_in_google", "Войти через Google", _A, "Вход и регистрация", sign_in_google),
    ComponentSpec("m3_sign_in_apple", "Войти через Apple", _A, "Вход и регистрация", sign_in_apple),
    ComponentSpec("m3_sign_in_vk", "Войти через VK ID", _A, "Вход и регистрация", sign_in_vk),
    ComponentSpec("m3_sign_in_phone", "Войти по номеру телефона", _A, "Вход и регистрация", sign_in_phone),
    ComponentSpec("m3_or_divider", "Разделитель «или»", _A, "Вход и регистрация", or_divider),
    ComponentSpec("m3_dropdown_field", "Выпадающий список", _A, "Поля", dropdown_field),
    ComponentSpec("m3_date_field", "Поле даты", _A, "Поля", date_field),
    ComponentSpec("m3_text_area", "Многострочное поле", _A, "Поля", text_area),
    ComponentSpec("m3_quantity", "Количество (− 2 +)", _A, "Поля", quantity_stepper),
    ComponentSpec("m3_avatar", "Аватар", _A, "Профиль и люди", avatar),
    ComponentSpec("m3_avatar_group", "Группа аватаров", _A, "Профиль и люди", avatar_group),
    ComponentSpec("m3_profile_header", "Шапка профиля", _A, "Профиль и люди", profile_header),
    ComponentSpec("m3_stats_row", "Статистика", _A, "Профиль и люди", stats_row),
    ComponentSpec("m3_settings_row", "Строка настройки", _A, "Профиль и люди", settings_row),
    ComponentSpec("m3_notification_item", "Уведомление", _A, "Профиль и люди", notification_item),
    ComponentSpec("m3_product_card", "Карточка товара", _A, "Магазин", product_card),
    ComponentSpec("m3_price", "Цена со скидкой", _A, "Магазин", price_tag),
    ComponentSpec("m3_rating", "Рейтинг", _A, "Магазин", rating),
    ComponentSpec("m3_empty_state", "Пустое состояние", _A, "Состояния", empty_state),
    ComponentSpec("m3_banner_info", "Баннер «сведения»", _A, "Состояния", banner_info),
    ComponentSpec("m3_banner_success", "Баннер «успех»", _A, "Состояния", banner_success),
    ComponentSpec("m3_banner_error", "Баннер «ошибка»", _A, "Состояния", banner_error),
    ComponentSpec("m3_steps", "Шаги", _A, "Состояния", steps),
    ComponentSpec("m3_page_dots", "Точки страниц", _A, "Состояния", page_dots),
    ComponentSpec("m3_accordion", "Раскрывающийся пункт", _A, "Состояния", accordion),
    ComponentSpec("m3_tooltip", "Подсказка", _A, "Состояния", tooltip),
    ComponentSpec("m3_bottom_actions", "Кнопки внизу", _A, "Навигация", bottom_actions),
)
