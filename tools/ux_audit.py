"""Обход интерфейса для ревизии удобства: все страницы при разных размерах окна, снимки и поиск
обрезанных подписей. Запуск: .venv\\Scripts\\python -m tools.ux_audit <папка> [ширина×высота ...]
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QAbstractButton, QApplication, QLabel

from app.context import AppContext
from app.core.paths import AppPaths
from app.core.project.service import NewProjectSpec
from app.ui.shell.main_window import STUDIOS, MainWindow, PAGE_HUB, PAGE_PROJECT, PAGE_SETTINGS
from app.ui.themes.fusion_amoled import apply_theme


def clipped(win) -> list[str]:
    """Видимые подписи и кнопки, текст которых не помещается (без переноса)."""
    out = []
    for w in win.findChildren(QLabel) + win.findChildren(QAbstractButton):
        if not w.isVisibleTo(win) or not w.text().strip() or w.width() < 4:
            continue
        if isinstance(w, QLabel) and (w.wordWrap() or w.pixmap() is not None and not w.pixmap().isNull()):
            continue
        need = w.fontMetrics().horizontalAdvance(w.text().split("\n")[0]) + (24 if isinstance(w, QAbstractButton) else 0)
        if need > w.width() + 2:
            out.append(f"{type(w).__name__} «{w.text()[:50]}» {w.width()}px < {need}px "
                       f"в {type(w.parent()).__name__}")
    return out


def main(out_dir: str, sizes: list[tuple[int, int]]) -> int:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="ads_audit_"))
    app = QApplication(sys.argv[:1])
    apply_theme(app)
    ctx = AppContext.create(AppPaths(tmp / "data").ensure())
    win = MainWindow(ctx)
    win.show()
    report = []

    def run():
        from tools.stage_screenshots import _demo_components, _demo_screen, _demo_window
        doc, path = ctx.service.create(NewProjectSpec(title="Ревизия интерфейса", location=tmp / "p",
                                                      platforms=["android", "windows"],
                                                      devices=["android_phone", "windows_window"]))
        win.open_project(str(path))
        ed = win.project_page.editor
        _demo_screen(ed)
        ed.set_screen(ed.doc.screens[1].id)
        _demo_window(ed)
        from app.core.document.model import Screen
        ed.add_screen(Screen(name="Компоненты", platform="android", width=1080, height=2400,
                             device_id="android_phone"))
        _demo_components(ed)
        ed.set_screen(ed.doc.screens[0].id)
        pages = [(PAGE_HUB, "hub"), (PAGE_PROJECT, "workspace"), (PAGE_SETTINGS, "settings")] + \
            [(p, icon) for p, _, icon, _ in STUDIOS]
        for w, h in sizes:
            win.resize(w, h)
            for page, name in pages:
                win.show_page(page)
                for _ in range(3):
                    app.processEvents()
                win.grab().save(str(out / f"{w}x{h}_{page:02d}_{name}.png"))
                for line in clipped(win):
                    report.append(f"{w}x{h} {name}: {line}")
        win.preview.deactivate()
        win.dirty = False
        win.project_page.mark_clean()
        app.quit()

    QTimer.singleShot(300, run)
    app.exec()
    ctx.close()
    (out / "clipped.txt").write_text("\n".join(report), encoding="utf-8")
    print(f"страниц снято, обрезанных подписей: {len(report)} → {out / 'clipped.txt'}")
    return 0


if __name__ == "__main__":
    args = sys.argv[2:] or ["1100x700", "1920x1040"]
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "docs/audit",
                  [tuple(int(x) for x in a.split("x")) for a in args]))
