"""Component Builder — утверждённая ревизия Fusion 2.0.

Слева — компактная библиотека с поиском; в центре — холст (сетка, направляющие, масштаб, прямое
редактирование) и режимы Дизайн / Интерактивный просмотр / Структура; справа — один инспектор с вкладками
Дизайн / Состояния / Анимация / Действия; снизу — сворачиваемый предпросмотр состояний.
Двойной клик по вложенному экземпляру изолирует его компонент. Мастер редактируется в отдельном документе
со своей историей и попадает в проект одной записью истории по кнопке «Сохранить компонент».
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QSplitter, QStackedWidget, QTableWidget,
    QTableWidgetItem, QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from app.core.document import tree
from app.core.document.model import (
    OVERRIDABLE, ROOT_REF, STATE_NAMES, ComponentDef, ModelError, Node, Screen, check_prop,
)
from app.engines.components import engine as ce
from app.engines.components.library import (
    EXTENSION, PersonalLibrary, make_bundle, read_bundle_file, write_bundle_file,
)
from app.ui.studio.common import ask_save, button, editor_toolbar, scratch_document
from app.ui.widgets import label, panel, pixmap_icon, stage_badge
from app.ui.workspace.canvas import CanvasView, render_thumbnail
from app.ui.workspace.editor import TOOL_ELLIPSE, TOOL_FRAME, TOOL_PEN, TOOL_RECT, TOOL_SELECT, TOOL_TEXT, Editor
from app.ui.workspace.panels import Inspector

ROLE = Qt.ItemDataRole.UserRole
MARGIN = 40
STATE_RU = {"default": "По умолчанию", "hover": "Наведение", "focus": "Фокус", "pressed": "Нажатие",
            "disabled": "Недоступно", "loading": "Загрузка", "empty": "Пусто", "error": "Ошибка"}
PROP_RU = {"visible": "Видимость", "fill": "Заливка", "stroke": "Обводка", "stroke_width": "Толщина обводки",
           "opacity": "Непрозрачность", "radius": "Скругление", "text": "Текст", "text_color": "Цвет текста",
           "font_family": "Шрифт", "font_size": "Размер шрифта", "font_weight": "Насыщенность",
           "align": "Выравнивание", "asset_id": "Ресурс", "path": "Путь"}
COMPONENT_FILTER = f"Компонент App Design Studio (*{EXTENSION})"


def parse_value(prop: str, text: str):
    t = text.strip()
    if prop == "visible":
        return t.lower() in ("1", "да", "true", "yes", "вкл")
    if prop in ("stroke_width", "opacity", "radius", "font_size", "font_weight"):
        return float(t.replace(",", "."))
    return t


class ComponentBuilderPage(QWidget):
    insert_requested = Signal()  # после вставки экземпляра показать рабочую область

    def __init__(self, ws, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.ws, self.main = ws, ws.editor
        self.library = PersonalLibrary(ws.ctx.paths.library)
        self.editor = Editor(self)
        self.editor.isolate_instances = True
        self.editor.grid_size = 4
        self.editor.open_component.connect(self.open_nested)
        self.current_id: str | None = None
        self.breadcrumb: list[str] = []
        self.states: dict = {}
        self._states_dirty = False

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_library())
        split.addWidget(self._build_center())
        split.addWidget(self._build_inspector())
        split.setSizes([260, 900, 360])
        split.setStretchFactor(1, 1)
        root.addWidget(split)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self.refresh_preview)
        self.editor.document_changed.connect(self._preview_timer.start)
        self.editor.document_changed.connect(self._update_title)
        self.main.document_changed.connect(self.refresh_library)
        self._show_empty()

    # ---------- левая колонка ----------
    def _build_library(self) -> QWidget:
        frame, lay = panel(margins=10)
        lay.addWidget(label("Компоненты", "H2"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск компонентов…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_library)
        lay.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemDoubleClicked.connect(self._open_from_tree)
        self.tree.itemClicked.connect(self._open_from_tree)
        lay.addWidget(self.tree, 1)
        grid = QHBoxLayout()
        grid.addWidget(button("+ Новый", self.new_component, "Новый пустой компонент"))
        grid.addWidget(button("Вставить", self.insert_on_screen, "Вставить экземпляр на текущий экран"))
        lay.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(button("Импорт…", self.import_file, "Импорт файла .adscomp"))
        row.addWidget(button("Удалить", self.delete_component, "Удалить неиспользуемый компонент проекта",
                             "Danger"))
        lay.addLayout(row)
        lay.addWidget(label("Личная библиотека — общая для всех проектов", "Muted", wrap=True))
        self.lib_list = QListWidget()
        self.lib_list.setFixedHeight(130)
        lay.addWidget(self.lib_list)
        row = QHBoxLayout()
        row.addWidget(button("В проект", self.install_from_library, "Скопировать компонент из библиотеки в проект"))
        row.addWidget(button("Убрать", self.remove_from_library, "Удалить из личной библиотеки", "Danger"))
        lay.addLayout(row)
        frame.setMinimumWidth(230)
        return frame

    def refresh_library(self) -> None:
        doc = self.main.doc
        needle = self.search.text().strip().casefold()
        self.tree.clear()
        cats: dict[str, QTreeWidgetItem] = {}
        for c in sorted(doc.components if doc else [], key=lambda c: (c.category.casefold(), c.name.casefold())):
            if needle and needle not in c.name.casefold() and needle not in c.category.casefold():
                continue
            cat = cats.get(c.category)
            if cat is None:
                cat = cats[c.category] = QTreeWidgetItem([c.category])
                cat.setFlags(cat.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                self.tree.addTopLevelItem(cat)
                cat.setExpanded(True)
            used = self.main.component_usage(c.id)
            it = QTreeWidgetItem([f"{c.name}   ·   {used}"])
            it.setToolTip(0, f"Экземпляров: {used}. Версия {c.version}. Состояний: {len(c.states)}")
            it.setData(0, ROLE, c.id)
            cat.addChild(it)
            if c.id == self.current_id:
                it.setSelected(True)
        self.lib_list.clear()
        for item in self.library.items():
            if needle and needle not in item["name"].casefold():
                continue
            li = QListWidgetItem(f"{item['name']}  ·  {item['category']}")
            li.setData(ROLE, item["id"])
            li.setToolTip(f"Сохранён {item['saved_at']}")
            self.lib_list.addItem(li)
        if self.current_id and doc and doc.component(self.current_id) is None:
            self._show_empty()

    # ---------- центр ----------
    def _build_center(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        top = QHBoxLayout()
        self.mode_buttons = []
        for i, text in enumerate(("Дизайн", "Интерактивный просмотр", "Структура")):
            b = QToolButton()
            b.setText(text)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, n=i: self.set_mode(n))
            self.mode_buttons.append(b)
            top.addWidget(b)
        top.addSpacing(12)
        self.crumbs = QLabel("")
        self.crumbs.setObjectName("Muted")
        top.addWidget(self.crumbs, 1)
        self.dirty_label = label("", "Muted")
        top.addWidget(self.dirty_label)
        top.addWidget(button("Сохранить компонент", self.save, "Записать мастер в проект и обновить экземпляры",
                             "Primary"))
        v.addLayout(top)
        canvas_box, cl = panel(margins=0)
        self.toolbar = editor_toolbar(self.editor, [
            (TOOL_SELECT, "➤", "Выделение (V)"), (TOOL_FRAME, "#", "Фрейм"), (TOOL_RECT, "▭", "Прямоугольник"),
            (TOOL_ELLIPSE, "◯", "Эллипс"), (TOOL_TEXT, "T", "Текст"), (TOOL_PEN, "✎", "Перо")],
            [button("Целиком", lambda: self.canvas.fit()), button("Auto Layout ↓",
                                                                 lambda: self.editor.wrap_in_auto_layout("vertical"))])
        cl.addWidget(self.toolbar)
        self.center_stack = QStackedWidget()
        self.canvas = CanvasView(self.editor)
        self.center_stack.addWidget(self.canvas)
        self.structure = QTreeWidget()
        self.structure.setHeaderLabels(["Элемент", "Тип", "ref (ключ переопределений)", "Переопределено"])
        self.structure.setColumnWidth(0, 260)
        self.center_stack.addWidget(self.structure)
        self.empty = label("Выберите компонент слева или создайте новый.\n"
                           "Компонент можно создать и из выделения на экране: «Создать компонент» (Ctrl+Alt+K).",
                           "Muted", wrap=True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.center_stack.addWidget(self.empty)
        self.live = QWidget()  # интерактивный просмотр: экземпляр компонента в проигрывателе
        self.live_lay = QVBoxLayout(self.live)
        self.live_lay.setContentsMargins(0, 0, 0, 0)
        self.live_lay.addWidget(label("Наведите курсор, нажмите и щёлкните — поведение компонента и переходы "
                                      "между состояниями как в прототипе. Изменения на холсте видны сразу.",
                                      "Muted", wrap=True))
        self.live_player = None
        self.center_stack.addWidget(self.live)
        cl.addWidget(self.center_stack, 1)
        v.addWidget(canvas_box, 1)

        prev_box, pl = panel(margins=8)
        head = QHBoxLayout()
        self.preview_toggle = QToolButton()
        self.preview_toggle.setText("▾ Предпросмотр на устройстве")
        self.preview_toggle.setCheckable(True)
        self.preview_toggle.setChecked(True)
        self.preview_toggle.toggled.connect(lambda on: (self.preview.setVisible(on), self.preview_toggle.setText(
            ("▾ " if on else "▸ ") + "Предпросмотр на устройстве")))
        head.addWidget(self.preview_toggle)
        self.preview_device = QComboBox()
        self.preview_device.addItem("Android телефон (тёмный фон)", ("android", "#000000"))
        self.preview_device.addItem("Android телефон (светлый фон)", ("android", "#FFFFFF"))
        self.preview_device.addItem("Окно Windows", ("windows", "#202020"))
        self.preview_device.currentIndexChanged.connect(self.refresh_preview)
        head.addWidget(self.preview_device)
        head.addStretch()
        pl.addLayout(head)
        self.preview = QListWidget()
        self.preview.setViewMode(QListWidget.ViewMode.IconMode)
        self.preview.setFlow(QListWidget.Flow.LeftToRight)
        self.preview.setWrapping(False)
        self.preview.setIconSize(QSize(180, 110))
        self.preview.setGridSize(QSize(196, 140))
        self.preview.setFixedHeight(150)
        self.preview.setMovement(QListWidget.Movement.Static)
        pl.addWidget(self.preview)
        v.addWidget(prev_box)
        self.set_mode(0)
        return w

    def set_mode(self, n: int) -> None:
        for i, b in enumerate(self.mode_buttons):
            b.setChecked(i == n)
        if self.current_id is None:
            self.center_stack.setCurrentWidget(self.empty)
            return
        if n != 1 and self.live_player is not None:
            self.live_player.stop_clock()
        if n == 2:
            self.refresh_structure()
            self.center_stack.setCurrentWidget(self.structure)
        elif n == 1:
            self.start_live()
            self.center_stack.setCurrentWidget(self.live)
        else:
            self.center_stack.setCurrentWidget(self.canvas)
        self.toolbar.setEnabled(n == 0)

    def start_live(self) -> None:
        """Проигрыватель с одним экземпляром редактируемого (ещё не сохранённого) компонента."""
        from types import SimpleNamespace

        from app.core.document.model import ComponentDef, ProjectDocument, Screen
        from app.engines.preview.devices import ViewSpec, custom_profile, screen_dpi
        from app.ui.studio.prototype import PrototypePlayer
        defn = self._current_def()
        if self.live_player is not None:
            self.live_player.stop_clock()
            self.live_player.setParent(None)
            self.live_player.deleteLater()
            self.live_player = None
        if defn is None:
            return
        doc = self.main.doc
        comps = [ComponentDef.from_dict(c.to_dict()) for c in doc.components if c.id != defn.id] + [defn]
        plat = defn.platform or (doc.meta.platforms[0] if doc.meta.platforms else "android")
        dev = next((s.device_id for s in doc.screens if s.platform == plat), "")
        w, h = int(max(defn.root.w + 160, 480)), int(max(defn.root.h + 160, 320))
        screen = Screen(name=f"Компонент «{defn.name}»", platform=plat, width=w, height=h, device_id=dev)
        screen.nodes.append(ce.make_instance(defn, (w - defn.root.w) / 2, (h - defn.root.h) / 2, self.main.engine))
        scratch = ProjectDocument(meta=doc.meta, screens=[screen], components=comps, assets=doc.assets,
                                  text_styles=doc.text_styles, colors=doc.colors)
        scratch.asset_data = doc.asset_data
        shim = SimpleNamespace(doc=scratch, engine=self.main.engine, screen_id=screen.id,
                               artboard_color=self.main.artboard_color)
        self.live_player = PrototypePlayer(shim)
        self.live_player.device_chrome = False
        self.live_player.specs[plat] = ViewSpec(custom_profile(plat, w, h, screen_dpi(screen)),
                                                "landscape" if w > h else "portrait")  # размер ровно как у сцены
        self.live_player.render(fit=True)
        self.live_lay.addWidget(self.live_player, 1)
        if self.isVisible():
            self.live_player.start_clock()

    # ---------- инспектор ----------
    def _build_inspector(self) -> QWidget:
        self.tabs = QTabWidget()
        design = QWidget()
        dl = QVBoxLayout(design)
        dl.setContentsMargins(6, 6, 6, 6)
        form = QFormLayout()
        self.f_name = QLineEdit()
        self.f_category = QLineEdit()
        self.f_desc = QPlainTextEdit()
        self.f_desc.setFixedHeight(60)
        for wdg in (self.f_name, self.f_category):
            wdg.textEdited.connect(self._mark_meta_dirty)
        self.f_desc.textChanged.connect(self._mark_meta_dirty)
        form.addRow("Имя", self.f_name)
        form.addRow("Категория", self.f_category)
        form.addRow("Описание", self.f_desc)
        dl.addLayout(form)
        self.inspector = Inspector(self.editor, show_document=False)
        dl.addWidget(self.inspector, 1)
        row = QHBoxLayout()
        row.addWidget(button("В личную библиотеку", self.save_to_library,
                             "Сохранить компонент (с ресурсами и стилями) для других проектов"))
        row.addWidget(button("Экспорт…", self.export_file, "Сохранить файл .adscomp"))
        dl.addLayout(row)
        ai = button("Экспорт с ИИ-заданием…", self.export_with_task,
                    "Пакет для Claude Code с экранами, где используется компонент")
        dl.addWidget(ai)
        self.tabs.addTab(design, "Дизайн")
        self.tabs.addTab(self._build_states(), "Состояния")
        self.tabs.addTab(self._build_anim_tab(), "Анимация")
        self.tabs.addTab(self._build_actions_tab(), "Действия")
        self.tabs.setMinimumWidth(340)
        return self.tabs

    def _build_anim_tab(self) -> QWidget:
        from PySide6.QtWidgets import QSpinBox
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 6, 6)
        v.addWidget(label("Переход между состояниями", "H2"))
        v.addWidget(label("Как экземпляр в прототипе меняет внешний вид при смене состояния: числовые свойства "
                          "и цвета плавно переходят от старых значений к новым.", "Muted", wrap=True))
        form = QFormLayout()
        self.tr_duration = QSpinBox()
        self.tr_duration.setRange(0, 5000)
        self.tr_duration.setSuffix(" мс")
        self.tr_duration.setValue(150)
        self.tr_easing = QComboBox()
        for key, text in (("linear", "Линейная"), ("ease_in", "Разгон"), ("ease_out", "Торможение"),
                          ("ease_in_out", "Разгон и торможение"), ("step", "Скачок")):
            self.tr_easing.addItem(text, key)
        self.tr_easing.setCurrentIndex(3)
        self.tr_duration.valueChanged.connect(self._mark_meta_dirty)
        self.tr_easing.currentIndexChanged.connect(self._mark_meta_dirty)
        form.addRow("Длительность", self.tr_duration)
        form.addRow("Плавность", self.tr_easing)
        v.addLayout(form)
        v.addWidget(label("0 мс — смена без анимации. Анимации экранов (ключевые кадры) — раздел «Анимации».",
                          "Muted", wrap=True))
        v.addStretch()
        return w

    def _build_actions_tab(self) -> QWidget:
        from PySide6.QtWidgets import QCheckBox
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 6, 6)
        v.addWidget(label("Встроенное поведение в прототипе", "H2"))
        v.addWidget(label("Работает у каждого экземпляра без отдельной настройки логики. Если взаимодействие "
                          "в «Логике» само задаёт состояние этого экземпляра, встроенное поведение не срабатывает.",
                          "Muted", wrap=True))
        self.bh_hover = QCheckBox("Наведение мышью → состояние «hover»")
        self.bh_press = QCheckBox("Пока нажато → состояние «pressed»")
        self.bh_toggle = QCheckBox("Нажатие переключает между двумя состояниями")
        for cb in (self.bh_hover, self.bh_press, self.bh_toggle):
            cb.toggled.connect(self._mark_meta_dirty)
            v.addWidget(cb)
        row = QHBoxLayout()
        self.bh_a, self.bh_b = QComboBox(), QComboBox()
        for c in (self.bh_a, self.bh_b):
            c.setEditable(False)
            c.currentIndexChanged.connect(self._mark_meta_dirty)
            row.addWidget(c)
        v.addLayout(row)
        self.bh_note = label("", "Muted", wrap=True)
        v.addWidget(self.bh_note)
        v.addStretch()
        return w

    def _fill_behavior(self, defn) -> None:
        widgets = (self.tr_duration, self.tr_easing, self.bh_hover, self.bh_press, self.bh_toggle, self.bh_a,
                   self.bh_b)
        for wdg in widgets:
            wdg.blockSignals(True)
        self.tr_duration.setValue(defn.transition.get("duration", 150))
        self.tr_easing.setCurrentIndex(max(0, self.tr_easing.findData(defn.transition.get("easing", "ease_in_out"))))
        b = defn.behavior
        self.bh_hover.setChecked(b.get("hover", False))
        self.bh_press.setChecked(b.get("press", False))
        self.bh_toggle.setChecked(len(b.get("toggle", [])) == 2)
        self._fill_state_combos(b.get("toggle", []))
        for wdg in widgets:
            wdg.blockSignals(False)

    def _fill_state_combos(self, toggle: list) -> None:
        names = ["default"] + list(self.states)
        for c, cur in ((self.bh_a, toggle[0] if toggle else "default"),
                       (self.bh_b, toggle[1] if len(toggle) == 2 else (names[1] if len(names) > 1 else "default"))):
            c.blockSignals(True)
            c.clear()
            for n in names:
                c.addItem(STATE_RU.get(n, n), n)
            c.setCurrentIndex(max(0, c.findData(cur)))
            c.blockSignals(False)
        missing = [s for s, cb in (("hover", self.bh_hover), ("pressed", self.bh_press)) if cb.isChecked()
                   and s not in self.states]
        self.bh_note.setText(("Нет состояний: " + ", ".join(missing) + " — добавьте их на вкладке «Состояния».")
                             if missing else "")

    def _behavior(self) -> tuple[dict, dict]:
        toggle = []
        if self.bh_toggle.isChecked() and self.bh_a.currentData() != self.bh_b.currentData():
            toggle = [self.bh_a.currentData(), self.bh_b.currentData()]
        return ({"duration": self.tr_duration.value(), "easing": self.tr_easing.currentData()},
                {"hover": self.bh_hover.isChecked(), "press": self.bh_press.isChecked(), "toggle": toggle})

    def _build_states(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 6, 6)
        v.addWidget(label("Состояние задаётся переопределениями поверх мастера. Экземпляры переключают "
                          "состояние в инспекторе рабочей области.", "Muted", wrap=True))
        self.state_list = QListWidget()
        self.state_list.setFixedHeight(150)
        self.state_list.currentItemChanged.connect(self.refresh_overrides)
        v.addWidget(self.state_list)
        row = QHBoxLayout()
        row.addWidget(button("+ Состояние", self.add_state))
        row.addWidget(button("Типовые", self.preset_states, "Наведение, нажатие, фокус, недоступно, загрузка, ошибка"))
        row.addWidget(button("Удалить", self.remove_state, object_name="Danger"))
        v.addLayout(row)
        v.addWidget(label("Переопределения выбранного состояния", "H2"))
        self.over_table = QTableWidget(0, 3)
        self.over_table.setHorizontalHeaderLabels(["Элемент", "Свойство", "Значение"])
        self.over_table.horizontalHeader().setStretchLastSection(True)
        self.over_table.verticalHeader().setVisible(False)
        self.over_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        v.addWidget(self.over_table, 1)
        form = QFormLayout()
        self.o_node = QComboBox()
        self.o_prop = QComboBox()
        for p in OVERRIDABLE:
            self.o_prop.addItem(PROP_RU.get(p, p), p)
        self.o_value = QLineEdit()
        self.o_value.setPlaceholderText("например #FF0000, 0.5, Загрузка…")
        form.addRow("Элемент", self.o_node)
        form.addRow("Свойство", self.o_prop)
        form.addRow("Значение", self.o_value)
        v.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(button("Добавить / заменить", self.add_override))
        row.addWidget(button("Удалить строку", self.remove_override, object_name="Danger"))
        v.addLayout(row)
        self.states_error = label("", "Error", wrap=True)
        v.addWidget(self.states_error)
        return w

    # ---------- открытие / сохранение ----------
    def is_dirty(self) -> bool:
        st = self.editor.stack
        return self.current_id is not None and (self._states_dirty or (st is not None and not st.is_clean()))

    def _mark_meta_dirty(self, *_):
        if self.current_id:
            self._states_dirty = True
            self._update_title()

    def confirm_leave(self) -> bool:
        if not self.is_dirty():
            return True
        choice = ask_save(self, f"компонент «{self.f_name.text()}»")
        if choice == "save":
            return self.save()
        return choice == "discard"

    def _show_empty(self) -> None:
        self.current_id = None
        self.breadcrumb = []
        self.editor.set_document(None)
        self.crumbs.setText("")
        self.preview.clear()
        self.state_list.clear()
        self.center_stack.setCurrentWidget(self.empty)
        self.tabs.setEnabled(False)
        self._update_title()

    def open_component(self, component_id: str, nested: bool = False) -> bool:
        doc = self.main.doc
        defn = doc.component(component_id) if doc else None
        if defn is None:
            return False
        if component_id != self.current_id and not self.confirm_leave():
            return False
        defn = ComponentDef.from_dict(defn.to_dict())
        root = defn.root
        dx, dy = MARGIN - root.x, MARGIN - root.y
        for n in tree.descendants(root):
            n.x, n.y = n.x + dx, n.y + dy
        screen = Screen(name=defn.name, platform=defn.platform or doc.meta.platforms[0],
                        width=math.ceil(root.w + 2 * MARGIN), height=math.ceil(root.h + 2 * MARGIN), nodes=[root])
        self.editor.set_document(scratch_document(doc, screen))
        self.current_id = component_id
        if nested:
            self.breadcrumb.append(component_id)
        else:
            self.breadcrumb = [component_id]
        self.states = json.loads(json.dumps(defn.states))
        self._states_dirty = False
        self.f_name.setText(defn.name)
        self.f_category.setText(defn.category)
        self.f_desc.blockSignals(True)
        self.f_desc.setPlainText(defn.description)
        self.f_desc.blockSignals(False)
        self._fill_behavior(defn)
        self.tabs.setEnabled(True)
        names = [doc.component(c).name if doc.component(c) else "?" for c in self.breadcrumb]
        self.crumbs.setText("  ›  ".join(names) + ("   (двойной клик по вложенному компоненту — изолировать)"
                                                    if len(names) == 1 else "   ← назад: щелчок по компоненту слева"))
        self.refresh_states()
        self.refresh_library()
        self.set_mode(0)
        self.canvas.fit()
        self.refresh_preview()
        self._update_title()
        return True

    def open_nested(self, component_id: str) -> None:
        self.open_component(component_id, nested=True)

    def hideEvent(self, e):
        if self.live_player is not None:
            self.live_player.stop_clock()
        super().hideEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        if self.live_player is not None and self.center_stack.currentWidget() is self.live:
            self.live_player.start_clock()

    def export_with_task(self) -> None:
        if self.current_id is None or not self.confirm_leave():
            return
        cid = self.current_id
        used = [s.id for s in self.main.doc.screens
                if any(n.is_instance and n.component_id == cid for n, _, _ in tree.walk(s.nodes))]
        if not used:
            QMessageBox.information(self, "Экспорт", "Компонент ещё не используется на экранах. Вставьте его на "
                                                     "экран («Вставить на экран») и повторите.")
            return
        win = self.window()
        if hasattr(win, "export_screens"):
            win.export_screens(used)

    def _current_def(self) -> ComponentDef | None:
        """Компонент по текущему состоянию редактора (ещё не сохранённый в проект)."""
        s = self.editor.screen()
        if self.current_id is None or s is None:
            return None
        if len(s.nodes) != 1 or not s.nodes[0].is_frame or s.nodes[0].is_instance:
            return None
        old = self.main.doc.component(self.current_id)
        root = Node.from_dict(s.nodes[0].to_dict())
        transition, behavior = self._behavior()
        return ComponentDef(transition=transition, behavior=behavior, name=self.f_name.text().strip() or (old.name if old else "Компонент"), root=root,
                            category=self.f_category.text().strip() or "Мои компоненты",
                            platform=old.platform if old else "", description=self.f_desc.toPlainText(),
                            states=json.loads(json.dumps(self.states)), version=old.version if old else 1,
                            id=self.current_id)

    def save(self) -> bool:
        defn = self._current_def()
        if defn is None:
            QMessageBox.warning(self, "Компонент", "На холсте компонента должен быть ровно один корневой фрейм. "
                                                   "Сгруппируйте элементы во фрейм (Auto Layout) и повторите.")
            return False
        if not self.main.update_component(defn):
            return False
        self.editor.stack.set_clean()
        self._states_dirty = False
        self.refresh_library()
        self._update_title()
        return True

    def _update_title(self) -> None:
        self.dirty_label.setText("● есть несохранённые изменения" if self.is_dirty() else "")

    # ---------- состояния ----------
    def refresh_states(self) -> None:
        self.state_list.blockSignals(True)
        self.state_list.clear()
        it = QListWidgetItem("По умолчанию (мастер)")
        it.setData(ROLE, "default")
        self.state_list.addItem(it)
        for name in self.states:
            n = sum(len(p) for p in self.states[name].values())
            it = QListWidgetItem(f"{STATE_RU.get(name, name)}   ·   {n}")
            it.setData(ROLE, name)
            self.state_list.addItem(it)
        self.state_list.blockSignals(False)
        self.state_list.setCurrentRow(0)
        self.o_node.clear()
        self.o_node.addItem("Корень компонента", ROOT_REF)
        s = self.editor.screen()
        if s and s.nodes:
            for n, _, depth in tree.walk(s.nodes[0].children):
                self.o_node.addItem("  " * depth + (n.name or n.type), n.id)
        self.refresh_overrides()

    def _state(self) -> str:
        it = self.state_list.currentItem()
        return it.data(ROLE) if it else "default"

    def refresh_overrides(self, *_):
        state = self._state()
        rows = []
        names = {self.o_node.itemData(i): self.o_node.itemText(i).strip() for i in range(self.o_node.count())}
        for ref, props in self.states.get(state, {}).items():
            for k, v in props.items():
                rows.append((ref, k, v))
        self.over_table.setRowCount(len(rows))
        for r, (ref, k, v) in enumerate(rows):
            a = QTableWidgetItem(names.get(ref, ref))
            a.setData(ROLE, (ref, k))
            self.over_table.setItem(r, 0, a)
            self.over_table.setItem(r, 1, QTableWidgetItem(PROP_RU.get(k, k)))
            self.over_table.setItem(r, 2, QTableWidgetItem(str(v)))
        self.states_error.clear()

    def add_state(self) -> None:
        free = [STATE_RU[s] for s in STATE_NAMES if s != "default" and s not in self.states]
        name, ok = QInputDialog.getItem(self, "Новое состояние", "Состояние (можно ввести своё):", free, 0, True)
        if not ok or not name.strip():
            return
        key = next((k for k, v in STATE_RU.items() if v == name), name.strip())
        try:
            check_prop("state", key, "instance")
        except ModelError as exc:
            self.states_error.setText(str(exc))
            return
        self.states.setdefault(key, {})
        self._changed_states()

    def preset_states(self) -> None:
        defn = self._current_def()
        if defn is None:
            return
        ce.preset_states(defn, self.main.doc.meta.appearance.accent)
        self.states = json.loads(json.dumps(defn.states))
        self._changed_states()

    def remove_state(self) -> None:
        st = self._state()
        if st != "default" and QMessageBox.question(self, "Состояние", f"Удалить состояние «{STATE_RU.get(st, st)}»?") \
                == QMessageBox.StandardButton.Yes:
            self.states.pop(st, None)
            self._changed_states()

    def add_override(self) -> None:
        st = self._state()
        if st == "default":
            self.states_error.setText("Выберите состояние (мастер редактируется на холсте)")
            return
        ref, prop = self.o_node.currentData(), self.o_prop.currentData()
        try:
            node_type = "vector" if prop == "path" else "image" if prop == "asset_id" else "text"
            value = check_prop(prop, parse_value(prop, self.o_value.text()), node_type)
        except (ModelError, ValueError) as exc:
            self.states_error.setText(f"Неверное значение: {exc}")
            return
        self.states.setdefault(st, {}).setdefault(ref, {})[prop] = value
        self._changed_states(keep=st)

    def remove_override(self) -> None:
        row = self.over_table.currentRow()
        if row < 0:
            return
        ref, prop = self.over_table.item(row, 0).data(ROLE)
        st = self._state()
        props = self.states.get(st, {}).get(ref, {})
        props.pop(prop, None)
        if not props:
            self.states.get(st, {}).pop(ref, None)
        self._changed_states(keep=st)

    def _changed_states(self, keep: str | None = None) -> None:
        self._states_dirty = True
        self.refresh_states()
        self._fill_state_combos(self._behavior()[1]["toggle"])
        if keep:
            for i in range(self.state_list.count()):
                if self.state_list.item(i).data(ROLE) == keep:
                    self.state_list.setCurrentRow(i)
        self.refresh_preview()
        self._update_title()

    # ---------- предпросмотр и структура ----------
    def refresh_preview(self) -> None:
        self.preview.clear()
        defn = self._current_def()
        if defn is None:
            return
        platform, bg = self.preview_device.currentData()
        tmp_doc = scratch_document(self.main.doc, Screen(name="p", platform=platform, width=10, height=10))
        tmp_doc.components = [c for c in tmp_doc.components if c.id != defn.id] + [defn]
        for st in ["default"] + list(self.states):
            inst = ce.make_instance(defn, 24, 24, self.editor.engine)
            inst.state = st
            ce.materialize(defn, inst, self.editor.engine)
            scr = Screen(name=st, platform=platform, width=max(1, math.ceil(inst.w + 48)),
                         height=max(1, math.ceil(inst.h + 48)), nodes=[inst])
            pm = render_thumbnail(scr, bg, 180, 110, tmp_doc, bg="#0B0B0B")
            it = QListWidgetItem(pixmap_icon(pm), STATE_RU.get(st, st))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.preview.addItem(it)

    def refresh_structure(self) -> None:
        self.structure.clear()
        s = self.editor.screen()
        if not s:
            return
        counts: dict[str, int] = {}
        for props in self.states.values():
            for ref in props:
                counts[ref] = counts.get(ref, 0) + 1

        def add(nodes, parent):
            for n in nodes:
                it = QTreeWidgetItem([n.name or n.type, n.type, n.id if parent else ROOT_REF,
                                      f"{counts.get(n.id if parent else ROOT_REF, 0)} сост." if
                                      counts.get(n.id if parent else ROOT_REF) else ""])
                (parent.addChild(it) if parent else self.structure.addTopLevelItem(it))
                if n.is_container and not n.is_instance:
                    add(n.children, it)
                it.setExpanded(True)
        add(s.nodes, None)

    # ---------- действия библиотеки ----------
    def reset_for_document(self) -> None:
        self._states_dirty = False
        self._show_empty()
        self.refresh_library()

    def _open_from_tree(self, item: QTreeWidgetItem, _col=0) -> None:
        cid = item.data(0, ROLE)
        if cid:
            self.open_component(cid)

    def new_component(self) -> None:
        name, ok = QInputDialog.getText(self, "Новый компонент", "Имя компонента:", text="Компонент")
        if not ok or not name.strip():
            return
        if not self.confirm_leave():
            return
        doc = self.main.doc
        label_ = Node(type="text", name="Подпись", text=name.strip(), fill="", sizing_h="hug", sizing_v="hug",
                      font_family=doc.meta.appearance.font_family, font_size=16, text_color="#F2F2F2")
        root = Node(type="frame", name=name.strip(), x=0, y=0, w=160, h=48, layout="horizontal", pad_l=16,
                    pad_r=16, pad_t=12, pad_b=12, gap=8, cross_align="center", main_align="center",
                    sizing_h="hug", sizing_v="hug", fill="#1C1C1C", radius=12, children=[label_])
        defn = ComponentDef(name=name.strip(), root=root, platform=self.main.screen().platform
                            if self.main.screen() else doc.meta.platforms[0])
        self._states_dirty = False
        if self.editor.stack is not None:
            self.editor.stack.set_clean()
        if self.main.update_component(defn):
            self.open_component(defn.id)

    def insert_on_screen(self) -> None:
        cid = self.current_id or (self.tree.currentItem().data(0, ROLE) if self.tree.currentItem() else None)
        if not cid:
            return
        if self.is_dirty() and not self.confirm_leave():
            return
        if self.main.insert_instance(cid):
            self.insert_requested.emit()

    def delete_component(self) -> None:
        item = self.tree.currentItem()
        cid = item.data(0, ROLE) if item else None
        if not cid:
            return
        name = self.main.doc.component(cid).name
        if QMessageBox.question(self, "Удаление компонента", f"Удалить компонент «{name}» из проекта? "
                                "Действие можно отменить (Ctrl+Z на рабочей области).") != QMessageBox.StandardButton.Yes:
            return
        if self.main.delete_component(cid) and cid == self.current_id:
            self._show_empty()

    def save_to_library(self) -> None:
        if self.current_id is None:
            return
        if self.is_dirty() and not self.save():
            return
        warnings = self.library.save(self.main.doc, self.current_id)
        self.refresh_library()
        QMessageBox.information(self, "Личная библиотека", "Компонент сохранён в личную библиотеку." +
                                ("\n\nЗамечания:\n• " + "\n• ".join(warnings) if warnings else ""))

    def export_file(self) -> None:
        if self.current_id is None:
            return
        if self.is_dirty() and not self.save():
            return
        name = self.main.doc.component(self.current_id).name
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт компонента", str(Path.home() / f"{name}{EXTENSION}"),
                                              COMPONENT_FILTER)
        if not path:
            return
        bundle, files, warnings = make_bundle(self.main.doc, self.current_id)
        write_bundle_file(Path(path), bundle, files)
        if warnings:
            QMessageBox.information(self, "Экспорт компонента", "Готово. Замечания:\n• " + "\n• ".join(warnings))

    def _install(self, bundle, files) -> None:
        warnings = self.main.install_bundle(bundle, files)
        self.refresh_library()
        self.open_component(bundle["main"])
        if warnings:
            QMessageBox.information(self, "Компонент добавлен", "Замечания:\n• " + "\n• ".join(warnings))

    def import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Импорт компонента", str(Path.home()), COMPONENT_FILTER)
        if not path:
            return
        try:
            bundle, files = read_bundle_file(Path(path))
        except ModelError as exc:
            QMessageBox.warning(self, "Импорт компонента", str(exc))
            return
        self._install(bundle, files)

    def install_from_library(self) -> None:
        it = self.lib_list.currentItem()
        if not it:
            return
        try:
            bundle, files = self.library.load(it.data(ROLE))
        except ModelError as exc:
            QMessageBox.warning(self, "Личная библиотека", str(exc))
            return
        self._install(bundle, files)

    def remove_from_library(self) -> None:
        it = self.lib_list.currentItem()
        if it and QMessageBox.question(self, "Личная библиотека", f"Удалить «{it.text()}» из личной библиотеки? "
                                       "Проекты, куда компонент уже вставлен, не изменятся.") \
                == QMessageBox.StandardButton.Yes:
            self.library.remove(it.data(ROLE))
            self.refresh_library()
