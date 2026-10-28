"""Компоненты Material 3 из дизайна → настоящие компоненты Jetpack Compose. Без Qt.

Корневой фрейм заготовки несёт роль (m3.switch, m3.button_filled, …). Для роли из ROLES экран получает
вызов компонента Compose (Switch, Button, NavigationBar, …) с подписями и значками из дизайна, состоянием
(включено, выбранный пункт, значение ползунка) и обработчиками нажатий из логики прототипа. Остальные роли
(карточки, диалог, меню, листы) переводятся общим способом — Column / Row по Auto Layout.
"""

from __future__ import annotations

from dataclasses import replace

from app.core.document import tree

EMPTY = '""'
# роли с собственным переводом; значение — начальное состояние (Kotlin) или None
ROLES: dict[str, str | None] = {
    "m3.button_filled": None, "m3.button_tonal": None, "m3.button_outlined": None, "m3.button_text": None,
    "m3.icon_button": None, "m3.fab": None, "m3.fab_extended": None, "m3.switch": "true", "m3.checkbox": "true",
    "m3.radio_group": "0", "m3.slider": "0.4f", "m3.chip_assist": None, "m3.chip_filter": "true",
    "m3.text_field": '""', "m3.progress_linear": None, "m3.progress_circular": None, "m3.divider": None,
    "m3.snackbar": None, "m3.badge": None, "m3.tabs": "0", "m3.segmented": "0", "m3.nav_bar": "0",
    "m3.top_app_bar": None,
}
# компоненты с собственным размером: ширина из дизайна не задаётся
_INTRINSIC = {"m3.button_filled", "m3.button_tonal", "m3.button_outlined", "m3.button_text", "m3.icon_button",
              "m3.fab", "m3.fab_extended", "m3.checkbox", "m3.chip_assist", "m3.chip_filter",
              "m3.progress_circular", "m3.badge", "m3.segmented"}
_BUTTONS = {"m3.button_filled": "Button", "m3.button_tonal": "FilledTonalButton",
            "m3.button_outlined": "OutlinedButton", "m3.button_text": "TextButton"}
STATE_PREFIX = {"m3.switch": "checked", "m3.checkbox": "checked", "m3.radio_group": "selected",
                "m3.slider": "value", "m3.chip_filter": "selected", "m3.text_field": "input", "m3.tabs": "tab",
                "m3.segmented": "segment", "m3.nav_bar": "navItem"}


def _texts(n):
    return [d for d in tree.descendants(n) if d.type == "text"]


def _vectors(n):
    return [d for d in tree.descendants(n) if d.type == "vector" and d.path]


def _items(n):
    """Пункты составного компонента: дочерние фреймы (без разделителей)."""
    return [c for c in n.children if c.is_frame]


