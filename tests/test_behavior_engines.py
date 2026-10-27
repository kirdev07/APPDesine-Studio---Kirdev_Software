"""Движки анимации и логики (S15, S16): плавности, выборка, детерминизм, безопасность, повтор, проверки."""

import json

import pytest

from app.core.document.behavior import Animation, Interaction, Keyframe, Track, Variable, check_action
from app.core.document.model import ModelError, Node, Screen
from app.core.persistence.container import load_project, save_project
from app.core.project.service import build_document
from app.engines.animation import engine as anim
from app.engines.components import engine as ce
from app.engines.layout import LayoutEngine, SimpleMeasurer
from app.engines.logic.engine import Interpreter, render_template, validate
from tests.conftest import make_spec


def test_easings_and_bezier():
    for name in ("linear", "ease_in", "ease_out", "ease_in_out", "cubic"):
        assert anim.ease(name, 0) == 0 and anim.ease(name, 1) == 1
    assert anim.ease("linear", 0.3) == pytest.approx(0.3)
    assert anim.ease("ease_in", 0.5) < 0.5 < anim.ease("ease_out", 0.5)
    assert anim.ease("ease_in_out", 0.5) == pytest.approx(0.5, abs=1e-6)
    assert anim.ease("step", 0.99) == 0 and anim.ease("step", 1) == 1
    # cubic-bezier(0,0,1,1) — линейная
    assert anim.cubic_bezier(0, 0, 1, 1, 0.37) == pytest.approx(0.37, abs=1e-6)
    # выход за 0…1 по y («пружина») допустим
    assert anim.ease("cubic", 0.5, [0.3, 1.6, 0.6, 1.0]) > 1.0


def make_anim(loop=False):
    a = Animation(name="Появление", screen_id="s", duration=1000, loop=loop)
    a.tracks.append(Track("n", "opacity", [Keyframe(0, 0.0, "linear"), Keyframe(1000, 1.0)]))
    a.tracks.append(Track("n", "fill", [Keyframe(0, "#000000", "linear"), Keyframe(500, "#FF0000")]))
    a.tracks.append(Track("n", "x", [Keyframe(200, 10.0, "ease_out"), Keyframe(800, 110.0)]))
    return a


def test_sampling_values():  # S16
    a = make_anim()
    assert anim.sample(a, 0) == {"n": {"opacity": 0.0, "fill": "#000000", "x": 10.0}}
    mid = anim.sample(a, 500)["n"]
    assert mid["opacity"] == 0.5 and mid["fill"] == "#FF0000"
    assert anim.sample(a, 250)["n"]["fill"] == "#800000"
    assert anim.sample(a, 100)["n"]["x"] == 10.0          # до первого кадра — его значение
    assert 60 < anim.sample(a, 500)["n"]["x"] < 110       # ease_out: быстрее линейного
    assert anim.sample(a, 5000)["n"]["opacity"] == 1.0    # после конца — конечное значение
    assert anim.finished(a, 1000) and not anim.finished(a, 999)


def test_loop_and_reduced_motion():
    a = make_anim(loop=True)
    assert anim.sample(a, 1250) == anim.sample(a, 250)
    assert not anim.finished(a, 10_000)
    assert anim.sample(a, 0, reduced_motion=True) == anim.sample(make_anim(), 1000)
    assert len(anim.frames(a, reduced_motion=True)) == 1


def test_frames_are_deterministic():  # S16
    f1 = json.dumps(anim.frames(make_anim(), 60), sort_keys=True)
    f2 = json.dumps(anim.frames(Animation.from_dict(make_anim().to_dict()), 60), sort_keys=True)
    assert f1 == f2 and len(anim.frames(make_anim(), 60)) == 61


def test_animation_validation_rejects_garbage():
    base = make_anim().to_dict()
    for bad in [
        {**base, "duration": -5},
        {**base, "tracks": [{"node_id": "n", "prop": "text", "keyframes": []}]},
        {**base, "tracks": [{"node_id": "n", "prop": "fill", "keyframes": [{"t": 0, "value": "red"}]}]},
        {**base, "tracks": [{"node_id": "n", "prop": "x", "keyframes": [{"t": 0, "value": 1}, {"t": 0, "value": 2}]}]},
        {**base, "tracks": [{"node_id": "n", "prop": "x", "keyframes": [{"t": 5000, "value": 1}]}]},
        {**base, "tracks": [{"node_id": "n", "prop": "x", "keyframes": [{"t": 0, "value": 1, "easing": "spring"}]}]},
    ]:
        with pytest.raises(ModelError):
            Animation.from_dict(bad)


# ---------------- логика ----------------

