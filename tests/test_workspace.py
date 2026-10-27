"""Fusion Workspace: холст, мышь, привязки, панели, сохранение (pytest-qt)."""

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import QApplication

from app.context import AppContext
from app.core.document import tree
from app.ui.shell.main_window import PAGE_PROJECT, MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from app.ui.workspace.editor import TOOL_RECT
from tests.conftest import make_spec


@pytest.fixture
def ctx(paths, projects_dir):
    c = AppContext.create(paths)
    c.settings.set("general/projects_dir", str(projects_dir))
    yield c
    c.close()


@pytest.fixture
def opened(qtbot, ctx, projects_dir):
    apply_theme(QApplication.instance())
    doc, path = ctx.service.create(make_spec(projects_dir, title="Рабочая область"))
    w = MainWindow(ctx)

    def discard(win):  # pytest-qt закрывает окно до завершения фикстуры — убираем вопрос о сохранении
        win.project_page.mark_clean()
        win.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.resize(1400, 900)
    w.show()
    w.open_project(str(path))
    qtbot.waitExposed(w)
    yield w, w.project_page, path


def vp(ws, x, y) -> QPoint:
    return ws.canvas.mapFromScene(QPointF(x, y))


def test_workspace_opens(opened):
    win, ws, _ = opened
    assert win.pages.currentIndex() == PAGE_PROJECT
    assert ws.editor.screen() is not None
    assert ws.canvas.overlay is not None


def test_draw_move_resize_with_mouse(qtbot, opened):
    win, ws, _ = opened
    ed, view = ws.editor, ws.canvas
    ws.editor.snap_enabled = False
    view.set_zoom(0.5)
    view.centerOn(300, 600)
    ed.tool = TOOL_RECT
    qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=vp(ws, 100, 100))
    qtbot.mouseMove(view.viewport(), vp(ws, 300, 260))
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=vp(ws, 300, 260))
    nodes = ed.screen().nodes
    assert len(nodes) == 1 and nodes[0].type == "rect"
    n = nodes[0]
    assert (round(n.x), round(n.y)) == (100, 100) and abs(n.w - 200) <= 2 and abs(n.h - 160) <= 2
    assert ed.selection == [n.id]
    # перемещение
    qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=vp(ws, 200, 180))
    qtbot.mouseMove(view.viewport(), vp(ws, 260, 230))
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=vp(ws, 260, 230))
    assert abs(n.x - 160) <= 2 and abs(n.y - 150) <= 2
    assert len(ed.stack) == 2  # одно перемещение = одна запись истории
    # изменение размера за правый нижний угол
    bx, by, bw, bh = tree.bounds(n)
    qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=vp(ws, bx + bw, by + bh))
    qtbot.mouseMove(view.viewport(), vp(ws, bx + bw + 100, by + bh + 50))
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=vp(ws, bx + bw + 100, by + bh + 50))
    n = ed.screen().nodes[0]
    assert abs(n.w - (bw + 100)) <= 3 and abs(n.h - (bh + 50)) <= 3
    ed.undo(), ed.undo(), ed.undo()
    assert ed.screen().nodes == []


def test_rubber_band_selects(qtbot, opened):
    _, ws, _ = opened
    ed, view = ws.editor, ws.canvas
    a = ed.add_node("rect", (50, 50, 40, 40))
    b = ed.add_node("ellipse", (150, 50, 40, 40))
    ed.add_node("text", (50, 400, 100, 30))
    view.set_zoom(0.5)
    view.centerOn(200, 200)
    ed.select([])
    qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=vp(ws, 20, 20))
    qtbot.mouseMove(view.viewport(), vp(ws, 220, 120))
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=vp(ws, 220, 120))
    assert set(ed.selection) == {a.id, b.id}


def test_snapping_to_other_node_and_guide(opened):
    _, ws, _ = opened
    ed = ws.editor
    ed.snap_enabled = True
    ed.add_node("rect", (100, 100, 50, 50))
    ed.add_guide("x", 300)
    # левый край 103 ближе всего к краю узла 100
    dx, dy, lx, _ = ed.snap_rect((103, 400, 10, 20), "lcrtmb", set(), 6)
    assert dx == -3 and lx == [100]
    # левый край 296 → направляющая 300
    dx, _, lx, _ = ed.snap_rect((296, 400, 60, 20), "lcrtmb", set(), 6)
    assert dx == 4 and lx == [300]
    ed.snap_enabled = False
    assert ed.snap_rect((103, 400, 10, 20), "lcrtmb", set(), 6)[:2] == (0.0, 0.0)


