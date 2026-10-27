"""Личная библиотека компонентов (общая для всех проектов) и файлы обмена .adscomp. Без Qt.

Компонент сохраняется вместе с зависимостями: вложенными компонентами, ресурсами (иконки, изображения,
файлы шрифтов из проекта) и текстовыми стилями. При вставке в другой проект зависимости копируются;
то, чего нет в пакете, перечисляется в предупреждениях.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.core.document.model import Asset, ComponentDef, ModelError, ProjectDocument, TextStyle
from app.core.persistence.container import ProjectFormatError, check_archive
from app.engines.components.engine import dependencies, sync_instances
from app.engines.layout import LayoutEngine

log = logging.getLogger(__name__)
BUNDLE_FORMAT = "ads-component-bundle"
EXTENSION = ".adscomp"


def make_bundle(doc: ProjectDocument, component_id: str) -> tuple[dict, dict[str, bytes], list[str]]:
    """Пакет компонента: JSON-описание, файлы ресурсов {archive_path: bytes} и предупреждения."""
    main = doc.component(component_id)
    if main is None:
        raise ModelError("Компонент не найден")
    deps = dependencies(doc, component_id)
    warnings = []
    assets, files = [], {}
    for aid in sorted(deps["assets"]):
        a = doc.asset(aid)
        if a is None:
            warnings.append(f"Ресурс {aid} не найден в проекте — в пакет не попадёт")
            continue
        data = doc.asset_data.get(a.id)
        if data is None:
            warnings.append(f"Файл ресурса «{a.name}» отсутствует — в пакете будет только описание")
        else:
            files[a.archive_path] = data
        if a.redistribution != "allowed":
            warnings.append(f"Лицензия ресурса «{a.name}»: распространение "
                            f"{'запрещено' if a.redistribution == 'forbidden' else 'не подтверждено'}")
        assets.append(a.to_dict())
    styles = [doc.text_style(s).to_dict() for s in sorted(deps["text_styles"]) if doc.text_style(s)]
    comps = [c.to_dict() for c in doc.components if c.id in deps["components"]]
    bundle = {"format": BUNDLE_FORMAT, "version": 1, "main": component_id, "components": comps,
              "assets": assets, "text_styles": styles, "fonts": sorted(deps["fonts"]),
              "saved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
    return bundle, files, warnings


def validate_bundle(bundle: dict) -> None:
    if not isinstance(bundle, dict) or bundle.get("format") != BUNDLE_FORMAT:
        raise ModelError("Это не пакет компонента App Design Studio")
    for key in ("components", "assets", "text_styles"):
        if not isinstance(bundle.get(key), list):
            raise ModelError(f"Пакет повреждён: нет «{key}»")
    for c in bundle["components"]:
        ComponentDef.from_dict(c)
    for a in bundle["assets"]:
        Asset.from_dict(a)
    for t in bundle["text_styles"]:
        TextStyle.from_dict(t)
    if not any(c["id"] == bundle.get("main") for c in bundle["components"]):
        raise ModelError("В пакете нет основного компонента")


def install_bundle(doc: ProjectDocument, bundle: dict, files: dict[str, bytes], engine: LayoutEngine) -> list[str]:
    """Копирует компонент и зависимости в проект. Существующий компонент с тем же id заменяется
    версией из пакета (экземпляры обновятся). Возвращает предупреждения."""
    validate_bundle(bundle)
    warnings = []
    for d in bundle["assets"]:
        a = Asset.from_dict(d)
        data = files.get(a.archive_path)
        if data is not None and hashlib.sha256(data).hexdigest() != a.sha256:
            warnings.append(f"Файл ресурса «{a.name}» повреждён — пропущен")
            data = None
        if doc.asset(a.id) is None:
            same = next((x for x in doc.assets if x.sha256 == a.sha256 and x.kind == a.kind), None)
            if same is not None:
                continue  # тот же файл уже есть в проекте
            doc.assets.append(a)
        if data is not None:
            doc.asset_data.setdefault(a.id, data)
        elif a.id not in doc.asset_data:
            warnings.append(f"Отсутствует ресурс «{a.name}» ({a.kind}) — элементы покажут заглушку")
    for d in bundle["text_styles"]:
        if doc.text_style(d["id"]) is None:
            doc.text_styles.append(TextStyle.from_dict(d))
    for d in bundle["components"]:
        c = ComponentDef.from_dict(d)
        existing = doc.component(c.id)
        if existing is not None:
            doc.components[doc.components.index(existing)] = c
        else:
            doc.components.append(c)
    project_fonts = {a.family for a in doc.assets if a.kind == "font"}
    for fam in bundle.get("fonts", []):
        if isinstance(fam, str) and fam not in project_fonts:
            warnings.append(f"Шрифт «{fam}» не входит в проект — нужен установленный в системе или будет замена")
    warnings += sync_instances(doc, engine)
    return warnings


def write_bundle_file(path: Path, bundle: dict, files: dict[str, bytes]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bundle.json", json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True))
        for p, data in sorted(files.items()):
            zf.writestr(p, data)
    os.replace(tmp, path)


def read_bundle_file(path: Path) -> tuple[dict, dict[str, bytes]]:
    try:
        with zipfile.ZipFile(path) as zf:
            check_archive(zf)
            bundle = json.loads(zf.read("bundle.json").decode("utf-8"))
            validate_bundle(bundle)
            wanted = {Asset.from_dict(a).archive_path for a in bundle["assets"]}
            files = {p: zf.read(p) for p in zf.namelist() if p in wanted}
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
        raise ModelError(f"Не удалось прочитать пакет компонента: {exc}") from None
    except ProjectFormatError as exc:
        raise ModelError(str(exc)) from None
    return bundle, files


class PersonalLibrary:
    """Папка с пакетами компонентов: <dir>/<component_id>.adscomp."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def save(self, doc: ProjectDocument, component_id: str) -> list[str]:
        bundle, files, warnings = make_bundle(doc, component_id)
        write_bundle_file(self.folder / f"{component_id}{EXTENSION}", bundle, files)
        log.info("Компонент %s сохранён в личную библиотеку", component_id)
        return warnings

    def items(self) -> list[dict]:
        out = []
        for p in sorted(self.folder.glob(f"*{EXTENSION}")):
            try:
                bundle, _ = read_bundle_file(p)
            except ModelError as exc:
                log.warning("Повреждённый пакет в библиотеке %s: %s", p, exc)
                continue
            main = next(c for c in bundle["components"] if c["id"] == bundle["main"])
            out.append({"id": main["id"], "name": main["name"], "category": main.get("category", ""),
                        "platform": main.get("platform", ""), "saved_at": bundle.get("saved_at", ""), "path": p})
        return sorted(out, key=lambda i: (i["category"].casefold(), i["name"].casefold()))

    def load(self, component_id: str) -> tuple[dict, dict[str, bytes]]:
        return read_bundle_file(self.folder / f"{component_id}{EXTENSION}")

    def remove(self, component_id: str) -> None:
        p = self.folder / f"{component_id}{EXTENSION}"
        if p.exists():
            p.unlink()
