"""Этап 7 — проверка проекта и AI-экспорт (S18 лицензии, S19 новый проект, S20 существующий, S21 детерминизм)."""

import hashlib
import json
import zipfile

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.behavior import Interaction, check_action
from app.core.document.model import Asset, Node, Screen
from app.engines.layout import LayoutEngine, SimpleMeasurer
from app.engines.validation.engine import contrast, summary, validate_project
from app.exporters import schema
from app.exporters.ai_export import (
    ExportError, ExportOptions, build_package, check_archive, check_package, slug, write_package,
)
from app.ui.shell.main_window import PAGE_EXPORT, PAGE_PROJECT, PAGE_VALIDATE, MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from tests.conftest import make_spec
from tests.test_preview import doc_with_form

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 2 L22 2 L12 22 Z"/></svg>'
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PREVIEW = PNG + b"preview"


def asset(kind, name, ext, data, red="allowed", lic="MIT"):
    return Asset(kind=kind, name=name, ext=ext, sha256=hashlib.sha256(data).hexdigest(), size=len(data),
                 license=lic, redistribution=red, source="тест")


def rich_doc():
    doc, ids = doc_with_form()
    form = doc.screens[0]
    icon = asset("icon", "Дом.svg", "svg", SVG)
    photo = asset("image", "Фото.png", "png", PNG, red="forbidden", lic="Только для макета")
    unknown = asset("image", "Фон.png", "png", PNG + b"1", red="unknown", lic="")
    for a, d in ((icon, SVG), (photo, PNG), (unknown, PNG + b"1")):
        doc.assets.append(a)
        doc.asset_data[a.id] = d
    form.nodes += [Node(type="image", name="Иконка", x=100, y=1200, w=144, h=144, asset_id=icon.id),
                   Node(type="image", name="Фото", x=300, y=1200, w=300, h=300, asset_id=photo.id),
                   Node(type="image", name="Фон", x=650, y=1200, w=300, h=300, asset_id=unknown.id)]
    ids.update(icon=icon.id, photo=photo.id, unknown=unknown.id)
    return doc, ids


def validate(doc, ids=None):
    return validate_project(doc, LayoutEngine(SimpleMeasurer()), lambda f: True, lambda f, t: "", ids)


# ---------- проверка проекта ----------
def test_validator_severity_and_location():
    doc, ids = rich_doc()
    form = doc.screens[0]
    gray = Node(type="rect", name="Плашка", x=0, y=1600, w=1080, h=200, fill="#777777")
    low = Node(type="text", name="Бледный", text="Плохо видно", x=40, y=1650, w=600, h=60, fill="",
               text_color="#888888", font_size=40)
    form.nodes += [gray, low]
    doc.interactions.append(Interaction(form.id, "tap", ids["next"], actions=[
        check_action({"type": "navigate", "screen_id": "deleted", "transition": "none", "duration": 0,
                      "easing": "linear"})]))
    del doc.asset_data[ids["icon"]]                     # файла ресурса нет
    issues = validate(doc)
    c = summary(issues)
    assert issues[0].severity == "critical" and c["critical"] >= 2
    crit = [i for i in issues if i.severity == "critical"]
    assert any("удалённый экран" in i.message and i.location == "Экран «Форма» › «Далее»" and
               i.node_id == ids["next"] for i in crit)
    assert any(i.code == "missing_resource" and "Иконка" in i.location for i in crit)
    warn = [i for i in issues if i.severity == "warning"]
    assert any(i.code == "contrast" and i.node_id == low.id and "WCAG" in i.message for i in warn)
    assert any(i.code == "license" and "Фон" in i.location for i in warn)        # лицензия неизвестна
    assert any("в пакет экспорта не войдёт" in i.message for i in warn)          # запрет распространения
    assert contrast("#FFFFFF", "#000000") == pytest.approx(21.0)
    # без висячих ссылок и с файлом — критичных нет
    doc.interactions.pop()
    doc.asset_data[ids["icon"]] = SVG
    assert summary(validate(doc))["critical"] == 0


