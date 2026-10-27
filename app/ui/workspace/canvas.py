"""Холст на QGraphicsView: отрисовка экрана, выделение, перемещение, масштаб, привязки, направляющие."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView, QInputDialog

from app.core.document import tree
from app.core.document.model import Node, Screen
from app.ui.themes.fusion_amoled import TOKENS
from app.ui.workspace.editor import TOOL_ELLIPSE, TOOL_HAND, TOOL_RECT, TOOL_SELECT, TOOL_TEXT, Editor

ACCENT = QColor(TOKENS["accent"])
HANDLE = 8  # px на экране
ALIGN_FLAGS = {"left": Qt.AlignmentFlag.AlignLeft, "center": Qt.AlignmentFlag.AlignHCenter,
               "right": Qt.AlignmentFlag.AlignRight}
ZOOM_MIN, ZOOM_MAX = 0.05, 32.0
# Ручки: (доля по X, доля по Y, двигаемые края)
HANDLES = [(0, 0, "lt"), (0.5, 0, "t"), (1, 0, "rt"), (1, 0.5, "r"), (1, 1, "rb"), (0.5, 1, "b"), (0, 1, "lb"),
           (0, 0.5, "l")]
HANDLE_CURSORS = [Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeVerCursor, Qt.CursorShape.SizeBDiagCursor,
                  Qt.CursorShape.SizeHorCursor, Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeVerCursor,
                  Qt.CursorShape.SizeBDiagCursor, Qt.CursorShape.SizeHorCursor]


def qcolor(value: str) -> QColor:
    """#RRGGBB или #RRGGBBAA (Qt трактует 8 цифр как #AARRGGBB, поэтому разбираем сами)."""
    if not value:
        return QColor(0, 0, 0, 0)
    v = value.lstrip("#")
    r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    a = int(v[6:8], 16) if len(v) == 8 else 255
    return QColor(r, g, b, a)


def paint_node(p: QPainter, n: Node) -> None:
    rect = QRectF(n.x, n.y, n.w, n.h)
    p.save()
    p.setOpacity(p.opacity() * n.opacity)
    p.setBrush(QBrush(qcolor(n.fill)) if n.fill else Qt.BrushStyle.NoBrush)
    if n.stroke and n.stroke_width > 0:
        pen = QPen(qcolor(n.stroke), n.stroke_width)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
    else:
        p.setPen(Qt.PenStyle.NoPen)
    if n.type == "ellipse":
        p.drawEllipse(rect)
    else:
        r = min(n.radius, n.w / 2, n.h / 2)
        if n.type == "rect" or n.fill or n.stroke:
            p.drawRoundedRect(rect, r, r)
        if n.type == "text":
            f = QFont(n.font_family)
            f.setPixelSize(max(1, int(round(n.font_size))))
            f.setWeight(QFont.Weight(n.font_weight))
            p.setFont(f)
            p.setPen(qcolor(n.text_color))
            p.setClipRect(rect)
            p.drawText(rect, ALIGN_FLAGS.get(n.align, Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignTop
                       | Qt.TextFlag.TextWordWrap, n.text)
    p.restore()


class NodeItem(QGraphicsItem):
    def __init__(self, node: Node):
        super().__init__()
        self.node = node
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, False)

    def boundingRect(self) -> QRectF:
        n = self.node
        m = n.stroke_width / 2 + 1
        return QRectF(n.x, n.y, n.w, n.h).adjusted(-m, -m, m, m)

    def sync(self) -> None:
        self.prepareGeometryChange()
        self.update()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_node(painter, self.node)


