"""Этап 6 — Interactive Preview: устройства, плотность, ориентация, безопасные области, жесты, прокрутка, ввод,
тестовые сценарии (S17). Движок — без Qt, страница — через интерфейс."""

import json
import zipfile

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.behavior import Interaction, Scenario, Variable, check_action
from app.core.document.model import ModelError, Node, Screen, check_prop
from app.core.persistence.container import load_project, save_project
from app.core.project.service import build_document
from app.engines.layout import LayoutEngine, SimpleMeasurer
from app.engines.logic.engine import Interpreter
from app.engines.preview import checks, scenarios
from app.engines.preview.devices import ViewSpec, adapt, custom_profile, default_profile, profile
from app.ui.shell.main_window import PAGE_PREVIEW, MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec


def engine():
    return LayoutEngine(SimpleMeasurer())


def doc_with_form():
    """Экран «Форма»: поле ввода, кнопка «Далее» (свайп влево и двойное нажатие), экран «Готово»."""
    doc = build_document(make_spec(".", title="Предпросмотр"))
    form = doc.screens[0]
    form.name = "Форма"
    field = Node(type="text", name="Имя", text="Введите имя", x=100, y=400, w=880, h=140, fill="",
                 editable=True)
    nxt = Node(type="rect", name="Далее", x=100, y=800, w=880, h=160, constraint_h="left_right")
    hint = Node(type="text", name="Подсказка", text="Готово к отправке", x=100, y=1000, w=880, h=80, fill="",
                visible=False)
    form.nodes += [field, nxt, hint]
    done = Screen(name="Готово", platform="android", width=1080, height=2400, device_id="android_phone")
    doc.screens.append(done)
    v = Variable(name="Имя", type="text", default="")
    doc.variables.append(v)
    field.input_var = v.id
    doc.interactions += [
        Interaction(form.id, "text_changed", field.id,
                    actions=[check_action({"type": "set_visible", "node_id": hint.id, "mode": "show"})]),
        Interaction(form.id, "swipe_left", nxt.id,
                    actions=[check_action({"type": "navigate", "screen_id": done.id, "transition": "slide_left",
                                           "duration": 200, "easing": "linear"})]),
        Interaction(form.id, "double_tap", nxt.id,
                    actions=[check_action({"type": "set_text", "node_id": hint.id, "text": "Привет, {Имя}"})]),
    ]
    return doc, dict(form=form.id, done=done.id, field=field.id, next=nxt.id, hint=hint.id, var=v.id)


# ---------- устройства ----------
def test_device_specs_sizes_density_orientation():
    doc, _ = doc_with_form()
    s = doc.screens[0]
    phone = default_profile(s)
    assert phone.id == "phone"
    spec = ViewSpec(phone)
    assert spec.design_size(s) == (1080, 2400) and spec.logical_size() == pytest.approx((411.43, 914.29), abs=0.01)
    land = spec.with_(orientation="landscape")
    assert land.px_size() == (2400, 1080) and land.design_size(s) == (2400, 1080)
    tab = ViewSpec(profile("tablet"))                 # 800 × 1280 dp → в единицах экрана (×2.625)
    assert tab.design_size(s) == (2100, 3360)
    assert ViewSpec(phone, dpi=560).logical_size()[0] == pytest.approx(308.57, abs=0.01)  # выше плотность — меньше dp
    ins = spec.insets(s)
    assert ins.top == pytest.approx(32 * 2.625) and ins.bottom == pytest.approx(24 * 2.625)
    assert land.insets(s).left > 0                    # вырез уходит вбок
    win = Screen(name="Окно", platform="windows", width=1280, height=800, device_id="windows_window")
    w125 = ViewSpec(profile("win_1920"))
    assert w125.logical_size() == (1536, 864) and w125.design_size(win) == (1536, 864)
    assert w125.insets(win).top == 0 and not w125.rotatable
    c = custom_profile("android", 1200, 2000, 300)
    assert c.kind == "tablet" and "1200 × 2000" in c.name


def test_adapt_reflows_layout_not_stretch():
    doc, ids = doc_with_form()
    s = doc.screens[0]
    same, d0 = adapt(s, ViewSpec(profile("phone")), engine())
    assert same is s and d0 == []                     # тот же размер — без перестройки
    tab, _ = adapt(s, ViewSpec(profile("tablet")), engine())
    m = tree.node_map(tab)
    assert tab.width == 2100 and m[ids["next"]].w == pytest.approx(2100 - 200)  # растянулась по привязке
    assert m[ids["field"]].w == 880                   # привязка «слева» — ширина не меняется
    assert tree.node_map(s)[ids["next"]].w == 880     # исходный экран не изменён