# ---------- AI-экспорт ----------
def test_export_new_project_package_schema_and_determinism(tmp_path):  # S19, S21
    doc, ids = rich_doc()
    issues = validate(doc)
    pkg = build_package(doc, ExportOptions(), issues, previews={ids["form"]: PREVIEW})
    f = pkg.files
    for req in ("manifest.json", "AI_TASK.md", "README.md", "screens/01_forma.json", "screens/02_gotovo.json",
                "styles/tokens.json", "animations/animations.json", "interactions/logic.json",
                "previews/01_forma.png", "schemas/screen.schema.json"):
        assert req in f, req
    man = json.loads(f["manifest.json"])
    assert schema.validate(man, schema.MANIFEST_SCHEMA) == []
    assert man["export_mode"] == "new" and man["target_platforms"] == ["android"]
    scr = json.loads(f["screens/01_forma.json"])
    assert schema.validate(scr, schema.SCREEN_SCHEMA) == []
    assert scr["viewport"]["px_per_dp"] == pytest.approx(2.625) and scr["safe_area_dp"]["top"] == 32
    assert any("свайп влево" in i["description"].lower() for i in scr["interactions"])
    # ресурсы: разрешённый включён, запрещённый — только описан
    by_id = {a["id"]: a for a in man["assets"]}
    assert by_id[ids["icon"]]["included"] and by_id[ids["icon"]]["path"].startswith("assets/icons/dom-")
    assert not by_id[ids["photo"]]["included"] and "запрещает" in by_id[ids["photo"]]["reason"]
    assert PNG not in f.values()
    task = pkg.task
    for section in ("## Цель", "## Платформа", "## Режим", "## Экраны для реализации", "## Правила визуальной точности",
                    "## Взаимодействия и навигация", "## Ресурсы", "## Ограничения интеграции", "## Что не входит",
                    "## Критерии приёмки", "## Как проверить", "## Сохранение существующего поведения",
                    "## Без разрушающих переписываний"):
        assert section in task, section
    assert "НЕ включён: Фото.png" in task and "Kotlin, Jetpack Compose" in task
    # детерминизм: те же данные — те же байты
    again = build_package(doc, ExportOptions(), issues, previews={ids["form"]: PREVIEW})
    assert again.zip_bytes() == pkg.zip_bytes()
    # запись, повторная проверка, извлечение
    path = write_package(pkg, tmp_path / "Экспорт" / "package.zip")
    assert not (tmp_path / "Экспорт" / "package.zip.tmp").exists()
    problems = check_archive(path)
    assert not [i for i in problems if i.severity == "critical"]
    assert any(i.severity == "warning" and "Фон" in i.location for i in problems)    # S18: лицензия неизвестна
    with zipfile.ZipFile(path) as zf:
        zf.extractall(tmp_path / "out")
        assert zf.getinfo("manifest.json").date_time == (1980, 1, 1, 0, 0, 0)
    listed = {x["path"]: x["sha256"] for x in man["files"]}
    for p, sha in listed.items():
        assert hashlib.sha256((tmp_path / "out" / p).read_bytes()).hexdigest() == sha


def test_export_update_mode_scope_and_edited_task():  # S20
    doc, ids = rich_doc()
    o = ExportOptions(mode="update", screen_ids=[ids["form"]], existing_notes="Репозиторий app/, модуль chat",
                      include_animations=False)
    pkg = build_package(doc, o)
    t = pkg.task
    assert "Обновление существующего проекта" in t and "Репозиторий app/, модуль chat" in t
    assert "Не удаляйте и не переписывайте целиком" in t and "Анимации в этот пакет не включены" in t
    assert [s["id"] for s in pkg.manifest["screens"]] == [ids["form"]]
    assert not any(p.startswith("screens/02") for p in pkg.files)
    custom = build_package(doc, ExportOptions(task_text="# Своё задание\n"))
    assert custom.files["AI_TASK.md"] == "# Своё задание\n".encode()
    with pytest.raises(ExportError):
        build_package(doc, ExportOptions(platforms=["windows"]))      # экранов Windows нет
    assert slug("Главный экран") == "glavnyy_ekran" and slug("con") == "con_" and slug("***") == "item"


