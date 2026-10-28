"""Этап 5 через интерфейс: логика, анимации, проигрыватель прототипа, запись и повтор (S15, S16)."""

import json
import zipfile

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.behavior import Animation, Keyframe, Track, Variable
from app.core.document.model import Screen
from app.core.persistence.container import load_project
from app.ui.shell.main_window import PAGE_ANIMATIONS, PAGE_LOGIC, MainWindow
from app.ui.studio.preview import PreviewPage
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec


@pytest.fixture
def app_win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)

    def discard(win):
        for studio in (win.builder, win.icons):
            if studio.editor.stack is not None:
                studio.editor.stack.set_clean()
            if hasattr(studio, "_states_dirty"):
                studio._states_dirty = False
        win.project_page.mark_clean()
        win.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.resize(1500, 950)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Прототип"))
    w.open_project(str(path))
    yield w, w.project_page.editor, path
    ctx.close()


def build(win, ed):
    """Вход (кнопка-компонент с переключателем «согласие») → Главная (счётчик, анимация, окно) → назад."""
    login = ed.screen()
    login.name = "Вход"
    btn = ed.insert_component("m3_button_filled")
    ed.set_props({btn.id: {"x": 100, "y": 1000}})
    agree = ed.insert_component("m3_button_outlined")
    ed.set_props({agree.id: {"x": 100, "y": 700}})
    ed.select([agree.id])
    cid = ed.create_component("Флажок")
    agree_inst = ed.selection[0]
    defn = ed.doc.component(cid)
    defn.states = {"on": {"__root__": {"fill": "#22C55E"}}, "hover": {"__root__": {"opacity": 0.8}}}
    defn.behavior = {"hover": True, "press": False, "toggle": ["default", "on"]}
    ed.update_component(defn)
    ed.add_screen(Screen(name="Главная", platform="android", width=1080, height=2400, device_id="android_phone"))
    home = ed.screen()
    plus = ed.add_node("rect", (100, 300, 200, 200))
    counter = ed.add_node("text", (100, 600, 800, 80))
    back = ed.add_node("rect", (100, 900, 200, 120))
    dialog = ed.add_node("frame", (100, 1200, 800, 600))
    ed.set_props({dialog.id: {"visible": False, "fill": "#333333"}})
    ed.set_screen(login.id)
    return dict(login=login.id, home=home.id, btn=btn.id, agree=agree_inst, plus=plus.id, counter=counter.id,
                back=back.id, dialog=dialog.id)


def configure_logic(win, ed, ids):
    """Часть логики — через страницу «Логика» (как пользователь), часть — через API редактора."""
    page = win.logic
    win.show_page(PAGE_LOGIC)
    # переменные через форму
    page.new_var()
    page.v_name.setText("Счёт")
    page.v_type.setCurrentIndex(page.v_type.findData("number"))
    page.v_default.setText("0")
    page.save_var()
    page.new_var()
    page.v_name.setText("Согласие")
    page.v_type.setCurrentIndex(page.v_type.findData("bool"))
    page.v_default.setText("нет")
    page.save_var()
    v_count = next(v for v in ed.doc.variables if v.name == "Счёт")
    v_agree = next(v for v in ed.doc.variables if v.name == "Согласие")
    assert v_count.default == 0 and v_agree.default is False
    # кнопка «Войти»: если согласие — на главную
    ed.select([ids["btn"]])
    page.new_interaction()
    page.c_on.setChecked(True)
    page.c_var.setCurrentIndex(page.c_var.findData(v_agree.id))
    page.c_val.setText("да")
    page.a_type.setCurrentIndex(page.a_type.findData("navigate"))
    page.add_action()
    assert page.work["actions"][0]["screen_id"] == ids["home"]
    assert page.save()
    # флажок: переключение переменной (поведение toggle компонента меняет вид)
    ed.select([ids["agree"]])
    page.new_interaction()
    page.a_type.setCurrentIndex(page.a_type.findData("set_variable"))
    page.add_action()
    page.work["actions"][0].update({"var_id": v_agree.id, "mode": "toggle"})
    assert page.save()
    # главная: анимация и действия через API
    anim = Animation(name="Пульс", screen_id=ids["home"], duration=400,
                     tracks=[Track(ids["plus"], "opacity", [Keyframe(0, 1.0, "linear"), Keyframe(200, 0.2, "linear"),
                                                            Keyframe(400, 1.0)])])
    ed.patch("Анимация", lambda doc: doc.animations.append(Animation.from_dict(anim.to_dict())))
    from app.core.document.behavior import Interaction, check_action
    acts_plus = [{"type": "set_variable", "var_id": v_count.id, "mode": "increment", "value": 1},
                 {"type": "set_text", "node_id": ids["counter"], "text": "Нажатий: {Счёт}"},
                 {"type": "play_animation", "animation_id": anim.id}]
    its = [Interaction(ids["home"], "tap", ids["plus"], actions=[check_action(a) for a in acts_plus]),
           Interaction(ids["home"], "long_press", ids["plus"],
                       actions=[check_action({"type": "open_overlay", "node_id": ids["dialog"]})]),
           Interaction(ids["home"], "tap", ids["back"],
                       actions=[check_action({"type": "back", "transition": "fade", "duration": 200,
                                              "easing": "linear"})]),
           Interaction(ids["home"], "screen_open", "",
                       actions=[check_action({"type": "set_text", "node_id": ids["counter"],
                                              "text": "Нажатий: {Счёт}"})])]
    ed.patch("Логика", lambda doc: doc.interactions.extend(its))
    page.refresh()
    assert page.diag.item(0).text().startswith("✓"), [page.diag.item(i).text() for i in range(page.diag.count())]
    return anim


