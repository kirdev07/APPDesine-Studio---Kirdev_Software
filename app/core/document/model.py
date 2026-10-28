"""Сериализуемая модель проекта. Не зависит от Qt и целевых платформ."""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

# 1 — этап 1 (экраны без содержимого); 2 — узлы и направляющие; 3 — фреймы, Auto Layout и привязки;
# 4 — векторы, изображения, компоненты и экземпляры, ресурсы, стили текста и цвета;
# 5 — анимации, переменные, взаимодействия, переходы и поведение состояний компонентов;
# 6 — сценарии предпросмотра, прокрутка, поля ввода; 7 — роль фрейма (вид компонента Material 3);
# 8 — эффекты: уровень тени, градиент, размытие; 9 — масштаб и поворот (для анимаций).
SCHEMA_VERSION = 9

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


NODE_TYPES = ("rect", "ellipse", "text", "group", "frame", "vector", "image", "instance")
GEOMETRY_PROPS = ("x", "y", "w", "h")
STYLE_PROPS = ("fill", "stroke", "stroke_width", "radius", "opacity")
# Эффекты: уровень тени Material 3 (0–5), градиент заливки (от fill к fill2 под углом), размытие слоя.
EFFECT_PROPS = ("elevation", "gradient", "fill2", "grad_angle", "blur", "scale", "rotation")
ELEVATION_DP = (0, 1, 3, 6, 8, 12)  # уровни тени Material 3, dp
GRADIENTS = ("none", "linear", "radial")
# Значения по умолчанию, которые не записываются в файл (старые проекты и экспорт не меняются).
_OMIT_DEFAULT = {"ref": "", "role": "", "elevation": 0, "gradient": "none", "fill2": "", "grad_angle": 180.0,
                 "blur": 0.0, "scale": 1.0, "rotation": 0.0}
TEXT_PROPS = ("text", "font_family", "font_size", "font_weight", "text_color", "align", "text_style")
# ref — идентификатор узла мастер-компонента, из которого получен узел экземпляра.
COMMON_PROPS = ("name", "visible", "locked", "ref")
# Поведение узла внутри родителя: размер в Auto Layout и привязки в обычном контейнере.
CHILD_PROPS = ("sizing_h", "sizing_v", "min_w", "max_w", "min_h", "max_h", "constraint_h", "constraint_v")
# Свойства контейнера-фрейма.
FRAME_PROPS = ("layout", "gap", "row_gap", "pad_t", "pad_r", "pad_b", "pad_l", "main_align", "cross_align",
               "grid_columns", "clip", "scroll", "role")
# Текстовое поле ввода в предпросмотре: текст можно набирать, значение можно связать с текстовой переменной.
INPUT_PROPS = ("editable", "input_var")
VECTOR_PROPS = ("path", "vb_w", "vb_h", "fill_rule")
INSTANCE_PROPS = ("component_id", "overrides", "state")
_STYLE = STYLE_PROPS + EFFECT_PROPS
LEAF_PROPS = COMMON_PROPS + GEOMETRY_PROPS + _STYLE + TEXT_PROPS + CHILD_PROPS + INPUT_PROPS
ALLOWED_PROPS = {
    "group": COMMON_PROPS,
    "frame": COMMON_PROPS + GEOMETRY_PROPS + _STYLE + CHILD_PROPS + FRAME_PROPS,
    "instance": COMMON_PROPS + GEOMETRY_PROPS + _STYLE + CHILD_PROPS + FRAME_PROPS + INSTANCE_PROPS,
    "vector": COMMON_PROPS + GEOMETRY_PROPS + _STYLE + CHILD_PROPS + VECTOR_PROPS,
    "image": COMMON_PROPS + GEOMETRY_PROPS + _STYLE + CHILD_PROPS + ("asset_id",),
}
# Свойства, которые экземпляр может переопределить у узлов мастера (и состояния компонента).
OVERRIDABLE = ("visible", "fill", "stroke", "stroke_width", "opacity", "radius", "text", "text_color", "font_family",
               "font_size", "font_weight", "align", "asset_id", "path", "elevation", "fill2", "blur")
