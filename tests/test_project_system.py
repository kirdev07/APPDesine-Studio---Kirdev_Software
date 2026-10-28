"""1.18: проект и система — история версий с откатом, комментарии на холсте, исправление контраста."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import Comment, ModelError, Screen
from app.engines.validation.engine import contrast, readable_color
from app.exporters.ai_export import ExportOptions, build_package
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec


def test_comment_model_and_readable_color():
    s = Screen(name="s", platform="android", width=100, height=100, comments=[Comment(x=10, y=20, text="Поправить")])
    back = Screen.from_dict(s.to_dict())
    assert back.comments[0].text == "Поправить" and not back.comments[0].resolved
    assert "comments" not in Screen(name="s", platform="android", width=10, height=10).to_dict()
    with pytest.raises(ModelError):
        Comment.from_dict({"id": "a", "x": 0, "y": 0, "text": 5})
    c = readable_color("#9E9E9ECC", "#FFFFFF", 4.5)
    assert contrast(c[:7], "#FFFFFF") >= 4.5 and c.endswith("CC")       # оттенок темнее, прозрачность та же


@pytest.fixture
def win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)
    w._quiet = True

    def discard(x):
        x.project_page.mark_clean()
        x.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Система"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_versions_save_list_restore(win):
    ed = win.project_page.editor
    win.save_version("Пустой")
    ed.add_template_screen("home")
    assert len(ed.doc.screens) == 2
    win.save_project()                                                   # ещё и автокопия
    win.save_project()
    vers = win.versions()
    named = [v for v in vers if not v.auto]
    assert named[0].label == "Пустой" and any(v.auto for v in vers)
    assert vers == sorted(vers, key=lambda v: v.when, reverse=True)
    pid = ed.doc.meta.id
    assert win.restore_version(named[0])
    assert len(ed.doc.screens) == 1 and ed.doc.meta.id == pid and ed.screen() is not None
    assert any(v.label == "Перед откатом" for v in win.versions())     # состояние до отката не потеряно
    ed.undo()
    assert len(ed.doc.screens) == 2                                      # откат отменяется
    win.show_versions()
    win._versions_dialog.close()


def test_comments_on_canvas(win, qtbot):
    page, ed = win.project_page, win.project_page.editor
    cid = page.add_comment_at(40, 60, "Сделать кнопку крупнее")
    assert ed.comment(cid).text == "Сделать кнопку крупнее"
    assert ed.update_comment(cid, resolved=True) and ed.comment(cid).resolved
    ed.undo()
    assert not ed.comment(cid).resolved
    # щелчок по значку комментария открывает его
    got = []
    ed.comment_clicked.disconnect(page.edit_comment)                    # без модального окна в тесте
    ed.comment_clicked.connect(got.append)
    canvas = page.canvas
    pt = canvas.mapFromScene(40, 60) + QPoint(8, -10)
    qtbot.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=pt)
    assert got == [cid]
    # в списке экрана и в задании для Claude Code (открытые)
    ed.select([])
    page.inspector.refresh()
    assert page.inspector.s_comments.count() == 1
    task = build_package(ed.doc, ExportOptions()).files["AI_TASK.md"].decode()
    assert "## Комментарии дизайнера" in task and "Сделать кнопку крупнее" in task
    assert ed.delete_comment(cid) and ed.screen().comments == []


def test_fix_contrast(win):
    ed = win.project_page.editor
    t = ed.add_node("text")
    bg = ed.artboard_color()
    ed.set_props({t.id: {"text": "Плохо видно", "text_color": bg[:7]}}, "x")    # цвет текста = цвет фона
    win.show_validator()
    vp = win.validator
    vp.refresh()
    assert any(i.code == "contrast" for i in vp.issues) and not vp.b_contrast.isHidden()
    assert vp.fix_contrast() >= 1
    n = tree.find(ed.screen(), t.id)[0]
    assert contrast(n.text_color[:7], bg) >= 4.5 and not any(i.code == "contrast" and i.node_id == t.id
                                                               for i in vp.issues)
    ed.undo()
    assert tree.find(ed.screen(), t.id)[0].text_color == bg[:7]
