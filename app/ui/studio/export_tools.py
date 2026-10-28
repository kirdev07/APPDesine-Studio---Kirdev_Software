"""Окна страницы экспорта: свой промпт для ИИ и сборка тестового APK (журнал Gradle, отмена, результат)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit, QPlainTextEdit, QVBoxLayout,
)

from app.exporters.apk_builder import Toolchain, apk_path, build_command
from app.exporters.prompts import PLACEHOLDERS, Prompt
from app.ui.studio.common import button
from app.ui.widgets import label


class PromptDialog(QDialog):
    """Создание и правка своего промпта (встроенный открывается как копия)."""

    def __init__(self, prompt: Prompt | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Промпт для ИИ")
        self.resize(640, 480)
        src = prompt
        self.prompt = Prompt(name=src.name + (" (копия)" if src.builtin else ""), text=src.text,
                             category="Мои промпты" if src.builtin else src.category,
                             **({} if src.builtin else {"id": src.id})) if src else Prompt(name="", text="")
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(self.prompt.name)
        self.name.setPlaceholderText("Например: «Стиль кода команды»")
        self.category = QLineEdit(self.prompt.category)
        form.addRow("Название", self.name)
        form.addRow("Раздел", self.category)
        v.addLayout(form)
        self.text = QPlainTextEdit(self.prompt.text)
        self.text.setPlaceholderText("Указания для ИИ: требования к коду, архитектуре, тестам, оформлению…")
        v.addWidget(self.text, 1)
        v.addWidget(label("Подстановки: " + ", ".join("{" + p + "}" for p in PLACEHOLDERS) +
                          " — заменяются значениями проекта при сборке пакета. Свои промпты доступны во всех "
                          "проектах.", "Muted", wrap=True))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.error = label("", "Muted")
        v.addWidget(self.error)

    def _accept(self) -> None:
        if not self.name.text().strip() or not self.text.toPlainText().strip():
            self.error.setText("Заполните название и текст промпта")
            return
        self.prompt.name = self.name.text().strip()[:120]
        self.prompt.category = self.category.text().strip()[:60] or "Мои промпты"
        self.prompt.text = self.text.toPlainText()
        self.accept()


class ApkBuildDialog(QDialog):
    """Сборка отладочного APK: Gradle в отдельном процессе, журнал, отмена, открыть папку с APK."""

    def __init__(self, toolchain: Toolchain, project: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Сборка тестового APK")
        self.resize(820, 560)
        self.project, self.toolchain = Path(project), toolchain
        v = QVBoxLayout(self)
        v.addWidget(label(f"Проект: {project}", "Muted", wrap=True))
        v.addWidget(label(toolchain.describe() + ". Первая сборка скачивает зависимости Gradle из Google Maven "
                          "и Maven Central — нужен интернет; дальше — из кэша.", "Muted", wrap=True))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        v.addWidget(self.log, 1)
        self.status = label("Сборка…", "H2")
        v.addWidget(self.status)
        row = QHBoxLayout()
        self.b_open = button("Открыть папку с APK", self.open_folder)
        self.b_open.setEnabled(False)
        self.b_project = button("Открыть проект", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(project))))
        self.b_stop = button("Остановить", self.stop, object_name="Danger")
        self.b_close = button("Закрыть", self.close)
        for b in (self.b_open, self.b_project, self.b_stop, self.b_close):
            row.addWidget(b)
        v.addLayout(row)
        self.proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        for k, val in toolchain.env().items():
            if k in ("JAVA_HOME", "ANDROID_HOME"):
                env.insert(k, val)
        self.proc.setProcessEnvironment(env)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._done)
        self.proc.errorOccurred.connect(lambda e: self._fail(f"не удалось запустить Gradle ({e.name})"))
        self.result: Path | None = None

    def start(self) -> None:
        exe, args = build_command(self.toolchain, self.project)
        self.log.appendPlainText(f"> {exe} {' '.join(args)}\n")
        self.proc.start("cmd.exe", ["/c", exe, *args])  # gradle.bat запускается через cmd

    def _read(self) -> None:
        data = bytes(self.proc.readAllStandardOutput())
        self.log.appendPlainText(data.decode("utf-8", errors="replace").rstrip())

    def _done(self, code, _status=None) -> None:
        self.b_stop.setEnabled(False)
        apk = apk_path(self.project)
        if code == 0 and apk.exists():
            self.result = apk
            self.status.setText(f"✓ APK собран: {apk} ({apk.stat().st_size // 1024} КБ)")
            self.b_open.setEnabled(True)
        else:
            self._fail(f"Gradle завершился с кодом {code} — подробности в журнале выше")

    def _fail(self, text: str) -> None:
        self.status.setText("⛔ " + text)
        self.b_stop.setEnabled(False)

    def stop(self) -> None:
        if self.proc.state() != QProcess.ProcessState.NotRunning:
            pid = self.proc.processId()
            if pid:  # gradle.bat запускает java — останавливаем всё дерево процессов сборки
                QProcess.execute("taskkill", ["/F", "/T", "/PID", str(pid)])
            self.proc.kill()
            self.status.setText("Сборка остановлена")

    def open_folder(self) -> None:
        if self.result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result.parent)))

    def closeEvent(self, e):
        self.stop()
        super().closeEvent(e)
