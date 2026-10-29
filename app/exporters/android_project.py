"""Каркас проекта Android Studio (Kotlin + Jetpack Compose + Material 3) по дизайну. Без Qt.

Генерирует готовую к сборке структуру: Gradle (Kotlin DSL, каталог версий), манифест, тема из токенов,
состояние приложения из переменных, навигация между экранами и экраны на Compose по дереву элементов.
Это стартовая точка для доработки (вручную или Claude Code): Auto Layout переводится в Column / Row,
остальное — в Box со смещениями; логика «нажатие → переход / переменная / показать» — в обработчики.
Что не переводится автоматически, помечено в коде комментарием TODO.
"""

from __future__ import annotations

import re

from app.core.document import tree
from app.core.document.model import ARTBOARD_COLORS, PLATFORM_ANDROID, ProjectDocument, Screen
from app.engines.material.color import ROLES as COLOR_ROLES, scheme
from app.engines.material.type_scale import TYPE_SCALE, role_of
from app.engines.preview.devices import screen_dpi
from app.engines.logic.runtime import smart_keys
from app.exporters.compose_m3 import Material
from app.exporters.compose_motion import (
    GRADIENT_KT, NAV_MOTION, Motion, brush, effects, kshape, plain_stroke, shadow, stroke_draw,
)

ROOT = "android_project"
VERSIONS = {"agp": "8.13.2", "kotlin": "2.2.10", "compose_bom": "2025.09.01", "activity_compose": "1.11.0",
            "core_ktx": "1.17.0", "gradle": "8.13",
            "compile_sdk": 36, "min_sdk": 26, "target_sdk": 36}
_KW = {"as", "break", "class", "continue", "do", "else", "false", "for", "fun", "if", "in", "interface", "is",
       "null", "object", "package", "return", "super", "this", "throw", "true", "try", "typealias", "typeof",
       "val", "var", "when", "while"}


_WIN_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_JAVA_KW = {"abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const", "continue",
            "default", "do", "double", "else", "enum", "extends", "final", "finally", "float", "for", "goto", "if",
            "implements", "import", "instanceof", "int", "interface", "long", "native", "new", "package", "private",
            "protected", "public", "return", "short", "static", "strictfp", "super", "switch", "synchronized", "this",
            "throw", "throws", "transient", "try", "void", "volatile", "while", "true", "false", "null", "var", "val",
            "fun", "object", "typealias", "is", "in", "as"}


def _translit(text: str) -> str:
    from app.exporters.ai_export import _RU
    return "".join(_RU.get(ch, ch) for ch in text.lower())


def ident(text: str, upper: bool, used: set[str], fallback: str) -> str:
    parts = [p for p in re.split(r"[^a-z0-9]+", _translit(text)) if p]
    name = "".join(p.capitalize() for p in parts) or fallback
    if name[0].isdigit():
        name = fallback + name
    if not upper:
        name = name[0].lower() + name[1:]
    if name in _KW:
        name += "_"
    base, i = name, 2
    while name in used:
        name, i = f"{base}{i}", i + 1
    used.add(name)
    return name


def package_name(title: str) -> str:
    seg = re.sub(r"[^a-z0-9]+", "", _translit(title)) or "app"
    if not seg[0].isalpha():
        seg = "app" + seg
    seg = seg[:30]
    if seg in _KW or seg in _JAVA_KW or seg in _WIN_RESERVED:  # «fun», «class», «con» — не имя пакета / папки
        seg += "app"
    return f"com.design.{seg}"


def route_names(screens) -> dict[str, str]:
    """Маршруты экранов из названий: «Корзина товаров» → korzina-tovarov (буквы, цифры, дефис; без повторов)."""
    out, used = {}, set()
    for i, s in enumerate(screens):
        base = re.sub(r"[^a-z0-9]+", "-", _translit(s.name)).strip("-")[:40].strip("-") or f"screen{i + 1}"
        if base[0].isdigit():
            base = "s-" + base
        name, k = base, 2
        while name in used:
            name, k = f"{base}-{k}", k + 1
        used.add(name)
        out[s.id] = name
    return out


