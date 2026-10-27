"""Сериализуемая модель проекта. Не зависит от Qt и целевых платформ."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

SCHEMA_VERSION = 1

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


@dataclass
class Screen:
    name: str
    platform: str
    width: int
    height: int
    device_id: str = ""
    orientation: str = "portrait"
    safe_areas: bool = True
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
            "nodes": [],
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
        return cls(
            id=_req(d, "id", str),
            name=_req(d, "name", str),
            platform=platform,
            width=width,
            height=height,
            device_id=str(d.get("device_id", "")),
            orientation=str(d.get("orientation", "portrait")),
            safe_areas=bool(d.get("safe_areas", True)),
        )


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
