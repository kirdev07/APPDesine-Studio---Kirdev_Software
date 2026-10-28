"""Тональные палитры и цветовые схемы Material 3 по одному цвету (seed).

Тон — светлота L* (CIELAB), как в Material 3: тон 0 — чёрный, 100 — белый. Оттенок и насыщенность берутся
в цилиндрических координатах LCh(ab) — это приближение пространства HCT из material-color-utilities: тоны
совпадают точно, оттенки и насыщенность — близко, но не побитово. Цвет вне sRGB приводится к границе
охвата уменьшением насыщенности при неизменных тоне и оттенке.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# опорный белый D65
_WX, _WY, _WZ = 0.95047, 1.0, 1.08883


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _delin(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _f(t: float) -> float:
    return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116


def _finv(t: float) -> float:
    return t ** 3 if t ** 3 > 216 / 24389 else (116 * t - 16) / (24389 / 27)


def parse_hex(value: str) -> tuple[int, int, int]:
    v = value.strip().lstrip("#")
    if len(v) not in (6, 8) or any(ch not in "0123456789abcdefABCDEF" for ch in v):
        raise ValueError(f"Неверный цвет: {value!r}")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % rgb


def hex_to_lch(value: str) -> tuple[float, float, float]:
    """(тон L*, насыщенность C, оттенок h в градусах)."""
    r, g, b = (_lin(c / 255) for c in parse_hex(value))
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / _WX
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / _WY
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / _WZ
    fx, fy, fz = _f(x), _f(y), _f(z)
    L, a, bb = 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)
    return L, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


def _lch_to_rgb(L: float, C: float, h: float) -> tuple[float, float, float]:
    a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200
    x, y, z = _finv(fx) * _WX, (fy ** 3 if L > 8 else L / (24389 / 27)) * _WY, _finv(fz) * _WZ
    r = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    g = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    bl = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z
    return r, g, bl


def tone(hue: float, chroma: float, t: float) -> str:
    """Цвет с тоном t (0…100), оттенком hue и насыщенностью не выше chroma (в пределах sRGB)."""
    t = min(100.0, max(0.0, t))
    if t <= 0:
        return "#000000"
    if t >= 100:
        return "#FFFFFF"
    lo, hi = 0.0, max(0.0, chroma)

    def inside(c):
        return all(-1e-4 <= v <= 1 + 1e-4 for v in _lch_to_rgb(t, c, hue))
    if not inside(hi):
        for _ in range(24):  # двоичный поиск границы охвата
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if inside(mid) else (lo, mid)
        hi = lo
    rgb = _lch_to_rgb(t, hi, hue)
    return to_hex(tuple(min(255, max(0, round(_delin(min(1.0, max(0.0, v))) * 255))) for v in rgb))


@dataclass(frozen=True)
class TonalPalette:
    hue: float
    chroma: float

    def __call__(self, t: float) -> str:
        return tone(self.hue, self.chroma, t)


TONES = (0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99, 100)

# роль → (тон в светлой схеме, тон в тёмной схеме, палитра)
ROLES: dict[str, tuple[float, float, str]] = {
    "primary": (40, 80, "p"), "onPrimary": (100, 20, "p"),
    "primaryContainer": (90, 30, "p"), "onPrimaryContainer": (10, 90, "p"),
    "inversePrimary": (80, 40, "p"),
    "secondary": (40, 80, "s"), "onSecondary": (100, 20, "s"),
    "secondaryContainer": (90, 30, "s"), "onSecondaryContainer": (10, 90, "s"),
    "tertiary": (40, 80, "t"), "onTertiary": (100, 20, "t"),
    "tertiaryContainer": (90, 30, "t"), "onTertiaryContainer": (10, 90, "t"),
    "error": (40, 80, "e"), "onError": (100, 20, "e"),
    "errorContainer": (90, 30, "e"), "onErrorContainer": (10, 90, "e"),
    "background": (98, 6, "n"), "onBackground": (10, 90, "n"),
    "surface": (98, 6, "n"), "onSurface": (10, 90, "n"),
    "surfaceVariant": (90, 30, "nv"), "onSurfaceVariant": (30, 80, "nv"),
    "surfaceDim": (87, 6, "n"), "surfaceBright": (98, 24, "n"),
    "surfaceContainerLowest": (100, 4, "n"), "surfaceContainerLow": (96, 10, "n"),
    "surfaceContainer": (94, 12, "n"), "surfaceContainerHigh": (92, 17, "n"),
    "surfaceContainerHighest": (90, 22, "n"),
    "inverseSurface": (20, 90, "n"), "inverseOnSurface": (95, 20, "n"),
    "outline": (50, 60, "nv"), "outlineVariant": (80, 30, "nv"),
    "scrim": (0, 0, "n"), "shadow": (0, 0, "n"),
}

ROLE_RU = {
    "primary": "Основной", "onPrimary": "На основном", "primaryContainer": "Контейнер основного",
    "onPrimaryContainer": "На контейнере основного", "inversePrimary": "Инверсный основной",
    "secondary": "Вторичный", "onSecondary": "На вторичном", "secondaryContainer": "Контейнер вторичного",
    "onSecondaryContainer": "На контейнере вторичного", "tertiary": "Третичный", "onTertiary": "На третичном",
    "tertiaryContainer": "Контейнер третичного", "onTertiaryContainer": "На контейнере третичного",
    "error": "Ошибка", "onError": "На ошибке", "errorContainer": "Контейнер ошибки",
    "onErrorContainer": "На контейнере ошибки", "background": "Фон", "onBackground": "На фоне",
    "surface": "Поверхность", "onSurface": "На поверхности", "surfaceVariant": "Вариант поверхности",
    "onSurfaceVariant": "На варианте поверхности", "surfaceDim": "Поверхность (тусклая)",
    "surfaceBright": "Поверхность (яркая)", "surfaceContainerLowest": "Контейнер (самый низкий)",
    "surfaceContainerLow": "Контейнер (низкий)", "surfaceContainer": "Контейнер",
    "surfaceContainerHigh": "Контейнер (высокий)", "surfaceContainerHighest": "Контейнер (самый высокий)",
    "inverseSurface": "Инверсная поверхность", "inverseOnSurface": "На инверсной поверхности",
    "outline": "Контур", "outlineVariant": "Вариант контура", "scrim": "Затемнение", "shadow": "Тень",
}


_ERROR_HUE = 37.0  # оттенок #B3261E (ошибка Material 3) в LCh(ab)


def palettes(seed: str) -> dict[str, TonalPalette]:
    """Ключевые палитры схемы «tonal spot»: основная, вторичная, третичная, нейтральные и ошибки."""
    _, c, h = hex_to_lch(seed)
    return {"p": TonalPalette(h, max(48.0, c)), "s": TonalPalette(h, 16.0), "t": TonalPalette((h + 60) % 360, 24.0),
            "n": TonalPalette(h, 4.0), "nv": TonalPalette(h, 8.0), "e": TonalPalette(_ERROR_HUE, 68.0)}


def contrast(a: str, b: str) -> float:
    """Контраст WCAG между двумя цветами."""
    def lum(v):
        r, g, bb = (_lin(c / 255) for c in parse_hex(v))
        return 0.2126 * r + 0.7152 * g + 0.0722 * bb
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def scheme(seed: str, dark: bool, fidelity: bool = True) -> dict[str, str]:
    """Цветовая схема Material 3. fidelity — основной цвет равен цвету бренда (как задано в оформлении),
    иначе — тон 40 / 80 основной палитры по правилам Material."""
    pal = palettes(seed)
    out = {role: pal[p](d if dark else l) for role, (l, d, p) in ROLES.items()}
    if fidelity:
        seed = to_hex(parse_hex(seed))
        out["primary"] = seed
        white_ok = contrast(seed, "#FFFFFF") >= 3.0  # как у кнопок прежних версий: белый, пока он читаем
        out["onPrimary"] = "#FFFFFF" if white_ok else pal["p"](10)
    return out


def tonal_table(seed: str) -> dict[str, list[tuple[int, str]]]:
    """Тоны ключевых палитр — для показа в интерфейсе."""
    names = {"p": "Основная", "s": "Вторичная", "t": "Третичная", "n": "Нейтральная", "nv": "Нейтральная (вариант)",
             "e": "Ошибка"}
    return {names[k]: [(t, p(t)) for t in TONES] for k, p in palettes(seed).items()}
