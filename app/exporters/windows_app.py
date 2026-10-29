"""Экраны Windows → запускаемое приложение Windows на Python + PySide6 (версия 1.32). Без Qt.

Пакет windows_app/: ui.json (экраны, элементы с их видом и положением, правила нажатий, переменные), app_runtime.py
(строит окна по ui.json: роли Fluent → настоящие виджеты Qt, остальное — рамки и надписи; прокрутка, переходы,
«Назад», показ / скрытие, тексты и переменные), main.py (запуск), картинки в assets/, README.md и
requirements.txt. Среда выполнения только читает данные — кода из проекта в приложении нет.
"""

from __future__ import annotations

import json
import re

from app.core.document import tree
from app.core.document.model import ProjectDocument, Screen

ROOT = "windows_app"

# роль → вид виджета в приложении
WIDGETS = {"win.button": "button", "win.button_accent": "accent_button", "win.textbox": "textbox",
           "win.search": "search", "win.checkbox": "checkbox", "win.toggle": "toggle", "win.slider": "slider",
           "win.combobox": "combobox", "win.progress": "progress", "win.link": "link"}


def _svg(n) -> str:
    rule = ' fill-rule="evenodd"' if n.fill_rule == "evenodd" else ""
    fill = n.fill[:7] if n.fill else "none"  # только обводка — без заливки (иначе контур станет чёрным пятном)
    op = int(n.fill[7:9], 16) / 255 if n.fill and len(n.fill) == 9 else 1.0
    stroke = ""
    if n.stroke and n.stroke_width:
        sop = int(n.stroke[7:9], 16) / 255 if len(n.stroke) == 9 else 1.0
        stroke = f' stroke="{n.stroke[:7]}" stroke-opacity="{sop:g}" stroke-width="{n.stroke_width:g}"'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n.vb_w:g} {n.vb_h:g}">'
            f'<path d="{n.path}" fill="{fill}" fill-opacity="{op:g}"{rule}{stroke}/></svg>')


def _texts(n) -> list[str]:
    return [d.text for d in tree.descendants(n) if d.type == "text" and d.text]


def _named(n, name: str):
    return next((d for d in tree.descendants(n) if d.name == name), None)


def _state(n, kind: str) -> dict:
    """Состояние виджета — как нарисовано в дизайне (включён ли флажок, где бегунок, какой вариант выбран)."""
    if kind == "checkbox":
        box = next((d for d in n.children if d.type != "text"), None)
        return {"checked": bool(box is not None and box.fill)}
    if kind == "toggle":
        track = _named(n, "Дорожка")
        return {"checked": bool(track is not None and (track.main_align == "end" or track.fill))}
    if kind in ("slider", "progress"):
        done = _named(n, "Пройдено" if kind == "slider" else "Выполнено")
        rest, whole = _named(n, "Осталось"), _named(n, "Индикатор")
        total = (done.w + rest.w if done is not None and rest is not None else 0) if kind == "slider" else \
            (whole.w if whole is not None else 0)
        return {"value": round(100 * done.w / total) if done is not None and total else 50}
    if kind == "radio":
        items = [c for c in n.children if c.type != "text"]
        on = [i for i, it in enumerate(items) if any(d.name == "Кольцо" and (d.fill or d.children)
                                                     for d in tree.descendants(it))]
        return {"selected": on[0] if on else 0}
    return {}


def _label(n) -> dict:
    """Вид подписи виджета — по первому тексту в дизайне (цвет, размер, насыщенность, шрифт)."""
    t = next((d for d in tree.descendants(n) if d.type == "text"), None)
    if t is None:
        return {}
    return {"color": t.text_color, "size": t.font_size, "weight": t.font_weight, "font": t.font_family}


def _node(n, parent, assets: dict) -> dict | None:
    px, py = (parent.x, parent.y) if parent is not None else (0.0, 0.0)
    d = {"id": n.id, "name": n.name, "x": round(n.x - px, 2), "y": round(n.y - py, 2), "w": round(n.w, 2),
         "h": round(n.h, 2), "visible": n.visible, "opacity": n.opacity,
         # растягиваемое окно: привязки к краям родителя и размер в раскладке (заполнить / фиксированный)
         "ch": n.constraint_h, "cv": n.constraint_v, "sh": n.sizing_h, "sv": n.sizing_v}
    if n.role == "win.titlebar":
        d["bar"] = True
    if n.is_group:
        d.update(kind="group", x=0, y=0, w=0, h=0, children=[c for c in (_node(c, parent, assets) for c in n.children)
                                                              if c])
        return d
    kind = WIDGETS.get(n.role) or ("radio" if n.role == "win.radio" else None)
    if not kind and n.is_frame and n.name == "Дорожка" and n.w <= 48 and n.h <= 24 and parent is not None             and parent.role != "win.slider":  # переключатель внутри карточки параметра — настоящий, без подписи
        d.update(kind="toggle", texts=[], label={}, style={},
                 checked=bool(n.main_align == "end" or n.fill))
        return d
    style = {"fill": n.fill, "stroke": n.stroke if n.stroke_width else "", "stroke_width": n.stroke_width,
             "radius": n.radius if n.type != "ellipse" else min(n.w, n.h) / 2}
    if kind:
        d.update(kind=kind, texts=_texts(n), label=_label(n), style=style, **_state(n, kind))
        if kind in ("button", "accent_button") and not n.fill:  # кнопка — вид из дизайна: заливка, обводка, углы
            box = next((c for c in tree.descendants(n) if c.type != "text" and c.fill), None)
            if box is not None:
                d["style"] = dict(style, fill=box.fill, radius=box.radius)
        return d
    d["style"] = style
    if n.type == "text":
        d.update(kind="text", text=n.text, color=n.text_color, font=n.font_family, size=n.font_size,
                 weight=n.font_weight, align=n.align, italic=n.italic, underline=n.decoration == "underline",
                 wrap=n.sizing_h != "hug")
        return d
    if n.type == "vector" and n.path:
        d.update(kind="svg", svg=_svg(n))
        return d
    if n.type == "image":
        name = assets.get(n.asset_id)
        d.update(kind="image", src=f"assets/{name}" if name else "", fit=n.fit)
        return d
    d["kind"] = "frame"
    if n.is_frame:
        d.update(layout=n.layout if n.auto_layout else "none", main=n.main_align, cross=n.cross_align,
                 pad_r=n.pad_r)
    if n.is_frame and n.scroll != "none" and n.children:
        leaves = [c for c, _, _ in tree.walk(n.children) if not c.is_group]
        d["scroll"] = n.scroll
        d["content_w"] = round(max([n.w] + [c.x + c.w - n.x + n.pad_r for c in leaves]), 2)
        d["content_h"] = round(max([n.h] + [c.y + c.h - n.y + n.pad_b for c in leaves]), 2)
        d["content_b"] = round(max([0.0] + [c.y + c.h - n.y + n.pad_b for c in leaves]), 2)  # низ последнего
    if n.is_container:
        d["children"] = [c for c in (_node(c, n, assets) for c in n.children) if c]
    return d


# события, которые работают в приложении: нажатие, двойное нажатие, удержание, наведение мышью, свайп мышью
# (протянуть дальше 48 пикселей), изменение текста в поле и открытие экрана
def _overlap(a0: float, a1: float, b0: float, b1: float) -> bool:
    return min(a1, b1) - max(a0, b0) > 1


