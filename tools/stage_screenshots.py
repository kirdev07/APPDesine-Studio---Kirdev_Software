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


ICON_SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M4 12 L12 4 L20 12 L17 12 '
            b'L17 20 L7 20 L7 12 Z" fill="#F2F2F2"/><rect x="10" y="14" width="4" height="6" fill="#2F7BFF"/>'
            b'<script>alert(1)</script></svg>')


def _stage4(win, ed, app, out):
    import hashlib

    from app.core.document.model import Asset, ColorToken, TextStyle
    from app.engines.assets.svg import sanitize
    from app.ui.shell.main_window import PAGE_COLORS, PAGE_FONTS, PAGE_ICONS, PAGE_PROJECT, PAGE_RESOURCES
    ed.set_screen(ed.doc.screens[0].id)
    clean, _ = sanitize(ICON_SVG)
    icon = Asset(kind="icon", name="Дом", ext="svg", sha256=hashlib.sha256(clean).hexdigest(), size=len(clean),
                 license="MIT", source="собственная отрисовка", redistribution="allowed")
    ed.add_asset(icon, clean)
    ed.save_text_style(TextStyle(name="Кнопка", font_family="Segoe UI", font_size=42, font_weight=600,
                                 text_color="#FFFFFF", id="style_btn"))
    ed.save_color(ColorToken(name="Акцент", value="#2F7BFF"))
    ed.save_color(ColorToken(name="Поверхность", value="#141414"))
    btn = ed.insert_component("m3_button_filled")
    ed.select([], entered_group=btn.id)
    ed.insert_image(icon.id, (54, 54))
    ed.reorder("bottom")
    ed.select([btn.children[0].id] if btn.children else [])
    ed.select_any([n.id for n in tree_find(ed, btn.id).children if n.type == "text"])
    ed.apply_text_style_to_selection("style_btn")
    ed.select([btn.id], entered_group=None)
    cid = ed.create_component("Кнопка с иконкой", "Кнопки")
    inst = ed.selection[0]
    ed.set_props({inst: {"x": 64, "y": 1950}})
    second = ed.insert_instance(cid, (64, 1750))
    label = next(n for n in second.children if n.type == "text")
    ed.set_props({label.id: {"text": "Оформить заказ"}})
    win.show_page(PAGE_PROJECT)
    ed.select([second.id])
    win.project_page.canvas.fit()
    app.processEvents()
    win.grab().save(str(out / "stage4_01_instances_overrides.png"))
    win.open_in_builder(cid)
    b = win.builder
    b.preset_states()
    b.save()
    b.canvas.fit()
    app.processEvents()
    win.grab().save(str(out / "stage4_02_component_builder.png"))
    b.tabs.setCurrentIndex(1)
    b.state_list.setCurrentRow(1)
    app.processEvents()
    win.grab().save(str(out / "stage4_03_builder_states.png"))
    b.tabs.setCurrentIndex(0)
    win.show_page(PAGE_ICONS)
    win.icons.refresh_list()
    win.icons.open_icon(icon.id)
    win.icons.editor.add_vector([(3, 21), (21, 21)], closed=False)
    app.processEvents()
    win.grab().save(str(out / "stage4_04_svg_editor.png"))
    win.icons.save_icon()
    win.show_page(PAGE_FONTS)
    win.fonts_page.show_family("Segoe UI")
    win.fonts_page.style_list.setCurrentRow(0)
    app.processEvents()
    win.grab().save(str(out / "stage4_05_typography.png"))
    win.show_page(PAGE_RESOURCES)
    app.processEvents()
    win.grab().save(str(out / "stage4_06_resources.png"))
    win.show_page(PAGE_COLORS)
    app.processEvents()
    win.grab().save(str(out / "stage4_07_colors.png"))
    win.show_page(PAGE_PROJECT)


def tree_find(ed, node_id):
    from app.core.document import tree
    return tree.find(ed.screen(), node_id)[0]


def _demo_components(ed) -> str:
    """Экран из базовых компонентов: верхняя панель, поле, карточка с длинным текстом, кнопки, навигация."""
    s = ed.screen()
    k = s.width / 411
    ed.insert_component("m3_top_app_bar")
    title = next(n for n in tree_find(ed, ed.selection[0]).children if n.type == "text")
    ed.set_props({title.id: {"text": "Профиль"}})
    ed.insert_component("m3_text_field")
    ed.set_props({ed.selection[0]: {"x": round(16 * k), "y": round(96 * k), "w": s.width - round(32 * k),
                                    "constraint_h": "left_right"}})
    card = ed.insert_component("m3_card")
    ed.set_props({card.id: {"x": round(16 * k), "y": round(200 * k), "w": s.width - round(32 * k),
                            "constraint_h": "left_right"}})
    desc = tree_find(ed, card.id).children[1]
    ed.set_props({desc.id: {"text": "Карточка растёт по высоте вместе с текстом. Длинный русский текст переносится "
                                    "по словам и не обрезается: высота карточки задана «по содержимому», а ширина "
                                    "привязана к краям экрана, поэтому на планшете строк становится меньше."}})
    row = ed.insert_component("m3_button_outlined")
    ok = ed.insert_component("m3_button_filled")
    ed.select([row.id, ok.id])
    ed.wrap_in_auto_layout("horizontal")
    frame = ed.selection[0]
    ed.set_props({frame: {"x": round(16 * k), "y": round(470 * k), "w": s.width - round(32 * k),
                          "sizing_h": "fixed", "main_align": "end", "gap": round(8 * k),
                          "constraint_h": "left_right"}})
    ed.insert_component("m3_nav_bar")
    return card.id


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

        # ---- этап 3: Auto Layout и базовые компоненты
        from app.core.document.model import Screen
        from app.ui.workspace.layout_tools import ResponsiveDialog
        ed.add_screen(Screen(name="Настройки профиля", platform="android", width=1080, height=2400,
                             device_id="android_phone"))
        card_id = _demo_components(ed)
        ws.screens.rebuild()
        ws.canvas.fit()
        ed.select([card_id])
        app.processEvents()
        win.grab().save(str(out / "stage3_01_components_autolayout.png"))
        ed.select_any([tree_find(ed, card_id).children[1].id])
        ws.dock_diag.raise_()
        app.processEvents()
        win.grab().save(str(out / "stage3_02_child_sizing_diagnostics.png"))
        dlg = ResponsiveDialog(ed, win)
        dlg.show()
        app.processEvents()
        dlg.grab().save(str(out / "stage3_03_responsive_check.png"))
        dlg.close()
        ed.set_screen(ed.doc.screens[1].id)
        ed.insert_component("win_nav_pane")
        nav = ed.selection[0]
        ed.insert_component("win_command_bar")
        ed.set_props({ed.selection[0]: {"x": 300, "y": 230}})
        ed.insert_component("win_card")
        ed.set_props({ed.selection[0]: {"x": 300, "y": 300, "w": 600}})
        ed.select([nav])
        ws.screens.rebuild()
        ws.canvas.fit()
        app.processEvents()
        win.grab().save(str(out / "stage3_04_windows_components.png"))

        # ---- этап 4: компоненты, SVG, типографика
        _stage4(win, ed, app, out)
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
