# AI handoff export contract
Modes: (A) New app from design; (B) Update existing app, preserving functionality and inspecting existing code first.

Export root:
manifest.json; screens/; components/; styles/; animations/; interactions/; assets/icons/; assets/fonts/; assets/images/; previews/; AI_TASK.md; README.md.

Manifest: export_schema_version, project_id, target_platform(s), project_title, screen IDs, component IDs, asset hashes and licenses, references, tool_version, export_mode. Use versioned JSON schema; stable identifiers and deterministic ordering.

Each screen: viewport, safe area, node tree, styles/tokens, constraints, variants, interactive states and actions. Components: master definition, instance overrides, state mappings. Animations: targets, keyframes, timing, easing. Resources: exact relative path, SHA-256, provenance, redistribution status. Never silently include disallowed fonts.

AI_TASK.md editable sections: objective, platform, new/update mode, screens to implement, visual fidelity rules, interactions, integration constraints, assets, excluded functionality, acceptance criteria, testing instructions, preserve existing behavior, no destructive rewrites.

Export validator blocks critical broken references, unsafe paths and missing required files; warns on unsupported visual features and license uncertainty. Archive can be inspected offline.
