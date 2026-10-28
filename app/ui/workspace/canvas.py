"""Холст на QGraphicsView: отрисовка экрана, выделение, перемещение, масштаб, привязки, направляющие."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QCursor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient, QTransform,
)
from PySide6.QtWidgets import (
    QGraphicsBlurEffect, QGraphicsDropShadowEffect, QGraphicsItem, QGraphicsScene, QGraphicsView, QInputDialog,
)

from app.core.document import tree
from app.core.document.model import ELEVATION_DP, Node, Screen
from app.engines.preview.devices import screen_dpi
from app.ui.themes.fusion_amoled import TOKENS
from app.ui.workspace.editor import (
    TOOL_ELLIPSE, TOOL_FRAME, TOOL_HAND, TOOL_PEN, TOOL_RECT, TOOL_SELECT, TOOL_TEXT, Editor,
)

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


_PATH_CACHE: dict[str, QPainterPath] = {}
_RENDER_CACHE: dict[tuple[str, int], object] = {}
MAX_IMAGE_SIDE = 8192


def vector_path(n: Node) -> QPainterPath:
    from app.core.document import pathdata
    base = _PATH_CACHE.get(n.path)
    if base is None:
        base = QPainterPath()
        try:
            for s in pathdata.parse(n.path) if n.path else []:
                if s[0] == "M":
                    base.moveTo(s[1], s[2])
                elif s[0] == "L":
                    base.lineTo(s[1], s[2])
                elif s[0] == "C":
                    base.cubicTo(*s[1:])
                else:
                    base.closeSubpath()
        except pathdata.PathError:
            pass
        if len(_PATH_CACHE) > 5000:
            _PATH_CACHE.clear()
        _PATH_CACHE[n.path] = base
    path = QTransform().translate(n.x, n.y).scale(n.w / n.vb_w if n.vb_w else 1,
                                                  n.h / n.vb_h if n.vb_h else 1).map(base)
    path.setFillRule(Qt.FillRule.OddEvenFill if n.fill_rule == "evenodd" else Qt.FillRule.WindingFill)
    return path


def _renderer(asset, data: bytes):
    """Рендерер ресурса: QSvgRenderer для SVG (уже очищенного при импорте) или QImage для растра."""
    key = (asset.sha256, len(data))
    r = _RENDER_CACHE.get(key)
    if r is None:
        from PySide6.QtCore import QByteArray
        if asset.ext == "svg":
            from PySide6.QtSvg import QSvgRenderer
            r = QSvgRenderer(QByteArray(data))
        else:
            from PySide6.QtGui import QImageReader
            from PySide6.QtCore import QBuffer, QIODevice
            buf = QBuffer()
            buf.setData(QByteArray(data))
            buf.open(QIODevice.OpenModeFlag.ReadOnly)
            reader = QImageReader(buf)
            size = reader.size()
            if size.width() > MAX_IMAGE_SIDE or size.height() > MAX_IMAGE_SIDE:
                r = False  # защита от «бомб» распаковки изображения
            else:
                r = reader.read()
        if len(_RENDER_CACHE) > 500:
            _RENDER_CACHE.clear()
        _RENDER_CACHE[key] = r
    return r


def _paint_missing(p: QPainter, rect: QRectF, text: str) -> None:
    pen = QPen(QColor(TOKENS["danger"]), 1, Qt.PenStyle.DashLine)
    pen.setCosmetic(True)
    p.setPen(pen)
    p.setBrush(QColor(229, 72, 77, 30))
    p.drawRect(rect)
    p.drawLine(rect.topLeft(), rect.bottomRight())
    p.drawLine(rect.topRight(), rect.bottomLeft())
    if rect.width() > 60:
        f = QFont(TOKENS["font"])
        f.setPixelSize(max(8, min(14, int(rect.height() / 6))))
        p.setFont(f)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


def fill_brush(n: Node, rect: QRectF):
    """Заливка узла: цвет или градиент от fill к fill2 (угол как в CSS: 180° — сверху вниз)."""
    if not n.fill:
        return Qt.BrushStyle.NoBrush
    if n.gradient == "none" or not n.fill2 or n.type == "text":
        return QBrush(qcolor(n.fill))
    if n.gradient == "radial":
        g = QRadialGradient(rect.center(), max(rect.width(), rect.height()) / 2)
    else:
        a = math.radians(n.grad_angle)
        dx, dy = math.sin(a), -math.cos(a)
        half = (abs(rect.width() * dx) + abs(rect.height() * dy)) / 2
        c = rect.center()
        g = QLinearGradient(c - QPointF(dx * half, dy * half), c + QPointF(dx * half, dy * half))
    g.setColorAt(0, qcolor(n.fill))
    g.setColorAt(1, qcolor(n.fill2))
    return QBrush(g)


def apply_effects(item: QGraphicsItem, n: Node, k: float) -> None:
    """Тень уровня Material 3 или размытие слоя (у элемента сцены может быть один эффект; размытие важнее);
    масштаб и поворот — вокруг центра элемента, вместе с содержимым."""
    item.setTransformOriginPoint(n.x + n.w / 2, n.y + n.h / 2)
    item.setScale(n.scale)
    item.setRotation(n.rotation)
    if n.blur > 0:
        eff = item.graphicsEffect()
        if not isinstance(eff, QGraphicsBlurEffect):
            eff = QGraphicsBlurEffect()
            item.setGraphicsEffect(eff)
        eff.setBlurRadius(n.blur)
    elif n.elevation > 0:
        e = ELEVATION_DP[n.elevation] * k
        eff = item.graphicsEffect()
        if not isinstance(eff, QGraphicsDropShadowEffect):
            eff = QGraphicsDropShadowEffect()
            item.setGraphicsEffect(eff)
        eff.setBlurRadius(2.2 * e + 2 * k)
        eff.setOffset(0, max(1.0, 0.6 * e))
        eff.setColor(QColor(0, 0, 0, 110))
    elif item.graphicsEffect() is not None:
        item.setGraphicsEffect(None)


def _fit_rects(rect: QRectF, iw: int, ih: int, fit: str) -> tuple[QRectF, QRectF]:
    """Куда и какую часть картинки рисовать: fill — растянуть, cover — заполнить и обрезать по центру,
    contain — вписать целиком с полями."""
    if fit == "cover" and iw > 0 and ih > 0:
        k = max(rect.width() / iw, rect.height() / ih)
        sw, sh = rect.width() / k, rect.height() / k
        return rect, QRectF((iw - sw) / 2, (ih - sh) / 2, sw, sh)
    if fit == "contain" and iw > 0 and ih > 0:
        k = min(rect.width() / iw, rect.height() / ih)
        dw, dh = iw * k, ih * k
        return QRectF(rect.x() + (rect.width() - dw) / 2, rect.y() + (rect.height() - dh) / 2, dw, dh), \
            QRectF(0, 0, iw, ih)
    return rect, QRectF(0, 0, iw, ih)


def paint_node(p: QPainter, n: Node, assets=None) -> None:
    rect = QRectF(n.x, n.y, n.w, n.h)
    p.save()
    p.setOpacity(p.opacity() * n.opacity)
    p.setBrush(fill_brush(n, rect))
    if n.stroke and n.stroke_width > 0:
        pen = QPen(qcolor(n.stroke), n.stroke_width)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
    else:
        p.setPen(Qt.PenStyle.NoPen)
    if n.type == "vector":
        p.drawPath(vector_path(n))
    elif n.type == "image":
        found = assets(n.asset_id) if assets and n.asset_id else None
        if found is None:
            _paint_missing(p, rect, "нет ресурса")
        else:
            asset, data = found
            r = _renderer(asset, data)
            if r is False or r is None or (hasattr(r, "isNull") and r.isNull()) or \
                    (hasattr(r, "isValid") and not r.isValid()):
                _paint_missing(p, rect, "не читается")
            else:
                if n.radius > 0:  # маска: скругление или круг (радиус = половина стороны)
                    clip = QPainterPath()
                    rr = min(n.radius, n.w / 2, n.h / 2)
                    clip.addRoundedRect(rect, rr, rr)
                    p.setClipPath(clip, Qt.ClipOperation.IntersectClip)
                if asset.ext == "svg":
                    r.render(p, rect)
                else:
                    dst, src = _fit_rects(rect, r.width(), r.height(), n.fit)
                    p.drawImage(dst, r, src)
    elif n.type == "ellipse":
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
    def __init__(self, node: Node, assets=None, k: float = 1.0):
        super().__init__()
        self.node = node
        self.assets = assets
        self.k = k  # пикселей в dp — для теней
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, False)
        apply_effects(self, node, k)

    def boundingRect(self) -> QRectF:
        n = self.node
        m = n.stroke_width / 2 + 1
        return QRectF(n.x, n.y, n.w, n.h).adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        n = self.node
        path = QPainterPath()
        r = min(n.radius, n.w / 2, n.h / 2)
        path.addRoundedRect(QRectF(n.x, n.y, n.w, n.h), r, r)
        return path

    def sync(self) -> None:
        self.prepareGeometryChange()
        apply_effects(self, self.node, self.k)
        self.update()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_node(painter, self.node, self.assets)


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


def asset_lookup(doc):
    """Функция id → (Asset, bytes) или None для отрисовки изображений документа."""
    if doc is None:
        return None

    def lookup(asset_id):
        a = doc.asset(asset_id)
        data = doc.asset_data.get(asset_id) if a else None
        return (a, data) if data is not None else None
    return lookup


def build_scene(scene: QGraphicsScene, screen: Screen, artboard_color: str, assets=None) -> dict[str, NodeItem]:
    scene.clear()
    scene.addItem(ArtboardItem(screen, artboard_color))
    items: dict[str, NodeItem] = {}
    k = screen_dpi(screen) / 160 if screen.platform == "android" else 1.0

    def rec(nodes, visible, parent_item):
        for n in nodes:
            v = visible and n.visible
            if n.is_group:
                rec(n.children, v, parent_item)
            elif v:
                item = NodeItem(n, assets, k)
                if parent_item is not None:
                    item.setParentItem(parent_item)
                else:
                    scene.addItem(item)
                items[n.id] = item
                if n.is_frame:
                    # дети фрейма — дочерние элементы сцены, чтобы работала обрезка по форме фрейма
                    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, n.clip)
                    rec(n.children, v, item)
    rec(screen.nodes, True, None)
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
        if view.pen_points:
            p.setPen(self._pen(ACCENT, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            pts = [QPointF(x, y) for x, y in view.pen_points]
            if view.pen_hover:
                pts.append(QPointF(*view.pen_hover))
            for a, b in zip(pts, pts[1:]):
                p.drawLine(a, b)
            hs = 6 / scale
            p.setBrush(QColor("#FFFFFF"))
            for x, y in view.pen_points:
                p.drawRect(QRectF(x - hs / 2, y - hs / 2, hs, hs))
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
    context_menu = Signal(object)  # глобальная точка: страница показывает меню действий с выделенным
    files_dropped = Signal(list, float, float)  # картинки из проводника: пути и точка экрана

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
        self.setAcceptDrops(True)
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
        self._reorder_id: str | None = None
        self.pen_points: list[tuple[float, float]] = []
        self.pen_hover: tuple[float, float] | None = None
        self._fitted_screen: str | None = None
        self._auto_fit = True  # экран «целиком» подстраивается под размер окна, пока масштаб не меняли вручную

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
        self.items_by_id = build_scene(self.scene(), s, self.editor.artboard_color(), asset_lookup(self.editor.doc))
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

    def set_zoom(self, value: float, anchor_under_mouse: bool = False, view_pos=None) -> None:
        """Масштаб с неподвижной точкой: под курсором (колесо с Ctrl) или в центре окна (кнопки, клавиши).

        Точка привязки считается вручную: встроенная привязка Qt берёт последнее движение мыши, которое холст
        не передаёт, и экран «уплывал» вправо при увеличении."""
        value = max(ZOOM_MIN, min(ZOOM_MAX, value))
        self._auto_fit = False
        vp = self.viewport()
        pos = vp.rect().center()
        if anchor_under_mouse:
            p = view_pos if view_pos is not None else vp.mapFromGlobal(QCursor.pos())
            if vp.rect().contains(p):
                pos = p
        target = self.mapToScene(pos)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setTransform(QTransform.fromScale(value, value))
        drift = self.mapFromScene(target) - pos
        h, v = self.horizontalScrollBar(), self.verticalScrollBar()
        h.setValue(h.value() + drift.x())
        v.setValue(v.value() + drift.y())
        self.zoom_changed.emit(value)
        self._refresh_overlay()

    def zoom_step(self, direction: int, under_mouse: bool = False) -> None:
        self.set_zoom(self.zoom() * (1.25 if direction > 0 else 0.8), under_mouse)

    def fit(self) -> None:
        s = self.editor.screen()
        if not s:
            return
        pad = 0.04 * max(s.width, s.height)  # экран крупнее: поля вокруг небольшие
        self.fitInView(QRectF(-pad, -pad, s.width + 2 * pad, s.height + 2 * pad), Qt.AspectRatioMode.KeepAspectRatio)
        z = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom()))
        self.setTransform(QTransform.fromScale(z, z))
        self.centerOn(s.width / 2, s.height / 2)
        self._auto_fit = True
        self.zoom_changed.emit(z)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.editor.screen() and (self._fitted_screen is None or self._auto_fit):
            self._fitted_screen = self.editor.screen().id
            self.fit()

    # ---------- ввод ----------
    def _tool_cursor(self):
        return {TOOL_HAND: Qt.CursorShape.OpenHandCursor, TOOL_RECT: Qt.CursorShape.CrossCursor,
                TOOL_ELLIPSE: Qt.CursorShape.CrossCursor, TOOL_FRAME: Qt.CursorShape.CrossCursor, TOOL_PEN: Qt.CursorShape.CrossCursor, TOOL_TEXT: Qt.CursorShape.IBeamCursor,
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
        if ed.tool == TOOL_PEN:
            q = self._snap_point(p)
            pts = self.pen_points
            if len(pts) >= 3 and math.hypot(q.x() - pts[0][0], q.y() - pts[0][1]) * self.zoom() <= 8:
                self.finish_pen(closed=True)  # щелчок по первой точке замыкает контур
            else:
                pts.append((q.x(), q.y()))
                self._refresh_overlay()
            return
        if ed.tool in (TOOL_RECT, TOOL_ELLIPSE, TOOL_TEXT, TOOL_FRAME):
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
        self.editor.begin_preview()
        sel = self.editor.selection
        # перетаскивание ребёнка Auto Layout — это перестановка, а не свободное перемещение
        self._reorder_id = sel[0] if len(sel) == 1 and self.editor.auto_layout_parent(sel[0]) else None

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
            if self._reorder_id:
                self.snap_lines_x, self.snap_lines_y = [], []
                ed.preview(self._translated(dx, dy), keep=set(self._originals))
            else:
                ed.preview(self._translated(dx, dy))
            return
        if self._mode == "resize" and self._orig_bbox:
            ed.preview(Editor.scale_changes(self._originals, self._orig_bbox, self._resized_bbox(p, event)))
            return
        if self._mode == "band":
            self.band_rect = QRectF(self._start, p).normalized()
            self._refresh_overlay()
            return
        if ed.tool == TOOL_PEN and self.pen_points:
            self.pen_hover = (p.x(), p.y())
            self._refresh_overlay()
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
        elif mode == "move" and self._reorder_id:
            moved = math.hypot(p.x() - self._start.x(), p.y() - self._start.y()) * self.zoom() >= 3
            if moved:
                ed.drop_in_auto_layout(self._reorder_id, (p.x(), p.y()))
            else:
                ed.commit_geometry(self._originals, {}, "Переместить")  # просто клик — вернуть как было
        elif mode == "move":
            m = tree.node_map(ed.screen())
            changes = {nid: {"x": m[nid].x, "y": m[nid].y} for nid in self._originals}
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
            kind = {TOOL_RECT: "rect", TOOL_ELLIPSE: "ellipse", TOOL_TEXT: "text", TOOL_FRAME: "frame"}[ed.tool]
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

    def finish_pen(self, closed: bool = False) -> None:
        pts, self.pen_points, self.pen_hover = self.pen_points, [], None
        pts = [pt for i, pt in enumerate(pts) if i == 0 or pt != pts[i - 1]]  # двойной клик даёт повтор точки
        if len(pts) >= 2:
            self.editor.add_vector(pts, closed)
        self._refresh_overlay()

    def mouseDoubleClickEvent(self, event):
        ed = self.editor
        if ed.tool == TOOL_PEN:
            self.finish_pen(closed=False)
            return
        if event.button() != Qt.MouseButton.LeftButton or ed.tool != TOOL_SELECT:
            return
        p = self._scene_pos(event)
        hit = ed.hit(p.x(), p.y())
        if not hit:
            return
        node = tree.node_map(ed.screen())[hit]
        if node.is_instance and ed.isolate_instances:
            ed.open_component.emit(node.component_id)  # Component Builder: изолировать вложенный компонент
            return
        if node.is_container:
            ed.select([], entered_group=node.id)
            inner = ed.hit(p.x(), p.y())
            ed.select([inner] if inner else [])
            return
        if node.type == "text":
            text, ok = QInputDialog.getMultiLineText(self, "Текст", "Текст элемента:", node.text)
            if ok and text != node.text:
                ed.set_props({node.id: {"text": text}}, "Изменить текст")

    # ---------- перетаскивание заготовки из галереи ----------
    @staticmethod
    def _image_paths(md) -> list[str]:
        from app.ui.workspace.images import IMAGE_SUFFIXES
        return [u.toLocalFile() for u in md.urls() if u.isLocalFile()
                and u.toLocalFile().lower().endswith(IMAGE_SUFFIXES)] if md.hasUrls() else []

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if (md.hasFormat("application/x-ads-component") or self._image_paths(md)) and self.editor.screen():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-ads-component") or self._image_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        md = event.mimeData()
        paths = self._image_paths(md)
        if paths:  # фото из проводника — в точку отпускания
            p = self.mapToScene(event.position().toPoint())
            self.files_dropped.emit(paths, p.x(), p.y())
            event.acceptProposedAction()
            return
        if not md.hasFormat("application/x-ads-component"):
            return super().dropEvent(event)
        kind = bytes(md.data("application/x-ads-component")).decode("utf-8")
        p = self.mapToScene(event.position().toPoint())
        self.editor.insert_component(kind, at=(p.x(), p.y()))
        event.acceptProposedAction()
        self.setFocus()

    def contextMenuEvent(self, event):
        ed = self.editor
        if not ed.screen():
            return
        p = self.mapToScene(event.pos())
        nid = ed.hit(p.x(), p.y(), 4 / self.zoom())
        if nid and nid not in ed.selection:
            ed.select([nid])
        elif not nid:
            ed.select([])
        self.context_menu.emit(event.globalPos())

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y() or event.angleDelta().x()
            factor = math.pow(1.0015, delta)
            self.set_zoom(self.zoom() * factor, anchor_under_mouse=True, view_pos=event.position().toPoint())
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
        if ed.tool == TOOL_PEN and self.pen_points and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter,
                                                               Qt.Key.Key_Escape):
            if key == Qt.Key.Key_Escape:
                self.pen_points, self.pen_hover = [], None
                self._refresh_overlay()
            else:
                self.finish_pen(closed=False)
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
                and ed.selected_nodes()[0].is_container:
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


def render_thumbnail(screen: Screen, color: str, w: int, h: int, doc=None, bg: str | None = None):
    from PySide6.QtGui import QPixmap
    pm = QPixmap(w, h)
    pm.fill(QColor(bg or TOKENS["surface_2"]))
    scene = QGraphicsScene()
    build_scene(scene, screen, color, asset_lookup(doc))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    scale = min((w - 8) / screen.width, (h - 8) / screen.height)
    tw, th = screen.width * scale, screen.height * scale
    scene.render(p, QRectF((w - tw) / 2, (h - th) / 2, tw, th), QRectF(0, 0, screen.width, screen.height))
    p.end()
    return pm


__all__ = ["CanvasView", "render_thumbnail", "qcolor", "QCursor", "QPainterPath"]
