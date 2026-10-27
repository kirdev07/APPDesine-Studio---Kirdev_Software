"""Компоненты, экземпляры, переопределения, состояния, ресурсы, библиотека, шаблоны (S14, S18)."""

import hashlib
import json
import zipfile

import pytest

from app.core.commands import DocPatch, UndoStack
from app.core.document import tree
from app.core.document.model import ROOT_REF, Asset, ModelError, Node, TextStyle
from app.core.persistence.container import load_project, save_project
from app.core.project.service import build_document
from app.core.project.templates import TemplateStore
from app.engines.components import engine as ce
from app.engines.components.library import PersonalLibrary, install_bundle, make_bundle, read_bundle_file, write_bundle_file
from app.engines.layout import LayoutEngine, SimpleMeasurer
from tests.conftest import make_spec

ENG = LayoutEngine(SimpleMeasurer())
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 2 L22 2 L12 22 Z"/></svg>'


def button_nodes():
    label = Node(type="text", name="Подпись", text="Купить", fill="", sizing_h="hug", sizing_v="hug",
                 font_size=16, text_color="#FFFFFF")
    icon = Node(type="image", name="Значок", w=20, h=20, asset_id="", fill="")
    btn = Node(type="frame", name="Кнопка", x=40, y=40, w=100, h=48, layout="horizontal", gap=8, pad_l=16,
               pad_r=16, cross_align="center", sizing_h="hug", fill="#2F7BFF", radius=24, children=[icon, label])
    return btn, label, icon


@pytest.fixture
def doc(tmp_path):
    d = build_document(make_spec(tmp_path))
    a = Asset(kind="icon", name="Стрелка", ext="svg", sha256=hashlib.sha256(SVG).hexdigest(), size=len(SVG),
              license="MIT", redistribution="allowed")
    d.assets.append(a)
    d.asset_data[a.id] = SVG
    d.text_styles.append(TextStyle(name="Кнопка", font_family="Segoe UI", font_size=16, font_weight=600,
                                   id="style_button"))
    btn, label, icon = button_nodes()
    icon.asset_id = a.id
    label.text_style = "style_button"
    d.screens[0].nodes.append(btn)
    return d


def comp(doc):
    s = doc.screens[0]
    defn, inst = ce.create_component(doc, s, [s.nodes[0].id], "Кнопка", ENG)
    return s, defn, inst


def test_create_component_replaces_selection_with_instance(doc):
    s, defn, inst = comp(doc)
    assert s.nodes == [inst] and inst.is_instance and inst.component_id == defn.id
    assert [c.ref for c in inst.children] == [c.id for c in defn.root.children]
    assert all(c.id.startswith(inst.id + ":") for c in inst.children)
    assert (inst.x, inst.y) == (40, 40) and inst.fill == "#2F7BFF"
    doc.validate()


def test_instance_overrides_survive_master_change(doc):  # S14
    s, defn, inst = comp(doc)
    label = inst.children[1]
    ce.set_overrides(doc, s, {label.id: {"text": "Оплатить заказ", "text_color": "#000000"}}, ENG)
    inst = s.nodes[0]
    assert inst.children[1].text == "Оплатить заказ"
    w_override = inst.w
    # мастер меняется: новый цвет и скругление, подпись мастера другая
    defn.root.fill = "#00AA55"
    defn.root.children[1].text = "Купить сейчас"
    defn.root.children[1].font_size = 20
    ce.sync_instances(doc, ENG)
    inst = s.nodes[0]
    assert inst.fill == "#00AA55"                       # из мастера
    assert inst.children[1].text == "Оплатить заказ"    # переопределение сохранилось
    assert inst.children[1].text_color == "#000000"
    assert inst.children[1].font_size == 20            # не переопределено — из мастера
    assert inst.w != w_override                         # раскладка пересчитана
    ce.reset_overrides(doc, inst, ENG)
    assert s.nodes[0].children[1].text == "Купить сейчас"


