"""Каркас Android-проекта в экспорте, библиотека промптов, запись проекта, кнопки страницы экспорта."""

import hashlib
import re
import xml.etree.ElementTree as ET

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import Asset, Node
from app.exporters import apk_builder
from app.exporters.ai_export import ExportOptions, build_package, check_package
from app.exporters.android_project import ROOT, ident, kstr, package_name
from app.exporters.prompts import BUILTIN, Prompt, PromptStore, render
from app.libraries import components
from app.ui.shell.main_window import PAGE_EXPORT, MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec
from tests.test_preview import doc_with_form

PNG = b"\x89PNG\r\n\x1a\n" + b"\x01" * 40


def _balanced(src: str) -> bool:
    """Скобки сбалансированы вне строк и комментариев."""
    src = re.sub(r'"(\\.|[^"\\])*"', '""', src)
    src = re.sub(r"//[^\n]*", "", src)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    stack, pairs = [], {")": "(", "]": "[", "}": "{"}
    for ch in src:
        if ch in "([{":
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                return False
    return not stack


def rich():
    doc, ids = doc_with_form()
    s = doc.screens[0]
    for kind in ("m3_button_filled", "m3_card", "m3_nav_bar"):
        n = components.build(kind, s, doc.meta.appearance)
        for c, _, _ in tree.walk([n]):  # сдвиг вместе с содержимым (координаты абсолютные)
            c.y += 1500
        s.nodes.append(n)
    a = Asset(kind="image", name="Фото героя.png", ext="png", sha256=hashlib.sha256(PNG).hexdigest(), size=len(PNG),
              license="CC0", redistribution="allowed")
    doc.assets.append(a)
    doc.asset_data[a.id] = PNG
    s.nodes.append(Node(type="image", name="Герой", x=0, y=2000, w=400, h=300, asset_id=a.id))
    return doc, ids


def test_android_project_structure_and_code():
    doc, ids = rich()
    pkg = build_package(doc, ExportOptions())
    f = pkg.files
    assert not [i for i in check_package(f) if i.severity == "critical"]
    p = package_name(doc.meta.title)
    assert re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", p)
    base = f"{ROOT}/app/src/main/java/{p.replace('.', '/')}"
    for req in ("settings.gradle.kts", "build.gradle.kts", "gradle/libs.versions.toml", "app/build.gradle.kts",
                "app/src/main/AndroidManifest.xml", "app/src/main/res/values/strings.xml", "README_ANDROID.md",
                "gradle/wrapper/gradle-wrapper.properties"):
        assert f"{ROOT}/{req}" in f, req
    for kt in ("MainActivity.kt", "AppState.kt", "navigation/AppNavHost.kt", "ui/theme/Theme.kt", "ui/theme/Type.kt",
               "ui/screens/FormaScreen.kt", "ui/screens/GotovoScreen.kt"):
        src = f[f"{base}/{kt}"].decode()
        assert src.startswith(f"package {p}") and _balanced(src), kt
    ET.fromstring(f[f"{ROOT}/app/src/main/AndroidManifest.xml"])
    ET.fromstring(f[f"{ROOT}/app/src/main/res/values/strings.xml"])
    screen = f[f"{base}/ui/screens/FormaScreen.kt"].decode()
    assert "fun FormaScreen(state: AppState, onNavigate: (String, NavMotion) -> Unit, onBack: () -> Unit)" in screen
    assert "BasicTextField(" in screen and "state.imya = it" in screen            # поле ввода → переменная
    assert "onDoubleClick" in screen and "${fmt(state.imya)}" in screen          # двойное нажатие → текст
    assert "visiblePodskazka = true" in screen                                    # «Изменение текста» → показать
    assert "TODO: жесты" not in screen and ".pointerInput(Unit) {" in screen        # свайп — настоящий жест
    assert "painterResource(R.drawable.foto_geroya)" in screen
    assert f[f"{ROOT}/app/src/main/res/drawable/foto_geroya.png"] == PNG
    nav = f[f"{base}/navigation/AppNavHost.kt"].decode()
    assert '"screen1" -> FormaScreen' in nav and "BackHandler" in nav
    state = f[f"{base}/AppState.kt"].decode()
    assert 'var imya by mutableStateOf<String>("")' in state
    man = pkg.manifest["android_project"]
    assert man["package"] == p and man["screens"][ids["form"]]["route"] == "screen1"
    assert "## Готовый каркас Android-проекта" in pkg.task
    assert build_package(doc, ExportOptions()).zip_bytes() == pkg.zip_bytes()     # детерминизм
    off = build_package(doc, ExportOptions(include_android_project=False))
    assert not any(k.startswith(ROOT) for k in off.files) and off.manifest["android_project"] is None


