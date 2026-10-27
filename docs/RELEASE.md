# Сборка и выпуск

## Сборка программы

```bash
.venv\Scripts\python -m pip install -e .[dev,build]
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

Скрипт:
1. прогоняет тесты (`pytest -q`);
2. собирает `dist\AppDesignStudio\AppDesignStudio.exe` (PyInstaller, папка программы — Python не нужен);
3. запускает собранную программу с `--smoke-test` в окружении без Python и проверяет отчёт;
4. упаковывает `dist\AppDesignStudio-<версия>-win64.zip` (portable);
5. если установлен Inno Setup 6 (`ISCC.exe`), собирает установщик `dist\AppDesignStudio-<версия>-setup.exe`.

## Проверка на чистой машине (S23, S24)

1. Windows 10 или 11 без Python; сеть можно отключить.
2. Распаковать ZIP в любую папку (в том числе с русскими буквами в пути) или запустить установщик.
3. Выполнить `AppDesignStudio.exe --smoke-test %TEMP%\ads_smoke.json` — код выхода 0, в отчёте `"ok": true`.
4. Запустить программу обычным образом: Project Hub → новый проект → рабочая область → F5 (предпросмотр) →
   Ctrl+E (AI-экспорт) → собрать пакет.

## Где программа хранит данные

- Проекты: `Документы\App Design Studio` (меняется в настройках).
- Служебные данные: `%LOCALAPPDATA%\AppDesignStudio` (журнал, резервные копии, восстановление, настройки).
- Удаление программы: удалить папку программы (или через «Установка и удаление программ» для setup.exe);
  проекты и служебные данные пользователя при этом не удаляются.
