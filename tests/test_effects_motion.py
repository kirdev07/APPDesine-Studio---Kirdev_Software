"""1.3: эффекты (тень, градиент, размытие), живые компоненты и волна нажатия в предпросмотре, анимации в Compose."""

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QGraphicsBlurEffect, QGraphicsDropShadowEffect, QGraphicsScene, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.behavior import Animation, Interaction, Keyframe, Track
from app.core.document.model import ModelError, Node
from app.core.persistence.migrations import migrate
from app.engines.material.color import scheme
from app.engines.preview import live
from app.exporters.ai_export import ExportOptions, build_package
from app.exporters.android_project import ROOT, package_name
from app.exporters.compose_motion import brush, easing
from app.libraries import components
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from app.ui.workspace.canvas import build_scene, fill_brush
from tests.conftest import make_spec
from tests.test_android_export import _balanced
from tests.test_preview import doc_with_form


def test_effect_props_validation_and_file_format():
    n = Node(type="rect", elevation=3, gradient="linear", fill="#112233", fill2="#445566", grad_angle=90, blur=4)
    d = n.to_dict()
    assert (d["elevation"], d["gradient"], d["fill2"], d["grad_angle"], d["blur"]) == (3, "linear", "#445566", 90, 4)
    back = Node.from_dict(d)
    assert (back.elevation, back.gradient, back.blur) == (3, "linear", 4)
    plain = Node(type="rect").to_dict()                          # значения по умолчанию не пишутся
    assert not {"elevation", "gradient", "fill2", "grad_angle", "blur"} & set(plain)
    for bad in ({"elevation": 6}, {"elevation": True}, {"gradient": "conic"}, {"blur": 300}, {"fill2": "red"}):
        with pytest.raises(ModelError):
            Node.from_dict({**plain, **bad})
    assert migrate({"screens": []}, 7) == {"screens": []}


def test_canvas_draws_shadow_gradient_and_blur(qtbot):
    doc, _ = doc_with_form()
    s = doc.screens[0]
    card = components.build("m3_card", s, doc.meta.appearance)
    card.elevation = 2
    glass = Node(type="rect", name="Стекло", x=10, y=10, w=200, h=100, fill="#FFFFFF33", blur=8)
    grad = Node(type="rect", name="Градиент", x=10, y=200, w=200, h=100, fill="#FF0000", fill2="#0000FF",
                gradient="linear", grad_angle=90)
    s.nodes += [card, glass, grad]
    scene = QGraphicsScene()
    items = build_scene(scene, s, "#000000")
    shadow = items[card.id].graphicsEffect()
    assert isinstance(shadow, QGraphicsDropShadowEffect) and shadow.blurRadius() > 3 and shadow.offset().y() > 0
    assert isinstance(items[glass.id].graphicsEffect(), QGraphicsBlurEffect)
    assert items[grad.id].graphicsEffect() is None
    b = fill_brush(grad, items[grad.id].boundingRect())
    g = b.gradient()
    assert g is not None and g.stops()[0][1].name() == "#ff0000" and g.finalStop().x() > g.start().x()
    card.elevation = 0
    items[card.id].sync()                                         # эффект снимается при изменении
    assert items[card.id].graphicsEffect() is None


def test_live_components_change_with_taps():
    doc, _ = doc_with_form()
    s = doc.screens[0]
    ap = doc.meta.appearance
    sw, nav, slider, radio = (components.build(k, s, ap) for k in ("m3_switch", "m3_nav_bar", "m3_slider", "m3_radio"))
    s.nodes += [sw, nav, slider, radio]
    sch, k, state = scheme(ap.accent, True), 2.625, {}
    track = sw.children[1]
    root, idx = live.target(s, [track.children[0].id, track.id, sw.id])
    assert root is sw and idx is None
    live.toggle(state, root)
    live.apply(s, state, sch, k)
    assert state[sw.id] is False and track.fill == sch["surfaceContainerHighest"]
    assert track.children[0].x == pytest.approx(track.x + 8 * k) and track.children[0].w == pytest.approx(16 * k)
    third = nav.children[2]
    root, idx = live.target(s, [third.children[1].id, third.id, nav.id])
    assert root is nav and idx == 2
    live.toggle(state, root, idx)
    live.apply(s, state, sch, k)
    assert third.children[0].fill == sch["secondaryContainer"] and nav.children[0].children[0].fill == ""
    live.toggle(state, slider, frac=live.slider_fraction(slider, slider.x + slider.w))
    live.apply(s, state, sch, k)
    assert state[slider.id] == 1.0 and slider.children[2].w == pytest.approx(0, abs=0.01)
    live.toggle(state, radio, 2)
    live.apply(s, state, sch, k)
    rings = [r.children[0].children[0] for r in radio.children]
    assert [len(r.children) for r in rings] == [0, 0, 1] and rings[2].stroke == sch["primary"]


