"""Мастер нового проекта: 6 шагов по макету 12."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QRadioButton, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from app.core.document.model import PLATFORM_ANDROID, PLATFORM_WINDOWS, Appearance
from app.core.persistence.container import EXTENSION, CONTENT_DIRS
from app.core.project.service import NewProjectSpec, ProjectError, validate_file_name
from app.libraries.catalog import DEVICES, TEMPLATES, template, templates_for
from app.ui.widgets import label, panel, pixmap_icon, platforms_text, thumbnail

STEPS = [("Платформа", "Выбор платформы"), ("Шаблон", "Готовые решения"), ("Оформление", "Тема, цвет, шрифт"),
         ("Устройства", "Экраны и ориентация"), ("Структура", "Содержимое проекта"), ("Готово", "Название и место")]

PLATFORM_CHOICES = [
    ((PLATFORM_ANDROID,), "Android", "Kotlin + Jetpack Compose"),
    ((PLATFORM_WINDOWS,), "Windows", "Python + PySide6"),
    ((PLATFORM_ANDROID, PLATFORM_WINDOWS), "Android + Windows", "Единый проект"),
]
THEMES = [("amoled", "AMOLED"), ("dark", "Тёмная"), ("gray", "Серая"), ("light", "Светлая")]
ACCENTS = ["#2F7BFF", "#1E5BD8", "#7C4DFF", "#B04DFF", "#FF3D8B", "#FF4D4D", "#FF8A00", "#F5C400", "#22C55E", "#12A37F"]
DENSITIES = [("comfortable", "Удобная"), ("compact", "Компактная")]
STRUCTURE_INFO = {
    "screens": "Экраны", "components": "Компоненты интерфейса", "styles": "Темы и стили",
    "animations": "Анимации и переходы", "interactions": "Логика взаимодействий", "assets": "Изображения, SVG, шрифты",
}


class NewProjectWizard(QDialog):
    def __init__(self, default_location: Path, template_id: str = "", parent: QWidget | None = None,
                 user_templates: list | None = None):
        super().__init__(parent)
        self.setWindowTitle("Создание нового проекта")
        self.resize(960, 640)
        self.result_spec: NewProjectSpec | None = None
        self.open_after = True
        self._platforms: tuple[str, ...] = (PLATFORM_ANDROID,)
        self._template_id = template_id
        # пользовательские шаблоны: id вида «user:<id>» → UserTemplate (копия сохранённого проекта)
        self._user = {f"user:{t.id}": t for t in user_templates or []}

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.addWidget(label("Создание нового проекта", "H1"))
        root.addWidget(label("Пошаговый мастер. Все данные хранятся локально.", "Muted"))

        self.step_buttons: list[QToolButton] = []
        steps = QHBoxLayout()
        for i, (name, sub) in enumerate(STEPS):
            b = QToolButton()
            b.setText(f"{i + 1}  {name}\n{sub}")
            b.setCheckable(True)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            b.clicked.connect(lambda _=False, n=i: self.go(n))
            self.step_buttons.append(b)
            steps.addWidget(b, 1)
        root.addLayout(steps)

        self.pages = QStackedWidget()
        for build in (self._page_platform, self._page_template, self._page_appearance, self._page_devices,
                      self._page_structure, self._page_name):
            self.pages.addWidget(build())
        root.addWidget(self.pages, 1)

        self.error = label("", "Error", wrap=True)
        root.addWidget(self.error)
        nav = QHBoxLayout()
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        nav.addWidget(cancel)
        nav.addStretch()
        self.back_btn = QPushButton("← Назад")
        self.back_btn.clicked.connect(lambda: self.go(self.pages.currentIndex() - 1))
        self.next_btn = QPushButton("Далее →")
        self.next_btn.setObjectName("Primary")
        self.next_btn.clicked.connect(self._next)
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        root.addLayout(nav)

        self.location.setText(str(default_location))
        if template_id in self._user:
            plats = tuple(self._user[template_id].platforms)
            idx = next((i for i, c in enumerate(PLATFORM_CHOICES) if set(c[0]) == set(plats)), 0)
            self.platform_group.button(idx).setChecked(True)
            self._platforms = PLATFORM_CHOICES[idx][0]
            self._sync_devices(reset=True)
        elif template_id:
            self._apply_template(template(template_id))
        self.go(0)

    # ---------- шаги ----------
    def _page_platform(self) -> QWidget:
        w, lay = panel()
        lay.addWidget(label("1. Выбор платформы", "H2"))
        lay.addWidget(label("Выберите целевую платформу или обе сразу", "Muted"))
        row = QHBoxLayout()
        self.platform_group = QButtonGroup(self)
        for i, (plats, name, sub) in enumerate(PLATFORM_CHOICES):
            b = QToolButton()
            b.setCheckable(True)
            b.setIcon(pixmap_icon(thumbnail(list(plats), name, 160, 96)))
            b.setIconSize(thumbnail(list(plats), name, 160, 96).size())
            b.setText(f"{name}\n{sub}")
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setMinimumSize(200, 170)
            self.platform_group.addButton(b, i)
            row.addWidget(b)
        self.platform_group.button(0).setChecked(True)
        self.platform_group.idClicked.connect(self._on_platform)
        row.addStretch()
        lay.addLayout(row)
        lay.addSpacing(12)
        lay.addWidget(label("Тип проекта", "H2"))
        self.type_ui = QRadioButton("UI-дизайн — интерфейс, экраны и ресурсы")
        self.type_ui.setChecked(True)
        lay.addWidget(self.type_ui)
        full = QRadioButton("Полный проект с кодом — недоступно: программа не генерирует приложения, "
                            "только пакет задания для Claude Code (AI-экспорт)")
        full.setEnabled(False)
        lay.addWidget(full)
        imp = QRadioButton("Импорт дизайна из Figma / изображений — не входит в v1.0")
        imp.setEnabled(False)
        lay.addWidget(imp)
        lay.addStretch()
        return w

    def _page_template(self) -> QWidget:
        w, lay = panel()
        lay.addWidget(label("2. Выбор шаблона", "H2"))
        lay.addWidget(label("Пустой проект или «Мой шаблон» — проект, сохранённый как шаблон "
                            "(Проект → Сохранить как шаблон).", "Muted"))
        self.template_list = QListWidget()
        self.template_list.setObjectName("Cards")
        self.template_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.template_list.setIconSize(thumbnail([], "", 200, 120).size())
        self.template_list.setMovement(QListWidget.Movement.Static)
        self.template_list.setSpacing(8)
        self.template_list.currentItemChanged.connect(self._on_template)
        lay.addWidget(self.template_list, 1)
        return w

    def _page_appearance(self) -> QWidget:
        w, lay = panel()
        lay.addWidget(label("3. Оформление проекта", "H2"))
        lay.addWidget(label("Это настройки дизайна вашего приложения, а не интерфейса App Design Studio.", "Muted"))
        form = QFormLayout()
        form.setHorizontalSpacing(24)
        self.theme_combo = QComboBox()
        for key, text in THEMES:
            self.theme_combo.addItem(text, key)
        form.addRow("Тема", self.theme_combo)
        accent_row = QHBoxLayout()
        self.accent_group = QButtonGroup(self)
        for i, color in enumerate(ACCENTS):
            b = QToolButton()
            b.setCheckable(True)
            b.setFixedSize(30, 24)
            b.setToolTip(color)
            b.setAccessibleName(f"Акцентный цвет {color}")
            b.setStyleSheet(f"QToolButton{{background:{color};border:2px solid #000;border-radius:6px}}"
                            f"QToolButton:checked{{border:2px solid #FFFFFF}}"
                            f"QToolButton:focus{{border:2px solid #A0A0A0}}")
            self.accent_group.addButton(b, i)
            accent_row.addWidget(b)
        self.accent_group.button(0).setChecked(True)
        accent_row.addStretch()
        form.addRow("Акцентный цвет", accent_row)
        self.font_combo = QComboBox()
        self.font_combo.setEditable(False)
        families = sorted(set(QFontDatabase.families()), key=str.casefold)
        self.font_combo.addItems(families)
        idx = self.font_combo.findText("Segoe UI")
        self.font_combo.setCurrentIndex(max(0, idx))
        form.addRow("Основной шрифт (системный)", self.font_combo)
        self.radius_combo = QComboBox()
        for r in (0, 4, 8, 12, 16, 24):
            self.radius_combo.addItem(f"{r} dp", r)
        self.radius_combo.setCurrentIndex(3)
        form.addRow("Радиус скругления", self.radius_combo)
        self.density_combo = QComboBox()
        for key, text in DENSITIES:
            self.density_combo.addItem(text, key)
        form.addRow("Плотность элементов", self.density_combo)
        lay.addLayout(form)
        lay.addWidget(label("Собственные шрифты TTF/OTF импортируются в студии «Шрифты» после создания проекта.", "Muted"))
        lay.addStretch()
        return w

    def _page_devices(self) -> QWidget:
        w, lay = panel()
        lay.addWidget(label("4. Устройства и экраны", "H2"))
        lay.addWidget(label("Для каждого выбранного устройства будет создан стартовый экран.", "Muted"))
        self.device_grid = QGridLayout()
        self.device_checks: dict[str, QCheckBox] = {}
        for i, d in enumerate(DEVICES):
            cb = QCheckBox(f"{d.name} — {d.width} × {d.height}, {d.dpi} dpi")
            cb.setProperty("platform", d.platform)
            self.device_checks[d.id] = cb
            self.device_grid.addWidget(cb, i, 0)
        lay.addLayout(self.device_grid)
        lay.addSpacing(8)
        lay.addWidget(label("Ориентация (телефоны и планшеты)", "H2"))
        orow = QHBoxLayout()
        self.portrait = QRadioButton("Портрет")
        self.portrait.setChecked(True)
        self.landscape = QRadioButton("Ландшафт")
        orow.addWidget(self.portrait)
        orow.addWidget(self.landscape)
        orow.addStretch()
        lay.addLayout(orow)
        self.safe_areas = QCheckBox("Учитывать безопасные области (статус-бар, навигация, вырез)")
        self.safe_areas.setChecked(True)
        lay.addWidget(self.safe_areas)
        lay.addWidget(label("Другие устройства, плотность и ориентация проверяются на странице «Просмотр» (F5).", "Muted"))
        lay.addStretch()
        return w

    def _page_structure(self) -> QWidget:
        w, lay = panel()
        lay.addWidget(label("5. Структура проекта", "H2"))
        lay.addWidget(label(f"Файл {EXTENSION} всегда содержит эти разделы — они нужны для экспорта в Claude Code.",
                            "Muted", wrap=True))
        for d in CONTENT_DIRS:
            lay.addWidget(label(f"▢  {d}/  —  {STRUCTURE_INFO[d]}"))
        lay.addSpacing(8)
        lay.addWidget(label("README.md, AI_TASK.md и структура для Claude Code формируются при AI-экспорте (Ctrl+E).",
                            "Muted", wrap=True))
        lay.addStretch()
        return w

    def _page_name(self) -> QWidget:
        w, lay = panel()
        lay.addWidget(label("6. Название и расположение", "H2"))
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Например: Мой мессенджер")
        self.name_edit.textChanged.connect(self._update_summary)
        form.addRow("Название проекта", self.name_edit)
        self.desc_edit = QLineEdit()
        form.addRow("Описание", self.desc_edit)
        loc_row = QHBoxLayout()
        self.location = QLineEdit()
        self.location.textChanged.connect(self._update_summary)
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self._browse)
        loc_row.addWidget(self.location, 1)
        loc_row.addWidget(browse)
        form.addRow("Расположение", loc_row)
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("через запятую")
        form.addRow("Теги", self.tags_edit)
        lay.addLayout(form)
        self.open_after_cb = QCheckBox("Открыть проект после создания")
        self.open_after_cb.setChecked(True)
        lay.addWidget(self.open_after_cb)
        lay.addSpacing(8)
        self.summary = label("", "Muted", wrap=True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.summary)
        lay.addStretch()
        return w

    # ---------- логика ----------
    def go(self, n: int) -> None:
        n = max(0, min(n, len(STEPS) - 1))
        if n == 1:
            self._fill_templates()
        if n == 3:
            self._sync_devices()
        if n == 5:
            self._update_summary()
            self.name_edit.setFocus()
        self.pages.setCurrentIndex(n)
        for i, b in enumerate(self.step_buttons):
            b.setChecked(i == n)
        self.back_btn.setEnabled(n > 0)
        self.next_btn.setText("Создать проект →" if n == len(STEPS) - 1 else "Далее →")
        self.error.clear()

    def _next(self) -> None:
        i = self.pages.currentIndex()
        if i == 3 and not self._selected_devices():
            self.error.setText("Выберите хотя бы одно устройство")
            return
        if i < len(STEPS) - 1:
            self.go(i + 1)
        else:
            self._finish()

    def _on_platform(self, idx: int) -> None:
        self._platforms = PLATFORM_CHOICES[idx][0]
        self._template_id = ""
        self._sync_devices(reset=True)

    def _apply_template(self, t) -> None:
        idx = next(i for i, c in enumerate(PLATFORM_CHOICES) if set(c[0]) == set(t.platforms))
        self.platform_group.button(idx).setChecked(True)
        self._platforms = PLATFORM_CHOICES[idx][0]
        self._template_id = t.id
        self._sync_devices(reset=True)

    def _fill_templates(self) -> None:
        self.template_list.blockSignals(True)
        self.template_list.clear()
        options = templates_for(self._platforms)
        for t in options:
            item = QListWidgetItem(pixmap_icon(thumbnail(list(t.platforms), t.name)), f"{t.name}\n{t.description}")
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            self.template_list.addItem(item)
        for uid, ut in self._user.items():
            if set(ut.platforms) != set(self._platforms):
                continue
            item = QListWidgetItem(pixmap_icon(thumbnail(list(ut.platforms), ut.title)),
                                   f"{ut.title}\nМой шаблон · экранов: {ut.screens}")
            item.setData(Qt.ItemDataRole.UserRole, uid)
            self.template_list.addItem(item)
            options.append(ut)
        self.template_list.blockSignals(False)
        ids = [self.template_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.template_list.count())]
        if self._template_id not in ids:
            self._template_id = ids[0] if ids else ""
        if ids:
            self.template_list.setCurrentRow(ids.index(self._template_id))

    def _on_template(self, item, _prev=None) -> None:
        if item:
            self._template_id = item.data(Qt.ItemDataRole.UserRole)
            self._sync_devices(reset=True)

    def _sync_devices(self, reset: bool = False) -> None:
        defaults = (set(template(self._template_id).default_devices)
                    if self._template_id and self._template_id not in self._user else set())
        if not defaults:
            ts = templates_for(self._platforms)
            defaults = set(ts[0].default_devices) if ts else set()
        for dev_id, cb in self.device_checks.items():
            allowed = cb.property("platform") in self._platforms
            cb.setVisible(allowed)
            if not allowed:
                cb.setChecked(False)
            elif reset:
                cb.setChecked(dev_id in defaults)
        if not self._selected_devices():
            for dev_id in defaults:
                self.device_checks[dev_id].setChecked(True)

    def _selected_devices(self) -> list[str]:
        return [d for d, cb in self.device_checks.items() if cb.isChecked() and cb.property("platform") in self._platforms]

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Папка для проекта", self.location.text())
        if d:
            self.location.setText(d)

    def _target_path(self) -> Path | None:
        try:
            name = validate_file_name(self.name_edit.text())
        except ProjectError:
            return None
        return Path(self.location.text().strip()) / f"{name}{EXTENSION}"

    def _update_summary(self) -> None:
        target = self._target_path()
        rows = [("Платформы", platforms_text(list(self._platforms))),
                ("Шаблон", self._template_name()),
                ("Экранов", str(len(self._selected_devices()))),
                ("Файл", str(target) if target else "укажите название")]
        self.summary.setText("<table>" + "".join(
            f"<tr><td style='padding-right:12px'>{k}</td><td style='color:#F2F2F2'>{v}</td></tr>" for k, v in rows)
            + "</table>")

    def _template_name(self) -> str:
        if self._template_id in self._user:
            return f"{self._user[self._template_id].title} (мой шаблон — экраны берутся из шаблона)"
        return template(self._template_id).name if self._template_id else "—"

    def _finish(self) -> None:
        try:
            title = validate_file_name(self.name_edit.text())
        except ProjectError as exc:
            self.error.setText(str(exc))
            return
        if not self._selected_devices():
            self.error.setText("Выберите хотя бы одно устройство (шаг 4)")
            return
        loc = self.location.text().strip()
        if not loc:
            self.error.setText("Укажите расположение проекта")
            return
        target = Path(loc) / f"{title}{EXTENSION}"
        if target.exists():
            self.error.setText(f"Файл уже существует: {target}")
            return
        self.result_spec = NewProjectSpec(
            title=title, location=Path(loc), platforms=list(self._platforms), template_id=self._template_id,
            description=self.desc_edit.text().strip(), devices=self._selected_devices(),
            orientation="landscape" if self.landscape.isChecked() else "portrait",
            safe_areas=self.safe_areas.isChecked(),
            tags=[t.strip() for t in self.tags_edit.text().split(",") if t.strip()],
            appearance=Appearance(theme=self.theme_combo.currentData(),
                                  accent=ACCENTS[max(0, self.accent_group.checkedId())],
                                  font_family=self.font_combo.currentText(),
                                  corner_radius=self.radius_combo.currentData(),
                                  density=self.density_combo.currentData()))
        if self._template_id in self._user:
            self.result_spec.template_path = self._user[self._template_id].path
            self.result_spec.template_id = ""
        self.open_after = self.open_after_cb.isChecked()
        self.accept()


__all__ = ["NewProjectWizard", "TEMPLATES"]
