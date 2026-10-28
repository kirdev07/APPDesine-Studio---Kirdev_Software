"""Виджеты рабочего стола Android → Jetpack Glance. Без Qt.

Экран-виджет (устройство «Виджет N×M») переводится в GlanceAppWidget: контейнеры — Column / Row / Box, текст —
Text со стилем, фигуры — Box с заливкой и скруглением, значки — Image из векторного ресурса (res/drawable),
картинки — Image из ресурса. Нажатие на виджет открывает приложение. Для каждого виджета — приёмник
(GlanceAppWidgetReceiver), описание в res/xml и запись в манифесте; виджет появляется в списке виджетов телефона.
Ограничения Glance: нет свободного смещения (элементы вне раскладки ставятся отступами внутри Box), нет теней,
градиентов и масок; скругление углов работает на Android 12+.
"""

from __future__ import annotations

from xml.sax.saxutils import quoteattr

from app.core.document import tree
from app.core.document.model import Screen

WIDGET_PREFIX = "android_widget_"
GLANCE_VERSION = "1.1.1"
_WEIGHT = {(0, 449): "FontWeight.Normal", (450, 599): "FontWeight.Medium", (600, 1000): "FontWeight.Bold"}


def is_widget(s: Screen) -> bool:
    return s.platform == "android" and s.device_id.startswith(WIDGET_PREFIX)


def cells(s: Screen) -> tuple[int, int]:
    """Размер в клетках лаунчера из устройства «android_widget_4x2»."""
    try:
        c, r = s.device_id[len(WIDGET_PREFIX):].split("x")
        return int(c), int(r)
    except ValueError:
        return 2, 2


def _w(n) -> str:
    return next(v for (lo, hi), v in _WEIGHT.items() if lo <= n.font_weight <= hi)


def _kc(c: str) -> str:
    c = (c or "#000000").lstrip("#").upper()
    a = c[6:8] if len(c) == 8 else "FF"
    return f"Color(0x{a}{c[:6]})"


def vector_xml(n) -> str:
    """Значок (векторный узел) → VectorDrawable; цвет задаётся при показе (tint)."""
    w, h = round(n.vb_w, 3), round(n.vb_h, 3)
    rule = ' android:fillType="evenOdd"' if n.fill_rule == "evenodd" else ""
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
            f'    android:width="24dp" android:height="24dp" android:viewportWidth="{w}" android:viewportHeight="{h}">\n'
            f'    <path android:fillColor="#FF000000"{rule} android:pathData={quoteattr(n.path)} />\n</vector>\n')


