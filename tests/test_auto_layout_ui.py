"""Этап 3 через редактор: Auto Layout, компоненты, адаптивность, история, сохранение (S09, S10)."""

import json

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import Screen
from app.engines.layout import resize_screen
from app.libraries import components
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec

LONG_RU = ("Широкая электрификация южных губерний даст мощный толчок подъёму сельского хозяйства, а съешь же ещё "
           "этих мягких французских булок — и выпей чаю. ") * 3


@pytest.fixture
def ws(qtbot, paths, projects_dir):
    apply_theme(QApplication.instance())
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    _, path = ctx.service.create(make_spec(projects_dir, title="Раскладка", platforms=("android", "windows"),
                                           devices=("android_phone", "windows_window")))
    w = MainWindow(ctx)

    def discard(win):
        win.project_page.mark_clean()
        win.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.resize(1400, 900)
    w.show()
    w.open_project(str(path))
    yield w.project_page, w, path
    ctx.close()


def snap(ed):
    return json.dumps(ed.doc.to_dict()["screens"], sort_keys=True)


@pytest.mark.parametrize("platform", ["android", "windows"])
def test_every_component_inserts_without_layout_warnings(ws, platform):
    page, _, _ = ws
    ed = page.editor
    ed.set_screen(next(s.id for s in ed.doc.screens if s.platform == platform))
    for spec in components.specs_for(platform):
        node = ed.insert_component(spec.kind)
        assert node is not None, spec.kind
        warnings = [d for d in ed.diagnostics if d.severity == "warning" and d.node_id in
                    {n.id for n in tree.descendants(tree.find(ed.screen(), node.id)[0])}]
        assert not warnings, (spec.kind, [d.message for d in warnings])
    assert len(ed.screen().nodes) == len(components.specs_for(platform))


def test_button_hugs_label_and_one_history_entry(ws):
    page, _, _ = ws
    ed = page.editor
    btn = ed.insert_component("m3_button_filled")
    label = btn.children[0]
    n_before = len(ed.stack)
    w_before = tree.find(ed.screen(), btn.id)[0].w
    ed.set_props({label.id: {"text": "Очень длинная подпись кнопки"}}, "Текст")
    assert len(ed.stack) == n_before + 1  # текст + раскладка = одна запись
    b = tree.find(ed.screen(), btn.id)[0]
    lbl = b.children[0]
    assert b.w > w_before
    assert b.w == pytest.approx(lbl.w + b.pad_l + b.pad_r, abs=0.02)
    assert lbl.x == pytest.approx(b.x + b.pad_l, abs=0.02)
    ed.undo()
    assert tree.find(ed.screen(), btn.id)[0].w == w_before


def test_wrap_in_auto_layout_and_change_gap(ws):
    page, _, _ = ws
    ed = page.editor
    a = ed.add_node("rect", (100, 500, 200, 80))
    b = ed.add_node("rect", (100, 300, 200, 80))  # выше на холсте — станет первым
    c = ed.add_node("rect", (100, 700, 200, 80))
    ed.select([a.id, b.id, c.id])
    before = snap(ed)
    n = len(ed.stack)
    ed.wrap_in_auto_layout("vertical")
    assert len(ed.stack) == n + 1
    f = ed.selected_nodes()[0]
    assert f.is_frame and f.layout == "vertical"
    assert [ch.id for ch in f.children] == [b.id, a.id, c.id]
    ys = [ch.y for ch in f.children]
    assert ys == sorted(ys) and ys[1] - ys[0] == 80 + f.gap
    page.inspector.al_gap.setValue(40)
    f = tree.find(ed.screen(), f.id)[0]
    assert f.children[1].y - f.children[0].y == 120
    assert f.h == 3 * 80 + 2 * 40  # «по содержимому»
    ed.undo()
    ed.undo()
    assert snap(ed) == before


def test_drag_reorders_child_in_auto_layout(qtbot, ws):
    page, _, _ = ws
    ed, view = page.editor, page.canvas
    ed.snap_enabled = False
    kids = [ed.add_node("rect", (100, 100 + i * 150, 300, 100)) for i in range(3)]
    ed.select([k.id for k in kids])
    ed.wrap_in_auto_layout("vertical")
    f = ed.selected_nodes()[0]
    first = f.children[0]
    ed.select([first.id], entered_group=f.id)
    view.set_zoom(0.4)
    view.centerOn(300, 400)
    pos = lambda x, y: view.mapFromScene(QPointF(x, y))
    start = (first.x + 50, first.y + 50)
    end = (start[0], f.children[2].y + f.children[2].h - 10)
    qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=pos(*start))
    qtbot.mouseMove(view.viewport(), pos(start[0], start[1] + 60))
    qtbot.mouseMove(view.viewport(), pos(*end))
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=pos(*end))
    f = tree.find(ed.screen(), f.id)[0]
    assert f.children[-1].id == first.id
    ys = [ch.y for ch in f.children]
    assert ys == sorted(ys)  # раскладка снова упорядочена


def _responsive_screen(ed):
    ed.insert_component("m3_top_app_bar")
    card = ed.insert_component("m3_card")
    s = ed.screen()
    desc = next(n for n in tree.descendants(card) if n.name == "Описание")
    k = s.width / 411  # примерно dp → px
    ed.set_props({card.id: {"x": round(16 * k), "w": s.width - 2 * round(16 * k), "constraint_h": "left_right"},
                  desc.id: {"text": LONG_RU}})
    ed.insert_component("m3_nav_bar")
    return card.id, desc.id


