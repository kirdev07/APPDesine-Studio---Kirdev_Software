"""Генератор AI_TASK.md и README.md пакета экспорта; понятные описания взаимодействий. Без Qt.

AI_TASK.md — редактируемый текст: программа предлагает черновик по проекту, пользователь правит его перед
сборкой пакета. Разделы фиксированы контрактом экспорта (07_EXPORT_CONTRACT.md).
"""

from __future__ import annotations

from app.core.document import tree
from app.core.document.behavior import ACTION_NAMES
from app.core.document.model import PLATFORM_ANDROID, ProjectDocument
from app.engines.logic.engine import format_value

PLATFORM_STACK = {
    "android": "Android — Kotlin, Jetpack Compose, Material 3 (minSdk 26 или выше, если проект не требует иного)",
    "windows": "Windows — Python 3.12, PySide6 (Qt 6 Widgets)",
}
TRIGGER_TEXT = {"tap": "нажатие", "long_press": "долгое нажатие", "hover_enter": "наведение", "hover_leave":
                "уход курсора", "screen_open": "открытие экрана", "double_tap": "двойное нажатие",
                "swipe_left": "свайп влево", "swipe_right": "свайп вправо", "swipe_up": "свайп вверх",
                "swipe_down": "свайп вниз", "text_changed": "изменение текста"}
TRANSITION_TEXT = {"none": "без анимации", "fade": "затухание", "slide_left": "сдвиг влево",
                   "slide_right": "сдвиг вправо", "slide_up": "сдвиг вверх", "slide_down": "сдвиг вниз"}


def describe_interaction(doc: ProjectDocument, it) -> str:
    screens = {s.id: s for s in doc.screens}
    s = screens.get(it.screen_id)
    nodes = tree.node_map(s) if s else {}
    src = nodes.get(it.node_id)
    who = f" «{src.name or src.type}»" if src is not None else ""
    text = f"{TRIGGER_TEXT.get(it.trigger, it.trigger).capitalize()}{who}"
    if it.condition:
        v = doc.variable(it.condition["var_id"])
        text += f", если «{v.name if v else '?'}» {it.condition['op']} {format_value(it.condition['value'])}"
    acts = []
    for a in it.actions:
        t = a["type"]
        if t == "navigate":
            to = screens.get(a["screen_id"])
            acts.append(f"перейти на «{to.name if to else '?'}» ({TRANSITION_TEXT.get(a['transition'])}, "
                        f"{a['duration']} мс)")
        elif t == "back":
            acts.append("назад к предыдущему экрану")
        elif t == "set_variable":
            v = doc.variable(a["var_id"])
            mode = {"set": "=", "toggle": "переключить", "increment": "+=", "decrement": "-="}[a["mode"]]
            acts.append(f"«{v.name if v else '?'}» {mode} {format_value(a['value'])}".strip())
        elif t in ("set_state", "set_variant", "set_visible", "set_text", "open_overlay"):
            n = nodes.get(a["node_id"])
            name = f"«{n.name or n.type}»" if n is not None else "?"
            extra = {"set_state": f" → {a.get('state')}",
                     "set_variant": f" «{a.get('axis')}» → {a.get('value') or 'следующее значение'}", "set_visible": f" ({a.get('mode')})",
                     "set_text": f" = «{a.get('text')}»"}.get(t, "")
            acts.append(f"{ACTION_NAMES[t].lower()} {name}{extra}")
        elif t == "play_animation":
            an = doc.animation(a["animation_id"])
            acts.append(f"анимация «{an.name if an else '?'}»")
        else:
            acts.append(ACTION_NAMES[t].lower())
    return text + " → " + "; ".join(acts or ["нет действий"])


