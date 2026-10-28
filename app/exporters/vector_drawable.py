"""SVG-картинка проекта → векторный ресурс Android (VectorDrawable, res/drawable/*.xml). Без Qt.

SVG сначала очищается (как при импорте: без скриптов и ссылок наружу), затем каждая фигура становится
<path> с цветом заливки и обводки; градиенты — первым цветом (как на холсте).
"""

from __future__ import annotations

from xml.sax.saxutils import quoteattr

from app.core.document import pathdata
from app.engines.assets import svg


def _android_color(c: str, opacity: float = 1.0) -> str | None:
    """#RRGGBB[AA] → #AARRGGBB; прозрачность фигуры умножается на альфу цвета."""
    if not c or not c.startswith("#") or len(c) not in (7, 9):
        return None
    a = int(c[7:9], 16) if len(c) == 9 else 255
    a = max(0, min(255, round(a * opacity)))
    return f"#{a:02X}{c[1:7].upper()}"


def svg_to_vector(data: bytes) -> str | None:
    """Текст XML векторного ресурса или None, если SVG не разобрать или в нём нет фигур."""
    try:
        clean, _ = svg.sanitize(data)
        nodes, (_x, _y, vw, vh) = svg.svg_to_nodes(clean)
    except Exception:  # noqa: BLE001 — любой разбор, который не удался, — просто «не переводится»
        return None
    paths = []
    for n in nodes:
        if not n.path or not n.visible:
            continue
        try:  # путь узла — в его рамке; в ресурсе — в координатах всего рисунка
            d = pathdata.to_string(pathdata.transform(pathdata.parse(n.path), (1, 0, 0, 1, n.x, n.y)))
        except pathdata.PathError:
            continue
        attrs = [f"android:pathData={quoteattr(d)}"]
        fill = _android_color(n.fill, n.opacity)
        if fill:
            attrs.append(f'android:fillColor="{fill}"')
        stroke = _android_color(n.stroke, n.opacity)
        if stroke and n.stroke_width:
            attrs += [f'android:strokeColor="{stroke}"', f'android:strokeWidth="{round(n.stroke_width, 3)}"']
        if n.fill_rule == "evenodd":
            attrs.append('android:fillType="evenOdd"')
        if len(attrs) > 1:
            paths.append("    <path " + "\n        ".join(attrs) + " />")
    if not paths:
        return None
    w, h = round(vw, 3), round(vh, 3)
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
            f'    android:width="{w}dp" android:height="{h}dp"\n'
            f'    android:viewportWidth="{w}" android:viewportHeight="{h}">\n'
            + "\n".join(paths) + "\n</vector>\n")
