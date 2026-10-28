"""Анимации и эффекты дизайна → Jetpack Compose. Без Qt.

- Анимации из студии «Анимации» (дорожки непрозрачности и положения) → Animatable с keyframes и теми же
  плавностями; действие «Запустить анимацию» запускает их, «Открытие экрана» — при показе экрана.
- Тень уровня Material 3 → Modifier.shadow, градиент → Brush, размытие → Modifier.blur.
- Переходы между экранами — в AppNavHost (AnimatedContent): затухание и сдвиги с длительностью и плавностью.
Остальные дорожки (размер, цвет, скругление, шрифт) помечаются TODO.
"""

from __future__ import annotations

import math

from app.core.document import tree
from app.core.document.model import ELEVATION_DP

SUPPORTED = ("opacity", "x", "y")
_BEZIER = {"ease_in": (0.42, 0.0, 1.0, 1.0), "ease_out": (0.0, 0.0, 0.58, 1.0), "ease_in_out": (0.42, 0.0, 0.58, 1.0)}


def easing(name: str, bezier=None) -> str:
    """Плавность студии → Easing в Compose (те же кривые cubic-bezier)."""
    if name == "linear":
        return "LinearEasing"
    if name == "step":
        return "StepEasing"
    b = bezier if name == "cubic" and bezier else _BEZIER.get(name, _BEZIER["ease_in_out"])
    return "CubicBezierEasing(" + ", ".join(f"{float(v):g}f" for v in b) + ")"


def _f(v: float) -> str:
    v = round(float(v), 3)
    return f"{v:g}f" if "e" not in f"{v:g}" else f"{v:.3f}f"


class Motion:
    """Анимации одного экрана; gen — генератор экрана (_Screen)."""

    def __init__(self, gen):
        self.g = gen
        m = tree.node_map(gen.s)
        self.vars: dict[tuple[str, str], str] = {}   # (узел, свойство) → Animatable
        self.plays: dict[str, str] = {}               # анимация → имя функции запуска
        self.todo: list[str] = []
        self.decls: list[str] = []
        # анимации при открытии экрана начинаются с первого кадра — без мелькания конечного вида
        opening = {act.get("animation_id") for it in gen.its if it.trigger == "screen_open" and not it.condition
                   for act in it.actions if act["type"] == "play_animation"}
        for a in gen.g.doc.animations:
            if a.screen_id != gen.s.id:
                continue
            launches = []
            for tr in a.tracks:
                n = m.get(tr.node_id)
                if n is None or len(tr.keyframes) < 1:
                    continue
                if tr.prop not in SUPPORTED:
                    self.todo.append(f"«{a.name}»: дорожка «{tr.prop}» элемента «{n.name}»")
                    continue
                key = (n.id, tr.prop)
                if key not in self.vars:
                    var = gen.ident(f"anim {n.name} {tr.prop}")
                    self.vars[key] = var
                    init = n.opacity if tr.prop == "opacity" else 0.0
                    if a.id in opening:
                        init = self._value(n, tr.prop, tr.keyframes[0].value)
                    self.decls.append(f"    val {var} = remember {{ Animatable({_f(init)}) }}")
                launches.append(self._launch(self.vars[key], n, tr, a))
            if launches:
                fn = gen.ident(f"play {a.name}")
                self.plays[a.id] = fn
                self.decls.append(f"    /** Анимация «{a.name}» ({a.duration} мс{', по кругу' if a.loop else ''}). */")
                self.decls += [f"    val {fn}: suspend () -> Unit = {{", "        coroutineScope {"]
                for body in launches:
                    self.decls += [f"            launch {{ {body} }}"]
                self.decls += ["        }", "    }"]
        if self.plays:
            self.decls.insert(0, "    val scope = rememberCoroutineScope()")

    def _value(self, n, prop: str, v) -> float:
        if prop == "opacity":
            return float(v)
        return (float(v) - (n.x if prop == "x" else n.y)) / self.g.k   # смещение от места в дизайне, dp

    def _launch(self, var: str, n, tr, a) -> str:
        kfs = tr.keyframes
        dur = max(1, a.duration)
        entries = [f"{_f(self._value(n, tr.prop, k.value))} at {k.t} using {easing(k.easing, k.bezier)}"
                   for k in kfs]
        if kfs[-1].t < dur:  # держать последнее значение до конца анимации
            entries.append(f"{_f(self._value(n, tr.prop, kfs[-1].value))} at {dur}")
        spec = f"keyframes {{ durationMillis = {dur}; {'; '.join(entries)} }}"
        if a.loop:
            spec = f"infiniteRepeatable({spec}, RepeatMode.Restart)"
        first = _f(self._value(n, tr.prop, kfs[0].value))
        last = _f(self._value(n, tr.prop, kfs[-1].value))
        return f"{var}.snapTo({first}); {var}.animateTo({last}, {spec})"

    # ---------- в генераторе экрана ----------
    def action(self, anim_id: str) -> str | None:
        fn = self.plays.get(anim_id)
        return f"scope.launch {{ {fn}() }}" if fn else None

    def animated(self, n) -> bool:
        return any((n.id, p) in self.vars for p in SUPPORTED)

    def layer(self, n, ind: str) -> list[str]:
        """graphicsLayer с анимируемыми значениями узла (вместо статической непрозрачности)."""
        parts = []
        if (n.id, "opacity") in self.vars:
            parts.append(f"alpha = {self.vars[(n.id, 'opacity')]}.value")
        elif n.opacity < 1:
            parts.append(f"alpha = {_f(n.opacity)}")
        for prop, attr in (("x", "translationX"), ("y", "translationY")):
            if (n.id, prop) in self.vars:
                parts.append(f"{attr} = {self.vars[(n.id, prop)]}.value.dp.toPx()")
        return [f"{ind}.graphicsLayer {{ {'; '.join(parts)} }}"] if parts else []


