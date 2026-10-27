"""Снимки экрана для отчёта этапа. Использует временную папку данных, реальные данные пользователя не трогает.

Запуск: .venv\\Scripts\\python -m tools.stage_screenshots docs\\screenshots
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.context import AppContext
from app.core.paths import AppPaths
from app.core.project.service import NewProjectSpec
from app.ui.dialogs.new_project_wizard import NewProjectWizard
from app.ui.shell.main_window import PAGE_SETTINGS, MainWindow
from app.ui.themes.fusion_amoled import apply_theme

DEMO = [
    ("KiroX Design", ["android", "windows"], ["android_phone", "windows_window"], ["KiroX", "Telegram", "Dark UI"],
     "Современный дизайн для мессенджера"),
    ("PulseDesk UI", ["windows"], ["windows_window"], ["мониторинг"], "Панель удалённого управления ПК"),
    ("Зимние воспоминания", ["android"], ["android_phone"], ["игра"], "2D-игра, экран меню"),
    ("Kiro Bot v4", ["android"], ["android_phone", "android_tablet"], [], ""),
]


def main(out_dir: str) -> int:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="ads_shots_"))
    app = QApplication(sys.argv)
    apply_theme(app)
    ctx = AppContext.create(AppPaths(tmp / "data"))
    projects = tmp / "Проекты"
    ctx.settings.set("general/projects_dir", str(projects))
    ids = []
    for title, plats, devs, tags, desc in DEMO:
        doc, _ = ctx.service.create(NewProjectSpec(title=title, location=projects, platforms=plats, devices=devs,
                                                   tags=tags, description=desc))
        ids.append(doc.meta.id)
    ctx.index.add_folder("Android")
    ctx.index.add_folder("Клиенты")
    ctx.index.set_folder(ids[0], "Клиенты")
    ctx.index.set_favorite(ids[0], True)

    win = MainWindow(ctx)
    win.resize(1536, 960)
    win.show()

    def shots():
        win.hub.refresh()
        win.hub.select_project(ids[0])
        app.processEvents()
        win.grab().save(str(out / "stage1_01_project_hub.png"))
        win.hub.set_view_mode("list")
        app.processEvents()
        win.grab().save(str(out / "stage1_02_project_hub_list.png"))
        win.hub.set_view_mode("grid")

        wiz = NewProjectWizard(projects, "", win)
        wiz.resize(1100, 700)
        wiz.show()
        for i, name in ((0, "platform"), (3, "devices"), (5, "name")):
            wiz.go(i)
            if i == 5:
                wiz.name_edit.setText("Мой мессенджер")
            app.processEvents()
            wiz.grab().save(str(out / f"stage1_03_wizard_{i + 1}_{name}.png"))
        wiz.close()

        win.open_project(str(projects / "KiroX Design.adsproj"))
        app.processEvents()
        win.grab().save(str(out / "stage1_04_project_page.png"))
        win.show_page(PAGE_SETTINGS)
        app.processEvents()
        win.grab().save(str(out / "stage1_05_settings.png"))
        win.dirty = False
        app.quit()

    QTimer.singleShot(500, shots)
    app.exec()
    ctx.close()
    print("Снимки сохранены в", out.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots"))
