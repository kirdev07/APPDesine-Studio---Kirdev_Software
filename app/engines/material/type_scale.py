"""Шкала типографики и форм Material 3 (значения в sp / dp)."""

from __future__ import annotations

# роль Compose Typography → (русское имя, размер sp, межстрочный sp, насыщенность)
TYPE_SCALE: dict[str, tuple[str, float, float, int]] = {
    "displayLarge": ("Дисплей крупный", 57, 64, 400),
    "displayMedium": ("Дисплей средний", 45, 52, 400),
    "displaySmall": ("Дисплей мелкий", 36, 44, 400),
    "headlineLarge": ("Заголовок крупный", 32, 40, 400),
    "headlineMedium": ("Заголовок средний", 28, 36, 400),
    "headlineSmall": ("Заголовок мелкий", 24, 32, 400),
    "titleLarge": ("Название крупное", 22, 28, 400),
    "titleMedium": ("Название среднее", 16, 24, 500),
    "titleSmall": ("Название мелкое", 14, 20, 500),
    "bodyLarge": ("Текст крупный", 16, 24, 400),
    "bodyMedium": ("Текст средний", 14, 20, 400),
    "bodySmall": ("Текст мелкий", 12, 16, 400),
    "labelLarge": ("Подпись крупная", 14, 20, 500),
    "labelMedium": ("Подпись средняя", 12, 16, 500),
    "labelSmall": ("Подпись мелкая", 11, 16, 500),
}

PREFIX = "M3 · "


def style_name(role: str) -> str:
    return f"{PREFIX}{TYPE_SCALE[role][0]}"


def role_of(style_name_: str) -> str | None:
    """Роль Typography по имени стиля, созданного кнопкой «Типографика Material 3»."""
    for role, (ru, *_rest) in TYPE_SCALE.items():
        if style_name_ in (f"{PREFIX}{ru}", role):
            return role
    return None


# шкала скруглений (dp); full — половина меньшей стороны
SHAPES = {"none": 0, "extra_small": 4, "small": 8, "medium": 12, "large": 16, "extra_large": 28}
