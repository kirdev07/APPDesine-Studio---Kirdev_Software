"""1.16: прототип и анимации — «Подождать» и автопереход, умный переход (Smart Animate),
окна поверх экрана с затемнением и шторка снизу."""

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.behavior import Interaction, check_action
from app.core.document.model import Node, Screen
from app.engines.logic.engine import Interpreter
from app.engines.logic.runtime import compose, overlay_entrance, smart_transition
from app.exporters.ai_export import ExportOptions, build_package
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec


def test_actions_validate():
    assert check_action({"type": "wait", "duration": 1500}) == {"type": "wait", "duration": 1500}
    assert check_action({"type": "open_overlay", "node_id": "abc"})["scrim"] is False   # старые проекты — без
    assert check_action({"type": "navigate", "screen_id": "abc", "transition": "smart"})["transition"] == "smart"


def test_smart_transition_and_overlay_entrance():
    a = Screen(name="a", platform="android", width=400, height=800, nodes=[
        Node(type="rect", name="Фото", x=0, y=0, w=100, h=100, radius=8, fill="#FF0000"),
        Node(type="rect", name="Кнопка", x=10, y=700, w=100, h=40)])
    b = Screen(name="b", platform="android", width=400, height=800, nodes=[
        Node(type="rect", name="Фото", x=0, y=0, w=400, h=300, radius=0, fill="#00FF00"),
        Node(type="text", name="Описание", x=10, y=320, w=300, h=40, text="x")])
    anim = smart_transition(a, b, 400, "ease_out")
    tracks = {(t.node_id, t.prop): t for t in anim.tracks}
    foto = b.nodes[0].id
    assert tracks[(foto, "w")].keyframes[0].value == 100 and tracks[(foto, "w")].keyframes[-1].value == 400
    assert (foto, "fill") in tracks and (b.nodes[1].id, "opacity") in tracks     # новое — проявляется
    assert smart_transition(a, b, 0, "ease_out") is None
    sheet = Node(type="frame", name="Шторка", x=0, y=500, w=400, h=300)
    s = Screen(name="s", platform="android", width=400, height=800, nodes=[sheet])
    ent = overlay_entrance(s, sheet.id)
    assert ent.tracks[0].prop == "y" and ent.tracks[0].keyframes[0].value == 800   # выезжает снизу


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
    _, path = ctx.service.create(make_spec(projects_dir, title="Прототип"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_auto_advance_wait_and_compose(win):
    page, ed = win.project_page, win.project_page.editor
    first = ed.screen().id
    second = ed.add_template_screen("home").id
    ed.set_screen(first)
    insp = page.inspector
    ed.select([])
    insp.refresh()
    insp.s_auto.setCurrentIndex(insp.s_auto.findData(second))
    insp.s_auto.activated.emit(insp.s_auto.currentIndex())
    insp.s_auto_ms.setValue(1.5)
    assert ed.auto_advance() == (second, 1500, "fade")
    it = Interpreter(ed.doc, first)
    assert it.effects[-1].kind == "wait" and it.state.screen_id == first
    effects = it.resume(it.effects[-1])
    assert effects[0].kind == "navigate" and it.state.screen_id == second
    # ушли с экрана раньше — продолжение не срабатывает
    it2 = Interpreter(ed.doc, first)
    w = it2.effects[-1]
    it2.state.screen_id = second
    assert it2.resume(w) == []
    # проигрыватель: через 1.5 с сам переходит
    from app.ui.studio.prototype import PrototypePlayer
    player = PrototypePlayer(ed, start_screen_id=first)
    assert player.interp.state.screen_id == first and player.waits
    player.advance(1600)
    assert player.interp.state.screen_id == second
    f = build_package(ed.doc, ExportOptions()).files
    src = next(v.decode() for k, v in f.items() if b"delay(1500)" in v)
    assert "val scope = rememberCoroutineScope()" in src and "scope.launch {" in src
    ed.set_auto_advance(None)
    assert ed.auto_advance() is None


def test_overlay_scrim_and_smart_tap(win):
    page, ed = win.project_page, win.project_page.editor
    s = ed.screen()
    btn = ed.add_node("rect")
    sheet = ed.add_node("frame")
    ed.set_props({sheet.id: {"name": "Шторка", "y": s.height - 300.0, "h": 300.0, "x": 0.0, "w": float(s.width)},
                  btn.id: {"name": "Открыть"}}, "x")
    ed.select([btn.id])
    assert ed.set_overlay_tap(btn.id, sheet.id)
    assert not tree.find(ed.screen(), sheet.id)[0].visible                      # окно скрыто до открытия
    assert ed.tap_action(btn.id)["scrim"] is True and "окно" in page._tap_text(btn.id)
    it = Interpreter(ed.doc, s.id)
    it.dispatch("tap", btn.id)
    assert it.state.overlays == [sheet.id] and it.state.scrims == [sheet.id]
    scr = compose(ed.doc, it.state, ed.engine)
    ids = [n.id for n in scr.nodes]
    assert ids.index(f"scrim:{sheet.id}") == ids.index(sheet.id) - 1            # затемнение прямо под окном
    it.dispatch("tap", f"scrim:{sheet.id}")
    assert it.state.overlays == [] and it.state.scrims == []
    f = build_package(ed.doc, ExportOptions()).files
    src = next(v.decode() for k, v in f.items() if b"MutableInteractionSource()" in v)
    assert "slideInVertically { it } + fadeIn()" in src and "Color(0x66000000)" in src
    # умный переход: одноимённый элемент на двух экранах получает .smart(...)
    other = ed.add_template_screen("product").id
    ed.set_screen(s.id)
    ed.set_props({btn.id: {"name": "Фото товара"}}, "n")
    ed.set_tap_action(btn.id, {"type": "navigate", "screen_id": other})
    ed.select([btn.id])
    page._fill_tap_menu()
    how = next(m for m in page._tap_submenus if m.title() == "Как переходить")
    next(a for a in how.actions() if "Smart" in a.text()).trigger()
    assert ed.tap_action(btn.id)["transition"] == "smart"
    files = build_package(ed.doc, ExportOptions()).files
    allsrc = "".join(v.decode() for k, v in files.items() if k.endswith(".kt"))
    assert '.smart("Фото товара")' in allsrc and "SharedTransitionLayout" in allsrc
    assert "fun Modifier.smart(key: String)" in allsrc
