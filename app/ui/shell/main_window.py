"""Главное окно: меню, навигационная панель, страницы, автосохранение."""

from __future__ import annotations

import os

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from app import APP_NAME, APP_VERSION, COPYRIGHT, WINDOW_TITLE
from app.context import AppContext
from app.core.document.model import ProjectDocument
from app.core.persistence.container import ProjectFormatError
from app.core.project.service import ProjectError
from app.ui.dialogs.new_project_wizard import NewProjectWizard
from app.ui.panels.project_hub import ProjectHubPage
from app.ui.panels.settings_page import SettingsPage
from app.ui.widgets import glyph_icon
from app.ui.workspace.page import WorkspacePage

log = logging.getLogger(__name__)

# (подпись, иконка, этап) — разделы, которые ещё не реализованы, неактивны и подписаны этапом.
NAV_FUTURE: list[tuple[str, str, int]] = []
MENU_FUTURE = {
    "Инструменты": [],
    "Экспорт": [],
    "Устройства": [],
}

(PAGE_HUB, PAGE_PROJECT, PAGE_SETTINGS, PAGE_BUILDER, PAGE_ICONS, PAGE_FONTS, PAGE_COLORS, PAGE_RESOURCES,
 PAGE_ANIMATIONS, PAGE_LOGIC, PAGE_PREVIEW, PAGE_VALIDATE, PAGE_EXPORT) = range(13)
# студии, которым нужен открытый проект: (страница, подпись, иконка, сочетание клавиш)
STUDIOS = [(PAGE_BUILDER, "Компоненты", "components", "Ctrl+Alt+1"), (PAGE_ICONS, "Иконки", "icons", "Ctrl+Alt+2"),
           (PAGE_FONTS, "Шрифты", "fonts", "Ctrl+Alt+3"), (PAGE_COLORS, "Цвета", "colors", "Ctrl+Alt+4"),
           (PAGE_RESOURCES, "Ресурсы", "resources", "Ctrl+Alt+5"),
           (PAGE_ANIMATIONS, "Анимации", "animations", "Ctrl+Alt+6"), (PAGE_LOGIC, "Логика", "logic", "Ctrl+Alt+7"),
           (PAGE_PREVIEW, "Просмотр", "devices", "Ctrl+Alt+8"), (PAGE_VALIDATE, "Проверка", "validate", "Ctrl+Alt+9"),
           (PAGE_EXPORT, "Экспорт", "export", "Ctrl+Alt+0")]
