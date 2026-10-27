"""Проигрыватель прототипа: экраны, логика, анимации, переходы, запись и повтор сценария.

Это простой проигрыватель этапа 5 (на холсте с размерами экрана). Рамки устройств, плотность, безопасные
области и симуляция касаний — Interactive Preview, этап 6. Отрисовка Android — приближение, не Compose.
Время идёт по «виртуальным часам»: в окне — от таймера, в тестах — вызовом advance(мс), поэтому
воспроизведение повторяемо.
"""

from __future__ import annotations

import copy

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QGraphicsScene, QGraphicsView, QHBoxLayout, QListWidget, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.core.document import tree
from app.engines.animation import engine as anim
from app.engines.logic.engine import Interpreter, format_value
from app.engines.logic.runtime import compose, state_transition
from app.ui.studio.common import button
from app.ui.widgets import label, panel
from app.ui.workspace.canvas import asset_lookup, build_scene

LONG_PRESS_MS = 550
TRANSITION_RU = {"none": "без перехода", "fade": "затухание", "slide_left": "сдвиг влево",
                 "slide_right": "сдвиг вправо", "slide_up": "сдвиг вверх", "slide_down": "сдвиг вниз"}


class _Transition:
    def __init__(self, from_pm: QPixmap, to_pm: QPixmap, kind: str, duration: int, easing: str, start: float):
        self.from_pm, self.to_pm, self.kind = from_pm, to_pm, kind
        self.duration, self.easing, self.start = max(1, duration), easing, start

    def progress(self, now: float) -> float:
        return anim.ease(self.easing, (now - self.start) / self.duration)

    def done(self, now: float) -> bool:
        return now - self.start >= self.duration


class PlayerView(QGraphicsView):
    def __init__(self, player: "PrototypePlayer"):
        super().__init__()
        self.player = player
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setBackgroundBrush(QColor("#0B0B0B"))
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.player.fit()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.player.press(self.mapToScene(e.position().toPoint()))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.player.release(self.mapToScene(e.position().toPoint()))

    def mouseMoveEvent(self, e):
        self.player.hover(self.mapToScene(e.position().toPoint()))

    def leaveEvent(self, e):
        self.player.hover(None)
        super().leaveEvent(e)

    def drawForeground(self, p: QPainter, rect):
        t = self.player.transition
        if t is None:
            return
        pr = t.progress(self.player.now)
        p.save()
        p.resetTransform()
        w, h = self.viewport().width(), self.viewport().height()
        if t.kind == "fade":
            p.setOpacity(1 - pr)
            p.drawPixmap(0, 0, t.from_pm)
            p.setOpacity(pr)
            p.drawPixmap(0, 0, t.to_pm)
        else:
            dx, dy = {"slide_left": (-w, 0), "slide_right": (w, 0), "slide_up": (0, -h),
                      "slide_down": (0, h)}.get(t.kind, (0, 0))
            p.fillRect(0, 0, w, h, QColor("#0B0B0B"))
            p.drawPixmap(int(dx * pr), int(dy * pr), t.from_pm)
            p.drawPixmap(int(-dx * (1 - pr)), int(-dy * (1 - pr)), t.to_pm)
        p.restore()


