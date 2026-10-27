# Full product requirements — App Design Studio v1.0
## Product mission
A local-first Windows desktop visual design studio to create Android (Jetpack Compose / Material 3) and Windows (Python / PySide6) app UIs, preview their interactions without building APK/EXE, and hand complete, structured design packages to Claude Code. This is NOT an Android compiler or guaranteed pixel-perfect Compose renderer.

## UI and usability
- Strict monochrome Fusion AMOLED application chrome: black backgrounds, grayscale surfaces, thin separators, accessible contrast, compact density; project design may use arbitrary colors.
- Russian UI with localization-ready strings; responsive dockable panels, keyboard shortcuts, accessible focus states.
- Shared workspace: component browser on left, large central canvas, property inspector on right, collapsible bottom screen/asset/preview strip.
- Project Hub approved layout **variant 2**: minimal folder navigation left, projects center, details right, templates below.
- All controls visible in approved designs must either function or be clearly marked unavailable with a documented phase; never present dummy buttons as working features.

## Capabilities
1. Project Hub, New Project Wizard: Android/Windows/combined, folders, recent, search, tags, duplicate, import/export, template manager, local persistence.
2. Fusion Workspace: multi-screen documents, layers, select/move/resize, guides, grid, snap, zoom, alignment, group, lock, hide, copy/paste, undo/redo.
3. Auto Layout: vertical/horizontal stacks, grids, padding/gaps, min/max, fill/wrap/fixed, anchors and responsive variants. Deterministic layout with cycle handling and diagnostics.
4. Component Studio: buttons, fields, cards, navigation bars, pill indicators, music players, sliders, switches, dialogs, lists, charts and reusable nested components. States: default, hover (desktop), focus, pressed, disabled, loading, empty, error as applicable. Component instance overrides and reusable libraries.
5. SVG/Icon Editor: import/export SVG, vector primitives, paths, strokes, fills, gradients, viewBox, layers, selection handles, icon collections; sanitize untrusted SVG; avoid promising full support for all SVG features.
6. Typography: font import and preview (TTF/OTF), Cyrillic/Latin, sizes, weights, spacing, line height, style tokens, overflow and fallback warnings; licensing metadata.
7. Animation Studio: timeline, keyframes, easing, transitions, state-based effects, play/pause, reduced-motion preview.
8. Visual Logic: safe declarative event-action graph (tap, click, toggle, navigate, set variable, show dialog), no arbitrary code evaluation, invalid cycles/links diagnosed.
9. Interactive Preview: phone/tablet/Windows sizes, DPI, orientation, safe areas, mouse/touch simulations, input, scroll, screen navigation, repeatable scripted interactions. Android is approximation; Windows Qt preview may use native widgets where safe.
10. Validator: structural/schema errors, missing assets, text overflow, layout constraints, unsupported platform features, dangling references, inaccessible contrast warnings, asset licensing warnings; severity and actionable location.
11. AI Export: new project vs update existing project; ZIP with images, assets, screen/component JSON, tokens, animation and interaction specs, AI_TASK.md, README; user-editable instructions, selectable target platform and scope.
12. Settings & Library Manager: theme, language, device profiles, performance, backups, resource packs, versions, source/licensing, default export options.

## Quality and nonfunctional requirements
- Offline-first; no compulsory account, telemetry, cloud, advertising, or API key.
- Responsive UI during asset import, validation, and export (background workers and cancellation where appropriate).
- Unicode paths and Russian file names work.
- Never silently delete user content. Atomic save, backups, recoverable autosave, schema migrations, path traversal protections and decompression limits.
- No executing imported Python, scripts, JavaScript, or arbitrary SVG content. Font/image parsers should be isolated or guarded where practical.
- Project document is independent of Qt widgets and target platform code.
- Preserve licenses/attribution and avoid bundling nonredistributable fonts/icons.
- No promised exact Android rendering or turnkey generation of complete applications.