STUDIO_TITLES = {PAGE_BUILDER: "Конструктор компонентов", PAGE_ICONS: "SVG-редактор и иконки",
                 PAGE_FONTS: "Шрифты и стили текста", PAGE_COLORS: "Цвета", PAGE_RESOURCES: "Ресурсы",
                 PAGE_ANIMATIONS: "Анимации", PAGE_LOGIC: "Визуальная логика",
                 PAGE_PREVIEW: "Интерактивный предпросмотр", PAGE_VALIDATE: "Проверка проекта",
                 PAGE_EXPORT: "AI-экспорт для Claude Code"}


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.doc: ProjectDocument | None = None
        self.doc_path: Path | None = None
        self.dirty = False
        self.setWindowTitle(WINDOW_TITLE)
        from app.ui.shell.updates import Updates
        self.updates = Updates(self)
        self.resize(1480, 920)
        self.setMinimumSize(1100, 700)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_nav())
        self.pages = QStackedWidget()
        self.hub = ProjectHubPage(ctx)
        self.project_page = WorkspacePage(ctx)
        self.settings_page = SettingsPage(ctx)
        from app.ui.studio.builder import ComponentBuilderPage
        from app.ui.studio.icons import IconsPage
        from app.ui.studio.resources import ColorsPage, ResourcesPage
        from app.ui.studio.typography import TypographyPage
        self.builder = ComponentBuilderPage(self.project_page)
        self.icons = IconsPage(self.project_page)
        self.fonts_page = TypographyPage(self.project_page)
        self.colors = ColorsPage(self.project_page)
        self.resources = ResourcesPage(self.project_page)
        from app.ui.studio.animation import AnimationPage
        from app.ui.studio.logic import LogicPage
        self.animations = AnimationPage(self.project_page)
        self.logic = LogicPage(self.project_page)
        self.logic.run_requested.connect(self.run_prototype)
        from app.ui.studio.preview import PreviewPage
        self.preview = PreviewPage(self.project_page)
        from app.ui.studio.export import ExportPage, ValidatorPage
        self.validator = ValidatorPage(self.project_page)
        self.validator.goto.connect(self.go_to_node)
        self.export_page = ExportPage(self.project_page)
        for p in (self.hub, self.project_page, self.settings_page, self.builder, self.icons, self.fonts_page,
                  self.colors, self.resources, self.animations, self.logic, self.preview, self.validator,
                  self.export_page):
            self.pages.addWidget(p)
        for page in (self.builder, self.icons, self.resources):
            page.insert_requested.connect(lambda: self.show_page(PAGE_PROJECT))
        ed = self.project_page.editor
        ed.message.connect(lambda text: self.statusBar().showMessage(text, 8000))
        ed.open_component.connect(self.open_in_builder)
        lay.addWidget(self.pages, 1)
        self.setCentralWidget(central)

        self.hub.open_requested.connect(self.open_project)
        self.hub.new_requested.connect(self.new_project)
        self.project_page.changed.connect(self._mark_dirty)
        self.settings_page.changed.connect(self._settings_changed)

        self._build_menu()
        from app.ui.shell import shortcuts
        shortcuts.apply(self, shortcuts.load(ctx.settings))  # свои горячие клавиши поверх стандартных
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.autosave)
        self._settings_changed()
        self.statusBar().showMessage("Fusion AMOLED · без облака и аналитики")
        self._update_state()
        self.show_page(PAGE_HUB)

    # ---------- построение ----------
    def _nav_button(self, text: str, icon: str) -> QToolButton:
        b = QToolButton()
        b.setObjectName("NavButton")
        b.setText(text)
        b.setAccessibleName(text)  # имя для экранного диктора
        b.setIcon(glyph_icon(icon, 20, fallback=text))
        b.setIconSize(QSize(20, 20))
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        b.setFixedSize(94, 50)
        return b

    def _build_nav(self) -> QWidget:
        nav = QFrame()
        nav.setFixedWidth(108)
        nav.setStyleSheet("QFrame{background:#000;border-right:1px solid #262626}")
        outer = QVBoxLayout(nav)
        outer.setContentsMargins(0, 0, 0, 8)
        outer.setSpacing(2)
        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()  # в невысоком окне разделы прокручиваются, а не сжимаются
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:#000;border:none}QScrollBar:vertical{width:6px}")
        inner = QWidget()
        inner.setStyleSheet("background:#000")
        v = QVBoxLayout(inner)
        v.setContentsMargins(6, 8, 6, 4)
        v.setSpacing(2)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        self.nav_group = QButtonGroup(self)
        self.nav_hub = self._nav_button("Проекты", "projects")
        self.nav_project = self._nav_button("Проект", "project")
        self.nav_settings = self._nav_button("Настройки", "settings")
        for b, page in ((self.nav_hub, PAGE_HUB), (self.nav_project, PAGE_PROJECT), (self.nav_settings, PAGE_SETTINGS)):
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, p=page: self.show_page(p))
            self.nav_group.addButton(b)
        v.addWidget(self.nav_hub)
        # три шага работы вместо длинного списка студий; редкие студии — под «Ещё»
        steps = QLabel("ШАГИ")
        steps.setStyleSheet("color:#6A6A6A;font-size:10px;letter-spacing:1px;padding:6px 0 0 4px")
        v.addWidget(steps)
        self.nav_project.setText("1 · Рисую")
        self.nav_project.setToolTip("Рисовать экраны: добавлять компоненты, менять текст, цвета и размеры")
        v.addWidget(self.nav_project)
        self.nav_layers = self._nav_button("Слои", "layers")
        self.nav_layers.setToolTip("Панель слоёв открытого проекта")
        self.nav_layers.clicked.connect(self._show_layers)
        self.nav_studios = {}
        for page, text, icon, _ in STUDIOS:
            b = self._nav_button(text, icon)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, pg=page: self.show_page(pg))
            self.nav_group.addButton(b)
            self.nav_studios[page] = b
        for page, text, tip in ((PAGE_PREVIEW, "2 · Проверяю", "Проверить экраны на телефоне, планшете или в окне: "
                                 "нажимать кнопки, листать, вводить текст (F5)"),
                                (PAGE_EXPORT, "3 · Выгружаю", "Получить проект Android Studio, тестовый APK и "
                                 "задание для ИИ")):
            b = self.nav_studios[page]
            b.setText(text)
            b.setToolTip(tip)
            v.addWidget(b)
        self.nav_task = self._nav_button("ИИ-задание", "ai")
        self.nav_task.setToolTip("Задание для Claude Code (AI_TASK.md) на странице экспорта")
        self.nav_task.clicked.connect(self.open_task)
        self.nav_more = QToolButton()
        self.nav_more.setObjectName("NavMore")
        self.nav_more.setCheckable(True)
        self.nav_more.setText("Ещё ▾")
        self.nav_more.setToolTip("Компоненты, значки, шрифты, цвета, ресурсы, анимации, логика, проверка ошибок")
        self.nav_more.setFixedSize(94, 30)
        self.nav_more.toggled.connect(self._toggle_more)
        v.addSpacing(6)
        v.addWidget(self.nav_more)
        self.more_box = QWidget()
        mv = QVBoxLayout(self.more_box)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(2)
        for page, *_ in STUDIOS:
            if page not in (PAGE_PREVIEW, PAGE_EXPORT):
                mv.addWidget(self.nav_studios[page])
        mv.addWidget(self.nav_layers)
        mv.addWidget(self.nav_task)
        self.more_box.setVisible(False)
        v.addWidget(self.more_box)
        for text, icon, stage in NAV_FUTURE:
            b = self._nav_button(text, icon)
            b.setEnabled(False)
            b.setToolTip(f"{text}: будет доступно на этапе {stage}")
            v.addWidget(b)
        v.addStretch()
        sl = QHBoxLayout()
        sl.setContentsMargins(6, 0, 6, 0)
        sl.addWidget(self.nav_settings)
        outer.addLayout(sl)
        return nav

    def show_tour(self) -> None:
        from app.ui.shell.tour import TourDialog
        self.tour = TourDialog(self)
        self.tour.setModal(False)  # не мешает работать: окно можно закрыть или отодвинуть
        self.tour.show()

    def open_animations(self) -> None:
        self.show_page(PAGE_ANIMATIONS)

    def open_logic(self) -> None:
        self.show_page(PAGE_LOGIC)

    def _toggle_more(self, on: bool) -> None:
        self.more_box.setVisible(on)
        self.nav_more.setText("Ещё ▴" if on else "Ещё ▾")

    def _build_menu(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("Проект")
        self.act_new = self._act(m, "Новый проект…", QKeySequence.StandardKey.New, lambda: self.new_project(""))
        self._act(m, "Открыть…", QKeySequence.StandardKey.Open, self.hub.open_file_dialog)
        self._act(m, "Импорт проекта…", None, self.hub.import_dialog)
        m.addSeparator()
        self.act_save = self._act(m, "Сохранить", QKeySequence.StandardKey.Save, self.save_project)
        self.act_close = self._act(m, "Закрыть проект", QKeySequence("Ctrl+W"), self.close_project)
        m.addSeparator()
        self.act_version = self._act(m, "Сохранить версию…", QKeySequence("Ctrl+Alt+S"), self.save_version)
        self.act_history = self._act(m, "История версий…", None, self.show_versions)
        m.addSeparator()
        self.act_template = self._act(m, "Сохранить как шаблон…", None, self.save_as_template)
        m.addSeparator()
        self._act(m, "Все проекты", QKeySequence("Ctrl+H"), lambda: self.show_page(PAGE_HUB))
        self._act(m, "Настройки", QKeySequence("Ctrl+,"), lambda: self.show_page(PAGE_SETTINGS))
        m.addSeparator()
        self._act(m, "Выход", QKeySequence("Alt+F4"), self.close)
        ws = self.project_page
        self.menu_edit = mb.addMenu("Правка")
        self.menu_view = mb.addMenu("Вид")
        for menu, actions in ((self.menu_edit, ws.edit_actions), (self.menu_view, ws.view_actions)):
            for a in actions:
                menu.addSeparator() if a is None else menu.addAction(a)
        self.menu_view.addSeparator()
        for dock in (ws.dock_layers, ws.dock_inspector, ws.dock_screens, ws.dock_diag):
            self.menu_view.addAction(dock.toggleViewAction())
        for title, items in MENU_FUTURE.items():
            sub = mb.addMenu(title)
            if title == "Инструменты":
                for a in ws.tools_actions:
                    sub.addSeparator() if a is None else sub.addAction(a)
                sub.addSeparator()
                self.studio_actions = []
                for page, _, _, sc in STUDIOS:
                    a = self._act(sub, STUDIO_TITLES[page], QKeySequence(sc),
                                  lambda _=False, pg=page: self.show_page(pg))
                    self.studio_actions.append(a)
                sub.addSeparator()
            if title == "Экспорт":
                for text, sc, slot in (("Экраны в PNG…", "Ctrl+Shift+E", self.export_png),
                                       ("Экраны в PDF…", None, self.export_pdf),
                                       ("Прототип в браузере (HTML)…", None, self.export_html),
                                       ("Показ на весь экран", "Shift+F5", self.present),
                                       ("Иконка приложения из выделенного", None, self.make_app_icon),
                                       ("Проверка проекта", "F7", self.show_validator),
                                       ("AI-экспорт для Claude Code…", "Ctrl+E", lambda: self.show_page(PAGE_EXPORT)),
                                       ("Задание для Claude Code (AI_TASK.md)", None, self.open_task)):
                    self.studio_actions.append(self._act(sub, text, QKeySequence(sc) if sc else None, slot))
            if title == "Устройства":
                self.act_run = self._act(sub, "▶ Интерактивный предпросмотр", QKeySequence("F5"),
                                         self.run_prototype)
                self.studio_actions.append(self.act_run)
            for text, stage in items:
                a = sub.addAction(f"{text}  —  этап {stage}")
                a.setEnabled(False)
        h = mb.addMenu("Помощь")
        self._act(h, "Как пользоваться", QKeySequence("F1"), self.show_tour)
        self._act(h, "Горячие клавиши", QKeySequence("Ctrl+/"), self.show_shortcuts)
        h.addSeparator()
        self._act(h, "Открыть папку журнала", None,
                  lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.paths.logs))))
        self._act(h, "Проверить обновления…", None, lambda: self.updates.check_now())
        self._act(h, "О программе", None, lambda: QMessageBox.about(
            self, APP_NAME, f"{APP_NAME} {APP_VERSION}\nЛокальная студия дизайна интерфейсов Android и Windows.\n\n"
                            f"{COPYRIGHT}\nБесплатная программа: пользоваться можно свободно, ваши дизайны — ваши.\n"
                            "Использует PySide6 / Qt (LGPLv3) — см. THIRD_PARTY_NOTICES."))

    def shortcut_rows(self) -> list[tuple[str, str]]:
        """Все действия с клавишами: (сочетание, что делает), без повторов, по алфавиту."""
        rows = {}
        extra = [("Alt (зажать)", "Расстояния от выделенного до элемента под курсором"),
                 ("Пробел + перетаскивание", "Двигать холст"), ("Стрелки / Shift+стрелки", "Сдвиг на 1 / 10"),
                 ("Ctrl + колесо", "Масштаб холста"), ("Esc", "Снять выделение, отменить пипетку")]
        for a in self.findChildren(QAction):
            keys = [k.toString(QKeySequence.SequenceFormat.NativeText) for k in a.shortcuts() if not k.isEmpty()]
            text = a.text().replace("&", "").strip()
            if keys and text:
                rows.setdefault(" / ".join(keys), text)
        return sorted(rows.items(), key=lambda r: r[1].lower()) + extra

    # ---------- свои горячие клавиши ----------
    def set_shortcut(self, name: str, seq: str, take: bool = True) -> bool:
        """Назначить команде сочетание ("" — без клавиш). Занятое другой командой — отобрать у неё (take)."""
        from app.ui.shell import shortcuts as sc
        cmds = sc.commands(self)
        if name not in cmds:
            return False
        custom = sc.load(self.ctx.settings)
        fmt = QKeySequence.SequenceFormat.PortableText
        seq = QKeySequence(seq, fmt).toString(fmt) if seq else ""
        if seq:
            other = sc.owner(self, seq, skip=name)
            if other is not None:
                if not take:
                    return False
                custom[other] = [k for k in sc.current(cmds[other]) if k != seq]
            custom[name] = [seq]
        else:
            custom[name] = []
        for n in list(custom):  # хранить только отличия от стандартных
            if n in cmds and custom[n] == sc.group_defaults(cmds[n]):
                del custom[n]
        sc.save(self.ctx.settings, custom)
        sc.apply(self, custom)
        return True

    def reset_shortcuts(self) -> None:
        from app.ui.shell import shortcuts as sc
        sc.save(self.ctx.settings, {})
        sc.apply(self, {})

    def edit_shortcut(self, name: str) -> bool:
        """Окно «нажмите новое сочетание»; занятое — с вопросом, отдать ли его этой команде."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QKeySequenceEdit, QLabel, QVBoxLayout
        from app.ui.shell import shortcuts as sc
        d = QDialog(self)
        d.setWindowTitle("Горячая клавиша")
        v = QVBoxLayout(d)
        v.addWidget(QLabel(f"Команда «{name}». Нажмите новое сочетание клавиш:"))
        edit = QKeySequenceEdit()
        edit.setMaximumSequenceLength(1)
        edit.setClearButtonEnabled(True)
        cur = sc.current(sc.commands(self).get(name, []))
        if cur:
            edit.setKeySequence(QKeySequence(cur[0], QKeySequence.SequenceFormat.PortableText))
        v.addWidget(edit)
        hint = QLabel("Очистить поле (×) — команда без клавиш.")
        hint.setObjectName("Hint")
        v.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        v.addWidget(bb)
        edit.setFocus()
        self._key_dialog = (d, edit)
        if d.exec() != QDialog.DialogCode.Accepted:
            return False
        seq = edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        other = sc.owner(self, seq, skip=name) if seq else None
        if other is not None and QMessageBox.question(
                self, "Сочетание занято", f"«{sc.native([seq])}» уже у команды «{other}».\n"
                f"Отдать его команде «{name}»? У «{other}» клавиши не будет.") != QMessageBox.StandardButton.Yes:
            return False
        return self.set_shortcut(name, seq)

    def show_shortcuts(self) -> None:
        """Все команды и их клавиши; двойной щелчок или «Изменить…» — своё сочетание."""
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                                       QVBoxLayout)
        from app.ui.shell import shortcuts as sc
        d = QDialog(self)
        d.setWindowTitle("Горячие клавиши")
        d.resize(600, 660)
        v = QVBoxLayout(d)
        find = QLineEdit()
        find.setPlaceholderText("Найти действие или клавишу…")
        v.addWidget(find)
        t = QTableWidget(0, 2)
        t.setHorizontalHeaderLabels(["Клавиши", "Действие"])
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        v.addWidget(t)
        row = QHBoxLayout()
        change = QPushButton("Изменить…")
        change.setToolTip("Или двойной щелчок по строке")
        reset = QPushButton("Сбросить всё")
        reset.setToolTip("Вернуть стандартные клавиши всем командам")
        row.addWidget(change)
        row.addStretch(1)
        row.addWidget(reset)
        v.addLayout(row)
        fixed = [("Alt (зажать)", "Расстояния от выделенного до элемента под курсором"),
                 ("Пробел + перетаскивание", "Двигать холст"), ("Стрелки / Shift+стрелки", "Сдвиг на 1 / 10"),
                 ("Ctrl + колесо", "Масштаб холста"), ("Esc", "Снять выделение, отменить пипетку")]

        def fill():
            r = t.currentRow()
            keep = t.item(r, 1).text() if r >= 0 and t.item(r, 1) is not None else ""
            cmds = sc.commands(self)
            rows = sorted(((sc.native(sc.current(a)), n, True) for n, a in cmds.items()), key=lambda x: x[1].lower())
            rows += [(k, n, False) for k, n in fixed]
            t.setRowCount(len(rows))
            custom = sc.load(self.ctx.settings)
            for i, (k, n, editable) in enumerate(rows):
                ki, ni = QTableWidgetItem(k or "—"), QTableWidgetItem(n)
                ki.setData(Qt.ItemDataRole.UserRole, n if editable else None)
                if not editable:
                    for it in (ki, ni):
                        it.setForeground(t.palette().placeholderText())
                        it.setToolTip("Встроено в холст — не меняется")
                elif n in custom:
                    f = QFont(ki.font())
                    f.setBold(True)
                    ki.setFont(f)
                    ki.setToolTip("Своё сочетание")
                t.setItem(i, 0, ki)
                t.setItem(i, 1, ni)
                if n == keep:
                    t.setCurrentCell(i, 0)
            t.resizeColumnToContents(0)
            t.setColumnWidth(0, t.columnWidth(0) + 16)  # воздух у границы столбца
            if t.currentRow() < 0:
                t.setCurrentCell(0, 0)  # «Изменить…» сразу работает
            filt(find.text())

        def filt(q):
            for i in range(t.rowCount()):
                text = (t.item(i, 0).text() + " " + t.item(i, 1).text()).lower()
                t.setRowHidden(i, bool(q) and q.lower() not in text)

        def edit_row(*_):
            r = t.currentRow()
            name = t.item(r, 0).data(Qt.ItemDataRole.UserRole) if r >= 0 else None
            if name and self.edit_shortcut(name):
                fill()

        def reset_all():
            if QMessageBox.question(d, "Горячие клавиши", "Вернуть стандартные клавиши всем командам?") == \
                    QMessageBox.StandardButton.Yes:
                self.reset_shortcuts()
                fill()
        t.cellDoubleClicked.connect(edit_row)
        change.clicked.connect(edit_row)
        reset.clicked.connect(reset_all)
        find.textChanged.connect(filt)
        fill()
        self._shortcuts_dialog = d
        self._shortcuts_table = t
        d.show()

    def _act(self, menu, text, shortcut, slot) -> QAction:
        a = QAction(text, self)
        if shortcut is not None:
            a.setShortcut(shortcut)
        # флажок получает состояние; обычной команде «checked=False» не передаётся (иначе export_png(folder=False))
        a.triggered.connect(lambda checked=False, act=a, fn=slot: fn(checked) if act.isCheckable() else fn())
        menu.addAction(a)
        return a

    # ---------- состояние ----------
    def show_page(self, page: int) -> None:
        if (page == PAGE_PROJECT or page in STUDIO_TITLES) and self.doc is None:
            page = PAGE_HUB
        current = self.pages.currentWidget()
        if current in (self.builder, self.icons) and self.pages.widget(page) is not current \
                and not current.confirm_leave():
            return
        if page == PAGE_HUB:
            self.hub.refresh()
        self.pages.setCurrentIndex(page)
        btn = {PAGE_HUB: self.nav_hub, PAGE_PROJECT: self.nav_project, PAGE_SETTINGS: self.nav_settings,
               **self.nav_studios}[page]
        btn.setChecked(True)
        if btn.parent() is self.more_box and not self.nav_more.isChecked():
            self.nav_more.setChecked(True)  # открытый раздел из «Ещё» должен быть виден в меню
        if page in (PAGE_COLORS, PAGE_RESOURCES, PAGE_FONTS, PAGE_ANIMATIONS, PAGE_LOGIC, PAGE_VALIDATE, PAGE_EXPORT):
            self.pages.widget(page).refresh()
        if page != PAGE_ANIMATIONS and hasattr(self, "animations"):
            self.animations.stop(keep_position=True)
        if page == PAGE_PREVIEW:
            self.preview.activate()
        elif hasattr(self, "preview"):
            self.preview.deactivate()

    def _update_state(self) -> None:
        has = self.doc is not None
        self.act_save.setEnabled(has)
        self.act_close.setEnabled(has)
        self.nav_project.setEnabled(has)
        self.nav_layers.setEnabled(has)
        self.nav_task.setEnabled(has)
        self.nav_task.setToolTip("Задание для Claude Code (AI_TASK.md) на странице экспорта" if has
                                 else "Откройте или создайте проект")
        for b in self.nav_studios.values():
            b.setEnabled(has)
            b.setToolTip("" if has else "Откройте или создайте проект")
        for a in getattr(self, "studio_actions", []):
            a.setEnabled(has)
        self.act_template.setEnabled(has)
        self.act_version.setEnabled(has)
        self.act_history.setEnabled(has)
        self.nav_project.setToolTip("" if has else "Откройте или создайте проект")
        title = WINDOW_TITLE
        if has:
            title = f"{'● ' if self.dirty else ''}{self.doc.meta.title} — {WINDOW_TITLE}"
            self.statusBar().showMessage(f"{self.doc_path}  ·  {'есть несохранённые изменения' if self.dirty else 'сохранено'}")
        self.setWindowTitle(title)

    def _mark_dirty(self) -> None:
        self.dirty = self.doc is not None and self.project_page.is_dirty()
        self._update_state()

    def _show_layers(self) -> None:
        if self.doc is None:
            self.nav_layers.setChecked(False)
            return
        self.show_page(PAGE_PROJECT)
        self.project_page.focus_layers()

    def _settings_changed(self) -> None:
        s = self.ctx.settings
        if s.get("project/autosave_enabled"):
            self.autosave_timer.start(s.get("project/autosave_minutes") * 60_000)
        else:
            self.autosave_timer.stop()

    def _err(self, title: str, exc: Exception) -> None:
        log.warning("%s: %s", title, exc)
        QMessageBox.warning(self, title, str(exc))

    # ---------- операции ----------
    def new_project(self, template_id: str = "") -> None:
        if not self._confirm_discard():
            return
        location = self.ctx.settings.projects_dir
        from app.core.project.templates import TemplateStore
        wiz = NewProjectWizard(location, template_id, self,
                               user_templates=TemplateStore(self.ctx.paths.templates).items())
        if wiz.exec() != NewProjectWizard.DialogCode.Accepted or wiz.result_spec is None:
            return
        try:
            doc, path = self.ctx.service.create(wiz.result_spec)
        except ProjectError as exc:
            self._err("Не удалось создать проект", exc)
            return
        if wiz.open_after:
            self._set_document(doc, path)
            self.ctx.index.touch_opened(doc.meta.id)
            self.show_page(PAGE_PROJECT)
        else:
            self.show_page(PAGE_HUB)
            self.hub.select_project(doc.meta.id)

    def open_project(self, path: str) -> None:
        if self.doc_path and Path(path).resolve() == self.doc_path.resolve():
            self.show_page(PAGE_PROJECT)
            return
        if not self._confirm_discard():
            return
        try:
            doc = self.ctx.service.open(path)
        except ProjectFormatError as exc:
            self._err("Не удалось открыть проект", exc)
            self.hub.refresh()
            return
        self._set_document(doc, Path(path))
        self.show_page(PAGE_PROJECT)
        if not self.ctx.settings.get("general/tour_done") and not os.environ.get("ADS_NO_TOUR"):
            # первый проект — короткое обучение по шагам (в тестах и самопроверке не показывается)
            self.ctx.settings.set("general/tour_done", True)
            self.show_tour()

    def _set_document(self, doc: ProjectDocument | None, path: Path | None, dirty: bool = False) -> None:
        self.doc, self.doc_path = doc, path
        if doc is not None:
            from app.ui.fonts import REGISTRY
            problems = REGISTRY.register_document(doc)
            if problems:
                self.statusBar().showMessage("Шрифты проекта: " + "; ".join(problems), 10000)
        self.project_page.set_document(doc, dirty)
        self.builder.reset_for_document()
        self.icons.reset_for_document()
        self.dirty = dirty
        self._update_state()

    def save_project(self) -> bool:
        if not self.doc or not self.doc_path:
            return False
        try:
            self.ctx.service.save(self.doc, self.doc_path)
        except (ProjectError, ProjectFormatError, OSError) as exc:
            self._err("Не удалось сохранить проект", exc)
            return False
        self.ctx.recovery.clear(self.doc.meta.id)
        self.project_page.mark_clean()
        self.dirty = False
        self._update_state()
        self.statusBar().showMessage(f"Сохранено: {self.doc_path}", 5000)
        return True

    def autosave(self) -> None:
        if self.doc and self.dirty:
            try:
                self.ctx.recovery.write(self.doc, self.doc_path)
            except (OSError, ProjectFormatError) as exc:
                log.error("Ошибка автосохранения: %s", exc)

    def close_project(self) -> bool:
        if not self._confirm_discard():
            return False
        if self.doc:
            self.ctx.recovery.clear(self.doc.meta.id)
        self._set_document(None, None)
        self.show_page(PAGE_HUB)
        return True

    def _confirm_discard(self) -> bool:
        for studio in (self.builder, self.icons):  # несохранённый мастер или иконка ещё не в документе
            if not studio.confirm_leave():
                return False
        if not self.doc or not self.dirty:
            return True
        box = QMessageBox(QMessageBox.Icon.Question, "Несохранённые изменения",
                          f"Сохранить изменения в проекте «{self.doc.meta.title}»?", parent=self)
        save = box.addButton("Сохранить", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Не сохранять", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is save:
            return self.save_project()
        if box.clickedButton() is discard:
            self.ctx.recovery.clear(self.doc.meta.id)
            self.dirty = False
            return True
        return False

    def run_prototype(self) -> None:
        if self.doc is None:
            return
        self.preview.start(self.project_page.editor.screen_id)  # новый сеанс с текущего экрана
        self.show_page(PAGE_PREVIEW)

    def show_validator(self) -> None:
        self.show_page(PAGE_VALIDATE)

    # ---------- экраны картинками и показ ----------
    def _export_dir(self) -> str:
        from pathlib import Path
        base = Path(self.ctx.settings.get("general/projects_dir") or str(Path.home())) / "Экспорт"
        return str(base / (self.doc.meta.title if self.doc else "проект"))

    def export_png(self, folder: str | None = None, scale: float | None = None, all_screens: bool | None = None):
        """Экраны в PNG: текущий или все, масштаб 0,5× – 3×; после — открывается папка."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QComboBox, QFormLayout, QFileDialog
        ed = self.project_page.editor
        if self.doc is None or ed.screen() is None:
            return None
        if folder is None:
            d = QDialog(self)
            d.setWindowTitle("Экраны в PNG")
            f = QFormLayout(d)
            which = QComboBox()
            which.addItem(f"Текущий — «{ed.screen().name}»", False)
            which.addItem(f"Все экраны ({len(self.doc.screens)})", True)
            f.addRow("Что", which)
            size = QComboBox()
            for k, t in ((1.0, "1× — как в макете"), (2.0, "2× — для печати и Retina"), (3.0, "3×"),
                         (0.5, "0,5× — лёгкий, для чатов")):
                size.addItem(t, k)
            f.addRow("Размер", size)
            bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            bb.accepted.connect(d.accept)
            bb.rejected.connect(d.reject)
            f.addRow(bb)
            if d.exec() != QDialog.DialogCode.Accepted:
                return None
            folder = QFileDialog.getExistingDirectory(self, "Папка для картинок", self._export_dir())
            if not folder:
                return None
            scale, all_screens = size.currentData(), which.currentData()
        from app.ui.workspace.render_export import save_pngs
        screens = list(self.doc.screens) if all_screens else [ed.screen()]
        try:
            paths = save_pngs(screens, self.doc, ed.artboard_color(), folder, scale or 1.0)
        except OSError as exc:
            QMessageBox.warning(self, "Экраны в PNG", str(exc))
            return None
        self.statusBar().showMessage(f"Сохранено картинок: {len(paths)} — {folder}", 8000)
        if not self._quiet:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        return paths

    def export_pdf(self, path: str | None = None):
        """Все экраны одним PDF: страница — экран, текст векторный."""
        from PySide6.QtWidgets import QFileDialog
        ed = self.project_page.editor
        if self.doc is None or not self.doc.screens:
            return None
        if path is None:
            from pathlib import Path
            path, _ = QFileDialog.getSaveFileName(self, "Экраны в PDF",
                                                  str(Path(self._export_dir()) / f"{self.doc.meta.title}.pdf"),
                                                  "PDF (*.pdf)")
            if not path:
                return None
        from pathlib import Path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        from app.ui.workspace.render_export import save_pdf
        pages = save_pdf(list(self.doc.screens), self.doc, ed.artboard_color(), path, self.doc.meta.title)
        self.statusBar().showMessage(f"PDF: {pages} стр. — {path}", 8000)
        if not self._quiet:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        return path

    def export_html(self, path: str | None = None):
        """Прототип одним HTML-файлом: открывается в любом браузере, на компьютере и на телефоне."""
        from pathlib import Path
        from PySide6.QtWidgets import QApplication, QFileDialog, QProgressDialog
        ed = self.project_page.editor
        if self.doc is None or not self.doc.screens:
            return None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Прототип в браузере",
                                                  str(Path(self._export_dir()) / f"{self.doc.meta.title}.html"),
                                                  "Веб-страница (*.html)")
            if not path:
                return None
        from app.ui.workspace.web_export import save_html
        wait = QProgressDialog("Обхожу состояния прототипа…", None, 0, 0, self)
        wait.setWindowTitle("Прототип в браузере")
        wait.setMinimumDuration(400)

        def progress(i, n):
            wait.setMaximum(n)
            wait.setValue(i)
            QApplication.processEvents()
        start = ed.screen_id if ed.screen() is not None else None
        try:
            r = save_html(self.doc, ed.engine, ed.artboard_color(), path, start, progress)
        except OSError as e:
            QMessageBox.warning(self, "Прототип в браузере", f"Не удалось записать файл:\n{e}")
            return None
        finally:
            wait.close()
        mb = r.size / 1_000_000
        self.statusBar().showMessage(f"Прототип: {r.states} сост., {mb:.1f} МБ — {r.path}", 10000)
        if r.cut and not self._quiet:
            QMessageBox.information(self, "Прототип в браузере",
                                    f"Состояний очень много — в файл вошли первые {r.states}. Обычно так бывает "
                                    "со счётчиками без предела: в браузере после них появится подсказка.")
        if not self._quiet:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(r.path)))
        return r

    _quiet = False  # тесты: не открывать проводник и просмотрщик

    def present(self):
        """Экраны проекта на весь экран, с текущего; стрелки — листать, Esc — выход."""
        from app.ui.studio.present import Presentation
        ed = self.project_page.editor
        if self.doc is None or not self.doc.screens:
            return None
        start = next((i for i, s in enumerate(self.doc.screens) if s.id == ed.screen_id), 0)
        self._presentation = Presentation(self.doc.screens, self.doc, ed.artboard_color(), start)
        self._presentation.showFullScreen()
        self._presentation.setFocus()
        return self._presentation

    # ---------- версии ----------
    def save_version(self, label: str | None = None):
        from PySide6.QtWidgets import QInputDialog
        from app.core.project.versions import save_version
        if self.doc is None:
            return None
        if label is None:
            label, ok = QInputDialog.getText(self, "Сохранить версию", "Подпись (что сделано):",
                                             text="Перед правками")
            if not ok:
                return None
        path = save_version(self.doc, self.ctx.paths.base, label)
        self.statusBar().showMessage(f"Версия «{label}» сохранена — Проект → История версий", 6000)
        return path

    def versions(self):
        from app.core.project.versions import list_versions
        return list_versions(self.doc.meta.id, self.ctx.paths.base, self.ctx.paths.backups) if self.doc else []

    def restore_version(self, version) -> bool:
        from app.core.project.versions import load_version
        try:
            other = load_version(version.path)
        except Exception as exc:  # noqa: BLE001 — повреждённая копия: сообщение пользователю
            self._err("Не удалось открыть версию", exc)
            return False
        self.save_version("Перед откатом")  # текущее состояние не теряется
        ok = self.project_page.editor.restore_document(other, f"Вернуть версию {version.when:%d.%m %H:%M}")
        if ok:
            self.statusBar().showMessage(f"Возвращена версия {version.title} — Ctrl+Z отменит", 8000)
        return ok

    def show_versions(self) -> None:
        from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout
        if self.doc is None:
            return
        d = QDialog(self)
        d.setWindowTitle("История версий")
        d.resize(520, 480)
        v = QVBoxLayout(d)
        v.addWidget(QLabel("Свои точки сохранения (Ctrl+Alt+S) и автокопии перед каждым сохранением. "
                           "Возврат можно отменить (Ctrl+Z); текущее состояние перед ним сохраняется версией."))
        lst = QListWidget()
        for ver in self.versions():
            it = QListWidgetItem(("🕘 " if ver.auto else "★ ") + ver.title)
            it.setData(Qt.ItemDataRole.UserRole, ver)
            lst.addItem(it)
        v.addWidget(lst, 1)
        row = QHBoxLayout()
        b_new = QPushButton("Сохранить версию сейчас")
        b_back = QPushButton("Вернуть выбранную")
        b_back.setObjectName("Primary")
        row.addWidget(b_new)
        row.addStretch()
        row.addWidget(b_back)
        v.addLayout(row)

        def back():
            it = lst.currentItem()
            if it and QMessageBox.question(d, "История версий", f"Вернуть версию {it.text()[2:]}?") == \
                    QMessageBox.StandardButton.Yes and self.restore_version(it.data(Qt.ItemDataRole.UserRole)):
                d.accept()

        def new():
            if self.save_version():
                d.accept()
                self.show_versions()
        b_back.clicked.connect(back)
        b_new.clicked.connect(new)
        lst.itemDoubleClicked.connect(lambda _: back())
        self._versions_dialog = d
        d.show()

    def make_app_icon(self) -> bool:
        ed = self.project_page.editor
        nodes = ed.selected_nodes()
        if len(nodes) != 1:
            QMessageBox.information(self, "Иконка приложения",
                                    "Выделите один элемент (например, квадрат или круг со значком) — он станет "
                                    "иконкой приложения. Держите главное в центре: Android обрезает края по форме "
                                    "иконки телефона.")
            return False
        return ed.set_app_icon(nodes[0].id)

    def export_screens(self, screen_ids: list[str]) -> None:
        """AI-экспорт с заранее выбранными экранами (например, где используется компонент)."""
        self.show_page(PAGE_EXPORT)
        if self.pages.currentWidget() is self.export_page:
            self.export_page.select_screens(screen_ids)

    def open_task(self) -> None:
        if self.doc is None:
            return
        self.show_page(PAGE_EXPORT)
        self.export_page.focus_task()

    def go_to_node(self, screen_id: str, node_id: str) -> None:
        """Из списка замечаний — к экрану и элементу в рабочей области."""
        ed = self.project_page.editor
        if self.doc is None or all(s.id != screen_id for s in self.doc.screens):
            return
        ed.set_screen(screen_id)
        self.show_page(PAGE_PROJECT)
        if node_id:
            from app.core.document import tree
            if node_id in tree.node_map(ed.screen()):
                ed.select_any([node_id])

    def open_in_builder(self, component_id: str) -> None:
        self.show_page(PAGE_BUILDER)
        if self.pages.currentWidget() is self.builder:
            self.builder.open_component(component_id)

    def save_as_template(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        from app.core.project.templates import TemplateStore
        if self.doc is None:
            return
        title, ok = QInputDialog.getText(self, "Сохранить как шаблон", "Название шаблона:", text=self.doc.meta.title)
        if not ok or not title.strip():
            return
        try:
            TemplateStore(self.ctx.paths.templates).save(self.doc, title.strip())
        except (OSError, ProjectFormatError) as exc:
            self._err("Не удалось сохранить шаблон", exc)
            return
        self.statusBar().showMessage(f"Шаблон «{title.strip()}» сохранён — он доступен в мастере нового проекта",
                                     8000)
        self.hub.refresh()

    def check_recovery(self) -> None:
        for entry in self.ctx.recovery.entries():
            box = QMessageBox(QMessageBox.Icon.Warning, "Восстановление проекта",
                              f"Найдены несохранённые изменения проекта «{entry.title}» после аварийного завершения.\n\n"
                              f"Файл проекта: {entry.original_path}", parent=self)
            restore = box.addButton("Восстановить", QMessageBox.ButtonRole.AcceptRole)
            discard = box.addButton("Отказаться от изменений", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("Решить позже", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is restore:
                try:
                    doc = self.ctx.recovery.load(entry)
                except ProjectFormatError as exc:
                    self._err("Снимок восстановления повреждён", exc)
                    continue
                self._set_document(doc, Path(entry.original_path), dirty=True)
                self.show_page(PAGE_PROJECT)
                self.statusBar().showMessage("Проект восстановлен. Сохраните его (Ctrl+S).")
                return
            if box.clickedButton() is discard:
                self.ctx.recovery.clear(entry.project_id)

    def closeEvent(self, event: QCloseEvent) -> None:
        if getattr(self, "_skip_confirm", False) or self._confirm_discard():  # обновление уже спросило
            if self.doc:
                self.ctx.recovery.clear(self.doc.meta.id)
            event.accept()
        else:
            event.ignore()


__all__ = ["MainWindow", "Qt"]
