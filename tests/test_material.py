"""1.2: Material 3 — схема цвета по цвету бренда, типографика, компоненты с ролями, экспорт в Compose."""

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.behavior import Interaction
from app.core.document.model import ModelError, Node
from app.engines.material.color import ROLES, contrast, hex_to_lch, scheme, tone
from app.engines.material.type_scale import TYPE_SCALE, role_of, style_name
from app.exporters.ai_export import ExportOptions, build_package
from app.exporters.android_project import ROOT, package_name
from app.exporters.compose_m3 import ROLES as COMPOSE_ROLES
from app.libraries import components
from app.libraries.m3_icons import ICONS
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from app.ui.workspace.panels import LayersPanel
from tests.conftest import make_spec
from tests.test_android_export import _balanced
from tests.test_preview import doc_with_form


def _dist(a: str, b: str) -> float:
    la, lb = hex_to_lch(a), hex_to_lch(b)
    return abs(la[0] - lb[0]) + abs(la[1] - lb[1]) / 4


def test_scheme_matches_material_baseline():
    s = scheme("#6750A4", dark=False, fidelity=False)  # эталонная схема Material 3 по цвету #6750A4
    for role, ref in (("primary", "#6750A4"), ("onPrimary", "#FFFFFF"), ("primaryContainer", "#EADDFF"),
                      ("secondary", "#625B71"), ("outline", "#79747E"), ("error", "#B3261E")):
        assert _dist(s[role], ref) < 6, (role, s[role], ref)
    for t in (10, 40, 80, 95):                       # тон — ровно светлота L*
        assert hex_to_lch(tone(300, 48, t))[0] == pytest.approx(t, abs=0.7)
    assert tone(120, 200, 50) and tone(0, 0, 0) == "#000000" and tone(0, 0, 100) == "#FFFFFF"
    d = scheme("#2F7BFF", dark=True)
    assert d["primary"] == "#2F7BFF" and set(d) == set(ROLES)
    assert hex_to_lch(d["surface"])[0] < 10 and hex_to_lch(scheme("#2F7BFF", False)["surface"])[0] > 95
    for bg, fg in (("primaryContainer", "onPrimaryContainer"), ("surface", "onSurface")):
        assert contrast(d[bg], d[fg]) >= 4.5      # пары ролей читаемы
    with pytest.raises(ValueError):
        scheme("красный", False)


def test_type_scale_names():
    assert len(TYPE_SCALE) == 15 and TYPE_SCALE["bodyLarge"][1:] == (16, 24, 400)
    assert role_of(style_name("labelSmall")) == "labelSmall" and role_of("Заголовок") is None


def test_components_have_roles_and_icons():
    doc, _ = doc_with_form()
    s = doc.screens[0]
    kinds = [sp.kind for sp in components.specs_for("android")]
    assert len(kinds) >= 30 + len(ICONS)
    for kind in kinds:
        n = components.build(kind, s, doc.meta.appearance)
        if kind.removeprefix("m3_icon_") in ICONS:
            assert n.type == "vector" and n.path
            continue
        assert n.role.startswith(("m3.", "chart.")) or kind == "chart_kpi", kind   # графики (1.19) — chart.*
        for d in tree.descendants(n):
            if d.type == "vector":
                assert d.path, kind
    for kind in ("m3_search_bar", "m3_divider", "m3_snackbar"):  # растягиваются по ширине с полями 16 dp
        n = components.build(kind, s, doc.meta.appearance)
        assert n.constraint_h == "left_right" and n.x > 0 and n.x + n.w == pytest.approx(s.width - n.x, abs=0.1)
        assert n.y > 0
    badge = components.build("m3_badge", s, doc.meta.appearance)
    ico = badge.children[0]
    assert ico.x > badge.x and ico.y > badge.y      # содержимое сдвигается вместе с корнем
    sw = components.build("m3_switch", s, doc.meta.appearance)
    raw = sw.to_dict()                                # роль сохраняется, пустая — не пишется
    assert raw["role"] == "m3.switch" and "role" not in raw["children"][0]
    assert Node.from_dict(raw).role == "m3.switch"
    with pytest.raises(ModelError):
        Node.from_dict({**raw, "role": "M3 Switch!"})


