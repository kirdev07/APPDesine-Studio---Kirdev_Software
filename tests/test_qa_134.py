"""1.34: списки из данных, сохранение состояния, понятные маршруты, подписи TalkBack ресурсами, переключатель
Material 1, анимация обводки и градиента, фигуры виджетов картинкой."""

from app.core.document.behavior import Animation, Interaction, Keyframe, Track
from app.core.document.model import Appearance, Node, Screen
from app.exporters.ai_export import ExportOptions, build_package
from app.exporters.android_project import ROOT, package_name, route_names
from app.exporters.glance import PART_PREFIX, needs_backdrop
from app.libraries import components
from tests.test_android_export import _balanced
from tests.test_preview import doc_with_form


def _files(doc, previews=None):
    f = build_package(doc, ExportOptions(), None, previews).files
    return f, f"{ROOT}/app/src/main/java/{package_name(doc.meta.title).replace('.', '/')}"


def _row(i):
    return Node(type="frame", name=f"Строка {i}", layout="horizontal", w=400, h=72, gap=12, sizing_h="fill",
                fill="#EEEEEE" if i % 2 else "#DDDDDD",
                children=[Node(type="text", name="Имя", text=f"Контакт {i}", fill="", w=200, h=24),
                          Node(type="text", name="Статус", text="в сети", fill="", w=100, h=20)])


def test_repeating_cards_become_lazy_column_with_data():
    doc, _ = doc_with_form()
    s = doc.screens[0]
    rows = [_row(i) for i in range(5)]
    lst = Node(type="frame", name="Контакты", layout="vertical", scroll="vertical", x=0, y=200, w=400, h=600,
               gap=8, pad_t=8, pad_l=8, pad_r=8, pad_b=8,
               children=[Node(type="text", name="Заголовок", text="Все контакты", fill="", w=300, h=30)] + rows)
    s.nodes.append(lst)
    doc.interactions.append(Interaction(screen_id=s.id, trigger="tap", node_id=rows[1].id, actions=[
        {"type": "navigate", "screen_id": doc.screens[1].id, "transition": "none", "duration": 0, "easing": "linear"}]))
    f, base = _files(doc)
    src = next(v.decode() for k, v in f.items() if k.startswith(f"{base}/ui/screens/") and b"LazyColumn(" in v)
    assert _balanced(src)
    assert "private data class" in src and "val textImya: String" in src and "val fill" in src  # имя, заливка
    assert "val textStatus" not in src                                     # одинаковый текст — в шаблоне строки
    assert "val onClick: () -> Unit" in src and "item.onClick()" in src     # нажатие — своё у каждой строки
    assert "items(kontaktyItems) { item ->" in src and "item {" in src      # заголовок — отдельный item
    assert "contentPadding = PaddingValues(" in src and ".verticalScroll(" not in src.split("LazyColumn(")[1][:400]
    strings = f[f"{ROOT}/app/src/main/res/values/strings.xml"].decode()
    assert ">Контакт 3<" in strings                                         # данные — строковые ресурсы


def test_cards_with_own_behaviour_stay_a_column():
    doc, _ = doc_with_form()
    s = doc.screens[0]
    rows = [_row(i) for i in range(4)]
    s.nodes.append(Node(type="frame", name="Контакты", layout="vertical", scroll="vertical", w=400, h=600,
                        children=rows))
    doc.interactions.append(Interaction(screen_id=s.id, trigger="tap", node_id=rows[0].id, actions=[
        {"type": "set_visible", "node_id": rows[2].children[1].id, "mode": "toggle"}]))
    f, base = _files(doc)
    assert not any(b"LazyColumn(" in v for k, v in f.items() if k.startswith(f"{base}/ui/screens/"))


def test_routes_saveable_state_and_talkback_resources():
    assert list(route_names([Screen(name=n, platform="android", width=1, height=1) for n in
                             ("Корзина товаров", "Корзина товаров", "123", "")]).values()) == \
        ["korzina-tovarov", "korzina-tovarov-2", "s-123", "screen4"]
    doc, _ = doc_with_form()
    f, base = _files(doc)
    nav = f[f"{base}/navigation/AppNavHost.kt"].decode()
    assert "rememberSaveable(saver = StackSaver)" in nav and "rememberSaveable(saver = AppState.Saver)" in nav
    assert '"forma" -> FormaScreen' in nav
    assert "val Saver = listSaver<AppState, Any>(" in f[f"{base}/AppState.kt"].decode()
    act = f[f"{base}/MainActivity.kt"].decode()
    assert "://screen2" not in act


def test_material1_switch_classic_look_and_code():
    s = Screen(name="Экран", platform="android", width=1080, height=2400, device_id="pixel_7")
    sw = components.build("m3_switch", s, Appearance(material="m1"))
    track = next(d for d in sw.children if d.is_frame)
    assert track.h < track.children[0].h and not track.clip                 # бегунок выступает за дорожку
    doc, _ = doc_with_form()
    doc.meta.appearance.material = "m1"
    doc.screens[0].nodes.append(components.build("m3_switch", doc.screens[0], doc.meta.appearance))
    f, base = _files(doc)
    assert f"{base}/ui/components/ClassicSwitch.kt" in f
    assert any(b"ClassicSwitch(checked = " in v for k, v in f.items() if k.startswith(f"{base}/ui/screens/"))
    doc.meta.appearance.material = "m3"
    f, base = _files(doc)
    assert f"{base}/ui/components/ClassicSwitch.kt" not in f


