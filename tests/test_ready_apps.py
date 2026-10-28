"""1.28: новые готовые экраны и готовые приложения — наборы связанных экранов."""

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.engines.preview import live
from app.libraries.screen_templates import GROUPS, all_templates, grouped_templates
from app.libraries.screen_templates_apps import APPS, find_target
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
    _, path = ctx.service.create(make_spec(projects_dir, title="Приложения"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_groups_cover_all_templates():
    keys = {k for ks in GROUPS.values() for k in ks}
    assert keys == set(all_templates()) and len(keys) == 49
    assert [g for g, _ in grouped_templates()] == list(GROUPS)       # «Другие» не нужны — все в группах


@pytest.mark.parametrize("key", list(APPS))
def test_ready_app_links_screens(win, key):
    ed = win.project_page.editor
    before = len(ed.doc.screens)
    first = ed.add_ready_app(key)
    title, keys, _kind, nav_targets, taps = APPS[key]
    assert first is not None and len(ed.doc.screens) == before + len(keys)
    screens = ed.doc.screens[before:]
    ids = [s.id for s in screens]
    rules = [it for it in ed.doc.interactions if it.screen_id in ids]
    # каждый переход по кнопке настроен
    for si, what, ti in taps:
        n = find_target(screens[si], what)
        assert n is not None, (key, what)
        assert any(it.node_id == n.id and it.actions[0].get("screen_id") == ids[ti] for it in rules), (key, what)
    # нижнее меню: на экране из меню выбран свой пункт, пункты ведут на свои экраны
    for i, s in enumerate(screens):
        bar = next((n for n in s.nodes if n.role == "m3.nav_bar"), None)
        if bar is None or i not in nav_targets:
            continue
        assert live.selected(bar) == nav_targets.index(i), (key, s.name)
        for it, t in zip(live._items(bar), nav_targets):
            if t is not None and t != i:
                assert any(r.node_id == it.id and r.actions[0]["screen_id"] == ids[t] for r in rules)
    # «Назад» в шапке — назад
    assert any(r.actions[0]["type"] == "back" for r in rules) or key == "fitness"
    # прототип: первый переход работает
    from app.ui.studio.prototype import PrototypePlayer
    si, what, ti = taps[0]
    p = PrototypePlayer(ed, start_screen_id=ids[si])
    p.dispatch("tap", find_target(screens[si], what).id)
    assert p.interp.state.screen_id == ids[ti]
    # одна запись истории
    ed.undo()
    assert len(ed.doc.screens) == before


def test_new_screens_have_no_layout_warnings(win):
    ed = win.project_page.editor
    from app.libraries.screen_templates_apps import TEMPLATES
    for key in TEMPLATES:
        ed.set_screen(ed.doc.screens[0].id)
        s = ed.add_template_screen(key)
        assert s is not None and s.nodes
        assert not [d for d in ed.diagnostics if d.severity == "warning"], (key, [d.message for d in ed.diagnostics])
    names = {n.name for s in ed.doc.screens for n, _, _ in tree.walk(s.nodes)}
    assert "Ресторан «Додо Пицца»" in names and "Карта «Дебетовая»" in names


def test_food_app_texts_match_theme(win):
    ed = win.project_page.editor
    ed.add_ready_app("food")
    cart = next(s for s in ed.doc.screens if s.name == "Корзина")
    texts = {d.text for d, _, _ in tree.walk(cart.nodes) if d.type == "text"}
    assert "Маргарита" in texts and "Наушники" not in texts and "1 470 ₽" in texts
