"""Для разработчика: свойства выделенного элемента в единицах Android (dp, sp) и его код Jetpack Compose.

Код берётся из того же генератора, что и проект Android Studio, — фрагмент совпадает с тем, что будет в экспорте.
"""

from __future__ import annotations

from app.core.document import tree
from app.core.document.model import Node, ProjectDocument, Screen
from app.engines.preview.devices import screen_dpi

_MODES = {"vertical": "col", "horizontal": "row", "grid": "row", "wrap": "flow"}
_WEIGHTS = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Normal", 500: "Medium", 600: "SemiBold",
            700: "Bold", 800: "ExtraBold", 900: "Black"}


def _project(doc: ProjectDocument, screen: Screen):
    from app.exporters.android_project import AndroidProject, drawable_name
    used: set[str] = set()
    drawables = {a.id: (drawable_name(a.name, used), b"", a.ext) for a in doc.assets if a.kind == "image"}
    return AndroidProject(doc, [screen], drawables)


def compose_snippet(doc: ProjectDocument, screen: Screen, node_id: str) -> str:
    """Код Compose элемента (с вложенными), как в экспорте; пусто — элемент не найден или экран не Android."""
    from app.exporters.android_project import _Screen
    if screen.platform != "android":
        return ""
    try:
        n, parent, _ = tree.find(screen, node_id)
    except Exception:
        return ""
    proj = _project(doc, screen)
    gen = _Screen(proj, screen, proj.fns[screen.id])
    mode = _MODES.get(parent.layout, "abs") if parent is not None and parent.is_frame else "abs"
    code = "\n".join(gen.node(n, parent, mode, ""))
    if proj.strings:  # тексты — строковые ресурсы: строки для res/values/strings.xml рядом с кодом
        code += "\n\n// res/values/strings.xml:\n" + "\n".join(
            f'// <string name="{k}">{proj.xml_string(t)}</string>' for t, k in proj.strings.items())
    return code


def _color(c: str, tokens: dict[str, str], roles: dict[str, str], role: str | None = None) -> str:
    if not c:
        return "нет"
    out = c.upper()
    hints = []
    role = role or roles.get(c[:7].upper())
    if role:
        hints.append(f"colorScheme.{role}")
    if c.upper() in tokens or c[:7].upper() in tokens:
        hints.append(f"цвет «{tokens.get(c.upper()) or tokens[c[:7].upper()]}»")
    if len(c) == 9 and c[7:9].upper() != "FF":
        hints.append(f"прозрачность {round(int(c[7:9], 16) / 255 * 100)} %")
    return out + (f" — {', '.join(hints)}" if hints else "")


def spec_rows(doc: ProjectDocument, screen: Screen, node: Node) -> list[tuple[str, str]]:
    """Свойства для разработчика: (что, значение) в dp / sp, цвета — с ролью темы и именем цвета проекта."""
    k = screen_dpi(screen) / 160 if screen.platform == "android" else 1.0
    unit = "dp" if screen.platform == "android" else "px"

    def num(v: float) -> str:
        v = round(v / k, 1)
        return str(int(v)) if v == int(v) else str(v)

    def u(v: float) -> str:
        return f"{num(v)} {unit}"
    proj = _project(doc, screen) if screen.platform == "android" else None
    roles = proj.roles if proj is not None else {}
    tokens = {t.value.upper(): t.name for t in doc.colors}
    rows = [("Элемент", f"{node.name or node.type} ({node.type})"),
            ("Размер", f"{u(node.w)} × {u(node.h)}"), ("Положение", f"x {u(node.x)}, y {u(node.y)}")]
    if node.type != "text" and node.fill:
        rows.append(("Заливка", _color(node.fill, tokens, roles)))
    if node.fill2:
        rows.append(("Градиент до", _color(node.fill2, tokens, roles)))
    if node.stroke and node.stroke_width:
        rows.append(("Обводка", f"{u(node.stroke_width)}, {_color(node.stroke, tokens, roles)}"))
    if node.radius:  # как в коде: не больше половины меньшей стороны
        rows.append(("Скругление", u(min(node.radius, min(node.w, node.h) / 2))))
    if node.opacity < 1:
        rows.append(("Непрозрачность", f"{round(node.opacity * 100)} %"))
    if node.elevation:
        rows.append(("Тень (высота)", u(node.elevation)))
    if node.type == "text":
        sp = "sp" if screen.platform == "android" else "px"
        family = node.font_family or "системный"
        if proj is not None and node.font_family not in {a.family for a in doc.assets if a.kind == "font"}:
            family = f"по умолчанию (Roboto), в макете «{family}»"  # шрифта нет в проекте — в Android его нет
        on = None
        if proj is not None:
            from app.exporters.android_project import _Screen
            on = proj.on_role(node.text_color, _Screen(proj, screen, proj.fns[screen.id]).behind(node))
        rows += [("Текст", node.text[:80] + ("…" if len(node.text) > 80 else "")),
                 ("Шрифт", f"{family}, {num(node.font_size)} {sp}, "
                           f"{_WEIGHTS.get(node.font_weight, node.font_weight)} ({node.font_weight})"),
                 ("Цвет текста", _color(node.text_color, tokens, roles, on))]
        if node.line_height:
            rows.append(("Межстрочный", f"{node.line_height}×"))
        if node.letter_spacing:
            rows.append(("Межбуквенный", f"{node.letter_spacing} {unit}"))
    if node.is_frame and node.layout != "none":
        names = {"vertical": "Column", "horizontal": "Row", "grid": "сетка", "wrap": "FlowRow (с переносом)"}
        rows.append(("Раскладка", names.get(node.layout, node.layout)))
        rows.append(("Промежуток", u(node.gap) + (f", строки {u(node.row_gap)}"
                                                    if node.layout in ("grid", "wrap") else "")))
        pads = (node.pad_t, node.pad_r, node.pad_b, node.pad_l)
        if any(pads):
            rows.append(("Отступы ↑→↓←", " ".join(num(p) for p in pads) + f" {unit}"))
    return rows


def spec_text(rows: list[tuple[str, str]]) -> str:
    return "\n".join(f"{a}: {b}" for a, b in rows)