def anchor(nodes: list[dict], pw: float, ph: float, free: bool = True) -> None:
    """Привязки по умолчанию («слева», «сверху») уточняются по месту в дизайне, чтобы окно растягивалось
    осмысленно: элемент во всю ширину родителя тянется, прижатый к правому краю — остаётся у края
    (узкий) или тянется (широкий); так же по высоте. Область между соседями (переписка между шапкой и полем
    ввода, лента между меню и правой колонкой) тянется до соседа, прижатого к краю. Заданные в дизайне
    привязки не меняются."""
    flat = []
    for n in nodes:  # дети группы лежат в том же родителе
        if n["kind"] == "group":
            flat += [c for c in _flat_dicts(n.get("children", []))]
        else:
            flat.append(n)
    loose_h = [n for n in flat if n.get("ch", "left") == "left"] if free else []
    loose_v = [n for n in flat if n.get("cv", "top") == "top"] if free else []
    for n in loose_h:
        left, right = n["x"] <= 1, abs(n["x"] + n["w"] - pw) <= 1
        if left and right:
            n["ch"] = "left_right"
        elif right:
            n["ch"] = "right" if n["w"] < pw / 2 else "left_right"
    for n in loose_v:
        top, bottom = n["y"] <= 1, abs(n["y"] + n["h"] - ph) <= 1
        if top and bottom:
            n["cv"] = "top_bottom"
        elif bottom:
            n["cv"] = "bottom" if n["h"] < ph / 2 else "top_bottom"
    for n in loose_h:  # упирается справа в узкий элемент у правого края — тянется до него
        if n.get("ch", "left") == "left" and any(
                s is not n and s.get("ch") == "right" and 0 <= s["x"] - (n["x"] + n["w"]) <= GAP
                and _overlap(n["y"], n["y"] + n["h"], s["y"], s["y"] + s["h"]) for s in flat):
            n["ch"] = "left_right"
    for n in loose_v:  # упирается снизу в элемент у нижнего края — тянется до него
        if n.get("cv", "top") == "top" and any(
                s is not n and s.get("cv") == "bottom" and 0 <= s["y"] - (n["y"] + n["h"]) <= GAP
                and _overlap(n["x"], n["x"] + n["w"], s["x"], s["x"] + s["w"]) for s in flat):
            n["cv"] = "top_bottom"
    for n in flat:
        if n.get("children"):
            cw = n["w"] if n.get("scroll") != "horizontal" else n.get("content_w", n["w"])
            chh = n["h"] if n.get("scroll") != "vertical" else n.get("content_h", n["h"])
            anchor(n["children"], cw, chh, n.get("layout", "none") == "none")


GAP = 32  # до соседа у края не дальше этого — область тянется до него


def _flat_all(nodes: list[dict]) -> list[dict]:
    out = []
    for n in nodes:
        out += [n] + _flat_all(n.get("children", []))
    return out


def _flat_dicts(nodes: list[dict]) -> list[dict]:
    out = []
    for n in nodes:
        out += _flat_dicts(n.get("children", [])) if n["kind"] == "group" else [n]
    return out


TRIGGERS = ("tap", "double_tap", "long_press", "hover_enter", "hover_leave", "swipe_left", "swipe_right", "swipe_up",
            "swipe_down", "text_changed", "screen_open")


def build_ui(doc: ProjectDocument, screens: list[Screen], assets: dict[str, str], fonts: list[str] = ()) -> dict:
    ids = {s.id for s in screens}
    from app.core.document.model import ARTBOARD_COLORS
    theme = doc.meta.appearance.theme
    bg = {"light": "#F3F3F3", "dark": "#202020", "amoled": "#000000", "gray": "#2B2B2B"}.get(
        theme, ARTBOARD_COLORS.get(theme, "#202020"))
    out_screens = []
    for s in screens:
        nodes = [x for x in (_node(n, None, assets) for n in s.nodes) if x]
        for pane in (n for n, _, _ in tree.walk(s.nodes) if n.role == "win.navpane"):  # подписи пунктов — в строку
            one_line = {d.id for d, _, _ in tree.walk([pane]) if d.type == "text"}
            for d in _flat_all(nodes):
                if d["id"] in one_line:
                    d["wrap"] = False
        anchor(nodes, s.width, s.height)
        out_screens.append({"id": s.id, "name": s.name, "w": s.width, "h": s.height, "bg": bg, "nodes": nodes})
    return {
        "title": doc.meta.title, "start": screens[0].id if screens else "", "accent": doc.meta.appearance.accent,
        "dark": theme != "light", "fonts": list(fonts),
        "screens": out_screens,
        "interactions": [{"screen": it.screen_id, "node": it.node_id, "trigger": it.trigger,
                          "condition": it.condition, "actions": it.actions}
                         for it in doc.interactions if it.screen_id in ids and it.trigger in TRIGGERS],
        "variables": [{"id": v.id, "name": v.name, "type": v.type, "default": v.default} for v in doc.variables],
    }


def skipped_triggers(doc: ProjectDocument, screens: list[Screen]) -> int:
    """Сколько правил с событиями, которых в приложении нет, в него не попало."""
    ids = {s.id for s in screens if s.platform == "windows"}
    return sum(1 for it in doc.interactions if it.screen_id in ids and it.trigger not in TRIGGERS)


def _safe(name: str, default: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name.rsplit(".", 1)[0]).strip("_") or default


def files(doc: ProjectDocument, screens: list[Screen]) -> dict[str, bytes]:
    """Файлы пакета windows_app/ для экранов Windows (пусто — экранов Windows нет)."""
    screens = [s for s in screens if s.platform == "windows"]
    if not screens:
        return {}
    nodes = [n for s in screens for n, _, _ in tree.walk(s.nodes)]
    used = {n.asset_id for n in nodes if n.type == "image" and n.asset_id}
    families = {n.font_family for n in nodes if n.type == "text"}
    assets, out, fonts = {}, {}, []
    for a in doc.assets:
        if a.id not in doc.asset_data or a.redistribution == "forbidden":
            continue
        if a.id in used:
            name = f"{_safe(a.name, 'image')}-{a.sha256[:8]}.{a.ext}"
            assets[a.id] = name
            out[f"{ROOT}/assets/{name}"] = doc.asset_data[a.id]
        elif a.kind == "font" and a.family in families and a.ext.lower() in ("ttf", "otf"):
            name = f"{_safe(a.name, 'font')}-{a.sha256[:8]}.{a.ext.lower()}"  # свой шрифт проекта
            fonts.append(f"assets/fonts/{name}")
            out[f"{ROOT}/assets/fonts/{name}"] = doc.asset_data[a.id]
    ui = build_ui(doc, screens, assets, fonts)
    out[f"{ROOT}/ui.json"] = json.dumps(ui, ensure_ascii=False, indent=1).encode("utf-8")
    out[f"{ROOT}/app_runtime.py"] = RUNTIME.encode("utf-8")
    out[f"{ROOT}/main.py"] = MAIN.encode("utf-8")
    out[f"{ROOT}/requirements.txt"] = b"PySide6>=6.6\n"
    out[f"{ROOT}/README.md"] = README.replace("{title}", doc.meta.title).encode("utf-8")
    return out


MAIN = '''"""Запуск приложения: python main.py (нужен Python 3.10+ и PySide6 — pip install -r requirements.txt)."""

import sys
from pathlib import Path

from app_runtime import run

if __name__ == "__main__":
    sys.exit(run(Path(__file__).with_name("ui.json")))
'''

