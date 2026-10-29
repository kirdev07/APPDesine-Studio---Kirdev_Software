"""1.25: всё переключается — пункт меню → экран, вкладка → панель; в Android: выбранный пункт из дизайна,
состояния своих компонентов, свайпы."""

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.behavior import Interaction
from app.core.document.model import Node
from app.engines.preview import live
from app.exporters.ai_export import ExportOptions, build_package
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec


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
    _, path = ctx.service.create(make_spec(projects_dir, title="Переключение"))
    w.open_project(str(path))
    yield w
    ctx.close()


def _screen_src(ed, screen_id):
    files = build_package(ed.doc, ExportOptions()).files
    return next(v.decode() for k, v in files.items() if k.endswith("Screen.kt")
                and f"Экран «{ed.doc.screen(screen_id).name}»" in v.decode())


def test_nav_items_lead_to_screens(win):
    page, ed = win.project_page, win.project_page.editor
    a = ed.add_template_screen("profile")                      # своё нижнее меню, выбран первый пункт
    b = ed.add_template_screen("chat")
    c = ed.add_template_screen("settings")
    ed.set_screen(a.id)
    nav = next(n for n in ed.screen().nodes if n.role == "m3.nav_bar")
    ed.select([nav.id])
    page.inspector.refresh()
    insp = page.inspector
    assert not insp.sec_switch.isHidden() and len(insp.switch_combos) == 4
    assert ed.nav_targets(nav.id)[0] == a.id                  # выбранный пункт — этот экран
    assert ed.link_nav_item(nav.id, 1, b.id) and ed.link_nav_item(nav.id, 3, c.id)
    for sid, idx in ((b.id, 1), (c.id, 3)):
        navs = [n for n in ed.doc.screen(sid).nodes if n.role == "m3.nav_bar"]
        assert len(navs) == 1 and live.selected(navs[0]) == idx  # на экране — своё меню, свой пункт выбран
    # на «Чате» меню не было: поле ввода и содержимое — над меню, не под ним
    nb = next(n for n in ed.doc.screen(b.id).nodes if n.role == "m3.nav_bar")
    assert all(n.y + n.h <= nb.y + 0.5 for n in ed.doc.screen(b.id).nodes if n is not nb and n.visible)
    # с экрана B: пункт 0 ведёт на A, пункт 3 — на C
    nb = next(n for n in ed.doc.screen(b.id).nodes if n.role == "m3.nav_bar")
    rules = {it.node_id: it.actions[0]["screen_id"] for it in ed.doc.interactions
             if it.screen_id == b.id and it.trigger == "tap" and it.node_id in {x.id for x in live._items(nb)}}
    items = live._items(nb)
    assert rules[items[0].id] == a.id and rules[items[3].id] == c.id and items[1].id not in rules
    # прототип: нажали «Чаты» на A — открылся B
    from app.ui.studio.prototype import PrototypePlayer
    p = PrototypePlayer(ed, start_screen_id=a.id)
    p.dispatch("tap", live._items(nav)[1].id)
    assert p.interp.state.screen_id == b.id
    # Android: на экране B выбран второй пункт
    assert "mutableStateOf(1)" in _screen_src(ed, b.id)
    # отмена — одной записью
    ed.undo()
    assert not any(n.role == "m3.nav_bar" and live.selected(n) == 3 for n in ed.doc.screen(c.id).nodes)


def test_tabs_show_their_panel(win):
    page, ed = win.project_page, win.project_page.editor
    s = ed.screen()
    tabs = ed.insert_component("m3_tabs")
    p1 = ed.add_node("frame", (0, 400, 600, 300))
    p2 = ed.add_node("frame", (0, 400, 600, 300))
    ed.set_props({p1.id: {"name": "Панель чатов"}, p2.id: {"name": "Панель статусов"}}, "имена")
    tabs = tree.find(ed.screen(), tabs.id)[0]
    assert {p1.id, p2.id} <= {n.id for n in ed.panel_candidates(tabs.id)}
    assert ed.link_tab_panel(tabs.id, 0, p1.id) and ed.link_tab_panel(tabs.id, 1, p2.id)
    m = tree.node_map(ed.screen())
    assert m[p1.id].visible and not m[p2.id].visible              # видна панель выбранной вкладки
    assert ed.tab_panels(tabs.id)[:2] == [p1.id, p2.id]
    from app.ui.studio.prototype import PrototypePlayer
    p = PrototypePlayer(ed, start_screen_id=s.id)
    p.dispatch("tap", live._items(tabs)[1].id)
    vis = p.interp.state.visibility
    assert vis[p2.id] and not vis[p1.id]
    src = _screen_src(ed, s.id)
    assert src.count("by rememberSaveable { mutableStateOf(") >= 3          # видимость панелей + вкладка
    ed.select([tabs.id])
    page.inspector.refresh()
    assert not page.inspector.sec_switch.isHidden() and page.inspector.switch_combos[1].currentData() == p2.id


def test_android_component_states_and_swipes(win):
    ed = win.project_page.editor
    s = ed.screen()
    agree = ed.insert_component("m3_button_outlined")
    ed.select([agree.id])
    cid = ed.create_component("Флажок")
    inst = ed.selection[0]
    defn = ed.doc.component(cid)
    defn.states = {"on": {"__root__": {"fill": "#22C55E"}}}
    defn.behavior = {"hover": False, "press": False, "toggle": ["default", "on"]}
    ed.update_component(defn)
    card = ed.add_node("rect", (100, 1200, 600, 300))
    other = ed.add_node("rect", (100, 1600, 600, 100))
    sid = s.id

    def rules(doc):
        doc.interactions += [
            Interaction(screen_id=sid, trigger="swipe_left", node_id=card.id,
                        actions=[{"type": "set_state", "node_id": inst, "state": "on"}]),
            Interaction(screen_id=sid, trigger="swipe_right", node_id=card.id,
                        actions=[{"type": "set_state", "node_id": inst, "state": "default"}]),
            Interaction(screen_id=sid, trigger="tap", node_id=other.id,
                        actions=[{"type": "set_state", "node_id": inst, "state": "on"}])]
    assert ed.patch("правила", rules)
    src = _screen_src(ed, sid)
    assert "TODO: действие «set_state»" not in src and "TODO: жесты" not in src
    assert "when (state" in src and '"default" -> {' in src and "else -> {" in src  # свой вид для каждого состояния
    assert 'mutableStateOf("default")' in src
    assert '= if (state' in src                                         # встроенное переключение по нажатию
    assert ".pointerInput(Unit) {" in src and "detectDragGestures(" in src and "abs(dx) > far" in src
    assert src.count('= "on"') >= 2                                      # свайп влево и нажатие на «другое»
