"""Контейнер .adsproj (ZIP): безопасное чтение и атомарная запись."""

from __future__ import annotations

import json
import logging
import os
import re
import stat
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app import APP_VERSION
from app.core.document.model import (
    SCHEMA_VERSION,
    ModelError,
    ProjectDocument,
    ProjectMeta,
    Screen,
)
from app.core.persistence.migrations import migrate

log = logging.getLogger(__name__)

FORMAT_ID = "adsproj"
EXTENSION = ".adsproj"
CONTENT_DIRS = ("screens", "components", "styles", "animations", "interactions", "assets")


@dataclass(frozen=True)
class Limits:
    max_entries: int = 20_000
    max_entry_size: int = 256 * 1024 * 1024
    max_total_size: int = 1024 * 1024 * 1024
    max_ratio: int = 200
    max_json_size: int = 32 * 1024 * 1024


DEFAULT_LIMITS = Limits()

_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.IGNORECASE)


class ProjectFormatError(Exception):
    """Файл проекта повреждён, небезопасен или несовместим. Текст — для пользователя."""


def _check_entry_name(name: str) -> None:
    if not name or "\\" in name or name.startswith("/") or "\x00" in name:
        raise ProjectFormatError(f"Недопустимый путь в архиве: {name!r}")
    if re.match(r"^[A-Za-z]:", name):
        raise ProjectFormatError(f"Абсолютный путь в архиве: {name!r}")
    for part in name.rstrip("/").split("/"):
        if part in ("", ".", ".."):
            raise ProjectFormatError(f"Выход за пределы архива: {name!r}")
        if _RESERVED.match(part) or part.endswith((" ", ".")) or re.search(r'[<>:"|?*]', part):
            raise ProjectFormatError(f"Недопустимое имя файла Windows: {name!r}")


def check_archive(zf: zipfile.ZipFile, limits: Limits = DEFAULT_LIMITS) -> None:
    infos = zf.infolist()
    if len(infos) > limits.max_entries:
        raise ProjectFormatError("Слишком много файлов в архиве")
    seen: set[str] = set()
    total = 0
    for info in infos:
        _check_entry_name(info.filename)
        key = info.filename.rstrip("/").casefold()
        if key in seen:
            raise ProjectFormatError(f"Повторяющееся имя в архиве: {info.filename!r}")
        seen.add(key)
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ProjectFormatError(f"Символические ссылки запрещены: {info.filename!r}")
        if info.flag_bits & 0x1:
            raise ProjectFormatError("Зашифрованные архивы не поддерживаются")
        if info.file_size > limits.max_entry_size:
            raise ProjectFormatError(f"Слишком большой файл в архиве: {info.filename!r}")
        if info.compress_size and info.file_size / info.compress_size > limits.max_ratio and info.file_size > 1024 * 1024:
            raise ProjectFormatError("Подозрительная степень сжатия (возможна ZIP-бомба)")
        total += info.file_size
        if total > limits.max_total_size:
            raise ProjectFormatError("Суммарный размер архива превышает лимит")


def _read_json(zf: zipfile.ZipFile, name: str, limits: Limits):
    try:
        info = zf.getinfo(name)
    except KeyError:
        raise ProjectFormatError(f"В проекте нет обязательного файла {name}") from None
    if info.file_size > limits.max_json_size:
        raise ProjectFormatError(f"Файл {name} слишком большой")
    with zf.open(info) as fh:
        data = fh.read(limits.max_json_size + 1)
    if len(data) > limits.max_json_size:
        raise ProjectFormatError(f"Файл {name} слишком большой")
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectFormatError(f"Файл {name} повреждён: {exc}") from None


def load_project(path: str | os.PathLike, limits: Limits = DEFAULT_LIMITS) -> ProjectDocument:
    path = Path(path)
    if not path.is_file():
        raise ProjectFormatError(f"Файл не найден: {path}")
    try:
        with zipfile.ZipFile(path) as zf:
            check_archive(zf, limits)
            manifest = _read_json(zf, "manifest.json", limits)
            if not isinstance(manifest, dict) or manifest.get("format") != FORMAT_ID:
                raise ProjectFormatError("Файл не является проектом App Design Studio")
            version = manifest.get("schema_version")
            if not isinstance(version, int) or version < 1:
                raise ProjectFormatError("Неверная версия схемы проекта")
            if version > SCHEMA_VERSION:
                raise ProjectFormatError(
                    f"Проект создан более новой версией программы (схема {version}, поддерживается {SCHEMA_VERSION})"
                )
            project = _read_json(zf, "project.json", limits)
            screens = []
            for sid in manifest.get("screens", []):
                if not isinstance(sid, str) or not re.fullmatch(r"[0-9a-f]{32}", sid):
                    raise ProjectFormatError(f"Неверный идентификатор экрана: {sid!r}")
                screens.append(_read_json(zf, f"screens/{sid}.json", limits))
            raw = migrate({"meta": project, "screens": screens}, version)
    except zipfile.BadZipFile:
        raise ProjectFormatError("Файл повреждён или не является ZIP-архивом") from None
    except OSError as exc:
        raise ProjectFormatError(f"Не удалось прочитать файл: {exc}") from None
    except ValueError as exc:
        raise ProjectFormatError(f"Не удалось обновить схему проекта: {exc}") from None
    try:
        doc = ProjectDocument(
            meta=ProjectMeta.from_dict(raw["meta"]),
            screens=[Screen.from_dict(s) for s in raw["screens"]],
        )
        doc.validate()
    except ModelError as exc:
        raise ProjectFormatError(f"Данные проекта повреждены: {exc}") from None
    if manifest.get("project_id") != doc.meta.id:
        raise ProjectFormatError("Манифест не соответствует данным проекта")
    return doc


def _dump(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def write_archive(doc: ProjectDocument, target: Path) -> None:
    manifest = {
        "format": FORMAT_ID,
        "schema_version": SCHEMA_VERSION,
        "tool_version": APP_VERSION,
        "project_id": doc.meta.id,
        "screens": [s.id for s in doc.screens],
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", _dump(manifest))
        zf.writestr("project.json", _dump(doc.meta.to_dict()))
        for d in CONTENT_DIRS:
            zf.writestr(d + "/", b"")
        for screen in doc.screens:
            zf.writestr(f"screens/{screen.id}.json", _dump(screen.to_dict()))


def save_project(doc: ProjectDocument, path: str | os.PathLike, backup_dir: Path | None = None, keep_backups: int = 5) -> Path:
    """Атомарно сохраняет проект: временный файл -> проверка чтением -> резервная копия -> замена."""
    doc.validate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex[:8]}")
    try:
        write_archive(doc, tmp)
        with open(tmp, "rb+") as fh:
            os.fsync(fh.fileno())
        load_project(tmp)
        if path.exists() and backup_dir is not None and keep_backups > 0:
            _rotate_backup(path, backup_dir / doc.meta.id, keep_backups)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    log.info("Проект сохранён: %s", path)
    return path


def _rotate_backup(path: Path, folder: Path, keep: int) -> None:
    import shutil
    from datetime import datetime

    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    shutil.copy2(path, folder / f"{stamp}{EXTENSION}")
    backups = sorted(folder.glob(f"*{EXTENSION}"))
    for old in backups[:-keep]:
        old.unlink()