class GlanceWidget:
    """Один виджет: Kotlin-код, ресурсы значков, описание для лаунчера."""

    def __init__(self, proj, s: Screen, name: str):
        from app.engines.preview.devices import screen_dpi
        self.p, self.s, self.name = proj, s, name
        self.k = screen_dpi(s) / 160
        self.res = name.lower()
        self.icons: dict[str, str] = {}   # имя ресурса → XML
        self._icon_names: dict[str, str] = {}
        from app.exporters.android_project import kstr
        self.kstr = kstr

    def dp(self, v: float) -> str:
        return f"{round(v / self.k, 1):g}.dp"

    def _icon(self, n) -> str:
        key = (n.path, n.vb_w, n.vb_h, n.fill_rule)
        k = repr(key)
        if k not in self._icon_names:
            res = f"{self.res}_icon_{len(self._icon_names) + 1}"
            self._icon_names[k] = res
            self.icons[res] = vector_xml(n)
        return self._icon_names[k]

    def _mod(self, n, parent, extra: list[str] | None = None) -> str:
        m = ["GlanceModifier"]
        if parent is not None and not parent.auto_layout:  # свободное место в Box — отступом
            dx, dy = n.x - parent.x - parent.pad_l, n.y - parent.y - parent.pad_t
            if dx > 0.5 or dy > 0.5:
                m.append(f".padding(start = {self.dp(max(0.0, dx))}, top = {self.dp(max(0.0, dy))})")
        if n.sizing_h == "fill" and parent is not None and parent.auto_layout and parent.layout == "horizontal":
            m.append(".defaultWeight()")
        elif n.sizing_h == "fill" or (parent is None):
            m.append(".fillMaxWidth()")
        elif n.sizing_h != "hug" and n.type != "text":
            m.append(f".width({self.dp(n.w)})")
        if parent is None:
            m.append(".fillMaxHeight()")
        elif n.sizing_v == "fill":
            m.append(".fillMaxHeight()" if parent.layout != "vertical" else ".defaultWeight()")
        elif n.sizing_v != "hug" and n.type != "text":
            m.append(f".height({self.dp(n.h)})")
        if n.fill and n.type not in ("text", "vector", "image"):
            m.append(f".background({_kc(n.fill)})")
        if n.radius and n.type not in ("text", "vector"):
            m.append(f".cornerRadius({self.dp(min(n.radius, min(n.w, n.h) / 2))})")
        if n.is_frame and any((n.pad_t, n.pad_r, n.pad_b, n.pad_l)):
            m.append(f".padding(start = {self.dp(n.pad_l)}, top = {self.dp(n.pad_t)}, end = {self.dp(n.pad_r)}, "
                     f"bottom = {self.dp(n.pad_b)})")
        m += extra or []
        return "".join(m)

    def node(self, n, parent, ind: str) -> list[str]:
        if not n.visible:
            return []
        if n.is_group:
            return [x for c in n.children for x in self.node(c, parent, ind)]
        if n.type == "text":
            style = (f"TextStyle(color = ColorProvider({_kc(n.text_color)}), fontSize = {round(n.font_size / self.k, 1):g}.sp, "
                     f"fontWeight = {_w(n)})")
            lines = f", maxLines = {n.max_lines}" if n.max_lines else ""
            return [f"{ind}Text({self.kstr(n.text)}, style = {style}, modifier = {self._mod(n, parent)}{lines})"]
        if n.type == "vector" and n.path:
            res = self._icon(n)
            tint = f", colorFilter = ColorFilter.tint(ColorProvider({_kc(n.fill)}))" if n.fill else ""
            return [f"{ind}Image(provider = ImageProvider(R.drawable.{res}), contentDescription = "
                    f"{self.kstr(n.name)}, modifier = GlanceModifier.size({self.dp(n.w)}, {self.dp(n.h)}){tint})"]
        if n.type == "image":
            res = self.p.drawables.get(n.asset_id)
            if not res:
                return [f"{ind}// картинка «{n.name}» не включена в пакет"]
            return [f"{ind}Image(provider = ImageProvider(R.drawable.{res}), contentDescription = {self.kstr(n.name)}, "
                    f"contentScale = ContentScale.{'Crop' if n.fit == 'cover' else 'Fit'}, modifier = {self._mod(n, parent)})"]
        if not n.is_container or not n.children:  # фигура: прямоугольник / круг
            return [f"{ind}Box(modifier = {self._mod(n, parent)}) {{}}"]
        kids = [c for c in n.children if c.visible]
        if n.layout == "vertical":
            h = {"start": "Start", "center": "CenterHorizontally", "end": "End", "stretch": "Start"}[n.cross_align]
            v = {"start": "Top", "center": "CenterVertically", "end": "Bottom", "space_between": "Top"}[n.main_align]
            out = [f"{ind}Column(modifier = {self._mod(n, parent)}, verticalAlignment = Alignment.{v}, "
                   f"horizontalAlignment = Alignment.{h}) {{"]
            for i, c in enumerate(kids):
                if i and n.gap:
                    out.append(f"{ind}    Spacer(GlanceModifier.height({self.dp(n.gap)}))")
                out += self.node(c, n, ind + "    ")
            return out + [f"{ind}}}"]
        if n.layout in ("horizontal", "wrap"):
            v = {"start": "Top", "center": "CenterVertically", "end": "Bottom", "stretch": "Top"}[n.cross_align]
            h = {"start": "Start", "center": "CenterHorizontally", "end": "End", "space_between": "Start"}[n.main_align]
            out = [f"{ind}Row(modifier = {self._mod(n, parent)}, horizontalAlignment = Alignment.{h}, "
                   f"verticalAlignment = Alignment.{v}) {{"]
            for i, c in enumerate(kids):
                if i and (n.gap or n.main_align == "space_between"):
                    sp = "GlanceModifier.defaultWeight()" if n.main_align == "space_between" else \
                        f"GlanceModifier.width({self.dp(n.gap)})"
                    out.append(f"{ind}    Spacer({sp})")
                out += self.node(c, n, ind + "    ")
            return out + [f"{ind}}}"]
        if n.layout == "grid":
            cols = max(1, n.grid_columns)
            out = [f"{ind}Column(modifier = {self._mod(n, parent)}) {{"]
            for r in range(0, len(kids), cols):
                if r:
                    out.append(f"{ind}    Spacer(GlanceModifier.height({self.dp(n.row_gap)}))")
                out.append(f"{ind}    Row(modifier = GlanceModifier.fillMaxWidth()) {{")
                for i, c in enumerate(kids[r:r + cols]):
                    if i:
                        out.append(f"{ind}        Spacer(GlanceModifier.width({self.dp(n.gap)}))")
                    out += self.node(c, n, ind + "        ")
                out.append(f"{ind}    }}")
            return out + [f"{ind}}}"]
        out = [f"{ind}Box(modifier = {self._mod(n, parent)}) {{"]
        for c in kids:
            out += self.node(c, n, ind + "    ")
        return out + [f"{ind}}}"]

    def kotlin(self) -> str:
        pkg = self.p.pkg
        body = []
        roots = [n for n in self.s.nodes if n.visible]
        for n in roots:
            body += self.node(n, None, "            ")
        c, r = cells(self.s)
        return f'''package {pkg}.widget

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.ColorFilter
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.Image
import androidx.glance.ImageProvider
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.layout.*
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import {pkg}.MainActivity
import {pkg}.R

/** Виджет «{self.title()}» ({c}×{r} клетки). Сгенерирован App Design Studio. Нажатие открывает приложение. */
class {self.name}Widget : GlanceAppWidget() {{
    override suspend fun provideGlance(context: Context, id: GlanceId) {{
        provideContent {{
            Box(modifier = GlanceModifier.fillMaxSize().clickable(actionStartActivity<MainActivity>())) {{
{chr(10).join(body)}
            }}
        }}
    }}
}}

class {self.name}WidgetReceiver : GlanceAppWidgetReceiver() {{
    override val glanceAppWidget: GlanceAppWidget = {self.name}Widget()
}}
'''

    def info_xml(self) -> str:
        c, r = cells(self.s)
        w, h = 70 * c - 30, 70 * r - 30  # минимум по правилу Android (иначе лаунчер берёт лишнюю клетку)
        preview = (f'    android:previewImage="@drawable/{self.res}_preview"\n'
                   if self.s.id in self.p.widget_previews else "")
        return ('<?xml version="1.0" encoding="utf-8"?>\n'
                '<appwidget-provider xmlns:android="http://schemas.android.com/apk/res/android"\n'
                f'    android:minWidth="{w}dp" android:minHeight="{h}dp"\n'
                f'    android:targetCellWidth="{c}" android:targetCellHeight="{r}"\n'
                '    android:resizeMode="horizontal|vertical" android:widgetCategory="home_screen"\n'
                '    android:updatePeriodMillis="0"\n' + preview +
                '    android:initialLayout="@layout/glance_default_loading_layout"\n'
                f'    android:description="@string/{self.res}_widget_description" />\n')

    def title(self) -> str:
        """Название виджета для людей: «Часы и погода» из «Виджет «Часы и погода»»."""
        t = self.s.name.strip()
        if t.startswith("Виджет «") and t.endswith("»"):
            t = t[len("Виджет «"):-1]
        return t or "Виджет"

    def receiver_xml(self) -> str:
        return (f'        <receiver\n            android:name=".widget.{self.name}WidgetReceiver"\n'
                f'            android:label="@string/{self.res}_widget_label"\n'
                '            android:exported="true">\n            <intent-filter>\n'
                '                <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />\n'
                '            </intent-filter>\n            <meta-data\n'
                '                android:name="android.appwidget.provider"\n'
                f'                android:resource="@xml/{self.res}_widget_info" />\n        </receiver>\n')

    def files(self, src: str) -> dict[str, str]:
        out = {f"{src}/widget/{self.name}Widget.kt": self.kotlin(),
               f"app/src/main/res/xml/{self.res}_widget_info.xml": self.info_xml()}
        for res, xml in self.icons.items():
            out[f"app/src/main/res/drawable/{res}.xml"] = xml
        if self.s.id in self.p.widget_previews:  # снимок виджета из дизайна — в списке виджетов телефона
            out[f"app/src/main/res/drawable-nodpi/{self.res}_preview.png"] = self.p.widget_previews[self.s.id]
        return out
