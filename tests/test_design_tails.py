"""1.20: хвосты дизайна — матовое стекло, слой поверх с режимом наложения, объединение / вычитание фигур,
маска любой формой."""

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsScene, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import ModelError, Node, Screen, check_prop
from app.exporters.ai_export import ExportOptions, build_package
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from app.ui.workspace.canvas import build_scene, qpath_to_d
from tests.conftest import make_spec


def _render(nodes, w=200, h=120, bg="#FFFFFF"):
    s = Screen(name="s", platform="windows", width=w, height=h, nodes=nodes)
    scene = QGraphicsScene()
    build_scene(scene, s, bg)
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(bg))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), QRectF(0, 0, w, h))
    p.end()
    return img


def test_model():
    n = Node.from_dict(Node(type="image", clip_path="M0 0 L1000 0 L500 1000 Z", overlay="#00000080",
                            overlay_blend="multiply", backdrop_blur=12).to_dict())
    assert (n.overlay, n.overlay_blend, n.backdrop_blur) == ("#00000080", "multiply", 12) and n.clip_path
    plain = Node(type="rect").to_dict()
    assert not {"clip_path", "overlay", "backdrop_blur", "overlay_blend"} & set(plain)
    with pytest.raises(ModelError):
        check_prop("overlay_blend", "dodge", "rect")
    with pytest.raises(ModelError):
        check_prop("clip_path", "M 0 0 Q", "rect")


def test_canvas_glass_overlay_mask(qapp):
    # стекло: под ним — чёрно-белые полосы, размытые до серого
    stripes = [Node(type="rect", x=i * 4, y=0, w=2, h=120, fill="#000000") for i in range(50)]
    glass = Node(type="rect", x=50, y=30, w=100, h=60, fill="#FFFFFF00", backdrop_blur=12)
    img = _render(stripes + [glass])
    inside = [img.pixelColor(x, 60).lightness() for x in range(60, 140)]
    outside = [img.pixelColor(x, 10).lightness() for x in range(60, 140)]
    assert max(outside) - min(outside) > 200 and max(inside) - min(inside) < 80          # полосы размыты
    # слой поверх: белый прямоугольник затемнён наполовину
    dark = _render([Node(type="rect", x=0, y=0, w=100, h=100, fill="#FFFFFF", overlay="#00000080")])
    assert 100 < dark.pixelColor(50, 50).lightness() < 150
    # маска треугольником: верхние углы закрашены, нижние — нет
    tri = _render([Node(type="rect", x=0, y=0, w=100, h=100, fill="#FF0000", clip_path="M0 0 L1000 0 L500 1000 Z")])
    assert tri.pixelColor(50, 5).red() > 200 and tri.pixelColor(50, 5).green() < 60
    assert tri.pixelColor(5, 95) == QColor("#FFFFFF")


def test_qpath_roundtrip(qapp):
    from PySide6.QtGui import QPainterPath
    p = QPainterPath()
    p.addEllipse(QRectF(0, 0, 100, 50))
    d = qpath_to_d(p, kx=2)
    assert d.startswith("M") and "C" in d and d.endswith("Z") and "200" in d


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
    _, path = ctx.service.create(make_spec(projects_dir, title="Фигуры"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_shape_ops_mask_and_export(win):
    page, ed = win.project_page, win.project_page.editor
    a, b = ed.add_node("ellipse"), ed.add_node("rect")
    ed.set_props({a.id: {"x": 0.0, "y": 0.0, "w": 100.0, "h": 100.0, "fill": "#6750A4"},
                  b.id: {"x": 50.0, "y": 25.0, "w": 150.0, "h": 50.0}}, "x")
    ed.select([a.id, b.id])
    assert ed.shape_op_ready()
    nid = ed.combine_shapes("union")
    v = tree.find(ed.screen(), nid)[0]
    assert v.type == "vector" and v.fill == "#6750A4" and v.w == pytest.approx(200, abs=1)
    assert len(ed.screen().nodes) == 1                                                      # две стали одной
    ed.undo()
    assert len(ed.screen().nodes) == 2
    ed.select([a.id, b.id])
    nid = ed.combine_shapes("intersect")
    assert tree.find(ed.screen(), nid)[0].w == pytest.approx(50, abs=1)
    ed.undo()
    # не пересекаются — пересечение пустое, ничего не меняется
    ed.set_props({b.id: {"x": 300.0}}, "x")
    ed.select([a.id, b.id])
    assert ed.combine_shapes("intersect") is None and len(ed.screen().nodes) == 2
    # маска: картинка-заглушка + круг → картинка в форме круга
    ed.select([])
    page.placeholder_photo("food")
    img = ed.selected_nodes()[0]
    circle = ed.add_node("ellipse")
    ed.set_props({circle.id: {"x": img.x, "y": img.y, "w": img.w, "h": img.h}}, "x")
    ed.select([img.id, circle.id])
    assert ed.mask_ready() and ed.mask_with_shape()
    im = tree.find(ed.screen(), img.id)[0]
    assert im.clip_path
    assert all(n.id != circle.id for n, _, _ in tree.walk(ed.screen().nodes))           # фигура ушла в маску
    ed.set_props({im.id: {"overlay": "#00000080", "overlay_blend": "multiply", "backdrop_blur": 0.0}}, "x")
    f = build_package(ed.doc, ExportOptions()).files
    src = "".join(v.decode() for k, v in f.items() if k.endswith("Screen.kt"))
    assert "maskShape(" in src and "BlendMode.Multiply" in src
    assert any(b"fun maskShape" in v for v in f.values())
    page.inspector._image_mask("none")                                                      # «Без маски»
    assert not tree.find(ed.screen(), img.id)[0].clip_path


def test_glass_exports_blurred_copy(win):
    """Стекло над картинкой: в Android под ним — размытая копия картинки (Modifier.blur), заливка — поверх."""
    page, ed = win.project_page, win.project_page.editor
    ed.select([])
    page.placeholder_photo("city")
    photo = ed.selected_nodes()[0]
    glass = ed.add_node("rect")
    ed.set_props({glass.id: {"x": photo.x + 10, "y": photo.y + 10, "w": 200.0, "h": 80.0, "fill": "#FFFFFF33",
                             "backdrop_blur": 20.0}}, "x")
    src = "".join(v.decode() for k, v in build_package(ed.doc, ExportOptions()).files.items()
                  if k.endswith("Screen.kt"))
    assert "// фон под стеклом" in src and ".blur(" in src and "drawRect(glass" in src
