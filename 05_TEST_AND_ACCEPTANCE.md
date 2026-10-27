# QA and acceptance plan
Test with pytest, pytest-qt, unit tests for pure model/layout, integration tests for save/open/export, GUI smoke tests and manual visual review against approved mockups.

## Every stage
- Application launches; no critical exceptions; controls under test are functional.
- New tests and prior regression suite pass, or failures are transparently reported.
- Unicode/Cyrillic names and paths tested.
- Save/reopen data equivalence and undo/redo consistency tested where applicable.
- No missing assets or severe log errors.
- Real screenshots and reproducible steps supplied.
- No phase transition without explicit approval.

## Scenario matrix
S01 New Android project; S02 Windows project; S03 combined project; S04 save/reopen; S05 malformed ZIP; S06 zip-slip payload; S07 Unicode path; S08 undo/redo 50 operations; S09 nested Auto Layout; S10 long Cyrillic text and clipping; S11 import safe SVG; S12 reject unsafe external SVG content; S13 missing font fallback; S14 reusable component instance overrides; S15 multi-screen logic; S16 replay animation; S17 phone/tablet/window preview; S18 resource licensing warnings; S19 AI export new project; S20 AI export existing project; S21 deterministic export; S22 crash/autosave recovery; S23 installer clean machine; S24 offline run.

## Load tests (targets for measurement, not guarantees)
10/50/100 screens, 500–2000 components, hundreds of SVG resources. Record startup time, canvas responsiveness, memory, save/load/export time; agree thresholds after baseline measurement.

## Final v1.0 acceptance
All 13 approved design areas are represented by working capabilities; core project editing, Auto Layout, component/SVG/font/animation editors, Visual Logic, preview, validator, AI export and installer operate with documented platform limitations. No critical failing tests, no silent data loss, no hidden broken controls.
