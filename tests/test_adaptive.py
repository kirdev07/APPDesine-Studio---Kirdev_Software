"""1.6: адаптивная вёрстка в Android-проекте — Scaffold, выравнивание по привязкам, прокрутка, планшет."""

from app.core.document.model import Node
from app.exporters.ai_export import ExportOptions, build_package
from app.exporters.android_project import ROOT, package_name
from app.libraries import components, screen_templates
from tests.test_android_export import _balanced
from tests.test_preview import doc_with_form


def _screen_src(doc, fn="FormaScreen"):
    f = build_package(doc, ExportOptions()).files
    base = f"{ROOT}/app/src/main/java/{package_name(doc.meta.title).replace('.', '/')}"
    return f[f"{base}/ui/screens/{fn}.kt"].decode()


def test_constraints_become_alignment_not_offsets():
    doc, _ = doc_with_form()
    s = doc.screens[0]
    W, H = s.width, s.height
    k = W / 411
    cases = {
        "Справа": dict(x=W - 16 * k - 100, y=200, constraint_h="right"),
        "По центру": dict(x=(W - 100) / 2, y=300, constraint_h="center"),
        "Масштаб": dict(x=0, y=400, w=W / 2, constraint_h="scale"),
        "Вся высота": dict(x=0, y=100, h=H - 200, constraint_v="top_bottom"),
        "Центр экрана": dict(x=(W - 100) / 2, y=(H - 100) / 2, constraint_h="center", constraint_v="center"),
        "Справа внизу": dict(x=W - 100, y=H - 100, constraint_h="right", constraint_v="bottom"),
    }
    for name, kw in cases.items():
        s.nodes.append(Node(type="rect", name=name, **{"w": 100, "h": 100, "fill": "#FF0000", **kw}))
    src = _screen_src(doc)
    assert _balanced(src)

    def block(name):
        i = src.index(f"// {name}")
        return src[i:src.index("Box(", i + 3) + 400]
    assert ".align(Alignment.TopEnd)" in block("Справа") and ".padding(end = 16.dp)" in block("Справа")
    assert ".align(Alignment.TopCenter)" in block("По центру")
    assert ".fillMaxWidth(0.5f)" in block("Масштаб")
    assert ".fillMaxHeight()" in block("Вся высота") and "top = " in block("Вся высота")
    assert ".align(Alignment.Center)" in block("Центр экрана") and ".offset" not in block("Центр экрана")
    assert ".align(Alignment.BottomEnd)" in block("Справа внизу")


def test_scaffold_slots_scroll_and_tablet_rail():
    doc, _ = doc_with_form()
    like = doc.screens[0]
    feed = screen_templates.build("feed", like, doc.meta.appearance)
    doc.screens.append(feed)
    src = _screen_src(doc, "SpisokLentaScreen")
    assert _balanced(src)
    for code in ("Scaffold(", "topBar = {", "TopAppBar(", "bottomBar = {", "if (!wide) {", "NavigationBar(",
                 "floatingActionButton = {", "FloatingActionButton(", "Row(modifier = Modifier.fillMaxSize().padding(inner))",
                 "if (wide) {", "NavigationRail {", "NavigationRailItem(",
                 "LocalConfiguration.current.screenWidthDp >= 600", "Modifier.widthIn(max = 600.dp).fillMaxSize()",
                 "LazyColumn(", "items(", "= listOf(",  # 1.34: лента одинаковых карточек — список из данных
                 '@Preview(name = "Планшет"',
                 '@Preview(name = "Маленький телефон"'):
        assert code in src, code
    assert "windowInsets = WindowInsets(0, 0, 0, 0)" not in src     # в слотах — системные отступы Scaffold
    assert src.count("NavigationBarItem(") == src.count("NavigationRailItem(") == 4
    # FAB — в слоте, а не на фиксированных координатах
    fab_part = src[src.index("floatingActionButton = {"):src.index(") { inner ->")]
    assert ".offset" not in fab_part and "modifier = Modifier," in fab_part


def test_fill_width_buttons_stay_full_width():
    doc, _ = doc_with_form()
    login = screen_templates.build("login", doc.screens[0], doc.meta.appearance)
    doc.screens.append(login)
    src = _screen_src(doc, "VhodScreen")
    i = src.index("Button(")
    assert ".fillMaxWidth()" in src[i:i + 300]
    # заготовка без «заполнить» остаётся по размеру текста
    doc2, _ = doc_with_form()
    doc2.screens[0].nodes.append(components.build("m3_button_filled", doc2.screens[0], doc2.meta.appearance))
    src2 = _screen_src(doc2)
    j = src2.index("Button(")
    assert ".fillMaxWidth()" not in src2[j:j + 200] and ".width(" not in src2[j:j + 200]
