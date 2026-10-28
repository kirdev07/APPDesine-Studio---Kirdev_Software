# Сборка: .venv\Scripts\python -m PyInstaller packaging\AppDesignStudio.spec --noconfirm
# Результат: dist\AppDesignStudio\AppDesignStudio.exe (папка с программой, Python не нужен).
from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "LICENSE"), "."), (str(ROOT / "THIRD_PARTY_NOTICES"), "."),
           (str(ROOT / "app" / "resources" / "material_symbols.json.gz"), "app/resources"),
           (str(ROOT / "app" / "resources" / "MATERIAL_SYMBOLS_LICENSE.txt"), "app/resources")],
    hiddenimports=["PySide6.QtSvg"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
              "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtNetwork",
              "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.QtDataVisualization", "pytest", "pytestqt"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="AppDesignStudio",
    icon=str(ROOT / "packaging" / "app.ico"),
    version=str(ROOT / "packaging" / "version_info.txt"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="AppDesignStudio")
