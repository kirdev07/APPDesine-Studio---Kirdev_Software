"""1.13: нажатие переключает вариант — правило «При нажатии…», прототип, «Логика», код Android."""

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.behavior import Interaction, check_action
from app.core.document.model import ModelError, ROOT_REF
from app.engines.logic.engine import Interpreter, validate
from app.engines.logic.runtime import compose
from app.exporters.ai_export import ExportOptions, build_package
from app.exporters.android_project import ROOT, package_name
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec


def test_action_validation():
    a = check_action({"type": "set_variant", "node_id": "abc123", "axis": "Стиль", "value": ""})
    assert a == {"type": "set_variant", "node_id": "abc123", "axis": "Стиль", "value": ""}
    assert check_action({**a, "value": "Контур"})["value"] == "Контур"
    with pytest.raises(ModelError):
        check_action({**a, "axis": ""})


@pytest.fixture
def win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Кнопка", True))
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)

    def discard(x):
        x.project_page.mark_clean()
        x.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Нажатия"))
    w.open_project(str(path))
    yield w
    ctx.close()


def _button(win):
    page, ed = win.project_page, win.project_page.editor
    b = ed.insert_component("m3_button_icon")
    ed.select([b.id])
    page.make_variant_component()
    return ed.selected_nodes()[0]


def test_style_variant_switches_material_role(win):
    inst = _button(win)
    ed = win.project_page.editor
    defn = ed.doc.component(inst.component_id)
    assert defn.variants["Стиль"]["Контур"][ROOT_REF]["role"] == "m3.button_outlined"
    ed.set_instance_variant("Стиль", "Контур")
    assert ed.selected_nodes()[0].role == "m3.button_outlined"
    ed.set_instance_variant("Стиль", "Заливка")
    assert ed.selected_nodes()[0].role == defn.root.role                           # роль возвращается к мастеру


def test_tap_menu_prototype_and_compose(win):
    inst = _button(win)
    page, ed = win.project_page, win.project_page.editor
    # меню «При нажатии…» → «Переключить вариант» → «Стиль» → «Следующий по кругу»
    page._fill_tap_menu()
    sub = next(m for m in page._tap_submenus if m.title() == "Переключить вариант")
    acts = sub.actions()
    assert [a.text() for a in acts if a.isSeparator()] == ["Размер", "Стиль"]       # разделы по свойствам
    style_next = [a for a in acts if a.text() == "Следующий по кругу"][1]           # второе свойство — «Стиль»
    style_next.trigger()
    assert ed.tap_action(inst.id) == {"type": "set_variant", "node_id": inst.id, "axis": "Стиль", "value": ""}
    assert "Стиль" in page._tap_text(inst.id)
    assert not [d for d in validate(ed.doc) if d.level == "warning"]
    # прототип: нажатия идут по кругу Заливка → Тональный → Контур → Текст → Заливка
    it = Interpreter(ed.doc, ed.screen().id)
    seen = []
    for _ in range(4):
        effects = it.dispatch("tap", inst.id)
        assert effects and effects[0].kind == "state" and effects[0].data["axis"] == "Стиль"
        scr = compose(ed.doc, it.state, ed.engine)
        seen.append(tree.node_map(scr)[inst.id].role)
    assert seen == ["m3.button_tonal", "m3.button_outlined", "m3.button_text", "m3.button_filled"]
    # конкретное значение
    ed.set_tap_action(inst.id, {"type": "set_variant", "node_id": inst.id, "axis": "Размер", "value": "L"})
    it = Interpreter(ed.doc, ed.screen().id)
    it.dispatch("tap", inst.id)
    assert tree.node_map(compose(ed.doc, it.state, ed.engine))[inst.id].h == pytest.approx(inst.h * 1.25)
    it.dispatch("tap", inst.id)
    assert it.state.variants[inst.id] == {"Размер": "L"}
    # код Android: переменная варианта и when с видом каждой ветки
    ed.set_tap_action(inst.id, {"type": "set_variant", "node_id": inst.id, "axis": "Стиль", "value": ""})
    f = build_package(ed.doc, ExportOptions()).files
    base = f"{ROOT}/app/src/main/java/{package_name(ed.doc.meta.title).replace('.', '/')}/ui/screens/"
    src = next(v.decode() for k, v in f.items() if k.startswith(base) and b"when (variant" in v)
    assert 'by remember { mutableStateOf("Заливка") }' in src
    assert '= when (variant' in src and '"Заливка" -> "Тональный"' in src and 'else -> "Заливка"' in src
    for comp in ("FilledTonalButton(", "OutlinedButton(", "TextButton("):
        assert comp in src


def test_logic_studio_edits_variant_action(win):
    inst = _button(win)
    page, ed = win.project_page, win.project_page.editor
    from app.ui.studio.logic import LogicPage
    studio = win.findChildren(LogicPage)[0]
    studio.reset_for_document() if hasattr(studio, "reset_for_document") else None
    studio.work = {"id": "abcdef12", "screen_id": ed.screen().id, "trigger": "tap", "node_id": inst.id, "condition": None,
                   "actions": [], "_new": True}
    studio.a_type.setCurrentIndex(studio.a_type.findData("set_variant"))
    studio.add_action()
    a = studio.work["actions"][0]
    assert a["node_id"] == inst.id and a["axis"] == "Размер" and a["value"] == ""
    studio._set(0, "axis", "Стиль")
    assert a["value"] == ""
    studio._set(0, "value", "Текст")
    Interaction.from_dict({k: v for k, v in studio.work.items() if k != "_new"})


def test_size_variant_scales_material_button_in_compose(win):
    inst = _button(win)
    ed = win.project_page.editor
    ed.set_tap_action(inst.id, {"type": "set_variant", "node_id": inst.id, "axis": "Размер", "value": ""})
    f = build_package(ed.doc, ExportOptions()).files
    src = next(v.decode() for k, v in f.items() if b"when (variant" in v)
    assert '"M" -> "S"; "S" -> "L"; else -> "M"' in src
    assert ".height(32.dp)" in src and ".height(50.dp)" in src            # S и L; M — как у Material
    assert "fontSize = 11.2.sp" in src and "fontSize = 17.5.sp" in src
