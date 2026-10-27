"""Настройки программы (QSettings, INI в UTF-8). Телеметрии и сетевых параметров нет."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from app.core.paths import default_projects_dir

DEFAULTS = {
    "general/language": "ru",
    "general/show_hub_on_start": True,
    "general/recent_limit": 20,
    "general/projects_dir": str(default_projects_dir()),
    "project/autosave_enabled": True,
    "project/autosave_minutes": 5,
    "project/backups_keep": 5,
    "hub/view_mode": "grid",
    "hub/sort": "modified",
    "devices/default_android": "android_phone",
    "devices/default_windows": "windows_window",
    "workspace/grid_visible": True,
    "workspace/grid_size": 8,
    "workspace/snap": True,
    "workspace/guides_visible": True,
}


class Settings:
    def __init__(self, path: Path):
        self.q = QSettings(str(path), QSettings.Format.IniFormat)

    def get(self, key: str):
        default = DEFAULTS[key]
        value = self.q.value(key, default)
        if isinstance(default, bool):
            return value if isinstance(value, bool) else str(value).lower() in ("true", "1")
        if isinstance(default, int):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        return str(value)

    def set(self, key: str, value) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        self.q.setValue(key, value)
        self.q.sync()

    def reset(self) -> None:
        self.q.clear()
        self.q.sync()

    @property
    def projects_dir(self) -> Path:
        return Path(self.get("general/projects_dir"))
