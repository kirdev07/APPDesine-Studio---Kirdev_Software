import pytest

from app.core.paths import AppPaths
from app.core.project.index import ProjectIndex
from app.core.project.service import NewProjectSpec, ProjectService


@pytest.fixture
def paths(tmp_path):
    return AppPaths(tmp_path / "Данные программы").ensure()


@pytest.fixture
def service(paths):
    index = ProjectIndex(paths.index_db)
    yield ProjectService(paths, index)
    index.close()


@pytest.fixture
def projects_dir(tmp_path):
    d = tmp_path / "Мои проекты" / "Дизайн"
    d.mkdir(parents=True)
    return d


def make_spec(location, title="Мой проект", platforms=("android",), devices=("android_phone",)):
    return NewProjectSpec(title=title, location=location, platforms=list(platforms), devices=list(devices),
                          template_id="blank_android")