def test_preview_checks_safe_area_touch_overflow_scroll():
    doc, ids = doc_with_form()
    s = doc.screens[0]
    m = tree.node_map(s)
    m[ids["next"]].y, m[ids["next"]].h = 20, 100       # под строкой состояния и меньше 48 dp (100/2.625 ≈ 38)
    tail = Node(type="rect", name="Хвост", x=0, y=2500, w=200, h=200)
    s.nodes.append(tail)
    spec = ViewSpec(profile("phone"))
    msgs = [d.message for d in checks.check(doc, s.id, s, spec)]
    assert any("строку состояния" in t for t in msgs)
    assert any("меньше рекомендуемых 48" in t for t in msgs)
    assert any("Хвост" in t and "прокрутку" in t for t in msgs)
    s.nodes.remove(tail)
    box = Node(type="frame", name="Лента", x=0, y=1200, w=1080, h=600, scroll="vertical",
               children=[Node(type="rect", name="Длинный", x=0, y=1200, w=1080, h=3000)])
    s.nodes.append(box)
    msgs = [d.message for d in checks.check(doc, s.id, s, spec)]
    assert not any("Длинный" in t for t in msgs)       # внутри прокрутки — не замечание


# ---------- ввод, жесты, сценарии в движке ----------
def test_text_input_binds_variable_and_fires_text_changed():
    doc, ids = doc_with_form()
    it = Interpreter(doc, ids["form"])
    it.dispatch("text_input", ids["field"], "Аня")
    st = it.state
    assert st.texts[ids["field"]] == "Аня" and st.variables[ids["var"]] == "Аня"
    assert st.visibility[ids["hint"]] is True
    it.dispatch("double_tap", ids["next"])
    assert st.texts[ids["hint"]] == "Привет, Аня"
    assert it.log == [("text_input", ids["field"], "Аня"), ("double_tap", ids["next"])]
    bad = it.dispatch("text_input", ids["next"], "x")  # не поле ввода
    assert bad[0].kind == "error"
    digest, _ = Interpreter(doc, ids["form"]).replay(it.log)
    assert digest == it.state.digest()


def test_scenario_record_run_and_regressions(tmp_path):
    doc, ids = doc_with_form()
    it = Interpreter(doc, ids["form"])
    it.dispatch("text_input", ids["field"], "Аня")
    it.dispatch("swipe_left", ids["next"])
    assert it.state.screen_id == ids["done"]
    sc = scenarios.record(it, "Отправка формы")
    assert sc.expect_screen_id == ids["done"] and sc.expect_vars == {ids["var"]: "Аня"}
    r = scenarios.run(doc, sc)
    assert r.ok and r.messages[0].startswith("✓")
    doc.scenarios.append(sc)
    # сохранение и загрузка проекта (схема 6)
    path = tmp_path / "п.adsproj"
    save_project(doc, path)
    with zipfile.ZipFile(path) as zf:
        assert json.loads(zf.read("interactions/scenarios.json"))[0]["name"] == "Отправка формы"
    doc2 = load_project(path)
    assert doc2.scenarios[0].to_dict() == sc.to_dict()
    assert tree.node_map(doc2.screens[0])[ids["field"]].editable is True
    assert scenarios.run(doc2, doc2.scenarios[0]).ok
    # регрессии: изменили логику — сценарий падает с понятной причиной
    doc2.interactions = [i for i in doc2.interactions if i.trigger != "swipe_left"]
    r = scenarios.run(doc2, doc2.scenarios[0])
    assert not r.ok and any("ожидался «Готово»" in t for t in r.messages)
    doc2.screens[0].nodes = [n for n in doc2.screens[0].nodes if n.id != ids["field"]]
    r = scenarios.run(doc2, doc2.scenarios[0])
    assert not r.ok and "Шаг 1: элемент не найден" in r.messages[0]


def test_scenario_validation_rejects_bad_data():
    good = {"id": "s1", "name": "Т", "start_screen_id": "a", "steps": [["tap", "n"], ["system_back", ""],
                                                                       ["text_input", "f", "текст"]]}
    assert len(Scenario.from_dict(good).steps) == 3
    for bad in ([["eval", "n"]], [["tap", "n", "лишнее"]], [["text_input", "f"]], [["tap", "../x?"]], "x"):
        with pytest.raises(ModelError):
            Scenario.from_dict({**good, "steps": bad})
    with pytest.raises(ModelError):
        Scenario.from_dict({**good, "digest": "not-hex"})
    with pytest.raises(ModelError):  # поле ввода — только у текста
        check_prop("editable", True, "rect")
    with pytest.raises(ModelError):
        Node.from_dict({"id": "f", "type": "frame", "scroll": "diagonal"})


