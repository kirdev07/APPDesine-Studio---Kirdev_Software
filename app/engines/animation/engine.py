"""Модуль 07 — Animation Engine: плавности, интерполяция, выборка анимации по времени, проверка. Без Qt.

Результат зависит только от анимации и времени, поэтому воспроизведение детерминировано: одна и та же
последовательность моментов времени даёт одинаковые кадры. Режим «уменьшить движение» сразу даёт
конечное состояние без промежуточных кадров.
"""

from __future__ import annotations

import math

from app.core.document import tree
from app.core.document.behavior import COLOR_PROPS, Animation, Track
from app.core.document.model import ProjectDocument
from app.engines.layout import Diagnostic


def cubic_bezier(x1: float, y1: float, x2: float, y2: float, t: float) -> float:
    """CSS cubic-bezier: находим параметр s, при котором x(s)=t, и возвращаем y(s)."""
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0

    def bx(s):
        return 3 * x1 * s * (1 - s) ** 2 + 3 * x2 * s * s * (1 - s) + s ** 3

    def by(s):
        return 3 * y1 * s * (1 - s) ** 2 + 3 * y2 * s * s * (1 - s) + s ** 3

    lo, hi, s = 0.0, 1.0, t
    for _ in range(40):  # бисекция: всегда сходится, детерминирована
        x = bx(s)
        if abs(x - t) < 1e-7:
            break
        if x < t:
            lo = s
        else:
            hi = s
        s = (lo + hi) / 2
    return by(s)


PRESETS = {"ease_in": (0.42, 0.0, 1.0, 1.0), "ease_out": (0.0, 0.0, 0.58, 1.0), "ease_in_out": (0.42, 0.0, 0.58, 1.0)}


def ease(name: str, t: float, bezier=None) -> float:
    t = max(0.0, min(1.0, t))
    if name == "linear":
        return t
    if name == "step":
        return 0.0 if t < 1 else 1.0
    if name == "cubic":
        return cubic_bezier(*(bezier or (0.25, 0.1, 0.25, 1.0)), t)
    return cubic_bezier(*PRESETS.get(name, PRESETS["ease_in_out"]), t)


def _rgba(c: str) -> tuple[int, int, int, int]:
    v = c.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16), int(v[6:8], 16) if len(v) == 8 else 255


def lerp_color(a: str, b: str, t: float) -> str:
    ca, cb = _rgba(a), _rgba(b)
    r, g, bl, al = (round(x + (y - x) * t) for x, y in zip(ca, cb))
    return f"#{r:02X}{g:02X}{bl:02X}" + ("" if al >= 255 else f"{al:02X}")


def interpolate(prop: str, a, b, t: float):
    if prop in COLOR_PROPS:
        return lerp_color(a, b, t)
    v = a + (b - a) * t
    return round(v, 3)


def sample_track(track: Track, t_ms: float):
    kfs = track.keyframes
    if not kfs:
        return None
    if t_ms <= kfs[0].t:
        return kfs[0].value
    if t_ms >= kfs[-1].t:
        return kfs[-1].value
    for k0, k1 in zip(kfs, kfs[1:]):
        if k0.t <= t_ms <= k1.t:
            local = (t_ms - k0.t) / (k1.t - k0.t) if k1.t > k0.t else 1.0
            return interpolate(track.prop, k0.value, k1.value, ease(k0.easing, local, k0.bezier))
    return kfs[-1].value


def local_time(anim: Animation, elapsed_ms: float, reduced_motion: bool = False) -> float:
    if reduced_motion:
        return float(anim.duration)
    if anim.loop and anim.duration > 0:
        return elapsed_ms % anim.duration
    return min(float(elapsed_ms), float(anim.duration))


def sample(anim: Animation, elapsed_ms: float, reduced_motion: bool = False) -> dict[str, dict]:
    """Значения всех дорожек в момент elapsed_ms: {node_id: {свойство: значение}}."""
    t = local_time(anim, elapsed_ms, reduced_motion)
    out: dict[str, dict] = {}
    for tr in anim.tracks:
        v = sample_track(tr, t)
        if v is not None:
            out.setdefault(tr.node_id, {})[tr.prop] = v
    return out


def finished(anim: Animation, elapsed_ms: float, reduced_motion: bool = False) -> bool:
    return reduced_motion or (not anim.loop and elapsed_ms >= anim.duration)


def frames(anim: Animation, fps: int = 60, reduced_motion: bool = False) -> list[dict]:
    """Все кадры одного прохода — для проверки детерминизма и экспорта."""
    if reduced_motion:
        return [sample(anim, anim.duration, True)]
    step = 1000 / fps
    n = max(1, math.ceil(anim.duration / step))
    return [sample(anim, min(i * step, anim.duration)) for i in range(n + 1)]


def validate(doc: ProjectDocument) -> list[Diagnostic]:
    diags = []
    screens = {s.id: s for s in doc.screens}
    for a in doc.animations:
        s = screens.get(a.screen_id)
        if s is None:
            diags.append(Diagnostic("warning", "", f"Анимация «{a.name}»: экран удалён"))
            continue
        nodes = tree.node_map(s)
        if not a.tracks:
            diags.append(Diagnostic("info", "", f"Анимация «{a.name}»: нет дорожек"))
        for tr in a.tracks:
            n = nodes.get(tr.node_id)
            if n is None:
                diags.append(Diagnostic("warning", "", f"Анимация «{a.name}»: элемент дорожки «{tr.prop}» удалён"))
                continue
            if len(tr.keyframes) < 2:
                diags.append(Diagnostic("info", n.id, f"Анимация «{a.name}»: у дорожки «{tr.prop}» элемента "
                                                      f"«{n.name}» меньше двух ключевых кадров"))
            if tr.prop in ("font_size",) and n.type != "text":
                diags.append(Diagnostic("info", n.id, f"Анимация «{a.name}»: размер шрифта у не-текста не действует"))
            if n.ref:
                diags.append(Diagnostic("warning", n.id, f"Анимация «{a.name}»: элемент внутри экземпляра — "
                                                         "геометрию задаёт мастер"))
    return diags
