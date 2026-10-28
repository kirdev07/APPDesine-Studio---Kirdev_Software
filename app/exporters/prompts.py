"""Библиотека промптов для задания ИИ: встроенные шаблоны и свои промпты пользователя. Без Qt.

Свои промпты хранятся в %LOCALAPPDATA%\\AppDesignStudio\\prompts\\*.json и доступны во всех проектах.
В тексте можно использовать подстановки: {проект}, {платформа}, {экраны}, {пакет}, {режим}.
Выбранные промпты попадают в AI_TASK.md (раздел «Дополнительные указания») и в папку prompts/ пакета.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

MAX_TEXT = 50_000
PLACEHOLDERS = ("проект", "платформа", "экраны", "пакет", "режим")


@dataclass
class Prompt:
    name: str
    text: str
    category: str = "Мои промпты"
    builtin: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "text": self.text, "category": self.category}

    @classmethod
    def from_dict(cls, d: dict) -> Prompt:
        name, text = d.get("name"), d.get("text")
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("Неверное название промпта")
        if not isinstance(text, str) or len(text) > MAX_TEXT:
            raise ValueError("Неверный текст промпта")
        pid = d.get("id") or uuid.uuid4().hex
        if not re.fullmatch(r"[0-9a-f]{32}", str(pid)):
            raise ValueError("Неверный идентификатор промпта")
        cat = d.get("category") or "Мои промпты"
        return cls(name=name.strip(), text=text, category=str(cat)[:60], id=str(pid))


BUILTIN = [
    Prompt("Точно по макету", "Соблюдайте отступы, размеры, цвета и типографику из JSON экранов и `styles/tokens.json`. "
           "Сверяйте результат с превью в `previews/`; если что-то нельзя повторить в {платформа}, опишите отличие.",
           "Качество", True, "0" * 31 + "1"),
    Prompt("Без лишних зависимостей", "Используйте только стандартный стек ({платформа}). Каждую новую библиотеку "
           "обоснуйте и перечислите в README проекта.", "Ограничения", True, "0" * 31 + "2"),
    Prompt("Архитектура MVVM", "Вынесите состояние экранов в ViewModel, навигацию — в отдельный граф, данные — в "
           "репозитории. UI-слой экранов «{экраны}» — только отображение и события.", "Архитектура", True,
           "0" * 31 + "3"),
    Prompt("Доступность", "Добавьте описания для экранного диктора (contentDescription), минимальную область "
           "касания 48 dp, поддержку крупного шрифта системы и контраст текста не ниже 4.5:1.", "Качество", True,
           "0" * 31 + "4"),
    Prompt("UI-тесты по сценариям", "Для каждого тестового сценария из `interactions/logic.json` напишите UI-тест "
           "(Compose UI Test / pytest-qt): шаги сценария → ожидаемый экран и значения.", "Тесты", True,
           "0" * 31 + "5"),
    Prompt("Тёмная и светлая тема", "Поддержите тёмную и светлую тему системы; цвета берите из токенов проекта "
           "«{проект}», для светлой темы подберите пары с достаточным контрастом.", "Оформление", True,
           "0" * 31 + "6"),
    Prompt("Осторожное обновление", "Режим: {режим}. Перед правками опишите план изменений по файлам. Не удаляйте "
           "существующий код без замены; после каждого шага проект должен собираться.", "Ограничения", True,
           "0" * 31 + "7"),
]


class PromptStore:
    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def items(self) -> list[Prompt]:
        own = []
        if self.folder.is_dir():
            for f in sorted(self.folder.glob("*.json")):
                try:
                    own.append(Prompt.from_dict(json.loads(f.read_text(encoding="utf-8"))))
                except (OSError, ValueError):
                    continue  # повреждённый файл не мешает остальным
        return list(BUILTIN) + sorted(own, key=lambda p: (p.category, p.name.lower()))

    def get(self, pid: str) -> Prompt | None:
        return next((p for p in self.items() if p.id == pid), None)

    def save(self, prompt: Prompt) -> Prompt:
        if prompt.builtin:
            raise ValueError("Встроенный промпт нельзя изменить — создайте копию")
        Prompt.from_dict(prompt.to_dict())
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.folder / f"{prompt.id}.json.tmp"
        tmp.write_text(json.dumps(prompt.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.folder / f"{prompt.id}.json")
        return prompt

    def delete(self, pid: str) -> bool:
        f = self.folder / f"{pid}.json"
        if re.fullmatch(r"[0-9a-f]{32}", pid) and f.exists():
            f.unlink()
            return True
        return False


def render(text: str, values: dict[str, str]) -> str:
    """Подстановки {имя}; неизвестные остаются как есть."""
    return re.sub(r"\{(" + "|".join(PLACEHOLDERS) + r")\}", lambda m: values.get(m.group(1), m.group(0)), text)
