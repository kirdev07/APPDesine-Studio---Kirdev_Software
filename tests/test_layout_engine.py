"""Движок раскладки: стеки, сетки, размеры, привязки, детерминизм, диагностика (S09, S10)."""

import copy

import pytest

from app.core.document import tree
from app.core.document.model import Node, Screen
from app.engines.layout import LayoutEngine, SimpleMeasurer

LONG_RU = ("Съешь же ещё этих мягких французских булок, да выпей чаю. Широкая электрификация южных губерний "
           "даст мощный толчок подъёму сельского хозяйства.")


def frame(layout="vertical", x=0, y=0, w=400, h=600, **kw):
    f = Node(type="frame", name=kw.pop("name", "Фрейм"), x=x, y=y, w=w, h=h, layout=layout, **kw)
    return f


def box(w=50, h=50, **kw):
    return Node(type="rect", name=kw.pop("name", "Блок"), w=w, h=h, **kw)


def text(t, **kw):
    return Node(type="text", name=kw.pop("name", "Текст"), text=t, font_size=kw.pop("font_size", 20), fill="",
                w=kw.pop("w", 100), h=kw.pop("h", 20), **kw)


def run(screen, before=None, before_size=None, apply=True):
    eng = LayoutEngine(SimpleMeasurer())
    changes, diags = eng.layout_screen(screen, before, before_size)
    if apply:
        m = tree.node_map(screen)
        for nid, props in changes.items():
            for k, v in props.items():
                setattr(m[nid], k, v)
    return changes, diags


def screen_with(*nodes, w=1080, h=2400):
    return Screen(name="Экран", platform="android", width=w, height=h, nodes=list(nodes))


def test_vertical_stack_padding_gap_alignment():
    a, b = box(100, 40), box(60, 20)
    f = frame(gap=10, pad_t=20, pad_l=30, pad_r=30, pad_b=20, children=[a, b])
    run(screen_with(f))
    assert (a.x, a.y, a.w, a.h) == (30, 20, 100, 40)
    assert (b.x, b.y) == (30, 70)
    f.cross_align = "center"
    f.main_align = "end"
    run(screen_with(f))
    assert a.x == 30 + (340 - 100) / 2 and b.y + b.h == 600 - 20


def test_horizontal_fill_and_minmax():
    a, b, c = box(100, 40), box(10, 40, sizing_h="fill"), box(10, 40, sizing_h="fill", max_w=50)
    f = frame("horizontal", w=500, h=100, gap=10, pad_l=10, pad_r=10, children=[a, b, c])
    run(screen_with(f))
    # 480 внутри − 100 − 2×10 зазора = 360; c ограничен 50, b получает остальное 310
    assert c.w == 50 and b.w == 310
    assert b.x == 120 and c.x == 440


def test_space_between_and_stretch():
    kids = [box(40, 40) for _ in range(3)]
    f = frame("horizontal", w=300, h=100, main_align="space_between", cross_align="stretch", children=kids)
    run(screen_with(f))
    assert [k.x for k in kids] == [0, 130, 260]
    assert all(k.h == 100 for k in kids)


def test_hug_frame_with_long_russian_text_wraps():  # S10
    t = text(LONG_RU, sizing_h="fill", sizing_v="hug")
    card = frame(w=300, h=10, pad_t=16, pad_b=16, pad_l=16, pad_r=16, gap=8, sizing_v="hug",
                 children=[text("Заголовок", sizing_h="hug", sizing_v="hug"), t])
    run(screen_with(card))
    assert t.w == 268  # заполняет ширину карточки минус отступы
    _, h_expected = SimpleMeasurer().measure(LONG_RU, "Segoe UI", 20, 400, 268)
    assert t.h == h_expected and t.h > 100  # перенесён на несколько строк
    assert card.h == pytest.approx(16 + 25 + 8 + t.h + 16)


def test_nested_auto_layout():  # S09
    inner = frame("horizontal", w=10, h=10, gap=4, sizing_h="hug", sizing_v="hug",
                  children=[box(20, 20), box(30, 10)])
    outer = frame("vertical", w=200, h=10, gap=6, pad_t=5, pad_l=5, sizing_v="hug",
                  children=[box(50, 50), inner])
    run(screen_with(outer))
    assert (inner.w, inner.h) == (54, 20)
    assert (inner.x, inner.y) == (5, 5 + 50 + 6)
    assert inner.children[1].x == 5 + 20 + 4
    assert outer.h == 5 + 50 + 6 + 20


