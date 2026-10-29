"""1.32: экраны Windows → готовое приложение на Python + PySide6 (ui.json + среда выполнения)."""

import importlib.util
import json
import re
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractButton, QApplication, QLineEdit, QMessageBox, QPushButton

from app.context import AppContext
from app.core.document import tree
from app.exporters import windows_app
from app.exporters.ai_export import ExportOptions, build_package
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec


@pytest.fixture
def win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)

    def discard(x):
        x.project_page.mark_clean()
        x.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Окно", platforms=["windows"],
                                           devices=["windows_window"]))
    w.open_project(str(path))
    yield w
    ctx.close()


def _app(ed):
    blank = ed.screen().id
    login, settings = ed.add_template_screen("win_login"), ed.add_template_screen("win_settings")
    ed.remove_screen(blank)
    ed.set_screen(login.id)
    btn = next(n for n, _, _ in tree.walk(ed.screen().nodes) if n.role == "win.button_accent")
    ed.set_tap_action(btn.id, {"type": "navigate", "screen_id": settings.id, "transition": "fade", "duration": 200,
                               "easing": "ease_out"})
    return login, settings


def test_files_and_ui_json(win):
    ed = win.project_page.editor
    login, settings = _app(ed)
    files = windows_app.files(ed.doc, ed.doc.screens)
    for name in ("ui.json", "app_runtime.py", "main.py", "requirements.txt", "README.md"):
        assert f"windows_app/{name}" in files, name
    ui = json.loads(files["windows_app/ui.json"])
    assert ui["start"] == login.id and len(ui["screens"]) == 2
    kinds = set()

    def walk(ns):
        for n in ns:
            kinds.add(n["kind"])
            walk(n.get("children", []))
    for s in ui["screens"]:
        walk(s["nodes"])
    assert {"accent_button", "textbox", "checkbox", "link", "frame", "text", "svg"} <= kinds
    assert any(i["actions"][0].get("screen_id") == settings.id for i in ui["interactions"])
    runtime = files["windows_app/app_runtime.py"].decode()
    assert not re.search(r"(?<![.\w])(eval|exec)\(", runtime)               # только данные, без выполнения кода
    pkg = build_package(ed.doc, ExportOptions()).files
    assert "windows_app/ui.json" in pkg


