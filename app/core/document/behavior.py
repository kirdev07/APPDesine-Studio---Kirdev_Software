"""Поведение прототипа: анимации (ключевые кадры), переменные и взаимодействия «событие → действия». Без Qt.

Логика декларативна: набор триггеров, условий и действий из фиксированного списка. Никакого выполнения
кода — значения проверяются по типам, текстовые шаблоны подставляют только значения переменных.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from app.core.document.model import ModelError, check_prop, new_id

ANIMATABLE = ("x", "y", "w", "h", "opacity", "radius", "fill", "stroke", "text_color", "font_size", "stroke_width",
              "scale", "rotation")
COLOR_PROPS = ("fill", "stroke", "text_color")
EASINGS = ("linear", "ease_in", "ease_out", "ease_in_out", "step", "cubic")
TRANSITIONS = ("none", "fade", "slide_left", "slide_right", "slide_up", "slide_down")
TRIGGERS = ("tap", "long_press", "hover_enter", "hover_leave", "screen_open", "double_tap", "swipe_left",
            "swipe_right", "swipe_up", "swipe_down", "text_changed")
# События сценария: всё, что делает пользователь (screen_open происходит само), плюс системные.
EVENTS = tuple(t for t in TRIGGERS if t not in ("screen_open", "text_changed")) + ("system_back", "text_input")
MAX_STEPS = 10_000
VAR_TYPES = ("bool", "number", "text")
OPS = ("==", "!=", "<", ">", "<=", ">=")
MAX_DURATION = 600_000  # 10 минут
_ID = re.compile(r"^[0-9A-Za-z_:./-]{1,512}$")
_NAME = re.compile(r"^[0-9A-Za-zА-Яа-яЁё_ -]{1,64}$")


def _id(v, what="идентификатор") -> str:
    if not isinstance(v, str) or not _ID.match(v):
        raise ModelError(f"Неверный {what}: {v!r}")
    return v


def _int(v, lo, hi, what) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        raise ModelError(f"«{what}» должно быть числом от {lo} до {hi}")
    return int(round(v))


def check_bezier(v) -> list[float]:
    if not isinstance(v, (list, tuple)) or len(v) != 4:
        raise ModelError("Кривая cubic-bezier задаётся четырьмя числами")
    out = [float(x) for x in v if not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x)]
    if len(out) != 4 or not (0 <= out[0] <= 1 and 0 <= out[2] <= 1) or any(abs(x) > 10 for x in out):
        raise ModelError("cubic-bezier: x1 и x2 должны быть в диапазоне 0…1")
    return out


def check_anim_value(prop: str, value):
    if prop not in ANIMATABLE:
        raise ModelError(f"Свойство «{prop}» не анимируется")
    v = check_prop(prop, value, "text")
    if prop in COLOR_PROPS and not v:
        raise ModelError("Цвет ключевого кадра не может быть пустым")
    return v


@dataclass
class Keyframe:
    t: int                   # время, мс от начала анимации
    value: object
    easing: str = "ease_in_out"   # плавность участка ОТ этого кадра к следующему
    bezier: list = field(default_factory=lambda: [0.25, 0.1, 0.25, 1.0])

    def to_dict(self) -> dict:
        return {"t": self.t, "value": self.value, "easing": self.easing, "bezier": list(self.bezier)}


@dataclass
class Track:
    node_id: str
    prop: str
    keyframes: list[Keyframe] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"node_id": self.node_id, "prop": self.prop, "keyframes": [k.to_dict() for k in self.keyframes]}


@dataclass
class Animation:
    name: str
    screen_id: str
    duration: int = 1000
    loop: bool = False
    tracks: list[Track] = field(default_factory=list)
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "screen_id": self.screen_id, "duration": self.duration,
                "loop": self.loop, "tracks": [t.to_dict() for t in self.tracks]}

    @classmethod
    def from_dict(cls, d: dict) -> Animation:
        if not isinstance(d, dict):
            raise ModelError("Анимация должна быть объектом")
        name = d.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ModelError("Неверное имя анимации")
        a = cls(name=name.strip(), screen_id=_id(d.get("screen_id"), "экран анимации"),
                duration=_int(d.get("duration", 1000), 1, MAX_DURATION, "длительность"),
                loop=bool(d.get("loop", False)), id=_id(d.get("id"), "id анимации"))
        tracks = d.get("tracks", [])
        if not isinstance(tracks, list) or len(tracks) > 1000:
            raise ModelError("Неверные дорожки анимации")
        seen = set()
        for td in tracks:
            if not isinstance(td, dict):
                raise ModelError("Дорожка должна быть объектом")
            prop = td.get("prop")
            if prop not in ANIMATABLE:
                raise ModelError(f"Свойство «{prop}» не анимируется")
            tr = Track(node_id=_id(td.get("node_id"), "узел дорожки"), prop=prop)
            if (tr.node_id, prop) in seen:
                raise ModelError("Повторяющаяся дорожка анимации")
            seen.add((tr.node_id, prop))
            kfs = td.get("keyframes", [])
            if not isinstance(kfs, list) or len(kfs) > 10_000:
                raise ModelError("Неверные ключевые кадры")
            for kd in kfs:
                if not isinstance(kd, dict):
                    raise ModelError("Ключевой кадр должен быть объектом")
                easing = kd.get("easing", "ease_in_out")
                if easing not in EASINGS:
                    raise ModelError(f"Неизвестная плавность: {easing!r}")
                tr.keyframes.append(Keyframe(t=_int(kd.get("t"), 0, a.duration, "время кадра"),
                                             value=check_anim_value(prop, kd.get("value")), easing=easing,
                                             bezier=check_bezier(kd.get("bezier", [0.25, 0.1, 0.25, 1.0]))))
            tr.keyframes.sort(key=lambda k: k.t)
            if len({k.t for k in tr.keyframes}) != len(tr.keyframes):
                raise ModelError("Два ключевых кадра в одно время на одной дорожке")
            a.tracks.append(tr)
        return a


@dataclass
class Variable:
    name: str
    type: str = "bool"
    default: object = False
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "type": self.type, "default": self.default}

    @classmethod
    def from_dict(cls, d: dict) -> Variable:
        if not isinstance(d, dict):
            raise ModelError("Переменная должна быть объектом")
        name = d.get("name")
        if not isinstance(name, str) or not _NAME.match(name):
            raise ModelError("Имя переменной: буквы, цифры, пробел, _ и - (до 64 символов)")
        vt = d.get("type")
        if vt not in VAR_TYPES:
            raise ModelError("Неверный тип переменной")
        return cls(name=name, type=vt, default=coerce(vt, d.get("default")), id=_id(d.get("id"), "id переменной"))


def coerce(var_type: str, value):
    """Приведение значения к типу переменной (без вычисления выражений)."""
    if var_type == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "да", "истина", "вкл")
        return bool(value)
    if var_type == "number":
        if isinstance(value, bool):
            return float(value)
        try:
            v = float(str(value).replace(",", ".")) if not isinstance(value, (int, float)) else float(value)
        except ValueError:
            raise ModelError(f"Не число: {value!r}") from None
        if not math.isfinite(v) or abs(v) > 1e15:
            raise ModelError("Число вне допустимого диапазона")
        return v
    s = "" if value is None else str(value)
    if len(s) > 10_000:
        raise ModelError("Слишком длинный текст")
    return s


# Действия: тип → обязательные поля и их проверка.
ACTION_FIELDS = {
    "navigate": ("screen_id", "transition", "duration", "easing"),
    "back": ("transition", "duration", "easing"),
    "set_variable": ("var_id", "mode", "value"),
    "set_state": ("node_id", "state"),
    "set_visible": ("node_id", "mode"),
    "set_text": ("node_id", "text"),
    "play_animation": ("animation_id",),
    "open_overlay": ("node_id",),
    "close_overlay": (),
}
ACTION_NAMES = {"navigate": "Перейти на экран", "back": "Назад", "set_variable": "Изменить переменную",
                "set_state": "Состояние компонента", "set_visible": "Показать / скрыть", "set_text": "Задать текст",
                "play_animation": "Запустить анимацию", "open_overlay": "Открыть всплывающее окно",
                "close_overlay": "Закрыть окно"}
VAR_MODES = ("set", "toggle", "increment", "decrement")
VIS_MODES = ("show", "hide", "toggle")


def check_action(d: dict) -> dict:
    if not isinstance(d, dict) or d.get("type") not in ACTION_FIELDS:
        raise ModelError(f"Неизвестное действие: {d.get('type') if isinstance(d, dict) else d!r}")
    t = d["type"]
    out = {"type": t}
    for f in ACTION_FIELDS[t]:
        v = d.get(f)
        if f in ("screen_id", "var_id", "node_id", "animation_id"):
            out[f] = _id(v, f)
        elif f == "transition":
            if (v or "none") not in TRANSITIONS:
                raise ModelError(f"Неизвестный переход: {v!r}")
            out[f] = v or "none"
        elif f == "duration":
            out[f] = _int(v if v is not None else 300, 0, 10_000, "длительность перехода")
        elif f == "easing":
            if (v or "ease_in_out") not in EASINGS[:5]:
                raise ModelError(f"Неизвестная плавность: {v!r}")
            out[f] = v or "ease_in_out"
        elif f == "mode":
            allowed = VAR_MODES if t == "set_variable" else VIS_MODES
            if v not in allowed:
                raise ModelError(f"Неверный режим действия: {v!r}")
            out[f] = v
        elif f == "state":
            out[f] = check_prop("state", v, "instance")
        else:  # value, text
            if v is not None and not isinstance(v, (str, int, float, bool)):
                raise ModelError("Значение действия должно быть числом, текстом или логическим")
            if isinstance(v, str) and len(v) > 10_000:
                raise ModelError("Слишком длинный текст действия")
            out[f] = "" if v is None else v
    return out


@dataclass
class Interaction:
    screen_id: str
    trigger: str
    node_id: str = ""          # источник события; для screen_open — пусто
    condition: dict | None = None   # {"var_id", "op", "value"}
    actions: list[dict] = field(default_factory=list)
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        return {"id": self.id, "screen_id": self.screen_id, "trigger": self.trigger, "node_id": self.node_id,
                "condition": dict(self.condition) if self.condition else None,
                "actions": [dict(a) for a in self.actions]}

    @classmethod
    def from_dict(cls, d: dict) -> Interaction:
        if not isinstance(d, dict):
            raise ModelError("Взаимодействие должно быть объектом")
        trig = d.get("trigger")
        if trig not in TRIGGERS:
            raise ModelError(f"Неизвестный триггер: {trig!r}")
        node = d.get("node_id") or ""
        if trig != "screen_open":
            node = _id(node, "элемент взаимодействия")
        cond = d.get("condition")
        if cond is not None:
            if not isinstance(cond, dict) or cond.get("op") not in OPS:
                raise ModelError("Неверное условие")
            val = cond.get("value")
            if not isinstance(val, (str, int, float, bool)):
                raise ModelError("Значение условия должно быть числом, текстом или логическим")
            cond = {"var_id": _id(cond.get("var_id"), "переменная условия"), "op": cond["op"], "value": val}
        acts = d.get("actions", [])
        if not isinstance(acts, list) or len(acts) > 100:
            raise ModelError("Неверный список действий (не больше 100)")
        return cls(screen_id=_id(d.get("screen_id"), "экран взаимодействия"), trigger=trig, node_id=node,
                   condition=cond, actions=[check_action(a) for a in acts], id=_id(d.get("id"), "id"))


def check_transition(v) -> dict:
    if not isinstance(v, dict):
        raise ModelError("Переход состояний должен быть объектом")
    easing = v.get("easing", "ease_in_out")
    if easing not in EASINGS[:5]:
        raise ModelError("Неизвестная плавность перехода")
    return {"duration": _int(v.get("duration", 150), 0, 5000, "длительность перехода"), "easing": easing}


def check_behavior(v) -> dict:
    """Встроенное поведение компонента в прототипе: наведение, нажатие, переключение между двумя состояниями."""
    if not isinstance(v, dict):
        raise ModelError("Поведение компонента должно быть объектом")
    toggle = v.get("toggle", [])
    if not isinstance(toggle, list) or len(toggle) not in (0, 2):
        raise ModelError("Переключение задаётся двумя состояниями")
    return {"hover": bool(v.get("hover", False)), "press": bool(v.get("press", False)),
            "toggle": [check_prop("state", s, "instance") for s in toggle]}


@dataclass
class Scenario:
    """Записанный сценарий предпросмотра: события пользователя и ожидаемый итог (экран, переменные)."""
    name: str
    start_screen_id: str
    steps: list = field(default_factory=list)       # [триггер, узел] или [«text_input», узел, текст]
    expect_screen_id: str = ""
    expect_vars: dict = field(default_factory=dict)  # var_id → значение
    digest: str = ""                                 # хэш полного состояния на момент записи
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "start_screen_id": self.start_screen_id,
                "steps": [list(s) for s in self.steps], "expect_screen_id": self.expect_screen_id,
                "expect_vars": dict(self.expect_vars), "digest": self.digest}

    @classmethod
    def from_dict(cls, d: dict) -> Scenario:
        if not isinstance(d, dict):
            raise ModelError("Сценарий должен быть объектом")
        name = d.get("name")
        if not isinstance(name, str) or not 1 <= len(name) <= 128:
            raise ModelError("Неверное имя сценария")
        steps = d.get("steps", [])
        if not isinstance(steps, list) or len(steps) > MAX_STEPS:
            raise ModelError(f"Неверный список шагов сценария (не больше {MAX_STEPS})")
        out = []
        for st in steps:
            if not isinstance(st, list) or len(st) not in (2, 3) or st[0] not in EVENTS:
                raise ModelError("Неверный шаг сценария")
            node = st[1] if st[0] == "system_back" and not st[1] else _id(st[1], "элемент шага")
            if st[0] == "text_input":
                if len(st) != 3 or not isinstance(st[2], str) or len(st[2]) > 10_000:
                    raise ModelError("Шаг ввода текста должен содержать строку")
                out.append([st[0], node, st[2]])
            elif len(st) == 2:
                out.append([st[0], node])
            else:
                raise ModelError("Лишнее значение в шаге сценария")
        ev = d.get("expect_vars", {})
        if not isinstance(ev, dict) or not all(isinstance(v, (str, int, float, bool)) for v in ev.values()):
            raise ModelError("Неверные ожидаемые значения переменных")
        digest = d.get("digest", "")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{0,64}", digest):
            raise ModelError("Неверный хэш сценария")
        exp = d.get("expect_screen_id") or ""
        return cls(name=name, start_screen_id=_id(d.get("start_screen_id"), "стартовый экран"), steps=out,
                   expect_screen_id=_id(exp, "ожидаемый экран") if exp else "",
                   expect_vars={_id(k, "переменная"): v for k, v in ev.items()}, digest=digest,
                   id=_id(d.get("id"), "id"))
