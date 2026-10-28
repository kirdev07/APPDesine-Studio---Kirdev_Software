"""1.14: тонкая настройка вида — своя тень, обводка (пунктир, положение, стороны), углы по отдельности,
третий цвет градиента, интервалы, курсив, линия, регистр и предел строк текста."""

import pytest
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import ModelError, Node, check_prop
from app.engines.layout.engine import SimpleMeasurer
from app.exporters.ai_export import ExportOptions, build_package
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from app.ui.workspace.canvas import paint_node
from tests.conftest import make_spec


def test_model_defaults_validation_roundtrip():
    plain = Node(type="rect").to_dict()
    for k in ("shadow_color", "stroke_dash", "radius_tl", "fill3", "stroke_sides"):
        assert k not in plain                                            # значения по умолчанию не пишутся
    n = Node(type="rect", w=100, h=40, radius=8, radius_tl=0, shadow_color="#00000044", shadow_inset=True,
             stroke_dash="dot", stroke_align="outside", stroke_sides="b", fill3="#ffd54f")
    back = Node.from_dict(n.to_dict())
    assert back.corner_radii() == (0, 8, 8, 8) and back.shadow_inset and back.stroke_sides == "b"
    assert Node(type="rect", w=10, h=40, radius=50).corner_radii() == (5, 5, 5, 5)   # не больше половины стороны
    assert check_prop("stroke_sides", "lt") == "tl" and check_prop("fill3", "#ffd54f") == "#FFD54F"
    for name, bad in (("stroke_sides", ""), ("stroke_sides", "x"), ("stroke_dash", "wave"),
                      ("max_lines", -1), ("letter_spacing", 500), ("radius_tl", -2)):
        with pytest.raises(ModelError):
            check_prop(name, bad, "text" if name in ("max_lines", "letter_spacing") else "rect")
    t = Node.from_dict(Node(type="text", text="a", italic=True, decoration="strike", text_case="title",
                            letter_spacing=2, line_height=1.5, max_lines=3).to_dict())
    assert (t.italic, t.decoration, t.text_case, t.letter_spacing, t.line_height, t.max_lines) == \
        (True, "strike", "title", 2, 1.5, 3)


def test_simple_measurer_spacing_lines():
    m = SimpleMeasurer()
    w0, h0 = m.measure("abcd", "x", 10, 400, None)
    w1, _ = m.measure("abcd", "x", 10, 400, None, (2.0, 0.0, False, "none", 0))
    assert w1 == pytest.approx(w0 + 8)
    long = "слово " * 40
    _, h = m.measure(long, "x", 10, 400, 100, (0.0, 2.0, False, "none", 2))
    assert h == pytest.approx(2 * 10 * 2.0)                               # две строки высотой 20


def _render(n, w=120, h=80):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#FFFFFF"))
    p = QPainter(img)
    paint_node(p, n)
    p.end()
    return img


def test_canvas_corners_strokes_shadow(qapp):
    sq = _render(Node(type="rect", x=10, y=10, w=100, h=60, fill="#000000", radius=20, radius_tl=0))
    assert sq.pixelColor(11, 11).black() > 200 and sq.pixelColor(108, 11).black() < 50   # острый и скруглённый
    bottom = _render(Node(type="rect", x=10, y=10, w=100, h=60, fill="", stroke="#FF0000", stroke_width=4,
                          stroke_sides="b"))
    assert bottom.pixelColor(60, 69).red() > 200 and bottom.pixelColor(60, 69).green() < 60
    assert bottom.pixelColor(60, 10) == QColor("#FFFFFF")                  # сверху линии нет
    outside = _render(Node(type="rect", x=20, y=20, w=80, h=40, fill="#FFFFFF", stroke="#0000FF",
                           stroke_width=6, stroke_align="outside"))
    assert outside.pixelColor(60, 17).blue() > 200 and outside.pixelColor(60, 23) == QColor("#FFFFFF")
    shadow = _render(Node(type="rect", x=20, y=10, w=80, h=40, fill="#FFFFFF", shadow_color="#000000AA",
                          shadow_y=10, shadow_blur=0))
    assert shadow.pixelColor(60, 55).black() > 80                           # тень под элементом
    grad = _render(Node(type="rect", x=0, y=0, w=120, h=80, fill="#FF0000", fill2="#0000FF", fill3="#00FF00",
                        gradient="linear", grad_angle=90))
    assert grad.pixelColor(60, 40).green() > 200                            # посередине — средний цвет


