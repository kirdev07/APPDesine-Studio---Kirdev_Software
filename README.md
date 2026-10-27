# App Design Studio

Локальная студия дизайна интерфейсов Android (Jetpack Compose / Material 3) и Windows (Python / PySide6).
Спецификация — файлы `00_START_HERE.md` … `08_OPEN_DECISIONS.md` и `assets/mockups/`.

**Состояние:** этапы 1–7 из 8 (Foundation & Project Hub, Fusion Workspace, Auto Layout, компоненты/SVG/типографика,
анимации и визуальная логика, интерактивный предпросмотр на устройствах, проверка проекта и AI-экспорт).

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
  индекс проектов (SQLite, его можно удалить — он перестроится при открытии проектов), `settings.ini`,
  личная библиотека компонентов (`library\*.adscomp`) и пользовательские шаблоны (`templates\*.adsproj`).
- Переменная `ADS_DATA_DIR` переопределяет папку служебных данных (для тестов).

Интерактивный предпросмотр (F5) — симуляция без сборки APK/EXE: экран перестраивается под выбранное
устройство и рисуется в его рамке. Android — приближение Compose / Material 3; Windows — отрисовка студии
в рамке окна, без нативных виджетов. Ограничения перечислены на странице предпросмотра.

AI-экспорт (Ctrl+E) собирает ZIP для Claude Code: `manifest.json` (экраны, компоненты, ресурсы с SHA-256 и
лицензиями, список файлов), `screens/`, `components/`, `styles/`, `animations/`, `interactions/`, `assets/`,
`previews/`, `schemas/`, `AI_TASK.md` (редактируется перед сборкой), `README.md`. Режимы: новое приложение или
обновление существующего. Одинаковый проект даёт побайтно одинаковый архив; критичные замечания проверки (F7)
блокируют сборку; ресурсы с запретом распространения в пакет не входят.

Программа работает офлайн: без учётной записи, облака, телеметрии и ключей API.

## Структура

```
app/core/document     модель проекта и дерево узлов (без Qt)
app/core/commands     команды изменения документа и стек undo/redo (без Qt)
app/core/persistence  контейнер .adsproj, миграции, восстановление
app/engines/layout    движок раскладки: Auto Layout, привязки, диагностика (без Qt)
app/engines/components мастер-компоненты, экземпляры, состояния, личная библиотека (без Qt)
app/engines/assets    SVG: санитизация, импорт в векторы, экспорт (без Qt)
app/engines/animation ключевые кадры, плавности, выборка по времени (без Qt)
app/engines/logic     интерпретатор взаимодействий без eval, повтор сценариев (без Qt)
app/engines/validation проверка проекта: серьёзность, место, ссылки, ресурсы, лицензии, контраст (без Qt)
app/exporters         AI-экспорт: детерминированный ZIP, JSON-схемы, AI_TASK.md, проверка пакета (без Qt)
app/engines/preview   профили устройств, плотность, ориентация, безопасные области, проверки, тест-сценарии (без Qt)
app/core/project      индекс SQLite и операции над проектами
app/libraries         профили устройств, шаблоны проектов, базовые компоненты Android/Windows
app/ui                тема Fusion AMOLED, оболочка, Project Hub, мастер, настройки
app/ui/workspace      холст, слои, инспектор, полоса экранов
app/ui/studio         Component Builder, SVG-редактор, типографика, цвета, ресурсы, анимации, логика, предпросмотр,
                      проверка проекта, AI-экспорт
tests/                pytest + pytest-qt
```

## Лицензия

© 2026 Kirdev Software. Все права защищены — см. `LICENSE`. Использование без письменного разрешения
правообладателя запрещено. Сторонние компоненты (PySide6/Qt, LGPLv3) — см. `THIRD_PARTY_NOTICES`.
