"""Контроллер рабочей области: выделение, инструменты, привязки и операции над документом через команды."""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import QObject, Signal

from app.core.commands import (
    AddNodes, AddScreen, Batch, Command, DeleteNodes, Group, MoveToIndex, RemoveScreen, Reorder, SetMeta, SetProps,
    SetScreenProps, Ungroup, UndoStack,
)
from app.core.document import tree
from app.core.document.model import Guide, ModelError, Node, ProjectDocument, Screen, new_id
from app.core.document.tree import Rect
from app.core.commands import DocPatch
from app.core.document.model import OVERRIDABLE, ROOT_REF, Asset, ColorToken, ComponentDef, TextStyle
from app.engines.components import engine as comp_engine
from app.engines.components.checks import resource_diagnostics
from app.engines.layout import Diagnostic, LayoutEngine
from app.libraries import components
from app.ui.fonts import REGISTRY
from app.ui.workspace.text_measure import QtTextMeasurer

log = logging.getLogger(__name__)

TOOL_SELECT, TOOL_HAND, TOOL_RECT, TOOL_ELLIPSE, TOOL_TEXT, TOOL_FRAME, TOOL_PEN = (
    "select", "hand", "rect", "ellipse", "text", "frame", "pen")
CLIPBOARD_MIME = "application/x-ads-nodes"
TYPE_NAMES = {"rect": "Прямоугольник", "ellipse": "Эллипс", "text": "Текст", "group": "Группа", "frame": "Контейнер",
              "vector": "Фигура", "image": "Изображение", "instance": "Копия компонента"}
from app.core.document.model import ARTBOARD_COLORS  # noqa: E402 — общий с проверкой проекта


