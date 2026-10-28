"""1.17: экспорт и показ — экраны в PNG (масштаб) и PDF, иконка приложения из дизайна, показ на весь экран."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document.model import Appearance, Node, Screen
from app.exporters.ai_export import ExportOptions, build_package
from app.exporters.android_project import ROOT
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from app.ui.workspace.render_export import file_names, icon_image, render_screen
from tests.conftest import make_spec


def test_file_names_unique_and_safe():
    s = [Screen(name="Главная", platform="android", width=10, height=10),
         Screen(name="Главная", platform="android", width=10, height=10),
         Screen(name='a/b:c*?', platform="android", width=10, height=10)]
    names = file_names(s, "png")
    assert names[0] == "01 Главная.png" and names[1] == "02 Главная.png" and "/" not in names[2]


def test_render_and_icon(qapp):
    red = Node(type="rect", x=10, y=10, w=40, h=20, fill="#FF0000")
    s = Screen(name="s", platform="windows", width=100, height=50, nodes=[red])
    img = render_screen(s, None, "#000000", 2.0)
    assert (img.width(), img.height()) == (200, 100)
    assert img.pixelColor(60, 40).red() > 200 and img.pixelColor(5, 5) == img.pixelColor(190, 90)
    icon = icon_image(s, None, "#000000", red, 64)
    assert (icon.width(), icon.height()) == (64, 64)
    assert icon.pixelColor(32, 32).red() > 200 and icon.pixelColor(32, 2).alpha() == 0   # вокруг прозрачно
    assert Appearance.from_dict(Appearance(app_icon="abc", app_icon_bg="#112233").to_dict()).app_icon == "abc"
    assert "app_icon" not in Appearance().to_dict()                                       # старые проекты без


@pytest.fixture
def win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)
    w._quiet = True

    def discard(x):
        x.project_page.mark_clean()
        x.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Показ"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_png_pdf_icon_and_presentation(win, tmp_path, qtbot):
    ed = win.project_page.editor
    ed.add_template_screen("home")
    s = ed.screen()
    paths = win.export_png(str(tmp_path / "png"), 0.5, all_screens=True)
    assert len(paths) == 2 and all(p.exists() for p in paths)
    img = QImage(str(paths[1]))
    assert (img.width(), img.height()) == (round(s.width * 0.5), round(s.height * 0.5))
    pdf = win.export_pdf(str(tmp_path / "out" / "макет.pdf"))
    data = open(pdf, "rb").read()
    assert data.startswith(b"%PDF") and data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 2 \
        or data.count(b"/Type /Page") >= 3                                               # страниц — по экранам
    # иконка: без выделения — подсказка, с элементом — ресурс и адаптивная иконка в Android-проекте
    ed.select([])
    assert not win.make_app_icon()
    from app.core.document import tree
    avatar = next(n for n, _, _ in tree.walk(s.nodes) if n.name == "Аватар")
    ed.select([avatar.id])
    assert win.make_app_icon()
    ap = ed.doc.meta.appearance
    assert ap.app_icon and ed.asset_usage(ap.app_icon) == 1 and ap.app_icon_bg.startswith("#")
    f = build_package(ed.doc, ExportOptions()).files
    manifest = f[f"{ROOT}/app/src/main/AndroidManifest.xml"].decode()
    assert 'android:icon="@mipmap/ic_launcher"' in manifest
    assert f"{ROOT}/app/src/main/res/drawable-nodpi/ic_launcher_art.png" in f
    assert b"<adaptive-icon" in f[f"{ROOT}/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml"]
    ed.undo()
    assert not ed.doc.meta.appearance.app_icon                                            # отмена — одной записью
    f = build_package(ed.doc, ExportOptions()).files
    assert "android:icon" not in f[f"{ROOT}/app/src/main/AndroidManifest.xml"].decode()
    # показ на весь экран: с текущего экрана, листается стрелками, Esc — выход
    pres = win.present()
    assert pres.index == 1
    qtbot.keyClick(pres, Qt.Key.Key_Left)
    assert pres.index == 0
    qtbot.keyClick(pres, Qt.Key.Key_Left)
    assert pres.index == 0                                                                # дальше первого — нет
    qtbot.keyClick(pres, Qt.Key.Key_End)
    assert pres.index == 1
    pres.repaint()
    qtbot.keyClick(pres, Qt.Key.Key_Escape)
    assert not pres.isVisible()
