import copy
import json
import random
import zipfile

import pytest

from app.core.commands import (
    AddNodes, AddScreen, DeleteNodes, Group, RemoveScreen, Reorder, SetMeta, SetProps, SetScreenProps, Ungroup,
    UndoStack,
)
from app.core.document import tree
from app.core.document.model import Guide, ModelError, Node, Screen
from app.core.persistence.container import load_project, save_project
from app.core.project.service import build_document
from tests.conftest import make_spec


@pytest.fixture
def doc(tmp_path):
    return build_document(make_spec(tmp_path))


def snap(doc):
    return json.dumps(doc.to_dict(), sort_keys=True)


def rect(x=0, y=0, w=10, h=10, name="r"):
    return Node(type="rect", name=name, x=x, y=y, w=w, h=h)


def test_add_delete_undo(doc):
    sid = doc.screens[0].id
    st = UndoStack(doc)
    a, b = rect(name="a"), rect(name="b")
    st.push(AddNodes(sid, [a, b]))
    assert [n.name for n in doc.screens[0].nodes] == ["a", "b"]
    st.push(DeleteNodes(sid, [a.id]))
    assert [n.name for n in doc.screens[0].nodes] == ["b"]
    st.undo()
    assert [n.name for n in doc.screens[0].nodes] == ["a", "b"]
    st.undo()
    assert doc.screens[0].nodes == []
    st.redo(), st.redo()
    assert [n.name for n in doc.screens[0].nodes] == ["b"]


def test_group_ungroup_preserve_order(doc):
    sid = doc.screens[0].id
    st = UndoStack(doc)
    nodes = [rect(name=c) for c in "abcd"]
    st.push(AddNodes(sid, nodes))
    before = snap(doc)
    g = Group(sid, [nodes[1].id, nodes[3].id])
    st.push(g)
    names = [n.name for n in doc.screens[0].nodes]
    assert names == ["a", "c", "Группа"]
    assert [c.name for c in doc.screens[0].nodes[2].children] == ["b", "d"]
    st.push(Ungroup(sid, g.group_id))
    assert [n.name for n in doc.screens[0].nodes] == ["a", "c", "b", "d"]
    st.undo(), st.undo()
    assert snap(doc) == before


def test_group_requires_same_parent(doc):
    sid = doc.screens[0].id
    st = UndoStack(doc)
    a, b, c = rect(), rect(), rect()
    st.push(AddNodes(sid, [a, b, c]))
    st.push(Group(sid, [a.id, b.id]))
    with pytest.raises(ModelError):
        st.push(Group(sid, [a.id, c.id]))


def test_delete_all_children_removes_group(doc):
    sid = doc.screens[0].id
    st = UndoStack(doc)
    a, b = rect(), rect()
    st.push(AddNodes(sid, [a, b]))
    st.push(Group(sid, [a.id, b.id]))
    st.push(DeleteNodes(sid, [a.id, b.id]))
    assert doc.screens[0].nodes == []
    st.undo()
    assert doc.screens[0].nodes[0].is_group


def test_reorder_modes(doc):
    sid = doc.screens[0].id
    st = UndoStack(doc)
    nodes = [rect(name=c) for c in "abcd"]
    st.push(AddNodes(sid, nodes))
    names = lambda: "".join(n.name for n in doc.screens[0].nodes)
    st.push(Reorder(sid, [nodes[0].id], "up"))
    assert names() == "bacd"
    st.push(Reorder(sid, [nodes[0].id], "top"))
    assert names() == "bcda"
    st.push(Reorder(sid, [nodes[0].id, nodes[3].id], "bottom"))
    assert names() == "dabc"  # относительный порядок выбранных сохраняется
    st.undo(), st.undo(), st.undo()
    assert names() == "abcd"


def test_setprops_validation_is_atomic(doc):
    sid = doc.screens[0].id
    st = UndoStack(doc)
    a = rect()
    st.push(AddNodes(sid, [a]))
    before = snap(doc)
    with pytest.raises(ModelError):
        st.push(SetProps(sid, {a.id: {"x": 5, "fill": "красный"}}))
    assert snap(doc) == before and len(st) == 1


def test_screen_and_meta_commands(doc):
    st = UndoStack(doc)
    sid = doc.screens[0].id
    st.push(SetScreenProps(sid, {"name": "Вход", "guides": [Guide("x", 16)]}))
    st.push(SetMeta({"title": "Новое"}))
    s2 = Screen(name="Второй", platform="android", width=100, height=200)
    st.push(AddScreen(s2))
    st.push(RemoveScreen(sid))
    assert [s.name for s in doc.screens] == ["Второй"]
    with pytest.raises(ModelError):
        st.push(RemoveScreen(s2.id))
    for _ in range(4):
        st.undo()
    assert doc.screens[0].guides == [] and doc.meta.title == "Мой проект"


