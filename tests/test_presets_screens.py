"""1.9: готовые анимации (масштаб, поворот, пружина, по очереди…) и новые готовые экраны."""

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import ModelError, Node
from app.engines.animation import engine as anim
from app.engines.animation.presets import PRESETS, build as build_preset
from app.exporters.ai_export import ExportOptions, build_package
from app.exporters.android_project import ROOT, package_name
from app.libraries import components
from app.libraries.screen_templates import all_templates
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec
from tests.test_android_export import _balanced
from tests.test_preview import doc_with_form


def test_scale_rotation_props_and_all_presets_valid():
    n = Node(type="rect", scale=1.5, rotation=45)
    d = n.to_dict()
    assert (d["scale"], d["rotation"]) == (1.5, 45) and "scale" not in Node(type="rect").to_dict()
    with pytest.raises(ModelError):
        Node.from_dict({**d, "scale": 50})
    doc, _ = doc_with_form()
    s = doc.screens[0]
    card = components.build("m3_card", s, doc.meta.appearance)
    s.nodes.append(card)
    for p in PRESETS:
        a = build_preset(p.key, card, s.id, 2.625)
        assert a.tracks and a.duration > 0 and a.loop == ("по кругу" in p.name), p.key
        frames = anim.frames(a, fps=30)
        assert frames and frames[0]
    pop = build_preset("pop", card, s.id, 2.625)
    mid = anim.sample(pop, 320)[card.id]
    assert mid["scale"] == pytest.approx(1.08, abs=0.01)
    spin = build_preset("spin", card, s.id, 1)
    assert anim.sample(spin, 500)[card.id]["rotation"] == pytest.approx(180, abs=1)
    stag = build_preset("stagger", card, s.id, 1)
    starts = sorted({tr.node_id for tr in stag.tracks})
    assert len(starts) == len(card.children)                                # каждый ребёнок — своя пара дорожек


def test_compose_scale_rotation_animation():
    doc, _ = doc_with_form()
    s = doc.screens[0]
    fab = components.build("m3_fab", s, doc.meta.appearance)
    icon = components.build("m3_icon_star", s, doc.meta.appearance)
    icon.rotation = 15
    s.nodes += [fab, icon]
    doc.animations.append(build_preset("spin", icon, s.id, 2.625))
    doc.animations.append(build_preset("pulse", fab, s.id, 2.625))
    from app.core.document.behavior import Interaction
    doc.interactions.append(Interaction(screen_id=s.id, trigger="screen_open", actions=[
        {"type": "play_animation", "animation_id": a.id} for a in doc.animations]))
    f = build_package(doc, ExportOptions()).files
    src = f[f"{ROOT}/app/src/main/java/{package_name(doc.meta.title).replace('.', '/')}/ui/screens/FormaScreen.kt"]\
        .decode()
    assert _balanced(src)
    assert "rotationZ = " in src and "infiniteRepeatable(keyframes" in src and "360f at 1000" in src


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
    _, path = ctx.service.create(make_spec(projects_dir, title="Анимации"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_presets_from_selection_bar_play_in_preview(qtbot, win):
    page, ed = win.project_page, win.project_page.editor
    card = ed.insert_component("m3_card")
    ed.select([card.id])
    page._fill_anim_menu()
    titles = [a.text() for a in page.anim_menu.actions()]
    assert titles[0] == "При открытии экрана" and any(t.startswith("Убрать анимации") for t in titles)
    assert ed.add_animation_preset(card.id, "pop", "open")
    assert page.anim_button.text() == "Анимация (1) ▾"
    rule = next(it for it in ed.doc.interactions if it.trigger == "screen_open")
    assert rule.actions[0]["type"] == "play_animation"
    win.run_prototype()
    p = win.preview.player
    p.stop_clock()
    p.restart()
    p.advance(150)
    sc = tree.node_map(p.screen)[card.id].scale
    assert 0.6 < sc < 1.08                                                   # в середине увеличения
    p.advance(2000)
    assert tree.node_map(p.screen)[card.id].scale == pytest.approx(1.0)
    win.show_page(1)
    assert ed.add_animation_preset(card.id, "shake", "tap")
    assert len(ed.node_animations(card.id)) == 2
    assert ed.remove_node_animations(card.id)
    assert ed.node_animations(card.id) == [] and not [it for it in ed.doc.interactions if it.actions == []]
    ed.undo()
    assert len(ed.node_animations(card.id)) == 2


def test_eighteen_ready_screens(qtbot, win):
    ed = win.project_page.editor
    t = all_templates()
    assert len(t) == 22  # 1.19: календарь, карта, статистика, лента соцсети
    for key in ("onboarding", "home", "product", "checkout", "search", "player", "notifications", "wallet",
                "splash", "offline", "tracking"):
        ed.set_screen(ed.doc.screens[0].id)
        s = ed.add_template_screen(key)
        assert s.nodes and not [d for d in ed.diagnostics if d.severity == "warning"], key
    strip = win.project_page.screens
    strip._fill_add_menu()
    assert "Музыкальный плеер" in [a.text() for a in strip.add_menu.actions()]
