# Changelog

## Unreleased

- One-time, opt-in GitHub star offer: on first use `femm_status` / `femm_selftest` carry a
  `first_run_note`; new tool `femm_star_repo` ("star" via the `gh` CLI with a browser fallback,
  "open", "dismiss") records the answer in `state.json` under `FEMM_AGENT_HOME` and never asks again.

## 0.1.0 (2026-10-17)

First release, built against FEMM 5.0 build 06oct2026.

- TCP link to `femm_headless` / `femm_gui` speaking FEMM 5's newline protocol directly
  (no pyFEMM import needed), multi-instance sessions on separate ports.
- MCP server `femm` with tool groups: session, document, geometry, properties, materials,
  mesh/solve, post-processing, scripting, docs, experiments, health, report.
- Catalog of every FEMM 5 scripting command and all four material libraries as JSON.
- Physics health checks, analytic estimates, standard experiments (force vs position,
  torque vs angle, cogging, back-EMF, inductance, AC sweep, parametric).
- Claude skills, Claude Code plugin manifests, installer scripts for Windows and Unix.
