"""Модуль 08 — Visual Logic Engine: безопасный интерпретатор декларативных взаимодействий. Без Qt.

Нет eval/exec и вычисления выражений: условия — сравнение переменной со значением, действия — из
фиксированного списка, текстовые шаблоны подставляют только значения переменных по имени {Имя}.
Интерпретатор детерминирован: одинаковая последовательность событий от одного начального состояния
даёт одинаковые эффекты и итоговое состояние (это используется для повтора сценариев).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from app.core.document import tree
from app.core.document.behavior import ACTION_NAMES, Interaction, coerce
from app.core.document.model import ProjectDocument
from app.engines.layout import Diagnostic

MAX_DEPTH = 8          # вложенные screen_open → navigate
MAX_ACTIONS = 1000     # на одно событие
_TEMPLATE = re.compile(r"\{([0-9A-Za-zА-Яа-яЁё_ -]{1,64})\}")


@dataclass
class Effect:
    kind: str   # navigate, back, animation, state, visible, text, variable, overlay_open, overlay_close, error
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": self.kind, **self.data}


@dataclass
class RuntimeState:
    screen_id: str
    history: list[str] = field(default_factory=list)
    variables: dict = field(default_factory=dict)    # var_id → значение
    states: dict = field(default_factory=dict)       # node_id экземпляра → состояние
    variants: dict = field(default_factory=dict)     # node_id экземпляра → {свойство варианта: значение}
    visibility: dict = field(default_factory=dict)   # node_id → bool
    texts: dict = field(default_factory=dict)        # node_id → текст
    overlays: list[str] = field(default_factory=list)

    def snapshot(self) -> dict:
        return {"screen_id": self.screen_id, "history": list(self.history),
                "variables": dict(sorted(self.variables.items())), "states": dict(sorted(self.states.items())),
                "visibility": dict(sorted(self.visibility.items())), "texts": dict(sorted(self.texts.items())),
                "overlays": list(self.overlays),
                **({"variants": {k: dict(sorted(v.items())) for k, v in sorted(self.variants.items())}}
                   if self.variants else {})}

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.snapshot(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def render_template(text: str, doc: ProjectDocument, variables: dict) -> str:
    by_name = {v.name: v for v in doc.variables}

    def sub(m):
        v = by_name.get(m.group(1))
        if v is None:
            return m.group(0)
        return format_value(variables.get(v.id, v.default))
    return _TEMPLATE.sub(sub, text)


def format_value(val) -> str:
    if isinstance(val, bool):
        return "да" if val else "нет"
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val)


def compare(a, op: str, b) -> bool:
    try:
        if op == "==":
            return a == b
        if op == "!=":
            return a != b
        if op == "<":
            return a < b
        if op == ">":
            return a > b
        if op == "<=":
            return a <= b
        return a >= b
    except TypeError:
        return False


class Interpreter:
    def __init__(self, doc: ProjectDocument, start_screen_id: str | None = None):
        self.doc = doc
        self.start = start_screen_id or (doc.screens[0].id if doc.screens else "")
        self.log: list[tuple] = []                # (триггер, узел[, текст]) — сценарий для повтора
        self.effects: list[Effect] = []           # все эффекты по порядку
        self.reset()

    # ---------- состояние ----------
    def reset(self) -> list[Effect]:
        self.state = RuntimeState(screen_id=self.start,
                                  variables={v.id: v.default for v in self.doc.variables})
        self.log, self.effects = [], []
        return self._fire_screen_open(0)

    def screen(self):
        return next((s for s in self.doc.screens if s.id == self.state.screen_id), None)

    def is_visible(self, node) -> bool:
        if node.id in self.state.overlays:
            return True
        return self.state.visibility.get(node.id, node.visible)

    # ---------- события ----------
    def dispatch(self, trigger: str, node_id: str = "", value: str | None = None) -> list[Effect]:
        """Событие от пользователя. Срабатывает самое внутреннее взаимодействие по цепочке предков узла.

        text_input — ввод в поле (value — весь текст поля): текст сохраняется в состоянии, связанная
        переменная получает значение, затем срабатывает «Изменение текста» (text_changed) по цепочке.
        """
        self.log.append((trigger, node_id) if value is None else (trigger, node_id, value))
        out: list[Effect] = []
        s = self.screen()
        if s is None:
            return out
        if trigger == "text_input":
            n = tree.node_map(s).get(node_id)
            if n is None or n.type != "text" or not n.editable:
                out = [Effect("error", {"message": "Ввод текста: поле не на текущем экране"})]
                self.effects += out
                return out
            text = str(value or "")[:10_000]
            self.state.texts[n.id] = text
            out.append(Effect("text", {"node_id": n.id, "text": text}))
            var = self.doc.variable(n.input_var) if n.input_var else None
            if var is not None and var.type == "text":
                self.state.variables[var.id] = text
                out.append(Effect("variable", {"var_id": var.id, "value": text}))
            out += self._dispatch_chain("text_changed", node_id, s)
            self.effects += out
            return out
        if trigger == "system_back":  # системная кнопка «Назад»: закрыть окно или вернуться на экран
            if self.state.overlays:
                out = self._act({"type": "close_overlay"}, 0)
            else:
                out = self._act({"type": "back", "transition": "slide_right", "duration": 250,
                                 "easing": "ease_out"}, 0)
            self.effects += out
            return out
        chain = self._chain(s, node_id)
        handled = self.handles(trigger, node_id)
        out += self._dispatch_chain(trigger, node_id, s)
        # встроенное поведение компонента срабатывает, если взаимодействие само не меняло состояние экземпляра
        changed_state = any(e.kind == "state" for e in out)
        if trigger in ("tap", "hover_enter", "hover_leave") and not changed_state and \
                (not handled or self.state.screen_id == s.id):
            out += self._component_behavior(trigger, chain, s)
        self.effects += out
        return out

    @staticmethod
    def _chain(s, node_id: str) -> list[str]:
        if not node_id:
            return []
        try:
            return [node_id] + [a.id for a in reversed(tree.ancestors(s, node_id))]
        except Exception:
            return [node_id]

    def handles(self, trigger: str, node_id: str) -> bool:
        """Есть ли взаимодействие с этим триггером у узла или его предков на текущем экране."""
        s = self.screen()
        if s is None:
            return False
        chain = set(self._chain(s, node_id))
        return any(i.screen_id == s.id and i.trigger == trigger and i.node_id in chain for i in self.doc.interactions)

    def _dispatch_chain(self, trigger: str, node_id: str, s) -> list[Effect]:
        out: list[Effect] = []
        for nid in self._chain(s, node_id):
            matches = [i for i in self.doc.interactions if i.screen_id == s.id and i.trigger == trigger
                       and i.node_id == nid]
            if matches:
                for it in matches:
                    out += self._run(it, 0)
                break
        return out

    def _component_behavior(self, trigger: str, chain: list[str], s) -> list[Effect]:
        """Встроенное поведение экземпляров компонентов: наведение и переключение состояний."""
        nodes = tree.node_map(s)
        for nid in chain:
            n = nodes.get(nid)
            if n is None or not n.is_instance or n.ref:
                continue
            defn = self.doc.component(n.component_id)
            if defn is None:
                continue
            b = defn.behavior
            cur = self.state.states.get(n.id, n.state)
            if trigger == "tap" and len(b.get("toggle", [])) == 2:
                a, c = b["toggle"]
                new = c if cur == a else a
            elif trigger == "hover_enter" and b.get("hover") and "hover" in defn.states:
                if cur in b.get("toggle", []) and cur != "default":
                    return []
                new = "hover"
            elif trigger == "hover_leave" and b.get("hover") and cur == "hover":
                new = "default"
            else:
                continue
            self.state.states[n.id] = new
            return [Effect("state", {"node_id": n.id, "state": new, "from": cur})]
        return []

    def _fire_screen_open(self, depth: int) -> list[Effect]:
        out = []
        for it in [i for i in self.doc.interactions if i.screen_id == self.state.screen_id
                   and i.trigger == "screen_open"]:
            out += self._run(it, depth)
        self.effects += out
        return out

    def _cond_ok(self, it: Interaction) -> bool:
        c = it.condition
        if not c:
            return True
        var = self.doc.variable(c["var_id"])
        if var is None:
            return False
        try:
            expected = coerce(var.type, c["value"])
        except Exception:
            return False
        return compare(self.state.variables.get(var.id, var.default), c["op"], expected)

    def _run(self, it: Interaction, depth: int) -> list[Effect]:
        if not self._cond_ok(it):
            return []
        out: list[Effect] = []
        for n, act in enumerate(it.actions):
            if n >= MAX_ACTIONS:
                out.append(Effect("error", {"message": "Превышено число действий"}))
                break
            before = self.state.screen_id
            out += self._act(act, depth)
            if act["type"] in ("navigate", "back") and self.state.screen_id != before:
                break  # после смены экрана остальные действия старого экрана не выполняются
        return out

    def _act(self, a: dict, depth: int) -> list[Effect]:
        st, t = self.state, a["type"]
        screens = {s.id: s for s in self.doc.screens}
        if t == "navigate":
            if a["screen_id"] not in screens:
                return [Effect("error", {"message": "Экран перехода не найден"})]
            if depth >= MAX_DEPTH:
                return [Effect("error", {"message": "Цикл переходов при открытии экрана остановлен"})]
            st.history.append(st.screen_id)
            prev, st.screen_id = st.screen_id, a["screen_id"]
            st.overlays = []
            eff = [Effect("navigate", {"from": prev, "to": st.screen_id, "transition": a["transition"],
                                       "duration": a["duration"], "easing": a["easing"]})]
            for it in [i for i in self.doc.interactions if i.screen_id == st.screen_id
                       and i.trigger == "screen_open"]:
                eff += self._run(it, depth + 1)
            return eff
        if t == "back":
            if not st.history:
                return []
            prev, st.screen_id = st.screen_id, st.history.pop()
            st.overlays = []
            eff = [Effect("back", {"from": prev, "to": st.screen_id, "transition": a["transition"],
                                   "duration": a["duration"], "easing": a["easing"]})]
            if depth < MAX_DEPTH:  # возврат на экран — тоже «открытие экрана»
                for it in [i for i in self.doc.interactions if i.screen_id == st.screen_id
                           and i.trigger == "screen_open"]:
                    eff += self._run(it, depth + 1)
            return eff
        if t == "set_variable":
            var = self.doc.variable(a["var_id"])
            if var is None:
                return [Effect("error", {"message": "Переменная не найдена"})]
            cur = st.variables.get(var.id, var.default)
            mode = a["mode"]
            try:
                if mode == "toggle":
                    new = not bool(cur) if var.type == "bool" else cur
                elif mode in ("increment", "decrement") and var.type == "number":
                    step = coerce("number", a.get("value") or 1)
                    new = cur + step if mode == "increment" else cur - step
                else:
                    new = coerce(var.type, a.get("value"))
            except Exception:
                return [Effect("error", {"message": f"Неверное значение для «{var.name}»"})]
            st.variables[var.id] = new
            return [Effect("variable", {"var_id": var.id, "value": new})]
        s = screens.get(st.screen_id)
        nodes = tree.node_map(s) if s else {}
        if t in ("set_state", "set_variant", "set_visible", "set_text", "open_overlay") and \
                a["node_id"] not in nodes:
            return [Effect("error", {"message": f"{ACTION_NAMES[t]}: элемент не на текущем экране"})]
        if t == "set_variant":
            n = nodes[a["node_id"]]
            defn = self.doc.component(n.component_id) if n.is_instance else None
            vals = list(defn.variants.get(a["axis"], {})) if defn is not None else []
            if not vals:
                return [Effect("error", {"message": f"У компонента нет свойства «{a['axis']}»"})]
            cur = {**n.variant, **st.variants.get(n.id, {})}.get(a["axis"])
            prev = cur if cur in vals else vals[0]
            new = a["value"] or vals[(vals.index(prev) + 1) % len(vals)]
            if new not in vals:
                return [Effect("error", {"message": f"У свойства «{a['axis']}» нет значения «{new}»"})]
            st.variants.setdefault(n.id, {})[a["axis"]] = new
            return [Effect("state", {"node_id": n.id, "state": f"{a['axis']}: {new}", "from": f"{a['axis']}: {prev}",
                                     "axis": a["axis"], "value": new})]
        if t == "set_state":
            n = nodes[a["node_id"]]
            if not n.is_instance:
                return [Effect("error", {"message": "Состояние меняется только у экземпляра компонента"})]
            prev = st.states.get(n.id, n.state)
            st.states[n.id] = a["state"]
            return [Effect("state", {"node_id": n.id, "state": a["state"], "from": prev})]
        if t == "set_visible":
            n = nodes[a["node_id"]]
            cur = st.visibility.get(n.id, n.visible)
            new = {"show": True, "hide": False}.get(a["mode"], not cur)
            st.visibility[n.id] = new
            return [Effect("visible", {"node_id": n.id, "visible": new})]
        if t == "set_text":
            n = nodes[a["node_id"]]
            if n.type != "text":
                return [Effect("error", {"message": "Текст задаётся только текстовому элементу"})]
            text = render_template(str(a["text"]), self.doc, st.variables)
            st.texts[n.id] = text
            return [Effect("text", {"node_id": n.id, "text": text})]
        if t == "play_animation":
            anim = self.doc.animation(a["animation_id"])
            if anim is None or anim.screen_id != st.screen_id:
                return [Effect("error", {"message": "Анимация не найдена на текущем экране"})]
            return [Effect("animation", {"animation_id": anim.id})]
        if t == "open_overlay":
            if a["node_id"] not in st.overlays:
                st.overlays.append(a["node_id"])
            return [Effect("overlay_open", {"node_id": a["node_id"]})]
        if t == "close_overlay":
            if not st.overlays:
                return []
            return [Effect("overlay_close", {"node_id": st.overlays.pop()})]
        return [Effect("error", {"message": f"Неизвестное действие {t}"})]

    # ---------- повтор ----------
    def replay(self, script: list) -> tuple[str, list[dict]]:
        """Сценарий с начала: итоговый хэш состояния и все эффекты."""
        self.reset()
        for step in script:
            self.dispatch(*step)
        return self.state.digest(), [e.to_dict() for e in self.effects]


def validate(doc: ProjectDocument) -> list[Diagnostic]:
    """Висячие ссылки, несовпадение типов, циклы переходов при открытии экранов."""
    diags = []
    screens = {s.id: s for s in doc.screens}
    vars_ = {v.id: v for v in doc.variables}
    names = [v.name for v in doc.variables]
    for dup in {n for n in names if names.count(n) > 1}:
        diags.append(Diagnostic("warning", "", f"Логика: две переменные с именем «{dup}»"))
    edges: dict[str, set[str]] = {}
    for it in doc.interactions:
        s = screens.get(it.screen_id)
        where = f"Логика «{s.name if s else '?'}»"
        if s is None:
            diags.append(Diagnostic("warning", "", f"{where}: экран взаимодействия удалён"))
            continue
        nodes = tree.node_map(s)
        if it.trigger != "screen_open" and it.node_id not in nodes:
            diags.append(Diagnostic("warning", "", f"{where}: элемент-источник события удалён"))
        if it.condition:
            v = vars_.get(it.condition["var_id"])
            if v is None:
                diags.append(Diagnostic("warning", it.node_id, f"{where}: переменная условия удалена"))
            else:
                try:
                    coerce(v.type, it.condition["value"])
                except Exception:
                    diags.append(Diagnostic("warning", it.node_id, f"{where}: значение условия не подходит к типу "
                                                                   f"переменной «{v.name}»"))
        if not it.actions:
            diags.append(Diagnostic("info", it.node_id, f"{where}: у взаимодействия нет действий"))
        for a in it.actions:
            t, label = a["type"], ACTION_NAMES[a["type"]]
            if t == "navigate":
                if a["screen_id"] not in screens:
                    diags.append(Diagnostic("warning", it.node_id, f"{where}: {label} — экран удалён"))
                elif it.trigger == "screen_open":
                    edges.setdefault(it.screen_id, set()).add(a["screen_id"])
            if t == "set_variant" and a["node_id"] in nodes:
                n = nodes[a["node_id"]]
                defn = doc.component(n.component_id) if n.is_instance else None
                vals = defn.variants.get(a["axis"]) if defn is not None else None
                if vals is None:
                    diags.append(Diagnostic("warning", n.id, f"{where}: у компонента нет свойства «{a['axis']}»"))
                elif a["value"] and a["value"] not in vals:
                    diags.append(Diagnostic("warning", n.id, f"{where}: у свойства «{a['axis']}» нет значения "
                                                             f"«{a['value']}»"))
            if t in ("set_state", "set_variant", "set_visible", "set_text", "open_overlay") and \
                    a["node_id"] not in nodes:
                diags.append(Diagnostic("warning", it.node_id, f"{where}: {label} — элемент не на этом экране"))
            if t == "set_state" and a["node_id"] in nodes:
                n = nodes[a["node_id"]]
                defn = doc.component(n.component_id) if n.is_instance else None
                if defn is None:
                    diags.append(Diagnostic("warning", n.id, f"{where}: состояние задаётся не экземпляру компонента"))
                elif a["state"] != "default" and a["state"] not in defn.states:
                    diags.append(Diagnostic("warning", n.id, f"{where}: у компонента «{defn.name}» нет состояния "
                                                             f"«{a['state']}»"))
            if t == "set_text" and a["node_id"] in nodes and nodes[a["node_id"]].type != "text":
                diags.append(Diagnostic("warning", a["node_id"], f"{where}: текст задаётся не текстовому элементу"))
            if t == "set_variable":
                v = vars_.get(a["var_id"])
                if v is None:
                    diags.append(Diagnostic("warning", it.node_id, f"{where}: переменная удалена"))
                elif a["mode"] in ("increment", "decrement") and v.type != "number":
                    diags.append(Diagnostic("warning", it.node_id, f"{where}: «{a['mode']}» только для числа"))
                elif a["mode"] == "set":
                    try:
                        coerce(v.type, a.get("value"))
                    except Exception:
                        diags.append(Diagnostic("warning", it.node_id, f"{where}: значение не подходит к типу "
                                                                       f"«{v.name}»"))
            if t == "play_animation":
                anim = doc.animation(a["animation_id"])
                if anim is None:
                    diags.append(Diagnostic("warning", it.node_id, f"{where}: анимация удалена"))
                elif anim.screen_id != it.screen_id:
                    diags.append(Diagnostic("warning", it.node_id, f"{where}: анимация «{anim.name}» относится "
                                                                   "к другому экрану"))
    # циклы: экран при открытии сразу уходит на экран, который при открытии возвращается обратно
    state: dict[str, int] = {}

    def dfs(v: str, path: list[str]) -> None:
        state[v] = 1
        for w in sorted(edges.get(v, ())):
            if state.get(w) == 1:
                cyc = path[path.index(w):] + [w] if w in path else [v, w]
                names_ = " → ".join(screens[x].name for x in cyc if x in screens)
                diags.append(Diagnostic("warning", "", f"Логика: бесконечный цикл переходов при открытии: {names_}"))
            elif state.get(w) is None:
                dfs(w, path + [w])
        state[v] = 2
    for v in sorted(edges):
        if state.get(v) is None:
            dfs(v, [v])
    return diags