def test_stroke_and_gradient_animation_become_code():
    doc, _ = doc_with_form()
    s = doc.screens[0]
    box = Node(type="rect", name="Рамка", w=200, h=100, fill="#111111", fill2="#222222", gradient="linear",
               stroke="#FF0000", stroke_width=4)
    s.nodes.append(box)
    doc.animations.append(Animation(name="Мигание", screen_id=s.id, duration=500, tracks=[
        Track(node_id=box.id, prop="stroke", keyframes=[Keyframe(0, "#FF0000"), Keyframe(500, "#00FF00")]),
        Track(node_id=box.id, prop="stroke_width", keyframes=[Keyframe(0, 4), Keyframe(500, 12)]),
        Track(node_id=box.id, prop="fill", keyframes=[Keyframe(0, "#111111"), Keyframe(500, "#FFFFFF")])]))
    f, base = _files(doc)
    src = f[f"{base}/ui/screens/FormaScreen.kt"].decode()
    assert "TODO: анимации" not in src and _balanced(src)
    assert ".border(animRamkaStrokeWidth.value.dp, animRamkaStroke.value," in src
    assert "Brush.verticalGradient(listOf(animRamkaFill.value" in src


def test_widget_shapes_glance_cannot_draw_go_as_pictures():
    doc, _ = doc_with_form()
    w = Screen(name="Виджет «Погода»", platform="android", width=500, height=250, device_id="android_widget_4x2")
    card = Node(type="frame", name="Фон", layout="vertical", w=500, h=250, gradient="linear", fill="#3366FF",
                fill2="#0022AA", children=[Node(type="text", name="Т", text="+21°", fill="", w=100, h=40)])
    w.nodes.append(card)
    doc.screens.append(w)
    assert needs_backdrop(card) and not needs_backdrop(card.children[0])
    f, base = _files(doc, {PART_PREFIX + card.id: b"\x89PNG fake"})
    kt = next(v.decode() for k, v in f.items() if k.startswith(f"{base}/widget/"))
    assert "R.drawable.pogoda_part_1" in kt and "ContentScale.FillBounds" in kt and _balanced(kt)
    assert 'context.getString(R.string.' in kt                              # текст виджета — ресурс
    assert f"{ROOT}/app/src/main/res/drawable-nodpi/pogoda_part_1.png" in f


def test_theme_round_trip_keeps_white_captions():
    from app.engines.material.restyle import restyle
    doc, _ = doc_with_form()
    s = doc.screens[0]
    cap = Node(type="text", name="Подпись на фото", text="Автор", fill="", text_color="#FFFFFF", w=100, h=20)
    ico = Node(type="vector", name="Закрыть", path="M0 0 L10 10", fill="#FFFFFF", w=24, h=24)
    s.nodes += [cap, ico]
    for theme in ("light", "dark", "amoled", "light"):
        restyle(doc, Appearance(theme=theme, accent="#2F7BFF"))
        doc.meta.appearance = Appearance(theme=theme, accent="#2F7BFF")
    assert cap.text_color == "#FFFFFF" and ico.fill == "#FFFFFF"


def test_component_rows_in_list_keep_their_own_action():
    doc, _ = doc_with_form()
    s = doc.screens[0]
    chips = [components.build("m3_chip_assist", s, doc.meta.appearance) for _ in range(3)]
    s.nodes.append(Node(type="frame", name="Подсказки", layout="horizontal", scroll="horizontal", w=400, h=60,
                        children=chips))
    for c in chips:
        doc.interactions.append(Interaction(screen_id=s.id, trigger="tap", node_id=c.id, actions=[
            {"type": "navigate", "screen_id": doc.screens[1].id, "transition": "none", "duration": 0,
             "easing": "linear"}]))
    f, base = _files(doc)
    src = next(v.decode() for k, v in f.items() if k.startswith(f"{base}/ui/screens/") and b"LazyRow(" in v)
    row = src.split("items(")[1]
    assert "item.onClick()" in row and "onNavigate(" not in row             # действие — из данных строки


def test_removing_screen_removes_its_animations_with_undo():
    from app.core.commands import RemoveScreen, UndoStack
    doc, _ = doc_with_form()
    s = doc.screens[1]
    doc.animations.append(Animation(name="Пульс", screen_id=s.id, duration=300, tracks=[]))
    st = UndoStack(doc)
    st.push(RemoveScreen(s.id))
    assert not doc.animations
    st.undo()
    assert len(doc.animations) == 1


def test_windows_middle_areas_and_grid_stretch():
    from app.exporters import windows_app

    def f(nid, x, y, w, h, **kw):
        return {"id": nid, "kind": "frame", "x": x, "y": y, "w": w, "h": h, **kw}
    head, chat, inp = f("head", 340, 0, 940, 60), f("chat", 340, 60, 940, 660), f("input", 340, 720, 940, 80)
    grid = f("grid", 0, 0, 340, 800, layout="grid", children=[f("a", 0, 0, 160, 100), f("b", 170, 0, 160, 100)])
    nodes = [head, chat, inp, grid]
    windows_app.anchor(nodes, 1280, 800)
    assert inp["cv"] == "bottom" and chat["cv"] == "top_bottom" and chat["ch"] == "left_right"
    assert grid["children"][1].get("ch", "left") == "left"                  # ячейки сетки — не по краям