class PrototypePlayer(QWidget):
    changed = Signal()

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.doc = editor.doc
        self.engine = editor.engine
        self.reduced_motion = False
        self.now = 0.0
        self.active: list[tuple[object, float]] = []   # (Animation, время старта)
        self.persist: dict[str, dict] = {}             # итоговые значения закончившихся анимаций
        self.transition: _Transition | None = None
        self.hover_id: str | None = None
        self.pressed: tuple[str, str] | None = None     # (узел, исходная точка-узел) нажатия
        self._press_state: str | None = None
        self._long_fired = False
        self.screen = None
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
        self.interp = Interpreter(self.doc, editor.screen_id)
        self._after_effects(self.interp.effects)
        self.render(fit=True)

    # ---------- время ----------
    def start_clock(self) -> None:
        self._clock.start()
        self._timer.start()

    def _tick(self) -> None:
        self.advance(float(self._clock.restart()))

    def advance(self, ms: float) -> None:
        self.now += ms
        busy = bool(self.active) or self.transition is not None
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

    def samples(self) -> dict:
        out = copy.deepcopy(self.persist)
        for a, start in self.active:
            for nid, props in anim.sample(a, self.now - start, self.reduced_motion).items():
                out.setdefault(nid, {}).update(props)
        return out

    # ---------- отрисовка ----------
    def render(self, fit: bool = False) -> None:
        state = self.interp.state
        if self.pressed and self._press_state:
            state = copy.deepcopy(state)
            state.states[self.pressed[0]] = self._press_state
        self.screen = compose(self.doc, state, self.engine, self.samples())
        if self.screen is None:
            self.view.scene().clear()
            return
        build_scene(self.view.scene(), self.screen, self.editor.artboard_color(), asset_lookup(self.doc))
        self.view.setSceneRect(QRectF(0, 0, self.screen.width, self.screen.height))
        if fit:
            self.fit()
        self.view.viewport().update()
        self.changed.emit()

    def fit(self) -> None:
        if self.screen is not None:
            self.view.fitInView(QRectF(0, 0, self.screen.width, self.screen.height),
                                Qt.AspectRatioMode.KeepAspectRatio)

    def frame(self) -> QPixmap:
        return self.view.viewport().grab()

    # ---------- ввод ----------
    def hit(self, p: QPointF | None) -> str | None:
        if p is None or self.screen is None:
            return None
        vis = {}

        def rec(nodes, visible):
            for n in nodes:
                vis[n.id] = visible and n.visible
                if n.is_container:
                    rec(n.children, vis[n.id])
        rec(self.screen.nodes, True)
        for n, _, _ in reversed(list(tree.walk(self.screen.nodes))):
            if n.is_group or not vis[n.id]:
                continue
            if n.x <= p.x() <= n.x + n.w and n.y <= p.y() <= n.y + n.h:
                return n.id
        return None

    def _chain(self, nid: str) -> list[str]:
        try:
            return [nid] + [a.id for a in reversed(tree.ancestors(self.screen, nid))]
        except Exception:
            return [nid]

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
        if self.transition is not None:
            return
        target = self._hover_target(self.hit(p))
        if target != self.hover_id:
            if self.hover_id:
                self.dispatch("hover_leave", self.hover_id)
            self.hover_id = target
            if target:
                self.dispatch("hover_enter", target)

    def press(self, p) -> None:
        nid = self.hit(p)
        if nid is None or self.transition is not None:
            return
        self._long_fired = False
        self.pressed = (nid, nid)
        self._press_state = None
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

    def _long_press(self) -> None:
        if self.pressed:
            self._long_fired = True
            nid = self.pressed[1]
            self.pressed, self._press_state = None, None
            self.dispatch("long_press", nid)

    def release(self, p) -> None:
        self._long.stop()
        if not self.pressed:
            return
        target, origin = self.pressed
        self.pressed, self._press_state = None, None
        nid = self.hit(p)
        if not self._long_fired and nid is not None and (nid == origin or origin in self._chain(nid)
                                                          or nid in self._chain(origin)):
            self.dispatch("tap", nid)
        else:
            self.render()

    def system_back(self) -> None:
        self.dispatch("system_back", "")

    # ---------- логика ----------
    def dispatch(self, trigger: str, node_id: str) -> None:
        before_state = copy.deepcopy(self.interp.state)
        before_pm = self.frame() if self.screen is not None else None
        effects = self.interp.dispatch(trigger, node_id)
        self._after_effects(effects, before_state, before_pm)

    def _after_effects(self, effects, before_state=None, before_pm=None) -> None:
        nav = None
        for e in effects:
            self.effect_log.append(describe(self.doc, e))
            if e.kind in ("navigate", "back"):
                nav = e
                self.active, self.persist = [], {}
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
        self.effect_log = []
        effects = self.interp.reset()
        self._after_effects(effects)


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


