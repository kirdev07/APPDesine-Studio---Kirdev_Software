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

from app import APP_NAME, APP_VERSION, COPYRIGHT
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
STUDIO_TITLES = {PAGE_BUILDER: "Component Builder", PAGE_ICONS: "SVG-редактор и иконки",
                 PAGE_FONTS: "Typography Studio", PAGE_COLORS: "Цвета", PAGE_RESOURCES: "Ресурсы",
                 PAGE_ANIMATIONS: "Animation Studio", PAGE_LOGIC: "Визуальная логика",
                 PAGE_PREVIEW: "Интерактивный предпросмотр", PAGE_VALIDATE: "Проверка проекта",
                 PAGE_EXPORT: "AI-экспорт для Claude Code"}


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.doc: ProjectDocument | None = None
        self.doc_path: Path | None = None
        self.dirty = False
        self.setWindowTitle(APP_NAME)
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
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.autosave)
        self._settings_changed()
        self.statusBar().showMessage("Fusion AMOLED · офлайн")
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
        self.act_template = self._act(m, "Сохранить как шаблон…", None, self.save_as_template)
        m.addSeparator()
        self._act(m, "Project Hub", QKeySequence("Ctrl+H"), lambda: self.show_page(PAGE_HUB))
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
                for text, sc, slot in (("Проверка проекта", "F7", self.show_validator),
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
        self._act(h, "О программе", None, lambda: QMessageBox.about(
            self, APP_NAME, f"{APP_NAME} {APP_VERSION}\nЛокальная студия дизайна интерфейсов Android и Windows.\n\n"
                            f"{COPYRIGHT}\nИспользование без письменного разрешения правообладателя запрещено.\n"
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

    def show_shortcuts(self) -> None:
        from PySide6.QtWidgets import QDialog, QTableWidget, QTableWidgetItem, QVBoxLayout, QLineEdit
        d = QDialog(self)
        d.setWindowTitle("Горячие клавиши")
        d.resize(560, 620)
        v = QVBoxLayout(d)
        find = QLineEdit()
        find.setPlaceholderText("Найти действие или клавишу…")
        v.addWidget(find)
        rows = self.shortcut_rows()
        t = QTableWidget(len(rows), 2)
        t.setHorizontalHeaderLabels(["Клавиши", "Действие"])
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i, (k, text) in enumerate(rows):
            t.setItem(i, 0, QTableWidgetItem(k))
            t.setItem(i, 1, QTableWidgetItem(text))
        t.resizeColumnToContents(0)
        v.addWidget(t)
        find.textChanged.connect(lambda q: [t.setRowHidden(i, bool(q) and q.lower() not in (r[0] + r[1]).lower())
                                            for i, r in enumerate(rows)])
        self._shortcuts_dialog = d
        d.show()

    def _act(self, menu, text, shortcut, slot) -> QAction:
        a = QAction(text, self)
        if shortcut is not None:
            a.setShortcut(shortcut)
        a.triggered.connect(slot)
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
        self.nav_project.setToolTip("" if has else "Откройте или создайте проект")
        title = APP_NAME
        if has:
            title = f"{'● ' if self.dirty else ''}{self.doc.meta.title} — {APP_NAME}"
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
        if self._confirm_discard():
            if self.doc:
                self.ctx.recovery.clear(self.doc.meta.id)
            event.accept()
        else:
            event.ignore()


__all__ = ["MainWindow", "Qt"]