def proto():
    """Прототип: вход → (если согласие) главная; на главной счётчик и переключатель; назад."""
    doc = build_document(make_spec(".", title="Прототип"))
    login = doc.screens[0]
    login.name = "Вход"
    btn = Node(type="rect", name="Войти", x=0, y=0, w=100, h=40)
    label = Node(type="text", name="Подпись", text="Войти", x=0, y=0, w=100, h=40, fill="")
    btn_frame = Node(type="frame", name="Кнопка", x=0, y=0, w=100, h=40, children=[btn, label])
    agree = Node(type="rect", name="Согласие", x=0, y=60, w=20, h=20)
    error = Node(type="text", name="Ошибка", text="Нужно согласие", x=0, y=100, w=200, h=20, visible=False, fill="")
    login.nodes += [btn_frame, agree, error]
    home = Screen(name="Главная", platform="android", width=1080, height=2400)
    plus = Node(type="rect", name="Плюс", x=0, y=0, w=50, h=50)
    counter = Node(type="text", name="Счётчик", text="0", x=0, y=60, w=200, h=30, fill="")
    back = Node(type="rect", name="Назад", x=0, y=100, w=50, h=50)
    dialog = Node(type="frame", name="Диалог", x=0, y=200, w=300, h=200, visible=False)
    home.nodes += [plus, counter, back, dialog]
    doc.screens.append(home)
    v_agree = Variable("Согласие", "bool", False)
    v_count = Variable("Счёт", "number", 0)
    doc.variables += [v_agree, v_count]
    fade = Animation(name="Пульс", screen_id=home.id, duration=300,
                     tracks=[Track(plus.id, "opacity", [Keyframe(0, 1.0), Keyframe(150, 0.5), Keyframe(300, 1.0)])])
    doc.animations.append(fade)
    I = Interaction
    doc.interactions += [
        I(login.id, "tap", agree.id, actions=[{"type": "set_variable", "var_id": v_agree.id, "mode": "toggle",
                                               "value": ""}]),
        I(login.id, "tap", btn_frame.id, condition={"var_id": v_agree.id, "op": "==", "value": True},
          actions=[{"type": "navigate", "screen_id": home.id, "transition": "slide_left", "duration": 300,
                    "easing": "ease_out"}, {"type": "set_visible", "node_id": error.id, "mode": "show"}]),
        I(login.id, "tap", btn_frame.id, condition={"var_id": v_agree.id, "op": "==", "value": False},
          actions=[{"type": "set_visible", "node_id": error.id, "mode": "show"}]),
        I(home.id, "screen_open", "", actions=[{"type": "set_text", "node_id": counter.id,
                                               "text": "Счёт: {Счёт}"}]),
        I(home.id, "tap", plus.id, actions=[
            {"type": "set_variable", "var_id": v_count.id, "mode": "increment", "value": 1},
            {"type": "set_text", "node_id": counter.id, "text": "Счёт: {Счёт}, согласие {Согласие} {__import__}"},
            {"type": "play_animation", "animation_id": fade.id},
            {"type": "open_overlay", "node_id": dialog.id}]),
        I(home.id, "tap", back.id, actions=[{"type": "back", "transition": "fade", "duration": 200,
                                             "easing": "linear"}]),
    ]
    for it in doc.interactions:
        it.actions = [check_action(a) for a in it.actions]
    doc.validate()
    return doc, dict(login=login, home=home, btn=btn, label=label, btn_frame=btn_frame, agree=agree, error=error,
                     plus=plus, counter=counter, back=back, dialog=dialog)


def test_multiscreen_logic_flow():  # S15
    doc, n = proto()
    it = Interpreter(doc)
    assert it.state.screen_id == n["login"].id
    eff = it.dispatch("tap", n["label"].id)  # нажатие на подпись всплывает к кнопке-фрейму
    assert it.state.screen_id == n["login"].id and it.state.visibility[n["error"].id] is True
    assert [e.kind for e in eff] == ["visible"]
    it.dispatch("tap", n["agree"].id)
    eff = it.dispatch("tap", n["btn"].id)
    assert it.state.screen_id == n["home"].id
    assert eff[0].kind == "navigate" and eff[0].data["transition"] == "slide_left"
    assert "visible" not in [e.kind for e in eff]  # действие после перехода не выполнено
    assert it.state.texts[n["counter"].id] == "Счёт: 0"   # screen_open нового экрана
    eff = it.dispatch("tap", n["plus"].id)
    assert it.state.variables[doc.variables[1].id] == 1
    # шаблон подставляет только переменные; {__import__} остаётся текстом
    assert it.state.texts[n["counter"].id] == "Счёт: 1, согласие да {__import__}"
    assert [e.kind for e in eff] == ["variable", "text", "animation", "overlay_open"]
    assert it.state.overlays == [n["dialog"].id] and it.is_visible(n["dialog"])
    it.dispatch("tap", n["back"].id)
    assert it.state.screen_id == n["login"].id and it.state.overlays == []


