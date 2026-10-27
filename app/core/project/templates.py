"""Пользовательские шаблоны проектов: обычные файлы .adsproj в папке шаблонов программы."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.core.document.model import ProjectDocument, new_id, now_iso
from app.core.persistence.container import EXTENSION, ProjectFormatError, load_project, save_project

log = logging.getLogger(__name__)


@dataclass
class UserTemplate:
    id: str
    title: str
    platforms: list[str]
    description: str
    path: Path
    screens: int


def fresh_copy(doc: ProjectDocument, title: str) -> ProjectDocument:
    """Копия документа как новый проект: новые id проекта и экранов, новые даты."""
    copy = load_or_clone(doc)
    copy.meta.id = new_id()
    copy.meta.title = title
    copy.meta.created_at = copy.meta.modified_at = now_iso()
    for s in copy.screens:
        s.id = new_id()
    return copy


def load_or_clone(doc: ProjectDocument) -> ProjectDocument:
    from app.core.commands import DocPatch
    from app.core.document.model import ProjectMeta
    clone = ProjectDocument(meta=ProjectMeta.from_dict(doc.meta.to_dict()))
    DocPatch.restore(clone, DocPatch.capture(doc))
    return clone


class TemplateStore:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def save(self, doc: ProjectDocument, title: str, description: str = "") -> Path:
        tpl = fresh_copy(doc, title.strip() or doc.meta.title)
        tpl.meta.description = description or doc.meta.description
        tpl.meta.template_id = ""
        tpl.meta.tags = []
        path = self.folder / f"{tpl.meta.id}{EXTENSION}"
        save_project(tpl, path)
        log.info("Сохранён шаблон «%s»", tpl.meta.title)
        return path

    def items(self) -> list[UserTemplate]:
        out = []
        for p in sorted(self.folder.glob(f"*{EXTENSION}")):
            try:
                d = load_project(p)
            except ProjectFormatError as exc:
                log.warning("Шаблон %s не читается: %s", p, exc)
                continue
            out.append(UserTemplate(d.meta.id, d.meta.title, d.meta.platforms, d.meta.description, p,
                                    len(d.screens)))
        return sorted(out, key=lambda t: t.title.casefold())

    def remove(self, template_id: str) -> None:
        p = self.folder / f"{template_id}{EXTENSION}"
        if p.exists():
            p.unlink()
