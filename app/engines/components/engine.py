"""Компоненты: мастер, экземпляры, переопределения, состояния, синхронизация. Без Qt.

Экземпляр — узел типа instance. Его дети — материализованная копия детей мастера:
  id ребёнка = «<id экземпляра>:<id узла мастера>», ref = id узла мастера.
Поверх копии применяются переопределения состояния компонента, затем переопределения экземпляра
(по ref; ключ ROOT_REF — сам корень). После изменения мастера все экземпляры пересобираются,
переопределения сохраняются. Вложенные компоненты синхронизируются в порядке зависимостей.
"""

from __future__ import annotations

from app.core.document import tree
from app.core.document.model import (
    FRAME_PROPS, OVERRIDABLE, ROOT_REF, STYLE_PROPS, ComponentDef, ModelError, Node, ProjectDocument, Screen,
    check_prop, new_id,
)
from app.engines.layout import LayoutEngine


def _reid(node: Node) -> Node:
    """Глубокая копия с новыми идентификаторами (для мастера)."""
    copy = Node.from_dict(node.to_dict())
    for n, _, _ in tree.walk([copy]):
        n.id = new_id()
        n.ref = ""
    return copy


def component_ids_in(nodes: list[Node]) -> set[str]:
    return {n.component_id for n, _, _ in tree.walk(nodes) if n.is_instance}


def dependency_order(doc: ProjectDocument) -> list[ComponentDef]:
    """Компоненты так, что вложенные идут раньше содержащих. Цикл — ошибка."""
    by_id = {c.id: c for c in doc.components}
    order, state = [], {}

    def visit(c: ComponentDef, chain: list[str]):
        if state.get(c.id) == "done":
            return
        if state.get(c.id) == "active":
            names = " → ".join(by_id[i].name for i in chain + [c.id] if i in by_id)
            raise ModelError(f"Компонент не может содержать сам себя: {names}")
        state[c.id] = "active"
        for dep in sorted(component_ids_in([c.root])):
            if dep in by_id:
                visit(by_id[dep], chain + [c.id])
        state[c.id] = "done"
        order.append(c)

    for c in doc.components:
        visit(c, [])
    return order


def _apply(target: Node, props: dict) -> None:
    for k, v in props.items():
        try:
            setattr(target, k, check_prop(k, v, target.type))
        except ModelError:
            pass  # свойство не подходит этому типу узла (например, текст у прямоугольника) — пропускаем


def materialize(defn: ComponentDef, inst: Node, engine: LayoutEngine) -> None:
    """Пересобирает содержимое экземпляра из мастера с учётом состояния и переопределений."""
    root = defn.root
    for k in STYLE_PROPS + FRAME_PROPS:
        setattr(inst, k, getattr(root, k))
    if inst.w <= 0 or inst.h <= 0:
        inst.w, inst.h = root.w, root.h
    dx, dy = inst.x - root.x, inst.y - root.y
    kids = [Node.from_dict(c.to_dict()) for c in root.children]
    for n, _, _ in tree.walk(kids):
        n.ref = n.id
        n.id = f"{inst.id}:{n.id}"
        if not n.is_group:
            n.x, n.y = n.x + dx, n.y + dy
    by_ref = {n.ref: n for n, _, _ in tree.walk(kids)}
    for source in (defn.states.get(inst.state, {}) if inst.state != "default" else {}, inst.overrides):
        for ref, props in source.items():
            target = inst if ref == ROOT_REF else by_ref.get(ref)
            if target is not None:
                _apply(target, props)
    inst.children = kids
    # раскладка: содержимое собрано для размера мастера, затем экземпляр получает свой размер
    target = (inst.w, inst.h)
    tmp = Screen(name="tmp", platform="android", width=100_000, height=100_000, nodes=[inst])
    before = tree.geometry(tmp)
    before[inst.id] = (inst.x, inst.y, root.w, root.h)
    inst.w, inst.h = target
    changes, _ = engine.layout_screen(tmp, before)
    m = tree.node_map(tmp)
    for nid, props in changes.items():
        for k, v in props.items():
            setattr(m[nid], k, v)


def _instances(nodes: list[Node]) -> list[Node]:
    """Экземпляры верхнего уровня (вложенные в экземпляр пересобираются вместе с ним)."""
    out = []
    for n in nodes:
        if n.is_instance:
            out.append(n)
        elif n.is_container:
            out.extend(_instances(n.children))
    return out