README = '''# {title} — приложение Windows

Создано App Design Studio по экранам Windows из дизайна: Python + PySide6 (Qt 6).

## Запуск

```
pip install -r requirements.txt
python main.py
```

## Как устроено

- `ui.json` — экраны, элементы (вид, положение, роли Fluent), правила нажатий и переменные из дизайна.
- `app_runtime.py` — строит окна по `ui.json`: кнопки, поля, флажки, переключатели, ползунки, списки выбора и
  индикаторы — настоящие виджеты Qt; рамки, надписи и значки — как в дизайне; переходы между экранами, «Назад»
  (Esc), показ и скрытие, тексты и переменные работают.
- Окно — размера экрана из дизайна; для адаптивной раскладки замените абсолютные положения на макеты Qt.

## Сборка в EXE

```
pip install pyinstaller
pyinstaller --noconsole --name App --add-data "ui.json;." --add-data "assets;assets" main.py
```
'''

RUNTIME = r'''"""Среда приложения: окно по описанию ui.json (созданному App Design Studio). Только данные — без выполнения кода."""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QObject, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QAbstractButton, QAbstractSlider, QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame,
                               QGraphicsOpacityEffect, QLabel, QLineEdit, QMainWindow, QProgressBar, QPushButton,
                               QScrollArea, QSlider, QStackedWidget, QVBoxLayout, QWidget)

BASE = Path(__file__).resolve().parent
MAX_DEPTH = 8  # «при открытии экрана → другой экран» по кругу не зацикливает приложение


def _css_color(c: str) -> str:
    c = (c or "").lstrip("#")
    if len(c) == 8:
        return f"rgba({int(c[0:2], 16)}, {int(c[2:4], 16)}, {int(c[4:6], 16)}, {int(c[6:8], 16)})"
    return f"#{c}" if c else "transparent"


def _qcolor(c: str) -> QColor:
    c = (c or "").lstrip("#")
    if len(c) == 8:  # в дизайне #RRGGBBAA
        return QColor(int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), int(c[6:8], 16))
    return QColor("#" + c) if c else QColor(0, 0, 0, 0)


def _style(st: dict) -> str:
    out = [f"background: {_css_color(st.get('fill'))};"]
    if st.get("stroke"):
        out.append(f"border: {max(1, round(st.get('stroke_width') or 1))}px solid {_css_color(st['stroke'])};")
    else:
        out.append("border: none;")
    if st.get("radius"):
        out.append(f"border-radius: {round(st['radius'])}px;")
    return " ".join(out)


def coerce(var_type: str, value):
    """Значение → тип переменной (как в студии): да/нет, число или текст."""
    if var_type == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "да", "истина", "вкл")
        return bool(value)
    if var_type == "number":
        v = float(value) if isinstance(value, (int, float)) else float(str(value).replace(",", "."))
        if not math.isfinite(v):
            raise ValueError(value)
        return v
    return "" if value is None else str(value)


def format_value(val) -> str:
    if isinstance(val, bool):
        return "да" if val else "нет"
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val)


class Toggle(QCheckBox):
    """Переключатель Windows 11: дорожка-«пилюля» с бегунком, подпись слева."""

    def __init__(self, text: str, accent: str, dark: bool, parent=None):
        super().__init__(text, parent)
        self.accent, self.dark = QColor(accent), dark
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tw, th = 40, 20
        x, y = self.width() - tw - 1, (self.height() - th) / 2
        if self.isChecked():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.accent)
        else:
            p.setPen(QColor("#9A9A9A" if self.dark else "#616161"))
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(x + 0.5, y + 0.5, tw - 1, th - 1), th / 2, th / 2)
        knob = QColor("#000000" if self.dark and self.isChecked() else "#FFFFFF") if self.isChecked() else \
            QColor("#CFCFCF" if self.dark else "#5D5D5D")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(knob)
        cx = x + tw - th / 2 if self.isChecked() else x + th / 2
        p.drawEllipse(QRectF(cx - 6, y + th / 2 - 6, 12, 12))
        p.setPen(self.palette().color(QPalette.ColorRole.WindowText) if not self.property("fg") else
                 QColor(self.property("fg")))
        p.setFont(self.font())
        p.drawText(QRectF(0, 0, x - 8, self.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self.text())


class _Mark(QAbstractButton):
    """Флажок или радиокнопка Windows 11: квадрат / кольцо цвета акцента, подпись справа."""

    def __init__(self, text: str, radio: bool, accent: str, dark: bool, fg: str, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setAutoExclusive(radio)
        self.radio, self.accent, self.dark, self.fg = radio, QColor(accent), dark, QColor(fg)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return QSize(28 + self.fontMetrics().horizontalAdvance(self.text()), 28)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = (self.height() - 20) / 2
        box = QRectF(0.5, y + 0.5, 19, 19)
        on = self.isChecked()
        p.setPen(Qt.PenStyle.NoPen if on else QColor("#9A9A9A" if self.dark else "#8A8A8A"))
        p.setBrush(self.accent if on else QColor(0, 0, 0, 0))
        if self.radio:
            p.drawEllipse(box)
            if on:
                p.setBrush(QColor("#000000" if self.dark else "#FFFFFF"))
                p.drawEllipse(QRectF(6, y + 6, 8, 8))
        else:
            p.drawRoundedRect(box, 4, 4)
            if on:
                p.setPen(QPen(QColor("#000000" if self.dark else "#FFFFFF"), 1.6))
                p.drawPolyline([QPointF(5.5, y + 10), QPointF(8.5, y + 13), QPointF(14.5, y + 7)])
        p.setPen(self.fg)
        p.setFont(self.font())
        p.drawText(QRectF(28, 0, self.width() - 28, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())


LONG_MS, SWIPE_PX = 500, 48
MIN_SCALE = 0.7  # окно можно сузить до 70 % размера дизайна


SHRINK = ("search", "textbox", "combobox")  # в тесном ряду сужаются (не уже 40% дизайна)


def _stack_delta(flat: list, fills: set, dmain: float, horiz: bool) -> dict:
    """На сколько меняется размер каждого элемента стека по главной оси: «заполняющие» делят прирост поровну,
    при сжатии уменьшаются до нуля; чего не хватило — отдают поля ввода и поиска, потом промежутки ряда (ключ
    ("gap", i) — промежуток после элемента i). Пусто — двигать нечего."""
    key = "w" if horiz else "h"
    if dmain >= 0:
        return {i: dmain / len(fills) for i in fills} if fills else {}
    out, need = {}, -dmain
    total = sum(flat[i][key] for i in fills)
    if total > 0:
        k = min(1.0, need / total)
        for i in fills:
            out[i] = -flat[i][key] * k
        need -= total * k
    soft = [i for i, n in enumerate(flat) if horiz and n["kind"] in SHRINK]
    room = sum(flat[i][key] * 0.6 for i in soft)
    if need > 0 and room > 0:
        k = min(1.0, need / room)
        for i in soft:
            out[i] = out.get(i, 0.0) - flat[i][key] * 0.6 * k
        need -= room * k
    if need > 0 and horiz and len(flat) > 1:  # ряд всё ещё шире места — сжимаются промежутки (до четверти)
        gaps = [max(0.0, flat[i + 1]["x"] - flat[i]["x"] - flat[i]["w"]) for i in range(len(flat) - 1)]
        total_gap = sum(gaps)
        if total_gap > 0:
            k = min(0.75, need / total_gap)
            for i, g in enumerate(gaps):  # промежуток перед элементом i+1 — как уменьшение предыдущего
                out[("gap", i)] = -g * k
    return out if fills or out else {}


def _constrain(mode: str, pos: float, size: float, old: float, new: float) -> tuple[float, float]:
    """Привязка к краям родителя, когда он стал размером new вместо old."""
    if mode in ("right", "bottom"):
        return pos + new - old, size
    if mode in ("left_right", "top_bottom"):
        return pos, max(0.0, size + new - old)
    if mode == "center":
        return pos + (new - old) / 2, size
    if mode == "scale":
        k = new / old if old else 1.0
        return pos * k, size * k
    return pos, size


def _put(lab: QLabel, text: str) -> None:
    """Новый текст надписи: полный — в свойстве (на экране он может быть с многоточием)."""
    lab.setProperty("full", text)
    lab.setText(text)


class _Scrim(QWidget):
    """Затемнение под всплывающим окном: перекрывает экран, щелчок по нему закрывает окно."""

    def __init__(self, page: QWidget, close):
        super().__init__(page)
        self.close_cb = close
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(0, 0, 0, 90);")
        self.setGeometry(page.rect())
        self.show()
        self.raise_()

    def mousePressEvent(self, e):
        self.close_cb()


class _Events(QObject):
    """События мыши на виджете с правилами: нажатие, двойное нажатие, удержание, свайп, наведение.
    Действие выполняется, а сам виджет работает как обычно (событие не перехватывается)."""

    def __init__(self, fire, triggers: set, widget: QWidget):
        super().__init__(widget)
        self.fire, self.triggers, self.widget = fire, triggers, widget
        self.start = None
        self.seen = None  # событие, всплывшее от дочернего виджета к родителю, — не второй раз
        self.long_done = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(LONG_MS)
        self.timer.timeout.connect(self._long)

    def _long(self):
        self.long_done = True
        self.fire("long_press")

    def eventFilter(self, obj, e):
        t = e.type()
        if t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick):
            key = (t, e.timestamp())
            if key == self.seen:
                return False
            self.seen = key
        if t == QEvent.Type.Enter and obj is self.widget and "hover_enter" in self.triggers:
            self.fire("hover_enter")
        elif t == QEvent.Type.Leave and obj is self.widget and "hover_leave" in self.triggers:
            self.fire("hover_leave")
        elif t == QEvent.Type.MouseButtonPress and e.button() == Qt.MouseButton.LeftButton:
            self.start, self.long_done = e.globalPosition(), False
            if "long_press" in self.triggers:
                self.timer.start()
        elif t == QEvent.Type.MouseMove and self.start is not None:
            d = e.globalPosition() - self.start
            if max(abs(d.x()), abs(d.y())) > SWIPE_PX / 3:
                self.timer.stop()  # палец (мышь) поехал — это не удержание
        elif t == QEvent.Type.MouseButtonRelease and e.button() == Qt.MouseButton.LeftButton and self.start is not None:
            self.timer.stop()
            d = e.globalPosition() - self.start
            self.start = None
            if max(abs(d.x()), abs(d.y())) > SWIPE_PX:
                way = ("swipe_right" if d.x() > 0 else "swipe_left") if abs(d.x()) >= abs(d.y()) else \
                    ("swipe_down" if d.y() > 0 else "swipe_up")
                if way in self.triggers:
                    self.fire(way)
            elif not self.long_done and "tap" in self.triggers and not isinstance(obj, QAbstractButton):
                self.fire("tap")
        elif t == QEvent.Type.MouseButtonDblClick and e.button() == Qt.MouseButton.LeftButton:
            if "double_tap" in self.triggers:
                self.fire("double_tap")
        return False


class Screen(QWidget):
    def __init__(self, app: "App", data: dict):
        super().__init__()
        self.app, self.data = app, data
        self.byid: dict[str, list[QWidget]] = {}  # у группы — все её элементы
        self.texts: dict[str, QLabel] = {}
        self.design_h: dict[str, float] = {}  # высота надписи с текстом из дизайна: от неё считается рост
        self.inner: dict[str, QWidget] = {}  # содержимое прокручиваемых областей
        self.scrims: dict[str, QWidget] = {}  # затемнения под открытыми окнами
        self._seq = 0
        self.resize(round(data["w"]), round(data["h"]))
        self.setMinimumSize(round(data["w"] * MIN_SCALE), round(data["h"] * MIN_SCALE))
        self.setObjectName("screen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)  # без этого фон экрана не рисуется
        self.setStyleSheet(f"#screen {{ background: {data['bg']}; }}")
        for n in data["nodes"]:
            self.build(n, self)

    # ---------- растягиваемое окно ----------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        for s in self.scrims.values():
            s.setGeometry(self.rect())
        self.relayout()

    @staticmethod
    def _flat(nodes: list[dict]) -> list[dict]:
        out = []
        for n in nodes:  # дети группы лежат в том же родителе, что и группа
            out += Screen._flat(n.get("children", [])) if n["kind"] == "group" else [n]
        return out

    def relayout(self) -> None:
        """Заново разместить всё (текст, заданный правилом, мог стать длиннее). Если выросший текст увёл
        содержимое за нижний край, окно становится выше (не выше экрана компьютера)."""
        self._place(self.data["nodes"], self.data["w"], self.data["h"], self.width(), self.height(), None)
        base = round(self.data["h"] * MIN_SCALE)
        # сколько не влезает при самой низкой высоте окна (пробная раскладка — от нынешней высоты не зависит)
        self._low = 0.0
        self._place(self.data["nodes"], self.data["w"], self.data["h"], self.width(), base, None, dry=True)
        scr = QApplication.primaryScreen()
        cap = scr.availableGeometry().height() - 60 if scr is not None else 10 ** 5
        want = max(base, min(cap, round(self._low + 0.49)))
        if want != self.minimumHeight():
            self.setMinimumHeight(want)
            win = self.app  # окно задаёт свой предел сам (при переходе на экран) — обновить и его
            if self.app.current is self:
                win.setMinimumHeight(self.minimumHeight() + max(0, win.height() - self.height()))
                if win.height() < win.minimumHeight():
                    win.resize(win.width(), win.minimumHeight())

    def _text_font(self, n, lab: QLabel, w: float) -> QFont:
        """Шрифт надписи при ширине w: короткая строка или самое длинное слово, которые не влезают, —
        шрифт меньше (до 60%), а не обрезка; абзацы не уменьшаются — переносятся."""
        f = lab.font()
        f.setPixelSize(max(1, round(n["size"])))
        fm = QFontMetrics(f)
        text = lab.property("full") or lab.text()
        single = not n.get("wrap") or self.design_h.get(n["id"], 0) < fm.lineSpacing() * 1.6
        full = fm.horizontalAdvance(text)
        word = max((fm.horizontalAdvance(x) for x in text.replace("-", "- ").split()),
                   default=0)  # слово не переносится (по дефису — переносится)
        need = full if single and len(text) <= 24 else (word if n.get("wrap") else 0)
        if need > w >= need * 0.6:
            f.setPixelSize(max(1, int(n["size"] * w / need)))
        if f.pixelSize() != lab.font().pixelSize():
            lab.setFont(f)
        return f

    def _fit(self, n, w: float, h: float) -> tuple[float, float]:
        """(высота на экране, на сколько сдвинуть то, что ниже) при ширине w. Текст с переносом в узком окне
        выше — соседи ниже сдвигаются; при ширине как в дизайне ничего не двигается, а надпись лишь не
        обрезает низ букв. Карточка растёт вместе с текстом внутри."""
        if n["kind"] == "text":
            lab = self.texts.get(n["id"])
            if lab is None or lab.isHidden():
                return h, 0.0
            self._text_font(n, lab, w)
            need = float(lab.heightForWidth(max(1, round(w))) if n.get("wrap") else lab.sizeHint().height())
            at_design = self.design_h.get(n["id"], need)  # текст из дизайна при ширине из дизайна
            push = max(0.0, need - max(h, at_design))
            if n.get("wrap") and need < at_design and abs(h - at_design) <= 3:  # шире окно — строк меньше,
                push = need - at_design                                           # то, что ниже, подтягивается
                return h + push, push
            return max(h + push, need), push
        if n["kind"] == "textbox":  # подпись и поле — во всю нужную высоту, рамка снизу не срезается
            ws = self.byid.get(n["id"], [])
            return (max(h, float(ws[0].sizeHint().height())) if ws else h), 0.0
        if n["kind"] == "frame" and n.get("children") and not n.get("scroll"):
            ws = self.byid.get(n["id"], [])
            if ws and ws[0].isHidden():
                return h, 0.0
            grow = self._place(n["children"], n["w"], n["h"], w, h, n, dry=True)
            low = max((c["y"] + c["h"] for c in self._flat(n["children"])), default=0.0)
            spare = max(0.0, h - low)  # свободное место внизу рамки (при её нынешней высоте) — сначала занимается оно
            push = max(0.0, grow - spare) if grow > 0 else (grow if spare < 2 else 0.0)
            return h + push, push
        return h, 0.0

    def _place(self, nodes, ow, oh, nw, nh, box, dry: bool = False) -> float:
        """Новое место элементов, когда родитель стал nw × nh вместо ow × oh: в раскладке-стеке растут элементы
        «заполнить» (остальные сдвигаются за ними), в обычном контейнере — по привязкам к краям. Текст с
        переносом в узком окне становится выше, а то, что под ним, сдвигается вниз. Возвращает, на сколько
        выросло содержимое по высоте; dry — только посчитать, ничего не двигая."""
        flat = self._flat(nodes)
        dw, dh = nw - ow, nh - oh
        stack = box is not None and box.get("layout") in ("horizontal", "vertical")
        if box is not None and box.get("layout") in ("grid", "wrap"):  # сетка: колонки шире / уже вместе с окном
            grow = 0.0
            for n in flat:
                x, w = _constrain("scale", n["x"], n["w"], ow, nw)
                h, push = self._fit(n, w, n["h"])
                grow = max(grow, push)
                if not dry:
                    self._set(n, x, n["y"], w, h)
            return grow
        if not stack:
            placed = []
            bar = max((n["y"] + n["h"] for n in flat if n.get("bar")), default=0.0)  # строка заголовка окна
            for n in flat:
                x, w = _constrain(n.get("ch", "left"), n["x"], n["w"], ow, nw)
                y, h = _constrain(n.get("cv", "top"), n["y"], n["h"], oh, nh)
                if bar and not n.get("bar") and n.get("cv") in ("center", "bottom") and y < bar + 8:
                    y = min(n["y"], bar + 8)  # в низком окне — под заголовком (окно станет выше, если надо)
                placed.append([n, x, y, w, h, *self._fit(n, w, h)])
            base = max((y + h for _, _, y, _, h, _, _ in placed), default=0.0)
            for p in placed:  # то, что ниже выросшего текста (и под ним по ширине), сдвигается вниз
                n = p[0]
                p[2] += sum(q[6] for q in placed if q[6] != 0 and q[0] is not n
                            and n["y"] >= q[0]["y"] + q[0]["h"] - 1
                            and min(n["x"] + n["w"], q[0]["x"] + q[0]["w"]) - max(n["x"], q[0]["x"]) > 1)
            if not dry:
                for n, x, y, w, h, draw, _ in placed:
                    self._set(n, x, y, w, draw)
            low = max((y + h + g for _, _, y, _, h, _, g in placed), default=0.0)
            if box is None:
                self._low = low  # низ всего содержимого экрана (для высоты окна)
            return max(0.0, low - base)
        horiz = box["layout"] == "horizontal"
        dmain, dcross = (dw, dh) if horiz else (dh, dw)
        fills = {i for i, n in enumerate(flat) if n.get("sh" if horiz else "sv") == "fill"}
        delta = _stack_delta(flat, fills, dmain, horiz)
        shift = 0.0
        grow = pushed = 0.0
        for i, n in enumerate(flat):
            mp, ms = (n["x"], n["w"]) if horiz else (n["y"], n["h"])
            cp, cs = (n["y"], n["h"]) if horiz else (n["x"], n["w"])
            if delta:
                mp += shift
                ms, shift = max(0.0, ms + delta.get(i, 0.0)), shift + delta.get(i, 0.0)
                shift += delta.get(("gap", i), 0.0)
            elif box.get("main") == "center":
                mp += dmain / 2
            elif box.get("main") == "end":
                mp += dmain
            elif box.get("main") == "space_between" and len(flat) > 1:
                mp += dmain * i / (len(flat) - 1)
            if n.get("sv" if horiz else "sh") == "fill" or box.get("cross") == "stretch":
                cs = max(0.0, cs + dcross)
            elif box.get("cross") == "center":
                cp += dcross / 2
            elif box.get("cross") == "end":
                cp += dcross
            if not horiz and (n["kind"] == "text" or n.get("layout") == "horizontal"):  # надпись и ряд — не шире
                # места в столбце (иначе их режет край); ряд тогда сжимает промежутки
                room = nw - cp - box.get("pad_r", 0.0)
                cs = max(1.0, min(cs, room))
            if horiz:
                cs2, push = self._fit(n, ms, cs)  # в ряду текст растёт вниз, соседей не двигает
                grow = max(grow, push)
                if not dry:
                    self._set(n, mp, cp, ms, cs2)
            else:
                mp += pushed  # в столбце следующие элементы — ниже выросшего текста
                ms2, push = self._fit(n, cs, ms)
                pushed += push
                if not dry:
                    self._set(n, cp, mp, cs, ms2)
        return max(grow, pushed)

    def _set(self, n, x, y, w, h) -> None:
        for wd in self.byid.get(n["id"], [])[:1]:
            wd.setGeometry(round(x), round(y), max(1, round(w)), max(1, round(h)))
        lab = self.texts.get(n["id"]) if n["kind"] == "text" else None
        if lab is not None:
            f = self._text_font(n, lab, w)
            text = lab.property("full") or lab.text()
            if not n.get("wrap"):  # строка без переноса не влезает и так — с многоточием, целиком — в подсказке
                one = " ".join(text.splitlines())
                cut = QFontMetrics(f).elidedText(one, Qt.TextElideMode.ElideRight, max(1, round(w)))
                lab.setText(cut if cut != one else text)
                lab.setToolTip(text if cut != one else "")
        kids = n.get("children")
        if not kids or n["kind"] != "frame":
            return
        if n.get("scroll"):
            inner = self.inner.get(n["id"])
            if n["scroll"] == "vertical":  # ширина содержимого — по области, длина — как в дизайне (+ рост текста)
                grow = self._place(kids, n["w"], n["content_h"], w, n["content_h"], n)
                if inner is not None:  # не ниже области (фон до низа) и не длиннее, чем нужно (без пустой прокрутки)
                    inner.setFixedSize(max(1, round(w)), max(1, round(h), round(n.get("content_b", n["content_h"]) + grow)))
            else:
                if inner is not None:
                    inner.setFixedSize(inner.width(), max(1, round(h)))
                self._place(kids, n["content_w"], n["h"], n["content_w"], h, n)
            return
        self._place(kids, n["w"], n["h"], w, h, n)

    def _name(self, w: QWidget) -> str:
        self._seq += 1  # имя для правила стиля — своё, а не id из дизайна (в нём могут быть точки и пробелы)
        w.setObjectName(f"n{self._seq}")
        return w.objectName()

    def build(self, n: dict, parent: QWidget) -> list[QWidget]:
        if n["kind"] == "group":
            ws = [w for c in n.get("children", []) for w in self.build(c, parent)]
            for w in ws:
                if not n.get("visible", True):
                    w.setVisible(False)
                if n.get("opacity", 1) < 1:
                    self._opacity(w, n["opacity"])
        else:
            w = getattr(self, "make_" + n["kind"], self.make_frame)(n, parent)
            w.setGeometry(round(n["x"]), round(n["y"]), max(1, round(n["w"])), max(1, round(n["h"])))
            if n.get("opacity", 1) < 1:
                self._opacity(w, n["opacity"])
            w.setVisible(n.get("visible", True))
            ws = [w]
        self.byid[n["id"]] = ws
        triggers = self.app.handles(self.data["id"], n["id"])
        if triggers:
            for w in ws:
                self._wire(w, n["id"], triggers)
        return ws

    def _opacity(self, w: QWidget, value: float) -> None:
        eff = w.graphicsEffect()
        if isinstance(eff, QGraphicsOpacityEffect):
            value *= eff.opacity()
        eff = QGraphicsOpacityEffect(w)
        eff.setOpacity(value)
        w.setGraphicsEffect(eff)

    def _wire(self, w: QWidget, nid: str, triggers: set) -> None:
        """Правила элемента: нажатие у кнопок — их сигнал clicked, остальное — фильтр событий мыши."""
        sid = self.data["id"]
        fire = lambda trig: self.app.fire(sid, nid, trig)  # noqa: E731
        if triggers & {"tap", "double_tap", "long_press"}:
            w.setCursor(Qt.CursorShape.PointingHandCursor)
        if "text_changed" in triggers:
            edit = w if hasattr(w, "textChanged") else w.findChild(QLineEdit)  # поле с подписью — внутри
            if edit is not None:
                edit.textChanged.connect(lambda *_: fire("text_changed"))
        f = _Events(fire, triggers, w)
        for x in [w] + w.findChildren(QWidget):
            x.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            if x is not w and isinstance(x, (QAbstractSlider, QLineEdit)):
                continue  # перетаскивание ползунка и выделение текста — не свайп и не нажатие карточки
            x.installEventFilter(f)
            if isinstance(x, QAbstractButton) and "tap" in triggers:
                x.clicked.connect(lambda _=False: fire("tap"))

    # ---------- элементы ----------
    def make_frame(self, n, parent):
        if n.get("scroll"):
            vertical = n["scroll"] == "vertical"
            area = QScrollArea(parent)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setStyleSheet("QScrollArea { background: transparent; border: none; } "
                               "QScrollBar:vertical { width: 6px; background: transparent; } "
                               "QScrollBar:horizontal { height: 6px; background: transparent; } "
                               "QScrollBar::handle { background: rgba(128, 128, 128, 140); border-radius: 3px; } "
                               "QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }")
            area.viewport().setObjectName("vp")
            area.viewport().setStyleSheet("#vp { background: transparent; }")
            inner = QFrame()
            inner.setStyleSheet(f"#{self._name(inner)} {{ {_style(n['style'])} }}")
            inner.setFixedSize(round(n["w"] if vertical else n["content_w"]),
                               round(n["content_h"] if vertical else n["h"]))
            area.setWidget(inner)
            self.inner[n["id"]] = inner
            off, need = Qt.ScrollBarPolicy.ScrollBarAlwaysOff, Qt.ScrollBarPolicy.ScrollBarAsNeeded
            area.setHorizontalScrollBarPolicy(off if vertical else need)
            area.setVerticalScrollBarPolicy(need if vertical else off)
            for c in n.get("children", []):
                self.build(c, inner)
            return area
        f = QFrame(parent)
        f.setStyleSheet(f"#{self._name(f)} {{ {_style(n['style'])} }}")
        for c in n.get("children", []):
            self.build(c, f)
        return f

    def make_text(self, n, parent):
        lab = QLabel(n["text"], parent)
        lab.setProperty("full", n["text"])  # полный текст (на экране он может быть с многоточием)
        lab.setTextFormat(Qt.TextFormat.PlainText)  # «<b>» в тексте дизайна — просто символы
        font = QFont(n.get("font") or "Segoe UI")
        font.setPixelSize(max(1, round(n["size"])))
        font.setWeight(QFont.Weight(min(900, max(100, int(n.get("weight", 400))))))
        font.setItalic(bool(n.get("italic")))
        font.setUnderline(bool(n.get("underline")))
        lab.setFont(font)
        lab.setStyleSheet(f"color: {_css_color(n.get('color') or '#000000')}; background: transparent;")
        lab.setWordWrap(bool(n.get("wrap")))
        h = {"left": Qt.AlignmentFlag.AlignLeft, "center": Qt.AlignmentFlag.AlignHCenter,
             "right": Qt.AlignmentFlag.AlignRight}.get(n.get("align"), Qt.AlignmentFlag.AlignLeft)
        # строка без переноса — по центру своей рамки (с многоточием она остаётся на виду)
        lab.setAlignment(h | (Qt.AlignmentFlag.AlignTop if n.get("wrap") else Qt.AlignmentFlag.AlignVCenter))
        self.texts[n["id"]] = lab
        self.design_h[n["id"]] = float(lab.heightForWidth(max(1, round(n["w"]))) if n.get("wrap")
                                       else lab.sizeHint().height())
        return lab

    def make_svg(self, n, parent):
        w = QSvgWidget(parent)
        w.load(QByteArray(n["svg"].encode("utf-8")))
        w.setStyleSheet("background: transparent;")
        return w

    def make_image(self, n, parent):
        lab = QLabel(parent)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setStyleSheet("background: transparent;")
        pm = QPixmap(str(BASE / n["src"])) if n.get("src") else QPixmap()
        if not pm.isNull():
            w, h, fit = max(1, round(n["w"])), max(1, round(n["h"])), n.get("fit") or "fill"
            if fit == "cover":  # заполнить, лишнее обрезать по центру
                pm = pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
                pm = pm.copy((pm.width() - w) // 2, (pm.height() - h) // 2, w, h)
            elif fit in ("contain", "fit"):
                pm = pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            else:  # растянуть на всю рамку
                pm = pm.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            lab.setPixmap(pm)
        return lab

    def _first(self, n, default=""):
        return n["texts"][0] if n.get("texts") else default

    def _font(self, n) -> QFont:
        lb = n.get("label") or {}
        font = QFont(lb.get("font") or "Segoe UI")
        font.setPixelSize(max(1, round(lb.get("size") or 14)))
        font.setWeight(QFont.Weight(min(900, max(100, int(lb.get("weight") or 400)))))
        return font

    def _fg_raw(self, n) -> str:
        c = ((n.get("label") or {}).get("color") or ("#FFFFFF" if self.app.dark else "#1B1B1B"))[:7]
        return c

    def _fg(self, n) -> str:
        return _css_color((n.get("label") or {}).get("color") or ("#FFFFFF" if self.app.dark else "#1B1B1B"))

    def _caption(self, n, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setTextFormat(Qt.TextFormat.PlainText)
        lab.setFont(self._font(n))
        lab.setStyleSheet(f"color: {self._fg(n)}; background: transparent;")
        return lab

    def _box(self, parent, spacing=6):
        box = QWidget(parent)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(spacing)
        return box, lay

    def make_button(self, n, parent):
        b = QPushButton(self._first(n), parent)
        b.setFont(self._font(n))
        b.setStyleSheet(self.app.button_css(n, self._fg(n)))
        return b

    make_accent_button = make_button

    def make_textbox(self, n, parent):
        box, lay = self._box(parent)
        if len(n.get("texts", [])) > 1:
            lay.addWidget(self._caption(n, n["texts"][0]))
        edit = QLineEdit()
        edit.setPlaceholderText(n["texts"][-1] if n.get("texts") else "")
        if n.get("texts") and "пароль" in n["texts"][0].lower():  # поле пароля — ввод скрыт
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setMinimumHeight(32)
        edit.setFont(self._font(n))
        edit.setTextMargins(6, 0, 6, 0)
        edit.setStyleSheet(self._input_css())
        lay.addWidget(edit)
        return box

    def _input_css(self) -> str:
        """Поле ввода Windows 11: тонкая рамка, линия снизу темнее, при вводе — линия цвета акцента."""
        dark, acc = self.app.dark, self.app.accent
        bg, stroke, line, fg = (("#2D2D2D", "#3A3A3A", "#9A9A9A", "#FFFFFF") if dark
                                else ("#FFFFFF", "#E5E5E5", "#8A8A8A", "#1B1B1B"))
        return (f"QLineEdit {{ background: {bg}; color: {fg}; border: 1px solid {stroke}; "
                f"border-bottom: 1px solid {line}; border-radius: 4px; selection-background-color: {acc}; }} "
                f"QLineEdit:focus {{ border-bottom: 2px solid {acc}; }}")

    def make_search(self, n, parent):
        e = QLineEdit(parent)
        e.setPlaceholderText(self._first(n, "Поиск"))
        e.setClearButtonEnabled(True)
        e.setFont(self._font(n))
        e.setTextMargins(6, 0, 6, 0)
        e.setStyleSheet(self._input_css())
        pm = QPixmap(32, 32)  # значок лупы справа, как в поиске Windows 11
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#C5C5C5" if self.app.dark else "#5D5D5D"), 2.6))
        p.drawEllipse(5, 5, 16, 16)
        p.drawLine(19, 19, 27, 27)
        p.end()
        e.addAction(QIcon(pm), QLineEdit.ActionPosition.TrailingPosition)
        return e

    def make_checkbox(self, n, parent):
        c = _Mark(self._first(n), False, self.app.accent, self.app.dark, self._fg_raw(n), parent)
        c.setFont(self._font(n))
        c.setChecked(bool(n.get("checked")))
        return c

    def make_toggle(self, n, parent):
        c = Toggle(self._first(n), self.app.accent, self.app.dark, parent)
        c.setFont(self._font(n))
        c.setProperty("fg", (n.get("label") or {}).get("color", "")[:7] or None)
        c.setChecked(bool(n.get("checked")))
        return c

    def make_radio(self, n, parent):
        box, lay = self._box(parent, 2)
        texts = n.get("texts", [])
        if texts:
            lay.addWidget(self._caption(n, texts[0]))
        group = QButtonGroup(box)
        for i, t in enumerate(texts[1:]):
            r = _Mark(t, True, self.app.accent, self.app.dark, self._fg_raw(n))
            font = self._font(n)
            font.setWeight(QFont.Weight.Normal)  # варианты — обычным шрифтом (жирный — только заголовок)
            r.setFont(font)
            r.setMinimumHeight(28)
            r.setChecked(i == n.get("selected", 0))
            group.addButton(r)
            lay.addWidget(r)
        return box

    def make_slider(self, n, parent):
        box, lay = self._box(parent)
        if n.get("texts"):
            lay.addWidget(self._caption(n, n["texts"][0]))
        s = QSlider(Qt.Orientation.Horizontal)
        s.setValue(int(n.get("value", 50)))
        s.setMinimumHeight(22)
        dark, acc = self.app.dark, self.app.accent  # ползунок Windows 11: тонкая дорожка, круглый бегунок с точкой
        track, ring = ("#8A8A8A", "#454545") if dark else ("#8A8A8A", "#FFFFFF")
        s.setStyleSheet(f"QSlider::groove:horizontal {{ height: 4px; background: {track}; border-radius: 2px; }} "
                        f"QSlider::sub-page:horizontal {{ background: {acc}; border-radius: 2px; }} "
                        f"QSlider::handle:horizontal {{ width: 10px; height: 10px; margin: -8px 0; "
                        f"border-radius: 10px; background: {acc}; border: 5px solid {ring}; }} "
                        f"QSlider::handle:horizontal:hover {{ width: 12px; height: 12px; margin: -9px 0; "
                        f"border-radius: 11px; border: 5px solid {ring}; }}")
        lay.addWidget(s)
        return box

    def make_combobox(self, n, parent):
        box, lay = self._box(parent)
        texts = n.get("texts", [])
        if len(texts) > 1:
            lay.addWidget(self._caption(n, texts[0]))
        cb = QComboBox()
        cb.addItems(texts[1:] or texts or [""])
        cb.setMinimumHeight(32)
        lay.addWidget(cb)
        return box

    def make_progress(self, n, parent):
        box, lay = self._box(parent)
        if n.get("texts"):
            lay.addWidget(self._caption(n, n["texts"][0]))
        p = QProgressBar()
        p.setValue(int(n.get("value", 50)))
        p.setTextVisible(False)
        p.setFixedHeight(3)  # Windows 11: тонкая линия дорожки и полоса акцента толщиной 3 px поверх неё
        line = "#9A9A9A" if self.app.dark else "#8A8A8A"
        p.setStyleSheet(f"QProgressBar {{ border: none; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                        f"stop:0 transparent, stop:0.33 transparent, stop:0.34 {line}, stop:0.66 {line}, "
                        f"stop:0.67 transparent, stop:1 transparent); }} "
                        f"QProgressBar::chunk {{ border-radius: 1px; background: {self.app.accent_text}; }}")
        lay.addWidget(p)
        return box

    def make_link(self, n, parent):
        lab = QLabel(self._first(n), parent)
        lab.setTextFormat(Qt.TextFormat.PlainText)
        lab.setFont(self._font(n))
        lab.setStyleSheet(f"color: {self._fg(n)}; background: transparent;")
        lab.setCursor(Qt.CursorShape.PointingHandCursor)
        return lab


class App(QMainWindow):
    def __init__(self, ui: dict):
        super().__init__()
        self.ui = ui
        self.dark = bool(ui.get("dark"))
        self.accent = ui.get("accent") or "#0067C0"
        acc = QColor(self.accent)
        self.accent_text = acc.lighter(160).name() if self.dark and acc.lightness() < 110 else acc.name()
        self.setWindowTitle(ui.get("title") or "Приложение")
        self.types = {v["id"]: v.get("type", "text") for v in ui.get("variables", [])}
        self.vars = {}
        self.text_state: dict = {}  # (экран, элемент) → текст, заданный правилом: при возврате на экран тот же
        for v in ui.get("variables", []):
            try:
                self.vars[v["id"]] = coerce(self.types[v["id"]], v["default"])
            except (TypeError, ValueError):
                self.vars[v["id"]] = v["default"]
        self.screens = {s["id"]: s for s in ui["screens"]}
        self.stack: list[str] = []
        self.overlays: list[str] = []  # открытые всплывающие окна (закрываются по порядку)
        self.depth = 0
        self.pages = QStackedWidget()
        self.setCentralWidget(self.pages)
        self.current: Screen | None = None
        self.go(ui["start"])

    def button_css(self, n: dict, fg: str) -> str:
        st = n.get("style") or {}
        fill = st.get("fill") or (self.accent if n["kind"] == "accent_button" else "")
        base = QColor(_qcolor(fill)) if fill else QColor(255, 255, 255, 0)
        hover = base.lighter(112) if base.alpha() else QColor(128, 128, 128, 30)
        hover_css = f"rgba({hover.red()}, {hover.green()}, {hover.blue()}, {max(hover.alpha(), 30)})"
        border = (f"{max(1, round(st.get('stroke_width') or 1))}px solid {_css_color(st['stroke'])}"
                  if st.get("stroke") else "none")
        return (f"QPushButton {{ background: {_css_color(fill)}; color: {fg}; border: {border}; "
                f"border-radius: {round(st.get('radius') or 4)}px; padding: 6px 12px; }} "
                f"QPushButton:hover {{ background: {hover_css}; }} "
                f"QPushButton:pressed {{ background: {_css_color(fill)}; }}")

    def handles(self, sid: str, nid: str) -> set:
        """События, на которые у элемента есть правила."""
        return {i["trigger"] for i in self.ui["interactions"] if i["screen"] == sid and i["node"] == nid
                and i["trigger"] != "screen_open"}

    # ---------- переходы ----------
    def go(self, sid: str, remember: bool = True) -> None:
        if sid not in self.screens or self.depth >= MAX_DEPTH:
            return
        if remember and self.current is not None:
            self.stack.append(self.current.data["id"])
        page = Screen(self, self.screens[sid])
        for (s_id, nid), text in self.text_state.items():
            if s_id == sid and nid in page.texts:
                _put(page.texts[nid], self._fmt(text))
        self.pages.addWidget(page)
        self.pages.setCurrentWidget(page)
        if self.current is not None:
            self.pages.removeWidget(self.current)
            self.current.deleteLater()
        self.current = page
        self.overlays = []
        size = QSize(round(page.data["w"]), round(page.data["h"]))
        if size != getattr(self, "_design", None):  # экран другого размера — окно по дизайну, иначе размер остаётся
            self._design = size
            self.resize(size)
        self.setMinimumSize(page.minimumSize())
        self.depth += 1
        try:
            for it in self.ui["interactions"]:
                if it["screen"] == sid and it["trigger"] == "screen_open" and self.current is page:
                    self.run(it)
        finally:
            self.depth -= 1

    def back(self) -> None:
        if self.stack:
            self.go(self.stack.pop(), remember=False)

    def system_back(self) -> None:
        """Esc: сначала закрывается открытое окно, потом — переход назад."""
        if self.overlays:
            self.close_overlay()
        else:
            self.back()

    def close_overlay(self) -> None:
        if self.overlays and self.current is not None:
            nid = self.overlays.pop()
            for w in self.current.byid.get(nid, []):
                w.setVisible(False)
            scrim = self.current.scrims.pop(nid, None)
            if scrim is not None:
                scrim.deleteLater()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.system_back()
            return
        super().keyPressEvent(e)

    # ---------- логика ----------
    def tap(self, sid: str, nid: str) -> None:
        self.fire(sid, nid, "tap")

    def fire(self, sid: str, nid: str, trigger: str) -> None:
        for it in list(self.ui["interactions"]):  # все правила элемента — по порядку, пока экран тот же
            if self.current is None or self.current.data["id"] != sid:
                return
            if it["screen"] == sid and it["node"] == nid and it["trigger"] == trigger:
                self.run(it)

    def _ok(self, cond) -> bool:
        if not cond:
            return True
        vid = cond.get("var_id")
        if vid not in self.vars:
            return False
        a = self.vars[vid]
        try:
            b = coerce(self.types.get(vid, "text"), cond.get("value"))
            return {"==": lambda: a == b, "!=": lambda: a != b, "<": lambda: a < b, ">": lambda: a > b,
                    "<=": lambda: a <= b, ">=": lambda: a >= b}[cond.get("op", "==")]()
        except (TypeError, ValueError, KeyError):
            return False

    def run(self, it: dict) -> None:
        if not self._ok(it.get("condition")):
            return
        for a in it.get("actions", []):
            t, page = a.get("type"), self.current
            if t == "navigate":
                self.go(a.get("screen_id", ""))
                return
            if t == "back":
                self.back()
                return
            if page is None:
                continue
            if t == "close_overlay":  # закрыть последнее открытое окно
                self.close_overlay()
            elif t in ("set_visible", "open_overlay"):
                ws = page.byid.get(a.get("node_id", ""), [])
                mode = a.get("mode", "show")
                for w in ws:
                    w.setVisible(True if t == "open_overlay" or mode == "show" else
                                 False if mode == "hide" else not w.isVisible())
                    w.raise_()
                if ws and t == "open_overlay":
                    if a.get("scrim", True):  # затемнение: то, что под окном, не нажимается; щелчок — закрыть
                        scrim = _Scrim(page, self.close_overlay)
                        page.scrims[a["node_id"]] = scrim
                        for w in ws:
                            w.raise_()
                    self.overlays.append(a["node_id"])
            elif t == "set_text" and a.get("node_id") in page.texts:
                self.text_state[(page.data["id"], a["node_id"])] = str(a.get("text", ""))
                _put(page.texts[a["node_id"]], self._fmt(str(a.get("text", ""))))
                page.relayout()  # длинный текст — выше, то, что под ним, ниже
            elif t == "set_variable" and a.get("var_id") in self.vars:
                v, mode, kind = a["var_id"], a.get("mode", "set"), self.types.get(a["var_id"], "text")
                cur = self.vars[v]
                try:
                    if mode == "toggle":
                        new = (not bool(cur)) if kind == "bool" else cur
                    elif mode in ("increment", "decrement") and kind == "number":
                        step = coerce("number", a.get("value") or 1)
                        new = cur + step if mode == "increment" else cur - step
                    else:
                        new = coerce(kind, a.get("value"))
                except (TypeError, ValueError):
                    continue  # неверное значение — переменная не меняется
                self.vars[v] = new

    def _fmt(self, text: str) -> str:
        for v in self.ui.get("variables", []):
            text = text.replace("{" + v["name"] + "}", format_value(self.vars.get(v["id"], v["default"])))
        return text


def _palette(dark: bool, accent: str) -> QPalette:
    """Цвета обычных виджетов Qt под тему дизайна: в тёмной — тёмные поля и светлый текст."""
    p = QPalette()
    if dark:
        win, base, text, btn = "#202020", "#2D2D2D", "#FFFFFF", "#2D2D2D"
    else:
        win, base, text, btn = "#F3F3F3", "#FFFFFF", "#1B1B1B", "#FDFDFD"
    for role, c in ((QPalette.ColorRole.Window, win), (QPalette.ColorRole.Base, base),
                    (QPalette.ColorRole.AlternateBase, btn), (QPalette.ColorRole.Button, btn),
                    (QPalette.ColorRole.Text, text), (QPalette.ColorRole.WindowText, text),
                    (QPalette.ColorRole.ButtonText, text), (QPalette.ColorRole.ToolTipBase, base),
                    (QPalette.ColorRole.ToolTipText, text), (QPalette.ColorRole.Highlight, accent),
                    (QPalette.ColorRole.HighlightedText, "#FFFFFF")):
        p.setColor(role, QColor(c))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#9A9A9A" if dark else "#707070"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#6E6E6E" if dark else "#A0A0A0"))
    return p


def run(path: Path) -> int:
    ui = json.loads(Path(path).read_text(encoding="utf-8"))
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(_palette(bool(ui.get("dark")), ui.get("accent") or "#0067C0"))
    for f in ui.get("fonts", []):  # свои шрифты проекта
        QFontDatabase.addApplicationFont(str(BASE / f))
    win = App(ui)
    win.show()
    shot = os.environ.get("APP_SNAPSHOT")  # для проверки: снимок окна и выход
    if shot:
        app.processEvents()
        win.grab().save(shot)
        return 0
    return app.exec()
'''
