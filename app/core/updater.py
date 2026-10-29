"""Обновление программы с официальной страницы (выпуски GitHub). Без Qt.

Проверка — один запрос номера последней версии (без сведений о пользователе). Архив скачивается только с
github.com и сверяется с контрольной суммой SHA-256 из того же выпуска; без совпадения ничего не ставится.
Замену файлов делает отдельный скрипт PowerShell после закрытия программы, затем запускает новую версию."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app import APP_NAME, APP_VERSION

REPO = "kirdev07/APPDesine-Studio---Kirdev_Software"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
HOSTS = ("github.com", "api.github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
MAX_SIZE = 400 * 1024 * 1024
EXE = "AppDesignStudio.exe"
CHECK_EVERY_S = 24 * 3600


class UpdateError(Exception):
    pass


@dataclass
class Release:
    version: str
    notes: str
    zip_url: str
    zip_name: str
    size: int
    sha_url: str


def parse_version(text: str) -> tuple[int, ...]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def is_newer(remote: str, current: str = APP_VERSION) -> bool:
    return parse_version(remote) > parse_version(current)


def _host_ok(url: str) -> bool:
    u = urlparse(url)
    return u.scheme == "https" and (u.hostname or "") in HOSTS


def _open(url: str, timeout: float):
    if not _host_ok(url):
        raise UpdateError(f"адрес не с официальной страницы: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME.replace(' ', '')}/{APP_VERSION}",
                                               "Accept": "application/vnd.github+json"})
    resp = urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 — только https и github (проверено выше)
    if not _host_ok(resp.geturl()):
        resp.close()
        raise UpdateError("перенаправление не на официальную страницу")
    return resp


def release_from_json(data: dict) -> Release | None:
    """Выпуск из ответа GitHub: архив *-win64.zip и его контрольная сумма *.zip.sha256."""
    assets = {a.get("name", ""): a for a in data.get("assets", [])}
    zip_name = next((n for n in assets if n.endswith("-win64.zip")), "")
    sha = assets.get(zip_name + ".sha256") if zip_name else None
    if not zip_name or sha is None or data.get("draft") or data.get("prerelease"):
        return None
    z = assets[zip_name]
    return Release(version=".".join(map(str, parse_version(data.get("tag_name", "")))),
                   notes=str(data.get("body") or "").strip(), zip_url=z.get("browser_download_url", ""),
                   zip_name=zip_name, size=int(z.get("size") or 0), sha_url=sha.get("browser_download_url", ""))


def fetch_latest(timeout: float = 8.0) -> Release | None:
    """Последний выпуск на официальной странице (None — выпусков с архивом нет)."""
    try:
        with _open(API, timeout) as r:
            data = json.loads(r.read(2_000_000).decode("utf-8"))
    except UpdateError:
        raise
    except Exception as exc:  # noqa: BLE001 — нет сети, ответ не тот: сообщаем понятным текстом
        raise UpdateError("нет связи с официальной страницей — проверьте интернет") from exc
    return release_from_json(data)


def download(rel: Release, folder: Path, progress=None, cancelled=lambda: False) -> Path:
    """Скачать архив и сверить SHA-256. progress(получено, всего)."""
    if rel.size > MAX_SIZE:
        raise UpdateError("архив подозрительно большой")
    try:
        with _open(rel.sha_url, 20) as r:
            want = r.read(4096).decode("ascii", "replace").split()[0].strip().lower()
    except UpdateError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise UpdateError("не удалось получить контрольную сумму") from exc
    if not re.fullmatch(r"[0-9a-f]{64}", want):
        raise UpdateError("контрольная сумма в выпуске неверного вида")
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / rel.zip_name
    h, got = hashlib.sha256(), 0
    try:
        with _open(rel.zip_url, 30) as r, open(dest, "wb") as f:
            while True:
                if cancelled():
                    raise UpdateError("скачивание отменено")
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                got += len(chunk)
                if got > MAX_SIZE:
                    raise UpdateError("архив подозрительно большой")
                h.update(chunk)
                f.write(chunk)
                if progress:
                    progress(got, rel.size)
    except UpdateError:
        dest.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise UpdateError("скачивание прервалось — проверьте интернет и попробуйте ещё раз") from exc
    if h.hexdigest() != want:
        dest.unlink(missing_ok=True)
        raise UpdateError("архив повреждён или подменён: контрольная сумма не совпала — ничего не установлено")
    return dest


def extract(zip_path: Path, folder: Path) -> Path:
    """Распаковать архив (без путей за пределы папки) и вернуть папку с программой."""
    with zipfile.ZipFile(zip_path) as z:
        root = folder.resolve()
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            target = (root / name).resolve()
            if name.startswith("/") or ".." in Path(name).parts or root not in (target, *target.parents):
                raise UpdateError(f"в архиве недопустимый путь: {info.filename}")
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())
    found = next((p.parent for p in folder.rglob(EXE)), None)
    if found is None:
        raise UpdateError(f"в архиве нет {EXE}")
    return found


def install_dir() -> Path | None:
    """Папка установленной программы (None — запуск из исходников: заменять нечего)."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent


def writable(folder: Path) -> bool:
    try:
        probe = folder / ".ads_update_probe"
        probe.write_text("1", encoding="ascii")
        probe.unlink()
        return True
    except OSError:
        return False


def install_script(src: Path, dst: Path, pid: int) -> str:
    """Скрипт PowerShell: дождаться закрытия программы, скопировать новые файлы, запустить её."""
    def q(p):
        return "'" + str(p).replace("'", "''") + "'"
    return "\n".join([
        "$ErrorActionPreference = 'Stop'",
        f"try {{ Wait-Process -Id {int(pid)} -Timeout 120 -ErrorAction SilentlyContinue }} catch {{}}",
        "Start-Sleep -Milliseconds 500",
        f"robocopy {q(src)} {q(dst)} /E /R:5 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null",
        "if ($LASTEXITCODE -ge 8) { exit 1 }",
        f"Start-Process -FilePath {q(dst / EXE)}",
    ]) + "\n"


def launch_install(new_dir: Path, dst: Path) -> None:
    """Запустить установку после выхода программы; папка без прав записи — через запрос администратора."""
    script = Path(tempfile.mkdtemp(prefix="ads_update_")) / "install.ps1"
    script.write_text(install_script(new_dir, dst, os.getpid()), encoding="utf-8-sig")
    args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script)]
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if writable(dst):
        subprocess.Popen(["powershell.exe", *args], creationflags=flags, close_fds=True)  # noqa: S603,S607
    else:
        joined = ",".join("'" + a.replace("'", "''") + "'" for a in args)
        subprocess.Popen(["powershell.exe", "-NoProfile", "-Command",  # noqa: S603,S607
                          f"Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList {joined}"],
                         creationflags=flags, close_fds=True)
