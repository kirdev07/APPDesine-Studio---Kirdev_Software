"""Проверки экрана на устройстве предпросмотра: безопасные области, размер касания, выход за экран. Без Qt."""

from __future__ import annotations

from app.core.document import tree
from app.core.document.model import PLATFORM_ANDROID, ProjectDocument, Screen
from app.engines.layout.engine import Diagnostic
from app.engines.preview.devices import ViewSpec

MIN_TOUCH_DP = 48


def interactive_ids(doc: ProjectDocument, screen_id: str, screen: Screen) -> set[str]:
    """Элементы, с которыми взаимодействует пользователь: взаимодействия, поведение компонентов, поля ввода."""
    ids = {i.node_id for i in doc.interactions if i.screen_id == screen_id and i.node_id}
    for n, _, _ in tree.walk(screen.nodes):
        if n.is_instance and not n.ref:
            d = doc.component(n.component_id)
            if d is not None and (d.behavior.get("press") or d.behavior.get("toggle")):
                ids.add(n.id)
        if n.type == "text" and n.editable:
            ids.add(n.id)
        if n.role in TOUCH_ROLES or n.role.startswith(("m3.button_", "m3.icon_button", "m3.chip_", "m3.fab")):
            ids.add(n.id)  # стандартные кнопки и поля Material — их нажимают, даже без своих правил
    return ids


# поля и переключатели Material (верхняя панель и нижнее меню сами обходят строку состояния и жестовую полоску)
TOUCH_ROLES = ("m3.text_field", "m3.text_field_filled", "m3.text_area", "m3.password_field", "m3.phone_field",
               "m3.search_bar", "m3.date_field", "m3.dropdown_field", "m3.otp_code", "m3.switch", "m3.checkbox",
               "m3.slider", "m3.segmented", "m3.split_button", "m3.quantity")


def _scrolls(screen: Screen) -> set[str]:
    """Узлы внутри прокручиваемых фреймов (их выход за край — нормальная прокрутка)."""
    inside: set[str] = set()

    def rec(nodes, under):
        for n in nodes:
            if under:
                inside.add(n.id)
            if n.is_container:
                rec(n.children, under or (n.is_frame and n.scroll != "none"))
    rec(screen.nodes, False)
    return inside


def check(doc: ProjectDocument, screen_id: str, screen: Screen, spec: ViewSpec, visible=None) -> list[Diagnostic]:
    """screen — экран, уже перестроенный под устройство (devices.adapt). visible(node) — видимость в прототипе."""
    out: list[Diagnostic] = []
    u = spec.units(screen)
    ins = spec.insets(screen)
    m = tree.node_map(screen)
    vis = visible or (lambda n: n.visible)
    hidden: set[str] = set()
    for n, parent, _ in tree.walk(screen.nodes):
        if not vis(n) or (parent is not None and parent.id in hidden):
            hidden.add(n.id)
    ids = [i for i in interactive_ids(doc, screen_id, screen) if i in m and i not in hidden]
    for nid in sorted(ids):
        n = m[nid]
        if n.is_group:
            continue
        name = n.name or n.type
        if ins.top and n.y < ins.top and n.y + n.h > 0:
            out.append(Diagnostic("warning", nid, f"«{name}»: заходит под строку состояния — касание "
                                                   "может не сработать (безопасная область сверху)"))
        if ins.bottom and n.y + n.h > screen.height - ins.bottom and n.y < screen.height:
            out.append(Diagnostic("warning", nid, f"«{name}»: заходит на панель навигации (безопасная область "
                                                   "снизу)"))
        if ins.left and n.x < ins.left:
            out.append(Diagnostic("warning", nid, f"«{name}»: перекрыт вырезом камеры (безопасная область слева)"))
        if screen.platform == PLATFORM_ANDROID and n.type != "text" and (n.w < MIN_TOUCH_DP * u - 0.5 or n.h < MIN_TOUCH_DP * u - 0.5):
            out.append(Diagnostic("warning", nid, f"«{name}»: область касания {n.w / u:.0f} × {n.h / u:.0f} dp — "
                                                   f"меньше рекомендуемых {MIN_TOUCH_DP} × {MIN_TOUCH_DP} dp"))
    scrolled = _scrolls(screen)
    outside, flagged = [], set()
    for n, parent, _ in tree.walk(screen.nodes):
        if parent is not None and parent.id in flagged:
            flagged.add(n.id)  # о вложенных не повторяем
            continue
        if n.id in scrolled or n.id in hidden or n.is_group:
            continue
        if n.x + n.w > screen.width + 0.5 or n.y + n.h > screen.height + 0.5:
            outside.append(n)
            flagged.add(n.id)
    for n in outside[:20]:
        out.append(Diagnostic("info", n.id, f"«{n.name or n.type}»: за пределами экрана устройства — добавьте "
                                            "прокрутку контейнеру (Прокрутка: вертикальная) или уменьшите содержимое"))
    if screen.platform == PLATFORM_ANDROID and any(i.screen_id == screen_id and i.trigger in ("hover_enter",
                                                                                              "hover_leave")
                                                   for i in doc.interactions):
        out.append(Diagnostic("info", "", "«Наведение» срабатывает от мыши, тачпада или стилуса (планшет, "
                                          "Chromebook, режим компьютера); пальцем на телефоне — нет"))
    return out