def sync_instances(doc: ProjectDocument, engine: LayoutEngine) -> list[str]:
    """Пересобирает все экземпляры во всех мастерах и экранах. Возвращает предупреждения."""
    warnings = []
    by_id = {c.id: c for c in doc.components}
    for c in dependency_order(doc):
        for inst in _instances(c.root.children):
            dep = by_id.get(inst.component_id)
            if dep is not None:
                materialize(dep, inst, engine)
    for s in doc.screens:
        for inst in _instances(s.nodes):
            dep = by_id.get(inst.component_id)
            if dep is None:
                warnings.append(f"Экран «{s.name}»: компонент экземпляра «{inst.name}» не найден")
                continue
            materialize(dep, inst, engine)
    return warnings


def make_instance(defn: ComponentDef, x: float, y: float, engine: LayoutEngine) -> Node:
    root = defn.root
    inst = Node(type="instance", name=defn.name, component_id=defn.id, x=x, y=y, w=root.w, h=root.h,
                sizing_h=root.sizing_h, sizing_v=root.sizing_v, constraint_h=root.constraint_h,
                constraint_v=root.constraint_v, min_w=root.min_w, max_w=root.max_w, min_h=root.min_h,
                max_h=root.max_h)
    materialize(defn, inst, engine)
    return inst


def create_component(doc: ProjectDocument, screen: Screen, node_ids: list[str], name: str,
                     engine: LayoutEngine, category: str = "Мои компоненты") -> tuple[ComponentDef, Node]:
    """Создаёт мастер из выделения и заменяет выделение экземпляром на том же месте."""
    ids = tree.top_ids(screen, node_ids)
    if not ids:
        raise ModelError("Выделите элементы для компонента")
    found = [tree.find(screen, i) for i in ids]
    parents = {p.id if p else None for _, p, _ in found}
    if len(parents) != 1:
        raise ModelError("Компонент создаётся из элементов одного уровня")
    nodes = [n for n, _, _ in found]
    if any(n.ref for n in nodes) or any(a.is_instance for a in tree.ancestors(screen, ids[0])):
        raise ModelError("Нельзя создать компонент из содержимого экземпляра — сначала отсоедините его")
    if len(nodes) == 1 and nodes[0].is_frame and not nodes[0].is_instance:
        root = _reid(nodes[0])
    else:
        b = tree.bounds_of(nodes)
        root = Node(type="frame", name=name, x=b[0], y=b[1], w=b[2], h=b[3], fill="", children=[])
        root.children = [_reid(n) for n in nodes]
    root.name = name
    for nested in _instances(root.children):  # вложенные экземпляры получили новые id — пересобираем
        dep = doc.component(nested.component_id)
        if dep is not None:
            materialize(dep, nested, engine)
    defn = ComponentDef(name=name, root=root, category=category, platform=screen.platform)
    doc.components.append(defn)
    parent_id = parents.pop()
    cont = tree.container(screen, parent_id)
    index = min(cont.index(n) for n in nodes)
    inst = make_instance(defn, root.x, root.y, engine)
    if len(nodes) == 1:
        src = nodes[0]
        for k in ("sizing_h", "sizing_v", "constraint_h", "constraint_v"):
            setattr(inst, k, getattr(src, k))
    cont[:] = [n for n in cont if n.id not in ids]
    cont.insert(index, inst)
    return defn, inst


def owner_instance(screen: Screen, node_id: str) -> Node | None:
    """Самый внешний экземпляр, содержащий узел (или сам узел, если это экземпляр верхнего уровня).
    Переопределения хранятся именно в нём: вложенные экземпляры пересобираются из мастера вместе с ним."""
    chain = tree.ancestors(screen, node_id) + [tree.find(screen, node_id)[0]]
    return next((a for a in chain if a.is_instance), None)


def set_overrides(doc: ProjectDocument, screen: Screen, changes: dict[str, dict], engine: LayoutEngine) -> None:
    """Записывает изменения узлов внутри экземпляров как переопределения и пересобирает экземпляры."""
    m = tree.node_map(screen)
    touched = {}
    for nid, props in changes.items():
        node = m.get(nid)
        if node is None:
            raise ModelError(f"Узел не найден: {nid}")
        inst = owner_instance(screen, nid)
        if inst is None:
            raise ModelError("Узел не принадлежит экземпляру")
        bad = [k for k in props if k not in OVERRIDABLE]
        if bad:
            raise ModelError(f"В экземпляре можно менять только содержимое и стиль, не «{bad[0]}»")
        # ref относительно самого экземпляра: отрезаем префикс «<id экземпляра>:»
        ref = ROOT_REF if node is inst else node.id[len(inst.id) + 1:]
        entry = dict(inst.overrides.get(ref, {}))
        for k, v in props.items():
            entry[k] = check_prop(k, v, node.type)
        new = dict(inst.overrides)
        new[ref] = entry
        inst.overrides = new
        touched[inst.id] = inst
    by_id = {c.id: c for c in doc.components}
    for inst in touched.values():
        dep = by_id.get(inst.component_id)
        if dep is not None:
            materialize(dep, inst, engine)