def build_task(doc: ProjectDocument, opts, screens: list, files: dict[str, str], issues: list,
               included_assets: list, excluded_assets: list, android: dict | None = None,
               prompts: list | None = None) -> str:
    """Черновик AI_TASK.md. files — {screen_id: путь JSON в пакете}."""
    m = doc.meta
    update = opts.mode == "update"
    L = [f"# Задание для Claude Code: {m.title}", ""]
    L += ["## Цель", ""]
    if update:
        L += [f"Обновить существующее приложение «{m.title}» по дизайну из этого пакета, сохранив работающую "
              "функциональность.", ""]
    else:
        L += [f"Создать новое приложение «{m.title}» по дизайну из этого пакета.", ""]
    if m.description.strip():
        L += [m.description.strip(), ""]
    L += ["## Платформа", ""]
    L += [f"- {PLATFORM_STACK[p]}" for p in opts.platforms] + [""]
    L += ["## Режим", ""]
    if update:
        L += ["**Обновление существующего проекта.** Перед изменениями изучите текущий код: структуру, навигацию, "
              "состояние, тесты. Вносите изменения точечно.", ""]
        if opts.existing_notes.strip():
            L += ["Сведения о существующем проекте:", "", opts.existing_notes.strip(), ""]
    else:
        L += ["**Новый проект.** Создайте структуру проекта, навигацию и экраны с нуля.", ""]
    if android:
        L += ["## Готовый каркас Android-проекта", "",
              f"В папке `{android['root']}/` — проект Android Studio (Kotlin, Jetpack Compose, Material 3, пакет "
              f"`{android['package']}`): Gradle, тема из токенов, `AppState` с переменными, навигация и экраны "
              "по дизайну. Он собирается как есть — используйте его как основу" +
              (" или перенесите нужные части в существующий проект." if update else "."),
              "- Сохраните структуру пакетов и маршруты навигации; доработайте места с `TODO`.",
              "- Абсолютные смещения (`offset`) замените адаптивной раскладкой, тексты вынесите в `strings.xml`.",
              ""]
        L += [f"- `{c['composable']}` (маршрут `{c['route']}`) — «{_screen_name(doc, sid)}»"
              for sid, c in android["screens"].items()] + [""]
    L += ["## Экраны для реализации", ""]
    for s in screens:
        k = _px_per_dp(s)
        size = (f"{s.width / k:.0f} × {s.height / k:.0f} dp" if s.platform == PLATFORM_ANDROID
                else f"{s.width} × {s.height} px")
        texts = [n.text for n, _, _ in tree.walk(s.nodes) if n.type == "text" and n.text.strip()][:6]
        L.append(f"- **{s.name}** ({s.platform}, {size}) — `{files[s.id]}`" +
                 (f"; тексты: {', '.join('«' + t[:40] + '»' for t in texts)}" if texts else ""))
    L += [""]
    L += ["## Правила визуальной точности", ""]
    L += ["- Координаты и размеры в JSON — в пикселях макета; для Android делите на `viewport.px_per_dp`, "
          "чтобы получить dp. Шрифты Android — в тех же единицах (переведите в sp).",
          "- Фреймы с `layout` vertical / horizontal / grid — это Auto Layout: Column / Row / сетка в Compose, "
          "QVBoxLayout / QHBoxLayout / QGridLayout в Qt. `gap`, `pad_*`, `sizing_*` (fixed / fill / hug) задают "
          "отступы и поведение размеров; `constraint_*` — привязки к краям у элементов без Auto Layout.",
          "- Цвета и стили текста берите из `styles/tokens.json`; экземпляры компонентов — из `components/` "
          "(мастер, состояния, переопределения экземпляров).",
          "- `safe_area_dp` — системные области; учитывайте отступы (WindowInsets в Compose).",
          "- Превью в `previews/` — отрисовка студии, а не Compose: ориентир по композиции, не эталон пикселей.", ""]
    its = [i for i in doc.interactions if i.screen_id in {s.id for s in screens}]
    if opts.include_interactions and its:
        L += ["## Взаимодействия и навигация", ""]
        L += [f"- {_screen_name(doc, i.screen_id)}: {describe_interaction(doc, i)}" for i in its]
        if doc.variables:
            L += ["", "Переменные состояния: " + ", ".join(
                f"«{v.name}» ({v.type}, по умолчанию {format_value(v.default)})" for v in doc.variables)]
        L += ["", "Полные данные — `interactions/logic.json` (там же поля ввода `editable` / `input_var`).", ""]
    anims = [a for a in doc.animations if a.screen_id in {s.id for s in screens}]
    if opts.include_animations and anims:
        L += ["## Анимации", ""]
        L += [f"- «{a.name}» ({_screen_name(doc, a.screen_id)}, {a.duration} мс"
              f"{', повтор' if a.loop else ''}): " + ", ".join(sorted({t.prop for t in a.tracks})) for a in anims]
        L += ["", "Ключевые кадры и плавности — `animations/animations.json`. Уважайте настройку «уменьшить "
              "движение» системы.", ""]
    L += ["## Ресурсы", ""]
    if included_assets:
        L += [f"- `{a['path']}` — {a['name']} (лицензия: {a['license'] or 'не указана'}, "
              f"распространение: {a['redistribution']})" for a in included_assets]
    else:
        L += ["- Файлов ресурсов в пакете нет."]
    for a in excluded_assets:
        L.append(f"- НЕ включён: {a['name']} — {a['reason']}. Подберите замену с подходящей лицензией.")
    L += ["", "## Ограничения интеграции", "",
          "- Без телеметрии, учётных записей и сетевых вызовов, если они не описаны в задании явно.",
          "- Не добавляйте зависимости с несовместимыми лицензиями; укажите новые зависимости в README проекта.",
          "- Логика прототипа декларативна: реализуйте её обычным кодом приложения, без интерпретатора.", ""]
    L += ["## Что не входит", "",
          "- Серверная часть, хранение данных и авторизация — только если описаны выше."]
    if not opts.include_animations:
        L.append("- Анимации в этот пакет не включены.")
    if not opts.include_interactions:
        L.append("- Логика взаимодействий в этот пакет не включена.")
    L += [""]
    L += ["## Критерии приёмки", "",
          "- Каждый экран из списка реализован; композиция, тексты, цвета и отступы соответствуют JSON и превью.",
          "- Навигация и взаимодействия ведут себя как описано выше.",
          "- Длинные русские тексты переносятся и не обрезаются; интерфейс работает на телефоне и планшете "
          "(или в окне разного размера для Windows)."]
    if doc.scenarios:
        L.append("- Тестовые сценарии из `interactions/logic.json` (`scenarios`) проходят: шаги → ожидаемый "
                 "экран и значения переменных:")
        L += [f"  - «{sc.name}»: {len(sc.steps)} шагов, итог — «{_screen_name(doc, sc.expect_screen_id)}»"
              for sc in doc.scenarios]
    L += [""]
    L += ["## Как проверить", ""]
    if "android" in opts.platforms:
        L.append("- Android: `./gradlew assembleDebug`, UI-тесты Compose для навигации и сценариев.")
    if "windows" in opts.platforms:
        L.append("- Windows: `python -m pytest` (pytest-qt) — запуск окна, навигация, сценарии.")
    L += [""]
    L += ["## Сохранение существующего поведения", ""]
    if update:
        L += ["- Не удаляйте и не переписывайте целиком работающие модули; изменения — минимальные и проверяемые.",
              "- Сохраните публичные API, форматы данных и настройки пользователя; миграции — явные.",
              "- Перед заменой экрана убедитесь, что вся его текущая функциональность перенесена.", ""]
    else:
        L += ["- Не применимо для нового проекта; при повторной генерации не затирайте уже написанный код.", ""]
    L += ["## Без разрушающих переписываний", "",
          "- Не удаляйте пользовательские данные и файлы; спорные места оставьте с пометкой TODO и опишите.", ""]
    if prompts:
        L += ["## Дополнительные указания", ""]
        for name, text in prompts:
            L += [f"### {name}", "", text.strip(), ""]
    warn = [i for i in issues if i.severity != "info"]
    if warn:
        L += ["## Замечания проверки дизайна", ""]
        L += [f"- [{i.severity}] {i.location}: {i.message}" for i in warn[:40]]
        L += [""]
    return "\n".join(L)


