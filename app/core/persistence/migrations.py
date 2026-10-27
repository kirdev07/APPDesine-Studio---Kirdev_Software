"""Явные миграции схемы проекта. Каждая функция переводит версию N в N+1."""

from __future__ import annotations

from collections.abc import Callable

from app.core.document.model import SCHEMA_VERSION


def _v1_to_v2(raw: dict) -> dict:
    # В схеме 1 экраны не имели содержимого: узлы обнуляются, добавляются пустые направляющие.
    for screen in raw.get("screens", []):
        if isinstance(screen, dict):
            screen["nodes"] = []
            screen.setdefault("guides", [])
    return raw


# {исходная_версия: функция(raw) -> raw}
MIGRATIONS: dict[int, Callable[[dict], dict]] = {1: _v1_to_v2}


def migrate(raw: dict, version: int) -> dict:
    while version < SCHEMA_VERSION:
        step = MIGRATIONS.get(version)
        if step is None:
            raise ValueError(f"Нет миграции со схемы {version}")
        raw = step(raw)
        version += 1
    return raw
