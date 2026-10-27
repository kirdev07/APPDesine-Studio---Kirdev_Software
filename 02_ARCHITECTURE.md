# Architecture and module boundaries
## Stack (proposed, validate on target machine)
Python 3.12+, PySide6 Qt Widgets, QGraphicsView/QGraphicsScene canvas, Qt SVG and font APIs, SQLite for local project index, QSettings for preferences, JSON versioned schema, ZIP container, pytest + pytest-qt, Windows packaging with PyInstaller (evaluate installer format later).

## Twelve modules
01 Core & Project System — project CRUD, document model, serialization, migrations, atomic saves, autosave, backups, commands.
02 Fusion Workspace — shell, dock panels, canvas, selection, layers, inspector, keyboard shortcuts.
03 Layout Engine — deterministic constraints, stacks, grids, responsive variants, validation.
04 Component Engine — component schema, instances, overrides, state machine, reusable library.
05 Asset & SVG Engine — sanitized imports, vector model, resource IDs, licensing metadata.
06 Typography Engine — font registration, preview, tokenization, glyph coverage and overflow checks.
07 Animation Engine — keyframes, easing, state transitions, timeline playback.
08 Visual Logic Engine — declarative triggers/actions/variables; sandboxed interpreter with no eval.
09 Preview Engine — target adapters, event simulation, device presets, Qt desktop preview.
10 Validation Engine — schema/asset/layout/accessibility/export diagnostics.
11 AI Export Engine — deterministic structured export and task generator.
12 Settings & Library Manager — preferences, library catalogs, device profiles, backup controls.

## Dependency direction
Qt UI -> application services -> pure document/model and layout services. Target-specific adapters depend on shared model, not vice versa. Export and preview consume immutable document snapshots. Do not serialize QObject, QGraphicsItem or arbitrary Python objects.

## Suggested repository structure
app/{core/{project,document,commands,persistence},ui/{shell,workspace,panels,dialogs,themes},editors/{components,svg,typography,animations,logic},engines/{layout,preview,validation},platforms/{android,windows},libraries,exporters}; resources/; templates/; tests/; docs/; packaging/.

## Versioned project model
.adsproj is a ZIP container with manifest.json, screens/, components/, styles/, animations/, interactions/, assets/, project metadata. Use stable IDs and relative asset references; versioned schema and explicit migrations. Separate editor session state from content. Asset hashes, deduplication, validation, atomic save, backups, crash recovery.

## Safety
Validate ZIP entry paths, sizes, file counts, duplicate names, and symlinks; treat all imported resources as untrusted. Avoid unsafe SVG external references and embedded scripts. Native preview executes only app-owned trusted code, not imported arbitrary Python.
