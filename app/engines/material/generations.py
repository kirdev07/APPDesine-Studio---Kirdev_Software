"""Поколения Material Design: вид компонентов по роли — Material 1 (2014), Material 2 (2018), Material 3 и
Material 3 Expressive (2025). Без Qt.

Меняется только вид (скругления, заглавные буквы на кнопках, цвет шапки, индикатор меню, тени, вид полей ввода),
содержимое и расположение — нет. Тот же перевод применяется к новым компонентам и при смене поколения в теме.
В коде Android остаётся библиотека Material 3, а форма и цвета берутся из дизайна — приложение выглядит как
выбранное поколение.
"""

from __future__ import annotations

from app.core.document import tree

GENERATIONS = (("m1", "Material 1 (2014)"), ("m2", "Material 2 (2018)"), ("m3", "Material 3"),
               ("m3x", "Material 3 Expressive (2025)"))
KEYS = tuple(k for k, _ in GENERATIONS)
OLD = ("m1", "m2")

BUTTONS = ("m3.button_filled", "m3.button_tonal", "m3.button_outlined", "m3.button_text", "m3.button_elevated")
FABS = ("m3.fab", "m3.fab_small", "m3.fab_large")
TOP_BARS = ("m3.top_app_bar", "m3.top_app_bar_center", "m3.top_app_bar_medium", "m3.top_app_bar_large")
CARDS = ("m3.card", "m3.product_card")
CHIPS = ("m3.chip_assist", "m3.chip_filter", "m3.chip_suggestion", "m3.chip_input")
WINDOWS = ("m3.dialog",)
SHEETS = ("m3.bottom_sheet", "m3.side_sheet")
FIELDS = ("m3.text_field", "m3.text_field_filled", "m3.password_field", "m3.text_area", "m3.date_field",
          "m3.dropdown_field", "m3.phone_field")

# скругления (dp) по поколениям; None — «капсула» (половина высоты)
RADIUS = {
    "button": {"m1": 2, "m2": 4, "m3": None, "m3x": None},
    "fab": {"m1": None, "m2": None, "m3": 16, "m3x": 20},
    "card": {"m1": 2, "m2": 4, "m3": 12, "m3x": 24},
    "chip": {"m1": None, "m2": None, "m3": 8, "m3x": 12},
    "window": {"m1": 2, "m2": 4, "m3": 28, "m3x": 32},
    "sheet": {"m1": 0, "m2": 4, "m3": 28, "m3x": 32},
    "field": {"m1": 0, "m2": 4, "m3": 4, "m3x": 12},
    "search": {"m1": 2, "m2": 4, "m3": None, "m3x": None},
    "segmented": {"m1": 2, "m2": 4, "m3": None, "m3x": None},
}


def _r(kind: str, gen: str, n, k: float) -> float:
    v = RADIUS[kind].get(gen, RADIUS[kind]["m3"])
    if v is not None:
        return round(v * k, 2)
    # «капсула»: половина высоты (ширина «по содержимому» до раскладки ещё условная); FAB — круг
    return round((min(n.w, n.h) if kind == "fab" else n.h) / 2, 2)


def _texts(n):
    return [d for d in tree.descendants(n) if d.type == "text"]


def _vectors(n):
    return [d for d in tree.descendants(n) if d.type == "vector"]


def _items(n):
    return [c for c in n.children if c.is_frame]


def nav_selected(n) -> int:
    """Выбранный пункт нижнего меню в любом поколении: индикатор («пилюля») или жирная подпись."""
    for i, it in enumerate(_items(n)):
        pill = next((c for c in it.children if c.is_frame), None)
        label = next((c for c in it.children if c.type == "text"), None)
        if (pill is not None and pill.fill) or (label is not None and label.font_weight >= 600):
            return i
    return 0


def nav_item_look(it, on: bool, gen: str, s: dict) -> None:
    """Пункт нижнего меню: M3 — «пилюля» за значком; M1/M2 — без неё, выбранный пункт цвета бренда."""
    pill = next((c for c in it.children if c.is_frame), None)
    old = gen in OLD
    if pill is not None:
        pill.fill = "" if old or not on else s["secondaryContainer"]
        for c in pill.children:
            if c.type == "vector":
                c.fill = (s["primary"] if old else s["onSecondaryContainer"]) if on else s["onSurfaceVariant"]
    for c in it.children:
        if c.type == "text":
            c.text_color = (s["primary"] if old else s["onSurface"]) if on else s["onSurfaceVariant"]
            c.font_weight = 600 if on else 500


def switch_track(n):
    """Дорожка переключателя (фрейм с бегунком-кругом) или None."""
    return next((d for d in tree.descendants(n) if d.is_frame and d.children and d.children[0].type == "ellipse"), None)


