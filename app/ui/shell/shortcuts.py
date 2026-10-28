"""Свои горячие клавиши: любую команду меню и рабочей области можно переназначить; хранится в настройках.

Команда узнаётся по названию (как в меню). В настройках — только отличия от стандартных клавиш:
{название: ["Ctrl+Shift+K", …]}; пустой список — команда без клавиш.
"""

from __future__ import annotations

import json

from PySide6.QtGui import QAction, QKeySequence

KEY = "keys/custom"
_DEFAULT = "ads_default_keys"
_FMT = QKeySequence.SequenceFormat.PortableText


def name_of(a: QAction) -> str:
    """Название команды; «…» в конце не различает команды (один пункт может быть в двух меню)."""
    return a.text().replace("&", "").strip().rstrip("…").strip()


def commands(root) -> dict[str, list[QAction]]:
    """Название команды → её действия (одна команда может быть в нескольких местах, например «Отменить»)."""
    out: dict[str, list[QAction]] = {}
    for a in root.findChildren(QAction):
        name = name_of(a)
        if not name or a.isSeparator() or "этап" in name or a.menu() is not None:
            continue
        out.setdefault(name, []).append(a)
    return out


def defaults(a: QAction) -> list[str]:
    """Стандартные клавиши действия (запоминаются при первом обращении)."""
    keys = a.property(_DEFAULT)
    if keys is None:
        keys = [k.toString(_FMT) for k in a.shortcuts() if not k.isEmpty()]
        a.setProperty(_DEFAULT, keys)
    return list(keys)


def current(actions: list[QAction]) -> list[str]:
    seen: list[str] = []
    for a in actions:
        for k in a.shortcuts():
            s = k.toString(_FMT)
            if s and s not in seen:
                seen.append(s)
    return seen


def load(settings) -> dict[str, list[str]]:
    try:
        data = json.loads(settings.get(KEY) or "{}")
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): [str(s) for s in v if isinstance(s, str)] for k, v in data.items() if isinstance(v, list)}


def save(settings, custom: dict[str, list[str]]) -> None:
    settings.set(KEY, json.dumps(custom, ensure_ascii=False, sort_keys=True))


def group_defaults(actions: list[QAction]) -> list[str]:
    out: list[str] = []
    for a in actions:
        out += [k for k in defaults(a) if k not in out]
    return out


def apply(root, custom: dict[str, list[str]]) -> None:
    for name, acts in commands(root).items():
        for i, a in enumerate(acts):
            std = defaults(a)  # запомнить стандартные до первой замены
            if name in custom:  # своё сочетание — у первого действия команды, иначе Qt сочтёт его неоднозначным
                keys = custom[name] if i == 0 else []
            else:
                keys = std
            a.setShortcuts([QKeySequence(s, _FMT) for s in keys])


def owner(root, seq: str, skip: str = "") -> str | None:
    """Какая команда уже занимает это сочетание."""
    want = QKeySequence(seq, _FMT).toString(_FMT)
    for name, acts in commands(root).items():
        if name != skip and want in current(acts):
            return name
    return None


def native(seqs: list[str]) -> str:
    """Как показать пользователю: «Ctrl+Shift+K / F2»."""
    return " / ".join(QKeySequence(s, _FMT).toString(QKeySequence.SequenceFormat.NativeText) for s in seqs)
