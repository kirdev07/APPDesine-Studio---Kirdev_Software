"""1.19: ещё контента — графики (линия, столбцы, кольцо, карточка показателя) с данными в свойствах
и готовые экраны: календарь, карта, статистика, лента соцсети."""

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import Appearance, ModelError, Node, Screen, check_prop
from app.engines.layout import LayoutEngine
from app.exporters.ai_export import ExportOptions, build_package
from app.libraries import charts, components, screen_templates
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from app.ui.workspace.text_measure import QtTextMeasurer
from tests.conftest import make_spec

PHONE = Screen(name="s", platform="android", width=1080, height=2400)


def test_parse_and_model():
    assert charts.parse_values("12, 30; 18 40.5") == [12, 30, 18, 40.5]
    assert len(charts.parse_values(" ".join(["1"] * 40))) == charts.MAX_VALUES
    assert check_prop("data", "1 2.5 -3", "frame") == "1 2.5 -3"
    with pytest.raises(ModelError):
        check_prop("data", "1; drop", "frame")
    assert "data" not in Node(type="frame").to_dict()


def test_chart_builders():
    ap = Appearance(theme="light")
    bar = components.build("chart_bar", PHONE, ap)
    assert bar.role == "chart.bar" and bar.layout == "horizontal" and len(bar.children) == 7
    hs = [c.h for c in bar.children]
    assert hs.index(max(hs)) == 3 and all(c.sizing_h == "fill" for c in bar.children)   # 19 — самый высокий
    line = components.build("chart_line", PHONE, ap)
    assert [c.name for c in line.children] == ["Заливка под линией", "Линия"] and line.children[1].stroke
    donut = components.build("chart_donut", PHONE, ap)
    assert len(donut.children) == 4 and len({c.fill for c in donut.children}) == 4
    assert all("A" in c.path or "C" in c.path for c in donut.children)                 # дуги
    kpi = components.build("chart_kpi", PHONE, ap)
    assert any(n.role == "chart.line" for n, _, _ in tree.walk([kpi]))
    assert {s.kind for s in components.all_specs() if s.category == "Графики"} == \
        {"chart_line", "chart_bar", "chart_donut", "chart_kpi"}


@pytest.mark.parametrize("key", ["calendar", "map", "stats", "social"])
def test_new_screens_fit(qapp, key):
    for w, h in ((1080, 2400), (720, 1600)):
        s = screen_templates.build(key, Screen(name="x", platform="android", width=w, height=h),
                                   Appearance(theme="light"))
        _, diags = LayoutEngine(QtTextMeasurer()).layout_screen(s)
        assert not [d.message for d in diags if d.severity == "warning"]
    names = {n.name for n, _, _ in tree.walk(s.nodes)}
    if key == "calendar":
        assert "День 30" in names                                                        # шесть недель
    if key == "map":
        pins = [n for n, _, _ in tree.walk(s.nodes) if n.name.startswith("Метка")]
        assert pins and all(p.constraint_h == "center" for p in pins)                     # метки не сплющиваются


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
    _, path = ctx.service.create(make_spec(projects_dir, title="Графики"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_chart_data_in_inspector_and_export(win):
    page, ed = win.project_page, win.project_page.editor
    bar = ed.insert_component("chart_bar")
    ed.set_props({bar.children[0].id: {"fill": "#FF0000"}}, "цвет")                     # перекрасили столбец
    ed.select([bar.id])
    insp = page.inspector
    assert insp.sec_chart.isVisible() and insp.chart_data.text() == bar.data
    insp.chart_data.setText("1 2 3 10")
    insp.chart_data.editingFinished.emit()
    b = tree.find(ed.screen(), bar.id)[0]
    assert b.data == "1 2 3 10" and len(b.children) == 4 and b.children[0].fill == "#FF0000"   # цвет сохранён
    assert b.children[3].h > b.children[0].h * 5
    insp.chart_data.setText("5")                                                         # мало чисел — отказ
    insp.chart_data.editingFinished.emit()
    assert tree.find(ed.screen(), bar.id)[0].data == "1 2 3 10" and insp.chart_data.text() == "1 2 3 10"
    ed.undo()
    assert tree.find(ed.screen(), bar.id)[0].data != "1 2 3 10"
    ed.add_template_screen("stats")
    f = build_package(ed.doc, ExportOptions()).files
    src = "".join(v.decode() for k, v in f.items() if k.endswith("Screen.kt") and "Statistika" in k)
    assert "Canvas(" in src and "Row(" in src                                            # линия и столбцы
