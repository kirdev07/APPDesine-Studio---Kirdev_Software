"""1.31: Windows 11 (Fluent 2) — компоненты с ролями и готовые экраны Windows."""

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import Appearance, Screen
from app.engines.layout import LayoutEngine
from app.libraries import components
from app.libraries.components_win import SPECS as WIN
from app.libraries.screen_templates_win import TEMPLATES
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from app.ui.workspace.text_measure import QtTextMeasurer
from tests.conftest import make_spec

LIKE = Screen(name="w", platform="windows", width=1280, height=800, device_id="windows_window")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_fluent_components_build_with_roles(qapp, theme):
    ap = Appearance(theme=theme, accent="#0067C0")
    kinds = [s.kind for s in components.specs_for("windows")]
    assert len(kinds) >= 22 and all(s.kind in kinds for s in WIN)
    eng = LayoutEngine(QtTextMeasurer())
    for kind in kinds:
        n = components.build(kind, LIKE, ap)
        assert n.role.startswith("win."), kind
        s = Screen(name="x", platform="windows", width=1280, height=800, device_id="windows_window", nodes=[n])
        _, diags = eng.layout_screen(s)
        assert not [d for d in diags if d.severity == "warning"], (kind, [d.message for d in diags])


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
    _, path = ctx.service.create(make_spec(projects_dir, title="Окна", platforms=["android", "windows"],
                                           devices=["android_phone", "windows_window"]))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_windows_ready_screens(win):
    page, ed = win.project_page, win.project_page.editor
    wscreen = next(s for s in ed.doc.screens if s.platform == "windows")
    ed.set_screen(wscreen.id)
    page.screens._fill_add_menu()
    titles = [a.text() for a in page.screens.add_menu.actions()]
    assert "Настройки" in titles and "Вход" in titles
    for key in TEMPLATES:
        ed.set_screen(wscreen.id)
        s = ed.add_template_screen(key)
        assert s is not None and s.platform == "windows" and s.width == wscreen.width, key
        assert not [d for d in ed.diagnostics if d.severity == "warning"], (key, [d.message for d in ed.diagnostics])
    roles = {n.role for s in ed.doc.screens for n, _, _ in tree.walk(s.nodes) if n.role.startswith("win.")}
    assert {"win.titlebar", "win.navpane", "win.settings_card", "win.list", "win.textbox"} <= roles
    ed.set_screen(next(s for s in ed.doc.screens if s.platform == "android").id)
    assert ed.add_template_screen("win_settings") is None                  # не для экрана Android



def test_theme_change_recolors_windows_screens():
    """1.33: светлая тема для готовых экранов Windows — карточки и фон окна по палитре Fluent, текст читается."""
    from dataclasses import replace

    from app.core.document import tree
    from app.core.project.service import build_document
    from app.engines.material.restyle import restyle
    from app.libraries import screen_templates_win
    from app.libraries.components import _palette
    from tests.conftest import make_spec

    def fills(nodes):
        return {n.fill.upper() for n, _, _ in tree.walk(nodes) if n.fill and n.type != "vector"}

    doc = build_document(make_spec(".", title="Окно", platforms=["windows"], devices=["windows_window"]))
    ap = replace(doc.meta.appearance, theme="amoled")
    doc.meta.appearance = ap
    light = replace(ap, theme="light")
    doc.screens = [screen_templates_win.build("win_dashboard", doc.screens[0], ap)]
    fresh = screen_templates_win.build("win_dashboard", doc.screens[0], light)
    restyle(doc, light)
    dark = {v.upper() for k, v in _palette("amoled").items() if k.startswith("win_")}
    assert not (fills(doc.screens[0].nodes) & dark)                          # тёмных подложек не осталось
    assert fills(doc.screens[0].nodes) <= fills(fresh.nodes)                  # как у экрана, созданного в светлой