def test_package_check_detects_tampering_and_unsafe_paths():
    doc, ids = rich_doc()
    files = dict(build_package(doc, ExportOptions()).files)
    assert not [i for i in check_package(files) if i.severity == "critical"]
    bad = dict(files)
    bad["screens/01_forma.json"] = bad["screens/01_forma.json"].replace(b"Form", b"XXXX") + b" "
    assert any("хэш не совпадает" in i.message for i in check_package(bad))
    bad = dict(files)
    bad["../evil.txt"] = b"x"
    assert any("небезопасный путь" in i.message for i in check_package(bad))
    bad = dict(files)
    del bad["AI_TASK.md"]
    assert any("AI_TASK.md" in i.message for i in check_package(bad))
    man = json.loads(files["manifest.json"])
    man["export_mode"] = "rewrite-everything"
    bad = dict(files, **{"manifest.json": json.dumps(man).encode()})
    assert any("manifest.json" in i.message for i in check_package(bad))


# ---------- интерфейс ----------
@pytest.fixture
def app_win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)

    def discard(win):
        for studio in (win.builder, win.icons):
            if studio.editor.stack is not None:
                studio.editor.stack.set_clean()
        win.project_page.mark_clean()
        win.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.resize(1500, 950)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Экспорт"))
    w.open_project(str(path))
    yield w, w.project_page.editor, projects_dir
    ctx.close()


def test_validator_page_lists_and_navigates(qtbot, app_win):
    win, ed, _ = app_win
    s = ed.screen()
    t = ed.add_node("text", (40, 40, 600, 60))
    ed.set_props({t.id: {"text": "Серый на сером", "text_color": "#777777"}})
    back = ed.add_node("rect", (0, 0, 1080, 400))
    ed.set_props({back.id: {"fill": "#707070"}})
    ed.patch("Порядок", lambda doc: _to_back(doc, s.id, back.id))
    win.show_page(PAGE_VALIDATE)
    page = win.validator
    assert page.tree.topLevelItemCount() >= 1 and "предупреждений" in page.summary.text()
    item = next(page.tree.topLevelItem(i).child(j) for i in range(page.tree.topLevelItemCount())
                for j in range(page.tree.topLevelItem(i).childCount())
                if "контраст" in page.tree.topLevelItem(i).child(j).text(1))
    ed.select([])
    page._open(item)
    assert win.pages.currentIndex() == PAGE_PROJECT and ed.selection == [t.id]


def _to_back(doc, sid, nid):
    sc = next(x for x in doc.screens if x.id == sid)
    n = next(x for x in sc.nodes if x.id == nid)
    sc.nodes.remove(n)
    sc.nodes.insert(0, n)


def test_export_page_builds_archive_and_blocks_on_critical(qtbot, app_win):
    win, ed, projects = app_win
    ed.add_node("rect", (100, 300, 400, 200))
    ed.add_screen(Screen(name="Второй", platform="android", width=1080, height=2400, device_id="android_phone"))
    win.show_page(PAGE_EXPORT)
    page = win.export_page
    assert page.screens.count() == 2 and page.plat["android"].isChecked() and not page.plat["windows"].isEnabled()
    assert "## Экраны для реализации" in page.task.toPlainText() and page.b_export.isEnabled()
    page.screens.item(1).setCheckState(Qt.CheckState.Unchecked)
    assert "Выбрано экранов: 1" in page.screens_info.text()
    page.task.setPlainText(page.task.toPlainText() + "\nДополнение пользователя.")
    assert page.task_edited
    page.m_update.setChecked(True)                   # смена настроек не затирает правку
    assert page.task.toPlainText().endswith("Дополнение пользователя.")
    page.folder.setText(str(projects / "Экспорт"))
    path = page.export()
    assert path is not None and path.exists() and "Архив записан и проверен" in page.steps.text()
    with zipfile.ZipFile(path) as zf:
        assert zf.read("AI_TASK.md").decode().endswith("Дополнение пользователя.")
        man = json.loads(zf.read("manifest.json"))
        assert man["export_mode"] == "update" and len(man["screens"]) == 1 and man["screens"][0]["preview"]
    assert not [i for i in check_archive(path) if i.severity == "critical"]
    # висячая ссылка — экспорт заблокирован
    sid = ed.doc.screens[0].id
    ed.patch("Сломать", lambda doc: doc.interactions.append(Interaction(sid, "tap", "nope", actions=[])))
    win.show_page(PAGE_EXPORT)
    assert not page.b_export.isEnabled() and "заблокирован" in page.check_info.text()
    assert page.export() is None
    win.open_task()
    assert win.pages.currentIndex() == PAGE_EXPORT
