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
from app.engines.preview.devices import screen_dpi

ROOT = "android_project"
VERSIONS = {"agp": "8.13.2", "kotlin": "2.2.10", "compose_bom": "2025.09.01", "activity_compose": "1.11.0",
            "core_ktx": "1.17.0", "gradle": "8.13",
            "compile_sdk": 36, "min_sdk": 26, "target_sdk": 36}
_KW = {"as", "break", "class", "continue", "do", "else", "false", "for", "fun", "if", "in", "interface", "is",
       "null", "object", "package", "return", "super", "this", "throw", "true", "try", "typealias", "typeof",
       "val", "var", "when", "while"}


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
    return f"com.design.{seg[:30]}"


def kstr(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("\n", "\\n") + '"'


def kcolor(c: str) -> str:
    c = (c or "#000000").lstrip("#").upper()
    a = c[6:8] if len(c) == 8 else "FF"
    return f"Color(0x{a}{c[:6]})"


def _num(v: float) -> str:
    v = round(float(v), 1)
    return str(int(v)) if v == int(v) else str(v)


class _Screen:
    """Генерация одного экрана."""

    def __init__(self, gen: "AndroidProject", s: Screen, fn: str):
        self.g, self.s, self.fn = gen, s, fn
        self.k = screen_dpi(s) / 160
        self.its = [i for i in gen.doc.interactions if i.screen_id == s.id]
        self.used: set[str] = set()
        self.vis: dict[str, str] = {}     # node_id → имя переменной видимости
        self.texts: dict[str, str] = {}   # node_id → имя переменной текста
        self.inputs: dict[str, str] = {}  # node_id → имя переменной поля ввода
        self.todo: list[str] = []
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
        for n, _, _ in tree.walk(s.nodes):
            if n.type == "text" and n.editable:
                self.inputs[n.id] = ident(f"input {n.name}", False, self.used, "input")

    def dp(self, v: float) -> str:
        return f"{_num(v / self.k)}.dp"

    # ---------- действия ----------
    def actions_code(self, it, ind: str) -> list[str]:
        out = []
        st = self.g.state_names
        for a in it.actions:
            t = a["type"]
            if t == "navigate":
                route = self.g.routes.get(a["screen_id"])
                out.append(f"onNavigate({kstr(route)})" if route else
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
            elif t == "set_text" and a["node_id"] in self.texts:
                out.append(f"{self.texts[a['node_id']]} = {self.template(str(a['text']))}")
            else:
                out.append(f"// TODO: действие «{t}» (состояния компонентов и анимации — вручную)")
        if it.condition:
            v = self.g.doc.variable(it.condition["var_id"])
            if v is not None:
                cond = f"state.{st[v.id]} {it.condition['op']} {self.g.literal(v.type, it.condition['value'])}"
                return [f"{ind}if ({cond}) {{"] + [f"{ind}    {x}" for x in out] + [f"{ind}}}"]
        return [ind + x for x in out]

    def template(self, text: str) -> str:
        by_name = {v.name: v for v in self.g.doc.variables}

        def sub(m):
            v = by_name.get(m.group(1))
            return "${fmt(state." + self.g.state_names[v.id] + ")}" if v else m.group(0)
        body = text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("\n", "\\n")
        return '"' + re.sub(r"\{([0-9A-Za-zА-Яа-яЁё_ -]{1,64})\}", sub, body) + '"'

    def handlers(self, n, ind: str) -> list[str]:
        """Modifier-обработчики событий узла (нажатие, долгое, двойное)."""
        mine = {}
        for it in self.its:
            if it.node_id == n.id and it.trigger in ("tap", "long_press", "double_tap"):
                mine.setdefault(it.trigger, []).append(it)
        if not mine:
            return []
        def body(trig):
            lines = []
            for it in mine.get(trig, []):
                lines += self.actions_code(it, ind + "        ")
            return lines
        if set(mine) == {"tap"}:
            return [f"{ind}.clickable {{"] + body("tap") + [f"{ind}}}"]
        out = [f"{ind}.combinedClickable("]
        for trig, arg in (("tap", "onClick"), ("long_press", "onLongClick"), ("double_tap", "onDoubleClick")):
            if trig in mine or trig == "tap":
                out += [f"{ind}    {arg} = {{"] + body(trig) + [f"{ind}    }},"]
        return out + [f"{ind})"]

    # ---------- элементы ----------
    def modifier(self, n, parent, mode: str, ind: str) -> list[str]:
        """mode: abs (смещение в Box), col / row (в Auto Layout)."""
        m = [f"{ind}Modifier"]
        if mode == "abs":
            ox, oy = n.x - (parent.x if parent else 0), n.y - (parent.y if parent else 0)
            if ox or oy:
                m.append(f"{ind}    .offset(x = {self.dp(ox)}, y = {self.dp(oy)})")
        main_fill = (mode == "col" and n.sizing_v == "fill") or (mode == "row" and n.sizing_h == "fill")
        if main_fill:
            m.append(f"{ind}    .weight(1f)")
        if n.sizing_h == "fill" and mode == "col":
            m.append(f"{ind}    .fillMaxWidth()")
        elif n.sizing_h != "hug" and not (mode == "row" and n.sizing_h == "fill"):
            m.append(f"{ind}    .width({self.dp(n.w)})")
        if n.sizing_v == "fill" and mode == "row":
            m.append(f"{ind}    .fillMaxHeight()")
        elif n.sizing_v != "hug" and not (mode == "col" and n.sizing_v == "fill") and n.type != "text":
            m.append(f"{ind}    .height({self.dp(n.h)})")
        elif n.type == "text" and n.sizing_v == "fixed":
            m.append(f"{ind}    .heightIn(min = {self.dp(n.h)})")
        if n.opacity < 1:
            m.append(f"{ind}    .alpha({_num(n.opacity)}f)")
        shape = "CircleShape" if n.type == "ellipse" else (f"RoundedCornerShape({self.dp(n.radius)})" if n.radius
                                                           else "RectangleShape")
        if n.fill and n.type not in ("text", "image", "vector"):
            m.append(f"{ind}    .clip({shape})")
            m.append(f"{ind}    .background({kcolor(n.fill)})")
        if n.stroke and n.stroke_width and n.type not in ("text", "vector"):
            m.append(f"{ind}    .border({self.dp(n.stroke_width)}, {kcolor(n.stroke)}, {shape})")
        m += self.handlers(n, ind + "    ")
        if n.is_frame and n.layout != "none" and (n.pad_t or n.pad_r or n.pad_b or n.pad_l):
            m.append(f"{ind}    .padding(start = {self.dp(n.pad_l)}, top = {self.dp(n.pad_t)}, "
                     f"end = {self.dp(n.pad_r)}, bottom = {self.dp(n.pad_b)})")
        return m

    def node(self, n, parent, mode: str, ind: str) -> list[str]:
        out: list[str] = []
        if n.is_group:  # у группы нет геометрии — дети в координатах родителя группы
            for c in n.children:
                out += self.node(c, parent, mode, ind)
            return out
        hidden = not n.visible
        if n.id in self.vis:
            out.append(f"{ind}if ({self.vis[n.id]}) {{")
            ind2 = ind + "    "
        elif hidden:
            return [f"{ind}// скрыт в дизайне: «{n.name or n.type}»"]
        else:
            ind2 = ind
        out.append(f"{ind2}// {n.name or n.type}" + (f" — экземпляр компонента" if n.is_instance else ""))
        mod = self.modifier(n, parent, mode, ind2 + "    ")
        mod[0] = mod[0].lstrip()
        modtxt = "\n".join([mod[0]] + mod[1:])
        if n.type == "text":
            out += self.text(n, modtxt, ind2)
        elif n.type == "image":
            res = self.g.drawables.get(n.asset_id)
            if res:
                out += [f"{ind2}Image(", f"{ind2}    painter = painterResource(R.drawable.{res}),",
                        f"{ind2}    contentDescription = {kstr(n.name)},", f"{ind2}    contentScale = ContentScale.Crop,",
                        f"{ind2}    modifier = {modtxt},", f"{ind2})"]
            else:
                out += [f"{ind2}// TODO: изображение «{n.name}» (SVG или не включено в пакет)",
                        f"{ind2}Box(modifier = {modtxt}.background(Color(0x22FFFFFF)))"]
        elif n.type == "vector" and n.path:
            out += [f"{ind2}Canvas(modifier = {modtxt}) {{",
                    f"{ind2}    scale(size.width / {_num(n.vb_w)}f, size.height / {_num(n.vb_h)}f, pivot = Offset.Zero) {{",
                    f"{ind2}        val p = PathParser().parsePathString({kstr(n.path)}).toPath()",
                    f"{ind2}        drawPath(p, {kcolor(n.fill or '#00000000')})"]
            if n.stroke and n.stroke_width:
                out.append(f"{ind2}        drawPath(p, {kcolor(n.stroke)}, style = Stroke(width = {_num(n.stroke_width)}f))")
            out += [f"{ind2}    }}", f"{ind2}}}"]
        elif n.is_frame and n.layout in ("vertical", "horizontal", "grid"):
            out += self.stack(n, modtxt, ind2)
        else:
            if n.is_container and n.children:
                out.append(f"{ind2}Box(modifier = {modtxt}) {{")
                for c in n.children:
                    out += self.node(c, n, "abs", ind2 + "    ")
                out.append(f"{ind2}}}")
            else:
                out.append(f"{ind2}Box(modifier = {modtxt})")
        if n.id in self.vis:
            out.append(f"{ind}}}")
        return out

    def text(self, n, modtxt: str, ind: str) -> list[str]:
        align = {"left": "TextAlign.Start", "center": "TextAlign.Center", "right": "TextAlign.End"}[n.align]
        style = (f"color = {kcolor(n.text_color)}, fontSize = {_num(n.font_size / self.k)}.sp, "
                 f"fontWeight = FontWeight({n.font_weight}), textAlign = {align}")
        if n.id in self.inputs:
            var = self.inputs[n.id]
            bind = ""
            v = self.g.doc.variable(n.input_var) if n.input_var else None
            if v is not None and v.type == "text":
                bind = f"; state.{self.g.state_names[v.id]} = it"
            changed = []
            for it in self.its:
                if it.node_id == n.id and it.trigger == "text_changed":
                    changed += self.actions_code(it, ind + "        ")
            return ([f"{ind}BasicTextField(", f"{ind}    value = {var},",
                     f"{ind}    onValueChange = {{ {var} = it{bind}"] + changed + [f"{ind}    }},",
                     f"{ind}    textStyle = TextStyle({style}),",
                     f"{ind}    cursorBrush = SolidColor({kcolor(n.text_color)}),",
                     f"{ind}    modifier = {modtxt},",
                     f"{ind}    decorationBox = {{ inner ->",
                     f"{ind}        if ({var}.isEmpty()) Text({kstr(n.text)}, {style.replace(kcolor(n.text_color), kcolor(n.text_color[:7] + '88'))})",
                     f"{ind}        inner()", f"{ind}    }},", f"{ind})"])
        value = self.texts.get(n.id) or kstr(n.text)
        return [f"{ind}Text(", f"{ind}    text = {value},", f"{ind}    {style},", f"{ind}    modifier = {modtxt},",
                f"{ind})"]

    def stack(self, n, modtxt: str, ind: str) -> list[str]:
        main = {"start": "Start", "center": "Center", "end": "End", "space_between": "SpaceBetween"}[n.main_align]
        cross = {"start": "Start", "center": "CenterHorizontally", "end": "End", "stretch": "Start"}[n.cross_align]
        if n.layout == "vertical":
            arr = (f"Arrangement.SpaceBetween" if main == "SpaceBetween" else
                   f"Arrangement.spacedBy({self.dp(n.gap)}, Alignment.{ {'Start': 'Top', 'Center': 'CenterVertically', 'End': 'Bottom'}[main] })")
            out = [f"{ind}Column(", f"{ind}    modifier = {modtxt},", f"{ind}    verticalArrangement = {arr},",
                   f"{ind}    horizontalAlignment = Alignment.{cross},", f"{ind}) {{"]
            for c in n.children:
                out += self.node(c, n, "col", ind + "    ")
            return out + [f"{ind}}}"]
        if n.layout == "horizontal":
            vcross = {"start": "Top", "center": "CenterVertically", "end": "Bottom", "stretch": "Top"}[n.cross_align]
            arr = (f"Arrangement.SpaceBetween" if main == "SpaceBetween" else
                   f"Arrangement.spacedBy({self.dp(n.gap)}, Alignment.{ {'Start': 'Start', 'Center': 'CenterHorizontally', 'End': 'End'}[main] })")
            out = [f"{ind}Row(", f"{ind}    modifier = {modtxt},", f"{ind}    horizontalArrangement = {arr},",
                   f"{ind}    verticalAlignment = Alignment.{vcross},", f"{ind}) {{"]
            for c in n.children:
                out += self.node(c, n, "row", ind + "    ")
            return out + [f"{ind}}}"]
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
             "@Composable",
             f"fun {self.fn}(state: AppState, onNavigate: (String) -> Unit, onBack: () -> Unit) {{"]
        m = tree.node_map(s)
        for nid, var in self.vis.items():
            L.append(f"    var {var} by remember {{ mutableStateOf({'true' if m[nid].visible and nid not in self.overlays else 'false'}) }}")
        for nid, var in self.texts.items():
            L.append(f"    var {var} by remember {{ mutableStateOf({kstr(m[nid].text)}) }}")
        for nid, var in self.inputs.items():
            L.append(f"    var {var} by remember {{ mutableStateOf(\"\") }}")
        opens = [it for it in self.its if it.trigger == "screen_open"]
        if opens:
            L.append("    LaunchedEffect(Unit) {")
            for it in opens:
                L += self.actions_code(it, "        ")
            L.append("    }")
        L.append(f"    Box(modifier = Modifier.fillMaxSize().background({bg})) {{")
        for n in s.nodes:
            L += self.node(n, None, "abs", "        ")
        L += ["    }", "}", "",
              f"@Preview(widthDp = {round(s.width / self.k)}, heightDp = {round(s.height / self.k)}, showBackground = true)",
              "@Composable",
              f"private fun {self.fn}Preview() {{",
              f"    AppTheme {{ {self.fn}(AppState(), onNavigate = {{}}, onBack = {{}}) }}", "}", ""]
        swipes = [it for it in self.its if it.trigger.startswith("swipe") or it.trigger in ("hover_enter", "hover_leave")]
        if swipes:
            L.insert(L.index("@Composable"), f"// TODO: жесты {sorted({i.trigger for i in swipes})} — добавьте "
                                              "pointerInput / detectDragGestures по описанию в AI_TASK.md")
        return "\n".join(L)


class AndroidProject:
    def __init__(self, doc: ProjectDocument, screens: list[Screen], drawables: dict[str, tuple[str, bytes, str]]):
        """drawables — {asset_id: (имя ресурса, данные, расширение)} для включённых растровых изображений."""
        self.doc = doc
        self.screens = [s for s in screens if s.platform == PLATFORM_ANDROID]
        self.pkg = package_name(doc.meta.title)
        self.artboard = ARTBOARD_COLORS.get(doc.meta.appearance.theme, "#000000")
        self.drawables = {aid: name for aid, (name, _, _) in drawables.items()}
        self._drawable_files = drawables
        used: set[str] = set()
        self.fns = {s.id: ident(s.name, True, used, "Screen") + "Screen" for s in self.screens}
        self.routes = {s.id: f"screen{i + 1}" for i, s in enumerate(self.screens)}
        vused: set[str] = set()
        self.state_names = {v.id: ident(v.name, False, vused, "value") for v in doc.variables}

    def imports(self) -> list[str]:
        return [f"import {x}" for x in (
            "androidx.compose.foundation.*", "androidx.compose.foundation.layout.*",
            "androidx.compose.foundation.shape.*", "androidx.compose.foundation.text.BasicTextField",
            "androidx.compose.material3.*", "androidx.compose.runtime.*", "androidx.compose.ui.Alignment",
            "androidx.compose.ui.Modifier", "androidx.compose.ui.draw.alpha", "androidx.compose.ui.draw.clip",
            "androidx.compose.ui.geometry.Offset", "androidx.compose.ui.graphics.Color",
            "androidx.compose.ui.graphics.RectangleShape", "androidx.compose.ui.graphics.SolidColor",
            "androidx.compose.ui.graphics.drawscope.Stroke", "androidx.compose.ui.graphics.drawscope.scale",
            "androidx.compose.ui.graphics.vector.PathParser", "androidx.compose.ui.layout.ContentScale",
            "androidx.compose.ui.res.painterResource", "androidx.compose.ui.text.TextStyle",
            "androidx.compose.ui.text.font.FontWeight", "androidx.compose.ui.text.style.TextAlign",
            "androidx.compose.ui.tooling.preview.Preview", "androidx.compose.ui.unit.dp",
            "androidx.compose.ui.unit.sp", f"{self.pkg}.AppState", f"{self.pkg}.R", f"{self.pkg}.fmt",
            f"{self.pkg}.ui.theme.AppTheme")]

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
        out[".gitignore"] = "*.iml\n.gradle/\n/local.properties\n/.idea/\n.DS_Store\n/build/\n/app/build/\n/captures/\n.externalNativeBuild/\n.cxx/\n"
        out["app/build.gradle.kts"] = f'''import org.jetbrains.kotlin.gradle.dsl.JvmTarget

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
        versionCode = 1
        versionName = "1.0"
    }}

    buildTypes {{
        release {{
            isMinifyEnabled = false
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
    debugImplementation(libs.androidx.ui.tooling)
}}
'''
        out["app/src/main/AndroidManifest.xml"] = f'''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application
        android:allowBackup="true"
        android:label="@string/app_name"
        android:supportsRtl="true"
        android:theme="@android:style/Theme.Material.NoActionBar">
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
'''
        esc = app_name.replace("&", "&amp;").replace("<", "&lt;").replace("'", "\\'").replace('"', '\\"')
        out["app/src/main/res/values/strings.xml"] = f'<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <string name="app_name">{esc}</string>\n</resources>\n'
        for aid, (name, data, ext) in sorted(self._drawable_files.items()):
            out[f"app/src/main/res/drawable/{name}.{ext}"] = data
        src = f"app/src/main/java/{path}"
        start = self.routes[self.screens[0].id] if self.screens else "screen1"
        out[f"{src}/MainActivity.kt"] = f'''package {pkg}

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import {pkg}.navigation.AppNavHost
import {pkg}.ui.theme.AppTheme

class MainActivity : ComponentActivity() {{
    override fun onCreate(savedInstanceState: Bundle?) {{
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {{
            AppTheme {{
                AppNavHost()
            }}
        }}
    }}
}}
'''
        fields = []
        for var in self.doc.variables:
            t = {"bool": "Boolean", "number": "Double", "text": "String"}[var.type]
            fields.append(f"    /** «{var.name}» */\n    var {self.state_names[var.id]} by mutableStateOf<{t}>({self.literal(var.type, var.default)})")
        out[f"{src}/AppState.kt"] = f'''package {pkg}

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** Переменные прототипа (общие для всех экранов). */
class AppState {{
{chr(10).join(fields) if fields else "    // переменных в дизайне нет"}
}}

/** Число без «.0» для подстановки в текст. */
fun fmt(value: Any): String = if (value is Double && value % 1.0 == 0.0) value.toLong().toString() else value.toString()
'''
        routes = "\n".join(f'            "{self.routes[s.id]}" -> {self.fns[s.id]}(state, go, back)'
                           for s in self.screens)
        imports = "\n".join(f"import {pkg}.ui.screens.{self.fns[s.id]}" for s in self.screens)
        out[f"{src}/navigation/AppNavHost.kt"] = f'''package {pkg}.navigation

import androidx.activity.compose.BackHandler
import androidx.compose.animation.Crossfade
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import {pkg}.AppState
{imports}

/**
 * Навигация по экранам дизайна: стек маршрутов; системная «Назад» возвращает на предыдущий экран.
 * При росте приложения замените на Navigation Compose — маршруты уже названы.
 */
@Composable
fun AppNavHost() {{
    val state = remember {{ AppState() }}
    val stack = remember {{ mutableStateListOf("{start}") }}
    val go: (String) -> Unit = {{ stack.add(it) }}
    val back: () -> Unit = {{ if (stack.size > 1) stack.removeAt(stack.lastIndex) }}
    BackHandler(enabled = stack.size > 1) {{ back() }}
    Crossfade(targetState = stack.last(), label = "screen") {{ route ->
        when (route) {{
{routes}
        }}
    }}
}}
'''
        ap = self.doc.meta.appearance
        dark = ap.theme != "light"
        cused = {"Accent", "Background", "Scheme", "AppTheme"}
        colors = "\n".join(f"val {ident(c.name, True, cused, 'Token')} = {kcolor(c.value)}" for c in self.doc.colors)
        out[f"{src}/ui/theme/Theme.kt"] = f'''package {pkg}.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.{"darkColorScheme" if dark else "lightColorScheme"}
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Цвета проекта (токены)
val Accent = {kcolor(ap.accent)}
val Background = {kcolor(self.artboard)}
{colors}

private val Scheme = {"darkColorScheme" if dark else "lightColorScheme"}(
    primary = Accent,
    background = Background,
    surface = Background,
)

@Composable
fun AppTheme(content: @Composable () -> Unit) {{
    MaterialTheme(colorScheme = Scheme, content = content)
}}
'''
        tused: set[str] = set()
        k = screen_dpi(self.screens[0]) / 160 if self.screens else 1.0
        styles = "\n".join(
            f"val {ident(t.name, True, tused, 'Style')} = TextStyle(fontSize = {_num(t.font_size / k)}.sp, "
            f"fontWeight = FontWeight({t.font_weight}){', color = ' + kcolor(t.text_color) if t.text_color else ''})"
            for t in self.doc.text_styles)
        out[f"{src}/ui/theme/Type.kt"] = f'''package {pkg}.ui.theme

import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
{"import androidx.compose.ui.graphics.Color" if any(t.text_color for t in self.doc.text_styles) else ""}

// Текстовые стили проекта
{styles or "// стилей в дизайне нет"}
'''
        for s in self.screens:
            out[f"{src}/ui/screens/{self.fns[s.id]}.kt"] = _Screen(self, s, self.fns[s.id]).source()
        out["README_ANDROID.md"] = self.readme()
        return {f"{ROOT}/{p}": (b if isinstance(b, bytes) else b.encode("utf-8")) for p, b in sorted(out.items())}

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
                 "- `ui/theme` — цвета и текстовые стили проекта; `AppState.kt` — переменные прототипа.",
                 "- `navigation/AppNavHost.kt` — переходы между экранами (стек маршрутов `screen1`, `screen2`, …; системная «Назад»).",
                 "- `ui/screens/*Screen.kt` — экраны: Auto Layout → Column / Row, остальное — Box со смещениями; "
                 "нажатия, переходы, переменные, показ/скрытие и поля ввода — рабочий код.", "",
                 "## Что доработать", "",
                 "- Места с `TODO`: состояния компонентов, анимации, свайпы, SVG-изображения.",
                 "- Абсолютные смещения → адаптивная раскладка, тексты → `strings.xml`, данные → ViewModel.",
                 "- Подробное задание для ИИ — `AI_TASK.md` в корне пакета.", "",
                 "## Экраны", ""]
        lines += [f"- `{self.fns[s.id]}` — «{s.name}» (маршрут `{self.routes[s.id]}`)" for s in self.screens]
        return "\n".join(lines) + "\n"


def drawable_name(name: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", _translit(name.rsplit(".", 1)[0])).strip("_") or "image"
    if not base[0].isalpha():
        base = "img_" + base
    n, i = base, 2
    while n in used:
        n, i = f"{base}_{i}", i + 1
    used.add(n)
    return n
