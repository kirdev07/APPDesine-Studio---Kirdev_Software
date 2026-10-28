"""Графики из обычных фигур (версия 1.19): линейный, столбцы, кольцевая диаграмма, карточка показателя. Без Qt.

Корень графика — контейнер с ролью chart.line / chart.bar / chart.donut и числами в свойстве data
(«12 30 18 40»). Содержимое — прямоугольники и контуры: так график рисуется на холсте, тянется вместе
с контейнером (привязка «масштаб») и без особого кода попадает в Android (Box и Canvas). Новые числа —
editor.set_chart_data: содержимое перестраивается, цвета сохраняются.
"""

from __future__ import annotations

import math
import re

from app.core.document.model import Node
from app.libraries.components import ComponentSpec, _Ctx

_A = "android"
CHART_ROLES = {"chart.line": "Линейный график", "chart.bar": "Столбцы", "chart.donut": "Кольцевая диаграмма"}
MAX_VALUES = 24


def parse_values(text: str) -> list[float]:
    """Числа через пробел, запятую с пробелом или «;»; дробная часть — через точку."""
    nums = re.findall(r"-?\d+(?:\.\d+)?", re.sub(r",(?=\s|$)|;", " ", text or ""))
    return [float(x) for x in nums][:MAX_VALUES]


def format_values(values: list[float]) -> str:
    return " ".join(f"{v:g}" for v in values)


def _f(v: float) -> str:
    return f"{round(v, 2):g}"


def _scaled(n: Node) -> Node:
    n.constraint_h = n.constraint_v = "scale"  # тянется вместе с графиком
    return n


def _colors(root: Node, default: list[str]) -> list[str]:
    """Цвета текущего графика (если его перекрасили), иначе — по умолчанию."""
    got = []
    for c in root.children:
        col = c.stroke if c.type == "vector" and c.stroke and not c.fill else c.fill
        if col and col[:7] not in [g[:7] for g in got] and c.name != "Заливка под линией":
            got.append(col[:7])
    return got or default


def bars(root: Node, values: list[float], colors: list[str], k: float) -> list[Node]:
    """Столбцы — строкой Auto Layout по низу: ширина делится поровну, промежутки одинаковые на любом экране."""
    n = max(1, len(values))
    root.layout, root.cross_align, root.main_align = "horizontal", "end", "start"
    root.gap = round(root.w * (0.06 if n <= 8 else 0.03), 2)
    bw = max(1.0, (root.w - root.gap * (n - 1)) / n)
    top = max(max(values, default=0), 1e-9)
    r = min(bw / 2, 8 * k)
    out = []
    for i, v in enumerate(values):
        h = max(2 * k, root.h * max(v, 0) / top)
        out.append(Node(type="rect", name=f"Столбец {i + 1}", x=root.x + i * (bw + root.gap),
                        y=root.y + root.h - h, w=bw, h=h, fill=colors[0], radius=0, radius_tl=r, radius_tr=r,
                        sizing_h="fill"))
    return out


def line(root: Node, values: list[float], colors: list[str], k: float) -> list[Node]:
    w, h = root.w, root.h
    lo, hi = min(values, default=0), max(values, default=1)
    span = (hi - lo) or 1
    pad = 4 * k
    n = max(2, len(values))
    pts = [(pad + i * (w - 2 * pad) / (n - 1), pad + (h - 2 * pad) * (1 - (v - lo) / span))
           for i, v in enumerate(values or [0, 0])]
    d = "M" + " L".join(f"{_f(x)} {_f(y)}" for x, y in pts)
    area = d + f" L{_f(pts[-1][0])} {_f(h)} L{_f(pts[0][0])} {_f(h)} Z"
    main = colors[0]
    fill = Node(type="vector", name="Заливка под линией", x=root.x, y=root.y, w=w, h=h, path=area, vb_w=w, vb_h=h,
                fill=main[:7] + "2E")
    stroke = Node(type="vector", name="Линия", x=root.x, y=root.y, w=w, h=h, path=d, vb_w=w, vb_h=h, fill="",
                  stroke=main, stroke_width=round(2.5 * k, 2))
    return [_scaled(fill), _scaled(stroke)]


