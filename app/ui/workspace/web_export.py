"""Прототип в браузере: один HTML-файл, который открывается без программы — на компьютере и на телефоне.

Все состояния прототипа заранее обходит интерпретатор логики (нажатия, переменные, варианты, окна,
«Подождать»), каждое рисуется картинками; в файле — зоны нажатия, переходы, прокрутка, липкие элементы,
листание страницами. Из сети ничего не загружается (запрет в Content-Security-Policy), кода проекта в файле
нет — только картинки и описание переходов.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import heapq
import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene

from app.core.document import tree
from app.core.document.model import Node, Screen
from app.engines.logic.engine import Interpreter
from app.engines.logic.runtime import compose
from app.ui.workspace.canvas import ArtboardItem, asset_lookup, build_scene

MAX_STATES = 200        # больше — файл слишком тяжёлый; дальше переходы сообщают, что не вошли
PER_SCREEN = 24         # состояний одного экрана (переключатели, счётчики) — чтобы хватило места другим экранам
TARGET_W = 860          # ширина картинки экрана, px (на телефоне — чётко, файл — не огромный)
GESTURES = ("tap", "long_press", "double_tap", "swipe_left", "swipe_right", "swipe_up", "swipe_down")
_NO_PAINT = QGraphicsItem.GraphicsItemFlag.ItemDoesntPropagateOpacityToChildren


@dataclass
class WebResult:
    path: Path
    states: int
    images: int
    size: int
    cut: bool       # не все состояния вошли (MAX_STATES)


# ---------- обход состояний ----------
def _waits_key(waits) -> str:
    return json.dumps([[w.data["screen_id"], w.data["ms"], w.data["rest"]] for w in waits],
                      sort_keys=True, ensure_ascii=False)


class _Explorer:
    """Граф состояний: узел — состояние логики + отложенные «Подождать», рёбра — жесты и таймеры."""

    def __init__(self, doc, start: str | None):
        self.doc = doc
        self.interp = Interpreter(doc, start)
        self.states: list = []        # (RuntimeState, [Effect wait], шагов на этом экране)
        self.index: dict[str, int] = {}
        self.per_screen: dict[str, int] = {}
        self.queue: list[tuple[int, int]] = []   # (шагов на экране, номер): сначала новые экраны, потом мелочи
        self.cut = False
        self.add(self.interp.state, [e for e in self.interp.effects if e.kind == "wait"], 0)

    def add(self, state, waits, depth: int) -> int:
        key = state.digest() + _waits_key(waits)
        if key in self.index:
            return self.index[key]
        busy = self.per_screen.get(state.screen_id, 0)
        if len(self.states) >= MAX_STATES or (depth > 0 and busy >= PER_SCREEN):
            self.cut = True
            return -1
        self.per_screen[state.screen_id] = busy + 1
        self.index[key] = len(self.states)
        self.states.append((copy.deepcopy(state), list(waits), depth))
        heapq.heappush(self.queue, (depth, self.index[key]))
        return self.index[key]

    def step(self, i: int, run, keep_waits) -> dict | None:
        """Выполнить событие из состояния i; ребро перехода или None, если ничего не изменилось."""
        state, _, depth = self.states[i]
        it = self.interp
        it.state = copy.deepcopy(state)
        it.log, it.effects = [], []
        effects = [e for e in run(it) if e.kind != "error"]
        st = it.state
        if st.screen_id in st.history:  # вернулись на экран из истории — как в Android, хвост истории снимается
            st.history = st.history[:st.history.index(st.screen_id)]
        st.history = st.history[-8:]
        waits = [w for w in keep_waits if w.data["screen_id"] == st.screen_id] + \
                [e for e in effects if e.kind == "wait"]
        scroll = next((e.data["node_id"] for e in effects if e.kind == "scroll_to"), None)
        same = st.digest() == state.digest() and _waits_key(waits) == _waits_key(self.states[i][1])
        if same and scroll is None:
            return None
        nav = next((e for e in effects if e.kind in ("navigate", "back")), None)
        if nav is not None:
            tr, ms, ease = nav.data["transition"], nav.data["duration"], nav.data["easing"]
        elif any(e.kind in ("overlay_open", "overlay_close") for e in effects):
            tr, ms, ease = "fade", 200, "ease_out"
        else:
            tr, ms, ease = ("fade", 120, "ease_out") if not same else ("none", 0, "linear")
        depth = 0 if st.screen_id != state.screen_id else depth + 1
        edge = {"to": i if same else self.add(st, waits, depth), "tr": tr, "ms": ms, "ease": ease}
        if scroll is not None:
            edge["scroll"] = scroll
        return edge


def _handlers(doc, screen: Screen) -> dict[str, list[str]]:
    """Видимые элементы, на которые можно нажать (или провести), → жесты."""
    by: dict[str, set] = {}
    for it in doc.interactions:
        if it.screen_id == screen.id and it.trigger in GESTURES and it.node_id:
            by.setdefault(it.node_id, set()).add(it.trigger)
    out: dict[str, list[str]] = {}

    def rec(nodes):
        for n in nodes:
            if not n.visible:
                continue
            g = set(by.get(n.id, ()))
            if n.id.startswith("scrim:"):
                g.add("tap")
            if n.is_instance and not n.ref:
                defn = doc.component(n.component_id)
                if defn is not None and len(defn.behavior.get("toggle", [])) == 2:
                    g.add("tap")
            if g:
                out[n.id] = [t for t in GESTURES if t in g]
            if n.is_container:
                rec(n.children)
    rec(screen.nodes)
    return out


# ---------- раскладка слоёв ----------
def _extent(n: Node) -> tuple[float, float]:
    leaves = [c for c, _, _ in tree.walk(n.children) if not c.is_group]
    w = max((c.x + c.w for c in leaves), default=n.x) - n.x + n.pad_r
    h = max((c.y + c.h for c in leaves), default=n.y) - n.y + n.pad_b
    return max(n.w, w), max(n.h, h)


def _scrollable(n: Node) -> bool:
    if not (n.is_frame and n.scroll != "none" and n.children):
        return False
    cw, ch = _extent(n)
    return ch > n.h + 0.5 if n.scroll == "vertical" else cw > n.w + 0.5


def _dots_of(screen: Screen, frame: Node) -> Node | None:
    """Точки страниц — следующий за листаемым контейнером элемент или внутри него (как в прототипе)."""
    try:
        _, parent, idx = tree.find(screen, frame.id)
    except Exception:
        return None
    sib = parent.children if parent is not None else screen.nodes
    nxt = sib[idx + 1] if idx + 1 < len(sib) else None
    d = next((d for d, _, _ in tree.walk([nxt]) if d.role == "m3.page_dots"), None) if nxt else None
    return d if d is not None and d.children else None


def _copy(nodes, cleared: set, hidden: set) -> list[Node]:
    out = [Node.from_dict(n.to_dict()) for n in nodes]
    for n, _, _ in tree.walk(out):
        if n.id in cleared:
            n.children = []
        if n.id in hidden:
            n.visible = False
    return out


def _png(img: QImage, opaque: bool) -> bytes:
    def enc(fmt: str, q: int = -1) -> bytes:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, fmt, q)
        return bytes(ba)
    png = enc("PNG")
    if opaque:  # непрозрачный фон: JPEG часто втрое легче
        jpg = enc("JPG", 90)
        if jpg and len(jpg) < len(png) * 0.8:
            return jpg
    return png


class _Builder:
    def __init__(self, doc, color: str):
        self.doc, self.color = doc, color
        self.assets = asset_lookup(doc)
        self.images: list[str] = []
        self.by_hash: dict[str, int] = {}

    def image(self, data: bytes) -> int:
        h = hashlib.sha1(data).hexdigest()
        if h not in self.by_hash:
            mime = "image/jpeg" if data[:2] == b"\xff\xd8" else "image/png"
            self.by_hash[h] = len(self.images)
            self.images.append(f"data:{mime};base64," + base64.b64encode(data).decode("ascii"))
        return self.by_hash[h]

    def segments(self, screen: Screen, nodes: list[Node], rect, scale: float, root: bool,
                 cuts: list[str]) -> tuple[list[int], dict[str, int]]:
        """Картинки слоя, разрезанного по вложенным прокручиваемым контейнерам (то, что выше них, — отдельно),
        и номер куска для каждого элемента."""
        s = copy.copy(screen)
        s.nodes = nodes
        scene = QGraphicsScene()
        items = build_scene(scene, s, self.color, self.assets)
        order: list[str] = []

        def rec(ns, vis):
            for n in ns:
                v = vis and n.visible
                if n.is_group:
                    rec(n.children, v)
                elif v:
                    order.append(n.id)
                    if n.is_frame:
                        rec(n.children, v)
        rec(nodes, True)
        seg_of, seg = {}, 0
        for nid in order:
            seg_of[nid] = seg
            if nid in cuts:
                seg += 1
        art = next((it for it in scene.items() if isinstance(it, ArtboardItem)), None)
        x, y, w, h = rect
        size = (max(1, round(w * scale)), max(1, round(h * scale)))
        out = []
        for k in range(seg + 1):
            if art is not None:
                art.setVisible(root and k == 0)
            for nid, it in items.items():
                mine = seg_of.get(nid) == k
                it.setFlag(_NO_PAINT, not mine)
                it.setOpacity(1.0 if mine else 0.0)
            img = QImage(*size, QImage.Format.Format_ARGB32)
            opaque = root and k == 0
            img.fill(QColor(self.color) if opaque else QColor(0, 0, 0, 0))
            p = QPainter(img)
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                             | QPainter.RenderHint.SmoothPixmapTransform)
            scene.render(p, QRectF(0, 0, *size), QRectF(x, y, w, h))
            p.end()
            out.append(self.image(_png(img, opaque)))
        return out, seg_of


def _layout(screen: Screen):
    """Слои экрана: корень, прокручиваемые контейнеры (вложенные тоже), липкие элементы.
    owner: элемент → ключ слоя ("" — корень, id контейнера, "sticky:<id>")."""
    owner: dict[str, str] = {}
    scrollers: dict[str, Node] = {}
    stickies: dict[str, list[Node]] = {}

    def rec(nodes, key, in_sticky):
        for n in nodes:
            if not n.visible:
                continue
            owner[n.id] = key
            if not n.is_container:
                continue
            if not in_sticky and _scrollable(n):
                scrollers[n.id] = n
                stickies[n.id] = [c for c in n.children if c.sticky and c.visible and n.scroll == "vertical"]
                for c in n.children:
                    if c in stickies[n.id]:
                        rec([c], "sticky:" + c.id, True)
                    else:
                        rec([c], n.id, False)
            else:
                rec(n.children, key, in_sticky)
    rec(screen.nodes, "", False)
    return owner, scrollers, stickies


def _hotspots(nodes_in: list[Node], ox: float, oy: float, edges: dict) -> list[dict]:
    out = []
    for n in nodes_in:
        ev = edges.get(n.id)
        if ev:
            out.append({"x": round(n.x - ox, 2), "y": round(n.y - oy, 2), "w": round(n.w, 2),
                        "h": round(n.h, 2), "e": ev})
    return out


def _css(color: str) -> str:
    c = QColor(color or "#00000000")
    return f"rgba({c.red()},{c.green()},{c.blue()},{round(c.alphaF(), 3)})"


def _state_view(b: _Builder, screen: Screen, edges: dict, scale: float) -> dict:
    owner, scrollers, stickies = _layout(screen)
    nodes_by = tree.node_map(screen)
    dots: dict[str, tuple[Node, Node]] = {}        # id точек → (контейнер, точки)
    for f in scrollers.values():
        if f.paging and f.scroll == "horizontal":
            d = _dots_of(screen, f)
            if d is not None:
                dots[d.id] = (f, d)
    hidden = set(dots)
    walk_order = [n for n, _, _ in tree.walk(screen.nodes) if n.id in owner]

    def members(key):
        return [n for n in walk_order if owner[n.id] == key]

    def dots_specs(key, ox, oy):
        out = []
        for did, (f, d) in dots.items():
            if owner.get(did) != key:
                continue
            active = max(d.children, key=lambda c: c.w)
            other = min(d.children, key=lambda c: c.w)
            base = nodes_by[f.id]
            out.append({"f": f.id, "x": round(d.children[0].x - ox, 2), "y": round(active.y - oy, 2),
                        "h": round(active.h, 2), "gap": d.gap, "aw": active.w, "ow": other.w,
                        "ac": _css(active.fill), "oc": _css(other.fill), "n": len(d.children),
                        "pages": [round(max(0.0, c.x - base.x - base.pad_l), 2) for c in base.children]})
        return out

    def layer(key: str, nodes: list[Node], rect, ox, oy, root: bool) -> dict:
        inner = [f for f in scrollers.values() if owner.get(f.id) == key]
        cuts = [f.id for f in inner]
        imgs, seg_of = b.segments(screen, _copy(nodes, set(scrollers), hidden), rect, scale, root, cuts)
        mem = members(key)
        hs = _hotspots(mem, ox, oy, edges)
        hs_seg = {}
        for h, n in zip(hs, [n for n in mem if edges.get(n.id)]):
            hs_seg.setdefault(seg_of.get(n.id, 0), []).append(h)
        parts = []
        for k, img in enumerate(imgs):
            parts.append({"img": img, "hs": hs_seg.get(k, [])})
            if k < len(inner):
                parts[-1]["kid"] = scroller(inner[k], ox, oy)
        return {"parts": parts, "dots": dots_specs(key, ox, oy)}

    def scroller(f: Node, px, py) -> dict:
        cw, ch = _extent(f)
        kids = [c for c in f.children if c.id not in {s.id for s in stickies[f.id]}]
        lay = layer(f.id, kids, (f.x, f.y, cw, ch), f.x, f.y, False)
        lay.update({"id": f.id, "ax": "v" if f.scroll == "vertical" else "h", "x": round(f.x - px, 2),
                    "y": round(f.y - py, 2), "w": round(f.w, 2), "h": round(f.h, 2), "r": round(f.radius, 2),
                    "cw": round(cw, 2), "ch": round(ch, 2)})
        if f.paging and f.scroll == "horizontal":
            lay["snap"] = [round(max(0.0, c.x - f.x - f.pad_l), 2) for c in f.children]
        st = []
        for c in stickies[f.id]:
            key = "sticky:" + c.id
            imgs, _ = b.segments(screen, _copy([c], set(), hidden), (c.x, c.y, c.w, c.h), scale, False, [])
            st.append({"img": imgs[0], "x": round(c.x - f.x, 2), "y": round(c.y - f.y, 2), "w": round(c.w, 2),
                       "h": round(c.h, 2), "hs": _hotspots(members(key), c.x, c.y, edges)})
        lay["sticky"] = st
        return lay

    root_nodes = screen.nodes
    view = layer("", root_nodes, (0, 0, screen.width, screen.height), 0, 0, True)
    view.update({"w": screen.width, "h": screen.height})
    return view


def _scroll_target(screen: Screen, node_id: str) -> tuple[str, float] | None:
    """«Прокрутить к элементу»: контейнер и смещение (как в прототипе — элемент у верхнего / левого края)."""
    target = tree.node_map(screen).get(node_id)
    if target is None:
        return None
    try:
        chain = list(reversed(tree.ancestors(screen, node_id)))
    except Exception:
        return None
    f = next((a for a in chain if a.is_frame and a.scroll != "none"), None)
    if f is None:
        return None
    off = target.y - f.y - f.pad_t if f.scroll == "vertical" else target.x - f.x - f.pad_l
    return f.id, round(max(0.0, off), 2)


def build_html(doc, engine, color: str, start_screen_id: str | None = None, progress=None) -> tuple[str, dict]:
    """HTML прототипа и сводка {states, images, cut}. progress(i, n) — для полосы ожидания."""
    ex = _Explorer(doc, start_screen_id)
    composed: dict[int, Screen | None] = {}
    raw_edges: dict[int, dict] = {}    # номер состояния → {элемент: {жест: ребро}}, "_timer", "_back"
    while ex.queue:
        _, i = heapq.heappop(ex.queue)
        state, waits, _ = ex.states[i]
        scr = compose(doc, state, engine, None)
        composed[i] = scr
        per: dict = {}
        if scr is not None:
            for nid, gestures in _handlers(doc, scr).items():
                for g in gestures:
                    e = ex.step(i, lambda it, g=g, nid=nid: it.dispatch(g, nid), waits)
                    if e is not None:
                        per.setdefault(nid, {})[g] = e
            if waits:
                first, rest = waits[0], waits[1:]
                e = ex.step(i, lambda it, w=first: it.resume(w), rest)
                if e is not None:
                    per["_timer"] = dict(e, wait=first.data["ms"])
            e = ex.step(i, lambda it: it.dispatch("system_back", ""), waits)
            if e is not None:
                per["_back"] = e
        raw_edges[i] = per
        if progress is not None:
            progress(len(raw_edges), len(ex.states))
    b = _Builder(doc, color)
    states = []
    for i in range(len(ex.states)):
        scr, per = composed[i], raw_edges[i]
        for ev in [*per.values()]:
            for e in (ev.values() if "to" not in ev else [ev]):
                nid = e.pop("scroll", None)
                if nid is not None and e["to"] >= 0 and composed[e["to"]] is not None:
                    t = _scroll_target(composed[e["to"]], nid)
                    if t is not None:
                        e["sf"], e["so"] = t
        if scr is None:
            states.append(None)
            continue
        scale = min(2.5, TARGET_W / max(1.0, scr.width))
        edges = {k: v for k, v in per.items() if not k.startswith("_")}
        view = _state_view(b, scr, edges, scale)
        view.update({"s": scr.id, "name": scr.name, "bg": color, "t": per.get("_timer"), "b": per.get("_back")})
        states.append(view)
    data = {"title": doc.meta.title, "start": 0, "images": b.images, "states": states, "cut": ex.cut}
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = (doc.meta.title or "Прототип").replace("&", "&amp;").replace("<", "&lt;")
    html = _TEMPLATE.replace("__TITLE__", title).replace("__DATA__", js)
    return html, {"states": len(states), "images": len(b.images), "cut": ex.cut}


def save_html(doc, engine, color: str, path: str | Path, start_screen_id: str | None = None,
              progress=None) -> WebResult:
    html, info = build_html(doc, engine, color, start_screen_id, progress)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = html.encode("utf-8")
    path.write_bytes(data)
    return WebResult(path, info["states"], info["images"], len(data), info["cut"])


_TEMPLATE = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<meta name="generator" content="App Design Studio">
<title>__TITLE__</title>
<style>
:root { --bg:#1b1b1f; --bar:#26262b; --ink:#ececf1; --mute:#a0a0aa; --accent:#8ab4f8; }
@media (prefers-color-scheme: light) { :root { --bg:#ececf0; --bar:#ffffff; --ink:#1b1b1f; --mute:#5f6068; --accent:#1a73e8; } }
* { box-sizing:border-box; }
html, body { margin:0; height:100%; background:var(--bg); color:var(--ink);
  font:14px/1.3 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; overflow:hidden; }
#bar { position:fixed; left:0; right:0; top:0; height:48px; display:flex; align-items:center; gap:8px;
  padding:0 12px; background:var(--bar); box-shadow:0 1px 0 rgba(127,127,127,.2); z-index:5; }
#bar .t { font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
#bar .s { color:var(--mute); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1; }
#bar button { font:inherit; color:var(--ink); background:transparent; border:1px solid rgba(127,127,127,.35);
  border-radius:999px; padding:6px 12px; cursor:pointer; white-space:nowrap; }
#bar button:hover { border-color:var(--accent); }
#bar button[hidden] { display:none; }
#bar button.on { background:var(--accent); color:#fff; border-color:var(--accent); }
#stage { position:fixed; left:0; right:0; top:48px; bottom:0; display:flex; align-items:center; justify-content:center; }
#dev { position:relative; overflow:hidden; border-radius:28px; box-shadow:0 10px 40px rgba(0,0,0,.35);
  transform-origin:center center; touch-action:none; user-select:none; -webkit-user-select:none; flex:none; }
.scr { position:absolute; left:0; top:0; overflow:hidden; }
.scr img, .sticky img { position:absolute; left:0; top:0; pointer-events:none; -webkit-user-drag:none; }
.scroll { position:absolute; overflow:hidden; scrollbar-width:none; overscroll-behavior:contain; }
.scroll::-webkit-scrollbar { display:none; }
.sv { overflow-y:auto; touch-action:pan-y; }
.sh { overflow-x:auto; touch-action:pan-x; }
.sh.snap { scroll-snap-type:x mandatory; }
.snapm { position:absolute; top:0; height:1px; scroll-snap-align:start; pointer-events:none; }
.content { position:relative; }
.sticky { position:absolute; z-index:2; will-change:transform; }
.hs { position:absolute; cursor:pointer; border-radius:calc(var(--u, 1px) * 8); transition:background .15s; }
.hs.down { background:rgba(127,127,127,.18); }
.hints .hs, .flash .hs { background:rgba(66,133,244,.3);
  box-shadow:inset 0 0 0 calc(var(--u, 1px) * 2) rgba(66,133,244,.9); }
.dots { position:absolute; display:flex; align-items:center; pointer-events:none; }
.dots i { display:block; border-radius:999px; transition:width .2s, background .2s; }
#toast { position:fixed; left:50%; bottom:24px; transform:translateX(-50%); background:#323236; color:#fff;
  padding:10px 16px; border-radius:10px; opacity:0; transition:opacity .2s; pointer-events:none; z-index:9;
  max-width:90vw; text-align:center; }
#toast.on { opacity:1; }
@media (max-width:600px) { #bar .s { display:none; } #dev { border-radius:0; box-shadow:none; } }
</style>
</head>
<body>
<div id="bar"><span class="t" id="title"></span><span class="s" id="sname"></span>
<button id="back" hidden title="Как системная кнопка «Назад» (Esc)">← Назад</button>
<button id="hints" title="Показать, куда можно нажать">Зоны</button>
<button id="restart" title="С начала (R)">↺ Сначала</button></div>
<div id="stage"><div id="dev"></div></div>
<div id="toast"></div>
<script type="application/json" id="data">__DATA__</script>
<script>
(function () {
"use strict";
var D = JSON.parse(document.getElementById("data").textContent);
var dev = document.getElementById("dev"), stage = document.getElementById("stage");
var cur = -1, curEl = null, timer = 0, scale = 1;
var EASE = { linear:"linear", ease_in:"cubic-bezier(.4,0,1,1)", ease_out:"cubic-bezier(0,0,.2,1)",
  ease_in_out:"cubic-bezier(.4,0,.2,1)", step:"steps(1,end)", cubic:"cubic-bezier(.2,0,0,1)" };
document.getElementById("title").textContent = D.title || "Прототип";
document.title = D.title || "Прототип";

function px(v) { return v + "px"; }
function box(el, x, y, w, h) { el.style.left = px(x); el.style.top = px(y); el.style.width = px(w); el.style.height = px(h); }
function img(i, w, h) { var im = new Image(); im.src = D.images[i]; im.alt = ""; im.draggable = false;
  im.style.width = px(w); im.style.height = px(h); return im; }
function hotspots(parent, list) {
  list.forEach(function (h) { var d = document.createElement("div"); d.className = "hs"; box(d, h.x, h.y, h.w, h.h);
    d._e = h.e; parent.appendChild(d); });
}
function layer(L, parent, w, h, dotsOut) {
  L.parts.forEach(function (p) {
    parent.appendChild(img(p.img, w, h));
    hotspots(parent, p.hs);
    if (p.kid) parent.appendChild(scroller(p.kid, dotsOut));
  });
  L.dots.forEach(function (d) {
    var el = document.createElement("div"); el.className = "dots"; el.style.left = px(d.x); el.style.top = px(d.y);
    el.style.height = px(d.h); el.style.gap = px(d.gap);
    for (var k = 0; k < d.n; k++) { var i = document.createElement("i"); i.style.height = px(d.h); el.appendChild(i); }
    parent.appendChild(el); dotsOut.push([d, el]);
  });
}
function scroller(S, dotsOut) {
  var el = document.createElement("div");
  el.className = "scroll " + (S.ax === "v" ? "sv" : "sh") + (S.snap ? " snap" : "");
  box(el, S.x, S.y, S.w, S.h); el.style.borderRadius = px(S.r); el.dataset.f = S.id;
  var c = document.createElement("div"); c.className = "content"; c.style.width = px(S.cw); c.style.height = px(S.ch);
  el.appendChild(c);
  layer(S, c, S.cw, S.ch, dotsOut);
  (S.snap || []).forEach(function (o) { var m = document.createElement("div"); m.className = "snapm";
    m.style.left = px(o); m.style.width = px(S.w); c.appendChild(m); });
  el._snap = S.snap || null;
  var st = S.sticky.map(function (s) {
    var d = document.createElement("div"); d.className = "sticky"; box(d, s.x, s.y, s.w, s.h);
    d.appendChild(img(s.img, s.w, s.h)); hotspots(d, s.hs); c.appendChild(d); return [d, s.y];
  });
  if (st.length) el.addEventListener("scroll", function () {
    st.forEach(function (p) { p[0].style.transform = "translateY(" + Math.max(0, el.scrollTop - p[1]) + "px)"; });
  }, { passive:true });
  return el;
}
function syncDots(d, el, sc) {
  var off = sc.scrollLeft, best = 0;
  d.pages.forEach(function (p, i) { if (Math.abs(p - off) < Math.abs(d.pages[best] - off)) best = i; });
  for (var k = 0; k < el.children.length; k++) { var on = k === best, i = el.children[k];
    i.style.width = px(on ? d.aw : d.ow); i.style.background = on ? d.ac : d.oc; }
}
function build(i) {
  var S = D.states[i], el = document.createElement("div"); el.className = "scr";
  el.style.width = px(S.w); el.style.height = px(S.h); el.style.background = S.bg;
  var dots = [];
  layer(S, el, S.w, S.h, dots);
  dots.forEach(function (p) {
    var sc = el.querySelector('[data-f="' + p[0].f + '"]'); if (!sc) return;
    var f = function () { syncDots(p[0], p[1], sc); }; sc.addEventListener("scroll", f, { passive:true }); f();
  });
  return el;
}
function fit() {
  if (cur < 0) return;
  var S = D.states[cur], aw = stage.clientWidth, ah = stage.clientHeight, small = aw <= 600;
  var m = small ? 0 : 24;
  scale = Math.min((aw - m * 2) / S.w, (ah - m * 2) / S.h);
  dev.style.width = px(S.w); dev.style.height = px(S.h);
  dev.style.transform = "scale(" + scale + ")";
  dev.style.setProperty("--u", (1 / scale) + "px");  // 1 экранный пиксель в единицах макета
  dev.style.borderRadius = small ? "0" : px(28 / scale);
}
function toast(t) { var el = document.getElementById("toast"); el.textContent = t; el.classList.add("on");
  clearTimeout(el._t); el._t = setTimeout(function () { el.classList.remove("on"); }, 2200); }
function slide(kind) {
  return { slide_left:["translateX(100%)", "translateX(-30%)"], slide_right:["translateX(-100%)", "translateX(30%)"],
    slide_up:["translateY(100%)", "translateY(-30%)"], slide_down:["translateY(-100%)", "translateY(30%)"] }[kind];
}
function go(e) {
  if (!e) return;
  if (e.to < 0 || !D.states[e.to]) { toast("Дальше этот прототип в файл не вошёл — слишком много состояний"); return; }
  clearTimeout(timer);
  var prev = cur >= 0 ? D.states[cur] : null, next = D.states[e.to], keep = {};
  if (curEl && prev && prev.s === next.s) curEl.querySelectorAll(".scroll").forEach(function (s) {
    keep[s.dataset.f] = [s.scrollLeft, s.scrollTop]; });
  var el = build(e.to), old = curEl;
  dev.appendChild(el);
  el.querySelectorAll(".scroll").forEach(function (s) { var k = keep[s.dataset.f];
    if (k) { s.scrollLeft = k[0]; s.scrollTop = k[1]; } });
  cur = e.to; curEl = el; fit();
  var ms = e.ms || 0, ease = EASE[e.ease] || "ease";
  if (old && ms > 0 && e.tr !== "none" && el.animate) {
    var sl = slide(e.tr);
    if (sl) {
      el.animate([{ transform:sl[0] }, { transform:"none" }], { duration:ms, easing:ease });
      old.animate([{ transform:"none" }, { transform:sl[1] }], { duration:ms, easing:ease, fill:"forwards" })
        .onfinish = function () { old.remove(); };
    } else {
      el.animate([{ opacity:0 }, { opacity:1 }], { duration:ms, easing:ease }).onfinish = function () { old.remove(); };
    }
  } else if (old) old.remove();
  document.getElementById("sname").textContent = next.name;
  document.getElementById("back").hidden = !next.b;
  if (e.sf) { var sc = el.querySelector('[data-f="' + e.sf + '"]');
    if (sc) setTimeout(function () { sc.scrollTo(Object.assign({ behavior:"smooth" },
      sc.classList.contains("sv") ? { top:e.so } : { left:e.so })); }, Math.min(ms, 300)); }
  if (next.t) timer = setTimeout(function () { go(next.t); }, next.t.wait);
}
function restart() { go({ to:D.start, tr:"fade", ms:200, ease:"ease_out" }); }

// ---------- жесты: нажатие, долгое, двойное, свайп; мышью — ещё и перетаскивание прокрутки ----------
var P = null, lastTap = null, dblTimer = 0;
function fire(hs, g) { if (hs && hs._e && hs._e[g]) { go(hs._e[g]); return true; } return false; }
dev.addEventListener("pointerdown", function (ev) {
  var hs = ev.target.closest(".hs"), sc = ev.target.closest(".scroll");
  P = { x:ev.clientX, y:ev.clientY, t:Date.now(), hs:hs, sc:sc, moved:false, long:false, id:ev.pointerId,
        mouse:ev.pointerType === "mouse", sl:sc ? sc.scrollLeft : 0, st:sc ? sc.scrollTop : 0 };
  if (hs) { hs.classList.add("down");
    if (hs._e.long_press) P.lt = setTimeout(function () { P.long = true; hs.classList.remove("down"); fire(hs, "long_press"); }, 500); }
  if (P.mouse) try { dev.setPointerCapture(ev.pointerId); } catch (e) {}
});
dev.addEventListener("pointermove", function (ev) {
  if (!P || ev.pointerId !== P.id) return;
  var dx = ev.clientX - P.x, dy = ev.clientY - P.y;
  if (!P.moved && Math.hypot(dx, dy) > 8) { P.moved = true; clearTimeout(P.lt); if (P.hs) P.hs.classList.remove("down"); }
  if (P.moved && P.mouse && P.sc) {
    if (P.sc.classList.contains("sv")) P.sc.scrollTop = P.st - dy / scale;
    else { P.sc.style.scrollSnapType = "none"; P.sc.scrollLeft = P.sl - dx / scale; }
  }
});
function end(ev, cancel) {
  if (!P || ev.pointerId !== P.id) return;
  var p = P; P = null; clearTimeout(p.lt);
  if (p.hs) p.hs.classList.remove("down");
  if (p.mouse && p.sc && p.sc._snap && p.moved) {
    var off = p.sc.scrollLeft, v = (ev.clientX - p.x) / scale, best = p.sc._snap[0];
    var target = off - v * 0.3;
    p.sc._snap.forEach(function (o) { if (Math.abs(o - target) < Math.abs(best - target)) best = o; });
    p.sc.scrollTo({ left:best, behavior:"smooth" });
    setTimeout(function () { p.sc.style.scrollSnapType = ""; }, 400);
  }
  if (cancel || p.long) return;
  var dx = ev.clientX - p.x, dy = ev.clientY - p.y, dt = Date.now() - p.t;
  if (p.moved) {
    if (dt < 600 && Math.max(Math.abs(dx), Math.abs(dy)) > 40) {
      var g = Math.abs(dx) > Math.abs(dy) ? (dx < 0 ? "swipe_left" : "swipe_right") : (dy < 0 ? "swipe_up" : "swipe_down");
      var all = document.elementsFromPoint(p.x, p.y), el = null;  // самая верхняя зона с этим жестом
      for (var i = 0; i < all.length && !el; i++) if (all[i]._e && all[i]._e[g]) el = all[i];
      fire(el, g);
    }
    return;
  }
  var hs = p.hs;
  if (!hs) { dev.classList.add("flash"); setTimeout(function () { dev.classList.remove("flash"); }, 450); return; }
  if (hs._e.double_tap) {
    if (lastTap && lastTap.hs === hs && Date.now() - lastTap.t < 300) { clearTimeout(dblTimer); lastTap = null; fire(hs, "double_tap"); return; }
    lastTap = { hs:hs, t:Date.now() };
    if (hs._e.tap) dblTimer = setTimeout(function () { lastTap = null; fire(hs, "tap"); }, 260);
    return;
  }
  fire(hs, "tap");
}
dev.addEventListener("pointerup", function (ev) { end(ev, false); });
dev.addEventListener("pointercancel", function (ev) { end(ev, true); });
dev.addEventListener("wheel", function (ev) {
  var sc = ev.target.closest(".sh");
  if (sc && Math.abs(ev.deltaY) > Math.abs(ev.deltaX) && !ev.target.closest(".sv")) { sc.scrollLeft += ev.deltaY; ev.preventDefault(); }
}, { passive:false });
document.getElementById("restart").onclick = restart;
document.getElementById("back").onclick = function () { if (cur >= 0) go(D.states[cur].b); };
document.getElementById("hints").onclick = function () { this.classList.toggle("on"); dev.classList.toggle("hints"); };
document.addEventListener("keydown", function (ev) {
  if (ev.key === "Escape" || ev.key === "Backspace") { if (cur >= 0) go(D.states[cur].b); }
  else if (ev.key === "r" || ev.key === "R" || ev.key === "к" || ev.key === "К") restart();
});
window.addEventListener("resize", fit);
go({ to:D.start, tr:"none", ms:0 });
if (D.cut) toast("Состояний много — в файл вошли первые " + D.states.length);
})();
</script>
</body>
</html>
"""
