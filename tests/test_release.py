"""Этап 8: самопроверка сборки, интерактивный просмотр компонента, экспорт компонента, настройки экспорта."""

import json

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app import smoke
from app.context import AppContext
from app.core.document import tree
from app.ui.shell.main_window import PAGE_EXPORT, PAGE_SETTINGS, MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec


def test_smoke_self_check_passes(tmp_path):  # S23/S24: тот же сценарий запускается в собранной программе
    report = tmp_path / "отчёт.json"
    assert smoke.run(str(report)) == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["ok"] and [s["step"] for s in data["steps"]] == [
        "Запуск окна", "Создание проекта", "Сохранение и открытие", "Проверка проекта",
        "Интерактивный предпросмотр", "AI-экспорт", "Значки"]


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
    _, path = ctx.service.create(make_spec(projects_dir, title="Выпуск"))
    w.open_project(str(path))
    yield w, w.project_page.editor, ctx
    ctx.close()


def test_builder_live_preview_and_export_with_task(qtbot, app_win):
    win, ed, _ = app_win
    btn = ed.insert_component("m3_button_filled")
    ed.select([btn.id])
    cid = ed.create_component("Кнопка с наведением")
    defn = ed.doc.component(cid)
    defn.states = {"hover": {"__root__": {"opacity": 0.6}}}
    defn.behavior = {"hover": True, "press": False, "toggle": []}
    ed.update_component(defn)
    ed.add_screen(type(ed.screen())(name="Пустой", platform="android", width=1080, height=2400,
                                    device_id="android_phone"))
    win.open_in_builder(cid)
    b = win.builder
    b.set_mode(1)
    p = b.live_player
    assert p is not None and b.center_stack.currentWidget() is b.live
    p.stop_clock()
    inst = next(n for n in p.screen.nodes if n.is_instance)
    p.hover(QPointF(inst.x + inst.w / 2, inst.y + inst.h / 2))
    assert p.interp.state.states[inst.id] == "hover"
    p.advance(1000)
    assert tree.node_map(p.screen)[inst.id].opacity == pytest.approx(0.6)
    b.set_mode(0)
    assert b.center_stack.currentWidget() is b.canvas
    # экспорт с ИИ-заданием: выбираются только экраны, где есть компонент
    b.export_with_task()
    assert win.pages.currentIndex() == PAGE_EXPORT
    page = win.export_page
    checked = [page.screens.item(i).data(Qt.ItemDataRole.UserRole) for i in range(page.screens.count())
               if page.screens.item(i).checkState() == Qt.CheckState.Checked]
    assert checked == [ed.doc.screens[0].id]
    assert "components/" in "".join(page.package.files)


def test_settings_export_defaults(qtbot, app_win, tmp_path):
    win, ed, ctx = app_win
    win.show_page(PAGE_SETTINGS)
    sp = win.settings_page
    sp.export_dir.setText(str(tmp_path / "Пакеты"))
    sp.export_dir.editingFinished.emit()
    sp.export_previews.setChecked(False)
    assert ctx.settings.get("export/folder") == str(tmp_path / "Пакеты")
    assert ctx.settings.get("export/include_previews") is False
    win.export_page.folder.clear()
    win.show_page(PAGE_EXPORT)
    assert win.export_page.folder.text() == str(tmp_path / "Пакеты")
    assert not win.export_page.inc["include_previews"].isChecked()


def test_ui_scale_setting_and_scrollable_nav(qtbot, app_win, monkeypatch):
    win, ed, ctx = app_win
    monkeypatch.delenv("QT_SCALE_FACTOR", raising=False)
    win.show_page(PAGE_SETTINGS)
    sp = win.settings_page
    sp.ui_scale.setCurrentIndex(sp.ui_scale.findData(150))
    assert ctx.settings.get("general/ui_scale") == 150
    assert sp.b_restart.isVisibleTo(sp) and "перезапуска" in sp.scale_note.text()
    from app.__main__ import _apply_ui_scale
    _apply_ui_scale(ctx.paths)
    import os
    assert os.environ.pop("QT_SCALE_FACTOR") == "1.5"
    from PySide6.QtWidgets import QScrollArea
    nav = win.nav_hub.parentWidget()
    while nav is not None and not isinstance(nav, QScrollArea):
        nav = nav.parentWidget()
    assert nav is not None  # в невысоком окне разделы прокручиваются
