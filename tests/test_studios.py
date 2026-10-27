"""Этап 4 через интерфейс: компоненты и Component Builder, переиспользование между проектами, SVG-редактор,
шрифты и стили, цвета, ресурсы, шаблоны (S11–S14, S18)."""

import hashlib
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import Asset, ColorToken, TextStyle
from app.engines.assets.svg import sanitize
from app.ui.fonts import REGISTRY
from app.ui.shell.main_window import PAGE_BUILDER, PAGE_PROJECT, MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec

EVIL_SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" onload="alert(1)">'
            b'<script>alert(1)</script><path d="M4 4 L20 4 L12 20 Z" fill="#ff0000"/></svg>')


@pytest.fixture
def app_win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)

    def discard(win):
        for studio in (win.builder, win.icons):
            if studio.editor.stack is not None:
                studio.editor.stack.set_clean()
            if hasattr(studio, "_states_dirty"):
                studio._states_dirty = False
        win.project_page.mark_clean()
        win.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.resize(1500, 950)
    w.show()
    yield w, ctx, projects_dir
    ctx.close()


def open_new(win, ctx, folder, title):
    _, path = ctx.service.create(make_spec(folder, title=title))
    win.open_project(str(path))
    return path


def build_button(ed):
    btn = ed.insert_component("m3_button_filled")
    ed.select([btn.id])
    cid = ed.create_component("Кнопка покупки", "Кнопки")
    assert cid
    return cid


def test_create_component_and_override_in_instance(app_win):  # S14
    win, ctx, folder = app_win
    open_new(win, ctx, folder, "Магазин")
    ed = win.project_page.editor
    cid = build_button(ed)
    inst = ed.selected_nodes()[0]
    assert inst.is_instance and ed.doc.component(cid).name == "Кнопка покупки"
    label = inst.children[0]
    n = len(ed.stack)
    ed.set_props({label.id: {"text": "Оплатить", "x": 999}}, "Текст")  # x внутри экземпляра игнорируется
    assert len(ed.stack) == n + 1
    inst = tree.find(ed.screen(), inst.id)[0]
    assert inst.children[0].text == "Оплатить" and inst.overrides
    assert inst.children[0].x != 999
    ed.delete_selection()  # выделен экземпляр целиком — можно
    ed.undo()
    ed.select_any([inst.children[0].id])
    ed.delete_selection()  # содержимое экземпляра удалить нельзя
    assert tree.find(ed.screen(), inst.id)[0].children
    ed.undo()  # отменяет переопределение (заблокированное удаление в историю не попало)
    assert not tree.find(ed.screen(), inst.id)[0].overrides


def test_builder_edits_master_and_updates_instances(app_win):
    win, ctx, folder = app_win
    open_new(win, ctx, folder, "Билдер")
    ed = win.project_page.editor
    cid = build_button(ed)
    inst_id = ed.selection[0]
    label_ref = ed.doc.component(cid).root.children[0].id
    ed.set_props({f"{inst_id}:{label_ref}": {"text": "Переопределено"}})
    ed.insert_instance(cid, (100, 900))
    win.open_in_builder(cid)
    assert win.pages.currentIndex() == PAGE_BUILDER
    b = win.builder
    root = b.editor.screen().nodes[0]
    b.editor.set_props({root.id: {"fill": "#00AA55", "radius": 4}})
    assert b.is_dirty()
    n_main = len(ed.stack)
    assert b.save()
    assert len(ed.stack) == n_main + 1 and not b.is_dirty()
    insts = [n for n in ed.screen().nodes if n.is_instance]
    assert len(insts) == 2 and all(i.fill == "#00AA55" for i in insts)
    assert tree.find(ed.screen(), inst_id)[0].children[0].text == "Переопределено"
    ed.undo()  # одна отмена возвращает мастер и все экземпляры
    assert all(i.fill != "#00AA55" for i in ed.screen().nodes if i.is_instance)


