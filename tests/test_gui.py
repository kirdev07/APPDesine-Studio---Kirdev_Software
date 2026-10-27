"""GUI-тесты (pytest-qt): запуск, мастер, Hub, сохранение и восстановление."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.ui.dialogs.new_project_wizard import NewProjectWizard
from app.ui.shell.main_window import PAGE_HUB, PAGE_PROJECT, MainWindow
from app.ui.themes.fusion_amoled import apply_theme


@pytest.fixture
def ctx(paths, projects_dir):
    c = AppContext.create(paths)
    c.settings.set("general/projects_dir", str(projects_dir))
    yield c
    c.close()


@pytest.fixture
def win(qtbot, ctx):
    apply_theme(QApplication.instance())
    w = MainWindow(ctx)

    def discard(win):  # pytest-qt закрывает окно до завершения фикстуры
        win.project_page.mark_clean()
        win.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.show()
    yield w


def _run_wizard(wiz: NewProjectWizard, name: str, platform_idx: int = 0):
    wiz.platform_group.button(platform_idx).click()
    for _ in range(5):
        wiz._next()
    wiz.name_edit.setText(name)
    wiz._next()


def test_app_launches_with_hub(win):
    assert win.pages.currentIndex() == PAGE_HUB
    assert not win.act_save.isEnabled()
    assert not win.nav_project.isEnabled()


@pytest.mark.parametrize("idx,platforms,screens", [(0, ["android"], 1), (1, ["windows"], 1),
                                                    (2, ["android", "windows"], 2)])
def test_wizard_produces_spec(qtbot, projects_dir, idx, platforms, screens):
    wiz = NewProjectWizard(projects_dir)
    qtbot.addWidget(wiz)
    _run_wizard(wiz, "Проект мастера", idx)
    assert wiz.result_spec is not None
    assert wiz.result_spec.platforms == platforms
    assert len(wiz.result_spec.devices) == screens


def test_wizard_rejects_bad_name(qtbot, projects_dir):
    wiz = NewProjectWizard(projects_dir)
    qtbot.addWidget(wiz)
    _run_wizard(wiz, "плохое:имя")
    assert wiz.result_spec is None and wiz.error.text()


def test_wizard_template_preselects_platform(qtbot, projects_dir):
    wiz = NewProjectWizard(projects_dir, "blank_windows")
    qtbot.addWidget(wiz)
    assert wiz._platforms == ("windows",)
    assert wiz._selected_devices() == ["windows_window"]


def test_create_edit_save_reopen_via_ui(win, ctx, projects_dir, monkeypatch):  # S01 + S04 + S07
    def fake_exec(self):
        _run_wizard(self, "Ёжик в тумане")
        return NewProjectWizard.DialogCode.Accepted
    monkeypatch.setattr(NewProjectWizard, "exec", fake_exec)
    win.new_project("")
    assert win.pages.currentIndex() == PAGE_PROJECT
    path = projects_dir / "Ёжик в тумане.adsproj"
    assert path.exists() and win.doc_path == path

    win.project_page.editor.set_meta({"description": "Описание с кириллицей"})
    assert win.dirty and "●" in win.windowTitle()
    assert win.save_project()
    assert not win.dirty

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    assert win.close_project()
    win.open_project(str(path))
    assert win.doc.meta.description == "Описание с кириллицей"


def test_hub_lists_and_filters(win, ctx, projects_dir):
    from tests.conftest import make_spec
    a, _ = ctx.service.create(make_spec(projects_dir, title="Альфа"))
    ctx.service.create(make_spec(projects_dir, title="Бета"))
    win.hub.refresh()
    ids = [win.hub.cards.item(i).data(256) for i in range(win.hub.cards.count())]
    assert a.meta.id in ids and "__new__" in ids
    win.hub.search.setText("альф")
    assert [win.hub.cards.item(i).data(256) for i in range(win.hub.cards.count())] == [a.meta.id]
    win.hub.search.clear()
    win.hub.select_project(a.meta.id)
    win.hub._toggle_favorite()
    assert ctx.index.get(a.meta.id).favorite
    assert "Избранные   ·   1" in win.hub.filter_list.item(2).text()
    win.hub.set_view_mode("list")
    assert ctx.settings.get("hub/view_mode") == "list"


def test_open_corrupted_shows_error_not_crash(win, ctx, projects_dir, monkeypatch):  # S05
    bad = projects_dir / "сломанный.adsproj"
    bad.write_bytes(b"PK\x03\x04 broken")
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    win.open_project(str(bad))
    assert win.doc is None and shown and "повреждён" in shown[0]


def test_autosave_and_recovery(qtbot, win, ctx, projects_dir, monkeypatch):  # S22
    from tests.conftest import make_spec
    doc, path = ctx.service.create(make_spec(projects_dir, title="Авария"))
    win.open_project(str(path))
    win.project_page.editor.set_meta({"description": "несохранённый текст"})
    win.autosave()
    assert len(ctx.recovery.entries()) == 1
    # имитация сбоя: новое окно, исходный файл не изменён
    win.dirty = False
    win2 = MainWindow(ctx)
    qtbot.addWidget(win2)

    def pick_restore(box):
        for b in box.buttons():
            if b.text() == "Восстановить":
                box.clickedButton = lambda b=b: b
        return 0
    monkeypatch.setattr(QMessageBox, "exec", pick_restore)
    win2.check_recovery()
    assert win2.doc.meta.description == "несохранённый текст" and win2.dirty
    assert win2.save_project()
    assert ctx.service.open(path).meta.description == "несохранённый текст"
    assert ctx.recovery.entries() == []


def test_future_sections_are_disabled_and_labelled(win):
    from PySide6.QtWidgets import QToolButton
    future = [b for b in win.findChildren(QToolButton) if b.objectName() == "NavButton" and not b.isEnabled()
              and "этапе" in b.toolTip()]
    assert len(future) == 6  # после этапа 4 остаются разделы этапов 5–7
