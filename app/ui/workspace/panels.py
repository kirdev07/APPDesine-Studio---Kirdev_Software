"""Панели рабочей области: элементы и слои, инспектор свойств, полоса экранов."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFontComboBox, QFormLayout, QGridLayout, QHBoxLayout,
    QHeaderView,
    QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy,
    QScrollArea, QSpinBox, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from app.core.document import tree
from app.core.document.model import Screen
from app.libraries import components
from app.libraries.catalog import DEVICES
from app.ui.widgets import glyph_icon, label, pixmap_icon, separator
from app.ui.workspace.canvas import qcolor, render_thumbnail
from app.ui.workspace.editor import TYPE_NAMES, Editor

ROLE_ID = Qt.ItemDataRole.UserRole
TYPE_GLYPH = {"rect": "▭", "ellipse": "◯", "text": "T", "group": "▣", "frame": "#", "vector": "✎", "image": "▨",
              "instance": "◈"}
SIZING = [("fixed", "Фиксированный"), ("fill", "Заполнить"), ("hug", "По содержимому")]
LAYOUTS = [("none", "Нет (свободно)"), ("vertical", "Вертикально ↓"), ("horizontal", "Горизонтально →"),
           ("grid", "Сетка ▦")]
MAIN_ALIGN = [("start", "В начале"), ("center", "По центру"), ("end", "В конце"), ("space_between", "Равномерно")]
CROSS_ALIGN = [("start", "В начале"), ("center", "По центру"), ("end", "В конце"), ("stretch", "Растянуть")]
CONSTRAINT_H = [("left", "Слева"), ("right", "Справа"), ("left_right", "Слева и справа"), ("center", "По центру"),
                ("scale", "Масштаб")]
CONSTRAINT_V = [("top", "Сверху"), ("bottom", "Снизу"), ("top_bottom", "Сверху и снизу"), ("center", "По центру"),
                ("scale", "Масштаб")]


def _combo(options) -> QComboBox:
    c = QComboBox()
    for key, text in options:
        c.addItem(text, key)
    return c


# ---------------- элементы и слои ----------------

class LayersPanel(QWidget):
    def __init__(self, editor: Editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.addWidget(label("Элементы", "H2"))
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (kind, key, short) in enumerate((("frame", "F", "Фрейм"), ("rect", "R", "Прямоугольник"),
                                                ("ellipse", "O", "Эллипс"), ("text", "T", "Текст"))):
            b = QPushButton(f"{TYPE_GLYPH[kind]}  {short}")
            b.setStyleSheet("padding:6px 4px")
            b.setToolTip(f"{TYPE_NAMES[kind]}: добавить в центр экрана (инструмент — клавиша {key})")
            b.clicked.connect(lambda _=False, k=kind: editor.add_node(k))
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)
        lay.addWidget(label("Компоненты", "H2"))
        self.components = QListWidget()
        self.components.setFixedHeight(170)
        self.components.itemClicked.connect(self._insert_component)
        lay.addWidget(self.components)
        lay.addWidget(label("Заготовки из фреймов с Auto Layout. Свои мастер-компоненты — раздел «Компоненты» "
                            "и «Создать компонент» (Ctrl+Alt+K).", "Muted", wrap=True))
        lay.addWidget(separator())
        head = QHBoxLayout()
        head.addWidget(label("Слои", "H2"))
        head.addStretch()
        for text, tip, mode in (("↑", "Выше (Ctrl+])", "up"), ("↓", "Ниже (Ctrl+[)", "down")):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, m=mode: editor.reorder(m))
            head.addWidget(b)
        lay.addLayout(head)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(3)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2):
            self.tree.header().setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.tree.setColumnWidth(c, 26)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setEditTriggers(QTreeWidget.EditTrigger.DoubleClicked | QTreeWidget.EditTrigger.EditKeyPressed)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)
        self.tree.itemClicked.connect(self._on_click)
        self.tree.itemChanged.connect(self._on_renamed)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.setStyleSheet("QTreeWidget{background:transparent;border:none}"
                                "QTreeWidget::item{padding:3px}"
                                "QTreeWidget::item:selected{background:#1C1C1C;border:1px solid #2F7BFF}")
        lay.addWidget(self.tree, 1)
        self._eye = glyph_icon("view", 14, "#A0A0A0", "👁")
        self._eye_off = glyph_icon("hide", 14, "#5A5A5A", "–")
        self._lock = glyph_icon("lock", 14, "#F2F2F2", "L")
        self._unlock = glyph_icon("unlock", 14, "#3A3A3A", "·")
        self._syncing = False
        editor.document_changed.connect(self.rebuild)
        editor.screen_changed.connect(self.rebuild)
        editor.selection_changed.connect(self.sync_selection)
        editor.screen_changed.connect(self.rebuild_components)

    def rebuild_components(self) -> None:
        self.components.clear()
        s = self.editor.screen()
        if s is None:
            return
        for spec in components.specs_for(s.platform):
            it = QListWidgetItem(f"{spec.category} · {spec.name}")
            it.setData(ROLE_ID, spec.kind)
            it.setToolTip("Нажмите, чтобы добавить на экран")
            self.components.addItem(it)

    def _insert_component(self, item: QListWidgetItem) -> None:
        self.editor.insert_component(item.data(ROLE_ID))

    def rebuild(self) -> None:
        self._syncing = True
        self.tree.blockSignals(True)
        self.tree.clear()
        s = self.editor.screen()
        if s:
            def add(nodes, parent):
                for n in reversed(nodes):
                    it = QTreeWidgetItem([f"{TYPE_GLYPH[n.type]}  {n.name or TYPE_NAMES[n.type]}", "", ""])
                    it.setData(0, ROLE_ID, n.id)
                    it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
                    it.setIcon(1, self._eye if n.visible else self._eye_off)
                    it.setIcon(2, self._lock if n.locked else self._unlock)
                    it.setToolTip(1, "Скрыть / показать")
                    it.setToolTip(2, "Заблокировать / разблокировать")
                    if not n.visible:
                        it.setForeground(0, QColor("#5A5A5A"))
                    (parent.addChild(it) if parent else self.tree.addTopLevelItem(it))
                    if n.is_container:
                        add(n.children, it)
                        it.setExpanded(True)
            add(s.nodes, None)
        self.tree.blockSignals(False)
        self._syncing = False
        self.sync_selection()

    def _items(self):
        stack = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while stack:
            it = stack.pop()
            yield it
            stack.extend(it.child(i) for i in range(it.childCount()))

    def sync_selection(self) -> None:
        self._syncing = True
        self.tree.blockSignals(True)
        sel = set(self.editor.selection)
        for it in self._items():
            it.setSelected(it.data(0, ROLE_ID) in sel)
        self.tree.blockSignals(False)
        self._syncing = False

    def _on_tree_selection(self) -> None:
        if not self._syncing:
            self.editor.select_any([it.data(0, ROLE_ID) for it in self.tree.selectedItems()])

    def _on_click(self, item: QTreeWidgetItem, column: int) -> None:
        nid = item.data(0, ROLE_ID)
        if column == 1:
            self.editor.toggle("visible", [nid])
        elif column == 2:
            self.editor.toggle("locked", [nid])

    def _on_renamed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._syncing or column != 0:
            return
        name = item.text(0)
        for g in TYPE_GLYPH.values():
            if name.startswith(g + "  "):
                name = name[len(g) + 2:]
        name = name.strip()
        if name:
            self.editor.set_props({item.data(0, ROLE_ID): {"name": name}}, "Переименовать")
        else:
            self.rebuild()

    def _menu(self, pos) -> None:
        if not self.tree.itemAt(pos):
            return
        ed = self.editor
        menu = QMenu(self)
        menu.addAction("Сгруппировать", ed.group_selection)
        menu.addAction("Разгруппировать", ed.ungroup_selection)
        menu.addSeparator()
        menu.addAction("На передний план", lambda: ed.reorder("top"))
        menu.addAction("На задний план", lambda: ed.reorder("bottom"))
        menu.addSeparator()
        menu.addAction("Скрыть / показать", lambda: ed.toggle("visible"))
        menu.addAction("Заблокировать / разблокировать", lambda: ed.toggle("locked"))
        menu.addAction("Дублировать", ed.duplicate)
        menu.addAction("Удалить", ed.delete_selection)
        menu.exec(self.tree.viewport().mapToGlobal(pos))


# ---------------- инспектор ----------------

class ColorField(QWidget):
    committed = Signal(str)

    def __init__(self, allow_none: bool = True, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.swatch = QToolButton()
        self.swatch.setFixedSize(28, 24)
        self.swatch.setToolTip("Выбрать цвет")
        self.swatch.clicked.connect(self._pick)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("нет")
        self.edit.setMaxLength(9)
        self.edit.editingFinished.connect(self._typed)
        lay.addWidget(self.swatch)
        lay.addWidget(self.edit, 1)
        self.clear_btn = QToolButton()
        self.clear_btn.setText("✕")
        self.clear_btn.setToolTip("Без цвета")
        self.clear_btn.setVisible(allow_none)
        self.clear_btn.clicked.connect(lambda: self.committed.emit(""))
        lay.addWidget(self.clear_btn)
        self._value = ""

    def set_value(self, v: str) -> None:
        self._value = v
        self.edit.setText(v)
        c = qcolor(v).name(QColor.NameFormat.HexArgb) if v else "transparent"
        style = f"background:{qcolor(v).name()};" if v else "background:transparent;"
        self.swatch.setStyleSheet(f"QToolButton{{{style}border:1px solid #3A3A3A;border-radius:4px}}")
        del c

    def _typed(self) -> None:
        t = self.edit.text().strip().upper()
        if t and not t.startswith("#"):
            t = "#" + t
        if t != self._value:
            self.committed.emit(t)

    def _pick(self) -> None:
        start = qcolor(self._value) if self._value else QColor("#FFFFFF")
        c = QColorDialog.getColor(start, self, "Цвет", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            hexv = f"#{c.red():02X}{c.green():02X}{c.blue():02X}" + (f"{c.alpha():02X}" if c.alpha() < 255 else "")
            self.committed.emit(hexv)


def _spin(lo=-100000.0, hi=100000.0, decimals=0, suffix="") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setKeyboardTracking(False)
    s.setSuffix(suffix)
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setMinimumWidth(52)  # компактно: в строке инспектора помещаются 4 поля
    s.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return s


class Inspector(QScrollArea):
    def __init__(self, editor: Editor, parent=None, show_document: bool = True):
        super().__init__(parent)
        self.editor = editor
        self.show_document = show_document  # в изолированных редакторах свойства экрана/проекта скрыты
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(12, 10, 12, 10)
        self.setWidget(body)
        self._loading = False
        self._build_node()
        self._build_screen()
        for combo in body.findChildren(QComboBox):  # длинные пункты не должны расширять панель
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
        self.lay.addStretch()
        editor.selection_changed.connect(self.refresh)
        editor.document_changed.connect(self.refresh)
        editor.preview_changed.connect(self._refresh_geometry)
        editor.screen_changed.connect(self.refresh)

    # --- узел
    def _section(self, title: str):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 6, 0, 6)
        v.addWidget(label(title, "H2"))
        f = QFormLayout()
        f.setHorizontalSpacing(12)
        v.addLayout(f)
        self.lay.addWidget(w)
        return w, f

    def _build_node(self) -> None:
        self.sec_layer, f = self._section("Слой")
        self.title = label("", "Muted")
        f.addRow(self.title)
        self.name = QLineEdit()
        self.name.editingFinished.connect(lambda: self._commit_each("name", self.name.text().strip(), "Переименовать"))
        f.addRow("Имя", self.name)
        flags = QHBoxLayout()
        self.visible = QCheckBox("Видим")
        self.visible.clicked.connect(lambda v: self._commit_nodes("visible", v))
        self.locked = QCheckBox("Заблокирован")
        self.locked.clicked.connect(lambda v: self._commit_nodes("locked", v))
        flags.addWidget(self.visible)
        flags.addWidget(self.locked)
        f.addRow(flags)

        self.sec_geom, f = self._section("Положение и размер")
        self.gx, self.gy, self.gw, self.gh = _spin(), _spin(), _spin(0, 100000), _spin(0, 100000)
        r1, r2 = QHBoxLayout(), QHBoxLayout()
        for row, (a, b, la, lb) in ((r1, (self.gx, self.gy, "X", "Y")), (r2, (self.gw, self.gh, "Ш", "В"))):
            row.addWidget(label(la, "Muted"))
            row.addWidget(a)
            row.addWidget(label(lb, "Muted"))
            row.addWidget(b)
        f.addRow(r1)
        f.addRow(r2)
        for s in (self.gx, self.gy, self.gw, self.gh):
            s.valueChanged.connect(self._commit_geometry)
        al = QHBoxLayout()
        for mode, glyph, tip in (("left", "⇤", "По левому краю"), ("hcenter", "↔", "По центру"),
                                 ("right", "⇥", "По правому краю"), ("top", "⤒", "По верху"),
                                 ("vcenter", "↕", "По середине"), ("bottom", "⤓", "По низу")):
            b = QToolButton()
            b.setText(glyph)
            b.setFixedSize(30, 28)
            b.setStyleSheet("padding:0")
            b.setToolTip(tip + " (один элемент — относительно экрана)")
            b.clicked.connect(lambda _=False, m=mode: self.editor.align(m))
            al.addWidget(b)
        for axis, glyph, tip in (("x", "⋯", "Распределить по горизонтали (от 3)"),
                                 ("y", "⋮", "Распределить по вертикали (от 3)")):
            b = QToolButton()
            b.setText(glyph)
            b.setFixedSize(30, 28)
            b.setStyleSheet("padding:0")
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, a=axis: self.editor.distribute(a))
            al.addWidget(b)
        f.addRow(al)

        self._build_layout()
        self._build_extra()

        self.sec_style, f = self._section("Заливка и обводка")
        self.fill = ColorField()
        self.fill.committed.connect(lambda v: self._commit_leaves("fill", v, "Заливка"))
        f.addRow("Заливка", self.fill)
        self.stroke = ColorField()
        self.stroke.committed.connect(lambda v: self._commit_leaves("stroke", v, "Обводка"))
        f.addRow("Обводка", self.stroke)
        self.stroke_w = _spin(0, 1000, 1)
        self.stroke_w.valueChanged.connect(lambda v: self._commit_leaves("stroke_width", v, "Толщина обводки"))
        f.addRow("Толщина", self.stroke_w)
        self.radius = _spin(0, 100000)
        self.radius.valueChanged.connect(lambda v: self._commit_leaves("radius", v, "Скругление"))
        f.addRow("Скругление", self.radius)
        self.opacity = QSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setSuffix(" %")
        self.opacity.setKeyboardTracking(False)
        self.opacity.valueChanged.connect(lambda v: self._commit_leaves("opacity", v / 100, "Непрозрачность"))
        f.addRow("Непрозрачность", self.opacity)

        self.sec_text, f = self._section("Текст")
        self.text = QPlainTextEdit()
        self.text.setFixedHeight(80)
        self._text_timer = QTimer(self)
        self._text_timer.setSingleShot(True)
        self._text_timer.setInterval(600)
        self._text_timer.timeout.connect(lambda: self._commit_leaves("text", self.text.toPlainText(), "Изменить текст",
                                                                     only_type="text"))
        self.text.textChanged.connect(lambda: None if self._loading else self._text_timer.start())
        f.addRow(self.text)
        self.font = QFontComboBox()
        self.font.currentFontChanged.connect(
            lambda fnt: self._commit_leaves("font_family", fnt.family(), "Шрифт", only_type="text"))
        f.addRow("Шрифт", self.font)
        self.font_size = _spin(1, 1000, 0, " px")
        self.font_size.valueChanged.connect(lambda v: self._commit_leaves("font_size", v, "Размер шрифта", "text"))
        f.addRow("Размер", self.font_size)
        self.weight = QComboBox()
        for w in range(100, 1000, 100):
            self.weight.addItem(str(w), w)
        self.weight.currentIndexChanged.connect(
            lambda: self._commit_leaves("font_weight", self.weight.currentData(), "Насыщенность", "text"))
        f.addRow("Насыщенность", self.weight)
        self.text_color = ColorField(allow_none=False)
        self.text_color.committed.connect(lambda v: self._commit_leaves("text_color", v, "Цвет текста", "text"))
        f.addRow("Цвет", self.text_color)
        self.align = QComboBox()
        for key, t in (("left", "Влево"), ("center", "По центру"), ("right", "Вправо")):
            self.align.addItem(t, key)
        self.align.currentIndexChanged.connect(
            lambda: self._commit_leaves("align", self.align.currentData(), "Выравнивание текста", "text"))
        f.addRow("Выравнивание", self.align)

    # --- раскладка
    def _build_layout(self) -> None:
        self.sec_al, f = self._section("Auto Layout")
        self.al_mode = _combo(LAYOUTS)
        self.al_mode.currentIndexChanged.connect(lambda: self._commit_frames("layout", self.al_mode.currentData(),
                                                                             "Режим раскладки"))
        f.addRow("Раскладка", self.al_mode)
        self.al_gap, self.al_row_gap = _spin(0, 100000), _spin(0, 100000)
        self.al_gap.valueChanged.connect(lambda v: self._commit_frames("gap", v, "Промежуток"))
        self.al_row_gap.valueChanged.connect(lambda v: self._commit_frames("row_gap", v, "Промежуток строк"))
        gaps = QHBoxLayout()
        gaps.addWidget(self.al_gap)
        self.al_row_gap_label = label("строки", "Muted")
        gaps.addWidget(self.al_row_gap_label)
        gaps.addWidget(self.al_row_gap)
        f.addRow("Промежуток", gaps)
        self.al_cols = QSpinBox()
        self.al_cols.setRange(1, 64)
        self.al_cols.setKeyboardTracking(False)
        self.al_cols.valueChanged.connect(lambda v: self._commit_frames("grid_columns", v, "Колонки сетки"))
        self.al_cols_label = label("Колонки")
        f.addRow(self.al_cols_label, self.al_cols)
        pads = QHBoxLayout()
        self.al_pads = {}
        for key, tip in (("pad_t", "Сверху"), ("pad_r", "Справа"), ("pad_b", "Снизу"), ("pad_l", "Слева")):
            s = _spin(0, 100000)
            s.setToolTip(f"Отступ: {tip.lower()}")
            s.valueChanged.connect(lambda v, k=key: self._commit_frames(k, v, "Отступы"))
            self.al_pads[key] = s
            pads.addWidget(s)
        f.addRow("Отступы ↑→↓←", pads)
        self.al_main = _combo(MAIN_ALIGN)
        self.al_main.currentIndexChanged.connect(
            lambda: self._commit_frames("main_align", self.al_main.currentData(), "Распределение"))
        f.addRow("По главной оси", self.al_main)
        self.al_cross = _combo(CROSS_ALIGN)
        self.al_cross.currentIndexChanged.connect(
            lambda: self._commit_frames("cross_align", self.al_cross.currentData(), "Выравнивание"))
        f.addRow("По поперечной", self.al_cross)
        self.al_clip = QCheckBox("Обрезать содержимое по фрейму")
        self.al_clip.clicked.connect(lambda v: self._commit_frames("clip", v, "Обрезка"))
        f.addRow(self.al_clip)

        self.sec_size, f = self._section("Размер в раскладке")
        self.sz_h, self.sz_v = _combo(SIZING), _combo(SIZING)
        self.sz_h.currentIndexChanged.connect(lambda: self._commit_geo_nodes("sizing_h", self.sz_h.currentData(),
                                                                            "Ширина: режим"))
        self.sz_v.currentIndexChanged.connect(lambda: self._commit_geo_nodes("sizing_v", self.sz_v.currentData(),
                                                                            "Высота: режим"))
        f.addRow("Ширина", self.sz_h)
        f.addRow("Высота", self.sz_v)
        self.sz_limits = {}
        for row_label, keys in (("Ширина мин/макс", ("min_w", "max_w")), ("Высота мин/макс", ("min_h", "max_h"))):
            row = QHBoxLayout()
            for k in keys:
                s = _spin(0, 100000)
                s.setSpecialValueText("—")
                s.setToolTip("0 — без ограничения")
                s.valueChanged.connect(lambda v, key=k: self._commit_geo_nodes(key, v, "Ограничение размера"))
                self.sz_limits[k] = s
                row.addWidget(s)
            f.addRow(row_label, row)

        self.sec_cons, f = self._section("Привязки")
        self.cons_h, self.cons_v = _combo(CONSTRAINT_H), _combo(CONSTRAINT_V)
        self.cons_h.currentIndexChanged.connect(
            lambda: self._commit_geo_nodes("constraint_h", self.cons_h.currentData(), "Привязка"))
        self.cons_v.currentIndexChanged.connect(
            lambda: self._commit_geo_nodes("constraint_v", self.cons_v.currentData(), "Привязка"))
        f.addRow("По горизонтали", self.cons_h)
        f.addRow("По вертикали", self.cons_v)
        f.addRow(label("Как элемент ведёт себя при изменении размера экрана или фрейма.", "Muted", wrap=True))

    # --- вектор и экземпляр
    def _build_extra(self) -> None:
        self.sec_vec, f = self._section("Вектор")
        self.vec_path = QPlainTextEdit()
        self.vec_path.setFixedHeight(80)
        self.vec_path.setToolTip("Данные пути в системе координат viewBox узла (M, L, C, Q, A, Z…)")
        f.addRow(self.vec_path)
        row = QHBoxLayout()
        apply = QPushButton("Применить путь")
        apply.clicked.connect(self._commit_path)
        row.addWidget(apply)
        self.vec_rule = _combo([("nonzero", "Заливка: ненулевая"), ("evenodd", "Заливка: чёт-нечёт")])
        self.vec_rule.currentIndexChanged.connect(
            lambda: self._commit_type("vector", "fill_rule", self.vec_rule.currentData(), "Правило заливки"))
        row.addWidget(self.vec_rule)
        f.addRow(row)
        self.vec_info = label("", "Muted")
        f.addRow(self.vec_info)

        self.sec_inst, f = self._section("Экземпляр компонента")
        self.inst_info = label("", "Muted", wrap=True)
        f.addRow(self.inst_info)
        self.inst_state = QComboBox()
        self.inst_state.activated.connect(lambda: self.editor.set_instance_state(self.inst_state.currentData()))
        f.addRow("Состояние", self.inst_state)
        row = QHBoxLayout()
        for text, slot in (("Сбросить переопределения", self.editor.reset_overrides_selection),
                           ("Отсоединить", self.editor.detach_selection)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        f.addRow(row)
        self.inst_open = QPushButton("Открыть мастер в Component Builder")
        self.inst_open.clicked.connect(lambda: self.editor.selected_instances() and self.editor.open_component.emit(
            self.editor.selected_instances()[0].component_id))
        f.addRow(self.inst_open)

    def _refresh_extra(self, nodes) -> None:
        vecs = [n for n in self.editor.selected_leaves() if n.type == "vector"]
        self.sec_vec.setVisible(bool(vecs))
        if vecs:
            v = vecs[0]
            if not self.vec_path.hasFocus():
                self.vec_path.setPlainText(v.path)
            self.vec_rule.setCurrentIndex(self.vec_rule.findData(v.fill_rule))
            self.vec_info.setText(f"viewBox {v.vb_w:g} × {v.vb_h:g}")
        insts = self.editor.selected_instances()
        self.sec_inst.setVisible(bool(insts))
        if insts:
            inst = insts[0]
            defn = self.editor.doc.component(inst.component_id)
            n_over = sum(len(p) for p in inst.overrides.values())
            self.inst_info.setText(f"Мастер: «{defn.name if defn else 'не найден'}». "
                                   f"Переопределений: {n_over}. Содержимое меняется только в мастере; "
                                   f"здесь — текст, цвета, видимость.")
            self.inst_state.clear()
            self.inst_state.addItem("По умолчанию", "default")
            for st in (defn.states if defn else {}):
                self.inst_state.addItem(st, st)
            self.inst_state.setCurrentIndex(max(0, self.inst_state.findData(inst.state)))

    def _commit_path(self) -> None:
        vecs = [n for n in self.editor.selected_leaves() if n.type == "vector"]
        if vecs and not self.editor.set_props({vecs[0].id: {"path": self.vec_path.toPlainText().strip()}},
                                              "Изменить путь"):
            self.refresh()

    def _commit_type(self, node_type: str, prop: str, value, label_: str) -> None:
        if self._loading:
            return
        nodes = [n for n in self.editor.selected_leaves() if n.type == node_type and getattr(n, prop) != value]
        if nodes:
            self.editor.set_props({n.id: {prop: value} for n in nodes}, label_)

    def _refresh_layout(self, nodes) -> None:
        ed = self.editor
        geo = [n for n in ed.selected_leaves()]
        frames = [n for n in geo if n.is_frame and not n.is_instance]  # раскладку экземпляра задаёт мастер
        self.sec_al.setVisible(bool(frames))
        if frames:
            f0 = frames[0]
            self.al_mode.setCurrentIndex(self.al_mode.findData(f0.layout))
            auto = f0.layout != "none"
            grid = f0.layout == "grid"
            for w in (self.al_gap, self.al_main, self.al_cross, *self.al_pads.values()):
                w.setEnabled(auto)
            self.al_row_gap.setVisible(grid)
            self.al_row_gap_label.setVisible(grid)
            self.al_cols.setVisible(grid)
            self.al_cols_label.setVisible(grid)
            self.al_main.setEnabled(auto and not grid)
            self.al_gap.setValue(f0.gap)
            self.al_row_gap.setValue(f0.row_gap)
            self.al_cols.setValue(f0.grid_columns)
            for k, s in self.al_pads.items():
                s.setValue(getattr(f0, k))
            self.al_main.setCurrentIndex(self.al_main.findData(f0.main_align))
            self.al_cross.setCurrentIndex(self.al_cross.findData(f0.cross_align))
            self.al_clip.setChecked(f0.clip)
        self.sec_size.setVisible(bool(geo))
        self.sec_cons.setVisible(False)
        if geo:
            g0 = geo[0]
            self.sz_h.setCurrentIndex(self.sz_h.findData(g0.sizing_h))
            self.sz_v.setCurrentIndex(self.sz_v.findData(g0.sizing_v))
            for k, s in self.sz_limits.items():
                s.setValue(getattr(g0, k))
            parents_auto = [ed.auto_layout_parent(n.id) is not None for n in geo]
            self.sec_cons.setVisible(not any(parents_auto))
            self.cons_h.setCurrentIndex(self.cons_h.findData(g0.constraint_h))
            self.cons_v.setCurrentIndex(self.cons_v.findData(g0.constraint_v))

    def _commit_frames(self, prop: str, value, label_: str) -> None:
        if self._loading:
            return
        frames = [n for n in self.editor.selected_leaves() if n.is_frame]
        changes = {n.id: {prop: value} for n in frames if getattr(n, prop) != value}
        if changes and not self.editor.set_props(changes, label_):
            self.refresh()

    def _commit_geo_nodes(self, prop: str, value, label_: str) -> None:
        if self._loading:
            return
        nodes = self.editor.selected_leaves()
        changes = {n.id: {prop: value} for n in nodes if getattr(n, prop) != value}
        if changes and not self.editor.set_props(changes, label_):
            self.refresh()

    # --- экран и проект
    def _build_screen(self) -> None:
        self.sec_screen, f = self._section("Экран")
        self.s_name = QLineEdit()
        self.s_name.editingFinished.connect(
            lambda: self.s_name.text().strip() and self.editor.set_screen_props({"name": self.s_name.text().strip()},
                                                                                label="Переименовать экран"))
        f.addRow("Имя", self.s_name)
        self.s_w, self.s_h = QSpinBox(), QSpinBox()
        for s in (self.s_w, self.s_h):
            s.setRange(1, 20000)
            s.setKeyboardTracking(False)
            s.valueChanged.connect(self._commit_screen_size)
        row = QHBoxLayout()
        row.addWidget(self.s_w)
        row.addWidget(label("×", "Muted"))
        row.addWidget(self.s_h)
        f.addRow("Размер", row)
        self.s_info = label("", "Muted")
        f.addRow(self.s_info)

        self.sec_guides, f = self._section("Направляющие")
        self.guides = QListWidget()
        self.guides.setFixedHeight(110)
        f.addRow(self.guides)
        row = QHBoxLayout()
        self.guide_pos = QSpinBox()
        self.guide_pos.setRange(-20000, 20000)
        row.addWidget(self.guide_pos)
        for axis, text in (("x", "| Верт."), ("y", "— Гориз.")):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, a=axis: self.editor.add_guide(a, self.guide_pos.value()))
            row.addWidget(b)
        f.addRow(row)
        rm = QPushButton("Удалить выбранную")
        rm.clicked.connect(self._remove_guide)
        f.addRow(rm)
        f.addRow(label("Направляющие можно перетаскивать на холсте; вынесите за край экрана, чтобы удалить.",
                       "Muted", wrap=True))

        self.sec_project, f = self._section("Проект")
        self.p_title = QLineEdit()
        self.p_title.editingFinished.connect(
            lambda: self.p_title.text().strip() and self.p_title.text().strip() != self.editor.doc.meta.title
            and self.editor.set_meta({"title": self.p_title.text().strip()}))
        f.addRow("Название", self.p_title)
        self.p_desc = QPlainTextEdit()
        self.p_desc.setFixedHeight(90)
        self._desc_timer = QTimer(self)
        self._desc_timer.setSingleShot(True)
        self._desc_timer.setInterval(700)
        self._desc_timer.timeout.connect(self._commit_desc)
        self.p_desc.textChanged.connect(lambda: None if self._loading else self._desc_timer.start())
        f.addRow("Описание", self.p_desc)

    # --- обновление
    def refresh(self) -> None:
        self._loading = True
        try:
            ed = self.editor
            nodes = ed.selected_nodes()
            leaves = ed.selected_leaves()
            has = bool(nodes)
            for w in (self.sec_layer, self.sec_geom, self.sec_al, self.sec_size, self.sec_cons, self.sec_vec,
                      self.sec_inst):
                w.setVisible(has)
            self.sec_style.setVisible(has)
            texts = [n for n in leaves if n.type == "text"]
            self.sec_text.setVisible(bool(texts))
            for w in (self.sec_screen, self.sec_guides, self.sec_project):
                w.setVisible(not has and ed.screen() is not None and self.show_document)
            if has:
                n0 = nodes[0]
                kinds = {TYPE_NAMES[n.type] for n in nodes}
                self.title.setText(f"Выбрано: {len(nodes)} · {', '.join(sorted(kinds))}")
                self.name.setText(n0.name if len(nodes) == 1 else "")
                self.name.setEnabled(len(nodes) == 1)
                self.visible.setChecked(all(n.visible for n in nodes))
                self.locked.setChecked(all(n.locked for n in nodes))
                self._refresh_geometry()
                self._refresh_layout(nodes)
                self._refresh_extra(nodes)
                if leaves:
                    l0 = leaves[0]
                    self.fill.set_value(l0.fill)
                    self.stroke.set_value(l0.stroke)
                    self.stroke_w.setValue(l0.stroke_width)
                    self.radius.setValue(l0.radius)
                    self.opacity.setValue(round(l0.opacity * 100))
                if texts:
                    t0 = texts[0]
                    if self.text.toPlainText() != t0.text and not self.text.hasFocus():
                        self.text.setPlainText(t0.text)
                    self.font.setCurrentFont(QFont(t0.font_family))
                    self.font_size.setValue(t0.font_size)
                    self.weight.setCurrentIndex(max(0, self.weight.findData(t0.font_weight)))
                    self.text_color.set_value(t0.text_color)
                    self.align.setCurrentIndex(max(0, self.align.findData(t0.align)))
            s = ed.screen()
            if s and not has:
                self.s_name.setText(s.name)
                self.s_w.setValue(s.width)
                self.s_h.setValue(s.height)
                orient = {"portrait": "портрет", "landscape": "ландшафт"}.get(s.orientation, s.orientation)
                self.s_info.setText(f"Android · {orient}" if s.platform == "android" else "Windows · окно")
                self.guides.clear()
                for g in s.guides:
                    it = QListWidgetItem(f"{'Вертикальная' if g.axis == 'x' else 'Горизонтальная'} · {g.pos:g}")
                    it.setData(ROLE_ID, g.id)
                    self.guides.addItem(it)
                self.p_title.setText(ed.doc.meta.title)
                if self.p_desc.toPlainText() != ed.doc.meta.description and not self.p_desc.hasFocus():
                    self.p_desc.setPlainText(ed.doc.meta.description)
        finally:
            self._loading = False

    def _refresh_geometry(self) -> None:
        bb = self.editor.selection_bbox()
        if not bb:
            return
        was = self._loading
        self._loading = True
        for s, v in zip((self.gx, self.gy, self.gw, self.gh), bb):
            s.blockSignals(True)
            s.setValue(v)
            s.blockSignals(False)
        self._loading = was

    # --- запись
    def _commit_geometry(self) -> None:
        if self._loading:
            return
        bb = self.editor.selection_bbox()
        new = (self.gx.value(), self.gy.value(), max(1.0, self.gw.value()), max(1.0, self.gh.value()))
        if bb and tuple(round(v, 2) for v in bb) != new:
            self.editor.set_bbox(new)

    def _commit_nodes(self, prop: str, value) -> None:
        if not self._loading:
            self.editor.set_props({n.id: {prop: value} for n in self.editor.selected_nodes()})

    def _commit_each(self, prop: str, value, label_: str) -> None:
        nodes = self.editor.selected_nodes()
        if not self._loading and value and len(nodes) == 1 and getattr(nodes[0], prop) != value:
            self.editor.set_props({nodes[0].id: {prop: value}}, label_)

    def _commit_leaves(self, prop: str, value, label_: str, only_type: str | None = None) -> None:
        if self._loading:
            return
        leaves = [n for n in self.editor.selected_leaves() if only_type is None or n.type == only_type]
        changes = {n.id: {prop: value} for n in leaves if getattr(n, prop) != value}
        if changes and not self.editor.set_props(changes, label_):
            self.refresh()  # неверное значение — вернуть показ к данным модели

    def _commit_screen_size(self) -> None:
        s = self.editor.screen()
        if self._loading or not s:
            return
        w, h = self.s_w.value(), self.s_h.value()
        if (w, h) != (s.width, s.height):
            self.editor.set_screen_props({"width": w, "height": h}, label="Размер экрана")

    def _commit_desc(self) -> None:
        if self.editor.doc and self.p_desc.toPlainText() != self.editor.doc.meta.description:
            self.editor.set_meta({"description": self.p_desc.toPlainText()})

    def _remove_guide(self) -> None:
        it = self.guides.currentItem()
        if it:
            self.editor.move_guide(it.data(ROLE_ID), None)


# ---------------- полоса экранов ----------------

class ScreensStrip(QWidget):
    def __init__(self, editor: Editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        self.list = QListWidget()
        self.list.setObjectName("Cards")
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setFlow(QListWidget.Flow.LeftToRight)
        self.list.setWrapping(False)
        self.list.setIconSize(QSize(96, 96))
        self.list.setGridSize(QSize(150, 136))
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setFixedHeight(150)
        self.list.currentItemChanged.connect(self._on_current)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list, 1)
        add = QPushButton("+  Экран")
        add.setToolTip("Добавить экран")
        add.clicked.connect(self.add_screen)
        lay.addWidget(add, 0, Qt.AlignmentFlag.AlignTop)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.rebuild)
        editor.document_changed.connect(self._timer.start)
        editor.screen_changed.connect(self._select_current)

    def rebuild(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        doc = self.editor.doc
        if doc:
            for s in doc.screens:
                it = QListWidgetItem(pixmap_icon(render_thumbnail(s, self.editor.artboard_color(), 96, 96, self.editor.doc)),
                                     f"{s.name}\n{s.width}×{s.height}")
                it.setData(ROLE_ID, s.id)
                it.setToolTip(s.name)
                self.list.addItem(it)
        self.list.blockSignals(False)
        self._select_current()

    def _select_current(self) -> None:
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            if self.list.item(i).data(ROLE_ID) == self.editor.screen_id:
                self.list.setCurrentRow(i)
        self.list.blockSignals(False)

    def _on_current(self, item, _prev=None) -> None:
        if item:
            self.editor.set_screen(item.data(ROLE_ID))

    def add_screen(self) -> None:
        doc = self.editor.doc
        if not doc:
            return
        options = [d for d in DEVICES if d.platform in doc.meta.platforms]
        names = [f"{d.name} — {d.width}×{d.height}" for d in options]
        choice, ok = QInputDialog.getItem(self, "Новый экран", "Устройство:", names, 0, False)
        if not ok:
            return
        d = options[names.index(choice)]
        name, ok = QInputDialog.getText(self, "Новый экран", "Имя экрана:", text=f"Экран {len(doc.screens) + 1}")
        if ok and name.strip():
            self.editor.add_screen(Screen(name=name.strip(), platform=d.platform, width=d.width, height=d.height,
                                          device_id=d.id))

    def _menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if not item:
            return
        sid = item.data(ROLE_ID)
        s = self.editor.doc.screen(sid)
        menu = QMenu(self)
        rename = menu.addAction("Переименовать…")
        delete = menu.addAction("Удалить экран")
        delete.setEnabled(len(self.editor.doc.screens) > 1)
        act = menu.exec(self.list.viewport().mapToGlobal(pos))
        if act is rename:
            name, ok = QInputDialog.getText(self, "Экран", "Имя экрана:", text=s.name)
            if ok and name.strip():
                self.editor.set_screen_props({"name": name.strip()}, sid, "Переименовать экран")
        elif act is delete:
            if QMessageBox.question(self, "Удаление экрана",
                                    f"Удалить экран «{s.name}»? Действие можно отменить (Ctrl+Z).") \
                    == QMessageBox.StandardButton.Yes:
                self.editor.remove_screen(sid)


__all__ = ["LayersPanel", "Inspector", "ScreensStrip", "tree"]
