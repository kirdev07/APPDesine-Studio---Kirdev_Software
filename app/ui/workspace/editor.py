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
TYPE_NAMES = {"rect": "Прямоугольник", "ellipse": "Эллипс", "text": "Текст", "group": "Группа", "frame": "Фрейм",
              "vector": "Вектор", "image": "Изображение", "instance": "Экземпляр"}
from app.core.document.model import ARTBOARD_COLORS  # noqa: E402 — общий с проверкой проекта


class Editor(QObject):
    document_changed = Signal()   # структура или свойства документа
    selection_changed = Signal()
    screen_changed = Signal()
    view_changed = Signal()       # сетка, привязки, инструмент
    preview_changed = Signal()    # временная геометрия при перетаскивании
    message = Signal(str)         # сообщение пользователю (строка состояния)
    open_component = Signal(str)  # двойной клик по экземпляру в режиме изоляции

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

    def replace_selection(self, kind: str) -> Node | None:
        """Заменить выделенный элемент заготовкой: новый встаёт на то же место (родитель, порядок, положение),
        старый удаляется; одна запись истории."""
        s = self.screen()
        if not s or not self.doc or len(self.selection) != 1 or self.inside_instance(self.selection[0]):
            if self.selection:
                self.message.emit("Заменить можно один элемент верхнего уровня или внутри фрейма")
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

    def delete_selection(self) -> None:
        s = self.screen()
        if s and self.selection:
            if any(self.inside_instance(i) for i in self.selection):
                self.message.emit("Содержимое экземпляра нельзя удалить — скройте элемент или отсоедините экземпляр")
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
        frame = Node(type="frame", name="Auto Layout", x=bb[0], y=bb[1], w=bb[2], h=bb[3], fill="",
                     layout=direction, gap=gap, sizing_h="hug", sizing_v="hug")
        cmds: list[Command] = [Group(s.id, [n.id for n in nodes], frame, label="Обернуть в Auto Layout")]
        cmds += [MoveToIndex(s.id, n.id, i) for i, n in enumerate(ordered)]
        if self.execute(Batch(cmds, "Обернуть в Auto Layout")):
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
            self.message.emit("Компонент используется — сначала удалите или отсоедините его экземпляры")
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
