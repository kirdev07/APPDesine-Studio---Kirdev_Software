# App Design Studio

Локальная студия дизайна интерфейсов Android (Jetpack Compose / Material 3) и Windows (Python / PySide6).
Спецификация — файлы `00_START_HERE.md` … `08_OPEN_DECISIONS.md` и `assets/mockups/`.

**Состояние:** этап 1 из 8 (Foundation & Project Hub).

## Запуск (Windows 10/11, Python 3.12)

```bash
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python -m app
```

Тесты: `.venv\Scripts\python -m pytest -q`
Скриншоты для отчёта: `.venv\Scripts\python -m tools.stage_screenshots docs\screenshots`

## Данные

- Проекты: `Документы\App Design Studio\*.adsproj` (папку можно сменить в настройках).
- Служебные данные: `%LOCALAPPDATA%\AppDesignStudio` — журнал, резервные копии, снимки восстановления,
  индекс проектов (SQLite, его можно удалить — он перестроится при открытии проектов), `settings.ini`.
- Переменная `ADS_DATA_DIR` переопределяет папку служебных данных (для тестов).

Программа работает офлайн: без учётной записи, облака, телеметрии и ключей API.

## Структура

```
app/core/document     модель проекта (без Qt)
app/core/persistence  контейнер .adsproj, миграции, восстановление
app/core/project      индекс SQLite и операции над проектами
app/libraries         встроенные профили устройств и шаблоны
app/ui                тема Fusion AMOLED, оболочка, Project Hub, мастер, настройки
tests/                pytest + pytest-qt
```