ROOT_REF = "__root__"  # ключ переопределений самого корня компонента
STATE_NAMES = ("default", "hover", "focus", "pressed", "disabled", "loading", "empty", "error")
ALIGNMENTS = ("left", "center", "right")
_ID = re.compile(r"^[0-9A-Za-z_:./-]{0,512}$")
ENUMS = {
    "align": ALIGNMENTS,
    "sizing_h": ("fixed", "fill", "hug"),
    "sizing_v": ("fixed", "fill", "hug"),
    "constraint_h": ("left", "right", "left_right", "center", "scale"),
    "constraint_v": ("top", "bottom", "top_bottom", "center", "scale"),
    "layout": ("none", "vertical", "horizontal", "grid"),
    "main_align": ("start", "center", "end", "space_between"),
    "cross_align": ("start", "center", "end", "stretch"),
    "fill_rule": ("nonzero", "evenodd"),
    "scroll": ("none", "vertical", "horizontal"),
    "gradient": GRADIENTS,
}
MAX_DEPTH = 32
MAX_COORD = 1_000_000.0
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")


def check_prop(name: str, value, node_type: str = "rect"):
    """Проверяет и нормализует значение свойства узла. Возвращает нормализованное значение."""
    allowed = ALLOWED_PROPS.get(node_type, LEAF_PROPS)
    if name not in allowed:
        raise ModelError(f"Свойство «{name}» недоступно для типа {node_type}")
    if name in INPUT_PROPS and node_type != "text":
        raise ModelError(f"Свойство «{name}» есть только у текста")
    if name in ENUMS:
        if value not in ENUMS[name]:
            raise ModelError(f"Недопустимое значение «{name}»: {value!r}")
        return value
    if name == "elevation":
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < len(ELEVATION_DP):
            raise ModelError("Уровень тени должен быть от 0 до 5")
        return value
    if name == "grid_columns":
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 64:
            raise ModelError("Число колонок должно быть от 1 до 64")
        return value
    if name in ("visible", "locked", "clip", "editable"):
        if not isinstance(value, bool):
            raise ModelError(f"«{name}» должно быть логическим")
        return value
    if name in ("ref", "asset_id", "component_id", "text_style", "input_var"):
        if not isinstance(value, str) or not _ID.match(value):
            raise ModelError(f"Неверный идентификатор «{name}»")
        return value
    if name == "role":
        if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9_.]{0,64}", value):
            raise ModelError("Неверная роль фрейма")
        return value
    if name == "state":
        if not isinstance(value, str) or not re.fullmatch(r"[0-9A-Za-zА-Яа-яЁё _-]{1,64}", value):
            raise ModelError("Неверное имя состояния")
        return value
    if name == "path":
        from app.core.document.pathdata import PathError, normalize
        try:
            return normalize(value)
        except PathError as exc:
            raise ModelError(f"Неверный путь: {exc}") from None
    if name == "overrides":
        return check_overrides(value)
    if name in ("name", "text", "font_family"):
        if not isinstance(value, str) or len(value) > 100_000:
            raise ModelError(f"«{name}» должно быть строкой")
        return value
    if name in ("fill", "stroke", "text_color", "fill2"):
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
    limits["vb_w"] = limits["vb_h"] = (0.001, MAX_COORD)
    limits["grad_angle"] = (-360, 360)
    limits["blur"] = (0, 250)
    limits["scale"] = (0, 20)          # масштаб вокруг центра (1 — как нарисовано)
    limits["rotation"] = (-3600, 3600)  # поворот вокруг центра, градусы
    lo, hi = limits.get(name, (-MAX_COORD, MAX_COORD))
    if not lo <= value <= hi:
        raise ModelError(f"«{name}» вне диапазона {lo}…{hi}")
    return int(round(value / 100) * 100) if name == "font_weight" else value