def test_builder_states_preview_and_structure(app_win):
    win, ctx, folder = app_win
    open_new(win, ctx, folder, "Состояния")
    ed = win.project_page.editor
    cid = build_button(ed)
    win.open_in_builder(cid)
    b = win.builder
    b.preset_states()
    assert {"hover", "pressed", "focus", "disabled", "loading", "error"} <= set(b.states)
    assert b.preview.count() == 1 + len(b.states)
    b.state_list.setCurrentRow(1)
    b.o_node.setCurrentIndex(0)
    b.o_prop.setCurrentIndex(b.o_prop.findData("opacity"))
    b.o_value.setText("0,5")
    b.add_override()
    assert any(p.get("opacity") == 0.5 for p in b.states[b._state()].values())
    b.o_value.setText("не число")
    b.add_override()
    assert b.states_error.text()
    b.set_mode(2)
    assert b.structure.topLevelItemCount() == 1
    assert b.save()
    inst = next(n for n in ed.screen().nodes if n.is_instance)
    ed.select([inst.id])
    ed.set_instance_state("disabled")
    assert tree.find(ed.screen(), inst.id)[0].opacity == pytest.approx(0.38)
    # вкладки Анимация/Действия честно помечены этапом
    titles = [b.tabs.tabText(i) for i in range(b.tabs.count())]
    assert titles == ["Дизайн", "Состояния", "Анимация", "Действия"]


def test_nested_component_isolation(app_win):
    win, ctx, folder = app_win
    open_new(win, ctx, folder, "Вложенность")
    ed = win.project_page.editor
    btn_id = build_button(ed)
    inst = ed.selected_nodes()[0]
    card = ed.insert_component("m3_card")
    ed.select([card.id, inst.id])
    ed.wrap_in_auto_layout("vertical")
    ed.create_component("Карточка с кнопкой")
    card_id = ed.doc.components[-1].id
    win.open_in_builder(card_id)
    b = win.builder
    b.editor.open_component.emit(btn_id)  # то же, что двойной щелчок по вложенному экземпляру
    assert b.current_id == btn_id and b.breadcrumb == [card_id, btn_id]
    assert "›" in b.crumbs.text()


def test_reuse_component_in_another_project(app_win, tmp_path):  # критерий приёмки этапа 4
    win, ctx, folder = app_win
    open_new(win, ctx, folder, "Первый проект")
    ed = win.project_page.editor
    svg_clean, _ = sanitize(EVIL_SVG)
    icon = Asset(kind="icon", name="Стрелка", ext="svg", sha256=hashlib.sha256(svg_clean).hexdigest(),
                 size=len(svg_clean), license="MIT", redistribution="allowed")
    assert ed.add_asset(icon, svg_clean)
    ed.save_text_style(TextStyle(name="Акцент", font_family="Segoe UI", font_size=18, font_weight=700, id="accent"))
    frame = ed.add_node("frame", (40, 40, 240, 64))
    ed.set_props({frame.id: {"layout": "horizontal", "gap": 8, "pad_l": 12, "fill": "#222222"}})
    ed.select([frame.id], entered_group=None)
    img = ed.add_node("rect", (50, 50, 24, 24))
    ed.select([img.id])
    ed.delete_selection()
    ed.select([], entered_group=frame.id)
    image = ed.insert_image(icon.id, (24, 24))
    txt = ed.add_node("text", (0, 0, 120, 30))
    ed.select([txt.id])
    ed.apply_text_style_to_selection("accent")
    ed.select([frame.id], entered_group=None)
    cid = ed.create_component("Элемент с иконкой")
    win.open_in_builder(cid)
    win.builder.save_to_library()
    assert [i["id"] for i in win.builder.library.items()] == [cid]
    assert win.save_project()
    assert win.close_project()
    # второй проект: компонент из личной библиотеки
    open_new(win, ctx, folder, "Второй проект")
    ed2 = win.project_page.editor
    win.show_page(PAGE_BUILDER)
    b = win.builder
    b.refresh_library()
    b.lib_list.setCurrentRow(0)
    b.install_from_library()
    comp = ed2.doc.component(cid)
    assert comp is not None
    assert ed2.doc.text_style("accent").font_weight == 700        # стиль сохранён
    a = ed2.doc.assets[0]
    assert a.license == "MIT" and ed2.doc.asset_data[a.id] == svg_clean  # ресурс и лицензия
    b.insert_on_screen()
    assert win.pages.currentIndex() == PAGE_PROJECT
    inst = ed2.selected_nodes()[0]
    texts = [n for n in tree.descendants(inst) if n.type == "text"]
    assert texts and texts[0].font_size == 18 and texts[0].font_weight == 700
    assert not [d for d in ed2.diagnostics if "ресурс" in d.message]
    del image


