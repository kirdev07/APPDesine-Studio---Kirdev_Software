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
from app.ui.themes.fusion_amoled import apply_theme, install_qt_russian

log = logging.getLogger("app")


def _install_excepthook() -> None:
    def hook(exc_type, exc, tb):
        log.critical("Необработанное исключение:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        if QApplication.instance():
            QMessageBox.critical(None, APP_NAME, f"Произошла внутренняя ошибка:\n{exc}\n\nПодробности записаны в журнал.")
    sys.excepthook = hook


def _apply_ui_scale(paths: AppPaths) -> None:
    """Масштаб интерфейса из настроек (до создания QApplication). Переменная QT_SCALE_FACTOR важнее."""
    import os

    from app.core.settings import UI_SCALES, Settings
    scale = Settings(paths.settings_file).get("general/ui_scale")
    if scale in UI_SCALES and scale != 100 and "QT_SCALE_FACTOR" not in os.environ:
        os.environ["QT_SCALE_FACTOR"] = f"{scale / 100:g}"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if "--smoke-test" in argv:  # самопроверка сборки: своя временная папка данных, данные пользователя не трогает
        from app import smoke
        i = argv.index("--smoke-test")
        return smoke.run(argv[i + 1] if len(argv) > i + 1 else None)
    paths = AppPaths.default().ensure()
    _apply_ui_scale(paths)
    setup_logging(paths.logs)
    log.info("Запуск %s %s, Python %s", APP_NAME, APP_VERSION, sys.version.split()[0])
    _install_excepthook()
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    apply_theme(app)
    install_qt_russian(app)
    from app.ui import logo
    from app.ui.themes import titlebar
    from app.ui.themes.fusion_amoled import TOKENS
    app.setWindowIcon(logo.icon())  # значок окна и панели задач
    titlebar.install(app, TOKENS["bg"], TOKENS["text"], TOKENS["border"])  # строка заголовка — в цвет программы
    ctx = AppContext.create(paths)
    win = MainWindow(ctx)
    win.show()
    QTimer.singleShot(0, win.check_recovery)
    QTimer.singleShot(2000, win.updates.check_on_start)  # раз в день, в фоне; выключается в настройках
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