def test_clean_state_tracking(doc):
    st = UndoStack(doc)
    sid = doc.screens[0].id
    assert st.is_clean()
    st.push(AddNodes(sid, [rect()]))
    assert not st.is_clean()
    st.set_clean()
    st.undo()
    assert not st.is_clean()
    st.redo()
    assert st.is_clean()
    st.undo()
    st.push(AddNodes(sid, [rect()]))  # ветка с чистым состоянием отброшена
    assert not st.is_clean()


def _random_op(rng, doc, sid):
    screen = doc.screen(sid)
    all_nodes = [n for n, _, _ in tree.walk(screen.nodes)]
    top = list(screen.nodes)
    op = rng.choice(["add", "add", "move", "style", "delete", "group", "ungroup", "reorder", "guide", "text"])
    if op == "add" or not top:
        kind = rng.choice(["rect", "ellipse", "text"])
        n = Node(type=kind, name=f"{kind}{rng.randint(0, 999)}", x=rng.randint(0, 300), y=rng.randint(0, 600),
                 w=rng.randint(1, 200), h=rng.randint(1, 200), text="Привет" if kind == "text" else "")
        return AddNodes(sid, [n], index=rng.randint(0, len(top)))
    leaves = [n for n in all_nodes if not n.is_group]
    if op == "move" and leaves:
        n = rng.choice(leaves)
        return SetProps(sid, {n.id: {"x": n.x + rng.randint(-50, 50), "y": n.y + rng.randint(-50, 50),
                                     "w": rng.randint(1, 300)}})
    if op == "style" and leaves:
        n = rng.choice(leaves)
        return SetProps(sid, {n.id: {"fill": f"#{rng.randint(0, 0xFFFFFF):06X}", "opacity": rng.random(),
                                     "radius": rng.randint(0, 20), "locked": rng.random() < 0.3}})
    if op == "text":
        texts = [n for n in leaves if n.type == "text"]
        if texts:
            n = rng.choice(texts)
            return SetProps(sid, {n.id: {"text": "Длинный русский текст " * rng.randint(1, 3), "font_size": 20}})
    if op == "delete":
        return DeleteNodes(sid, [rng.choice(all_nodes).id])
    if op == "group" and len(top) >= 2:
        return Group(sid, [n.id for n in rng.sample(top, 2)])
    if op == "ungroup":
        groups = [n for n in all_nodes if n.is_group]
        if groups:
            return Ungroup(sid, rng.choice(groups).id)
    if op == "reorder":
        return Reorder(sid, [rng.choice(top).id], rng.choice(Reorder.MODES))
    if op == "guide":
        return SetScreenProps(sid, {"guides": screen.guides + [Guide(rng.choice("xy"), rng.randint(0, 500))]})
    return SetProps(sid, {rng.choice(all_nodes).id: {"visible": rng.random() < 0.8}})


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_50_operations_undo_redo_roundtrip(doc, tmp_path, seed):  # S08
    rng = random.Random(seed)
    sid = doc.screens[0].id
    st = UndoStack(doc)
    states = [snap(doc)]
    while len(st) < 50:
        st.push(_random_op(rng, doc, sid))
        doc.validate()
        states.append(snap(doc))
    for i in range(50, 0, -1):
        assert st.undo()
        assert snap(doc) == states[i - 1], f"undo до шага {i - 1}"
    for i in range(1, 51):
        assert st.redo()
        assert snap(doc) == states[i], f"redo шага {i}"
    # итоговый документ сохраняется и читается без потерь
    path = tmp_path / f"проект_{seed}.adsproj"
    save_project(doc, path)
    assert snap(load_project(path)) == states[-1]


def test_v1_project_migrates(tmp_path):
    doc = build_document(make_spec(tmp_path))
    d = doc.to_dict()
    p = tmp_path / "старый.adsproj"
    with zipfile.ZipFile(p, "w") as zf:
        manifest = {"format": "adsproj", "schema_version": 1, "project_id": doc.meta.id,
                    "screens": [s["id"] for s in d["screens"]]}
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("project.json", json.dumps(d["meta"]))
        for s in d["screens"]:
            s = copy.deepcopy(s)
            s.pop("guides")
            zf.writestr(f"screens/{s['id']}.json", json.dumps(s))
    loaded = load_project(p)
    assert loaded.screens[0].guides == [] and loaded.screens[0].nodes == []


def test_node_validation_rejects_garbage():
    for bad in [{"type": "script", "id": "x"}, {"type": "rect", "id": "x", "x": float("nan")},
                {"type": "rect", "id": "x", "fill": "javascript:"}, {"type": "rect", "id": "x", "opacity": 5}]:
        with pytest.raises(ModelError):
            Node.from_dict(bad)
    deep = {"type": "group", "id": "0", "children": []}
    cur = deep
    for i in range(40):
        child = {"type": "group", "id": str(i + 1), "children": []}
        cur["children"].append(child)
        cur = child
    with pytest.raises(ModelError, match="вложенность"):
        Node.from_dict(deep)
