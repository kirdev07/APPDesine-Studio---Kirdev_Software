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
         "h": round(n.h, 2), "visible": n.visible, "opacity": n.opacity}
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
    if n.is_frame and n.scroll != "none" and n.children:
        leaves = [c for c, _, _ in tree.walk(n.children) if not c.is_group]
        d["scroll"] = n.scroll
        d["content_w"] = round(max([n.w] + [c.x + c.w - n.x + n.pad_r for c in leaves]), 2)
        d["content_h"] = round(max([n.h] + [c.y + c.h - n.y + n.pad_b for c in leaves]), 2)
    if n.is_container:
        d["children"] = [c for c in (_node(c, n, assets) for c in n.children) if c]
    return d


TRIGGERS = ("tap", "screen_open")  # остальные (двойное нажатие, удержание, наведение) — пока только в прототипе


def build_ui(doc: ProjectDocument, screens: list[Screen], assets: dict[str, str], fonts: list[str] = ()) -> dict:
    ids = {s.id for s in screens}
    from app.core.document.model import ARTBOARD_COLORS
    theme = doc.meta.appearance.theme
    bg = {"light": "#F3F3F3", "dark": "#202020", "amoled": "#000000", "gray": "#2B2B2B"}.get(
        theme, ARTBOARD_COLORS.get(theme, "#202020"))
    return {
        "title": doc.meta.title, "start": screens[0].id if screens else "", "accent": doc.meta.appearance.accent,
        "dark": theme != "light", "fonts": list(fonts),
        "screens": [{"id": s.id, "name": s.name, "w": s.width, "h": s.height, "bg": bg,
                     "nodes": [x for x in (_node(n, None, assets) for n in s.nodes) if x]} for s in screens],
        "interactions": [{"screen": it.screen_id, "node": it.node_id, "trigger": it.trigger,
                          "condition": it.condition, "actions": it.actions}
                         for it in doc.interactions if it.screen_id in ids and it.trigger in TRIGGERS],
        "variables": [{"id": v.id, "name": v.name, "type": v.type, "default": v.default} for v in doc.variables],
    }


def skipped_triggers(doc: ProjectDocument, screens: list[Screen]) -> int:
    """Сколько правил с другими событиями (не нажатие и не открытие экрана) в приложение не попало."""
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

from PySide6.QtCore import QByteArray, QEvent, QObject, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPalette, QPen, QPixmap
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame,
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


class _Tap(QObject):
    """Нажатие на виджет с правилом: действие выполняется, а сам виджет работает как обычно."""

    def __init__(self, cb, parent):
        super().__init__(parent)
        self.cb = cb

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Type.MouseButtonRelease and e.button() == Qt.MouseButton.LeftButton:
            self.cb()
        return False


class Screen(QWidget):
    def __init__(self, app: "App", data: dict):
        super().__init__()
        self.app, self.data = app, data
        self.byid: dict[str, list[QWidget]] = {}  # у группы — все её элементы
        self.texts: dict[str, QLabel] = {}
        self._seq = 0
        self.setFixedSize(round(data["w"]), round(data["h"]))
        self.setObjectName("screen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)  # без этого фон экрана не рисуется
        self.setStyleSheet(f"#screen {{ background: {data['bg']}; }}")
        for n in data["nodes"]:
            self.build(n, self)

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
        if self.app.handles(self.data["id"], n["id"]):
            for w in ws:
                self._on_tap(w, n["id"])
        return ws

    def _opacity(self, w: QWidget, value: float) -> None:
        eff = w.graphicsEffect()
        if isinstance(eff, QGraphicsOpacityEffect):
            value *= eff.opacity()
        eff = QGraphicsOpacityEffect(w)
        eff.setOpacity(value)
        w.setGraphicsEffect(eff)

    def _on_tap(self, w: QWidget, nid: str) -> None:
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        cb = lambda: self.app.tap(self.data["id"], nid)  # noqa: E731
        if isinstance(w, QAbstractButton):
            w.clicked.connect(lambda _=False: cb())
            return
        f = _Tap(cb, w)
        for x in [w] + w.findChildren(QWidget):
            if not isinstance(x, QAbstractButton):
                x.installEventFilter(f)
            else:
                x.clicked.connect(lambda _=False: cb())

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
            area.viewport().setStyleSheet("background: transparent;")
            inner = QFrame()
            inner.setStyleSheet(f"#{self._name(inner)} {{ {_style(n['style'])} }}")
            inner.setFixedSize(round(n["w"] if vertical else n["content_w"]),
                               round(n["content_h"] if vertical else n["h"]))
            area.setWidget(inner)
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
        lab.setAlignment(h | Qt.AlignmentFlag.AlignTop)
        self.texts[n["id"]] = lab
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
        lay.addWidget(edit)
        return box

    def make_search(self, n, parent):
        e = QLineEdit(parent)
        e.setPlaceholderText(self._first(n, "Поиск"))
        e.setClearButtonEnabled(True)
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
        p.setFixedHeight(4)
        p.setStyleSheet(f"QProgressBar {{ border: none; border-radius: 2px; background: "
                        f"{'#3A3A3A' if self.app.dark else '#E5E5E5'}; }} "
                        f"QProgressBar::chunk {{ border-radius: 2px; background: {self.app.accent_text}; }}")
        lay.addWidget(p)
        return box

    def make_link(self, n, parent):
        lab = QLabel(self._first(n), parent)
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

    def handles(self, sid: str, nid: str) -> bool:
        return any(i["screen"] == sid and i["node"] == nid and i["trigger"] == "tap" for i in self.ui["interactions"])

    # ---------- переходы ----------
    def go(self, sid: str, remember: bool = True) -> None:
        if sid not in self.screens or self.depth >= MAX_DEPTH:
            return
        if remember and self.current is not None:
            self.stack.append(self.current.data["id"])
        page = Screen(self, self.screens[sid])
        self.pages.addWidget(page)
        self.pages.setCurrentWidget(page)
        if self.current is not None:
            self.pages.removeWidget(self.current)
            self.current.deleteLater()
        self.current = page
        self.overlays = []
        self.setFixedSize(page.size())
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
            for w in self.current.byid.get(self.overlays.pop(), []):
                w.setVisible(False)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.system_back()
            return
        super().keyPressEvent(e)

    # ---------- логика ----------
    def tap(self, sid: str, nid: str) -> None:
        for it in list(self.ui["interactions"]):  # все правила элемента — по порядку, пока экран тот же
            if self.current is None or self.current.data["id"] != sid:
                return
            if it["screen"] == sid and it["node"] == nid and it["trigger"] == "tap":
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
                    self.overlays.append(a["node_id"])
            elif t == "set_text" and a.get("node_id") in page.texts:
                page.texts[a["node_id"]].setText(self._fmt(str(a.get("text", ""))))
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
