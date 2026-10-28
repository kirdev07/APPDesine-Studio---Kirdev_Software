"""Живые компоненты Material 3 в предпросмотре: переключатель, флажок, чип фильтра, радиокнопки, вкладки,
нижняя навигация, сегменты и ползунок меняют вид по нажатию, как настоящие компоненты. Без Qt.

Состояние хранится отдельно от логики прототипа: {id корня компонента: значение} — включено (bool),
выбранный пункт (int) или положение ползунка (0…1). Значение по умолчанию — как нарисовано в дизайне.
Вид меняется прямо в копии экрана предпросмотра (геометрия в пикселях экрана), дизайн не изменяется.
"""

from __future__ import annotations

from app.core.document import tree

TOGGLES = ("m3.switch", "m3.checkbox", "m3.chip_filter")
CHOICES = ("m3.radio_group", "m3.tabs", "m3.nav_bar", "m3.segmented")
LIVE_ROLES = TOGGLES + CHOICES + ("m3.slider",)


def _items(n):
    return [c for c in n.children if c.is_frame]


def _first(n, pred):
    return next((d for d in tree.descendants(n) if pred(d)), None)


def target(screen, chain: list[str]):
    """Живой компонент под нажатием: (корень, номер пункта или None). chain — узел и его предки."""
    m = tree.node_map(screen)
    for i, nid in enumerate(chain):
        n = m.get(nid)
        if n is not None and n.is_frame and n.role in LIVE_ROLES:
            idx = None
            if n.role in CHOICES:
                below = set(chain[:i])
                idx = next((j for j, it in enumerate(_items(n)) if it.id in below), None)
                if idx is None:
                    return None, None
            return n, idx
    return None, None


def toggle(live: dict, root, index: int | None = None, frac: float | None = None) -> None:
    if root.role in TOGGLES:
        live[root.id] = not live.get(root.id, True)
    elif root.role in CHOICES and index is not None:
        live[root.id] = index
    elif root.role == "m3.slider" and frac is not None:
        live[root.id] = max(0.0, min(1.0, frac))


def selected(n) -> int:
    """Какой пункт выбран в дизайне (по виду): меню — заливка индикатора, вкладки — полоска снизу,
    сегменты — заливка пункта, радиокнопки — закрашенная точка. Не видно — первый."""
    items = _items(n)
    for i, it in enumerate(items):
        if n.role == "m3.nav_bar":
            pill = next((c for c in it.children if c.is_frame), None)
            on = pill is not None and bool(pill.fill)
        elif n.role == "m3.tabs":
            rects = [c for c in it.children if c.type == "rect"]
            on = bool(rects) and bool(rects[-1].fill)
        elif n.role == "m3.segmented":
            on = bool(it.fill)
        elif n.role == "m3.radio_group":
            on = any(d.type == "ellipse" and d.fill and d.w < 14 * 3 for d in tree.descendants(it))
        else:
            on = False
        if on:
            return i
    return 0


def restyle(n, index: int, sch: dict) -> None:
    """Нарисовать пункт index выбранным прямо в дизайне (копия меню на другом экране)."""
    if n.role in _APPLY and n.role in CHOICES:
        _APPLY[n.role](n, index, sch, 1.0)


def slider_fraction(root, x: float) -> float:
    thumb = next((c for c in root.children if c.type == "ellipse"), None)
    tw = thumb.w if thumb is not None else 0
    span = root.w - tw
    return (x - root.x - tw / 2) / span if span > 0 else 0.0


def apply(screen, live: dict, sch: dict, u: float) -> None:
    """Применить состояние живых компонентов к копии экрана; sch — роли цвета Material 3, u — px в dp."""
    if not live:
        return
    m = tree.node_map(screen)
    for nid, value in live.items():
        n = m.get(nid)
        if n is not None and n.role in LIVE_ROLES:
            _APPLY[n.role](n, value, sch, u)


