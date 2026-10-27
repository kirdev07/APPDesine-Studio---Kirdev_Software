# Decisions for Stage 1 planning (not blockers for this documentation pack)
- Exact Windows 10/11 build support and Qt/Python compatibility to verify on target.
- Precise Fusion AMOLED design tokens and pixel measurements require screenshots of actual implementation for user signoff.
- Qt Widgets/QGraphicsView chosen as baseline; optional advanced rendering approach must be justified, not silently substituted.
- Final installer format and code-signing strategy to decide in Stage 8.
- Preview support matrix for Compose/Material 3 components to specify and label honestly.
- Asset pack licenses must be checked before bundling.
- Autosave cadence, backup retention, file size limits, and performance thresholds to tune via tests.
- Plugin architecture may be deferred; do not promise executable third-party plugins in v1.0 without security design.
