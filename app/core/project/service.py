"""Операции над проектами: создание, открытие, сохранение, дублирование, импорт/экспорт."""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from app.core.document.model import Appearance, ProjectDocument, ProjectMeta, Screen, new_id, now_iso
from app.core.paths import AppPaths
from app.core.persistence.container import EXTENSION, ProjectFormatError, load_project, save_project
from app.core.project.index import ProjectIndex, ProjectRecord
from app.libraries.catalog import device

log = logging.getLogger(__name__)

_BAD_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])$", re.IGNORECASE)


class ProjectError(Exception):
    """Ошибка операции с проектом; текст показывается пользователю."""


def validate_file_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ProjectError("Укажите название проекта")
    if _BAD_NAME.search(name):
        raise ProjectError('Название не может содержать символы < > : " / \\ | ? *')
    if _RESERVED.match(name) or name.endswith("."):
        raise ProjectError("Это имя зарезервировано Windows")
    if len(name) > 120:
        raise ProjectError("Название слишком длинное (максимум 120 символов)")
    return name


@dataclass
class NewProjectSpec:
    title: str
    location: Path
    platforms: list[str]
    template_id: str = ""
    description: str = ""
    devices: list[str] = field(default_factory=list)
    orientation: str = "portrait"
    safe_areas: bool = True
    tags: list[str] = field(default_factory=list)
    appearance: Appearance = field(default_factory=Appearance)


def build_document(spec: NewProjectSpec) -> ProjectDocument:
    meta = ProjectMeta(title=spec.title.strip(), platforms=list(spec.platforms), description=spec.description,
                       template_id=spec.template_id, tags=list(spec.tags), appearance=spec.appearance)
    screens = []
    for dev_id in spec.devices:
        d = device(dev_id)
        if d.platform not in spec.platforms:
            continue
        w, h = d.width, d.height
        if spec.orientation == "landscape" and d.kind != "window":
            w, h = h, w
        screens.append(Screen(name=f"Главный экран — {d.name}", platform=d.platform, width=w, height=h,
                              device_id=d.id, orientation=spec.orientation, safe_areas=spec.safe_areas))
    return ProjectDocument(meta=meta, screens=screens)


class ProjectService:
    def __init__(self, paths: AppPaths, index: ProjectIndex, keep_backups: int = 5):
        self.paths = paths
        self.index = index
        self.keep_backups = keep_backups

    def _register(self, doc: ProjectDocument, path: Path) -> None:
        self.index.upsert(id=doc.meta.id, path=path, title=doc.meta.title, description=doc.meta.description,
                          platforms=doc.meta.platforms, tags=doc.meta.tags, created_at=doc.meta.created_at,
                          modified_at=doc.meta.modified_at, size=path.stat().st_size, screens=len(doc.screens))

    def create(self, spec: NewProjectSpec) -> tuple[ProjectDocument, Path]:
        name = validate_file_name(spec.title)
        if not spec.platforms:
            raise ProjectError("Выберите хотя бы одну платформу")
        path = Path(spec.location) / f"{name}{EXTENSION}"
        if path.exists():
            raise ProjectError(f"Файл уже существует: {path}")
        doc = build_document(spec)
        try:
            save_project(doc, path)
        except OSError as exc:
            raise ProjectError(f"Не удалось создать проект: {exc}") from None
        self._register(doc, path)
        log.info("Создан проект «%s»: %s", doc.meta.title, path)
        return doc, path

    def open(self, path: Path | str) -> ProjectDocument:
        path = Path(path)
        try:
            doc = load_project(path)
        except ProjectFormatError:
            rec = self._record_by_path(path)
            if rec:
                self.index.mark_missing(rec.id, True)
            raise
        self._register(doc, path)
        self.index.touch_opened(doc.meta.id)
        return doc

    def save(self, doc: ProjectDocument, path: Path | str) -> Path:
        path = Path(path)
        doc.touch()
        try:
            save_project(doc, path, backup_dir=self.paths.backups, keep_backups=self.keep_backups)
        except OSError as exc:
            raise ProjectError(f"Не удалось сохранить проект: {exc}") from None
        self._register(doc, path)
        return path

    def update_meta(self, record: ProjectRecord, *, title: str | None = None, description: str | None = None,
                    tags: list[str] | None = None) -> ProjectDocument:
        doc = self.open(record.path)
        if title is not None:
            if not title.strip():
                raise ProjectError("Название не может быть пустым")
            doc.meta.title = title.strip()
        if description is not None:
            doc.meta.description = description
        if tags is not None:
            doc.meta.tags = sorted({t.strip() for t in tags if t.strip()}, key=str.casefold)
        self.save(doc, record.path)
        return doc

    def _unique_path(self, folder: Path, stem: str) -> Path:
        candidate = folder / f"{stem}{EXTENSION}"
        n = 2
        while candidate.exists():
            candidate = folder / f"{stem} ({n}){EXTENSION}"
            n += 1
        return candidate

    def duplicate(self, record: ProjectRecord) -> tuple[ProjectDocument, Path]:
        doc = load_project(record.path)
        doc.meta.id = new_id()
        doc.meta.title = f"{doc.meta.title} (копия)"
        doc.meta.created_at = doc.meta.modified_at = now_iso()
        for s in doc.screens:
            s.id = new_id()
        src = Path(record.path)
        path = self._unique_path(src.parent, f"{src.stem} (копия)")
        save_project(doc, path)
        self._register(doc, path)
        self.index.set_folder(doc.meta.id, record.folder)
        return doc, path

    def import_file(self, src: Path | str, dest_dir: Path | str) -> tuple[ProjectDocument, Path]:
        """Импорт: файл проверяется, затем копируется в папку проектов. Исходник не изменяется."""
        src = Path(src)
        doc = load_project(src)
        existing = self.index.get(doc.meta.id)
        if existing and Path(existing.path).exists() and Path(existing.path).resolve() != src.resolve():
            # Тот же проект уже есть — импортируем как отдельную копию с новым ID.
            doc.meta.id = new_id()
            for s in doc.screens:
                s.id = new_id()
        dest_dir = Path(dest_dir)
        if src.parent.resolve() == dest_dir.resolve() and not existing:
            path = src
        else:
            path = self._unique_path(dest_dir, src.stem)
            save_project(doc, path)
        self._register(doc, path)
        return doc, path

    def export_copy(self, record: ProjectRecord, target: Path | str) -> Path:
        target = Path(target)
        load_project(record.path)  # не экспортируем повреждённый файл
        shutil.copy2(record.path, target)
        return target

    def _record_by_path(self, path: Path) -> ProjectRecord | None:
        p = str(path.resolve())
        row = self.index.conn.execute("SELECT id FROM projects WHERE path = ?", (p,)).fetchone()
        return self.index.get(row[0]) if row else None

    def refresh_missing(self) -> None:
        for rec in self.index.query() + self.index.query(filter="archive"):
            self.index.mark_missing(rec.id, not Path(rec.path).exists())
