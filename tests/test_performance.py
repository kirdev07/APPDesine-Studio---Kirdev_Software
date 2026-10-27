"""Этап 8: производительность на больших проектах и доступность интерфейса.

Пороги заданы с большим запасом к базовым замерам (docs/PERFORMANCE.md): тест ловит деградацию
в разы, а не колебания машины.
"""

import time

import pytest
from PySide6.QtWidgets import QAbstractButton, QApplication, QCheckBox, QMessageBox, QRadioButton

from app.context import AppContext
from app.core.persistence.container import load_project, save_project
from app.engines.components import engine as ce
from app.engines.validation.engine import contrast, validate_project
from app.exporters.ai_export import ExportOptions, build_package
from app.ui.shell.main_window import PAGE_EXPORT, PAGE_PREVIEW, PAGE_VALIDATE, STUDIOS, MainWindow
from app.ui.themes.fusion_amoled import TOKENS, apply_theme
from tools.perf_baseline import build_large


def test_large_project_operations_within_limits(tmp_path):
    t = time.perf_counter()
    doc, master, eng = build_large(100, 2000, 300)
    times = {"build": time.perf_counter() - t}

    def timed(name, fn):
        s = time.perf_counter()
        r = fn()
        times[name] = time.perf_counter() - s
        return r
    timed("save", lambda: save_project(doc, tmp_path / "big.adsproj"))
    doc2 = timed("load", lambda: load_project(tmp_path / "big.adsproj"))
    assert len(doc2.screens) == 100 and sum(len(s.nodes) for s in doc2.screens) >= 100 * 12 + 2000
    master.root.fill = "#303030"
    timed("sync", lambda: ce.sync_instances(doc, eng))
    issues = timed("validate", lambda: validate_project(doc2, eng, lambda f: True, lambda f, t: ""))
    assert not [i for i in issues if i.severity == "critical"]
    pkg = timed("export", lambda: build_package(doc2, ExportOptions(include_previews=False)))
    assert len(pkg.manifest["screens"]) == 100 and sum(a["included"] for a in pkg.manifest["assets"]) == 300
    limits = {"save": 15, "load": 15, "sync": 10, "validate": 20, "export": 20}
    assert all(times[k] < v for k, v in limits.items()), times


@pytest.fixture
def win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    t = time.perf_counter()
    w = MainWindow(ctx)
    w.startup_seconds = time.perf_counter() - t

    def discard(window):
        window.project_page.mark_clean()
        window.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.resize(1500, 950)
    w.show()
    yield w
    ctx.close()


def test_open_large_project_and_switch_pages(win, projects_dir):
    assert win.startup_seconds < 10
    doc, _, _ = build_large(50, 1000, 150)
    path = projects_dir / "Большой.adsproj"
    save_project(doc, path)
    t = time.perf_counter()
    win.open_project(str(path))
    QApplication.processEvents()
    opened = time.perf_counter() - t
    ed = win.project_page.editor
    t = time.perf_counter()
    for s in ed.doc.screens[:10]:
        ed.set_screen(s.id)
        QApplication.processEvents()
    switching = (time.perf_counter() - t) / 10
    t = time.perf_counter()
    for page in (PAGE_VALIDATE, PAGE_PREVIEW, PAGE_EXPORT):
        win.show_page(page)
        QApplication.processEvents()
    pages = time.perf_counter() - t
    win.preview.deactivate()
    assert opened < 20 and switching < 3 and pages < 30, (opened, switching, pages)


def test_controls_have_names_and_theme_contrast(win):
    """Доступность: у каждой кнопки и флажка есть текст или имя для экранного диктора; контраст темы."""
    for page in [p for p, *_ in STUDIOS]:
        win.show_page(page)  # без проекта студии недоступны — проверяем то, что видно
    nameless = []
    for b in win.findChildren(QAbstractButton):
        if not b.isVisibleTo(win):
            continue
        if not (b.text().strip() or b.accessibleName().strip() or b.toolTip().strip()):
            nameless.append(f"{type(b).__name__} {b.objectName()!r} в {type(b.parent()).__name__}")
    assert not nameless, nameless
    nav = [b for b in win.findChildren(QAbstractButton) if b.objectName() == "NavButton"]
    assert nav and all(b.accessibleName() for b in nav)
    for fg in ("text", "text_muted"):
        for bg in ("bg", "surface", "surface_2"):
            if fg in TOKENS and bg in TOKENS:
                assert contrast(TOKENS[fg], TOKENS[bg]) >= 4.5, (fg, bg, contrast(TOKENS[fg], TOKENS[bg]))
    for cls in (QCheckBox, QRadioButton):
        assert all(c.text().strip() or c.accessibleName() for c in win.findChildren(cls) if c.isVisibleTo(win))
