# Changelog

## 0.2.1 (2026-11-09)

Closes the last open item of 0.2.0 (sector models), measured on FEMM 5.0 build 20261101 (1144).

- `femm_build_benchmark("spm", params={"sector": N})` (`benchmarks_sector.py`): 1/N of the SPM
  benchmark with one periodic / antiperiodic boundary per region on each cut line and an
  (anti)periodic air-gap element; refuses `rotor_method="rotate"` (rotate-and-remesh cannot keep
  the cut lines matched) and sectors that do not divide the slots, poles or winding.
- Measured scale rule (full machine vs N = 2 and N = 4, 12-slot 4-pole SPM): flux linkage, EMF,
  coenergy, energy, circuit resistance (DC and 50 Hz) and coil resistive loss of a sector are x N
  within 0.05 %, inductance x N within 0.12 %; the air-gap element torque (`mo_gapintegral`) of a
  sector is already the full-machine torque (within 0.05 %). Iron losses: x N expected,
  unmeasured. The 0.2.0 warning
  ("torque and flux linkage are for the sector as drawn; multiply by N") was wrong for the torque.
- Experiments on a 1/N sector add `full_machine` {factor, rule, summary, notes} (rows and summary
  stay as drawn). Virtual-work and dq torques are put on the full-machine footing of the gap torque,
  so `mean_torque_vs_dq`, `torque_vs_virtual_work`, `torque_fem_vs_dq` and `psi_pm_vs_analytic` no
  longer fail on sectors by the factor N; with WST torque on a sector the dq checks are not
  applicable. `inductance` and `ac_sweep` now detect sectors too.
- Pre-flight refusal no longer rewrites the session document: when the file on disk equals FEMM's
  state, FEMM is pointed back by close / re-open / reload instead of `mi_saveas` (it still saves
  when there are unsaved edits).
- Settled live: `ei_/hi_/ci_getprobleminfo` return `[type, depth, unit]` (no frequency, also for
  current flow; `data/commands.json` return text corrected), `mo_makeplot` returns the number of
  points, the 4.2 material-rename error path. docs/femm5-facts.md has no open questions left from
  the audit.
- Tests: `tests/test_sector.py` (fixture geometry from FEMM-written sector files, scale logic,
  builder commands, refusal path), `tests/live/test_live_sector.py` (sector x N vs full machine).

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

Review fixes (before release):
- A requested circuit with no coil labels (or zero turns) is refused before solving; default
  circuit lists skip such circuits with a warning. Renaming a circuit with mi_modifycircprop drops
  its label links on FEMM 5 (verified). `energy_consistency` fails when a current flows but the
  energy and 1/2 sum I psi are both ~0.
- `L_incremental` uses central differences inside and first-order one-sided ends (no negative
  slopes on sparse grids); L(I) rows are sorted by current; a warning flags increments <= 0 or
  > 1.5 x L_secant.
- A failed experiment leaves the session unsolved and unchecked; one refused by pre-flight keeps
  its state.
- `experiments_core.py` holds Ops / Run / helpers, so `experiments_sweeps` imports on its own.
- `poles` / `pole_pairs` both accepted by `build_spm` (default 4 poles), `cogging` /
  `femm_experiment_cogging` and `femm_estimate("cogging_period_deg")`.
- `femm_estimate(..., session=)` records the comparison; `femm_report` counts it as the analytic
  reference and lists CHECK / FAIL estimates and a FAIL health verdict among its doubts.
- Verdict bands get a 1e-9 relative slack (a difference of exactly the tolerance is PASS).
- WST force / torque groups must hold a block label; rotate / move groups may be geometry only.
- Sector detection requires radial periodic segments (a linear periodic model is not a sector).
- `force_vs_position` restores exactly the steps taken (and the offset) after a failure; steps < 1
  is refused.
- examples/README.md and run_spm.py use the new names; test_tool_names also scans CLAUDE.md and
  examples/*.md.

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
