"""Готовые экраны Android (Material 3): вход, регистрация, список, профиль, настройки, чат, корзина. Без Qt.

Экран собирается из тех же заготовок, что и в галерее (настоящие компоненты Material 3 с ролями), в цветах
оформления проекта. Содержимое — контейнер «столбцом» с отступами 16 dp: раскладка сама расставит элементы,
а на другом устройстве экран перестроится. Сверху — верхняя панель, снизу при необходимости — навигация.
"""

from __future__ import annotations

from app.core.document import tree
from app.core.document.model import Node, Screen
from app.libraries import components
from app.libraries.components import _Ctx


def _set_text(node: Node, name: str, text: str, nth: int = 0) -> None:
    found = [d for d in tree.descendants(node) if d.type == "text" and d.name == name]
    if len(found) > nth:
        found[nth].text = text


def _field(c, s, ap, placeholder: str, hint: str = "") -> Node:
    f = components.build("m3_text_field", s, ap)
    _set_text(f, "Плейсхолдер", placeholder)
    help_ = next(d for d in f.children if d.name == "Подсказка")
    if hint:
        help_.text = hint
    else:
        f.children.remove(help_)
    f.sizing_h = "fill"
    return f


def _fill(n: Node) -> Node:
    n.sizing_h = "fill"
    n.constraint_h = "left"
    return n


def _text(c, t: str, size: float, color: str, weight: int = 400, name: str = "Текст") -> Node:
    return c.text(t, size, color, weight, name, sizing_h="fill")


def _top_bar(s, ap, title: str, back: bool = False) -> Node:
    bar = components.build("m3_top_app_bar", s, ap)
    _set_text(bar, "Заголовок", title)
    if back:
        from app.libraries.m3_icons import ICONS
        ico = bar.children[0]
        ico.name, ico.path, ico.fill_rule = "Назад", ICONS["arrow_back"][1], ICONS["arrow_back"][2]
    return bar


def _content(c, s, children: list[Node], top_dp: float, bottom_dp: float = 0, gap: float = 12) -> Node:
    """Содержимое экрана: столбец на всю ширину под верхней панелью."""
    h = s.height / c.k - top_dp - bottom_dp
    return c.frame("Содержимое", "vertical", children, x=0, y=c.d(top_dp), w=c.width_dp, h=h, pad_l=16, pad_r=16,
                   pad_t=16, pad_b=16, gap=gap, constraint_h="left_right", constraint_v="top_bottom",
                   cross_align="stretch", clip=True)


def _list_item(s, ap, title: str, sub: str) -> Node:
    it = components.build("m3_list_item", s, ap)
    _set_text(it, "Заголовок", title)
    _set_text(it, "Подпись", sub)
    it.constraint_h = "left"
    it.sizing_h = "fill"
    it.pad_l = it.pad_r = 0
    return it


