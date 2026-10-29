"""1.29: виджеты рабочего стола Android — готовые и пустые, перевод в Jetpack Glance."""

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.exporters.ai_export import ExportOptions, build_package
from app.exporters.android_project import ROOT, package_name
from app.exporters.glance import cells, is_widget
from app.libraries.catalog import DEVICES, device
from app.libraries.widget_templates import SIZES, WIDGETS
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
    _, path = ctx.service.create(make_spec(projects_dir, title="Виджеты"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_widget_devices_not_in_project_lists():
    assert all(not d.id.startswith("android_widget_") for d in DEVICES)
    for size in SIZES:
        d = device(f"android_widget_{size}")
        assert d.kind == "widget" and d.dpi == 420


def test_add_widgets_and_export_glance(win):
    page, ed = win.project_page, win.project_page.editor
    page.screens._fill_add_menu()
    inner = [x.text() for a in page.screens.add_menu.actions() if a.menu() for x in a.menu().actions()]
    assert "Часы и погода · 4×2" in inner and "Пустой 2×2" in inner
    for k in WIDGETS:
        ed.set_screen(ed.doc.screens[0].id)
        s = ed.add_widget(k)
        assert s is not None and is_widget(s) and s.nodes and not [d for d in ed.diagnostics
                                                                   if d.severity == "warning"], k
    assert ed.add_widget("", "4x4") and cells(ed.screen()) == (4, 4)
    ed.undo()
    files = build_package(ed.doc, ExportOptions()).files
    base = f"{ROOT}/app/src/main/java/{package_name(ed.doc.meta.title).replace('.', '/')}"
    kts = {k: v.decode() for k, v in files.items() if k.startswith(f"{base}/widget/")}
    assert len(kts) == len(WIDGETS)
    clock = next(v for k, v in kts.items() if "Chasy" in k)
    assert "class ChasyIPogodaWidget : GlanceAppWidget()" in clock and "provideContent" in clock
    assert "actionStartActivity<MainActivity>()" in clock and 'Text(context.getString(R.string.text_10_24)' in clock
    assert "ImageProvider(R.drawable." in clock and clock.count("{") == clock.count("}")
    manifest = files[f"{ROOT}/app/src/main/AndroidManifest.xml"].decode()
    assert manifest.count("<receiver") == len(WIDGETS) and "android.appwidget.provider" in manifest
    info = files[f"{ROOT}/app/src/main/res/xml/chasyipogoda_widget_info.xml"].decode()
    assert 'android:minWidth="250dp"' in info and 'android:minHeight="110dp"' in info  # 70·N − 30
    assert 'targetCellWidth="4"' in info and 'targetCellHeight="2"' in info
    gradle = files[f"{ROOT}/app/build.gradle.kts"].decode()
    assert 'implementation("androidx.glance:glance-appwidget:' in gradle
    nav = next(v.decode() for k, v in files.items() if k.endswith("AppNavHost.kt"))
    assert "ChasyIPogoda" not in nav                                       # виджет — не экран приложения
    assert any(k.endswith("_icon_1.xml") for k in files)
    strings = files[f"{ROOT}/app/src/main/res/values/strings.xml"].decode()
    assert "chasyipogoda_widget_description" in strings and '<string name="text_10_24">10:24</string>' in strings


def test_widget_preview_image(win):
    ed = win.project_page.editor
    s = ed.add_widget("note")
    from app.ui.workspace.render_export import widget_previews
    prev = widget_previews(ed.doc, [s])
    files = build_package(ed.doc, ExportOptions(), None, prev).files
    assert f"{ROOT}/app/src/main/res/drawable-nodpi/zametka_preview.png" in files
    assert "@drawable/zametka_preview" in files[f"{ROOT}/app/src/main/res/xml/zametka_widget_info.xml"].decode()


def test_no_glance_without_widgets(win):
    files = build_package(win.project_page.editor.doc, ExportOptions()).files
    assert "glance" not in files[f"{ROOT}/app/build.gradle.kts"].decode()


def test_new_screen_from_widget_is_phone_sized(win):
    """Открыт виджет — «Пустой экран», готовый экран и готовое приложение всё равно размера телефона."""
    ed = win.project_page.editor
    phone = ed.doc.screens[0]
    ed.add_widget("note")
    assert ed.add_blank_screen().width == phone.width
    ed.add_widget("note")
    assert ed.add_template_screen("login").height == phone.height
    ed.add_widget("note")
    assert ed.add_ready_app("bank").width == phone.width
    files = build_package(ed.doc, ExportOptions()).files
    manifest = files[f"{ROOT}/app/src/main/AndroidManifest.xml"].decode()
    assert manifest.count("<receiver") == 3 and '@string/zametka_widget_label' in manifest
    strings = files[f"{ROOT}/app/src/main/res/values/strings.xml"].decode()
    assert '<string name="zametka_widget_label">Заметка</string>' in strings


def test_widget_preview_has_transparent_corners(win):
    ed = win.project_page.editor
    s = ed.add_widget("clock_weather")
    from PySide6.QtGui import QImage
    from app.ui.workspace.render_export import widget_previews
    img = QImage.fromData(widget_previews(ed.doc, [s])[s.id])
    assert img.pixelColor(0, 0).alpha() == 0 and img.pixelColor(img.width() - 1, 0).alpha() == 0
    assert ed.screen().orientation == "landscape"
