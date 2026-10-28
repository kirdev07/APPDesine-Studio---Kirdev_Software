"""Сборка «живого» экрана прототипа: копия экрана с текущим состоянием логики и кадром анимаций. Без Qt."""

from __future__ import annotations

from app.core.document import tree
from app.core.document.behavior import ANIMATABLE, Animation, Keyframe, Track
from app.core.document.model import ModelError, Node, ProjectDocument, Screen, check_prop
from app.engines.components import engine as ce
from app.engines.layout import LayoutEngine
from app.engines.logic.engine import RuntimeState


def compose(doc: ProjectDocument, state: RuntimeState, engine: LayoutEngine,
            samples: dict[str, dict] | None = None) -> Screen | None:
    src = next((s for s in doc.screens if s.id == state.screen_id), None)
    if src is None:
        return None
    clone = Screen.from_dict(src.to_dict())
    m = tree.node_map(clone)
    for nid in list(dict.fromkeys([*state.states, *state.variants])):
        inst = m.get(nid)
        defn = doc.component(inst.component_id) if inst is not None and inst.is_instance else None
        if defn is not None:
            inst.state = state.states.get(nid, inst.state)
            inst.variant = {**inst.variant, **state.variants.get(nid, {})}
            ce.materialize(defn, inst, engine)
    m = tree.node_map(clone)
    for nid, vis in state.visibility.items():
        if nid in m:
            m[nid].visible = vis
    for nid in state.overlays:
        if nid in m:
            m[nid].visible = True
    for nid in state.scrims:  # затемнение под окном: прямоугольник на весь экран прямо перед ним
        top = next((i for i, n in enumerate(clone.nodes) if n.id == nid), None)
        if top is not None:
            clone.nodes.insert(top, Node(type="rect", id=f"scrim:{nid}", name="Затемнение", x=0, y=0,
                                         w=clone.width, h=clone.height, fill="#00000066"))
    for nid, text in state.texts.items():
        if nid in m and m[nid].type == "text":
            m[nid].text = text
    changes, _ = engine.layout_screen(clone)  # новый текст и видимость могут менять раскладку
    for nid, props in changes.items():
        for k, v in props.items():
            setattr(m[nid], k, v)
    apply_samples(clone, samples or {})
    return clone


def apply_samples(screen: Screen, samples: dict[str, dict]) -> None:
    m = tree.node_map(screen)
    for nid, props in samples.items():
        n = m.get(nid)
        if n is None or n.is_group:
            continue
        for k, v in props.items():
            try:
                setattr(n, k, check_prop(k, v, n.type))
            except ModelError:
                pass


def smart_keys(screen: Screen) -> dict[str, Node]:
    """Имя → узел для имён, встречающихся на экране один раз (по ним «умный переход» сопоставляет элементы).
    Крупные контейнеры (больше половины экрана — «Содержимое», фон) не сопоставляются: перетекают детали."""
    seen: dict[str, list] = {}
    half = screen.width * screen.height / 2
    for n, _, _ in tree.walk(screen.nodes):
        if n.name and not n.is_group and not n.ref and n.w * n.h <= half:
            seen.setdefault(n.name, []).append(n)
    return {k: v[0] for k, v in seen.items() if len(v) == 1}


def smart_transition(before: Screen, after: Screen, duration: int, easing: str) -> Animation | None:
    """Smart Animate: одноимённые элементы перетекают из старого места и вида в новые, новые — проявляются."""
    if duration <= 0:
        return None
    old, new = smart_keys(before), smart_keys(after)
    anim = Animation(name="переход состояния", screen_id=after.id, duration=duration)
    for name, nb in new.items():
        na = old.get(name)
        if na is None:  # нового элемента не было — проявляется
            if nb.opacity > 0 and not any(c.name in old for c, _, _ in tree.walk(nb.children)):
                anim.tracks.append(Track(nb.id, "opacity", [Keyframe(0, 0.0, easing), Keyframe(duration, nb.opacity,
                                                                                               easing)]))
            continue
        for prop in ANIMATABLE:
            a, b = getattr(na, prop, None), getattr(nb, prop, None)
            if a is None or a == b or (prop in ("fill", "stroke", "text_color") and (not a or not b)):
                continue
            anim.tracks.append(Track(nb.id, prop, [Keyframe(0, a, easing), Keyframe(duration, b, easing)]))
    return anim if anim.tracks else None


def overlay_entrance(screen: Screen, nid: str, duration: int = 260) -> Animation | None:
    """Появление окна: прижатое к низу экрана выезжает снизу (шторка), остальные — проявляются."""
    n = tree.node_map(screen).get(nid)
    if n is None or n.is_group:
        return None
    anim = Animation(name="переход состояния", screen_id=screen.id, duration=duration)
    if n.y + n.h >= screen.height - 1:
        anim.tracks.append(Track(nid, "y", [Keyframe(0, float(screen.height), "ease_out"),
                                            Keyframe(duration, n.y, "ease_out")]))
    else:
        anim.tracks.append(Track(nid, "opacity", [Keyframe(0, 0.0, "ease_out"),
                                                  Keyframe(duration, n.opacity, "ease_out")]))
    return anim


def state_transition(before: Screen, after: Screen, duration: int, easing: str) -> Animation | None:
    """Синтетическая анимация перехода между двумя состояниями экземпляра (свойства, что изменились)."""
    if duration <= 0:
        return None
    ma, mb = tree.node_map(before), tree.node_map(after)
    anim = Animation(name="переход состояния", screen_id=after.id, duration=duration)
    for nid, nb in mb.items():
        na = ma.get(nid)
        if na is None or nb.is_group:
            continue
        for prop in ANIMATABLE:
            a, b = getattr(na, prop), getattr(nb, prop)
            if a == b:
                continue
            if prop in ("fill", "stroke", "text_color") and (not a or not b):
                # «нет цвета» ↔ цвет: плавно меняем прозрачность того же цвета
                a, b = (a or b[:7] + "00"), (b or a[:7] + "00")
                if prop == "stroke" and not getattr(nb, "stroke_width", 0) and not getattr(na, "stroke_width", 0):
                    continue
            anim.tracks.append(Track(nid, prop, [Keyframe(0, a, easing), Keyframe(duration, b, easing)]))
    return anim if anim.tracks else None
