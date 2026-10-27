"""Сериализуемая модель проекта. Не зависит от Qt и целевых платформ."""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

# 1 — этап 1 (экраны без содержимого); 2 — узлы и направляющие; 3 — фреймы, Auto Layout и привязки.
SCHEMA_VERSION = 3

PLATFORM_ANDROID = "android"
PLATFORM_WINDOWS = "windows"
PLATFORMS = (PLATFORM_ANDROID, PLATFORM_WINDOWS)

PROJECT_TYPE_UI = "ui_design"


class ModelError(ValueError):
    """Данные проекта не соответствуют схеме."""


def new_id() -> str:
    return uuid.uuid4().hex


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _req(d: dict, key: str, typ: type | tuple[type, ...]):
    if key not in d:
        raise ModelError(f"Отсутствует поле «{key}»")
    value = d[key]
    if not isinstance(value, typ) or isinstance(value, bool) and typ is int:
        raise ModelError(f"Поле «{key}» имеет неверный тип")
    return value


@dataclass
class Appearance:
    theme: str = "amoled"
    accent: str = "#2F7BFF"
    font_family: str = "Segoe UI"
    corner_radius: int = 12
    density: str = "comfortable"

    def to_dict(self) -> dict:
        return {
            "theme": self.theme,
            "accent": self.accent,
            "font_family": self.font_family,
            "corner_radius": self.corner_radius,
            "density": self.density,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Appearance:
        if not isinstance(d, dict):
            raise ModelError("Поле «appearance» должно быть объектом")
        return cls(
            theme=str(d.get("theme", "amoled")),
            accent=str(d.get("accent", "#2F7BFF")),
            font_family=str(d.get("font_family", "Segoe UI")),
            corner_radius=int(d.get("corner_radius", 12)),
            density=str(d.get("density", "comfortable")),
        )


NODE_TYPES = ("rect", "ellipse", "text", "group", "frame")
GEOMETRY_PROPS = ("x", "y", "w", "h")
STYLE_PROPS = ("fill", "stroke", "stroke_width", "radius", "opacity")
TEXT_PROPS = ("text", "font_family", "font_size", "font_weight", "text_color", "align")
COMMON_PROPS = ("name", "visible", "locked")
# Поведение узла внутри родителя: размер в Auto Layout и привязки в обычном контейнере.
CHILD_PROPS = ("sizing_h", "sizing_v", "min_w", "max_w", "min_h", "max_h", "constraint_h", "constraint_v")
# Свойства контейнера-фрейма.
FRAME_PROPS = ("layout", "gap", "row_gap", "pad_t", "pad_r", "pad_b", "pad_l", "main_align", "cross_align",
               "grid_columns", "clip")
LEAF_PROPS = COMMON_PROPS + GEOMETRY_PROPS + STYLE_PROPS + TEXT_PROPS + CHILD_PROPS
ALLOWED_PROPS = {
    "group": COMMON_PROPS,
    "frame": COMMON_PROPS + GEOMETRY_PROPS + STYLE_PROPS + CHILD_PROPS + FRAME_PROPS,
}
ALIGNMENTS = ("left", "center", "right")
ENUMS = {
    "align": ALIGNMENTS,
    "sizing_h": ("fixed", "fill", "hug"),
    "sizing_v": ("fixed", "fill", "hug"),
    "constraint_h": ("left", "right", "left_right", "center", "scale"),
    "constraint_v": ("top", "bottom", "top_bottom", "center", "scale"),
    "layout": ("none", "vertical", "horizontal", "grid"),
    "main_align": ("start", "center", "end", "space_between"),
    "cross_align": ("start", "center", "end", "stretch"),
}
MAX_DEPTH = 32
MAX_COORD = 1_000_000.0
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")


def check_prop(name: str, value, node_type: str = "rect"):
    """Проверяет и нормализует значение свойства узла. Возвращает нормализованное значение."""
    allowed = ALLOWED_PROPS.get(node_type, LEAF_PROPS)
    if name not in allowed:
        raise ModelError(f"Свойство «{name}» недоступно для типа {node_type}")
    if name in ENUMS:
        if value not in ENUMS[name]:
            raise ModelError(f"Недопустимое значение «{name}»: {value!r}")
        return value
    if name == "grid_columns":
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 64:
            raise ModelError("Число колонок должно быть от 1 до 64")
        return value
    if name in ("visible", "locked", "clip"):
        if not isinstance(value, bool):
            raise ModelError(f"«{name}» должно быть логическим")
        return value
    if name in ("name", "text", "font_family"):
        if not isinstance(value, str) or len(value) > 100_000:
            raise ModelError(f"«{name}» должно быть строкой")
        return value
    if name in ("fill", "stroke", "text_color"):
        if not isinstance(value, str) or (value and not _COLOR.match(value)):
            raise ModelError(f"Неверный цвет «{name}»: {value!r}")
        return value.upper()
    if name == "align":
        if value not in ALIGNMENTS:
            raise ModelError("Неверное выравнивание текста")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ModelError(f"«{name}» должно быть числом")
    value = float(value)
    limits = {"w": (0, MAX_COORD), "h": (0, MAX_COORD), "stroke_width": (0, 1000), "radius": (0, MAX_COORD),
              "opacity": (0, 1), "font_size": (1, 1000), "font_weight": (100, 900)}
    for k in ("gap", "row_gap", "pad_t", "pad_r", "pad_b", "pad_l", "min_w", "max_w", "min_h", "max_h"):
        limits[k] = (0, MAX_COORD)  # для max_* ноль означает «без ограничения»
    lo, hi = limits.get(name, (-MAX_COORD, MAX_COORD))
    if not lo <= value <= hi:
        raise ModelError(f"«{name}» вне диапазона {lo}…{hi}")
    return int(round(value / 100) * 100) if name == "font_weight" else value


@dataclass
class Node:
    type: str
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    w: float = 100.0
    h: float = 100.0
    visible: bool = True
    locked: bool = False
    fill: str = "#3A3A3A"
    stroke: str = ""
    stroke_width: float = 0.0
    radius: float = 0.0
    opacity: float = 1.0
    text: str = ""
    font_family: str = "Segoe UI"
    font_size: float = 16.0
    font_weight: int = 400
    text_color: str = "#FFFFFF"
    align: str = "left"
    # поведение в родителе
    sizing_h: str = "fixed"
    sizing_v: str = "fixed"
    min_w: float = 0.0
    max_w: float = 0.0
    min_h: float = 0.0
    max_h: float = 0.0
    constraint_h: str = "left"
    constraint_v: str = "top"
    # фрейм
    layout: str = "none"
    gap: float = 0.0
    row_gap: float = 0.0
    pad_t: float = 0.0
    pad_r: float = 0.0
    pad_b: float = 0.0
    pad_l: float = 0.0
    main_align: str = "start"
    cross_align: str = "start"
    grid_columns: int = 2
    clip: bool = True
    children: list[Node] = field(default_factory=list)
    id: str = field(default_factory=new_id)

    @property
    def is_group(self) -> bool:
        return self.type == "group"

    @property
    def is_frame(self) -> bool:
        return self.type == "frame"

    @property
    def is_container(self) -> bool:
        return self.type in ("group", "frame")

    @property
    def auto_layout(self) -> bool:
        return self.is_frame and self.layout != "none"

    def to_dict(self) -> dict:
        d = {"id": self.id, "type": self.type, "name": self.name, "visible": self.visible, "locked": self.locked}
        if self.is_group:
            d["children"] = [c.to_dict() for c in self.children]
            return d
        for k in GEOMETRY_PROPS + STYLE_PROPS + CHILD_PROPS:
            d[k] = getattr(self, k)
        if self.type == "text":
            for k in TEXT_PROPS:
                d[k] = getattr(self, k)
        if self.is_frame:
            for k in FRAME_PROPS:
                d[k] = getattr(self, k)
            d["children"] = [c.to_dict() for c in self.children]
        return d

    @classmethod
    def from_dict(cls, d: dict, depth: int = 0) -> Node:
        if depth > MAX_DEPTH:
            raise ModelError("Слишком глубокая вложенность групп")
        if not isinstance(d, dict):
            raise ModelError("Узел должен быть объектом")
        node_type = d.get("type")
        if node_type not in NODE_TYPES:
            raise ModelError(f"Неизвестный тип узла: {node_type!r}")
        node = cls(type=node_type, id=_req(d, "id", str))
        if node_type == "text":
            node.fill = ""
        props = COMMON_PROPS
        if not node.is_group:
            props += GEOMETRY_PROPS + STYLE_PROPS + CHILD_PROPS
        if node_type == "text":
            props += TEXT_PROPS
        if node.is_frame:
            props += FRAME_PROPS
        for k in props:
            if k in d:
                setattr(node, k, check_prop(k, d[k], node_type))
        if node.is_container:
            children = d.get("children", [])
            if not isinstance(children, list):
                raise ModelError("children должно быть списком")
            node.children = [cls.from_dict(c, depth + 1) for c in children]
        return node


@dataclass
class Guide:
    axis: str  # "x" — вертикальная линия, "y" — горизонтальная
    pos: float
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        return {"id": self.id, "axis": self.axis, "pos": self.pos}

    @classmethod
    def from_dict(cls, d: dict) -> Guide:
        if not isinstance(d, dict) or d.get("axis") not in ("x", "y"):
            raise ModelError("Неверная направляющая")
        return cls(axis=d["axis"], pos=check_prop("x", d.get("pos", 0)), id=_req(d, "id", str))


@dataclass
class Screen:
    name: str
    platform: str
    width: int
    height: int
    device_id: str = ""
    orientation: str = "portrait"
    safe_areas: bool = True
    nodes: list[Node] = field(default_factory=list)
    guides: list[Guide] = field(default_factory=list)
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "platform": self.platform,
            "device_id": self.device_id,
            "viewport": {"width": self.width, "height": self.height},
            "orientation": self.orientation,
            "safe_areas": self.safe_areas,
            "nodes": [n.to_dict() for n in self.nodes],
            "guides": [g.to_dict() for g in self.guides],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Screen:
        if not isinstance(d, dict):
            raise ModelError("Экран должен быть объектом")
        vp = _req(d, "viewport", dict)
        platform = _req(d, "platform", str)
        if platform not in PLATFORMS:
            raise ModelError(f"Неизвестная платформа экрана: {platform}")
        width, height = _req(vp, "width", int), _req(vp, "height", int)
        if not (1 <= width <= 20000 and 1 <= height <= 20000):
            raise ModelError("Недопустимый размер экрана")
        nodes, guides = d.get("nodes", []), d.get("guides", [])
        if not isinstance(nodes, list) or not isinstance(guides, list):
            raise ModelError("nodes и guides должны быть списками")
        screen = cls(
            id=_req(d, "id", str),
            name=_req(d, "name", str),
            platform=platform,
            width=width,
            height=height,
            device_id=str(d.get("device_id", "")),
            orientation=str(d.get("orientation", "portrait")),
            safe_areas=bool(d.get("safe_areas", True)),
            nodes=[Node.from_dict(n) for n in nodes],
            guides=[Guide.from_dict(g) for g in guides],
        )
        screen.validate()
        return screen

    def validate(self) -> None:
        ids: set[str] = set()
        stack = list(self.nodes)
        while stack:
            n = stack.pop()
            if n.id in ids:
                raise ModelError(f"Повторяющийся идентификатор узла: {n.id}")
            ids.add(n.id)
            stack.extend(n.children)
        if len({g.id for g in self.guides}) != len(self.guides):
            raise ModelError("Повторяющиеся идентификаторы направляющих")


@dataclass
class ProjectMeta:
    title: str
    platforms: list[str]
    description: str = ""
    project_type: str = PROJECT_TYPE_UI
    template_id: str = ""
    tags: list[str] = field(default_factory=list)
    appearance: Appearance = field(default_factory=Appearance)
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now_iso)
    modified_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "platforms": list(self.platforms),
            "project_type": self.project_type,
            "template_id": self.template_id,
            "tags": list(self.tags),
            "appearance": self.appearance.to_dict(),
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ProjectMeta:
        if not isinstance(d, dict):
            raise ModelError("Метаданные проекта должны быть объектом")
        platforms = _req(d, "platforms", list)
        if not platforms or any(p not in PLATFORMS for p in platforms):
            raise ModelError("Недопустимый список платформ")
        tags = d.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise ModelError("Теги должны быть списком строк")
        title = _req(d, "title", str).strip()
        if not title:
            raise ModelError("Пустое название проекта")
        return cls(
            id=_req(d, "id", str),
            title=title,
            description=str(d.get("description", "")),
            platforms=list(platforms),
            project_type=str(d.get("project_type", PROJECT_TYPE_UI)),
            template_id=str(d.get("template_id", "")),
            tags=tags,
            appearance=Appearance.from_dict(d.get("appearance", {})),
            created_at=_req(d, "created_at", str),
            modified_at=_req(d, "modified_at", str),
        )


@dataclass
class ProjectDocument:
    meta: ProjectMeta
    screens: list[Screen] = field(default_factory=list)

    def touch(self) -> None:
        self.meta.modified_at = now_iso()

    def to_dict(self) -> dict:
        return {"meta": self.meta.to_dict(), "screens": [s.to_dict() for s in self.screens]}

    def validate(self) -> None:
        ids = [s.id for s in self.screens]
        if len(ids) != len(set(ids)):
            raise ModelError("Повторяющиеся идентификаторы экранов")
        for s in self.screens:
            s.validate()

    def screen(self, screen_id: str) -> Screen:
        for s in self.screens:
            if s.id == screen_id:
                return s
        raise ModelError(f"Экран не найден: {screen_id}")
