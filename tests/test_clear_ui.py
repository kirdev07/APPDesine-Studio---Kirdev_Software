"""1.5: понятный интерфейс — шаги в меню, «При нажатии», готовые экраны, размеры в dp, «?», обучение."""

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QToolButton

from app.context import AppContext
from app.core.document import tree
from app.libraries.screen_templates import TEMPLATES
from app.ui.shell.main_window import PAGE_ANIMATIONS, PAGE_EXPORT, PAGE_LOGIC, PAGE_PREVIEW, MainWindow
from app.ui.shell.tour import STEPS, TourDialog
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
    w.resize(1280, 720)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Понятно"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_navigation_has_three_steps_and_more(qtbot, win):
    assert win.nav_project.text() == "1 · Рисую"
    assert win.nav_studios[PAGE_PREVIEW].text() == "2 · Проверяю" and win.nav_studios[PAGE_EXPORT].text() == "3 · Выгружаю"
    assert not win.more_box.isVisible() and not win.nav_studios[PAGE_ANIMATIONS].isVisible()
    win.show_page(PAGE_ANIMATIONS)                                   # открытый раздел из «Ещё» виден в меню
    assert win.nav_more.isChecked() and win.nav_studios[PAGE_ANIMATIONS].isVisible()
    win.nav_more.setChecked(False)
    assert not win.more_box.isVisible()


def test_tap_action_from_selection_bar(qtbot, win):
    page, ed = win.project_page, win.project_page.editor
    btn = ed.insert_component("m3_button_filled")
    second = ed.add_blank_screen()
    ed.set_screen(ed.doc.screens[0].id)
    ed.select([btn.id])
    assert page.tap_button.isVisible() and page.tap_button.text() == "При нажатии… ▾"
    page._fill_tap_menu()
    go = next(a for a in page.tap_menu.actions() if a.text() == "Открыть экран").menu()
    next(a for a in go.actions() if a.text() == second.name).trigger()
    assert ed.tap_action(btn.id)["screen_id"] == second.id and "«Экран 2»" in page.tap_button.text()
    rules = ed.tap_rules(btn.id)
    assert len(rules) == 1 and rules[0].actions[0]["transition"] == "slide_left"
    ed.set_tap_action(btn.id, {"type": "back"})
    assert len(ed.tap_rules(btn.id)) == 1 and page.tap_button.text() == "При нажатии ← назад ▾"
    ed.set_tap_action(btn.id, None)
    assert ed.tap_rules(btn.id) == [] and page.tap_button.text() == "При нажатии… ▾"
    # сложное правило из «Логики» простыми кнопками не перезаписывается
    from app.core.document.behavior import Interaction
    ed.patch("rule", lambda doc: doc.interactions.append(Interaction(
        screen_id=doc.screens[0].id, node_id=btn.id, trigger="tap",
        actions=[{"type": "back", "transition": "none", "duration": 0, "easing": "linear"},
                 {"type": "back", "transition": "none", "duration": 0, "easing": "linear"}])))
    assert ed.tap_action(btn.id) == "custom" and not ed.set_tap_action(btn.id, None)
    page._fill_tap_menu()
    page.tap_menu.actions()[0].trigger()
    assert win.pages.currentIndex() == PAGE_LOGIC


def test_ready_screens_and_add_menu(qtbot, win):
    ed = win.project_page.editor
    strip = win.project_page.screens
    strip._fill_add_menu()
    titles = [a.text() for a in strip.add_menu.actions()]
    assert "Пустой экран" in titles and all(t in titles for t, _ in TEMPLATES.values())
    for key in TEMPLATES:
        ed.set_screen(ed.doc.screens[0].id)
        s = ed.add_template_screen(key)
        assert s is not None and ed.screen().id == s.id and s.nodes
        assert not [d for d in ed.diagnostics if d.severity == "warning"], key
    roles = {n.role for s in ed.doc.screens for n, _, _ in tree.walk(s.nodes)}
    assert {"m3.switch", "m3.text_field", "m3.button_filled", "m3.nav_bar", "m3.top_app_bar", "m3.fab"} <= roles
    ed.undo()
    assert len(ed.doc.screens) == 1 + len(TEMPLATES) - 1                 # готовый экран — одна запись истории


def test_dp_hint_help_buttons_and_tour(qtbot, win):
    page, ed = win.project_page, win.project_page.editor
    btn = ed.insert_component("m3_button_filled")
    ed.select([btn.id])
    insp = page.inspector
    assert insp.dp_hint.isVisible() and "dp" in insp.dp_hint.text()
    k = ed.screen().width / 411
    assert f"{btn.h / k:.0f} dp" in insp.dp_hint.text().replace(" × ", " ").split(",")[0] or "40 dp" in insp.dp_hint.text()
    helps = [b for b in insp.findChildren(QToolButton) if b.objectName() == "HelpButton"]
    assert len(helps) >= 4 and all(len(b.toolTip()) > 40 for b in helps)
    ed.select([])
    assert "dp" in insp.s_info.text()
    t = TourDialog()
    assert t.counter.text() == f"Шаг 1 из {len(STEPS)}" and not t.back.isEnabled()
    for _ in range(len(STEPS) - 1):
        t.next.click()
    assert t.next.text() == "Начать работу" and not t.skip.isVisible()
    t.next.click()
    assert t.result() == 1
    t.deleteLater()
