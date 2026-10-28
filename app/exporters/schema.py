"""Версионированные JSON-схемы пакета экспорта и небольшой проверяющий (подмножество JSON Schema).

Поддерживается: type (одно имя или список), required, properties, additionalProperties: false, items, enum,
pattern, minimum, $ref на #/definitions/<имя>. Этого хватает для собственных схем пакета; схемы кладутся в пакет
(schemas/), чтобы его можно было проверить без программы.
"""

from __future__ import annotations

import re

EXPORT_SCHEMA_VERSION = 1
_ID = "^[0-9A-Za-z_:./-]{1,512}$"
_SHA = "^[0-9a-f]{64}$"
_PATH = r"^(?!.*\.\.)([a-z0-9_][a-z0-9_-]*/)*[A-Za-z0-9_.][A-Za-z0-9_.-]*$"  # относительный, без «..» (папки вида drawable-nodpi — можно)

MANIFEST_SCHEMA = {
    "$id": "ads-ai-export/manifest/1",
    "type": "object",
    "required": ["export_schema_version", "format", "tool", "tool_version", "project_id", "project_title",
                 "export_mode", "target_platforms", "screens", "components", "assets", "references", "files"],
    "properties": {
        "export_schema_version": {"type": "integer", "enum": [EXPORT_SCHEMA_VERSION]},
        "format": {"type": "string", "enum": ["ads-ai-export"]},
        "tool": {"type": "string"},
        "tool_version": {"type": "string"},
        "project_id": {"type": "string", "pattern": _ID},
        "project_title": {"type": "string"},
        "project_description": {"type": "string"},
        "export_mode": {"type": "string", "enum": ["new", "update"]},
        "target_platforms": {"type": "array", "items": {"type": "string", "enum": ["android", "windows"]}},
        "screens": {"type": "array", "items": {
            "type": "object", "required": ["id", "name", "platform", "file"],
            "properties": {"id": {"type": "string", "pattern": _ID}, "name": {"type": "string"},
                           "platform": {"type": "string", "enum": ["android", "windows"]},
                           "file": {"type": "string", "pattern": _PATH},
                           "preview": {"type": ["string", "null"]}}}},
        "components": {"type": "array", "items": {
            "type": "object", "required": ["id", "name", "file"],
            "properties": {"id": {"type": "string", "pattern": _ID}, "name": {"type": "string"},
                           "file": {"type": "string", "pattern": _PATH}}}},
        "assets": {"type": "array", "items": {
            "type": "object", "required": ["id", "kind", "name", "sha256", "redistribution", "included"],
            "properties": {"id": {"type": "string", "pattern": _ID},
                           "kind": {"type": "string", "enum": ["icon", "font", "image"]},
                           "name": {"type": "string"}, "path": {"type": ["string", "null"]},
                           "sha256": {"type": "string", "pattern": _SHA}, "size": {"type": "integer", "minimum": 0},
                           "license": {"type": "string"}, "source": {"type": "string"}, "author": {"type": "string"},
                           "redistribution": {"type": "string", "enum": ["allowed", "forbidden", "unknown"]},
                           "included": {"type": "boolean"}, "reason": {"type": "string"}}}},
        "references": {"type": "object", "required": ["start_screen", "screen_components", "screen_assets"]},
        "files": {"type": "array", "items": {
            "type": "object", "required": ["path", "sha256", "size"],
            "properties": {"path": {"type": "string", "pattern": _PATH}, "sha256": {"type": "string", "pattern": _SHA},
                           "size": {"type": "integer", "minimum": 0}}}},
    },
}

SCREEN_SCHEMA = {
    "$id": "ads-ai-export/screen/1",
    "type": "object",
    "required": ["export_schema_version", "id", "name", "platform", "viewport", "orientation", "safe_area_dp",
                 "nodes", "interactions", "animations", "components_used", "assets_used"],
    "definitions": {
        "node": {"type": "object", "required": ["id", "type", "name"],
                 "properties": {"id": {"type": "string", "pattern": _ID},
                                "type": {"type": "string", "enum": ["rect", "ellipse", "text", "group", "frame",
                                                                    "vector", "image", "instance"]},
                                "children": {"type": "array", "items": {"$ref": "#/definitions/node"}}}},
    },
    "properties": {
        "export_schema_version": {"type": "integer", "enum": [EXPORT_SCHEMA_VERSION]},
        "id": {"type": "string", "pattern": _ID},
        "platform": {"type": "string", "enum": ["android", "windows"]},
        "viewport": {"type": "object", "required": ["width", "height", "unit", "px_per_dp"],
                     "properties": {"width": {"type": "integer", "minimum": 1},
                                    "height": {"type": "integer", "minimum": 1},
                                    "unit": {"type": "string", "enum": ["px"]},
                                    "px_per_dp": {"type": "number", "minimum": 0}}},
        "orientation": {"type": "string", "enum": ["portrait", "landscape"]},
        "safe_area_dp": {"type": "object", "required": ["top", "bottom", "left", "right"]},
        "nodes": {"type": "array", "items": {"$ref": "#/definitions/node"}},
        "interactions": {"type": "array"},
        "animations": {"type": "array"},
        "components_used": {"type": "array", "items": {"type": "string", "pattern": _ID}},
        "assets_used": {"type": "array", "items": {"type": "string", "pattern": _ID}},
    },
}

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _type_ok(value, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[name])


def validate(value, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """Список ошибок (пустой — документ соответствует схеме)."""
    root = root or schema
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return validate(value, root["definitions"][name], root, path)
    errs: list[str] = []
    t = schema.get("type")
    if t is not None:
        names = t if isinstance(t, list) else [t]
        if not any(_type_ok(value, n) for n in names):
            return [f"{path}: ожидается {'/'.join(names)}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: значение {value!r} не из списка")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        errs.append(f"{path}: «{value}» не соответствует шаблону")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and "minimum" in schema \
            and value < schema["minimum"]:
        errs.append(f"{path}: меньше {schema['minimum']}")
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{path}: нет поля «{k}»")
        props = schema.get("properties", {})
        for k, v in value.items():
            if k in props:
                errs += validate(v, props[k], root, f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                errs.append(f"{path}: лишнее поле «{k}»")
    if isinstance(value, list) and "items" in schema:
        for i, v in enumerate(value):
            errs += validate(v, schema["items"], root, f"{path}[{i}]")
    return errs
