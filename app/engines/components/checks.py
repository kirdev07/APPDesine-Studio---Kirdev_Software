"""Проверки ресурсов, шрифтов и компонентов для диагностики. Без Qt: доступность шрифтов передаётся извне."""

from __future__ import annotations

from collections.abc import Callable

from app.core.document import tree
from app.core.document.model import ProjectDocument, Screen
from app.engines.layout import Diagnostic


def resource_diagnostics(doc: ProjectDocument, screen: Screen, font_available: Callable[[str], bool],
                         missing_chars: Callable[[str, str], str]) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    seen_fonts: set[str] = set()

    def diag(sev, node, msg):
        out.append(Diagnostic(sev, node.id, f"«{node.name or node.type}»: {msg}"))

    for n, _, _ in tree.walk(screen.nodes):
        if not n.visible:
            continue
        if n.type == "image":
            a = doc.asset(n.asset_id) if n.asset_id else None
            if not n.asset_id:
                diag("info", n, "ресурс изображения не выбран")
            elif a is None:
                diag("warning", n, "ресурс не найден в проекте")
            elif a.id not in doc.asset_data:
                diag("warning", n, f"файл ресурса «{a.name}» отсутствует — показана заглушка")
            elif a.redistribution == "forbidden":
                diag("info", n, f"лицензия «{a.name}» запрещает распространение")
        if n.is_instance and doc.component(n.component_id) is None:
            diag("warning", n, "мастер-компонент не найден — экземпляр не обновляется")
        if n.type == "text":
            if not font_available(n.font_family):
                if n.font_family not in seen_fonts:
                    diag("warning", n, f"шрифт «{n.font_family}» недоступен — будет использована замена")
                seen_fonts.add(n.font_family)
            else:
                miss = missing_chars(n.font_family, n.text)
                if miss:
                    diag("warning", n, f"в шрифте «{n.font_family}» нет символов: {miss[:20]}")
            if n.text_style and doc.text_style(n.text_style) is None:
                diag("info", n, "связанный текстовый стиль удалён")
    return out