def build_readme(doc: ProjectDocument, manifest: dict) -> str:
    return "\n".join([
        f"# Пакет дизайна «{doc.meta.title}»",
        "",
        f"Создан App Design Studio {manifest['tool_version']} (схема экспорта {manifest['export_schema_version']}, "
        f"режим: {'обновление существующего приложения' if manifest['export_mode'] == 'update' else 'новое приложение'}).",
        "",
        "Пакет можно изучать без программы: все данные — JSON и обычные файлы.",
        "",
        "## Состав",
        "",
        "- `AI_TASK.md` — задание для Claude Code (начните с него).",
        "- `manifest.json` — экраны, компоненты, ресурсы с SHA-256 и лицензиями, связи, список всех файлов.",
        "- `screens/*.json` — экраны: размер, безопасные области, дерево элементов, взаимодействия.",
        "- `components/*.json` — мастер-компоненты, состояния, экземпляры и их переопределения.",
        "- `styles/tokens.json` — цвета, текстовые стили, оформление проекта.",
        "- `animations/animations.json` — анимации: цели, ключевые кадры, плавности.",
        "- `interactions/logic.json` — переменные, взаимодействия, тестовые сценарии.",
        "- `assets/icons|fonts|images/` — файлы ресурсов (только разрешённые к распространению).",
        "- `previews/*.png` — превью экранов (отрисовка студии).",
        "- `schemas/*.schema.json` — JSON-схемы манифеста и экрана для проверки.",
        "",
        "Целостность: SHA-256 каждого файла указан в `manifest.json` → `files`.",
        "",
    ])


def _px_per_dp(s) -> float:
    from app.engines.preview.devices import screen_dpi
    return screen_dpi(s) / 160 if s.platform == PLATFORM_ANDROID else 1.0


def _screen_name(doc, sid: str) -> str:
    return next((s.name for s in doc.screens if s.id == sid), "?")