@pytest.fixture
def win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)

    def discard(x):
        x.project_page.mark_clean()
        x.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Вид"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_inspector_and_compose(qtbot, win):
    page, ed = win.project_page, win.project_page.editor
    insp = page.inspector
    insp.set_simple(False)
    card = ed.insert_component("m3_card")
    ed.select([card.id])
    insp.stroke.committed.emit("#6750A4")
    insp.stroke_w.setValue(2)
    insp.stroke_dash.setCurrentIndex(insp.stroke_dash.findData("dash"))
    insp.stroke_align.setCurrentIndex(insp.stroke_align.findData("inside"))
    insp.corner["radius_tl"].setValue(0)
    insp.shadow_color.committed.emit("#6750A4")
    insp.shadow["shadow_y"].setValue(12)
    c = tree.find(ed.screen(), card.id)[0]
    assert (c.stroke_dash, c.stroke_align, c.radius_tl, c.shadow_color, c.shadow_y) == \
        ("dash", "inside", 0, "#6750A466", 12)                              # тени без альфы — 40 %
    insp.side_btns["t"].click()                                            # снять верхнюю сторону
    assert tree.find(ed.screen(), card.id)[0].stroke_sides == "rbl"
    for s in "rbl":
        insp.side_btns[s].click()
    assert tree.find(ed.screen(), card.id)[0].stroke_sides == "l"           # последнюю снять нельзя
    ed.undo()
    text = next(n for n, _, _ in tree.walk([tree.find(ed.screen(), card.id)[0]]) if n.type == "text")
    ed.select([text.id])
    insp.letter_spacing.setValue(2)
    insp.italic.click()
    insp.text_case.setCurrentIndex(insp.text_case.findData("upper"))
    insp.max_lines.setValue(1)
    t = tree.find(ed.screen(), text.id)[0]
    assert (t.letter_spacing, t.italic, t.text_case, t.max_lines) == (2, True, "upper", 1)
    insp.set_simple(True)
    assert insp.corner_row.isHidden() or not insp.corner_row.isVisible()
    insp.set_simple(False)
    f = build_package(ed.doc, ExportOptions()).files
    src = next(v.decode() for k, v in f.items() if b"dropShadow" in v)
    assert "RoundedCornerShape(topStart = 0.dp" in src and "PathEffect.dashPathEffect" in src
    assert "drawWithContent {" in src and "drawLine(" in src           # две стороны — линиями
    assert "fontStyle = FontStyle.Italic" in src and "letterSpacing" in src
    assert "maxLines = 1," in src and "TextOverflow.Ellipsis" in src


def test_compose_inner_shadow_sides_three_colors_case():
    from app.exporters.compose_motion import brush, kshape, shadow, stroke_draw
    n = Node(type="rect", w=100, h=40, radius=8, radius_br=0, fill="#FF0000", fill2="#0000FF", fill3="#00FF00",
             gradient="linear", grad_angle=0, shadow_color="#00000044", shadow_inset=True, stroke="#000000",
             stroke_width=2, stroke_sides="tb")
    dp = lambda v: f"{v:g}.dp"
    shape = kshape(n, dp)
    assert shape == "RoundedCornerShape(topStart = 8.dp, topEnd = 8.dp, bottomEnd = 0.dp, bottomStart = 8.dp)"
    assert shadow(n, dp, str, shape, inset=False) is None and ".innerShadow(" in shadow(n, dp, str, shape, True)
    assert brush(n, str) == "Brush.verticalGradient(listOf(#0000FF, #00FF00, #FF0000))"   # 0° — снизу вверх
    lines = "\n".join(stroke_draw(n, dp, str, shape, ""))
    assert lines.count("drawLine(") == 2 and "drawOutline" not in lines
    from app.exporters.android_project import _cased
    assert _cased("привет мир", "title") == "Привет Мир" and _cased("Ab", "upper") == "AB"
