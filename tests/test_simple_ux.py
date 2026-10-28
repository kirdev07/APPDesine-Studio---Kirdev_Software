"""1.4: простой интерфейс — галерея с картинками, вставка в точку, замена, панель выделения, простой режим."""

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QByteArray
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from app.ui.workspace.gallery import MIME, PickComponentDialog, THUMB
from tests.conftest import make_spec


@pytest.fixture
def ws(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)

    def discard(win):
        win.project_page.mark_clean()
        win.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.resize(1280, 720)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Просто"))
    w.open_project(str(path))
    yield w, w.project_page, w.project_page.editor
    ctx.close()


def test_gallery_has_pictures_categories_and_search(qtbot, ws):
    win, page, ed = ws
    g = page.layers.gallery
    assert g.tiles.count() >= 50
    icon = g.tiles.item(0).icon().pixmap(THUMB)
    img = icon.toImage()
    colors = {img.pixelColor(x, y).name() for x in range(0, img.width(), 6) for y in range(0, img.height(), 6)}
    assert len(colors) > 3                                           # настоящая картинка, а не пустая плитка
    g.category.setCurrentText("Выбор")
    assert set(g.visible_names()) >= {"Переключатель", "Флажок", "Ползунок"} and "Кнопка" not in g.visible_names()
    g.category.setCurrentText("Все")
    g.search.setText("fab")
    assert g.visible_names() == ["Плавающая кнопка (FAB)"]
    g.search.setText("плавающая")
    assert len(g.visible_names()) >= 2 and all("Плавающая" in n for n in g.visible_names())
    g.search.clear()
    assert all("\n" not in n for n in g.visible_names())
    assert any("\n" in g.tiles.item(i).text() for i in range(g.tiles.count()))  # длинные подписи — в 2 строки


def test_click_drop_replace_and_selection_bar(qtbot, ws, monkeypatch):
    win, page, ed = ws
    g = page.layers.gallery
    assert page.start_hint.isVisible()                                # пустой экран — подсказка «с чего начать»
    btn = next(g.tiles.item(i) for i in range(g.tiles.count()) if g.tiles.item(i).data(Qt.ItemDataRole.UserRole)
               == "m3_button_filled")
    g.tiles.itemClicked.emit(btn)
    assert len(ed.screen().nodes) == 1 and not page.start_hint.isVisible()
    assert page.sel_bar.isVisible() and "Кнопка" in page.sel_label.text()
    # перетаскивание: компонент встаёт в точку отпускания
    v = page.canvas
    md = QMimeData()
    md.setData(MIME, QByteArray(b"m3_fab"))
    target = QPointF(300, 900)
    pos = v.mapFromScene(target)
    ev = QDropEvent(QPointF(pos), Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    v.dropEvent(ev)
    fab = ed.screen().nodes[-1]
    assert fab.role == "m3.fab" and abs(fab.x - 300) < 3 and abs(fab.y - 900) < 3
    # замена: на то же место, одной записью истории
    ed.select([fab.id])
    n_hist = len(ed.stack)
    new = ed.replace_selection("m3_icon_button")
    assert new.role == "m3.icon_button" and abs(new.x - fab.x) < 0.01 and abs(new.y - fab.y) < 0.01
    assert len(ed.screen().nodes) == 2 and fab.id not in tree.node_map(ed.screen()) and ed.selection == [new.id]
    assert len(ed.stack) == n_hist + 1
    ed.undo()
    assert tree.node_map(ed.screen())[fab.id].role == "m3.fab"
    # «Заменить…» с панели выделения открывает выбор по картинкам
    ed.select([fab.id])
    monkeypatch.setattr(PickComponentDialog, "exec", lambda self: (self._choose("m3_switch"),
                                                                   QDialog.DialogCode.Accepted)[1])
    page.a_replace.trigger()
    assert ed.screen().nodes[-1].role == "m3.switch"
    page.a_delete.trigger()
    assert len(ed.screen().nodes) == 1 and not page.sel_bar.isVisible()


def test_simple_mode_hides_advanced_and_persists(qtbot, ws):
    win, page, ed = ws
    assert page.simple and page.a_simple.isChecked()
    bar_actions = page.toolbar.actions()
    assert page.a_group not in bar_actions and page.a_guides not in bar_actions and page.a_grid in bar_actions
    card = ed.insert_component("m3_card")
    ed.select([card.children[0].id])
    assert not page.inspector.sec_cons.isVisible() and not page.inspector.sec_size.isVisible()
    page.a_simple.trigger()                                           # выключить
    assert not page.simple and page.a_group in page.toolbar.actions()
    assert page.inspector.sec_size.isVisible()
    assert win.ctx.settings.get("workspace/simple") is False
    page.a_simple.trigger()
    assert win.ctx.settings.get("workspace/simple") is True


def test_canvas_resizes_screen_to_window_until_manual_zoom(qtbot, ws):
    win, page, ed = ws
    v = page.canvas
    z_small = v.zoom()
    win.resize(1900, 1040)
    qtbot.wait(50)
    QApplication.processEvents()
    assert v.zoom() > z_small                                         # окно больше — экран крупнее
    v.set_zoom(0.5)
    win.resize(1500, 900)
    QApplication.processEvents()
    assert v.zoom() == pytest.approx(0.5)                             # ручной масштаб не сбрасывается
