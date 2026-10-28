"""Animation Studio: анимации экрана, таймлайн с ключевыми кадрами, плавности, просмотр."""

from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGraphicsScene, QGraphicsView, QHBoxLayout, QInputDialog,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from app.core.document import tree
from app.core.document.behavior import ANIMATABLE, COLOR_PROPS, EASINGS, Animation, Keyframe, Track, check_anim_value
from app.core.document.model import ModelError
from app.engines.animation import engine as anim
from app.engines.logic.runtime import apply_samples
from app.ui.studio.common import button
from app.ui.themes.fusion_amoled import TOKENS
from app.ui.widgets import label, panel
from app.ui.workspace.canvas import asset_lookup, build_scene

ROLE = Qt.ItemDataRole.UserRole
PROP_RU = {"x": "X", "y": "Y", "w": "Ширина", "h": "Высота", "opacity": "Непрозрачность", "radius": "Скругление",
           "fill": "Заливка", "stroke": "Обводка", "text_color": "Цвет текста", "font_size": "Размер шрифта",
           "stroke_width": "Толщина обводки", "scale": "Масштаб", "rotation": "Поворот"}
EASE_RU = {"linear": "Линейная", "ease_in": "Разгон", "ease_out": "Торможение", "ease_in_out": "Разгон и торможение",
           "step": "Скачок в конце", "cubic": "cubic-bezier…"}
ROW_H, HEAD_W, RULER_H = 26, 190, 24