def test_missing_asset_warning_and_placeholder(app_win):
    win, ctx, folder = app_win
    open_new(win, ctx, folder, "Ресурсы")
    ed = win.project_page.editor
    clean, _ = sanitize(EVIL_SVG)
    a = Asset(kind="icon", name="Значок", ext="svg", sha256=hashlib.sha256(clean).hexdigest(), size=len(clean))
    ed.add_asset(a, clean)
    node = ed.insert_image(a.id)
    assert not [d for d in ed.diagnostics if d.node_id == node.id and d.severity == "warning"]
    ed.doc.asset_data.pop(a.id)  # файл ресурса пропал (например, повреждённый архив)
    ed.refresh_diagnostics()
    assert any(d.node_id == node.id and "отсутствует" in d.message for d in ed.diagnostics)
    win.resources.refresh()
    assert win.resources.table.item(0, 6).text() == "файл отсутствует"
    assert not ed.remove_asset(a.id)  # используемый ресурс не удаляется


def test_svg_editor_import_draw_save_insert(app_win, qtbot):  # S11/S12
    win, ctx, folder = app_win
    open_new(win, ctx, folder, "Иконки")
    ed = win.project_page.editor
    page = win.icons
    clean, report = sanitize(EVIL_SVG)
    assert any("script" in r for r in report.removed) and b"script" not in clean
    a = Asset(kind="icon", name="Треугольник", ext="svg", sha256=hashlib.sha256(clean).hexdigest(), size=len(clean))
    assert ed.add_asset(a, clean)
    page.refresh_list()
    page.open_icon(a.id)
    assert len(page.editor.screen().nodes) == 1 and page.editor.screen().width == 24
    page.editor.add_vector([(2, 20), (12, 2), (22, 20)], closed=True)
    page.editor.add_node("ellipse", (9, 12, 6, 6))
    assert page.is_dirty()
    old_sha = ed.doc.asset(a.id).sha256
    assert page.save_icon()
    new = ed.doc.asset(a.id)
    assert new.sha256 != old_sha and not page.is_dirty()
    saved, rep = sanitize(ed.doc.asset_data[a.id])
    assert rep.removed == [] and saved.count(b"<path") == 3
    page.list.setCurrentRow(0)
    page.insert_on_screen()
    node = ed.selected_nodes()[0]
    assert node.type == "image" and node.asset_id == a.id
    assert node.id in win.project_page.canvas.items_by_id


def test_typography_font_import_and_styles(app_win, tmp_path):
    win, ctx, folder = app_win
    open_new(win, ctx, folder, "Шрифты")
    ed = win.project_page.editor
    t = ed.add_node("text", (40, 40, 300, 40))
    st = TextStyle(name="Заголовок", font_family="Segoe UI", font_size=28, font_weight=600)
    assert ed.save_text_style(st)
    ed.select([t.id])
    assert ed.apply_text_style_to_selection(st.id)
    st2 = TextStyle(name="Заголовок", font_family="Segoe UI", font_size=34, font_weight=700, id=st.id)
    ed.save_text_style(st2)
    t = tree.find(ed.screen(), t.id)[0]
    assert (t.font_size, t.font_weight, t.text_style) == (34, 700, st.id)
    ed.delete_text_style(st.id)
    assert tree.find(ed.screen(), t.id)[0].text_style == "" and tree.find(ed.screen(), t.id)[0].font_size == 34
    # импорт файла шрифта (системный Arial как пример файла; в проект кладём только для теста)
    src = Path("C:/Windows/Fonts/arial.ttf")
    if not src.exists() or not REGISTRY.families():
        pytest.skip("нет системного файла шрифта или базы шрифтов")
    data = src.read_bytes()
    families = REGISTRY.register("test-arial", data)
    font = Asset(kind="font", name="arial.ttf", ext="ttf", sha256=hashlib.sha256(data).hexdigest(), size=len(data),
                 family=families[0])
    assert ed.add_asset(font, data)
    cov = REGISTRY.coverage(families[0])
    assert cov["Кириллица"][0] == cov["Кириллица"][1]