def test_replay_is_deterministic():  # S15/S16
    doc, n = proto()
    it = Interpreter(doc)
    for ev in [("tap", n["btn"].id), ("tap", n["agree"].id), ("tap", n["btn"].id), ("tap", n["plus"].id),
               ("tap", n["plus"].id), ("tap", n["back"].id), ("hover_enter", n["btn"].id)]:
        it.dispatch(*ev)
    final = it.state.digest()
    script = list(it.log)
    h1, e1 = Interpreter(doc).replay(script)
    h2, e2 = Interpreter(Interpreter(doc).doc).replay(script)
    assert h1 == h2 == final and e1 == e2
    # после сохранения и загрузки проекта сценарий даёт тот же результат
    p = __import__("pathlib").Path(__import__("tempfile").mkdtemp()) / "прототип.adsproj"
    save_project(doc, p)
    h3, e3 = Interpreter(load_project(p)).replay(script)
    assert h3 == final and e3 == e1


def test_navigation_cycle_is_stopped_and_reported():
    doc, n = proto()
    login, home = n["login"], n["home"]
    nav = lambda sid: {"type": "navigate", "screen_id": sid, "transition": "none", "duration": 0,
                       "easing": "linear"}
    doc.interactions = [Interaction(login.id, "screen_open", "", actions=[check_action(nav(home.id))]),
                        Interaction(home.id, "screen_open", "", actions=[check_action(nav(login.id))])]
    it = Interpreter(doc)
    assert any(e.kind == "error" and "Цикл" in e.data["message"] for e in it.effects)
    assert any("бесконечный цикл" in d.message for d in validate(doc))


def test_validation_finds_dangling_and_type_errors():
    doc, n = proto()
    home = n["home"]
    doc.screens.remove(home)
    doc.variables[1].type = "text"
    msgs = " | ".join(d.message for d in validate(doc))
    assert "экран взаимодействия удалён" in msgs
    assert "экран удалён" in msgs
    doc, n = proto()
    doc.interactions[4].actions[0]["mode"] = "increment"
    doc.variables[1].type = "bool"
    assert any("только для числа" in d.message for d in validate(doc))


def test_actions_are_whitelisted():
    for bad in [{"type": "exec", "code": "import os"}, {"type": "navigate", "screen_id": "x", "transition": "boom"},
                {"type": "set_variable", "var_id": "v", "mode": "eval", "value": 1},
                {"type": "set_text", "node_id": "n", "text": {"__class__": 1}}]:
        with pytest.raises(ModelError):
            check_action(bad)
    assert render_template("{нет такой} {}", build_document(make_spec(".")), {}) == "{нет такой} {}"


def test_component_behavior_toggle_and_hover():
    doc, n = proto()
    eng = LayoutEngine(SimpleMeasurer())
    login = n["login"]
    defn, inst = ce.create_component(doc, login, [n["agree"].id], "Флажок", eng)
    defn.states = {"on": {"__root__": {"fill": "#00FF00"}}, "hover": {"__root__": {"opacity": 0.8}}}
    defn.behavior = {"hover": True, "press": False, "toggle": ["default", "on"]}
    doc.interactions = [i for i in doc.interactions if i.node_id != n["agree"].id]
    it = Interpreter(doc)
    it.dispatch("hover_enter", inst.id)
    assert it.state.states[inst.id] == "hover"
    it.dispatch("hover_leave", inst.id)
    it.dispatch("tap", inst.id)
    assert it.state.states[inst.id] == "on"
    it.dispatch("hover_enter", inst.id)
    assert it.state.states[inst.id] == "on"   # включённый переключатель не теряет состояние при наведении
    it.dispatch("tap", inst.id)
    assert it.state.states[inst.id] == "default"


def test_behavior_roundtrip_in_project(tmp_path):
    doc, n = proto()
    p = tmp_path / "логика.adsproj"
    save_project(doc, p)
    loaded = load_project(p)
    assert loaded.to_dict() == json.loads(json.dumps(doc.to_dict()))


def test_back_runs_screen_open_of_destination():
    doc, n = proto()
    doc.interactions.append(Interaction(n["login"].id, "screen_open", "", actions=[check_action(
        {"type": "set_text", "node_id": n["label"].id, "text": "Счёт {Счёт}"})]))
    it = Interpreter(doc)
    assert it.state.texts[n["label"].id] == "Счёт 0"
    it.dispatch("tap", n["agree"].id)
    it.dispatch("tap", n["btn"].id)
    it.dispatch("tap", n["plus"].id)
    it.dispatch("tap", n["back"].id)
    assert it.state.screen_id == n["login"].id and it.state.texts[n["label"].id] == "Счёт 1"
