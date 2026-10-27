"""SVG: санитизация недоверенных файлов, преобразование в векторные узлы и экспорт. Без Qt.

Поддерживается подмножество SVG: path, rect, circle, ellipse, line, polyline, polygon, g, трансформации,
сплошные заливки и обводки. Градиенты упрощаются до цвета первой точки, текст и растровые изображения
внутри SVG при импорте отбрасываются. Скрипты, обработчики событий, внешние ссылки, foreignObject,
DTD/ENTITY запрещены. Отчёт перечисляет всё, что было удалено или упрощено.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from app.core.document import pathdata
from app.core.document.model import Node

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
MAX_SVG_BYTES = 2 * 1024 * 1024
MAX_ELEMENTS = 20_000
MAX_DEPTH = 64

ALLOWED_ELEMENTS = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "defs",
                    "linearGradient", "radialGradient", "stop", "title", "desc"}
SHAPES = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
ALLOWED_ATTRS = {"id", "d", "x", "y", "width", "height", "cx", "cy", "r", "rx", "ry", "x1", "y1", "x2", "y2",
                 "points", "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "opacity",
                 "fill-opacity", "stroke-opacity", "fill-rule", "clip-rule", "transform", "viewBox", "offset",
                 "stop-color", "stop-opacity", "gradientUnits", "gradientTransform", "fx", "fy", "version",
                 "preserveAspectRatio", "stroke-miterlimit", "display", "visibility"}
STYLE_PROPS = {"fill", "stroke", "stroke-width", "opacity", "fill-opacity", "stroke-opacity", "fill-rule",
               "stroke-linecap", "stroke-linejoin", "stop-color", "stop-opacity", "display", "visibility"}
NAMED = {"black": "#000000", "white": "#FFFFFF", "red": "#FF0000", "green": "#008000", "blue": "#0000FF",
         "gray": "#808080", "grey": "#808080", "yellow": "#FFFF00", "orange": "#FFA500", "currentcolor": "#000000",
         "transparent": ""}


class SvgError(ValueError):
    pass


@dataclass
class SanitizeReport:
    removed: list[str] = field(default_factory=list)
    simplified: list[str] = field(default_factory=list)

    def note(self, kind: str, text: str) -> None:
        target = self.removed if kind == "removed" else self.simplified
        if text not in target:
            target.append(text)

    @property
    def clean(self) -> bool:
        return not self.removed and not self.simplified


def _local(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _attr_name(name: str) -> str:
    if name.startswith("{"):
        ns, local = name[1:].split("}", 1)
        return ("xlink:" if ns == XLINK_NS else "?:") + local
    return name


def _safe_value(v: str) -> bool:
    low = v.lower().replace(" ", "")
    if "javascript:" in low or "data:" in low or "expression(" in low:
        return False
    for m in re.finditer(r"url\(([^)]*)\)", low):
        if not m.group(1).strip("'\"").startswith("#"):
            return False
    return True


def sanitize(data: bytes) -> tuple[bytes, SanitizeReport]:
    """Возвращает очищенный SVG и отчёт. Бросает SvgError, если файл нельзя безопасно использовать."""
    if len(data) > MAX_SVG_BYTES:
        raise SvgError("SVG больше 2 МБ")
    head = data[:4096].lower()
    if b"<!doctype" in data.lower() or b"<!entity" in head:
        raise SvgError("SVG содержит DTD/ENTITY — такие файлы не принимаются")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise SvgError(f"Файл не является корректным SVG: {exc}") from None
    if _local(root.tag) != "svg":
        raise SvgError("Корневой элемент не <svg>")
    report = SanitizeReport()
    count = 0

    def clean(el: ET.Element, depth: int) -> ET.Element | None:
        nonlocal count
        count += 1
        if count > MAX_ELEMENTS or depth > MAX_DEPTH:
            raise SvgError("SVG слишком сложный")
        tag = _local(el.tag)
        if tag not in ALLOWED_ELEMENTS:
            report.note("removed", f"элемент <{tag}>")
            return None
        out = ET.Element(f"{{{SVG_NS}}}{tag}")
        for name, value in el.attrib.items():
            an = _attr_name(name)
            if an.lower().startswith("on"):
                report.note("removed", f"обработчик события {an}")
                continue
            if an in ("href", "xlink:href"):
                if value.startswith("#") and tag in ("linearGradient", "radialGradient"):
                    out.set(f"{{{XLINK_NS}}}href", value)
                else:
                    report.note("removed", "внешняя ссылка href")
                continue
            if an == "style":
                kept = []
                for part in value.split(";"):
                    if ":" not in part:
                        continue
                    k, v = (s.strip() for s in part.split(":", 1))
                    if k in STYLE_PROPS and _safe_value(v):
                        kept.append(f"{k}:{v}")
                    else:
                        report.note("removed", f"свойство стиля {k}")
                if kept:
                    out.set("style", ";".join(kept))
                continue
            if an not in ALLOWED_ATTRS:
                report.note("removed", f"атрибут {an}")
                continue
            if not _safe_value(value):
                report.note("removed", f"небезопасное значение {an}")
                continue
            if an == "d":
                try:
                    value = pathdata.normalize(value)
                except pathdata.PathError as exc:
                    report.note("removed", f"неверный путь ({exc})")
                    return None
            out.set(an, value)
        for child in el:
            c = clean(child, depth + 1)
            if c is not None:
                out.append(c)
        if el.text and el.text.strip() and tag not in ("title", "desc"):
            report.note("removed", "текстовое содержимое")
        if tag in ("title", "desc") and el.text:
            out.text = el.text[:500]
        return out

    cleaned = clean(root, 0)
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    return ET.tostring(cleaned, encoding="utf-8", xml_declaration=False), report


# ---------------- разбор очищенного SVG ----------------

def _num(v: str | None, default: float = 0.0) -> float:
    if v is None:
        return default
    m = re.match(r"\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)", v)
    return float(m.group(1)) if m else default


def parse_color(v: str | None, opacity: float = 1.0, gradients: dict | None = None,
                report: SanitizeReport | None = None) -> str:
    if v is None:
        return ""
    v = v.strip()
    low = v.lower()
    if low in ("none", ""):
        return ""
    if low.startswith("url("):
        gid = low[4:].strip(")'\" #")
        color = (gradients or {}).get(gid, "#808080")
        if report:
            report.note("simplified", "градиент заменён сплошным цветом")
        return _with_alpha(color, opacity)
    if low in NAMED:
        return _with_alpha(NAMED[low], opacity) if NAMED[low] else ""
    m = re.fullmatch(r"#([0-9a-f]{3})", low)
    if m:
        h = m.group(1)
        return _with_alpha("#" + "".join(c * 2 for c in h).upper(), opacity)
    m = re.fullmatch(r"#([0-9a-f]{6})", low)
    if m:
        return _with_alpha("#" + m.group(1).upper(), opacity)
    m = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", low)
    if m:
        r, g, b = (min(255, int(m.group(i))) for i in (1, 2, 3))
        a = float(m.group(4)) if m.group(4) else 1.0
        return _with_alpha(f"#{r:02X}{g:02X}{b:02X}", opacity * a)
    if report:
        report.note("simplified", f"неизвестный цвет {v} заменён серым")
    return _with_alpha("#808080", opacity)


def _with_alpha(color: str, opacity: float) -> str:
    if not color:
        return ""
    a = max(0, min(255, round(opacity * 255)))
    return color[:7] if a >= 255 else f"{color[:7]}{a:02X}"


def _parse_transform(t: str | None):
    m = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    if not t:
        return tuple(m)
    for name, args in re.findall(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)", t):
        a = [float(x) for x in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", args)]
        if name == "matrix" and len(a) == 6:
            n = a
        elif name == "translate":
            n = [1, 0, 0, 1, a[0] if a else 0, a[1] if len(a) > 1 else 0]
        elif name == "scale":
            sx = a[0] if a else 1
            n = [sx, 0, 0, a[1] if len(a) > 1 else sx, 0, 0]
        elif name == "rotate":
            ang = math.radians(a[0] if a else 0)
            c, s = math.cos(ang), math.sin(ang)
            n = [c, s, -s, c, 0, 0]
            if len(a) == 3:
                cx, cy = a[1], a[2]
                n = _mul(_mul([1, 0, 0, 1, cx, cy], n), [1, 0, 0, 1, -cx, -cy])
        elif name == "skewX":
            n = [1, 0, math.tan(math.radians(a[0] if a else 0)), 1, 0, 0]
        else:
            n = [1, math.tan(math.radians(a[0] if a else 0)), 0, 1, 0, 0]
        m = _mul(m, n)
    return tuple(m)


def _mul(m, n):
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return [a * a2 + c * b2, b * a2 + d * b2, a * c2 + c * d2, b * c2 + d * d2, a * e2 + c * f2 + e,
            b * e2 + d * f2 + f]


def _style(el: ET.Element) -> dict:
    d = {k: v for k, v in el.attrib.items() if k in STYLE_PROPS}
    for part in el.get("style", "").split(";"):
        if ":" in part:
            k, v = (s.strip() for s in part.split(":", 1))
            d[k] = v
    return d


def _shape_path(tag: str, el: ET.Element) -> str:
    g = el.get
    if tag == "path":
        return g("d", "")
    if tag == "rect":
        rx = _num(g("rx"), _num(g("ry")))
        return pathdata.rect_path(_num(g("x")), _num(g("y")), _num(g("width")), _num(g("height")), rx,
                                  _num(g("ry"), rx))
    if tag == "circle":
        r = _num(g("r"))
        return pathdata.ellipse_path(_num(g("cx")), _num(g("cy")), r, r) if r > 0 else ""
    if tag == "ellipse":
        rx, ry = _num(g("rx")), _num(g("ry"))
        return pathdata.ellipse_path(_num(g("cx")), _num(g("cy")), rx, ry) if rx > 0 and ry > 0 else ""
    if tag == "line":
        return f"M {_num(g('x1'))} {_num(g('y1'))} L {_num(g('x2'))} {_num(g('y2'))}"
    pts = [float(x) for x in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", g("points", ""))]
    if len(pts) < 4:
        return ""
    d = f"M {pts[0]} {pts[1]} " + " ".join(f"L {pts[i]} {pts[i + 1]}" for i in range(2, len(pts) - 1, 2))
    return d + (" Z" if tag == "polygon" else "")


def svg_to_nodes(clean_svg: bytes, report: SanitizeReport | None = None) -> tuple[list[Node], tuple]:
    """Очищенный SVG → векторные узлы в координатах viewBox. Возвращает (узлы, viewBox)."""
    report = report or SanitizeReport()
    root = ET.fromstring(clean_svg)
    vb = [_num(v) for v in re.split(r"[ ,]+", root.get("viewBox", "").strip())] if root.get("viewBox") else []
    if len(vb) != 4 or vb[2] <= 0 or vb[3] <= 0:
        vb = [0, 0, _num(root.get("width"), 24) or 24, _num(root.get("height"), 24) or 24]
    gradients = {}
    for el in root.iter():
        if _local(el.tag) in ("linearGradient", "radialGradient") and el.get("id"):
            stops = [s for s in el if _local(s.tag) == "stop"]
            if stops:
                st = _style(stops[0])
                gradients[el.get("id").lower()] = parse_color(st.get("stop-color", "#000000"))
    nodes: list[Node] = []
    base = _mul([1, 0, 0, 1, 0, 0], [1, 0, 0, 1, -vb[0], -vb[1]])
    inherited0 = {"fill": "#000000", "stroke": "none", "stroke-width": "1", "opacity": "1", "fill-opacity": "1",
                  "stroke-opacity": "1", "fill-rule": "nonzero"}

    def walk(el, matrix, inh, depth):
        tag = _local(el.tag)
        if tag in ("defs", "linearGradient", "radialGradient", "title", "desc", "stop"):
            return
        st = {**inh, **_style(el)}
        if st.get("display") == "none" or st.get("visibility") == "hidden":
            return
        m = _mul(matrix, list(_parse_transform(el.get("transform"))))
        if tag in ("svg", "g"):
            op = float(_num(el.get("opacity"), 1.0)) if el is not root else 1.0
            st["opacity"] = str(float(inh.get("opacity", "1")) * op)
            for c in el:
                walk(c, m, {k: v for k, v in st.items() if k != "opacity"} | {"opacity": st["opacity"]}, depth + 1)
            return
        if tag not in SHAPES:
            return
        d = _shape_path(tag, el)
        if not d:
            return
        try:
            segs = pathdata.transform(pathdata.parse(d), tuple(m))
        except pathdata.PathError:
            report.note("removed", "неверный путь")
            return
        b = pathdata.bounds(segs)
        if b is None:
            return
        x, y, w, h = b
        local = pathdata.transform(segs, (1, 0, 0, 1, -x, -y))
        scale = math.sqrt(abs(m[0] * m[3] - m[1] * m[2])) or 1.0
        opacity = float(st.get("opacity", 1)) * _num(el.get("opacity"), 1.0)
        fill = parse_color(st.get("fill"), _num(st.get("fill-opacity"), 1.0), gradients, report)
        stroke = parse_color(st.get("stroke"), _num(st.get("stroke-opacity"), 1.0), gradients, report)
        sw = _num(st.get("stroke-width"), 1.0) * scale if stroke else 0.0
        nodes.append(Node(type="vector", name=el.get("id") or {"path": "Контур"}.get(tag, tag.capitalize()),
                          x=round(x, 3), y=round(y, 3), w=round(max(w, 0.01), 3), h=round(max(h, 0.01), 3),
                          vb_w=max(w, 0.01), vb_h=max(h, 0.01), path=pathdata.to_string(local), fill=fill,
                          stroke=stroke, stroke_width=round(sw, 3), opacity=max(0.0, min(1.0, opacity)),
                          fill_rule="evenodd" if st.get("fill-rule") == "evenodd" else "nonzero"))

    walk(root, base, inherited0, 0)
    return nodes, (0, 0, vb[2], vb[3])


# ---------------- экспорт ----------------

def _svg_color(attr: str, color: str) -> str:
    if not color:
        return f'{attr}="none"'
    out = f'{attr}="{color[:7]}"'
    if len(color) == 9:
        out += f' {attr}-opacity="{int(color[7:9], 16) / 255:.3f}"'
    return out


def node_segments(n: Node) -> list:
    """Сегменты пути узла в абсолютных координатах экрана."""
    if n.type == "vector" and n.path:
        sx = n.w / n.vb_w if n.vb_w else 1
        sy = n.h / n.vb_h if n.vb_h else 1
        return pathdata.transform(pathdata.parse(n.path), (sx, 0, 0, sy, n.x, n.y))
    if n.type == "ellipse":
        return pathdata.parse(pathdata.ellipse_path(n.x + n.w / 2, n.y + n.h / 2, n.w / 2, n.h / 2))
    if n.type in ("rect", "frame", "instance"):
        return pathdata.parse(pathdata.rect_path(n.x, n.y, n.w, n.h, n.radius))
    return []


def nodes_to_svg(nodes: list[Node], width: float, height: float, title: str = "") -> str:
    from app.core.document.tree import walk
    parts = [f'<svg xmlns="{SVG_NS}" width="{pathdata._f(width)}" height="{pathdata._f(height)}" '
             f'viewBox="0 0 {pathdata._f(width)} {pathdata._f(height)}">']
    if title:
        parts.append(f"<title>{_xml(title)}</title>")
    for n, _, _ in walk(nodes):
        if not n.visible or n.is_group or n.type in ("text", "image"):
            continue
        segs = node_segments(n)
        if not segs:
            continue
        attrs = [f'd="{pathdata.to_string(segs)}"', _svg_color("fill", n.fill)]
        if n.stroke and n.stroke_width > 0:
            attrs += [_svg_color("stroke", n.stroke), f'stroke-width="{pathdata._f(n.stroke_width)}"']
        if n.opacity < 1:
            attrs.append(f'opacity="{n.opacity:.3f}"')
        if n.fill_rule == "evenodd":
            attrs.append('fill-rule="evenodd"')
        parts.append("<path " + " ".join(attrs) + "/>")
    parts.append("</svg>")
    return "\n".join(parts)


def _xml(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