def donut(root: Node, values: list[float], colors: list[str], k: float) -> list[Node]:
    w, h = root.w, root.h
    cx, cy = w / 2, h / 2
    big = min(w, h) / 2
    small = big * 0.62
    total = sum(max(v, 0) for v in values) or 1
    gap = 2.0 if len(values) > 1 else 0.0
    out, a = [], -90.0
    for i, v in enumerate(values):
        sweep = 360 * max(v, 0) / total
        if sweep <= gap:
            a += sweep
            continue
        s0, s1 = a + gap / 2, a + min(sweep, 359.9) - gap / 2
        a += sweep
        large = 1 if s1 - s0 > 180 else 0

        def pt(r, ang):
            return cx + r * math.cos(math.radians(ang)), cy + r * math.sin(math.radians(ang))
        (x0, y0), (x1, y1) = pt(big, s0), pt(big, s1)
        (x2, y2), (x3, y3) = pt(small, s1), pt(small, s0)
        d = (f"M{_f(x0)} {_f(y0)} A{_f(big)} {_f(big)} 0 {large} 1 {_f(x1)} {_f(y1)} L{_f(x2)} {_f(y2)} "
             f"A{_f(small)} {_f(small)} 0 {large} 0 {_f(x3)} {_f(y3)} Z")
        out.append(_scaled(Node(type="vector", name=f"Доля {i + 1}", x=root.x, y=root.y, w=w, h=h, path=d,
                                vb_w=w, vb_h=h, fill=colors[i % len(colors)])))
    return out


BUILDERS = {"chart.bar": bars, "chart.line": line, "chart.donut": donut}


def rebuild(root: Node, values: list[float], k: float, default_colors: list[str]) -> None:
    """Перестроить содержимое графика под числа и текущий размер корня, цвета сохранить."""
    colors = _colors(root, default_colors)
    if root.role == "chart.donut" and len(colors) < len(values):
        colors = colors + [c for c in default_colors if c not in colors]
    root.children = BUILDERS[root.role](root, values, colors, k)
    root.data = format_values(values)


def _root(c: _Ctx, name: str, role: str, values: list[float], w: float, h: float, colors: list[str]) -> Node:
    root = c.frame(name, "none", [], w=w, h=h, role=role, clip=False)
    rebuild(root, values, c.k, colors)
    return root


def _donut_colors(c: _Ctx) -> list[str]:
    return [c.s["primary"], c.s["tertiary"], c.s["secondary"], c.s["error"], c.s["primaryContainer"],
            c.s["tertiaryContainer"]]


def chart_line(c: _Ctx) -> Node:
    return _root(c, "Линейный график", "chart.line", [12, 18, 15, 24, 21, 30, 28], 328, 160, [c.s["primary"]])


def chart_bar(c: _Ctx) -> Node:
    return _root(c, "Столбцы", "chart.bar", [8, 14, 11, 19, 16, 9, 12], 328, 160, [c.s["primary"]])


def chart_donut(c: _Ctx) -> Node:
    return _root(c, "Кольцевая диаграмма", "chart.donut", [45, 25, 18, 12], 160, 160, _donut_colors(c))


def kpi_card(c: _Ctx) -> Node:
    """Карточка показателя: подпись, число, рост и маленький график."""
    spark = _root(c, "Мини-график", "chart.line", [3, 5, 4, 6, 5, 8, 9], 120, 40, [c.s["primary"]])
    delta = c.frame("Рост", "horizontal", [c.icon(16, color="#1E8E3E", glyph="trending_up"),
                                           c.text("+12%", 12, "#1E8E3E", 600, "Процент")],
                    gap=4, cross_align="center", sizing_h="hug", sizing_v="hug")
    return c.frame("Карточка показателя", "vertical",
                   [c.text("Выручка", 14, c.s["onSurfaceVariant"], name="Подпись"),
                    c.text("128 400 ₽", 28, c.s["onSurface"], 600, "Число", sizing_h="fill"), delta, spark],
                   w=180, gap=6, pad_l=16, pad_r=16, pad_t=16, pad_b=16, radius=20, fill=c.s["surfaceContainerLow"],
                   sizing_v="hug")


def legend(c: _Ctx, items: list[tuple[str, str]]) -> Node:
    rows = [c.frame(f"Пункт «{t}»", "horizontal", [c.dot("Цвет", 10, col), c.text(t, 14, c.s["onSurface"],
                                                                                    name="Подпись")],
                    gap=8, cross_align="center", sizing_h="hug", sizing_v="hug") for t, col in items]
    return c.frame("Легенда", "vertical", rows, gap=8, sizing_h="hug", sizing_v="hug")


SPECS: tuple[ComponentSpec, ...] = (
    ComponentSpec("chart_line", "Линейный график", _A, "Графики", chart_line),
    ComponentSpec("chart_bar", "Столбчатая диаграмма", _A, "Графики", chart_bar),
    ComponentSpec("chart_donut", "Кольцевая диаграмма", _A, "Графики", chart_donut),
    ComponentSpec("chart_kpi", "Карточка показателя", _A, "Графики", kpi_card),
)
