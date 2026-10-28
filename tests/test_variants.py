"""1.12: компоненты с вариантами — свойства «Размер», «Стиль», «Тема» и свои; выбор у копии, сохранение, код."""

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import ROOT_REF, ComponentDef, ModelError, Node, Screen, check_variants
from app.engines.components import engine as ce
from app.exporters.ai_export import ExportOptions, build_package
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec


def test_model_validation_and_roundtrip():
    root = Node(type="frame", w=100, h=40)
    d = ComponentDef(name="К", root=root, variants={"Размер": {"M": {}, "L": {ROOT_REF: {"h": 50, "gap": 8}}}})
    back = ComponentDef.from_dict(d.to_dict())
    assert back.variants == d.variants
    assert "variants" not in ComponentDef(name="К", root=Node(type="frame")).to_dict()   # пусто — не пишется
    with pytest.raises(ModelError):
        check_variants({"Размер": {}})                                       # нет значений
    with pytest.raises(ModelError):
        check_variants({"Размер": {"M": {ROOT_REF: {"component_id": "x"}}}})  # запрещённое свойство
    with pytest.raises(ModelError):
        check_variants({str(i): {"a": {}} for i in range(9)})                # больше 8 свойств
    n = Node.from_dict({**Node(type="instance", component_id="c", variant={"Размер": "L"}).to_dict()})
    assert n.variant == {"Размер": "L"}
    assert "variant" not in Node(type="frame").to_dict()


def test_variant_overrides_default_and_merge():
    d = ComponentDef(name="К", root=Node(type="frame"), variants={
        "Размер": {"M": {}, "L": {ROOT_REF: {"radius": 20}}},
        "Стиль": {"Заливка": {ROOT_REF: {"fill": "#111111"}}, "Контур": {ROOT_REF: {"fill": "", "radius": 4}}}})
    assert ce.variant_overrides(d, {}) == {ROOT_REF: {"fill": "#111111"}}            # первые значения
    assert ce.variant_overrides(d, {"Размер": "L", "Стиль": "Контур"}) == {ROOT_REF: {"radius": 4, "fill": ""}}
    assert ce.variant_overrides(d, {"Размер": "нет такого"}) == {ROOT_REF: {"fill": "#111111"}}


@pytest.fixture
def win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)

    def discard(x):
        x.project_page.mark_clean()
        x.builder.editor.stack.set_clean() if x.builder.editor.stack else None
        x.builder._states_dirty = False
        x.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Варианты"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_make_switch_undo_and_export(qtbot, win, monkeypatch):
    page, ed = win.project_page, win.project_page.editor
    b = ed.insert_component("m3_button_icon")
    ed.select([b.id])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Моя кнопка", True))
    page.make_variant_component()
    inst = ed.selected_nodes()[0]
    cid = inst.component_id
    defn = ed.doc.component(cid)
    assert list(defn.variants) == ["Размер", "Стиль"] and list(defn.variants["Размер"]) == ["M", "S", "L"]
    h0 = inst.h
    # переключение в свойствах
    insp = page.inspector
    assert insp.variant_form.rowCount() == 2 and not insp.variant_box.isHidden()
    ed.set_instance_variant("Размер", "L")
    big = ed.selected_nodes()[0]
    assert big.h == pytest.approx(h0 * 1.25) and big.variant == {"Размер": "L"}
    ed.set_instance_variant("Стиль", "Контур")
    big = ed.selected_nodes()[0]
    assert big.stroke and not big.fill and big.h == pytest.approx(h0 * 1.25)   # свойства складываются
    ed.set_instance_variant("Размер", "M")
    assert ed.selected_nodes()[0].h == pytest.approx(h0)                        # размер возвращается
    ed.undo()
    assert ed.selected_nodes()[0].h == pytest.approx(h0 * 1.25)
    # тема как готовый набор из меню свойств
    ed.select([inst.id])
    assert ed.add_variant_preset(cid, "theme")
    assert "Тема" in ed.doc.component(cid).variants
    # сохранение: варианты и выбор у копии переживают перезапись файла
    scr = Screen.from_dict(ed.screen().to_dict())
    i2 = next(n for n, _, _ in tree.walk(scr.nodes) if n.id == inst.id)
    d2 = ComponentDef.from_dict(ed.doc.component(cid).to_dict())
    assert i2.variant.get("Стиль") == "Контур" and d2.variants == ed.doc.component(cid).variants
    # код Android строится из материализованной копии
    files = build_package(ed.doc, ExportOptions()).files
    assert any(k.endswith(".kt") for k in files)


def test_builder_variants_tab(qtbot, win, monkeypatch):
    page, ed = win.project_page, win.project_page.editor
    b = ed.insert_component("m3_button_icon")
    ed.select([b.id])
    cid = ed.create_component("Кнопка")
    bl = win.builder
    assert bl.open_component(cid)
    bl.preset_variants("size")
    assert list(bl.variants) == ["Размер"]
    answers = iter([("Акцент", True), ("Нет, Да", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: next(answers))
    bl.add_variant_axis()
    assert list(bl.variants["Акцент"]) == ["Нет", "Да"]
    # выбрать «Да» и задать заливку корня
    row = next(i for i in range(bl.variant_list.count()) if bl.variant_list.item(i).data(0x0100) == ("Акцент", "Да"))
    bl.variant_list.setCurrentRow(row)
    bl.v_node.setCurrentIndex(0)
    bl.v_prop.setCurrentIndex(bl.v_prop.findData("fill"))
    bl.v_value.setText("#FF0000")
    bl.add_variant_override()
    assert bl.variants["Акцент"]["Да"] == {ROOT_REF: {"fill": "#FF0000"}}
    bl.v_prop.setCurrentIndex(bl.v_prop.findData("h"))
    bl.v_value.setText("60")
    bl.add_variant_override()
    assert bl.variants["Акцент"]["Да"][ROOT_REF]["h"] == 60
    # предпросмотр: по умолчанию + S, L + Да
    assert bl.preview.count() >= 4
    assert bl.save()
    assert ed.doc.component(cid).variants["Акцент"]["Да"][ROOT_REF]["fill"] == "#FF0000"
    # копия в проекте переключается на новое значение
    inst = next(n for n, _, _ in tree.walk(ed.screen().nodes) if n.component_id == cid)
    ed.select([inst.id])
    ed.set_instance_variant("Акцент", "Да")
    got = ed.selected_nodes()[0]
    assert got.fill == "#FF0000" and got.h == pytest.approx(60)
    # удаление свойства
    bl.variant_list.setCurrentRow(0)
    bl.remove_variant()
    assert list(bl.variants) == ["Акцент"]
