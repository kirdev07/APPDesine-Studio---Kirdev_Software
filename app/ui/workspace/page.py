"""Fusion Workspace: панель инструментов, холст и стыкуемые панели."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QDockWidget, QLabel, QMainWindow, QSizePolicy, QToolBar, QToolButton, QWidget,
)

from app.context import AppContext
from app.core.document.model import ProjectDocument
from app.ui.widgets import glyph_icon, label, stage_badge
from app.ui.workspace.canvas import CanvasView
from app.ui.workspace.editor import (
    CLIPBOARD_MIME, TOOL_ELLIPSE, TOOL_HAND, TOOL_RECT, TOOL_SELECT, TOOL_TEXT, Editor,
)
from app.ui.workspace.panels import Inspector, LayersPanel, ScreensStrip

TOOLS = [(TOOL_SELECT, "➤", "Выделение", "V"), (TOOL_HAND, "✋", "Рука (или пробел)", "H"),
         (TOOL_RECT, "▭", "Прямоугольник", "R"), (TOOL_ELLIPSE, "◯", "Эллипс", "O"), (TOOL_TEXT, "T", "Текст", "T")]
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

        self.editor.document_changed.connect(self._on_changed)
        self.editor.selection_changed.connect(self._update_actions)
        self.editor.view_changed.connect(self._sync_tools)
        self.canvas.zoom_changed.connect(lambda z: self.zoom_combo.setEditText(f"{round(z * 100)}%"))
        self.canvas.cursor_moved.connect(lambda x, y: self.pos_label.setText(f"x {x:.0f}   y {y:.0f}"))
        self._update_actions()

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
        self.a_snap = self._action("Привязка", lambda v: self._set_view("snap_enabled", "workspace/snap", v),
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
        for text, stage in (("Просмотр", 6), ("Структура", 3)):
            b = QToolButton()
            b.setText(text)
            b.setEnabled(False)
            b.setToolTip(f"{'Интерактивный просмотр' if stage == 6 else 'Структура'}: будет доступно на этапе {stage}")
            bar.addWidget(b)
        bar.addSeparator()
        for key, *_ in TOOLS:
            bar.addAction(self.tool_actions[key])
        bar.addSeparator()
        for action, short in ((self.a_undo, "↶"), (self.a_redo, "↷"), (self.a_group, "Группа"),
                              (self.a_ungroup, "Разгруппировать"), (self.a_grid, "Сетка"), (self.a_snap, "Привязка"),
                              (self.a_guides, "Направляющие")):
            action.setIconText(short)
            bar.addAction(action)
            if action in (self.a_redo, self.a_ungroup):
                bar.addSeparator()
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        self.pos_label = QLabel("")
        self.pos_label.setObjectName("Muted")
        self.pos_label.setMinimumWidth(110)
        bar.addWidget(self.pos_label)
        self.a_zoom_out.setIconText("−")
        bar.addAction(self.a_zoom_out)
        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.setFixedWidth(96)
        for z in ZOOMS:
            self.zoom_combo.addItem(f"{z}%", z)
        self.zoom_combo.addItem("Целиком", 0)
        self.zoom_combo.activated.connect(self._zoom_chosen)
        self.zoom_combo.lineEdit().editingFinished.connect(self._zoom_typed)
        bar.addWidget(self.zoom_combo)
        self.a_zoom_in.setIconText("+")
        bar.addAction(self.a_zoom_in)
        return bar

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
        self.a_ungroup.setEnabled(any(n.is_group for n in ed.selected_nodes()))
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

    def focus_layers(self) -> None:
        self.dock_layers.show()
        self.dock_layers.raise_()
        self.layers.tree.setFocus()


__all__ = ["WorkspacePage", "label", "stage_badge", "glyph_icon"]
