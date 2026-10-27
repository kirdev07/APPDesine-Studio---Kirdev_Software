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


def _demo_screen(ed) -> None:
    """Простой экран телефона, собранный через API редактора (как пользователь собрал бы его вручную)."""
    hdr = ed.add_node("rect", (0, 0, 1080, 560))
    ed.set_props({hdr.id: {"name": "Шапка", "fill": "#1A1A1A", "radius": 0}})
    title = ed.add_node("text", (64, 300, 900, 120))
    ed.set_props({title.id: {"name": "Заголовок", "text": "KiroX", "font_size": 96, "font_weight": 700}})
    sub = ed.add_node("text", (64, 420, 900, 60))
    ed.set_props({sub.id: {"name": "Подзаголовок", "text": "Быстрый. Удобный. Твой.", "font_size": 40,
                           "text_color": "#A0A0A0"}})
    search = ed.add_node("rect", (64, 620, 952, 120))
    ed.set_props({search.id: {"name": "Поиск", "fill": "#141414", "stroke": "#3A3A3A", "stroke_width": 2,
                              "radius": 60}})
    hint = ed.add_node("text", (120, 655, 600, 60))
    ed.set_props({hint.id: {"name": "Подсказка", "text": "Поиск…", "font_size": 40, "text_color": "#7A7A7A"}})
    ids = []
    for i in range(4):
        row = ed.add_node("rect", (64, 820 + i * 200, 952, 170))
        av = ed.add_node("ellipse", (88, 845 + i * 200, 120, 120))
        name = ed.add_node("text", (240, 850 + i * 200, 600, 60))
        ed.set_props({row.id: {"name": f"Чат {i + 1}", "fill": "#0F0F0F", "radius": 28},
                      av.id: {"name": "Аватар", "fill": "#3A3A3A"},
                      name.id: {"name": "Имя", "text": ["Kir Dev", "KiroX News", "Дизайн", "Архив"][i],
                                "font_size": 44, "font_weight": 600}})
        ed.select([row.id, av.id, name.id])
        ed.group_selection()
        ed.set_props({ed.selection[0]: {"name": f"Строка чата {i + 1}"}})
        ids.append(ed.selection[0])
    btn = ed.add_node("rect", (64, 2160, 952, 150))
    lbl = ed.add_node("text", (64, 2200, 952, 70))
    ed.set_props({btn.id: {"name": "Фон кнопки", "fill": "#F2F2F2", "radius": 75},
                  lbl.id: {"name": "Подпись", "text": "Новый чат", "font_size": 48, "font_weight": 600,
                           "text_color": "#000000", "align": "center"}})
    ed.select([btn.id, lbl.id])
    ed.group_selection()
    ed.set_props({ed.selection[0]: {"name": "Кнопка"}})
    ed.add_guide("x", 64)
    ed.add_guide("x", 1016)
    ed.add_guide("y", 2160)
    ed.select(ids[:2])


def _demo_window(ed) -> None:
    side = ed.add_node("rect", (0, 0, 240, 800))
    ed.set_props({side.id: {"name": "Боковая панель", "fill": "#0F0F0F", "radius": 0}})
    for i, t in enumerate(["Главная", "Система", "Мониторинг", "Настройки"]):
        n = ed.add_node("text", (32, 90 + i * 56, 180, 36))
        ed.set_props({n.id: {"name": t, "text": t, "font_size": 18}})
    for i, t in enumerate(["CPU 12%", "RAM 5.6 ГБ", "GPU 28%"]):
        card = ed.add_node("rect", (272 + i * 330, 40, 306, 160))
        txt = ed.add_node("text", (296 + i * 330, 64, 260, 40))
        ed.set_props({card.id: {"name": "Карточка", "fill": "#141414", "radius": 16},
                      txt.id: {"name": "Значение", "text": t, "font_size": 24, "font_weight": 600}})
    ed.select([])


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
        ws = win.project_page
        ed = ws.editor
        _demo_screen(ed)
        app.processEvents()
        ws.screens.rebuild()
        ws.canvas.fit()
        app.processEvents()
        win.grab().save(str(out / "stage2_01_workspace_selection.png"))
        ed.select([])
        app.processEvents()
        win.grab().save(str(out / "stage2_02_workspace_screen_props.png"))
        ed.set_screen(ed.doc.screens[1].id)
        _demo_window(ed)
        ws.screens.rebuild()
        ws.canvas.fit()
        app.processEvents()
        win.grab().save(str(out / "stage2_03_windows_screen.png"))
        ed.set_screen(ed.doc.screens[0].id)
        ws.canvas.set_zoom(1.0)
        ws.canvas.centerOn(300, 260)
        ed.select([ed.screen().nodes[1].id])
        app.processEvents()
        win.grab().save(str(out / "stage2_04_zoom_grid_handles.png"))
        win.save_project()
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
