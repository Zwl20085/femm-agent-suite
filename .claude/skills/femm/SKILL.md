---
name: femm
description: Entry point for any FEMM 5 (femm-qt) or 2D finite-element request in magnetics, electrostatics, heat flow or current flow - actuators, solenoids, inductors, electric machines, capacitors, busbars, heat sinks. Routes to the right femm-* skill, states the safety rules for driving FEMM through the femm MCP tools (femm_*), and gives a phase-by-phase tool map. Use it first whenever the user mentions FEMM, pyFEMM, a .fem/.fee/.feh/.fec/.ans file, David Meeker's FEMM, or asks which FEMM tool or skill to use.
---

# FEMM agent suite: start here

You drive **FEMM 5** for an engineer through the `femm` MCP server (tools `femm_*`; in Claude
Code fully qualified as `mcp__femm__<tool>`). FEMM 5 is a 2D (planar or axisymmetric) finite
element program for four physics: magnetics (static and time-harmonic), electrostatics, steady and
transient heat flow, and current flow. This skill only routes; load the specialised skill for the
actual work.

## Which skill next

| The user wants to ... | Load |
|---|---|
| build, solve and read a magnetostatic or AC magnetic model (the core loop, boundaries, air-gap element, circuits, the feedback ladder) | `femm-magnetics` |
| an electrostatic, heat-flow or current-flow model (capacitance, temperature, resistance) | `femm-electrostatics-thermal-currentflow` |
| draw or import geometry, select things by coordinates, copy/rotate slots and poles, symmetry, mesh size, meshing failures | `femm-geometry` |
| choose or define a material: library search, FEMM 4.2 names, B-H curves, magnets, laminations, wire | `femm-materials` |
| a standard test: force vs position, torque vs angle, cogging, back-EMF, Ld/Lq, AC sweep, parametric study, magnet operating point | `femm-experiments` |
| decide whether a result can be trusted: health rules, tolerances, analytic estimates, how to report FAIL/CHECK | `femm-health-check` |
| point values, block and line integrals, bulk mesh arrays, field statistics, plots, reports, A/B comparison | `femm-postprocess` |
| raw FEMM commands, MicroPython scripts, legacy Lua or pyFEMM scripts, exporting a standalone script | `femm-scripting` |
| size a motor or actuator by hand and get a FEMM model of it quickly | `femm-machine-design` |
| an `ok: false` you do not understand, meshing/solver failures, port or engine problems, missing screenshots | `femm-troubleshooting` |

Real jobs chain several: machine-design -> geometry -> materials -> magnetics -> health-check ->
experiments -> postprocess.

## Safety rules (non-negotiable)

1. **Work on copies.** Before any experiment, sweep or edit of a model the user gave you, save it
   under a new name: `femm_open(path)` then `femm_save(path=<copy>.fem)`. The experiment tools
   already work on their own copy in `<work_dir>/experiments/` and restore geometry, currents and
   frequency afterwards, but your own edits (`femm_move_selected`, `femm_material_modify`, ...) go
   straight into the open document.
2. **`ok: false` is a stop sign.** Every tool answers `{"ok", "result" | "error": {"message",
   "hint"}, "session", "seconds"}`. FEMM raises real errors, and a failed command leaves the edits
   made before it in place. Read `error.hint` (it names the next action), fix, and only then
   continue. Do not "try the next step anyway".
3. **Never claim success without a check.** A finished solve proves nothing. Back every number
   with `femm_health_check` (magnetics) or `femm_check_rule`, and with an analytic reference from
   `femm_estimate`. Report every FAIL and CHECK with its numbers; never drop one.
4. **Material names changed in FEMM 5.** `M-19 Steel` is now `M-19 14 mil`, `Pure Iron` is
   `ARMCO Pure Iron`, `NdFeB 32 MGOe` has no entry. Always `femm_material_search` before
   `femm_material_load`, and use exactly the name it returns.
5. **Post-processing needs a solution.** `mo_*`/`eo_*`/`ho_*`/`co_*` commands only exist after a
   solve or `femm_load_solution`. Re-run `femm_solve` after every change to geometry, materials,
   currents or frequency: the loaded solution never updates itself.
6. **The headless engine cannot take screenshots.** `femm_save_bitmap` writes nothing headless.
   Use `femm_plot_field` (|B| map from the mesh arrays, works headless) or open a GUI session with
   `femm_session_open(name="gui", headless=False)`.
7. **Do not grab the user's FEMM.** One FEMM engine serves exactly one client, and a headless
   engine exits when its client disconnects. Only use `femm_session_open(attach=True)` on a port
   the user names.