def check_overrides(value) -> dict:
    """{ref: {свойство: значение}} — только переопределяемые свойства, каждое проверяется."""
    if not isinstance(value, dict) or len(value) > 10_000:
        raise ModelError("Переопределения должны быть объектом")
    out = {}
    for ref, props in value.items():
        if not isinstance(ref, str) or not _ID.match(ref) or not isinstance(props, dict):
            raise ModelError("Неверное переопределение")
        clean = {}
        for k, v in props.items():
            if k not in OVERRIDABLE:
                raise ModelError(f"Свойство «{k}» нельзя переопределять")
            node_type = "vector" if k == "path" else "image" if k == "asset_id" else "text"
            clean[k] = check_prop(k, v, node_type)
        if clean:
            out[ref] = clean
    return out


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
    # эффекты
    elevation: int = 0
    gradient: str = "none"
    fill2: str = ""
    grad_angle: float = 180.0     # как в CSS: 180 — сверху вниз, 90 — слева направо
    blur: float = 0.0
    scale: float = 1.0            # масштаб и поворот вокруг центра — для анимаций (пружина, пульс, вращение)
    rotation: float = 0.0
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
    scroll: str = "none"          # прокрутка содержимого фрейма в предпросмотре
    role: str = ""                # вид стандартного компонента (m3.switch, …) — для экспорта в Compose
    # поле ввода (текст)
    editable: bool = False
    input_var: str = ""
    # текстовый стиль (токен), вектор, изображение, экземпляр компонента
    text_style: str = ""
    path: str = ""
    vb_w: float = 24.0
    vb_h: float = 24.0
    fill_rule: str = "nonzero"
    asset_id: str = ""
    component_id: str = ""
    overrides: dict = field(default_factory=dict)
    state: str = "default"
    ref: str = ""
    children: list[Node] = field(default_factory=list)
    id: str = field(default_factory=new_id)

    @property
    def is_group(self) -> bool:
        return self.type == "group"

    @property
    def is_frame(self) -> bool:
        """Фрейм или экземпляр компонента (экземпляр — фрейм с содержимым из мастера)."""
        return self.type in ("frame", "instance")

    @property
    def is_instance(self) -> bool:
        return self.type == "instance"

    @property
    def is_container(self) -> bool:
        return self.type in ("group", "frame", "instance")

    @property
    def auto_layout(self) -> bool:
        return self.is_frame and self.layout != "none"

    def _props(self) -> tuple[str, ...]:
        props = COMMON_PROPS
        if not self.is_group:
            props += GEOMETRY_PROPS + _STYLE + CHILD_PROPS
        if self.type == "text":
            props += TEXT_PROPS + INPUT_PROPS
        if self.is_frame:
            props += FRAME_PROPS
        if self.is_instance:
            props += INSTANCE_PROPS
        if self.type == "vector":
            props += VECTOR_PROPS
        if self.type == "image":
            props += ("asset_id",)
        return props

    def to_dict(self) -> dict:
        d = {"id": self.id, "type": self.type}
        for k in self._props():
            if k in _OMIT_DEFAULT and getattr(self, k) == _OMIT_DEFAULT[k]:
                continue
            v = getattr(self, k)
            d[k] = dict(v) if isinstance(v, dict) else v
        if self.is_container:
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
        if node_type in ("text", "image"):
            node.fill = ""
        for k in node._props():
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


# цвет монтажной области по теме проекта (фон экрана, если у элементов нет своего)
ARTBOARD_COLORS = {"amoled": "#000000", "dark": "#121212", "gray": "#2B2B2B", "light": "#FFFFFF"}
ASSET_KINDS = {"icon": ("svg",), "font": ("ttf", "otf"), "image": ("png", "jpg", "jpeg", "webp", "svg")}
REDISTRIBUTION = ("allowed", "forbidden", "unknown")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _str(d: dict, key: str, default: str = "", limit: int = 2000) -> str:
    v = d.get(key, default)
    if not isinstance(v, str) or len(v) > limit:
        raise ModelError(f"Поле «{key}» должно быть строкой")
    return v


