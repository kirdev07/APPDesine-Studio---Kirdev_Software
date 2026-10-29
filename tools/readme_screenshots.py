"""Скриншоты для страницы программы (README на GitHub). Временная папка данных — данные пользователя не трогает,
в кадр не попадают пути и имена с этого компьютера (строка состояния очищается).

Запуск: .venv\\Scripts\\python -m tools.readme_screenshots publish\\screenshots
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.paths import AppPaths
from app.core.project.service import NewProjectSpec
from app.ui import logo
from app.ui.shell.main_window import PAGE_EXPORT, PAGE_HUB, PAGE_PREVIEW, MainWindow
from app.ui.themes.fusion_amoled import apply_theme

W, H = 1600, 960


def _settle(app, n=12):
    from PySide6.QtCore import QEventLoop, QTimer
    for _ in range(n):
        app.processEvents()
    loop = QEventLoop()
    QTimer.singleShot(600, loop.quit)  # отложенные обновления (полоса экранов, миниатюры)
    loop.exec()
    app.processEvents()


def _shot(win, app, path: Path) -> None:
    win.statusBar().clearMessage()
    win.statusBar().showMessage("")
    _settle(app)
    win.grab().save(str(path))
    print(path)


def _project(ctx, root: Path, title: str, platforms, devices, desc=""):
    spec = NewProjectSpec(title=title, description=desc, platforms=list(platforms), devices=list(devices),
                          location=root)
    return ctx.service.create(spec)[1]


def main(out_dir: str) -> int:
    os.environ.setdefault("ADS_NO_TOUR", "1")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    apply_theme(app)
    app.setWindowIcon(logo.icon())
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    tmp = Path(tempfile.mkdtemp(prefix="ads_readme_"))
    root = tmp / "Проекты"
    root.mkdir()
    ctx = AppContext.create(AppPaths(tmp / "data").ensure())
    ctx.settings.set("general/projects_dir", str(root))
    ctx.settings.set("general/tour_done", True)
    ctx.settings.set("export/folder", r"D:\Проекты\Экспорт")  # в кадре — не папка с этого компьютера
    win = MainWindow(ctx)
    win.resize(W, H)
    win.show()
    music = _project(ctx, root, "Музыкальный плеер", ["android"], ["android_phone"], "Плеер с виджетом")
    _project(ctx, root, "Доставка еды", ["android"], ["android_phone", "android_tablet"], "Готовое приложение")
    desk = _project(ctx, root, "Панель мониторинга", ["windows"], ["windows_window"], "Программа для Windows")
    _project(ctx, root, "Мессенджер", ["android", "windows"], ["android_phone", "windows_window"], "Android + Windows")
    win.hub.refresh()
    win.show_page(PAGE_HUB)
    _shot(win, app, out / "01_projects.png")

    win.open_project(str(music))
    ed = win.project_page.editor
    blank = ed.screen().id
    player = ed.add_template_screen("player")
    for key in ("feed", "chat", "profile"):
        ed.add_template_screen(key)
    ed.remove_screen(blank)
    ed.set_screen(player.id)
    win.project_page.canvas.fit()
    big = max((n for n in ed.screen().nodes if n.is_frame), key=lambda n: n.w * n.h, default=None)
    if big is not None:
        ed.select([big.id])
    _shot(win, app, out / "02_android_design.png")
    win.run_prototype()
    _settle(app, 30)
    _shot(win, app, out / "03_prototype.png")
    win.show_page(PAGE_EXPORT)
    _shot(win, app, out / "05_export.png")
    win.project_page.mark_clean()
    win.dirty = False

    win.open_project(str(desk))
    ed = win.project_page.editor
    blank = ed.screen().id
    dash = ed.add_template_screen("win_dashboard")
    ed.add_template_screen("win_settings")
    ed.remove_screen(blank)
    ed.set_screen(dash.id)
    win.project_page.canvas.fit()
    ed.select([])
    _shot(win, app, out / "04_windows_design.png")
    win.project_page.mark_clean()
    win.dirty = False
    ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "publish/screenshots"))