class Material:
    """Перевод ролей для одного экрана; gen — генератор экрана (_Screen)."""

    def __init__(self, gen):
        self.g = gen
        self.state: dict[str, str] = {}  # node_id → имя переменной состояния
        self.decls: list[str] = []
        for n, _, _ in tree.walk(gen.s.nodes):
            if n.is_frame and n.role in ROLES and ROLES[n.role] is not None:
                if n.role == "m3.text_field" and _texts(n) and _texts(n)[0].id in gen.inputs:
                    continue  # поле уже связано с вводом (переменная inputs)
                var = gen.ident(f"{STATE_PREFIX[n.role]} {n.name}")
                init = ROLES[n.role]
                if n.role == "m3.slider":
                    init = f"{self._slider_value(n):.2f}f"
                self.state[n.id] = var
                self.decls.append(f"    var {var} by remember {{ mutableStateOf({init}) }}")

    @staticmethod
    def _slider_value(n) -> float:
        rects = [c for c in n.children if c.type == "rect"]
        dots = [c for c in n.children if c.type == "ellipse"]
        span = n.w - sum(d.w for d in dots)
        return max(0.0, min(1.0, rects[0].w / span)) if rects and span > 0 else 0.5

    # ---------- общие части ----------
    def handles(self, n) -> bool:
        return n.is_frame and n.role in ROLES

    def modifier(self, n, parent, mode, ind) -> str:
        """Положение и ширина без заливки, рамки и отступов — их рисует компонент Compose."""
        bare = replace(n, fill="", stroke="", stroke_width=0, layout="none", children=[], radius=0,
                       sizing_v="hug", sizing_h="hug" if n.role in _INTRINSIC else n.sizing_h)
        m = self.g.modifier(bare, parent, mode, ind, handlers=False)
        m[0] = m[0].lstrip()
        return "\n".join(m)

    def taps(self, node_id: str, ind: str) -> list[str]:
        out = []
        for it in self.g.its:
            if it.node_id == node_id and it.trigger == "tap":
                out += self.g.actions_code(it, ind)
        return out

    def text(self, t) -> str:
        return self.g.texts.get(t.id) or self.g.kstr(t.text)

    def icon(self, v, ind: str, size: int = 24) -> str:
        args = [self.g.kstr(v.path), f"contentDescription = {self.g.kstr(v.name)}"]
        if size != 24:
            args.append(f"iconSize = {size}.dp")
        if v.vb_w != 24 or v.vb_h != 24:
            args.append(f"viewport = {round(max(v.vb_w, v.vb_h), 2)}f")
        if v.fill_rule == "evenodd":
            args.append("evenOdd = true")
        return f"DesignIcon({', '.join(args)})"

    # ---------- перевод ----------
    def node(self, n, parent, mode: str, ind: str) -> list[str]:
        r, M = n.role, self.modifier(n, parent, mode, ind + "    ")
        texts, icons, var = _texts(n), _vectors(n), self.state.get(n.id)
        i2, i3 = ind + "    ", ind + "        "
        label = self.text(texts[0]) if texts else '""'
        if r in _BUTTONS:
            out = [f"{ind}{_BUTTONS[r]}(", f"{i2}onClick = {{"] + self.taps(n.id, i3) + [f"{i2}}},",
                                                                                      f"{i2}modifier = {M},", f"{ind}) {{"]
            if icons:
                out += [f"{i2}{self.icon(icons[0], i2, 18)}", f"{i2}Spacer(Modifier.width(8.dp))"]
            return out + [f"{i2}Text({label})", f"{ind}}}"]
        if r in ("m3.icon_button", "m3.fab"):
            comp = "IconButton" if r == "m3.icon_button" else "FloatingActionButton"
            body = [f"{i2}{self.icon(icons[0], i2)}"] if icons else []
            return ([f"{ind}{comp}(", f"{i2}onClick = {{"] + self.taps(n.id, i3) +
                    [f"{i2}}},", f"{i2}modifier = {M},", f"{ind}) {{"] + body + [f"{ind}}}"])
        if r == "m3.fab_extended":
            ico = [f"{i2}icon = {{ {self.icon(icons[0], i2)} }},"] if icons else []
            return ([f"{ind}ExtendedFloatingActionButton(", f"{i2}onClick = {{"] + self.taps(n.id, i3) +
                    [f"{i2}}},"] + ico + [f"{i2}text = {{ Text({label}) }},", f"{i2}modifier = {M},", f"{ind})"])
        if r in ("m3.switch", "m3.checkbox"):
            ctl = "Switch" if r == "m3.switch" else "Checkbox"
            control = ([f"{i2}{ctl}(checked = {var}, onCheckedChange = {{", f"{i3}{var} = it"] +
                       self.taps(n.id, i3) + [f"{i2}}})"])
            txt = [f"{i2}Text({label}{', Modifier.weight(1f)' if r == 'm3.switch' else ''})"]
            body = txt + control if r == "m3.switch" else control + txt
            return [f"{ind}Row(", f"{i2}modifier = {M},", f"{i2}verticalAlignment = Alignment.CenterVertically,",
                    f"{ind}) {{"] + body + [f"{ind}}}"]
        if r == "m3.radio_group":
            out = [f"{ind}Column(modifier = {M}) {{"]
            for i, item in enumerate(_items(n)):
                t = _texts(item)
                act = [f"{i3}    {var} = {i}"] + self.taps(item.id, i3 + "    ")
                out += [f"{i2}Row(", f"{i3}modifier = Modifier.fillMaxWidth().selectable(selected = {var} == {i}, "
                        f"onClick = {{"] + act + [f"{i3}}}),", f"{i3}verticalAlignment = Alignment.CenterVertically,",
                                                  f"{i2}) {{",
                                                  f"{i3}RadioButton(selected = {var} == {i}, onClick = null, "
                                                  f"modifier = Modifier.padding(12.dp))",
                                                  f"{i3}Text({self.text(t[0]) if t else EMPTY})", f"{i2}}}"]
            return out + [f"{ind}}}"]
        if r == "m3.slider":
            return [f"{ind}Slider(value = {var}, onValueChange = {{ {var} = it }}, modifier = {M})"]
        if r == "m3.chip_assist":
            ico = [f"{i2}leadingIcon = {{ {self.icon(icons[0], i2, 18)} }},"] if icons else []
            return ([f"{ind}AssistChip(", f"{i2}onClick = {{"] + self.taps(n.id, i3) + [f"{i2}}},",
                                                                                    f"{i2}label = {{ Text({label}) }},"]
                    + ico + [f"{i2}modifier = {M},", f"{ind})"])
        if r == "m3.chip_filter":
            ico = (f"{i2}leadingIcon = if ({var}) {{ {{ {self.icon(icons[0], i2, 18)} }} }} else null,"
                   if icons else None)
            return ([f"{ind}FilterChip(", f"{i2}selected = {var},", f"{i2}onClick = {{", f"{i3}{var} = !{var}"] +
                    self.taps(n.id, i3) + [f"{i2}}},", f"{i2}label = {{ Text({label}) }},"] +
                    ([ico] if ico else []) + [f"{i2}modifier = {M},", f"{ind})"])
        if r == "m3.text_field":
            ph = texts[0] if texts else None
            hint = texts[1] if len(texts) > 1 else None
            v = self.g.inputs.get(ph.id) if ph is not None and ph.id in self.g.inputs else var
            change = self.g.input_change(ph, v, i3) if ph is not None and ph.id in self.g.inputs else []
            out = [f"{ind}OutlinedTextField(", f"{i2}value = {v},", f"{i2}onValueChange = {{", f"{i3}{v} = it"]
            out += change + [f"{i2}}},"]
            if ph is not None:
                out.append(f"{i2}placeholder = {{ Text({self.g.kstr(ph.text)}) }},")
            if hint is not None:
                out.append(f"{i2}supportingText = {{ Text({self.text(hint)}) }},")
            return out + [f"{i2}singleLine = true,", f"{i2}modifier = {M},", f"{ind})"]
        if r == "m3.progress_linear":
            part = [c for c in n.children if c.type == "rect"]
            p = max(0.0, min(1.0, part[0].w / n.w)) if part and n.w else 0.5
            return [f"{ind}LinearProgressIndicator(progress = {{ {p:.2f}f }}, modifier = {M})"]
        if r == "m3.progress_circular":
            return [f"{ind}CircularProgressIndicator(modifier = {M})"]
        if r == "m3.divider":
            return [f"{ind}HorizontalDivider(modifier = {M})"]
        if r == "m3.snackbar":
            msg = texts[0] if texts else None
            act = texts[1] if len(texts) > 1 else None
            out = [f"{ind}Snackbar(", f"{i2}modifier = {M},"]
            if act is not None:
                out += [f"{i2}action = {{", f"{i3}TextButton(onClick = {{"] + self.taps(act.id, i3 + "    ") + \
                       [f"{i3}}}) {{ Text({self.text(act)}) }}", f"{i2}}},"]
            return out + [f"{ind}) {{", f"{i2}Text({self.text(msg) if msg else EMPTY})", f"{ind}}}"]
        if r == "m3.badge":
            num = texts[0] if texts else None
            badge = f"Badge {{ Text({self.text(num)}) }}" if num else "Badge()"
            body = [f"{i2}{self.icon(icons[0], i2)}"] if icons else []
            return [f"{ind}BadgedBox(badge = {{ {badge} }}, modifier = {M}) {{"] + body + [f"{ind}}}"]
        if r == "m3.tabs":
            out = [f"{ind}PrimaryTabRow(selectedTabIndex = {var}, modifier = {M}) {{"]
            for i, item in enumerate(_items(n)):
                t = _texts(item)
                out += [f"{i2}Tab(", f"{i3}selected = {var} == {i},", f"{i3}onClick = {{", f"{i3}    {var} = {i}"] + \
                       self.taps(item.id, i3 + "    ") + [
                    f"{i3}}},", f"{i3}text = {{ Text({self.text(t[0]) if t else EMPTY}) }},",
                    f"{i3}unselectedContentColor = MaterialTheme.colorScheme.onSurfaceVariant,", f"{i2})"]
            return out + [f"{ind}}}"]
        if r == "m3.segmented":
            items = _items(n)
            out = [f"{ind}SingleChoiceSegmentedButtonRow(modifier = {M}) {{"]
            for i, item in enumerate(items):
                t = _texts(item)
                out += [f"{i2}SegmentedButton(", f"{i3}selected = {var} == {i},", f"{i3}onClick = {{",
                        f"{i3}    {var} = {i}"] + self.taps(item.id, i3 + "    ") + [
                    f"{i3}}},", f"{i3}shape = SegmentedButtonDefaults.itemShape(index = {i}, count = {len(items)}),",
                    f"{i2}) {{ Text({self.text(t[0]) if t else EMPTY}) }}"]
            return out + [f"{ind}}}"]
        if r == "m3.nav_bar":
            out = [f"{ind}NavigationBar(modifier = {M}, windowInsets = WindowInsets(0, 0, 0, 0)) {{"]
            for i, item in enumerate(_items(n)):
                t, ic = _texts(item), _vectors(item)
                out += [f"{i2}NavigationBarItem(", f"{i3}selected = {var} == {i},", f"{i3}onClick = {{",
                        f"{i3}    {var} = {i}"] + self.taps(item.id, i3 + "    ") + [f"{i3}}},"]
                out.append(f"{i3}icon = {{ {self.icon(ic[0], i3)} }}," if ic else f"{i3}icon = {{}},")
                if t:
                    out.append(f"{i3}label = {{ Text({self.text(t[0])}) }},")
                out.append(f"{i2})")
            return out + [f"{ind}}}"]
        if r == "m3.top_app_bar":
            title = next((t for t in texts), None)
            vecs = [c for c in n.children if c.type == "vector" and c.path]
            out = [f"{ind}TopAppBar(", f"{i2}title = {{ Text({self.text(title) if title else EMPTY}) }},"]
            if vecs:
                v = vecs[0]
                out += [f"{i2}navigationIcon = {{", f"{i3}IconButton(onClick = {{"] + self.taps(v.id, i3 + "    ") + \
                       [f"{i3}}}) {{ {self.icon(v, i3)} }}", f"{i2}}},"]
            if len(vecs) > 1:
                out.append(f"{i2}actions = {{")
                for v in vecs[1:]:
                    out += [f"{i3}IconButton(onClick = {{"] + self.taps(v.id, i3 + "    ") + \
                           [f"{i3}}}) {{ {self.icon(v, i3)} }}"]
                out.append(f"{i2}}},")
            return out + [f"{i2}windowInsets = WindowInsets(0, 0, 0, 0),", f"{i2}modifier = {M},", f"{ind})"]
        return []
