"""Готовые анимации в один щелчок: появление, выезд, увеличение, пружина, пульс, встряска, вращение, мерцание,
парение, появление по очереди. Без Qt.

Каждая заготовка строит обычную анимацию проекта (дорожки с ключевыми кадрами) для выбранного элемента: её видно
и можно поправить в студии «Анимации», она играет в предпросмотре и переводится в код Compose. Смещения задаются
в dp и пересчитываются в пиксели экрана (k — пикселей в dp).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.core.document.behavior import Animation, Keyframe, Track


@dataclass(frozen=True)
class Preset:
    key: str
    name: str
    hint: str
    build: Callable  # (node, k) -> (длительность, по кругу, [Track])
    entrance: bool = True  # «появление» — уместно при открытии экрана


def _t(node_id: str, prop: str, frames: list[tuple[int, object, str]]) -> Track:
    by_time: dict[int, tuple] = {}
    for t, v, e in frames:  # один кадр на момент времени (последний побеждает)
        by_time[t] = (v, e)
    return Track(node_id=node_id, prop=prop,
                 keyframes=[Keyframe(t=t, value=v, easing=e) for t, (v, e) in sorted(by_time.items())])


def _fade_in(n, k):
    return 400, False, [_t(n.id, "opacity", [(0, 0.0, "ease_out"), (400, n.opacity, "linear")])]


def _slide_up(n, k):
    return 450, False, [_t(n.id, "opacity", [(0, 0.0, "ease_out"), (300, n.opacity, "linear")]),
                        _t(n.id, "y", [(0, round(n.y + 40 * k, 2), "ease_out"), (450, n.y, "linear")])]


def _slide_in(n, k):
    return 450, False, [_t(n.id, "opacity", [(0, 0.0, "ease_out"), (300, n.opacity, "linear")]),
                        _t(n.id, "x", [(0, round(n.x + 48 * k, 2), "ease_out"), (450, n.x, "linear")])]


def _pop(n, k):
    return 500, False, [_t(n.id, "opacity", [(0, 0.0, "ease_out"), (200, n.opacity, "linear")]),
                        _t(n.id, "scale", [(0, 0.6, "ease_out"), (320, 1.08, "ease_in_out"), (500, 1.0, "linear")])]


def _bounce(n, k):
    y = n.y
    return 800, False, [_t(n.id, "y", [(0, y, "ease_out"), (200, round(y - 18 * k, 2), "ease_in"),
                                         (400, y, "ease_out"), (550, round(y - 7 * k, 2), "ease_in"),
                                         (700, y, "ease_out"), (800, y, "linear")])]


def _pulse(n, k):
    return 1200, True, [_t(n.id, "scale", [(0, 1.0, "ease_in_out"), (600, 1.08, "ease_in_out"),
                                             (1200, 1.0, "linear")])]


def _shake(n, k):
    x = n.x
    pts = [(0, 0), (80, -10), (160, 10), (240, -8), (320, 8), (400, -4), (480, 0)]
    return 480, False, [_t(n.id, "x", [(t, round(x + d * k, 2), "ease_in_out") for t, d in pts])]


def _spin(n, k):
    return 1000, True, [_t(n.id, "rotation", [(0, 0.0, "linear"), (1000, 360.0, "linear")])]


def _blink(n, k):
    return 1200, True, [_t(n.id, "opacity", [(0, n.opacity, "ease_in_out"), (600, round(n.opacity * 0.35, 3),
                                                                             "ease_in_out"),
                                               (1200, n.opacity, "linear")])]


def _float(n, k):
    y = n.y
    return 2400, True, [_t(n.id, "y", [(0, y, "ease_in_out"), (1200, round(y - 8 * k, 2), "ease_in_out"),
                                         (2400, y, "linear")])]


def _stagger(n, k):
    """Дети контейнера появляются по очереди снизу (шаг 70 мс)."""
    kids = [c for c in n.children if c.visible] or [n]
    tracks = []
    step, each = 70, 380
    for i, c in enumerate(kids[:12]):
        t0 = i * step
        tracks.append(_t(c.id, "opacity", [(0, 0.0, "linear"), (t0, 0.0, "ease_out"), (t0 + each, c.opacity,
                                                                                          "linear")]))
        tracks.append(_t(c.id, "y", [(0, round(c.y + 24 * k, 2), "linear"), (t0, round(c.y + 24 * k, 2),
                                                                               "ease_out"),
                                     (t0 + each, c.y, "linear")]))
    total = (min(len(kids), 12) - 1) * step + each
    for tr in tracks:  # все дорожки — одной длины
        if tr.keyframes[-1].t < total:
            tr.keyframes.append(Keyframe(t=total, value=tr.keyframes[-1].value, easing="linear"))
    return total, False, tracks


PRESETS: tuple[Preset, ...] = (
    Preset("fade_in", "Появление", "Плавно проявляется из прозрачного", _fade_in),
    Preset("slide_up", "Выезд снизу", "Поднимается на 40 dp и проявляется", _slide_up),
    Preset("slide_in", "Выезд сбоку", "Въезжает справа и проявляется", _slide_in),
    Preset("pop", "Увеличение с отскоком", "Вырастает из 60 % с лёгким перелётом", _pop),
    Preset("stagger", "Появление по очереди", "Вложенные элементы появляются друг за другом (для списков)",
           _stagger),
    Preset("bounce", "Прыжок", "Подпрыгивает и приземляется", _bounce, entrance=False),
    Preset("shake", "Встряска", "Качается влево-вправо — например, при ошибке", _shake, entrance=False),
    Preset("pulse", "Пульс (по кругу)", "Плавно увеличивается и уменьшается", _pulse, entrance=False),
    Preset("spin", "Вращение (по кругу)", "Крутится — например, значок загрузки", _spin, entrance=False),
    Preset("blink", "Мерцание (по кругу)", "Плавно гаснет и загорается — заготовка загрузки", _blink,
           entrance=False),
    Preset("float", "Парение (по кругу)", "Медленно покачивается вверх-вниз", _float, entrance=False),
)


def preset(key: str) -> Preset:
    return next(p for p in PRESETS if p.key == key)


def build(key: str, node, screen_id: str, k: float) -> Animation:
    p = preset(key)
    duration, loop, tracks = p.build(node, k)
    a = Animation(name=f"{p.name} · {node.name or 'элемент'}", screen_id=screen_id, duration=duration, loop=loop,
                  tracks=tracks)
    return Animation.from_dict(a.to_dict())  # те же проверки, что у анимаций из файла
