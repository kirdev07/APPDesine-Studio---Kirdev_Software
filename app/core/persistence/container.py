"""Контейнер .adsproj (ZIP): безопасное чтение и атомарная запись."""

from __future__ import annotations

import hashlib
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
    Asset,
    ColorToken,
    ComponentDef,
    ModelError,
    ProjectDocument,
    ProjectMeta,
    Screen,
    TextStyle,
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
            raw = {"meta": project, "screens": screens}
            if version >= 4:
                raw["components"] = []
                for cid in manifest.get("components", []):
                    if not isinstance(cid, str) or not re.fullmatch(r"[0-9A-Za-z_-]{1,64}", cid):
                        raise ProjectFormatError(f"Неверный идентификатор компонента: {cid!r}")
                    raw["components"].append(_read_json(zf, f"components/{cid}.json", limits))
                raw["assets"] = _read_json(zf, "assets/assets.json", limits)
                styles = _read_json(zf, "styles/styles.json", limits)
                if not isinstance(styles, dict):
                    raise ProjectFormatError("Файл стилей повреждён")
                raw["text_styles"] = styles.get("text_styles", [])
                raw["colors"] = styles.get("colors", [])
            raw = migrate(raw, version)
            asset_bytes = _read_assets(zf, raw.get("assets", []), limits)
    except zipfile.BadZipFile:
        raise ProjectFormatError("Файл повреждён или не является ZIP-архивом") from None
    except OSError as exc:
        raise ProjectFormatError(f"Не удалось прочитать файл: {exc}") from None
    except ValueError as exc:
        raise ProjectFormatError(f"Не удалось обновить схему проекта: {exc}") from None
    try:
        for key in ("components", "assets", "text_styles", "colors"):
            if not isinstance(raw.get(key, []), list):
                raise ModelError(f"«{key}» должно быть списком")
        doc = ProjectDocument(
            meta=ProjectMeta.from_dict(raw["meta"]),
            screens=[Screen.from_dict(s) for s in raw["screens"]],
            components=[ComponentDef.from_dict(c) for c in raw.get("components", [])],
            assets=[Asset.from_dict(a) for a in raw.get("assets", [])],
            text_styles=[TextStyle.from_dict(t) for t in raw.get("text_styles", [])],
            colors=[ColorToken.from_dict(c) for c in raw.get("colors", [])],
        )
        doc.validate()
    except ModelError as exc:
        raise ProjectFormatError(f"Данные проекта повреждены: {exc}") from None
    # отсутствующие или повреждённые файлы ресурсов не мешают открыть проект — о них предупреждает диагностика
    for a in doc.assets:
        data = asset_bytes.get(a.archive_path)
        if data is not None and hashlib.sha256(data).hexdigest() == a.sha256:
            doc.asset_data[a.id] = data
        else:
            log.warning("Ресурс «%s» отсутствует или повреждён в архиве (%s)", a.name, a.archive_path)
    if manifest.get("project_id") != doc.meta.id:
        raise ProjectFormatError("Манифест не соответствует данным проекта")
    return doc


def _read_assets(zf: zipfile.ZipFile, assets: list, limits: Limits) -> dict[str, bytes]:
    names = set(zf.namelist())
    out = {}
    for a in assets if isinstance(assets, list) else []:
        if not isinstance(a, dict):
            continue
        p = f"assets/{a.get('kind')}s/{a.get('sha256')}.{str(a.get('ext', '')).lower()}"
        if p in names:
            info = zf.getinfo(p)
            if info.file_size <= limits.max_entry_size:
                out[p] = zf.read(info)
    return out


def _dump(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def write_archive(doc: ProjectDocument, target: Path) -> None:
    manifest = {
        "format": FORMAT_ID,
        "schema_version": SCHEMA_VERSION,
        "tool_version": APP_VERSION,
        "project_id": doc.meta.id,
        "screens": [s.id for s in doc.screens],
        "components": [c.id for c in doc.components],
        "assets": sorted({a.sha256: a.archive_path for a in doc.assets}.values()),
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", _dump(manifest))
        zf.writestr("project.json", _dump(doc.meta.to_dict()))
        for d in CONTENT_DIRS:
            zf.writestr(d + "/", b"")
        for screen in doc.screens:
            zf.writestr(f"screens/{screen.id}.json", _dump(screen.to_dict()))
        for comp in doc.components:
            zf.writestr(f"components/{comp.id}.json", _dump(comp.to_dict()))
        zf.writestr("styles/styles.json", _dump({"text_styles": [t.to_dict() for t in doc.text_styles],
                                                 "colors": [c.to_dict() for c in doc.colors]}))
        zf.writestr("assets/assets.json", _dump([a.to_dict() for a in doc.assets]))
        written = set()
        for a in doc.assets:
            data = doc.asset_data.get(a.id)
            if data is not None and a.archive_path not in written:
                # одинаковые файлы (один SHA-256) хранятся один раз
                zf.writestr(a.archive_path, data, compress_type=zipfile.ZIP_STORED if a.kind == "font"
                            else zipfile.ZIP_DEFLATED)
                written.add(a.archive_path)


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
