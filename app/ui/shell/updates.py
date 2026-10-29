"""Обновления в окне программы: проверка раз в день при запуске (выключается в настройках) и по команде
«Помощь → Проверить обновления»; скачивание с прогрессом, сверка SHA-256 и перезапуск в новой версии."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QMessageBox, QProgressDialog, QTextBrowser,
                               QVBoxLayout)

from app import APP_VERSION, HOME_PAGE
from app.core import updater


class _Job(QThread):
    done = Signal(object, object)       # результат, ошибка
    progress = Signal(int, int)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn, self.stop = fn, False

    def run(self):
        try:
            self.done.emit(self.fn(self), None)
        except Exception as exc:  # noqa: BLE001 — показать пользователю понятный текст
            self.done.emit(None, exc)


class Updates(QObject):
    def __init__(self, win):
        super().__init__(win)
        self.win, self.job = win, None

    @property
    def settings(self):
        return self.win.ctx.settings

    # ---------- проверка ----------
    def check_on_start(self) -> None:
        """Тихая проверка при запуске: не чаще раза в сутки и только если не выключена в настройках."""
        if not self.settings.get("updates/auto_check"):
            return
        if time.time() - float(self.settings.get("updates/last_check") or 0) < updater.CHECK_EVERY_S:
            return
        self._check(silent=True)

    def check_now(self) -> None:
        self._check(silent=False)

    def _check(self, silent: bool) -> None:
        if self.job is not None:
            return
        self.job = _Job(lambda _job: updater.fetch_latest(), self)
        self.job.done.connect(lambda rel, err: self._checked(rel, err, silent))
        self.job.start()

    def _checked(self, rel, err, silent: bool) -> None:
        self.job = None
        if err is None:
            self.settings.set("updates/last_check", str(int(time.time())))
        if err is not None:
            if not silent:
                QMessageBox.warning(self.win, "Обновления", f"Не удалось проверить обновления: {err}")
            return
        if rel is None:
            if not silent:
                QMessageBox.information(self.win, "Обновления", "На официальной странице пока нет выпусков "
                                        f"для скачивания. У вас версия {APP_VERSION}.")
            return
        if not updater.is_newer(rel.version):
            if not silent:
                QMessageBox.information(self.win, "Обновления", f"У вас последняя версия ({APP_VERSION}).")
            return
        if silent and self.settings.get("updates/skip") == rel.version:
            return
        self._offer(rel)

    def _offer(self, rel) -> None:
        """Окно «Доступно обновление»: список изменений целиком, оформленным (Markdown), с прокруткой."""
        d = QDialog(self.win)
        d.setWindowTitle("Доступно обновление")
        d.resize(620, 520)
        lay = QVBoxLayout(d)
        size = f" Размер — {rel.size / 1048576:.0f} МБ." if rel.size >= 1048576 else ""
        head = QLabel(f"<b>Вышла версия {rel.version}</b> (у вас {APP_VERSION}).{size}")
        head.setWordWrap(True)
        lay.addWidget(head)
        lay.addWidget(QLabel("Что нового:"))
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(rel.notes or "_Список изменений не указан._")
        lay.addWidget(notes, 1)
        buttons = QDialogButtonBox()
        go = buttons.addButton("Обновить", QDialogButtonBox.ButtonRole.AcceptRole)
        later = buttons.addButton("Позже", QDialogButtonBox.ButtonRole.RejectRole)
        skip = buttons.addButton("Пропустить эту версию", QDialogButtonBox.ButtonRole.DestructiveRole)
        choice = {}
        for b, key in ((go, "go"), (later, "later"), (skip, "skip")):
            b.clicked.connect(lambda _=False, key=key: (choice.setdefault("v", key), d.accept()))
        go.setDefault(True)
        lay.addWidget(buttons)
        d.exec()
        if choice.get("v") == "skip":
            self.settings.set("updates/skip", rel.version)
        elif choice.get("v") == "go":
            self._download(rel)

    # ---------- скачивание и установка ----------
    def _download(self, rel) -> None:
        dest = updater.install_dir()
        if dest is None:  # запуск из исходников — заменять нечего, открываем страницу выпусков
            QDesktopServices.openUrl(QUrl(HOME_PAGE + "/releases/latest"))
            return
        bar = QProgressDialog("Скачивание обновления…", "Отмена", 0, 100, self.win)
        bar.setWindowTitle("Обновление")
        bar.setWindowModality(Qt.WindowModality.WindowModal)
        bar.setMinimumDuration(0)
        folder = Path(tempfile.mkdtemp(prefix="ads_dl_"))

        def work(job):
            z = updater.download(rel, folder, lambda got, total: job.progress.emit(got, total or rel.size or 1),
                                 lambda: job.stop)
            return updater.extract(z, folder / "new")
        self.job = _Job(work, self)
        self.job.progress.connect(lambda got, total: bar.setValue(min(100, int(got * 100 / max(1, total)))))
        bar.canceled.connect(lambda: setattr(self.job, "stop", True) if self.job else None)
        self.job.done.connect(lambda new_dir, err: self._downloaded(new_dir, err, bar, dest, rel))
        self.job.start()

    def _downloaded(self, new_dir, err, bar, dest, rel) -> None:
        self.job = None
        bar.close()
        if err is not None:
            QMessageBox.warning(self.win, "Обновление", f"Обновление не установлено: {err}")
            return
        if QMessageBox.question(self.win, "Обновление",
                                f"Версия {rel.version} скачана и проверена. Программа закроется и откроется уже "
                                "новой версией. Продолжить?") != QMessageBox.StandardButton.Yes:
            return
        if not self.win._confirm_discard():  # несохранённые изменения — сначала решение пользователя
            return
        updater.launch_install(new_dir, dest)
        self.win.ctx.settings.set("updates/skip", "")
        self.win._skip_confirm = True
        self.win.close()
