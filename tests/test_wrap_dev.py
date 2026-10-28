"""1.24: раскладка с переносом (FlowRow) и раздел «Для разработчика» (свойства в dp и код Compose)."""

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import Node, Screen
from app.engines.layout import LayoutEngine, SimpleMeasurer
from app.exporters import dev_info
from app.exporters.ai_export import ExportOptions, build_package
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec


def _run(screen):
    changes, diags = LayoutEngine(SimpleMeasurer()).layout_screen(screen)
    m = tree.node_map(screen)
    for nid, props in changes.items():
        for k, v in props.items():
            setattr(m[nid], k, v)
    return diags


def _wrap(**kw):
    kids = [Node(type="rect", name=f"Чип {i}", w=100, h=40) for i in range(5)]
    kw.setdefault("h", 200)
    f = Node(type="frame", name="Чипы", x=0, y=0, w=300, layout="wrap", gap=8, row_gap=6,
             pad_t=10, pad_l=10, pad_r=10, pad_b=10, children=kids, **kw)
    return Screen(name="Э", platform="android", width=1080, height=2400, nodes=[f]), f, kids


def test_wrap_lines_and_hug_height():
    s, f, kids = _wrap(sizing_v="hug")
    diags = _run(s)
    # внутри 280: в строку помещается два по 100 (100 + 8 + 100), третий — на новую строку
    assert [(k.x, k.y) for k in kids] == [(10, 10), (118, 10), (10, 56), (118, 56), (10, 102)]
    assert f.h == pytest.approx(10 + 40 * 3 + 6 * 2 + 10)
    assert not [d for d in diags if d.severity == "warning"]


def test_wrap_center_and_overflow_warning():
    s, f, kids = _wrap(main_align="center", h=80)
    diags = _run(s)
    assert kids[0].x == pytest.approx(10 + (280 - 208) / 2)              # строка по центру
    assert kids[4].x == pytest.approx(10 + (280 - 100) / 2)              # последняя (один чип) — тоже
    assert any("строки не помещаются" in d.message for d in diags)


def test_wrap_hug_width_is_one_line():
    s, f, kids = _wrap(sizing_h="hug")
    _run(s)
    assert len({k.y for k in kids}) == 1 and f.w == pytest.approx(10 + 5 * 100 + 4 * 8 + 10)


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
    _, path = ctx.service.create(make_spec(projects_dir, title="Перенос"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_wrap_in_editor_and_compose(win):
    page, ed = win.project_page, win.project_page.editor
    f = ed.add_node("frame")
    ed.set_props({f.id: {"x": 0, "y": 0, "w": 600, "h": 400, "name": "Теги"}}, "место")
    fid, sid = f.id, ed.screen().id

    def tags(doc):
        tree.find(doc.screen(sid), fid)[0].children += [Node(type="rect", name=f"Тег {i}", w=180, h=80)
                                                         for i in range(6)]
    assert ed.patch("теги", tags)
    ed.select([f.id])
    page.inspector.refresh()
    insp = page.inspector
    insp.al_mode.setCurrentIndex(insp.al_mode.findData("wrap"))
    fr = tree.find(ed.screen(), f.id)[0]
    assert fr.layout == "wrap" and len(fr.children) == 6
    assert len({c.y for c in fr.children}) > 1                           # не влезли в одну строку
    assert not insp.al_row_gap.isHidden() and insp.al_cols.isHidden()
    src = "".join(v.decode() for k, v in build_package(ed.doc, ExportOptions()).files.items()
                  if k.endswith("Screen.kt"))
    assert "FlowRow(" in src and "verticalArrangement = Arrangement.spacedBy(" in src
    assert "ExperimentalLayoutApi::class" in src


def test_dev_section_spec_and_code(win, qtbot):
    page, ed = win.project_page, win.project_page.editor
    s = ed.screen()
    k = s.width / 411
    t = ed.add_node("text")
    ed.set_props({t.id: {"x": 16 * k, "y": 32 * k, "w": 200 * k, "h": 30 * k, "text": "Привет",
                         "font_size": 22 * k, "font_weight": 500}}, "текст")
    t = tree.find(ed.screen(), t.id)[0]
    rows = dict(dev_info.spec_rows(ed.doc, ed.screen(), t))
    assert rows["Положение"].startswith("x 16 dp") and "22 sp" in rows["Шрифт"] and "Medium" in rows["Шрифт"]
    code = dev_info.compose_snippet(ed.doc, ed.screen(), t.id)
    assert "Text(" in code and "\"Привет\"" in code
    ed.select([t.id])
    insp = page.inspector
    insp.refresh()
    assert not insp.sec_dev.isHidden() and insp.dev_code.isHidden()      # код — по кнопке, не всегда
    insp.dev_toggle.click()
    assert not insp.dev_code.isHidden() and "Text(" in insp.dev_code.toPlainText()
    insp.dev_copy_code.click()
    assert "Text(" in QApplication.clipboard().text()
    ed.select([])
    insp.refresh()
    assert insp.sec_dev.isHidden()


def test_text_on_role_fill_uses_on_color(win):
    """Белый текст на заливке primary — в коде onPrimary (в тёмной теме не станет цветом фона)."""
    ed = win.project_page.editor
    proj = dev_info._project(ed.doc, ed.screen())
    primary, on = proj.scheme["primary"], proj.scheme["onPrimary"]
    sid = ed.screen().id

    def add(doc):
        doc.screen(sid).nodes.append(Node(type="frame", name="Кнопка", layout="horizontal", x=0, y=0, w=200, h=60,
                                          fill=primary, children=[Node(type="text", name="Надпись", text="Купить",
                                                                       fill="", text_color=on, w=100, h=30)]))
    assert ed.patch("кнопка", add)
    btn = next(n for n in ed.screen().nodes if n.name == "Кнопка")
    t = btn.children[0]
    assert "colorScheme.onPrimary" in dev_info.compose_snippet(ed.doc, ed.screen(), btn.id)
    assert "colorScheme.onPrimary" in dict(dev_info.spec_rows(ed.doc, ed.screen(), t))["Цвет текста"]
    rows = dict(dev_info.spec_rows(ed.doc, ed.screen(), btn))
    assert rows["Размер"].startswith("200") or "dp" in rows["Размер"]
