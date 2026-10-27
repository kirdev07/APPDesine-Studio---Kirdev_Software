"""Visual Logic: взаимодействия «событие → условие → действия», переменные и карта переходов между экранами."""

from __future__ import annotations

import copy

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGraphicsScene, QGraphicsView, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from app.core.document import tree
from app.core.document.behavior import (
    ACTION_FIELDS, ACTION_NAMES, EASINGS, OPS, TRANSITIONS, TRIGGERS, VAR_MODES, VAR_TYPES, VIS_MODES,
    Interaction, Variable, check_action,
)
from app.core.document.model import ModelError
from app.engines.logic.engine import format_value, validate
from app.ui.studio.common import button
from app.ui.studio.prototype import TRANSITION_RU
from app.ui.themes.fusion_amoled import TOKENS
from app.ui.widgets import label, panel, pixmap_icon
from app.ui.workspace.canvas import render_thumbnail

ROLE = Qt.ItemDataRole.UserRole
TRIGGER_RU = {"tap": "Нажатие", "long_press": "Долгое нажатие", "hover_enter": "Наведение (мышь)",
              "hover_leave": "Уход курсора", "screen_open": "Открытие экрана"}
TYPE_RU = {"bool": "Логическое", "number": "Число", "text": "Текст"}
MODE_RU = {"set": "Присвоить", "toggle": "Переключить", "increment": "Увеличить на", "decrement": "Уменьшить на",
           "show": "Показать", "hide": "Скрыть"}
EASE_RU = {"linear": "Линейная", "ease_in": "Разгон", "ease_out": "Торможение", "ease_in_out": "Разгон и торможение",
           "step": "Скачок"}
DEFAULTS = {"navigate": {"transition": "slide_left", "duration": 300, "easing": "ease_out"},
            "back": {"transition": "slide_right", "duration": 250, "easing": "ease_out"},
            "set_variable": {"mode": "set", "value": ""}, "set_state": {"state": "default"},
            "set_visible": {"mode": "toggle"}, "set_text": {"text": ""}}


class FlowMap(QGraphicsView):
    """Экраны и переходы между ними (действия «Перейти на экран»)."""
    screen_clicked = Signal(str)

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setBackgroundBrush(QColor(TOKENS["surface"]))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.boxes: dict[str, QRectF] = {}

    def rebuild(self) -> None:
        sc = self.scene()
        sc.clear()
        doc = self.editor.doc
        self.boxes = {}
        if not doc:
            return
        cols = 3
        font = QFont(TOKENS["font"])
        font.setPixelSize(12)
        for i, s in enumerate(doc.screens):
            x, y = (i % cols) * 220, (i // cols) * 280
            r = QRectF(x, y, 150, 220)
            self.boxes[s.id] = r
            pm = render_thumbnail(s, self.editor.artboard_color(), 150, 200, doc)
            item = sc.addPixmap(pm)
            item.setPos(x, y)
            pen = QPen(QColor(TOKENS["accent"] if s.id == self.editor.screen_id else TOKENS["border_strong"]), 2)
            sc.addRect(r, pen)
            t = sc.addText(s.name, font)
            t.setDefaultTextColor(QColor(TOKENS["text"]))
            t.setPos(x, y + 200)
        pen = QPen(QColor("#9A9A9A"), 1.6)
        for it in doc.interactions:
            for a in it.actions:
                if a["type"] != "navigate" or it.screen_id not in self.boxes or a["screen_id"] not in self.boxes:
                    continue
                r1, r2 = self.boxes[it.screen_id], self.boxes[a["screen_id"]]
                p1, p2 = r1.center(), r2.center()
                if r1 == r2:
                    continue
                line = QLineF(p1, p2)
                ln = line.length()
                a1 = line.pointAt(min(0.45, 90 / ln)) if ln else p1
                a2 = line.pointAt(max(0.55, 1 - 90 / ln)) if ln else p2
                sc.addLine(QLineF(a1, a2), pen)
                v = QLineF(a2, a1)
                v.setLength(10)
                left, right = QLineF(v), QLineF(v)
                left.setAngle(v.angle() + 25)
                right.setAngle(v.angle() - 25)
                sc.addPolygon(QPolygonF([a2, left.p2(), right.p2()]), pen, QColor("#9A9A9A"))
                trig = TRIGGER_RU[it.trigger].lower()
                lbl = sc.addText(trig, font)
                lbl.setDefaultTextColor(QColor(TOKENS["text_muted"]))
                mid = QLineF(a1, a2).pointAt(0.5)
                lbl.setPos(mid + QPointF(4, -18))
        self.setSceneRect(sc.itemsBoundingRect().adjusted(-20, -20, 20, 20))
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self.sceneRect().isEmpty():
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self, e):
        p = self.mapToScene(e.position().toPoint())
        for sid, r in self.boxes.items():
            if r.contains(p):
                self.screen_clicked.emit(sid)
                return


