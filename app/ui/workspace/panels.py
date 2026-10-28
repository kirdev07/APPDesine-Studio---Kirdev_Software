"""Панели рабочей области: элементы и слои, инспектор свойств, полоса экранов."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFontComboBox, QFormLayout, QGridLayout, QHBoxLayout,
    QHeaderView,
    QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy,
    QScrollArea, QSpinBox, QSplitter, QTabWidget, QToolButton, QToolTip, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from app.core.document import tree
from app.core.document.model import ELEVATION_DP, Screen
from app.libraries import components
from app.libraries.catalog import DEVICES
from app.ui.widgets import glyph_icon, label, pixmap_icon, separator
from app.ui.workspace.canvas import qcolor, render_thumbnail
from app.ui.workspace.editor import TYPE_NAMES, Editor
from app.ui.workspace.gallery import ComponentGallery

def _dp_factor(screen) -> float | None:
    """Пикселей макета в одном dp (только Android)."""
    if screen is None or screen.platform != "android":
        return None
    from app.engines.preview.devices import screen_dpi
    return screen_dpi(screen) / 160


# Короткие объяснения разделов свойств (кнопка «?»): простыми словами, без терминов
HELP = {
    "geom": "X и Y — где элемент на экране (от левого верхнего угла), Ш и В — ширина и высота. Значения в пикселях "
            "макета; в Android их делят на плотность экрана — рядом показан размер в dp.",
    "al": "Контейнер сам расставляет вложенные элементы столбцом или строкой с одинаковыми промежутками и отступами. "
          "Меняете текст — кнопка сама становится шире; добавляете пункт — список сам удлиняется.",
    "size": "Как элемент занимает место в контейнере: «фиксированный» — свой размер, «заполнить» — растянуться "
            "на свободное место, «по содержимому» — ровно по тексту и вложенным элементам.",
    "cons": "Что происходит с элементом на экране другого размера (телефон, планшет): остаётся у левого края, "
            "у правого, растягивается между краями или держится по центру.",
    "inst": "Это копия компонента из библиотеки проекта. Изменения главного компонента сразу появляются во всех "
            "копиях; здесь можно поменять текст и цвета только этой копии.",
    "img": "Как картинка заполняет рамку: «заполнить» — без полей, лишнее по краям обрезается; «вписать» — целиком, "
           "с полями; «растянуть» — по размеру рамки, пропорции могут исказиться. Маска «круг» — для аватаров.",
    "fx": "Тень — насколько элемент «приподнят» над фоном (уровни Material 3). Градиент — плавный переход между "
          "двумя цветами. Размытие — элемент становится нечётким.",
}

ROLE_ID = Qt.ItemDataRole.UserRole
TYPE_GLYPH = {"rect": "▭", "ellipse": "◯", "text": "T", "group": "▣", "frame": "#", "vector": "✎", "image": "▨",
              "instance": "◈"}
SIZING = [("fixed", "Фиксированный"), ("fill", "Заполнить"), ("hug", "По содержимому")]
LAYOUTS = [("none", "Нет (свободно)"), ("vertical", "Вертикально ↓"), ("horizontal", "Горизонтально →"),
           ("wrap", "С переносом ↵"), ("grid", "Сетка ▦")]
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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        # две вкладки вместо длинной панели: «Добавить» (картинки компонентов) и «Слои» (что уже на экране)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        outer.addWidget(self.tabs)
        top = QWidget()
        lay = QVBoxLayout(top)
        lay.setContentsMargins(10, 10, 10, 4)
        lay.addWidget(label("Простые элементы", "H2"))
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (kind, key, short) in enumerate((("frame", "F", "Контейнер"), ("rect", "R", "Прямоуг."),
                                                ("ellipse", "O", "Эллипс"), ("text", "T", "Текст"))):
            b = QPushButton(f"{TYPE_GLYPH[kind]}  {short}")
            b.setStyleSheet("padding:6px 2px")
            b.setMinimumWidth(b.fontMetrics().horizontalAdvance(b.text()) + 16)
            b.setToolTip(f"{TYPE_NAMES[kind]}: добавить в центр экрана (инструмент — клавиша {key})")
            b.clicked.connect(lambda _=False, k=kind: editor.add_node(k))
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)
        lay.addWidget(label("Компоненты", "H2"))
        self.symbols_button = QPushButton("★ Значки (3900+)")
        self.symbols_button.setToolTip("Google Material Symbols: поиск по-русски, три стиля, заливка (Ctrl+Shift+I)")
        self.symbols_button.clicked.connect(lambda: self.window().project_page.symbols_dialog()
                                            if hasattr(self.window(), "project_page") else None)
        img_row = QHBoxLayout()
        img_row.addWidget(self.symbols_button, 1)
        self.image_button = QPushButton("Фото ▾")
        self.image_button.setToolTip("Картинка из файла или фото-заглушка для макета")
        self.image_menu = QMenu(self.image_button)
        self.image_menu.aboutToShow.connect(self._fill_image_menu)
        self.image_button.setMenu(self.image_menu)
        img_row.addWidget(self.image_button)
        lay.addLayout(img_row)
        self.gallery = ComponentGallery(editor)
        self.gallery.add_requested.connect(lambda kind: editor.insert_component(kind))
        self.gallery.replace_requested.connect(lambda kind: editor.replace_selection(kind))
        lay.addWidget(self.gallery, 1)
        self.comp_filter = self.gallery.search      # совместимость: поиск и плитки галереи
        self.components = self.gallery.tiles
        self.tabs.addTab(top, "Добавить")
        bottom = QWidget()
        lay = QVBoxLayout(bottom)
        lay.setContentsMargins(10, 8, 10, 10)
        self.tabs.addTab(bottom, "Слои")
        head = QHBoxLayout()
        head.addWidget(label("Что на экране", "H2"))
        head.addStretch()
        for text, tip, mode in (("↑", "Выше (Ctrl+])", "up"), ("↓", "Ниже (Ctrl+[)", "down")):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, m=mode: editor.reorder(m))
            head.addWidget(b)
        lay.addLayout(head)
        self.layer_search = QLineEdit()
        self.layer_search.setPlaceholderText("Найти слой по имени…")
        self.layer_search.setClearButtonEnabled(True)
        self.layer_search.textChanged.connect(self.filter_layers)
        lay.addWidget(self.layer_search)
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
        editor.document_changed.connect(self._maybe_rebuild_components)
        self._gallery_key = None

    def _fill_image_menu(self) -> None:
        from app.ui.workspace.images import PLACEHOLDERS
        page = self.window().project_page if hasattr(self.window(), "project_page") else None
        m = self.image_menu
        m.clear()
        if page is None:
            return
        m.addAction("Из файла… (PNG, JPEG, WebP)", lambda: page.image_dialog())
        m.addSection("Фото-заглушка для макета")
        for key, name in PLACEHOLDERS.items():
            m.addAction(name, lambda k=key: page.placeholder_photo(k))

    def _appearance_key(self):
        s, doc = self.editor.screen(), self.editor.doc
        if s is None or doc is None:
            return None
        ap = doc.meta.appearance
        return s.platform, s.device_id, s.width, ap.theme, ap.accent, ap.font_family

    def rebuild_components(self) -> None:
        self._gallery_key = self._appearance_key()
        self.gallery.rebuild()

    def _maybe_rebuild_components(self) -> None:
        if self._appearance_key() != self._gallery_key:  # картинки зависят от оформления и платформы экрана
            self.rebuild_components()

    def filter_components(self, text: str) -> None:
        self.comp_filter.setText(text)

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
        if self.layer_search.text():
            self.filter_layers(self.layer_search.text())

    def filter_layers(self, text: str) -> None:
        """Показать слои, в имени которых есть текст, вместе с их родителями."""
        q = text.strip().lower()

        def walk(it) -> bool:
            hit = not q or q in it.text(0).lower()
            child_hit = False
            for i in range(it.childCount()):
                child_hit = walk(it.child(i)) or child_hit
            it.setHidden(not (hit or child_hit))
            return hit or child_hit
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

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

RECENT_COLORS: list[str] = []  # последние выбранные цвета (за сеанс), новые — первыми


def remember_color(value: str) -> None:
    if not value:
        return
    v = value.upper()
    if v in RECENT_COLORS:
        RECENT_COLORS.remove(v)
    RECENT_COLORS.insert(0, v)
    del RECENT_COLORS[12:]


def swatch_icon(value: str):
    from PySide6.QtGui import QIcon, QPixmap
    pm = QPixmap(14, 14)
    pm.fill(qcolor(value))
    return QIcon(pm)


class ColorField(QWidget):
    committed = Signal(str)

    def __init__(self, allow_none: bool = True, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.swatch = QToolButton()
        self.swatch.setFixedSize(28, 24)
        self.swatch.setToolTip("Выбрать цвет")
        self.swatch.clicked.connect(self._pick)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("нет")
        self.edit.setMaxLength(9)
        self.edit.setMinimumWidth(self.edit.fontMetrics().horizontalAdvance("#DDDDDDDD") + 20)  # код цвета целиком
        self.edit.editingFinished.connect(self._typed)
        lay.addWidget(self.swatch)
        lay.addWidget(self.edit, 1)
        self.clear_btn = QToolButton()
        self.clear_btn.setText("✕")
        self.clear_btn.setToolTip("Без цвета")
        self.clear_btn.setFixedWidth(26)
        self.clear_btn.setStyleSheet("padding:0")
        self.clear_btn.setVisible(allow_none)
        self.clear_btn.clicked.connect(lambda: self.committed.emit(""))
        lay.addWidget(self.clear_btn)
        self.more = QToolButton()
        self.more.setText("▾")
        self.more.setToolTip("Пипетка, последние цвета и цвета проекта")
        self.more.setStyleSheet("padding:0 4px")
        self.more_menu = QMenu(self.more)
        self.more_menu.aboutToShow.connect(self._fill_more)
        self.more.setMenu(self.more_menu)
        self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        lay.addWidget(self.more)
        self.committed.connect(remember_color)
        self._value = ""

    def set_value(self, v: str) -> None:
        self._value = v
        self.edit.setText(v)
        self.edit.setCursorPosition(0)  # видно начало кода цвета («#»), а не хвост
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

    def _editor(self):
        w = self.parentWidget()
        while w is not None and not hasattr(w, "editor"):
            w = w.parentWidget()
        return getattr(w, "editor", None)

    def _fill_more(self) -> None:
        m = self.more_menu
        m.clear()
        ed = self._editor()
        pick = m.addAction("💧 Пипетка — взять цвет с холста", self.eyedrop)
        pick.setEnabled(bool(getattr(ed, "color_picker", None)))
        if RECENT_COLORS:
            m.addSection("Последние")
            for c in RECENT_COLORS:
                m.addAction(swatch_icon(c), c, lambda v=c: self.committed.emit(v))
        doc = getattr(ed, "doc", None)
        colors = doc.colors if doc is not None else []
        if colors:
            m.addSection("Цвета проекта")
            for t in colors[:40]:
                m.addAction(swatch_icon(t.value), t.name, lambda v=t.value: self.committed.emit(v))
        if self._value and hasattr(ed, "add_color_token"):
            m.addSeparator()
            m.addAction("Сохранить в цвета проекта", lambda: ed.add_color_token(self._value))

    def eyedrop(self) -> None:
        ed = self._editor()
        if getattr(ed, "color_picker", None):
            ed.color_picker(self.committed.emit)

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
    s.setMinimumWidth(44)  # компактно: в строке инспектора помещаются 4 поля
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
        self._build_dev()
        for combo in body.findChildren(QComboBox):  # длинные пункты не должны расширять панель
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
        self.lay.addStretch(1)  # лишняя высота — вниз, а не между строками разделов
        editor.selection_changed.connect(self.refresh)
        editor.document_changed.connect(self.refresh)
        editor.preview_changed.connect(self._refresh_geometry)
        editor.screen_changed.connect(self.refresh)

    # --- узел
    def _section(self, title: str, help_text: str = ""):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 6, 0, 6)
        head = QHBoxLayout()
        head.addWidget(label(title, "H2"))
        if help_text:  # «?» рядом с заголовком: короткое объяснение по наведению и щелчку
            q = QToolButton()
            q.setText("?")
            q.setObjectName("HelpButton")
            q.setFixedSize(22, 22)
            q.setStyleSheet("QToolButton{border:1px solid #3A3A3A;border-radius:11px;color:#A0A0A0;padding:0}"
                            "QToolButton:hover{border-color:#2F7BFF;color:#FFFFFF}")
            q.setToolTip(help_text)
            q.clicked.connect(lambda _=False, b=q, t=help_text: QToolTip.showText(
                b.mapToGlobal(b.rect().bottomLeft()), t, b))
            head.addWidget(q)
        head.addStretch()
        v.addLayout(head)
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
        self.sticky = QCheckBox("Липкий — остаётся сверху при прокрутке")
        self.sticky.setToolTip("Шапка раздела, вкладки, строка поиска: когда до них докрутили, они не уходят вверх. "
                               "Дайте элементу заливку — иначе под ним будет просвечивать содержимое")
        self.sticky.clicked.connect(self._commit_sticky)
        f.addRow(self.sticky)
        self.paging = QCheckBox("Листать страницами (с точками)")
        self.paging.setToolTip("Горизонтальный ряд листается пальцем по одной странице; «Точки страниц» сразу после "
                               "него показывают текущую. В Android — HorizontalPager")
        self.paging.clicked.connect(lambda v: self.editor.set_paging(self.editor.selected_nodes()[0].id, v))
        f.addRow(self.paging)

        self.sec_geom, f = self._section("Положение и размер", HELP["geom"])
        self.gx, self.gy, self.gw, self.gh = _spin(), _spin(), _spin(0, 100000), _spin(0, 100000)
        r1, r2 = QHBoxLayout(), QHBoxLayout()
        for row, (a, b, la, lb) in ((r1, (self.gx, self.gy, "X", "Y")), (r2, (self.gw, self.gh, "Ш", "В"))):
            row.addWidget(label(la, "Muted"))
            row.addWidget(a)
            row.addSpacing(8)  # подпись второго поля не липнет к первому
            row.addWidget(label(lb, "Muted"))
            row.addWidget(b)
        f.addRow(r1)
        f.addRow(r2)
        self.dp_hint = label("", "Muted")
        self.dp_hint.setToolTip("Размер в dp — так его считают в Android: пиксели макета, делённые на плотность")
        f.addRow(self.dp_hint)
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
        self.stroke_dash = _combo([("solid", "Сплошная"), ("dash", "Пунктир"), ("dot", "Точки")])
        self.stroke_dash.currentIndexChanged.connect(
            lambda: self._commit_leaves("stroke_dash", self.stroke_dash.currentData(), "Вид обводки"))
        self.stroke_align = _combo([("center", "По краю"), ("inside", "Внутри"), ("outside", "Снаружи")])
        self.stroke_align.setToolTip("Где проходит обводка: по краю элемента, внутри него или снаружи")
        self.stroke_align.currentIndexChanged.connect(
            lambda: self._commit_leaves("stroke_align", self.stroke_align.currentData(), "Положение обводки"))
        f.addRow("Линия", self.stroke_dash)
        f.addRow("Положение", self.stroke_align)
        self.stroke_look = self.stroke_dash
        sides = QHBoxLayout()
        sides.setContentsMargins(0, 0, 0, 0)
        self.side_btns = {}
        for side, glyph, tip in (("t", "↑", "Сверху"), ("r", "→", "Справа"), ("b", "↓", "Снизу"), ("l", "←", "Слева")):
            b = QToolButton()
            b.setText(glyph)
            b.setCheckable(True)
            b.setFixedSize(32, 26)
            b.setStyleSheet("padding:0")
            b.setToolTip(f"Обводка {tip.lower()}")
            b.clicked.connect(self._commit_sides)
            self.side_btns[side] = b
            sides.addWidget(b)
        sides.addStretch()
        self.stroke_side_row = QWidget()
        self.stroke_side_row.setLayout(sides)
        f.addRow("Стороны", self.stroke_side_row)
        self.radius = _spin(0, 100000)
        self.radius.valueChanged.connect(lambda v: self._commit_leaves("radius", v, "Скругление"))
        f.addRow("Скругление", self.radius)
        corners = QHBoxLayout()
        corners.setContentsMargins(0, 0, 0, 0)
        self.corner = {}
        for key, glyph, tip in (("radius_tl", "↖", "левый верхний"), ("radius_tr", "↗", "правый верхний"),
                                ("radius_br", "↘", "правый нижний"), ("radius_bl", "↙", "левый нижний")):
            s = _spin(-1, 100000)
            s.setMinimumWidth(34)
            s.setSpecialValueText(glyph)  # -1 — как общее скругление
            s.setToolTip(f"Скругление: {tip} угол. Пусто ({glyph}) — как общее")
            s.valueChanged.connect(lambda v, k=key: self._commit_leaves(k, v, "Скругление угла"))
            self.corner[key] = s
            corners.addWidget(s)
        self.corner_row = QWidget()
        self.corner_row.setLayout(corners)
        f.addRow("Углы", self.corner_row)
        self.opacity = QSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setSuffix(" %")
        self.opacity.setKeyboardTracking(False)
        self.opacity.valueChanged.connect(lambda v: self._commit_leaves("opacity", v / 100, "Непрозрачность"))
        f.addRow("Непрозрачность", self.opacity)

        self.sec_fx, f = self._section("Эффекты", HELP["fx"])
        self.elevation = QComboBox()
        for lvl, dp in enumerate(ELEVATION_DP):
            self.elevation.addItem("Нет" if lvl == 0 else f"Уровень {lvl} · {dp} dp", lvl)
        self.elevation.setToolTip("Тень по уровням возвышения Material 3; в Android-проекте — Modifier.shadow")
        self.elevation.currentIndexChanged.connect(
            lambda: self._commit_leaves("elevation", self.elevation.currentData(), "Тень"))
        f.addRow("Тень", self.elevation)
        self.gradient = _combo([("none", "Нет"), ("linear", "Линейный"), ("radial", "Радиальный")])
        self.gradient.setToolTip("Градиент от цвета заливки ко второму цвету")
        self.gradient.currentIndexChanged.connect(self._commit_gradient)
        f.addRow("Градиент", self.gradient)
        self.fill2 = ColorField()
        self.fill2.committed.connect(lambda v: self._commit_leaves("fill2", v, "Второй цвет градиента"))
        f.addRow("Второй цвет", self.fill2)
        self.fill3 = ColorField()
        self.fill3.setToolTip("Цвет посередине градиента — для переходов из трёх цветов")
        self.fill3.committed.connect(lambda v: self._commit_leaves("fill3", v, "Средний цвет градиента"))
        f.addRow("Середина", self.fill3)
        self.grad_angle = _spin(-360, 360, 0, "°")
        self.grad_angle.setToolTip("Направление линейного градиента: 180° — сверху вниз, 90° — слева направо")
        self.grad_angle.valueChanged.connect(lambda v: self._commit_leaves("grad_angle", v, "Угол градиента"))
        f.addRow("Угол", self.grad_angle)
        self.blur = _spin(0, 250, 1, " px")
        self.blur.setToolTip("Размытие слоя вместе с содержимым (на Android 12+ — Modifier.blur)")
        self.blur.valueChanged.connect(lambda v: self._commit_leaves("blur", v, "Размытие"))
        f.addRow("Размытие", self.blur)
        self.backdrop = _spin(0, 200, 0, " px")
        self.backdrop.setToolTip("Матовое стекло: размывается то, что под элементом (заливку сделайте "
                                 "полупрозрачной, например #FFFFFF33). В Android-коде — полупрозрачная «морозная» "
                                 "заливка и светлый край; настоящее размытие фона — библиотека Haze")
        self.backdrop.valueChanged.connect(lambda v: self._commit_leaves("backdrop_blur", v, "Матовое стекло"))
        f.addRow("Стекло", self.backdrop)
        self.overlay = ColorField()
        self.overlay.setToolTip("Слой поверх заливки и картинки: затемнить фото под текстом, тонировать цветом")
        self.overlay.committed.connect(self._commit_overlay)
        f.addRow("Слой поверх", self.overlay)
        self.overlay_blend = _combo([("normal", "Обычный"), ("multiply", "Умножение"), ("screen", "Осветление"),
                                     ("overlay", "Перекрытие"), ("darken", "Темнее"), ("lighten", "Светлее")])
        self.overlay_blend.setToolTip("Как слой поверх смешивается с содержимым")
        self.overlay_blend.currentIndexChanged.connect(
            lambda: self._commit_leaves("overlay_blend", self.overlay_blend.currentData(), "Режим наложения"))
        f.addRow("Наложение", self.overlay_blend)
        self.shadow_color = ColorField()
        self.shadow_color.setToolTip("Своя тень любого цвета; в Android — Modifier.dropShadow / innerShadow")
        self.shadow_color.committed.connect(self._commit_shadow_color)
        f.addRow("Своя тень", self.shadow_color)
        self.shadow = {}
        self.shadow_rows = []
        for title, pair in (("Смещение", (("shadow_x", "X", "Смещение по X"), ("shadow_y", "Y", "Смещение по Y"))),
                            ("Размытие", (("shadow_blur", "", "Размытие"), ("shadow_spread", "±", "Растяжение")))):
            sh = QHBoxLayout()
            sh.setContentsMargins(0, 0, 0, 0)
            for key, mark, tip in pair:
                s = _spin(0 if key == "shadow_blur" else -1000, 1000, 0, " px")
                s.setToolTip(tip + " тени")
                s.valueChanged.connect(lambda v, k=key, t=tip: self._commit_leaves(k, v, t + " тени"))
                self.shadow[key] = s
                if mark:
                    sh.addWidget(label(mark, "Muted"))
                sh.addWidget(s)
            row = QWidget()
            row.setLayout(sh)
            self.shadow_rows.append(row)
            f.addRow(title if title == "Смещение" else "Размытие тени", row)
        self.shadow_row = self.shadow_rows[0]
        self.shadow_inset = QCheckBox("Внутренняя тень")
        self.shadow_inset.clicked.connect(lambda v: self._commit_leaves("shadow_inset", v, "Внутренняя тень"))
        f.addRow(self.shadow_inset)

        self.sec_chart, f = self._section("График", "Числа через пробел: «12 30 18 40». Столбцы и линия — "
                                                     "по порядку слева направо, кольцо — доли от целого. "
                                                     "Цвета — у столбцов и долей в слоях графика.")
        self.chart_data = QLineEdit()
        self.chart_data.setPlaceholderText("12 30 18 40")
        self.chart_data.editingFinished.connect(self._commit_chart)
        f.addRow("Числа", self.chart_data)

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
        self.letter_spacing = _spin(-50, 200, 1, " px")
        self.letter_spacing.setToolTip("Интервал между буквами (в Android — letterSpacing)")
        self.letter_spacing.valueChanged.connect(
            lambda v: self._commit_leaves("letter_spacing", v, "Интервал между буквами", "text"))
        self.line_height = _spin(0, 10, 2, " ×")
        self.line_height.setSingleStep(0.1)
        self.line_height.setSpecialValueText("обычная")
        self.line_height.setToolTip("Высота строки в долях размера шрифта: 1.5 — полуторный интервал")
        self.line_height.valueChanged.connect(
            lambda v: self._commit_leaves("line_height", round(v, 2), "Высота строки", "text"))
        sp = QHBoxLayout()
        sp.setContentsMargins(0, 0, 0, 0)
        sp.addWidget(self.letter_spacing)  # слева — между буквами, справа — высота строки (подсказки по наведению)
        sp.addWidget(self.line_height)
        f.addRow("Интервалы", sp)
        self.italic = QCheckBox("Курсив")
        self.italic.clicked.connect(lambda v: self._commit_leaves("italic", v, "Курсив", "text"))
        self.decoration = _combo([("none", "Без линии"), ("underline", "Подчёркнутый"), ("strike", "Зачёркнутый")])
        self.decoration.currentIndexChanged.connect(
            lambda: self._commit_leaves("decoration", self.decoration.currentData(), "Линия текста", "text"))
        st = QHBoxLayout()
        st.setContentsMargins(0, 0, 0, 0)
        st.addWidget(self.italic)
        st.addWidget(self.decoration)
        f.addRow("Начертание", st)
        self.text_case = _combo([("none", "Как набрано"), ("upper", "ВСЕ ЗАГЛАВНЫЕ"), ("lower", "все строчные"),
                                 ("title", "Каждое Слово")])
        self.text_case.currentIndexChanged.connect(
            lambda: self._commit_leaves("text_case", self.text_case.currentData(), "Регистр", "text"))
        f.addRow("Регистр", self.text_case)
        self.max_lines = QSpinBox()
        self.max_lines.setRange(0, 1000)
        self.max_lines.setSpecialValueText("все")
        self.max_lines.setKeyboardTracking(False)
        self.max_lines.setToolTip("Не больше стольких строк; лишнее обрезается многоточием «…»")
        self.max_lines.valueChanged.connect(
            lambda v: self._commit_leaves("max_lines", v, "Число строк", "text"))
        f.addRow("Макс. строк", self.max_lines)
        self.editable = QCheckBox("Поле ввода в предпросмотре")
        self.editable.setToolTip("В предпросмотре текст можно набирать; исходный текст — подсказка")
        self.editable.clicked.connect(lambda v: self._commit_leaves("editable", v, "Поле ввода", "text"))
        f.addRow(self.editable)
        self.input_var = QComboBox()
        self.input_var.setToolTip("Текстовая переменная, которая получает набранный текст")
        self.input_var.currentIndexChanged.connect(
            lambda: self._commit_leaves("input_var", self.input_var.currentData() or "", "Переменная поля", "text"))
        f.addRow("Значение в", self.input_var)

    # --- раскладка
    def _build_layout(self) -> None:
        self.sec_al, f = self._section("Выстраивание содержимого", HELP["al"])
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
        self.al_clip = QCheckBox("Обрезать содержимое по краю")
        self.al_clip.clicked.connect(lambda v: self._commit_frames("clip", v, "Обрезка"))
        f.addRow(self.al_clip)
        self.al_scroll = _combo([("none", "Нет"), ("vertical", "Вертикальная"), ("horizontal", "Горизонтальная")])
        self.al_scroll.setToolTip("Прокрутка содержимого в предпросмотре (колесо мыши или перетаскивание)")
        self.al_scroll.currentIndexChanged.connect(
            lambda: self._commit_frames("scroll", self.al_scroll.currentData(), "Прокрутка"))
        f.addRow("Прокрутка", self.al_scroll)

        self.sec_size, f = self._section("Размер внутри контейнера", HELP["size"])
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

        self.sec_cons, f = self._section("При изменении размера экрана", HELP["cons"])
        self.cons_h, self.cons_v = _combo(CONSTRAINT_H), _combo(CONSTRAINT_V)
        self.cons_h.currentIndexChanged.connect(
            lambda: self._commit_geo_nodes("constraint_h", self.cons_h.currentData(), "Поведение при изменении размера"))
        self.cons_v.currentIndexChanged.connect(
            lambda: self._commit_geo_nodes("constraint_v", self.cons_v.currentData(), "Поведение при изменении размера"))
        f.addRow("По горизонтали", self.cons_h)
        f.addRow("По вертикали", self.cons_v)
        f.addRow(label("Как элемент ведёт себя на экране другого размера или в растянутом контейнере.", "Muted", wrap=True))

    # --- вектор и экземпляр
    # --- для разработчика
    def _build_dev(self) -> None:
        self.sec_dev, f = self._section("Для разработчика", "Размеры в dp, цвета с ролью темы и код Jetpack Compose "
                                        "выделенного элемента — тот же, что попадёт в проект Android Studio.")
        self.dev_toggle = QPushButton("Показать код ▾")
        self.dev_toggle.setCheckable(True)
        self.dev_toggle.setToolTip("Свойства и код Compose выделенного элемента")
        self.dev_toggle.toggled.connect(lambda on: (self.dev_toggle.setText("Скрыть код ▴" if on else "Показать код ▾"),
                                                    self._refresh_dev()))
        f.addRow(self.dev_toggle)
        self.dev_spec = QPlainTextEdit()
        self.dev_spec.setReadOnly(True)
        self.dev_spec.setFixedHeight(190)
        self.dev_code = QPlainTextEdit()
        self.dev_code.setReadOnly(True)
        self.dev_code.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.dev_code.setFixedHeight(220)
        self.dev_code.setStyleSheet("font-family: Consolas, 'Cascadia Mono', monospace; font-size: 9pt;")  # код — моноширинным
        f.addRow(self.dev_spec)
        f.addRow(self.dev_code)
        row = QHBoxLayout()
        self.dev_copy_spec = QPushButton("Копировать свойства")
        self.dev_copy_code = QPushButton("Копировать код")
        self.dev_copy_spec.clicked.connect(lambda: self._copy_dev(self.dev_spec.toPlainText(), "Свойства"))
        self.dev_copy_code.clicked.connect(lambda: self._copy_dev(self.dev_code.toPlainText(), "Код Compose"))
        row.addWidget(self.dev_copy_spec)
        row.addWidget(self.dev_copy_code)
        self.dev_buttons = QWidget()
        self.dev_buttons.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        f.addRow(self.dev_buttons)
        self._dev_key = None

    def _copy_dev(self, text: str, what: str) -> None:
        QApplication.clipboard().setText(text)
        self.editor.message.emit(f"{what} скопированы в буфер обмена")

    def _refresh_dev(self) -> None:
        """Свойства и код считаются, только когда раздел раскрыт (и элемент или документ поменялись)."""
        ed = self.editor
        nodes = ed.selected_nodes()
        one = len(nodes) == 1 and ed.screen() is not None
        self.sec_dev.setVisible(one)
        on = one and self.dev_toggle.isChecked()
        for w in (self.dev_spec, self.dev_code, self.dev_buttons):
            w.setVisible(on)
        if not on:
            self._dev_key = None
            return
        n, s = nodes[0], ed.screen()
        key = (n.id, s.id, repr(n.to_dict()), repr(ed.doc.meta.appearance))
        if key == self._dev_key:
            return
        self._dev_key = key
        from app.exporters import dev_info
        self.dev_spec.setPlainText(dev_info.spec_text(dev_info.spec_rows(ed.doc, s, n)))
        try:
            code = dev_info.compose_snippet(ed.doc, s, n.id)
        except Exception as e:  # noqa: BLE001 — показать причину вместо пустого поля
            code = f"// не удалось построить код: {e}"
        real = bool(code) and not code.startswith("// не удалось")
        if not code:
            code = ("// Код Compose — для экранов Android." if s.platform != "android" else
                    "// Это часть компонента: код — у самого компонента (выделите его целиком).")
        self.dev_code.setPlainText(code)
        self.dev_copy_code.setEnabled(real)

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

        self.sec_img, f = self._section("Картинка", HELP["img"])
        self.img_fit = _combo([("cover", "Заполнить (обрезать края)"), ("contain", "Вписать целиком"),
                               ("fill", "Растянуть")])
        self.img_fit.currentIndexChanged.connect(
            lambda: self._commit_type("image", "fit", self.img_fit.currentData(), "Картинка в рамке"))
        f.addRow("В рамке", self.img_fit)
        mask = QHBoxLayout()
        for text, mode in (("Без маски", "none"), ("Скругление", "round"), ("Круг", "circle")):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, m=mode: self._image_mask(m))
            mask.addWidget(b)
        f.addRow("Маска", mask)
        self.img_info = label("", "Muted", wrap=True)
        f.addRow(self.img_info)
        self.img_replace = QPushButton("Заменить картинку…")
        self.img_replace.clicked.connect(lambda: self.window().project_page.image_dialog()
                                         if hasattr(self.window(), "project_page") else None)
        f.addRow(self.img_replace)

        self.sec_inst, f = self._section("Копия компонента", HELP["inst"])
        self.inst_info = label("", "Muted", wrap=True)
        f.addRow(self.inst_info)
        self.inst_state = QComboBox()
        self.inst_state.activated.connect(lambda: self.editor.set_instance_state(self.inst_state.currentData()))
        f.addRow("Состояние", self.inst_state)
        self.variant_box = QWidget()  # выбор значения у каждого свойства варианта (Размер, Стиль …)
        self.variant_form = QFormLayout(self.variant_box)
        self.variant_form.setContentsMargins(0, 0, 0, 0)
        f.addRow(self.variant_box)
        self.variant_presets = QPushButton("+ Варианты ▾")
        self.variant_presets.setToolTip("Добавить компоненту готовые варианты: размер S / M / L, стиль, тема")
        self.variant_menu = QMenu(self.variant_presets)
        self.variant_menu.aboutToShow.connect(self._fill_variant_menu)
        self.variant_presets.setMenu(self.variant_menu)
        f.addRow(self.variant_presets)
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
        imgs = [n for n in self.editor.selected_leaves() if n.type == "image"]
        self.sec_img.setVisible(bool(imgs))
        if imgs:
            im = imgs[0]
            self.img_fit.setCurrentIndex(max(0, self.img_fit.findData(im.fit)))
            a = self.editor.doc.asset(im.asset_id) if self.editor.doc else None
            self.img_info.setText(f"«{a.name}» · {a.ext.upper()} · {a.size // 1024} КБ" if a else "Нет файла")
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
            while self.variant_form.rowCount():
                self.variant_form.removeRow(0)
            for axis, vals in (defn.variants if defn else {}).items():
                combo = QComboBox()
                for v in vals:
                    combo.addItem(v, v)
                chosen = inst.variant.get(axis) if inst.variant.get(axis) in vals else next(iter(vals), "")
                combo.setCurrentIndex(max(0, combo.findData(chosen)))
                combo.activated.connect(lambda _i, a=axis, c=combo: self.editor.set_instance_variant(a, c.currentData()))
                self.variant_form.addRow(axis, combo)
            self.variant_box.setVisible(bool(defn and defn.variants))

    def _fill_variant_menu(self) -> None:
        from app.engines.components.variants import PRESET_AXES
        m = self.variant_menu
        m.clear()
        insts = self.editor.selected_instances()
        defn = self.editor.doc.component(insts[0].component_id) if insts and self.editor.doc else None
        if defn is None:
            return
        for key, axis in PRESET_AXES.items():
            title = {"size": "Размер (S / M / L)", "style": "Стиль (заливка / тональный / контур / текст)",
                     "theme": "Тема (светлая / тёмная)"}[key]
            a = m.addAction(title + (" — заменить" if axis in defn.variants else ""),
                            lambda k=key, c=defn.id: self.editor.add_variant_preset(c, k))
            a.setToolTip(f"Свойство «{axis}» у компонента «{defn.name}» и всех его копий")

    def _image_mask(self, mode: str) -> None:
        """Маска картинки: без скругления, скругление 16 dp или круг (квадрат с радиусом половины стороны)."""
        from app.engines.preview.devices import screen_dpi
        s = self.editor.screen()
        k = screen_dpi(s) / 160 if s is not None and s.platform == "android" else 1.0
        changes = {}
        for n in self.editor.selected_leaves():
            if n.type != "image":
                continue
            if mode == "none":
                changes[n.id] = {"radius": 0.0, "clip_path": ""}  # и маску формой тоже
            elif mode == "round":
                changes[n.id] = {"radius": round(16 * k, 2), "clip_path": ""}
            else:
                parent = tree.find(s, n.id)[1]
                stretched = parent is not None and parent.layout == "vertical" and parent.cross_align == "stretch"
                side = n.w if stretched else min(n.w, n.h)  # столбец растягивает ширину — круг на всю ширину
                changes[n.id] = {"w": side, "h": side, "radius": side / 2, "fit": "cover", "sizing_h": "fixed",
                                 "sizing_v": "fixed"}
        if changes:
            self.editor.set_props(changes, "Маска картинки")

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
            rows = grid or f0.layout == "wrap"  # промежуток между строками — у сетки и у переноса
            for w in (self.al_gap, self.al_main, self.al_cross, *self.al_pads.values()):
                w.setEnabled(auto)
            self.al_row_gap.setVisible(rows)
            self.al_row_gap_label.setVisible(rows)
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
            self.al_scroll.setCurrentIndex(max(0, self.al_scroll.findData(f0.scroll)))
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
            s.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)  # стрелки в тёмной теме не рисуются — без них
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
        self.s_auto = QComboBox()
        self.s_auto.setToolTip("При открытии экрана — пауза и переход на другой (заставка, приветствие)")
        self.s_auto.activated.connect(self._commit_auto)
        self.s_auto_ms = _spin(0.1, 60, 1, " с")
        self.s_auto_ms.setSingleStep(0.5)
        self.s_auto_ms.valueChanged.connect(self._commit_auto)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.s_auto, 1)
        row.addWidget(self.s_auto_ms)
        f.addRow("Автопереход", row)
        self.s_comments = QListWidget()
        self.s_comments.setMaximumHeight(120)
        self.s_comments.setToolTip("Двойной щелчок — открыть; новый — правый клик по холсту")
        self.s_comments.itemDoubleClicked.connect(
            lambda it: self.window().project_page.edit_comment(it.data(ROLE_ID))
            if hasattr(self.window(), "project_page") else None)
        f.addRow("Комментарии", self.s_comments)

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
                      self.sec_inst, self.sec_img):
                w.setVisible(has)
            self.sec_style.setVisible(has)
            self.sec_fx.setVisible(has)
            chart = nodes[0] if len(nodes) == 1 and nodes[0].role.startswith("chart.") else None
            self.sec_chart.setVisible(chart is not None)
            if chart is not None and not self.chart_data.hasFocus():
                self.chart_data.setText(chart.data)
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
                parent = tree.find(ed.screen(), n0.id)[1] if len(nodes) == 1 else None
                in_scroll = parent is not None and parent.is_frame and parent.scroll == "vertical"
                self._row_visible(self.sticky, in_scroll)
                self.sticky.setChecked(n0.sticky)
                pageable = len(nodes) == 1 and n0.is_frame and len(n0.children) > 1 and n0.layout != "vertical"
                self._row_visible(self.paging, pageable)
                self.paging.setChecked(n0.paging)
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
                    self.elevation.setCurrentIndex(l0.elevation)
                    self.gradient.setCurrentIndex(max(0, self.gradient.findData(l0.gradient)))
                    self.fill2.set_value(l0.fill2)
                    self.grad_angle.setValue(l0.grad_angle)
                    self.blur.setValue(l0.blur)
                    linear = l0.gradient == "linear"
                    self.fill2.setEnabled(l0.gradient != "none")
                    self.fill3.set_value(l0.fill3)
                    self.fill3.setEnabled(l0.gradient != "none")
                    self.grad_angle.setEnabled(linear)
                    self.stroke_dash.setCurrentIndex(max(0, self.stroke_dash.findData(l0.stroke_dash)))
                    self.stroke_align.setCurrentIndex(max(0, self.stroke_align.findData(l0.stroke_align)))
                    for side, b in self.side_btns.items():
                        b.setChecked(side in l0.stroke_sides)
                    for key, s in self.corner.items():
                        s.setValue(getattr(l0, key))
                    self.backdrop.setValue(l0.backdrop_blur)
                    self.overlay.set_value(l0.overlay)
                    self.overlay_blend.setCurrentIndex(max(0, self.overlay_blend.findData(l0.overlay_blend)))
                    self.overlay_blend.setEnabled(bool(l0.overlay))
                    self.shadow_color.set_value(l0.shadow_color)
                    for key, s in self.shadow.items():
                        s.setValue(getattr(l0, key))
                        s.setEnabled(bool(l0.shadow_color))
                    self.shadow_inset.setChecked(l0.shadow_inset)
                    self.shadow_inset.setEnabled(bool(l0.shadow_color))
                if texts:
                    t0 = texts[0]
                    if self.text.toPlainText() != t0.text and not self.text.hasFocus():
                        self.text.setPlainText(t0.text)
                    self.font.setCurrentFont(QFont(t0.font_family))
                    self.font_size.setValue(t0.font_size)
                    self.weight.setCurrentIndex(max(0, self.weight.findData(t0.font_weight)))
                    self.text_color.set_value(t0.text_color)
                    self.align.setCurrentIndex(max(0, self.align.findData(t0.align)))
                    self.letter_spacing.setValue(t0.letter_spacing)
                    self.line_height.setValue(t0.line_height)
                    self.italic.setChecked(t0.italic)
                    self.decoration.setCurrentIndex(max(0, self.decoration.findData(t0.decoration)))
                    self.text_case.setCurrentIndex(max(0, self.text_case.findData(t0.text_case)))
                    self.max_lines.setValue(t0.max_lines)
                    own = all(not t.ref for t in texts)  # поле экземпляра задаёт мастер-компонент
                    self.editable.setEnabled(own)
                    self.editable.setChecked(t0.editable)
                    self.input_var.clear()
                    self.input_var.addItem("— не связано —", "")
                    for v in (ed.doc.variables if ed.doc else []):
                        if v.type == "text":
                            self.input_var.addItem(v.name, v.id)
                    self.input_var.setCurrentIndex(max(0, self.input_var.findData(t0.input_var)))
                    self.input_var.setEnabled(own and t0.editable)
            s = ed.screen()
            if s and not has:
                self.s_name.setText(s.name)
                self.s_w.setValue(s.width)
                self.s_h.setValue(s.height)
                orient = {"portrait": "портрет", "landscape": "ландшафт"}.get(s.orientation, s.orientation)
                k = _dp_factor(s)
                self.s_info.setText(f"Android · {orient} · {s.width / k:.0f} × {s.height / k:.0f} dp" if k
                                    else "Windows · окно")
                self.s_comments.clear()
                for i, c in enumerate(s.comments, 1):
                    it = QListWidgetItem(f"{'✓' if c.resolved else '●'} {i}. {c.text.splitlines()[0][:40]}")
                    it.setData(ROLE_ID, c.id)
                    if c.resolved:
                        it.setForeground(QColor("#6B6B6B"))
                    self.s_comments.addItem(it)
                self._row_visible(self.s_comments, bool(s.comments))
                auto = ed.auto_advance()
                self.s_auto.clear()
                if auto == "custom":
                    self.s_auto.addItem("своё правило в «Логике»", "custom")
                else:
                    self.s_auto.addItem("нет", "")
                    for x in ed.doc.screens:
                        if x.id != s.id and x.platform == s.platform:
                            self.s_auto.addItem(f"→ {x.name}", x.id)
                    if auto:
                        self.s_auto.setCurrentIndex(max(0, self.s_auto.findData(auto[0])))
                    self.s_auto_ms.setValue(auto[1] / 1000 if auto else 2.0)  # пауза по умолчанию — 2 с
                self.s_auto.setEnabled(auto != "custom")
                self.s_auto_ms.setEnabled(bool(auto) and auto != "custom")
                self.guides.clear()
                for g in s.guides:
                    it = QListWidgetItem(f"{'Вертикальная' if g.axis == 'x' else 'Горизонтальная'} · {g.pos:g}")
                    it.setData(ROLE_ID, g.id)
                    self.guides.addItem(it)
                self.p_title.setText(ed.doc.meta.title)
                if self.p_desc.toPlainText() != ed.doc.meta.description and not self.p_desc.hasFocus():
                    self.p_desc.setPlainText(ed.doc.meta.description)
            if self.simple:  # простой режим: без привязок, размеров в раскладке, точек пути и направляющих
                for w in (self.sec_size, self.sec_cons, self.sec_vec, self.sec_guides):
                    w.setVisible(False)
            for w in (self.stroke_look, self.stroke_align, self.stroke_side_row, self.corner_row, *self.shadow_rows, self.shadow_inset):
                self._row_visible(w, not self.simple)  # простой режим: без тонкой настройки обводки, углов и тени
            self._refresh_dev()
        finally:
            self._loading = False

    simple = False

    def set_simple(self, on: bool) -> None:
        self.simple = on
        self.refresh()
        if self.simple:
            for w in (self.sec_size, self.sec_cons, self.sec_vec, self.sec_guides):
                w.setVisible(False)

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
        scr = self.editor.screen()
        k = _dp_factor(scr)
        self.dp_hint.setVisible(k is not None)
        if k:
            self.dp_hint.setText(f"В Android: {bb[2] / k:.0f} × {bb[3] / k:.0f} dp, отступ слева {bb[0] / k:.0f} dp")
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

    def _commit_auto(self, *_):
        if self._loading:
            return
        target = self.s_auto.currentData()
        if target == "custom":
            return
        cur = self.editor.auto_advance()
        ms = int(round(self.s_auto_ms.value() * 1000))
        if not target:
            if cur:
                self.editor.set_auto_advance(None)
        elif not cur or (cur[0], cur[1]) != (target, ms):
            self.editor.set_auto_advance(target, ms, cur[2] if cur else "fade")

    @staticmethod
    def _row_visible(w: QWidget, on: bool) -> None:
        """Скрыть строку формы вместе с подписью."""
        box = w.parentWidget().layout() if w.parentWidget() else None
        for i in range(box.count() if box else 0):
            form = box.itemAt(i).layout()
            if isinstance(form, QFormLayout) and form.indexOf(w) >= 0:
                form.setRowVisible(w, on)
                return
        w.setVisible(on)

    def _commit_chart(self) -> None:
        nodes = self.editor.selected_nodes()
        if self._loading or len(nodes) != 1 or self.chart_data.text().strip() == nodes[0].data:
            return
        if not self.editor.set_chart_data(nodes[0].id, self.chart_data.text()):
            self.chart_data.setText(nodes[0].data)

    def _commit_sides(self) -> None:
        sides = "".join(s for s, b in self.side_btns.items() if b.isChecked())
        if not sides:  # без сторон обводки не бывает — снять последнюю нельзя
            self.refresh()
            return
        self._commit_leaves("stroke_sides", sides, "Стороны обводки")

    def _commit_sticky(self, on: bool) -> None:
        """Липкий без заливки просвечивал бы: такой элемент получает цвет фона экрана."""
        if self._loading:
            return
        changes = {}
        for n in self.editor.selected_nodes():
            props = {"sticky": on}
            if on and not n.fill and n.type != "text":
                props["fill"] = self.editor.artboard_color()
            changes[n.id] = props
        self.editor.set_props(changes, "Липкий элемент")

    def _commit_overlay(self, value: str) -> None:
        """Слой поверх без прозрачности закрыл бы всё: цвету без альфы ставится 40 %."""
        if value and len(value) == 7:
            value += "66"
        self._commit_leaves("overlay", value, "Слой поверх")

    def _commit_shadow_color(self, value: str) -> None:
        """Тень без прозрачности выглядит грубо: цвету без альфы ставится 40 %."""
        if value and len(value) == 7:
            value += "66"
        self._commit_leaves("shadow_color", value, "Своя тень")

    def _commit_gradient(self) -> None:
        """Градиент без второго цвета не виден: подставляется более тёмный вариант заливки."""
        if self._loading:
            return
        kind = self.gradient.currentData()
        changes = {}
        for n in self.editor.selected_leaves():
            props = {"gradient": kind} if n.gradient != kind else {}
            if kind != "none" and not n.fill2:
                props["fill2"] = QColor(n.fill or "#2F7BFF").darker(160).name().upper()
            if props:
                changes[n.id] = props
        if changes:
            self.editor.set_props(changes, "Градиент")

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
        self.list.setIconSize(QSize(56, 56))       # компактная полоса: холсту остаётся основная высота
        self.list.setGridSize(QSize(132, 86))
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setFixedHeight(96)
        self.list.currentItemChanged.connect(self._on_current)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list, 1)
        add = QPushButton("+  Экран ▾")
        add.setToolTip("Добавить пустой или готовый экран (вход, список, профиль, настройки, чат, корзина)")
        self.add_menu = QMenu(add)
        self.add_menu.aboutToShow.connect(self._fill_add_menu)
        add.setMenu(self.add_menu)
        self.add_button = add
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
                it = QListWidgetItem(pixmap_icon(render_thumbnail(s, self.editor.artboard_color(), 56, 56, self.editor.doc)),
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

    def _fill_add_menu(self) -> None:
        from app.libraries.screen_templates import all_templates
        m = self.add_menu
        m.clear()
        cur = self.editor.screen()
        m.addAction("Пустой экран", self.editor.add_blank_screen).setEnabled(cur is not None)
        m.addAction("Пустой экран для другого устройства…", self.add_screen)
        if cur is not None and cur.platform == "android":
            m.addSeparator()
            m.addSection("Готовые экраны")
            for key, (title, _) in all_templates().items():
                m.addAction(title, lambda k=key: self.editor.add_template_screen(k))

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