def test_responsive_phone_tablet_window_long_russian_text(ws):  # критерий приёмки этапа 3
    page, _, _ = ws
    ed = page.editor
    card_id, desc_id = _responsive_screen(ed)
    s = ed.screen()
    results = {}
    for name, w, h in (("телефон", 720, 1600), ("телефон+", 1080, 2400), ("планшет", 1600, 2560),
                       ("окно", 1280, 800)):
        clone, diags = resize_screen(s, w, h, ed.engine)
        m = tree.node_map(clone)
        bar = next(n for n in clone.nodes if n.name == "Верхняя панель")
        nav = next(n for n in clone.nodes if n.name == "Нижняя навигация")
        card, desc = m[card_id], m[desc_id]
        assert bar.w == w and bar.x == 0, name
        assert nav.w == w and nav.y + nav.h == pytest.approx(h), name
        assert card.x + card.w == pytest.approx(w - (s.width - (tree.find(s, card_id)[0].x
                                                                  + tree.find(s, card_id)[0].w))), name
        assert desc.w == pytest.approx(card.w - card.pad_l - card.pad_r), name
        assert card.h == pytest.approx(sum(c.h for c in card.children) + card.gap * 2 + card.pad_t + card.pad_b,
                                       abs=0.05), name
        assert not [d for d in diags if "текст обрезан" in d.message], name
        # повторный прогон — тот же результат (детерминизм)
        clone2, _ = resize_screen(s, w, h, ed.engine)
        assert json.dumps(clone.to_dict(), sort_keys=True) == json.dumps(clone2.to_dict(), sort_keys=True)
        results[name] = desc.h
    # чем уже экран, тем больше строк у длинного текста
    assert results["телефон"] > results["телефон+"] > results["планшет"]
    assert tree.find(s, card_id)[0].w == s.width - 2 * round(16 * s.width / 411)  # исходный экран не изменился


def test_screen_resize_in_document_applies_constraints_and_undo(ws):
    page, _, _ = ws
    ed = page.editor
    _responsive_screen(ed)
    before = snap(ed)
    ed.set_screen_props({"width": 1600, "height": 2560})
    s = ed.screen()
    nav = next(n for n in s.nodes if n.name == "Нижняя навигация")
    assert nav.w == 1600 and nav.y + nav.h == pytest.approx(2560)
    ed.undo()
    assert snap(ed) == before


def test_frames_and_layout_props_survive_save_reopen(ws):
    page, win, path = ws
    ed = page.editor
    _responsive_screen(ed)
    ed.set_screen(next(s.id for s in ed.doc.screens if s.platform == "windows"))
    ed.insert_component("win_nav_pane")
    ed.insert_component("win_card")
    expected = ed.doc.to_dict()["screens"]
    assert win.save_project()
    assert win.close_project()
    win.open_project(str(path))
    assert win.project_page.editor.doc.to_dict()["screens"] == expected


def test_inspector_sizing_and_constraints_sections(ws):
    page, _, _ = ws
    ed = page.editor
    page.set_simple(False)  # раздел «Привязки» и размеры в раскладке — в расширенном режиме
    card = ed.insert_component("m3_card")
    insp = page.inspector
    assert not insp.sec_al.isHidden() and not insp.sec_cons.isHidden()
    insp.al_cross.setCurrentIndex(insp.al_cross.findData("center"))
    assert tree.find(ed.screen(), card.id)[0].cross_align == "center"
    title = tree.find(ed.screen(), card.id)[0].children[0]
    ed.select_any([title.id])
    assert insp.sec_cons.isHidden()  # внутри Auto Layout привязки не действуют
    insp.sz_h.setCurrentIndex(insp.sz_h.findData("hug"))
    t = tree.find(ed.screen(), title.id)[0]
    assert t.sizing_h == "hug"
    assert page.diagnostics.list.count() == len(ed.diagnostics)


def test_v2_project_opens_with_defaults(tmp_path):
    import zipfile
    from app.core.document.model import Node
    from app.core.persistence.container import load_project
    from app.core.project.service import build_document
    doc = build_document(make_spec(tmp_path))
    doc.screens[0].nodes.append(Node(type="rect", name="Старый", x=5, y=6, w=7, h=8))
    d = doc.to_dict()
    for s in d["screens"]:
        for n in s["nodes"]:
            for k in ("sizing_h", "sizing_v", "min_w", "max_w", "min_h", "max_h", "constraint_h", "constraint_v"):
                n.pop(k)
    p = tmp_path / "схема2.adsproj"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "adsproj", "schema_version": 2, "project_id": doc.meta.id,
                                                 "screens": [s["id"] for s in d["screens"]]}))
        zf.writestr("project.json", json.dumps(d["meta"]))
        for s in d["screens"]:
            zf.writestr(f"screens/{s['id']}.json", json.dumps(s))
    n = load_project(p).screens[0].nodes[0]
    assert (n.x, n.y, n.w, n.h, n.sizing_h, n.constraint_h) == (5, 6, 7, 8, "fixed", "left")


def test_qt_measurer_matches_rendering_width(ws):
    page, _, _ = ws
    ed = page.editor
    t = ed.add_node("text", (50, 50, 300, 40))
    ed.set_props({t.id: {"sizing_h": "hug", "text": "Привет, мир"}})
    t = tree.find(ed.screen(), t.id)[0]
    w1 = t.w
    ed.set_props({t.id: {"text": "Привет, мир! Привет, мир!"}})
    t = tree.find(ed.screen(), t.id)[0]
    assert t.w > w1 * 1.8
    assert Screen  # импорт используется в других тестах