def login(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    btn = _fill(components.build("m3_button_filled", s, ap))
    _set_text(btn, "Подпись", "Войти")
    forgot = components.build("m3_button_text", s, ap)
    _set_text(forgot, "Подпись", "Забыли пароль?")
    create = _fill(components.build("m3_button_outlined", s, ap))
    _set_text(create, "Подпись", "Создать аккаунт")
    remember = components.build("m3_checkbox", s, ap)
    kids = [c.rect("Отступ сверху", 10, 48, "", sizing_h="fill"),
            _text(c, "Вход", 32, c.s["onSurface"], 400, "Заголовок"),
            _text(c, "Войдите, чтобы продолжить", 16, c.s["onSurfaceVariant"], name="Подзаголовок"),
            _field(c, s, ap, "Электронная почта"), _field(c, s, ap, "Пароль", "Не меньше 8 символов"),
            remember, btn, forgot, create]
    return [_content(c, s, kids, 0, gap=16)]


def register(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    btn = _fill(components.build("m3_button_filled", s, ap))
    _set_text(btn, "Подпись", "Зарегистрироваться")
    agree = components.build("m3_checkbox", s, ap)
    _set_text(agree, "Подпись", "Согласен с условиями")
    kids = [_text(c, "Создайте аккаунт за минуту", 16, c.s["onSurfaceVariant"], name="Подзаголовок"),
            _field(c, s, ap, "Имя"), _field(c, s, ap, "Электронная почта"),
            _field(c, s, ap, "Пароль", "Не меньше 8 символов"), agree, btn]
    return [_top_bar(s, ap, "Регистрация", back=True), _content(c, s, kids, 64, gap=16)]


def feed(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    search = _fill(components.build("m3_search_bar", s, ap))
    people = (("Анна Смирнова", "Увидимся завтра в десять"), ("Команда дизайна", "Макеты готовы к проверке"),
              ("Игорь", "Спасибо, всё получил"), ("Мама", "Позвони, когда освободишься"),
              ("Доставка", "Заказ будет у вас в 18:00"))
    kids = [search] + [_list_item(s, ap, a, b) for a, b in people]
    fab = components.build("m3_fab", s, ap)
    fx, fy = s.width - c.d(16 + 56), s.height - c.d(80 + 16 + 56)
    dx, dy = fx - fab.x, fy - fab.y
    for n, _, _ in tree.walk([fab]):
        n.x, n.y = round(n.x + dx, 2), round(n.y + dy, 2)
    fab.constraint_h, fab.constraint_v = "right", "bottom"
    return [_top_bar(s, ap, "Сообщения"), _content(c, s, kids, 64, 80, gap=4), fab,
            components.build("m3_nav_bar", s, ap)]


def profile(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    avatar = c.frame("Аватар", "horizontal", [c.dot("Фото", 96, c.s["primaryContainer"])], h=104,
                     main_align="center", cross_align="center", sizing_h="fill")
    name = _text(c, "Анна Смирнова", 24, c.s["onSurface"], name="Имя")
    name.align = "center"
    sub = _text(c, "Дизайнер интерфейсов · Москва", 14, c.s["onSurfaceVariant"], name="О себе")
    sub.align = "center"
    edit = _fill(components.build("m3_button_tonal", s, ap))
    _set_text(edit, "Подпись", "Изменить профиль")
    items = [_list_item(s, ap, t, d) for t, d in (("Уведомления", "Звук и вибрация"),
                                                   ("Конфиденциальность", "Кто видит профиль"),
                                                   ("Помощь", "Вопросы и поддержка"))]
    out = _fill(components.build("m3_button_outlined", s, ap))
    _set_text(out, "Подпись", "Выйти")
    kids = [avatar, name, sub, edit] + items + [out]
    return [_top_bar(s, ap, "Профиль"), _content(c, s, kids, 64, 80), components.build("m3_nav_bar", s, ap)]


def settings(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)
    kids = [_text(c, "Основные", 14, c.s["primary"], 500, "Раздел")]
    for t in ("Уведомления", "Тёмная тема", "Звук", "Автообновление"):
        sw = _fill(components.build("m3_switch", s, ap))
        _set_text(sw, "Подпись", t)
        kids.append(sw)
    kids.append(_fill(components.build("m3_divider", s, ap)))
    kids.append(_text(c, "Аккаунт", 14, c.s["primary"], 500, "Раздел"))
    kids += [_list_item(s, ap, t, d) for t, d in (("Язык", "Русский"), ("Память", "Занято 1,2 ГБ"))]
    return [_top_bar(s, ap, "Настройки", back=True), _content(c, s, kids, 64)]


def chat(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)

    def bubble(t: str, mine: bool) -> Node:
        b = c.frame("Сообщение", "horizontal",
                    [c.text(t, 16, c.s["onPrimary"] if mine else c.s["onSurface"], name="Текст", sizing_h="hug",
                            max_w=c.d(260))],
                    pad_l=14, pad_r=14, pad_t=10, pad_b=10, radius=18, sizing_h="hug", sizing_v="hug",
                    fill=c.s["primary"] if mine else c.s["surfaceContainerHigh"])
        return c.frame("Моё сообщение" if mine else "Сообщение собеседника", "horizontal", [b],
                       main_align="end" if mine else "start", sizing_h="fill", sizing_v="hug")
    msgs = [bubble("Привет! Как дела с макетом?", False), bubble("Почти готов, осталась пара экранов", True),
            bubble("Отлично, жду 🙂", False), bubble("Пришлю вечером", True)]
    send = components.build("m3_icon_button", s, ap)
    from app.libraries.m3_icons import ICONS
    ico = send.children[0]
    ico.name, ico.path, ico.fill_rule, ico.fill = "Отправить", ICONS["arrow_forward"][1], ICONS["arrow_forward"][2], \
        c.s["primary"]
    field = _field(c, s, ap, "Сообщение")
    row = c.frame("Ввод сообщения", "horizontal", [field, send], x=0, y=s.height - c.d(72), w=c.width_dp, h=72,
                  pad_l=16, pad_r=8, gap=8, cross_align="center", fill=c.s["surfaceContainer"],
                  constraint_h="left_right", constraint_v="bottom")
    return [_top_bar(s, ap, "Анна Смирнова", back=True), _content(c, s, msgs, 64, 72, gap=8), row]


def cart(s: Screen, ap) -> list[Node]:
    c = _Ctx(s, ap)

    def item(name: str, price: str) -> Node:
        return c.frame(f"Товар «{name}»", "horizontal",
                       [c.dot("Фото", 56, c.s["secondaryContainer"]),
                        c.frame("Описание", "vertical", [c.text(name, 16, c.s["onSurface"], name="Название",
                                                                sizing_h="fill"),
                                                         c.text("1 шт.", 14, c.s["onSurfaceVariant"], name="Количество")],
                                gap=2, sizing_h="fill", sizing_v="hug"),
                        c.text(price, 16, c.s["onSurface"], 600, "Цена")],
                       pad_t=12, pad_b=12, pad_l=12, pad_r=16, gap=12, radius=12, fill=c.s["surfaceContainerHigh"],
                       cross_align="center", sizing_h="fill", sizing_v="hug")
    total = c.frame("Итого", "horizontal", [c.text("Итого", 18, c.s["onSurface"], 500, "Подпись", sizing_h="fill"),
                                             c.text("4 270 ₽", 22, c.s["onSurface"], 600, "Сумма")],
                    cross_align="center", sizing_h="fill", sizing_v="hug")
    buy = _fill(components.build("m3_button_filled", s, ap))
    _set_text(buy, "Подпись", "Оформить заказ")
    kids = [item("Наушники", "2 990 ₽"), item("Чехол", "590 ₽"), item("Кабель USB-C", "690 ₽"),
            _fill(components.build("m3_divider", s, ap)), total, buy]
    return [_top_bar(s, ap, "Корзина", back=True), _content(c, s, kids, 64)]


TEMPLATES: dict[str, tuple[str, callable]] = {
    "login": ("Вход", login), "register": ("Регистрация", register), "feed": ("Список (лента)", feed),
    "profile": ("Профиль", profile), "settings": ("Настройки", settings), "chat": ("Чат", chat),
    "cart": ("Корзина", cart),
}


def build(key: str, like: Screen, appearance) -> Screen:
    """Новый экран того же устройства, что like, с готовым содержимым."""
    title, fn = TEMPLATES[key]
    s = Screen(name=title, platform=like.platform, width=like.width, height=like.height, device_id=like.device_id)
    s.nodes = fn(s, appearance)
    return s
