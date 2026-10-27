"""SVG: санитизация (S11, S12), пути, импорт в векторы, экспорт."""

import pytest

from app.core.document import pathdata
from app.engines.assets.svg import SvgError, nodes_to_svg, sanitize, svg_to_nodes

SAFE = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <title>Home</title>
  <path d="M3 10 L12 3 L21 10 V21 H3 Z" fill="#111" stroke="#fff" stroke-width="1.5"/>
  <rect x="9" y="14" width="6" height="7" rx="1" fill="rgb(255,0,0)" fill-opacity="0.5"/>
  <circle cx="12" cy="9" r="1.5"/>
</svg>"""


def test_safe_svg_imports_cleanly():  # S11
    clean, report = sanitize(SAFE)
    assert report.removed == []
    nodes, vb = svg_to_nodes(clean, report)
    assert vb == (0, 0, 24, 24)
    assert len(nodes) == 3
    house, door, dot = nodes
    assert (house.x, house.y, house.w, house.h) == (3, 3, 18, 18)
    assert house.fill == "#111111" and house.stroke == "#FFFFFF" and house.stroke_width == 1.5
    assert door.fill == "#FF000080"
    assert dot.fill == "#000000"  # заливка по умолчанию в SVG — чёрная


@pytest.mark.parametrize("payload,what", [
    (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><path d="M0 0L1 1"/></svg>', "<script>"),
    (b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><path d="M0 0L1 1"/></svg>', "onload"),
    (b'<svg xmlns="http://www.w3.org/2000/svg"><image href="http://evil/x.png"/></svg>', "<image>"),
    (b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject><p>x</p></foreignObject></svg>', "<foreignObject>"),
    (b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0L1 1" fill="url(http://evil/#a)"/></svg>', "fill"),
    (b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><use xlink:href="http://e/a.svg#x"/></svg>', "<use>"),
    (b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0L1 1" style="fill:red;behavior:url(x.htc)"/></svg>', "behavior"),
])
def test_unsafe_content_removed(payload, what):  # S12
    clean, report = sanitize(payload)
    assert any(what in r for r in report.removed), report.removed
    low = clean.lower()
    for bad in (b"script", b"onload", b"http://evil", b"http://e/", b"foreignobject", b"behavior"):
        assert bad not in low


@pytest.mark.parametrize("payload", [
    b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x SYSTEM "file:///c:/windows/win.ini">]><svg>&x;</svg>',
    b'<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]><svg>&lol2;</svg>',
    b"<html><body>not svg</body></html>",
    b"<svg><path",
    b"x" * (2 * 1024 * 1024 + 1),
], ids=["xxe", "billion-laughs", "not-svg", "truncated", "too-big"])
def test_dangerous_or_broken_files_rejected(payload):  # S12
    with pytest.raises(SvgError):
        sanitize(payload)


def test_path_parser_normalizes_all_commands():
    d = "m10 10 h5 v5 l-5 0 z M0 0 Q 5 5 10 0 T 20 0 C 1 2 3 4 5 6 S 7 8 9 10 A 5 5 0 0 1 20 20"
    segs = pathdata.parse(d)
    assert {s[0] for s in segs} <= {"M", "L", "C", "Z"}
    assert segs[1] == ("L", 15, 10) and segs[2] == ("L", 15, 15)
    assert pathdata.normalize(pathdata.normalize(d)) == pathdata.normalize(d)
    for bad in ("L 1 1", "M 1", "M 1 1 X 2", "M 1e400 1"):
        with pytest.raises(pathdata.PathError):
            pathdata.parse(bad)


def test_transforms_are_baked():
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><g transform="translate(10 20) scale(2)">'
           b'<rect x="1" y="1" width="5" height="5"/></g></svg>')
    clean, rep = sanitize(svg)
    nodes, _ = svg_to_nodes(clean, rep)
    assert (nodes[0].x, nodes[0].y, nodes[0].w, nodes[0].h) == (12, 22, 10, 10)


def test_export_roundtrip():
    clean, rep = sanitize(SAFE)
    nodes, vb = svg_to_nodes(clean, rep)
    out = nodes_to_svg(nodes, 24, 24, "Дом").encode("utf-8")
    clean2, rep2 = sanitize(out)
    assert rep2.removed == []
    nodes2, _ = svg_to_nodes(clean2, rep2)
    assert [(round(n.x, 2), round(n.y, 2), round(n.w, 2), round(n.h, 2), n.fill) for n in nodes2] == \
           [(round(n.x, 2), round(n.y, 2), round(n.w, 2), round(n.h, 2), n.fill) for n in nodes]


def test_gradient_is_reported_as_simplified():
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="g"><stop offset="0" '
           b'stop-color="#ff0000"/></linearGradient></defs><rect width="5" height="5" fill="url(#g)"/></svg>')
    clean, rep = sanitize(svg)
    nodes, _ = svg_to_nodes(clean, rep)
    assert nodes[0].fill == "#FF0000"
    assert any("градиент" in s for s in rep.simplified)
