import os

import pytest

os.environ.setdefault("ADS_NO_TOUR", "1")  # обучение при первом запуске мешало бы тестам клавиатуры

from app.core.paths import AppPaths
from app.core.project.index import ProjectIndex
from app.core.project.service import NewProjectSpec, ProjectService


@pytest.fixture(autouse=True, scope="session")
def _clear_clipboard_at_exit():
    # Платформа offscreen падает при выходе, если в буфере обмена остались данные из Python (QMimeData).
    # На реальной платформе windows этого нет; очищаем буфер, чтобы код выхода тестов был честным.
    yield
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        app.clipboard().clear()
        app.processEvents()


@pytest.fixture(autouse=True)
def _delete_leftover_windows():
    # qtbot закрывает окна, но не удаляет их: без этого окна всех тестов копятся вместе с таймерами,
    # и общий прогон с каждым тестом становится медленнее (вплоть до «зависания»).
    yield
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    for w in app.topLevelWidgets():  # без close(): он мог бы показать модальный вопрос о сохранении
        w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    import gc
    gc.collect()


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


def inline_strings(src: str, files: dict) -> str:
    """Код экрана с текстами вместо stringResource(R.string.…) — для проверок по надписям (1.30: строки
    вынесены в values/strings.xml)."""
    import re
    key = next(k for k in files if k.endswith("app/src/main/res/values/strings.xml"))
    xml = files[key].decode()
    table = {m.group(1): m.group(2).replace("\'", "'").replace('\\"', '"').replace("&lt;", "<").replace("&gt;", ">")
             .replace("&amp;", "&") for m in re.finditer(r'<string name="([^"]+)"[^>]*>(.*?)</string>', xml)}
    return re.sub(r"stringResource\(R\.string\.([a-z0-9_]+)\)",
                  lambda m: '"' + table.get(m.group(1), m.group(1)) + '"', src)