def test_structural_override_rejected(doc):
    s, defn, inst = comp(doc)
    with pytest.raises(ModelError):
        ce.set_overrides(doc, s, {inst.children[0].id: {"x": 5}}, ENG)


def test_states_apply_on_top_of_master(doc):
    s, defn, inst = comp(doc)
    ce.preset_states(defn)
    assert {"hover", "pressed", "focus", "disabled", "loading", "error"} <= set(defn.states)
    inst.state = "disabled"
    ce.sync_instances(doc, ENG)
    assert s.nodes[0].opacity == 0.38
    inst = s.nodes[0]
    inst.state = "loading"
    ce.sync_instances(doc, ENG)
    assert s.nodes[0].children[1].text == "Загрузка…"
    inst = s.nodes[0]
    ce.set_overrides(doc, s, {inst.id: {"fill": "#123456"}}, ENG)
    assert s.nodes[0].overrides[ROOT_REF] == {"fill": "#123456"}


def test_nested_components_and_cycle_detection(doc):
    s, button, inst = comp(doc)
    title = Node(type="text", name="Заголовок", text="Карточка", fill="", sizing_h="hug", sizing_v="hug")
    card = Node(type="frame", name="Карточка", x=0, y=200, w=300, h=200, layout="vertical", gap=8, pad_t=16,
                pad_l=16, sizing_v="hug", children=[title])
    s.nodes.append(card)
    # кладём экземпляр кнопки в карточку и делаем карточку компонентом
    s.nodes.remove(inst)
    card.children.append(inst)
    cdef, cinst = ce.create_component(doc, s, [card.id], "Карточка", ENG)
    nested = cinst.children[1]
    assert nested.is_instance and nested.component_id == button.id
    # изменение кнопки доходит до вложенного экземпляра в карточке на экране
    button.root.fill = "#FF0000"
    ce.sync_instances(doc, ENG)
    assert s.nodes[0].children[1].fill == "#FF0000"
    # переопределение текста вложенной кнопки хранится во внешнем экземпляре
    inner_label = s.nodes[0].children[1].children[1]
    ce.set_overrides(doc, s, {inner_label.id: {"text": "Подробнее"}}, ENG)
    ce.sync_instances(doc, ENG)
    assert s.nodes[0].children[1].children[1].text == "Подробнее"
    # цикл: кнопка содержит карточку
    button.root.children.append(ce.make_instance(cdef, 0, 0, ENG))
    with pytest.raises(ModelError, match="сам себя"):
        ce.sync_instances(doc, ENG)


def test_save_load_roundtrip_with_assets_and_components(doc, tmp_path):
    s, defn, inst = comp(doc)
    ce.preset_states(defn)
    p = tmp_path / "компоненты.adsproj"
    save_project(doc, p)
    loaded = load_project(p)
    assert loaded.to_dict() == doc.to_dict()
    assert loaded.asset_data == doc.asset_data
    with zipfile.ZipFile(p) as zf:
        names = zf.namelist()
    assert f"components/{defn.id}.json" in names
    assert doc.assets[0].archive_path in names


def test_missing_asset_file_does_not_block_open(doc, tmp_path):
    p = tmp_path / "p.adsproj"
    save_project(doc, p)
    broken = tmp_path / "broken.adsproj"
    with zipfile.ZipFile(p) as src, zipfile.ZipFile(broken, "w") as dst:
        for item in src.infolist():
            if not item.filename.startswith("assets/icons/"):
                dst.writestr(item, src.read(item))
    loaded = load_project(broken)
    assert loaded.assets and loaded.assets[0].id not in loaded.asset_data


def canon(doc) -> str:
    # снимок нормализует числа (20 → 20.0), поэтому сравниваем по значению
    return json.dumps(json.loads(json.dumps(doc.to_dict()), parse_int=float), sort_keys=True)