class Editor(QObject):
    document_changed = Signal()   # структура или свойства документа
    selection_changed = Signal()
    screen_changed = Signal()
    view_changed = Signal()       # сетка, привязки, инструмент
    preview_changed = Signal()    # временная геометрия при перетаскивании
    message = Signal(str)         # сообщение пользователю (строка состояния)
    open_component = Signal(str)  # двойной клик по экземпляру в режиме изоляции
    comment_clicked = Signal(str)  # щелчок по значку комментария на холсте

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.doc: ProjectDocument | None = None
        self.stack: UndoStack | None = None
        self.screen_id: str | None = None
        self.selection: list[str] = []
        self.entered_group: str | None = None
        self.tool = TOOL_SELECT
        self.grid_visible = True
        self.grid_size = 8
        self.snap_enabled = True
        self.guides_visible = True
        self._clipboard: list[dict] = []
        self._paste_serial = 0
        self.engine = LayoutEngine(QtTextMeasurer())
        self.diagnostics: list[Diagnostic] = []
        self._preview_base: dict[str, Rect] | None = None
        self.isolate_instances = False  # Component Builder: двойной клик по экземпляру открывает его мастер

    # ---------- документ ----------
    def set_document(self, doc: ProjectDocument | None) -> None:
        self.doc = doc
        self.stack = UndoStack(doc) if doc else None
        if self.stack is not None:
            self.stack.listeners.append(self._after_stack_change)
        self.screen_id = doc.screens[0].id if doc and doc.screens else None
        self.selection, self.entered_group = [], None
        self.refresh_diagnostics()
        self.screen_changed.emit()
        self.document_changed.emit()
        self.selection_changed.emit()

    def screen(self) -> Screen | None:
        if not self.doc or not self.screen_id:
            return None
        try:
            return self.doc.screen(self.screen_id)
        except ModelError:
            return None

    def execute(self, cmd: Command) -> bool:
        """Выполняет команду, затем раскладку; обе попадают в историю одной записью."""
        if self.stack is None:
            return False
        before = {s.id: (tree.geometry(s), (s.width, s.height)) for s in self.doc.screens}
        try:
            cmd.redo(self.doc)
        except ModelError as exc:
            log.warning("Команда «%s» отклонена: %s", cmd.label, exc)
            self.message.emit(f"{cmd.label}: {exc}")
            return False
        parts = [cmd]
        for s in self.doc.screens:
            geo, size = before.get(s.id, (None, None))
            changes, diags = self.engine.layout_screen(s, geo, size)
            if s.id == self.screen_id:
                self.diagnostics = diags
            if changes:
                layout_cmd = SetProps(s.id, changes, "Раскладка")
                layout_cmd.redo(self.doc)
                parts.append(layout_cmd)
        self.stack.push_done(Batch(parts, cmd.label) if len(parts) > 1 else cmd)
        return True

    def refresh_diagnostics(self) -> None:
        s = self.screen()
        if s is None:
            self.diagnostics = []
            return
        _, layout_diags = self.engine.layout_screen(s)  # проверочный прогон: документ не меняется
        from app.engines.animation.engine import validate as validate_animations
        from app.engines.logic.engine import validate as validate_logic
        self.diagnostics = layout_diags + resource_diagnostics(self.doc, s, REGISTRY.available,
                                                               REGISTRY.missing_chars)
        from app.engines.preview.scenarios import validate as validate_scenarios
        self.diagnostics += validate_animations(self.doc) + validate_logic(self.doc) + validate_scenarios(self.doc)

    def undo(self) -> None:
        if self.stack is not None:
            self.stack.undo()

    def redo(self) -> None:
        if self.stack is not None:
            self.stack.redo()

    def _after_stack_change(self) -> None:
        if self.doc and (not self.screen_id or all(s.id != self.screen_id for s in self.doc.screens)):
            self.screen_id = self.doc.screens[0].id if self.doc.screens else None
            self.screen_changed.emit()
        self.refresh_diagnostics()
        s = self.screen()
        if s is not None:
            nodes = tree.node_map(s)
            self.selection = [i for i in self.selection if i in nodes]
            if self.entered_group not in nodes:
                self.entered_group = None
        self.document_changed.emit()
        self.selection_changed.emit()

    def set_screen(self, screen_id: str) -> None:
        if screen_id != self.screen_id:
            self.screen_id = screen_id
            self.selection, self.entered_group = [], None
            self.refresh_diagnostics()
            self.screen_changed.emit()
            self.selection_changed.emit()

    def artboard_color(self) -> str:
        theme = self.doc.meta.appearance.theme if self.doc else "amoled"
        return ARTBOARD_COLORS.get(theme, "#000000")

    # ---------- выделение ----------
    def select(self, ids: list[str], entered_group: str | None | bool = False) -> None:
        if entered_group is not False:
            self.entered_group = entered_group
        seen = []
        for i in ids:
            if i not in seen:
                seen.append(i)
        if seen != self.selection:
            self.selection = seen
            self.selection_changed.emit()

    def select_any(self, ids: list[str]) -> None:
        """Выделение из панели слоёв: допускает вложенные узлы, входя в их группу."""
        s = self.screen()
        if not s:
            return
        pm = tree.parent_map(s)
        parents = {pm[i].id if pm.get(i) else None for i in ids if i in pm}
        if len(parents) == 1:
            self.select(ids, entered_group=next(iter(parents)))
        else:
            self.select([self.selectable_for(i) for i in ids] if ids else [], entered_group=None)

    def selected_nodes(self) -> list[Node]:
        s = self.screen()
        if not s:
            return []
        m = tree.node_map(s)
        return [m[i] for i in self.selection if i in m]

    def selected_leaves(self) -> list[Node]:
        out, seen = [], set()
        for n in self.selected_nodes():
            for leaf in tree.leaves(n):
                if leaf.id not in seen:
                    seen.add(leaf.id)
                    out.append(leaf)
        return out

    def selection_bbox(self) -> Rect | None:
        return tree.bounds_of(self.selected_nodes())

    def _effective(self, s: Screen) -> dict[str, tuple[bool, bool]]:
        """(видим, заблокирован) с учётом предков."""
        result = {}

        def rec(nodes, vis, lock):
            for n in nodes:
                v, lk = vis and n.visible, lock or n.locked
                result[n.id] = (v, lk)
                if n.is_container:
                    rec(n.children, v, lk)
        rec(s.nodes, True, False)
        return result

    def selectable_for(self, leaf_id: str) -> str:
        s = self.screen()
        chain = tree.ancestors(s, leaf_id)
        ids = [a.id for a in chain] + [leaf_id]
        if self.entered_group and self.entered_group in ids[:-1]:
            return ids[ids.index(self.entered_group) + 1]
        return ids[0]

    def hit(self, x: float, y: float, tolerance: float = 0.0) -> str | None:
        """Самый верхний видимый незаблокированный лист в точке → выделяемый узел."""
        s = self.screen()
        if not s:
            return None
        eff = self._effective(s)
        for n, _, _ in reversed(list(tree.walk(s.nodes))):
            if n.is_group:
                continue
            vis, locked = eff[n.id]
            if not vis or locked:
                continue
            t = tolerance
            if n.x - t <= x <= n.x + n.w + t and n.y - t <= y <= n.y + n.h + t:
                if n.type == "ellipse" and n.w > 0 and n.h > 0:
                    rx, ry = n.w / 2 + t, n.h / 2 + t
                    cx, cy = n.x + n.w / 2, n.y + n.h / 2
                    if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 > 1:
                        continue
                return self.selectable_for(n.id)
        return None

    def ids_in_rect(self, r: Rect) -> list[str]:
        s = self.screen()
        if not s:
            return []
        eff = self._effective(s)
        cont = s.nodes
        if self.entered_group:
            cont = tree.find(s, self.entered_group)[0].children
        x, y, w, h = r
        result = []
        for n in cont:
            vis, locked = eff[n.id]
            b = tree.bounds(n)
            if not vis or locked or b is None:
                continue
            if b[0] < x + w and b[0] + b[2] > x and b[1] < y + h and b[1] + b[3] > y:
                result.append(n.id)
        return result

    # ---------- геометрия ----------
    def translate_changes(self, nodes: list[Node], dx: float, dy: float) -> dict[str, dict]:
        """Сдвиг узлов. Двигаются только узлы с собственной геометрией (сквозь группы);
        дети фреймов следуют за ними через раскладку (привязки)."""
        changes = {}
        for n in nodes:
            for leaf in tree.geo_nodes(n):
                changes[leaf.id] = {"x": round(leaf.x + dx, 2), "y": round(leaf.y + dy, 2)}
        return changes

    @staticmethod
    def scale_changes(originals: dict[str, Rect], old: Rect, new: Rect) -> dict[str, dict]:
        ox, oy, ow, oh = old
        nx, ny, nw, nh = new
        sx = nw / ow if ow else 1.0
        sy = nh / oh if oh else 1.0
        changes = {}
        for nid, (x, y, w, h) in originals.items():
            changes[nid] = {"x": round(nx + (x - ox) * sx, 2), "y": round(ny + (y - oy) * sy, 2),
                            "w": round(max(0.0, w * sx), 2), "h": round(max(0.0, h * sy), 2)}
        return changes

    def begin_preview(self) -> None:
        s = self.screen()
        self._preview_base = tree.geometry(s) if s else None

    def _restore_preview_base(self) -> None:
        s = self.screen()
        if s is None or self._preview_base is None:
            return
        m = tree.node_map(s)
        for nid, (x, y, w, h) in self._preview_base.items():
            if nid in m:
                n = m[nid]
                n.x, n.y, n.w, n.h = x, y, w, h

    def preview(self, changes: dict[str, dict], keep: set[str] | None = None) -> None:
        """Временное изменение геометрии без команды (во время перетаскивания) с живой раскладкой.
        keep — узлы, чьё положение из changes важнее раскладки (перетаскиваемые внутри Auto Layout)."""
        s = self.screen()
        if self._preview_base is None:
            self.begin_preview()
        self._restore_preview_base()
        m = tree.node_map(s)
        for nid, props in changes.items():
            for k, v in props.items():
                setattr(m[nid], k, v)
        layout, _ = self.engine.layout_screen(s, self._preview_base)
        for nid, props in layout.items():
            if keep and nid in keep:
                continue
            for k, v in props.items():
                setattr(m[nid], k, v)
        self.preview_changed.emit()

    def commit_geometry(self, originals: dict[str, Rect], changes: dict[str, dict], label: str) -> None:
        """Возвращает исходную геометрию и применяет итог одной командой (одна запись в истории)."""
        s = self.screen()
        if self._preview_base is not None:
            self._restore_preview_base()
            self._preview_base = None
        m = tree.node_map(s)
        for nid, (x, y, w, h) in originals.items():
            n = m[nid]
            n.x, n.y, n.w, n.h = x, y, w, h
        real = {nid: props for nid, props in changes.items()
                if any(getattr(m[nid], k) != v for k, v in props.items())}
        if real:
            self.execute(SetProps(s.id, real, label))
        else:
            self.preview_changed.emit()

    def auto_layout_parent(self, node_id: str) -> Node | None:
        s = self.screen()
        anc = tree.ancestors(s, node_id) if s else []
        return anc[-1] if anc and anc[-1].auto_layout else None

    def drop_in_auto_layout(self, node_id: str, point: tuple[float, float]) -> None:
        """Перестановка ребёнка Auto Layout перетаскиванием: индекс — по положению точки на главной оси."""
        s = self.screen()
        if self._preview_base is not None:
            self._restore_preview_base()
            self._preview_base = None
        parent = self.auto_layout_parent(node_id)
        if parent is None:
            return
        siblings = [c for c in parent.children if c.id != node_id]
        axis = 0 if parent.layout == "horizontal" else 1
        index = 0
        for c in siblings:
            b = tree.bounds(c)
            if b and point[axis] > b[axis] + b[axis + 2] / 2:
                index += 1
        if parent.layout == "grid":
            index = 0
            for c in siblings:
                b = tree.bounds(c)
                if b and (point[1] > b[1] + b[3] or (point[1] >= b[1] and point[0] > b[0] + b[2] / 2)):
                    index += 1
        current = next(i for i, c in enumerate(parent.children) if c.id == node_id)
        if index != current:
            self.execute(MoveToIndex(s.id, node_id, index))
        else:
            self.preview_changed.emit()

    def snap_targets(self, exclude: set[str]) -> tuple[list[float], list[float]]:
        s = self.screen()
        xs, ys = [0.0, s.width / 2, float(s.width)], [0.0, s.height / 2, float(s.height)]
        for g in s.guides:
            (xs if g.axis == "x" else ys).append(g.pos)
        eff = self._effective(s)
        excluded_leaves = set()
        for nid in exclude:
            try:
                excluded_leaves |= {d.id for d in tree.descendants(tree.find(s, nid)[0])}
            except ModelError:
                pass
        for n, _, _ in tree.walk(s.nodes):
            if n.is_group or n.id in excluded_leaves or not eff[n.id][0]:
                continue
            xs += [n.x, n.x + n.w / 2, n.x + n.w]
            ys += [n.y, n.y + n.h / 2, n.y + n.h]
        return xs, ys

    def _snap_axis(self, values: list[float], targets: list[float], threshold: float) -> tuple[float, float | None]:
        best, line = None, None
        for v in values:
            for t in targets:
                d = t - v
                if abs(d) <= threshold and (best is None or abs(d) < abs(best)):
                    best, line = d, t
        if best is None and self.grid_size > 0:
            v = values[0]
            g = round(v / self.grid_size) * self.grid_size
            if abs(g - v) <= threshold:
                return g - v, None
        return (best or 0.0), line

    def snap_rect(self, r: Rect, edges: str, exclude: set[str], threshold: float) -> tuple[float, float, list, list]:
        """edges — какие края двигаются: строка из l,c,r (по X) и t,m,b (по Y). Возвращает сдвиги и линии."""
        if not self.snap_enabled:
            return 0.0, 0.0, [], []
        xs, ys = self.snap_targets(exclude)
        x, y, w, h = r
        vx = [v for k, v in (("l", x), ("c", x + w / 2), ("r", x + w)) if k in edges]
        vy = [v for k, v in (("t", y), ("m", y + h / 2), ("b", y + h)) if k in edges]
        dx, lx = self._snap_axis(vx, xs, threshold) if vx else (0.0, None)
        dy, ly = self._snap_axis(vy, ys, threshold) if vy else (0.0, None)
        return dx, dy, [lx] if lx is not None else [], [ly] if ly is not None else []

    # ---------- операции ----------
    def _container_id(self) -> str | None:
        return self.entered_group

    def default_node(self, node_type: str, x: float, y: float, w: float, h: float) -> Node:
        font = self.doc.meta.appearance.font_family if self.doc else "Segoe UI"
        n = Node(type=node_type, name=TYPE_NAMES[node_type], x=round(x, 2), y=round(y, 2), w=round(w, 2),
                 h=round(h, 2), font_family=font)
        if node_type == "text":
            n.fill = ""
            n.text = "Текст"
            n.text_color = "#111111" if self.artboard_color() == "#FFFFFF" else "#F2F2F2"
            n.sizing_v = "hug"  # высота по тексту; ширина задаётся рамкой
        elif node_type == "frame":
            n.fill = "#F2F2F2" if self.artboard_color() == "#FFFFFF" else "#141414"
            n.radius = 0.0
        else:
            n.radius = 0 if node_type == "ellipse" else float(self.doc.meta.appearance.corner_radius if self.doc else 0)
        return n

    def add_node(self, node_type: str, rect: Rect | None = None) -> Node | None:
        s = self.screen()
        if not s:
            return None
        if rect is None:
            w, h = (200, 40) if node_type == "text" else (120, 120)
            rect = (round((s.width - w) / 2), round((s.height - h) / 2), w, h)
        n = self.default_node(node_type, *rect)
        if self.execute(AddNodes(s.id, [n], self._container_id(), label=f"Добавить: {TYPE_NAMES[node_type]}")):
            self.select([n.id])
            return n
        return None

    def insert_symbol(self, name: str, style: str = "outlined", filled: bool = False, size_dp: float = 24,
                      at: tuple[float, float] | None = None) -> Node | None:
        """Значок Material Symbols на экран (по центру или в точку), цвет — «на поверхности» схемы проекта."""
        from app.engines.material.color import scheme
        from app.engines.preview.devices import screen_dpi
        from app.libraries import symbols
        s = self.screen()
        d = symbols.path(name, style, filled)
        if not s or not self.doc or not d:
            return None
        k = screen_dpi(s) / 160 if s.platform == "android" else 1.0
        side = round(size_dp * k, 2)
        ap = self.doc.meta.appearance
        x, y = at if at is not None else ((s.width - side) / 2, s.height * 0.35)
        node = Node(type="vector", name=symbols.russian_name(name), x=round(x, 2), y=round(y, 2), w=side, h=side,
                    path=d, vb_w=symbols.VIEWBOX, vb_h=symbols.VIEWBOX,
                    fill=scheme(ap.accent, ap.theme != "light")["onSurface"])
        if self.execute(AddNodes(s.id, [node], self._container_id(), label=f"Значок: {name}")):
            self.select([node.id])
            return node
        return None

    def replace_symbol(self, node_id: str, name: str, style: str = "outlined", filled: bool = False) -> bool:
        """Сменить рисунок значка (размер, цвет и место остаются)."""
        from app.libraries import symbols
        d = symbols.path(name, style, filled)
        if not d:
            return False
        return self.set_props({node_id: {"path": d, "vb_w": float(symbols.VIEWBOX), "vb_h": float(symbols.VIEWBOX),
                                         "name": symbols.russian_name(name)}}, f"Значок: {name}")

    # ---------- готовые анимации ----------
    def node_animations(self, node_id: str) -> list:
        if not self.doc:
            return []
        s = self.screen()
        ids = {node_id} | ({d.id for d in tree.descendants(tree.find(s, node_id)[0])} if s else set())
        return [a for a in self.doc.animations if any(t.node_id in ids for t in a.tracks)]

    def add_animation_preset(self, node_id: str, key: str, trigger: str = "open") -> bool:
        """Готовая анимация для элемента; trigger: open — при открытии экрана, tap — при нажатии на элемент,
        none — только создать (запуск — правилом «Логики»). Одна запись истории."""
        from app.core.document.behavior import Interaction
        from app.engines.animation import presets
        from app.engines.preview.devices import screen_dpi
        s = self.screen()
        if not s or not self.doc:
            return False
        node = tree.find(s, node_id)[0]
        k = screen_dpi(s) / 160 if s.platform == "android" else 1.0
        anim = presets.build(key, node, s.id, k)
        rule = None
        if trigger in ("open", "tap"):
            rule = Interaction.from_dict(Interaction(
                screen_id=s.id, node_id="" if trigger == "open" else node_id,
                trigger="screen_open" if trigger == "open" else "tap",
                actions=[{"type": "play_animation", "animation_id": anim.id}]).to_dict())

        def mutate(doc):
            from app.core.document.behavior import Animation, Interaction as I
            doc.animations.append(Animation.from_dict(anim.to_dict()))
            if rule is not None:
                doc.interactions.append(I.from_dict(rule.to_dict()))
        return self.patch(f"Анимация «{presets.preset(key).name}»", mutate)

    def remove_node_animations(self, node_id: str) -> bool:
        """Убрать анимации элемента и правила, которые их запускают."""
        ids = {a.id for a in self.node_animations(node_id)}
        if not ids:
            return False

        def mutate(doc):
            doc.animations = [a for a in doc.animations if a.id not in ids]
            for it in list(doc.interactions):
                it.actions = [a for a in it.actions if not (a["type"] == "play_animation"
                                                            and a.get("animation_id") in ids)]
            doc.interactions = [it for it in doc.interactions if it.actions]
        return self.patch("Убрать анимации элемента", mutate)

    def apply_appearance(self, new) -> bool:
        """Тема и стиль проекта: перекраска всех экранов и компонентов по ролям цвета, шрифт, скругления.
        Одна запись истории."""
        from app.engines.material.restyle import restyle
        if not self.doc:
            return False
        data = new.to_dict()

        def mutate(doc):
            from app.core.document.model import Appearance
            restyle(doc, Appearance.from_dict(data))
        return self.patch("Тема и стиль", mutate)

    def replace_selection(self, kind: str) -> Node | None:
        """Заменить выделенный элемент заготовкой: новый встаёт на то же место (родитель, порядок, положение),
        старый удаляется; одна запись истории."""
        s = self.screen()
        if not s or not self.doc or len(self.selection) != 1 or self.inside_instance(self.selection[0]):
            if self.selection:
                self.message.emit("Заменить можно один элемент (не часть копии компонента)")
            return None
        old_id = self.selection[0]
        new = components.build(kind, s, self.doc.meta.appearance)
        holder: dict = {}

        def mutate(doc):
            scr = next(x for x in doc.screens if x.id == s.id)
            old, parent, idx = tree.find(scr, old_id)
            siblings = parent.children if parent is not None else scr.nodes
            node = Node.from_dict(new.to_dict())
            dx = 0.0 if node.constraint_h == "left_right" else old.x - node.x
            dy = old.y - node.y
            for n, _, _ in tree.walk([node]):
                n.x, n.y = round(n.x + dx, 2), round(n.y + dy, 2)
            if parent is not None and parent.auto_layout:
                node.sizing_h = old.sizing_h if node.constraint_h != "left_right" else node.sizing_h
            siblings[idx] = node
            holder["id"] = node.id
        if not self.patch(f"Заменить на: {new.name}", mutate):
            return None
        self.select([holder["id"]])
        return tree.find(self.screen(), holder["id"])[0]

    # ---------- простое действие при нажатии (без студии «Логика») ----------
    def tap_rules(self, node_id: str) -> list:
        s = self.screen()
        if not s or not self.doc:
            return []
        return [it for it in self.doc.interactions if it.screen_id == s.id and it.node_id == node_id
                and it.trigger == "tap"]

    def auto_advance(self) -> tuple[str, int, str] | None | str:
        """Автопереход экрана: (экран, пауза мс, переход), None — нет, "custom" — своё правило в «Логике»."""
        s = self.screen()
        rules = [it for it in (self.doc.interactions if self.doc else []) if s and it.screen_id == s.id
                 and it.trigger == "screen_open"]
        if not rules:
            return None
        acts = rules[0].actions
        if len(rules) == 1 and not rules[0].condition and len(acts) == 2 and acts[0]["type"] == "wait" \
                and acts[1]["type"] == "navigate":
            return acts[1]["screen_id"], acts[0]["duration"], acts[1]["transition"]
        return "custom"

    def set_auto_advance(self, target_id: str | None, ms: int = 2000, transition: str = "fade") -> bool:
        """«Через N секунд перейти на экран» при открытии текущего (заставка, онбординг). Одна запись истории."""
        from app.core.document.behavior import Interaction
        s = self.screen()
        if not s or not self.doc or self.auto_advance() == "custom":
            return False
        full = None
        if target_id:
            full = Interaction.from_dict(Interaction(screen_id=s.id, trigger="screen_open", actions=[
                {"type": "wait", "duration": int(ms)},
                {"type": "navigate", "screen_id": target_id, "transition": transition, "duration": 400,
                 "easing": "ease_in_out"}]).to_dict())
        sid = s.id

        def mutate(doc):
            doc.interactions = [it for it in doc.interactions if not (it.screen_id == sid
                                                                       and it.trigger == "screen_open")]
            if full is not None:
                doc.interactions.append(Interaction.from_dict(full.to_dict()))
        return self.patch("Автопереход" if target_id else "Убрать автопереход", mutate)

    def set_tap_transition(self, node_id: str, transition: str) -> bool:
        cur = self.tap_action(node_id)
        if not isinstance(cur, dict) or cur.get("type") != "navigate":
            return False
        return self.set_tap_action(node_id, {**cur, "transition": transition})

    def set_overlay_tap(self, node_id: str, target_id: str) -> bool:
        """Нажатие открывает окно поверх экрана с затемнением; само окно в дизайне скрывается."""
        if not self.set_tap_action(node_id, {"type": "open_overlay", "node_id": target_id, "scrim": True}):
            return False
        target = tree.find(self.screen(), target_id)[0] if self.screen() else None
        if target is not None and target.visible:
            self.set_props({target_id: {"visible": False}}, "Окно скрыто до открытия")
        return True

    def tap_action(self, node_id: str) -> dict | None | str:
        """Действие при нажатии: словарь простого действия, None — ничего, "custom" — своё правило в «Логике»."""
        rules = self.tap_rules(node_id)
        if not rules:
            return None
        if len(rules) == 1 and not rules[0].condition and len(rules[0].actions) == 1:
            return dict(rules[0].actions[0])
        return "custom"

    def set_tap_action(self, node_id: str, action: dict | None) -> bool:
        """Простое правило «нажатие → одно действие». Сложные правила из «Логики» не трогаются."""
        from app.core.document.behavior import Interaction
        s = self.screen()
        if not s or not self.doc or self.tap_action(node_id) == "custom":
            return False
        full = None
        if action is not None:
            t = action["type"]
            base = {"navigate": {"transition": "slide_left", "duration": 300, "easing": "ease_in_out"},
                    "back": {"transition": "slide_right", "duration": 300, "easing": "ease_in_out"},
                    "set_visible": {"mode": "toggle"}, "open_overlay": {"scrim": True}}.get(t, {})
            full = Interaction.from_dict(Interaction(screen_id=s.id, node_id=node_id, trigger="tap",
                                                     actions=[{**base, **action}]).to_dict())
        old_ids = {it.id for it in self.tap_rules(node_id)}

        def mutate(doc):
            doc.interactions = [it for it in doc.interactions if it.id not in old_ids]
            if full is not None:
                doc.interactions.append(Interaction.from_dict(full.to_dict()))
        return self.patch("При нажатии" if action else "Убрать действие при нажатии", mutate)

    # ---------- фигуры: объединение, вычитание, маски ----------
    SHAPE_TYPES = ("rect", "ellipse", "vector")
    SHAPE_OPS = {"union": "Объединение", "subtract": "Вычитание", "intersect": "Пересечение",
                 "exclude": "Исключение"}

    def shape_op_ready(self) -> bool:
        nodes = self.selected_nodes()
        return len(nodes) >= 2 and all(n.type in self.SHAPE_TYPES and not self.inside_instance(n.id) for n in nodes)

    def combine_shapes(self, op: str) -> str | None:
        """Две и больше фигуры → одна: объединение, вычитание (из нижней — верхние), пересечение, исключение.
        Результат — контур на месте нижней фигуры с её заливкой и обводкой. Одна запись истории."""
        from PySide6.QtGui import QPainterPath
        from app.core.document.model import Node
        from app.ui.workspace.canvas import node_outline, qpath_to_d
        s = self.screen()
        if not s or not self.shape_op_ready() or op not in self.SHAPE_OPS:
            return None
        order = {n.id: i for i, (n, _, _) in enumerate(tree.walk(s.nodes))}
        nodes = sorted(self.selected_nodes(), key=lambda n: order[n.id])  # снизу вверх
        base = node_outline(nodes[0]).simplified()
        for n in nodes[1:]:
            o = node_outline(n).simplified()
            if op == "union":
                base = base.united(o)
            elif op == "subtract":
                base = base.subtracted(o)
            elif op == "intersect":
                base = base.intersected(o)
            else:
                base = base.subtracted(o).united(o.subtracted(base))
        base = base.simplified()
        r = base.boundingRect()
        if r.width() < 0.5 or r.height() < 0.5:
            self.message.emit(f"{self.SHAPE_OPS[op]}: фигуры не пересекаются — ничего не осталось")
            return None
        d = qpath_to_d(base, -r.x(), -r.y())
        first = nodes[0]
        new = Node(type="vector", name=self.SHAPE_OPS[op], x=r.x(), y=r.y(), w=r.width(), h=r.height(), path=d,
                   vb_w=r.width(), vb_h=r.height(), fill=first.fill or "#808080", stroke=first.stroke,
                   stroke_width=first.stroke_width, opacity=first.opacity, fill_rule="nonzero",
                   constraint_h=first.constraint_h, constraint_v=first.constraint_v)
        ids = [n.id for n in nodes]
        sid = s.id

        def mutate(doc):
            scr = doc.screen(sid)
            _, parent, idx = tree.find(scr, ids[0])
            siblings = parent.children if parent is not None else scr.nodes
            siblings[idx] = Node.from_dict(new.to_dict())
            for nid in ids[1:]:
                _, par, i = tree.find(scr, nid)
                (par.children if par is not None else scr.nodes).pop(i)
        if self.patch(self.SHAPE_OPS[op], mutate):
            self.select([new.id])
            return new.id
        return None

    def mask_ready(self) -> bool:
        nodes = self.selected_nodes()
        if len(nodes) != 2:
            return False
        shapes = [n for n in nodes if n.type in self.SHAPE_TYPES]
        targets = [n for n in nodes if n.type in ("image", "frame", "rect") and n not in shapes[:1]]
        return bool(shapes) and bool(targets) and not any(self.inside_instance(n.id) for n in nodes)

    def mask_with_shape(self) -> bool:
        """Картинка (или контейнер) + фигура → картинка в форме фигуры; фигура убирается. Одна запись истории."""
        from app.core.document.model import MASK_BOX
        from app.ui.workspace.canvas import node_outline, qpath_to_d
        s = self.screen()
        if not s or not self.mask_ready():
            return False
        nodes = self.selected_nodes()
        order = {n.id: i for i, (n, _, _) in enumerate(tree.walk(s.nodes))}
        nodes.sort(key=lambda n: order[n.id])
        # форма — верхняя фигура (как в Figma наоборот не путать: обрезаем то, что под ней)
        shape = next(n for n in reversed(nodes) if n.type in self.SHAPE_TYPES)
        target = next(n for n in nodes if n is not shape)
        if target.w < 1 or target.h < 1:
            return False
        d = qpath_to_d(node_outline(shape), -target.x, -target.y, MASK_BOX / target.w, MASK_BOX / target.h)
        tid, sid_, scr_id = target.id, shape.id, s.id

        def mutate(doc):
            scr = doc.screen(scr_id)
            tree.find(scr, tid)[0].clip_path = d
            _, par, i = tree.find(scr, sid_)
            (par.children if par is not None else scr.nodes).pop(i)
        if self.patch("Маска формой", mutate):
            self.select([tid])
            return True
        return False

    def delete_selection(self) -> None:
        s = self.screen()
        if s and self.selection:
            if any(self.inside_instance(i) for i in self.selection):
                self.message.emit("Часть копии компонента нельзя удалить — скройте её или отвяжите копию от компонента")
                return
            self.execute(DeleteNodes(s.id, self.selection))
            self.select([])

    def inside_instance(self, node_id: str) -> bool:
        """Узел — часть содержимого экземпляра (не сам экземпляр верхнего уровня)."""
        s = self.screen()
        return bool(s) and any(a.is_instance for a in tree.ancestors(s, node_id))

    def set_props(self, changes: dict[str, dict], label: str = "Изменить свойства") -> bool:
        """Изменение свойств. Внутри экземпляров содержимое и стиль становятся переопределениями,
        структура и геометрия содержимого экземпляра не меняются."""
        s = self.screen()
        if not (s and changes):
            return False
        m = tree.node_map(s)
        plain, overrides = {}, {}
        for nid, props in changes.items():
            node = m.get(nid)
            in_inst = self.inside_instance(nid)
            if node is not None and (in_inst or node.is_instance):
                ov = {k: v for k, v in props.items() if k in OVERRIDABLE}
                rest = {k: v for k, v in props.items() if k not in OVERRIDABLE}
                if ov:
                    overrides[nid] = ov
                if rest and in_inst:
                    if set(rest) - {"x", "y", "w", "h", "name", "locked"}:
                        self.message.emit("В экземпляре меняются только содержимое и стиль — "
                                          "структуру правьте в мастер-компоненте")
                    continue  # геометрию содержимого задаёт мастер и раскладка
                if rest:
                    plain[nid] = rest
            else:
                plain[nid] = props
        ok = True
        if overrides:
            sid = s.id

            def mutate(doc):
                comp_engine.set_overrides(doc, doc.screen(sid), overrides, self.engine)
            cmds: list[Command] = [DocPatch(label, mutate)]
            if plain:
                cmds.append(SetProps(s.id, plain, label))
            return self.execute(Batch(cmds, label) if len(cmds) > 1 else cmds[0])
        if plain:
            ok = self.execute(SetProps(s.id, plain, label))
        return ok

    def patch(self, label: str, mutate) -> bool:
        """Операция над документом целиком (компоненты, ресурсы, стили) одной записью истории."""
        try:
            return self.execute(DocPatch(label, mutate))
        except Exception as exc:  # noqa: BLE001 — сообщение пользователю, детали в журнал
            log.exception("Операция «%s» не выполнена", label)
            self.message.emit(f"{label}: {exc}")
            return False

    def set_props_for_selection(self, props: dict, label: str = "Изменить свойства") -> bool:
        leaves = self.selected_leaves()
        geometry_free = {k: v for k, v in props.items()}
        return self.set_props({n.id: dict(geometry_free) for n in leaves}, label)

    def toggle(self, prop: str, ids: list[str] | None = None) -> None:
        s = self.screen()
        nodes = self.selected_nodes() if ids is None else [tree.node_map(s)[i] for i in ids]
        if not nodes:
            return
        value = not all(getattr(n, prop) for n in nodes)
        label = {"visible": "Показать/скрыть", "locked": "Заблокировать/разблокировать"}[prop]
        self.set_props({n.id: {prop: value} for n in nodes}, label)
        if prop == "locked" and value or prop == "visible" and not value:
            self.select([i for i in self.selection if i not in {n.id for n in nodes}])

    def nudge(self, dx: float, dy: float) -> None:
        nodes = self.selected_nodes()
        if nodes:
            self.set_props(self.translate_changes(nodes, dx, dy), "Сдвинуть")

    def set_bbox(self, new: Rect) -> None:
        old = self.selection_bbox()
        if not old:
            return
        originals = {n.id: (n.x, n.y, n.w, n.h) for n in self.selected_leaves()}
        self.set_props(self.scale_changes(originals, old, new), "Изменить размер")

    def group_selection(self) -> None:
        s = self.screen()
        if s and self.selection:
            cmd = Group(s.id, self.selection)
            if self.execute(cmd):
                self.select([cmd.group_id])

    def ungroup_selection(self) -> None:
        """Разгруппировать группы и «снять» фреймы (дети остаются на своих местах)."""
        s = self.screen()
        groups = [n for n in self.selected_nodes() if n.is_container]
        if not s or not groups:
            return
        children = [c.id for g in groups for c in g.children]
        cmds = [Ungroup(s.id, g.id) for g in groups]
        self.execute(Batch(cmds, "Разгруппировать") if len(cmds) > 1 else cmds[0])
        self.select(children)

    def wrap_in_auto_layout(self, direction: str = "vertical") -> None:
        """Обернуть выделение во фрейм с Auto Layout; порядок детей — по положению на холсте."""
        s = self.screen()
        nodes = self.selected_nodes()
        bb = self.selection_bbox()
        if not s or not nodes or not bb:
            return
        axis = 1 if direction == "vertical" else 0
        ordered = sorted(nodes, key=lambda n: tree.bounds(n)[axis])
        rects = [tree.bounds(n) for n in ordered]
        gaps = [rects[i + 1][axis] - (rects[i][axis] + rects[i][axis + 2]) for i in range(len(rects) - 1)]
        gap = max(0.0, round(sum(gaps) / len(gaps))) if gaps else 0.0
        frame = Node(type="frame", name="Контейнер", x=bb[0], y=bb[1], w=bb[2], h=bb[3], fill="",
                     layout=direction, gap=gap, sizing_h="hug", sizing_v="hug")
        cmds: list[Command] = [Group(s.id, [n.id for n in nodes], frame, label="Выстроить в контейнер")]
        cmds += [MoveToIndex(s.id, n.id, i) for i, n in enumerate(ordered)]
        if self.execute(Batch(cmds, "Выстроить в контейнер")):
            self.select([frame.id], entered_group=self.entered_group)

    # ---------- мастер-компоненты ----------
    def create_component(self, name: str, category: str = "Мои компоненты") -> str | None:
        s = self.screen()
        if not s or not self.selection:
            return None
        sid, ids, result = s.id, list(self.selection), {}

        def mutate(doc):
            defn, inst = comp_engine.create_component(doc, doc.screen(sid), ids, name, self.engine, category)
            result["id"], result["inst"] = defn.id, inst.id
        if self.patch("Создать компонент", mutate):
            self.select([result["inst"]], entered_group=self.entered_group)
            return result["id"]
        return None

    def insert_instance(self, component_id: str, pos: tuple[float, float] | None = None) -> Node | None:
        s = self.screen()
        defn = self.doc.component(component_id) if self.doc else None
        if not s or defn is None:
            return None
        x, y = pos or (round((s.width - defn.root.w) / 2), round((s.height - defn.root.h) / 2))
        inst = comp_engine.make_instance(defn, x, y, self.engine)
        if self.execute(AddNodes(s.id, [inst], self._container_id(), label=f"Вставить: {defn.name}")):
            self.select([inst.id])
            return inst
        return None

    def selected_instances(self) -> list[Node]:
        return [n for n in self.selected_nodes() if n.is_instance]

    def detach_selection(self) -> None:
        s = self.screen()
        ids = [n.id for n in self.selected_instances()]
        if s and ids:
            sid = s.id
            self.patch("Отсоединить экземпляр",
                       lambda doc: [comp_engine.detach(tree.find(doc.screen(sid), i)[0]) for i in ids])

    def reset_overrides_selection(self) -> None:
        s = self.screen()
        ids = [n.id for n in self.selected_instances()]
        if s and ids:
            sid = s.id
            self.patch("Сбросить переопределения", lambda doc: [
                comp_engine.reset_overrides(doc, tree.find(doc.screen(sid), i)[0], self.engine) for i in ids])

    def set_instance_state(self, state: str) -> None:
        s = self.screen()
        ids = [n.id for n in self.selected_instances()]
        if not s or not ids:
            return
        sid = s.id

        def mutate(doc):
            for i in ids:
                inst = tree.find(doc.screen(sid), i)[0]
                inst.state = state
                dep = doc.component(inst.component_id)
                if dep is not None:
                    comp_engine.materialize(dep, inst, self.engine)
        self.patch(f"Состояние: {state}", mutate)

    # ---------- копировать / вставить стиль ----------
    STYLE_COPY = ("fill", "stroke", "stroke_width", "radius", "opacity", "elevation", "gradient", "fill2",
                  "grad_angle", "blur", "shadow_color", "shadow_x", "shadow_y", "shadow_blur", "shadow_spread",
                  "shadow_inset", "stroke_dash", "stroke_align", "stroke_sides", "radius_tl", "radius_tr",
                  "radius_br", "radius_bl", "fill3")
    TEXT_STYLE_COPY = ("font_family", "font_size", "font_weight", "text_color", "align", "letter_spacing",
                       "line_height", "italic", "decoration", "text_case", "max_lines")
    style_clipboard: dict | None = None

    def copy_style(self) -> bool:
        """Запомнить оформление выделенного элемента (без текста, размеров и положения)."""
        nodes = [n for n in self.selected_nodes() if not n.is_group]
        if not nodes:
            return False
        n = nodes[0]
        props = {k: getattr(n, k) for k in self.STYLE_COPY}
        if n.type == "text":
            props.update({k: getattr(n, k) for k in self.TEXT_STYLE_COPY})
        Editor.style_clipboard = {"type": n.type, "props": props}
        self.message.emit(f"Стиль «{n.name or n.type}» скопирован — Ctrl+Alt+V вставит его другим элементам")
        return True

    def paste_style(self) -> bool:
        """Применить запомненный стиль к выделенным: оформление — всем, свойства текста — только текстам."""
        clip = Editor.style_clipboard
        targets = [n for n in self.selected_leaves() if not self.inside_instance(n.id)]
        if not clip or not targets:
            return False
        changes = {}
        for n in targets:
            props = {k: v for k, v in clip["props"].items()
                     if (k in self.STYLE_COPY or n.type == "text") and getattr(n, k) != v}
            if (n.type == "text") != (clip["type"] == "text"):
                props.pop("fill", None)  # у текста заливка — это фон, а не цвет букв: между текстом и фигурой не переносится
            if props:
                changes[n.id] = props
        return bool(changes) and self.set_props(changes, "Вставить стиль")

    def add_color_token(self, value: str, name: str = "") -> str | None:
        """Сохранить цвет в цвета проекта (если такого ещё нет); возвращает имя."""
        from app.core.document.model import ColorToken
        if not self.doc or not value:
            return None
        found = next((c for c in self.doc.colors if c.value.upper() == value.upper()), None)
        if found is not None:
            return found.name
        name = name or f"Цвет {len(self.doc.colors) + 1}"

        def mutate(doc):
            doc.colors.append(ColorToken(name=name, value=value.upper()))
        return name if self.patch("Цвет в проект", mutate) else None

    color_picker = None  # холст: функция(обратный_вызов) — следующий щелчок по холсту берёт цвет
    comments_visible = True

    # ---------- комментарии ----------
    def add_comment(self, x: float, y: float, text: str, author: str = "") -> str | None:
        from app.core.document.model import Comment
        s = self.screen()
        if not s or not text.strip():
            return None
        c = Comment(x=float(x), y=float(y), text=text.strip(), author=author)
        sid = s.id

        def mutate(doc):
            doc.screen(sid).comments.append(Comment.from_dict(c.to_dict()))
        return c.id if self.patch("Комментарий", mutate) else None

    def comment(self, comment_id: str):
        s = self.screen()
        return next((c for c in (s.comments if s else []) if c.id == comment_id), None)

    def update_comment(self, comment_id: str, **props) -> bool:
        s = self.screen()
        if self.comment(comment_id) is None:
            return False
        sid = s.id

        def mutate(doc):
            c = next(c for c in doc.screen(sid).comments if c.id == comment_id)
            for k, v in props.items():
                setattr(c, k, v)
        label = "Комментарий решён" if props.get("resolved") else "Изменить комментарий"
        return self.patch(label, mutate)

    def delete_comment(self, comment_id: str) -> bool:
        s = self.screen()
        if self.comment(comment_id) is None:
            return False
        sid = s.id

        def mutate(doc):
            doc.screen(sid).comments[:] = [c for c in doc.screen(sid).comments if c.id != comment_id]
        return self.patch("Удалить комментарий", mutate)

    # ---------- графики ----------
    def set_chart_data(self, node_id: str, text: str) -> bool:
        """Новые числа графика: содержимое перестраивается под размер, цвета сохраняются."""
        from app.engines.material.color import scheme
        from app.engines.preview.devices import screen_dpi
        from app.libraries import charts
        s = self.screen()
        node = tree.find(s, node_id)[0] if s else None
        if node is None or node.role not in charts.CHART_ROLES:
            return False
        values = charts.parse_values(text)
        if len(values) < (1 if node.role == "chart.donut" else 2) or \
                (node.role != "chart.line" and any(v < 0 for v in values)):
            self.message.emit("График: нужно не меньше двух чисел (у кольца — одно), без минусов у столбцов и кольца")
            return False
        ap = self.doc.meta.appearance
        sch = scheme(ap.accent, ap.theme != "light")
        default = [sch[r] for r in ("primary", "tertiary", "secondary", "error", "primaryContainer",
                                    "tertiaryContainer")]
        k = screen_dpi(s) / 160 if s.platform == "android" else 1.0
        sid = s.id

        def mutate(doc):
            charts.rebuild(tree.find(doc.screen(sid), node_id)[0], values, k, default)
        return self.patch("Данные графика", mutate)

    # ---------- версии и контраст ----------
    def restore_document(self, other, label: str = "Вернуть версию") -> bool:
        """Содержимое другой копии проекта (версии) — в текущий документ одной записью истории."""
        from app.core.commands import DocPatch
        snap = DocPatch.capture(other)
        keep_id = self.doc.meta.id if self.doc else ""

        def mutate(doc):
            DocPatch.restore(doc, snap)
            doc.meta.id = keep_id
        ok = self.patch(label, mutate)
        if ok and self.doc.screens and not self.screen():
            self.set_screen(self.doc.screens[0].id)
        return ok

    def fix_contrast(self, screen_ids=None) -> int:
        """Тексты с недостаточным контрастом — тот же оттенок, светлее или темнее. Одной записью истории."""
        from app.engines.validation.engine import contrast_fixes
        fixes = contrast_fixes(self.doc, self.artboard_color(), screen_ids) if self.doc else {}
        count = sum(len(v) for v in fixes.values())
        if not count:
            return 0

        def mutate(doc):
            for sid, nodes in fixes.items():
                m = tree.node_map(doc.screen(sid))
                for nid, color in nodes.items():
                    m[nid].text_color = color
        return count if self.patch("Исправить контраст", mutate) else 0

    def set_app_icon(self, node_id: str | None = None) -> bool:
        """Выделенный элемент — иконка приложения (картинка 432×432 в ресурсах проекта); None — убрать."""
        import hashlib
        from dataclasses import replace
        from PySide6.QtCore import QBuffer, QIODevice
        from app.core.document.model import Asset
        from app.ui.workspace.render_export import icon_background, icon_image
        s = self.screen()
        if not s or not self.doc:
            return False
        ap = self.doc.meta.appearance
        if node_id is None:
            new_ap = replace(ap, app_icon="", app_icon_bg="")

            def clear(doc):
                doc.meta.appearance = replace(new_ap)
            return self.patch("Убрать иконку приложения", clear)
        node = tree.find(s, node_id)[0]
        img = icon_image(s, self.doc, self.artboard_color(), node)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        data = bytes(buf.data())
        sha = hashlib.sha256(data).hexdigest()
        old = next((a for a in self.doc.assets if a.sha256 == sha), None)
        asset = old or Asset(kind="image", name=f"Иконка приложения ({node.name or node.type})", ext="png",
                             sha256=sha, size=len(data), source="App Design Studio (из дизайна)",
                             author="автор проекта", license="Собственная работа", redistribution="allowed")
        bg = icon_background(img, node)

        def mutate(doc):
            if old is None:
                doc.assets.append(Asset.from_dict(asset.to_dict()))
                doc.asset_data[asset.id] = data
            doc.meta.appearance = replace(doc.meta.appearance, app_icon=asset.id, app_icon_bg=bg)
        ok = self.patch("Иконка приложения", mutate)
        if ok:
            self.message.emit("Иконка приложения готова — она попадёт в Android-проект и APK")
        return ok

    def set_instance_variant(self, axis: str, value: str) -> None:
        """Выбрать значение свойства варианта у выделенных копий компонента."""
        s = self.screen()
        ids = [n.id for n in self.selected_instances()]
        if not s or not ids:
            return
        sid = s.id

        def mutate(doc):
            for i in ids:
                inst = tree.find(doc.screen(sid), i)[0]
                inst.variant = {**inst.variant, axis: value}
                dep = doc.component(inst.component_id)
                if dep is not None:
                    comp_engine.materialize(dep, inst, self.engine)
        self.patch(f"{axis}: {value}", mutate)

    def add_variant_preset(self, component_id: str, key: str) -> bool:
        """Готовый набор вариантов компонента: size — Размер S / M / L, style — Стиль, theme — Тема."""
        from app.engines.components import variants
        from app.engines.preview.devices import screen_dpi
        defn = self.doc.component(component_id) if self.doc else None
        if defn is None:
            return False
        s = self.screen()
        k = screen_dpi(s) / 160 if s is not None and s.platform == "android" else 1.0
        ap = self.doc.meta.appearance

        def mutate(doc):
            d = doc.component(component_id)
            variants.add_preset(d, key, ap, k)
            d.version += 1
            comp_engine.sync_instances(doc, self.engine)
        return self.patch(f"Варианты «{variants.PRESET_AXES[key]}»", mutate)

    def make_variant_component(self, name: str, presets: tuple[str, ...] = ("size", "style")) -> str | None:
        """Из выделения — компонент с готовыми вариантами; выделение становится его копией. Отмена — по шагам."""
        cid = self.create_component(name)
        if cid is None:
            return None
        for key in presets:
            self.add_variant_preset(cid, key)
        return cid

    def update_component(self, defn: ComponentDef) -> bool:
        data = defn.to_dict()

        def mutate(doc):
            new = ComponentDef.from_dict(data)
            old = doc.component(new.id)
            if old is None:
                doc.components.append(new)
            else:
                new.version = old.version + 1
                doc.components[doc.components.index(old)] = new
            comp_engine.sync_instances(doc, self.engine)
        return self.patch(f"Изменить компонент «{defn.name}»", mutate)

    def component_usage(self, component_id: str) -> int:
        if not self.doc:
            return 0
        roots = [n for s in self.doc.screens for n in s.nodes] + [c.root for c in self.doc.components]
        return sum(1 for n, _, _ in tree.walk(roots) if n.is_instance and n.component_id == component_id)

    def delete_component(self, component_id: str) -> bool:
        if self.component_usage(component_id):
            self.message.emit("Компонент используется — сначала удалите его копии или отвяжите их")
            return False
        return self.patch("Удалить компонент",
                          lambda doc: doc.components.remove(doc.component(component_id)))

    def install_bundle(self, bundle: dict, files: dict) -> list[str]:
        from app.engines.components.library import install_bundle
        out: list[str] = []

        def mutate(doc):
            out.extend(install_bundle(doc, bundle, files, self.engine))
        self.patch("Вставить компонент из библиотеки", mutate)
        for a in self.doc.assets if self.doc else []:
            if a.kind == "font" and a.id in self.doc.asset_data:
                try:
                    REGISTRY.register(a.id, self.doc.asset_data[a.id])
                except ValueError as exc:
                    out.append(f"Шрифт «{a.name}»: {exc}")
        return out

    # ---------- ресурсы ----------
    def add_asset(self, asset: Asset, data: bytes) -> bool:
        payload = asset.to_dict()

        def mutate(doc):
            a = Asset.from_dict(payload)
            same = next((x for x in doc.assets if x.sha256 == a.sha256 and x.kind == a.kind), None)
            if same is not None:
                raise ModelError(f"Такой файл уже есть в проекте: «{same.name}»")
            doc.assets.append(a)
            doc.asset_data[a.id] = data
        return self.patch(f"Добавить ресурс «{asset.name}»", mutate)

    def update_asset(self, asset_id: str, data: bytes | None = None, **meta) -> bool:
        import hashlib

        def mutate(doc):
            a = doc.asset(asset_id)
            if a is None:
                raise ModelError("Ресурс не найден")
            d = a.to_dict()
            d.update(meta)
            if data is not None:
                d["sha256"], d["size"] = hashlib.sha256(data).hexdigest(), len(data)
                doc.asset_data[asset_id] = data
            doc.assets[doc.assets.index(a)] = Asset.from_dict(d)
            comp_engine.sync_instances(doc, self.engine)
        return self.patch("Изменить ресурс", mutate)

    def asset_usage(self, asset_id: str) -> int:
        if not self.doc:
            return 0
        if self.doc.meta.appearance.app_icon == asset_id:  # иконка приложения — тоже использование
            return 1
        roots = [n for s in self.doc.screens for n in s.nodes] + [c.root for c in self.doc.components]
        n_nodes = sum(1 for n, _, _ in tree.walk(roots) if n.asset_id == asset_id)
        a = self.doc.asset(asset_id)
        if a is not None and a.kind == "font":
            n_nodes += sum(1 for n, _, _ in tree.walk(roots) if n.type == "text" and n.font_family == a.family)
        return n_nodes

    def remove_asset(self, asset_id: str) -> bool:
        if self.asset_usage(asset_id):
            self.message.emit("Ресурс используется — удалить можно только неиспользуемый ресурс")
            return False

        def mutate(doc):
            doc.assets.remove(doc.asset(asset_id))
            doc.asset_data.pop(asset_id, None)
        return self.patch("Удалить ресурс", mutate)

    # ---------- картинки и фото ----------
    def add_or_reuse_asset(self, asset: Asset, data: bytes) -> str | None:
        """Добавить ресурс; тот же файл уже есть — вернуть его id (без дубликата)."""
        if not self.doc:
            return None
        same = next((x for x in self.doc.assets if x.sha256 == asset.sha256 and x.kind == asset.kind), None)
        if same is not None:
            return same.id
        return asset.id if self.add_asset(asset, data) else None

    def place_image(self, asset_id: str, pixel_size: tuple[int, int], at: tuple[float, float] | None = None,
                    target_id: str | None = None, fit: str = "cover") -> Node | None:
        """Поставить картинку на экран (по центру или в точку) или в выбранный элемент: у картинки меняется
        файл, другой элемент (заглушка, прямоугольник, контейнер-фото) заменяется картинкой того же места и
        размера со скруглением. Новая картинка — до 60 % ширины экрана с сохранением пропорций."""
        s = self.screen()
        a = self.doc.asset(asset_id) if self.doc else None
        if not s or a is None:
            return None
        if target_id:
            target = tree.find(s, target_id)[0]
            if target.type == "image":
                return target if self.set_props({target.id: {"asset_id": asset_id, "fit": fit}},
                                                f"Картинка: {a.name}") else None
            img = Node(type="image", name=a.name, asset_id=asset_id, fill="", fit=fit, x=target.x, y=target.y,
                       w=target.w, h=target.h, radius=target.radius, sizing_h=target.sizing_h,
                       sizing_v=target.sizing_v if target.sizing_v != "hug" else "fixed",
                       constraint_h=target.constraint_h, constraint_v=target.constraint_v)
            data = img.to_dict()

            def mutate(doc):
                scr = next(x for x in doc.screens if x.id == s.id)
                old, parent, idx = tree.find(scr, target_id)
                (parent.children if parent is not None else scr.nodes)[idx] = Node.from_dict(data)
            if self.patch(f"Картинка вместо «{target.name}»", mutate):
                self.select([img.id])
                return tree.find(self.screen(), img.id)[0]
            return None
        iw, ih = pixel_size
        w = min(s.width * 0.6, float(iw)) if iw else s.width * 0.6
        h = w * ih / iw if iw else w * 0.75
        if h > s.height * 0.6:
            h = s.height * 0.6
            w = h * iw / ih if ih else h
        x, y = at if at is not None else ((s.width - w) / 2, (s.height - h) / 2)
        n = Node(type="image", name=a.name, asset_id=asset_id, fill="", fit=fit, x=round(x, 2), y=round(y, 2),
                 w=round(w, 2), h=round(h, 2))
        if self.execute(AddNodes(s.id, [n], self._container_id(), label=f"Вставить: {a.name}")):
            self.select([n.id])
            return n
        return None

    def insert_image(self, asset_id: str, size: tuple[float, float] | None = None) -> Node | None:
        s = self.screen()
        a = self.doc.asset(asset_id) if self.doc else None
        if not s or a is None:
            return None
        w, h = size or (96, 96)
        n = Node(type="image", name=a.name, asset_id=a.id, fill="", x=round((s.width - w) / 2),
                 y=round((s.height - h) / 2), w=w, h=h)
        if self.execute(AddNodes(s.id, [n], self._container_id(), label=f"Вставить: {a.name}")):
            self.select([n.id])
            return n
        return None

    def add_vector(self, points: list[tuple[float, float]], closed: bool) -> Node | None:
        from app.core.document import pathdata
        s = self.screen()
        if not s or len(points) < 2:
            return None
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        x, y = min(xs), min(ys)
        w, h = max(max(xs) - x, 0.01), max(max(ys) - y, 0.01)
        segs = [("M", points[0][0] - x, points[0][1] - y)] + [("L", px - x, py - y) for px, py in points[1:]]
        if closed:
            segs.append(("Z",))
        n = Node(type="vector", name="Контур", x=x, y=y, w=w, h=h, vb_w=w, vb_h=h,
                 path=pathdata.to_string(segs), fill="#9A9A9A" if closed else "",
                 stroke="#F2F2F2" if not closed else "", stroke_width=0 if closed else 2.0)
        if self.execute(AddNodes(s.id, [n], self._container_id(), label="Нарисовать контур")):
            self.select([n.id])
            return n
        return None

    # ---------- стили текста и цвета ----------
    def save_text_style(self, style: TextStyle) -> bool:
        data = style.to_dict()

        def mutate(doc):
            st = TextStyle.from_dict(data)
            old = doc.text_style(st.id)
            if old is None:
                doc.text_styles.append(st)
            else:
                doc.text_styles[doc.text_styles.index(old)] = st
            comp_engine.apply_text_style(doc, st.id, self.engine)
        return self.patch(f"Стиль текста «{style.name}»", mutate)

    def delete_text_style(self, style_id: str) -> bool:
        def mutate(doc):
            st = doc.text_style(style_id)
            doc.text_styles.remove(st)
            roots = [n for s in doc.screens for n in s.nodes] + [c.root for c in doc.components]
            for n, _, _ in tree.walk(roots):
                if n.text_style == style_id:
                    n.text_style = ""  # тексты сохраняют свои свойства, связь со стилем снимается
            comp_engine.sync_instances(doc, self.engine)
        return self.patch("Удалить стиль текста", mutate)

    def apply_text_style_to_selection(self, style_id: str) -> bool:
        st = self.doc.text_style(style_id) if self.doc else None
        texts = [n for n in self.selected_leaves() if n.type == "text"] + [
            n for sel in self.selected_nodes() for n in tree.descendants(sel) if n.type == "text" and sel.is_frame]
        if st is None or not texts:
            return False
        props = {"text_style": st.id, "font_family": st.font_family, "font_size": st.font_size,
                 "font_weight": st.font_weight}
        if st.text_color:
            props["text_color"] = st.text_color
        return self.set_props({n.id: dict(props) for n in texts}, f"Применить стиль «{st.name}»")

    def save_color(self, token: ColorToken) -> bool:
        data = token.to_dict()

        def mutate(doc):
            t = ColorToken.from_dict(data)
            old = next((c for c in doc.colors if c.id == t.id), None)
            if old is None:
                doc.colors.append(t)
            else:
                doc.colors[doc.colors.index(old)] = t
        return self.patch(f"Цвет «{token.name}»", mutate)

    def add_material_colors(self, seed: str, variants: tuple[str, ...], fidelity: bool = True) -> int:
        """Цветовые токены всех ролей схемы Material 3 («M3 тёмная · Основной (primary)» …) одной записью
        истории. Токен с тем же именем обновляется, а не дублируется. Возвращает число токенов."""
        from app.engines.material.color import ROLE_RU, scheme
        tokens = []
        for variant in variants:
            sch = scheme(seed, variant == "dark", fidelity)
            ru = "тёмная" if variant == "dark" else "светлая"
            tokens += [(f"M3 {ru} · {ROLE_RU[r]} ({r})", v) for r, v in sch.items()]

        def mutate(doc):
            by_name = {c.name: c for c in doc.colors}
            for name, value in tokens:
                if name in by_name:
                    by_name[name].value = value
                else:
                    doc.colors.append(ColorToken(name=name, value=value))
        return len(tokens) if self.patch("Схема Material 3", mutate) else 0

    def add_material_typography(self) -> int:
        """Стили текста шкалы Material 3 (размер в px по плотности первого экрана Android)."""
        from app.engines.material.type_scale import TYPE_SCALE, style_name
        from app.engines.preview.devices import screen_dpi
        if not self.doc:
            return 0
        android = next((s for s in self.doc.screens if s.platform == "android"), None)
        k = screen_dpi(android) / 160 if android else 1.0
        family = self.doc.meta.appearance.font_family

        def mutate(doc):
            by_name = {t.name: t for t in doc.text_styles}
            for role, (_, size, _, weight) in TYPE_SCALE.items():
                name = style_name(role)
                old = by_name.get(name)
                st = TextStyle(name=name, font_family=family, font_size=round(size * k, 2), font_weight=weight,
                               id=old.id if old else new_id())
                if old is None:
                    doc.text_styles.append(st)
                else:
                    doc.text_styles[doc.text_styles.index(old)] = st
                    comp_engine.apply_text_style(doc, st.id, self.engine)
        return len(TYPE_SCALE) if self.patch("Типографика Material 3", mutate) else 0

    def delete_color(self, token_id: str) -> bool:
        return self.patch("Удалить цвет", lambda doc: doc.colors.remove(
            next(c for c in doc.colors if c.id == token_id)))

    def apply_color(self, value: str, prop: str = "fill") -> bool:
        nodes = self.selected_leaves()
        if prop == "text_color":
            nodes = [n for n in nodes if n.type == "text"] + [
                d for sel in self.selected_nodes() for d in tree.descendants(sel) if d.type == "text" and sel.is_frame]
        return bool(nodes) and self.set_props({n.id: {prop: value} for n in nodes}, "Применить цвет")

    def insert_component(self, kind: str, at: tuple[float, float] | None = None) -> Node | None:
        """Добавить заготовку; at — точка экрана (перетаскивание из галереи): туда ставится левый верхний угол,
        растянутые по ширине компоненты сохраняют свои поля по горизонтали."""
        s = self.screen()
        if not s or not self.doc:
            return None
        node = components.build(kind, s, self.doc.meta.appearance)
        if at is not None:
            dx = 0.0 if node.constraint_h == "left_right" else min(max(0.0, at[0]), max(0.0, s.width - node.w)) - node.x
            dy = min(max(0.0, at[1]), max(0.0, s.height - node.h)) - node.y
            for n, _, _ in tree.walk([node]):
                n.x, n.y = round(n.x + dx, 2), round(n.y + dy, 2)
        if self.execute(AddNodes(s.id, [node], self._container_id(), label=f"Добавить: {node.name}")):
            self.select([node.id])
            return node
        return None

    def reorder(self, mode: str) -> None:
        s = self.screen()
        if s and self.selection:
            self.execute(Reorder(s.id, self.selection, mode))

    def align(self, mode: str) -> None:
        nodes = self.selected_nodes()
        s = self.screen()
        if not nodes:
            return
        ref = (0, 0, s.width, s.height) if len(nodes) == 1 else self.selection_bbox()
        rx, ry, rw, rh = ref
        changes = {}
        for n in nodes:
            x, y, w, h = tree.bounds(n)
            dx = {"left": rx - x, "hcenter": rx + rw / 2 - (x + w / 2), "right": rx + rw - (x + w)}.get(mode, 0)
            dy = {"top": ry - y, "vcenter": ry + rh / 2 - (y + h / 2), "bottom": ry + rh - (y + h)}.get(mode, 0)
            changes.update(self.translate_changes([n], dx, dy))
        self.set_props(changes, "Выровнять")

    def distribute(self, axis: str) -> None:
        nodes = self.selected_nodes()
        if len(nodes) < 3:
            return
        i0, i1 = (0, 2) if axis == "x" else (1, 3)
        items = sorted(((tree.bounds(n), n) for n in nodes), key=lambda t: t[0][i0])
        start = items[0][0][i0]
        end = items[-1][0][i0] + items[-1][0][i1]
        gap = (end - start - sum(b[i1] for b, _ in items)) / (len(items) - 1)
        pos = start
        changes = {}
        for b, n in items:
            d = pos - b[i0]
            changes.update(self.translate_changes([n], d if axis == "x" else 0, d if axis == "y" else 0))
            pos += b[i1] + gap
        self.set_props(changes, "Распределить")

    # ---------- буфер обмена ----------
    def copy_selection(self) -> str:
        s = self.screen()
        ids = tree.top_ids(s, self.selection) if s else []
        m = tree.node_map(s) if s else {}
        self._clipboard = [m[i].to_dict() for i in ids]
        self._paste_serial = 0
        return json.dumps({"ads_nodes": 1, "nodes": self._clipboard}, ensure_ascii=False)

    @staticmethod
    def _reid(d: dict) -> dict:
        d = dict(d)
        d["id"] = new_id()
        if "children" in d:
            d["children"] = [Editor._reid(c) for c in d["children"]]
        return d

    def paste(self, payload: str | None = None) -> None:
        s = self.screen()
        if not s:
            return
        data = self._clipboard
        if payload:
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict) and parsed.get("ads_nodes") == 1 and isinstance(parsed.get("nodes"), list):
                    data = parsed["nodes"]
            except (ValueError, TypeError):
                pass
        if not data:
            return
        self._paste_serial += 1
        try:
            nodes = [Node.from_dict(self._reid(d)) for d in data]
        except ModelError as exc:
            log.warning("Вставка отклонена: %s", exc)
            return
        off = 16 * self._paste_serial
        for n in nodes:
            for leaf in tree.descendants(n):  # вставка: сдвигаем всё поддерево, включая детей фреймов
                leaf.x += off
                leaf.y += off
        if self.execute(AddNodes(s.id, nodes, self._container_id(), label="Вставить")):
            self.select([n.id for n in nodes])

    def duplicate(self) -> None:
        saved, serial = self._clipboard, self._paste_serial
        self.copy_selection()
        self.paste()
        self._clipboard, self._paste_serial = saved, serial

    def cut(self) -> str:
        payload = self.copy_selection()
        self.delete_selection()
        return payload

    # ---------- экраны, направляющие, проект ----------
    def add_screen(self, screen: Screen) -> None:
        if self.execute(AddScreen(screen)):
            self.set_screen(screen.id)

    def add_template_screen(self, key: str) -> Screen | None:
        """Готовый экран (вход, список, профиль…) для того же устройства, что текущий; одна запись истории."""
        from app.libraries import screen_templates
        cur = self.screen()
        if cur is None or not self.doc:
            return None
        s = screen_templates.build(key, cur, self.doc.meta.appearance)
        if self.execute(AddScreen(s)):
            self.set_screen(s.id)
            return self.screen()
        return None

    def add_blank_screen(self) -> Screen | None:
        """Пустой экран того же устройства, что текущий."""
        cur = self.screen()
        if cur is None or not self.doc:
            return None
        s = Screen(name=f"Экран {len(self.doc.screens) + 1}", platform=cur.platform, width=cur.width,
                   height=cur.height, device_id=cur.device_id, orientation=cur.orientation)
        self.add_screen(s)
        return self.screen()

    def remove_screen(self, screen_id: str) -> bool:
        return self.execute(RemoveScreen(screen_id))

    def set_screen_props(self, changes: dict, screen_id: str | None = None, label: str | None = None) -> bool:
        sid = screen_id or self.screen_id
        try:
            return bool(sid) and self.execute(SetScreenProps(sid, changes, label))
        except ModelError as exc:
            log.warning("Изменение экрана отклонено: %s", exc)
            return False

    def add_guide(self, axis: str, pos: float) -> None:
        s = self.screen()
        if s:
            self.set_screen_props({"guides": s.guides + [Guide(axis, float(pos))]}, label="Добавить направляющую")

    def move_guide(self, guide_id: str, pos: float | None) -> None:
        """pos=None удаляет направляющую."""
        s = self.screen()
        if not s:
            return
        guides = []
        for g in s.guides:
            if g.id == guide_id:
                if pos is None:
                    continue
                g = Guide(g.axis, float(pos), g.id)
            guides.append(g)
        self.set_screen_props({"guides": guides}, label="Удалить направляющую" if pos is None else "Переместить направляющую")

    def set_meta(self, changes: dict) -> bool:
        try:
            return self.execute(SetMeta(changes))
        except ModelError as exc:
            log.warning("Изменение проекта отклонено: %s", exc)
            return False
