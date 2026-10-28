"""Проверка проекта и AI-экспорт для Claude Code: выбор платформы, режима и экранов, состав пакета,
редактируемое задание AI_TASK.md, сборка детерминированного архива с повторной проверкой."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QRadioButton, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from app.engines.validation.engine import SEVERITY_RU, summary, validate_project
from app.exporters.ai_export import ExportError, ExportOptions, build_package, scope_screens, slug, write_package
from app.ui.fonts import REGISTRY
from app.ui.studio.common import button
from app.ui.widgets import format_size, label, panel, pixmap_icon
from app.ui.workspace.canvas import render_thumbnail

ROLE = Qt.ItemDataRole.UserRole
MARK = {"critical": "⛔", "warning": "⚠", "info": "ℹ"}
PLATFORM_RU = {"android": "Android · Kotlin + Compose (Material 3)", "windows": "Windows · Python + PySide6 (Qt 6)"}


def run_validation(editor, screen_ids=None):
    return validate_project(editor.doc, editor.engine, REGISTRY.available, REGISTRY.missing_chars, screen_ids)


class ValidatorPage(QWidget):
    """Все замечания проекта с серьёзностью и местом; двойной щелчок ведёт к элементу."""
    goto = Signal(str, str)   # экран, элемент

    def __init__(self, ws, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.main = ws.editor
        self.issues = []
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        frame, lay = panel(margins=12)
        row = QHBoxLayout()
        row.addWidget(label("Проверка проекта", "H1"))
        row.addStretch()
        self.scope = QComboBox()
        self.scope.addItem("Весь проект", "all")
        self.scope.addItem("Текущий экран", "screen")
        self.scope.currentIndexChanged.connect(lambda _: self.refresh())
        row.addWidget(self.scope)
        self.filters = {}
        for sev in ("critical", "warning", "info"):
            cb = QCheckBox(SEVERITY_RU[sev])
            cb.setChecked(True)
            cb.toggled.connect(lambda _: self._fill())
            self.filters[sev] = cb
            row.addWidget(cb)
        row.addWidget(button("⟳ Проверить", self.refresh, "Проверить заново", "Primary"))
        lay.addLayout(row)
        self.b_contrast = button("Исправить контраст", self.fix_contrast,
                                 "Тексты с плохо читаемым цветом — тот же оттенок, светлее или темнее (WCAG AA)")
        lay.addWidget(self.b_contrast)
        self.summary = label("", "Muted", wrap=True)
        lay.addWidget(self.summary)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Место", "Замечание"])
        self.tree.setColumnWidth(0, 470)
        self.tree.setWordWrap(True)
        self.tree.itemDoubleClicked.connect(self._open)
        lay.addWidget(self.tree, 1)
        lay.addWidget(label("Критичные замечания блокируют экспорт: висячие ссылки, отсутствующие файлы ресурсов, "
                            "повреждённая структура. Двойной щелчок — перейти к элементу.", "Muted", wrap=True))
        root.addWidget(frame)

    def refresh(self) -> None:
        if self.main.doc is None:
            self.issues = []
        else:
            ids = [self.main.screen_id] if self.scope.currentData() == "screen" and self.main.screen_id else None
            self.issues = run_validation(self.main, ids)
        self._fill()

    def fix_contrast(self) -> int:
        ids = [self.main.screen_id] if self.scope.currentData() == "screen" and self.main.screen_id else None
        n = self.main.fix_contrast(ids)
        self.refresh()
        self.summary.setText(f"Цвет текста исправлен: {n}. " + self.summary.text() if n else self.summary.text())
        return n

    def _fill(self) -> None:
        self.tree.clear()
        self.b_contrast.setVisible(any(i.code == "contrast" for i in self.issues))
        c = summary(self.issues)
        self.summary.setText("✓ Замечаний нет — проект готов к экспорту" if not self.issues else
                             f"Критично: {c['critical']} · предупреждений: {c['warning']} · сведений: {c['info']}"
                             + (" — экспорт заблокирован" if c["critical"] else ""))
        groups = {}
        for i in self.issues:
            if not self.filters[i.severity].isChecked():
                continue
            if i.severity not in groups:
                g = QTreeWidgetItem([f"{MARK[i.severity]} {SEVERITY_RU[i.severity]} ({c[i.severity]})", ""])
                self.tree.addTopLevelItem(g)
                g.setExpanded(True)
                groups[i.severity] = g
            it = QTreeWidgetItem([i.location, i.message])
            it.setData(0, ROLE, (i.screen_id, i.node_id))
            it.setToolTip(1, i.message)
            groups[i.severity].addChild(it)

    def _open(self, item, _col=0) -> None:
        data = item.data(0, ROLE)
        if data and data[0]:
            self.goto.emit(*data)


class ExportPage(QWidget):
    """AI-экспорт: платформа, режим, экраны, состав, задание, сборка архива."""

    def __init__(self, ws, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.ws = ws
        self.main = ws.editor
        self.task_edited = False
        self._loading = False
        self._thumbs: dict[str, bytes] = {}
        self.last_path: Path | None = None
        self.package = None
        self.issues = []
        self._rebuild = QTimer(self)  # настройки меняются пачкой — пересобираем один раз после паузы
        self._rebuild.setSingleShot(True)
        self._rebuild.setInterval(250)
        self._rebuild.timeout.connect(self.rebuild)
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_options())
        split.addWidget(self._build_contents())
        split.addWidget(self._build_task())
        split.setSizes([330, 430, 620])
        root.addWidget(split)

    # ---------- 1–2: платформа, режим, экраны ----------
    def _build_options(self) -> QWidget:
        frame, lay = panel(margins=10)
        lay.addWidget(label("1. Платформа", "H2"))
        self.plat = {}
        for p in ("android", "windows"):
            cb = QCheckBox(PLATFORM_RU[p])
            cb.toggled.connect(lambda _: self._options_changed())
            self.plat[p] = cb
            lay.addWidget(cb)
        lay.addWidget(label("Режим", "H2"))
        self.mode = QButtonGroup(self)
        self.m_new = QRadioButton("Новое приложение по дизайну")
        self.m_update = QRadioButton("Обновить существующее приложение")
        self.m_new.setChecked(True)
        for i, b in enumerate((self.m_new, self.m_update)):
            self.mode.addButton(b, i)
            lay.addWidget(b)
        self.mode.idToggled.connect(lambda *_: self._options_changed())
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Что известно о существующем проекте: репозиторий, модули, что нельзя "
                                      "ломать… (войдёт в задание)")
        self.notes.setFixedHeight(80)
        self.notes.textChanged.connect(self._options_changed)
        lay.addWidget(self.notes)
        lay.addWidget(label("Состав пакета", "H2"))
        self.inc = {}
        for key, text in (("include_interactions", "Логика и навигация"), ("include_animations", "Анимации"),
                          ("include_assets", "Ресурсы (иконки, шрифты, изображения)"),
                          ("include_previews", "Превью экранов (PNG)"),
                          ("include_android_project", "Проект Android Studio (Kotlin + Compose)")):
            cb = QCheckBox(text)
            cb.setChecked(True)
            cb.toggled.connect(lambda _: self._options_changed())
            self.inc[key] = cb
            lay.addWidget(cb)
        lay.addWidget(label("2. Экраны", "H2"))
        self.screens = QListWidget()
        self.screens.itemChanged.connect(lambda _: self._options_changed())
        lay.addWidget(self.screens, 1)
        self.screens_info = label("", "Muted")
        lay.addWidget(self.screens_info)
        return frame

    # ---------- 3: структура и ресурсы ----------
    def _build_contents(self) -> QWidget:
        frame, lay = panel(margins=10)
        lay.addWidget(label("3. Структура пакета", "H2"))
        self.files = QTreeWidget()
        self.files.setHeaderLabels(["Файл", "Размер"])
        hdr = self.files.header()  # имя файла занимает свободное место, размер — по содержимому
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, hdr.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, hdr.ResizeMode.ResizeToContents)
        lay.addWidget(self.files, 3)
        lay.addWidget(label("Ресурсы и лицензии", "H2"))
        self.assets = QListWidget()
        self.assets.setWordWrap(True)
        lay.addWidget(self.assets, 2)
        lay.addWidget(label("Промпты для ИИ", "H2"))
        self.prompts = QListWidget()
        self.prompts.setWordWrap(True)
        self.prompts.setToolTip("Отмеченные промпты войдут в AI_TASK.md и в папку prompts/ пакета")
        self.prompts.itemChanged.connect(lambda _: self._options_changed())
        self.prompts.itemDoubleClicked.connect(lambda _: self.edit_prompt())
        lay.addWidget(self.prompts, 2)
        from app.ui.widgets import FlowLayout
        row_w = QWidget()
        row = FlowLayout(row_w, spacing=4)
        for text, slot, tip in (("+ Свой…", self.new_prompt, "Новый промпт в личную библиотеку"),
                                ("Изменить…", self.edit_prompt, "Изменить свой промпт или сделать копию встроенного"),
                                ("Удалить", self.delete_prompt, "Удалить свой промпт"),
                                ("Вставить в задание", self.insert_prompt, "Вставить текст в AI_TASK.md у курсора")):
            row.addWidget(button(text, slot, tip))
        lay.addWidget(row_w)
        lay.addWidget(label("Проверка", "H2"))
        self.check_info = label("", "Muted", wrap=True)
        lay.addWidget(self.check_info)
        self.b_issues = button("Открыть проверку проекта", lambda: self.window().show_validator()
                               if hasattr(self.window(), "show_validator") else None)
        lay.addWidget(self.b_issues)
        return frame

    # ---------- 4–5: задание и сборка ----------
    def _build_task(self) -> QWidget:
        frame, lay = panel(margins=10)
        row = QHBoxLayout()
        row.addWidget(label("4. AI_TASK.md", "H2"), 1)
        row.addWidget(button("Сгенерировать заново", self.regenerate_task, "Черновик по текущим настройкам"))
        row.addWidget(button("Копировать", self.copy_task, "Скопировать задание в буфер обмена"))
        lay.addLayout(row)
        self.task = QPlainTextEdit()
        self.task.textChanged.connect(self._task_changed)
        lay.addWidget(self.task, 1)
        self.task_info = label("", "Muted")
        lay.addWidget(self.task_info)
        lay.addWidget(label("5. Сборка", "H2"))
        row = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Имя архива")
        row.addWidget(self.name, 1)
        row.addWidget(label(".zip", "Muted"))
        lay.addLayout(row)
        row = QHBoxLayout()
        self.folder = QLineEdit()
        row.addWidget(self.folder, 1)
        row.addWidget(button("…", self.choose_folder, "Выбрать папку"))
        lay.addLayout(row)
        self.b_export = button("Собрать пакет", self.export, "Проверить проект, собрать и проверить архив", "Primary")
        lay.addWidget(self.b_export)
        row = QHBoxLayout()
        self.b_android = button("Проект Android…", self.save_android,
                                "Сохранить проект Android Studio, чтобы открыть его сразу")
        self.b_apk = button("Тестовый APK", self.build_apk,
                            "Собрать отладочный APK на этом компьютере (Android SDK, JDK и Gradle из Android Studio)")
        self.b_play = button("Google Play (AAB)…", self.build_release,
                             "Подписанный пакет AAB для загрузки в Google Play и подписанный APK")
        self.b_windows = button("Приложение Windows…", self.save_windows,
                                "Экраны Windows — готовое приложение на Python + PySide6 (запуск: python main.py)")
        row.addWidget(self.b_android)
        row.addWidget(self.b_apk)
        row.addWidget(self.b_play)
        row.addWidget(self.b_windows)
        lay.addLayout(row)
        self.steps = label("", "Muted", wrap=True)
        lay.addWidget(self.steps)
        return frame

    # ---------- данные ----------
    def options(self) -> ExportOptions:
        ids = [self.screens.item(i).data(ROLE) for i in range(self.screens.count())
               if self.screens.item(i).checkState() == Qt.CheckState.Checked]
        o = ExportOptions(mode="update" if self.m_update.isChecked() else "new",
                          platforms=[p for p, cb in self.plat.items() if cb.isChecked() and cb.isEnabled()],
                          screen_ids=ids, existing_notes=self.notes.toPlainText(),
                          **{k: cb.isChecked() for k, cb in self.inc.items()})
        o.prompts = [(p.name, p.text) for p in self._checked_prompts()]
        if self.task_edited:
            o.task_text = self.task.toPlainText()
        return o

    def refresh(self) -> None:
        """Страница открыта: заполнить экраны и платформы проекта, обновить черновик."""
        doc = self.main.doc
        if doc is None:
            return
        self._loading = True
        prev = {self.screens.item(i).data(ROLE): self.screens.item(i).checkState()
                for i in range(self.screens.count())}
        fresh = getattr(self, "_doc_id", None) != doc.meta.id  # другой проект — настройки по умолчанию
        self._doc_id = doc.meta.id
        if fresh:
            self.task_edited = False
            self.name.clear()
        for p, cb in self.plat.items():
            has = p in doc.meta.platforms
            cb.setEnabled(has)
            cb.setChecked(has and (fresh or cb.isChecked()))
        self.screens.clear()
        for s in doc.screens:
            it = QListWidgetItem(f"{s.name}\n{'Android' if s.platform == 'android' else 'Windows'} · "
                                 f"{s.width} × {s.height}")
            it.setIcon(pixmap_icon(render_thumbnail(s, self.main.artboard_color(), 48, 64, doc)))
            it.setData(ROLE, s.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(prev.get(s.id, Qt.CheckState.Checked))
            self.screens.addItem(it)
        if not self.name.text().strip():
            self.name.setText(f"{slug(doc.meta.title, 'design')}_ai_package")
        if not self.folder.text().strip():
            self.folder.setText(self.ws.ctx.settings.get("export/folder") or
                                str(self.ws.ctx.settings.projects_dir / "Экспорт"))
        self.inc["include_previews"].setChecked(self.ws.ctx.settings.get("export/include_previews"))
        self.refresh_prompts()
        self._loading = False
        self.rebuild()

    def _options_changed(self) -> None:
        if not self._loading and self.main.doc is not None:
            self._rebuild.start()

    def rebuild(self) -> None:
        """Пересчитать проверку, состав пакета и черновик задания по текущим настройкам."""
        self._rebuild.stop()
        if self.main.doc is None:
            return
        self.notes.setEnabled(self.m_update.isChecked())
        o = self.options()
        platforms = {s.id: s.platform for s in self.main.doc.screens}
        self._loading = True
        for i in range(self.screens.count()):  # экраны невыбранной платформы не экспортируются
            it = self.screens.item(i)
            it.setForeground(self.palette().text() if platforms.get(it.data(ROLE)) in o.platforms
                             else self.palette().mid())
        self._loading = False
        chosen = scope_screens(self.main.doc, o)
        self.screens_info.setText(f"Выбрано экранов: {len(chosen)} из {len(self.main.doc.screens)}")
        self.issues = run_validation(self.main, [s.id for s in chosen]) if chosen else []
        c = summary(self.issues)
        self.check_info.setText(("✓ Замечаний нет" if not self.issues else
                                 f"Критично: {c['critical']} · предупреждений: {c['warning']} · сведений: {c['info']}")
                                + ("\n⛔ Экспорт заблокирован — исправьте критичные замечания" if c["critical"] else ""))
        self.b_export.setEnabled(bool(chosen) and not c["critical"])
        has_android = any(s.platform == "android" for s in chosen) and o.include_android_project
        for b in (self.b_android, self.b_apk):
            b.setEnabled(has_android and not c["critical"])
        self.b_export.setToolTip("" if self.b_export.isEnabled() else
                                 "Нет экранов или есть критичные замечания проверки")
        try:
            # превью рисуются только при сборке; здесь — их места в пакете
            pkg = build_package(self.main.doc, o, self.issues, {s.id: b"" for s in chosen}
                                if o.include_previews else None)
        except ExportError as exc:
            self.files.clear()
            self.assets.clear()
            self.task_info.setText(str(exc))
            return
        self.package = pkg
        self._fill_files(pkg)
        self._fill_assets(pkg)
        if not self.task_edited:
            self._loading = True
            self.task.setPlainText(pkg.task)
            self._loading = False
        self._task_info()

    def _previews(self, screens) -> dict[str, bytes]:
        out = {}
        for s in screens:
            pm = render_thumbnail(s, self.main.artboard_color(), 360, 720 if s.height > s.width else 300,
                                  self.main.doc, bg="#000000")
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            pm.save(buf, "PNG")
            out[s.id] = bytes(ba.data())
        return out

    def _fill_files(self, pkg) -> None:
        self.files.clear()
        dirs: dict[str, QTreeWidgetItem] = {}
        for path, data in pkg.files.items():
            parts = path.split("/")
            parent = None
            for i, part in enumerate(parts[:-1]):
                key = "/".join(parts[:i + 1])
                if key not in dirs:
                    node = QTreeWidgetItem([part + "/", ""])
                    (parent.addChild(node) if parent else self.files.addTopLevelItem(node))
                    node.setExpanded(part in ("screens", "assets"))
                    dirs[key] = node
                parent = dirs[key]
            leaf = QTreeWidgetItem([parts[-1], format_size(len(data)) if data else "при сборке"])
            (parent.addChild(leaf) if parent else self.files.addTopLevelItem(leaf))
        for key, node in dirs.items():
            node.setText(1, f"{node.childCount()}")

    def _fill_assets(self, pkg) -> None:
        self.assets.clear()
        for a in pkg.manifest["assets"]:
            lic = a["license"] or "лицензия не указана"
            state = "✓ в пакете" if a["included"] else f"— не включён: {a.get('reason', '')}"
            mark = "⚠ " if a["redistribution"] == "unknown" else ""
            self.assets.addItem(f"{mark}{a['name']} ({a['kind']}) · {lic} · {state}")
        if not pkg.manifest["assets"]:
            self.assets.addItem("Ресурсов в проекте нет")

    def _task_changed(self) -> None:
        if not self._loading:
            self.task_edited = True
            self._task_info()

    def _task_info(self) -> None:
        self.task_info.setText(f"{len(self.task.toPlainText())} символов" +
                               (" · изменено вручную — настройки больше не меняют текст" if self.task_edited else
                                " · черновик по настройкам"))

    def regenerate_task(self) -> None:
        self.task_edited = False
        self.rebuild()

    def copy_task(self) -> None:
        QGuiApplication.clipboard().setText(self.task.toPlainText())
        self.task_info.setText("Задание скопировано в буфер обмена")

    # ---------- промпты ----------
    def prompt_store(self):
        from app.exporters.prompts import PromptStore
        return PromptStore(self.ws.ctx.paths.prompts)

    def refresh_prompts(self, select: str | None = None) -> None:
        checked = {p.id for p in self._checked_prompts()}
        loading, self._loading = self._loading, True
        self.prompts.clear()
        for p in self.prompt_store().items():
            it = QListWidgetItem(f"{'◆' if p.builtin else '✎'} {p.name}  ·  {p.category}")
            it.setToolTip(p.text)
            it.setData(ROLE, p.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if p.id in checked else Qt.CheckState.Unchecked)
            self.prompts.addItem(it)
            if p.id == select:
                self.prompts.setCurrentItem(it)
        self._loading = loading

    def _checked_prompts(self):
        store = self.prompt_store()
        ids = [self.prompts.item(i).data(ROLE) for i in range(self.prompts.count())
               if self.prompts.item(i).checkState() == Qt.CheckState.Checked]
        return [p for p in (store.get(i) for i in ids) if p is not None]

    def _current_prompt(self):
        it = self.prompts.currentItem()
        return self.prompt_store().get(it.data(ROLE)) if it else None

    def new_prompt(self) -> None:
        self._edit(None)

    def edit_prompt(self) -> None:
        p = self._current_prompt()
        if p is not None:
            self._edit(p)

    def _edit(self, p) -> None:
        from app.ui.studio.export_tools import PromptDialog
        dlg = PromptDialog(p, self)
        if dlg.exec() == PromptDialog.DialogCode.Accepted:
            self.save_prompt(dlg.prompt)

    def save_prompt(self, prompt):
        saved = self.prompt_store().save(prompt)
        self.refresh_prompts(select=saved.id)
        it = self.prompts.currentItem()
        if it is not None:
            it.setCheckState(Qt.CheckState.Checked)
        return saved

    def delete_prompt(self) -> None:
        p = self._current_prompt()
        if p is None:
            return
        if p.builtin:
            QMessageBox.information(self, "Промпты", "Встроенный промпт удалить нельзя — его можно не отмечать.")
            return
        if QMessageBox.question(self, "Промпты", f"Удалить свой промпт «{p.name}»?") == QMessageBox.StandardButton.Yes:
            self.prompt_store().delete(p.id)
            self.refresh_prompts()
            self._options_changed()

    def insert_prompt(self) -> None:
        p = self._current_prompt()
        if p is not None:
            self.task.insertPlainText(f"\n## {p.name}\n\n{p.text.strip()}\n")
            self.task.setFocus()

    # ---------- Android ----------
    def _android_files(self):
        o = self.options()
        o.include_previews = False
        from app.exporters.glance import is_widget  # снимки виджетов — картинка предпросмотра в списке виджетов
        from app.ui.workspace.render_export import widget_previews
        widgets = [s for s in self.main.doc.screens if is_widget(s) and (o.screen_ids is None or s.id in o.screen_ids)]
        return build_package(self.main.doc, o, self.issues, widget_previews(self.main.doc, widgets)).files

    def save_android(self, folder: str | None = None) -> Path | None:
        from app.exporters.apk_builder import find_toolchain, write_project
        if self.main.doc is None:
            return None
        if not folder:
            folder = QFileDialog.getExistingDirectory(self, "Папка для Android-проекта", self.folder.text())
            if not folder:
                return None
        target = Path(folder) / f"{slug(self.main.doc.meta.title, 'app')}_android"
        if target.exists() and any(target.iterdir()) and QMessageBox.question(
                self, "Android-проект", f"Папка {target} не пуста. Перезаписать файлы проекта? Ваши другие "
                                       "файлы в ней не удаляются.") != QMessageBox.StandardButton.Yes:
            return None
        write_project(self._android_files(), target, find_toolchain().sdk)
        self.steps.setText(f"✓ Android-проект сохранён: {target}\nОткройте папку в Android Studio (File → Open).")
        return target

    def save_windows(self, folder: str | None = None) -> Path | None:
        """Экраны Windows → папка приложения PySide6 (ui.json, среда выполнения, main.py, картинки)."""
        from app.exporters import windows_app
        if self.main.doc is None:
            return None
        import shutil
        doc, o = self.main.doc, self.options()
        everything = [s for s in doc.screens if s.platform == "windows"]
        screens = [s for s in everything if o.screen_ids is None or s.id in o.screen_ids]
        if not screens:
            QMessageBox.information(self, "Приложение Windows", (
                "Отметьте экраны Windows в списке экранов." if everything else
                "В проекте нет экранов Windows — добавьте экран для окна Windows («+ Экран → Пустой экран для "
                "другого устройства…»)."))
            return None
        if not folder:
            folder = QFileDialog.getExistingDirectory(self, "Папка для приложения Windows", self.folder.text())
            if not folder:
                return None
        target = Path(folder) / f"{slug(doc.meta.title, 'app')}_windows"
        if target.exists() and any(target.iterdir()) and QMessageBox.question(
                self, "Приложение Windows", f"Папка {target} не пуста. Перезаписать файлы приложения? Ваши другие "
                                           "файлы в ней не удаляются.") != QMessageBox.StandardButton.Yes:
            return None
        prefix = windows_app.ROOT + "/"
        try:
            shutil.rmtree(target / "assets", ignore_errors=True)  # картинки прошлой выгрузки не остаются
            for path, data in windows_app.files(doc, screens).items():
                out = (target / path[len(prefix):]).resolve()
                if target.resolve() not in out.parents:
                    raise ValueError(f"небезопасный путь: {path}")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Приложение Windows", f"Не удалось сохранить приложение: {exc}")
            return None
        skipped = windows_app.skipped_triggers(doc, screens)
        note = (f"\nВ приложение попали нажатия и открытие экранов; правил с другими событиями (двойное нажатие, "
                f"удержание, наведение): {skipped} — они работают только в прототипе.") if skipped else ""
        self.steps.setText(f"✓ Приложение Windows сохранено: {target}\nЗапуск: pip install -r requirements.txt, "
                           f"затем python main.py (нужен Python 3.10+).{note}")
        return target

    def build_apk(self):
        """Тестовый APK: проект в служебной папке программы → Gradle assembleDebug."""
        import shutil

        from app.exporters.apk_builder import find_toolchain, write_project
        from app.ui.studio.export_tools import ApkBuildDialog
        if self.main.doc is None:
            return None
        t = find_toolchain()
        if not t.ok:
            QMessageBox.warning(self, "Сборка APK", "Не хватает инструментов: " + t.describe() +
                                ".\n\nПроект можно сохранить кнопкой «Проект Android…» и собрать в "
                                "Android Studio.")
            return None
        project = self.ws.ctx.paths.base / "apk_build" / self.main.doc.meta.id
        if project.exists():  # служебная папка программы: исходники пересоздаются целиком
            shutil.rmtree(project / "app" / "src", ignore_errors=True)
        write_project(self._android_files(), project, t.sdk)
        dlg = ApkBuildDialog(t, project, self)
        dlg.show()
        dlg.start()
        self.apk_dialog = dlg
        return dlg

    def build_release(self, version_name: str | None = None):
        """Сборка для Google Play: ключ загрузки (создаётся один раз), номер версии растёт, Gradle bundleRelease."""
        import shutil

        from PySide6.QtWidgets import QInputDialog

        from app.exporters.android_project import package_name
        from app.exporters.apk_builder import find_toolchain, prepare_release, signing_key, write_project
        from app.ui.studio.export_tools import ApkBuildDialog
        if self.main.doc is None:
            return None
        t = find_toolchain()
        if not t.ok:
            QMessageBox.warning(self, "Сборка для Google Play", "Не хватает инструментов: " + t.describe())
            return None
        if version_name is None:
            version_name, ok = QInputDialog.getText(self, "Сборка для Google Play",
                                                    "Версия для пользователей (например 1.0 или 1.2.3):", text="1.0")
            if not ok or not version_name.strip():
                return None
        pkg = package_name(self.main.doc.meta.title)
        keys = self.ws.ctx.paths.base / "keys"
        try:
            key = signing_key(t, keys, pkg)
        except (RuntimeError, OSError) as e:
            QMessageBox.warning(self, "Сборка для Google Play", f"Ключ подписи не создан: {e}")
            return None
        project = self.ws.ctx.paths.base / "apk_build" / self.main.doc.meta.id
        if project.exists():
            shutil.rmtree(project / "app" / "src", ignore_errors=True)
        write_project(self._android_files(), project, t.sdk)
        code = prepare_release(project, key, keys, pkg, version_name.strip())
        note = (f"Версия {version_name.strip()} (номер сборки {code}). Ключ подписи: {key.store} — "
                "сохраните копию папки с ключом: без него обновить приложение в Google Play будет нельзя.")
        dlg = ApkBuildDialog(t, project, self, release=True, note=note)
        dlg.show()
        dlg.start()
        self.apk_dialog = dlg
        return dlg

    def select_screens(self, screen_ids: list[str]) -> None:
        self._loading = True
        for i in range(self.screens.count()):
            it = self.screens.item(i)
            it.setCheckState(Qt.CheckState.Checked if it.data(ROLE) in screen_ids else Qt.CheckState.Unchecked)
        self._loading = False
        self.rebuild()

    def focus_task(self) -> None:
        self.task.setFocus()

    def choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Папка для пакета", self.folder.text())
        if d:
            self.folder.setText(d)
            self.ws.ctx.settings.set("export/folder", d)

    def target_path(self) -> Path:
        name = slug(self.name.text().strip() or "design_package", "design_package")
        return Path(self.folder.text().strip() or ".") / f"{name}.zip"

    def export(self, confirm_overwrite: bool = True) -> Path | None:
        """Проверка → сборка → запись архива → повторная проверка архива."""
        if self.main.doc is None:
            return None
        o = self.options()
        chosen = scope_screens(self.main.doc, o)
        steps = []
        self.issues = run_validation(self.main, [s.id for s in chosen]) if chosen else []
        crit = [i for i in self.issues if i.severity == "critical"]
        if crit or not chosen:
            text = "\n".join(f"• {i.location}: {i.message}" for i in crit[:12]) or "Не выбрано ни одного экрана"
            QMessageBox.warning(self, "Экспорт заблокирован", f"Исправьте критичные замечания:\n\n{text}")
            self.steps.setText("⛔ Проверка проекта: есть критичные замечания")
            return None
        steps.append(f"✓ Проверка проекта (предупреждений: {summary(self.issues)['warning']})")
        path = self.target_path()
        if confirm_overwrite and path.exists() and QMessageBox.question(
                self, "Экспорт", f"Файл {path.name} уже есть. Заменить?") != QMessageBox.StandardButton.Yes:
            return None
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            pkg = build_package(self.main.doc, o, self.issues, self._previews(chosen) if o.include_previews else None)
            steps.append(f"✓ Ресурсы: в пакете {sum(1 for a in pkg.manifest['assets'] if a['included'])}, "
                         f"исключено {sum(1 for a in pkg.manifest['assets'] if not a['included'])}")
            steps.append(f"✓ Задание: {len(pkg.task)} символов")
            write_package(pkg, path)
        except (ExportError, OSError) as exc:
            QMessageBox.warning(self, "Экспорт не выполнен", str(exc))
            self.steps.setText("\n".join(steps + [f"⛔ {exc}"]))
            return None
        finally:
            QApplication.restoreOverrideCursor()
        steps.append(f"✓ Архив записан и проверен повторным чтением: {path} ({format_size(path.stat().st_size)})")
        self.steps.setText("\n".join(steps))
        self.last_path = path
        self.ws.ctx.settings.set("export/include_previews", o.include_previews)
        return path


__all__ = ["ExportPage", "ValidatorPage", "run_validation"]