def _switch(n, on, s, u):
    track = _first(n, lambda d: d.is_frame and d.children and d.children[0].type == "ellipse")
    if track is None or on:
        return
    thumb = track.children[0]
    track.fill, track.stroke, track.stroke_width = s["surfaceContainerHighest"], s["outline"], 2 * u
    thumb.w = thumb.h = 16 * u
    thumb.x, thumb.y = track.x + 8 * u, track.y + (track.h - thumb.w) / 2
    thumb.fill = s["outline"]


def _checkbox(n, on, s, u):
    box = _first(n, lambda d: d.is_frame and any(c.type == "vector" for c in d.children))
    if box is None or on:
        return
    box.fill, box.stroke, box.stroke_width = "", s["onSurfaceVariant"], 2 * u
    for c in box.children:
        c.visible = False


def _chip(n, on, s, u):
    if on:
        return
    n.fill, n.stroke, n.stroke_width = "", s["outline"], u
    for c in n.children:
        if c.type == "vector":
            c.visible = False
        elif c.type == "text":
            c.text_color = s["onSurfaceVariant"]


def _radio(n, sel, s, u):
    rings = [_first(it, lambda d: d.is_frame and d.stroke) for it in _items(n)]
    dot = next((c for r in rings if r is not None for c in r.children), None)
    if dot is None or not 0 <= sel < len(rings) or rings[sel] is None:
        return
    for r in rings:
        if r is not None:
            r.children = [c for c in r.children if c is not dot]
    for i, r in enumerate(rings):
        if r is not None:
            r.stroke = s["primary"] if i == sel else s["onSurfaceVariant"]
    ring = rings[sel]
    dot.x, dot.y = ring.x + (ring.w - dot.w) / 2, ring.y + (ring.h - dot.h) / 2
    dot.fill = s["primary"]
    ring.children.append(dot)


def _tabs(n, sel, s, u):
    for i, it in enumerate(_items(n)):
        on = i == sel
        for c in it.children:
            if c.type == "text":
                c.text_color = s["primary"] if on else s["onSurfaceVariant"]
        rects = [c for c in it.children if c.type == "rect"]
        if rects:
            rects[-1].fill = s["primary"] if on else ""


def _nav(n, sel, s, u):
    for i, it in enumerate(_items(n)):
        on = i == sel
        pill = next((c for c in it.children if c.is_frame), None)
        if pill is not None:
            pill.fill = s["secondaryContainer"] if on else ""
            for c in pill.children:
                if c.type == "vector":
                    c.fill = s["onSecondaryContainer"] if on else s["onSurfaceVariant"]
        for c in it.children:
            if c.type == "text":
                c.text_color = s["onSurface"] if on else s["onSurfaceVariant"]
                c.font_weight = 600 if on else 500


def _segmented(n, sel, s, u):
    for i, it in enumerate(_items(n)):
        on = i == sel
        it.fill = s["secondaryContainer"] if on else ""
        for c in it.children:
            if c.type == "text":
                c.text_color = s["onSecondaryContainer"] if on else s["onSurface"]
            elif c.type == "vector":
                c.visible = on


def _slider(n, frac, s, u):
    rects = [c for c in n.children if c.type == "rect"]
    thumb = next((c for c in n.children if c.type == "ellipse"), None)
    if len(rects) < 2 or thumb is None:
        return
    active, rest = rects[0], rects[-1]
    span = n.w - thumb.w
    active.x, active.w = n.x, max(0.0, frac * span)
    thumb.x = n.x + active.w
    rest.x, rest.w = thumb.x + thumb.w, max(0.0, span - active.w)


_APPLY = {"m3.switch": _switch, "m3.checkbox": _checkbox, "m3.chip_filter": _chip, "m3.radio_group": _radio,
          "m3.tabs": _tabs, "m3.nav_bar": _nav, "m3.segmented": _segmented, "m3.slider": _slider}
