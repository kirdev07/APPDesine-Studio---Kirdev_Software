"""1.15: удобство работы — копировать / вставить стиль, пипетка, последние цвета и цвета проекта,
расстояния с Alt, поиск слоёв, список горячих клавиш."""

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from app.ui.workspace import panels
from app.ui.workspace.canvas import measure_lines
from tests.conftest import make_spec


def test_measure_lines():
    # соседи по горизонтали: промежуток 30 посередине общей высоты
    assert measure_lines((0, 0, 50, 40), (80, 10, 20, 40)) == [(50, 25, 80, 25, 30)]
    # сверху
    assert measure_lines((0, 100, 50, 40), (10, 0, 30, 60)) == [(25, 60, 25, 100, 40)]
    # внутри экрана — четыре расстояния до краёв
    lines = measure_lines((10, 20, 30, 40), (0, 0, 100, 200))
    assert sorted(round(d) for *_, d in lines) == [10, 20, 60, 140]


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
    _, path = ctx.service.create(make_spec(projects_dir, title="Удобство"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_copy_paste_style(win):
    ed = win.project_page.editor
    a = ed.add_node("rect")
    b = ed.add_node("rect")
    t = ed.add_node("text")
    ed.set_props({a.id: {"fill": "#6750A4", "radius": 12.0, "shadow_color": "#00000044", "stroke_dash": "dash"},
                  t.id: {"text_color": "#123456", "italic": True, "font_size": 30.0}}, "x")
    ed.select([a.id])
    assert ed.copy_style()
    ed.select([b.id, t.id])
    assert ed.paste_style()
    nb = tree.find(ed.screen(), b.id)[0]
    nt = tree.find(ed.screen(), t.id)[0]
    assert (nb.fill, nb.radius, nb.shadow_color, nb.stroke_dash) == ("#6750A4", 12, "#00000044", "dash")
    assert nt.fill == "" and nt.radius == 12 and nt.italic                    # у текста фон не появился
    ed.select([t.id])
    ed.copy_style()
    ed.select([b.id])
    ed.paste_style()                                                          # текстовые свойства фигуре не нужны
    assert tree.find(ed.screen(), b.id)[0].fill == "#6750A4"
    ed.undo()
    page = win.project_page
    assert page.a_copy_style.shortcut().toString() == "Ctrl+Alt+C"


def test_colors_eyedropper_tokens(win, qtbot):
    page, ed = win.project_page, win.project_page.editor
    insp = page.inspector
    r = ed.add_node("rect")
    ed.select([r.id])
    insp.fill.committed.emit("#FF0000")
    assert panels.RECENT_COLORS[0] == "#FF0000"
    insp.fill.set_value("#FF0000")
    insp.fill._fill_more()
    texts = [a.text() for a in insp.fill.more_menu.actions()]
    assert "#FF0000" in texts and "Сохранить в цвета проекта" in texts
    next(a for a in insp.fill.more_menu.actions() if a.text() == "Сохранить в цвета проекта").trigger()
    assert any(c.value == "#FF0000" for c in ed.doc.colors)
    assert ed.add_color_token("#ff0000") == ed.doc.colors[-1].name            # без дубликатов
    # пипетка: следующий щелчок по холсту даёт цвет пикселя под курсором
    got = []
    canvas = page.canvas
    canvas.pick_at = lambda pos: "#00FF00"
    ed.color_picker(got.append)
    qtbot.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.viewport().rect().center())
    assert got == ["#00FF00"] and canvas._pick_cb is None


def test_layer_search_alt_and_shortcuts(win, qtbot):
    page, ed = win.project_page, win.project_page.editor
    a = ed.add_node("rect")
    ed.set_props({a.id: {"name": "Кнопка оплаты"}}, "n")
    ed.add_node("ellipse")
    layers = page.layers
    layers.layer_search.setText("оплат")
    vis = [it.text(0) for it in layers._items() if not it.isHidden()]
    assert len(vis) == 1 and "Кнопка оплаты" in vis[0]
    layers.layer_search.clear()
    assert all(not it.isHidden() for it in layers._items())
    canvas = page.canvas
    ed.select([a.id])
    qtbot.keyPress(canvas, Qt.Key.Key_Alt)
    assert canvas.measuring()
    canvas.viewport().update()
    qtbot.keyRelease(canvas, Qt.Key.Key_Alt)
    assert not canvas.measuring()
    rows = dict((t, k) for k, t in win.shortcut_rows())
    assert rows.get("Копировать стиль") == "Ctrl+Alt+C" and "Alt (зажать)" in [k for k, _ in win.shortcut_rows()]
    win.show_shortcuts()
    win._shortcuts_dialog.close()
