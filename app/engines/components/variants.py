"""Готовые наборы вариантов компонента: «Размер» (S / M / L), «Стиль» (заливка / тональный / контур / текст),
«Тема» (как в проекте / светлая или тёмная). Без Qt.

Вариант — переопределения поверх мастера (как состояния), но выбираются у копии по каждому свойству отдельно:
например «Размер = L» и «Стиль = Контур» одновременно. Первое значение свойства — мастер без изменений.
"""

from __future__ import annotations

from dataclasses import replace

from app.core.document import tree
from app.core.document.model import ROOT_REF, Appearance, ComponentDef

PRESET_AXES = {"size": "Размер", "style": "Стиль", "theme": "Тема"}
_BUTTON_ROLES = {"Заливка": "m3.button_filled", "Тональный": "m3.button_tonal", "Контур": "m3.button_outlined",
                 "Текст": "m3.button_text"}
_ICON_ROLES = {"Заливка": "m3.icon_button_filled", "Тональный": "m3.icon_button_tonal",
               "Контур": "m3.icon_button_outlined", "Текст": "m3.icon_button"}


def _ref(defn: ComponentDef, n) -> str:
    return ROOT_REF if n is defn.root else n.id


def _scaled(defn: ComponentDef, k: float, font_k: float) -> dict:
    out: dict[str, dict] = {}
    for n, _, _ in tree.walk([defn.root]):
        props = {}
        if n.type == "text":
            props["font_size"] = round(n.font_size * font_k, 2)
        else:
            if n.sizing_h == "fixed" and n is not defn.root or n.type in ("vector", "ellipse", "rect") \
                    and n.sizing_h == "fixed":
                props["w"] = round(n.w * k, 2)
            if n.sizing_v == "fixed":
                props["h"] = round(n.h * k, 2)
            if n.is_frame:
                for p in ("pad_t", "pad_r", "pad_b", "pad_l", "gap"):
                    if getattr(n, p):
                        props[p] = round(getattr(n, p) * k, 2)
            if n.radius:
                props["radius"] = round(n.radius * k, 2)
        if props:
            out[_ref(defn, n)] = props
    return out


def size_variants(defn: ComponentDef) -> dict:
    return {"M": {}, "S": _scaled(defn, 0.8, 0.86), "L": _scaled(defn, 1.25, 1.14)}


def style_variants(defn: ComponentDef, sch: dict, k: float) -> dict:
    """Стили кнопки Material 3 для любого компонента: корень и его тексты и значки.
    У кнопок Material 3 меняется и роль — в коде Android это Button / FilledTonalButton / OutlinedButton / TextButton."""
    role = defn.root.role
    roles = _BUTTON_ROLES if role in _BUTTON_ROLES.values() else _ICON_ROLES if role in _ICON_ROLES.values() else {}

    def recolor(fill: str, stroke: str, sw: float, fg: str, style: str) -> dict:
        out = {ROOT_REF: {"fill": fill, "stroke": stroke, "stroke_width": sw,
                          **({"role": roles[style]} if roles else {})}}
        for n, _, _ in tree.walk(defn.root.children):
            if n.type == "text":
                out[n.id] = {"text_color": fg}
            elif n.type == "vector":
                out[n.id] = {"fill": fg}
        return out
    first = {ROOT_REF: {"role": roles["Заливка"]}} if roles and role != roles["Заливка"] else {}
    return {"Заливка": first,
            "Тональный": recolor(sch["secondaryContainer"], "", 0.0, sch["onSecondaryContainer"], "Тональный"),
            "Контур": recolor("", sch["outline"], round(1 * k, 2), sch["primary"], "Контур"),
            "Текст": recolor("", "", 0.0, sch["primary"], "Текст")}


def theme_variants(defn: ComponentDef, ap: Appearance) -> dict:
    """«Как в проекте» и противоположная тема: цвета ролей Material 3 перекрашиваются."""
    from app.engines.material.restyle import _map, color_map
    other = "light" if ap.theme != "light" else "amoled"
    cmap = color_map(ap, replace(ap, theme=other))
    out: dict[str, dict] = {}
    for n, _, _ in tree.walk([defn.root]):
        props = {}
        for p in ("fill", "stroke", "text_color"):
            v = getattr(n, p)
            nv = _map(cmap, v)
            if v and nv != v:
                props[p] = nv
        if props:
            out[_ref(defn, n)] = props
    return {"Как в проекте": {}, "Светлая" if other == "light" else "Тёмная": out}


def add_preset(defn: ComponentDef, key: str, ap: Appearance, k: float) -> None:
    from app.engines.material.color import scheme
    if key == "size":
        defn.variants[PRESET_AXES[key]] = size_variants(defn)
    elif key == "style":
        defn.variants[PRESET_AXES[key]] = style_variants(defn, scheme(ap.accent, ap.theme != "light"), k)
    elif key == "theme":
        defn.variants[PRESET_AXES[key]] = theme_variants(defn, ap)
    else:
        raise KeyError(key)
