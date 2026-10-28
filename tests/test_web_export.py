"""1.22: прототип в браузере — один HTML-файл со всеми состояниями, переходами и прокруткой."""

import json
import re

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.behavior import Interaction, Variable
from app.core.document.model import Node
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from app.ui.workspace import web_export
from app.ui.workspace.web_export import build_html, save_html
from tests.conftest import make_spec


@pytest.fixture
def win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)
    w._quiet = True

    def discard(x):
        x.project_page.mark_clean()
        x.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Веб"))
    w.open_project(str(path))
    yield w
    ctx.close()


def _data(html: str) -> dict:
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


def _hs(view):
    """Все зоны нажатия состояния: корень, прокрутка, липкие."""
    out = []

    def rec(lay):
        for p in lay["parts"]:
            out.extend(p["hs"])
            if "kid" in p:
                rec(p["kid"])
                for s in p["kid"]["sticky"]:
                    out.extend(s["hs"])
    rec(view)
    return out


def _rect(ed, x, y, w, h, name):
    n = ed.add_node("rect")
    ed.set_props({n.id: {"x": x, "y": y, "w": w, "h": h, "name": name, "fill": "#6750A4"}}, "место")
    return n


def test_states_transitions_overlay_timer(win):
    ed = win.project_page.editor
    a = ed.screen()
    nxt = _rect(ed, 20, 40, 200, 60, "Дальше")
    sheet = _rect(ed, 0, 300, a.width, 200, "Шторка")
    opener = _rect(ed, 20, 140, 200, 60, "Открыть")
    ed.set_overlay_tap(opener.id, sheet.id)
    b = ed.add_template_screen("notifications")
    ed.set_auto_advance(a.id, 1500, "fade")          # с экрана B через 1,5 с — обратно на A
    ed.set_screen(a.id)
    ed.set_tap_action(nxt.id, {"type": "navigate", "screen_id": b.id, "transition": "slide_left",
                               "duration": 300, "easing": "ease_out"})
    html, info = build_html(ed.doc, ed.engine, ed.artboard_color(), a.id)
    d = _data(html)
    assert "Content-Security-Policy" in html and "default-src 'none'" in html
    assert not re.search(r'(src|href)="https?:', html)                    # ничего из сети
    assert all(i.startswith("data:image/") for i in d["images"])
    st = d["states"]
    assert st[0]["s"] == a.id and info["states"] == len(st) and not d["cut"]
    by = {h["e"].get("tap", {}).get("to"): h for h in _hs(st[0])}
    go_b = next(h["e"]["tap"] for h in _hs(st[0]) if st[h["e"]["tap"]["to"]]["s"] == b.id)
    assert go_b["tr"] == "slide_left" and go_b["ms"] == 300
    sb = st[go_b["to"]]
    assert sb["t"]["wait"] == 1500 and st[sb["t"]["to"]]["s"] == a.id   # автопереход
    assert sb["b"] is not None and st[sb["b"]["to"]]["s"] == a.id        # «Назад»
    # шторка: новое состояние на том же экране, зона затемнения закрывает
    ov = next(h["e"]["tap"] for h in _hs(st[0]) if h["e"]["tap"]["to"] not in (0, go_b["to"]))
    so = st[ov["to"]]
    assert so["s"] == a.id and ov["tr"] == "fade"
    scrim = next(h for h in _hs(so) if h["w"] == pytest.approx(a.width) and h["h"] == pytest.approx(a.height))
    assert scrim["e"]["tap"]["to"] == 0
    assert by  # зоны есть


def test_scroll_sticky_and_scroll_to(win):
    ed = win.project_page.editor
    s = ed.add_template_screen("notifications")
    content = next(n for n in s.nodes if n.name == "Содержимое")
    cid, sid = content.id, s.id

    def more(doc):
        c = tree.find(doc.screen(sid), cid)[0]
        for i in range(30):
            c.children.append(Node(type="text", name=f"Строка {i}", text=f"Строка {i}", fill="", w=300, h=60,
                                   sizing_h="fill"))
    assert ed.patch("длиннее", more)
    seg = next(n for n, _, _ in tree.walk(ed.screen().nodes) if n.role == "m3.segmented")
    ed.set_props({seg.id: {"sticky": True, "fill": "#FFFFFF"}}, "липкий")
    item = next(n for n, _, _ in tree.walk(ed.screen().nodes) if n.name == "Уведомление")
    target = next(n for n, _, _ in tree.walk(ed.screen().nodes) if n.name == "Строка 20")
    ed.set_tap_action(item.id, {"type": "scroll_to", "node_id": target.id})
    d = _data(build_html(ed.doc, ed.engine, ed.artboard_color(), sid)[0])
    v = d["states"][0]
    kid = next(p["kid"] for p in v["parts"] if "kid" in p)
    assert kid["id"] == cid and kid["ax"] == "v" and kid["ch"] > kid["h"]
    assert len(v["parts"]) >= 2                       # то, что над прокруткой (панели), — отдельной картинкой
    assert [x for x in kid["sticky"]] and kid["sticky"][0]["w"] > 0
    e = next(h["e"]["tap"] for h in _hs(v) if "sf" in h["e"].get("tap", {}))
    assert e["to"] == 0 and e["sf"] == cid and e["so"] > 0


def test_counter_is_cut_and_menu(win, tmp_path, monkeypatch):
    ed = win.project_page.editor
    s = ed.screen()
    plus = _rect(ed, 20, 40, 200, 60, "Плюс")
    var = Variable(name="Счёт", type="number", default=0)

    def add(doc):
        doc.variables.append(var)
        doc.interactions.append(Interaction(screen_id=s.id, trigger="tap", node_id=plus.id, actions=[
            {"type": "set_variable", "var_id": var.id, "mode": "increment", "value": 1}]))
    assert ed.patch("счётчик", add)
    monkeypatch.setattr(web_export, "MAX_STATES", 5)
    r = save_html(ed.doc, ed.engine, ed.artboard_color(), tmp_path / "p.html", s.id)
    assert r.cut and r.states == 5 and r.path.exists()
    d = _data(r.path.read_text(encoding="utf-8"))
    assert any(h["e"]["tap"]["to"] == -1 for h in _hs(d["states"][-1]))   # дальше — подсказка, не тупик
    out = win.export_html(str(tmp_path / "menu.html"))
    assert out is not None and out.path.exists() and out.size > 1000
