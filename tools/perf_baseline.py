"""Замер производительности на больших проектах (05_TEST_AND_ACCEPTANCE.md: 10/50/100 экранов,
500–2000 компонентов, сотни SVG). Запуск: .venv\\Scripts\\python -m tools.perf_baseline

Печатает таблицу времени операций; базовые значения записаны в docs/PERFORMANCE.md.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import time
from pathlib import Path

from app.core.document.model import Asset, ComponentDef, Node, Screen
from app.core.persistence.container import load_project, save_project
from app.core.project.service import build_document
from app.engines.components import engine as ce
from app.engines.layout import LayoutEngine, SimpleMeasurer
from app.engines.validation.engine import validate_project
from app.exporters.ai_export import ExportOptions, build_package


def build_large(screens: int, instances: int, icons: int):
    """Проект: screens экранов по 12 элементов, instances экземпляров мастера поровну, icons SVG-ресурсов."""
    from app.core.project.service import NewProjectSpec
    eng = LayoutEngine(SimpleMeasurer())
    doc = build_document(NewProjectSpec(title="Большой проект", location=Path("."), platforms=["android"],
                                        devices=["android_phone"]))
    root = Node(type="frame", name="Карточка", x=0, y=0, w=900, h=200, layout="vertical", gap=16, pad_t=24,
                pad_l=24, pad_r=24, pad_b=24, sizing_v="hug", fill="#1A1A1A", radius=24,
                children=[Node(type="text", name="Заголовок", text="Заголовок карточки", x=0, y=0, w=852, h=60,
                               sizing_h="fill", font_size=44, fill=""),
                          Node(type="text", name="Описание", text="Длинный русский текст описания карточки " * 3,
                               x=0, y=0, w=852, h=120, sizing_h="fill", sizing_v="hug", font_size=36, fill="")])
    master = ComponentDef(name="Карточка", root=root, states={"hover": {"__root__": {"fill": "#2A2A2A"}}})
    doc.components.append(master)
    svg_ids = []
    for i in range(icons):
        data = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M{i % 20} 2 L22 2 '
                f'L12 22 Z"/></svg>').encode()
        a = Asset(kind="icon", name=f"Иконка {i}.svg", ext="svg", sha256=hashlib.sha256(data).hexdigest(),
                  size=len(data), license="MIT", redistribution="allowed")
        doc.assets.append(a)
        doc.asset_data[a.id] = data
        svg_ids.append(a.id)
    doc.screens = []
    per = max(1, instances // screens)
    for s_i in range(screens):
        s = Screen(name=f"Экран {s_i + 1}", platform="android", width=1080, height=2400, device_id="android_phone")
        for j in range(12):
            s.nodes.append(Node(type="text" if j % 3 == 0 else "rect", name=f"Элемент {j}", x=40, y=40 + j * 180,
                                w=1000, h=150, text=f"Строка {j}" if j % 3 == 0 else "", fill="" if j % 3 == 0
                                else "#202020"))
        for k in range(per):
            s.nodes.append(ce.make_instance(master, 90, 300 + (k % 10) * 210, eng))
        for k in range(icons // screens):
            s.nodes.append(Node(type="image", name="Иконка", x=40 + k * 80, y=2200, w=72, h=72,
                                asset_id=svg_ids[(s_i * (icons // screens) + k) % len(svg_ids)]))
        doc.screens.append(s)
    return doc, master, eng


def measure(screens=100, instances=2000, icons=300) -> list[tuple[str, float]]:
    out = []

    def timed(name, fn):
        t = time.perf_counter()
        r = fn()
        out.append((name, time.perf_counter() - t))
        return r
    doc, master, eng = timed("Сборка проекта в памяти", lambda: build_large(screens, instances, icons))
    tmp = Path(tempfile.mkdtemp(prefix="ads_perf_"))
    timed("Сохранение .adsproj", lambda: save_project(doc, tmp / "big.adsproj"))
    doc2 = timed("Открытие .adsproj", lambda: load_project(tmp / "big.adsproj"))
    master.root.children[0].font_size = 48
    timed("Изменение мастера → все экземпляры", lambda: ce.sync_instances(doc, eng))
    timed("Раскладка всех экранов", lambda: [eng.layout_screen(s) for s in doc.screens])
    timed("Проверка проекта", lambda: validate_project(doc2, eng, lambda f: True, lambda f, t: ""))
    pkg = timed("AI-экспорт (без превью)", lambda: build_package(doc2, ExportOptions(include_previews=False)))
    timed("Запись ZIP", lambda: pkg.zip_bytes())
    return out


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:4]] or [100, 2000, 300]
    for sc in ((10, 200, 30), (50, 1000, 150), tuple(args)):
        print(f"\n{sc[0]} экранов, {sc[1]} экземпляров, {sc[2]} SVG:")
        for name, sec in measure(*sc):
            print(f"  {name:<40} {sec:7.2f} с")
