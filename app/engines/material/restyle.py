"""Темы и стили проекта: готовые наборы (цвет бренда, светлая / тёмная тема, шрифт, скругления) и перекраска
уже нарисованных экранов по ролям цвета Material 3. Без Qt.

Цвет элемента, совпадающий с ролью схемы старой темы («основной», «поверхность», «контур» …), заменяется той же
ролью новой схемы; фон экрана — новым фоном. Свои цвета, не совпадающие ни с одной ролью, не трогаются.
Скругления пересчитываются по стилю формы, «таблетки» остаются таблетками. Шрифт меняется у текстов со старым
шрифтом оформления.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.core.document import tree
from app.core.document.model import ARTBOARD_COLORS, Appearance, ProjectDocument
from app.engines.material.color import ROLES, scheme

# стиль формы: corner_radius в оформлении → (название, множитель скруглений)
SHAPES = {4: ("Строгие", 0.35), 12: ("Обычные", 1.0), 20: ("Мягкие", 1.6)}
THEMES = {"amoled": "Тёмная (AMOLED)", "dark": "Тёмная", "gray": "Серая", "light": "Светлая"}
FONTS = ("Segoe UI", "Arial", "Calibri", "Verdana", "Tahoma", "Trebuchet MS", "Bahnschrift", "Georgia",
         "Cambria", "Times New Roman")
# порядок важности ролей: при совпадении цветов у нескольких ролей побеждает первая
_ORDER = ("primary", "onPrimary", "primaryContainer", "onPrimaryContainer", "secondaryContainer",
          "onSecondaryContainer", "tertiaryContainer", "onTertiaryContainer", "surface", "onSurface",
          "onSurfaceVariant", "outline", "outlineVariant", "surfaceContainerLowest", "surfaceContainerLow",
          "surfaceContainer", "surfaceContainerHigh", "surfaceContainerHighest", "error", "onError",
          "errorContainer", "onErrorContainer", "inverseSurface", "inverseOnSurface", "inversePrimary")
ORDERED_ROLES = _ORDER + tuple(r for r in ROLES if r not in _ORDER)


@dataclass(frozen=True)
class ThemePreset:
    key: str
    name: str
    hint: str
    accent: str
    theme: str
    font: str
    shape: int


PRESETS: tuple[ThemePreset, ...] = (
    ThemePreset("material", "Material", "Классический синий Material 3", "#2F7BFF", "amoled", "Segoe UI", 12),
    ThemePreset("ocean", "Океан", "Спокойный бирюзовый, светлая тема", "#00838F", "light", "Segoe UI", 12),
    ThemePreset("forest", "Лес", "Природный зелёный, мягкие формы", "#2E7D32", "light", "Trebuchet MS", 20),
    ThemePreset("sunset", "Закат", "Тёплый оранжевый на тёмном", "#F4511E", "dark", "Segoe UI", 20),
    ThemePreset("berry", "Ягода", "Сочный малиновый, мягкие формы", "#C2185B", "light", "Verdana", 20),
    ThemePreset("violet", "Фиалка", "Фиолетовый Material You", "#6750A4", "light", "Segoe UI", 12),
    ThemePreset("graphite", "Графит", "Сдержанный серо-синий, строгие формы", "#546E7A", "dark", "Bahnschrift", 4),
    ThemePreset("neon", "Неон", "Яркий салатовый на чёрном", "#00E676", "amoled", "Bahnschrift", 20),
    ThemePreset("corporate", "Деловой", "Строгий тёмно-синий, светлая тема", "#1A3C8E", "light", "Calibri", 4),
    ThemePreset("gold", "Премиум", "Золото на чёрном, строгие формы", "#C9A227", "amoled", "Georgia", 4),
    ThemePreset("candy", "Пастель", "Нежный розовый, светлая тема", "#E91E63", "light", "Segoe UI", 20),
    ThemePreset("sky", "Небо", "Голубой, светлая тема", "#0288D1", "light", "Arial", 12),
)


def preset(key: str) -> ThemePreset:
    return next(p for p in PRESETS if p.key == key)


def appearance_of(p: ThemePreset, base: Appearance) -> Appearance:
    return replace(base, accent=p.accent, theme=p.theme, font_family=p.font, corner_radius=p.shape)


def _scheme_full(ap: Appearance) -> dict[str, str]:
    s = scheme(ap.accent, ap.theme != "light")
    return s


def color_map(old: Appearance, new: Appearance) -> dict[str, str]:
    """Старый цвет (#RRGGBB) → новый: роли схемы и фон экрана."""
    a, b = _scheme_full(old), _scheme_full(new)
    out: dict[str, str] = {}
    for r in ORDERED_ROLES:
        out.setdefault(a[r].upper(), b[r].upper())
    out[ARTBOARD_COLORS.get(old.theme, "#000000").upper()] = ARTBOARD_COLORS.get(new.theme, "#000000").upper()
    out.setdefault(old.accent.upper()[:7], new.accent.upper()[:7])
    return out


def _map(cmap: dict[str, str], c: str) -> str:
    if not c:
        return c
    base, alpha = c[:7].upper(), c[7:]
    return cmap[base] + alpha if base in cmap else c


def shape_factor(old: int, new: int) -> float:
    return SHAPES.get(new, ("", 1.0))[1] / SHAPES.get(old, ("", 1.0))[1]


WIN_KEYS = ("win_surface", "win_card", "win_stroke", "win_ctrl", "win_select")


def win_map(old: Appearance, new: Appearance) -> dict[str, str]:
    """Цвета Fluent (фон окна, карточки, рамки, подложки) старой темы → новой; точное совпадение, с прозрачностью."""
    from app.libraries.components import _palette
    a, b = _palette(old.theme, old.accent), _palette(new.theme, new.accent)
    out: dict[str, str] = {}
    for k in WIN_KEYS:
        out.setdefault(a[k].upper(), b[k].upper())
    return out


ABSOLUTE = ("#FFFFFF", "#000000")


def restyle_node(n, cmap: dict[str, str], factor: float, old_font: str, new_font: str,
                 exact: dict[str, str] | None = None) -> None:
    for prop in ("fill", "stroke", "text_color", "fill2"):
        v = getattr(n, prop)
        # окна Windows: фон и рамки — по палитре Fluent (значки и тексты — по ролям, белая галочка остаётся белой)
        if exact and prop in ("fill", "stroke") and n.type not in ("vector", "text") and v and v.upper() in exact:
            setattr(n, prop, exact[v.upper()])
            continue
        # чисто белый и чисто чёрный текст и значки — свои цвета (подписи на фото и видео), а не роль темы:
        # иначе «тёмная → светлая → тёмная» делала белые подписи почти чёрными
        if (n.type in ("vector", "text") or prop == "text_color") and v and v[:7].upper() in ABSOLUTE:
            continue
        setattr(n, prop, _map(cmap, v))
    if n.radius > 0 and factor != 1.0:
        pill = min(n.w, n.h) / 2
        n.radius = round(pill if n.radius >= pill - 0.5 else min(n.radius * factor, pill), 2)
    if n.type == "text" and n.font_family == old_font:
        n.font_family = new_font
    if n.overrides:
        for props in n.overrides.values():
            for k in ("fill", "stroke", "text_color"):
                if k in props:
                    props[k] = _map(cmap, props[k])


def restyle(doc: ProjectDocument, new: Appearance) -> int:
    """Перекрасить проект под новое оформление. Возвращает число изменённых элементов."""
    old = doc.meta.appearance
    cmap = color_map(old, new)
    factor = shape_factor(old.corner_radius, new.corner_radius)
    changed = 0
    wmap = win_map(old, new)
    roots = [(n, s.platform == "windows") for s in doc.screens for n in s.nodes] + \
        [(c.root, False) for c in doc.components]
    for root, win in roots:
        for n, _, _ in tree.walk([root]):
            before = (n.fill, n.stroke, n.text_color, n.fill2, n.radius, n.font_family)
            restyle_node(n, cmap, factor, old.font_family, new.font_family, wmap if win else None)
            changed += before != (n.fill, n.stroke, n.text_color, n.fill2, n.radius, n.font_family)
    for comp in doc.components:  # состояния компонентов — тоже переопределения
        for state in comp.states.values():
            for props in state.values():
                for k in ("fill", "stroke", "text_color"):
                    if k in props:
                        props[k] = _map(cmap, props[k])
    for t in doc.text_styles:
        if t.font_family == old.font_family:
            t.font_family = new.font_family
        t.text_color = _map(cmap, t.text_color)
    for c in doc.colors:
        c.value = _map(cmap, c.value)
    if new.material != old.material:  # другое поколение Material: вид компонентов по ролям
        from app.engines.material import generations
        from app.engines.material.color import scheme
        from app.engines.preview.devices import screen_dpi
        sch = scheme(new.accent, new.theme != "light")
        ks = [screen_dpi(s) / 160 for s in doc.screens if s.platform == "android"]
        for s in doc.screens:
            if s.platform == "android":
                changed += generations.apply(s.nodes, new.material, sch, screen_dpi(s) / 160)
        changed += generations.apply([c.root for c in doc.components], new.material, sch, ks[0] if ks else 2.625)
    doc.meta.appearance = replace(new)
    return changed