# ---------- страница предпросмотра ----------
@pytest.fixture
def app_win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)

    def discard(win):
        for studio in (win.builder, win.icons):
            if studio.editor.stack is not None:
                studio.editor.stack.set_clean()
        win.project_page.mark_clean()
        win.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.resize(1500, 950)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Предпросмотр"))
    w.open_project(str(path))
    yield w, w.project_page.editor, path
    ctx.close()


def load_form(ed):
    doc, ids = doc_with_form()
    src = doc.to_dict()
    from app.core.document.behavior import Interaction as I, Variable as V

    def mutate(d):
        d.screens[:] = [Screen.from_dict(s) for s in src["screens"]]
        d.variables[:] = [V.from_dict(v) for v in src["variables"]]
        d.interactions[:] = [I.from_dict(i) for i in src["interactions"]]
    assert ed.patch("Форма", mutate)
    ed.set_screen(ids["form"])
    return ids


def type_keys(widget, text):
    """Набор символов событиями клавиатуры (QTest.keyClicks не работает с кириллицей на offscreen)."""
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    for ch in text:
        QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, ch))


def center(p, nid):
    n = tree.node_map(p.screen)[nid]
    return QPointF(n.x + n.w / 2, n.y + n.h / 2)


def test_preview_page_devices_rotation_density_compare(qtbot, app_win):  # S17
    win, ed, _ = app_win
    ids = load_form(ed)
    win.run_prototype()
    page = win.preview
    assert win.pages.currentIndex() == PAGE_PREVIEW and page.player is not None
    p = page.player
    p.stop_clock()
    assert (p.screen.width, p.screen.height) == (1080, 2400) and p.spec.profile.id == "phone"
    assert "411 × 914 dp" in page.spec_info.text()
    page.set_profile(profile("tablet"))
    assert (p.screen.width, p.screen.height) == (2100, 3360)
    assert tree.node_map(p.screen)[ids["next"]].w == pytest.approx(1900)
    page.rotate()
    assert p.screen.width > p.screen.height and p.spec.orientation == "landscape"
    page.density.setCurrentIndex(page.density.findData(160))   # mdpi: 2560 px → 2560 dp
    assert p.spec.density == 160 and p.screen.width == round(2560 * 2.625)
    page.set_profile(profile("phone"))
    page.tabs.setCurrentIndex(1)
    thumbs = [page.compare_lay.itemAt(i).widget() for i in range(page.compare_lay.count())]
    assert len([t for t in thumbs if t is not None]) == 4   # телефон, компактный, складной, планшет
    page.tabs.setCurrentIndex(0)
    page.o_safe.setChecked(True)
    assert p.show_safe
    pm = p.frame()
    assert not pm.isNull()
    # устройство не меняет документ
    assert ed.screen().width == 1080 and not any(n.w == 1900 for n, _, _ in tree.walk(ed.screen().nodes))


def test_preview_gestures_keyboard_input_scroll(qtbot, app_win):
    win, ed, _ = app_win
    ids = load_form(ed)
    box = ed.add_node("frame", (100, 1300, 880, 400))
    ed.set_props({box.id: {"scroll": "vertical", "fill": "#222222"}})
    inner = ed.add_node("rect", (100, 1300, 880, 1500))
    ed.patch("В фрейм", lambda doc: _nest(doc, ids["form"], box.id, inner.id))
    win.run_prototype()
    p = win.preview.player
    p.stop_clock()
    # касание поля → фокус и экранная клавиатура; ввод с экранной и физической клавиатуры
    qtbot.mouseClick(p.view.viewport(), Qt.MouseButton.LeftButton, pos=p.view.mapFromScene(center(p, ids["field"])))
    assert p.focus_id == ids["field"] and p.keyboard_visible()
    key = next(r for r, ch in p.keyboard_keys() if ch == "а")
    p.press(key.center())
    p.release(key.center())
    type_keys(p.view, "ня")
    assert p.interp.state.texts[ids["field"]] == "аня" and p.interp.state.variables[ids["var"]] == "аня"
    assert tree.node_map(p.screen)[ids["hint"]].visible
    qtbot.keyClick(p.view, Qt.Key.Key_Backspace)
    qtbot.keyClick(p.view, Qt.Key.Key_Return)
    assert p.interp.state.texts[ids["field"]] == "ан" and p.focus_id is None
    # двойное нажатие (виртуальные часы: второе касание в пределах 300 мс)
    nxt = center(p, ids["next"])
    p.press(nxt); p.release(nxt)
    p.advance(120)
    p.press(nxt); p.release(nxt)
    assert tree.node_map(p.screen)[ids["hint"]].text == "Привет, ан"
    # прокрутка колесом внутри фрейма
    y0 = tree.node_map(p.screen)[inner.id].y
    p.wheel(QPointF(500, 1400), -240)
    assert tree.node_map(p.screen)[inner.id].y < y0 and p.scroll[box.id] > 0
    p.wheel(QPointF(500, 1400), -120 * 100)
    assert p.scroll[box.id] == pytest.approx(p.scroll_max[box.id])  # не дальше конца
    # свайп влево по кнопке → переход
    p.press(nxt)
    p.drag(QPointF(nxt.x() - 200, nxt.y()))
    p.release(QPointF(nxt.x() - 400, nxt.y()))
    assert p.interp.state.screen_id == ids["done"] and p.transition is not None
    p.advance(1000)
    assert p.transition is None and p.scroll == {}


