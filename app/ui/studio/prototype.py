"""Проигрыватель прототипа на устройстве предпросмотра: экраны, логика, анимации, переходы, жесты, ввод.

Экран перестраивается под выбранное устройство (размер, ориентация, плотность) движком раскладки и рисуется
внутри рамки устройства: строка состояния, вырез, жестовая панель (Android) или заголовок окна (Windows).
Это симуляция, а не сборка APK/EXE: отрисовка Android — приближение Compose, ограничения перечислены в
app.engines.preview.devices.SIMULATION_LIMITS.

Время идёт по «виртуальным часам»: на странице — от таймера, в тестах — вызовом advance(мс), поэтому
воспроизведение повторяемо. Жесты (двойное касание, свайпы, долгое нажатие) тоже меряются этими часами.
"""

from __future__ import annotations

import copy

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QVBoxLayout, QWidget

from app.core.document import tree
from app.core.document.model import PLATFORM_ANDROID, Screen
from app.engines.animation import engine as anim
from app.engines.logic.engine import Interpreter, format_value
from app.engines.logic.runtime import apply_samples, compose, state_transition
from app.engines.material.color import scheme
from app.engines.preview import live
from app.engines.preview.devices import TITLE_BAR, ViewSpec, adapt, default_profile
from app.ui.themes.fusion_amoled import TOKENS
from app.ui.workspace.canvas import asset_lookup, build_scene

LONG_PRESS_MS = 550
DOUBLE_TAP_MS = 300
SWIPE_DP = 32         # минимальная длина свайпа
SLOP_PX = 8           # экранных пикселей до начала перетаскивания
WHEEL_DP = 48         # прокрутка колесом за один щелчок
RIPPLE_MS = 450       # волна нажатия
KEY_ROWS = ("йцукенгшщзхъ", "фывапролджэ", "ячсмитьбю")
KEY_BACK, KEY_SPACE, KEY_DONE = "⌫", "␣", "⏎"
TRANSITION_RU = {"none": "без перехода", "fade": "затухание", "slide_left": "сдвиг влево",
                 "slide_right": "сдвиг вправо", "slide_up": "сдвиг вверх", "slide_down": "сдвиг вниз"}
STAGE_BG = QColor("#0B0B0B")


class _Transition:
    def __init__(self, from_pm: QPixmap, to_pm: QPixmap, kind: str, duration: int, easing: str, start: float):
        self.from_pm, self.to_pm, self.kind = from_pm, to_pm, kind
        self.duration, self.easing, self.start = max(1, duration), easing, start

    def progress(self, now: float) -> float:
        return anim.ease(self.easing, (now - self.start) / self.duration)

    def done(self, now: float) -> bool:
        return now - self.start >= self.duration


# ---------- рамка устройства (общая для проигрывателя и миниатюр сравнения) ----------
def bezel(screen: Screen, spec: ViewSpec) -> float:
    u = spec.units(screen)
    return {"phone": 12, "foldable": 14, "tablet": 18}.get(spec.profile.kind, 0) * u


def frame_rect(screen: Screen, spec: ViewSpec) -> QRectF:
    """Прямоугольник устройства с рамкой в координатах экрана (экран — от 0,0)."""
    if spec.profile.platform == PLATFORM_ANDROID:
        b = bezel(screen, spec)
        return QRectF(-b, -b, screen.width + 2 * b, screen.height + 2 * b)
    t = TITLE_BAR * spec.units(screen)
    return QRectF(-1, -t - 1, screen.width + 2, screen.height + t + 2)


def _ink(color: str) -> QColor:
    c = QColor(color or "#000000")
    return QColor("#000000") if 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue() > 150 else QColor("#FFFFFF")