def test_runtime_builds_window_and_navigates(win, tmp_path, qtbot):
    ed = win.project_page.editor
    _app(ed)
    win.export_page.refresh()
    out = win.export_page.save_windows(str(tmp_path))
    assert out is not None and (out / "main.py").exists()
    spec = importlib.util.spec_from_file_location("app_runtime_test", out / "app_runtime.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ui = json.loads((out / "ui.json").read_text(encoding="utf-8"))
    app = mod.App(ui)
    qtbot.addWidget(app)
    assert app.current.data["name"] == "Вход" and app.size().width() == 1280
    pwd = [e for e in app.current.findChildren(QLineEdit)]
    assert len(pwd) == 2 and pwd[1].echoMode() == QLineEdit.EchoMode.Password
    assert [b for b in app.current.findChildren(QAbstractButton) if b.isCheckable() and b.text() == "Запомнить меня"]
    next(b for b in app.current.findChildren(QPushButton) if b.text() == "Войти").click()
    assert app.current.data["name"] == "Настройки"
    app.back()
    assert app.current.data["name"] == "Вход"
    sys.modules.pop("app_runtime_test", None)


# ---------- среда выполнения на готовых данных ui.json ----------
def _runtime(tmp_path):
    (tmp_path / "app_runtime.py").write_text(windows_app.RUNTIME, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("app_runtime_data", tmp_path / "app_runtime.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _f(nid, x=0, y=0, w=100, h=40, **kw):
    return {"id": nid, "name": nid, "kind": "frame", "x": x, "y": y, "w": w, "h": h, "visible": True, "opacity": 1,
            "style": {"fill": "#FF0000", "stroke": "", "stroke_width": 0, "radius": 0}} | kw


def _ui(screens, interactions=(), variables=(), dark=False):
    return {"title": "T", "start": screens[0]["id"], "accent": "#0067C0", "dark": dark, "fonts": [],
            "screens": [{"w": 400, "h": 300, "bg": "#202020" if dark else "#F3F3F3", **s} for s in screens],
            "interactions": list(interactions), "variables": list(variables)}


def _tap(sid, nid, *actions, cond=None):
    return {"screen": sid, "node": nid, "trigger": "tap", "condition": cond, "actions": list(actions)}


def test_runtime_background_loop_and_groups(tmp_path, qtbot):
    m = _runtime(tmp_path)
    loop = [{"screen": "a", "node": "", "trigger": "screen_open", "condition": None,
             "actions": [{"type": "navigate", "screen_id": "b"}]},
            {"screen": "b", "node": "", "trigger": "screen_open", "condition": None,
             "actions": [{"type": "navigate", "screen_id": "a"}]}]
    group = {"id": "g", "name": "g", "kind": "group", "x": 0, "y": 0, "w": 0, "h": 0, "visible": False, "opacity": 1,
             "children": [_f("c1", id="c1"), _f("c2", y=50)]}
    app = m.App(_ui([{"id": "a", "name": "A", "nodes": [group, _f("a.b", x=200)]}, {"id": "b", "name": "B",
                                                                                    "nodes": []}],
                    loop, dark=True))                                       # круг «при открытии» не роняет приложение
    qtbot.addWidget(app)
    assert app.current is not None and app.depth == 0
    app = m.App(_ui([{"id": "a", "name": "A", "nodes": [group, _f("a.b", x=200)]}], dark=True))
    qtbot.addWidget(app)
    page = app.current
    assert page.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    img = page.grab().toImage()
    assert img.pixelColor(390, 290).name() == "#202020"                      # фон экрана из дизайна
    assert img.pixelColor(250, 20).name() == "#ff0000"                       # id с точкой — стиль применён
    assert all(not w.isVisible() for w in page.byid["g"]) and len(page.byid["g"]) == 2   # скрытая группа


def test_runtime_variables_overlays_and_native_taps(tmp_path, qtbot):
    m = _runtime(tmp_path)
    cb = {"id": "cb", "name": "cb", "kind": "checkbox", "x": 0, "y": 0, "w": 160, "h": 32, "visible": True,
          "opacity": 1, "texts": ["Запомнить"], "label": {}, "style": {}, "checked": False}
    txt = {"id": "t", "name": "t", "kind": "text", "x": 0, "y": 100, "w": 200, "h": 20, "visible": True,
           "opacity": 1, "style": {}, "text": "", "color": "#000000", "font": "", "size": 14, "weight": 400}
    sheet = _f("sheet", y=200, visible=False)
    var = [{"id": "n", "name": "счёт", "type": "number", "default": "1"},
           {"id": "f", "name": "флаг", "type": "bool", "default": False}]
    its = [_tap("s", "cb", {"type": "set_variable", "var_id": "n", "mode": "set", "value": "5"},
                {"type": "set_variable", "var_id": "n", "mode": "increment", "value": "2"}),
           _tap("s", "cb", {"type": "set_variable", "var_id": "f", "mode": "toggle"},
                {"type": "set_text", "node_id": "t", "text": "{счёт} / {флаг}"}),
           _tap("s", "cb", {"type": "open_overlay", "node_id": "sheet"}, cond={"var_id": "n", "op": ">", "value": "6"})]
    app = m.App(_ui([{"id": "s", "name": "S", "nodes": [cb, txt, sheet]}], its, var))
    qtbot.addWidget(app)
    app.show()
    box = app.current.byid["cb"][0]
    qtbot.mouseClick(box, Qt.MouseButton.LeftButton)
    assert box.isChecked()                                                  # флажок с правилом переключается
    assert app.vars["n"] == 7.0 and app.vars["f"] is True                   # все правила, значения — по типу
    assert app.current.texts["t"].text() == "7 / да"
    assert app.current.byid["sheet"][0].isVisible() and app.overlays == ["sheet"]
    app.system_back()                                                       # Esc сначала закрывает окно
    assert not app.current.byid["sheet"][0].isVisible() and app.current.data["id"] == "s"


def test_exported_state_from_design_and_skipped_triggers(win):
    ed = win.project_page.editor
    ed.add_template_screen("win_settings")
    ui = json.loads(windows_app.files(ed.doc, ed.doc.screens)["windows_app/ui.json"])
    toggles = []

    def walk(ns):
        for n in ns:
            if n["kind"] == "toggle":
                toggles.append(n["checked"])
            walk(n.get("children", []))
    for s in ui["screens"]:
        walk(s["nodes"])
    assert toggles == [True, True, False]                                   # переключатели карточек — как в дизайне
    assert windows_app.skipped_triggers(ed.doc, ed.doc.screens) == 0


def test_runtime_events_and_resizable_window(tmp_path, qtbot):
    """1.34: двойное нажатие, удержание, наведение и свайп мышью; окно растягивается по привязкам."""
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    m = _runtime(tmp_path)
    var = [{"id": "v", "name": "v", "type": "text", "default": ""}]

    def rule(trig, value):
        return {"screen": "a", "node": "box", "trigger": trig, "condition": None,
                "actions": [{"type": "set_variable", "var_id": "v", "mode": "set", "value": value}]}
    bar = _f("bar", 0, 0, 400, 40)                                          # во всю ширину — тянется
    side = _f("side", 340, 60, 60, 40)                                      # у правого края — остаётся у края
    row = _f("row", 0, 100, 400, 50, layout="horizontal", main="start", cross="center",
             children=[_f("fix", 0, 5, 100, 40, sh="fixed"), _f("grow", 100, 5, 300, 40, sh="fill")])
    box = _f("box", 10, 200, 100, 80)
    ui = _ui([{"id": "a", "name": "A", "nodes": [bar, side, row, box]}],
             [rule("double_tap", "2"), rule("hover_enter", "in"), rule("swipe_left", "sw")], var)
    windows_app.anchor(ui["screens"][0]["nodes"], 400, 300)                # привязки по месту в дизайне
    app = m.App(ui)
    qtbot.addWidget(app)
    app.show()
    w = app.current.byid["box"][0]
    QTest.mouseDClick(w, Qt.MouseButton.LeftButton)
    assert app.vars["v"] == "2"
    app.fire("a", "box", "hover_enter")
    assert app.vars["v"] == "in"
    QTest.mousePress(w, Qt.MouseButton.LeftButton, pos=QPoint(90, 40))
    QTest.mouseMove(w, QPoint(10, 40))
    QTest.mouseRelease(w, Qt.MouseButton.LeftButton, pos=QPoint(10, 40))
    assert app.vars["v"] == "sw"
    assert app.minimumSize().width() < 400                                  # окно не фиксированного размера
    app.resize(800, 300)
    qtbot.waitUntil(lambda: app.current.width() == 800)
    g = lambda nid: app.current.byid[nid][0].geometry()                     # noqa: E731
    assert g("bar").width() == 800 and g("side").x() == 740 and g("box").x() == 10
    assert g("fix").width() == 100 and g("grow").width() == 700


def test_link_windows_nav_pane_items(win):
    """1.34: пункт панели навигации Windows связывается с экраном одной кнопкой, как нижнее меню Android."""
    from app.engines.preview import live
    ed = win.project_page.editor
    blank = ed.screen().id
    settings, files = ed.add_template_screen("win_settings"), ed.add_template_screen("win_files")
    empty = ed.add_blank_screen()
    ed.remove_screen(blank)
    ed.set_screen(settings.id)
    pane = next(n for n in ed.screen().nodes if n.role == "win.navpane")
    sel = live.selected(pane)
    ed.select([pane.id])
    win.project_page.inspector.refresh()
    assert not win.project_page.inspector.sec_switch.isHidden()            # список «Пункт → экран» на виду
    assert ed.link_nav_item(pane.id, 0, empty.id) and ed.link_nav_item(pane.id, 1, files.id)
    other = next(n for n in ed.doc.screen(empty.id).nodes if n.role == "win.navpane")
    assert live.selected(other) == 0 and other.x == pane.x                  # своя панель, выбран свой пункт
    assert all(n.x >= other.x + other.w - 0.5 for n in ed.doc.screen(empty.id).nodes if n is not other)
    assert live.selected(next(n for n in ed.doc.screen(files.id).nodes if n.role == "win.navpane")) == 1
    assert ed.nav_targets(pane.id)[:2] == [empty.id, files.id]
    if sel > 1:
        assert ed.nav_targets(pane.id)[sel] == settings.id                  # выбранный пункт — этот же экран
    ed.undo()
    assert ed.nav_targets(pane.id)[1] != files.id


def _t(nid, x, y, w, h, text, **kw):
    return {"id": nid, "name": nid, "kind": "text", "x": x, "y": y, "w": w, "h": h, "visible": True, "opacity": 1,
            "style": {"fill": "", "stroke": "", "stroke_width": 0, "radius": 0}, "text": text, "color": "#000000",
            "font": "Segoe UI", "size": 14, "weight": 400, "align": "left", "wrap": True} | kw


@pytest.fixture
def plain_app():
    """Без общего стиля тем студии (его ставят другие тесты в том же процессе): в готовом приложении его нет,
    а шрифт надписи он подменяет."""
    qa = QApplication.instance()
    css = qa.styleSheet()
    qa.setStyleSheet("")
    yield
    qa.setStyleSheet(css)


def test_runtime_wrapped_text_grows_when_window_narrows(tmp_path, qtbot, plain_app):
    """1.36: в узком окне текст с переносом становится выше, а то, что под ним, сдвигается вниз;
    в прокрутке содержимое удлиняется; длинный текст из правила тоже раздвигает соседей."""
    m = _runtime(tmp_path)
    long = "Очень длинное описание параметра, которое в узком окне переносится на несколько строк " * 2
    free_t = _t("ft", 0, 10, 400, 40, long, ch="left_right")
    below = _f("below", 0, 60, 400, 30, ch="left_right")
    aside = _f("aside", 0, 0, 10, 5)                                        # выше текста — не двигается
    col = _f("col", 0, 100, 400, 200, layout="vertical", main="start", cross="stretch", scroll="vertical",
             content_w=400, content_h=200, ch="left_right",
             children=[_t("ct", 0, 0, 400, 40, long, sh="fill"), _f("after", 0, 40, 400, 30, sh="fill")])
    short = _t("st", 0, 0, 400, 20, "Коротко", ch="left_right")
    ui = _ui([{"id": "a", "name": "A", "nodes": [aside, free_t, below, col]},
              {"id": "b", "name": "B", "nodes": [short, _f("under", 0, 30, 400, 30, ch="left_right"),
                                                 _f("go", 300, 200, 80, 40)]}],
             [_tap("b", "go", {"type": "set_text", "node_id": "st", "text": long * 2})])
    app = m.App(ui)
    qtbot.addWidget(app)
    app.show()
    scr = app.current
    g = lambda nid: scr.byid[nid][0].geometry()                             # noqa: E731
    qtbot.waitUntil(lambda: scr.width() >= 400)
    wide_h, wide_below = g("ft").height(), g("below").y()
    app.resize(290, 300)
    qtbot.waitUntil(lambda: scr.width() <= 300)
    lab = scr.texts["ft"]
    assert g("ft").height() > wide_h and g("ft").height() >= lab.heightForWidth(g("ft").width())
    assert g("below").y() - wide_below == g("ft").height() - wide_h        # сдвинулось ровно на рост текста
    assert g("aside").y() == 0
    ct = scr.texts["ct"]
    grown = ct.heightForWidth(g("ct").width()) - max(40, ct.heightForWidth(400))
    assert grown > 0 and abs(g("after").y() - (40 + grown)) <= 1          # в столбце — ниже на рост текста
    assert scr.inner["col"].height() > 200                                  # прокрутка стала длиннее
    app.resize(400, 300)
    qtbot.waitUntil(lambda: scr.width() >= 400)
    assert g("ft").height() == wide_h                                       # шире — снова как в дизайне
    assert g("below").y() == wide_below == 60                               # при ширине дизайна ничего не сдвинулось
    app.go("b")
    b = app.current
    gb = lambda nid: b.byid[nid][0].geometry()                              # noqa: E731
    top = gb("under").y()
    app.tap("b", "go")
    assert gb("st").height() > 20 and gb("under").y() > top                 # длинный текст из правила раздвинул


def test_runtime_card_grows_with_text_and_window_gets_taller(tmp_path, qtbot, plain_app):
    """1.36 (замечания тестировщика): карточка растёт вместе с текстом и сдвигает следующую; если
    содержимое ушло за низ окна, окно становится выше."""
    m = _runtime(tmp_path)
    long = "Описание параметра, которое в узком окне переносится на несколько строк подряд " * 3
    card = _f("card", 0, 10, 400, 60, ch="left_right", children=[
        _t("title", 10, 10, 380, 20, "Заголовок", ch="left_right"),
        _t("desc", 10, 34, 380, 20, long[:40], ch="left_right")])
    nxt = _f("next", 0, 80, 400, 40, ch="left_right")
    btn = _f("btn", 0, 250, 100, 40)
    ui = _ui([{"id": "a", "name": "A", "nodes": [card, nxt, btn]}],
             [_tap("a", "next", {"type": "set_text", "node_id": "desc", "text": long})])
    app = m.App(ui)
    qtbot.addWidget(app)
    app.show()
    scr = app.current
    g = lambda nid: scr.byid[nid][0].geometry()                             # noqa: E731
    qtbot.waitUntil(lambda: scr.width() >= 400)
    assert g("card").height() == 60 and g("next").y() == 80
    app.tap("a", "next")
    lab = scr.texts["desc"]
    grown = lab.heightForWidth(g("desc").width()) - max(20, scr.design_h["desc"])
    assert grown > 20
    assert g("card").height() == 60 + grown                                 # карточка выше на рост текста
    assert g("next").y() >= 80 + grown - 1                                  # следующая карточка ниже
    assert g("btn").y() > 250
    qtbot.waitUntil(lambda: scr.height() >= g("btn").y() + g("btn").height())  # окно стало выше — кнопка видна


def test_runtime_tight_window_layout_and_fluent_inputs(tmp_path, qtbot, plain_app):
    """Тесное окно: в ряду поиск сужается, а не наезжает на кнопки; окно по центру не заезжает на заголовок;
    короткая строка уменьшает шрифт, длинная без переноса — с многоточием; поля и поиск — вид Windows 11."""
    from PySide6.QtWidgets import QLineEdit
    m = _runtime(tmp_path)

    def w(kind, nid, x, y, ww, h, texts, **kw):
        return {"id": nid, "name": nid, "kind": kind, "x": x, "y": y, "w": ww, "h": h, "visible": True,
                "opacity": 1, "texts": texts, "label": {}, "style": {"fill": "", "stroke": "", "stroke_width": 0,
                                                                     "radius": 4}} | kw
    row = _f("row", 0, 40, 400, 40, layout="horizontal", main="start", cross="center", ch="left_right", pad_r=0,
             children=[_f("cmds", 0, 0, 200, 40, sh="fixed"), _f("gap", 200, 0, 60, 10, sh="fill"),
                       w("search", "find", 260, 4, 140, 32, ["Поиск"], sh="fixed")])
    bar = _f("bar", 0, 0, 400, 32, ch="left_right", bar=True)
    card = _f("card", 100, 120, 200, 150, ch="center", cv="center")
    tile = _f("tile", 0, 90, 0, 26, layout="vertical", main="start", cross="start", ch="scale", pad_r=8,
              children=[_t("big", 8, 0, 0, 26, "48 Мбит/с", size=22, wrap=False)])
    long = _t("long", 0, 280, 100, 20, "Очень длинная подпись без переноса строки в узком месте", wrap=False)
    from PySide6.QtGui import QFont, QFontMetrics
    f = QFont("Segoe UI")
    f.setPixelSize(22)
    need = QFontMetrics(f).horizontalAdvance("48 Мбит/с") + 2           # во всю ширину — при ширине дизайна
    tile["w"], tile["children"][0]["w"] = need + 16, need
    ui = _ui([{"id": "a", "name": "A", "nodes": [bar, row, tile, long, card]}])
    app = m.App(ui)
    qtbot.addWidget(app)
    app.show()
    scr = app.current
    g = lambda nid: scr.byid[nid][0].geometry()                             # noqa: E731
    qtbot.waitUntil(lambda: scr.width() >= 400)
    assert scr.texts["long"].text().endswith("…") and scr.texts["long"].toolTip().startswith("Очень")
    app.resize(290, 210)
    qtbot.waitUntil(lambda: scr.width() <= 300)
    assert g("find").x() >= g("cmds").x() + g("cmds").width()              # поиск не наезжает на кнопки
    assert g("find").x() + g("find").width() <= scr.width() + 1
    assert g("card").y() >= 32                                              # окно по центру — под заголовком
    big = scr.texts["big"]
    assert big.font().pixelSize() < 22                                      # шрифт меньше, а не обрезка
    find = scr.byid["find"][0]
    assert isinstance(find, QLineEdit) and find.actions() and "border-bottom" in find.styleSheet()
