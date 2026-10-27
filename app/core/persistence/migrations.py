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


def _v2_to_v3(raw: dict) -> dict:
    # В схеме 3 появились фреймы и свойства раскладки. У существующих узлов поля отсутствуют и при чтении
    # получают значения по умолчанию (фиксированный размер, привязка слева-сверху), поэтому геометрия не меняется.
    return raw


def _v3_to_v4(raw: dict) -> dict:
    # Схема 4 добавила компоненты, ресурсы, стили текста и цвета — в старых проектах их нет.
    for key in ("components", "assets", "text_styles", "colors"):
        raw.setdefault(key, [])
    return raw


def _v4_to_v5(raw: dict) -> dict:
    # Схема 5 добавила анимации, переменные и взаимодействия; у компонентов — переход и поведение (по умолчанию).
    for key in ("animations", "variables", "interactions"):
        raw.setdefault(key, [])
    return raw


# {исходная_версия: функция(raw) -> raw}
MIGRATIONS: dict[int, Callable[[dict], dict]] = {1: _v1_to_v2, 2: _v2_to_v3, 3: _v3_to_v4, 4: _v4_to_v5}


def migrate(raw: dict, version: int) -> dict:
    while version < SCHEMA_VERSION:
        step = MIGRATIONS.get(version)
        if step is None:
            raise ValueError(f"Нет миграции со схемы {version}")
        raw = step(raw)
        version += 1
    return raw
