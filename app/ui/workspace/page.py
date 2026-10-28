"""Fusion Workspace: панель инструментов, холст и стыкуемые панели."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QMimeData, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QDockWidget, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu, QSizePolicy, QToolBar, QToolButton,
    QWidget,
)

from app.context import AppContext
from app.core.document.model import ProjectDocument
from app.ui.widgets import glyph_icon, label, stage_badge
from app.core.document import tree
from app.ui.workspace.canvas import CanvasView
from app.ui.workspace.editor import (
    CLIPBOARD_MIME, TOOL_ELLIPSE, TOOL_FRAME, TOOL_HAND, TOOL_PEN, TOOL_RECT, TOOL_SELECT, TOOL_TEXT, TYPE_NAMES, Editor,
)
from app.ui.workspace.layout_tools import DiagnosticsPanel, ResponsiveDialog
from app.ui.workspace.panels import Inspector, LayersPanel, ScreensStrip

TOOLS = [(TOOL_SELECT, "➤", "Выделение", "V"), (TOOL_HAND, "✋", "Рука (или пробел)", "H"),
         (TOOL_FRAME, "#", "Контейнер", "F"), (TOOL_RECT, "▭", "Прямоугольник", "R"), (TOOL_ELLIPSE, "◯", "Эллипс", "O"),
         (TOOL_TEXT, "T", "Текст", "T"), (TOOL_PEN, "✎", "Перо (щелчки — точки, двойной щелчок — готово)", "P")]
ZOOMS = [25, 50, 75, 100, 150, 200, 400, 800]


class WorkspacePage(QMainWindow):
    changed = Signal()

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setObjectName("Page")
        self.ctx = ctx
        self.editor = Editor(self)
        s = ctx.settings
        self.editor.grid_visible = s.get("workspace/grid_visible")
        self.editor.grid_size = s.get("workspace/grid_size")
        self.editor.snap_enabled = s.get("workspace/snap")
        self.editor.guides_visible = s.get("workspace/guides_visible")
        self._forced_dirty = False
        self.setDockOptions(QMainWindow.DockOption.AnimatedDocks | QMainWindow.DockOption.AllowNestedDocks)

        self.canvas = CanvasView(self.editor)
        self._build_actions()
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._build_toolbar())
        self.setCentralWidget(self.canvas)

        self.layers = LayersPanel(self.editor)
        self.layers.setMinimumWidth(250)
        self.inspector = Inspector(self.editor)
        self.inspector.setMinimumWidth(330)
        self.screens = ScreensStrip(self.editor)
        self.dock_layers = self._dock("Элементы и слои", self.layers, Qt.DockWidgetArea.LeftDockWidgetArea, 280)
        self.dock_inspector = self._dock("Свойства", self.inspector, Qt.DockWidgetArea.RightDockWidgetArea, 320)
        self.dock_screens = self._dock("Экраны", self.screens, Qt.DockWidgetArea.BottomDockWidgetArea, 0)
        self.diagnostics = DiagnosticsPanel(self.editor)
        self.dock_diag = self._dock("Диагностика раскладки", self.diagnostics, Qt.DockWidgetArea.BottomDockWidgetArea, 0)
        self.tabifyDockWidget(self.dock_screens, self.dock_diag)
        self.dock_screens.raise_()
        self._docks_sized = False

        self.editor.document_changed.connect(self._on_changed)
        self.editor.selection_changed.connect(self._update_actions)
        self.editor.view_changed.connect(self._sync_tools)
        self.canvas.zoom_changed.connect(lambda z: self.zoom_combo.setEditText(f"{round(z * 100)}%"))
        self.canvas.context_menu.connect(self.show_context_menu)
        self._build_selection_bar()
        self._build_start_hint()
        self.editor.selection_changed.connect(self._sync_selection_bar)
        self.editor.document_changed.connect(self._sync_selection_bar)
        self.editor.screen_changed.connect(self._sync_selection_bar)
        self.set_simple(bool(s.get("workspace/simple")))
        self.canvas.cursor_moved.connect(lambda x, y: self.pos_label.setText(f"x {x:.0f}   y {y:.0f}"))
        self._update_actions()

    def showEvent(self, e):
        super().showEvent(e)
        if not self._docks_sized:  # размеры доков применяются только у показанного окна
            self._docks_sized = True
            self.resizeDocks([self.dock_screens], [110], Qt.Orientation.Vertical)  # холсту — основная высота

    # ---------- построение ----------
    def _dock(self, title: str, widget: QWidget, area, width: int) -> QDockWidget:
        d = QDockWidget(title, self)
        d.setObjectName(title)
        d.setWidget(widget)
        d.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetClosable
                      | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(area, d)
        if width:
            self.resizeDocks([d], [width], Qt.Orientation.Horizontal)
        return d

    def _action(self, text: str, slot, shortcut=None, checkable=False, tip: str = "") -> QAction:
        a = QAction(text, self)
        if shortcut is not None:
            seqs = shortcut if isinstance(shortcut, list) else [shortcut]
            a.setShortcuts([QKeySequence(s) if isinstance(s, str) else QKeySequence(s) for s in seqs])
        a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        a.setCheckable(checkable)
        a.setToolTip(tip or text)
        a.triggered.connect(slot)
        self.addAction(a)
        return a

    def _build_actions(self) -> None:
        ed = self.editor
        K = QKeySequence.StandardKey
        self.a_undo = self._action("Отменить", ed.undo, K.Undo)
        self.a_redo = self._action("Повторить", ed.redo, [K.Redo, "Ctrl+Shift+Z"])
        self.a_cut = self._action("Вырезать", lambda: self._to_clipboard(ed.cut()), K.Cut)
        self.a_copy = self._action("Копировать", lambda: self._to_clipboard(ed.copy_selection()), K.Copy)
        self.a_paste = self._action("Вставить", self._paste, K.Paste)
        self.a_dup = self._action("Дублировать", ed.duplicate, "Ctrl+D")
        self.a_delete = self._action("Удалить", ed.delete_selection, [K.Delete, "Backspace"])
        self.a_select_all = self._action("Выделить всё", self._select_all, K.SelectAll)
        self.a_group = self._action("Сгруппировать", ed.group_selection, "Ctrl+G")
        self.a_ungroup = self._action("Разгруппировать", ed.ungroup_selection, "Ctrl+Shift+G")
        self.a_lock = self._action("Заблокировать / разблокировать", lambda: ed.toggle("locked"), "Ctrl+Shift+L")
        self.a_hide = self._action("Скрыть / показать", lambda: ed.toggle("visible"), "Ctrl+Shift+H")
        self.a_up = self._action("Выше", lambda: ed.reorder("up"), "Ctrl+]")
        self.a_down = self._action("Ниже", lambda: ed.reorder("down"), "Ctrl+[")
        self.a_top = self._action("На передний план", lambda: ed.reorder("top"), "Ctrl+Shift+]")
        self.a_bottom = self._action("На задний план", lambda: ed.reorder("bottom"), "Ctrl+Shift+[")

        self.a_grid = self._action("Сетка", lambda v: self._set_view("grid_visible", "workspace/grid_visible", v),
                                   "Ctrl+'", checkable=True)
        self.a_snap = self._action("Прилипание", lambda v: self._set_view("snap_enabled", "workspace/snap", v),
                                   "Ctrl+Shift+;", checkable=True)
        self.a_guides = self._action("Направляющие", lambda v: self._set_view("guides_visible",
                                                                             "workspace/guides_visible", v),
                                     "Ctrl+;", checkable=True)
        self.a_grid.setChecked(ed.grid_visible)
        self.a_snap.setChecked(ed.snap_enabled)
        self.a_guides.setChecked(ed.guides_visible)
        self.a_zoom_in = self._action("Увеличить", lambda: self.canvas.zoom_step(1), [K.ZoomIn, "Ctrl+="])
        self.a_zoom_out = self._action("Уменьшить", lambda: self.canvas.zoom_step(-1), K.ZoomOut)
        self.a_zoom_fit = self._action("Показать экран целиком", self.canvas.fit, "Ctrl+0")
        self.a_zoom_100 = self._action("Масштаб 100%", lambda: self.canvas.set_zoom(1.0), "Ctrl+1")

        self.tool_group = QActionGroup(self)
        self.tool_actions = {}
        for key, glyph, text, sc in TOOLS:
            a = self._action(f"{text} ({sc})", lambda _=False, k=key: self._set_tool(k), sc, checkable=True)
            a.setIconText(glyph)
            a.setToolTip(f"{text} — {sc}")
            self.tool_group.addAction(a)
            self.tool_actions[key] = a
        self.tool_actions[TOOL_SELECT].setChecked(True)

        self.edit_actions = [self.a_undo, self.a_redo, None, self.a_cut, self.a_copy, self.a_paste, self.a_dup,
                             self.a_delete, None, self.a_select_all, None, self.a_group, self.a_ungroup, None,
                             self.a_up, self.a_down, self.a_top, self.a_bottom, None, self.a_lock, self.a_hide]
        self.view_actions = [self.a_zoom_in, self.a_zoom_out, self.a_zoom_fit, self.a_zoom_100, None,
                             self.a_grid, self.a_snap, self.a_guides]

        self.a_wrap_v = self._action("Выстроить в столбец ↓", lambda: ed.wrap_in_auto_layout("vertical"),
                                     "Shift+A")
        self.a_wrap_h = self._action("Выстроить в строку →", lambda: ed.wrap_in_auto_layout("horizontal"),
                                     "Ctrl+Shift+A")
        self.a_unwrap = self._action("Убрать контейнер / разгруппировать", ed.ungroup_selection)
        self.a_responsive = self._action("Проверка адаптивности…", self.show_responsive, "Ctrl+Alt+R")
        self.a_make_component = self._action("Создать компонент…", self.make_component, "Ctrl+Alt+K")
        self.a_detach = self._action("Отвязать копию от компонента", ed.detach_selection)
        self.a_reset_over = self._action("Сбросить переопределения", ed.reset_overrides_selection)
        self.a_replace = self._action("Заменить на компонент…", self.replace_dialog, "Ctrl+R")
        self.a_symbols = self._action("Значки Material…", self.symbols_dialog, "Ctrl+Shift+I")
        self.a_symbols.setToolTip("Около 3900 значков Google Material Symbols: поиск по-русски, три стиля, заливка")
        self.a_replace_symbol = self._action("Заменить значок…", self.replace_symbol_dialog)
        self.a_add_component = self._action("Добавить компонент…", self.add_dialog, "Ctrl+Shift+N")
        self.a_simple = self._action("Простой режим", self.set_simple, checkable=True)
        self.a_simple.setToolTip("Только основные кнопки и свойства. Выключите, чтобы видеть поведение при изменении размера, "
                                 "размеры в раскладке, направляющие и группы")
        self.a_run = self._action("▶ Просмотр", lambda: self.window().run_prototype()
                                  if hasattr(self.window(), "run_prototype") else None)
        self.a_run.setToolTip("Интерактивный предпросмотр на устройстве с текущего экрана (F5)")
        self.edit_actions[8:8] = [self.a_replace, self.a_add_component, self.a_symbols, self.a_replace_symbol]
        self.view_actions += [None, self.a_simple]
        self.tools_actions = [self.a_wrap_v, self.a_wrap_h, self.a_unwrap, None, self.a_make_component,
                              self.a_detach, self.a_reset_over, None, self.a_responsive]

    def _build_toolbar(self) -> QToolBar:
        bar = QToolBar("Инструменты", self)
        bar.setObjectName("WorkspaceToolbar")
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        bar.setStyleSheet("QToolBar{background:#000;border-bottom:1px solid #262626;padding:4px 8px;spacing:4px}"
                          "QToolBar QToolButton{padding:5px 9px}")
        design = QToolButton()
        design.setText("Дизайн")
        design.setCheckable(True)
        design.setChecked(True)
        design.setToolTip("Режим дизайна")
        bar.addWidget(design)
        bar.addAction(self.a_run)
        bar.addSeparator()
        for key, *_ in TOOLS:
            bar.addAction(self.tool_actions[key])
        bar.addSeparator()
        for action, short in ((self.a_undo, "↶"), (self.a_redo, "↷"), (self.a_group, "Группа"),
                              (self.a_ungroup, "Разгр."), (self.a_wrap_v, "В столбец"),
                              (self.a_responsive, "Адаптивность"), (self.a_grid, "Сетка"), (self.a_snap, "Прилипание"),
                              (self.a_guides, "Направл.")):
            action.setIconText(short)
            bar.addAction(action)
            if action in (self.a_redo, self.a_ungroup, self.a_responsive):
                bar.addSeparator()
        bar.addAction(self.a_simple)
        self.toolbar = bar
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        self.pos_label = QLabel("")
        self.pos_label.setObjectName("Muted")
        self.pos_label.setMinimumWidth(110)
        bar.addWidget(self.pos_label)
        self._build_zoom_box()
        return bar

    def _build_zoom_box(self) -> None:
        """Масштаб — плавающая панель в углу холста: видна при любой ширине окна (на панели инструментов
        кнопки уходили за край)."""
        box = QFrame(self.canvas)
        box.setObjectName("ZoomBox")
        box.setStyleSheet("#ZoomBox{background:rgba(20,20,20,220);border:1px solid #2A2A2A;border-radius:8px}"
                          "#ZoomBox QToolButton{padding:2px 6px}")
        lay = QHBoxLayout(box)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(2)
        for action, text in ((self.a_zoom_out, "−"), (None, ""), (self.a_zoom_in, "+"), (self.a_zoom_fit, "⤢")):
            if action is None:
                self.zoom_combo = QComboBox()
                self.zoom_combo.setEditable(True)
                self.zoom_combo.setFixedWidth(78)
                for z in ZOOMS:
                    self.zoom_combo.addItem(f"{z}%", z)
                self.zoom_combo.addItem("Целиком", 0)
                self.zoom_combo.activated.connect(self._zoom_chosen)
                self.zoom_combo.lineEdit().editingFinished.connect(self._zoom_typed)
                self.zoom_combo.setToolTip("Масштаб. Ctrl + колесо — увеличить под курсором; колесо — прокрутка, "
                                           "Shift + колесо — вбок; пробел или средняя кнопка — перемещение")
                lay.addWidget(self.zoom_combo)
                continue
            b = QToolButton()
            b.setDefaultAction(action)
            b.setText(text)
            b.setAutoRaise(True)
            lay.addWidget(b)
        box.adjustSize()
        self.zoom_box = box
        self.canvas.installEventFilter(self)
        self._place_zoom_box()

    # ---------- простые действия: панель выделения, меню правой кнопки, замена ----------
    def _build_selection_bar(self) -> None:
        """Над холстом, пока что-то выделено: имя и крупные кнопки «Заменить», «Дублировать», «Удалить»."""
        bar = QFrame(self.canvas)
        bar.setObjectName("SelBar")
        bar.setStyleSheet("#SelBar{background:#141414;border:1px solid #2F7BFF;border-radius:8px}"
                          "#SelBar QToolButton{padding:5px 10px}")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 4, 4, 4)
        lay.setSpacing(4)
        self.sel_label = QLabel("")
        self.sel_label.setMaximumWidth(220)
        lay.addWidget(self.sel_label)
        self.tap_button = QToolButton()
        self.tap_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.tap_button.setAutoRaise(True)
        self.tap_button.setToolTip("Что произойдёт, если нажать на этот элемент в приложении")
        self.tap_menu = QMenu(self.tap_button)
        self.tap_menu.aboutToShow.connect(self._fill_tap_menu)
        self.tap_button.setMenu(self.tap_menu)
        lay.addWidget(self.tap_button)
        self.sel_buttons = []
        for action, text, danger in ((self.a_replace_symbol, "Значок…", False),
                                     (self.a_replace, "Заменить…", False), (self.a_dup, "Дублировать", False),
                                     (self.a_delete, "Удалить", True)):
            b = QToolButton()  # своя короткая подпись: setDefaultAction подставил бы длинное имя команды
            b.setText(text)
            b.setToolTip(f"{action.text()} ({action.shortcut().toString()})")
            b.setAutoRaise(True)
            if danger:
                b.setStyleSheet("color:#FF6B6B")
            b.clicked.connect(action.trigger)
            action.changed.connect(lambda b=b, a=action: b.setEnabled(a.isEnabled()))
            lay.addWidget(b)
            self.sel_buttons.append(b)
        self.sel_bar = bar
        bar.hide()

    def _build_start_hint(self) -> None:
        hint = QLabel(self.canvas)
        hint.setObjectName("StartHint")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("#StartHint{background:#101826;border:1px solid #2F7BFF;border-radius:10px;"
                           "padding:12px 16px;color:#DDE6F5}")
        hint.setText("<b>С чего начать</b><br>1. Слева во вкладке «Добавить» щёлкните компонент — он появится на "
                     "экране, или перетащите его в нужное место.<br>2. Щёлкните элемент на экране — сверху появятся "
                     "кнопки «Заменить», «Дублировать», «Удалить»; справа — его цвет, текст и размер.<br>"
                     "3. Правая кнопка мыши — все действия. Ctrl + колесо — масштаб, F5 — проверить на телефоне.")
        hint.setFixedWidth(440)
        self.start_hint = hint
        hint.hide()

    def _sync_selection_bar(self) -> None:
        ed = self.editor
        nodes = ed.selected_nodes() if ed.doc else []
        bar = getattr(self, "sel_bar", None)
        if bar is not None:
            if nodes:
                name = nodes[0].name or TYPE_NAMES.get(nodes[0].type, "")
                text = name if len(nodes) == 1 else f"Выбрано: {len(nodes)}"
                self.sel_label.setText(self.sel_label.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight,
                                                                               200))
                self.sel_label.setToolTip(text)
                self.tap_button.setVisible(len(nodes) == 1)
                self.sel_buttons[0].setVisible(len(nodes) == 1 and nodes[0].type == "vector")
                if len(nodes) == 1:
                    self.tap_button.setText(self._tap_text(nodes[0].id))
                bar.adjustSize()
            bar.setVisible(bool(nodes))
        hint = getattr(self, "start_hint", None)
        if hint is not None:
            s = ed.screen()
            hint.adjustSize()
            hint.setVisible(bool(s is not None and not s.nodes))
        self._place_zoom_box()

    def _tap_text(self, node_id: str) -> str:
        ed = self.editor
        a = ed.tap_action(node_id)
        if a is None:
            return "При нажатии…"
        if a == "custom":
            return "При нажатии: своё правило"
        if a["type"] == "navigate":
            s = next((x for x in ed.doc.screens if x.id == a.get("screen_id")), None)
            name = s.name if s else "?"
            return "При нажатии → «" + (name if len(name) <= 18 else name[:17] + "…") + "»"
        if a["type"] == "back":
            return "При нажатии ← назад"
        if a["type"] == "set_visible":
            n = tree.node_map(ed.screen()).get(a.get("node_id"))
            return "При нажатии: показать / скрыть «" + ((n.name if n else "?")[:14]) + "»"
        return "При нажатии: своё правило"

    def _fill_tap_menu(self) -> None:
        ed = self.editor
        m = self.tap_menu
        for old in getattr(self, "_tap_submenus", []):  # прошлые подменю не копятся при каждом открытии
            old.deleteLater()
        self._tap_submenus = []
        m.clear()
        if len(ed.selection) != 1:
            return
        nid = ed.selection[0]
        cur = ed.tap_action(nid)
        if cur == "custom":
            m.addAction("Настроено правило в «Логике» — открыть…", self._open_logic)
            return
        none = m.addAction("Ничего не делать", lambda: ed.set_tap_action(nid, None))
        none.setCheckable(True)
        none.setChecked(cur is None)
        s = ed.screen()
        go = self._submenu(m, "Открыть экран")
        others = [x for x in ed.doc.screens if x.id != s.id and x.platform == s.platform]
        for x in others:
            a = go.addAction(x.name, lambda sid=x.id: ed.set_tap_action(nid, {"type": "navigate", "screen_id": sid}))
            a.setCheckable(True)
            a.setChecked(isinstance(cur, dict) and cur.get("type") == "navigate" and cur.get("screen_id") == x.id)
        if not others:
            go.addAction("Других экранов нет — добавьте экран внизу").setEnabled(False)
        back = m.addAction("Вернуться назад", lambda: ed.set_tap_action(nid, {"type": "back"}))
        back.setCheckable(True)
        back.setChecked(isinstance(cur, dict) and cur.get("type") == "back")
        vis = self._submenu(m, "Показать или скрыть")
        targets = [n for n in s.nodes if n.id != nid]
        for n in targets:
            a = vis.addAction(n.name or TYPE_NAMES.get(n.type, ""),
                              lambda tid=n.id: ed.set_tap_action(nid, {"type": "set_visible", "node_id": tid}))
            a.setCheckable(True)
            a.setChecked(isinstance(cur, dict) and cur.get("type") == "set_visible" and cur.get("node_id") == n.id)
        if not targets:
            vis.addAction("На экране нет других элементов").setEnabled(False)
        m.addSeparator()
        m.addAction("Сложнее (условия, переменные, анимации) — в «Логике»…", self._open_logic)

    def _submenu(self, parent: QMenu, title: str) -> QMenu:
        """Подменю с явным родителем и ссылкой: подменю из addMenu(str) PySide может удалить раньше времени."""
        sub = QMenu(title, parent)
        parent.addMenu(sub)
        self._tap_submenus = getattr(self, "_tap_submenus", []) + [sub]
        return sub

    def _open_logic(self) -> None:
        w = self.window()
        if hasattr(w, "open_logic"):
            w.open_logic()

    def show_context_menu(self, global_pos) -> None:
        ed = self.editor
        m = QMenu(self)
        if ed.selection:
            for a in (self.a_replace, self.a_dup, self.a_copy, self.a_delete):
                m.addAction(a)
            if self.a_replace_symbol.isEnabled():
                m.addAction(self.a_replace_symbol)
            if len(ed.selection) == 1:
                self._fill_tap_menu()
                sub = self._submenu(m, self._tap_text(ed.selection[0]))
                for a in self.tap_menu.actions():
                    sub.addAction(a)
            m.addSeparator()
            for a in (self.a_top, self.a_bottom, self.a_hide, self.a_lock):
                m.addAction(a)
            m.addSeparator()
            m.addAction(self.a_make_component)
            if not self.simple:
                m.addAction(self.a_group)
                m.addAction(self.a_wrap_v)
        else:
            m.addAction(self.a_add_component)
            m.addAction(self.a_symbols)
            m.addAction(self.a_paste)
            m.addSeparator()
            m.addAction(self.a_zoom_fit)
        m.exec(global_pos)

    def _pick_component(self, title: str) -> str | None:
        from app.ui.workspace.gallery import PickComponentDialog
        dlg = PickComponentDialog(self.editor, title, self)
        return dlg.kind if dlg.exec() else None

    def replace_dialog(self) -> None:
        if len(self.editor.selection) != 1:
            return
        kind = self._pick_component("Заменить выделенный элемент на…")
        if kind:
            self.editor.replace_selection(kind)

    def symbols_dialog(self) -> None:
        from app.ui.workspace.symbol_picker import SymbolPicker
        dlg = SymbolPicker("Значки Material", self)
        if dlg.exec() and dlg.name:
            self.editor.insert_symbol(dlg.name, dlg.style_key, dlg.is_filled, dlg.size_dp)

    def replace_symbol_dialog(self) -> None:
        from app.ui.workspace.symbol_picker import SymbolPicker
        ed = self.editor
        nodes = ed.selected_nodes()
        if len(nodes) != 1 or nodes[0].type != "vector":
            return
        dlg = SymbolPicker("Заменить значок", self, replace=True)
        if dlg.exec() and dlg.name:
            ed.replace_symbol(nodes[0].id, dlg.name, dlg.style_key, dlg.is_filled)

    def add_dialog(self) -> None:
        kind = self._pick_component("Добавить компонент")
        if kind:
            self.editor.insert_component(kind)

    simple = True

    def set_simple(self, on: bool) -> None:
        """Простой режим: прячет редкие кнопки панели и сложные разделы свойств."""
        self.simple = bool(on)
        self.a_simple.setChecked(self.simple)
        bar = self.toolbar
        advanced = (self.a_group, self.a_ungroup, self.a_responsive, self.a_guides)  # в меню они остаются
        for a in advanced:
            if a in bar.actions():
                bar.removeAction(a)
        if not self.simple:
            for a in advanced:
                bar.insertAction(self.a_grid, a)
        self.inspector.set_simple(self.simple)
        self.dock_diag.setVisible(not self.simple)  # вкладка диагностики — по меню «Вид» в простом режиме
        self.ctx.settings.set("workspace/simple", self.simple)

    def _place_zoom_box(self) -> None:
        box = getattr(self, "zoom_box", None)
        if box is not None:
            m = 12
            vp = self.canvas.viewport().geometry()
            box.move(vp.right() - box.width() - m, vp.bottom() - box.height() - m)
            box.raise_()
        bar = getattr(self, "sel_bar", None)
        if bar is not None:
            vp = self.canvas.viewport().geometry()
            bar.move(vp.left() + max(8, (vp.width() - bar.width()) // 2), vp.top() + 10)
            bar.raise_()
        hint = getattr(self, "start_hint", None)
        if hint is not None:
            vp = self.canvas.viewport().geometry()
            hint.setFixedWidth(min(440, max(260, vp.width() - 40)))
            hint.adjustSize()
            hint.move(vp.left() + (vp.width() - hint.width()) // 2, vp.top() + 16)
            hint.raise_()

    def eventFilter(self, obj, event):
        if obj is self.canvas and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self._place_zoom_box()
        return super().eventFilter(obj, event)

    # ---------- состояние ----------
    def set_document(self, doc: ProjectDocument | None, dirty: bool = False) -> None:
        self._forced_dirty = dirty
        self.editor.set_document(doc)
        self.screens.rebuild()
        self._update_actions()

    def is_dirty(self) -> bool:
        st = self.editor.stack
        return self._forced_dirty or bool(st is not None and not st.is_clean())

    def mark_clean(self) -> None:
        self._forced_dirty = False
        if self.editor.stack is not None:
            self.editor.stack.set_clean()

    def _on_changed(self) -> None:
        self._update_actions()
        self.changed.emit()

    def _update_actions(self) -> None:
        ed = self.editor
        has_doc = ed.doc is not None
        sel = bool(ed.selection)
        st = ed.stack
        self.a_undo.setEnabled(bool(st is not None and st.can_undo()))
        self.a_redo.setEnabled(bool(st is not None and st.can_redo()))
        self.a_undo.setText(f"Отменить: {st.undo_label()}" if st is not None and st.can_undo() else "Отменить")
        self.a_redo.setText(f"Повторить: {st.redo_label()}" if st is not None and st.can_redo() else "Повторить")
        for a in (self.a_cut, self.a_copy, self.a_dup, self.a_delete, self.a_group, self.a_lock, self.a_hide,
                  self.a_up, self.a_down, self.a_top, self.a_bottom):
            a.setEnabled(sel)
        self.a_replace.setEnabled(len(ed.selection) == 1)
        one = ed.selected_nodes() if len(ed.selection) == 1 else []
        self.a_replace_symbol.setEnabled(bool(one) and one[0].type == "vector")
        self.a_symbols.setEnabled(ed.screen() is not None)
        self.a_add_component.setEnabled(ed.screen() is not None)
        self.a_ungroup.setEnabled(any(n.is_container for n in ed.selected_nodes()))
        self.a_unwrap.setEnabled(any(n.is_container for n in ed.selected_nodes()))
        self.a_wrap_v.setEnabled(sel)
        self.a_wrap_h.setEnabled(sel)
        self.a_responsive.setEnabled(has_doc)
        self.a_make_component.setEnabled(sel)
        has_inst = bool(ed.selected_instances()) if has_doc else False
        self.a_detach.setEnabled(has_inst)
        self.a_reset_over.setEnabled(has_inst)
        self.a_paste.setEnabled(has_doc)
        self.a_select_all.setEnabled(has_doc)

    def _sync_tools(self) -> None:
        a = self.tool_actions.get(self.editor.tool)
        if a and not a.isChecked():
            a.setChecked(True)

    def _set_tool(self, key: str) -> None:
        self.editor.tool = key
        self.editor.view_changed.emit()

    def _set_view(self, attr: str, setting: str, value: bool) -> None:
        setattr(self.editor, attr, value)
        self.ctx.settings.set(setting, value)
        self.editor.view_changed.emit()

    def _select_all(self) -> None:
        s = self.editor.screen()
        if s:
            from app.core.document import tree
            cont = s.nodes if not self.editor.entered_group else tree.find(s, self.editor.entered_group)[0].children
            eff = self.editor._effective(s)
            self.editor.select([n.id for n in cont if eff[n.id][0] and not eff[n.id][1]])

    def _to_clipboard(self, payload: str) -> None:
        mime = QMimeData()
        mime.setData(CLIPBOARD_MIME, payload.encode("utf-8"))
        QGuiApplication.clipboard().setMimeData(mime)

    def _paste(self) -> None:
        mime = QGuiApplication.clipboard().mimeData()
        payload = None
        if mime is not None and mime.hasFormat(CLIPBOARD_MIME):
            payload = bytes(mime.data(CLIPBOARD_MIME)).decode("utf-8", errors="replace")
        self.editor.paste(payload)

    def _zoom_chosen(self, idx: int) -> None:
        z = self.zoom_combo.itemData(idx)
        if z == 0:
            self.canvas.fit()
        elif z:
            self.canvas.set_zoom(z / 100)

    def _zoom_typed(self) -> None:
        t = self.zoom_combo.currentText().strip().rstrip("%").replace(",", ".")
        try:
            self.canvas.set_zoom(float(t) / 100)
        except ValueError:
            self.zoom_combo.setEditText(f"{round(self.canvas.zoom() * 100)}%")

    def make_component(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        nodes = self.editor.selected_nodes()
        if not nodes:
            return
        name, ok = QInputDialog.getText(self, "Создать компонент", "Имя компонента:",
                                        text=nodes[0].name if len(nodes) == 1 else "Компонент")
        if ok and name.strip():
            self.editor.create_component(name.strip())

    def show_responsive(self) -> None:
        if self.editor.screen() is not None:
            ResponsiveDialog(self.editor, self).exec()

    def focus_layers(self) -> None:
        self.dock_layers.show()
        self.dock_layers.raise_()
        self.layers.tree.setFocus()


__all__ = ["WorkspacePage", "label", "stage_badge", "glyph_icon"]
