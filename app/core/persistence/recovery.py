"""Автосохранение в отдельную папку восстановления (не поверх файла пользователя)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from app.core.document.model import ProjectDocument
from app.core.persistence.container import ProjectFormatError, load_project, save_project

log = logging.getLogger(__name__)


@dataclass
class RecoveryEntry:
    project_id: str
    title: str
    original_path: str
    saved_at: str
    snapshot: Path


class RecoveryStore:
    def __init__(self, folder: Path):
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)

    def _snap(self, project_id: str) -> Path:
        return self.folder / f"{project_id}.adsproj"

    def _info(self, project_id: str) -> Path:
        return self.folder / f"{project_id}.json"

    def write(self, doc: ProjectDocument, original_path: str | os.PathLike) -> None:
        save_project(doc, self._snap(doc.meta.id))
        info = {
            "project_id": doc.meta.id,
            "title": doc.meta.title,
            "original_path": str(original_path),
            "saved_at": doc.meta.modified_at,
        }
        tmp = self._info(doc.meta.id).with_suffix(".json.tmp")
        tmp.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._info(doc.meta.id))
        log.info("Автосохранение: %s", doc.meta.title)

    def clear(self, project_id: str) -> None:
        for p in (self._snap(project_id), self._info(project_id)):
            if p.exists():
                p.unlink()

    def entries(self) -> list[RecoveryEntry]:
        result = []
        for info_file in sorted(self.folder.glob("*.json")):
            try:
                info = json.loads(info_file.read_text(encoding="utf-8"))
                snap = self._snap(info["project_id"])
                if snap.exists():
                    result.append(RecoveryEntry(info["project_id"], info["title"], info["original_path"], info["saved_at"], snap))
            except (OSError, ValueError, KeyError):
                log.warning("Повреждённая запись восстановления: %s", info_file)
        return result

    def load(self, entry: RecoveryEntry) -> ProjectDocument:
        try:
            return load_project(entry.snapshot)
        except ProjectFormatError:
            log.exception("Не удалось прочитать снимок восстановления")
            raise
