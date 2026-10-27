"""Самопроверка установленной программы: AppDesignStudio.exe --smoke-test [файл-отчёта]

Нужна для проверки сборки на чистой машине (S23) и офлайн-запуска (S24): создаёт проект во временной папке,
собирает экран из базовых компонентов, сохраняет и открывает заново, проверяет, запускает предпросмотр и
AI-экспорт, перечитывает архив. Данные пользователя не затрагиваются (своя временная папка данных).
Код выхода 0 — все шаги прошли.
"""

from __future__ import annotations

import json
import platform
import sys
import tempfile
import time
import traceback
from pathlib import Path


def run(report_path: str | None = None) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ads_smoke_"))
    from PySide6.QtWidgets import QApplication

    from app import APP_NAME, APP_VERSION
    from app.context import AppContext
    from app.core.paths import AppPaths
    from app.ui.themes.fusion_amoled import apply_theme
    steps: list[dict] = []
    t0 = time.perf_counter()

    def step(name, fn):
        s = time.perf_counter()
        try:
            detail = fn() or ""
            steps.append({"step": name, "ok": True, "detail": str(detail), "ms": round((time.perf_counter() - s) * 1000)})
        except Exception as exc:  # noqa: BLE001 — отчёт о любой ошибке шага
            steps.append({"step": name, "ok": False, "detail": f"{exc}\n{traceback.format_exc(limit=4)}",
                          "ms": round((time.perf_counter() - s) * 1000)})

    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_theme(app)
    ctx = AppContext.create(AppPaths(tmp / "data").ensure())
    state: dict = {}

    def start_window():
        from app.ui.shell.main_window import MainWindow
        state["win"] = MainWindow(ctx)
        state["win"].show()
        app.processEvents()
        return f"окно {state['win'].width()}×{state['win'].height()}"

    def create():
        from app.core.project.service import NewProjectSpec
        doc, path = ctx.service.create(NewProjectSpec(title="Самопроверка", location=tmp / "Проекты",
                                                      platforms=["android", "windows"],
                                                      devices=["android_phone", "windows_window"]))
        state["path"] = path
        state["win"].open_project(str(path))
        ed = state["win"].project_page.editor
        for cid in ("m3_top_app_bar", "m3_button_filled", "m3_text_field"):
            ed.insert_component(cid)
        return f"{path.name}: экранов {len(doc.screens)}"

    def save_reopen():
        win = state["win"]
        if not win.save_project():
            raise RuntimeError("сохранение не выполнено")
        from app.core.persistence.container import load_project
        doc = load_project(state["path"])
        n = sum(len(s.nodes) for s in doc.screens)
        if n < 3:
            raise RuntimeError(f"после открытия элементов {n}")
        return f"элементов {n}"

    def validate():
        from app.ui.studio.export import run_validation
        issues = run_validation(state["win"].project_page.editor)
        crit = [i for i in issues if i.severity == "critical"]
        if crit:
            raise RuntimeError("; ".join(i.message for i in crit[:3]))
        return f"замечаний {len(issues)}, критичных нет"

    def preview():
        win = state["win"]
        win.run_prototype()
        p = win.preview.player
        p.stop_clock()
        if p is None or p.screen is None:
            raise RuntimeError("предпросмотр не запустился")
        p.advance(500)
        return f"{p.spec.profile.name}: {p.screen.width}×{p.screen.height}"

    def export():
        from app.exporters.ai_export import check_archive
        from app.ui.shell.main_window import PAGE_EXPORT
        win = state["win"]
        win.show_page(PAGE_EXPORT)
        page = win.export_page
        page.folder.setText(str(tmp / "Экспорт"))
        path = page.export(confirm_overwrite=False)
        if path is None:
            raise RuntimeError("экспорт не выполнен: " + page.steps.text())
        bad = [i for i in check_archive(path) if i.severity == "critical"]
        if bad:
            raise RuntimeError("архив не прошёл проверку: " + bad[0].message)
        return f"{path.name}, {path.stat().st_size} байт"

    for name, fn in (("Запуск окна", start_window), ("Создание проекта", create),
                     ("Сохранение и открытие", save_reopen), ("Проверка проекта", validate),
                     ("Интерактивный предпросмотр", preview), ("AI-экспорт", export)):
        step(name, fn)
        if not steps[-1]["ok"]:
            break
    win = state.get("win")
    if win is not None:
        win.dirty = False
        win.project_page.mark_clean()
        win.preview.deactivate()
        win.close()
    ctx.close()
    ok = all(s["ok"] for s in steps) and len(steps) == 6
    report = {"app": APP_NAME, "version": APP_VERSION, "ok": ok, "python": sys.version.split()[0],
              "frozen": bool(getattr(sys, "frozen", False)), "os": platform.platform(),
              "total_ms": round((time.perf_counter() - t0) * 1000), "steps": steps}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if report_path:
        Path(report_path).write_text(text, encoding="utf-8")
    try:
        print(text)
    except (OSError, UnicodeEncodeError):  # оконная сборка без консоли
        pass
    return 0 if ok else 1
