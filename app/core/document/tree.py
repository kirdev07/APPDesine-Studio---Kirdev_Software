"""Обход дерева узлов экрана.

Координаты всех узлов абсолютные (в системе экрана). Группа не имеет собственной геометрии — её границы
вычисляются по детям. Фрейм — контейнер с собственным прямоугольником.
"""

from __future__ import annotations

from collections.abc import Iterator

from app.core.document.model import ModelError, Node, Screen

Rect = tuple[float, float, float, float]  # x, y, w, h


def walk(nodes: list[Node], parent: Node | None = None, depth: int = 0) -> Iterator[tuple[Node, Node | None, int]]:
    """Обход в порядке отрисовки (снизу вверх)."""
    for n in nodes:
        yield n, parent, depth
        if n.is_container:
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
    if not node.is_container:
        raise ModelError("Родитель должен быть группой или фреймом")
    return node.children


def ancestors(screen: Screen, node_id: str) -> list[Node]:
    """Контейнеры-предки от корня к непосредственному родителю."""
    pm = parent_map(screen)
    chain = []
    p = pm.get(node_id)
    while p is not None:
        chain.append(p)
        p = pm.get(p.id)
    return list(reversed(chain))


def geo_nodes(node: Node) -> Iterator[Node]:
    """Узлы с собственной геометрией, представляющие node: сквозь группы, но не внутрь фреймов."""
    if node.is_group:
        for c in node.children:
            yield from geo_nodes(c)
    else:
        yield node


def descendants(node: Node) -> Iterator[Node]:
    """Все узлы поддерева с геометрией (включая сам node, если он не группа)."""
    for n, _, _ in walk([node]):
        if not n.is_group:
            yield n


def union(rects: list[Rect]) -> Rect | None:
    if not rects:
        return None
    x1 = min(r[0] for r in rects)
    y1 = min(r[1] for r in rects)
    x2 = max(r[0] + r[2] for r in rects)
    y2 = max(r[1] + r[3] for r in rects)
    return x1, y1, x2 - x1, y2 - y1


def bounds(node: Node) -> Rect | None:
    return union([(n.x, n.y, n.w, n.h) for n in geo_nodes(node)])


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


def geometry(screen: Screen) -> dict[str, Rect]:
    """Снимок геометрии всех узлов экрана (кроме групп)."""
    return {n.id: (n.x, n.y, n.w, n.h) for n, _, _ in walk(screen.nodes) if not n.is_group}


# Совместимость: «листья» = узлы с геометрией, представляющие node.
leaves = geo_nodes


def color_under(screen: Screen, x: float, y: float, default: str) -> str:
    """Цвет того, что видно в точке экрана: верхняя картинка или фигура с заливкой (картинка — как тёмное фото).
    Строка состояния и жестовая панель выбирают по нему светлые или тёмные значки."""
    color = default

    def rec(nodes):
        nonlocal color
        for n in nodes:
            if not n.visible:  # скрытое — вместе со всем, что внутри
                continue
            if n.type not in ("text", "vector") and not n.is_group and n.opacity >= 0.5                     and n.x <= x <= n.x + n.w and n.y <= y <= n.y + n.h:
                if n.type == "image":
                    color = "#000000"
                elif n.fill and n.fill.startswith("#") and (len(n.fill) != 9 or int(n.fill[7:9], 16) > 128):
                    color = n.fill[:7]  # #RRGGBBAA — почти непрозрачная заливка
            if n.is_container:
                rec(n.children)
    rec(screen.nodes)
    return color


def is_light(color: str) -> bool:
    """Светлый цвет — на нём нужны тёмные значки."""
    c = (color or "#000000").lstrip("#")[:6]  # #RRGGBB или #RRGGBBAA
    try:
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        return False
    return 0.299 * r + 0.587 * g + 0.114 * b > 150
