"""1.21: прототип до конца — липкие элементы в прокрутке, «Прокрутить к элементу», листание страницами с точками."""

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.behavior import check_action
from app.core.document.model import Node
from app.engines.logic.engine import Interpreter
from app.exporters.ai_export import ExportOptions, build_package
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec


def test_model_and_action():
    n = Node.from_dict(Node(type="frame", sticky=True, paging=True).to_dict())
    assert n.sticky and n.paging and "sticky" not in Node(type="rect").to_dict()
    assert check_action({"type": "scroll_to", "node_id": "abc"}) == {"type": "scroll_to", "node_id": "abc"}


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
    _, path = ctx.service.create(make_spec(projects_dir, title="Прокрутка"))
    w.open_project(str(path))
    yield w
    ctx.close()


def _long_feed(ed):
    """Экран «Уведомления»: столбец с прокруткой; дописать длинное содержимое."""
    s = ed.add_template_screen("notifications")
    content = next(n for n in s.nodes if n.name == "Содержимое")
    cid, sid = content.id, s.id

    def more(doc):
        c = tree.find(doc.screen(sid), cid)[0]
        for i in range(30):
            c.children.append(Node(type="text", name=f"Строка {i}", text=f"Строка {i}", fill="", w=300, h=60,
                                   sizing_h="fill", sizing_v="fixed"))
        c.children.append(Node(type="text", name="Низ", text="Низ", fill="", w=300, h=60, sizing_h="fill"))
    assert ed.patch("длиннее", more)
    return ed.screen(), cid


def test_sticky_scroll_to_and_prototype(win, qtbot):
    page, ed = win.project_page, win.project_page.editor
    s, cid = _long_feed(ed)
    seg = next(n for n, _, _ in tree.walk(s.nodes) if n.role == "m3.segmented")
    ed.select([seg.id])
    page.inspector.refresh()
    assert not page.inspector.sticky.isHidden()                         # в прокрутке — можно сделать липким
    page.inspector.sticky.click()
    assert tree.find(ed.screen(), seg.id)[0].sticky
    item = next(n for n, _, _ in tree.walk(s.nodes) if n.name == "Уведомление")
    target = next(n for n, _, _ in tree.walk(ed.screen().nodes) if n.name == "Строка 20")
    ed.select([item.id])
    page._fill_tap_menu()
    to = next(m for m in page._tap_submenus if m.title() == "Прокрутить к…")
    next(a for a in to.actions() if a.text() == "Строка 20").trigger()
    assert ed.tap_action(item.id) == {"type": "scroll_to", "node_id": target.id}
    from app.ui.studio.prototype import PrototypePlayer
    p = PrototypePlayer(ed, start_screen_id=ed.screen().id)
    p.dispatch("tap", item.id)
    p.advance(400)
    content = tree.find(ed.screen(), cid)[0]
    assert p.scroll[cid] == pytest.approx(min(target.y - content.y - content.pad_t, p.scroll_max[cid]), abs=1)
    stuck = tree.node_map(p.screen)[seg.id]
    assert stuck.y == pytest.approx(content.y, abs=1)                   # липкий — у верхнего края контейнера
    assert tree.find(ed.screen(), seg.id)[0].fill                          # без заливки не просвечивает
    src = "".join(v.decode() for k, v in build_package(ed.doc, ExportOptions()).files.items()
                  if k.endswith("Screen.kt"))
    assert ".zIndex(1f)" in src and ".animateScrollTo(" in src and "= rememberScrollState()" in src
    assert "val density = LocalDensity.current" in src


def test_paging_with_dots(win):
    page, ed = win.project_page, win.project_page.editor
    s = ed.add_template_screen("onboarding")
    content = next(n for n in s.nodes if n.name == "Содержимое")
    dots = next(n for n, _, _ in tree.walk(s.nodes) if n.role == "m3.page_dots")
    # ряд из трёх страниц прямо перед строкой с точками
    row_id = next(r for r in content.children if any(d is dots for d, _, _ in tree.walk([r]))).id
    sid, cid = s.id, content.id

    def add(doc):
        c = tree.find(doc.screen(sid), cid)[0]
        i = next(j for j, x in enumerate(c.children) if x.id == row_id)
        pages = [Node(type="frame", name=f"Стр {k}", w=200, h=150, fill=col)
                 for k, col in enumerate(("#FF0000", "#00FF00", "#0000FF"))]
        c.children.insert(i, Node(type="frame", name="Листалка", layout="horizontal", w=c.w - c.pad_l - c.pad_r,
                                  h=150, fill="", sizing_h="fill", children=pages))
    assert ed.patch("листалка", add)
    pager = next(n for n, _, _ in tree.walk(ed.screen().nodes) if n.name == "Листалка")
    ed.select([pager.id])
    page.inspector.refresh()
    assert not page.inspector.paging.isHidden()
    page.inspector.paging.click()
    pg = tree.find(ed.screen(), pager.id)[0]
    assert pg.paging and pg.scroll == "horizontal" and all(c.w == pytest.approx(pg.w) for c in pg.children)
    from app.ui.studio.prototype import PrototypePlayer
    p = PrototypePlayer(ed, start_screen_id=ed.screen().id)
    p.set_scroll(pager.id, pg.w * 1.3)                                   # отпустили между 2-й и 3-й…
    p.snap_page(pager.id)
    p.advance(400)
    assert p.scroll[pager.id] == pytest.approx(pg.w, abs=2)              # …довелось до 2-й страницы
    d = tree.node_map(p.screen)[dots.id]
    assert max(d.children, key=lambda x: x.w) is d.children[1]           # точка — вторая
    src = "".join(v.decode() for k, v in build_package(ed.doc, ExportOptions()).files.items()
                  if k.endswith("Screen.kt"))
    assert "HorizontalPager(" in src and "rememberPagerState { 3 }" in src and ".currentPage == i" in src
    assert "horizontalScroll(rememberScrollState())" not in src.split("HorizontalPager(")[1].split(") { page ->")[0]


