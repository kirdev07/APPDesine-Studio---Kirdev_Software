"""История версий проекта: точки сохранения с подписью и автоматические копии перед каждой записью. Без Qt.

Версии лежат в папке данных программы: versions/<id проекта>/<время>__<подпись>.adsproj; автоматические копии —
backups/<id проекта>/ (их делает сохранение проекта). Откат загружает копию и подменяет содержимое одной
записью истории правок, поэтому его можно отменить.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.document.model import ProjectDocument
from app.core.persistence.container import EXTENSION, load_project, save_project

KEEP_NAMED = 100


@dataclass
class Version:
    path: Path
    when: datetime
    label: str
    auto: bool

    @property
    def title(self) -> str:
        return f"{self.when:%d.%m.%Y %H:%M} — {self.label}"


def _stamp(name: str) -> datetime | None:
    m = re.match(r"(\d{8}-\d{6})", name)
    try:
        return datetime.strptime(m.group(1), "%Y%m%d-%H%M%S") if m else None
    except ValueError:
        return None


def save_version(doc: ProjectDocument, base: Path, label: str) -> Path:
    folder = Path(base) / "versions" / doc.meta.id
    folder.mkdir(parents=True, exist_ok=True)
    clean = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", label).strip()[:60] or "Версия"
    path = folder / f"{datetime.now():%Y%m%d-%H%M%S-%f}__{clean}{EXTENSION}"
    save_project(doc, path)
    named = sorted(folder.glob(f"*{EXTENSION}"))
    for old in named[:-KEEP_NAMED]:
        old.unlink()
    return path


def list_versions(project_id: str, base: Path, backups: Path) -> list[Version]:
    """Новые сверху: свои точки сохранения и автоматические копии перед записью."""
    out = []
    for p in (Path(base) / "versions" / project_id).glob(f"*{EXTENSION}"):
        when = _stamp(p.name)
        if when:
            out.append(Version(p, when, p.stem.split("__", 1)[-1] if "__" in p.stem else "Версия", False))
    for p in (Path(backups) / project_id).glob(f"*{EXTENSION}"):
        when = _stamp(p.name)
        if when:
            out.append(Version(p, when, "автокопия перед сохранением", True))
    return sorted(out, key=lambda v: v.when, reverse=True)


def load_version(path: Path) -> ProjectDocument:
    return load_project(path)
