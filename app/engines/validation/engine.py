"""Проверка проекта: структура, висячие ссылки, ресурсы и лицензии, раскладка, контраст, касания, логика.

Серьёзность:
- critical — ломает экспорт (висячая ссылка, нет файла ресурса, повреждённая структура); экспорт блокируется;
- warning — результат будет хуже ожидаемого (переполнение текста, низкий контраст, неизвестная лицензия);
- info — к сведению (системный шрифт, пустой экран, ресурс исключён из пакета).
Каждое замечание указывает место: экран и элемент, либо раздел проекта.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.core.document import tree
from app.core.document.model import ARTBOARD_COLORS, PLATFORM_ANDROID, ModelError, ProjectDocument, Screen
from app.engines.components.checks import resource_diagnostics
from app.engines.layout import LayoutEngine
from app.engines.preview import checks as preview_checks
from app.engines.preview.devices import ViewSpec, default_profile

SEVERITIES = ("critical", "warning", "info")
SEVERITY_RU = {"critical": "Критично", "warning": "Предупреждение", "info": "Сведения"}
MIN_CONTRAST, MIN_CONTRAST_LARGE = 4.5, 3.0
LARGE_TEXT_DP = 24
# замечания движков логики и анимации о висячих ссылках проверяются здесь отдельно (как критичные)
_DANGLING = re.compile(r"(удал[её]н[аоы]?\b|не на этом экране)")


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    location: str = ""      # «Экран «Вход» › «Кнопка»» или раздел проекта
    screen_id: str = ""
    node_id: str = ""

    def to_dict(self) -> dict:
        return {"severity": self.severity, "code": self.code, "message": self.message, "location": self.location,
                "screen_id": self.screen_id, "node_id": self.node_id}


def _lum(color: str) -> float:
    def ch(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _opaque(color: str) -> bool:
    return bool(color) and (len(color) == 7 or color[7:9].upper() == "FF")


def background_of(screen: Screen, node, artboard: str) -> str:
    """Цвет под центром элемента: верхний непрозрачный элемент ниже по порядку отрисовки, иначе фон экрана."""
    cx, cy = node.x + node.w / 2, node.y + node.h / 2
    bg = artboard
    for n, _, _ in tree.walk(screen.nodes):
        if n is node:
            break
        if n.visible and not n.is_group and n.type in ("rect", "frame", "instance", "ellipse") and \
                _opaque(n.fill) and n.opacity >= 0.99 and n.x <= cx <= n.x + n.w and n.y <= cy <= n.y + n.h:
            bg = n.fill[:7]
    return bg


class _Ctx:
    def __init__(self, doc: ProjectDocument):
        self.doc = doc
        self.out: list[Issue] = []
        self.names = {s.id: s.name for s in doc.screens}

    def add(self, sev: str, code: str, msg: str, screen: Screen | None = None, node=None, where: str = ""):
        loc = where
        if screen is not None:
            loc = f"Экран «{screen.name}»" + (f" › «{node.name or node.type}»" if node is not None else "")
        self.out.append(Issue(sev, code, msg, loc, screen.id if screen else "", node.id if node is not None else ""))


def validate_project(doc: ProjectDocument, engine: LayoutEngine, font_available: Callable[[str], bool],
                     missing_chars: Callable[[str, str], str], screen_ids: list[str] | None = None) -> list[Issue]:
    """Все замечания проекта (или выбранных экранов), отсортированные: критичные первыми, затем по месту."""
    c = _Ctx(doc)
    try:
        doc.validate()
    except ModelError as exc:
        c.add("critical", "structure", f"Структура проекта повреждена: {exc}", where="Проект")
    if not doc.screens:
        c.add("critical", "no_screens", "В проекте нет экранов", where="Проект")
    scope = [s for s in doc.screens if screen_ids is None or s.id in screen_ids]
    artboard = ARTBOARD_COLORS.get(doc.meta.appearance.theme, "#000000")
    for s in scope:
        _screen(c, s, engine, font_available, missing_chars, artboard)
    _references(c, scope)
    _components(c)
    _assets(c)
    from app.engines.animation.engine import validate as validate_animations
    from app.engines.logic.engine import validate as validate_logic
    for d in validate_animations(doc) + validate_logic(doc):
        if _DANGLING.search(d.message):
            continue
        c.add(d.severity, "logic", d.message, where="Логика и анимации")
    order = {k: i for i, k in enumerate(SEVERITIES)}
    return sorted(c.out, key=lambda i: (order[i.severity], i.location, i.message))


def _screen(c: _Ctx, s: Screen, engine, font_available, missing_chars, artboard: str) -> None:
    doc = c.doc
    m = tree.node_map(s)
    if not s.nodes:
        c.add("info", "empty_screen", "Экран пустой", s)
    if s.platform not in doc.meta.platforms:
        c.add("warning", "platform", f"Платформа экрана ({s.platform}) не выбрана в проекте", s)
    _, layout_diags = engine.layout_screen(s)
    for d in layout_diags:
        c.add(d.severity, "layout", d.message, s, m.get(d.node_id))
    for d in resource_diagnostics(doc, s, font_available, missing_chars):
        n = m.get(d.node_id)
        msg = d.message.split("»: ", 1)[-1]
        if "не найден" in msg or "отсутствует" in msg:
            c.add("critical", "missing_resource", msg, s, n)
        elif "запрещает распространение" in msg:
            c.add("warning", "license", msg + " — в пакет экспорта не войдёт", s, n)
        else:
            c.add(d.severity, "resource", msg, s, n)
    spec = ViewSpec(default_profile(s))
    for d in preview_checks.check(doc, s.id, s, spec):
        c.add(d.severity, "device", d.message.split("»: ", 1)[-1], s, m.get(d.node_id))
    u = spec.units(s)
    for n, _, _ in tree.walk(s.nodes):
        if n.type != "text" or not n.visible or not n.text.strip() or not _opaque(n.text_color):
            continue
        bg = background_of(s, n, artboard)
        ratio = contrast(n.text_color[:7], bg)
        size_dp = n.font_size / u if s.platform == PLATFORM_ANDROID else n.font_size * 0.75
        need = MIN_CONTRAST_LARGE if size_dp >= LARGE_TEXT_DP or (size_dp >= 18.5 and n.font_weight >= 700) \
            else MIN_CONTRAST
        if ratio < need:
            c.add("warning", "contrast", f"контраст текста {ratio:.1f}:1 на фоне {bg} — нужно не меньше {need:g}:1 "
                                         "(WCAG AA)", s, n)
    for n, _, _ in tree.walk(s.nodes):
        if n.is_instance and not n.ref:
            d = doc.component(n.component_id)
            if d is not None and d.platform and d.platform != s.platform:
                c.add("warning", "platform", f"компонент «{d.name}» сделан для {d.platform}, а экран — "
                                             f"{s.platform}", s, n)


def _references(c: _Ctx, scope: list[Screen]) -> None:
    doc = c.doc
    screens = {s.id: s for s in doc.screens}
    nodes = {s.id: tree.node_map(s) for s in doc.screens}
    scope_ids = {s.id for s in scope}
    vars_ = {v.id for v in doc.variables}
    anims = {a.id for a in doc.animations}
    for it in doc.interactions:
        s = screens.get(it.screen_id)
        if s is None:
            c.add("critical", "dangling", "взаимодействие ссылается на удалённый экран", where="Логика")
            continue
        if it.screen_id not in scope_ids:
            continue
        if it.node_id and it.node_id not in nodes[s.id]:
            c.add("critical", "dangling", "источник взаимодействия удалён с экрана", s)
        if it.condition and it.condition["var_id"] not in vars_:
            c.add("critical", "dangling", "условие ссылается на удалённую переменную", s, nodes[s.id].get(it.node_id))
        for a in it.actions:
            src = nodes[s.id].get(it.node_id)
            if a.get("screen_id") and a["screen_id"] not in screens:
                c.add("critical", "dangling", "переход на удалённый экран", s, src)
            if a.get("var_id") and a["var_id"] not in vars_:
                c.add("critical", "dangling", "действие с удалённой переменной", s, src)
            if a.get("animation_id") and a["animation_id"] not in anims:
                c.add("critical", "dangling", "запуск удалённой анимации", s, src)
            if a.get("node_id") and a["node_id"] not in nodes[s.id]:
                c.add("critical", "dangling", "действие с элементом, которого нет на экране", s, src)
    for a in doc.animations:
        s = screens.get(a.screen_id)
        if s is None:
            c.add("critical", "dangling", f"анимация «{a.name}» относится к удалённому экрану", where="Анимации")
            continue
        for tr in a.tracks:
            if tr.node_id not in nodes[s.id]:
                c.add("critical", "dangling", f"анимация «{a.name}»: элемент дорожки удалён", s)
    for sc in doc.scenarios:
        if sc.start_screen_id not in screens:
            c.add("warning", "scenario", f"тестовый сценарий «{sc.name}»: стартовый экран удалён",
                  where="Тестовые сценарии")
    for s in scope:
        for n, _, _ in tree.walk(s.nodes):
            if n.type == "text" and n.input_var and n.input_var not in vars_:
                c.add("critical", "dangling", "поле ввода связано с удалённой переменной", s, n)


def _components(c: _Ctx) -> None:
    doc = c.doc
    for d in doc.components:
        for n, _, _ in tree.walk([d.root]):
            if n.is_instance and not n.ref and doc.component(n.component_id) is None:
                c.add("critical", "dangling", f"во вложенном экземпляре мастер «{n.component_id}» не найден",
                      where=f"Компонент «{d.name}»")
        for state, over in d.states.items():
            refs = {x.id for x, _, _ in tree.walk([d.root])} | {"__root__"}
            for ref in over:
                if ref not in refs and ":" not in ref:
                    c.add("warning", "component", f"состояние «{state}» меняет удалённый элемент мастера",
                          where=f"Компонент «{d.name}»")


def _assets(c: _Ctx) -> None:
    for a in c.doc.assets:
        where = f"Ресурс «{a.name}»"
        if a.id not in c.doc.asset_data:
            c.add("critical", "missing_resource", "файл ресурса отсутствует в проекте", where=where)
        if a.redistribution == "unknown":
            c.add("warning", "license", "лицензия не указана — проверьте право на распространение", where=where)
        elif a.redistribution == "forbidden":
            c.add("info", "license", "распространение запрещено — в пакет экспорта не войдёт, только описание",
                  where=where)
        if not a.license.strip() and a.redistribution == "allowed":
            c.add("info", "license", "не заполнено поле «Лицензия»", where=where)


def summary(issues: list[Issue]) -> dict[str, int]:
    return {k: sum(1 for i in issues if i.severity == k) for k in SEVERITIES}
