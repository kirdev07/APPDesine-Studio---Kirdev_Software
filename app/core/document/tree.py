"""Обход дерева узлов экрана. Координаты листьев абсолютные; границы группы вычисляются по детям."""

from __future__ import annotations

from collections.abc import Iterator

from app.core.document.model import ModelError, Node, Screen

Rect = tuple[float, float, float, float]  # x, y, w, h


def walk(nodes: list[Node], parent: Node | None = None, depth: int = 0) -> Iterator[tuple[Node, Node | None, int]]:
    """Обход в порядке отрисовки (снизу вверх)."""
    for n in nodes:
        yield n, parent, depth
        if n.is_group:
            yield from walk(n.children, n, depth + 1)


def node_map(screen: Screen) -> dict[str, Node]:
    return {n.id: n for n, _, _ in walk(screen.nodes)}


def parent_map(screen: Screen) -> dict[str, Node | None]:
    return {n.id: p for n, p, _ in walk(screen.nodes)}


def find(screen: Screen, node_id: str) -> tuple[Node, Node | None, int]:
    for n, p, _ in walk(screen.nodes):
        if n.id == node_id:
            cont = screen.nodes if p is None else p.children
            return n, p, cont.index(n)
    raise ModelError(f"Узел не найден: {node_id}")


def container(screen: Screen, parent_id: str | None) -> list[Node]:
    if parent_id is None:
        return screen.nodes
    node = find(screen, parent_id)[0]
    if not node.is_group:
        raise ModelError("Родитель должен быть группой")
    return node.children


def ancestors(screen: Screen, node_id: str) -> list[Node]:
    """Группы-предки от корня к непосредственному родителю."""
    pm = parent_map(screen)
    chain = []
    p = pm.get(node_id)
    while p is not None:
        chain.append(p)
        p = pm.get(p.id)
    return list(reversed(chain))


def leaves(node: Node) -> Iterator[Node]:
    if node.is_group:
        for c in node.children:
            yield from leaves(c)
    else:
        yield node


def union(rects: list[Rect]) -> Rect | None:
    if not rects:
        return None
    x1 = min(r[0] for r in rects)
    y1 = min(r[1] for r in rects)
    x2 = max(r[0] + r[2] for r in rects)
    y2 = max(r[1] + r[3] for r in rects)
    return x1, y1, x2 - x1, y2 - y1


def bounds(node: Node) -> Rect | None:
    return union([(n.x, n.y, n.w, n.h) for n in leaves(node)])


def bounds_of(nodes: list[Node]) -> Rect | None:
    return union([b for b in (bounds(n) for n in nodes) if b is not None])


def top_ids(screen: Screen, ids) -> list[str]:
    """Оставляет только узлы, у которых нет предка в наборе; порядок — порядок отрисовки."""
    wanted = set(ids)
    result = []
    for n, _, _ in walk(screen.nodes):
        if n.id in wanted and not any(a.id in wanted for a in ancestors(screen, n.id)):
            result.append(n.id)
    return result
