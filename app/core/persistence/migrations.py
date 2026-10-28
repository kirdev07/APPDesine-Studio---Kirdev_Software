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


def _v5_to_v6(raw: dict) -> dict:
    # Схема 6 добавила тестовые сценарии предпросмотра; прокрутка фреймов и поля ввода — по умолчанию выключены.
    raw.setdefault("scenarios", [])
    return raw


def _v6_to_v7(raw: dict) -> dict:
    # Схема 7 добавила необязательную роль фрейма; у старых узлов её нет — значение по умолчанию пустое.
    return raw


def _v7_to_v8(raw: dict) -> dict:
    # Схема 8 добавила эффекты (тень, градиент, размытие); у старых узлов их нет — значения по умолчанию.
    return raw


def _v8_to_v9(raw: dict) -> dict:
    # Схема 9 добавила масштаб и поворот узла (по умолчанию 1 и 0) — старые проекты не меняются.
    return raw


# {исходная_версия: функция(raw) -> raw}
MIGRATIONS: dict[int, Callable[[dict], dict]] = {1: _v1_to_v2, 2: _v2_to_v3, 3: _v3_to_v4, 4: _v4_to_v5,
                                                 5: _v5_to_v6, 6: _v6_to_v7, 7: _v7_to_v8, 8: _v8_to_v9}


def migrate(raw: dict, version: int) -> dict:
    while version < SCHEMA_VERSION:
        step = MIGRATIONS.get(version)
        if step is None:
            raise ValueError(f"Нет миграции со схемы {version}")
        raw = step(raw)
        version += 1
    return raw
