"""Команды изменения документа и стек отмены. Не зависят от Qt.

Каждая команда проверяет входные данные до изменения документа и хранит всё нужное для отмены
в сериализуемом виде, поэтому повтор (redo) детерминирован.
"""

from __future__ import annotations

import copy
from collections.abc import Callable

from app.core.document import tree
from app.core.document.model import (
    Guide, ModelError, Node, ProjectDocument, Screen, check_prop,
)


class Command:
    label = "Изменение"

    def redo(self, doc: ProjectDocument) -> None:
        raise NotImplementedError

    def undo(self, doc: ProjectDocument) -> None:
        raise NotImplementedError


class UndoStack:
    def __init__(self, doc: ProjectDocument, limit: int = 1000):
        self.doc = doc
        self.limit = limit
        self._done: list[Command] = []
        self._undone: list[Command] = []
        self._clean = 0
        self.listeners: list[Callable[[], None]] = []

    def _notify(self) -> None:
        for fn in list(self.listeners):
            fn()

    def push(self, cmd: Command) -> None:
        cmd.redo(self.doc)
        self.push_done(cmd)

    def push_done(self, cmd: Command) -> None:
        """Записывает уже выполненную команду (например, пакет «действие + раскладка»)."""
        self._done.append(cmd)
        if self._clean > len(self._done) - 1:
            self._clean = -1  # чистое состояние было в отменённой ветке и больше недостижимо
        self._undone.clear()
        if len(self._done) > self.limit:
            self._done.pop(0)
            self._clean -= 1
        self._notify()

    def undo(self) -> bool:
        if not self._done:
            return False
        cmd = self._done.pop()
        cmd.undo(self.doc)
        self._undone.append(cmd)
        self._notify()
        return True

    def redo(self) -> bool:
        if not self._undone:
            return False
        cmd = self._undone.pop()
        cmd.redo(self.doc)
        self._done.append(cmd)
        self._notify()
        return True

    def can_undo(self) -> bool:
        return bool(self._done)

    def can_redo(self) -> bool:
        return bool(self._undone)

    def undo_label(self) -> str:
        return self._done[-1].label if self._done else ""

    def redo_label(self) -> str:
        return self._undone[-1].label if self._undone else ""

    def is_clean(self) -> bool:
        return self._clean == len(self._done)

    def set_clean(self) -> None:
        self._clean = len(self._done)
        self._notify()

    def __len__(self) -> int:
        return len(self._done)


class Batch(Command):
    """Несколько команд как одна запись истории. Отмена — в обратном порядке."""

    def __init__(self, commands: list[Command], label: str | None = None):
        self.commands = list(commands)
        self.label = label or (commands[0].label if commands else "Изменение")

    def redo(self, doc):
        for c in self.commands:
            c.redo(doc)

    def undo(self, doc):
        for c in reversed(self.commands):
            c.undo(doc)


class DocPatch(Command):
    """Изменение документа функцией с сохранением снимков «до» и «после».

    Для операций, затрагивающих сразу компоненты, все их экземпляры, ресурсы и стили. Повтор применяет
    сохранённый снимок «после», поэтому результат детерминирован; если функция упала, документ
    возвращается в состояние «до».
    """

    def __init__(self, label: str, mutate: Callable[[ProjectDocument], None]):
        self.label, self.mutate = label, mutate
        self.before: dict | None = None
        self.after: dict | None = None

    @staticmethod
    def capture(doc: ProjectDocument) -> dict:
        return {"screens": [s.to_dict() for s in doc.screens],
                "components": [c.to_dict() for c in doc.components],
                "assets": [a.to_dict() for a in doc.assets],
                "text_styles": [t.to_dict() for t in doc.text_styles],
                "colors": [c.to_dict() for c in doc.colors],
                "animations": [a.to_dict() for a in doc.animations],
                "variables": [v.to_dict() for v in doc.variables],
                "interactions": [i.to_dict() for i in doc.interactions],
                "asset_data": dict(doc.asset_data),
                "meta": doc.meta.to_dict()}

    @staticmethod
    def restore(doc: ProjectDocument, snap: dict) -> None:
        from app.core.document.model import Asset, ColorToken, ComponentDef, ProjectMeta, TextStyle
        doc.screens[:] = [Screen.from_dict(s) for s in snap["screens"]]
        doc.components[:] = [ComponentDef.from_dict(c) for c in snap["components"]]
        doc.assets[:] = [Asset.from_dict(a) for a in snap["assets"]]
        doc.text_styles[:] = [TextStyle.from_dict(t) for t in snap["text_styles"]]
        doc.colors[:] = [ColorToken.from_dict(c) for c in snap["colors"]]
        from app.core.document.behavior import Animation, Interaction, Variable
        doc.animations[:] = [Animation.from_dict(a) for a in snap.get("animations", [])]
        doc.variables[:] = [Variable.from_dict(v) for v in snap.get("variables", [])]
        doc.interactions[:] = [Interaction.from_dict(i) for i in snap.get("interactions", [])]
        doc.asset_data.clear()
        doc.asset_data.update(snap["asset_data"])
        meta = ProjectMeta.from_dict(snap["meta"])
        doc.meta.title, doc.meta.description = meta.title, meta.description

    def redo(self, doc):
        if self.after is not None:
            self.restore(doc, self.after)
            return
        self.before = self.capture(doc)
        try:
            self.mutate(doc)
            doc.validate()
        except Exception:
            self.restore(doc, self.before)
            raise
        self.after = self.capture(doc)

    def undo(self, doc):
        if self.before is not None:
            self.restore(doc, self.before)