def switch_look(track, on: bool, gen: str, s: dict, k: float) -> None:
    """Переключатель по поколению. M1 / M2 — тонкая полупрозрачная дорожка и круглый бегунок с тенью, который
    выступает за неё; M3 — широкая дорожка-капсула с бегунком внутри."""
    thumb = track.children[0]
    if gen in OLD:
        track.w, track.h, track.radius = round(36 * k, 2), round(14 * k, 2), round(7 * k, 2)
        track.pad_l = track.pad_r = 0
        track.clip, track.stroke, track.stroke_width = False, "", 0
        track.fill = (s["primary"][:7] + "80") if on else (s["onSurface"][:7] + "4D")
        thumb.w = thumb.h = round(20 * k, 2)
        thumb.fill = s["primary"] if on else "#ECECEC"
        thumb.elevation = 1
    else:
        track.w, track.h, track.radius = round(52 * k, 2), round(32 * k, 2), round(16 * k, 2)
        track.pad_l = track.pad_r = round(4 * k, 2)
        track.clip = True
        track.fill = s["primary"] if on else s["surfaceContainerHighest"]
        track.stroke, track.stroke_width = ("", 0) if on else (s["outline"], round(2 * k, 2))
        thumb.w = thumb.h = round((24 if on else 16) * k, 2)
        thumb.fill = s["onPrimary"] if on else s["outline"]
        thumb.elevation = 0
    track.main_align = "end" if on else "start"


def restyle_component(n, gen: str, s: dict, k: float) -> bool:
    """Вид одного компонента по его роли под поколение. True — компонент узнан и перестроен."""
    r, old = n.role, gen in OLD
    if r in BUTTONS:
        n.radius = _r("button", gen, n, k)
        for t in _texts(n):
            t.text_case = "upper" if old else "none"
            t.letter_spacing = round(1.25 * k, 2) if old else 0.0
        if r in ("m3.button_filled", "m3.button_tonal"):
            n.elevation = 2 if old else 0
        return True
    if r in FABS:
        n.radius = _r("fab", gen, n, k)
        n.fill = s["primary"] if old else s["primaryContainer"]
        for v in _vectors(n):
            v.fill = s["onPrimary"] if old else s["onPrimaryContainer"]
        n.elevation = 3
        return True
    if r == "m3.fab_extended":
        n.radius = _r("fab", gen, n, k) if not old else round(n.h / 2, 2)
        for t in _texts(n):
            t.text_case = "upper" if old else "none"
        return True
    if r in TOP_BARS:
        vecs = _vectors(n)
        if old:  # шапка цвета бренда с тенью
            n.fill, n.elevation = s["primary"], 2
            for t in _texts(n):
                t.text_color = s["onPrimary"]
            for v in vecs:
                v.fill = s["onPrimary"]
        else:
            n.fill, n.elevation = s["surface"], 0
            for t in _texts(n):
                t.text_color = s["onSurface"]
            for i, v in enumerate(vecs):
                v.fill = s["onSurface"] if i == 0 else s["onSurfaceVariant"]
        return True
    if r == "m3.nav_bar":
        sel = nav_selected(n)
        n.fill = s["surface"] if old else s["surfaceContainer"]
        n.elevation = 3 if old else 0
        for i, it in enumerate(_items(n)):
            nav_item_look(it, i == sel, gen, s)
        return True
    if r == "m3.switch":
        track = switch_track(n)
        if track is None:
            return False
        switch_look(track, track.main_align == "end", gen, s, k)
        return True
    if r in CARDS:
        n.radius = _r("card", gen, n, k)
        n.elevation = 1 if old else n.elevation
        return True
    if r in CHIPS:
        n.radius = _r("chip", gen, n, k)
        return True
    if r in WINDOWS:
        n.radius = _r("window", gen, n, k)
        return True
    if r in SHEETS:
        v = _r("sheet", gen, n, k)
        n.radius, n.radius_bl, n.radius_br = v, 0, 0
        return True
    if r == "m3.search_bar":
        n.radius = _r("search", gen, n, k)
        return True
    if r == "m3.segmented":  # M1 / M2 — группа кнопок с малым скруглением и ЗАГЛАВНЫМИ подписями
        n.radius = _r("segmented", gen, n, k)
        for t in _texts(n):
            t.text_case = "upper" if old else "none"
        return True
    if r in FIELDS:
        box = next((c for c in n.children if c.is_frame and (c.stroke or c.fill)), None)
        if box is None:
            return False
        filled = r == "m3.text_field_filled"
        rad = _r("field", gen, box, k)
        if gen == "m1":  # только линия снизу
            box.fill, box.stroke_sides, box.radius = "", "b", 0
        elif gen == "m2" or filled:  # залитое поле с линией снизу и скруглением сверху
            box.fill, box.stroke_sides = s["surfaceContainerHighest"], "b"
            box.radius, box.radius_tl, box.radius_tr, box.radius_bl, box.radius_br = rad, rad, rad, 0, 0
        else:  # M3 / Expressive — контурное
            box.fill, box.stroke_sides = "", "trbl"
            box.radius, box.radius_tl, box.radius_tr, box.radius_bl, box.radius_br = rad, -1, -1, -1, -1
        box.stroke = box.stroke or s["outline"]
        box.stroke_width = box.stroke_width or round(1 * k, 2)
        return True
    return False


def apply(nodes, gen: str, s: dict, k: float) -> int:
    """Перестроить все узнанные компоненты в узлах (с вложенными). Возвращает их число."""
    count = 0
    for n, _, _ in tree.walk(nodes):
        if n.role and restyle_component(n, gen, s, k):
            count += 1
    return count
