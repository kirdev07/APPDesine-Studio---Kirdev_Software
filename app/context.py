"""Сборка служб программы. UI получает их отсюда и не создаёт сам."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.paths import AppPaths
from app.core.persistence.recovery import RecoveryStore
from app.core.project.index import ProjectIndex
from app.core.project.service import ProjectService
from app.core.settings import Settings


@dataclass
class AppContext:
    paths: AppPaths
    settings: Settings
    index: ProjectIndex
    service: ProjectService
    recovery: RecoveryStore

    @classmethod
    def create(cls, paths: AppPaths | None = None) -> AppContext:
        paths = (paths or AppPaths.default()).ensure()
        settings = Settings(paths.settings_file)
        index = ProjectIndex(paths.index_db)
        service = ProjectService(paths, index, keep_backups=settings.get("project/backups_keep"))
        return cls(paths, settings, index, service, RecoveryStore(paths.recovery))

    def close(self) -> None:
        self.index.close()