# ---------------- узлы ----------------

class AddNodes(Command):
    def __init__(self, screen_id: str, nodes: list[Node], parent_id: str | None = None, index: int | None = None,
                 label: str = "Добавить элемент"):
        self.screen_id, self.parent_id, self.index, self.label = screen_id, parent_id, index, label
        self.data = [n.to_dict() for n in nodes]
        self.ids = [n.id for n in nodes]

    def redo(self, doc):
        screen = doc.screen(self.screen_id)
        existing = tree.node_map(screen)
        new_nodes = [Node.from_dict(d) for d in self.data]
        for n in new_nodes:
            for leaf, _, _ in tree.walk([n]):
                if leaf.id in existing:
                    raise ModelError("Идентификатор узла уже существует")
        cont = tree.container(screen, self.parent_id)
        idx = len(cont) if self.index is None else max(0, min(self.index, len(cont)))
        cont[idx:idx] = new_nodes

    def undo(self, doc):
        cont = tree.container(doc.screen(self.screen_id), self.parent_id)
        cont[:] = [n for n in cont if n.id not in self.ids]


class DeleteNodes(Command):
    label = "Удалить"

    def __init__(self, screen_id: str, ids: list[str]):
        self.screen_id = screen_id
        self.ids = list(ids)
        self.records: list[tuple[str | None, int, dict]] | None = None

    @staticmethod
    def _normalize(screen: Screen, ids: list[str]) -> list[str]:
        wanted = set(ids)
        changed = True
        while changed:  # группа, у которой удаляются все дети, удаляется целиком
            changed = False
            for n, _, _ in tree.walk(screen.nodes):
                if n.is_group and n.id not in wanted and n.children and all(c.id in wanted for c in n.children):  # фрейм может быть пустым
                    wanted.add(n.id)
                    changed = True
        return tree.top_ids(screen, wanted)

    def redo(self, doc):
        screen = doc.screen(self.screen_id)
        if self.records is None:
            records = []
            for nid in self._normalize(screen, self.ids):
                node, parent, idx = tree.find(screen, nid)
                records.append((parent.id if parent else None, idx, node.to_dict()))
            self.records = sorted(records, key=lambda r: (r[0] or "", r[1]))
        for parent_id, idx, _ in reversed(self.records):
            tree.container(screen, parent_id).pop(idx)

    def undo(self, doc):
        screen = doc.screen(self.screen_id)
        for parent_id, idx, data in self.records or []:
            tree.container(screen, parent_id).insert(idx, Node.from_dict(data))


class SetProps(Command):
    def __init__(self, screen_id: str, changes: dict[str, dict], label: str = "Изменить свойства"):
        self.screen_id, self.label = screen_id, label
        self.changes = copy.deepcopy(changes)
        self.old: dict[str, dict] | None = None

    def _apply(self, screen: Screen, values: dict[str, dict]) -> None:
        nodes = tree.node_map(screen)
        normalized = {}
        for nid, props in values.items():
            if nid not in nodes:
                raise ModelError(f"Узел не найден: {nid}")
            normalized[nid] = {k: check_prop(k, v, nodes[nid].type) for k, v in props.items()}
        for nid, props in normalized.items():
            for k, v in props.items():
                setattr(nodes[nid], k, v)

    def redo(self, doc):
        screen = doc.screen(self.screen_id)
        if self.old is None:
            nodes = tree.node_map(screen)
            self.old = {nid: {k: getattr(nodes[nid], k) for k in props}
                        for nid, props in self.changes.items() if nid in nodes}
        self._apply(screen, self.changes)

    def undo(self, doc):
        self._apply(doc.screen(self.screen_id), self.old or {})