def test_vertical_paging_short_videos(win):
    """1.35: столбец листается вверх-вниз по одной странице — как короткие видео (VerticalPager)."""
    page, ed = win.project_page, win.project_page.editor
    s = ed.add_template_screen("onboarding")
    sid = s.id

    def add(doc):
        sc = doc.screen(sid)
        clips = [Node(type="frame", name=f"Видео {k}", w=sc.width, h=300, fill=col, sizing_h="fill")
                 for k, col in enumerate(("#FF0000", "#00FF00", "#0000FF"))]
        sc.nodes.append(Node(type="frame", name="Лента видео", layout="vertical", x=0, y=0, w=sc.width,
                             h=sc.height, pad_t=0, pad_b=0, fill="#000000", children=clips))
    assert ed.patch("лента", add)
    feed = next(n for n in ed.screen().nodes if n.name == "Лента видео")
    ed.select([feed.id])
    page.inspector.refresh()
    assert not page.inspector.paging.isHidden()                          # столбец тоже можно листать
    page.inspector.paging.click()
    pg = tree.find(ed.screen(), feed.id)[0]
    assert pg.paging and pg.scroll == "vertical" and pg.clip
    assert all(c.h == pytest.approx(pg.h) for c in pg.children)          # каждое видео — на весь экран
    clip = pg.children[0]
    ed.select([clip.id])
    page.inspector.refresh()
    assert page.inspector.sticky.isHidden()                              # в листалке липких нет
    from app.ui.studio.prototype import PrototypePlayer
    p = PrototypePlayer(ed, start_screen_id=ed.screen().id)
    assert p.page_offsets(pg) == pytest.approx([0, pg.h, 2 * pg.h], abs=1)
    p.set_scroll(feed.id, pg.h * 0.7)                                    # протянули чуть дальше середины…
    p.snap_page(feed.id)
    p.advance(400)
    assert p.scroll[feed.id] == pytest.approx(pg.h, abs=2)               # …перелистнулось на второе видео
    p.wheel(QPointF(pg.w / 2, pg.h / 2), -120)                           # колесо — ещё на одну страницу
    p.advance(400)
    assert p.scroll[feed.id] == pytest.approx(2 * pg.h, abs=2)
    p.wheel(QPointF(pg.w / 2, pg.h / 2), -120)                           # дальше последней — некуда
    p.advance(400)
    assert p.scroll[feed.id] == pytest.approx(2 * pg.h, abs=2)
    src = next(v.decode() for k, v in build_package(ed.doc, ExportOptions()).files.items()
               if k.endswith("Screen.kt") and "Лента видео" in v.decode())
    assert "VerticalPager(" in src and "rememberPagerState { 3 }" in src
    assert "import androidx.compose.foundation.pager.VerticalPager" in src
    head = src.split("VerticalPager(")[1].split(") { page ->")[0]
    assert "PaddingValues(top = " in head and "verticalScroll(" not in head
    from app.ui.workspace.web_export import build_html
    html = build_html(ed.doc, ed.engine, ed.artboard_color(), sid)[0]
    assert '"snap": [0.0, ' in html or '"snap":[0.0,' in html
    assert ".sv.snap { scroll-snap-type:y mandatory; }" in html