def _nest(doc, screen_id, frame_id, child_id):
    s = next(x for x in doc.screens if x.id == screen_id)
    child = next(n for n in s.nodes if n.id == child_id)
    s.nodes.remove(child)
    next(n for n in s.nodes if n.id == frame_id).children.append(child)


def test_preview_saved_scenarios_run_and_fail_after_change(qtbot, app_win):
    win, ed, path = app_win
    ids = load_form(ed)
    win.run_prototype()
    page = win.preview
    p = page.player
    p.stop_clock()
    p.tap(ids["field"])
    p.type_text("Ира")
    p.dispatch("swipe_left", ids["next"])
    assert page.save_scenario("Отправка")
    assert len(ed.doc.scenarios) == 1 and page.sc_list.count() == 1
    assert page.run_all() == (1, 1)
    assert page.sc_list.item(0).text().startswith("✓")
    page.sc_list.setCurrentRow(0)
    page.show_selected()
    assert p.interp.state.screen_id == ids["done"]
    assert win.save_project()
    assert load_project(path).scenarios[0].name == "Отправка"
    # убрали переход — тест сценария падает
    ed.patch("Без свайпа", lambda doc: doc.interactions.__setitem__(
        slice(None), [i for i in doc.interactions if i.trigger != "swipe_left"]))
    win.show_page(PAGE_PREVIEW)
    assert page.run_all() == (0, 1)
    page.sc_list.setCurrentRow(0)
    assert "ожидался" in page.sc_result.text()
    ed.undo()
    assert page.run_all() == (1, 1)


def test_windows_preview_frame_and_scale(qtbot, app_win):
    win, ed, _ = app_win
    ed.add_screen(Screen(name="Окно", platform="windows", width=1280, height=800, device_id="windows_window"))
    btn = ed.add_node("rect", (40, 40, 200, 40))
    ed.set_props({btn.id: {"constraint_h": "left_right"}})
    win.run_prototype()
    page = win.preview
    p = page.player
    p.stop_clock()
    assert p.spec.profile.platform == "windows" and p.screen.width == 1280
    assert not page.b_landscape.isEnabled()
    page.set_profile(profile("win_1920"))                  # 1920 × 1080 при 125 % → 1536 × 864
    assert (p.screen.width, p.screen.height) == (1536, 864)
    assert tree.node_map(p.screen)[btn.id].w == pytest.approx(200 + 256)
    from app.ui.studio.prototype import frame_rect
    assert frame_rect(p.screen, p.spec).top() < 0        # заголовок окна над содержимым
    assert any("наведен" not in page.checks.item(i).text() for i in range(page.checks.count()))


def test_material_field_under_gesture_bar_is_flagged():
    """1.37: поле ввода Material на жестовой полоске — замечание, даже без своих правил; нижнее меню — нет."""
    doc, _ = doc_with_form()
    s = doc.screens[0]
    field = Node(type="frame", name="Сообщение", role="m3.text_field", x=0, y=s.height - 120, w=600, h=150)
    menu = Node(type="frame", name="Меню", role="m3.nav_bar", x=0, y=s.height - 210, w=s.width, h=210)
    s.nodes += [field, menu]
    msgs = [d.message for d in checks.check(doc, s.id, s, ViewSpec(profile("phone")))]
    assert any("Сообщение" in t and "панель навигации" in t for t in msgs)
    assert not any("Меню" in t and "панель навигации" in t for t in msgs)