class Reorder(Command):
    label = "Изменить порядок слоёв"
    MODES = ("up", "down", "top", "bottom")

    def __init__(self, screen_id: str, ids: list[str], mode: str):
        if mode not in self.MODES:
            raise ModelError("Неверный режим порядка")
        self.screen_id, self.ids, self.mode = screen_id, list(ids), mode
        self.before: dict[str | None, list[str]] | None = None

    @staticmethod
    def _arrange(cont: list[Node], order: list[str]) -> None:
        by_id = {n.id: n for n in cont}
        cont[:] = [by_id[i] for i in order]

    def _new_order(self, order: list[str], sel: set[str]) -> list[str]:
        if self.mode == "top":
            return [i for i in order if i not in sel] + [i for i in order if i in sel]
        if self.mode == "bottom":
            return [i for i in order if i in sel] + [i for i in order if i not in sel]
        order = list(order)
        rng = range(len(order) - 2, -1, -1) if self.mode == "up" else range(1, len(order))
        step = 1 if self.mode == "up" else -1
        for i in rng:
            j = i + step
            if order[i] in sel and order[j] not in sel:
                order[i], order[j] = order[j], order[i]
        return order

    def redo(self, doc):
        screen = doc.screen(self.screen_id)
        if self.before is None:
            self.before = {}
            for nid in self.ids:
                _, parent, _ = tree.find(screen, nid)
                pid = parent.id if parent else None
                self.before.setdefault(pid, [n.id for n in tree.container(screen, pid)])
        sel = set(self.ids)
        for pid, order in self.before.items():
            self._arrange(tree.container(screen, pid), self._new_order(order, sel))

    def undo(self, doc):
        screen = doc.screen(self.screen_id)
        for pid, order in (self.before or {}).items():
            self._arrange(tree.container(screen, pid), order)


def _group(screen: Screen, parent_id: str | None, indices: list[int], group: dict) -> None:
    cont = tree.container(screen, parent_id)
    children = [cont[i] for i in indices]
    for i in reversed(indices):
        cont.pop(i)
    node = Node.from_dict({**group, "children": []})
    node.children = children
    cont.insert(indices[-1] - len(indices) + 1, node)


def _ungroup(screen: Screen, parent_id: str | None, group_id: str, indices: list[int]) -> None:
    cont = tree.container(screen, parent_id)
    pos = next(i for i, n in enumerate(cont) if n.id == group_id)
    group = cont.pop(pos)
    for i, child in zip(indices, group.children):
        cont.insert(i, child)


class MoveToIndex(Command):
    label = "Переместить в раскладке"

    def __init__(self, screen_id: str, node_id: str, index: int):
        self.screen_id, self.node_id, self.index = screen_id, node_id, index
        self.old_index: int | None = None
        self.parent_id: str | None = None

    def redo(self, doc):
        screen = doc.screen(self.screen_id)
        node, parent, idx = tree.find(screen, self.node_id)
        self.parent_id, self.old_index = (parent.id if parent else None), idx
        cont = tree.container(screen, self.parent_id)
        cont.pop(idx)
        cont.insert(max(0, min(self.index, len(cont))), node)

    def undo(self, doc):
        screen = doc.screen(self.screen_id)
        cont = tree.container(screen, self.parent_id)
        node = next(n for n in cont if n.id == self.node_id)
        cont.remove(node)
        cont.insert(self.old_index, node)


class Group(Command):
    """Объединяет узлы одного уровня в группу или во фрейм (если передан узел-фрейм с геометрией)."""
    label = "Сгруппировать"

    def __init__(self, screen_id: str, ids: list[str], group: Node | None = None, label: str | None = None):
        self.screen_id, self.ids = screen_id, list(ids)
        g = group or Node(type="group", name="Группа")
        self.group = {k: v for k, v in g.to_dict().items() if k != "children"}
        if label:
            self.label = label
        self.parent_id: str | None = None
        self.indices: list[int] = []

    @property
    def group_id(self) -> str:
        return self.group["id"]

    def redo(self, doc):
        screen = doc.screen(self.screen_id)
        if not self.indices:
            if len(self.ids) < 1:
                raise ModelError("Нечего группировать")
            found = [tree.find(screen, i) for i in self.ids]
            parents = {p.id if p else None for _, p, _ in found}
            if len(parents) != 1:
                raise ModelError("Группировать можно только элементы одного уровня")
            self.parent_id = parents.pop()
            self.indices = sorted(idx for _, _, idx in found)
        _group(screen, self.parent_id, self.indices, self.group)

    def undo(self, doc):
        _ungroup(doc.screen(self.screen_id), self.parent_id, self.group_id, self.indices)


