"""Набор значков в стиле Material (сетка 24 × 24, заливка).

Контуры нарисованы для App Design Studio (собственные пути из простых фигур), а не скопированы из
Material Symbols: их можно свободно использовать в проектах. Для финального приложения команда может
заменить их на Material Symbols (Apache 2.0) по именам из ICONS.
"""

from __future__ import annotations

import math

from app.core.document.pathdata import ellipse_path, normalize


def _circle(cx: float, cy: float, r: float) -> str:
    return ellipse_path(cx, cy, r, r)


def _poly(points) -> str:
    return "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in points) + " Z"


def _star(cx, cy, r_out, r_in, n=5, rot=-90) -> str:
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return _poly(pts)


def _gear() -> str:
    pts = []
    for i in range(8):  # 8 зубцов: по две точки на вершине и у основания
        a = math.radians(i * 45)
        for da, r in ((-12, 10), (12, 10), (16, 7.6), (29, 7.6)):
            b = a + math.radians(da)
            pts.append((12 + r * math.cos(b), 12 + r * math.sin(b)))
    return _poly(pts) + " " + _circle(12, 12, 3)


# имя → (русское имя, путь, правило заливки)
ICONS: dict[str, tuple[str, str, str]] = {
    "menu": ("Меню", "M3 6H21V8H3Z M3 11H21V13H3Z M3 16H21V18H3Z", "nonzero"),
    "search": ("Поиск", _circle(10, 10, 6.5) + " " + _circle(10, 10, 4.5) +
               " M14.6 16L16 14.6L21 19.6L19.6 21Z", "evenodd"),
    "add": ("Добавить", "M11 5H13V11H19V13H13V19H11V13H5V11H11Z", "nonzero"),
    "close": ("Закрыть", _poly([(6.4, 5), (12, 10.6), (17.6, 5), (19, 6.4), (13.4, 12), (19, 17.6), (17.6, 19),
                                (12, 13.4), (6.4, 19), (5, 17.6), (10.6, 12), (5, 6.4)]), "nonzero"),
    "check": ("Галочка", _poly([(9, 16.2), (4.8, 12), (3.4, 13.4), (9, 19), (21, 7), (19.6, 5.6)]), "nonzero"),
    "arrow_back": ("Назад", "M20 11H7.8L13.4 5.4L12 4L4 12L12 20L13.4 18.6L7.8 13H20Z", "nonzero"),
    "arrow_forward": ("Вперёд", "M4 11H16.2L10.6 5.4L12 4L20 12L12 20L10.6 18.6L16.2 13H4Z", "nonzero"),
    "more_vert": ("Ещё", _circle(12, 6, 2) + " " + _circle(12, 12, 2) + " " + _circle(12, 18, 2), "nonzero"),
    "home": ("Главная", "M12 3L2 12H5V20H10V14H14V20H19V12H22Z", "nonzero"),
    "person": ("Профиль", _circle(12, 8, 4) + " M4 20C4 15.6 8 14 12 14C16 14 20 15.6 20 20Z", "nonzero"),
    "settings": ("Настройки", _gear(), "evenodd"),
    "favorite": ("Избранное", "M12 21L10.6 19.7C5.4 15 2 12 2 8.3C2 5.3 4.3 3 7.3 3C9 3 10.7 3.8 12 5.1"
                 "C13.3 3.8 15 3 16.7 3C19.7 3 22 5.3 22 8.3C22 12 18.6 15 13.4 19.7Z", "nonzero"),
    "star": ("Звезда", _star(12, 12.6, 10, 4.2), "nonzero"),
    "edit": ("Изменить", "M3 17.2V21H6.8L17.8 10L14 6.2Z M20.7 7.1C21.1 6.7 21.1 6.1 20.7 5.7L18.3 3.3"
             "C17.9 2.9 17.3 2.9 16.9 3.3L15 5.2L18.8 9Z", "nonzero"),
    "delete": ("Удалить", "M6 19C6 20.1 6.9 21 8 21H16C17.1 21 18 20.1 18 19V7H6Z M19 4H15.5L14.5 3H9.5L8.5 4H5V6H19Z",
               "nonzero"),
    "share": ("Поделиться", _circle(18, 5, 3) + " " + _circle(6, 12, 3) + " " + _circle(18, 19, 3) +
              " M8.6 10.7L15.4 6.8L16.4 8.5L9.6 12.4Z M9.6 11.6L16.4 15.5L15.4 17.2L8.6 13.3Z", "nonzero"),
    "notifications": ("Уведомления", "M12 22C13.1 22 14 21.1 14 20H10C10 21.1 10.9 22 12 22Z M18 16V11"
                      "C18 7.9 16.4 5.4 13.5 4.7V4C13.5 3.2 12.8 2.5 12 2.5C11.2 2.5 10.5 3.2 10.5 4V4.7"
                      "C7.6 5.4 6 7.9 6 11V16L4 18V19H20V18Z", "nonzero"),
    "chat": ("Чат", "M2 6C2 4.9 2.9 4 4 4H20C21.1 4 22 4.9 22 6V16C22 17.1 21.1 18 20 18H6L2 22Z", "nonzero"),
    "call": ("Звонок", "M6.6 10.8C8 13.6 10.4 16 13.2 17.4L15.4 15.2C15.7 14.9 16.1 14.8 16.4 14.9"
             "C17.5 15.3 18.7 15.5 20 15.5C20.6 15.5 21 15.9 21 16.5V20C21 20.6 20.6 21 20 21"
             "C10.6 21 3 13.4 3 4C3 3.4 3.4 3 4 3H7.5C8.1 3 8.5 3.4 8.5 4C8.5 5.3 8.7 6.5 9.1 7.6"
             "C9.2 7.9 9.1 8.3 8.9 8.6Z", "nonzero"),
    "calendar": ("Календарь", "M19 4H18V2H16V4H8V2H6V4H5C3.9 4 3 4.9 3 6V20C3 21.1 3.9 22 5 22H19"
                 "C20.1 22 21 21.1 21 20V6C21 4.9 20.1 4 19 4Z M19 20H5V9H19Z", "evenodd"),
    "info": ("Сведения", _circle(12, 12, 10) + " M11 10H13V17H11Z M11 6.5H13V8.5H11Z", "evenodd"),
}

ICONS = {k: (ru, normalize(d), rule) for k, (ru, d, rule) in ICONS.items()}
