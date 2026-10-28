"""Расположение служебных данных программы."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    base: Path

    @classmethod
    def default(cls) -> AppPaths:
        override = os.environ.get("ADS_DATA_DIR")
        if override:
            return cls(Path(override))
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return cls(Path(root) / "AppDesignStudio")

    @property
    def logs(self) -> Path:
        return self.base / "logs"

    @property
    def backups(self) -> Path:
        return self.base / "backups"

    @property
    def recovery(self) -> Path:
        return self.base / "recovery"

    @property
    def library(self) -> Path:
        return self.base / "library"

    @property
    def templates(self) -> Path:
        return self.base / "templates"

    @property
    def prompts(self) -> Path:
        return self.base / "prompts"

    @property
    def index_db(self) -> Path:
        return self.base / "projects.sqlite3"

    @property
    def settings_file(self) -> Path:
        return self.base / "settings.ini"

    def ensure(self) -> AppPaths:
        for p in (self.base, self.logs, self.backups, self.recovery, self.library, self.templates, self.prompts):
            p.mkdir(parents=True, exist_ok=True)
        return self


def default_projects_dir() -> Path:
    return Path.home() / "Documents" / "App Design Studio"