class LogicPage(QWidget):
    run_requested = Signal()

    def __init__(self, ws, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.main = ws.editor
        self.work: dict | None = None    # редактируемое взаимодействие (копия)
        self.var_id: str | None = None
        self._loading = False
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_left())
        split.addWidget(self._build_editor())
        split.addWidget(self._build_right())
        split.setSizes([300, 560, 520])
        root.addWidget(split)
        self.main.document_changed.connect(self.refresh)
        self.main.screen_changed.connect(self.refresh)

    # ---------- левая колонка ----------
    def _build_left(self) -> QWidget:
        frame, lay = panel(margins=10)
        lay.addWidget(label("Взаимодействия экрана", "H2"))
        self.screen_label = label("", "Muted")
        lay.addWidget(self.screen_label)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.currentItemChanged.connect(self._select)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(button("+ Новое", self.new_interaction))
        row.addWidget(button("Удалить", self.delete_interaction, object_name="Danger"))
        lay.addLayout(row)
        lay.addWidget(button("▶ Запустить прототип", self.run_requested.emit, "Проиграть с текущего экрана (F5)",
                             "Primary"))
        lay.addWidget(label("Переменные проекта", "H2"))
        self.vars = QListWidget()
        self.vars.setFixedHeight(120)
        self.vars.currentItemChanged.connect(self._select_var)
        lay.addWidget(self.vars)
        form = QFormLayout()
        self.v_name = QLineEdit()
        self.v_type = QComboBox()
        for t in VAR_TYPES:
            self.v_type.addItem(TYPE_RU[t], t)
        self.v_default = QLineEdit()
        form.addRow("Имя", self.v_name)
        form.addRow("Тип", self.v_type)
        form.addRow("Начальное", self.v_default)
        lay.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(button("Новая", self.new_var))
        row.addWidget(button("Сохранить", self.save_var))
        row.addWidget(button("Удалить", self.delete_var, object_name="Danger"))
        lay.addLayout(row)
        frame.setMinimumWidth(270)
        return frame

    def refresh(self) -> None:
        doc, s = self.main.doc, self.main.screen()
        self.screen_label.setText(f"Экран: «{s.name}»" if s else "")
        names = {n.id: n.name or n.type for n, _, _ in tree.walk(s.nodes)} if s else {}
        cur = self.work["id"] if self.work else None
        self.list.blockSignals(True)
        self.list.clear()
        for it in doc.interactions if doc and s else []:
            if it.screen_id != s.id:
                continue
            src = "Экран" if it.trigger == "screen_open" else f"«{names.get(it.node_id, '⚠ удалён')}»"
            acts = ", ".join(ACTION_NAMES[a["type"]].lower() for a in it.actions) or "нет действий"
            cond = " · с условием" if it.condition else ""
            item = QListWidgetItem(f"{src} · {TRIGGER_RU[it.trigger].lower()}{cond}\n→ {acts}")
            item.setData(ROLE, it.id)
            self.list.addItem(item)
            if it.id == cur:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        if self.work and not any(i.id == self.work["id"] for i in (doc.interactions if doc else [])) \
                and not self.work.get("_new"):
            self.work = None
        self.vars.blockSignals(True)
        self.vars.clear()
        for v in doc.variables if doc else []:
            item = QListWidgetItem(f"{v.name} · {TYPE_RU[v.type]} · {format_value(v.default)}")
            item.setData(ROLE, v.id)
            self.vars.addItem(item)
        self.vars.blockSignals(False)
        self._fill_editor()
        self.flow.rebuild()
        self.diag.clear()
        diags = validate(doc) if doc else []
        self.diag.addItems([f"⚠ {d.message}" if d.severity == "warning" else f"ℹ {d.message}" for d in diags]
                           or ["✓ Замечаний к логике нет"])

    def _select(self, item, _prev=None) -> None:
        it = next((i for i in self.main.doc.interactions if item and i.id == item.data(ROLE)), None)
        self.work = it.to_dict() if it else None
        self._fill_editor()

    def new_interaction(self) -> None:
        s = self.main.screen()
        if s is None:
            return
        sel = self.main.selected_nodes()
        node = sel[0].id if sel else ""
        self.work = Interaction(screen_id=s.id, trigger="tap" if node else "screen_open", node_id=node).to_dict()
        self.work["_new"] = True
        self.list.clearSelection()
        self._fill_editor()
        self.status.setText("Новое взаимодействие: настройте и нажмите «Сохранить»" +
                            ("" if node else ". Подсказка: выделите элемент на холсте перед созданием"))

    def delete_interaction(self) -> None:
        if not self.work or self.work.get("_new"):
            self.work = None
            self._fill_editor()
            return
        iid = self.work["id"]
        if QMessageBox.question(self, "Взаимодействие", "Удалить взаимодействие? Можно отменить (Ctrl+Z).") \
                == QMessageBox.StandardButton.Yes:
            self.main.patch("Удалить взаимодействие", lambda doc: doc.interactions.remove(
                next(i for i in doc.interactions if i.id == iid)))
            self.work = None
            self.refresh()

    # ---------- переменные ----------
    def _select_var(self, item, _prev=None) -> None:
        v = self.main.doc.variable(item.data(ROLE)) if item else None
        if v:
            self.var_id = v.id
            self.v_name.setText(v.name)
            self.v_type.setCurrentIndex(self.v_type.findData(v.type))
            self.v_default.setText(format_value(v.default))

    def new_var(self) -> None:
        self.var_id = None
        self.vars.clearSelection()
        self.v_name.setText(f"Переменная {len(self.main.doc.variables) + 1}")
        self.v_default.setText("")

    def save_var(self) -> None:
        d = {"id": self.var_id or Variable("x").id, "name": self.v_name.text().strip(),
             "type": self.v_type.currentData(), "default": self.v_default.text()}
        try:
            Variable.from_dict(d)
        except ModelError as exc:
            self.status.setText(str(exc))
            return

        def mutate(doc):
            v = Variable.from_dict(d)
            old = doc.variable(v.id)
            if old is None:
                doc.variables.append(v)
            else:
                doc.variables[doc.variables.index(old)] = v
        if self.main.patch("Переменная", mutate):
            self.var_id = d["id"]
            self.status.setText(f"Переменная «{d['name']}» сохранена")

    def delete_var(self) -> None:
        if not self.var_id:
            return
        vid = self.var_id
        used = sum(1 for i in self.main.doc.interactions for a in i.actions if a.get("var_id") == vid) + \
            sum(1 for i in self.main.doc.interactions if i.condition and i.condition["var_id"] == vid)
        if QMessageBox.question(self, "Переменная", "Удалить переменную?" + (
                f" Она используется в {used} местах — они попадут в диагностику." if used else "")) \
                == QMessageBox.StandardButton.Yes:
            self.main.patch("Удалить переменную", lambda doc: doc.variables.remove(doc.variable(vid)))
            self.var_id = None

    # ---------- редактор взаимодействия ----------
    def _build_editor(self) -> QWidget:
        frame, lay = panel(margins=10)
        lay.addWidget(label("Взаимодействие", "H2"))
        form = QFormLayout()
        self.e_node = QComboBox()
        self.e_trigger = QComboBox()
        for t in TRIGGERS:
            self.e_trigger.addItem(TRIGGER_RU[t], t)
        self.e_node.currentIndexChanged.connect(self._edit_head)
        self.e_trigger.currentIndexChanged.connect(self._edit_head)
        form.addRow("Элемент", self.e_node)
        form.addRow("Событие", self.e_trigger)
        lay.addLayout(form)
        crow = QHBoxLayout()
        self.c_on = QCheckBox("Только если")
        self.c_var, self.c_op, self.c_val = QComboBox(), QComboBox(), QLineEdit()
        for op in OPS:
            self.c_op.addItem(op, op)
        for w in (self.c_on, self.c_var, self.c_op, self.c_val):
            crow.addWidget(w)
        self.c_on.toggled.connect(self._edit_head)
        self.c_var.currentIndexChanged.connect(self._edit_head)
        self.c_op.currentIndexChanged.connect(self._edit_head)
        self.c_val.editingFinished.connect(self._edit_head)
        lay.addLayout(crow)
        lay.addWidget(label("Действия (по порядку)", "H2"))
        self.actions = QListWidget()
        self.actions.setFixedHeight(150)
        self.actions.currentRowChanged.connect(self._fill_action)
        lay.addWidget(self.actions)
        row = QHBoxLayout()
        self.a_type = QComboBox()
        for t in ACTION_FIELDS:
            self.a_type.addItem(ACTION_NAMES[t], t)
        row.addWidget(self.a_type, 1)
        row.addWidget(button("+", self.add_action, "Добавить действие"))
        row.addWidget(button("↑", lambda: self.move_action(-1)))
        row.addWidget(button("↓", lambda: self.move_action(1)))
        row.addWidget(button("✕", self.remove_action, "Удалить действие", "Danger"))
        lay.addLayout(row)
        self.a_form_host = QWidget()
        self.a_form = QFormLayout(self.a_form_host)
        lay.addWidget(self.a_form_host)
        lay.addStretch()
        lay.addWidget(button("Сохранить взаимодействие", self.save, object_name="Primary"))
        self.status = label("", "Muted", wrap=True)
        lay.addWidget(self.status)
        frame.setMinimumWidth(420)
        return frame

    def _fill_editor(self) -> None:
        self._loading = True
        on = self.work is not None
        for w in (self.e_node, self.e_trigger, self.c_on, self.c_var, self.c_op, self.c_val, self.actions,
                  self.a_type):
            w.setEnabled(on)
        s = self.main.screen()
        self.e_node.clear()
        self.e_node.addItem("— Экран (для «Открытие экрана»)", "")
        if s:
            for n, _, depth in tree.walk(s.nodes):
                if not n.ref:
                    self.e_node.addItem("  " * depth + (n.name or n.type), n.id)
        self.c_var.clear()
        for v in self.main.doc.variables if self.main.doc else []:
            self.c_var.addItem(v.name, v.id)
        if on:
            w = self.work
            self.e_node.setCurrentIndex(max(0, self.e_node.findData(w["node_id"])))
            self.e_trigger.setCurrentIndex(self.e_trigger.findData(w["trigger"]))
            c = w.get("condition")
            self.c_on.setChecked(bool(c))
            if c:
                self.c_var.setCurrentIndex(max(0, self.c_var.findData(c["var_id"])))
                self.c_op.setCurrentIndex(self.c_op.findData(c["op"]))
                self.c_val.setText(str(c["value"]))
            else:
                self.c_val.setText("")
            self._fill_actions()
        else:
            self.actions.clear()
            self._clear_form()
        self._loading = False

    def _edit_head(self, *_):
        if self._loading or not self.work:
            return
        w = self.work
        w["trigger"] = self.e_trigger.currentData()
        w["node_id"] = "" if w["trigger"] == "screen_open" else (self.e_node.currentData() or "")
        if self.c_on.isChecked() and self.c_var.currentData():
            val = self.c_val.text().strip()
            var = self.main.doc.variable(self.c_var.currentData())
            if var and var.type == "bool":
                val = val.lower() in ("1", "true", "да", "истина", "вкл")
            w["condition"] = {"var_id": self.c_var.currentData(), "op": self.c_op.currentData(), "value": val}
        else:
            w["condition"] = None

    def _summary(self, a: dict) -> str:
        doc = self.main.doc
        s = self.main.screen()
        names = {n.id: n.name for n, _, _ in tree.walk(s.nodes)} if s else {}
        t = a["type"]
        if t == "navigate":
            scr = next((x.name for x in doc.screens if x.id == a.get("screen_id")), "?")
            return f"→ «{scr}», {TRANSITION_RU[a['transition']]}"
        if t == "set_variable":
            v = doc.variable(a.get("var_id", ""))
            return f"«{v.name if v else '?'}»: {MODE_RU[a['mode']].lower()} {a.get('value', '')}"
        if t in ("set_state", "set_visible", "set_text", "open_overlay"):
            extra = {"set_state": a.get("state", ""), "set_visible": MODE_RU.get(a.get("mode"), ""),
                     "set_text": f"«{a.get('text', '')[:24]}»", "open_overlay": ""}[t]
            return f"«{names.get(a.get('node_id'), '?')}» {extra}"
        if t == "play_animation":
            an = doc.animation(a.get("animation_id", ""))
            return f"«{an.name if an else '?'}»"
        return ""

    def _fill_actions(self) -> None:
        row = self.actions.currentRow()
        self.actions.blockSignals(True)
        self.actions.clear()
        for a in self.work["actions"]:
            self.actions.addItem(f"{ACTION_NAMES[a['type']]}  {self._summary(a)}")
        self.actions.blockSignals(False)
        if self.work["actions"]:
            self.actions.setCurrentRow(min(max(row, 0), len(self.work["actions"]) - 1))
        else:
            self._clear_form()

    def add_action(self) -> None:
        if not self.work:
            return
        t = self.a_type.currentData()
        a = {"type": t, **copy.deepcopy(DEFAULTS.get(t, {}))}
        doc, s = self.main.doc, self.main.screen()
        if t == "navigate":
            other = [x for x in doc.screens if x.id != s.id]
            a["screen_id"] = (other or doc.screens)[0].id
        if t in ("set_state", "set_visible", "set_text", "open_overlay"):
            sel = self.main.selected_nodes()
            a["node_id"] = sel[0].id if sel else (s.nodes[0].id if s.nodes else "")
        if t == "set_variable":
            if not doc.variables:
                self.status.setText("Сначала создайте переменную (слева)")
                return
            a["var_id"] = doc.variables[0].id
        if t == "play_animation":
            anims = [x for x in doc.animations if x.screen_id == s.id]
            if not anims:
                self.status.setText("На этом экране нет анимаций — создайте в «Анимациях»")
                return
            a["animation_id"] = anims[0].id
        self.work["actions"].append(a)
        self._fill_actions()
        self.actions.setCurrentRow(len(self.work["actions"]) - 1)

    def remove_action(self) -> None:
        r = self.actions.currentRow()
        if self.work and 0 <= r < len(self.work["actions"]):
            self.work["actions"].pop(r)
            self._fill_actions()

    def move_action(self, d: int) -> None:
        r = self.actions.currentRow()
        acts = self.work["actions"] if self.work else []
        if 0 <= r < len(acts) and 0 <= r + d < len(acts):
            acts[r], acts[r + d] = acts[r + d], acts[r]
            self._fill_actions()
            self.actions.setCurrentRow(r + d)

    def _clear_form(self) -> None:
        while self.a_form.rowCount():
            self.a_form.removeRow(0)

    def _fill_action(self, r: int) -> None:
        self._clear_form()
        if not self.work or not 0 <= r < len(self.work["actions"]):
            return
        a = self.work["actions"][r]
        doc, s = self.main.doc, self.main.screen()
        nodes = list(tree.walk(s.nodes)) if s else []

        def combo(items, key, cur):
            c = QComboBox()
            for text, data in items:
                c.addItem(text, data)
            c.setCurrentIndex(max(0, c.findData(cur)))
            c.currentIndexChanged.connect(lambda: self._set(r, key, c.currentData()))
            return c

        for f in ACTION_FIELDS[a["type"]]:
            cur = a.get(f)
            if f == "screen_id":
                w = combo([(x.name, x.id) for x in doc.screens], f, cur)
                title = "Экран"
            elif f == "transition":
                w, title = combo([(TRANSITION_RU[t], t) for t in TRANSITIONS], f, cur), "Переход"
            elif f == "easing":
                w, title = combo([(EASE_RU[e], e) for e in EASINGS[:5]], f, cur), "Плавность"
            elif f == "duration":
                w = QSpinBox()
                w.setRange(0, 10_000)
                w.setSuffix(" мс")
                w.setValue(int(cur or 0))
                w.valueChanged.connect(lambda v: self._set(r, "duration", v))
                title = "Длительность"
            elif f == "var_id":
                w, title = combo([(v.name, v.id) for v in doc.variables], f, cur), "Переменная"
            elif f == "mode":
                modes = VAR_MODES if a["type"] == "set_variable" else VIS_MODES
                w, title = combo([(MODE_RU[m], m) for m in modes], f, cur), "Режим"
            elif f == "node_id":
                only_inst = a["type"] == "set_state"
                only_text = a["type"] == "set_text"
                items = [("  " * d + (n.name or n.type), n.id) for n, _, d in nodes
                         if not n.is_group and not n.ref and (not only_inst or n.is_instance)
                         and (not only_text or n.type == "text")]
                w, title = combo(items, f, cur), "Элемент"
            elif f == "state":
                n = next((n for n, _, _ in nodes if n.id == a.get("node_id")), None)
                defn = doc.component(n.component_id) if n is not None and n.is_instance else None
                w = combo([("По умолчанию", "default")] + [(st, st) for st in (defn.states if defn else {})], f, cur)
                title = "Состояние"
            elif f == "animation_id":
                w = combo([(x.name, x.id) for x in doc.animations if s and x.screen_id == s.id], f, cur)
                title = "Анимация"
            else:  # value, text
                w = QLineEdit(str(cur if cur is not None else ""))
                w.setPlaceholderText("можно вставлять {Имя переменной}" if f == "text" else "значение")
                w.editingFinished.connect(lambda key=f, ww=w: self._set(r, key, ww.text()))
                title = "Текст" if f == "text" else "Значение"
            self.a_form.addRow(title, w)

    def _set(self, r: int, key: str, value) -> None:
        if not self.work or not 0 <= r < len(self.work["actions"]):
            return
        self.work["actions"][r][key] = value
        if key == "node_id" and self.work["actions"][r]["type"] == "set_state":
            self.work["actions"][r]["state"] = "default"
            self._fill_action(r)
        self.actions.item(r).setText(f"{ACTION_NAMES[self.work['actions'][r]['type']]}  "
                                     f"{self._summary(self.work['actions'][r])}")

    def save(self) -> bool:
        if not self.work:
            return False
        self._edit_head()
        d = {k: v for k, v in self.work.items() if k != "_new"}
        if d["trigger"] != "screen_open" and not d["node_id"]:
            self.status.setText("Выберите элемент — источник события")
            return False
        for a in d["actions"]:
            if a["type"] == "set_variable":
                var = self.main.doc.variable(a["var_id"])
                if var and var.type == "number" and a["mode"] != "toggle":
                    try:
                        a["value"] = float(str(a.get("value") or (1 if a["mode"] != "set" else 0)).replace(",", "."))
                    except ValueError:
                        self.status.setText(f"«{var.name}»: нужно число")
                        return False
                if var and var.type == "bool" and a["mode"] == "set":
                    a["value"] = str(a.get("value", "")).strip().lower() in ("1", "true", "да", "истина", "вкл")
        try:
            d["actions"] = [check_action(a) for a in d["actions"]]
            Interaction.from_dict(d)
        except ModelError as exc:
            self.status.setText(f"Не сохранено: {exc}")
            return False

        def mutate(doc):
            it = Interaction.from_dict(d)
            old = next((i for i in doc.interactions if i.id == it.id), None)
            if old is None:
                doc.interactions.append(it)
            else:
                doc.interactions[doc.interactions.index(old)] = it
        ok = self.main.patch("Взаимодействие", mutate)
        if ok:
            self.work = d
            self.status.setText("Сохранено")
            self.refresh()
        return ok

    # ---------- правая колонка ----------
    def _build_right(self) -> QWidget:
        frame, lay = panel(margins=8)
        lay.addWidget(label("Карта переходов", "H2"))
        self.flow = FlowMap(self.main)
        self.flow.screen_clicked.connect(self.main.set_screen)
        lay.addWidget(self.flow, 1)
        lay.addWidget(label("Проверка логики", "H2"))
        self.diag = QListWidget()
        self.diag.setWordWrap(True)
        self.diag.setFixedHeight(150)
        lay.addWidget(self.diag)
        return frame


__all__ = ["LogicPage", "pixmap_icon"]
