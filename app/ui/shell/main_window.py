"""Главное окно: меню, навигационная панель, страницы, автосохранение."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from app import APP_NAME, APP_VERSION
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
NAV_FUTURE = [
    ("Компоненты", "components", 4), ("Иконки", "icons", 4), ("Шрифты", "fonts", 4), ("Цвета", "colors", 4),
    ("Анимации", "animations", 5), ("Логика", "logic", 5), ("Устройства", "devices", 6),
    ("Ресурсы", "resources", 4), ("Проверка", "validate", 7), ("Экспорт", "export", 7), ("ИИ-задание", "ai", 7),
]
MENU_FUTURE = {
    "Инструменты": [("Конструктор компонентов", 4), ("SVG-редактор", 4), ("Типографика", 4),
                    ("Анимации", 5), ("Визуальная логика", 5)],
    "Экспорт": [("Проверка проекта", 7), ("AI-экспорт для Claude Code", 7)],
    "Устройства": [("Интерактивный предпросмотр", 6)],
}

PAGE_HUB, PAGE_PROJECT, PAGE_SETTINGS = 0, 1, 2


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
        for p in (self.hub, self.project_page, self.settings_page):
            self.pages.addWidget(p)
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
        b.setIcon(glyph_icon(icon, 20, fallback=text))
        b.setIconSize(QSize(20, 20))
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        b.setFixedSize(84, 50)
        return b

    def _build_nav(self) -> QWidget:
        nav = QFrame()
        nav.setFixedWidth(96)
        nav.setStyleSheet("QFrame{background:#000;border-right:1px solid #262626}")
        v = QVBoxLayout(nav)
        v.setContentsMargins(6, 8, 6, 8)
        v.setSpacing(2)
        self.nav_group = QButtonGroup(self)
        self.nav_hub = self._nav_button("Проекты", "projects")
        self.nav_project = self._nav_button("Проект", "project")
        self.nav_settings = self._nav_button("Настройки", "settings")
        for b, page in ((self.nav_hub, PAGE_HUB), (self.nav_project, PAGE_PROJECT), (self.nav_settings, PAGE_SETTINGS)):
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, p=page: self.show_page(p))
            self.nav_group.addButton(b)
        v.addWidget(self.nav_hub)
        v.addWidget(self.nav_project)
        self.nav_layers = self._nav_button("Слои", "layers")
        self.nav_layers.setToolTip("Панель слоёв открытого проекта")
        self.nav_layers.clicked.connect(self._show_layers)
        v.addWidget(self.nav_layers)
        for text, icon, stage in NAV_FUTURE:
            b = self._nav_button(text, icon)
            b.setEnabled(False)
            b.setToolTip(f"{text}: будет доступно на этапе {stage}")
            v.addWidget(b)
        v.addStretch()
        v.addWidget(self.nav_settings)
        return nav

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
            for text, stage in items:
                a = sub.addAction(f"{text}  —  этап {stage}")
                a.setEnabled(False)
        h = mb.addMenu("Помощь")
        self._act(h, "Открыть папку журнала", None,
                  lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.paths.logs))))
        self._act(h, "О программе", None, lambda: QMessageBox.about(
            self, APP_NAME, f"{APP_NAME} {APP_VERSION}\nЛокальная студия дизайна интерфейсов Android и Windows."))

    def _act(self, menu, text, shortcut, slot) -> QAction:
        a = QAction(text, self)
        if shortcut is not None:
            a.setShortcut(shortcut)
        a.triggered.connect(slot)
        menu.addAction(a)
        return a

    # ---------- состояние ----------
    def show_page(self, page: int) -> None:
        if page == PAGE_PROJECT and self.doc is None:
            page = PAGE_HUB
        if page == PAGE_HUB:
            self.hub.refresh()
        self.pages.setCurrentIndex(page)
        {PAGE_HUB: self.nav_hub, PAGE_PROJECT: self.nav_project, PAGE_SETTINGS: self.nav_settings}[page].setChecked(True)

    def _update_state(self) -> None:
        has = self.doc is not None
        self.act_save.setEnabled(has)
        self.act_close.setEnabled(has)
        self.nav_project.setEnabled(has)
        self.nav_layers.setEnabled(has)
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
        wiz = NewProjectWizard(location, template_id, self)
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

    def _set_document(self, doc: ProjectDocument | None, path: Path | None, dirty: bool = False) -> None:
        self.doc, self.doc_path = doc, path
        self.project_page.set_document(doc, dirty)
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