def kstr(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("\n", "\\n") \
        .replace("\r", "\\r") + '"'


def kcolor(c: str) -> str:
    c = (c or "#000000").lstrip("#").upper()
    a = c[6:8] if len(c) == 8 else "FF"
    return f"Color(0x{a}{c[:6]})"


def _num(v: float) -> str:
    v = round(float(v), 1)
    return str(int(v)) if v == int(v) else str(v)


def _cased(text: str, case: str) -> str:
    """Регистр текста из дизайна (ВСЕ ЗАГЛАВНЫЕ, строчные, Каждое Слово) — сразу в строке кода."""
    if case == "upper":
        return text.upper()
    if case == "lower":
        return text.lower()
    if case == "title":
        return " ".join(w[:1].upper() + w[1:] for w in text.split(" "))
    return text


class _Screen:
    """Генерация одного экрана."""

    def __init__(self, gen: "AndroidProject", s: Screen, fn: str):
        self.g, self.s, self.fn = gen, s, fn
        self.parts = 0  # счётчик частей большого экрана (локальные @Composable-функции)
        self.k = screen_dpi(s) / 160
        self.its = [i for i in gen.doc.interactions if i.screen_id == s.id]
        self.used: set[str] = set()
        self.vis: dict[str, str] = {}     # node_id → имя переменной видимости
        self.texts: dict[str, str] = {}   # node_id → имя переменной текста
        self.inputs: dict[str, str] = {}  # node_id → имя переменной поля ввода
        self.todo: list[str] = []
        self.pre: list[str] = []  # объявления перед элементом (цвет темы нельзя читать внутри рисования)
        # списки из данных (LazyColumn): свойство элемента шаблона строки → поле item, нажатие строки
        self.bound: dict[tuple[str, str], str] = {}
        self.row_click: dict[str, str] = {}
        self.data_classes: list[str] = []
        self.res_vals: dict[str, str] = {}  # текст из «Задать текст» → val с stringResource в начале экрана
        m = tree.node_map(s)
        overlays = set()
        for it in self.its:
            for a in it.actions:
                if a["type"] in ("set_visible", "open_overlay") and a.get("node_id") in m:
                    self.vis.setdefault(a["node_id"], ident(f"visible {m[a['node_id']].name}", False, self.used,
                                                            "visible"))
                    if a["type"] == "open_overlay":
                        overlays.add(a["node_id"])
                if a["type"] == "set_text" and a.get("node_id") in m:
                    self.texts.setdefault(a["node_id"], ident(f"text {m[a['node_id']].name}", False, self.used,
                                                              "text"))
        self.overlays = overlays
        self.scrims = {a["node_id"] for it in self.its for a in it.actions
                       if a["type"] == "open_overlay" and a.get("scrim")}
        self.waits = any(a["type"] in ("wait", "scroll_to") for it in self.its for a in it.actions)
        self.scroll_to = any(a["type"] == "scroll_to" for it in self.its for a in it.actions)
        # прокрутка: у каждого прокручиваемого контейнера — своё состояние (липкие элементы, «прокрутить к»)
        self.scroll_states = {n.id: ident(f"scroll {n.name}", False, self.used, "scroll")
                              for n, _, _ in tree.walk(s.nodes)
                              if n.is_frame and n.scroll != "none" and not n.paging and n.children}
        # листание страницами: контейнер → состояние HorizontalPager (VerticalPager); точки страниц сразу после него
        self.pagers, self.dots_for = {}, {}
        for n, _, _ in tree.walk(s.nodes):
            if n.is_frame and n.paging and n.children:
                self.pagers[n.id] = ident(f"pager {n.name}", False, self.used, "pager")
                _, parent, idx = tree.find(s, n.id)
                sib = parent.children if parent is not None else s.nodes
                nxt = sib[idx + 1] if idx + 1 < len(sib) else None  # точки — следующий элемент или внутри него
                dots = next((d for d, _, _ in tree.walk([nxt]) if d.role == "m3.page_dots"), None) if nxt else None
                if dots is not None:
                    self.dots_for[dots.id] = (self.pagers[n.id], len(n.children), dots)
        self.smart = {name: n.id for name, n in smart_keys(s).items() if name in gen.smart_names}
        # переключение вариантов: node_id копии → {свойство: имя переменной}
        self.variant_vars: dict[str, dict[str, str]] = {}
        self._expanding: set[str] = set()
        for it in self.its:
            for a in it.actions:
                n = m.get(a.get("node_id", "")) if a["type"] == "set_variant" else None
                d = gen.doc.component(n.component_id) if n is not None and n.is_instance else None
                if d is not None and a["axis"] in d.variants:
                    self.variant_vars.setdefault(n.id, {}).setdefault(
                        a["axis"], ident(f"variant {n.name} {a['axis']}", False, self.used, "variant"))
        # состояния своих компонентов: действие «Состояние компонента» и встроенное переключение по нажатию
        self.state_vars: dict[str, str] = {}
        self.state_toggle: dict[str, tuple[str, str]] = {}
        for it in self.its:
            for a in it.actions:
                n = m.get(a.get("node_id", "")) if a["type"] == "set_state" else None
                d = gen.doc.component(n.component_id) if n is not None and n.is_instance else None
                if d is not None and a["state"] in ("default", *d.states) and n.id not in self.variant_vars:
                    self.state_vars.setdefault(n.id, ident(f"state {n.name}", False, self.used, "state"))
        for n, _, _ in tree.walk(s.nodes):
            d = gen.doc.component(n.component_id) if n.is_instance and not n.ref else None
            toggle = d.behavior.get("toggle", []) if d is not None else []
            if len(toggle) == 2 and all(t in ("default", *d.states) for t in toggle) and n.id not in self.variant_vars:
                self.state_vars.setdefault(n.id, ident(f"state {n.name}", False, self.used, "state"))
                self.state_toggle[n.id] = (toggle[0], toggle[1])
        for n, _, _ in tree.walk(s.nodes):
            if n.type == "text" and n.editable:
                self.inputs[n.id] = ident(f"input {n.name}", False, self.used, "input")
        self.kstr = kstr
        self.m3 = Material(self)
        self.motion = Motion(self)

    def ident(self, text: str) -> str:
        return ident(text, False, self.used, "value")

    def dp(self, v: float) -> str:
        return f"{_num(v / self.k)}.dp"

    # ---------- действия ----------
    def actions_code(self, it, ind: str) -> list[str]:
        out = self._acts(it.actions)
        if it.condition:
            v = self.g.doc.variable(it.condition["var_id"])
            if v is not None:
                st = self.g.state_names
                cond = f"state.{st[v.id]} {it.condition['op']} {self.g.literal(v.type, it.condition['value'])}"
                return [f"{ind}if ({cond}) {{"] + [f"{ind}    {x}" for x in out] + [f"{ind}}}"]
        return [ind + x for x in out]

    def _acts(self, actions: list[dict]) -> list[str]:
        out = []
        st = self.g.state_names
        for i, a in enumerate(actions):
            t = a["type"]
            if t == "scroll_to":  # плавно прокрутить ближайший прокручиваемый контейнер к элементу
                target = tree.node_map(self.s).get(a["node_id"])
                chain = list(reversed(tree.ancestors(self.s, a["node_id"]))) if target is not None else []
                frame = next((f for f in chain if f.id in self.scroll_states), None)
                if frame is None:
                    out.append("// прокрутка к элементу: он не в прокручиваемом контейнере")
                    continue
                off = (target.y - frame.y - frame.pad_t) if frame.scroll == "vertical" else \
                    (target.x - frame.x - frame.pad_l)
                out.append(f"scope.launch {{ {self.scroll_states[frame.id]}.animateScrollTo("
                           f"with(density) {{ {self.dp(max(0.0, off))}.roundToPx() }}) }}")
                continue
            if t == "wait":  # пауза: остальные действия — в корутине после delay
                rest = self._acts(actions[i + 1:])
                out += [f"scope.launch {{", f"    delay({int(a.get('duration', 0))})"] + \
                    [f"    {x}" for x in rest] + ["}"]
                break
            if t == "navigate":
                route = self.g.routes.get(a["screen_id"])
                motion = (f'NavMotion("{a.get("transition", "none")}", {int(a.get("duration", 300))}, '
                          f'"{a.get("easing", "ease_in_out")}")')
                out.append(f"onNavigate({kstr(route)}, {motion})" if route else
                           "// TODO: переход на экран другой платформы или вне выбранных экранов")
            elif t == "back":
                out.append("onBack()")
            elif t == "set_variable":
                v = self.g.doc.variable(a["var_id"])
                if v is None:
                    continue
                name = f"state.{st[v.id]}"
                if a["mode"] == "toggle":
                    out.append(f"{name} = !{name}" if v.type == "bool" else f"// TODO: переключение «{v.name}»")
                elif a["mode"] in ("increment", "decrement") and v.type == "number":
                    op = "+=" if a["mode"] == "increment" else "-="
                    out.append(f"{name} {op} {_num(float(a.get('value') or 1))}")
                else:
                    out.append(f"{name} = {self.g.literal(v.type, a.get('value'))}")
            elif t == "set_visible" and a["node_id"] in self.vis:
                var = self.vis[a["node_id"]]
                out.append({"show": f"{var} = true", "hide": f"{var} = false"}.get(a["mode"], f"{var} = !{var}"))
            elif t == "open_overlay" and a["node_id"] in self.vis:
                out.append(f"{self.vis[a['node_id']]} = true")
            elif t == "close_overlay":
                out += [f"{self.vis[nid]} = false" for nid in sorted(self.overlays)] or ["// окно не открыто"]
            elif t == "play_animation" and self.motion.action(a["animation_id"]):
                out.append(self.motion.action(a["animation_id"]))
            elif t == "set_variant" and a["axis"] in self.variant_vars.get(a["node_id"], {}):
                var = self.variant_vars[a["node_id"]][a["axis"]]
                n = tree.node_map(self.s)[a["node_id"]]
                vals = list(self.g.doc.component(n.component_id).variants[a["axis"]])
                if a["value"] or len(vals) == 1:
                    out.append(f"{var} = {kstr(a['value'] or vals[0])}")
                else:  # следующее значение по кругу
                    steps = "; ".join(f"{kstr(v)} -> {kstr(vals[i + 1])}" for i, v in enumerate(vals[:-1]))
                    out.append(f"{var} = when ({var}) {{ {steps}; else -> {kstr(vals[0])} }}")
            elif t == "set_state" and a["node_id"] in self.state_vars:
                out.append(f"{self.state_vars[a['node_id']]} = {kstr(a['state'])}")
            elif t == "set_text" and a["node_id"] in self.texts:
                out.append(f"{self.texts[a['node_id']]} = {self.template(str(a['text']))}")
            else:
                out.append(f"// TODO: действие «{t}» (анимации и элементы вне экрана — вручную)")
        return out

    def template(self, text: str) -> str:
        by_name = {v.name: v for v in self.g.doc.variables}
        if text.strip() and not any(m.group(1) in by_name for m in re.finditer(r"\{([^{}]{1,64})\}", text)):
            # неизменный текст — строковый ресурс (переводится); в обработчике нажатия stringResource недоступен,
            # поэтому строка читается в начале экрана
            if text not in self.res_vals:
                self.res_vals[text] = ident(f"str {text[:24]}", False, self.used, "str")
            return self.res_vals[text]

        def sub(m):
            v = by_name.get(m.group(1))
            return "${fmt(state." + self.g.state_names[v.id] + ")}" if v else m.group(0)
        body = text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("\n", "\\n")
        return '"' + re.sub(r"\{([0-9A-Za-zА-Яа-яЁё_ -]{1,64})\}", sub, body) + '"'

    def handlers(self, n, ind: str) -> list[str]:
        """Modifier-обработчики событий узла (нажатие, долгое, двойное)."""
        if n.id in self.row_click:  # строка списка: своё действие у каждой строки — в её данных
            return [f"{ind}.clickable {{ {self.row_click[n.id]} }}"]
        mine, swipes = {}, {}
        for it in self.its:
            if it.node_id == n.id and it.trigger in ("tap", "long_press", "double_tap"):
                mine.setdefault(it.trigger, []).append(it)
            elif it.node_id == n.id and it.trigger.startswith("swipe_"):
                swipes.setdefault(it.trigger, []).append(it)
        toggle = self.state_toggle.get(n.id)
        if toggle is not None and not any(a["type"] == "set_state" and a.get("node_id") == n.id
                                          for it in mine.get("tap", []) for a in it.actions):
            mine.setdefault("tap", [])  # своё переключение компонента по нажатию (как в прототипе)
        else:
            toggle = None
        out_swipe = self.swipe_handler(swipes, ind) if swipes else []
        if not mine:
            return out_swipe

        def body(trig):
            lines = []
            for it in mine.get(trig, []):
                lines += self.actions_code(it, ind + "        ")
            if trig == "tap" and toggle is not None:
                var, (a, b) = self.state_vars[n.id], toggle
                lines.append(f"{ind}        {var} = if ({var} == {kstr(a)}) {kstr(b)} else {kstr(a)}")
            return lines
        if set(mine) == {"tap"}:  # подпись действия для TalkBack — видимая надпись элемента (имя слоя — нет)
            shown = next((d.text.strip() for d in tree.descendants(n) if d.type == "text" and d.text.strip()), "") \
                if n.is_container else (n.text.strip() if n.type == "text" else "")
            label = f"onClickLabel = {self.res_text(shown[:60])}" if shown else ""
            return [f"{ind}.clickable({label}) {{"] + body("tap") + [f"{ind}}}"] + out_swipe
        out = [f"{ind}.combinedClickable("]
        for trig, arg in (("tap", "onClick"), ("long_press", "onLongClick"), ("double_tap", "onDoubleClick")):
            if trig in mine or trig == "tap":
                out += [f"{ind}    {arg} = {{"] + body(trig) + [f"{ind}    }},"]
        return out + [f"{ind})"] + out_swipe

    def swipe_handler(self, swipes: dict, ind: str) -> list[str]:
        """Свайпы: провести пальцем дальше 48 dp — по главному направлению срабатывает свой жест."""
        def branch(trig, i2):
            lines = []
            for it in swipes.get(trig, []):
                lines += self.actions_code(it, i2)
            return lines or [f"{i2}Unit"]
        i1, i2, i3 = ind + "        ", ind + "            ", ind + "                "
        out = [f"{ind}.pointerInput(Unit) {{", f"{ind}    var dx = 0f", f"{ind}    var dy = 0f",
               f"{ind}    detectDragGestures(", f"{ind}        onDragStart = {{ dx = 0f; dy = 0f }},",
               f"{ind}        onDragEnd = {{", f"{i2}val far = 48.dp.toPx()",
               f"{i2}if (abs(dx) > abs(dy) && abs(dx) > far) {{",
               f"{i3}if (dx < 0) {{"] + branch("swipe_left", i3 + "    ") + [f"{i3}}} else {{"] +             branch("swipe_right", i3 + "    ") + [f"{i3}}}", f"{i2}}} else if (abs(dy) > far) {{",
                                               f"{i3}if (dy < 0) {{"] + branch("swipe_up", i3 + "    ") +             [f"{i3}}} else {{"] + branch("swipe_down", i3 + "    ") + [f"{i3}}}", f"{i2}}}",
                                                                      f"{i1}}},",
                                                                      f"{ind}    ) {{ change, d -> change.consume(); dx += d.x; dy += d.y }}",
                                                                      f"{ind}}}"]
        return out

    # ---------- элементы ----------
    def modifier(self, n, parent, mode: str, ind: str, handlers: bool = True) -> list[str]:
        """mode: abs (смещение в Box), col / row (в Auto Layout)."""
        m = [f"{ind}Modifier"]
        fill_w = fill_h = None  # None — размер из дизайна; 1.0 — на всё место; 0…1 — доля (масштабирование)
        if mode == "abs":
            m += self._place(n, parent, ind)
            fill_w, fill_h = self._fills
        if n.sticky and parent is not None and parent.id in self.scroll_states and parent.scroll == "vertical":
            top = self.dp(max(0.0, n.y - parent.y))  # липкий: прилипает к верхнему краю контейнера (поля — внутри)
            st = self.scroll_states[parent.id]
            m.append(f"{ind}    .zIndex(1f)")
            m.append(f"{ind}    .offset {{ IntOffset(0, ({st}.value - {top}.roundToPx()).coerceAtLeast(0)) }}")
        if self.smart.get(n.name) == n.id:  # умный переход: одноимённый элемент на другом экране
            m.append(f"{ind}    .smart({kstr(n.name)})")
        main_fill = (mode == "col" and n.sizing_v == "fill") or (mode == "row" and n.sizing_h == "fill")
        if main_fill:
            m.append(f"{ind}    .weight(1f)")
        if (n.sizing_h == "fill" and mode == "col") or fill_w == 1.0:
            m.append(f"{ind}    .fillMaxWidth()")
        elif fill_w is not None:
            m.append(f"{ind}    .fillMaxWidth({_num(fill_w)}f)")
        elif n.sizing_h != "hug" and not (mode == "row" and n.sizing_h == "fill"):
            aw = self.motion.var(n, "w")  # анимация ширины из студии
            m.append(f"{ind}    .width({aw + '.value.dp' if aw else self.dp(n.w)})")
        if (n.sizing_v == "fill" and mode == "row") or (fill_h == 1.0 and n.sizing_v != "hug"):
            m.append(f"{ind}    .fillMaxHeight()")
        elif fill_h is not None and n.sizing_v != "hug":
            m.append(f"{ind}    .fillMaxHeight({_num(fill_h)}f)")
        elif n.sizing_v != "hug" and not (mode == "col" and n.sizing_v == "fill") and n.type != "text":
            ah = self.motion.var(n, "h")
            m.append(f"{ind}    .height({ah + '.value.dp' if ah else self.dp(n.h)})")
        elif n.type == "text" and n.sizing_v == "fixed":
            m.append(f"{ind}    .heightIn(min = {self.dp(n.h)})")
        if self.motion.animated(n):  # анимация из студии: непрозрачность и смещение — в graphicsLayer
            m += self.motion.layer(n, ind + "    ")
        elif n.opacity < 1:
            m.append(f"{ind}    .alpha({_num(n.opacity)}f)")
        shape = f"maskShape({kstr(n.clip_path)})" if n.clip_path else kshape(n, self.dp)
        if self.motion.var(n, "radius") and not n.clip_path and n.type != "ellipse":  # анимация скругления
            shape = f"RoundedCornerShape({self.motion.var(n, 'radius')}.value.dp)"
        drop = shadow(n, self.dp, self.g.color, shape, inset=False)
        if drop:
            m.append(f"{ind}    {drop}")
        m += effects(n, self.dp, shape, ind + "    ")
        if n.stroke and n.stroke_width and n.type not in ("text", "vector") and not plain_stroke(n):
            # до обрезки по форме: обводка снаружи и по краю не срезается, рисуется поверх заливки
            color = self.ident(f"stroke {n.name}")
            sv = self.motion.var(n, "stroke")  # анимация цвета обводки
            self.pre.append(f"val {color} = {sv + '.value' if sv else self.g.color(n.stroke)}")
            sw = self.motion.var(n, "stroke_width")
            m += stroke_draw(n, (lambda v, w=sw: f"{w}.value.dp") if sw else self.dp, lambda _c, v=color: v, shape,
                             ind + "    ")
        if n.type == "image" and n.clip_path:  # маска любой формой
            m.append(f"{ind}    .clip({shape})")
        elif n.type == "image" and n.radius > 0:  # маска картинки: круг или скругление
            m.append(f"{ind}    .clip({'CircleShape' if n.radius >= min(n.w, n.h) / 2 - 0.5 else shape})")
        elif n.clip_path and not n.fill and n.type not in ("text", "vector"):
            m.append(f"{ind}    .clip({shape})")  # контейнер в форме фигуры обрезает содержимое
        if n.fill and n.type not in ("text", "image", "vector"):
            m.append(f"{ind}    .clip({shape})")
            fill = n.fill
            if n.backdrop_blur > 0 and not self.under_glass(n) and len(fill) == 9 and int(fill[7:], 16) < 0x80:
                fill = fill[:7] + "80"  # стекло без копии фона под ним: плотнее, чтобы текст на нём читался
            if n.backdrop_blur > 0 and self.under_glass(n):  # заливка стекла — поверх размытой копии фона
                tint = self.ident(f"glass {n.name}")
                self.pre.append(f"val {tint} = {self.g.color(fill)}")
                m.append(f"{ind}    .drawWithContent {{ drawContent(); drawRect({tint}) }}")
            elif self.motion.var(n, "fill"):  # анимация цвета заливки (у градиента — первого цвета)
                av = f"{self.motion.var(n, 'fill')}.value"
                m.append(f"{ind}    .background({brush(n, self.g.color, av) or av})")
            else:
                m.append(f"{ind}    .background({self.bound.get((n.id, 'fill')) or brush(n, self.g.color) or self.g.color(fill)})")
        inner = shadow(n, self.dp, self.g.color, shape, inset=True)
        if inner:
            m.append(f"{ind}    {inner}")
        if n.overlay and n.type not in ("text", "vector"):  # слой поверх содержимого с режимом наложения
            tint = self.ident(f"overlay {n.name}")
            self.pre.append(f"val {tint} = {self.g.color(n.overlay)}")
            blend = {"multiply": "Multiply", "screen": "Screen", "overlay": "Overlay", "darken": "Darken",
                     "lighten": "Lighten"}.get(n.overlay_blend, "SrcOver")
            m.append(f"{ind}    .drawWithContent {{ drawContent(); drawRect({tint}, blendMode = BlendMode.{blend}) }}")
        if n.backdrop_blur > 0 and n.type not in ("text", "vector") and not n.stroke:
            # матовое стекло: под ним — размытая копия картинок и фигур, что лежат ниже (Android 12+);
            # на старых телефонах размытия нет — остаётся полупрозрачная заливка и светлый край
            m.append(f"{ind}    .border(1.dp, Color.White.copy(alpha = 0.35f), {shape})")
        if n.stroke and n.stroke_width and n.type not in ("text", "vector"):
            if plain_stroke(n):
                sv, sw = self.motion.var(n, "stroke"), self.motion.var(n, "stroke_width")  # анимация обводки
                width = f"{sw}.value.dp" if sw else self.dp(n.stroke_width)
                m.append(f"{ind}    .border({width}, {sv + '.value' if sv else self.g.color(n.stroke)}, {shape})")
        if handlers:
            m += self.handlers(n, ind + "    ")
        if n.is_frame and n.scroll in ("vertical", "horizontal") and not n.paging:  # пейджер листает сам
            m.append(f"{ind}    .{n.scroll}Scroll({self.scroll_states.get(n.id, 'rememberScrollState()')})")
        if n.is_frame and n.layout != "none" and (n.pad_t or n.pad_r or n.pad_b or n.pad_l):
            m.append(f"{ind}    .padding(start = {self.dp(n.pad_l)}, top = {self.dp(n.pad_t)}, "
                     f"end = {self.dp(n.pad_r)}, bottom = {self.dp(n.pad_b)})")
        return m

    _ALIGN = {("Top", "Start"): "TopStart", ("Top", "Center"): "TopCenter", ("Top", "End"): "TopEnd",
              ("Center", "Start"): "CenterStart", ("Center", "Center"): "Center", ("Center", "End"): "CenterEnd",
              ("Bottom", "Start"): "BottomStart", ("Bottom", "Center"): "BottomCenter",
              ("Bottom", "End"): "BottomEnd"}

    def _place(self, n, parent, ind: str) -> list[str]:
        """Место элемента в Box по его поведению при изменении размера экрана (привязкам): у левого или правого
        края, по центру, растянут между краями или масштабируется. Так экран подстраивается под любой телефон
        и планшет, а не стоит на фиксированных смещениях. Результат размеров — в self._fills."""
        ox, oy = n.x - (parent.x if parent else 0), n.y - (parent.y if parent else 0)
        pw, ph = (parent.w, parent.h) if parent else (self.s.width, self.s.height)
        right, bottom = pw - ox - n.w, ph - oy - n.h
        pad: dict[str, float] = {}
        h, v = "Start", "Top"
        fw = fh = None
        ch, cv = n.constraint_h, n.constraint_v
        if ch == "right" and right >= 0:
            h, pad["end"], ox = "End", right, 0
        elif ch == "center":
            h, ox = "Center", ox - (pw - n.w) / 2
        elif ch == "left_right" and right >= 0:
            pad["start"], pad["end"], ox, fw = ox, right, 0, 1.0
        elif ch == "scale" and pw - ox > 0:
            pad["start"], fw, ox = ox, min(1.0, n.w / (pw - ox)), 0
        if cv == "bottom" and bottom >= 0:
            v, pad["bottom"], oy = "Bottom", bottom, 0
        elif cv == "center":
            v, oy = "Center", oy - (ph - n.h) / 2
        elif cv == "top_bottom" and bottom >= 0:
            pad["top"], pad["bottom"], oy, fh = oy, bottom, 0, 1.0
        elif cv == "scale" and ph - oy > 0:
            pad["top"], fh, oy = oy, min(1.0, n.h / (ph - oy)), 0
        self._fills = (fw, fh)
        out = []
        if (v, h) != ("Top", "Start"):
            out.append(f"{ind}    .align(Alignment.{self._ALIGN[(v, h)]})")
        parts = [f"{k} = {self.dp(pad[k])}" for k in ("start", "top", "end", "bottom") if pad.get(k, 0) > 0.5]
        if parts:
            out.append(f"{ind}    .padding({', '.join(parts)})")
        if abs(ox) > 0.05 or abs(oy) > 0.05:
            out.append(f"{ind}    .offset(x = {self.dp(ox)}, y = {self.dp(oy)})")
        return out

    def node(self, n, parent, mode: str, ind: str) -> list[str]:
        saved, self.pre = self.pre, []
        try:
            out = self._node(n, parent, mode, ind)
            return [ind + x for x in self.pre] + out
        finally:
            self.pre = saved

    def _node(self, n, parent, mode: str, ind: str) -> list[str]:
        out: list[str] = []
        if n.is_group:  # у группы нет геометрии — дети в координатах родителя группы
            for c in n.children:
                out += self.node(c, parent, mode, ind)
            return out
        if n.id in self.variant_vars and n.id not in self._expanding:
            return self.variant_node(n, parent, mode, ind)
        if n.id in self.state_vars and n.id not in self._expanding:
            return self.state_node(n, parent, mode, ind)
        hidden = not n.visible
        if n.id in self.vis:  # показ и скрытие — с плавным появлением
            var = self.vis[n.id]
            if n.id in self.scrims and n in self.s.nodes:  # затемнение под окном; нажатие по нему закрывает
                out += [f"{ind}androidx.compose.animation.AnimatedVisibility(visible = {var}, "
                        f"modifier = Modifier.matchParentSize(), enter = fadeIn(), exit = fadeOut()) {{",
                        f"{ind}    Box(Modifier.fillMaxSize().background(Color(0x66000000))",
                        f"{ind}        .clickable(remember {{ MutableInteractionSource() }}, null) {{ {var} = false }})",
                        f"{ind}}}"]
            sheet = n.id in self.overlays and n.y + n.h >= self.s.height - 1  # шторка снизу — выезжает
            enter, leave = ("slideInVertically { it } + fadeIn()", "slideOutVertically { it } + fadeOut()") \
                if sheet else ("fadeIn()", "fadeOut()")
            av = "androidx.compose.animation.AnimatedVisibility"  # полное имя: в Row/Column — не их перегрузка
            if mode == "abs":  # слой во весь родитель: внутри снова Box — работают align и offset элемента
                out += [f"{ind}{av}(visible = {var}, modifier = Modifier.matchParentSize(), enter = {enter}, "
                        f"exit = {leave}) {{", f"{ind}    Box(Modifier.fillMaxSize()) {{"]
                ind2 = ind + "        "
            else:
                out.append(f"{ind}{av}(visible = {var}, enter = {enter}, exit = {leave}) {{")
                ind2 = ind + "    "
        elif hidden:
            return [f"{ind}// скрыт в дизайне: «{n.name or n.type}»"]
        else:
            ind2 = ind
        close = ([f"{ind}    }}"] if n.id in self.vis and mode == "abs" else []) + [f"{ind}}}"]
        out.append(f"{ind2}// {n.name or n.type}" + (f" — экземпляр компонента" if n.is_instance else ""))
        if n.id in self.pagers:  # листание страницами
            out += self.pager(n, parent, mode, ind2)
            if n.id in self.vis:
                out += close
            return out
        if n.id in self.dots_for:  # точки страниц, связанные с листаемым контейнером
            out += self.pager_dots(n, parent, mode, ind2)
            if n.id in self.vis:
                out += close
            return out
        if self.m3.handles(n):  # стандартный компонент Material 3 → компонент Compose
            out += self.m3.node(n, parent, mode, ind2)
            if n.id in self.vis:
                out += close
            return out
        mod = self.modifier(n, parent, mode, ind2 + "    ")
        mod[0] = mod[0].lstrip()
        modtxt = "\n".join([mod[0]] + mod[1:])
        if n.type == "text":
            out += self.text(n, modtxt, ind2)
        elif n.type == "image":
            res = self.g.drawables.get(n.asset_id)
            if res:
                out += [f"{ind2}Image(", f"{ind2}    painter = painterResource({self.bound.get((n.id, 'image')) or 'R.drawable.' + res}),",
                        f"{ind2}    contentDescription = {self.res_text(n.name)},",
                        f"{ind2}    contentScale = ContentScale.{ {'cover': 'Crop', 'contain': 'Fit'}.get(n.fit, 'FillBounds') },",
                        f"{ind2}    modifier = {modtxt},", f"{ind2})"]
            else:
                out += [f"{ind2}// TODO: изображение «{n.name}» (не включено в пакет или SVG не разобрать)",
                        f"{ind2}Box(modifier = {modtxt}.background(Color(0x22FFFFFF)))"]
        elif n.type == "vector" and n.path:
            tint = self.ident(f"tint {n.name}")  # цвет темы читается до рисования (в Canvas он недоступен)
            out.append(f"{ind2}val {tint} = {self.bound.get((n.id, 'fill')) or self.g.color(n.fill or '#00000000')}")
            out += [f"{ind2}Canvas(modifier = {modtxt}) {{",
                    f"{ind2}    scale(size.width / {_num(n.vb_w)}f, size.height / {_num(n.vb_h)}f, pivot = Offset.Zero) {{",
                    f"{ind2}        val p = PathParser().parsePathString({kstr(n.path)}).toPath()"
                    + (".apply { fillType = PathFillType.EvenOdd }" if n.fill_rule == "evenodd" else ""),
                    f"{ind2}        drawPath(p, {tint})"]
            if n.stroke and n.stroke_width:
                out.append(f"{ind2}        drawPath(p, {kcolor(n.stroke)}, style = Stroke(width = {_num(n.stroke_width)}f))")
            out += [f"{ind2}    }}", f"{ind2}}}"]
        elif n.is_frame and n.layout in ("vertical", "horizontal", "grid", "wrap"):
            out += self.stack(n, modtxt, ind2)
        else:
            under = self.under_glass(n) if n.backdrop_blur > 0 else []
            if (n.is_container and n.children) or under:
                out.append(f"{ind2}Box(modifier = {modtxt}) {{")
                out += self.glass_copies(n, under, ind2 + "    ")
                for c in (n.children if n.is_container else []):
                    out += self.node(c, n, "abs", ind2 + "    ")
                out.append(f"{ind2}}}")
            else:
                out.append(f"{ind2}Box(modifier = {modtxt})")
        if n.id in self.vis:
            out += close
        return out

    def pager(self, n, parent, mode: str, ind: str) -> list[str]:
        """Контейнер «листать страницами» → HorizontalPager (столбец — VerticalPager, как короткие видео):
        каждая страница — свой дочерний элемент."""
        from app.core.document.model import Node
        var = self.pagers[n.id]
        if mode == "abs":  # лента от края до края (короткие видео) — на любом телефоне во весь экран
            px, py = (parent.x, parent.y) if parent is not None else (0, 0)
            pw, ph = (parent.w, parent.h) if parent is not None else (self.s.width, self.s.height)
            full_w = abs(n.x - px) <= 1 and abs(n.x + n.w - px - pw) <= 1
            full_h = abs(n.y - py) <= 1 and abs(n.y + n.h - py - ph) <= 1
            if full_w or full_h:
                n = Node.from_dict(n.to_dict())  # копия: проект при выгрузке не меняется
                n.constraint_h = "left_right" if full_w else n.constraint_h
                n.constraint_v = "top_bottom" if full_h else n.constraint_v
        mod = self.modifier(n, parent, mode, ind + "    ")
        mod[0] = mod[0].lstrip()
        vertical = n.scroll == "vertical"
        pad = (f"top = {self.dp(n.pad_t)}, bottom = {self.dp(n.pad_b)}" if vertical
               else f"start = {self.dp(n.pad_l)}, end = {self.dp(n.pad_r)}")
        out = [f"{ind}{'VerticalPager' if vertical else 'HorizontalPager'}(", f"{ind}    state = {var},",
               f"{ind}    modifier = " + "\n".join(mod) + ",",
               f"{ind}    pageSpacing = {self.dp(n.gap)},",
               f"{ind}    contentPadding = PaddingValues({pad}),",
               f"{ind}) {{ page ->", f"{ind}    when (page) {{"]
        for i, c in enumerate(n.children):
            box = Node(type="frame", x=c.x, y=c.y, w=c.w, h=c.h)  # страница занимает всё место пейджера
            c = Node.from_dict(c.to_dict())  # копия: проект при выгрузке не меняется
            c.constraint_h, c.constraint_v = "left_right", "top_bottom"  # на любом телефоне — во всю страницу
            out.append(f"{ind}        {i} -> Box(Modifier.fillMaxSize()) {{")
            out += self.node(c, box, "abs", ind + "            ")
            out.append(f"{ind}        }}")
        return out + [f"{ind}    }}", f"{ind}}}"]

    def pager_dots(self, n, parent, mode: str, ind: str) -> list[str]:
        """Точки страниц, которые следят за текущей страницей пейджера."""
        var, count, dots = self.dots_for[n.id]
        active = max(dots.children, key=lambda d: d.w)
        other = min(dots.children, key=lambda d: d.w)
        mod = self.modifier(n, parent, mode, ind + "    ")
        mod[0] = mod[0].lstrip()
        on, off = self.g.color(active.fill), self.g.color(other.fill)
        return [f"{ind}Row(modifier = " + "\n".join(mod) + f", horizontalArrangement = Arrangement.spacedBy("
                f"{self.dp(n.gap)}), verticalAlignment = Alignment.CenterVertically) {{",
                f"{ind}    repeat({count}) {{ i ->",
                f"{ind}        val current = {var}.currentPage == i",
                f"{ind}        Box(Modifier.size(if (current) {self.dp(active.w)} else {self.dp(other.w)}, "
                f"{self.dp(active.h)}).clip(CircleShape).background(if (current) {on} else {off}))",
                f"{ind}    }}", f"{ind}}}"]

    def under_glass(self, glass) -> list:
        """Картинки и фигуры с заливкой, которые лежат под стеклом (раньше по порядку) и перекрываются с ним."""
        if glass.backdrop_blur <= 0:
            return []
        out = []
        for n, _, _ in tree.walk(self.s.nodes):
            if n is glass:
                break
            if not n.visible or n.type not in ("image", "rect") or (n.type == "rect" and not n.fill):
                continue
            if n.type == "image" and n.asset_id not in self.g.drawables:
                continue
            if n.x < glass.x + glass.w and glass.x < n.x + n.w and n.y < glass.y + glass.h and glass.y < n.y + n.h:
                out.append(n)
        return out

    def glass_copies(self, glass, under: list, ind: str) -> list[str]:
        """Размытые копии того, что под стеклом, в его координатах (Modifier.blur — Android 12+)."""
        out = []
        for n in under:
            mod = (f"Modifier.wrapContentSize(Alignment.TopStart, unbounded = true)"
                   f".offset(x = {self.dp(n.x - glass.x)}, y = {self.dp(n.y - glass.y)})"
                   f".size({self.dp(n.w)}, {self.dp(n.h)}).blur({self.dp(glass.backdrop_blur)})")
            if n.type == "image":
                scale = {"cover": "Crop", "contain": "Fit"}.get(n.fit, "FillBounds")
                out.append(f"{ind}Image(painterResource(R.drawable.{self.g.drawables[n.asset_id]}), null, "
                           f"contentScale = ContentScale.{scale}, modifier = {mod})  // фон под стеклом")
            else:
                out.append(f"{ind}Box({mod}.background({brush(n, self.g.color) or self.g.color(n.fill)}))"
                           f"  // фон под стеклом")
        return out

    def variant_node(self, n, parent, mode: str, ind: str) -> list[str]:
        """Копия, у которой по нажатию меняется вариант: when по выбранным значениям, каждая ветка — свой вид."""
        from itertools import product

        from app.core.document.model import Node
        from app.engines.components import engine as ce
        from app.engines.layout import LayoutEngine
        d = self.g.doc.component(n.component_id)
        axes = self.variant_vars[n.id]
        names = list(axes)
        combos = list(product(*[list(d.variants[a]) for a in names]))
        self._expanding.add(n.id)
        try:
            if len(combos) > 32:
                return [f"{ind}// TODO: слишком много сочетаний вариантов ({len(combos)}) — показан текущий"] + \
                    self.node(n, parent, mode, ind)
            key = axes[names[0]] if len(names) == 1 else '"' + "|".join("${" + axes[a] + "}" for a in names) + '"'
            out = [f"{ind}// «{n.name}»: вид зависит от выбранного варианта ({', '.join(names)})",
                   f"{ind}when ({key}) {{"]
            engine = LayoutEngine()
            for i, combo in enumerate(combos):
                c = Node.from_dict(n.to_dict())
                c.variant = {**n.variant, **dict(zip(names, combo))}
                ce.materialize(d, c, engine)
                head = "else" if i == len(combos) - 1 else kstr("|".join(combo))
                out.append(f"{ind}    {head} -> {{")
                out += self.node(c, parent, mode, ind + "        ")
                out.append(f"{ind}    }}")
            return out + [f"{ind}}}"]
        finally:
            self._expanding.discard(n.id)

    def state_node(self, n, parent, mode: str, ind: str) -> list[str]:
        """Свой компонент, у которого меняется состояние: when по состоянию, каждая ветка — свой вид."""
        from app.core.document.model import Node
        from app.engines.components import engine as ce
        from app.engines.layout import LayoutEngine
        d = self.g.doc.component(n.component_id)
        states = list(dict.fromkeys(["default", *d.states]))[:12]  # «default» есть всегда
        var = self.state_vars[n.id]
        self._expanding.add(n.id)
        try:
            out = [f"{ind}// «{n.name}»: вид зависит от состояния ({', '.join(states)})", f"{ind}when ({var}) {{"]
            engine = LayoutEngine()
            for i, st in enumerate(states):
                c = Node.from_dict(n.to_dict())
                c.state = st
                ce.materialize(d, c, engine)
                head = "else" if i == len(states) - 1 else kstr(st)
                out.append(f"{ind}    {head} -> {{")
                out += self.node(c, parent, mode, ind + "        ")
                out.append(f"{ind}    }}")
            return out + [f"{ind}}}"]
        finally:
            self._expanding.discard(n.id)

    def behind(self, n) -> str:
        """Заливка ближайшего предка — то, на чём лежит текст."""
        try:
            chain = list(reversed(tree.ancestors(self.s, n.id)))
        except Exception:
            return ""
        return next((a.fill for a in chain if a.fill and a.type != "text"), "")

    def text(self, n, modtxt: str, ind: str) -> list[str]:
        align = {"left": "TextAlign.Start", "center": "TextAlign.Center", "right": "TextAlign.End"}[n.align]
        tc, fs = self.motion.var(n, "text_color"), self.motion.var(n, "font_size")  # анимации из студии
        style = (f"color = {tc + '.value' if tc else self.g.color(n.text_color, self.behind(n))}, "
                 f"fontSize = {fs + '.value.sp' if fs else _num(n.font_size / self.k) + '.sp'}, "
                 f"fontWeight = FontWeight({n.font_weight}), textAlign = {align}")
        if n.font_family in self.g.families:  # свой шрифт проекта (файл в res/font)
            style += f", fontFamily = {self.g.families[n.font_family]}"
        if n.letter_spacing:
            style += f", letterSpacing = {_num(n.letter_spacing / self.k)}.sp"
        if n.line_height:
            style += f", lineHeight = {_num(n.font_size * n.line_height / self.k)}.sp"
        if n.italic:
            style += ", fontStyle = FontStyle.Italic"
        if n.decoration != "none":
            style += f", textDecoration = TextDecoration.{'Underline' if n.decoration == 'underline' else 'LineThrough'}"
        if n.id in self.inputs:
            var = self.inputs[n.id]
            return ([f"{ind}BasicTextField(", f"{ind}    value = {var},",
                     f"{ind}    onValueChange = {{ {var} = it"] + self.input_change(n, var, ind + "        ") +
                    [f"{ind}    }},",
                     f"{ind}    textStyle = TextStyle({style}),",
                     f"{ind}    cursorBrush = SolidColor({self.g.color(n.text_color)}),",
                     f"{ind}    modifier = {modtxt},",
                     f"{ind}    decorationBox = {{ inner ->",
                     f"{ind}        if ({var}.isEmpty()) Text({kstr(n.text)}, {style.replace(self.g.color(n.text_color), self.g.color(n.text_color[:7] + '88'))})",
                     f"{ind}        inner()", f"{ind}    }},", f"{ind})"])
        bound = self.bound.get((n.id, "text"))  # строка списка: текст — из её данных (уже в нужном регистре)
        value = bound or self.texts.get(n.id)
        if value is None:
            value = self.res_text(_cased(n.text, n.text_case))
        elif bound is None and n.text_case != "none":  # текст меняется при работе — регистр в коде
            value += {"upper": ".uppercase()", "lower": ".lowercase()",
                      "title": '.split(" ").joinToString(" ") { it.replaceFirstChar(Char::titlecase) }'}[n.text_case]
        lines = ([f"{ind}    maxLines = {n.max_lines},", f"{ind}    overflow = TextOverflow.Ellipsis,"]
                 if n.max_lines else [])
        if n.font_size / self.k >= 22 and re.search(r"[A-Za-zА-Яа-яЁё]{3,}", n.text):  # крупный текст со словами —
            # заголовок: TalkBack переходит по заголовкам (цена «1 470 ₽» и «12 минут» — не заголовок)
            modtxt += f"\n{ind}        .semantics {{ heading() }}"
        return [f"{ind}Text(", f"{ind}    text = {value},", f"{ind}    {style},"] + lines + \
            [f"{ind}    modifier = {modtxt},", f"{ind})"]

    def res_text(self, text: str) -> str:
        """Неизменный текст — строковый ресурс (stringResource); пустой — как есть."""
        if not text.strip():
            return kstr(text)
        return f"stringResource(R.string.{self.g.string_key(text)})"

    def slots(self):
        """Верхняя панель, нижняя навигация и плавающая кнопка экрана — в слоты Scaffold (без смещений)."""
        s = self.s
        free = [n for n in s.nodes if n.visible and n.id not in self.vis]
        top = next((n for n in free if n.role.startswith("m3.top_app_bar") and n.y <= 1), None)
        nav = next((n for n in free if n.role == "m3.nav_bar" and n.y + n.h >= s.height - 1), None)
        fab = next((n for n in free if n.role in ("m3.fab", "m3.fab_extended") and n.x + n.w >= s.width * 0.7
                    and n.y >= s.height * 0.55), None)
        return top, nav, fab

    def scaffold(self, bg: str) -> list[str]:
        s = self.s
        top, nav, fab = self.slots()
        top_h = top.y + top.h if top else 0.0
        bot_h = s.height - nav.y if nav else 0.0
        from app.core.document.model import Node
        area = Node(type="frame", name="Содержимое", x=0, y=top_h, w=s.width, h=s.height - top_h - bot_h)
        max_w = max(600, round(s.width / self.k))  # на планшете содержимое не растягивается шире макета
        L = []
        if nav is not None:
            L.append("    val wide = LocalConfiguration.current.screenWidthDp >= 600  // планшет, сложенный экран")
        L += ["    Scaffold(", "        containerColor = MaterialTheme.colorScheme.background,",
              "        contentColor = MaterialTheme.colorScheme.onBackground,"]
        if top is not None:
            L += ["        topBar = {"] + self.node(top, None, "slot", "            ") + ["        },"]
        if nav is not None:
            L += ["        bottomBar = {", "            if (!wide) {"] + self.node(nav, None, "slot", "                ") + \
                 ["            }", "        },"]
        if fab is not None:
            L += ["        floatingActionButton = {"] + self.node(fab, None, "slot", "            ") + ["        },"]
        L += ["    ) { inner ->", "        Row(modifier = Modifier.fillMaxSize().padding(inner)) {"]
        if nav is not None:
            L += ["            if (wide) {"] + self.m3.rail(nav, "                ") + ["            }"]
        L += ["            Box(modifier = Modifier.weight(1f).fillMaxHeight(), contentAlignment = Alignment.TopCenter) {",
              f"                Box(modifier = Modifier.widthIn(max = {max_w}.dp).fillMaxSize()) {{"]
        L += self.children([n for n in s.nodes if n not in (top, nav, fab)], area, "abs", "                    ")
        L += ["                }", "            }", "        }", "    }", "}"]
        return L

    def input_change(self, n, var: str, ind: str) -> list[str]:
        """Строки обработчика изменения текста: связанная переменная и правила «Изменение текста»."""
        out = []
        v = self.g.doc.variable(n.input_var) if n.input_var else None
        if v is not None and v.type == "text":
            out.append(f"{ind}state.{self.g.state_names[v.id]} = it")
        for it in self.its:
            if it.node_id == n.id and it.trigger == "text_changed":
                out += self.actions_code(it, ind)
        return out

    PART_LINES = 300  # столько строк кода в одном блоке компилятор переваривает (больше — «Method too large»)
    SCOPES = {"abs": "BoxScope", "col": "ColumnScope", "row": "RowScope", "flow": "FlowRowScope"}

    def children(self, nodes: list, parent, ctx: str, ind: str) -> list[str]:
        """Код дочерних элементов; если его много — частями в локальных @Composable-функциях (каждая — свой метод
        JVM), иначе на экране из 40+ элементов сборка падает с «Method too large»."""
        blocks = [self.node(c, parent, ctx, ind) for c in nodes]
        if sum(len(b) for b in blocks) <= self.PART_LINES:
            return [line for b in blocks for line in b]
        out, chunk = [], []

        def flush():
            if not chunk:
                return
            self.parts += 1
            name = f"part{self.parts}"
            out.append(f"{ind}@Composable fun {self.SCOPES[ctx]}.{name}() {{")
            out.extend("    " + line for b in chunk for line in b)
            out.extend([f"{ind}}}", f"{ind}{name}()"])
            chunk.clear()
        for b in blocks:
            if chunk and sum(len(x) for x in chunk) + len(b) > self.PART_LINES:
                flush()
            chunk.append(b)
        flush()
        return out

    def _row_ok(self, row) -> bool:
        """Карточку можно сделать строкой списка: у неё и внутри нет своего поведения (показ, смена текста,
        состояния, анимации, поля ввода, прокрутки), только нажатие на саму карточку."""
        ids = {d.id for d, _, _ in tree.walk([row])}
        busy = (set(self.vis) | set(self.texts) | set(self.inputs) | set(self.state_vars) | set(self.variant_vars)
                | set(self.pagers) | set(self.dots_for) | set(self.scroll_states) | set(self.m3.state)
                | {nid for nid, _ in self.motion.vars} | set(self.smart.values()))
        if ids & busy or any(d.sticky for d, _, _ in tree.walk([row])):
            return False
        for it in self.its:
            if it.node_id in ids and (it.node_id != row.id or it.trigger != "tap"):
                return False
            if any(a.get("node_id") in ids for a in it.actions):
                return False
        return True

    def lazy(self, n, modtxt: str, ind: str) -> list[str] | None:
        """Прокручиваемый столбец (строка) с одинаковыми карточками подряд → LazyColumn (LazyRow) с данными."""
        from app.exporters import compose_lists as cl
        vertical = n.layout == "vertical"
        if n.paging or n.layout not in ("vertical", "horizontal") or n.main_align == "space_between" or \
                n.scroll != ("vertical" if vertical else "horizontal") or self.scroll_to or                 any(c.sticky for c in n.children):  # «прокрутить к» и липкие элементы — по состоянию прокрутки
            return None
        found = cl.runs(n.children, self.g.drawables, self._row_ok)
        if not found:
            return None
        lines = [x for x in modtxt.split("\n") if ".verticalScroll(" not in x and ".horizontalScroll(" not in x]
        pad = ""
        if len(lines) > 1 and lines[-1].strip().startswith(".padding(start = ") and (n.pad_t or n.pad_r or n.pad_b
                                                                                      or n.pad_l):
            lines.pop()  # поля контейнера — внутри списка (contentPadding), прокручиваются вместе с ним
            pad = (f"PaddingValues(start = {self.dp(n.pad_l)}, top = {self.dp(n.pad_t)}, end = {self.dp(n.pad_r)}, "
                   f"bottom = {self.dp(n.pad_b)})")
        mod = "\n".join(lines)
        if vertical:
            cross = {"start": "Start", "center": "CenterHorizontally", "end": "End", "stretch": "Start"}[n.cross_align]
            head = [f"{ind}LazyColumn(", f"{ind}    modifier = {mod},"] + \
                ([f"{ind}    contentPadding = {pad},"] if pad else []) + \
                [f"{ind}    verticalArrangement = Arrangement.spacedBy({self.dp(n.gap)}),",
                 f"{ind}    horizontalAlignment = Alignment.{cross},", f"{ind}) {{"]
            wrap, ctx = f"Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.{cross})", "col"
        else:
            vcross = {"start": "Top", "center": "CenterVertically", "end": "Bottom", "stretch": "Top"}[n.cross_align]
            head = [f"{ind}LazyRow(", f"{ind}    modifier = {mod},"] + \
                ([f"{ind}    contentPadding = {pad},"] if pad else []) + \
                [f"{ind}    horizontalArrangement = Arrangement.spacedBy({self.dp(n.gap)}),",
                 f"{ind}    verticalAlignment = Alignment.{vcross},", f"{ind}) {{"]
            wrap, ctx = f"Row(verticalAlignment = Alignment.{vcross})", "row"
        body, i, k = [], 0, 0
        ends = dict(found)
        while i < len(n.children):
            if i in ends:
                k += 1
                body += self.lazy_items(n, n.children[i:ends[i]], wrap, ctx, ind + "    ", k)
                i = ends[i]
                continue
            code = self.node(n.children[i], n, ctx, ind + "            ")
            if any(not x.strip().startswith("//") for x in code):  # заголовок и прочее — отдельный item
                body += [f"{ind}    item {{", f"{ind}        {wrap} {{"] + code + [f"{ind}        }}", f"{ind}    }}"]
            i += 1
        return head + body + [f"{ind}}}"]

    def lazy_items(self, parent, rows: list, wrap: str, ctx: str, ind: str, k: int) -> list[str]:
        """items(данные) { item -> строка }: данные — объявлением перед списком, строка — по первой карточке."""
        from app.exporters import compose_lists as cl
        walks = [[d for d, _, _ in tree.walk([r])] for r in rows]
        flds = [(i, p) for i, p in cl.fields(rows)
                if p != "image" or all(w[i].asset_id in self.g.drawables for w in walks)]
        cls = self.fn + ident(f"{parent.name} {k if k > 1 else ''} item", True, set(), "ListItem")
        taken: set[str] = {"onClick", "key"}
        names = {}
        for idx, prop in flds:
            names[(idx, prop)] = ident(f"{prop} {walks[0][idx].name}", False, taken, prop)
        row_ids = {r.id for r in rows}
        clicks = any(it.node_id in row_ids and it.trigger == "tap" for it in self.its)
        params = [f"val {names[f]}: {dict(text='String', image='Int', fill='Color')[f[1]]}" for f in flds]
        if clicks:
            params.append("val onClick: () -> Unit")
        if not params:
            params.append("val key: Int")
        self.data_classes.append(f"/** Строка списка «{parent.name}»: данные, которыми карточки отличаются. */\n"
                                 f"private data class {cls}({', '.join(params)})")
        var = ident(f"{parent.name} items", False, self.used, "items")
        self.pre.append(f"// список «{parent.name}»: замените данными приложения (сеть, база) — вид строки ниже")
        self.pre.append(f"val {var} = listOf(")
        for r_i, (r, w) in enumerate(zip(rows, walks)):
            args = []
            for (idx, prop) in flds:
                d = w[idx]
                v = (self.res_text(_cased(d.text, d.text_case)) if prop == "text" else
                     f"R.drawable.{self.g.drawables[d.asset_id]}" if prop == "image" else
                     self.g.color(d.fill) if d.fill else "Color.Transparent")
                args.append(f"{names[(idx, prop)]} = {v}")
            if not flds and not clicks:
                args.append(f"key = {r_i}")
            if clicks:
                acts = [x for it in self.its if it.node_id == r.id and it.trigger == "tap"
                        for x in self.actions_code(it, "        ")]
                self.pre.append(f"    {cls}({', '.join(args + ['onClick = {'])}")
                self.pre += acts + ["    }),"]
            else:
                self.pre.append(f"    {cls}({', '.join(args)}),")
        self.pre.append(")")
        tmpl = rows[0]
        for (idx, prop), nm in names.items():
            self.bound[(walks[0][idx].id, prop)] = f"item.{nm}"
        if clicks:
            self.row_click[tmpl.id] = "item.onClick()"
        try:
            code = self.node(tmpl, parent, ctx, ind + "        ")
        finally:
            for (idx, prop) in names:
                self.bound.pop((walks[0][idx].id, prop), None)
            self.row_click.pop(tmpl.id, None)
        return [f"{ind}items({var}) {{ item ->", f"{ind}    {wrap} {{"] + code + [f"{ind}    }}", f"{ind}}}"]

    def stack(self, n, modtxt: str, ind: str) -> list[str]:
        lazy = self.lazy(n, modtxt, ind)
        if lazy is not None:
            return lazy
        main = {"start": "Start", "center": "Center", "end": "End", "space_between": "SpaceBetween"}[n.main_align]
        cross = {"start": "Start", "center": "CenterHorizontally", "end": "End", "stretch": "Start"}[n.cross_align]
        if n.layout == "vertical":
            arr = (f"Arrangement.SpaceBetween" if main == "SpaceBetween" else
                   f"Arrangement.spacedBy({self.dp(n.gap)}, Alignment.{ {'Start': 'Top', 'Center': 'CenterVertically', 'End': 'Bottom'}[main] })")
            out = [f"{ind}Column(", f"{ind}    modifier = {modtxt},", f"{ind}    verticalArrangement = {arr},",
                   f"{ind}    horizontalAlignment = Alignment.{cross},", f"{ind}) {{"]
            return out + self.children(n.children, n, "col", ind + "    ") + [f"{ind}}}"]
        if n.layout == "horizontal":
            vcross = {"start": "Top", "center": "CenterVertically", "end": "Bottom", "stretch": "Top"}[n.cross_align]
            arr = (f"Arrangement.SpaceBetween" if main == "SpaceBetween" else
                   f"Arrangement.spacedBy({self.dp(n.gap)}, Alignment.{ {'Start': 'Start', 'Center': 'CenterHorizontally', 'End': 'End'}[main] })")
            out = [f"{ind}Row(", f"{ind}    modifier = {modtxt},", f"{ind}    horizontalArrangement = {arr},",
                   f"{ind}    verticalAlignment = Alignment.{vcross},", f"{ind}) {{"]
            return out + self.children(n.children, n, "row", ind + "    ") + [f"{ind}}}"]
        if n.layout == "wrap":  # с переносом: FlowRow, выравнивание — внутри строки
            vcross = {"start": "Top", "center": "CenterVertically", "end": "Bottom", "stretch": "Top"}[n.cross_align]
            arr = (f"Arrangement.spacedBy({self.dp(n.gap)})" if main == "Start" else
                   "Arrangement.SpaceBetween" if main == "SpaceBetween" else
                   f"Arrangement.spacedBy({self.dp(n.gap)}, Alignment.{ {'Center': 'CenterHorizontally', 'End': 'End'}[main] })")
            out = [f"{ind}FlowRow(", f"{ind}    modifier = {modtxt},", f"{ind}    horizontalArrangement = {arr},",
                   f"{ind}    verticalArrangement = Arrangement.spacedBy({self.dp(n.row_gap)}),",
                   f"{ind}    itemVerticalAlignment = Alignment.{vcross},", f"{ind}) {{"]
            return out + self.children(n.children, n, "flow", ind + "    ") + [f"{ind}}}"]
        cols = max(1, n.grid_columns)  # сетка: строки по cols элементов
        out = [f"{ind}Column(modifier = {modtxt}, verticalArrangement = Arrangement.spacedBy({self.dp(n.row_gap)})) {{"]
        for i in range(0, len(n.children), cols):
            out.append(f"{ind}    Row(horizontalArrangement = Arrangement.spacedBy({self.dp(n.gap)})) {{")
            for c in n.children[i:i + cols]:
                out += self.node(c, n, "row", ind + "        ")
            out.append(f"{ind}    }}")
        return out + [f"{ind}}}"]

    def source(self) -> str:
        s, g = self.s, self.g
        bg = kcolor(g.artboard)
        L = [f"package {g.pkg}.ui.screens", "", *g.imports(), "",
             f"/** Экран «{s.name}» ({_num(s.width / self.k)} × {_num(s.height / self.k)} dp). Сгенерирован App Design Studio. */",
             "@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)",
             "@Composable",
             f"fun {self.fn}(state: AppState, onNavigate: (String, NavMotion) -> Unit, onBack: () -> Unit) {{"]
        L += self.m3.decls + self.motion.decls
        if self.waits and "    val scope = rememberCoroutineScope()" not in L:
            L.append("    val scope = rememberCoroutineScope()")
        if self.scroll_to:
            L.append("    val density = LocalDensity.current")
        for _nid, var in self.scroll_states.items():
            L.append(f"    val {var} = rememberScrollState()")
        for nid, var in self.pagers.items():
            L.append(f"    val {var} = rememberPagerState {{ {len(tree.find(s, nid)[0].children)} }}")
        m = tree.node_map(s)
        for nid, var in self.vis.items():
            L.append(f"    var {var} by rememberSaveable {{ mutableStateOf({'true' if m[nid].visible and nid not in self.overlays else 'false'}) }}")
        for nid, var in self.texts.items():
            L.append(f"    var {var} by rememberSaveable {{ mutableStateOf({kstr(m[nid].text)}) }}")
        for nid, axes in self.variant_vars.items():
            d = g.doc.component(m[nid].component_id)
            for axis, var in axes.items():
                vals = list(d.variants[axis])
                cur = m[nid].variant.get(axis) if m[nid].variant.get(axis) in vals else vals[0]
                L.append(f"    var {var} by rememberSaveable {{ mutableStateOf({kstr(cur)}) }}")
        for nid, var in self.inputs.items():
            L.append(f"    var {var} by rememberSaveable {{ mutableStateOf(\"\") }}")
        for nid, var in self.state_vars.items():
            L.append(f"    var {var} by rememberSaveable {{ mutableStateOf({kstr(m[nid].state)}) }}")
        opens = [it for it in self.its if it.trigger == "screen_open"]
        if opens:
            L.append("    LaunchedEffect(Unit) {")
            for it in opens:
                L += self.actions_code(it, "        ")
            L.append("    }")
        L += self.scaffold(bg)
        if self.res_vals:  # строки для действий «Задать текст» — ресурсы, прочитанные до обработчиков
            at = next(i for i, x in enumerate(L) if x.startswith(f"fun {self.fn}(")) + 1
            L[at:at] = [f"    val {v} = {self.res_text(t)}" for t, v in self.res_vals.items()]
        if self.data_classes:  # строки списков из данных (LazyColumn) — классы данных перед экраном
            at = next(i for i, x in enumerate(L) if x.startswith("/** Экран «"))
            L[at:at] = [x for c in self.data_classes for x in (c, "")]
        wdp, hdp = round(s.width / self.k), round(s.height / self.k)
        L += ["", f"@Preview(name = \"Телефон\", widthDp = {wdp}, heightDp = {hdp}, showBackground = true)",
              "@Preview(name = \"Маленький телефон\", widthDp = 360, heightDp = 640, showBackground = true)",
              "@Preview(name = \"Планшет\", widthDp = 840, heightDp = 1200, showBackground = true)",
              "@Composable",
              f"private fun {self.fn}Preview() {{",
              f"    AppTheme {{ {self.fn}(AppState(), onNavigate = {{ _, _ -> }}, onBack = {{}}) }}", "}", ""]
        if self.motion.todo:
            L.insert(L.index("@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)"),
                     "// TODO: анимации, которые не переведены автоматически (обводка):\n"
                     + "\n".join(f"//   {t}" for t in self.motion.todo))
        hovers = [it for it in self.its if it.trigger in ("hover_enter", "hover_leave")]
        if hovers:
            L.insert(L.index("@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)"),
                     "// Наведение мыши на телефоне не бывает — эти правила в приложение не перенесены")
        return "\n".join(L)


class AndroidProject:
    def __init__(self, doc: ProjectDocument, screens: list[Screen], drawables: dict[str, tuple[str, bytes, str]],
                 fonts: dict[str, tuple[str, bytes, str]] | None = None,
                 widget_previews: dict[str, bytes] | None = None):
        """drawables — {asset_id: (имя ресурса, данные, расширение)} для включённых растровых изображений;
        fonts — то же для файлов шрифтов (ttf / otf)."""
        self.doc = doc
        from app.exporters.glance import is_widget
        self.widget_screens = [s for s in screens if is_widget(s)]  # виджеты рабочего стола — Glance, не экраны
        self.widget_previews = {k: v for k, v in (widget_previews or {}).items() if v}  # картинка в списке виджетов
        self.strings: dict[str, str] = {}   # текст → имя ресурса (values/strings.xml — для перевода приложения)
        self._string_names: set[str] = {"app_name"}
        screens = [s for s in screens if not is_widget(s)]
        self._font_files = fonts or {}
        # семейство шрифта → имя FontFamily в коде и начертания (ресурс, насыщенность, курсив)
        from app.exporters.fontinfo import weight_italic
        fused: set[str] = set()
        self.families: dict[str, str] = {}
        self.faces: dict[str, list[tuple[str, int, bool]]] = {}
        by_id = {a.id: a for a in doc.assets}
        for aid, (name, data, _ext) in sorted(fonts.items() if fonts else []):
            fam = by_id[aid].family if aid in by_id else ""
            if not fam:
                continue
            if fam not in self.families:
                self.families[fam] = ident(f"{fam} font", True, fused, "Font")
            w, it = weight_italic(data)
            self.faces.setdefault(fam, []).append((name, w, it))
        self.screens = [s for s in screens if s.platform == PLATFORM_ANDROID]
        self.pkg = package_name(doc.meta.title)
        from app.engines.material.generations import OLD
        self.classic_switch = doc.meta.appearance.material in OLD  # переключатель Material 1 / 2
        self.link_scheme = re.sub(r"[^a-z0-9]", "", self.pkg.rsplit(".", 1)[-1]) or "app"  # ссылки на экраны
        self.artboard = ARTBOARD_COLORS.get(doc.meta.appearance.theme, "#000000")
        self.drawables = {aid: name for aid, (name, _, _) in drawables.items()}
        self._drawable_files = drawables
        used: set[str] = set()
        self.fns = {s.id: ident(s.name, True, used, "Screen") + "Screen" for s in self.screens}
        self.routes = route_names(self.screens)  # «Корзина» → korzina: ссылка dostavka://korzina
        vused: set[str] = set()
        self.state_names = {v.id: ident(v.name, False, vused, "value") for v in doc.variables}
        self.roles = self._role_map()
        # имена для умного перехода: есть переход smart и имя встречается (по одному разу) хотя бы на двух экранах
        self.smart_names: set[str] = set()
        if any(a["type"] == "navigate" and a.get("transition") == "smart" for it in doc.interactions
               for a in it.actions):
            from collections import Counter
            counts = Counter(name for s in self.screens for name in smart_keys(s))
            self.smart_names = {name for name, c in counts.items() if c >= 2}

    def _role_map(self) -> dict[str, str]:
        """#RRGGBB → роль схемы дизайна (фон дизайна — background): такие цвета в коде берутся из темы."""
        ap = self.doc.meta.appearance
        sch = scheme(ap.accent, ap.theme != "light")
        self.scheme = {k: v.upper() for k, v in sch.items()}
        from app.engines.material.restyle import ORDERED_ROLES
        out = {self.artboard.upper(): "background"}
        for r in ORDERED_ROLES:
            if r not in ("shadow", "scrim", "background", "onBackground"):
                out.setdefault(sch[r].upper(), r)
        return out

    def on_role(self, c: str, behind: str) -> str | None:
        """Текст на заливке роли темы: его цвет — пара «on…» этой роли (белый на primary — onPrimary),
        иначе в тёмной теме текст получил бы цвет фона и пропал."""
        under = self.roles.get((behind or "")[:7].upper())
        if not c or under is None:
            return None
        on = "on" + under[0].upper() + under[1:]
        return on if self.scheme.get(on) == c[:7].upper() else None

    def color(self, c: str, behind: str = "") -> str:
        """Цвет для кода: роль темы (меняется со светлой / тёмной темой и цветами обоев) или точный цвет.
        behind — заливка под текстом: для пары «on…» роли."""
        if not c:
            return kcolor(c)
        role = self.on_role(c, behind) or self.roles.get(c[:7].upper())
        if role is None:
            return kcolor(c)
        alpha = c[7:9]
        if alpha and alpha.upper() != "FF":
            return f"MaterialTheme.colorScheme.{role}.copy(alpha = {int(alpha, 16) / 255:.2f}f)"
        return f"MaterialTheme.colorScheme.{role}"

    def imports(self) -> list[str]:
        return [f"import {x}" for x in (
            "androidx.compose.animation.AnimatedVisibility",
            "androidx.compose.animation.fadeIn", "androidx.compose.animation.fadeOut",
            "androidx.compose.animation.core.Animatable",
            "androidx.compose.animation.core.CubicBezierEasing", "androidx.compose.animation.core.LinearEasing",
            "androidx.compose.animation.core.RepeatMode", "androidx.compose.animation.core.infiniteRepeatable",
            "androidx.compose.animation.core.keyframes",
            "androidx.compose.foundation.*", "androidx.compose.foundation.layout.*",
            "androidx.compose.foundation.selection.selectable",
            "androidx.compose.foundation.shape.*", "androidx.compose.foundation.text.BasicTextField",
            "androidx.compose.material3.*", "androidx.compose.runtime.*", "androidx.compose.ui.Alignment",
            "androidx.compose.ui.Modifier", "androidx.compose.ui.draw.alpha", "androidx.compose.ui.draw.blur",
            "androidx.compose.ui.draw.clip", "androidx.compose.ui.draw.shadow", "androidx.compose.ui.graphics.Brush",
            "androidx.compose.ui.graphics.graphicsLayer",
            "androidx.compose.ui.geometry.Offset", "androidx.compose.ui.graphics.Color",
            "androidx.compose.ui.graphics.PathFillType",
            "androidx.compose.ui.graphics.RectangleShape", "androidx.compose.ui.graphics.SolidColor",
            "androidx.compose.ui.graphics.drawscope.Stroke", "androidx.compose.ui.graphics.drawscope.scale",
            "androidx.compose.ui.graphics.vector.PathParser", "androidx.compose.ui.layout.ContentScale",
            "androidx.compose.ui.platform.LocalConfiguration",
            "androidx.compose.ui.res.painterResource", "androidx.compose.ui.text.TextStyle",
            "androidx.compose.ui.text.font.FontWeight", "androidx.compose.ui.text.style.TextAlign",
            "androidx.compose.ui.text.font.FontStyle", "androidx.compose.ui.text.style.TextDecoration",
            "androidx.compose.ui.text.style.TextOverflow", "androidx.compose.ui.draw.drawWithContent",
            "androidx.compose.ui.draw.dropShadow", "androidx.compose.ui.draw.innerShadow",
            "androidx.compose.ui.graphics.PathEffect", "androidx.compose.ui.graphics.StrokeCap",
            "androidx.compose.ui.graphics.drawOutline", "androidx.compose.ui.graphics.drawscope.inset",
            "androidx.compose.ui.unit.DpOffset", "androidx.compose.animation.slideInVertically",
            "androidx.compose.ui.unit.IntOffset", "androidx.compose.ui.zIndex",
            "androidx.compose.foundation.gestures.detectDragGestures", "androidx.compose.ui.input.pointer.pointerInput",
            "androidx.compose.ui.res.stringResource", "androidx.compose.ui.semantics.heading",
            "androidx.compose.ui.semantics.semantics",
            "androidx.compose.runtime.saveable.rememberSaveable",
            "kotlin.math.abs",
            "androidx.compose.ui.platform.LocalDensity", "androidx.compose.foundation.pager.HorizontalPager",
            "androidx.compose.foundation.pager.VerticalPager",
            "androidx.compose.foundation.pager.rememberPagerState",
            "androidx.compose.foundation.lazy.LazyColumn", "androidx.compose.foundation.lazy.LazyRow",
            "androidx.compose.foundation.lazy.items",
            "androidx.compose.animation.slideOutVertically",
            "androidx.compose.foundation.interaction.MutableInteractionSource", "kotlinx.coroutines.delay",
            f"{self.pkg}.navigation.smart",
            "androidx.compose.ui.text.input.PasswordVisualTransformation",
            "androidx.compose.ui.text.input.VisualTransformation",
            "androidx.compose.ui.tooling.preview.Preview", "androidx.compose.ui.unit.dp",
            "androidx.compose.ui.unit.sp", f"{self.pkg}.AppState", f"{self.pkg}.R", f"{self.pkg}.fmt",
            f"{self.pkg}.navigation.NavMotion", f"{self.pkg}.navigation.StepEasing",
            f"{self.pkg}.ui.components.DesignIcon", f"{self.pkg}.ui.components.linearAngleBrush",
            f"{self.pkg}.ui.components.maskShape", "androidx.compose.ui.graphics.BlendMode",
            f"{self.pkg}.ui.theme.AppTheme", "kotlinx.coroutines.coroutineScope", "kotlinx.coroutines.launch")] + \
            [f"import {self.pkg}.ui.theme.{v}" for v in self.families.values()] + \
            ([f"import {self.pkg}.ui.components.ClassicSwitch"] if self.classic_switch else [])

    def literal(self, var_type: str, value) -> str:
        from app.core.document.behavior import coerce
        try:
            v = coerce(var_type, value)
        except Exception:  # noqa: BLE001 — неверное значение даёт значение по умолчанию типа
            v = {"bool": False, "number": 0.0, "text": ""}[var_type]
        if var_type == "bool":
            return "true" if v else "false"
        if var_type == "number":
            return f"{float(v)}"
        return kstr(str(v))

    def files(self) -> dict[str, bytes]:
        out: dict[str, str | bytes] = {}
        v, pkg, path = VERSIONS, self.pkg, self.pkg.replace(".", "/")
        app_name = self.doc.meta.title
        from app.exporters.glance import GLANCE_VERSION
        glance_dep = (f'\n    implementation("androidx.glance:glance-appwidget:{GLANCE_VERSION}")'
                      if self.widget_screens else "")  # виджеты рабочего стола — библиотека Glance
        out["settings.gradle.kts"] = f'''pluginManagement {{
    repositories {{
        google()
        mavenCentral()
        gradlePluginPortal()
    }}
}}
dependencyResolutionManagement {{
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {{
        google()
        mavenCentral()
    }}
}}
rootProject.name = {kstr(re.sub(r"[^A-Za-z0-9 _-]", "", _translit(app_name)).strip() or "DesignApp")}
include(":app")
'''
        out["build.gradle.kts"] = '''plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.compose) apply false
}
'''
        out["gradle.properties"] = "org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8\nandroid.useAndroidX=true\nkotlin.code.style=official\nandroid.nonTransitiveRClass=true\n"
        out["gradle/libs.versions.toml"] = f'''[versions]
agp = "{v['agp']}"
kotlin = "{v['kotlin']}"
composeBom = "{v['compose_bom']}"
activityCompose = "{v['activity_compose']}"
coreKtx = "{v['core_ktx']}"

[libraries]
androidx-core-ktx = {{ group = "androidx.core", name = "core-ktx", version.ref = "coreKtx" }}
androidx-activity-compose = {{ group = "androidx.activity", name = "activity-compose", version.ref = "activityCompose" }}
androidx-compose-bom = {{ group = "androidx.compose", name = "compose-bom", version.ref = "composeBom" }}
androidx-ui = {{ group = "androidx.compose.ui", name = "ui" }}
androidx-ui-graphics = {{ group = "androidx.compose.ui", name = "ui-graphics" }}
androidx-ui-tooling = {{ group = "androidx.compose.ui", name = "ui-tooling" }}
androidx-ui-tooling-preview = {{ group = "androidx.compose.ui", name = "ui-tooling-preview" }}
androidx-material3 = {{ group = "androidx.compose.material3", name = "material3" }}

[plugins]
android-application = {{ id = "com.android.application", version.ref = "agp" }}
kotlin-android = {{ id = "org.jetbrains.kotlin.android", version.ref = "kotlin" }}
kotlin-compose = {{ id = "org.jetbrains.kotlin.plugin.compose", version.ref = "kotlin" }}
'''
        out["gradle/wrapper/gradle-wrapper.properties"] = f"distributionBase=GRADLE_USER_HOME\ndistributionPath=wrapper/dists\ndistributionUrl=https\\://services.gradle.org/distributions/gradle-{v['gradle']}-bin.zip\nzipStoreBase=GRADLE_USER_HOME\nzipStorePath=wrapper/dists\n"
        out[".gitignore"] = "*.iml\n.gradle/\n/local.properties\n/release.properties\n*.jks\n/.idea/\n.DS_Store\n/build/\n/app/build/\n/captures/\n.externalNativeBuild/\n.cxx/\n"
        out["app/build.gradle.kts"] = f'''import java.util.Properties
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

// Подпись для Google Play: release.properties рядом с проектом (создаёт App Design Studio при сборке AAB;
// в Git не попадает). Без него release собирается без подписи.
val release = Properties().apply {{
    val f = rootProject.file("release.properties")
    if (f.exists()) f.inputStream().use {{ load(it) }}
}}

plugins {{
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}}

android {{
    namespace = "{pkg}"
    compileSdk = {v['compile_sdk']}

    defaultConfig {{
        applicationId = "{pkg}"
        minSdk = {v['min_sdk']}
        targetSdk = {v['target_sdk']}
        versionCode = (release.getProperty("versionCode") ?: "1").toInt()
        versionName = release.getProperty("versionName") ?: "1.0"
    }}

    signingConfigs {{
        if (release.getProperty("storeFile") != null) {{
            create("upload") {{
                storeFile = file(release.getProperty("storeFile"))
                storePassword = release.getProperty("storePassword")
                keyAlias = release.getProperty("keyAlias")
                keyPassword = release.getProperty("keyPassword")
            }}
        }}
    }}

    buildTypes {{
        release {{
            isMinifyEnabled = false
            signingConfigs.findByName("upload")?.let {{ signingConfig = it }}
        }}
    }}
    compileOptions {{
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }}
    buildFeatures {{
        compose = true
    }}
}}

kotlin {{
    compilerOptions {{
        jvmTarget.set(JvmTarget.JVM_17)
    }}
}}

dependencies {{
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    debugImplementation(libs.androidx.ui.tooling){glance_dep}
    implementation("androidx.core:core-splashscreen:1.0.1")
}}
'''
        has_icon = bool(self.doc.meta.appearance.app_icon
                        and self.doc.asset_data.get(self.doc.meta.appearance.app_icon))
        icon_attrs = ('\n        android:icon="@mipmap/ic_launcher"\n        android:roundIcon="@mipmap/ic_launcher_round"'
                      if has_icon else "")
        from app.exporters.glance import GLANCE_VERSION, GlanceWidget
        wused: set[str] = set()
        widgets = [GlanceWidget(self, s, ident(s.name.replace("Виджет", ""), True, wused, "Home"))
                   for s in self.widget_screens]
        receivers = "".join(w.receiver_xml() for w in widgets)
        out["app/src/main/AndroidManifest.xml"] = f'''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application
        android:allowBackup="true"
        android:label="@string/app_name"{icon_attrs}
        android:supportsRtl="true"
        android:enableOnBackInvokedCallback="true"
        android:theme="@android:style/Theme.Material.NoActionBar">
        <activity
            android:name=".MainActivity"
            android:theme="@style/Theme.App.Starting"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
            <intent-filter>
                <action android:name="android.intent.action.VIEW" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.BROWSABLE" />
                <data android:scheme="{self.link_scheme}" />
            </intent-filter>
        </activity>
{receivers}    </application>
</manifest>
'''
        esc = self.xml_string(app_name)
        # заставка запуска (Splash Screen API): фон — цвет фона дизайна, значок — иконка приложения
        light = self.doc.meta.appearance.theme == "light"
        icon_item = ('        <item name="windowSplashScreenAnimatedIcon">@mipmap/ic_launcher</item>\n'
                     if has_icon else "")  # без своей иконки — иконка приложения по умолчанию
        post = "@android:style/Theme.Material.Light.NoActionBar" if light else "@android:style/Theme.Material.NoActionBar"

        def splash(bg: str) -> str:
            return ('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
                    f'    <color name="splash_background">{bg}</color>\n'
                    '    <style name="Theme.App.Starting" parent="Theme.SplashScreen">\n'
                    '        <item name="windowSplashScreenBackground">@color/splash_background</item>\n'
                    + icon_item +
                    f'        <item name="postSplashScreenTheme">{post}</item>\n'
                    '    </style>\n</resources>\n')
        out["app/src/main/res/values/splash.xml"] = splash(self.artboard)
        if self.doc.meta.appearance.app_theme == "system":  # тёмная тема телефона — без белой вспышки
            out["app/src/main/res/values-night/splash.xml"] = splash("#121212" if light else self.artboard)
        icon = self.doc.meta.appearance.app_icon
        data = self.doc.asset_data.get(icon) if icon else None
        if data:  # иконка из дизайна: адаптивная (Android 8+), картинка в безопасной зоне на подложке
            out["app/src/main/res/drawable-nodpi/ic_launcher_art.png"] = data
            bg = self.doc.meta.appearance.app_icon_bg or "#FFFFFF"
            out["app/src/main/res/values/ic_launcher_background.xml"] = (
                '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
                f'    <color name="ic_launcher_background">{bg}</color>\n</resources>\n')
            xml = ('<?xml version="1.0" encoding="utf-8"?>\n'
                   '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
                   '    <background android:drawable="@color/ic_launcher_background" />\n'
                   '    <foreground>\n'
                   '        <inset android:drawable="@drawable/ic_launcher_art" android:inset="16.7%" />\n'
                   '    </foreground>\n'
                   '</adaptive-icon>\n')
            out["app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml"] = xml
            out["app/src/main/res/mipmap-anydpi-v26/ic_launcher_round.xml"] = xml
        wstr = "".join(f'    <string name="{w.res}_widget_label">{self.xml_string(w.title())}</string>\n'
                       f'    <string name="{w.res}_widget_description">{self.xml_string(w.s.name)}</string>\n'
                       for w in widgets)
        out["app/src/main/res/values/strings.xml"] = f'<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <string name="app_name">{esc}</string>\n{wstr}</resources>\n'
        for aid, (name, data, ext) in sorted(self._drawable_files.items()):
            out[f"app/src/main/res/drawable/{name}.{ext}"] = data
        for aid, (name, data, ext) in sorted(self._font_files.items()):
            out[f"app/src/main/res/font/{name}.{ext}"] = data
        src = f"app/src/main/java/{path}"
        start = self.routes[self.screens[0].id] if self.screens else "screen1"
        ap = self.doc.meta.appearance
        bars = ("statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT), "
                "navigationBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT)"
                if ap.theme != "light" and ap.app_theme != "system" else "")  # светлые значки на тёмной теме
        out[f"{src}/MainActivity.kt"] = f'''package {pkg}

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import {pkg}.navigation.AppNavHost
import {pkg}.ui.theme.AppTheme

class MainActivity : ComponentActivity() {{
    override fun onCreate(savedInstanceState: Bundle?) {{
        installSplashScreen()  // заставка запуска, затем — тема приложения
        super.onCreate(savedInstanceState)
        enableEdgeToEdge({bars})
        // ссылка «{self.link_scheme}://{self.routes[self.screens[-1].id] if self.screens else 'screen1'}» открывает нужный экран (маршруты — в README_ANDROID.md)
        val link = intent?.data?.host
        setContent {{
            AppTheme {{
                AppNavHost(startRoute = link)
            }}
        }}
    }}
}}
'''
        fields = []
        for var in self.doc.variables:
            t = {"bool": "Boolean", "number": "Double", "text": "String"}[var.type]
            fields.append(f"    /** «{var.name}» */\n    var {self.state_names[var.id]} by mutableStateOf<{t}>({self.literal(var.type, var.default)})")
        names = [self.state_names[v.id] for v in self.doc.variables]
        kinds = {"bool": "Boolean", "number": "Double", "text": "String"}
        restore = "; ".join(f"{n} = it[{i}] as {kinds[v.type]}" for i, (n, v) in enumerate(zip(names, self.doc.variables)))
        out[f"{src}/AppState.kt"] = f'''package {pkg}

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.setValue

/** Переменные прототипа (общие для всех экранов). */
class AppState {{
{chr(10).join(fields) if fields else "    // переменных в дизайне нет"}

    companion object {{
        /** Значения переменных переживают поворот экрана и выгрузку приложения из памяти. */
        val Saver = listSaver<AppState, Any>(
            save = {{ listOf<Any>({", ".join(f"it.{n}" for n in names)}) }},
            restore = {{ AppState().apply {{ {restore} }} }},
        )
    }}
}}

/** Число без «.0» для подстановки в текст. */
fun fmt(value: Any): String = if (value is Double && value % 1.0 == 0.0) value.toLong().toString() else value.toString()
'''
        routes = "\n".join(f'            "{self.routes[s.id]}" -> {self.fns[s.id]}(state, go, back)'
                           for s in self.screens)
        out[f"{src}/navigation/NavMotion.kt"] = NAV_MOTION.replace("{pkg}", pkg)
        out[f"{src}/ui/components/Gradients.kt"] = GRADIENT_KT.replace("{pkg}", pkg)
        imports = "\n".join(f"import {pkg}.ui.screens.{self.fns[s.id]}" for s in self.screens)
        routes_set = ", ".join(f'"{self.routes[s.id]}"' for s in self.screens)
        out[f"{src}/navigation/AppNavHost.kt"] = f'''package {pkg}.navigation

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.ExperimentalSharedTransitionApi
import androidx.compose.animation.SharedTransitionLayout
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.SnapshotStateList
import {pkg}.AppState
{imports}

private data class Entry(val route: String, val motion: NavMotion)

/** Стек экранов переживает поворот: маршрут и переход каждого шага — строками и числами. */
private val StackSaver = listSaver<SnapshotStateList<Entry>, Any>(
    save = {{ it.flatMap {{ e -> listOf(e.route, e.motion.kind, e.motion.durationMs, e.motion.easing) }} }},
    restore = {{ list ->
        mutableStateListOf<Entry>().apply {{
            list.chunked(4).forEach {{ (r, k, d, e) -> add(Entry(r as String, NavMotion(k as String, d as Int, e as String))) }}
        }}
    }},
)

/** Маршруты экранов (для ссылок вида схема://маршрут). */
val ROUTES = setOf({routes_set})

/**
 * Навигация по экранам дизайна: стек маршрутов с переходами из прототипа (затухание, сдвиги);
 * системная «Назад» возвращает на предыдущий экран обратным переходом.
 * При росте приложения замените на Navigation Compose — маршруты уже названы.
 */
@OptIn(ExperimentalSharedTransitionApi::class)
@Composable
fun AppNavHost(startRoute: String? = null) {{
    val state = rememberSaveable(saver = AppState.Saver) {{ AppState() }}
    val first = if (startRoute in ROUTES) startRoute!! else "{start}"  // ссылка на неизвестный экран — первый
    val stack = rememberSaveable(saver = StackSaver) {{ mutableStateListOf(Entry(first, NavMotion("none", 0))) }}
    var forward by rememberSaveable {{ mutableStateOf(true) }}
    var smartOn by rememberSaveable {{ mutableStateOf(false) }}  // умный переход: общие элементы перетекают
    val go: (String, NavMotion) -> Unit = {{ route, motion ->
        forward = true; smartOn = motion.kind == "smart"; stack.add(Entry(route, motion))
    }}
    val back: () -> Unit = {{
        if (stack.size > 1) {{
            forward = false; smartOn = stack.last().motion.kind == "smart"; stack.removeAt(stack.lastIndex)
        }}
    }}
    BackHandler(enabled = stack.size > 1) {{ back() }}
    SharedTransitionLayout {{
        val shared = this
        AnimatedContent(
            targetState = stack.last(),
            transitionSpec = {{ screenTransition(if (forward) targetState.motion else initialState.motion, forward) }},
            label = "screen",
        ) {{ entry ->
            CompositionLocalProvider(LocalSharedScope provides shared, LocalNavScope provides this,
                                     LocalSmartOn provides smartOn) {{
                when (entry.route) {{
{routes}
                }}
            }}
        }}
    }}
}}
'''
        out[f"{src}/ui/theme/Theme.kt"] = self.theme_kt()
        out[f"{src}/ui/theme/Type.kt"] = self.type_kt()
        for w in widgets:  # виджеты рабочего стола (Jetpack Glance)
            for path, text in w.files(src).items():
                out[path] = text
        if self.families:
            out[f"{src}/ui/theme/Fonts.kt"] = self.fonts_kt()
        out[f"{src}/ui/components/DesignIcon.kt"] = DESIGN_ICON.replace("{pkg}", pkg)
        if self.classic_switch:
            out[f"{src}/ui/components/ClassicSwitch.kt"] = CLASSIC_SWITCH.replace("{pkg}", pkg)
        for s in self.screens:
            out[f"{src}/ui/screens/{self.fns[s.id]}.kt"] = _Screen(self, s, self.fns[s.id]).source()
        if self.strings:  # тексты экранов — ресурсы: приложение можно перевести (values-en/strings.xml и т. п.)
            extra = "".join(f'    <string name="{k}"{" formatted=\"false\"" if "%" in t else ""}>{self.xml_string(t)}</string>\n'
                            for t, k in self.strings.items())
            key = "app/src/main/res/values/strings.xml"
            out[key] = out[key].replace("</resources>", extra + "</resources>")
        out["README_ANDROID.md"] = self.readme()
        return {f"{ROOT}/{p}": (b if isinstance(b, bytes) else b.encode("utf-8")) for p, b in sorted(out.items())}

    def theme_kt(self) -> str:
        ap = self.doc.meta.appearance
        dark = ap.theme != "light"
        cused = {"Accent", "Background", "LightScheme", "DarkScheme", "AppTheme", "DesignIsDark"}
        colors = "\n".join(f"val {ident(c.name, True, cused, 'Token')} = {kcolor(c.value)}" for c in self.doc.colors)

        def block(name: str, fn: str, sch: dict) -> str:
            roles = "\n".join(f"    {r} = {kcolor(sch[r])}," for r in COLOR_ROLES if r != "shadow")
            return f"private val {name} = {fn}(\n{roles}\n)"
        light, darks = scheme(ap.accent, False), scheme(ap.accent, True)
        if dark:  # фон дизайна (AMOLED-чёрный и т. п.) сохраняется
            darks = darks | {"background": self.artboard}
        else:
            light = light | {"background": self.artboard}
        follow = ap.app_theme == "system"
        return f"""package {self.pkg}.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

// Цвет бренда и фон дизайна
val Accent = {kcolor(ap.accent)}
val Background = {kcolor(self.artboard)}

// Цвета проекта (токены)
{colors or "// токенов в дизайне нет"}

/** Тема дизайна: {"тёмная" if dark else "светлая"}. Схемы Material 3 построены по цвету бренда {ap.accent}. */
const val DesignIsDark = {"true" if dark else "false"}

{block("LightScheme", "lightColorScheme", light)}

{block("DarkScheme", "darkColorScheme", darks)}

/** Светлая или тёмная: {"как в телефоне" if follow else "как в дизайне"}. Цвета из обоев (Android 12+): {"да" if ap.dynamic_color else "нет"}. */
const val FollowSystemTheme = {"true" if follow else "false"}
const val UseWallpaperColors = {"true" if ap.dynamic_color else "false"}

@Composable
fun AppTheme(
    darkTheme: Boolean = if (FollowSystemTheme) isSystemInDarkTheme() else DesignIsDark,
    dynamicColor: Boolean = UseWallpaperColors,
    content: @Composable () -> Unit,
) {{
    val colors = when {{
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S ->
            if (darkTheme) dynamicDarkColorScheme(LocalContext.current) else dynamicLightColorScheme(LocalContext.current)
        darkTheme -> DarkScheme
        else -> LightScheme
    }}
    MaterialTheme(colorScheme = colors, typography = AppTypography, content = content)
}}
"""

    def string_key(self, text: str) -> str:
        """Имя строкового ресурса для текста (один ресурс на одинаковый текст)."""
        if text not in self.strings:
            base = re.sub(r"[^a-z0-9_]+", "_", _translit(text)).strip("_")[:40] or "text"
            if not base[0].isalpha() or base in _KW or base in _JAVA_KW:  # имя поля R.string — не ключевое слово
                base = "text_" + base
            name, i = base, 2
            while name in self._string_names:
                name, i = f"{base}_{i}", i + 1
            self._string_names.add(name)
            self.strings[text] = name
        return self.strings[text]

    @staticmethod
    def xml_string(text: str) -> str:
        """Текст для values/strings.xml: экранирование правил Android."""
        t = text.replace("\\", "\\\\").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        t = t.replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n")
        if t[:1] in ("@", "?"):
            t = "\\" + t
        if text != text.strip() or "  " in text or "\t" in text:  # пробелы сохраняются только в кавычках
            t = '"' + t.replace("\t", "\\t") + '"'
        return t

    def fonts_kt(self) -> str:
        """Свои шрифты проекта: FontFamily для каждого семейства из файлов в res/font."""
        lines = [f"package {self.pkg}.ui.theme", "", "import androidx.compose.ui.text.font.Font",
                 "import androidx.compose.ui.text.font.FontFamily", "import androidx.compose.ui.text.font.FontStyle",
                 "import androidx.compose.ui.text.font.FontWeight", f"import {self.pkg}.R", ""]
        for fam, var in self.families.items():
            faces = ", ".join(f"Font(R.font.{res}, FontWeight({w}), FontStyle.{'Italic' if it else 'Normal'})"
                              for res, w, it in self.faces[fam])
            lines += [f"/** Шрифт «{fam}» из проекта. */", f"val {var} = FontFamily({faces})", ""]
        return "\n".join(lines)

    def type_kt(self) -> str:
        tused: set[str] = set()
        k = screen_dpi(self.screens[0]) / 160 if self.screens else 1.0
        lines, roles = [], {}
        for t in self.doc.text_styles:
            name = ident(t.name, True, tused | {"AppTypography"}, "Style")
            tused.add(name)
            lines.append(f"val {name} = TextStyle(fontSize = {_num(t.font_size / k)}.sp, "
                         f"fontWeight = FontWeight({t.font_weight})"
                         f"{', color = ' + kcolor(t.text_color) if t.text_color else ''})")
            role = role_of(t.name)
            if role and role not in roles:
                roles[role] = name
        typo = ",\n".join(f"    {r} = {roles[r]}" for r in TYPE_SCALE if r in roles)
        return f"""package {self.pkg}.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
{"import androidx.compose.ui.graphics.Color" if any(t.text_color for t in self.doc.text_styles) else ""}

// Текстовые стили проекта
{chr(10).join(lines) or "// стилей в дизайне нет"}

/** Типографика Material 3: роли из стилей «M3 · …» проекта, остальные — по умолчанию. */
val AppTypography = Typography({chr(10) + typo + "," + chr(10) if typo else ""})
"""

    def readme(self) -> str:
        v = VERSIONS
        lines = [f"# Android-проект «{self.doc.meta.title}»", "",
                 "Каркас создан App Design Studio по дизайну: Kotlin, Jetpack Compose, Material 3.", "",
                 "## Как открыть и собрать", "",
                 "1. Android Studio → File → Open → эта папка (`android_project`). Студия скачает Gradle "
                 f"{v['gradle']} и зависимости.",
                 "2. Run ▶ — запуск на эмуляторе или телефоне; Build → Build APK(s) — файл APK.",
                 f"3. Из командной строки: `gradle assembleDebug` (Gradle {v['gradle']}+, JDK 17+). "
                 "APK: `app/build/outputs/apk/debug/app-debug.apk`.", "",
                 "## Что сгенерировано", "",
                 f"- Пакет `{self.pkg}`, minSdk {v['min_sdk']}, targetSdk {v['target_sdk']}.",
                 "- `ui/theme` — схемы Material 3 (светлая и тёмная) по цвету бренда, токены и типографика; "
                 "`AppState.kt` — переменные прототипа.",
                 "- Стандартные компоненты из библиотеки студии — настоящие компоненты Material 3 (Button, Switch, "
                 "Checkbox, Slider, NavigationBar, TopAppBar, …) с состоянием; значки — `ui/components/DesignIcon.kt`.",
                 "- `navigation/AppNavHost.kt` — переходы между экранами (стек маршрутов по названиям экранов; системная «Назад»; стек и переменные переживают поворот экрана).",
                 "- `ui/screens/*Screen.kt` — экраны: Auto Layout → Column / Row, остальное — Box со смещениями; "
                 "нажатия, переходы, переменные, показ/скрытие и поля ввода — рабочий код.", "",
                 "## Что доработать", "",
                 "- Эффекты (тени Material 3, градиенты, размытие), переходы между экранами, плавное появление и "
                 "анимации непрозрачности и положения из студии — рабочий код.",
                 "- Места с `TODO`: анимации, которые не переводятся автоматически; картинки, не включённые в пакет.",
                 "- Абсолютные смещения → адаптивная раскладка, данные → ViewModel.",
                 "- Подробное задание для ИИ — `AI_TASK.md` в корне пакета.", "",
                 "## Уже сделано", "",
                 "- Тексты экранов — в `res/values/strings.xml`: для перевода добавьте `res/values-en/strings.xml` "
                 "с теми же именами.",
                 "- Заставка запуска (Splash Screen API, `res/values/splash.xml`), жест «назад» с предпросмотром "
                 "(Android 14+), крупные заголовки и подписи нажатий для TalkBack.",
                 f"- Ссылки на экраны: `{self.link_scheme}://маршрут` открывает экран (например, "
                 f"`{self.link_scheme}://{self.routes[self.screens[-1].id] if self.screens else 'screen1'}` — экран «{self.screens[-1].name if self.screens else ''}»); неизвестный маршрут открывает первый экран.", "",
                 "## Экраны", ""]
        lines += [f"- `{self.fns[s.id]}` — «{s.name}» (маршрут `{self.routes[s.id]}`)" for s in self.screens]
        return "\n".join(lines) + "\n"


def drawable_name(name: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", _translit(name.rsplit(".", 1)[0])).strip("_") or "image"
    if not base[0].isalpha():
        base = "img_" + base
    if base in _WIN_RESERVED:  # con, aux, com1… — в Windows такой файл не создать
        base += "_"
    n, i = base, 2
    while n in used:
        n, i = f"{base}_{i}", i + 1
    used.add(n)
    return n


CLASSIC_SWITCH = """package {pkg}.ui.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp

/** Переключатель Material 1 / 2: тонкая полупрозрачная дорожка и круглый бегунок с тенью. */
@Composable
fun ClassicSwitch(checked: Boolean, onCheckedChange: ((Boolean) -> Unit)?, modifier: Modifier = Modifier) {
    val primary = MaterialTheme.colorScheme.primary
    val offset by animateDpAsState(if (checked) 16.dp else 0.dp, label = "thumb")
    val track by animateColorAsState(
        if (checked) primary.copy(alpha = 0.5f) else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f),
        label = "track",
    )
    val thumb by animateColorAsState(if (checked) primary else Color(0xFFECECEC), label = "thumbColor")
    val toggle = if (onCheckedChange != null)
        Modifier.toggleable(value = checked, role = Role.Switch) { onCheckedChange(it) } else Modifier
    Box(modifier = modifier.then(toggle).size(width = 36.dp, height = 20.dp), contentAlignment = Alignment.CenterStart) {
        Box(Modifier.size(width = 36.dp, height = 14.dp).clip(RoundedCornerShape(7.dp)).background(track))
        Box(Modifier.offset(x = offset).size(20.dp).shadow(2.dp, CircleShape).background(thumb, CircleShape))
    }
}
"""


DESIGN_ICON = """package {pkg}.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.material3.LocalContentColor
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * Значок из дизайна (SVG-путь в сетке viewport × viewport). Цвет по умолчанию — цвет содержимого
 * компонента (LocalContentColor), как у Icon из Material 3. Можно заменить на Icon(Icons....).
 */
@Composable
fun DesignIcon(
    path: String,
    contentDescription: String? = null,
    modifier: Modifier = Modifier,
    tint: Color = LocalContentColor.current,
    iconSize: Dp = 24.dp,
    viewport: Float = 24f,
    evenOdd: Boolean = false,
) {
    val shape = remember(path, evenOdd) {
        PathParser().parsePathString(path).toPath().apply { if (evenOdd) fillType = PathFillType.EvenOdd }
    }
    val described = if (contentDescription != null) modifier.semantics { this.contentDescription = contentDescription }
    else modifier
    Canvas(described.size(iconSize)) {
        scale(size.width / viewport, size.height / viewport, pivot = Offset.Zero) {
            drawPath(shape, tint)
        }
    }
}
"""
