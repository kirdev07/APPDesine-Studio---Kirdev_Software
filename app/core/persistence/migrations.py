"""Явные миграции схемы проекта. Каждая функция переводит версию N в N+1."""

from __future__ import annotations

from collections.abc import Callable

from app.core.document.model import SCHEMA_VERSION

# {исходная_версия: функция(raw) -> raw}. Для схемы 1 миграций ещё нет.
MIGRATIONS: dict[int, Callable[[dict], dict]] = {}


def migrate(raw: dict, version: int) -> dict:
    while version < SCHEMA_VERSION:
        step = MIGRATIONS.get(version)
        if step is None:
            raise ValueError(f"Нет миграции со схемы {version}")
        raw = step(raw)
        version += 1
    return raw