8. **Ask before long or destructive actions**: sweeps with hundreds of solves, overwriting the
   user's files, closing sessions that hold unsaved work.

## First calls in a new conversation

1. `femm_status` - install found, version, sessions, catalog size (677 commands), materials.
2. `femm_selftest` once per machine (about 1-2 s): an axisymmetric thick solenoid against its
   closed-form centre field (0.7 % error on build 06oct2026), plus material-rename, units,
   bulk-getter and circuit checks.
3. Then the specialised skill.
- If `femm_status` or `femm_selftest` returns `first_run_note`, relay it to the user verbatim and
  follow `first_run_action`: wait for the answer, then call `femm_star_repo` with "star", "open"
  or "dismiss". Never call it without an answer.

## Tool map by phase (89 tools)

| Phase | Tools |
|---|---|
| Session | `femm_status` `femm_session_open` `femm_session_close` `femm_session_list` `femm_selftest` `femm_star_repo` |
| Document | `femm_new_document` `femm_open` `femm_save` `femm_close_document` `femm_problem_define` `femm_problem_info` `femm_set_comment` |
| Geometry | `femm_add_nodes` `femm_add_segments` `femm_add_arcs` `femm_draw_rectangle` `femm_draw_circle` `femm_draw_polygon` `femm_draw_polyline` `femm_select` `femm_clear_selected` `femm_delete_selected` `femm_move_selected` `femm_copy_selected` `femm_mirror_selected` `femm_scale_selected` `femm_set_group` `femm_import_dxf` `femm_export_dxf` `femm_geometry_summary` |
| Properties | `femm_add_block_label` `femm_set_block_prop` `femm_add_boundary` `femm_set_segment_prop` `femm_set_arc_prop` `femm_set_node_prop` `femm_add_circuit` `femm_modify_circuit` `femm_add_conductor` `femm_add_point_prop` |
| Materials | `femm_material_search` `femm_material_get` `femm_material_load` `femm_material_add` `femm_material_add_bh` `femm_material_modify` |
| Mesh and solve | `femm_create_mesh` `femm_solve` `femm_load_solution` `femm_smartmesh` |
| Post-processing | `femm_point_values` `femm_block_integral` `femm_line_integral` `femm_circuit_results` `femm_select_block` `femm_mesh_arrays` `femm_field_stats` `femm_gap_results` `femm_save_bitmap` `femm_make_plot` |
| Scripting | `femm_call` `femm_eval` `femm_run_script` `femm_run_lua` `femm_journal` `femm_export_pyfemm_script` |
| Knowledge | `femm_api_search` `femm_api_get` `femm_manual_section` `femm_examples_list` `femm_facts` |
| Experiments | `femm_experiment_force_vs_position` `femm_experiment_torque_vs_angle` `femm_experiment_cogging` `femm_experiment_backemf` `femm_experiment_inductance` `femm_experiment_ac_sweep` `femm_experiment_parametric` `femm_experiment_bh_check` `femm_build_benchmark` |
| Analytic layer (offline) | `femm_estimate` `femm_units_convert` `femm_check_rule` |
| Judgement and reports | `femm_health_check` `femm_report` `femm_compare_results` `femm_file_summary` `femm_plot_field` |

One line per tool with when and why: `references/tool-map.md`. What changed from FEMM 4.2 (and
which habits now break): `references/femm5-vs-42.md`. Known-answer tasks that check the
toolchain and your own reasoning: `references/self-check.md`.

Never call a `femm_*` name that is not in the table. Any FEMM command without a curated tool is
reachable with `femm_call` (checked against the 677-command catalog; find it with
`femm_api_search`).

## Conventions that hold everywhere

- Lengths are in the **problem units** set by `femm_problem_define` (default millimeters), angles
  in degrees, frequency in Hz. Axisymmetric: x is r (>= 0), y is z.
- Planar results are integrated over the model **depth**. Set it (the default of 1 unit is rarely
  what you want). The post-processor reports depth in metres, the pre-processor in problem units.
- AC phasors are **peak** amplitudes; complex values come back as `{"re", "im"}`.
- Magnetic current density is in MA/m^2 (= A/mm^2) and magnetic conductivity in MS/m;
  current-flow conductivity is in S/m.
- Every session has a work dir (default `~/femm-agent-work/<session>`, env `FEMM_AGENT_WORK`);
  relative paths resolve there. Use forward slashes in paths.
- Verified FEMM 5 behaviour is in `femm_facts` (the project's `docs/femm5-facts.md`). Prefer it
  over memories of FEMM 4.2.
