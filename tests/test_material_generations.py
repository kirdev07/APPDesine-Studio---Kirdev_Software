"""1.27: поколения Material — M1 (2014), M2 (2018), M3, M3 Expressive: вид компонентов, смена в теме, прототип,
код Android."""

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import Appearance, Screen
from app.engines.material import generations
from app.engines.material.color import scheme
from app.engines.preview import live
from app.exporters.ai_export import ExportOptions, build_package
from app.libraries import components
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec

S = Screen(name="э", platform="android", width=1080, height=2400, device_id="android_phone")
K = 1080 / 411


def _build(kind, gen):
    return components.build(kind, S, Appearance(theme="light", accent="#6750A4", material=gen))


def test_appearance_roundtrip():
    ap = Appearance(material="m2")
    assert Appearance.from_dict(ap.to_dict()).material == "m2"
    assert "material" not in Appearance().to_dict() and Appearance.from_dict({"material": "xx"}).material == "m3"


def test_components_per_generation():
    s = scheme("#6750A4", False)
    b1, b3 = _build("m3_button_filled", "m1"), _build("m3_button_filled", "m3")
    assert b1.radius < b1.h / 2 and b1.elevation == 2
    assert [t.text_case for t, _, _ in tree.walk([b1]) if t.type == "text"] == ["upper"]
    assert b3.radius == pytest.approx(b3.h / 2, abs=0.6) and b3.elevation == 0
    fab1, fab3, fabx = _build("m3_fab", "m2"), _build("m3_fab", "m3"), _build("m3_fab", "m3x")
    assert fab1.radius == pytest.approx(fab1.w / 2) and fab1.fill == s["primary"]
    assert fab3.radius < fabx.radius < fab3.w / 2
    top1, top3 = _build("m3_top_app_bar", "m1"), _build("m3_top_app_bar", "m3")
    assert top1.fill == s["primary"] and top1.elevation > 0 and top3.fill == s["surface"]
    nav2 = _build("m3_nav_bar", "m2")
    pills = [next(c for c in it.children if c.is_frame) for it in live._items(nav2)]
    assert all(not p.fill for p in pills) and generations.nav_selected(nav2) == 0
    first_label = next(c for c in live._items(nav2)[0].children if c.type == "text")
    assert first_label.text_color == s["primary"]
    f1, f2, f3 = (_build("m3_text_field", g) for g in ("m1", "m2", "m3"))
    box = lambda n: next(c for c in n.children if c.is_frame)  # noqa: E731
    assert box(f1).stroke_sides == "b" and not box(f1).fill
    assert box(f2).stroke_sides == "b" and box(f2).fill
    assert box(f3).stroke_sides == "trbl"
    c1, cx = _build("m3_card", "m1"), _build("m3_card", "m3x")
    assert c1.radius < cx.radius


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
    _, path = ctx.service.create(make_spec(projects_dir, title="Поколения"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_switch_generation_in_project_and_android(win):
    ed = win.project_page.editor
    a = ed.add_template_screen("profile")
    btn = ed.insert_component("m3_button_filled")
    fab = ed.insert_component("m3_fab")
    old_radius = tree.find(ed.screen(), btn.id)[0].radius
    assert ed.apply_appearance(replace(ed.doc.meta.appearance, material="m1"))
    assert ed.doc.meta.appearance.material == "m1"
    m = tree.node_map(ed.screen())
    assert m[btn.id].radius < old_radius and m[fab.id].radius == pytest.approx(m[fab.id].w / 2)
    nav = next(n for n in ed.screen().nodes if n.role == "m3.nav_bar")
    assert not next(c for c in live._items(nav)[0].children if c.is_frame).fill    # M1 — без «пилюли»
    # прототип: нажатие пункта меню не возвращает «пилюлю»
    from app.ui.studio.prototype import PrototypePlayer
    p = PrototypePlayer(ed, start_screen_id=a.id)
    root, idx = live.target(p.screen, [live._items(nav)[2].id, nav.id])
    live.toggle(p.live, root, idx)
    p.render()
    pn = tree.node_map(p.screen)[nav.id]
    assert all(not next(c for c in it.children if c.is_frame).fill for it in live._items(pn))
    assert live.selected(pn) == 2
    # код Android: форма кнопки, заглавные, круглая FAB, шапка цвета бренда, меню без индикатора
    src = next(v.decode() for k, v in build_package(ed.doc, ExportOptions()).files.items()
               if k.endswith("Screen.kt") and "Экран «Профиль»" in v.decode())
    for code in ("shape = RoundedCornerShape(", ".uppercase()", "shape = CircleShape",
                 "TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.primary",
                 "indicatorColor = Color.Transparent"):
        assert code in src, code
    # отмена — одной записью
    ed.undo()
    assert ed.doc.meta.appearance.material == "m3"
    assert tree.node_map(ed.screen())[btn.id].radius == pytest.approx(old_radius)


def test_theme_dialog_has_generation(win):
    from app.ui.studio.theme import ThemeDialog
    d = ThemeDialog(win.project_page.editor, win)
    d.material.setCurrentIndex(d.material.findData("m2"))
    assert d.appearance().material == "m2"
    d.close()