def test_font_fallback_warning(app_win):  # S13
    win, ctx, folder = app_win
    if not REGISTRY.families():
        pytest.skip("платформа без базы шрифтов (offscreen) — проверка доступности шрифтов не выполняется")
    open_new(win, ctx, folder, "Замена шрифта")
    ed = win.project_page.editor
    t = ed.add_node("text", (40, 40, 300, 40))
    ed.set_props({t.id: {"font_family": "Шрифт, которого нет"}})
    assert any("недоступен" in d.message for d in ed.diagnostics)


def test_colors_tokens(app_win):
    win, ctx, folder = app_win
    open_new(win, ctx, folder, "Цвета")
    ed = win.project_page.editor
    r = ed.add_node("rect", (10, 10, 50, 50))
    tok = ColorToken(name="Акцент", value="#FF8800")
    assert ed.save_color(tok)
    ed.select([r.id])
    assert ed.apply_color(tok.value)
    assert tree.find(ed.screen(), r.id)[0].fill == "#FF8800"
    win.colors.refresh()
    assert win.colors.tokens.count() == 1
    assert any(win.colors.used.item(i).data(256) == "#FF8800" for i in range(win.colors.used.count()))


def test_save_as_template_then_create(app_win, monkeypatch):
    from app.core.project.templates import TemplateStore
    from app.ui.dialogs.new_project_wizard import NewProjectWizard
    win, ctx, folder = app_win
    open_new(win, ctx, folder, "Исходник")
    ed = win.project_page.editor
    build_button(ed)
    monkeypatch.setattr("PySide6.QtWidgets.QInputDialog.getText", lambda *a, **k: ("Шаблон магазина", True))
    win.save_as_template()
    items = TemplateStore(ctx.paths.templates).items()
    assert [t.title for t in items] == ["Шаблон магазина"]
    win.hub.refresh_templates()
    assert any(win.hub.templates.item(i).data(256) == f"user:{items[0].id}" for i in range(win.hub.templates.count()))

    def fake_exec(self):
        self.go(1)
        row = next(i for i in range(self.template_list.count())
                   if self.template_list.item(i).data(256) == f"user:{items[0].id}")
        self.template_list.setCurrentRow(row)
        self.go(5)
        self.name_edit.setText("Из моего шаблона")
        self._next()
        return NewProjectWizard.DialogCode.Accepted
    monkeypatch.setattr(NewProjectWizard, "exec", fake_exec)
    assert win.save_project() and win.close_project()
    win.new_project("")
    assert win.doc.meta.title == "Из моего шаблона" and win.doc.components
    assert any(n.is_instance for n in win.doc.screens[0].nodes)


def test_project_with_components_roundtrip_via_ui(app_win):
    win, ctx, folder = app_win
    path = open_new(win, ctx, folder, "Сохранение")
    ed = win.project_page.editor
    build_button(ed)
    expected = json.loads(json.dumps(ed.doc.to_dict(), sort_keys=True), parse_int=float)
    expected["meta"].pop("modified_at")
    assert win.save_project() and win.close_project()
    win.open_project(str(path))
    got = json.loads(json.dumps(win.doc.to_dict(), sort_keys=True), parse_int=float)
    got["meta"].pop("modified_at")
    assert got == expected
