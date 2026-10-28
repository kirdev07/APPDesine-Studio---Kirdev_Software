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
