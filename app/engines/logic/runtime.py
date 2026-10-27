"""Сборка «живого» экрана прототипа: копия экрана с текущим состоянием логики и кадром анимаций. Без Qt."""

from __future__ import annotations

from app.core.document import tree
from app.core.document.behavior import ANIMATABLE, Animation, Keyframe, Track
from app.core.document.model import ModelError, ProjectDocument, Screen, check_prop
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
    for nid, inst_state in state.states.items():
        inst = m.get(nid)
        defn = doc.component(inst.component_id) if inst is not None and inst.is_instance else None
        if defn is not None:
            inst.state = inst_state
            ce.materialize(defn, inst, engine)
    m = tree.node_map(clone)
    for nid, vis in state.visibility.items():
        if nid in m:
            m[nid].visible = vis
    for nid in state.overlays:
        if nid in m:
            m[nid].visible = True
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
