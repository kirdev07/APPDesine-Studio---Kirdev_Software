"""Точка входа: python -m app"""

from __future__ import annotations

import logging
import sys
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_NAME, APP_VERSION
from app.context import AppContext
from app.core.logging_setup import setup_logging
from app.core.paths import AppPaths
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme

log = logging.getLogger("app")


def _install_excepthook() -> None:
    def hook(exc_type, exc, tb):
        log.critical("Необработанное исключение:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        if QApplication.instance():
            QMessageBox.critical(None, APP_NAME, f"Произошла внутренняя ошибка:\n{exc}\n\nПодробности записаны в журнал.")
    sys.excepthook = hook


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    paths = AppPaths.default().ensure()
    setup_logging(paths.logs)
    log.info("Запуск %s %s, Python %s", APP_NAME, APP_VERSION, sys.version.split()[0])
    _install_excepthook()
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    apply_theme(app)
    ctx = AppContext.create(paths)
    win = MainWindow(ctx)
    win.show()
    QTimer.singleShot(0, win.check_recovery)
    files = [a for a in argv[1:] if a.lower().endswith(".adsproj")]
    if not files and not ctx.settings.get("general/show_hub_on_start"):
        recent = ctx.index.query(filter="recent", recent_limit=1)
        files = [recent[0].path] if recent and not recent[0].missing else []
    if files:
        QTimer.singleShot(0, lambda: win.open_project(files[0]))
    code = app.exec()
    ctx.close()
    log.info("Завершение работы, код %s", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
