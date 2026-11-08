# Changelog

## 0.2.0 (2026-11-08)

Theme: an agent must not get a wrong or unchecked number out of the server silently. Every
behaviour change has an offline test against the fake engines in `tests/`; the live suite
(`pytest -m live`, 28 tests) passes on FEMM 5.0 build 20261101 (1144).

Breaking:
- Tool `femm_experiment_backemf` renamed `femm_experiment_back_emf` (no alias). The module function
  is `experiments.back_emf` (`experiments.backemf` kept as an alias); its result `experiment` is
  `"back_emf"`.
- `drive` / `dq` dicts (torque vs angle, inductance) now need `poles` or `pole_pairs`; a missing
  pole count used to default silently to p = 1.

Unchecked results are visible:
- `health.summarize` (every `health_summary`, `femm_health_check` summary) adds `verdict`: PASS (none
  failed, >= 1 passed, none inconclusive), CHECK (nothing applicable or some ok = null), FAIL.
- Sessions carry `checked` (in `femm_session_list`); it is reset by every solve / load / opened
  solution / experiment and set only by `femm_health_check`. `femm_solve` and `femm_load_solution`
  return `checked: false` and `next`, the exact health-check call (with the model's label groups).
- `femm_report` returns `doubts` ("health check not run on this session", "no analytic estimate
  attached", "planar depth left at default", experiments with failing checks);
  `femm_compare_results` returns per-side `doubts`. `femm_status` returns `next_steps` (the 7-step
  loop).
- Server instructions: the loop, "ok:false is a stop sign", "no number before femm_health_check /
  an experiment health_summary", and "call femm_guide if your client did not load the skills".

Experiments:
- Pre-flight before the first solve: a requested group with no objects or an absent circuit is
  refused, listing the groups / circuits present (`femm_set_group` / `femm_add_circuit` hints).
  `rotate_groups` is checked only for `method='rotate'`.
- Sector detection from periodic / antiperiodic boundaries: `warnings` says the torque and flux are
  for the sector as drawn and flags slots / poles that are not whole per sector.
- `femm_experiment_inductance(currents=[...])`: L(I) rows (circuit, current, psi, L_secant,
  L_incremental by finite differences through 0 A) with csv / json / png.
- `femm_experiment_force_vs_position`: `position` documented as the displacement from the model as
  saved (gap = g0 + position). The model is re-solved at the restored position as before, but the
  session's `solved` flag is now truthful: results carry `left_solved`, and a failed final solve
  leaves `solved` false with `next: femm_solve(...)` and a warning (it used to be swallowed).
- Every experiment result adds `warnings` and `left_solved`.
- `experiments.py` split: inductance / AC sweep / parametric moved to `experiments_sweeps.py`
  (re-exported, pure move) and the checks to `preflight.py`.

Hints are the next action:
- `ToolInputError` without a hint, unrecognised FEMM errors and plain `ValueError`s are looked up in
  a message -> hint table (`tools/_common.MESSAGE_HINTS`). Experiment input errors are
  `ExperimentInputError` / `PreflightError` (still `ValueError`s) and come back as input errors with a
  hint, without a traceback. Timeout hints name the parameter and a value (2x the current timeout).

Vocabulary aligned with the jmag suite:
- `poles` (= 2p, preferred) accepted wherever `pole_pairs` was (`femm_experiment_back_emf`, `drive`,
  `dq`, `femm_estimate` formulas); exactly one must be given.
- `femm_estimate`: `carter_factor` alias of `carter_coefficient`. `femm_check_rule`:
  `power_balance_ac` (alias `power_balance`).

Estimates:
- `femm_estimate(name, args)` returns `{name, value, unit, formula, assumptions,
  expected_fea_tolerance_pct}` (tolerances from the project benchmarks, 10 % where none exists).
  `fem_value=` adds `verdict` PASS (<= tol) / CHECK (<= 2 tol) / FAIL with `diff_pct` and the
  FEM / formula ratio. `femm_estimate()` lists every formula with its arguments.
- `femm_circuit_results` docstring: `inductance_H` is the secant psi / I and is meaningless with
  magnets.

Packaging and meta tools:
- `femm_guide(topic, reference)`: the skills for clients that did not load them; the skills and
  `docs/femm5-facts.md` ship in the wheel (`femm_agent/skills`, `femm_agent/docs`); `femm_facts`
  reads the packaged copy first.
- `femm_doctor` and `python -m femm_agent --doctor [--json]` / `--version`: PASS / WARN / FAIL rows
  with a `fix` (install, executables, port 48015, mcp, numpy / matplotlib / pypdf, state and work
  dirs, skills, catalogs).
- One-time, opt-in GitHub star offer (was Unreleased): on first use `femm_status` / `femm_selftest`
  carry `first_run_note` and `first_run_action`; `femm_star_repo` ("star" via `gh` with a browser
  fallback, "open", "dismiss") records the answer in `state.json` under `FEMM_AGENT_HOME`.
Verified live on FEMM 5.0 build 20261101 (1144) and recorded in `docs/femm5-facts.md` /
`tests/live/test_live_v020.py`:
- WST torque (block integral 22) is about the origin, counter-clockwise positive.
- Planar conductor results (electrostatic charge, heat flux, current-flow current) are totals over
  the depth; unassigned outer edges are zero-normal-flux edges.
- `femm_build_benchmark("ccore", params={"gap": g})` sets each of the two gaps to g.
- `femm_experiment_force_vs_position` leaves the saved position solved (identical B and force).
- A single brace or missing key in a parametric template fails that case with KeyError; the other
  cases run. No command drift against the catalog on this build.
- 25 tool docstrings rewritten for LLM callers (units, examples, return keys, caveats);
  `femm_set_block_prop` / `femm_set_node_prop` document their full-replacement semantics.
- `tests/test_catalog_vs_pyfemm.py` finds pyFEMM through `FEMM_DIR`.

Plumbing:
- Version 0.2.0 in pyproject, `__init__` and the plugin manifest (`tests/test_versions.py`); README
  tool counts are checked against the registry.

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
