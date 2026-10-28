"""1.23: свои горячие клавиши — переназначение, занятые сочетания, сброс, сохранение между запусками."""

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.ui.shell import shortcuts as sc
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme


@pytest.fixture
def ctx(paths, projects_dir):
    apply_theme(QApplication.instance())
    c = AppContext.create(paths)
    c.settings.set("general/projects_dir", str(projects_dir))
    yield c
    c.close()


def _win(qtbot, ctx):
    w = MainWindow(ctx)
    qtbot.addWidget(w)
    return w


def _keys(w, name):
    return sc.current(sc.commands(w)[name])


def test_reassign_conflict_reset_and_persist(qtbot, ctx):
    w = _win(qtbot, ctx)
    assert _keys(w, "Копировать стиль") == ["Ctrl+Alt+C"]
    assert w.set_shortcut("Копировать стиль", "Ctrl+Shift+K")
    assert _keys(w, "Копировать стиль") == ["Ctrl+Shift+K"]
    # занято «Вставить стиль»: без согласия не отбирается, с согласием — у той команды клавиши нет
    assert not w.set_shortcut("Копировать стиль", "Ctrl+Alt+V", take=False)
    assert w.set_shortcut("Копировать стиль", "Ctrl+Alt+V")
    assert _keys(w, "Вставить стиль") == [] and _keys(w, "Копировать стиль") == ["Ctrl+Alt+V"]
    assert sc.owner(w, "Ctrl+Alt+V") == "Копировать стиль"
    # новый запуск — свои клавиши на месте
    w2 = _win(qtbot, ctx)
    assert _keys(w2, "Копировать стиль") == ["Ctrl+Alt+V"] and _keys(w2, "Вставить стиль") == []
    w2.reset_shortcuts()
    assert _keys(w2, "Копировать стиль") == ["Ctrl+Alt+C"] and _keys(w2, "Вставить стиль") == ["Ctrl+Alt+V"]
    assert sc.load(ctx.settings) == {}
    # вернул стандартное сочетание вручную — в настройках не хранится
    assert w2.set_shortcut("Копировать стиль", "Ctrl+Alt+C") and sc.load(ctx.settings) == {}
    assert w2.set_shortcut("Копировать стиль", "") and _keys(w2, "Копировать стиль") == []


def test_dialog_edit_and_table(qtbot, ctx, monkeypatch):
    w = _win(qtbot, ctx)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)

    def press():
        d, edit = w._key_dialog
        edit.setKeySequence(QKeySequence("Ctrl+Alt+V"))   # занято «Вставить стиль» — спросит и отдаст
        d.accept()
    QTimer.singleShot(0, press)
    assert w.edit_shortcut("Копировать стиль")
    assert _keys(w, "Копировать стиль") == ["Ctrl+Alt+V"] and _keys(w, "Вставить стиль") == []
    w.show_shortcuts()
    t = w._shortcuts_table
    rows = {t.item(i, 1).text(): t.item(i, 0) for i in range(t.rowCount())}
    assert rows["Копировать стиль"].font().bold() and rows["Вставить стиль"].text() == "—"
    assert rows["Двигать холст"].data(256) is None                     # встроенные — не меняются
    assert "Прототип в браузере (HTML)" in rows                         # команды без клавиш тоже можно назначить
    assert t.currentRow() >= 0                                          # строка выбрана — «Изменить…» работает
    w._shortcuts_dialog.close()


def test_same_command_in_two_menus(qtbot, ctx):
    """«Проверка проекта» есть в двух меню: одна строка; своё сочетание — одному действию (иначе неоднозначно)."""
    w = _win(qtbot, ctx)
    acts = sc.commands(w)["Проверка проекта"]
    assert len(acts) == 2 and set(_keys(w, "Проверка проекта")) == {"Ctrl+Alt+9", "F7"}
    assert len(sc.commands(w)["AI-экспорт для Claude Code"]) == 2             # с «…» и без — одна команда
    assert w.set_shortcut("Проверка проекта", "F8")
    assert [a.shortcut().toString() for a in acts] == ["F8", ""]
    assert w.set_shortcut("Проверка проекта", "Ctrl+Alt+9") and sc.load(ctx.settings) == {"Проверка проекта": ["Ctrl+Alt+9"]}
    w.reset_shortcuts()
    assert set(_keys(w, "Проверка проекта")) == {"Ctrl+Alt+9", "F7"}


def test_gallery_category_fits(qtbot, ctx, projects_dir):
    from tests.conftest import make_spec
    w = _win(qtbot, ctx)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Клавиши"))
    w.open_project(str(path))
    g = w.project_page.layers.gallery
    qtbot.waitUntil(lambda: g.category.isVisible(), timeout=3000)
    QApplication.processEvents()
    assert g.category.geometry().right() <= g.width()                   # список «Все» не вылезает за край
    w.project_page.mark_clean()
    w.dirty = False


def test_qt_buttons_in_russian(qtbot):
    from PySide6.QtWidgets import QDialogButtonBox
    from app.ui.themes.fusion_amoled import install_qt_russian
    app = QApplication.instance()
    assert install_qt_russian(app)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    qtbot.addWidget(bb)
    assert bb.button(QDialogButtonBox.StandardButton.Cancel).text() == "Отмена"
