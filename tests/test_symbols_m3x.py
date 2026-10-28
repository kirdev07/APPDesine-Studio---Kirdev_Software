"""1.8: Material Symbols (~3900 значков) и варианты компонентов Material 3."""

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import Node
from app.exporters.ai_export import ExportOptions, build_package
from app.exporters.android_project import ROOT, package_name
from app.libraries import components, symbols
from app.libraries.components_m3x import SPECS as M3X
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from app.ui.workspace.symbol_picker import SymbolPicker
from tests.conftest import make_spec
from tests.test_android_export import _balanced
from tests.test_preview import doc_with_form


def test_symbols_library_search_and_paths():
    assert symbols.available() and len(symbols.names()) > 3500 and symbols.version()
    assert symbols.search("")[:3] == ["home", "search", "menu"]                 # популярные — первыми
    assert "shopping_cart" in symbols.search("корзина")
    assert symbols.search("стрелка назад")[0] == "arrow_back"
    assert symbols.search("shopping cart")[0] == "shopping_cart"
    for style in symbols.STYLES:
        d = symbols.path("home", style, filled=True)
        n = Node.from_dict(Node(type="vector", path=d, vb_w=960, vb_h=960).to_dict())   # путь проходит проверку
        assert n.path and min(float(t) for t in d.replace("M", " ").replace("L", " ").replace("C", " ")
                              .replace("Z", " ").split()) >= 0                       # сдвинут в 0…960
    assert symbols.path("home") != symbols.path("home", filled=True)
    assert symbols.LICENSE.exists() and "Apache" in symbols.LICENSE.read_text(encoding="utf-8")[:400]


def test_m3_variants_and_compose_mapping():
    doc, _ = doc_with_form()
    s = doc.screens[0]
    for sp in M3X:
        n = components.build(sp.kind, s, doc.meta.appearance)
        assert n.role.startswith("m3."), sp.kind
        for d in tree.descendants(n):
            if d.type == "vector":
                assert d.path, sp.kind
    assert components.build("m3_button_elevated", s, doc.meta.appearance).elevation == 1
    tabs = components.build("m3_tabs_icons", s, doc.meta.appearance)
    assert [d.vb_w for d in tree.descendants(tabs) if d.type == "vector"] == [960, 960, 960]  # значки Material
    for kind in ("m3_button_elevated", "m3_icon_button_filled", "m3_icon_button_tonal", "m3_icon_button_outlined",
                 "m3_fab_small", "m3_chip_suggestion", "m3_chip_input", "m3_text_field_filled"):
        s.nodes.append(components.build(kind, s, doc.meta.appearance))
    s.nodes.append(components.build("m3_top_bar_large", s, doc.meta.appearance))
    f = build_package(doc, ExportOptions()).files
    src = f[f"{ROOT}/app/src/main/java/{package_name(doc.meta.title).replace('.', '/')}/ui/screens/FormaScreen.kt"]\
        .decode()
    assert _balanced(src)
    for code in ("ElevatedButton(", "FilledIconButton(", "FilledTonalIconButton(", "OutlinedIconButton(",
                 "SmallFloatingActionButton(", "SuggestionChip(", "InputChip(", "TextField(", "LargeTopAppBar(",
                 "topBar = {"):
        assert code in src, code
    cats = [sp.category for sp in components.specs_for("android")]
    seen = []
    for c in cats:                                                              # категории идут подряд
        if not seen or seen[-1] != c:
            assert c not in seen, c
            seen.append(c)


@pytest.fixture
def win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)

    def discard(x):
        x.project_page.mark_clean()
        x.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Значки"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_picker_insert_and_replace_symbol(qtbot, win, monkeypatch):
    page, ed = win.project_page, win.project_page.editor
    d = SymbolPicker()
    d.search.setText("корзина")
    d.refresh()
    assert 0 < d.model.rowCount() < 40 and d.model.data(d.model.index(0), 0x0100)
    assert not d.model.data(d.model.index(0), 1).isNull()                   # картинка значка
    d.deleteLater()
    node = ed.insert_symbol("shopping_cart", "rounded", True, 32)
    k = ed.screen().width / 411
    assert node.type == "vector" and node.vb_w == 960 and node.w == pytest.approx(32 * k, abs=0.5)
    assert node.name == "Покупки" or node.name
    assert page.sel_buttons[0].isVisible()                                   # кнопка «Значок…» у значка
    old = tree.find(ed.screen(), node.id)[0].path
    assert ed.replace_symbol(node.id, "favorite", "outlined", False)
    n = tree.find(ed.screen(), node.id)[0]
    assert n.path != old and n.w == pytest.approx(32 * k, abs=0.5)
    ed.undo()
    assert tree.find(ed.screen(), node.id)[0].path == old
    monkeypatch.setattr(SymbolPicker, "exec", lambda self: (setattr(self, "name", "home"), 1)[1])
    page.symbols_dialog()
    assert ed.screen().nodes[-1].type == "vector" and ed.screen().nodes[-1].name == "Дом"
