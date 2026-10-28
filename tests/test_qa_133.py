"""1.33: исправления по итоговой проверке — ссылки после удаления, имена пакетов, пути с дефисом, крупные экраны."""

import re

from app.core.commands import DeleteNodes, RemoveScreen, UndoStack
from app.core.document.behavior import Interaction
from app.core.document.model import Appearance, Node, Screen
from app.core.project.service import build_document
from app.exporters import schema
from app.exporters.android_project import drawable_name, kstr, package_name
from app.libraries import components
from tests.conftest import make_spec


def _doc():
    doc = build_document(make_spec(".", title="Ссылки"))
    a = doc.screens[0]
    b = Screen(name="Второй", platform=a.platform, width=a.width, height=a.height, device_id=a.device_id)
    btn, panel = Node(type="rect", name="Кнопка", w=100, h=40), Node(type="frame", name="Панель", w=200, h=200)
    a.nodes += [btn, panel]
    doc.screens.append(b)
    doc.interactions += [
        Interaction(screen_id=a.id, trigger="tap", node_id=btn.id,
                    actions=[{"type": "navigate", "screen_id": b.id, "transition": "none", "duration": 0,
                              "easing": "linear"}]),
        Interaction(screen_id=a.id, trigger="tap", node_id=btn.id,
                    actions=[{"type": "set_visible", "node_id": panel.id, "mode": "show"},
                             {"type": "back"}]),
    ]
    return doc, a, b, btn, panel


def test_delete_screen_and_panel_prunes_links_with_undo():
    doc, a, b, btn, panel = _doc()
    st = UndoStack(doc)
    st.push(RemoveScreen(b.id))
    assert len(doc.interactions) == 1                                       # переход на удалённый экран убран
    st.push(DeleteNodes(a.id, [panel.id]))
    assert [x["type"] for x in doc.interactions[0].actions] == ["back"]     # показ удалённой панели убран
    st.undo()
    st.undo()
    assert len(doc.interactions) == 2 and len(doc.interactions[1].actions) == 2  # отмена — всё на месте


def test_android_names_and_paths():
    assert package_name("Fun") == "com.design.funapp" and package_name("Con") == "com.design.conapp"
    assert package_name("Доставка") == "com.design.dostavka"
    assert "\r" not in kstr("a\r\nb")
    assert drawable_name("con.png", set()) == "con_"
    assert re.match(schema._PATH, "android_project/app/src/main/res/drawable-nodpi/ic_launcher_art.png")
    assert not re.match(schema._PATH, "a/../b.png")


def test_full_height_components_stay_on_screen():
    s = Screen(name="Экран", platform="android", width=1080, height=2400, device_id="pixel_7")
    for kind in ("m3_nav_rail", "m3_side_sheet"):
        n = components.build(kind, s, Appearance())
        assert n.y + n.h <= s.height + 0.5, kind


def test_menu_commands_do_not_receive_checked(qtbot, paths, projects_dir, monkeypatch):
    """Команды меню с необязательным параметром (PDF, HTML, версия, картинка) не получают checked=False."""
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

    from app.context import AppContext
    from app.ui.shell.main_window import MainWindow
    from app.ui.themes.fusion_amoled import apply_theme
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    errors = []
    monkeypatch.setattr("sys.excepthook", lambda *exc: errors.append(exc))
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)
    qtbot.addWidget(w)
    _, path = ctx.service.create(make_spec(projects_dir, title="Меню"))
    w.open_project(str(path))
    seen = []
    for a in w.findChildren(QAction):
        if a.text() in ("Экраны в PDF…", "Прототип в браузере (HTML)…", "Сохранить версию…", "Картинка из файла…"):
            seen.append(a.text())
            a.trigger()
    assert len(set(seen)) >= 3 and not errors, (seen, errors)
    w.project_page.mark_clean()
    w.dirty = False
    ctx.close()


def test_big_screen_split_into_parts():
    """Экран из сотни элементов — код частями (локальные @Composable), иначе «Method too large» в Kotlin."""
    from app.exporters.ai_export import ExportOptions, build_package
    doc = build_document(make_spec(".", title="Много"))
    s = doc.screens[0]
    for i in range(120):
        s.nodes.append(Node(type="text", name=f"Текст {i}", text=f"Строка {i}", x=10, y=10 + i * 20, w=200, h=18))
    kt = next(v.decode() for k, v in build_package(doc, ExportOptions()).files.items()
              if k.endswith("Screen.kt") and "/screens/" in k)
    assert "@Composable fun BoxScope.part1()" in kt and "part1()" in kt
