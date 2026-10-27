from pathlib import Path

import pytest

from app.core.persistence.container import ProjectFormatError
from app.core.project.index import FILTER_ARCHIVE, FILTER_FAVORITES, FILTER_RECENT, SORT_TITLE
from app.core.project.service import ProjectError
from tests.conftest import make_spec


@pytest.mark.parametrize("platforms,devices,expected", [  # S01, S02, S03
    (("android",), ("android_phone",), ["android"]),
    (("windows",), ("windows_window",), ["windows"]),
    (("android", "windows"), ("android_phone", "windows_window"), ["android", "windows"]),
])
def test_create_projects(service, projects_dir, platforms, devices, expected):
    doc, path = service.create(make_spec(projects_dir, platforms=platforms, devices=devices))
    assert path.exists() and path.suffix == ".adsproj"
    reopened = service.open(path)
    assert reopened.meta.platforms == expected
    assert [s.platform for s in reopened.screens] == expected
    assert service.index.get(doc.meta.id).screens == len(expected)


def test_landscape_swaps_phone_size(service, projects_dir):
    spec = make_spec(projects_dir)
    spec.orientation = "landscape"
    doc, _ = service.create(spec)
    assert doc.screens[0].width > doc.screens[0].height


def test_create_rejects_bad_names_and_duplicates(service, projects_dir):
    for bad in ["", "a/b", "что?", "CON", "x" * 200]:
        with pytest.raises(ProjectError):
            service.create(make_spec(projects_dir, title=bad))
    service.create(make_spec(projects_dir, title="Один"))
    with pytest.raises(ProjectError, match="существует"):
        service.create(make_spec(projects_dir, title="Один"))


def test_save_reopen_and_meta_update(service, projects_dir):  # S04
    doc, path = service.create(make_spec(projects_dir))
    rec = service.index.get(doc.meta.id)
    service.update_meta(rec, title="Новое имя", tags=["Тёмная", "android", " ", "Тёмная"])
    again = service.open(path)
    assert again.meta.title == "Новое имя"
    assert again.meta.tags == ["android", "Тёмная"]
    assert service.index.get(doc.meta.id).title == "Новое имя"


def test_index_filters_search_folders(service, projects_dir):
    a, _ = service.create(make_spec(projects_dir, title="Альфа"))
    b, _ = service.create(make_spec(projects_dir, title="Бета"))
    c, pc = service.create(make_spec(projects_dir, title="Гамма"))
    idx = service.index
    idx.set_favorite(a.meta.id, True)
    idx.set_archived(b.meta.id, True)
    service.open(pc)
    idx.add_folder("Клиенты")
    idx.set_folder(c.meta.id, "Клиенты")
    assert [r.title for r in idx.query(filter=FILTER_FAVORITES)] == ["Альфа"]
    assert [r.title for r in idx.query(filter=FILTER_ARCHIVE)] == ["Бета"]
    assert [r.title for r in idx.query(filter=FILTER_RECENT)] == ["Гамма"]
    assert [r.title for r in idx.query(sort=SORT_TITLE)] == ["Альфа", "Гамма"]
    assert [r.title for r in idx.query(search="гАм")] == ["Гамма"]
    assert [r.title for r in idx.query(folder="Клиенты")] == ["Гамма"]
    idx.remove_folder("Клиенты")
    assert idx.get(c.meta.id).folder == "" and idx.get(c.meta.id) is not None
    assert idx.counts()["all"] == 2


def test_duplicate_gets_new_ids(service, projects_dir):
    doc, path = service.create(make_spec(projects_dir, title="Оригинал"))
    copy, cpath = service.duplicate(service.index.get(doc.meta.id))
    assert copy.meta.id != doc.meta.id
    assert {s.id for s in copy.screens}.isdisjoint({s.id for s in doc.screens})
    assert cpath != path and cpath.exists() and path.exists()
    assert copy.meta.title == "Оригинал (копия)"


def test_import_and_export(service, projects_dir, tmp_path):
    doc, path = service.create(make_spec(projects_dir, title="Экспорт"))
    out = tmp_path / "Выгрузка"
    out.mkdir()
    exported = service.export_copy(service.index.get(doc.meta.id), out / "Экспорт.adsproj")
    imported_doc, ipath = service.import_file(exported, projects_dir)
    assert imported_doc.meta.id != doc.meta.id  # тот же проект уже есть — импорт копией
    assert ipath.exists() and exported.exists()


def test_open_corrupted_marks_missing(service, projects_dir):
    doc, path = service.create(make_spec(projects_dir))
    path.write_bytes(b"broken")
    with pytest.raises(ProjectFormatError):
        service.open(path)
    assert service.index.get(doc.meta.id).missing


def test_refresh_missing(service, projects_dir):
    doc, path = service.create(make_spec(projects_dir))
    Path(path).unlink()
    service.refresh_missing()
    assert service.index.get(doc.meta.id).missing
