"""Сохранение Android-проекта в папку и сборка тестового APK на этом компьютере. Без Qt.

Для сборки нужны Android SDK, JDK 17+ и Gradle (берутся из Android Studio и кэша Gradle, если они
установлены). Программа сама ничего не устанавливает; при первой сборке Gradle скачивает зависимости
из Google Maven и Maven Central — это делает Gradle, а не App Design Studio.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.exporters.android_project import ROOT, VERSIONS


@dataclass
class Toolchain:
    sdk: Path | None = None
    java_home: Path | None = None
    gradle: Path | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def env(self) -> dict[str, str]:
        e = dict(os.environ)
        if self.java_home:
            e["JAVA_HOME"] = str(self.java_home)
        if self.sdk:
            e["ANDROID_HOME"] = str(self.sdk)
        return e

    def describe(self) -> str:
        if not self.ok:
            return "; ".join(self.problems)
        return f"SDK: {self.sdk} · JDK: {self.java_home} · Gradle: {self.gradle.parent.parent.name}"


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", text)[:3])


def find_toolchain() -> Toolchain:
    t = Toolchain()
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    for cand in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"), local / "Android" / "Sdk"):
        if cand and (Path(cand) / "platforms").is_dir():
            t.sdk = Path(cand)
            break
    if t.sdk is None:
        t.problems.append("не найден Android SDK (установите Android Studio)")
    for cand in (os.environ.get("JAVA_HOME"), r"C:\Program Files\Android\Android Studio\jbr",
                 local / "Programs" / "Android Studio" / "jbr"):
        if cand and (Path(cand) / "bin" / "java.exe").exists():
            release = Path(cand) / "release"
            ver = _version(release.read_text(errors="ignore").split("JAVA_VERSION=")[-1][:12]) if release.exists() else (17,)
            if ver and ver[0] >= 17:
                t.java_home = Path(cand)
                break
    if t.java_home is None:
        t.problems.append("не найден JDK 17+ (входит в Android Studio)")
    need = _version(VERSIONS["gradle"])
    dists = Path(os.environ.get("GRADLE_USER_HOME", Path.home() / ".gradle")) / "wrapper" / "dists"
    found = []
    if dists.is_dir():
        for exe in dists.glob("gradle-*-bin/*/gradle-*/bin/gradle.bat"):
            ver = _version(exe.parent.parent.name)
            if ver >= need and ver[0] == need[0]:
                found.append((ver, exe))
    if found:
        t.gradle = sorted(found)[0][1]
    else:
        t.problems.append(f"не найден Gradle {VERSIONS['gradle']}.x (откройте любой проект в Android Studio "
                          "или проект из пакета — студия скачает Gradle)")
    return t


def write_project(files: dict[str, bytes], folder: Path, sdk: Path | None = None) -> Path:
    """Записать android_project/ из пакета в папку; local.properties — путь к SDK этого компьютера."""
    folder = Path(folder)
    prefix = ROOT + "/"
    for path, data in files.items():
        if not path.startswith(prefix):
            continue
        rel = path[len(prefix):]
        target = (folder / rel).resolve()
        if folder.resolve() not in target.parents:
            raise ValueError(f"небезопасный путь: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if sdk:
        (folder / "local.properties").write_text("sdk.dir=" + str(sdk).replace("\\", "\\\\").replace(":", "\\:")
                                                 + "\n", encoding="utf-8")
    return folder


def build_command(t: Toolchain, project: Path, release: bool = False) -> tuple[str, list[str]]:
    """Программа и аргументы: отладочный APK или (release) пакет AAB для Google Play и подписанный APK."""
    tasks = ["bundleRelease", "assembleRelease"] if release else ["assembleDebug"]
    return str(t.gradle), ["-p", str(project), *tasks, "--console=plain", "--no-daemon"]


def apk_path(project: Path, release: bool = False) -> Path:
    kind = "release" if release else "debug"
    return Path(project) / "app" / "build" / "outputs" / "apk" / kind / f"app-{kind}.apk"


def aab_path(project: Path) -> Path:
    return Path(project) / "app" / "build" / "outputs" / "bundle" / "release" / "app-release.aab"


# ---------- подпись для Google Play ----------
@dataclass
class SigningKey:
    store: Path
    password: str
    alias: str = "upload"
    version_code: int = 0


def signing_key(t: Toolchain, keys_dir: Path, package: str) -> SigningKey:
    """Ключ загрузки приложения (один на пакет): создаётся keytool из JDK при первой сборке и хранится в папке
    программы. Его потеря — нельзя обновить приложение в Google Play, поэтому путь показывается пользователю."""
    import json
    import secrets
    import subprocess
    keys_dir = Path(keys_dir)
    keys_dir.mkdir(parents=True, exist_ok=True)
    store, info = keys_dir / f"{package}.jks", keys_dir / f"{package}.json"
    if store.exists() and info.exists():
        d = json.loads(info.read_text(encoding="utf-8"))
        return SigningKey(store, d["password"], d.get("alias", "upload"), int(d.get("version_code", 0)))
    if t.java_home is None:
        raise RuntimeError("не найден JDK (keytool) — установите Android Studio")
    password = secrets.token_urlsafe(18)
    name = re.sub(r"[^A-Za-z0-9._ -]", " ", package)[:60]  # латиница: кириллица в -dname ломается в консоли
    cmd = [str(t.java_home / "bin" / "keytool.exe"), "-genkeypair", "-keystore", str(store), "-storetype", "PKCS12",
           "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000", "-alias", "upload",
           "-storepass", password, "-keypass", password, "-dname", f"CN={name}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0 or not store.exists():
        raise RuntimeError("keytool не создал ключ: " + (r.stderr or r.stdout).strip()[:300])
    info.write_text(json.dumps({"package": package, "password": password, "alias": "upload", "version_code": 0},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return SigningKey(store, password, "upload", 0)


def prepare_release(project: Path, key: SigningKey, keys_dir: Path, package: str, version_name: str) -> int:
    """release.properties для Gradle; номер версии (versionCode) растёт с каждой сборкой — Google Play требует."""
    import json
    code = key.version_code + 1
    esc = lambda p: str(p).replace("\\", "/")  # noqa: E731 — в .properties обратная косая — экранирование
    (Path(project) / "release.properties").write_text(
        f"storeFile={esc(key.store)}\nstorePassword={key.password}\nkeyAlias={key.alias}\n"
        f"keyPassword={key.password}\nversionCode={code}\nversionName={version_name}\n", encoding="utf-8")
    info = Path(keys_dir) / f"{package}.json"
    d = json.loads(info.read_text(encoding="utf-8"))
    d["version_code"] = code
    info.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    key.version_code = code
    return code