def test_vertical_paging_follows_size_fullscreen_and_swipe(win):
    """1.35 (замечания тестировщика): страницы следуют за высотой ленты, лента во весь экран в Android,
    короткий взмах перелистывает."""
    page, ed = win.project_page, win.project_page.editor
    s = ed.add_template_screen("onboarding")
    sid = s.id

    def add(doc):
        sc = doc.screen(sid)
        clips = [Node(type="frame", name=f"Видео {k}", w=sc.width, h=300, fill="#FF0000", sizing_h="fill")
                 for k in range(3)]
        sc.nodes.append(Node(type="frame", name="Лента видео", layout="vertical", x=0, y=0, w=sc.width,
                             h=sc.height, fill="#000000", children=clips))
    assert ed.patch("лента", add)
    feed = next(n for n in ed.screen().nodes if n.name == "Лента видео")
    assert ed.set_paging(feed.id, True)
    new_h = feed.h * 0.75

    def shrink(doc):
        tree.find(doc.screen(sid), feed.id)[0].h = new_h
    assert ed.patch("ниже", shrink)
    pg = tree.find(ed.screen(), feed.id)[0]
    assert all(c.h == pytest.approx(new_h, abs=1) for c in pg.children)  # страницы — по новой высоте
    from app.ui.studio.prototype import PrototypePlayer
    p = PrototypePlayer(ed, start_screen_id=ed.screen().id)
    p.set_scroll(feed.id, new_h * 0.3)                                    # взмах на 30% от первой страницы
    p.snap_page(feed.id, 0.0)
    p.advance(400)
    assert p.scroll[feed.id] == pytest.approx(new_h, abs=2)              # перелистнулось вперёд
    p.set_scroll(feed.id, new_h * 0.9)                                    # чуть назад от второй
    p.snap_page(feed.id, new_h)
    p.advance(400)
    assert p.scroll[feed.id] == pytest.approx(new_h, abs=2)              # 10% — остаётся
    src = next(v.decode() for k, v in build_package(ed.doc, ExportOptions()).files.items()
               if k.endswith("Screen.kt") and "Лента видео" in v.decode())
    head = src.split("VerticalPager(")[1].split(") { page ->")[0]
    assert "fillMaxWidth()" in head or "fillMaxSize()" in head
    assert ".width(" not in head                                           # не жёсткая ширина телефона


def test_vertical_feed_makes_dots_white(win):
    """1.37: у ленты коротких видео точки страниц поверх неё — белые (неактивные полупрозрачные), их видно на видео."""
    ed = win.project_page.editor
    s = ed.screen()
    sid = s.id

    def add(doc):
        sc = doc.screen(sid)
        clips = [Node(type="frame", name=f"Видео {k}", w=sc.width, h=300, fill="#202020", sizing_h="fill")
                 for k in range(3)]
        dots = Node(type="frame", name="Точки", role="m3.page_dots", x=sc.width - 60, y=sc.height / 2, w=20, h=60,
                    children=[Node(type="rect", w=20, h=8, fill="#454652"), Node(type="rect", w=8, h=8, fill="#454652"),
                              Node(type="rect", w=8, h=8, fill="#454652")])
        sc.nodes += [Node(type="frame", name="Лента видео", layout="vertical", x=0, y=0, w=sc.width, h=sc.height,
                          fill="#000000", children=clips), dots]
    assert ed.patch("лента", add)
    feed = next(n for n in ed.screen().nodes if n.name == "Лента видео")
    assert ed.set_paging(feed.id, True)
    dots = next(n for n in ed.screen().nodes if n.name == "Точки")
    assert [c.fill for c in dots.children] == ["#FFFFFF", "#FFFFFF80", "#FFFFFF80"]
    from app.core.document.model import Appearance
    assert ed.apply_appearance(Appearance(theme="dark", accent="#2F7BFF"))   # тёмная тема — точки остаются белыми
    dots = next(n for n in ed.screen().nodes if n.name == "Точки")
    assert [c.fill for c in dots.children] == ["#FFFFFF", "#FFFFFF80", "#FFFFFF80"]


def test_paging_hides_extra_dots(win):
    """1.37: точек страниц на холсте столько, сколько страниц (лишние скрыты), как в прототипе и в Android."""
    ed = win.project_page.editor
    sid = ed.screen().id

    def add(doc):
        sc = doc.screen(sid)
        pages = [Node(type="frame", name=f"Стр {k}", w=200, h=150, fill="#FF0000") for k in range(3)]
        row = Node(type="frame", name="Листалка", layout="horizontal", x=0, y=200, w=400, h=150, children=pages)
        dots = Node(type="frame", name="Точки", role="m3.page_dots", x=150, y=360, w=60, h=8,
                    children=[Node(type="rect", w=20, h=8), Node(type="rect", w=8, h=8), Node(type="rect", w=8, h=8),
                              Node(type="rect", w=8, h=8)])
        sc.nodes += [row, dots]
    assert ed.patch("листалка", add)
    row = next(n for n in ed.screen().nodes if n.name == "Листалка")
    assert ed.set_paging(row.id, True)
    dots = next(n for n in ed.screen().nodes if n.name == "Точки")
    assert [c.visible for c in dots.children] == [True, True, True, False]