def reset_overrides(doc: ProjectDocument, inst: Node, engine: LayoutEngine) -> None:
    inst.overrides = {}
    dep = doc.component(inst.component_id)
    if dep is not None:
        materialize(dep, inst, engine)


def detach(inst: Node) -> None:
    """Отсоединить экземпляр: он становится обычным фреймом, связь с мастером теряется."""
    inst.type = "frame"
    inst.component_id, inst.overrides, inst.state = "", {}, "default"
    for n, _, _ in tree.walk(inst.children):
        n.ref = ""


def dependencies(doc: ProjectDocument, component_id: str) -> dict[str, set[str]]:
    """Что нужно компоненту: вложенные компоненты, ресурсы, текстовые стили, семейства шрифтов."""
    by_id = {c.id: c for c in doc.components}
    comps, assets, styles, fonts = set(), set(), set(), set()
    stack = [component_id]
    while stack:
        cid = stack.pop()
        if cid in comps or cid not in by_id:
            continue
        comps.add(cid)
        c = by_id[cid]
        for n, _, _ in tree.walk([c.root]):
            if n.asset_id:
                assets.add(n.asset_id)
            if n.type == "text":
                fonts.add(n.font_family)
                if n.text_style:
                    styles.add(n.text_style)
            if n.is_instance:
                stack.append(n.component_id)
        for state in c.states.values():
            for props in state.values():
                if props.get("asset_id"):
                    assets.add(props["asset_id"])
                if props.get("font_family"):
                    fonts.add(props["font_family"])
    font_assets = {a.id for a in doc.assets if a.kind == "font" and a.family in fonts}
    return {"components": comps, "assets": assets | font_assets, "text_styles": styles, "fonts": fonts}


def apply_text_style(doc: ProjectDocument, style_id: str, engine: LayoutEngine) -> int:
    """Обновляет все тексты, связанные со стилем (на экранах и в мастерах). Возвращает число узлов."""
    st = doc.text_style(style_id)
    if st is None:
        raise ModelError("Стиль не найден")
    count = 0
    roots = [n for s in doc.screens for n in s.nodes] + [c.root for c in doc.components]
    for n, _, _ in tree.walk(roots):
        if n.type == "text" and n.text_style == style_id and not n.ref:
            n.font_family, n.font_size, n.font_weight = st.font_family, st.font_size, st.font_weight
            if st.text_color:
                n.text_color = st.text_color
            count += 1
    sync_instances(doc, engine)
    return count


def preset_states(defn: ComponentDef, accent: str = "#2F7BFF") -> None:
    """Типовые состояния интерактивного элемента поверх мастера."""
    root = defn.root
    texts = [n for n, _, _ in tree.walk(root.children) if n.type == "text"]
    first_text = texts[0].id if texts else None

    def shade(color: str, k: float) -> str:
        if not color:
            return color
        v = color.lstrip("#")
        r, g, b = (int(v[i:i + 2], 16) for i in (0, 2, 4))
        f = (lambda c: min(255, round(c + (255 - c) * k))) if k > 0 else (lambda c: max(0, round(c * (1 + k))))
        return f"#{f(r):02X}{f(g):02X}{f(b):02X}" + (v[6:8] if len(v) == 8 else "")
    defn.states.setdefault("hover", {ROOT_REF: {"fill": shade(root.fill, 0.12)}} if root.fill else {})
    defn.states.setdefault("pressed", {ROOT_REF: {"fill": shade(root.fill, -0.15)}} if root.fill else {})
    defn.states.setdefault("focus", {ROOT_REF: {"stroke": accent, "stroke_width": max(2.0, root.stroke_width)}})
    defn.states.setdefault("disabled", {ROOT_REF: {"opacity": 0.38}})
    if first_text:
        defn.states.setdefault("loading", {first_text: {"text": "Загрузка…"}})
    defn.states.setdefault("error", {ROOT_REF: {"stroke": "#E5484D", "stroke_width": max(2.0, root.stroke_width)}})