def test_compose_export_real_material_components():
    doc, ids = doc_with_form()
    s = doc.screens[0]
    added = {}
    for kind in ("m3_top_app_bar", "m3_switch", "m3_checkbox", "m3_radio", "m3_slider", "m3_chip_filter",
                 "m3_fab", "m3_button_tonal", "m3_tabs", "m3_segmented", "m3_snackbar", "m3_badge",
                 "m3_progress_linear", "m3_text_field", "m3_nav_bar", "m3_dialog"):
        n = components.build(kind, s, doc.meta.appearance)
        s.nodes.append(n)
        added[kind] = n
    nav = added["m3_nav_bar"]
    doc.interactions.append(Interaction(screen_id=s.id, node_id=nav.children[1].id, trigger="tap",
                                        actions=[{"type": "navigate", "screen_id": doc.screens[1].id,
                                                  "transition": "none", "duration": 0}]))
    doc.meta.appearance.theme = "amoled"
    f = build_package(doc, ExportOptions()).files
    p = package_name(doc.meta.title).replace(".", "/")
    base = f"{ROOT}/app/src/main/java/{p}"
    src = f[f"{base}/ui/screens/FormaScreen.kt"].decode()
    from tests.conftest import inline_strings
    src = inline_strings(src, f)
    assert _balanced(src)
    for call in ("TopAppBar(", "Switch(checked = ", "Checkbox(checked = ", "RadioButton(selected = ", "Slider(value = ",
                 "FilterChip(", "FloatingActionButton(", "FilledTonalButton(", "PrimaryTabRow(", "SegmentedButton(",
                 "BadgedBox(", "LinearProgressIndicator(", "OutlinedTextField(", "NavigationBar(",
                 "NavigationBarItem(", "DesignIcon(", "@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)",
                 "contentColor = MaterialTheme.colorScheme.onBackground", "bottomBar = {", "NavigationRail {",
                 "topBar = {", "Scaffold("):
        assert call in src, call
    snack = src[src.index("// Всплывающее сообщение"):]
    assert ".padding(start = 16.dp, end = 16.dp)" in snack[:400] and ".fillMaxWidth()" in snack[:400]
    items = src.split("NavigationBarItem(")
    assert 'onNavigate("screen2"' not in items[1] and 'onNavigate("screen2", NavMotion("none", 0, ' in items[2]  # переход у второго пункта
    assert "Column(" in src and "Удалить черновик?" in src                    # диалог — общей раскладкой
    theme = f[f"{base}/ui/theme/Theme.kt"].decode()
    assert "lightColorScheme(" in theme and "darkColorScheme(" in theme and "surfaceContainerHighest = " in theme
    assert "shadow =" not in theme and "const val DesignIsDark = true" in theme and _balanced(theme)
    assert "typography = AppTypography" in theme and "val AppTypography = Typography()" in \
        f[f"{base}/ui/theme/Type.kt"].decode()
    icon = f[f"{base}/ui/components/DesignIcon.kt"].decode()
    assert "fun DesignIcon(" in icon and "PathFillType.EvenOdd" in icon and _balanced(icon)
    assert "SystemBarStyle.dark" in f[f"{base}/MainActivity.kt"].decode()
    for kind, comp in COMPOSE_ROLES.items():
        assert kind.startswith("m3.") and (comp is None or comp)


@pytest.fixture
def app_win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)

    def discard(win):
        win.project_page.mark_clean()
        win.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.resize(1500, 950)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Материал"))
    w.open_project(str(path))
    yield w, w.project_page.editor, ctx
    ctx.close()


def test_scheme_tokens_typography_and_component_search(qtbot, app_win, monkeypatch):
    win, ed, ctx = app_win
    n = ed.add_material_colors("#6750A4", ("light", "dark"))
    assert n == 2 * len(ROLES) and len(ed.doc.colors) == n
    assert ed.add_material_colors("#00897B", ("dark",)) == len(ROLES) and len(ed.doc.colors) == n  # обновление
    prim = next(c for c in ed.doc.colors if c.name == "M3 тёмная · Основной (primary)")
    assert prim.value == "#00897B"
    ed.undo()
    # тёмный цвет бренда в тёмной теме — светлый тон (на тёмном фоне читается), а не сам #6750A4
    from app.engines.material.color import contrast, scheme
    back = next(c for c in ed.doc.colors if c.name == prim.name).value
    assert back == scheme("#6750A4", True)["primary"] != "#6750A4"
    assert contrast(back, scheme("#6750A4", True)["surface"]) >= 3
    assert ed.add_material_typography() == 15 and ed.add_material_typography() == 15
    styles = [t for t in ed.doc.text_styles if t.name.startswith("M3 · ")]
    assert len(styles) == 15
    body = next(t for t in styles if role_of(t.name) == "bodyLarge")
    assert body.font_size > 16 and body.font_weight == 400                    # sp → px по плотности экрана
    f = build_package(ed.doc, ExportOptions()).files
    typ = next(v for k, v in f.items() if k.endswith("ui/theme/Type.kt")).decode()
    assert "bodyLarge = " in typ and "displayLarge = " in typ and _balanced(typ)
    # страница «Цвета»: диалог схемы
    from app.ui.studio.material import MaterialSchemeDialog
    dlg = MaterialSchemeDialog("#2F7BFF", True)
    assert dlg.variants() == ("dark",) and dlg.fidelity()
    dlg.which.setCurrentIndex(1)
    assert dlg.variants() == ("light", "dark")
    dlg.deleteLater()
    monkeypatch.setattr(MaterialSchemeDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    before = len(ed.doc.colors)
    win.colors.material_scheme()                                              # тема проекта — одна схема
    assert "токенов" in win.colors.status.text() and len(ed.doc.colors) == before  # имена уже есть — обновлены
    # поиск компонентов на рабочей области
    lp = win.findChildren(LayersPanel)[0]
    lp.comp_filter.setText("переключ")
    shown = lp.gallery.visible_names()
    assert "Переключатель" in shown and all("ереключат" in n for n in shown)
    lp.comp_filter.clear()
    assert all(not lp.components.item(i).isHidden() for i in range(lp.components.count()))
