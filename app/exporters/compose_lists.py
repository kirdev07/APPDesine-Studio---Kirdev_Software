"""Списки из данных → LazyColumn / LazyRow. Без Qt.

В прокручиваемом столбце (строке) подряд идущие одинаковые по устройству карточки — три и больше — это список:
шаблон строки (первая карточка) + данные (тексты, картинки и заливки, которыми карточки отличаются). В коде
Android такой список — LazyColumn (LazyRow) с items(список) { item -> строка }: на экране создаются только
видимые строки, а данные легко заменить настоящими (из сети, базы). Остальные элементы столбца (заголовки и
т. п.) остаются отдельными item { }.

Карточки — список, только если они отличаются лишь текстом, картинкой или заливкой и у них нет своего
поведения (показ / скрытие, смена текста, анимации, состояния): иначе — обычный столбец, как раньше.
"""

from __future__ import annotations

from app.core.document import tree

MIN_ROWS = 3


def _r(v: float) -> int:
    return round(v)


def signature(n, drawables: dict, in_role: bool = False) -> tuple:
    """Устройство элемента без того, чем карточки списка могут отличаться (текст, картинка, заливка)."""
    in_role = in_role or bool(n.role)
    bindable_fill = n.type in ("rect", "ellipse", "frame", "vector") and n.gradient == "none" and not in_role \
        and n.backdrop_blur <= 0
    sizing_free = n.type == "text" or n.sizing_h == "hug" or n.sizing_h == "fill"
    return (n.type, n.role, n.layout, n.main_align, n.cross_align, n.sizing_h, n.sizing_v, n.visible,
            None if sizing_free else _r(n.w), None if n.type == "text" or n.sizing_v != "fixed" else _r(n.h),
            round(n.radius, 1), n.stroke, round(n.stroke_width, 1), n.gradient, n.fill2, n.elevation,
            n.shadow_color, round(n.opacity, 2), n.font_size, n.font_weight, n.font_family, n.text_color,
            n.text_case, n.max_lines, n.align, n.path if n.type == "vector" else "",
            None if bindable_fill else n.fill,
            # картинка: в шаблоне — painterResource(item.…); в стандартном компоненте — как в дизайне
            (n.asset_id in drawables) if n.type == "image" and not in_role else (n.asset_id if n.type == "image" else ""),
            tuple(signature(c, drawables, in_role) for c in (n.children if n.is_container else [])))


def runs(children: list, drawables: dict, ok) -> list[tuple[int, int]]:
    """Участки [начало, конец) из MIN_ROWS и более одинаковых карточек подряд; ok(карточка) — можно ли в список."""
    out, i = [], 0
    sigs = [signature(c, drawables) if c.is_frame and c.visible and ok(c) else None for c in children]
    while i < len(children):
        j = i + 1
        if sigs[i] is not None:
            while j < len(children) and sigs[j] == sigs[i]:
                j += 1
            if j - i >= MIN_ROWS:
                out.append((i, j))
                i = j
                continue
        i = j
    return out


def fields(rows: list) -> list[tuple[int, str]]:
    """Чем карточки отличаются: (номер элемента в обходе шаблона, свойство text / image / fill)."""
    walks = [[d for d, _, _ in tree.walk([r])] for r in rows]
    out = []
    for i, n in enumerate(walks[0]):
        for prop, attr in (("text", "text"), ("image", "asset_id"), ("fill", "fill")):
            if prop == "text" and n.type != "text" or prop == "image" and n.type != "image":
                continue
            if prop == "fill" and n.type in ("text", "image"):
                continue
            if len({getattr(w[i], attr) for w in walks}) > 1:
                out.append((i, prop))
    return out
