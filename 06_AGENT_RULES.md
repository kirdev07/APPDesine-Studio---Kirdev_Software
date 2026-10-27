# Claude Code — mandatory agent operating rules
Current permission: READ AND PLAN ONLY. No code, package installs, file mutation or execution of setup scripts until the user explicitly authorizes Stage 1.

1. Study this pack and inspect actual environment/repository before proposing edits.
2. Do not invent implementation completion or test results.
3. Respect all 13 approved design decisions, especially Project Hub variant 2 and Component Builder Fusion 2.0 revised layout.
4. Keep 12-module architecture; separate Qt UI from serializable model.
5. Stage gates are mandatory: after every stage provide report and STOP for user confirmation.
6. Do not delete existing project files or overwrite working features without reason and permission.
7. Do not run imported scripts, unsafe SVG content or arbitrary user code.
8. Avoid unnecessary dependencies, network, telemetry, cloud, accounts and API keys.
9. Do not substitute static screenshots or dummy UI for functioning editor features.
10. Document unsupported features and partial implementations; do not falsely claim Compose pixel fidelity.
11. Maintain tests, docs and rollback checkpoints throughout.
12. Before first implementation request, deliver a proposed Stage 1 task breakdown, environment/dependency check plan, risks and acceptance checklist, then wait.

Required stage report: summary, files, test commands and results, screenshots, known limitations, checkpoint, next proposal, request for approval.
