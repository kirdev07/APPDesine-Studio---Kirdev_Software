# Тестирование

Запуск всех тестов (около 1,5 минуты):

```bash
.venv\Scripts\python -m pytest -q
```

Без окна (как в CI): `set QT_QPA_PLATFORM=offscreen` перед запуском. На платформе offscreen нет базы шрифтов,
поэтому два теста шрифтов пропускаются; на обычной платформе Windows проходят все тесты.

Самопроверка установленной программы (S23, S24):

```bash
AppDesignStudio.exe --smoke-test отчёт.json
```

Код выхода 0 — все шаги прошли; отчёт содержит время каждого шага. Данные пользователя не затрагиваются.

## Сценарии приёмки S01–S24

| Сценарий | Проверка |
|---|---|
| S01 Новый Android-проект | `test_gui::test_create_edit_save_reopen_via_ui`, `test_service::test_create_projects` |
| S02 Windows-проект | `test_service::test_create_projects[windows]`, `test_preview::test_windows_preview_frame_and_scale` |
| S03 Совмещённый проект | `test_service::test_create_projects[android+windows]`, `test_release::test_smoke_self_check_passes` |
| S04 Сохранение и открытие | `test_persistence::test_roundtrip_equivalence_cyrillic_path`, `test_service::test_save_reopen_and_meta_update` |
| S05 Повреждённый ZIP | `test_persistence::test_malformed_zip_rejected`, `test_gui::test_open_corrupted_shows_error_not_crash` |
| S06 Zip-slip | `test_persistence::test_zip_slip_and_bad_names_rejected`, `test_export::test_package_check_detects_tampering_and_unsafe_paths` |
| S07 Путь с Юникодом | `test_persistence::test_roundtrip_equivalence_cyrillic_path`; собранная программа проверена в папке «Программы» |
| S08 50 операций undo/redo | `test_commands::test_50_operations_undo_redo_roundtrip`, `test_workspace::test_fifty_ui_operations_undo_redo` |
| S09 Вложенный Auto Layout | `test_layout_engine::test_nested_auto_layout` |
| S10 Длинный русский текст | `test_layout_engine::test_hug_frame_with_long_russian_text_wraps`, `test_auto_layout_ui` |
| S11 Безопасный SVG | `test_svg::test_safe_svg_imports_cleanly`, `test_studios::test_svg_editor_import_draw_save_insert` |
| S12 Небезопасный SVG | `test_svg::test_unsafe_content_removed`, `test_svg::test_dangerous_or_broken_files_rejected` |
| S13 Замена отсутствующего шрифта | `test_studios::test_font_fallback_warning` |
| S14 Переопределения экземпляров | `test_components_core::test_instance_overrides_survive_master_change`, `test_studios` |
| S15 Логика нескольких экранов | `test_behavior_engines::test_multiscreen_logic_flow`, `test_prototype_ui` |
| S16 Повтор анимации | `test_behavior_engines::test_replay_is_deterministic`, `test_prototype_ui::test_animation_studio_edit_play_undo` |
| S17 Телефон / планшет / окно | `test_preview::test_preview_page_devices_rotation_density_compare`, `test_preview::test_windows_preview_frame_and_scale` |
| S18 Предупреждения о лицензиях | `test_export::test_validator_severity_and_location`, `test_export::test_export_new_project_package_schema_and_determinism` |
| S19 AI-экспорт нового проекта | `test_export::test_export_new_project_package_schema_and_determinism`, `test_export::test_export_page_builds_archive_and_blocks_on_critical` |
| S20 AI-экспорт существующего проекта | `test_export::test_export_update_mode_scope_and_edited_task` |
| S21 Детерминированный экспорт | `test_export::test_export_new_project_package_schema_and_determinism` |
| S22 Сбой и автосохранение | `test_gui::test_autosave_and_recovery`, `test_persistence::test_recovery_store_roundtrip` |
| S23 Установка на чистую машину | `--smoke-test` собранной программы без Python в окружении (см. RELEASE.md); на отдельной чистой ВМ — вручную |
| S24 Офлайн-запуск | программа не обращается к сети; `--smoke-test` выполняется без сети |

Производительность — `test_performance.py` и `docs/PERFORMANCE.md`; доступность —
`test_performance::test_controls_have_names_and_theme_contrast`.
