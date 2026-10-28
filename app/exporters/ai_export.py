"""AI-экспорт: детерминированный ZIP-пакет дизайна для Claude Code (07_EXPORT_CONTRACT.md). Без Qt.

Один и тот же проект с теми же настройками даёт побайтно одинаковый архив: JSON с сортировкой ключей,
устойчивые имена файлов, фиксированные дата и атрибуты записей ZIP, без отметок времени в содержимом.
Ресурсы с запретом распространения в пакет не входят — они только описаны в манифесте и задании.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from app import APP_NAME, APP_VERSION
from app.core.document import tree
from app.core.document.model import PLATFORM_ANDROID, ProjectDocument, Screen
from app.engines.preview.devices import ViewSpec, default_profile, screen_dpi
from app.engines.validation.engine import Issue
from app.exporters import schema
from app.exporters.task import build_readme, build_task, describe_interaction

REQUIRED = ("manifest.json", "AI_TASK.md", "README.md", "styles/tokens.json", "animations/animations.json",
            "interactions/logic.json", "schemas/manifest.schema.json", "schemas/screen.schema.json")
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
_RU = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class ExportError(Exception):
    pass


@dataclass
class ExportOptions:
    mode: str = "new"                  # new | update
    platforms: list[str] = field(default_factory=list)   # пусто — платформы проекта
    screen_ids: list[str] | None = None                  # None — все экраны выбранных платформ
    include_animations: bool = True
    include_interactions: bool = True
    include_assets: bool = True
    include_previews: bool = True
    include_android_project: bool = True   # каркас Android Studio (Kotlin + Compose), если выбран Android
    prompts: list = field(default_factory=list)   # [(название, текст)] — свои указания для ИИ
    existing_notes: str = ""           # режим обновления: что известно о существующем коде
    task_text: str | None = None       # отредактированный пользователем AI_TASK.md (None — черновик)


@dataclass
class ExportPackage:
    files: dict[str, bytes]
    manifest: dict
    task: str

    def zip_bytes(self) -> bytes:
        import io
        buf = io.BytesIO()
        _write_zip(buf, self.files)
        return buf.getvalue()


def slug(text: str, fallback: str = "item") -> str:
    out = "".join(_RU.get(ch, ch) for ch in text.lower())
    out = re.sub(r"[^a-z0-9]+", "_", out).strip("_")[:40] or fallback
    return out + "_" if out in _RESERVED else out


def _dump(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def scope_screens(doc: ProjectDocument, opts: ExportOptions) -> list[Screen]:
    plats = opts.platforms or doc.meta.platforms
    return [s for s in doc.screens if s.platform in plats and (opts.screen_ids is None or s.id in opts.screen_ids)]


def _components_used(doc: ProjectDocument, screens: list[Screen]) -> dict[str, list[str]]:
    """screen_id → мастера, используемые на экране (включая вложенные в мастера)."""
    out = {}
    for s in screens:
        ids: list[str] = []
        stack = [n.component_id for n, _, _ in tree.walk(s.nodes) if n.is_instance and n.component_id]
        while stack:
            cid = stack.pop(0)
            if cid in ids:
                continue
            ids.append(cid)
            d = doc.component(cid)
            if d is not None:
                stack += [n.component_id for n, _, _ in tree.walk([d.root]) if n.is_instance and n.component_id
                          and n is not d.root]
        out[s.id] = sorted(ids)
    return out


def _assets_used(doc: ProjectDocument, screens: list[Screen], comps: dict[str, list[str]]) -> dict[str, list[str]]:
    fonts: dict[str, list[str]] = {}  # семейство → все его файлы (обычный, жирный, курсив…)
    for a in doc.assets:
        if a.kind == "font" and a.family:
            fonts.setdefault(a.family, []).append(a.id)
    out = {}
    for s in screens:
        nodes = [n for n, _, _ in tree.walk(s.nodes)]
        for cid in comps[s.id]:
            d = doc.component(cid)
            if d is not None:
                nodes += [n for n, _, _ in tree.walk([d.root])]
        ids = {n.asset_id for n in nodes if n.type == "image" and n.asset_id}
        ids |= {fid for n in nodes if n.type == "text" and n.font_family in fonts for fid in fonts[n.font_family]}
        out[s.id] = sorted(i for i in ids if doc.asset(i) is not None)
    return out


def _safe_dp(s: Screen) -> dict:
    spec = ViewSpec(default_profile(s))
    ins, u = spec.insets(s), spec.units(s)
    return {k: round(getattr(ins, k) / u, 2) for k in ("top", "bottom", "left", "right")}


def build_package(doc: ProjectDocument, opts: ExportOptions, issues: list[Issue] | None = None,
                  previews: dict[str, bytes] | None = None) -> ExportPackage:
    """Собрать пакет в памяти. previews — PNG экранов {screen_id: bytes} (рисует интерфейс)."""
    if opts.mode not in ("new", "update"):
        raise ExportError("Неизвестный режим экспорта")
    opts.platforms = [p for p in (opts.platforms or doc.meta.platforms) if p in ("android", "windows")]
    screens = scope_screens(doc, opts)
    if not screens:
        raise ExportError("Не выбрано ни одного экрана для экспорта")
    sids = {s.id for s in screens}
    files: dict[str, bytes] = {}
    comps = _components_used(doc, screens)
    used_assets = _assets_used(doc, screens, comps)
    screen_files = {s.id: f"screens/{doc.screens.index(s) + 1:02d}_{slug(s.name, 'screen')}.json" for s in screens}
    interactions = [i for i in doc.interactions if i.screen_id in sids] if opts.include_interactions else []
    animations = [a for a in doc.animations if a.screen_id in sids] if opts.include_animations else []
    # экраны
    manifest_screens = []
    for s in screens:
        k = screen_dpi(s) / 160 if s.platform == PLATFORM_ANDROID else 1.0
        data = {
            "export_schema_version": schema.EXPORT_SCHEMA_VERSION, "id": s.id, "name": s.name,
            "platform": s.platform, "device_id": s.device_id,
            "viewport": {"width": s.width, "height": s.height, "unit": "px", "px_per_dp": k,
                         "width_dp": round(s.width / k, 2), "height_dp": round(s.height / k, 2)},
            "orientation": s.orientation, "safe_area_dp": _safe_dp(s),
            "nodes": [n.to_dict() for n in s.nodes], "guides": [g.to_dict() for g in s.guides],
            "interactions": [{**i.to_dict(), "description": describe_interaction(doc, i)}
                             for i in interactions if i.screen_id == s.id],
            "animations": sorted(a.id for a in animations if a.screen_id == s.id),
            "components_used": comps[s.id], "assets_used": used_assets[s.id],
        }
        files[screen_files[s.id]] = _dump(data)
        prev = None
        if opts.include_previews and previews and s.id in previews:
            prev = f"previews/{doc.screens.index(s) + 1:02d}_{slug(s.name, 'screen')}.png"
            files[prev] = previews[s.id]
        manifest_screens.append({"id": s.id, "name": s.name, "platform": s.platform, "file": screen_files[s.id],
                                 "preview": prev})
    # компоненты: мастер, состояния и все экземпляры в выбранных экранах
    all_comp = sorted({c for ids in comps.values() for c in ids})
    manifest_comps, used_names = [], set()
    for cid in all_comp:
        d = doc.component(cid)
        if d is None:
            continue
        name = slug(d.name, "component")
        while name in used_names:
            name += "_"
        used_names.add(name)
        path = f"components/{name}.json"
        instances = [{"screen_id": s.id, "node_id": n.id, "state": n.state, "overrides": dict(n.overrides)}
                     for s in screens for n, _, _ in tree.walk(s.nodes)
                     if n.is_instance and not n.ref and n.component_id == cid]
        files[path] = _dump({"export_schema_version": schema.EXPORT_SCHEMA_VERSION, "master": d.to_dict(),
                             "instances": instances})
        manifest_comps.append({"id": d.id, "name": d.name, "file": path})
    # стили, анимации, логика
    files["styles/tokens.json"] = _dump({"appearance": doc.meta.appearance.to_dict(),
                                         "colors": [c.to_dict() for c in doc.colors],
                                         "text_styles": [t.to_dict() for t in doc.text_styles]})
    files["animations/animations.json"] = _dump([a.to_dict() for a in animations])
    files["interactions/logic.json"] = _dump({
        "variables": [v.to_dict() for v in doc.variables] if opts.include_interactions else [],
        "interactions": [i.to_dict() for i in interactions],
        "scenarios": [sc.to_dict() for sc in doc.scenarios if sc.start_screen_id in sids]
        if opts.include_interactions else []})
    # ресурсы
    need = {a for ids in used_assets.values() for a in ids}
    manifest_assets, included, excluded = [], [], []
    for a in sorted(doc.assets, key=lambda x: x.id):
        rec = {"id": a.id, "kind": a.kind, "name": a.name, "path": None, "sha256": a.sha256, "size": a.size,
               "license": a.license, "source": a.source, "author": a.author, "redistribution": a.redistribution,
               "included": False}
        if a.id not in need:
            rec["reason"] = "не используется в выбранных экранах"
        elif not opts.include_assets:
            rec["reason"] = "ресурсы отключены в настройках экспорта"
        elif a.redistribution == "forbidden":
            rec["reason"] = "лицензия запрещает распространение"
        elif a.id not in doc.asset_data:
            rec["reason"] = "файл ресурса отсутствует в проекте"
        else:
            base = slug(os.path.splitext(a.name)[0], a.kind)
            rec["path"] = f"assets/{a.kind}s/{base}-{a.sha256[:8]}.{a.ext}"
            rec["included"] = True
            files[rec["path"]] = doc.asset_data[a.id]
            included.append(rec)
        if not rec["included"] and a.id in need:
            excluded.append(rec)
        manifest_assets.append(rec)
    android = None
    if opts.include_android_project and "android" in opts.platforms and any(s.platform == "android" for s in screens):
        from app.exporters.android_project import ROOT as A_ROOT, VERSIONS, AndroidProject, drawable_name
        used: set[str] = set()
        drawables = {r["id"]: (drawable_name(r["name"], used), files[r["path"]], r["path"].rsplit(".", 1)[-1])
                     for r in included if r["kind"] == "image" and r["path"].rsplit(".", 1)[-1] in ("png", "jpg", "webp")}
        from app.exporters.vector_drawable import svg_to_vector
        for r in included:  # SVG — векторным ресурсом Android
            if r["kind"] == "image" and r["path"].rsplit(".", 1)[-1].lower() == "svg":
                xml = svg_to_vector(files[r["path"]])
                if xml:
                    drawables[r["id"]] = (drawable_name(r["name"], used), xml.encode("utf-8"), "xml")
        fused: set[str] = set()
        fonts = {r["id"]: ("font_" + drawable_name(r["name"], fused), files[r["path"]], r["path"].rsplit(".", 1)[-1])
                 for r in included if r["kind"] == "font" and r["path"].rsplit(".", 1)[-1].lower() in ("ttf", "otf")}
        proj = AndroidProject(doc, screens, drawables, fonts)
        files.update(proj.files())
        android = {"root": A_ROOT, "package": proj.pkg, "versions": VERSIONS,
                   "screens": {s.id: {"composable": proj.fns[s.id], "route": proj.routes[s.id]} for s in proj.screens}}
    files["schemas/manifest.schema.json"] = _dump(schema.MANIFEST_SCHEMA)
    files["schemas/screen.schema.json"] = _dump(schema.SCREEN_SCHEMA)
    manifest = {
        "export_schema_version": schema.EXPORT_SCHEMA_VERSION, "format": "ads-ai-export", "tool": APP_NAME,
        "tool_version": APP_VERSION, "project_id": doc.meta.id, "project_title": doc.meta.title,
        "project_description": doc.meta.description, "export_mode": opts.mode,
        "target_platforms": list(opts.platforms), "screens": manifest_screens, "components": manifest_comps,
        "assets": manifest_assets,
        "references": {"start_screen": screens[0].id, "screen_components": comps, "screen_assets": used_assets,
                       "screen_files": screen_files},
        "options": {"include_animations": opts.include_animations, "include_interactions": opts.include_interactions,
                    "include_assets": opts.include_assets, "include_previews": opts.include_previews,
                    "include_android_project": bool(android)},
        "android_project": android,
    }
    from app.exporters.prompts import render
    stack = {"android": "Android (Kotlin + Jetpack Compose)", "windows": "Windows (Python + PySide6)"}
    values = {"проект": doc.meta.title, "платформа": ", ".join(stack[p] for p in opts.platforms),
              "экраны": ", ".join(s.name for s in screens), "пакет": android["package"] if android else "",
              "режим": "обновление существующего приложения" if opts.mode == "update" else "новое приложение"}
    prompts = [(name.strip()[:120] or "Промпт", render(text, values)) for name, text in opts.prompts if text.strip()]
    for i, (name, text) in enumerate(prompts, 1):
        files[f"prompts/{i:02d}_{slug(name, 'prompt')}.md"] = f"# {name}\n\n{text.strip()}\n".encode("utf-8")
    task = opts.task_text if opts.task_text is not None else build_task(
        doc, opts, screens, screen_files, issues or [], included, excluded, android, prompts)
    files["AI_TASK.md"] = task.encode("utf-8")
    files["README.md"] = build_readme(doc, manifest).encode("utf-8")
    manifest["files"] = [{"path": p, "sha256": _sha(b), "size": len(b)} for p, b in sorted(files.items())]
    files["manifest.json"] = _dump(manifest)
    return ExportPackage(dict(sorted(files.items())), manifest, task)


def _write_zip(fp, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(fp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(files):
            info = zipfile.ZipInfo(path, ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 0
            zf.writestr(info, files[path], compresslevel=9)


def write_package(pkg: ExportPackage, path: str | Path) -> Path:
    """Атомарная запись архива: временный файл рядом → проверка чтением → замена."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        _write_zip(f, pkg.files)
        f.flush()
        os.fsync(f.fileno())
    problems = check_archive(tmp)
    if any(i.severity == "critical" for i in problems):
        tmp.unlink(missing_ok=True)
        raise ExportError("Архив не прошёл проверку: " + "; ".join(i.message for i in problems[:5]))
    os.replace(tmp, path)
    return path


