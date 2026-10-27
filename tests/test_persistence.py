import stat
import zipfile

import pytest

from app.core.persistence.container import ProjectFormatError, load_project, save_project
from app.core.persistence.recovery import RecoveryStore
from app.core.project.service import build_document
from tests.conftest import make_spec


def _doc(tmp_path, **kw):
    return build_document(make_spec(tmp_path, **kw))


def test_roundtrip_equivalence_cyrillic_path(tmp_path):  # S04, S07
    doc = _doc(tmp_path, title="Проект «Ёлка» №1", platforms=("android", "windows"),
               devices=("android_phone", "windows_window"))
    doc.meta.tags = ["тёмная тема", "Telegram"]
    path = tmp_path / "Папка с пробелами" / "Проект Ёлка.adsproj"
    save_project(doc, path)
    loaded = load_project(path)
    assert loaded.to_dict() == doc.to_dict()


def test_save_is_atomic_and_keeps_backups(tmp_path):
    doc = _doc(tmp_path)
    path = tmp_path / "p.adsproj"
    backups = tmp_path / "backups"
    for i in range(8):
        doc.meta.description = f"версия {i}"
        save_project(doc, path, backup_dir=backups, keep_backups=3)
    assert load_project(path).meta.description == "версия 7"
    assert len(list((backups / doc.meta.id).glob("*.adsproj"))) == 3
    assert not list(tmp_path.glob("*.tmp-*"))


def test_failed_save_keeps_original(tmp_path, monkeypatch):
    doc = _doc(tmp_path)
    path = tmp_path / "p.adsproj"
    save_project(doc, path)
    original = path.read_bytes()
    import app.core.persistence.container as c

    def boom(*a, **k):
        raise OSError("диск переполнен")
    monkeypatch.setattr(c, "write_archive", boom)
    with pytest.raises(OSError):
        save_project(doc, path)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp-*"))


@pytest.mark.parametrize("payload", [b"", b"not a zip at all", b"PK\x03\x04garbage"])
def test_malformed_zip_rejected(tmp_path, payload):  # S05
    p = tmp_path / "bad.adsproj"
    p.write_bytes(payload)
    with pytest.raises(ProjectFormatError):
        load_project(p)


def test_truncated_project_rejected(tmp_path):  # S05
    doc = _doc(tmp_path)
    p = tmp_path / "p.adsproj"
    save_project(doc, p)
    data = p.read_bytes()
    p.write_bytes(data[: len(data) // 2])
    with pytest.raises(ProjectFormatError):
        load_project(p)


def _zip(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


@pytest.mark.parametrize("evil", ["../evil.txt", "screens/../../evil.txt", "/abs.txt", "C:/win.txt",
                                  "a\\..\\b.txt", "screens/CON.json", "screens/bad:name.json"])
def test_zip_slip_and_bad_names_rejected(tmp_path, evil):  # S06
    p = tmp_path / "evil.adsproj"
    _zip(p, {"manifest.json": '{"format":"adsproj","schema_version":1}', evil: "x"})
    with pytest.raises(ProjectFormatError):
        load_project(p)
    assert not (tmp_path.parent / "evil.txt").exists()


def test_duplicate_names_case_insensitive_rejected(tmp_path):
    p = tmp_path / "dup.adsproj"
    _zip(p, {"manifest.json": "{}", "Manifest.json": "{}"})
    with pytest.raises(ProjectFormatError):
        load_project(p)


def test_symlink_entry_rejected(tmp_path):
    p = tmp_path / "link.adsproj"
    with zipfile.ZipFile(p, "w") as zf:
        info = zipfile.ZipInfo("assets/link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(ProjectFormatError):
        load_project(p)


def test_zip_bomb_rejected(tmp_path):
    p = tmp_path / "bomb.adsproj"
    with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("assets/zeros.bin", b"\0" * (20 * 1024 * 1024))
    with pytest.raises(ProjectFormatError, match="сжатия"):
        load_project(p)


def test_newer_schema_rejected(tmp_path):
    p = tmp_path / "new.adsproj"
    _zip(p, {"manifest.json": '{"format":"adsproj","schema_version":99}'})
    with pytest.raises(ProjectFormatError, match="новой версией"):
        load_project(p)


def test_invalid_project_data_rejected(tmp_path):
    p = tmp_path / "bad.adsproj"
    _zip(p, {"manifest.json": '{"format":"adsproj","schema_version":1,"project_id":"x","screens":[]}',
             "project.json": '{"id":"x","title":"t","platforms":["web"],"created_at":"","modified_at":""}'})
    with pytest.raises(ProjectFormatError, match="повреждены"):
        load_project(p)


def test_recovery_store_roundtrip(tmp_path):  # S22
    doc = _doc(tmp_path, title="Восстановление")
    store = RecoveryStore(tmp_path / "recovery")
    store.write(doc, tmp_path / "оригинал.adsproj")
    entries = store.entries()
    assert len(entries) == 1 and entries[0].title == "Восстановление"
    assert store.load(entries[0]).to_dict() == doc.to_dict()
    store.clear(doc.meta.id)
    assert store.entries() == []