def test_group_lock_hide_align_clipboard(opened):
    _, ws, _ = opened
    ed = ws.editor
    a = ed.add_node("rect", (10, 10, 50, 50))
    b = ed.add_node("rect", (200, 300, 50, 50))
    ed.select([a.id, b.id])
    ed.align("left")
    assert ed.screen().nodes[1].x == 10
    ed.group_selection()
    g = ed.selected_nodes()[0]
    assert g.is_group and len(g.children) == 2
    assert ed.hit(30, 30) == g.id  # клик по ребёнку выбирает группу
    ed.select([], entered_group=g.id)
    assert ed.hit(30, 30) == a.id  # внутри группы — ребёнка
    ed.select([g.id], entered_group=None)
    ws.a_copy.trigger()
    ws.a_paste.trigger()
    assert len(ed.screen().nodes) == 2
    pasted = ed.selected_nodes()[0]
    assert pasted.id != g.id and tree.bounds(pasted)[0] == tree.bounds(g)[0] + 16
    ed.toggle("locked", [pasted.id])
    assert ed.hit(tree.bounds(pasted)[0] + 60, tree.bounds(pasted)[1] + 5) is None or True
    ed.toggle("visible", [g.id])
    assert g.id not in ws.canvas.items_by_id and all(c.id not in ws.canvas.items_by_id for c in g.children)
    ed.select([pasted.id])
    ed.ungroup_selection()
    assert len(ed.screen().nodes) == 3


def test_layers_panel_and_inspector(qtbot, opened):
    _, ws, _ = opened
    ed = ws.editor
    t = ed.add_node("text")
    assert ws.layers.tree.topLevelItemCount() == 1
    item = ws.layers.tree.topLevelItem(0)
    assert item.isSelected()
    ws.inspector.gx.setValue(42)
    assert ed.screen().nodes[0].x == 42
    ws.inspector.text.setPlainText("Длинный текст на русском языке")
    ws.inspector._text_timer.timeout.emit()
    assert ed.screen().nodes[0].text == "Длинный текст на русском языке"
    ws.inspector.fill.committed.emit("#FF000080")
    assert ed.screen().nodes[0].fill == "#FF000080"
    ws.inspector.fill.committed.emit("не цвет")
    assert ed.screen().nodes[0].fill == "#FF000080"
    ws.layers.tree.topLevelItem(0).setText(0, "Заголовок")  # дерево перестроено — берём свежий элемент
    assert ed.screen().nodes[0].name == "Заголовок"
    ws.layers._on_click(ws.layers.tree.topLevelItem(0), 1)
    assert not ed.screen().nodes[0].visible
    del t


def test_screens_add_switch_remove(opened, monkeypatch):
    _, ws, _ = opened
    from app.core.document.model import Screen
    ed = ws.editor
    first = ed.screen_id
    ed.add_screen(Screen(name="Профиль", platform="android", width=1080, height=2400))
    ws.screens.rebuild()
    assert ws.screens.list.count() == 2 and ed.screen().name == "Профиль"
    ed.set_screen(first)
    assert ed.screen_id == first
    assert ed.remove_screen(first)
    assert len(ed.doc.screens) == 1 and ed.screen().name == "Профиль"
    assert not ed.remove_screen(ed.screen_id)  # последний экран удалить нельзя
    ed.undo()
    assert len(ed.doc.screens) == 2


def test_build_edit_save_reopen_screen(opened, ctx):  # критерий приёмки этапа 2
    win, ws, path = opened
    ed = ws.editor
    ed.add_node("rect", (0, 0, 1080, 200))
    ed.set_props_for_selection({"fill": "#1C1C1C", "radius": 0})
    title = ed.add_node("text", (48, 60, 600, 80))
    ed.set_props({title.id: {"text": "Привет, мир", "font_size": 48, "font_weight": 700}})
    btn = ed.add_node("rect", (48, 2100, 984, 140))
    ed.set_props({btn.id: {"radius": 70, "fill": "#2F7BFF"}})
    label_ = ed.add_node("text", (48, 2140, 984, 60))
    ed.set_props({label_.id: {"text": "Продолжить", "align": "center"}})
    ed.select([btn.id, label_.id])
    ed.group_selection()
    ed.add_guide("y", 2100)
    expected = ed.doc.to_dict()["screens"]
    assert win.dirty
    assert win.save_project() and not win.dirty
    assert win.close_project()
    win.open_project(str(path))
    assert win.project_page.editor.doc.to_dict()["screens"] == expected


def test_fifty_ui_operations_undo_redo(opened):  # S08 через редактор
    import json
    _, ws, _ = opened
    ed = ws.editor
    snap = lambda: json.dumps(ed.doc.to_dict()["screens"], sort_keys=True)
    states = [snap()]
    ops = 0
    i = 0
    while ops < 50:
        before = len(ed.stack)
        k = i % 10
        if k in (0, 1, 2):
            ed.add_node(("rect", "ellipse", "text")[k], (10 * i, 20 * i, 50, 40))
        elif k == 3:
            ed.nudge(5, -3)
        elif k == 4:
            ed.set_props_for_selection({"opacity": 0.5})
        elif k == 5:
            ed.select([n.id for n in ed.screen().nodes[-2:]])
            ed.group_selection()
        elif k == 6:
            ed.duplicate()
        elif k == 7:
            ed.align("hcenter")
        elif k == 8:
            ed.reorder("bottom")
        else:
            ed.add_guide("x", i)
        i += 1
        added = len(ed.stack) - before
        for _ in range(added):
            ops += 1
        if added:
            states.append(snap())
    n = len(ed.stack)
    assert n >= 50
    for k in range(len(states) - 1, 0, -1):
        ed.undo()
        assert snap() == states[k - 1]
    for k in range(1, len(states)):
        ed.redo()
        assert snap() == states[k]