def test_docpatch_undo_redo_exact(doc):
    st = UndoStack(doc)
    before = canon(doc)
    holder = {}

    def mutate(d):
        holder["defn"], _ = ce.create_component(d, d.screens[0], [d.screens[0].nodes[0].id], "Кнопка", ENG)
    st.push(DocPatch("Создать компонент", mutate))
    after = canon(doc)
    st.undo()
    assert canon(doc) == before
    st.redo()
    assert canon(doc) == after

    def boom(d):
        d.components.clear()
        raise ModelError("ошибка")
    with pytest.raises(ModelError):
        st.push(DocPatch("Сбой", boom))
    assert canon(doc) == after  # частичное изменение откатилось


def test_reuse_across_projects_via_personal_library(doc, tmp_path):  # критерий приёмки этапа 4
    s, defn, inst = comp(doc)
    lib = PersonalLibrary(tmp_path / "Библиотека")
    warnings = lib.save(doc, defn.id)
    assert warnings == []
    assert [i["name"] for i in lib.items()] == ["Кнопка"]
    other = build_document(make_spec(tmp_path, title="Другой проект"))
    bundle, files = lib.load(defn.id)
    warnings = install_bundle(other, bundle, files, ENG)
    # единственное допустимое замечание — системный шрифт не входит в проект
    assert [w for w in warnings if not w.startswith("Шрифт")] == []
    got = other.component(defn.id)
    assert got is not None and got.root.fill == "#2F7BFF"
    assert other.text_style("style_button").font_weight == 600     # стиль приехал
    asset = other.assets[0]
    assert other.asset_data[asset.id] == SVG and asset.license == "MIT"  # ресурс и лицензия приехали
    inst2 = ce.make_instance(got, 10, 10, ENG)
    other.screens[0].nodes.append(inst2)
    assert inst2.children[1].text == "Купить"
    p = tmp_path / "другой.adsproj"
    save_project(other, p)
    assert load_project(p).component(defn.id).name == "Кнопка"


def test_missing_assets_are_warned_on_export_and_import(doc, tmp_path):
    s, defn, inst = comp(doc)
    doc.asset_data.clear()               # файл ресурса потерян
    doc.assets[0].redistribution = "unknown"
    bundle, files, warnings = make_bundle(doc, defn.id)
    assert any("отсутствует" in w for w in warnings)
    assert any("Лицензия" in w for w in warnings)
    path = tmp_path / "кнопка.adscomp"
    write_bundle_file(path, bundle, files)
    b2, f2 = read_bundle_file(path)
    other = build_document(make_spec(tmp_path, title="Третий"))
    warnings = install_bundle(other, b2, f2, ENG)
    assert any("Отсутствует ресурс" in w for w in warnings)


def test_bundle_file_is_validated(tmp_path):
    p = tmp_path / "evil.adscomp"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("bundle.json", "{}")
        zf.writestr("../evil.txt", "x")
    with pytest.raises(ModelError):
        read_bundle_file(p)


def test_text_style_propagates_to_masters_and_instances(doc):
    s, defn, inst = comp(doc)
    doc.text_style("style_button").font_size = 22
    n = ce.apply_text_style(doc, "style_button", ENG)
    assert n == 1  # подпись в мастере
    assert defn.root.children[1].font_size == 22
    assert s.nodes[0].children[1].font_size == 22


def test_detach_instance(doc):
    s, defn, inst = comp(doc)
    ce.detach(inst)
    assert inst.type == "frame" and not inst.component_id and all(not c.ref for c in inst.children)
    doc.validate()


def test_user_templates(doc, tmp_path, service, projects_dir):
    s, defn, inst = comp(doc)
    store = TemplateStore(tmp_path / "Шаблоны")
    store.save(doc, "Магазин")
    items = store.items()
    assert [t.title for t in items] == ["Магазин"]
    spec = make_spec(projects_dir, title="Из шаблона")
    spec.template_path = items[0].path
    new, path = service.create(spec)
    assert new.meta.id != doc.meta.id and new.meta.title == "Из шаблона"
    assert new.screens[0].id != doc.screens[0].id
    assert load_project(path).component(defn.id) is not None
    assert tree.node_map(new.screens[0])
