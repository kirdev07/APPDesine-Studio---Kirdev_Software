"""Тестовые сценарии предпросмотра: запись из сеанса, прогон, проверка ожидаемого итога. Без Qt.

Шаги ссылаются на элементы по идентификатору, а не на координаты, поэтому сценарий одинаково проходит
на любом устройстве, ориентации и плотности.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.document import tree
from app.core.document.behavior import Scenario
from app.core.document.model import ProjectDocument
from app.engines.layout.engine import Diagnostic
from app.engines.logic.engine import Interpreter, format_value


@dataclass
class ScenarioResult:
    ok: bool
    messages: list[str] = field(default_factory=list)
    digest: str = ""
    steps_run: int = 0


def record(interp: Interpreter, name: str) -> Scenario:
    st = interp.state
    return Scenario(name=name, start_screen_id=interp.start, steps=[list(s) for s in interp.log],
                    expect_screen_id=st.screen_id, expect_vars=dict(sorted(st.variables.items())),
                    digest=st.digest())


def run(doc: ProjectDocument, sc: Scenario) -> ScenarioResult:
    names = {s.id: s.name for s in doc.screens}
    if sc.start_screen_id not in names:
        return ScenarioResult(False, ["Стартовый экран сценария удалён"])
    interp = Interpreter(doc, sc.start_screen_id)
    res = ScenarioResult(True)
    for n, step in enumerate(sc.steps, 1):
        trig, nid = step[0], step[1]
        if trig != "system_back":
            s = interp.screen()
            if s is None or nid not in tree.node_map(s):
                res.ok = False
                res.messages.append(f"Шаг {n}: элемент не найден на экране «{names.get(interp.state.screen_id, '?')}»")
                break
        effects = interp.dispatch(*step)
        res.steps_run = n
        for e in effects:
            if e.kind == "error":
                res.ok = False
                res.messages.append(f"Шаг {n}: {e.data.get('message', 'ошибка')}")
    st = interp.state
    res.digest = st.digest()
    if sc.expect_screen_id and st.screen_id != sc.expect_screen_id:
        res.ok = False
        res.messages.append(f"Итоговый экран «{names.get(st.screen_id, '?')}», ожидался "
                            f"«{names.get(sc.expect_screen_id, 'удалён')}»")
    for vid, expected in sc.expect_vars.items():
        v = doc.variable(vid)
        if v is None:
            res.messages.append("⚠ Переменная из сценария удалена — проверка пропущена")
            continue
        got = st.variables.get(vid, v.default)
        if got != expected:
            res.ok = False
            res.messages.append(f"«{v.name}» = {format_value(got)}, ожидалось {format_value(expected)}")
    if res.ok and sc.digest and res.digest != sc.digest:
        res.messages.append("⚠ Экран и переменные совпали, но другие детали состояния (состояния компонентов, "
                            "тексты, окна) отличаются от записи")
    if res.ok and not res.messages:
        res.messages.append(f"✓ Пройдено: шагов {len(sc.steps)}, итог совпадает с записью")
    return res


def validate(doc: ProjectDocument) -> list[Diagnostic]:
    ids = {s.id for s in doc.screens}
    return [Diagnostic("warning", "", f"Сценарий «{sc.name}»: стартовый экран удалён")
            for sc in doc.scenarios if sc.start_screen_id not in ids]
