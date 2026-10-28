"""Project Hub — утверждённый вариант 2: папки слева, проекты в центре, детали справа, шаблоны снизу."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLineEdit, QListView, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import QFile

from app.context import AppContext
from app.core.persistence.container import EXTENSION, ProjectFormatError
from app.core.project.index import (
    FILTER_ALL, FILTER_ARCHIVE, FILTER_FAVORITES, FILTER_RECENT, SORT_CREATED, SORT_MODIFIED, SORT_TITLE,
    ProjectRecord,
)
from app.core.project.service import ProjectError
from app.libraries.catalog import TEMPLATES
from app.ui.widgets import (
    format_date, format_size, glyph_icon, label, panel, pixmap_icon, platforms_text, separator, thumbnail,
)

log = logging.getLogger(__name__)

ROLE_ID = Qt.ItemDataRole.UserRole
NEW_TILE = "__new__"
FILTERS = [(FILTER_ALL, "Все проекты"), (FILTER_RECENT, "Недавние"), (FILTER_FAVORITES, "Избранные"),
           (FILTER_ARCHIVE, "Архив")]
SORTS = [(SORT_MODIFIED, "По дате изменения"), (SORT_CREATED, "По дате создания"), (SORT_TITLE, "По названию")]
PROJECT_FILTER = f"Проекты App Design Studio (*{EXTENSION})"


class ProjectHubPage(QWidget):
    open_requested = Signal(str)
    new_requested = Signal(str)  # id шаблона или ""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx = ctx
        self._filter = FILTER_ALL
        self._folder: str | None = None
        self._records: dict[str, ProjectRecord] = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)
        root.addWidget(self._build_left(), 0)
        root.addWidget(self._build_center(), 1)
        root.addWidget(self._build_details(), 0)
        self.refresh()

    # ---------- левая колонка ----------
    def _build_left(self) -> QWidget:
        frame, lay = panel()
        frame.setFixedWidth(240)
        lay.addWidget(label("Проекты", "H1"))
        new_btn = QPushButton("+  Новый проект")
        new_btn.setObjectName("Primary")
        new_btn.clicked.connect(lambda: self.new_requested.emit(""))
        lay.addWidget(new_btn)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск проектов…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_projects)
        lay.addWidget(self.search)

        self.filter_list = QListWidget()
        self.filter_list.setFixedHeight(4 * 34)
        for key, _ in FILTERS:
            item = QListWidgetItem()
            item.setData(ROLE_ID, key)
            self.filter_list.addItem(item)
        self.filter_list.setCurrentRow(0)
        self.filter_list.itemClicked.connect(self._on_filter)
        lay.addWidget(self.filter_list)
        lay.addWidget(separator())

        head = QHBoxLayout()
        head.addWidget(label("Папки", "H2"))
        head.addStretch()
        add_folder = QToolButton()
        add_folder.setText("+")
        add_folder.setToolTip("Создать папку")
        add_folder.clicked.connect(self._add_folder)
        head.addWidget(add_folder)
        lay.addLayout(head)
        self.folder_list = QListWidget()
        self.folder_list.itemClicked.connect(self._on_folder)
        self.folder_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(self._folder_menu)
        lay.addWidget(self.folder_list, 1)

        disk, dlay = panel(margins=10)
        dlay.addWidget(label("Свободно на диске", "Muted"))
        self.disk_label = label("")
        dlay.addWidget(self.disk_label)
        self.disk_bar = QProgressBar()
        self.disk_bar.setTextVisible(False)
        dlay.addWidget(self.disk_bar)
        lay.addWidget(disk)
        return frame

    # ---------- центр ----------
    def _build_center(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        banner = QFrame()
        banner.setObjectName("Banner")
        bl = QVBoxLayout(banner)
        bl.setContentsMargins(20, 16, 20, 16)
        bl.addWidget(label("Управление проектами", "H1"))
        bl.addWidget(label("Создавайте, открывайте и организуйте свои дизайны. Всё хранится локально.", "Muted",
                           wrap=True))
        lay.addWidget(banner)

        projects, play = panel()
        from app.ui.widgets import FlowLayout
        self.list_title = label("Ваши проекты", "H2")
        play.addWidget(self.list_title)
        head_w = QWidget()
        head = FlowLayout(head_w, spacing=6)  # в узком окне кнопки переходят на вторую строку
        open_btn = QPushButton("Открыть файл…")
        open_btn.clicked.connect(self.open_file_dialog)
        head.addWidget(open_btn)
        import_btn = QPushButton("Импорт…")
        import_btn.setToolTip("Скопировать проект .adsproj в папку проектов")
        import_btn.clicked.connect(self.import_dialog)
        head.addWidget(import_btn)
        self.grid_btn = QToolButton()
        self.grid_btn.setIcon(glyph_icon("grid", 16, fallback="▦"))
        self.grid_btn.setToolTip("Плитки")
        self.list_btn = QToolButton()
        self.list_btn.setIcon(glyph_icon("list", 16, fallback="☰"))
        self.list_btn.setToolTip("Список")
        for b, mode in ((self.grid_btn, "grid"), (self.list_btn, "list")):
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, m=mode: self.set_view_mode(m))
            head.addWidget(b)
        self.sort_combo = QComboBox()
        for key, text in SORTS:
            self.sort_combo.addItem(text, key)
        saved_sort = self.ctx.settings.get("hub/sort")
        self.sort_combo.setCurrentIndex(max(0, self.sort_combo.findData(saved_sort)))
        self.sort_combo.currentIndexChanged.connect(self._on_sort)
        head.addWidget(self.sort_combo)
        play.addWidget(head_w)

        self.cards = QListWidget()
        self.cards.setObjectName("Cards")
        self.cards.setMovement(QListView.Movement.Static)
        self.cards.setResizeMode(QListView.ResizeMode.Adjust)
        self.cards.setUniformItemSizes(True)
        self.cards.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.cards.currentItemChanged.connect(self._on_select)
        self.cards.itemActivated.connect(self._on_activate)
        self.cards.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cards.customContextMenuRequested.connect(self._card_menu)
        play.addWidget(self.cards, 1)
        self.empty_label = label("", "Muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        play.addWidget(self.empty_label)
        lay.addWidget(projects, 1)

        tpl, tlay = panel()
        tlay.addWidget(label("Шаблоны проектов", "H2"))
        tlay.addWidget(label("Пустые стартовые шаблоны и ваши шаблоны (Проект → Сохранить как шаблон). "
                             "Шаблон удаляется через контекстное меню.", "Muted", wrap=True))
        self.templates = QListWidget()
        self.templates.setObjectName("Cards")
        self.templates.setViewMode(QListView.ViewMode.IconMode)
        self.templates.setFlow(QListView.Flow.LeftToRight)
        self.templates.setWrapping(False)
        self.templates.setIconSize(QSize(120, 66))
        self.templates.setGridSize(QSize(200, 112))
        self.templates.setFixedHeight(156)
        self.templates.setMovement(QListView.Movement.Static)
        self.templates.itemClicked.connect(lambda it: self.new_requested.emit(it.data(ROLE_ID)))
        self.templates.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.templates.customContextMenuRequested.connect(self._template_menu)
        tlay.addWidget(self.templates)
        lay.addWidget(tpl)

        self.set_view_mode(self.ctx.settings.get("hub/view_mode"), save=False)
        return w

    # ---------- правая колонка ----------
    def _build_details(self) -> QWidget:
        frame, lay = panel()
        frame.setFixedWidth(300)
        lay.addWidget(label("Информация о проекте", "H2"))
        self.d_preview = label("")
        self.d_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.d_preview)
        title_row = QHBoxLayout()
        self.d_title = label("", "H1", wrap=True)
        title_row.addWidget(self.d_title, 1)
        self.d_edit = QToolButton()
        self.d_edit.setIcon(glyph_icon("edit", 16, fallback="✎"))
        self.d_edit.setToolTip("Изменить название и описание")
        self.d_edit.clicked.connect(self._edit_meta)
        title_row.addWidget(self.d_edit, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(title_row)
        self.d_desc = label("", "Muted", wrap=True)
        lay.addWidget(self.d_desc)
        self.d_warn = label("", "Error", wrap=True)
        lay.addWidget(self.d_warn)
        lay.addWidget(separator())
        self.d_info = label("", wrap=True)
        self.d_info.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.d_info)
        lay.addWidget(separator())
        tags_head = QHBoxLayout()
        tags_head.addWidget(label("Теги", "H2"))
        tags_head.addStretch()
        self.add_tag_btn = QToolButton()
        self.add_tag_btn.setText("+")
        self.add_tag_btn.setToolTip("Добавить тег")
        self.add_tag_btn.clicked.connect(self._add_tag)
        tags_head.addWidget(self.add_tag_btn)
        lay.addLayout(tags_head)
        self.tags_box = QWidget()
        self.tags_layout = _FlowRows(self.tags_box)
        lay.addWidget(self.tags_box)
        lay.addStretch()

        self.b_open = QPushButton("▷  Открыть проект")
        self.b_open.setObjectName("Primary")
        self.b_open.clicked.connect(lambda: self._current() and self._open_record(self._current()))
        self.b_fav = QPushButton("★  В избранное")
        self.b_fav.clicked.connect(self._toggle_favorite)
        self.b_dup = QPushButton("Дублировать")
        self.b_dup.clicked.connect(self._duplicate)
        self.b_export = QPushButton("Экспорт копии…")
        self.b_export.clicked.connect(self._export)
        self.b_folder = QPushButton("Переместить в папку")
        self.b_folder.clicked.connect(lambda: self._folder_choice_menu().exec(self.b_folder.mapToGlobal(
            self.b_folder.rect().bottomLeft())))
        self.b_reveal = QPushButton("Показать в проводнике")
        self.b_reveal.clicked.connect(self._reveal)
        self.b_archive = QPushButton("Архивировать")
        self.b_archive.clicked.connect(self._toggle_archive)
        self.b_forget = QPushButton("Убрать из списка")
        self.b_forget.setToolTip("Файл на диске не трогается")
        self.b_forget.clicked.connect(self._forget)
        self.b_delete = QPushButton("Удалить в корзину")
        self.b_delete.setObjectName("Danger")
        self.b_delete.clicked.connect(self._delete)
        for b in (self.b_open, self.b_fav, self.b_dup, self.b_export, self.b_folder, self.b_reveal, self.b_archive,
                  self.b_forget, self.b_delete):
            lay.addWidget(b)
        scroll = QScrollArea()
        scroll.setWidget(frame)
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(316)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

    # ---------- данные ----------
    def refresh_templates(self) -> None:
        from app.core.project.templates import TemplateStore
        self.templates.clear()
        for t in TEMPLATES:
            item = QListWidgetItem(pixmap_icon(thumbnail(list(t.platforms), t.name, 140, 84)), t.name)
            item.setData(ROLE_ID, t.id)
            item.setToolTip(t.description)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.templates.addItem(item)
        for ut in TemplateStore(self.ctx.paths.templates).items():
            item = QListWidgetItem(pixmap_icon(thumbnail(ut.platforms, ut.title, 140, 84)), f"★ {ut.title}")
            item.setData(ROLE_ID, f"user:{ut.id}")
            item.setToolTip(f"Мой шаблон · экранов: {ut.screens}\n{ut.description}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.templates.addItem(item)

    def _template_menu(self, pos) -> None:
        from app.core.project.templates import TemplateStore
        item = self.templates.itemAt(pos)
        tid = item.data(ROLE_ID) if item else ""
        if not tid.startswith("user:"):
            return
        menu = QMenu(self)
        act = menu.addAction("Удалить шаблон…")
        if menu.exec(self.templates.mapToGlobal(pos)) == act and QMessageBox.question(
                self, "Шаблон", f"Удалить шаблон «{item.text()[2:]}»? Проекты, созданные из него, не изменятся.") \
                == QMessageBox.StandardButton.Yes:
            TemplateStore(self.ctx.paths.templates).remove(tid[5:])
            self.refresh_templates()

    def refresh(self) -> None:
        self.refresh_templates()
        self.ctx.service.refresh_missing()
        self.refresh_sidebar()
        self.refresh_projects()
        self._update_disk()

    def refresh_sidebar(self) -> None:
        limit = self.ctx.settings.get("general/recent_limit")
        counts = self.ctx.index.counts(limit)
        for i, (key, text) in enumerate(FILTERS):
            self.filter_list.item(i).setText(f"{text}   ·   {counts[key]}")
        fc = self.ctx.index.folder_counts()
        self.folder_list.clear()
        for name in self.ctx.index.folders():
            item = QListWidgetItem(glyph_icon("folder", 16, "#A0A0A0", "▢"), f"{name}   ·   {fc.get(name, 0)}")
            item.setData(ROLE_ID, name)
            self.folder_list.addItem(item)
            if name == self._folder:
                item.setSelected(True)

    def refresh_projects(self) -> None:
        selected = self._current().id if self._current() else None
        records = self.ctx.index.query(
            filter=self._filter if self._folder is None else FILTER_ALL,
            folder=self._folder, search=self.search.text().strip(),
            sort=self.sort_combo.currentData(), recent_limit=self.ctx.settings.get("general/recent_limit"))
        self._records = {r.id: r for r in records}
        self.cards.blockSignals(True)
        self.cards.clear()
        grid = self.cards.viewMode() == QListView.ViewMode.IconMode
        for r in records:
            star = "★ " if r.favorite else ""
            if grid:
                text = f"{star}{r.title}\n{format_date(r.modified_at)}\n{platforms_text(r.platforms)}"
            else:
                text = f"{star}{r.title}    ·    {platforms_text(r.platforms)}    ·    {format_date(r.modified_at)}"
            size = (200, 120) if grid else (64, 40)
            item = QListWidgetItem(pixmap_icon(thumbnail(r.platforms, r.title, *size, missing=r.missing)), text)
            item.setData(ROLE_ID, r.id)
            item.setToolTip(r.path)
            if grid:
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.cards.addItem(item)
        if self._filter != FILTER_ARCHIVE and not self.search.text():
            tile = QListWidgetItem("＋\nСоздать проект\nс нуля")
            tile.setData(ROLE_ID, NEW_TILE)
            tile.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if grid:
                tile.setSizeHint(QSize(216, 200))
            self.cards.addItem(tile)
        self.cards.blockSignals(False)
        self.empty_label.setText("" if records else ("Ничего не найдено" if self.search.text() else "Здесь пока нет проектов"))
        self.empty_label.setVisible(not records)
        if selected and selected in self._records:
            self.select_project(selected)
        elif records:
            self.cards.setCurrentRow(0)
        else:
            self._show_details(None)

    def select_project(self, project_id: str) -> None:
        for i in range(self.cards.count()):
            if self.cards.item(i).data(ROLE_ID) == project_id:
                self.cards.setCurrentRow(i)
                return

    def _update_disk(self) -> None:
        target = self.ctx.settings.projects_dir
        probe = target if target.exists() else Path(target.anchor or Path.home().anchor)
        try:
            du = shutil.disk_usage(probe)
        except OSError:
            self.disk_label.setText("нет данных")
            return
        gb = 1024 ** 3
        self.disk_label.setText(f"{du.free / gb:.1f} ГБ из {du.total / gb:.0f} ГБ ({probe.anchor})")
        self.disk_bar.setValue(int(100 * (du.total - du.free) / du.total))

    def set_view_mode(self, mode: str, save: bool = True) -> None:
        grid = mode != "list"
        self.grid_btn.setChecked(grid)
        self.list_btn.setChecked(not grid)
        if grid:
            self.cards.setViewMode(QListView.ViewMode.IconMode)
            self.cards.setIconSize(QSize(168, 100))
            self.cards.setGridSize(QSize(196, 186))
            self.cards.setWordWrap(True)
            self.cards.setSpacing(0)
        else:
            self.cards.setViewMode(QListView.ViewMode.ListMode)
            self.cards.setIconSize(QSize(64, 40))
            self.cards.setGridSize(QSize())
            self.cards.setSpacing(2)
        if save:
            self.ctx.settings.set("hub/view_mode", "grid" if grid else "list")
            self.refresh_projects()

    # ---------- обработчики ----------
    def _on_filter(self, item: QListWidgetItem) -> None:
        self._filter = item.data(ROLE_ID)
        self._folder = None
        self.folder_list.clearSelection()
        self.list_title.setText(dict(FILTERS)[self._filter])
        self.refresh_projects()

    def _on_folder(self, item: QListWidgetItem) -> None:
        self._folder = item.data(ROLE_ID)
        self._filter = FILTER_ALL
        self.filter_list.clearSelection()
        self.list_title.setText(f"Папка «{self._folder}»")
        self.refresh_projects()

    def _on_sort(self) -> None:
        self.ctx.settings.set("hub/sort", self.sort_combo.currentData())
        self.refresh_projects()

    def _current(self) -> ProjectRecord | None:
        item = self.cards.currentItem()
        return self._records.get(item.data(ROLE_ID)) if item else None

    def _on_select(self, *_):
        item = self.cards.currentItem()
        if item and item.data(ROLE_ID) == NEW_TILE:
            self._show_details(None)
            return
        self._show_details(self._current())

    def _on_activate(self, item: QListWidgetItem) -> None:
        if item.data(ROLE_ID) == NEW_TILE:
            self.new_requested.emit("")
        elif self._current():
            self._open_record(self._current())

    def _open_record(self, rec: ProjectRecord) -> None:
        self.open_requested.emit(rec.path)

    def _show_details(self, r: ProjectRecord | None) -> None:
        buttons = (self.b_open, self.b_fav, self.b_dup, self.b_export, self.b_folder, self.b_reveal, self.b_archive,
                   self.b_forget, self.b_delete, self.d_edit, self.add_tag_btn)
        for b in buttons:
            b.setEnabled(r is not None)
        if r is None:
            self.d_preview.clear()
            self.d_title.setText("Проект не выбран")
            self.d_desc.setText("Выберите проект в списке или создайте новый.")
            self.d_info.clear()
            self.d_warn.hide()
            self.tags_layout.set_tags([], None)
            return
        self.d_preview.setPixmap(thumbnail(r.platforms, r.title, 268, 150, missing=r.missing))
        self.d_title.setText(r.title)
        self.d_desc.setText(r.description or "Без описания")
        self.d_warn.setVisible(r.missing)
        self.d_warn.setText("Файл не найден или повреждён. Проверьте расположение или уберите проект из списка.")
        rows = [("Платформы", platforms_text(r.platforms)), ("Экранов", str(r.screens)),
                ("Создан", format_date(r.created_at)), ("Изменён", format_date(r.modified_at)),
                ("Размер", format_size(r.size)), ("Папка", r.folder or "—")]
        html = "".join(f"<tr><td style='color:#A0A0A0;padding-right:12px'>{k}</td><td>{v}</td></tr>" for k, v in rows)
        self.d_info.setText(f"<table>{html}</table>")
        self.b_fav.setText("☆  Убрать из избранного" if r.favorite else "★  В избранное")
        self.b_archive.setText("Вернуть из архива" if r.archived else "Архивировать")
        for b in (self.b_open, self.b_dup, self.b_export, self.d_edit, self.add_tag_btn):
            b.setEnabled(not r.missing)
        self.b_reveal.setEnabled(Path(r.path).exists())
        self.b_delete.setEnabled(Path(r.path).exists())
        self.tags_layout.set_tags(r.tags, None if r.missing else self._remove_tag)

    def _err(self, exc: Exception) -> None:
        log.warning("Ошибка операции: %s", exc)
        QMessageBox.warning(self, "App Design Studio", str(exc))

    def _after_change(self, select_id: str | None = None) -> None:
        self.refresh_sidebar()
        self.refresh_projects()
        if select_id:
            self.select_project(select_id)

    def _edit_meta(self) -> None:
        r = self._current()
        if not r:
            return
        title, ok = QInputDialog.getText(self, "Название проекта", "Название:", text=r.title)
        if not ok:
            return
        desc, ok = QInputDialog.getMultiLineText(self, "Описание проекта", "Описание:", r.description)
        if not ok:
            return
        try:
            self.ctx.service.update_meta(r, title=title, description=desc)
        except (ProjectError, ProjectFormatError) as exc:
            self._err(exc)
        self._after_change(r.id)

    def _add_tag(self) -> None:
        r = self._current()
        if not r:
            return
        tag, ok = QInputDialog.getText(self, "Новый тег", "Тег:")
        if ok and tag.strip():
            try:
                self.ctx.service.update_meta(r, tags=r.tags + [tag])
            except (ProjectError, ProjectFormatError) as exc:
                self._err(exc)
            self._after_change(r.id)

    def _remove_tag(self, tag: str) -> None:
        r = self._current()
        if r:
            try:
                self.ctx.service.update_meta(r, tags=[t for t in r.tags if t != tag])
            except (ProjectError, ProjectFormatError) as exc:
                self._err(exc)
            self._after_change(r.id)

    def _toggle_favorite(self) -> None:
        r = self._current()
        if r:
            self.ctx.index.set_favorite(r.id, not r.favorite)
            self._after_change(r.id)

    def _toggle_archive(self) -> None:
        r = self._current()
        if r:
            self.ctx.index.set_archived(r.id, not r.archived)
            self._after_change()

    def _duplicate(self) -> None:
        r = self._current()
        if not r:
            return
        try:
            doc, _ = self.ctx.service.duplicate(r)
        except (ProjectError, ProjectFormatError, OSError) as exc:
            self._err(exc)
            return
        self._after_change(doc.meta.id)

    def _export(self) -> None:
        r = self._current()
        if not r:
            return
        target, _ = QFileDialog.getSaveFileName(self, "Экспорт копии проекта",
                                                str(Path.home() / Path(r.path).name), PROJECT_FILTER)
        if target:
            try:
                self.ctx.service.export_copy(r, target)
            except (ProjectFormatError, OSError) as exc:
                self._err(exc)

    def _reveal(self) -> None:
        r = self._current()
        if r and Path(r.path).exists():
            if os.name == "nt":
                import subprocess
                subprocess.Popen(["explorer", "/select,", os.path.normpath(r.path)])
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(r.path).parent)))

    def _forget(self) -> None:
        r = self._current()
        if r and QMessageBox.question(self, "Убрать из списка",
                                      f"Убрать «{r.title}» из списка? Файл на диске останется.") == QMessageBox.StandardButton.Yes:
            self.ctx.index.remove(r.id)
            self._after_change()

    def _delete(self) -> None:
        r = self._current()
        if not r:
            return
        answer = QMessageBox.warning(
            self, "Удаление проекта",
            f"Переместить проект «{r.title}» в корзину Windows?\n\n{r.path}\n\nЕго можно будет восстановить из корзины.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not QFile.moveToTrash(r.path):
            self._err(Exception("Не удалось переместить файл в корзину. Файл не удалён."))
            return
        log.info("Проект перемещён в корзину: %s", r.path)
        self.ctx.index.remove(r.id)
        self._after_change()

    def _folder_choice_menu(self) -> QMenu:
        menu = QMenu(self)
        r = self._current()
        if not r:
            return menu
        none = menu.addAction("Без папки")
        none.triggered.connect(lambda: self._move_to(r, ""))
        for name in self.ctx.index.folders():
            act = menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(name == r.folder)
            act.triggered.connect(lambda _=False, n=name: self._move_to(r, n))
        menu.addSeparator()
        menu.addAction("Новая папка…").triggered.connect(lambda: self._add_folder(move=r))
        return menu

    def _move_to(self, r: ProjectRecord, folder: str) -> None:
        self.ctx.index.set_folder(r.id, folder)
        self._after_change(r.id)

    def _add_folder(self, move: ProjectRecord | None = None) -> None:
        name, ok = QInputDialog.getText(self, "Новая папка", "Название папки:")
        if ok and name.strip():
            self.ctx.index.add_folder(name)
            if isinstance(move, ProjectRecord):
                self.ctx.index.set_folder(move.id, name.strip())
            self._after_change(move.id if isinstance(move, ProjectRecord) else None)

    def _folder_menu(self, pos) -> None:
        item = self.folder_list.itemAt(pos)
        if not item:
            return
        name = item.data(ROLE_ID)
        menu = QMenu(self)
        act = menu.addAction("Удалить папку (проекты останутся)")
        if menu.exec(self.folder_list.mapToGlobal(pos)) == act:
            self.ctx.index.remove_folder(name)
            if self._folder == name:
                self._folder = None
            self._after_change()

    def _card_menu(self, pos) -> None:
        item = self.cards.itemAt(pos)
        if not item or item.data(ROLE_ID) == NEW_TILE:
            return
        r = self._current()
        if not r:
            return
        menu = QMenu(self)
        menu.addAction("Открыть").triggered.connect(lambda: self._open_record(r))
        menu.addAction(self.b_fav.text()).triggered.connect(self._toggle_favorite)
        menu.addMenu(self._folder_choice_menu()).setText("Переместить в папку")
        menu.addAction("Дублировать").triggered.connect(self._duplicate)
        menu.addAction("Экспорт копии…").triggered.connect(self._export)
        menu.addSeparator()
        menu.addAction(self.b_archive.text()).triggered.connect(self._toggle_archive)
        for a in menu.actions()[:1] + menu.actions()[3:5]:
            a.setEnabled(not r.missing)
        menu.exec(self.cards.mapToGlobal(pos))

    def open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Открыть проект", str(self.ctx.settings.projects_dir), PROJECT_FILTER)
        if path:
            self.open_requested.emit(path)

    def import_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Импорт проекта", str(Path.home()), PROJECT_FILTER)
        if not path:
            return
        dest = self.ctx.settings.projects_dir
        dest.mkdir(parents=True, exist_ok=True)
        try:
            doc, _ = self.ctx.service.import_file(path, dest)
        except (ProjectFormatError, ProjectError, OSError) as exc:
            self._err(exc)
            return
        self._after_change(doc.meta.id)


class _FlowRows(QVBoxLayout):
    """Простая раскладка тегов-чипов по строкам."""

    def __init__(self, parent: QWidget, per_row: int = 2):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.per_row = per_row

    def set_tags(self, tags: list[str], on_remove) -> None:
        while self.count():
            row = self.takeAt(0).layout()
            while row and row.count():
                w = row.takeAt(0).widget()
                if w:
                    w.deleteLater()
        if not tags:
            row = QHBoxLayout()
            row.addWidget(label("нет тегов", "Muted"))
            self.addLayout(row)
            return
        for i in range(0, len(tags), self.per_row):
            row = QHBoxLayout()
            for t in tags[i:i + self.per_row]:
                chip = QToolButton()
                chip.setText(f"{t}  ✕" if on_remove else t)
                chip.setToolTip("Удалить тег" if on_remove else "")
                chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
                if on_remove:
                    chip.clicked.connect(lambda _=False, tag=t: on_remove(tag))
                row.addWidget(chip)
            row.addStretch()
            self.addLayout(row)