def test_grid_layout():
    kids = [box(10, 30 + i * 10) for i in range(5)]
    g = frame("grid", w=320, h=500, gap=10, row_gap=20, grid_columns=3, cross_align="stretch", children=kids)
    run(screen_with(g))
    assert [k.w for k in kids] == [100] * 5
    assert [k.x for k in kids[:3]] == [0, 110, 220]
    assert kids[3].y == 50 + 20  # высота первой строки = max(30, 40, 50)


def test_constraints_on_screen_resize():
    left = box(100, 50, x=20, y=20)
    right = box(100, 50, x=960, y=20, constraint_h="right")
    stretch = box(1040, 80, x=20, y=2300, constraint_h="left_right", constraint_v="bottom")
    centered = box(200, 200, x=440, y=1100, constraint_h="center", constraint_v="center")
    s = screen_with(left, right, stretch, centered)
    before = tree.geometry(s)
    s.width, s.height = 1600, 2560
    run(s, before, (1080, 2400))
    assert (left.x, left.y) == (20, 20)
    assert right.x == 1600 - 20 - 100
    assert stretch.w == 1600 - 40
    assert stretch.y == 2560 - 20 - 80  # отступ снизу 20 сохраняется
    assert centered.x == 800 - 100 and centered.y == 1280 - 100


def test_free_frame_moves_children():
    child = box(10, 10, x=110, y=110)
    f = frame("none", x=100, y=100, w=200, h=200, children=[child])
    s = screen_with(f)
    before = tree.geometry(s)
    f.x, f.y = 300, 400
    run(s, before)
    assert (child.x, child.y) == (310, 410)


def test_deterministic_and_idempotent():
    def build():
        t = text(LONG_RU * 2, sizing_h="fill", sizing_v="hug")
        return screen_with(frame(w=360, sizing_v="hug", gap=12, pad_t=8, pad_l=8, pad_r=8, pad_b=8,
                                 children=[box(100, 40, sizing_h="fill"), t,
                                           frame("horizontal", sizing_v="hug", sizing_h="fill", gap=8,
                                                 children=[box(40, 40), box(10, 40, sizing_h="fill")])]))
    a, b = build(), build()
    ca, _ = run(a)
    cb, _ = run(b)
    strip = lambda s: [(n.x, n.y, n.w, n.h) for n, _, _ in tree.walk(s.nodes)]
    assert strip(a) == strip(b)
    again, _ = run(a, tree.geometry(a))
    assert again == {}  # повторный прогон ничего не меняет
    assert ca and len(ca) == len(cb)


def test_diagnostics():
    t = text(LONG_RU, w=200, h=20)  # фиксированная высота — текст обрежется
    over = frame("horizontal", w=100, h=50, children=[box(80, 10), box(80, 10)])
    bad = box(50, 50, min_w=100, max_w=60)
    fill_free = box(50, 50, sizing_h="fill")
    hug_fill = frame(w=200, sizing_v="hug", children=[box(10, 10, sizing_v="fill")])
    _, diags = run(screen_with(t, over, bad, fill_free, hug_fill))
    text_ = " | ".join(d.message for d in diags)
    assert "текст обрезан" in text_
    assert "не помещается" in text_
    assert "минимальная ширина" in text_
    assert "только внутри фрейма" in text_
    assert "считается по содержимому" in text_
    assert all(d.node_id for d in diags)


def test_hidden_children_excluded():
    a, b, c = box(10, 10), box(10, 10, visible=False), box(10, 10)
    run(screen_with(frame(gap=5, children=[a, b, c])))
    assert c.y == 15


def test_group_inside_auto_layout_moves_as_unit():
    g = Node(type="group", name="Группа", children=[box(10, 10, x=500, y=500), box(10, 10, x=520, y=530)])
    f = frame(gap=0, children=[box(50, 50), g])
    run(screen_with(f))
    assert tree.bounds(g)[:2] == (0, 50)
    assert g.children[1].x - g.children[0].x == 20


def test_simple_measurer_wraps_long_words():
    m = SimpleMeasurer()
    w1, h1 = m.measure("а" * 25, "x", 10, 400, 55)  # 10 символов в строке → 3 строки
    assert h1 == pytest.approx(3 * 12.5)
    assert m.measure("один два", "x", 10, 400, None)[1] == 12.5


def test_copy_stability():
    s = screen_with(frame(children=[box(), text(LONG_RU, sizing_h="fill", sizing_v="hug")]))
    s2 = copy.deepcopy(s)
    assert run(s)[0] == run(s2)[0]
