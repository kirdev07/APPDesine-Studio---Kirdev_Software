"""Встроенные профили устройств и шаблоны проектов (только собственные данные программы)."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.document.model import PLATFORM_ANDROID, PLATFORM_WINDOWS


@dataclass(frozen=True)
class DeviceProfile:
    id: str
    name: str
    platform: str
    width: int
    height: int
    dpi: int
    kind: str  # phone | tablet | window


DEVICES: tuple[DeviceProfile, ...] = (
    DeviceProfile("android_phone", "Android телефон", PLATFORM_ANDROID, 1080, 2400, 420, "phone"),
    DeviceProfile("android_phone_compact", "Android телефон (компактный)", PLATFORM_ANDROID, 720, 1600, 320, "phone"),
    DeviceProfile("android_tablet", "Android планшет", PLATFORM_ANDROID, 1600, 2560, 320, "tablet"),
    DeviceProfile("windows_window", "Окно Windows", PLATFORM_WINDOWS, 1280, 800, 96, "window"),
    DeviceProfile("windows_fullhd", "Windows Full HD", PLATFORM_WINDOWS, 1920, 1080, 96, "window"),
)


# Виджеты рабочего стола Android: размер в клетках лаунчера (в списки устройств проекта не входят)
WIDGET_DEVICES: tuple[DeviceProfile, ...] = tuple(
    DeviceProfile(f"android_widget_{key}", f"Виджет {key.replace('x', '×')}", PLATFORM_ANDROID,
                  round(w * 420 / 160), round(h * 420 / 160), 420, "widget")
    for key, (w, h) in (("2x1", (152, 72)), ("2x2", (152, 152)), ("4x1", (320, 72)), ("4x2", (320, 152)),
                        ("4x4", (320, 320))))


def device(device_id: str) -> DeviceProfile:
    for d in DEVICES + WIDGET_DEVICES:
        if d.id == device_id:
            return d
    raise KeyError(device_id)


@dataclass(frozen=True)
class ProjectTemplate:
    id: str
    name: str
    description: str
    platforms: tuple[str, ...]
    default_devices: tuple[str, ...]


TEMPLATES: tuple[ProjectTemplate, ...] = (
    ProjectTemplate("blank_android", "Пустой шаблон Android", "Один экран телефона", (PLATFORM_ANDROID,), ("android_phone",)),
    ProjectTemplate("blank_windows", "Пустой шаблон Windows", "Одно окно приложения", (PLATFORM_WINDOWS,), ("windows_window",)),
    ProjectTemplate(
        "blank_combined",
        "Пустой шаблон Android + Windows",
        "Экран телефона и окно Windows",
        (PLATFORM_ANDROID, PLATFORM_WINDOWS),
        ("android_phone", "windows_window"),
    ),
)


def template(template_id: str) -> ProjectTemplate:
    for t in TEMPLATES:
        if t.id == template_id:
            return t
    raise KeyError(template_id)


def templates_for(platforms: list[str] | tuple[str, ...]) -> list[ProjectTemplate]:
    return [t for t in TEMPLATES if set(t.platforms) == set(platforms)]
