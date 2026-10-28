"""1.10: темы и стили — готовые темы, перекраска по ролям, шрифт, скругления; цвета в коде через тему."""

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import Appearance, Node
from app.engines.material.color import scheme
from app.engines.material.restyle import PRESETS, appearance_of, color_map, preset, restyle
from app.exporters.ai_export import ExportOptions, build_package
from app.exporters.android_project import ROOT, package_name
from app.libraries import components
from app.ui.shell.main_window import MainWindow
from app.ui.studio.theme import ThemeDialog
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec
from tests.test_android_export import _balanced
from tests.test_preview import doc_with_form


def test_restyle_maps_roles_font_and_shapes():
    doc, _ = doc_with_form()
    s = doc.screens[0]
    btn = components.build("m3_button_filled", s, doc.meta.appearance)
    card = components.build("m3_card", s, doc.meta.appearance)
    custom = Node(type="rect", fill="#123456", radius=10, w=100, h=100)
    s.nodes += [btn, card, custom]
    old = doc.meta.appearance
    new = appearance_of(preset("forest"), old)
    old_s, new_s = scheme(old.accent, True), scheme(new.accent, False)
    assert color_map(old, new)[old_s["primary"]] == new_s["primary"]
    restyle(doc, new)
    assert btn.fill == new_s["primary"] and btn.children[0].text_color == new_s["onPrimary"]
    assert card.fill == new_s["surfaceContainerHighest"]
    assert custom.fill == "#123456"                                           # свой цвет не трогается
    assert btn.radius == pytest.approx(min(btn.w, btn.h) / 2)                 # таблетка осталась таблеткой
    assert card.radius > 12 * 2.625                                           # мягкие скругления
    assert all(t.font_family == "Trebuchet MS" for t in tree.descendants(card) if t.type == "text")
    assert doc.meta.appearance == new
    d = Appearance.from_dict(replace(new, app_theme="system", dynamic_color=True).to_dict())
    assert d.app_theme == "system" and d.dynamic_color
    assert len(PRESETS) >= 12 and len({p.key for p in PRESETS}) == len(PRESETS)
    built = components.build("m3_card", s, replace(new, corner_radius=4))   # новые компоненты — в стиле формы
    assert built.radius < 12 * 2.625


def test_export_uses_theme_roles_and_system_options():
    doc, _ = doc_with_form()
    s = doc.screens[0]
    s.nodes.append(components.build("m3_card", s, doc.meta.appearance))
    doc.meta.appearance = replace(doc.meta.appearance, app_theme="system", dynamic_color=True)
    f = build_package(doc, ExportOptions()).files
    base = f"{ROOT}/app/src/main/java/{package_name(doc.meta.title).replace('.', '/')}"
    src = f[f"{base}/ui/screens/FormaScreen.kt"].decode()
    assert _balanced(src)
    assert ".background(MaterialTheme.colorScheme.surfaceContainerHighest)" in src
    assert "color = MaterialTheme.colorScheme.onSurface" in src
    assert "containerColor = MaterialTheme.colorScheme.background" in src
    theme = f[f"{base}/ui/theme/Theme.kt"].decode()
    assert _balanced(theme)
    for code in ("const val FollowSystemTheme = true", "const val UseWallpaperColors = true",
                 "isSystemInDarkTheme()", "dynamicDarkColorScheme(", "Build.VERSION_CODES.S"):
        assert code in theme, code
    assert "SystemBarStyle.dark" not in f[f"{base}/MainActivity.kt"].decode()  # значки панелей — как в системе


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
    _, path = ctx.service.create(make_spec(projects_dir, title="Темы"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_theme_dialog_and_apply_with_undo(qtbot, win):
    page, ed = win.project_page, win.project_page.editor
    btn = ed.insert_component("m3_button_filled")
    old_fill = btn.fill
    d = ThemeDialog(ed)
    assert d.presets.count() == len(PRESETS) and not d.presets.item(0).icon().isNull()
    d.show()  # показ окна не меняет тему проекта (список не выбирает первую тему сам)
    assert d.appearance().accent == ed.doc.meta.appearance.accent
    d.presets.itemClicked.emit(d.presets.item(next(i for i, p in enumerate(PRESETS) if p.key == "sunset")))
    ap = d.appearance()
    assert ap.accent == "#F4511E" and ap.theme == "dark" and ap.corner_radius == 20
    assert not d.light_view.pixmap().isNull() and not d.dark_view.pixmap().isNull()
    d.follow.setChecked(True)
    ap = d.appearance()
    d.deleteLater()
    assert ed.apply_appearance(ap)
    n = tree.find(ed.screen(), btn.id)[0]
    assert n.fill == "#F4511E" and ed.doc.meta.appearance.app_theme == "system"
    assert ed.artboard_color() == "#121212"
    lp = page.layers
    lp._maybe_rebuild_components()                                            # галерея — в новой теме
    assert lp._gallery_key[3:5] == ("dark", "#F4511E")
    ed.undo()
    assert tree.find(ed.screen(), btn.id)[0].fill == old_fill and ed.doc.meta.appearance.theme == "amoled"
    assert page.a_theme.isEnabled() and page.a_theme in page.toolbar.actions()
