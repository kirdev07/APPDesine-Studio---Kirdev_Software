"""Движок раскладки: Auto Layout (стеки и сетки), размеры «фикс./заполнить/по содержимому», min/max,
привязки (constraints) в обычных контейнерах и диагностика. Не зависит от Qt.

Модель координат: все узлы хранят абсолютную геометрию. Движок получает снимок геометрии «до» изменения
и пересчитывает узлы так, чтобы:
  * дети Auto Layout-фрейма стояли по правилам раскладки;
  * дети обычного контейнера (экрана или фрейма без раскладки) следовали привязкам, если контейнер
    сдвинулся или изменил размер;
  * текст и фреймы «по содержимому» получили размер содержимого.
Результат детерминирован: одинаковый вход и одинаковое измерение текста дают одинаковый выход,
а повторный прогон по результату не даёт изменений.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from app.core.document.model import Node, Screen
from app.core.document.tree import Rect, bounds, descendants

EPS = 0.005


# Вид текста, влияющий на размер: (интервал между буквами, высота строки, курсив, регистр, не больше строк)
PLAIN_LOOK = (0.0, 0.0, False, "none", 0)


def text_look(n) -> tuple:
    return (n.letter_spacing, n.line_height, n.italic, n.text_case, n.max_lines)


class TextMeasurer(Protocol):
    def measure(self, text: str, family: str, size: float, weight: int, max_width: float | None,
                look: tuple = PLAIN_LOOK) -> tuple[float, float]:
        """Размер текста: без переноса (max_width=None) или с переносом по словам в заданную ширину."""


class SimpleMeasurer:
    """Детерминированное приближённое измерение (для тестов и работы без Qt): моноширинная модель."""

    def __init__(self, char_ratio: float = 0.55, line_ratio: float = 1.25):
        self.char_ratio, self.line_ratio = char_ratio, line_ratio

    def measure(self, text, family, size, weight, max_width, look=PLAIN_LOOK):
        spacing, line_h, _italic, case, max_lines = look
        cw = size * self.char_ratio * (1.06 if weight >= 600 else 1.0) * (1.1 if case == "upper" else 1.0) + spacing
        lh = size * (line_h or self.line_ratio)
        paragraphs = text.split("\n") if text else [""]
        lines, widest = 0, 0.0
        for para in paragraphs:
            if max_width is None:
                lines += 1
                widest = max(widest, len(para) * cw)
                continue
            per_line = max(1, int(max_width // cw))
            line_len, count = 0, 1
            for word in para.split(" "):
                wl = len(word)
                if wl > per_line:  # слово длиннее строки режется на части
                    if line_len:
                        count += 1
                    full, rest = divmod(wl, per_line)
                    count += full - (0 if rest else 1)
                    line_len = rest or per_line
                    widest = max(widest, per_line * cw)
                    continue
                need = wl if line_len == 0 else line_len + 1 + wl
                if need <= per_line:
                    line_len = need
                else:
                    count += 1
                    line_len = wl
                widest = max(widest, line_len * cw)
            lines += count
        if max_lines:
            lines = min(lines, max_lines)
        return round(widest, 2), round(lines * lh, 2)


@dataclass(frozen=True)
class Diagnostic:
    severity: str  # "warning" | "info"
    node_id: str
    message: str


def resize_screen(screen: Screen, width: int, height: int, engine: LayoutEngine) -> tuple[Screen, list[Diagnostic]]:
    """Копия экрана, перестроенная под другой размер (проверка адаптивности). Исходный экран не меняется."""
    from app.core.document.tree import geometry, node_map

    clone = Screen.from_dict(screen.to_dict())
    before, old_size = geometry(clone), (clone.width, clone.height)
    clone.width, clone.height = width, height
    changes, diags = engine.layout_screen(clone, before, old_size)
    m = node_map(clone)
    for nid, props in changes.items():
        for k, v in props.items():
            setattr(m[nid], k, v)
    return clone, diags


def _clamp(v: float, lo: float, hi: float) -> float:
    if hi > 0:
        v = min(v, hi)
    return max(v, lo)


def _constrain(mode: str, x: float, w: float, opos: float, osize: float, npos: float, nsize: float):
    if mode in ("left", "top"):
        return npos + (x - opos), w
    if mode in ("right", "bottom"):
        gap = (opos + osize) - (x + w)
        return npos + nsize - gap - w, w
    if mode in ("left_right", "top_bottom"):
        lg, rg = x - opos, (opos + osize) - (x + w)
        return npos + lg, max(0.0, nsize - lg - rg)
    if mode == "center":
        off = (x + w / 2) - (opos + osize / 2)
        return npos + nsize / 2 + off - w / 2, w
    s = nsize / osize if osize else 1.0  # scale
    return npos + (x - opos) * s, w * s


MAX_PASSES = 4


class LayoutEngine:
    def __init__(self, measurer: TextMeasurer | None = None):
        self.measurer = measurer or SimpleMeasurer()

    # ---------- публичный вход ----------
    def layout_screen(self, screen: Screen, before: dict[str, Rect] | None = None,
                      before_size: tuple[int, int] | None = None) -> tuple[dict[str, dict], list[Diagnostic]]:
        """Раскладка до устойчивого состояния: высота «по содержимому» зависит от ширины, которую родитель
        назначает в этом же проходе, поэтому иногда нужен повтор (не больше MAX_PASSES). Экран не меняется —
        возвращаются изменения относительно исходной геометрии."""
        changes, diags = self._layout_pass(screen, before, before_size)
        if not changes:
            return changes, diags
        nodes = [n for n in self._all(screen.nodes) if not n.is_group]
        original = {n.id: (n.x, n.y, n.w, n.h) for n in nodes}
        by_id = {n.id: n for n in nodes}
        try:
            cur = changes
            for _ in range(MAX_PASSES - 1):
                for nid, props in cur.items():
                    for k, v in props.items():
                        setattr(by_id[nid], k, v)
                snap = {n.id: (n.x, n.y, n.w, n.h) for n in nodes}
                cur, diags = self._layout_pass(screen, snap, (screen.width, screen.height))
                if not cur:
                    break
            for nid, props in cur.items():
                for k, v in props.items():
                    setattr(by_id[nid], k, v)
            final = {n.id: (n.x, n.y, n.w, n.h) for n in nodes}
        finally:
            for n in nodes:
                n.x, n.y, n.w, n.h = original[n.id]
        out = {}
        for nid, g in final.items():
            props = {k: round(v, 2) for k, v, old in zip("xywh", g, original[nid]) if abs(v - old) > EPS}
            if props:
                out[nid] = props
        return out, diags

    def _layout_pass(self, screen: Screen, before, before_size) -> tuple[dict[str, dict], list[Diagnostic]]:
        self.screen = screen
        self.start: dict[str, list[float]] = {}
        for n in self._all(screen.nodes):
            if not n.is_group:
                self.start[n.id] = [n.x, n.y, n.w, n.h]
        self.geo = {k: list(v) for k, v in self.start.items()}
        self.before = dict(before or {})  # копия: при переносе групп снимок «до» уточняется по ходу
        self.diags: list[Diagnostic] = []
        self._seen_diag: set[tuple[str, str]] = set()
        self._cache: dict = {}
        ow, oh = before_size or (screen.width, screen.height)
        self._arrange_free(screen.nodes, (0, 0, screen.width, screen.height), (0, 0, ow, oh))
        self._check_text_overflow(screen.nodes)
        changes = {}
        for nid, g in self.geo.items():
            s = self.start[nid]
            props = {k: round(v, 2) for k, v, old in zip("xywh", g, s) if abs(v - old) > EPS}
            if props:
                changes[nid] = props
        return changes, self.diags

    def diagnose(self, screen: Screen) -> list[Diagnostic]:
        return self.layout_screen(screen)[1]

    # ---------- вспомогательное ----------
    @staticmethod
    def _all(nodes):
        for n in nodes:
            yield n
            if n.is_container:
                yield from LayoutEngine._all(n.children)

    def _diag(self, severity: str, node: Node, message: str) -> None:
        key = (node.id, message)
        if key not in self._seen_diag:
            self._seen_diag.add(key)
            self.diags.append(Diagnostic(severity, node.id, f"«{node.name or node.type}»: {message}"))

    def _old(self, node: Node) -> list[float]:
        b = self.before.get(node.id)
        return list(b) if b is not None else list(self.start[node.id])

    def _measure(self, node: Node, max_width: float | None) -> tuple[float, float]:
        look = text_look(node)
        key = (node.text, node.font_family, node.font_size, node.font_weight,
               None if max_width is None else round(max_width, 2), look)
        if key not in self._cache:
            if look == PLAIN_LOOK:  # обычный текст — как раньше (сторонние измерители без look тоже работают)
                self._cache[key] = self.measurer.measure(node.text, node.font_family, node.font_size,
                                                         node.font_weight, max_width)
            else:
                self._cache[key] = self.measurer.measure(node.text, node.font_family, node.font_size,
                                                         node.font_weight, max_width, look)
        return self._cache[key]

    def _clamp_w(self, n: Node, w: float) -> float:
        if n.max_w and n.min_w > n.max_w:
            self._diag("warning", n, f"минимальная ширина {n.min_w:g} больше максимальной {n.max_w:g}")
        return _clamp(w, n.min_w, n.max_w)

    def _clamp_h(self, n: Node, h: float) -> float:
        if n.max_h and n.min_h > n.max_h:
            self._diag("warning", n, f"минимальная высота {n.min_h:g} больше максимальной {n.max_h:g}")
        return _clamp(h, n.min_h, n.max_h)

    @staticmethod
    def _visible(nodes):
        return [n for n in nodes if n.visible]

    # ---------- собственные размеры ----------
    def _intrinsic_w(self, n: Node) -> float:
        if n.is_group:
            b = bounds(n)
            return b[2] if b else 0.0
        if n.type == "text" and n.sizing_h == "hug":
            return self._clamp_w(n, self._measure(n, None)[0])
        if n.auto_layout and n.sizing_h == "hug":
            return self._clamp_w(n, self._content(n, None)[0])
        return self.geo[n.id][2]

    def _intrinsic_h(self, n: Node, width: float) -> float:
        if n.is_group:
            b = bounds(n)
            return b[3] if b else 0.0
        if n.type == "text" and n.sizing_v == "hug":
            return self._clamp_h(n, self._measure(n, max(1.0, width))[1])
        if n.auto_layout and n.sizing_v == "hug":
            return self._clamp_h(n, self._content(n, width)[1])
        return self.geo[n.id][3]

    def _child_w(self, f: Node, c: Node, inner_w: float, along_main: bool) -> float:
        fill = (not c.is_group) and c.sizing_h == "fill"
        if not along_main and (fill or f.cross_align == "stretch") and not c.is_group:
            return self._clamp_w(c, inner_w)
        return self._intrinsic_w(c)

    def _content(self, f: Node, width: float | None) -> tuple[float, float]:
        """Размер содержимого Auto Layout-фрейма (с отступами). width — заданная ширина фрейма или None."""
        kids = self._visible(f.children)
        ph, pv = f.pad_l + f.pad_r, f.pad_t + f.pad_b
        inner_w = None if width is None else max(0.0, width - ph)
        if not kids:
            return ph, pv
        if f.layout == "vertical":
            ws = [self._child_w(f, c, inner_w, False) if inner_w is not None else self._intrinsic_w(c) for c in kids]
            hs = [self._intrinsic_h(c, w) for c, w in zip(kids, ws)]
            for c in kids:
                if not c.is_group and c.sizing_v == "fill" and f.sizing_v == "hug":
                    self._diag("info", c, "«Заполнить» внутри фрейма «по содержимому» — считается по содержимому")
            return max(ws) + ph, sum(hs) + f.gap * (len(kids) - 1) + pv
        if f.layout == "horizontal":
            ws = [self._intrinsic_w(c) for c in kids]
            for c in kids:
                if not c.is_group and c.sizing_h == "fill" and f.sizing_h == "hug":
                    self._diag("info", c, "«Заполнить» внутри фрейма «по содержимому» — считается по содержимому")
            hs = [self._intrinsic_h(c, w) for c, w in zip(kids, ws)]
            return sum(ws) + f.gap * (len(kids) - 1) + ph, max(hs) + pv
        if f.layout == "wrap":
            if inner_w is None:  # ширина по содержимому — всё в одну строку
                ws = [self._intrinsic_w(c) for c in kids]
                hs = [self._intrinsic_h(c, w) for c, w in zip(kids, ws)]
                return sum(ws) + f.gap * (len(kids) - 1) + ph, max(hs) + pv
            lines = self._wrap_lines(f, kids, inner_w)
            heights = [max(h for _, _, h in line) for line in lines]
            return width, sum(heights) + f.row_gap * (len(lines) - 1) + pv
        cols = max(1, f.grid_columns)
        if inner_w is not None:
            col_w = max(0.0, (inner_w - f.gap * (cols - 1)) / cols)
        else:
            col_w = max(self._intrinsic_w(c) for c in kids)
        rows = [kids[i:i + cols] for i in range(0, len(kids), cols)]
        row_hs = [max(self._intrinsic_h(c, col_w) for c in r) for r in rows]
        return (cols * col_w + f.gap * (cols - 1) + ph,
                sum(row_hs) + f.row_gap * (len(rows) - 1) + pv)

    # ---------- размещение ----------
    def _own_size(self, n: Node, w: float, h: float, parent_auto: bool) -> tuple[float, float]:
        """Применяет «по содержимому» и min/max к узлу вне Auto Layout-родителя."""
        if n.is_group:
            return w, h
        if not parent_auto and "fill" in (n.sizing_h, n.sizing_v):
            self._diag("info", n, "«Заполнить» действует только внутри фрейма с Auto Layout")
        if n.type == "text":
            if n.sizing_h == "hug":
                w = self._measure(n, None)[0]
            w = self._clamp_w(n, w)
            if n.sizing_v == "hug":
                h = self._measure(n, max(1.0, w))[1]
            return w, self._clamp_h(n, h)
        if n.auto_layout:
            if n.sizing_h == "hug":
                w = self._content(n, None)[0]
            w = self._clamp_w(n, w)
            if n.sizing_v == "hug":
                h = self._content(n, w)[1]
            return w, self._clamp_h(n, h)
        if n.is_frame and "hug" in (n.sizing_h, n.sizing_v):
            self._diag("info", n, "«По содержимому» у фрейма без Auto Layout не применяется")
        return self._clamp_w(n, w), self._clamp_h(n, h)

    def _arrange_free(self, children: list[Node], new_c: Rect, old_c: Rect) -> None:
        changed = any(abs(a - b) > EPS for a, b in zip(new_c, old_c))
        for n in children:
            if n.is_group:
                self._arrange_free(n.children, new_c, old_c)
                continue
            x, y, w, h = self.geo[n.id]
            if changed:
                x, w = _constrain(n.constraint_h, x, w, old_c[0], old_c[2], new_c[0], new_c[2])
                y, h = _constrain(n.constraint_v, y, h, old_c[1], old_c[3], new_c[1], new_c[3])
            w, h = self._own_size(n, w, h, parent_auto=False)
            self._place(n, (x, y, w, h))

    def _place(self, n: Node, rect: Rect) -> None:
        if n.is_group:
            b = bounds(n)
            if not b:
                return
            dx, dy = rect[0] - b[0], rect[1] - b[1]
            if abs(dx) > EPS or abs(dy) > EPS:
                for d in descendants(n):
                    g = self.geo[d.id]
                    g[0] += dx
                    g[1] += dy
                    # узлы внутри группы переехали вместе с ней — их «старое» положение тоже сдвигается
                    self.before[d.id] = (g[0], g[1], g[2], g[3])
            return
        old = self._old(n)
        self.geo[n.id] = [rect[0], rect[1], rect[2], rect[3]]
        if n.is_frame:
            if n.auto_layout:
                self._arrange_auto(n, tuple(self.geo[n.id]))
            else:
                self._arrange_free(n.children, tuple(self.geo[n.id]), tuple(old))

    def _distribute(self, kids: list[Node], sizes: list[float | None], available: float, axis: str) -> list[float]:
        """Распределяет свободное место между «заполнить» (None) с учётом min/max."""
        sizes = list(sizes)
        pending = [i for i, s in enumerate(sizes) if s is None]
        for _ in range(len(pending) + 1):
            if not pending:
                break
            fixed = sum(s for s in sizes if s is not None)
            share = max(0.0, available - fixed) / len(pending)
            frozen = []
            for i in pending:
                c = kids[i]
                v = self._clamp_w(c, share) if axis == "w" else self._clamp_h(c, share)
                if abs(v - share) > EPS:
                    sizes[i] = v
                    frozen.append(i)
            if not frozen:
                for i in pending:
                    sizes[i] = share
                pending = []
            else:
                pending = [i for i in pending if i not in frozen]
        return [s or 0.0 for s in sizes]

    def _arrange_auto(self, f: Node, rect: Rect) -> None:
        kids = self._visible(f.children)
        if not kids:
            return
        x, y, w, h = rect
        ix, iy = x + f.pad_l, y + f.pad_t
        iw, ih = max(0.0, w - f.pad_l - f.pad_r), max(0.0, h - f.pad_t - f.pad_b)
        if f.layout == "grid":
            self._arrange_grid(f, kids, ix, iy, iw, ih)
            return
        if f.layout == "wrap":
            self._arrange_wrap(f, kids, ix, iy, iw, ih)
            return
        vertical = f.layout == "vertical"
        n = len(kids)
        gaps = f.gap * (n - 1)
        if vertical:
            cross = [self._child_w(f, c, iw, along_main=False) for c in kids]
            hug_parent = f.sizing_v == "hug"
            main0 = [None if (not c.is_group and c.sizing_v == "fill" and not hug_parent)
                     else self._intrinsic_h(c, cw) for c, cw in zip(kids, cross)]
            main = self._distribute(kids, main0, ih - gaps, "h")
            inner_main, inner_cross, start_main, start_cross = ih, iw, iy, ix
        else:
            hug_parent = f.sizing_h == "hug"
            main0 = [None if (not c.is_group and c.sizing_h == "fill" and not hug_parent)
                     else self._intrinsic_w(c) for c in kids]
            main = self._distribute(kids, main0, iw - gaps, "w")
            cross = []
            for c, cw in zip(kids, main):
                if not c.is_group and (c.sizing_v == "fill" or f.cross_align == "stretch"):
                    cross.append(self._clamp_h(c, ih))
                else:
                    cross.append(self._intrinsic_h(c, cw))
            inner_main, inner_cross, start_main, start_cross = iw, ih, ix, iy
        if f.paging and not hug_parent:  # листание страницами: каждая страница — во всю ширину (высоту) контейнера
            main = [inner_main] * n
        total = sum(main) + gaps
        gap = f.gap
        if f.main_align == "space_between" and n > 1:
            gap = max(f.gap if inner_main < sum(main) else 0.0, (inner_main - sum(main)) / (n - 1))
            offset = 0.0
            total = sum(main) + gap * (n - 1)
        else:
            free = inner_main - total
            offset = {"start": 0.0, "center": free / 2, "end": free}.get(f.main_align, 0.0)
        overflow_axis = f.sizing_v if vertical else f.sizing_h
        scrolls = f.scroll == ("vertical" if vertical else "horizontal")  # прокрутка — переполнение ожидаемо
        if total > inner_main + 0.5 and overflow_axis != "hug" and not scrolls:
            self._diag("warning", f, f"содержимое не помещается ({total:.0f} из {inner_main:.0f} px)")
        pos = start_main + offset
        for c, m, cr in zip(kids, main, cross):
            align = f.cross_align
            if align == "center":
                cpos = start_cross + (inner_cross - cr) / 2
            elif align == "end":
                cpos = start_cross + inner_cross - cr
            else:
                cpos = start_cross
            if vertical:
                self._place(c, (cpos, pos, cr, m))
            else:
                self._place(c, (pos, cpos, m, cr))
            pos += m + gap

    def _wrap_lines(self, f: Node, kids: list[Node], inner_w: float) -> list[list[tuple[Node, float, float]]]:
        """Строки раскладки с переносом: (элемент, ширина, высота); элемент шире строки — один в строке."""
        lines: list[list[tuple[Node, float, float]]] = [[]]
        used = 0.0
        for c in kids:
            w = min(self._intrinsic_w(c), inner_w) if inner_w > 0 else self._intrinsic_w(c)
            h = self._intrinsic_h(c, w)
            need = w if not lines[-1] else used + f.gap + w
            if lines[-1] and need > inner_w + 0.5:
                lines.append([])
                need = w
            lines[-1].append((c, w, h))
            used = need
        return [ln for ln in lines if ln]

    def _arrange_wrap(self, f: Node, kids: list[Node], ix: float, iy: float, iw: float, ih: float) -> None:
        """В строку, а что не помещается — на следующую (чипы, теги). Выравнивание — внутри каждой строки."""
        cy = iy
        for line in self._wrap_lines(f, kids, iw):
            row_h = max(h for _, _, h in line)
            total = sum(w for _, w, _ in line) + f.gap * (len(line) - 1)
            gap = f.gap
            if f.main_align == "space_between" and len(line) > 1:
                gap = max(f.gap, (iw - (total - f.gap * (len(line) - 1))) / (len(line) - 1))
                offset = 0.0
            else:
                offset = {"start": 0.0, "center": (iw - total) / 2, "end": iw - total}.get(f.main_align, 0.0)
            cx = ix + max(0.0, offset)
            for c, w, h in line:
                if not c.is_group and (c.sizing_v == "fill" or f.cross_align == "stretch"):
                    h = self._clamp_h(c, row_h)
                cpos = {"center": cy + (row_h - h) / 2, "end": cy + row_h - h}.get(f.cross_align, cy)
                self._place(c, (cx, cpos, w, h))
                cx += w + gap
            cy += row_h + f.row_gap
        used = cy - f.row_gap - iy
        if used > ih + 0.5 and f.sizing_v != "hug" and f.scroll != "vertical":
            self._diag("warning", f, f"строки не помещаются по высоте ({used:.0f} из {ih:.0f} px)")

    def _arrange_grid(self, f: Node, kids: list[Node], ix: float, iy: float, iw: float, ih: float) -> None:
        cols = max(1, f.grid_columns)
        col_w = max(0.0, (iw - f.gap * (cols - 1)) / cols)
        rows = [kids[i:i + cols] for i in range(0, len(kids), cols)]
        cy = iy
        for row in rows:
            sizes = []
            for c in row:
                stretch = not c.is_group and (c.sizing_h == "fill" or f.cross_align == "stretch")
                cw = self._clamp_w(c, col_w) if stretch else min(self._intrinsic_w(c), col_w)
                sizes.append((cw, self._intrinsic_h(c, cw)))
            row_h = max(hh for _, hh in sizes)
            for k, (c, (cw, ch)) in enumerate(zip(row, sizes)):
                if not c.is_group and c.sizing_v == "fill":
                    ch = self._clamp_h(c, row_h)
                cx = ix + k * (col_w + f.gap)
                if f.cross_align == "center":
                    cx += (col_w - cw) / 2
                elif f.cross_align == "end":
                    cx += col_w - cw
                self._place(c, (cx, cy, cw, ch))
            cy += row_h + f.row_gap
        used = cy - f.row_gap - iy
        if used > ih + 0.5 and f.sizing_v != "hug":
            self._diag("warning", f, f"сетка не помещается по высоте ({used:.0f} из {ih:.0f} px)")

    def _check_text_overflow(self, nodes: list[Node]) -> None:
        for n in self._all(nodes):
            if n.type == "text" and n.visible and n.sizing_v != "hug" and n.text:
                g = self.geo[n.id]
                need = self._measure(n, max(1.0, g[2]))[1]
                if need > g[3] + 0.5:
                    self._diag("warning", n, f"текст обрезан: нужно {math.ceil(need)} px по высоте, есть {g[3]:.0f}")