def paint_device(p: QPainter, screen: Screen, spec: ViewSpec, artboard: str, title: str,
                 show_safe: bool = False) -> None:
    """Системные панели, безопасные области и рамка поверх содержимого экрана (координаты экрана)."""
    W, H = screen.width, screen.height
    u = spec.units(screen)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if spec.profile.platform == PLATFORM_ANDROID:
        ins = spec.insets(screen)
        ink = _ink(artboard)
        if show_safe:
            band = QColor(255, 255, 255, 26) if ink.lightness() > 128 else QColor(0, 0, 0, 26)
            pen = QPen(QColor(ink.red(), ink.green(), ink.blue(), 110), 1.0 * u, Qt.PenStyle.DashLine)
            for r in (QRectF(0, 0, W, ins.top), QRectF(0, H - ins.bottom, W, ins.bottom),
                      QRectF(0, 0, ins.left, H), QRectF(W - ins.right, 0, ins.right, H)):
                if r.width() > 0 and r.height() > 0:
                    p.fillRect(r, band)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(ins.left, ins.top, W - ins.left - ins.right, H - ins.top - ins.bottom))
        # строка состояния: время, сеть, батарея
        p.setPen(ink)
        f = QFont("Segoe UI")
        f.setPixelSize(max(1, round(13 * u)))
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        sb = QRectF(ins.left + 16 * u, 0, W - ins.left - 32 * u, ins.top)
        p.drawText(sb, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "12:30")
        cy = ins.top / 2
        bx = W - 16 * u - 20 * u
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(ink, 1.2 * u))
        p.drawRoundedRect(QRectF(bx, cy - 5 * u, 18 * u, 10 * u), 2 * u, 2 * u)
        p.fillRect(QRectF(bx + 2 * u, cy - 3 * u, 11 * u, 6 * u), ink)
        p.fillRect(QRectF(bx + 18.5 * u, cy - 2 * u, 1.8 * u, 4 * u), ink)
        for i in range(4):  # уровень сигнала
            h = (3 + 2 * i) * u
            p.fillRect(QRectF(bx - 26 * u + i * 4 * u, cy + 5 * u - h, 2.6 * u, h), ink)
        if spec.profile.cutout:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#000000"))
            if ins.left:
                p.drawEllipse(QPointF(ins.left / 2, H / 2), 6 * u, 6 * u)
            else:
                p.drawEllipse(QPointF(W / 2, cy), 6 * u, 6 * u)
        # жестовая панель
        pw = min(108 * u, W * 0.3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ink)
        p.drawRoundedRect(QRectF((W - pw) / 2, H - ins.bottom / 2 - 2 * u, pw, 4 * u), 2 * u, 2 * u)
        # рамка: кольцо вокруг экрана со скруглением углов дисплея
        b = bezel(screen, spec)
        r = spec.profile.corner_dp * u
        outer, inner = QPainterPath(), QPainterPath()
        outer.addRoundedRect(QRectF(-b, -b, W + 2 * b, H + 2 * b), r + b, r + b)
        inner.addRoundedRect(QRectF(0, 0, W, H), r, r)
        p.fillPath(outer.subtracted(inner), QColor("#151515"))
        p.setPen(QPen(QColor("#3A3A3A"), 1.5 * u))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(outer)
        if spec.profile.kind == "foldable" and W < H * 1.2:
            p.setPen(QPen(QColor(255, 255, 255, 16), 1.0 * u))
            p.drawLine(QPointF(W / 2, 0), QPointF(W / 2, H))
    else:
        t = TITLE_BAR * u
        bar = QRectF(0, -t, W, t)
        p.fillRect(bar, QColor("#202020"))
        p.setPen(QColor("#E6E6E6"))
        f = QFont("Segoe UI")
        f.setPixelSize(max(1, round(12 * u)))
        p.setFont(f)
        p.drawText(bar.adjusted(12 * u, 0, -150 * u, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   title)
        for i, g in enumerate(("—", "☐", "✕")):  # изображение рамки окна, не элементы управления
            p.drawText(QRectF(W - (3 - i) * 46 * u, -t, 46 * u, t), Qt.AlignmentFlag.AlignCenter, g)
        p.setPen(QPen(QColor("#3A3A3A"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(-0.5, -t - 0.5, W + 1, H + t + 1))
    p.restore()


class PlayerView(QGraphicsView):
    def __init__(self, player: "PrototypePlayer"):
        super().__init__()
        self.player = player
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setBackgroundBrush(STAGE_BG)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.player.fit()

    def _pt(self, e) -> QPointF:
        return self.mapToScene(e.position().toPoint())

    def mousePressEvent(self, e):
        self.setFocus()
        if e.button() == Qt.MouseButton.LeftButton:
            self.player.press(self._pt(e))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.player.release(self._pt(e))

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self.player.drag(self._pt(e))
        else:
            self.player.hover(self._pt(e))

    def wheelEvent(self, e):
        d = e.angleDelta()
        horizontal = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier) or (d.x() and not d.y())
        self.player.wheel(self._pt(e), (d.x() or d.y()) if horizontal else d.y(), horizontal)

    def keyPressEvent(self, e):
        if not self.player.key(e.key(), e.text()):
            super().keyPressEvent(e)

    def leaveEvent(self, e):
        self.player.hover(None)
        super().leaveEvent(e)

    def drawForeground(self, p: QPainter, rect):
        self.player.paint_overlay(p)


class PrototypePlayer(QWidget):
    changed = Signal()

    def __init__(self, editor, parent=None, start_screen_id: str | None = None):
        super().__init__(parent)
        self.editor = editor
        self.doc = editor.doc
        self.engine = editor.engine
        self.reduced_motion = False
        self.touch_mode = False       # касание: нет наведения, след пальца; иначе мышь
        self.show_safe = False
        self.device_chrome = True     # рамка и системные панели устройства (в песочнице компонента — нет)
        self.specs: dict[str, ViewSpec] = {}   # платформа → устройство
        self.now = 0.0
        self.active: list[tuple[object, float]] = []   # (Animation, время старта)
        self.persist: dict[str, dict] = {}             # итоговые значения закончившихся анимаций
        self.transition: _Transition | None = None
        self.hover_id: str | None = None
        self.pressed: tuple[str, str] | None = None     # (узел, исходная точка-узел) нажатия
        self._press_state: str | None = None
        self._press_pos: QPointF | None = None
        self._long_fired = False
        self._dragging = False
        self._drag: tuple[str, float, str] | None = None   # (фрейм, исходное смещение, ось)
        self._last_tap: tuple[str, float] | None = None
        self._kb_key: str | None = None
        self._grabbing = False
        self._cache: dict = {}
        self.scroll: dict[str, float] = {}
        self.scroll_max: dict[str, float] = {}
        self.live: dict[str, object] = {}     # живые компоненты Material 3: корень → включено / пункт / доля
        self.ripple: tuple[QPointF, QRectF, float, float] | None = None  # центр, область, скругление, начало
        self._tap_pt: QPointF | None = None
        self.focus_id: str | None = None
        self.screen: Screen | None = None
        self.spec: ViewSpec | None = None
        self.layout_diags: list = []
        self.effect_log: list[str] = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.view = PlayerView(self)
        v.addWidget(self.view)
        self._long = QTimer(self)
        self._long.setSingleShot(True)
        self._long.timeout.connect(self._long_press)
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.interp = Interpreter(self.doc, start_screen_id or editor.screen_id)
        self._after_effects(self.interp.effects)
        self.render(fit=True)

    # ---------- время ----------
    def start_clock(self) -> None:
        self._clock.start()
        self._timer.start()

    def stop_clock(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self.advance(float(self._clock.restart()))

    def advance(self, ms: float) -> None:
        self.now += ms
        busy = bool(self.active) or self.transition is not None
        rippling = self.ripple is not None
        if rippling and self.now - self.ripple[3] > RIPPLE_MS:
            self.ripple = None
        if self.transition is not None and self.transition.done(self.now):
            self.transition = None
        still = []
        for a, start in self.active:
            if anim.finished(a, self.now - start, self.reduced_motion):
                for nid, props in anim.sample(a, a.duration, True).items():
                    if a.name != "переход состояния":
                        self.persist.setdefault(nid, {}).update(props)
            else:
                still.append((a, start))
        self.active = still
        if busy:
            self.render()
        elif rippling:
            self.view.viewport().update()

    def samples(self) -> dict:
        out = copy.deepcopy(self.persist)
        for a, start in self.active:
            for nid, props in anim.sample(a, self.now - start, self.reduced_motion).items():
                out.setdefault(nid, {}).update(props)
        return out

    # ---------- устройство ----------
    def effective_spec(self) -> ViewSpec | None:
        src = self.interp.screen()
        if src is None:
            return None
        return self.specs.get(src.platform) or ViewSpec(default_profile(src))

    def set_spec(self, spec: ViewSpec) -> None:
        self.specs[spec.profile.platform] = spec
        self.scroll = {}
        self.render(fit=True)

    def set_option(self, name: str, value: bool) -> None:
        setattr(self, name, value)
        if name == "touch_mode" and value:
            self.hover(None)
        self.view.setCursor(_touch_cursor() if self.touch_mode else Qt.CursorShape.ArrowCursor)
        self.render()

    def static_screen(self, spec: ViewSpec) -> tuple[Screen | None, list]:
        """Текущее состояние на другом устройстве (миниатюры сравнения): без прокрутки и нажатия."""
        return self._base(spec, self.interp.state)

    def _base(self, spec: ViewSpec | None, state) -> tuple[Screen | None, list]:
        if spec is None:
            return None, []
        key = (state.digest(), spec)
        hit = self._cache.get(key)
        if hit is None:
            composed = compose(self.doc, state, self.engine, None)
            if composed is None:
                return None, []
            adapted, diags = adapt(composed, spec, self.engine)
            hit = (adapted.to_dict(), diags)
            if len(self._cache) > 48:
                self._cache.clear()
            self._cache[key] = hit
        screen = Screen.from_dict(hit[0])
        apply_samples(screen, self.samples())
        if self.live:
            ap = self.doc.meta.appearance
            live.apply(screen, self.live, scheme(ap.accent, ap.theme != "light"), spec.units(screen))
        return screen, hit[1]

    # ---------- отрисовка ----------
    def render(self, fit: bool = False) -> None:
        state = self.interp.state
        if self.pressed and self._press_state:
            state = copy.deepcopy(state)
            state.states[self.pressed[0]] = self._press_state
        self.spec = self.effective_spec()
        screen, self.layout_diags = self._base(self.spec, state)
        self.screen = screen
        if screen is None:
            self.view.scene().clear()
            return
        self._apply_scroll(screen)
        build_scene(self.view.scene(), screen, self.editor.artboard_color(), asset_lookup(self.doc))
        fr = frame_rect(screen, self.spec)
        m = 24 * self.spec.units(screen)
        self.view.setSceneRect(fr.adjusted(-m, -m, m, m))
        if fit:
            self.fit()
        self.view.viewport().update()
        self.changed.emit()

    def _apply_scroll(self, screen: Screen) -> None:
        self.scroll_max = {}

        def rec(nodes):
            for n in nodes:
                if not n.is_container:
                    continue
                if n.is_frame and n.scroll != "none" and n.children:
                    leaves = [c for c, _, _ in tree.walk(n.children) if not c.is_group]
                    if n.scroll == "vertical":
                        extent = max((c.y + c.h for c in leaves), default=n.y) - n.y + n.pad_b
                        size = n.h
                    else:
                        extent = max((c.x + c.w for c in leaves), default=n.x) - n.x + n.pad_r
                        size = n.w
                    mx = max(0.0, extent - size)
                    self.scroll_max[n.id] = mx
                    off = min(max(self.scroll.get(n.id, 0.0), 0.0), mx)
                    self.scroll[n.id] = off
                    if off:
                        for c, _, _ in tree.walk(n.children):
                            if n.scroll == "vertical":
                                c.y -= off
                            else:
                                c.x -= off
                rec(n.children)
        rec(screen.nodes)

    def fit(self) -> None:
        if self.screen is not None and self.spec is not None:
            m = 24 * self.spec.units(self.screen)
            self.view.fitInView(frame_rect(self.screen, self.spec).adjusted(-m, -m, m, m),
                                Qt.AspectRatioMode.KeepAspectRatio)

    def _scale(self) -> float:
        return self.view.transform().m11() or 1.0

    def frame(self) -> QPixmap:
        """Снимок только экрана (без рамки и системных панелей) — для переходов."""
        if self.screen is None:
            return self.view.viewport().grab()
        r = self.view.mapFromScene(QRectF(0, 0, self.screen.width, self.screen.height)).boundingRect()
        self._grabbing = True
        try:
            return self.view.viewport().grab(r)
        finally:
            self._grabbing = False

    def paint_overlay(self, p: QPainter) -> None:
        s, spec = self.screen, self.spec
        if self._grabbing or s is None or spec is None:
            return
        W, H = s.width, s.height
        u = spec.units(s)
        t = self.transition
        if t is not None:
            pr = t.progress(self.now)
            target = QRectF(0, 0, W, H)
            p.save()
            p.setClipRect(target)
            if t.kind == "fade":
                p.fillRect(target, STAGE_BG)
                p.setOpacity(1 - pr)
                p.drawPixmap(target, t.from_pm, QRectF(t.from_pm.rect()))
                p.setOpacity(pr)
                p.drawPixmap(target, t.to_pm, QRectF(t.to_pm.rect()))
            else:
                dx, dy = {"slide_left": (-W, 0), "slide_right": (W, 0), "slide_up": (0, -H),
                          "slide_down": (0, H)}.get(t.kind, (0, 0))
                p.fillRect(target, STAGE_BG)
                p.drawPixmap(target.translated(dx * pr, dy * pr), t.from_pm, QRectF(t.from_pm.rect()))
                p.drawPixmap(target.translated(-dx * (1 - pr), -dy * (1 - pr)), t.to_pm, QRectF(t.to_pm.rect()))
            p.restore()
        m = tree.node_map(s)
        if self.focus_id in m and t is None:  # фокус поля ввода — акцентом (только фокус и выбор)
            n = m[self.focus_id]
            p.save()
            p.setPen(QPen(QColor(TOKENS["accent"]), 2 * u))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(n.x - 3 * u, n.y - 3 * u, n.w + 6 * u, n.h + 6 * u), 4 * u, 4 * u)
            p.restore()
        if self.keyboard_visible():
            self._paint_keyboard(p, s, u)
        if self.ripple is not None and t is None:
            self._paint_ripple(p)
        if self.touch_mode and self._press_pos is not None:
            p.save()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 70))
            p.drawEllipse(self._press_pos, 18 * u, 18 * u)
            p.restore()
        # содержимое за краем экрана устройство не показывает: закрываем всё вокруг корпуса фоном сцены
        outside, device = QPainterPath(), QPainterPath()
        outside.addRect(self.view.sceneRect().adjusted(-1e5, -1e5, 1e5, 1e5))
        fr = frame_rect(s, spec) if self.device_chrome else QRectF(0, 0, W, H)
        if not self.device_chrome:
            device.addRect(fr)
            p.fillPath(outside.subtracted(device), STAGE_BG)
            p.setPen(QPen(QColor("#3A3A3A"), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(fr)
            return
        if spec.profile.platform == PLATFORM_ANDROID:
            r = spec.profile.corner_dp * u + bezel(s, spec)
            device.addRoundedRect(fr, r, r)
        else:
            device.addRect(fr)
        p.fillPath(outside.subtracted(device), STAGE_BG)
        paint_device(p, s, spec, self.editor.artboard_color(), self.doc.meta.title, self.show_safe)

    def _paint_ripple(self, p: QPainter) -> None:
        """Волна нажатия Material: круг расходится от точки касания в пределах элемента и гаснет."""
        center, rect, radius, start = self.ripple
        pr = min(1.0, max(0.0, (self.now - start) / RIPPLE_MS))
        reach = max(QPointF(rect.left() - center.x(), rect.top() - center.y()).manhattanLength(),
                    QPointF(rect.right() - center.x(), rect.bottom() - center.y()).manhattanLength())
        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        light = self.doc.meta.appearance.theme == "light"
        c = QColor(0, 0, 0) if light else QColor(255, 255, 255)
        c.setAlphaF(0.22 * (1 - pr * pr))
        p.save()
        p.setClipPath(clip)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        r = reach * (0.25 + 0.75 * (1 - (1 - pr) ** 3))
        p.drawEllipse(center, r, r)
        p.restore()

    def _ripple_target(self, nid: str):
        """Нажимаемый элемент под касанием: компонент Material 3, экземпляр или узел с правилом нажатия."""
        m = tree.node_map(self.screen)
        below = None  # предыдущий фрейм цепочки: у вкладок, навигации и радиокнопок волна — на пункте
        for c in self._chain(nid):
            n = m.get(c)
            if n is None or n.is_group:
                continue
            if n.role in live.CHOICES and below is not None and any(ch is below for ch in n.children):
                return below
            if n.role.startswith("m3.") or n.is_instance or self.interp.handles("tap", c):
                return n
            below = n if n.is_frame else below
        return None

    # ---------- экранная клавиатура (Android) ----------
    def keyboard_visible(self) -> bool:
        return bool(self.focus_id and self.screen is not None and self.screen.platform == PLATFORM_ANDROID
                    and self.focus_id in tree.node_map(self.screen))

    def keyboard_keys(self) -> list[tuple[QRectF, str]]:
        s, spec = self.screen, self.spec
        u = spec.units(s)
        ins = spec.insets(s)
        kh = 4 * 50 * u + 16 * u
        top = s.height - ins.bottom - kh
        kw = s.width / 12
        keys = []
        for r, row in enumerate(KEY_ROWS):
            x0 = (s.width - kw * len(row)) / 2
            for i, ch in enumerate(row):
                keys.append((QRectF(x0 + i * kw + 2 * u, top + 8 * u + r * 50 * u, kw - 4 * u, 44 * u), ch))
        y = top + 8 * u + 3 * 50 * u
        keys.append((QRectF(2 * u, y, kw * 2 - 4 * u, 44 * u), KEY_BACK))
        keys.append((QRectF(kw * 2 + 2 * u, y, kw * 8 - 4 * u, 44 * u), KEY_SPACE))
        keys.append((QRectF(kw * 10 + 2 * u, y, kw * 2 - 4 * u, 44 * u), KEY_DONE))
        return keys

    def keyboard_rect(self) -> QRectF:
        keys = self.keyboard_keys()
        u = self.spec.units(self.screen)
        top = keys[0][0].top() - 8 * u
        return QRectF(0, top, self.screen.width, self.screen.height - self.spec.insets(self.screen).bottom - top)

    def _paint_keyboard(self, p: QPainter, s: Screen, u: float) -> None:
        p.save()
        p.fillRect(QRectF(0, self.keyboard_rect().top(), s.width, s.height - self.keyboard_rect().top()),
                   QColor("#1B1B1B"))
        f = QFont("Segoe UI")
        f.setPixelSize(max(1, round(18 * u)))
        p.setFont(f)
        for r, ch in self.keyboard_keys():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#3A3A3A") if ch not in (KEY_BACK, KEY_DONE) else QColor("#2A2A2A"))
            p.drawRoundedRect(r, 6 * u, 6 * u)
            p.setPen(QColor("#F2F2F2"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "пробел" if ch == KEY_SPACE else ch)
        p.restore()

    def _kb_hit(self, pt: QPointF) -> str | None:
        if not self.keyboard_visible():
            return None
        for r, ch in self.keyboard_keys():
            if r.contains(pt):
                return ch
        return "" if self.keyboard_rect().contains(pt) else None

    # ---------- попадание ----------
    def _hits(self, pt: QPointF | None, want=None) -> list[str]:
        """Узлы под точкой в порядке отрисовки с учётом видимости и обрезки фреймов."""
        out: list[str] = []
        if pt is None or self.screen is None:
            return out
        x, y = pt.x(), pt.y()

        def rec(nodes, ok):
            for n in nodes:
                if not n.visible:
                    continue
                inside = n.x <= x <= n.x + n.w and n.y <= y <= n.y + n.h
                if not n.is_group and ok and inside and (want is None or want(n)):
                    out.append(n.id)
                if n.is_container:
                    rec(n.children, ok and (inside or n.is_group or not n.clip))
        rec(self.screen.nodes, 0 <= x <= self.screen.width and 0 <= y <= self.screen.height)
        return out

    def hit(self, p: QPointF | None) -> str | None:
        hits = self._hits(p)
        return hits[-1] if hits else None

    def scroll_target(self, p: QPointF, axis: str) -> str | None:
        frames = self._hits(p, lambda n: n.is_frame and n.scroll == axis and self.scroll_max.get(n.id, 0) > 0)
        return frames[-1] if frames else None

    def set_scroll(self, frame_id: str, offset: float) -> None:
        self.scroll[frame_id] = max(0.0, min(offset, self.scroll_max.get(frame_id, 0.0)))
        self.render()

    def _chain(self, nid: str) -> list[str]:
        try:
            return [nid] + [a.id for a in reversed(tree.ancestors(self.screen, nid))]
        except Exception:
            return [nid]

    def editable_at(self, nid: str) -> str | None:
        """Поле ввода под касанием: сам текст или единственное поле внутри нажатого контейнера."""
        m = tree.node_map(self.screen)
        n = m.get(nid)
        if n is None:
            return None
        if n.type == "text" and n.editable:
            return n.id
        for c in self._chain(nid):
            cn = m.get(c)
            if cn is not None and cn.is_container:
                fields = [x for x, _, _ in tree.walk(cn.children) if x.type == "text" and x.editable]
                if len(fields) == 1:
                    return fields[0].id
                if fields:
                    return None
        return None

    # ---------- ввод ----------
    def _hover_target(self, nid: str | None) -> str | None:
        if not nid:
            return None
        sid = self.interp.state.screen_id
        with_hover = {i.node_id for i in self.doc.interactions if i.screen_id == sid
                      and i.trigger in ("hover_enter", "hover_leave")}
        m = tree.node_map(self.screen)
        for c in self._chain(nid):
            n = m.get(c)
            if c in with_hover:
                return c
            if n is not None and n.is_instance and not n.ref:
                d = self.doc.component(n.component_id)
                if d is not None and d.behavior.get("hover"):
                    return c
        return None

    def hover(self, p) -> None:
        if self.transition is not None or (self.touch_mode and p is not None):
            return
        target = self._hover_target(self.hit(p))
        if target != self.hover_id:
            if self.hover_id:
                self.dispatch("hover_leave", self.hover_id)
            self.hover_id = target
            if target:
                self.dispatch("hover_enter", target)

    def press(self, p) -> None:
        if self.transition is not None:
            return
        self._press_pos, self._dragging, self._drag = QPointF(p), False, None
        self._kb_key = self._kb_hit(p)
        if self._kb_key is not None:
            return
        nid = self.hit(p)
        self.pressed, self._press_state, self._long_fired = None, None, False
        if nid is None:
            self.view.viewport().update()
            return
        self.pressed = (nid, nid)
        tgt = None if self.reduced_motion else self._ripple_target(nid)
        if tgt is not None:
            self.ripple = (QPointF(p), QRectF(tgt.x, tgt.y, tgt.w, tgt.h), min(tgt.radius, tgt.w / 2, tgt.h / 2),
                           self.now)
        m = tree.node_map(self.screen)
        for c in self._chain(nid):
            n = m.get(c)
            if n is not None and n.is_instance and not n.ref:
                d = self.doc.component(n.component_id)
                if d is not None and d.behavior.get("press") and "pressed" in d.states:
                    self.pressed = (c, nid)
                    self._press_state = "pressed"
                break
        self._long.start(LONG_PRESS_MS)
        if self._press_state:
            self.render()
        else:
            self.view.viewport().update()

    def drag(self, p) -> None:
        if self._press_pos is None or self.transition is not None or self._kb_key is not None:
            return
        d = p - self._press_pos
        if not self._dragging and max(abs(d.x()), abs(d.y())) > SLOP_PX / self._scale():
            self._dragging = True
            self._long.stop()
            axis = "vertical" if abs(d.y()) >= abs(d.x()) else "horizontal"
            tgt = self.scroll_target(self._press_pos, axis)
            self._drag = (tgt, self.scroll.get(tgt, 0.0), axis) if tgt else None
            if self._press_state:
                self._press_state = None
                self.render()
        if self._dragging and self._drag is not None:
            tgt, start, axis = self._drag
            self.set_scroll(tgt, start - (d.y() if axis == "vertical" else d.x()))

    def _long_press(self) -> None:
        if self.pressed and not self._dragging:
            self._long_fired = True
            nid = self.pressed[1]
            self.pressed, self._press_state = None, None
            self.dispatch("long_press", nid)

    def release(self, p) -> None:
        self._long.stop()
        start, self._press_pos = self._press_pos, None
        if self._kb_key is not None:
            key, self._kb_key = self._kb_key, None
            if key and self._kb_hit(p) == key:
                self.keyboard_key(key)
            return
        pressed, self.pressed, self._press_state = self.pressed, None, None
        if self._dragging:
            self._dragging = False
            scrolled, self._drag = self._drag is not None, None
            d = p - start if start is not None else QPointF()
            u = self.spec.units(self.screen) if self.spec and self.screen else 1.0
            if not scrolled and pressed and max(abs(d.x()), abs(d.y())) >= SWIPE_DP * u:
                if abs(d.x()) >= abs(d.y()):
                    way = "left" if d.x() < 0 else "right"
                else:
                    way = "up" if d.y() < 0 else "down"
                self.dispatch(f"swipe_{way}", pressed[1])
            else:
                self.render()
            return
        if not pressed:
            self.view.viewport().update()
            return
        origin = pressed[1]
        nid = self.hit(p)
        if not self._long_fired and nid is not None and (nid == origin or origin in self._chain(nid)
                                                          or nid in self._chain(origin)):
            self._tap_pt = QPointF(p)
            self.tap(nid)
        else:
            self.render()

    def tap(self, nid: str) -> None:
        last, self._last_tap = self._last_tap, (nid, self.now)
        if last and last[0] == nid and self.now - last[1] <= DOUBLE_TAP_MS and self.interp.handles("double_tap", nid):
            self._last_tap = None
            self.dispatch("double_tap", nid)
            return
        field = self.editable_at(nid)
        if self.screen is not None:
            root, idx = live.target(self.screen, self._chain(nid))
            if root is not None:
                frac = live.slider_fraction(root, self._tap_pt.x()) if self._tap_pt is not None else None
                live.toggle(self.live, root, idx, frac)
        self._tap_pt = None
        self.dispatch("tap", nid)
        self.focus(field if field and self.screen is not None and field in tree.node_map(self.screen) else None)

    def focus(self, field_id: str | None) -> None:
        if field_id != self.focus_id:
            self.focus_id = field_id
            self.view.viewport().update()
            self.changed.emit()

    def field_text(self) -> str:
        return self.interp.state.texts.get(self.focus_id, "") if self.focus_id else ""

    def type_text(self, text: str) -> None:
        """Набор в поле с фокусом (весь новый текст поля)."""
        if self.focus_id:
            self.dispatch("text_input", self.focus_id, text)

    def keyboard_key(self, key: str) -> None:
        if key == KEY_DONE:
            self.focus(None)
        elif key == KEY_BACK:
            self.type_text(self.field_text()[:-1])
        elif key == KEY_SPACE:
            self.type_text(self.field_text() + " ")
        else:
            self.type_text(self.field_text() + key)

    def key(self, qt_key: int, text: str) -> bool:
        if self.focus_id:
            if qt_key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
                self.focus(None)
            elif qt_key == Qt.Key.Key_Backspace:
                self.type_text(self.field_text()[:-1])
            elif text and text.isprintable():
                self.type_text(self.field_text() + text)
            else:
                return False
            return True
        if qt_key in (Qt.Key.Key_Escape, Qt.Key.Key_Back):
            self.system_back()
            return True
        return False

    def wheel(self, p: QPointF, delta: int, horizontal: bool = False) -> None:
        if not delta or self.screen is None:
            return
        tgt = self.scroll_target(p, "horizontal" if horizontal else "vertical")
        if tgt:
            step = WHEEL_DP * self.spec.units(self.screen) * delta / 120
            self.set_scroll(tgt, self.scroll.get(tgt, 0.0) - step)

    def system_back(self) -> None:
        if self.focus_id:  # «Назад» сначала скрывает клавиатуру
            self.focus(None)
            return
        self.dispatch("system_back", "")

    # ---------- логика ----------
    def dispatch(self, trigger: str, node_id: str, value: str | None = None) -> None:
        before_state = copy.deepcopy(self.interp.state)
        before_pm = self.frame() if self.screen is not None else None
        effects = self.interp.dispatch(trigger, node_id, value)
        self._after_effects(effects, before_state, before_pm)

    def _after_effects(self, effects, before_state=None, before_pm=None) -> None:
        nav = None
        for e in effects:
            self.effect_log.append(describe(self.doc, e))
            if e.kind in ("navigate", "back"):
                nav = e
                self.active, self.persist, self.scroll, self.focus_id = [], {}, {}, None
                self.live, self.ripple = {}, None
            elif e.kind == "animation":
                a = self.doc.animation(e.data["animation_id"])
                if a is not None:
                    self.active = [(x, s) for x, s in self.active if x.id != a.id] + [(a, self.now)]
            elif e.kind == "state" and before_state is not None and not self.reduced_motion:
                n = tree.node_map(self.screen).get(e.data["node_id"]) if self.screen else None
                defn = self.doc.component(n.component_id) if n is not None and n.is_instance else None
                if defn is not None:
                    tr = defn.transition
                    old = compose(self.doc, before_state, self.engine, self.samples())
                    new = compose(self.doc, self.interp.state, self.engine, self.samples())
                    synth = state_transition(old, new, tr["duration"], tr["easing"]) if old and new else None
                    if synth is not None:
                        self.active.append((synth, self.now))
        self.render(fit=nav is not None)
        if nav is not None and before_pm is not None and not self.reduced_motion \
                and nav.data["transition"] != "none" and nav.data["duration"] > 0:
            self.transition = _Transition(before_pm, self.frame(), nav.data["transition"], nav.data["duration"],
                                          nav.data["easing"], self.now)
            self.view.viewport().update()
        self.changed.emit()

    def restart(self) -> None:
        self.active, self.persist, self.transition, self.hover_id = [], {}, None, None
        self.scroll, self.focus_id, self._last_tap = {}, None, None
        self.live, self.ripple = {}, None
        self.effect_log = []
        effects = self.interp.reset()
        self._after_effects(effects)

    def play_steps(self, steps: list) -> None:
        """Показать сценарий в проигрывателе: шаги по порядку, анимации и переходы доводятся сразу."""
        self.restart()
        for step in steps:
            self.dispatch(*step)
            self.advance(10_000)


def _touch_cursor() -> QCursor:
    pm = QPixmap(28, 28)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
    p.setBrush(QColor(255, 255, 255, 50))
    p.drawEllipse(QRectF(3, 3, 22, 22))
    p.end()
    return QCursor(pm, 14, 14)


def describe(doc, e) -> str:
    d = e.data
    names = {s.id: s.name for s in doc.screens}
    if e.kind == "navigate":
        return f"→ экран «{names.get(d['to'], '?')}» ({TRANSITION_RU.get(d['transition'], d['transition'])})"
    if e.kind == "back":
        return f"← назад на «{names.get(d['to'], '?')}»"
    if e.kind == "variable":
        v = doc.variable(d["var_id"])
        return f"переменная «{v.name if v else '?'}» = {format_value(d['value'])}"
    if e.kind == "state" and d.get("axis"):
        return f"вариант «{d['axis']}»: {d['from'].split(': ', 1)[-1]} → {d['value']}"
    if e.kind == "state":
        return f"состояние компонента: {d['from']} → {d['state']}"
    if e.kind == "visible":
        return "показан элемент" if d["visible"] else "скрыт элемент"
    if e.kind == "text":
        return f"текст: «{d['text'][:40]}»"
    if e.kind == "animation":
        a = doc.animation(d["animation_id"])
        return f"анимация «{a.name if a else '?'}»"
    if e.kind == "overlay_open":
        return "открыто окно"
    if e.kind == "overlay_close":
        return "закрыто окно"
    return f"⚠ {d.get('message', e.kind)}"


__all__ = ["PrototypePlayer", "PlayerView", "paint_device", "frame_rect", "describe", "TRANSITION_RU"]