class Timeline(QWidget):
    """Таймлайн: строки дорожек, ключевые кадры (ромбы), указатель времени. Перетаскивание кадров и указателя."""
    playhead_moved = Signal(float)
    key_selected = Signal(int, int)          # индекс дорожки, индекс кадра
    key_moved = Signal(int, int, int)        # дорожка, кадр, новое время

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(160)
        self.setMouseTracking(True)
        self.anim: Animation | None = None
        self.names: dict[str, str] = {}
        self.playhead = 0.0
        self.selected: tuple[int, int] | None = None
        self._drag: str | None = None
        self._drag_t = 0

    def set_animation(self, a: Animation | None, names: dict[str, str]) -> None:
        self.anim, self.names = a, names
        rows = len(a.tracks) if a else 0
        self.setMinimumHeight(RULER_H + max(3, rows) * ROW_H + 8)
        self.update()

    def _x(self, t: float) -> float:
        w = max(1, self.width() - HEAD_W - 16)
        return HEAD_W + (t / self.anim.duration) * w if self.anim else HEAD_W

    def _t(self, x: float) -> int:
        w = max(1, self.width() - HEAD_W - 16)
        return int(round(max(0.0, min(1.0, (x - HEAD_W) / w)) * self.anim.duration))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(TOKENS["surface"]))
        f = QFont(TOKENS["font"])
        f.setPixelSize(11)
        p.setFont(f)
        if self.anim is None:
            p.setPen(QColor(TOKENS["text_muted"]))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Выберите или создайте анимацию")
            return
        d = self.anim.duration
        step = next(s for s in (50, 100, 250, 500, 1000, 2000, 5000, 10_000, 60_000) if d / s <= 12)
        p.setPen(QColor(TOKENS["border_strong"]))
        t = 0
        while t <= d:
            x = self._x(t)
            p.drawLine(QPointF(x, RULER_H - 6), QPointF(x, self.height()))
            p.setPen(QColor(TOKENS["text_muted"]))
            p.drawText(QPointF(x + 3, 14), f"{t / 1000:g} с")
            p.setPen(QColor(TOKENS["border"]))
            t += step
        for i, tr in enumerate(self.anim.tracks):
            y = RULER_H + i * ROW_H
            if i % 2:
                p.fillRect(QRectF(0, y, self.width(), ROW_H), QColor(255, 255, 255, 6))
            p.setPen(QColor(TOKENS["text"]))
            p.drawText(QRectF(8, y, HEAD_W - 12, ROW_H), Qt.AlignmentFlag.AlignVCenter,
                       f"{self.names.get(tr.node_id, '⚠ удалён')} · {PROP_RU.get(tr.prop, tr.prop)}")
            pts = [self._x(k.t) for k in tr.keyframes]
            p.setPen(QPen(QColor(TOKENS["border_strong"]), 2))
            if len(pts) > 1:
                p.drawLine(QPointF(pts[0], y + ROW_H / 2), QPointF(pts[-1], y + ROW_H / 2))
            for j, k in enumerate(tr.keyframes):
                x = self._x(self._drag_t if self._drag == "key" and self.selected == (i, j) else k.t)
                cy = y + ROW_H / 2
                sel = self.selected == (i, j)
                p.setPen(QPen(QColor(TOKENS["accent"] if sel else "#FFFFFF"), 1.5))
                p.setBrush(QColor(TOKENS["accent"]) if sel else QColor("#D0D0D0"))
                p.drawPolygon(QPolygonF([QPointF(x, cy - 6), QPointF(x + 6, cy), QPointF(x, cy + 6),
                                         QPointF(x - 6, cy)]))
        x = self._x(self.playhead)
        p.setPen(QPen(QColor("#FF4D7A"), 1.5))
        p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        p.setBrush(QColor("#FF4D7A"))
        p.drawPolygon(QPolygonF([QPointF(x - 5, 0), QPointF(x + 5, 0), QPointF(x, 8)]))

    def _key_at(self, pos) -> tuple[int, int] | None:
        if self.anim is None:
            return None
        i = int((pos.y() - RULER_H) // ROW_H)
        if 0 <= i < len(self.anim.tracks):
            for j, k in enumerate(self.anim.tracks[i].keyframes):
                if abs(self._x(k.t) - pos.x()) <= 7:
                    return i, j
        return None

    def mousePressEvent(self, e):
        if self.anim is None:
            return
        pos = e.position()
        key = self._key_at(pos)
        if key is not None:
            self.selected = key
            self._drag, self._drag_t = "key", self.anim.tracks[key[0]].keyframes[key[1]].t
            self.key_selected.emit(*key)
        elif pos.x() >= HEAD_W:
            self._drag = "playhead"
            self.playhead = self._t(pos.x())
            self.playhead_moved.emit(self.playhead)
        self.update()

    def mouseMoveEvent(self, e):
        if self._drag == "playhead":
            self.playhead = self._t(e.position().x())
            self.playhead_moved.emit(self.playhead)
        elif self._drag == "key":
            self._drag_t = self._t(e.position().x())
        self.update()

    def mouseReleaseEvent(self, e):
        if self._drag == "key" and self.selected is not None:
            i, j = self.selected
            if self._drag_t != self.anim.tracks[i].keyframes[j].t:
                self.key_moved.emit(i, j, self._drag_t)
        self._drag = None
        self.update()


class AnimationPage(QWidget):
    def __init__(self, ws, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.main = ws.editor
        self.anim_id: str | None = None
        self.key: tuple[int, int] | None = None
        self.playing = False
        self._loading = False
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_list())
        split.addWidget(self._build_center())
        split.addWidget(self._build_right())
        split.setSizes([250, 880, 340])
        split.setStretchFactor(1, 1)
        root.addWidget(split)
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.main.document_changed.connect(self.refresh)
        self.main.screen_changed.connect(self.refresh)

    # ---------- список ----------
    def _build_list(self) -> QWidget:
        frame, lay = panel(margins=10)
        lay.addWidget(label("Анимации экрана", "H2"))
        self.screen_label = label("", "Muted", wrap=True)
        lay.addWidget(self.screen_label)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._select)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(button("+ Новая", self.new_anim))
        row.addWidget(button("Удалить", self.delete_anim, object_name="Danger"))
        lay.addLayout(row)
        form = QFormLayout()
        self.f_name = QLineEdit()
        self.f_name.editingFinished.connect(lambda: self._edit(lambda a: setattr(a, "name", self.f_name.text().strip()
                                                                              or a.name), "Имя анимации"))
        self.f_dur = QSpinBox()
        self.f_dur.setRange(1, 600_000)
        self.f_dur.setSuffix(" мс")
        self.f_dur.setKeyboardTracking(False)
        self.f_dur.valueChanged.connect(self._set_duration)
        self.f_loop = QCheckBox("Повторять")
        self.f_loop.toggled.connect(lambda v: self._edit(lambda a: setattr(a, "loop", v), "Повтор анимации"))
        form.addRow("Имя", self.f_name)
        form.addRow("Длительность", self.f_dur)
        form.addRow("", self.f_loop)
        lay.addLayout(form)
        lay.addWidget(label("Запуск анимации задаётся в «Логике» действием «Запустить анимацию».", "Muted",
                            wrap=True))
        frame.setMinimumWidth(230)
        return frame

    def refresh(self) -> None:
        if self.playing:
            return
        ed = self.main
        s = ed.screen()
        self.screen_label.setText(f"Экран: «{s.name}»" if s else "Нет экрана")
        self.list.blockSignals(True)
        self.list.clear()
        for a in ed.doc.animations if ed.doc and s else []:
            if a.screen_id != s.id:
                continue
            it = QListWidgetItem(f"{a.name}\n{a.duration} мс · дорожек: {len(a.tracks)}{' · ↻' if a.loop else ''}")
            it.setData(ROLE, a.id)
            self.list.addItem(it)
            if a.id == self.anim_id:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)
        if self.anim() is None:
            self.anim_id = None
        self._fill_nodes()
        self._load_anim()

    def anim(self) -> Animation | None:
        doc = self.main.doc
        return doc.animation(self.anim_id) if doc and self.anim_id else None

    def _select(self, item, _prev=None) -> None:
        self.stop()
        self.anim_id = item.data(ROLE) if item else None
        self.key = None
        self.timeline.selected = None
        self._load_anim()

    def _edit(self, fn, label_: str) -> bool:
        """Изменение текущей анимации одной записью истории."""
        if self._loading or self.anim_id is None:
            return False
        aid = self.anim_id

        def mutate(doc):
            a = doc.animation(aid)
            fn(a)
            doc.animations[doc.animations.index(a)] = Animation.from_dict(a.to_dict())  # повторная проверка
        return self.main.patch(label_, mutate)

    def new_anim(self) -> None:
        s = self.main.screen()
        if s is None:
            return
        name, ok = QInputDialog.getText(self, "Новая анимация", "Имя:", text=f"Анимация {len(self.main.doc.animations) + 1}")
        if not ok or not name.strip():
            return
        a = Animation(name=name.strip(), screen_id=s.id, duration=600)
        if self.main.patch("Новая анимация", lambda doc: doc.animations.append(Animation.from_dict(a.to_dict()))):
            self.anim_id = a.id
            self.refresh()

    def delete_anim(self) -> None:
        a = self.anim()
        if a and QMessageBox.question(self, "Анимация", f"Удалить анимацию «{a.name}»? Можно отменить (Ctrl+Z).") \
                == QMessageBox.StandardButton.Yes:
            aid = a.id
            self.main.patch("Удалить анимацию", lambda doc: doc.animations.remove(doc.animation(aid)))
            self.anim_id = None
            self.refresh()

    def _set_duration(self, v: int) -> None:
        def fn(a):
            a.duration = v
            for tr in a.tracks:  # кадры за пределами новой длительности прижимаются к концу
                seen = set()
                for k in tr.keyframes:
                    k.t = min(k.t, v)
                tr.keyframes = [k for k in sorted(tr.keyframes, key=lambda k: k.t) if not (k.t in seen or seen.add(k.t))]
        self._edit(fn, "Длительность анимации")

    # ---------- центр ----------
    def _build_center(self) -> QWidget:
        frame, lay = panel(margins=8)
        self.view = QGraphicsView(QGraphicsScene(self))
        self.view.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.view.setBackgroundBrush(QColor("#0B0B0B"))
        self.view.setFrameShape(QGraphicsView.Shape.NoFrame)
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        self.play_btn = button("▶ Воспроизвести", self.toggle_play)
        row.addWidget(self.play_btn)
        row.addWidget(button("■ Стоп", self.stop))
        self.reduced = QCheckBox("Уменьшить движение")
        self.reduced.setToolTip("Предпросмотр для пользователей, отключивших анимации: сразу конечное состояние")
        self.reduced.toggled.connect(lambda _: self.preview())
        row.addWidget(self.reduced)
        row.addStretch()
        self.time_label = label("0 мс", "Muted")
        row.addWidget(self.time_label)
        lay.addLayout(row)
        self.timeline = Timeline()
        self.timeline.playhead_moved.connect(lambda t: self.preview())
        self.timeline.key_selected.connect(self._select_key)
        self.timeline.key_moved.connect(self._move_key)
        lay.addWidget(self.timeline)
        return frame

    def preview(self) -> None:
        s = self.main.screen()
        if s is None:
            self.view.scene().clear()
            return
        from app.core.document.model import Screen
        clone = Screen.from_dict(s.to_dict())
        a = self.anim()
        if a is not None:
            apply_samples(clone, anim.sample(a, self.timeline.playhead, self.reduced.isChecked()))
        build_scene(self.view.scene(), clone, self.main.artboard_color(), asset_lookup(self.main.doc))
        self.view.setSceneRect(QRectF(0, 0, clone.width, clone.height))
        self.view.fitInView(QRectF(0, 0, clone.width, clone.height), Qt.AspectRatioMode.KeepAspectRatio)
        self.time_label.setText(f"{int(self.timeline.playhead)} мс")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.preview()

    def toggle_play(self) -> None:
        if self.playing:
            self.stop(keep_position=True)
            return
        if self.anim() is None:
            return
        self.playing = True
        self.play_btn.setText("❚❚ Пауза")
        if self.timeline.playhead >= self.anim().duration:
            self.timeline.playhead = 0
        self._clock.start()
        self._timer.start()

    def _tick(self) -> None:
        a = self.anim()
        if a is None:
            self.stop()
            return
        self.advance(self._clock.restart())

    def advance(self, ms: float) -> None:
        a = self.anim()
        t = self.timeline.playhead + ms
        if self.reduced.isChecked():
            t = a.duration
        if t >= a.duration:
            t = t % a.duration if a.loop else a.duration
            if not a.loop:
                self.timeline.playhead = t
                self.stop(keep_position=True)
                self.preview()
                return
        self.timeline.playhead = t
        self.timeline.update()
        self.preview()

    def stop(self, keep_position: bool = False) -> None:
        self._timer.stop()
        self.playing = False
        if hasattr(self, "play_btn"):
            self.play_btn.setText("▶ Воспроизвести")
        if not keep_position and hasattr(self, "timeline"):
            self.timeline.playhead = 0
            self.timeline.update()
            self.preview()

    # ---------- правая колонка ----------
    def _build_right(self) -> QWidget:
        frame, lay = panel(margins=10)
        lay.addWidget(label("Дорожка", "H2"))
        form = QFormLayout()
        self.t_node = QComboBox()
        self.t_prop = QComboBox()
        for p in ANIMATABLE:
            self.t_prop.addItem(PROP_RU[p], p)
        form.addRow("Элемент", self.t_node)
        form.addRow("Свойство", self.t_prop)
        lay.addLayout(form)
        lay.addWidget(button("+ Добавить дорожку", self.add_track,
                             "Дорожка с двумя кадрами: текущее значение в начале и в конце"))
        lay.addWidget(label("Ключевой кадр", "H2"))
        form = QFormLayout()
        self.k_time = QSpinBox()
        self.k_time.setRange(0, 600_000)
        self.k_time.setSuffix(" мс")
        self.k_value = QLineEdit()
        self.k_ease = QComboBox()
        for e in EASINGS:
            self.k_ease.addItem(EASE_RU[e], e)
        self.k_ease.currentIndexChanged.connect(lambda: self._bez_enabled())
        self.k_bez = []
        bez_row = QHBoxLayout()
        for v in (0.25, 0.1, 0.25, 1.0):
            sp = QDoubleSpinBox()
            sp.setRange(-10, 10)
            sp.setDecimals(2)
            sp.setSingleStep(0.05)
            sp.setValue(v)
            sp.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            self.k_bez.append(sp)
            bez_row.addWidget(sp)
        form.addRow("Время", self.k_time)
        form.addRow("Значение", self.k_value)
        form.addRow("Плавность до след.", self.k_ease)
        form.addRow("cubic-bezier", bez_row)
        lay.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(button("Применить", self.apply_key, object_name="Primary"))
        row.addWidget(button("Удалить кадр", self.delete_key, object_name="Danger"))
        lay.addLayout(row)
        lay.addWidget(button("+ Кадр в позиции указателя", self.add_key_here,
                             "Ключ выбранной дорожки со значением, которое сейчас показано"))
        lay.addWidget(button("Удалить дорожку", self.delete_track, object_name="Danger"))
        self.status = label("", "Muted", wrap=True)
        lay.addWidget(self.status)
        lay.addStretch()
        frame.setMinimumWidth(320)
        self._bez_enabled()
        return frame

    def _bez_enabled(self) -> None:
        for sp in self.k_bez:
            sp.setEnabled(self.k_ease.currentData() == "cubic")

    def _fill_nodes(self) -> None:
        s = self.main.screen()
        cur = self.t_node.currentData()
        self.t_node.clear()
        if s is None:
            return
        for n, _, depth in tree.walk(s.nodes):
            if not n.is_group and not n.ref:
                self.t_node.addItem("  " * depth + (n.name or n.type), n.id)
        if cur:
            self.t_node.setCurrentIndex(max(0, self.t_node.findData(cur)))

    def _names(self) -> dict[str, str]:
        s = self.main.screen()
        return {n.id: n.name or n.type for n, _, _ in tree.walk(s.nodes)} if s else {}

    def _load_anim(self) -> None:
        a = self.anim()
        self._loading = True
        for w in (self.f_name, self.f_dur, self.f_loop):
            w.setEnabled(a is not None)
        if a:
            self.f_name.setText(a.name)
            self.f_dur.setValue(a.duration)
            self.f_loop.setChecked(a.loop)
            self.k_time.setMaximum(a.duration)
        self._loading = False
        self.timeline.set_animation(a, self._names())
        if self.key and a and (self.key[0] >= len(a.tracks) or self.key[1] >= len(a.tracks[self.key[0]].keyframes)):
            self.key = None
            self.timeline.selected = None
        self._fill_key()
        self.preview()

    def _select_key(self, i: int, j: int) -> None:
        self.key = (i, j)
        self._fill_key()

    def _fill_key(self) -> None:
        a = self.anim()
        if not a or self.key is None:
            self.k_value.setText("")
            return
        k = a.tracks[self.key[0]].keyframes[self.key[1]]
        self.k_time.setValue(k.t)
        self.k_value.setText(str(k.value))
        self.k_ease.setCurrentIndex(self.k_ease.findData(k.easing))
        for sp, v in zip(self.k_bez, k.bezier):
            sp.setValue(v)

    def _current_value(self, node_id: str, prop: str):
        s = self.main.screen()
        n = tree.node_map(s).get(node_id) if s else None
        return getattr(n, prop) if n is not None else None

    def _parse(self, prop: str, text: str):
        t = text.strip()
        if prop not in COLOR_PROPS:
            t = float(t.replace(",", "."))
        elif not t.startswith("#"):
            t = "#" + t
        return check_anim_value(prop, t)

    def add_track(self) -> None:
        a = self.anim()
        nid, prop = self.t_node.currentData(), self.t_prop.currentData()
        if a is None or not nid:
            self.status.setText("Выберите анимацию и элемент")
            return
        if any(t.node_id == nid and t.prop == prop for t in a.tracks):
            self.status.setText("Такая дорожка уже есть")
            return
        v = self._current_value(nid, prop)
        if prop in COLOR_PROPS and not v:
            v = "#FFFFFF"
        self._edit(lambda x: x.tracks.append(Track(nid, prop, [Keyframe(0, v), Keyframe(x.duration, v)])),
                   "Добавить дорожку")
        self.status.setText("Дорожка добавлена: выберите кадр и задайте значение")

    def apply_key(self) -> None:
        a = self.anim()
        if a is None or self.key is None:
            return
        i, j = self.key
        prop = a.tracks[i].prop
        try:
            value = self._parse(prop, self.k_value.text())
        except (ModelError, ValueError) as exc:
            self.status.setText(f"Неверное значение: {exc}")
            return
        t, easing, bez = self.k_time.value(), self.k_ease.currentData(), [sp.value() for sp in self.k_bez]

        def fn(x):
            tr = x.tracks[i]
            if any(k.t == t for n, k in enumerate(tr.keyframes) if n != j):
                raise ModelError("На этой дорожке уже есть кадр в это время")
            k = tr.keyframes[j]
            k.t, k.value, k.easing, k.bezier = t, value, easing, bez
        if self._edit(fn, "Изменить ключевой кадр"):
            self.status.setText("Кадр изменён")

    def _move_key(self, i: int, j: int, t: int) -> None:
        def fn(x):
            tr = x.tracks[i]
            if any(k.t == t for n, k in enumerate(tr.keyframes) if n != j):
                raise ModelError("На этой дорожке уже есть кадр в это время")
            tr.keyframes[j].t = t
        self._edit(fn, "Переместить кадр")

    def add_key_here(self) -> None:
        a = self.anim()
        if a is None:
            return
        i = self.key[0] if self.key else (0 if a.tracks else None)
        if i is None:
            self.status.setText("Сначала добавьте дорожку")
            return
        t = int(self.timeline.playhead)
        tr = a.tracks[i]
        if any(k.t == t for k in tr.keyframes):
            self.status.setText("В этой позиции уже есть кадр")
            return
        v = anim.sample_track(tr, t)
        if self._edit(lambda x: x.tracks[i].keyframes.append(Keyframe(t, v)), "Добавить ключевой кадр"):
            self.status.setText(f"Кадр добавлен на {t} мс")

    def delete_key(self) -> None:
        if self.anim() is None or self.key is None:
            return
        i, j = self.key
        self.key = None
        self._edit(lambda x: x.tracks[i].keyframes.pop(j), "Удалить ключевой кадр")

    def delete_track(self) -> None:
        a = self.anim()
        if a is None or not a.tracks:
            return
        i = self.key[0] if self.key else 0
        self.key = None
        self._edit(lambda x: x.tracks.pop(i), "Удалить дорожку")