class ArtboardItem(QGraphicsItem):
    def __init__(self, screen: Screen, color: str):
        super().__init__()
        self.screen, self.color = screen, color

    def boundingRect(self) -> QRectF:
        return QRectF(-1, -1, self.screen.width + 2, self.screen.height + 2)

    def paint(self, painter, option, widget=None):
        painter.fillRect(QRectF(0, 0, self.screen.width, self.screen.height), QColor(self.color))
        pen = QPen(QColor(TOKENS["border_strong"]), 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRect(QRectF(0, 0, self.screen.width, self.screen.height))


def build_scene(scene: QGraphicsScene, screen: Screen, artboard_color: str) -> dict[str, NodeItem]:
    scene.clear()
    scene.addItem(ArtboardItem(screen, artboard_color))
    items: dict[str, NodeItem] = {}

    def rec(nodes, visible):
        for n in nodes:
            v = visible and n.visible
            if n.is_group:
                rec(n.children, v)
            elif v:
                item = NodeItem(n)
                scene.addItem(item)
                items[n.id] = item
    rec(screen.nodes, True)
    return items


class OverlayItem(QGraphicsItem):
    """Сетка, направляющие, выделение, ручки, линии привязки и рамки инструментов. Толщины — в пикселях экрана."""

    def __init__(self, view: CanvasView):
        super().__init__()
        self.view = view
        self.setZValue(1_000_000)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def boundingRect(self) -> QRectF:
        s = self.view.editor.screen()
        if not s:
            return QRectF()
        return QRectF(-50_000, -50_000, 100_000 + s.width, 100_000 + s.height)

    def _pen(self, color: QColor, width: float = 1.0, style=Qt.PenStyle.SolidLine) -> QPen:
        pen = QPen(color, width, style)
        pen.setCosmetic(True)
        return pen

    def paint(self, p: QPainter, option, widget=None):
        ed, view = self.view.editor, self.view
        s = ed.screen()
        if not s:
            return
        scale = view.zoom()
        board = QRectF(0, 0, s.width, s.height)
        if ed.grid_visible and ed.grid_size * scale >= 6:
            p.setPen(self._pen(QColor(255, 255, 255, 18)))
            g = ed.grid_size
            lines = []
            x = g
            while x < s.width:
                lines.append((QPointF(x, 0), QPointF(x, s.height)))
                x += g
            y = g
            while y < s.height:
                lines.append((QPointF(0, y), QPointF(s.width, y)))
                y += g
            for a, b in lines:
                p.drawLine(a, b)
        if ed.guides_visible:
            for gd in s.guides:
                hot = view.drag_guide_id == gd.id
                p.setPen(self._pen(ACCENT if hot else QColor("#9A9A9A"), 1, Qt.PenStyle.DashLine))
                pos = view.drag_guide_pos if hot else gd.pos
                if gd.axis == "x":
                    p.drawLine(QPointF(pos, -10_000), QPointF(pos, 10_000 + s.height))
                else:
                    p.drawLine(QPointF(-10_000, pos), QPointF(10_000 + s.width, pos))
        # подпись экрана
        p.save()
        p.translate(0, -6 / scale)
        p.scale(1 / scale, 1 / scale)
        p.setPen(QColor(TOKENS["text_muted"]))
        f = QFont(TOKENS["font"])
        f.setPixelSize(12)
        p.setFont(f)
        p.drawText(QPointF(0, 0), f"{s.name}   {s.width} × {s.height}")
        p.restore()

        if ed.entered_group:
            try:
                b = tree.bounds(tree.find(s, ed.entered_group)[0])
            except Exception:
                b = None
            if b:
                p.setPen(self._pen(QColor("#7A7A7A"), 1, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(QRectF(*b))
        if view.hover_id and view.hover_id not in ed.selection:
            try:
                b = tree.bounds(tree.find(s, view.hover_id)[0])
                if b:
                    p.setPen(self._pen(ACCENT, 1))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(QRectF(*b))
            except Exception:
                pass
        nodes = ed.selected_nodes()
        p.setBrush(Qt.BrushStyle.NoBrush)
        if nodes:
            p.setPen(self._pen(ACCENT, 1))
            for n in nodes:
                b = tree.bounds(n)
                if b:
                    p.drawRect(QRectF(*b))
            bb = ed.selection_bbox()
            if bb:
                r = QRectF(*bb)
                p.setPen(self._pen(ACCENT, 1.5))
                p.drawRect(r)
                hs = HANDLE / scale
                p.setPen(self._pen(ACCENT, 1))
                p.setBrush(QColor("#FFFFFF"))
                for fx, fy, _ in HANDLES:
                    c = QPointF(r.x() + r.width() * fx, r.y() + r.height() * fy)
                    p.drawRect(QRectF(c.x() - hs / 2, c.y() - hs / 2, hs, hs))
                # размер
                p.save()
                p.translate(r.center().x(), r.bottom() + 8 / scale)
                p.scale(1 / scale, 1 / scale)
                text = f"{bb[2]:g} × {bb[3]:g}"
                f = QFont(TOKENS["font"])
                f.setPixelSize(11)
                p.setFont(f)
                w = p.fontMetrics().horizontalAdvance(text) + 10
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ACCENT)
                p.drawRoundedRect(QRectF(-w / 2, 0, w, 18), 4, 4)
                p.setPen(QColor("#FFFFFF"))
                p.drawText(QRectF(-w / 2, 0, w, 18), Qt.AlignmentFlag.AlignCenter, text)
                p.restore()
        p.setPen(self._pen(QColor("#FF4D7A"), 1))
        for x in view.snap_lines_x:
            p.drawLine(QPointF(x, -10_000), QPointF(x, 10_000 + s.height))
        for y in view.snap_lines_y:
            p.drawLine(QPointF(-10_000, y), QPointF(10_000 + s.width, y))
        if view.band_rect is not None:
            p.setPen(self._pen(ACCENT, 1))
            c = QColor(ACCENT)
            c.setAlpha(40)
            p.setBrush(c)
            p.drawRect(view.band_rect)
        if view.create_rect is not None:
            p.setPen(self._pen(ACCENT, 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            if view.editor.tool == TOOL_ELLIPSE:
                p.drawEllipse(view.create_rect)
            else:
                p.drawRect(view.create_rect)
        del board


class CanvasView(QGraphicsView):
    zoom_changed = Signal(float)
    cursor_moved = Signal(float, float)

    def __init__(self, editor: Editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setBackgroundBrush(QColor("#0B0B0B"))
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.items_by_id: dict[str, NodeItem] = {}
        self.overlay: OverlayItem | None = None
        self.hover_id: str | None = None
        self.snap_lines_x: list[float] = []
        self.snap_lines_y: list[float] = []
        self.band_rect: QRectF | None = None
        self.create_rect: QRectF | None = None
        self.drag_guide_id: str | None = None
        self.drag_guide_pos = 0.0
        self._mode: str | None = None
        self._start = QPointF()
        self._pan_start = QPointF()
        self._space = False
        self._originals: dict = {}
        self._orig_bbox = None
        self._handle = -1
        self._fitted_screen: str | None = None

        editor.document_changed.connect(self.rebuild)
        editor.screen_changed.connect(self._on_screen)
        editor.selection_changed.connect(self._refresh_overlay)
        editor.view_changed.connect(self._on_view_changed)
        editor.preview_changed.connect(self._on_preview)

    # ---------- сцена ----------
    def rebuild(self) -> None:
        s = self.editor.screen()
        if s is None:
            self.scene().clear()
            self.items_by_id, self.overlay = {}, None
            return
        self.items_by_id = build_scene(self.scene(), s, self.editor.artboard_color())
        self.overlay = OverlayItem(self)
        self.scene().addItem(self.overlay)
        margin = max(s.width, s.height) * 4 + 2000
        self.setSceneRect(QRectF(-margin, -margin, s.width + 2 * margin, s.height + 2 * margin))
        if self._fitted_screen != s.id:
            self._fitted_screen = s.id
            self.fit()

    def _on_screen(self) -> None:
        self._fitted_screen = None
        self.rebuild()

    def _on_preview(self) -> None:
        for item in self.items_by_id.values():
            item.sync()
        self._refresh_overlay()

    def _on_view_changed(self) -> None:
        self.viewport().setCursor(self._tool_cursor())
        self._refresh_overlay()

    def _refresh_overlay(self) -> None:
        if self.overlay:
            self.overlay.update()
        self.viewport().update()

    # ---------- масштаб ----------
    def zoom(self) -> float:
        return self.transform().m11()

    def set_zoom(self, value: float, anchor_under_mouse: bool = False) -> None:
        value = max(ZOOM_MIN, min(ZOOM_MAX, value))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse if anchor_under_mouse
                                     else QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setTransform(QTransform.fromScale(value, value))
        self.zoom_changed.emit(value)
        self._refresh_overlay()

    def zoom_step(self, direction: int, under_mouse: bool = False) -> None:
        self.set_zoom(self.zoom() * (1.25 if direction > 0 else 0.8), under_mouse)

    def fit(self) -> None:
        s = self.editor.screen()
        if not s:
            return
        pad = 0.1 * max(s.width, s.height)
        self.fitInView(QRectF(-pad, -pad, s.width + 2 * pad, s.height + 2 * pad), Qt.AspectRatioMode.KeepAspectRatio)
        z = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom()))
        self.setTransform(QTransform.fromScale(z, z))
        self.centerOn(s.width / 2, s.height / 2)
        self.zoom_changed.emit(z)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fitted_screen is None and self.editor.screen():
            self._fitted_screen = self.editor.screen().id
            self.fit()

    # ---------- ввод ----------
    def _tool_cursor(self):
        return {TOOL_HAND: Qt.CursorShape.OpenHandCursor, TOOL_RECT: Qt.CursorShape.CrossCursor,
                TOOL_ELLIPSE: Qt.CursorShape.CrossCursor, TOOL_TEXT: Qt.CursorShape.IBeamCursor,
                }.get(self.editor.tool, Qt.CursorShape.ArrowCursor)

    def _scene_pos(self, event) -> QPointF:
        return self.mapToScene(event.position().toPoint())

    def _handle_at(self, p: QPointF) -> int:
        bb = self.editor.selection_bbox()
        if not bb:
            return -1
        hs = (HANDLE + 4) / self.zoom()
        for i, (fx, fy, _) in enumerate(HANDLES):
            c = QPointF(bb[0] + bb[2] * fx, bb[1] + bb[3] * fy)
            if abs(p.x() - c.x()) <= hs / 2 and abs(p.y() - c.y()) <= hs / 2:
                return i
        return -1

    def _guide_at(self, p: QPointF) -> str | None:
        s = self.editor.screen()
        if not s or not self.editor.guides_visible:
            return None
        tol = 4 / self.zoom()
        for g in reversed(s.guides):
            if abs((p.x() if g.axis == "x" else p.y()) - g.pos) <= tol:
                return g.id
        return None

    def _snap_threshold(self) -> float:
        return 6 / self.zoom()

    def _snap_point(self, p: QPointF) -> QPointF:
        dx, dy, lx, ly = self.editor.snap_rect((p.x(), p.y(), 0, 0), "lt", set(), self._snap_threshold())
        self.snap_lines_x, self.snap_lines_y = lx, ly
        return QPointF(round(p.x() + dx), round(p.y() + dy))

    def mousePressEvent(self, event):
        self.setFocus()
        p = self._scene_pos(event)
        ed = self.editor
        if event.button() == Qt.MouseButton.MiddleButton or (
                event.button() == Qt.MouseButton.LeftButton and (self._space or ed.tool == TOOL_HAND)):
            self._mode = "pan"
            self._pan_start = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if event.button() != Qt.MouseButton.LeftButton or not ed.screen():
            return super().mousePressEvent(event)
        self._start = p
        if ed.tool in (TOOL_RECT, TOOL_ELLIPSE, TOOL_TEXT):
            self._mode = "create"
            self._start = self._snap_point(p)
            self.create_rect = QRectF(self._start, self._start)
            return
        handle = self._handle_at(p)
        if handle >= 0:
            self._mode, self._handle = "resize", handle
            self._begin_transform()
            return
        guide = self._guide_at(p)
        hit = ed.hit(p.x(), p.y())
        if guide and not hit:
            self._mode = "guide"
            self.drag_guide_id = guide
            g = next(g for g in ed.screen().guides if g.id == guide)
            self.drag_guide_pos = g.pos
            return
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if hit:
            if shift:
                sel = [i for i in ed.selection if i != hit] if hit in ed.selection else ed.selection + [hit]
                ed.select(sel)
                self._mode = None
                return
            if hit not in ed.selection:
                ed.select([hit])
            self._mode = "move"
            self._begin_transform()
            return
        if not shift:
            ed.select([], entered_group=None)
        self._mode = "band"
        self.band_rect = QRectF(p, p)

    def _begin_transform(self) -> None:
        self._originals = {n.id: (n.x, n.y, n.w, n.h) for n in self.editor.selected_leaves()}
        self._orig_bbox = self.editor.selection_bbox()

    def mouseMoveEvent(self, event):
        p = self._scene_pos(event)
        self.cursor_moved.emit(p.x(), p.y())
        ed = self.editor
        if self._mode == "pan":
            d = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - d.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - d.y()))
            return
        if self._mode == "move" and self._orig_bbox:
            dx, dy = p.x() - self._start.x(), p.y() - self._start.y()
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                if abs(dx) > abs(dy):
                    dy = 0
                else:
                    dx = 0
            x, y, w, h = self._orig_bbox
            sx, sy, lx, ly = ed.snap_rect((x + dx, y + dy, w, h), "lcrtmb", set(ed.selection), self._snap_threshold())
            dx, dy = round(dx + sx), round(dy + sy)
            self.snap_lines_x, self.snap_lines_y = lx, ly
            ed.preview(self._translated(dx, dy))
            return
        if self._mode == "resize" and self._orig_bbox:
            ed.preview(Editor.scale_changes(self._originals, self._orig_bbox, self._resized_bbox(p, event)))
            return
        if self._mode == "band":
            self.band_rect = QRectF(self._start, p).normalized()
            self._refresh_overlay()
            return
        if self._mode == "create":
            q = self._snap_point(p)
            self.create_rect = QRectF(self._start, q).normalized()
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                side = max(self.create_rect.width(), self.create_rect.height())
                self.create_rect.setSize(QRectF(0, 0, side, side).size())
            self._refresh_overlay()
            return
        if self._mode == "guide":
            s = ed.screen()
            g = next(g for g in s.guides if g.id == self.drag_guide_id)
            self.drag_guide_pos = round(p.x() if g.axis == "x" else p.y())
            self._refresh_overlay()
            return
        # наведение
        if ed.tool == TOOL_SELECT and not self._space:
            h = self._handle_at(p)
            if h >= 0:
                self.viewport().setCursor(HANDLE_CURSORS[h])
            elif self._guide_at(p) and not ed.hit(p.x(), p.y()):
                s = ed.screen()
                gid = self._guide_at(p)
                axis = next(g.axis for g in s.guides if g.id == gid)
                self.viewport().setCursor(Qt.CursorShape.SplitHCursor if axis == "x" else Qt.CursorShape.SplitVCursor)
            else:
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            hover = ed.hit(p.x(), p.y())
            if hover != self.hover_id:
                self.hover_id = hover
                self._refresh_overlay()

    def _translated(self, dx: float, dy: float) -> dict:
        return {nid: {"x": round(x + dx, 2), "y": round(y + dy, 2)} for nid, (x, y, w, h) in self._originals.items()}

    def _resized_bbox(self, p: QPointF, event) -> tuple:
        x, y, w, h = self._orig_bbox
        edges = HANDLES[self._handle][2]
        x1, y1, x2, y2 = x, y, x + w, y + h
        if "l" in edges:
            x1 = p.x()
        if "r" in edges:
            x2 = p.x()
        if "t" in edges:
            y1 = p.y()
        if "b" in edges:
            y2 = p.y()
        snap_edges = "".join(e for e in edges)
        cand = (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
        sx, sy, lx, ly = self.editor.snap_rect(cand, snap_edges.replace("l", "l" if x1 <= x2 else "r"),
                                               set(self.editor.selection), self._snap_threshold())
        if "l" in edges:
            x1 += sx
        if "r" in edges:
            x2 += sx
        if "t" in edges:
            y1 += sy
        if "b" in edges:
            y2 += sy
        self.snap_lines_x, self.snap_lines_y = lx, ly
        nx, ny = min(x1, x2), min(y1, y2)
        nw, nh = max(1.0, abs(x2 - x1)), max(1.0, abs(y2 - y1))
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and w and h and len(edges) == 2:
            ratio = w / h
            if nw / nh > ratio:
                nw = nh * ratio
            else:
                nh = nw / ratio
            if "l" in edges:
                nx = x + w - nw
            if "t" in edges:
                ny = y + h - nh
        return round(nx), round(ny), round(nw), round(nh)

    def mouseReleaseEvent(self, event):
        ed = self.editor
        mode, self._mode = self._mode, None
        p = self._scene_pos(event)
        if mode == "pan":
            self.viewport().setCursor(self._tool_cursor())
        elif mode == "move":
            dx = ed.screen() and tree.node_map(ed.screen())
            changes = {nid: {"x": dx[nid].x, "y": dx[nid].y} for nid in self._originals}
            ed.commit_geometry(self._originals, changes, "Переместить")
        elif mode == "resize":
            m = tree.node_map(ed.screen())
            changes = {nid: {"x": m[nid].x, "y": m[nid].y, "w": m[nid].w, "h": m[nid].h} for nid in self._originals}
            ed.commit_geometry(self._originals, changes, "Изменить размер")
        elif mode == "band" and self.band_rect is not None:
            r = self.band_rect
            ids = ed.ids_in_rect((r.x(), r.y(), r.width(), r.height())) if r.width() > 1 or r.height() > 1 else []
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                ids = ed.selection + [i for i in ids if i not in ed.selection]
            ed.select(ids)
        elif mode == "create" and self.create_rect is not None:
            r = self.create_rect
            kind = {TOOL_RECT: "rect", TOOL_ELLIPSE: "ellipse", TOOL_TEXT: "text"}[ed.tool]
            if r.width() < 3 and r.height() < 3:
                w, h = (200, 40) if kind == "text" else (100, 100)
                rect = (r.x(), r.y(), w, h)
            else:
                rect = (r.x(), r.y(), max(1, r.width()), max(1, r.height()))
            ed.add_node(kind, rect)
            ed.tool = TOOL_SELECT
            ed.view_changed.emit()
        elif mode == "guide" and self.drag_guide_id:
            s = ed.screen()
            limit = s.width if next(g.axis for g in s.guides if g.id == self.drag_guide_id) == "x" else s.height
            outside = self.drag_guide_pos < -40 / self.zoom() or self.drag_guide_pos > limit + 40 / self.zoom()
            ed.move_guide(self.drag_guide_id, None if outside else self.drag_guide_pos)
            self.drag_guide_id = None
        self.band_rect = self.create_rect = None
        self.snap_lines_x, self.snap_lines_y = [], []
        self._originals, self._orig_bbox = {}, None
        self._refresh_overlay()
        del p

    def mouseDoubleClickEvent(self, event):
        ed = self.editor
        if event.button() != Qt.MouseButton.LeftButton or ed.tool != TOOL_SELECT:
            return
        p = self._scene_pos(event)
        hit = ed.hit(p.x(), p.y())
        if not hit:
            return
        node = tree.node_map(ed.screen())[hit]
        if node.is_group:
            ed.select([], entered_group=node.id)
            inner = ed.hit(p.x(), p.y())
            ed.select([inner] if inner else [])
            return
        if node.type == "text":
            text, ok = QInputDialog.getMultiLineText(self, "Текст", "Текст элемента:", node.text)
            if ok and text != node.text:
                ed.set_props({node.id: {"text": text}}, "Изменить текст")

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = math.pow(1.0015, event.angleDelta().y())
            self.set_zoom(self.zoom() * factor, anchor_under_mouse=True)
            return
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - event.angleDelta().y())
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        key, mods = event.key(), event.modifiers()
        ed = self.editor
        if key == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space = True
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            return
        step = 10 if mods & Qt.KeyboardModifier.ShiftModifier else 1
        arrows = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0), Qt.Key.Key_Up: (0, -step),
                  Qt.Key.Key_Down: (0, step)}
        if key in arrows and ed.selection:
            ed.nudge(*arrows[key])
            return
        if key == Qt.Key.Key_Escape:
            if ed.selection:
                ed.select([])
            elif ed.entered_group:
                ed.select([], entered_group=None)
            ed.tool = TOOL_SELECT
            ed.view_changed.emit()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and len(ed.selected_nodes()) == 1 \
                and ed.selected_nodes()[0].is_group:
            g = ed.selected_nodes()[0]
            ed.select([c.id for c in g.children[-1:]], entered_group=g.id)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space = False
            self.viewport().setCursor(self._tool_cursor())
            return
        super().keyReleaseEvent(event)

    def leaveEvent(self, event):
        if self.hover_id:
            self.hover_id = None
            self._refresh_overlay()
        super().leaveEvent(event)


def render_thumbnail(screen: Screen, color: str, w: int, h: int):
    from PySide6.QtGui import QPixmap
    pm = QPixmap(w, h)
    pm.fill(QColor(TOKENS["surface_2"]))
    scene = QGraphicsScene()
    build_scene(scene, screen, color)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    scale = min((w - 8) / screen.width, (h - 8) / screen.height)
    tw, th = screen.width * scale, screen.height * scale
    scene.render(p, QRectF((w - tw) / 2, (h - th) / 2, tw, th), QRectF(0, 0, screen.width, screen.height))
    p.end()
    return pm


__all__ = ["CanvasView", "render_thumbnail", "qcolor", "QCursor", "QPainterPath"]
