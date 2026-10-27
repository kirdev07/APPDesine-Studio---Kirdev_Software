# Eight gated implementation stages
**Global gate:** Only begin a stage with explicit user approval. Finish with test evidence, screenshot(s), changed files, limitations, rollback checkpoint and STOP. Never automatically proceed.

## Stage 1 — Foundation & Project Hub
Deliver app shell, Fusion AMOLED, navigation, minimal Project Hub variant 2, New Project Wizard, settings, versioned .adsproj persistence and logging. Acceptance: create/save/reopen a project; verify corruption handling and Cyrillic paths.
## Stage 2 — Fusion Workspace
Canvas, layers, selection, transform, grid/guides, snapping, grouping, inspector, undo/redo. Acceptance: build/edit/save a basic screen; 50 undo/redo operations round-trip correctly.
## Stage 3 — Auto Layout & basic components
Stacks, grids, constraints, text, buttons, fields, cards, navigation. Acceptance: responsive behavior on phone/tablet/window with long Russian text; deterministic results.
## Stage 4 — Component, SVG, Typography
Reusable component library, Component Builder Fusion 2.0, vector/icon editor, font manager, import/export and templates. Acceptance: create component, reuse across projects, preserve styles, warn on missing assets.
## Stage 5 — Animation & Visual Logic
Keyframes, easing, states, screen transitions, declarative actions/variables. Acceptance: functional multi-screen interactive prototype with deterministic replay.
## Stage 6 — Interactive Preview
Android device simulation and safe Windows Qt preview; device profiles, safe areas, orientation, interactions and test scenarios. Acceptance: exercise supported prototype interactions without APK/EXE build; clearly label simulation limits.
## Stage 7 — Validator & AI Export
Diagnostics with severity/location, new/update AI task modes, complete deterministic ZIP. Acceptance: round-trip extraction and schema validation; no missing references; verified resource attribution.
## Stage 8 — Stabilization & release
Regression/performance/accessibility testing, crash recovery, docs, installer, clean Windows 10/11 smoke tests. Acceptance: all critical tests pass, known limitations documented, packaged app runs without separately installed Python.

## Stage report format
1. Implemented functions and changed files. 2. Actual test commands and pass/fail totals. 3. Screenshots of running UI. 4. Known issues. 5. Commit/hash or rollback checkpoint. 6. Proposed next stage (not started). 7. Explicit request for approval.