class Ungroup(Command):
    label = "Разгруппировать"

    def __init__(self, screen_id: str, group_id: str):
        self.screen_id, self.group_id = screen_id, group_id
        self.parent_id: str | None = None
        self.indices: list[int] = []
        self.group: dict | None = None

    def redo(self, doc):
        screen = doc.screen(self.screen_id)
        node, parent, idx = tree.find(screen, self.group_id)
        if not node.is_container:
            raise ModelError("Это не группа и не фрейм")
        self.parent_id = parent.id if parent else None
        self.indices = list(range(idx, idx + len(node.children)))
        self.group = {k: v for k, v in node.to_dict().items() if k != "children"}
        _ungroup(screen, self.parent_id, self.group_id, self.indices)

    def undo(self, doc):
        _group(doc.screen(self.screen_id), self.parent_id, self.indices, self.group)


# ---------------- экраны и проект ----------------

class AddScreen(Command):
    label = "Добавить экран"

    def __init__(self, screen: Screen, index: int | None = None):
        self.data, self.index = screen.to_dict(), index

    def redo(self, doc):
        idx = len(doc.screens) if self.index is None else self.index
        doc.screens.insert(idx, Screen.from_dict(self.data))
        doc.validate()

    def undo(self, doc):
        doc.screens[:] = [s for s in doc.screens if s.id != self.data["id"]]


class RemoveScreen(Command):
    label = "Удалить экран"

    def __init__(self, screen_id: str):
        self.screen_id = screen_id
        self.data: dict | None = None
        self.index = 0

    def redo(self, doc):
        if len(doc.screens) <= 1:
            raise ModelError("В проекте должен остаться хотя бы один экран")
        s = doc.screen(self.screen_id)
        self.index, self.data = doc.screens.index(s), s.to_dict()
        doc.screens.pop(self.index)

    def undo(self, doc):
        doc.screens.insert(self.index, Screen.from_dict(self.data))


class SetScreenProps(Command):
    label = "Изменить экран"
    PROPS = ("name", "width", "height", "guides")

    def __init__(self, screen_id: str, changes: dict, label: str | None = None):
        self.screen_id = screen_id
        self.label = label or self.label
        for k, v in changes.items():
            if k not in self.PROPS:
                raise ModelError(f"Свойство экрана «{k}» не поддерживается")
            if k in ("width", "height") and (not isinstance(v, int) or not 1 <= v <= 20000):
                raise ModelError("Недопустимый размер экрана")
            if k == "name" and (not isinstance(v, str) or not v.strip()):
                raise ModelError("Пустое имя экрана")
        self.changes = {k: ([g.to_dict() for g in v] if k == "guides" else v) for k, v in changes.items()}
        self.old: dict | None = None

    def _apply(self, screen: Screen, values: dict) -> None:
        for k, v in values.items():
            setattr(screen, k, [Guide.from_dict(g) for g in v] if k == "guides" else v)

    def redo(self, doc):
        s = doc.screen(self.screen_id)
        if self.old is None:
            self.old = {k: ([g.to_dict() for g in s.guides] if k == "guides" else getattr(s, k)) for k in self.changes}
        self._apply(s, self.changes)

    def undo(self, doc):
        self._apply(doc.screen(self.screen_id), self.old or {})


class SetMeta(Command):
    label = "Изменить проект"

    def __init__(self, changes: dict):
        for k, v in changes.items():
            if k not in ("title", "description") or not isinstance(v, str):
                raise ModelError(f"Неверное свойство проекта: {k}")
            if k == "title" and not v.strip():
                raise ModelError("Название не может быть пустым")
        self.changes = dict(changes)
        self.old: dict | None = None

    def redo(self, doc):
        if self.old is None:
            self.old = {k: getattr(doc.meta, k) for k in self.changes}
        for k, v in self.changes.items():
            setattr(doc.meta, k, v)

    def undo(self, doc):
        for k, v in (self.old or {}).items():
            setattr(doc.meta, k, v)