def click(qtbot, player, node_id):
    n = tree.node_map(player.screen)[node_id]
    pos = player.view.mapFromScene(QPointF(n.x + n.w / 2, n.y + n.h / 2))
    qtbot.mouseClick(player.view.viewport(), Qt.MouseButton.LeftButton, pos=pos)


def test_interactive_multiscreen_prototype_with_replay(qtbot, app_win):  # критерий приёмки этапа 5
    win, ed, path = app_win
    ids = build(win, ed)
    configure_logic(win, ed, ids)
    win.run_prototype()
    proto: PreviewPage = win.preview
    p = proto.player
    p._timer.stop()  # время ведём вручную — детерминированно
    qtbot.waitExposed(proto)
    assert p.interp.state.screen_id == ids["login"]
    click(qtbot, p, ids["btn"])                       # без согласия — остаёмся
    assert p.interp.state.screen_id == ids["login"]
    click(qtbot, p, ids["agree"])                     # согласие + переключение состояния компонента
    v_agree = next(v for v in ed.doc.variables if v.name == "Согласие")
    assert p.interp.state.variables[v_agree.id] is True
    assert p.interp.state.states[ids["agree"]] == "on" and p.active  # встроенное переключение, идёт переход
    p.advance(1000)
    assert tree.node_map(p.screen)[ids["agree"]].fill == "#22C55E"
    click(qtbot, p, ids["btn"])
    assert p.interp.state.screen_id == ids["home"]
    assert p.transition is not None and p.transition.kind == "slide_left"
    p.advance(150)
    assert p.transition is not None
    p.advance(400)
    assert p.transition is None
    assert tree.node_map(p.screen)[ids["counter"]].text == "Нажатий: 0"
    click(qtbot, p, ids["plus"])
    p.advance(200)                                     # середина анимации
    assert tree.node_map(p.screen)[ids["plus"]].opacity == pytest.approx(0.2, abs=0.01)
    p.advance(300)
    assert tree.node_map(p.screen)[ids["plus"]].opacity == pytest.approx(1.0)
    click(qtbot, p, ids["plus"])
    assert tree.node_map(p.screen)[ids["counter"]].text == "Нажатий: 2"
    p.press(QPointF(tree.node_map(p.screen)[ids["plus"]].x + 5, tree.node_map(p.screen)[ids["plus"]].y + 5))
    p._long_press()
    p.release(QPointF(0, 0))
    assert ids["dialog"] in p.interp.state.overlays and tree.node_map(p.screen)[ids["dialog"]].visible
    p.system_back()                                     # системная «Назад» закрывает окно
    assert not p.interp.state.overlays
    click(qtbot, p, ids["back"])
    p.advance(1000)
    assert p.interp.state.screen_id == ids["login"]
    proto.refresh()
    assert proto.log.count() >= 8
    # запись и детерминированный повтор
    proto.remember()
    recorded = p.interp.state.digest()
    proto.replay()
    assert "совпадает" in proto.replay_result.text()
    assert p.interp.state.digest() == recorded
    # сохранение и повтор того же сценария на загруженном проекте
    script = list(proto.script)
    assert win.save_project()
    from app.engines.logic.engine import Interpreter
    digest, _ = Interpreter(load_project(path), ids["login"]).replay(script)
    assert digest == recorded


def test_reduced_motion_skips_transitions_and_animations(qtbot, app_win):
    win, ed, _ = app_win
    ids = build(win, ed)
    configure_logic(win, ed, ids)
    win.run_prototype()
    p = win.preview.player
    p._timer.stop()
    win.preview.reduced.setChecked(True)
    p.dispatch("tap", ids["agree"])
    p.dispatch("tap", ids["btn"])
    assert p.interp.state.screen_id == ids["home"] and p.transition is None
    p.dispatch("tap", ids["plus"])
    p.advance(0)
    assert tree.node_map(p.screen)[ids["plus"]].opacity == pytest.approx(1.0)
    assert not p.active