def test_identifiers_and_strings_are_safe():
    used = set()
    assert ident("Главный экран", True, used, "Screen") == "GlavnyyEkran"
    assert ident("Главный экран", True, used, "Screen") == "GlavnyyEkran2"
    assert ident("123", False, set(), "value") == "value123" and ident("class", False, set(), "v") == "class_"
    assert kstr('Цена: $5 "акция"\n') == '"Цена: \\$5 \\"акция\\"\\n"'
    assert package_name("Мой проект!") == "com.design.moyproekt" and package_name("2024") == "com.design.app2024"


def test_prompt_library_and_package(tmp_path):
    store = PromptStore(tmp_path / "prompts")
    assert [p.name for p in store.items()][:len(BUILTIN)] == [p.name for p in BUILTIN]
    mine = store.save(Prompt(name="Стиль команды", text="Пакет {пакет}, экраны: {экраны}. {неизвестно}"))
    assert store.get(mine.id).text.startswith("Пакет")
    with pytest.raises(ValueError):
        store.save(BUILTIN[0])
    assert render("{проект} / {режим}", {"проект": "А", "режим": "новое"}) == "А / новое"
    (tmp_path / "prompts" / "bad.json").write_text("{не json", encoding="utf-8")
    assert len(store.items()) == len(BUILTIN) + 1                                 # повреждённый файл пропущен
    doc, _ = rich()
    pkg = build_package(doc, ExportOptions(prompts=[(mine.name, mine.text), (BUILTIN[0].name, BUILTIN[0].text)]))
    body = pkg.files["prompts/01_stil_komandy.md"].decode()
    assert "Пакет com.design.predprosmotr, экраны: Форма, Готово. {неизвестно}" in body
    assert "## Дополнительные указания" in pkg.task and "### Стиль команды" in pkg.task
    assert store.delete(mine.id) and not store.delete(mine.id)


def test_write_project_and_toolchain(tmp_path):
    doc, _ = rich()
    files = build_package(doc, ExportOptions()).files
    out = apk_builder.write_project(files, tmp_path / "Проект", sdk=tmp_path / "Sdk Path")
    assert (out / "settings.gradle.kts").exists() and (out / "app" / "build.gradle.kts").exists()
    assert (out / "local.properties").read_text(encoding="utf-8").startswith("sdk.dir=")
    with pytest.raises(ValueError):
        apk_builder.write_project({f"{ROOT}/../evil.txt": b"x"}, tmp_path / "p2")
    t = apk_builder.find_toolchain()
    assert isinstance(t.problems, list) and (t.ok or t.describe())
    assert apk_builder.apk_path(out).name == "app-debug.apk"


@pytest.fixture
def app_win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)

    def discard(win):
        win.project_page.mark_clean()
        win.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.resize(1500, 950)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Андроид"))
    w.open_project(str(path))
    yield w, w.project_page.editor, ctx
    ctx.close()


def test_export_page_prompts_android_folder_and_apk(qtbot, app_win, tmp_path, monkeypatch):
    win, ed, ctx = app_win
    ed.insert_component("m3_button_filled")
    win.show_page(PAGE_EXPORT)
    page = win.export_page
    assert page.inc["include_android_project"].isChecked() and page.b_apk.isEnabled()
    assert page.prompts.count() == len(BUILTIN)
    page.save_prompt(Prompt(name="Мой стиль", text="Пишите комментарии по-русски в {проект}."))
    assert page.prompts.count() == len(BUILTIN) + 1 and [p.name for p in page._checked_prompts()] == ["Мой стиль"]
    page.rebuild()
    assert "### Мой стиль" in page.task.toPlainText() and "Пишите комментарии по-русски в Андроид." in \
        page.task.toPlainText()
    assert any(p.startswith("prompts/") for p in page.package.files)
    target = page.save_android(str(tmp_path))
    assert target is not None and (target / "app" / "src" / "main" / "AndroidManifest.xml").exists()
    monkeypatch.setattr(apk_builder, "find_toolchain", lambda: apk_builder.Toolchain(problems=["нет SDK"]))
    assert page.build_apk() is None                                               # без инструментов — понятный отказ
    page.inc["include_android_project"].setChecked(False)
    page.rebuild()
    assert not page.b_apk.isEnabled() and not any(p.startswith(ROOT) for p in page.package.files)