def test_compose_effects_animations_and_transitions():
    doc, ids = doc_with_form()
    s = doc.screens[0]
    card = components.build("m3_card", s, doc.meta.appearance)
    card.elevation, card.gradient, card.fill2, card.grad_angle, card.blur = 3, "linear", "#000000", 135, 2
    s.nodes.append(card)
    anim = Animation(name="Появление", screen_id=s.id, duration=600, tracks=[
        Track(node_id=card.id, prop="opacity", keyframes=[Keyframe(0, 0.0, "ease_out"), Keyframe(600, 1.0)]),
        Track(node_id=card.id, prop="y", keyframes=[Keyframe(0, card.y + 100), Keyframe(600, card.y)]),
        Track(node_id=card.id, prop="fill", keyframes=[Keyframe(0, "#000000"), Keyframe(600, "#FFFFFF")])])
    doc.animations.append(anim)
    doc.interactions += [
        Interaction(screen_id=s.id, trigger="screen_open", actions=[{"type": "play_animation", "animation_id": anim.id}]),
        Interaction(screen_id=s.id, node_id=card.id, trigger="tap", actions=[
            {"type": "navigate", "screen_id": doc.screens[1].id, "transition": "slide_left", "duration": 350,
             "easing": "ease_out"}, {"type": "set_visible", "node_id": ids["hint"], "mode": "toggle"}])]
    f = build_package(doc, ExportOptions()).files
    base = f"{ROOT}/app/src/main/java/{package_name(doc.meta.title).replace('.', '/')}"
    src = f[f"{base}/ui/screens/FormaScreen.kt"].decode()
    assert _balanced(src)
    for code in (".shadow(elevation = 6.dp", ".blur(", "linearAngleBrush(listOf(", "remember { Animatable(0f) }",
                 "keyframes { durationMillis = 600; 0f at 0 using CubicBezierEasing(0f, 0f, 0.58f, 1f)",
                 "scope.launch { playPoyavlenie() }", ".graphicsLayer { alpha = ", "translationY = ",
                 'onNavigate("screen2", NavMotion("slide_left", 350, "ease_out"))', "AnimatedVisibility(visible = ",
                 "onNavigate: (String, NavMotion) -> Unit", "// TODO: анимации, которые не переведены"):
        assert code in src, code
    nav = f[f"{base}/navigation/AppNavHost.kt"].decode()
    assert "AnimatedContent(" in nav and "screenTransition(" in nav and _balanced(nav)
    motion = f[f"{base}/navigation/NavMotion.kt"].decode()
    assert "slideInHorizontally" in motion and "fun screenTransition(" in motion and _balanced(motion)
    assert _balanced(f[f"{base}/ui/components/Gradients.kt"].decode())
    assert easing("linear") == "LinearEasing" and easing("cubic", [0.2, 0, 0, 1]) == "CubicBezierEasing(0.2f, 0f, 0f, 1f)"
    vert = Node(type="rect", fill="#111111", fill2="#222222", gradient="linear", grad_angle=180)
    assert brush(vert, lambda c: c).startswith("Brush.verticalGradient(")
    assert brush(Node(type="rect", fill="#111111"), lambda c: c) is None


@pytest.fixture
def app_win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)

    def discard(win):
        win.project_page.mark_clean()
        win.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.resize(1500, 950)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Эффекты"))
    w.open_project(str(path))
    yield w, w.project_page.editor, ctx
    ctx.close()


def test_inspector_effects_and_preview_ripple(qtbot, app_win):
    win, ed, _ = app_win
    card = ed.insert_component("m3_card")
    ed.select([card.id])
    insp = win.project_page.inspector
    insp.elevation.setCurrentIndex(2)
    insp.gradient.setCurrentIndex(insp.gradient.findData("linear"))
    n = tree.find(ed.screen(), card.id)[0]
    assert n.elevation == 2 and n.gradient == "linear" and n.fill2      # второй цвет подставлен
    assert insp.grad_angle.isEnabled() and insp.fill2.isEnabled()
    ed.undo()
    assert tree.find(ed.screen(), card.id)[0].gradient == "none"
    sw = ed.insert_component("m3_switch")
    win.run_prototype()
    p = win.preview.player
    p.stop_clock()
    track = tree.node_map(p.screen)[sw.children[1].id]
    pt = QPointF(track.x + track.w / 2, track.y + track.h / 2)
    p.press(pt)
    assert p.ripple is not None and p.ripple[1].width() == pytest.approx(tree.node_map(p.screen)[sw.id].w)
    p.release(pt)
    assert p.live == {sw.id: False}
    assert tree.node_map(p.screen)[sw.children[1].id].stroke                  # выключен: дорожка с контуром
    p.advance(1000)
    assert p.ripple is None
    p.restart()
    assert p.live == {}


def test_zoom_keeps_point_under_cursor_and_zoom_box_visible(qtbot, app_win):
    win, ed, _ = app_win
    page = win.project_page
    v = page.canvas
    v.fit()
    pos = v.viewport().rect().center() + QPointF(-120, -90).toPoint()
    target = v.mapToScene(pos)
    for _ in range(5):                                   # Ctrl + колесо: экран не «уплывает»
        v.set_zoom(v.zoom() * 1.25, anchor_under_mouse=True, view_pos=pos)
    now = v.mapToScene(pos)
    assert abs(now.x() - target.x()) * v.zoom() <= 5 and abs(now.y() - target.y()) * v.zoom() <= 5  # ≤ 1 px за шаг
    box = page.zoom_box
    assert box.isVisible() and v.rect().contains(box.geometry())   # кнопки масштаба всегда в пределах холста
    page.zoom_combo.setEditText("200%")
    page.zoom_combo.lineEdit().editingFinished.emit()
    assert v.zoom() == pytest.approx(2.0)