@dataclass
class Asset:
    """Ресурс проекта. Файл хранится в контейнере по пути assets/<kind>s/<sha256>.<ext>."""
    kind: str
    name: str
    ext: str
    sha256: str
    size: int = 0
    license: str = ""
    source: str = ""
    author: str = ""
    redistribution: str = "unknown"
    family: str = ""  # для шрифтов: семейство, прочитанное из файла
    id: str = field(default_factory=new_id)

    @property
    def archive_path(self) -> str:
        return f"assets/{self.kind}s/{self.sha256}.{self.ext}"

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("id", "kind", "name", "ext", "sha256", "size", "license", "source",
                                               "author", "redistribution", "family")}

    @classmethod
    def from_dict(cls, d: dict) -> Asset:
        if not isinstance(d, dict):
            raise ModelError("Ресурс должен быть объектом")
        kind, ext = _str(d, "kind"), _str(d, "ext").lower()
        if kind not in ASSET_KINDS or ext not in ASSET_KINDS[kind]:
            raise ModelError(f"Недопустимый тип ресурса: {kind}/{ext}")
        sha = _str(d, "sha256")
        if not _HEX64.match(sha):
            raise ModelError("Неверный SHA-256 ресурса")
        red = _str(d, "redistribution", "unknown")
        if red not in REDISTRIBUTION:
            raise ModelError("Неверный статус распространения")
        size = d.get("size", 0)
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ModelError("Неверный размер ресурса")
        aid = _str(d, "id")
        if not _ID.match(aid) or not aid:
            raise ModelError("Неверный идентификатор ресурса")
        return cls(kind=kind, name=_str(d, "name", limit=300), ext=ext, sha256=sha, size=size,
                   license=_str(d, "license"), source=_str(d, "source"), author=_str(d, "author"),
                   redistribution=red, family=_str(d, "family", limit=300), id=aid)


@dataclass
class TextStyle:
    name: str
    font_family: str = "Segoe UI"
    font_size: float = 16.0
    font_weight: int = 400
    text_color: str = ""  # пусто — цвет не задаётся стилем
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("id", "name", "font_family", "font_size", "font_weight", "text_color")}

    @classmethod
    def from_dict(cls, d: dict) -> TextStyle:
        if not isinstance(d, dict):
            raise ModelError("Стиль текста должен быть объектом")
        name = _str(d, "name", limit=200).strip()
        if not name:
            raise ModelError("Пустое имя стиля")
        return cls(name=name, font_family=check_prop("font_family", d.get("font_family", "Segoe UI"), "text"),
                   font_size=check_prop("font_size", d.get("font_size", 16), "text"),
                   font_weight=check_prop("font_weight", d.get("font_weight", 400), "text"),
                   text_color=check_prop("text_color", d.get("text_color", ""), "text"),
                   id=check_prop("text_style", _str(d, "id"), "text"))


@dataclass
class ColorToken:
    name: str
    value: str
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "value": self.value}

    @classmethod
    def from_dict(cls, d: dict) -> ColorToken:
        if not isinstance(d, dict):
            raise ModelError("Цвет должен быть объектом")
        name = _str(d, "name", limit=200).strip()
        value = check_prop("fill", d.get("value", ""), "rect")
        if not name or not value:
            raise ModelError("У цвета должны быть имя и значение")
        return cls(name=name, value=value, id=check_prop("ref", _str(d, "id"), "rect"))