def check_archive(path: str | Path) -> list[Issue]:
    """Повторное чтение готового архива: пути, хэши, схемы, ссылки."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if len(names) != len(set(names)):
                return [Issue("critical", "package", "в архиве повторяются имена файлов", "Архив")]
            files = {n: zf.read(n) for n in names}
    except (zipfile.BadZipFile, OSError) as exc:
        return [Issue("critical", "package", f"архив не читается: {exc}", "Архив")]
    return check_package(files)


def check_package(files: dict[str, bytes]) -> list[Issue]:
    out: list[Issue] = []

    def bad(msg, where="Пакет"):
        out.append(Issue("critical", "package", msg, where))
    for p in files:
        parts = p.split("/")
        if p.startswith("/") or "\\" in p or ".." in parts or ":" in p or \
                any(x.split(".")[0].lower() in _RESERVED for x in parts):
            bad(f"небезопасный путь в пакете: {p}")
    for req in REQUIRED:
        if req not in files:
            bad(f"нет обязательного файла {req}")
    if "manifest.json" not in files:
        return out
    try:
        man = json.loads(files["manifest.json"])
    except ValueError:
        bad("manifest.json — не JSON")
        return out
    for e in schema.validate(man, schema.MANIFEST_SCHEMA):
        bad(f"manifest.json: {e}")
    if out:
        return out
    listed = {f["path"]: f for f in man["files"]}
    for p, b in files.items():
        if p == "manifest.json":
            continue
        if p not in listed:
            bad(f"файл не указан в манифесте: {p}")
        elif listed[p]["sha256"] != _sha(b) or listed[p]["size"] != len(b):
            bad(f"хэш не совпадает: {p}")
    for p in listed:
        if p not in files:
            bad(f"файл из манифеста отсутствует: {p}")
    comp_ids = {c["id"] for c in man["components"]}
    for c in man["components"]:
        if c["file"] not in files:
            bad(f"нет файла компонента {c['file']}", f"Компонент «{c['name']}»")
    assets = {a["id"]: a for a in man["assets"]}
    for a in man["assets"]:
        if a["included"] and (not a.get("path") or a["path"] not in files or _sha(files[a["path"]]) != a["sha256"]):
            bad("файл ресурса отсутствует или изменён", f"Ресурс «{a['name']}»")
        if a["included"] and a["redistribution"] == "forbidden":
            bad("в пакет попал ресурс с запретом распространения", f"Ресурс «{a['name']}»")
        if a["included"] and a["redistribution"] == "unknown":
            out.append(Issue("warning", "license", "лицензия не указана — проверьте право на распространение",
                             f"Ресурс «{a['name']}»"))
    for s in man["screens"]:
        where = f"Экран «{s['name']}»"
        if s["file"] not in files:
            bad(f"нет файла экрана {s['file']}", where)
            continue
        if s.get("preview") and s["preview"] not in files:
            bad(f"нет превью {s['preview']}", where)
        try:
            data = json.loads(files[s["file"]])
        except ValueError:
            bad(f"{s['file']} — не JSON", where)
            continue
        for e in schema.validate(data, schema.SCREEN_SCHEMA)[:10]:
            bad(f"{s['file']}: {e}", where)
        for cid in data.get("components_used", []):
            if cid not in comp_ids:
                bad(f"компонент {cid} не включён в пакет", where)
        for aid in data.get("assets_used", []):
            if aid not in assets:
                bad(f"ресурс {aid} не описан в манифесте", where)
            elif not assets[aid]["included"]:
                out.append(Issue("info", "asset", f"ресурс «{assets[aid]['name']}» не включён: "
                                                  f"{assets[aid].get('reason', '')}", where))
    if not files.get("AI_TASK.md", b"").strip():
        bad("AI_TASK.md пустой")
    return out
