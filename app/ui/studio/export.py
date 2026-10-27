"""Проверка проекта и AI-экспорт для Claude Code: выбор платформы, режима и экранов, состав пакета,
редактируемое задание AI_TASK.md, сборка детерминированного архива с повторной проверкой."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, Signal
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

    def _fill(self) -> None:
        self.tree.clear()
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
                          ("include_previews", "Превью экранов (PNG)")):
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
        self.files.setColumnWidth(0, 290)
        lay.addWidget(self.files, 3)
        lay.addWidget(label("Ресурсы и лицензии", "H2"))
        self.assets = QListWidget()
        self.assets.setWordWrap(True)
        lay.addWidget(self.assets, 2)
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
        row.addWidget(label("4. Задание для Claude Code (AI_TASK.md)", "H2"), 1)
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
        self._loading = False
        self._options_changed()

    def _options_changed(self) -> None:
        if self._loading or self.main.doc is None:
            return
        self.notes.setEnabled(self.m_update.isChecked())
        o = self.options()
        for i in range(self.screens.count()):  # экраны невыбранной платформы не экспортируются
            it = self.screens.item(i)
            s = next(x for x in self.main.doc.screens if x.id == it.data(ROLE))
            it.setForeground(self.palette().text() if s.platform in o.platforms else self.palette().mid())
        chosen = scope_screens(self.main.doc, o)
        self.screens_info.setText(f"Выбрано экранов: {len(chosen)} из {len(self.main.doc.screens)}")
        self.issues = run_validation(self.main, [s.id for s in chosen]) if chosen else []
        c = summary(self.issues)
        self.check_info.setText(("✓ Замечаний нет" if not self.issues else
                                 f"Критично: {c['critical']} · предупреждений: {c['warning']} · сведений: {c['info']}")
                                + ("\n⛔ Экспорт заблокирован — исправьте критичные замечания" if c["critical"] else ""))
        self.b_export.setEnabled(bool(chosen) and not c["critical"])
        self.b_export.setToolTip("" if self.b_export.isEnabled() else
                                 "Нет экранов или есть критичные замечания проверки")
        try:
            pkg = build_package(self.main.doc, o, self.issues, self._previews(chosen) if o.include_previews else None)
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
            leaf = QTreeWidgetItem([parts[-1], format_size(len(data))])
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
        self._options_changed()

    def copy_task(self) -> None:
        QGuiApplication.clipboard().setText(self.task.toPlainText())
        self.task_info.setText("Задание скопировано в буфер обмена")

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
