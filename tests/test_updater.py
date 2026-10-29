"""1.40: обновления с официальной страницы — без настоящей сети (ответы подменены)."""

import hashlib
import io
import json
import zipfile

import pytest

from app.core import updater


class _Resp(io.BytesIO):
    def __init__(self, data: bytes, url: str):
        super().__init__(data)
        self.url = url

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def _release(zip_bytes: bytes, sha: str | None = None, version="v9.9.9"):
    zname = f"AppDesignStudio-{version[1:]}-win64.zip"
    base = "https://github.com/kirdev07/x/releases/download/" + version + "/"
    data = {"tag_name": version, "body": "Новое: всё лучше", "assets": [
        {"name": zname, "browser_download_url": base + zname, "size": len(zip_bytes)},
        {"name": zname + ".sha256", "browser_download_url": base + zname + ".sha256", "size": 80}]}
    files = {base + zname: zip_bytes,
             base + zname + ".sha256": ((sha or hashlib.sha256(zip_bytes).hexdigest()) + f"  {zname}\n").encode()}
    return data, files


def test_versions_and_release_parsing():
    assert updater.is_newer("1.40.0", "1.39.0") and not updater.is_newer("1.39.0", "1.39.0")
    assert updater.is_newer("v2.0.0", "1.99.9") and not updater.is_newer("1.9.0", "1.10.0")
    data, _ = _release(b"x")
    rel = updater.release_from_json(data)
    assert rel.version == "9.9.9" and rel.zip_name.endswith("-win64.zip") and rel.sha_url.endswith(".sha256")
    data["assets"] = data["assets"][:1]                       # без контрольной суммы — не обновляемся
    assert updater.release_from_json(data) is None
    assert updater.release_from_json({"tag_name": "v1", "assets": [], "prerelease": True}) is None


def test_only_official_hosts():
    with pytest.raises(updater.UpdateError):
        updater._open("https://evil.example.com/a.zip", 1)
    with pytest.raises(updater.UpdateError):
        updater._open("http://github.com/a.zip", 1)              # только https


def test_download_verifies_checksum_and_extracts(tmp_path, monkeypatch):
    zb = _zip({"AppDesignStudio/AppDesignStudio.exe": b"MZ", "AppDesignStudio/_internal/a.dll": b"dll"})
    data, files = _release(zb)
    monkeypatch.setattr(updater, "_open", lambda url, timeout: _Resp(
        json.dumps(data).encode() if url == updater.API else files[url], url))
    rel = updater.fetch_latest()
    seen = []
    z = updater.download(rel, tmp_path / "dl", lambda got, total: seen.append(got))
    assert z.read_bytes() == zb and seen and seen[-1] == len(zb)
    new = updater.extract(z, tmp_path / "new")
    assert (new / "AppDesignStudio.exe").read_bytes() == b"MZ"
    bad_data, bad_files = _release(zb, sha="0" * 64)          # сумма не совпала — архив удалён, не ставим
    monkeypatch.setattr(updater, "_open", lambda url, timeout: _Resp(bad_files[url], url))
    with pytest.raises(updater.UpdateError, match="контрольная сумма"):
        updater.download(updater.release_from_json(bad_data), tmp_path / "dl2")
    assert not list((tmp_path / "dl2").glob("*.zip"))


def test_extract_rejects_paths_outside(tmp_path):
    z = tmp_path / "evil.zip"
    z.write_bytes(_zip({"../../evil.txt": b"x", "AppDesignStudio.exe": b"MZ"}))
    with pytest.raises(updater.UpdateError, match="недопустимый путь"):
        updater.extract(z, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


def test_install_script_waits_copies_and_restarts(tmp_path):
    s = updater.install_script(tmp_path / "new", tmp_path / "App Design Studio", 1234)
    assert "Wait-Process -Id 1234" in s and "robocopy" in s and "AppDesignStudio.exe" in s
    assert "'" + str(tmp_path / "App Design Studio") + "'" in s     # пути в кавычках (с пробелами)
    assert updater.install_dir() is None                              # из исходников — заменять нечего