@dataclass
class ComponentDef:
    """Мастер-компонент: корневой фрейм и состояния (переопределения поверх мастера)."""
    name: str
    root: Node
    category: str = "Мои компоненты"
    platform: str = ""
    description: str = ""
    states: dict = field(default_factory=dict)  # {состояние: {ref: {свойство: значение}}}
    version: int = 1
    transition: dict = field(default_factory=lambda: {"duration": 150, "easing": "ease_in_out"})
    behavior: dict = field(default_factory=lambda: {"hover": False, "press": False, "toggle": []})
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "category": self.category, "platform": self.platform,
                "description": self.description, "version": self.version,
                "states": {k: {r: dict(p) for r, p in v.items()} for k, v in self.states.items()},
                "transition": dict(self.transition),
                "behavior": {**self.behavior, "toggle": list(self.behavior.get("toggle", []))},
                "root": self.root.to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> ComponentDef:
        if not isinstance(d, dict):
            raise ModelError("Компонент должен быть объектом")
        root = Node.from_dict(d.get("root"))
        if not root.is_frame or root.is_instance:
            raise ModelError("Корень компонента должен быть фреймом")
        states = d.get("states", {})
        if not isinstance(states, dict) or len(states) > 64:
            raise ModelError("Неверные состояния компонента")
        clean = {}
        for k, v in states.items():
            check_prop("state", k, "instance")
            clean[k] = check_overrides(v)
        version = d.get("version", 1)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ModelError("Неверная версия компонента")
        platform = _str(d, "platform")
        if platform and platform not in PLATFORMS:
            raise ModelError("Неверная платформа компонента")
        cid = _str(d, "id")
        if not cid or not _ID.match(cid):
            raise ModelError("Неверный идентификатор компонента")
        name = _str(d, "name", limit=200).strip()
        if not name:
            raise ModelError("Пустое имя компонента")
        from app.core.document.behavior import check_behavior, check_transition
        return cls(name=name, root=root, category=_str(d, "category", "Мои компоненты", 200), platform=platform,
                   description=_str(d, "description", limit=5000), states=clean, version=version,
                   transition=check_transition(d.get("transition", {})),
                   behavior=check_behavior(d.get("behavior", {})), id=cid)


@dataclass
class ProjectDocument:
    meta: ProjectMeta
    screens: list[Screen] = field(default_factory=list)
    components: list[ComponentDef] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    text_styles: list[TextStyle] = field(default_factory=list)
    colors: list[ColorToken] = field(default_factory=list)
    animations: list = field(default_factory=list)    # behavior.Animation
    variables: list = field(default_factory=list)     # behavior.Variable
    interactions: list = field(default_factory=list)  # behavior.Interaction
    scenarios: list = field(default_factory=list)     # behavior.Scenario — тестовые сценарии предпросмотра
    # содержимое файлов ресурсов в памяти: {asset_id: bytes}. Не сериализуется в JSON.
    asset_data: dict = field(default_factory=dict, repr=False, compare=False)

    def touch(self) -> None:
        self.meta.modified_at = now_iso()

    def to_dict(self) -> dict:
        return {"meta": self.meta.to_dict(), "screens": [s.to_dict() for s in self.screens],
                "components": [c.to_dict() for c in self.components],
                "assets": [a.to_dict() for a in self.assets],
                "text_styles": [t.to_dict() for t in self.text_styles],
                "colors": [c.to_dict() for c in self.colors],
                "animations": [a.to_dict() for a in self.animations],
                "variables": [v.to_dict() for v in self.variables],
                "interactions": [i.to_dict() for i in self.interactions],
                "scenarios": [s.to_dict() for s in self.scenarios]}

    def validate(self) -> None:
        ids = [s.id for s in self.screens]
        if len(ids) != len(set(ids)):
            raise ModelError("Повторяющиеся идентификаторы экранов")
        for s in self.screens:
            s.validate()
        for group, items in (("компонентов", self.components), ("ресурсов", self.assets),
                             ("стилей", self.text_styles), ("цветов", self.colors),
                             ("анимаций", self.animations), ("переменных", self.variables),
                             ("взаимодействий", self.interactions), ("сценариев", self.scenarios)):
            if len({i.id for i in items}) != len(items):
                raise ModelError(f"Повторяющиеся идентификаторы {group}")

    def component(self, component_id: str) -> ComponentDef | None:
        return next((c for c in self.components if c.id == component_id), None)

    def asset(self, asset_id: str) -> Asset | None:
        return next((a for a in self.assets if a.id == asset_id), None)

    def animation(self, anim_id: str):
        return next((a for a in self.animations if a.id == anim_id), None)

    def variable(self, var_id: str):
        return next((v for v in self.variables if v.id == var_id), None)

    def scenario(self, scenario_id: str):
        return next((s for s in self.scenarios if s.id == scenario_id), None)

    def text_style(self, style_id: str) -> TextStyle | None:
        return next((t for t in self.text_styles if t.id == style_id), None)

    def screen(self, screen_id: str) -> Screen:
        for s in self.screens:
            if s.id == screen_id:
                return s
        raise ModelError(f"Экран не найден: {screen_id}")