def effects(n, dp, shape: str, ind: str) -> list[str]:
    """Модификаторы эффектов узла до заливки: тень и размытие. dp(px) → строка «N.dp»."""
    out = []
    if n.elevation > 0 and n.type not in ("text", "vector"):
        out.append(f"{ind}.shadow(elevation = {ELEVATION_DP[n.elevation]}.dp, shape = {shape})")
    if n.blur > 0:
        out.append(f"{ind}.blur({dp(n.blur)})")
    return out


def brush(n, kcolor) -> str | None:
    """Градиент заливки → Brush (угол как в CSS: 180° — сверху вниз)."""
    if n.gradient == "none" or not n.fill or not n.fill2:
        return None
    colors = f"listOf({kcolor(n.fill)}, {kcolor(n.fill2)})"
    if n.gradient == "radial":
        return f"Brush.radialGradient({colors})"
    a = n.grad_angle % 360
    if abs(a - 180) < 0.5:
        return f"Brush.verticalGradient({colors})"
    if abs(a) < 0.5:
        return f"Brush.verticalGradient(listOf({kcolor(n.fill2)}, {kcolor(n.fill)}))"
    if abs(a - 90) < 0.5:
        return f"Brush.horizontalGradient({colors})"
    if abs(a - 270) < 0.5:
        return f"Brush.horizontalGradient(listOf({kcolor(n.fill2)}, {kcolor(n.fill)}))"
    dx, dy = math.sin(math.radians(a)), -math.cos(math.radians(a))
    return f"linearAngleBrush({colors}, {_f(dx)}, {_f(dy)})"


NAV_MOTION = '''package {pkg}.navigation

import androidx.compose.animation.ContentTransform
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.Easing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.ui.unit.IntOffset

/** Переход между экранами из логики прототипа: вид (fade, slide_left, …), длительность и плавность. */
data class NavMotion(val kind: String = "fade", val durationMs: Int = 300, val easing: String = "ease_in_out")

/** Плавность «шаг»: значение меняется в самом конце. */
val StepEasing = Easing { if (it < 1f) 0f else 1f }

fun easingOf(name: String): Easing = when (name) {
    "linear" -> LinearEasing
    "ease_in" -> CubicBezierEasing(0.42f, 0f, 1f, 1f)
    "ease_out" -> CubicBezierEasing(0f, 0f, 0.58f, 1f)
    "step" -> StepEasing
    else -> CubicBezierEasing(0.42f, 0f, 0.58f, 1f)
}

/** Переход вперёд — как в дизайне; «Назад» — тот же переход в обратную сторону. */
fun screenTransition(m: NavMotion, forward: Boolean): ContentTransform {
    if (m.kind == "none" || m.durationMs <= 0) return EnterTransition.None togetherWith ExitTransition.None
    val ease = easingOf(m.easing)
    val move = tween<IntOffset>(m.durationMs, easing = ease)
    val fade = tween<Float>(m.durationMs, easing = ease)
    val d = if (forward) 1 else -1
    return when (m.kind) {
        "slide_left" -> slideInHorizontally(move) { d * it } togetherWith slideOutHorizontally(move) { -d * it }
        "slide_right" -> slideInHorizontally(move) { -d * it } togetherWith slideOutHorizontally(move) { d * it }
        "slide_up" -> slideInVertically(move) { d * it } togetherWith slideOutVertically(move) { -d * it }
        "slide_down" -> slideInVertically(move) { -d * it } togetherWith slideOutVertically(move) { d * it }
        else -> fadeIn(fade) togetherWith fadeOut(fade)
    }
}
'''

GRADIENT_KT = '''package {pkg}.ui.components

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.LinearGradientShader
import androidx.compose.ui.graphics.Shader
import androidx.compose.ui.graphics.ShaderBrush
import kotlin.math.abs

/** Линейный градиент под произвольным углом (направление dx, dy), растянутый на размер элемента. */
fun linearAngleBrush(colors: List<Color>, dx: Float, dy: Float): Brush = object : ShaderBrush() {
    override fun createShader(size: Size): Shader {
        val half = (abs(size.width * dx) + abs(size.height * dy)) / 2f
        val c = Offset(size.width / 2f, size.height / 2f)
        return LinearGradientShader(c - Offset(dx * half, dy * half), c + Offset(dx * half, dy * half), colors)
    }
}
'''