class PrototypeWindow(QDialog):
    """Окно прототипа: проигрыватель, переменные, журнал, запись и повтор сценария."""

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Прототип")
        self.resize(1180, 820)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        root = QHBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        left, ll = panel(margins=6)
        self.player = PrototypePlayer(editor)
        ll.addWidget(self.player, 1)
        row = QHBoxLayout()
        row.addWidget(button("◀ Назад", self.player.system_back, "Системная кнопка «Назад»"))
        row.addWidget(button("⟲ Сначала", self.restart))
        self.reduced = QCheckBox("Уменьшить движение")
        self.reduced.setToolTip("Анимации и переходы показываются сразу конечным состоянием")
        self.reduced.toggled.connect(lambda v: setattr(self.player, "reduced_motion", v))
        row.addWidget(self.reduced)
        row.addStretch()
        ll.addLayout(row)
        ll.addWidget(label("Простой проигрыватель этапа 5. Рамки устройств, плотность и безопасные области — "
                           "этап 6. Отрисовка Android — приближение.", "Muted", wrap=True))
        split.addWidget(left)
        right, rl = panel(margins=8)
        rl.addWidget(label("Переменные", "H2"))
        self.vars = QTableWidget(0, 2)
        self.vars.setHorizontalHeaderLabels(["Имя", "Значение"])
        self.vars.horizontalHeader().setStretchLastSection(True)
        self.vars.verticalHeader().setVisible(False)
        self.vars.setFixedHeight(150)
        rl.addWidget(self.vars)
        rl.addWidget(label("Журнал событий", "H2"))
        self.log = QListWidget()
        rl.addWidget(self.log, 1)
        rl.addWidget(label("Сценарий", "H2"))
        self.script_info = label("", "Muted", wrap=True)
        rl.addWidget(self.script_info)
        row = QHBoxLayout()
        row.addWidget(button("Запомнить сценарий", self.remember, "Сохранить события с начала сеанса"))
        row.addWidget(button("Повторить", self.replay, "Проиграть сценарий с начала и сравнить итог"))
        rl.addLayout(row)
        self.replay_result = label("", "Muted", wrap=True)
        rl.addWidget(self.replay_result)
        split.addWidget(right)
        split.setSizes([800, 360])
        root.addWidget(split)
        self.script: list | None = None
        self.script_digest = ""
        self.player.changed.connect(self.refresh)
        self.refresh()
        self.player.start_clock()

    def refresh(self) -> None:
        doc, st = self.player.doc, self.player.interp.state
        self.vars.setRowCount(len(doc.variables))
        for r, v in enumerate(doc.variables):
            self.vars.setItem(r, 0, QTableWidgetItem(v.name))
            self.vars.setItem(r, 1, QTableWidgetItem(format_value(st.variables.get(v.id, v.default))))
        if self.log.count() != len(self.player.effect_log):
            self.log.clear()
            self.log.addItems(self.player.effect_log)
            self.log.scrollToBottom()
        n = len(self.player.interp.log)
        self.script_info.setText(f"Событий в сеансе: {n}" + (f" · запомнено: {len(self.script)}"
                                                              if self.script is not None else ""))

    def restart(self) -> None:
        self.player.restart()
        self.refresh()

    def remember(self) -> None:
        self.script = list(self.player.interp.log)
        self.script_digest = self.player.interp.state.digest()
        self.replay_result.setText("Сценарий запомнен. «Повторить» проиграет его с начала.")
        self.refresh()

    def replay(self) -> None:
        if self.script is None:
            self.replay_result.setText("Сначала пройдите сценарий и нажмите «Запомнить сценарий».")
            return
        digest, _ = Interpreter(self.player.doc, self.player.interp.start).replay(self.script)
        self.player.restart()
        for trig, nid in self.script:
            self.player.dispatch(trig, nid)
            self.player.advance(10_000)  # мгновенно довести анимации и переходы
        same = digest == self.script_digest == self.player.interp.state.digest()
        self.replay_result.setText("✓ Итоговое состояние совпадает с записанным (повтор детерминирован)" if same
                                   else "⚠ Итог отличается от записи")
        self.refresh()

    def closeEvent(self, e):
        self.player._timer.stop()
        super().closeEvent(e)


__all__ = ["PrototypeWindow", "PrototypePlayer", "QPushButton"]
