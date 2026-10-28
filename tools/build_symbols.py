"""Сборка ресурса значков Material Symbols из пакета npm @material-symbols/svg-400 (Apache 2.0).

Запуск: .venv\\Scripts\\python -I tools\\build_symbols.py <папка package из распакованного .tgz>
Результат: app/resources/material_symbols.json.gz — {стиль: {имя: d}} (стили outlined, rounded, sharp; варианты
с заливкой — имена с суффиксом «-fill»), и app/resources/MATERIAL_SYMBOLS_LICENSE.txt. Пути — как в исходных SVG
(viewBox 0 -960 960 960); программа сдвигает их при вставке.
"""

from __future__ import annotations

import gzip
import json
import re
import shutil
import sys
from pathlib import Path

_PATH = re.compile(r'<path d="([^"]+)"')
STYLES = ("outlined", "rounded", "sharp")


def main(package: str) -> int:
    src = Path(package)
    meta = json.loads((src / "package.json").read_text(encoding="utf-8"))
    out = {"version": meta["version"], "license": meta.get("license", ""), "styles": {}}
    for style in STYLES:
        icons = {}
        for f in sorted((src / style).glob("*.svg")):
            ds = _PATH.findall(f.read_text(encoding="utf-8"))
            if ds:
                icons[f.stem] = " ".join(ds)
        out["styles"][style] = icons
        print(style, len(icons))
    dst = Path(__file__).resolve().parent.parent / "app" / "resources"
    dst.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(out, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    (dst / "material_symbols.json.gz").write_bytes(gzip.compress(raw, 9, mtime=0))
    shutil.copyfile(src / "LICENSE", dst / "MATERIAL_SYMBOLS_LICENSE.txt")
    print("ok", (dst / "material_symbols.json.gz").stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