def test_hover_behavior_in_player(qtbot, app_win):
    win, ed, _ = app_win
    ids = build(win, ed)
    win.run_prototype()
    p = win.preview.player
    p._timer.stop()
    n = tree.node_map(p.screen)[ids["agree"]]
    p.hover(QPointF(n.x + 5, n.y + 5))
    assert p.interp.state.states[ids["agree"]] == "hover"
    p.hover(QPointF(1, 1))
    assert p.interp.state.states[ids["agree"]] == "default"
    assert [t for t, _ in p.interp.log] == ["hover_enter", "hover_leave"]


def test_animation_studio_edit_play_undo(qtbot, app_win):  # S16
    win, ed, _ = app_win
    r = ed.add_node("rect", (100, 100, 200, 200))
    win.show_page(PAGE_ANIMATIONS)
    page = win.animations
    monkey_name = ("Появление", True)
    import PySide6.QtWidgets as W
    orig = W.QInputDialog.getText
    W.QInputDialog.getText = staticmethod(lambda *a, **k: monkey_name)
    try:
        page.new_anim()
    finally:
        W.QInputDialog.getText = orig
    a = page.anim()
    assert a is not None and page.list.count() == 1
    page.t_node.setCurrentIndex(page.t_node.findData(r.id))
    page.t_prop.setCurrentIndex(page.t_prop.findData("x"))
    page.add_track()
    a = page.anim()
    assert len(a.tracks) == 1 and [k.value for k in a.tracks[0].keyframes] == [100, 100]
    page._select_key(0, 1)
    page.k_value.setText("700")
    page.k_ease.setCurrentIndex(page.k_ease.findData("cubic"))
    page.k_bez[1].setValue(0.0)
    page.apply_key()
    a = page.anim()
    k = a.tracks[0].keyframes[1]
    assert (k.value, k.easing, k.bezier[1]) == (700, "cubic", 0.0)
    page._select_key(0, 0)
    page.k_ease.setCurrentIndex(page.k_ease.findData("linear"))
    page.apply_key()
    page.timeline.playhead = 300
    page.preview()
    shown = [i for i in page.view.scene().items() if getattr(i, "node", None) is not None and i.node.id == r.id][0]
    assert shown.node.x == pytest.approx(100 + 600 * 0.5)
    page._move_key(0, 1, 400)
    assert page.anim().tracks[0].keyframes[1].t == 400
    page.toggle_play()
    page._timer.stop()
    page.advance(10_000)
    assert page.timeline.playhead == page.anim().duration and not page.playing
    assert tree.find(ed.screen(), r.id)[0].x == 100  # просмотр не меняет документ
    n = len(ed.doc.animations)
    ed.undo()  # отмена перемещения кадра
    assert page.anim().tracks[0].keyframes[1].t == 600
    assert len(ed.doc.animations) == n


def test_builder_actions_and_transition_saved(qtbot, app_win):
    win, ed, _ = app_win
    btn = ed.insert_component("m3_button_filled")
    ed.select([btn.id])
    cid = ed.create_component("Переключатель")
    win.open_in_builder(cid)
    b = win.builder
    b.preset_states()
    b.tr_duration.setValue(400)
    b.bh_hover.setChecked(True)
    b.bh_toggle.setChecked(True)
    b._fill_state_combos([])
    b.bh_b.setCurrentIndex(b.bh_b.findData("pressed"))
    assert b.save()
    d = ed.doc.component(cid)
    assert d.transition["duration"] == 400 and d.behavior["hover"] and d.behavior["toggle"] == ["default", "pressed"]
    assert [b.tabs.tabText(i) for i in range(b.tabs.count())] == ["Дизайн", "Состояния", "Варианты", "Анимация", "Действия"]


def test_logic_diagnostics_and_persistence(qtbot, app_win):
    win, ed, path = app_win
    ids = build(win, ed)
    configure_logic(win, ed, ids)
    ed.set_screen(ids["home"])
    ed.select([ids["counter"]])
    ed.delete_selection()
    ed.refresh_diagnostics()
    assert any("элемент не на этом экране" in d.message for d in ed.diagnostics)
    ed.undo()
    assert win.save_project()
    with zipfile.ZipFile(path) as zf:
        assert "interactions/logic.json" in zf.namelist() and "animations/animations.json" in zf.namelist()
    got = load_project(path)
    assert json.dumps([i.to_dict() for i in got.interactions], sort_keys=True) == \
        json.dumps([i.to_dict() for i in ed.doc.interactions], sort_keys=True)
    assert got.animations[0].tracks[0].keyframes[1].value == pytest.approx(0.2)
    assert [v.name for v in got.variables] == [v.name for v in ed.doc.variables]
    assert Variable  # используется в других тестах модуля
