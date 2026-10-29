"""Настройки программы. Показываются только работающие параметры; телеметрии нет."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QListWidget, QMessageBox, QPushButton,
    QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from app import APP_NAME, APP_VERSION, COPYRIGHT
from app.context import AppContext
from app.libraries.catalog import DEVICES
from app.ui.widgets import label, panel

SECTIONS = ["Основные", "Проект и автосохранение", "Устройства", "Экспорт", "Журнал и данные", "О программе"]


class SettingsPage(QWidget):
    changed = Signal()

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.ctx = ctx
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        nav, nlay = panel()
        nav.setFixedWidth(260)
        nlay.addWidget(label("Настройки", "H1"))
        self.nav = QListWidget()
        self.nav.addItems(SECTIONS)
        nlay.addWidget(self.nav, 1)
        reset = QPushButton("Сбросить настройки")
        reset.clicked.connect(self._reset)
        nlay.addWidget(reset)
        root.addWidget(nav)

        self.stack = QStackedWidget()
        for build in (self._general, self._project, self._devices, self._export, self._data, self._about):
            self.stack.addWidget(build())
        root.addWidget(self.stack, 1)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
        self.load()

    def _section(self, title: str, subtitle: str):
        w, lay = panel(margins=18)
        lay.addWidget(label(title, "H2"))
        lay.addWidget(label(subtitle, "Muted", wrap=True))
        form = QFormLayout()
        form.setHorizontalSpacing(32)
        form.setVerticalSpacing(10)
        lay.addLayout(form)
        return w, lay, form

    def _general(self) -> QWidget:
        w, lay, form = self._section("Основные настройки", "Базовые параметры программы")
        self.language = QComboBox()
        self.language.addItem("Русский", "ru")
        self.language.setToolTip("Строки подготовлены к локализации; другие языки появятся позже")
        form.addRow("Язык интерфейса", self.language)
        theme = label("Fusion AMOLED (чёрная)")
        theme.setToolTip("Оформление программы фиксировано. Темы дизайна проекта задаются в самом проекте.")
        form.addRow("Тема программы", theme)
        self.show_hub = QCheckBox("Показывать Project Hub при запуске")
        self.show_hub.toggled.connect(lambda v: self._set("general/show_hub_on_start", v))
        form.addRow("", self.show_hub)
        self.auto_update = QCheckBox("Проверять обновления при запуске (раз в день)")
        self.auto_update.setToolTip("Программа спрашивает у официальной страницы только номер последней версии — "
                                    "никаких сведений о вас и ваших проектах не отправляется")
        self.auto_update.toggled.connect(lambda v: self._set("updates/auto_check", v))
        form.addRow("", self.auto_update)
        self.recent = QSpinBox()
        self.recent.setRange(5, 100)
        self.recent.valueChanged.connect(lambda v: self._set("general/recent_limit", v))
        form.addRow("Сколько недавних проектов хранить", self.recent)
        row = QHBoxLayout()
        self.projects_dir = QLineEdit()
        self.projects_dir.editingFinished.connect(lambda: self._set("general/projects_dir", self.projects_dir.text().strip()))
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self._browse_dir)
        row.addWidget(self.projects_dir, 1)
        row.addWidget(browse)
        form.addRow("Папка проектов по умолчанию", row)
        from app.core.settings import UI_SCALES
        self.ui_scale = QComboBox()
        for sc in UI_SCALES:
            self.ui_scale.addItem(f"{sc} %", sc)
        self.ui_scale.currentIndexChanged.connect(self._set_scale)
        self.ui_scale.setToolTip("Крупнее — всё в окне больше: текст, кнопки, панели и холст")
        row = QHBoxLayout()
        row.addWidget(self.ui_scale)
        self.scale_note = label("", "Muted")
        row.addWidget(self.scale_note, 1)
        self.b_restart = QPushButton("Перезапустить")
        self.b_restart.setToolTip("Закрыть программу (с вопросом о несохранённых изменениях) и открыть снова")
        self.b_restart.clicked.connect(self._restart)
        self.b_restart.setVisible(False)
        row.addWidget(self.b_restart)
        form.addRow("Масштаб интерфейса", row)
        lay.addWidget(label("Без учётной записи, облака, рекламы и сбора аналитики. В интернет программа ходит только за номером "
                            "последней версии — если включена проверка обновлений.",
                            "Muted", wrap=True))
        lay.addStretch()
        return w

    def _project(self) -> QWidget:
        w, lay, form = self._section("Проект и автосохранение",
                                     "Автосохранение пишет снимок в папку восстановления и не перезаписывает ваш файл.")
        self.autosave = QCheckBox("Автосохранение для восстановления после сбоя")
        self.autosave.toggled.connect(lambda v: self._set("project/autosave_enabled", v))
        form.addRow("", self.autosave)
        self.autosave_min = QSpinBox()
        self.autosave_min.setRange(1, 60)
        self.autosave_min.setSuffix(" мин")
        self.autosave_min.valueChanged.connect(lambda v: self._set("project/autosave_minutes", v))
        form.addRow("Интервал автосохранения", self.autosave_min)
        self.backups = QSpinBox()
        self.backups.setRange(0, 50)
        self.backups.valueChanged.connect(self._set_backups)
        form.addRow("Резервных копий на проект", self.backups)
        lay.addStretch()
        return w

    def _devices(self) -> QWidget:
        w, lay, form = self._section("Устройства", "Профили для новых проектов. Устройства предпросмотра (телефоны, складные, планшеты, окна, свой размер и плотность) выбираются на странице «Просмотр».")
        self.def_android = QComboBox()
        self.def_windows = QComboBox()
        for d in DEVICES:
            target = self.def_android if d.platform == "android" else self.def_windows
            target.addItem(f"{d.name} — {d.width}×{d.height}, {d.dpi} dpi", d.id)
        self.def_android.currentIndexChanged.connect(
            lambda: self._set("devices/default_android", self.def_android.currentData()))
        self.def_windows.currentIndexChanged.connect(
            lambda: self._set("devices/default_windows", self.def_windows.currentData()))
        form.addRow("Android по умолчанию", self.def_android)
        form.addRow("Windows по умолчанию", self.def_windows)
        lay.addStretch()
        return w

    def _export(self) -> QWidget:
        w, lay, form = self._section("Экспорт", "Настройки AI-экспорта по умолчанию. Состав пакета и задание "
                                                "настраиваются перед каждой сборкой на странице «Экспорт».")
        row = QHBoxLayout()
        self.export_dir = QLineEdit()
        self.export_dir.setPlaceholderText("<папка проектов>\Экспорт")
        self.export_dir.editingFinished.connect(lambda: self._set("export/folder", self.export_dir.text().strip()))
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self._browse_export)
        row.addWidget(self.export_dir, 1)
        row.addWidget(browse)
        form.addRow("Папка для пакетов", row)
        self.export_previews = QCheckBox("Добавлять превью экранов (PNG)")
        self.export_previews.toggled.connect(lambda v: self._set("export/include_previews", v))
        form.addRow("", self.export_previews)
        lay.addStretch()
        return w

    def _browse_export(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Папка для пакетов экспорта", self.export_dir.text())
        if d:
            self.export_dir.setText(os.path.normpath(d))
            self._set("export/folder", self.export_dir.text())

    def _data(self) -> QWidget:
        w, lay, form = self._section("Журнал и данные", "Служебные файлы программы хранятся только на этом компьютере.")
        p = self.ctx.paths
        for title, path in (("Журнал", p.logs), ("Резервные копии", p.backups), ("Восстановление", p.recovery)):
            row = QHBoxLayout()
            row.addWidget(label(str(path), "Muted"), 1)
            btn = QPushButton("Открыть папку")
            btn.clicked.connect(lambda _=False, x=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(x))))
            row.addWidget(btn)
            form.addRow(title, row)
        lay.addStretch()
        return w

    def _about(self) -> QWidget:
        w, lay, _ = self._section(APP_NAME, f"Версия {APP_VERSION}")
        lay.addWidget(label("Локальная студия дизайна интерфейсов для Android (Jetpack Compose / Material 3) и "
                            "Windows (Python / PySide6) с передачей структурированного пакета в Claude Code.\n\n"
                            "Это не компилятор Android и не гарантирует точную отрисовку Compose.\n\n"
                            f"{COPYRIGHT}\nБесплатная программа: пользоваться можно свободно, ваши дизайны и "
                            "выгруженные проекты — ваши (см. LICENSE). "
                            "Использует PySide6 / Qt (LGPLv3) — см. THIRD_PARTY_NOTICES.", wrap=True))
        lay.addStretch()
        return w

    # ---------- данные ----------
    def load(self) -> None:
        s = self.ctx.settings
        widgets = (self.show_hub, self.auto_update, self.recent, self.autosave, self.autosave_min, self.backups, self.def_android,
                   self.def_windows, self.export_previews, self.ui_scale)
        for wdg in widgets:
            wdg.blockSignals(True)
        self.show_hub.setChecked(s.get("general/show_hub_on_start"))
        self.auto_update.setChecked(s.get("updates/auto_check"))
        self.recent.setValue(s.get("general/recent_limit"))
        self.projects_dir.setText(s.get("general/projects_dir"))
        self.autosave.setChecked(s.get("project/autosave_enabled"))
        self.autosave_min.setValue(s.get("project/autosave_minutes"))
        self.backups.setValue(s.get("project/backups_keep"))
        self.def_android.setCurrentIndex(max(0, self.def_android.findData(s.get("devices/default_android"))))
        self.def_windows.setCurrentIndex(max(0, self.def_windows.findData(s.get("devices/default_windows"))))
        self.export_dir.setText(s.get("export/folder"))
        self.ui_scale.setCurrentIndex(max(0, self.ui_scale.findData(s.get("general/ui_scale"))))
        self.export_previews.setChecked(s.get("export/include_previews"))
        for wdg in widgets:
            wdg.blockSignals(False)

    def _set(self, key: str, value) -> None:
        self.ctx.settings.set(key, value)
        self.changed.emit()

    def _set_scale(self, _i=None) -> None:
        self._set("general/ui_scale", int(self.ui_scale.currentData()))
        import os
        current = round(float(os.environ.get("QT_SCALE_FACTOR", "1")) * 100)
        changed = current != self.ui_scale.currentData()
        self.scale_note.setText("применится после перезапуска" if changed else "")
        self.b_restart.setVisible(changed)

    def _restart(self) -> None:
        import sys

        from PySide6.QtCore import QProcess
        win = self.window()
        if win.close():  # закрытие спросит о несохранённых изменениях; отказ — перезапуска нет
            args = sys.argv[1:] if getattr(sys, "frozen", False) else ["-m", "app"] + sys.argv[1:]
            os_env = __import__("os").environ
            os_env.pop("QT_SCALE_FACTOR", None)
            QProcess.startDetached(sys.executable, args)

    def _set_backups(self, v: int) -> None:
        self._set("project/backups_keep", v)
        self.ctx.service.keep_backups = v

    def _browse_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Папка проектов", self.projects_dir.text())
        if d:
            self.projects_dir.setText(os.path.normpath(d))
            self._set("general/projects_dir", self.projects_dir.text())

    def _reset(self) -> None:
        if QMessageBox.question(self, "Сброс настроек", "Вернуть все настройки к значениям по умолчанию? "
                                "Проекты не затрагиваются.") == QMessageBox.StandardButton.Yes:
            self.ctx.settings.reset()
            self.ctx.service.keep_backups = self.ctx.settings.get("project/backups_keep")
            self.load()
            self.changed.emit()


__all__ = ["SettingsPage", "Path"]
