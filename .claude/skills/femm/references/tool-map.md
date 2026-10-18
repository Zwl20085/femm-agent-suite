# Tool map: all 89 femm_* tools

Every tool takes `session` (default `"main"`) unless noted as offline, and returns the envelope
`{"ok", "result" | "error": {"message", "hint"}, "session", "seconds"}`. "Needs document" means a
model must be open (`femm_new_document` / `femm_open`); "needs solution" means `femm_solve` or
`femm_load_solution` ran since the last change.

## Session (6)

| Tool | When / why |
|---|---|
| `femm_status` | First call: install path, version, sessions, work dir, catalog and material counts, loaded tool groups. Offline-safe. |
| `femm_session_open` | Only to choose options: `headless=False` for a GUI (screenshots), a fixed `port`, a `work_dir`, or `attach=True` to an engine already listening. Other tools open "main" lazily. |
| `femm_session_close` | Quit one engine (unsaved work is lost: `femm_save` first). |
| `femm_session_list` | Port, pid, physics, document, solved flag, call/error counts of every session. Use when unsure what state a session is in. |
| `femm_selftest` | Known-answer check of the whole toolchain in a separate "selftest" session (thick solenoid, about 1-2 s). Run once per machine and after any install change. |
| `femm_star_repo` | One-time GitHub star offer: call only after the user answered the `first_run_note` from `femm_status` / `femm_selftest` ("star", "open" or "dismiss"). Asked once per machine. |

## Document (7)

| Tool | When / why |
|---|---|
| `femm_new_document` | New empty model: `physics` = magnetics, electrostatics, heatflow or currentflow. Defines the `mi_`/`ei_`/`hi_`/`ci_` commands. |
| `femm_open` | Open a model (.fem/.fee/.feh/.fec) or a solution (.ans/.res/.anh/.anc; post-processing tools then work directly). |
| `femm_save` | Save, or save a copy (`path`). Do this before experimenting on a user's model. |
| `femm_close_document` | Close pre- and post-processor of the current document; the engine keeps running. |
| `femm_problem_define` | Units, planar/axi, depth, frequency, precision, min angle (and AC solver, transient heat inputs). Writes the right `xi_probdef` argument order for each physics. |
| `femm_problem_info` | What FEMM reports back: problem type, frequency, depth, unit, bounding box, node/element counts when solved. |
| `femm_set_comment` | Store a one-line description in the model file. |

## Geometry (18) - all need a document

| Tool | When / why |
|---|---|
| `femm_add_nodes` | Single nodes; usually prefer the shape tools. |
| `femm_add_segments` | Straight segments `[[x1,y1],[x2,y2]]`; end nodes are created; crossings are split by FEMM. |
| `femm_add_arcs` | Arcs `[x1,y1,x2,y2,angle,maxseg]`, counter-clockwise, angle <= 180, maxseg in degrees (<= 1 in air gaps). |
| `femm_draw_rectangle` | Axis-aligned rectangle (4 nodes, 4 segments). |
| `femm_draw_circle` | Full circle as four 90-degree arcs. |
| `femm_draw_polygon` | Closed (or open) polygon; returns the vertex centroid (a label position only if convex). |
| `femm_draw_polyline` | Open chain of segments. |
| `femm_select` | Select nearest nodes/segments/arcs/labels to points, a whole group, or everything in a rectangle/circle; clears first by default. |
| `femm_clear_selected` | Deselect everything in the pre-processor. |
| `femm_delete_selected` | Delete the selection (all, nodes, segments, arcs, labels). |
| `femm_move_selected` | Translate or rotate the selection; pass `entities` ('group' after a group select). |
| `femm_copy_selected` | Copy the selection N times by translation or rotation: one slot -> all slots. |
| `femm_mirror_selected` | Mirror copy about a line (original stays). |
| `femm_scale_selected` | Scale the selection about a point. |
| `femm_set_group` | Put the selection in a group number (moving parts, integrals, per-material stats). |
| `femm_import_dxf` | Read a DXF into the model (optional node-merge tolerance); then add labels. |
| `femm_export_dxf` | Write the geometry to DXF. |
| `femm_geometry_summary` | Saves the model and reads counts of nodes, segments, arcs, labels, holes and the defined materials/boundaries/circuits from the file. The check before meshing. |

## Properties (10) - all need a document

| Tool | When / why |
|---|---|
| `femm_add_block_label` | One label per closed region: material (or `<No Mesh>`), mesh size, and in magnetics circuit, turns, magnetisation direction; group. |
| `femm_set_block_prop` | Change the label nearest a point (swap material or circuit between solves). |
| `femm_add_boundary` | Define a boundary for the current physics (magnetics 12-argument form incl. periodic air gap) and optionally assign it to segments/arcs by points on them. |
| `femm_set_segment_prop` | Boundary name, mesh size, hide flag, group, conductor of the segments nearest the points. |
| `femm_set_arc_prop` | Discretisation, boundary, hide, group, conductor of the arcs nearest the points. |
| `femm_set_node_prop` | Point property, group, conductor of the nodes nearest the points. |
| `femm_add_circuit` | Magnetics circuit with a current (peak at AC; complex allowed), series (stranded, turns on labels) or parallel (solid conductor). |
| `femm_modify_circuit` | Change a circuit's real current, series/parallel flag or name; re-solve afterwards. |
| `femm_add_conductor` | Electrostatics / heat / current flow: fixed voltage or charge, temperature or heat, voltage or current. |
| `femm_add_point_prop` | Nodal property (prescribed potential and point source) for any physics, optionally assigned to nodes. |

## Materials (6)

| Tool | When / why |
|---|---|
| `femm_material_search` | Offline fuzzy search of the FEMM 5 libraries; maps FEMM 4.2 names. Always before loading. |
| `femm_material_get` | Offline: full record (Mu_x, H_c, Sigma MS/m, d_lam mm, LamFill, B-H points ...). Check what you are about to use. |
| `femm_material_load` | Copy library materials into the model; reports suggestions on a miss, optional fallback with a `renamed` map. Needs document. |
| `femm_material_add` | Custom material for the current physics (all 13 magnetic properties, or eps / k / sigma sets). Needs document. |
| `femm_material_add_bh` | Nonlinear B-H (magnetics) or T-k (heat) curve for a material already in the model. |
| `femm_material_modify` | Change properties of a material in the model by key name; re-solve afterwards. |

## Mesh and solve (4) - all need a document

| Tool | When / why |
|---|---|
| `femm_create_mesh` | Mesh without solving (saves first) to see that meshing succeeds. Returns no element count in FEMM 5. |
| `femm_solve` | Save + analyse + load the solution in one call; returns solve time and node/element counts. Re-run after every change. |
| `femm_load_solution` | Load an existing solution without re-solving. |
| `femm_smartmesh` | Smart mesh on/off per document or globally; off cut the SPM benchmark from 33.5k to 9.7k elements. |

## Post-processing (10) - need a solution (except as noted)

| Tool | When / why |
|---|---|
| `femm_point_values` | Labelled field values at points (14 magnetic values, 8 / 7 / 15 for the other physics) plus the magnitude. |
| `femm_block_integral` | Select blocks by points or groups and evaluate integral codes (energy, losses, forces, torque ...). |
| `femm_line_integral` | Integrals along a contour (flux, MMF, force, torque; charge, heat flow, current). |
| `femm_circuit_results` | Circuit current, voltage, flux linkage with L and R or Z; conductor voltage/charge, temperature/heat, voltage/current. |
| `femm_select_block` | Block selection for hand-rolled `femm_call('mo_blockintegral', ...)` workflows. |
| `femm_mesh_arrays` | Dump nodes, elements and fields to .npz/.csv; returns path, shape and column stats, never raw arrays. |
| `femm_field_stats` | Area-weighted field-magnitude statistics (B, D, F or J), saturated fraction, per group. Fast, no file. |
| `femm_gap_results` | Air-gap element results: torque, force, energy, Br/Bt distribution (CSV) and harmonics. Warns when everything is zero (unknown boundary name). |
| `femm_save_bitmap` | Screenshot of the pre- or post-processor view. GUI session only (headless writes no file). Needs document. |
| `femm_make_plot` | Sample a quantity along a contour into a text file with stats (works headless). |

## Scripting (6)

| Tool | When / why |
|---|---|
| `femm_call` | Any FEMM command by name with positional args, checked against the catalog (warnings for wrong arity, pyFEMM-only names). |
| `femm_eval` | One line of MicroPython inside FEMM, value returned; variables persist. |
| `femm_run_script` | Multi-line MicroPython: in-process (`exec(open(p).read())`, sees the session's model, returns a `result` variable) or batch (`femm_headless -run`, separate engine). |
| `femm_run_lua` | Run an unchanged FEMM 4.2 Lua 4 script with the bundled `femm-lua` (own engine). Offline from sessions. |
| `femm_journal` | The exact lines this session sent (refused ones marked `#!`); optionally saved as a replayable script. |
| `femm_export_pyfemm_script` | Turn the journal into a standalone pyFEMM script the user can re-run without the agent. |

## Knowledge (5) - offline

| Tool | When / why |
|---|---|
| `femm_api_search` | Find FEMM commands by words or name, filter by physics and pre/post. |
| `femm_api_get` | Full catalog entry: arguments, return value, integer code tables, notes. |
| `femm_manual_section` | Read the installed FEMM 5 manual by section number, heading or keyword. |
| `femm_examples_list` | Example models and scripts shipped with FEMM 5, with headers. |
| `femm_facts` | The project's verified FEMM 5 behaviour, optionally filtered by a word. Read before trusting FEMM 4.2 habits. |

## Experiments (9) - magnetics, need a document

| Tool | When / why |
|---|---|
| `femm_experiment_force_vs_position` | Move groups step by step, WST force, coenergy and flux linkage per step; checked against virtual work. Actuators, plungers, coilguns. |
| `femm_experiment_torque_vs_angle` | Torque vs rotor angle by rotate-and-remesh or air-gap element; optional dq drive with a mean-torque check. |
| `femm_experiment_cogging` | Zero-current torque over cogging periods with harmonics; zero-mean, periodicity and virtual-work checks. |
| `femm_experiment_backemf` | Open-circuit flux linkage over one electrical period -> EMF, fundamental, THD, line-line EMF, Ke. |
| `femm_experiment_inductance` | Self/mutual inductance matrix by flux-linkage differences, or psi_pm, Ld, Lq and dq torque at one rotor position. |
| `femm_experiment_ac_sweep` | Frequency sweep: Z, R(f), L(f) and losses, with the AC power-balance check. |
| `femm_experiment_parametric` | Generic sweep: per case apply pre-processor commands or a template, solve, collect point/block/circuit/gap/line/expression outputs. |
| `femm_experiment_bh_check` | Magnet operating points (B_m, H_m, Pc, B_m/Br) with a demagnetisation flag. |
| `femm_build_benchmark` | Build a validated model from scratch: ccore, coilgun, spm (rotate or age), round_wire; returns groups, circuits and analytic estimates. Needs no document. |

## Analytic layer (3) - offline

| Tool | When / why |
|---|---|
| `femm_estimate` | 25 closed-form references (fields, inductance, Maxwell force, Carter, PM load line, SPM flux, dq torque, capacitance, resistance, skin depth, Bessel wire impedance). |
| `femm_units_convert` | Lengths in FEMM units, rpm, AWG/IEC diameters, gauss/oersted, magnet grade (MGOe) to Br/Hc. |
| `femm_check_rule` | Run one pure health rule on numbers you already have (energy, power balance, force consistency, ...). The route for non-magnetic physics. |

## Judgement and reports (5)

| Tool | When / why |
|---|---|
| `femm_health_check` | Physics invariants on the loaded magnetics solution: mesh, precision, energy, saturation, boundary, torque, force, AC power, flux, magnets. Needs solution. |
| `femm_report` | report.md + report.json + figures from the model, health check, B-magnitude map and this session's experiments. |
| `femm_compare_results` | A/B comparison of two experiment results with a relative tolerance (mesh refinement, rotate vs air-gap element, two designs). Offline. |
| `femm_file_summary` | Parse any FEMM model or solution file offline: problem, materials, boundaries, circuits, groups, magnets; optional mesh .npz. |
| `femm_plot_field` | Flux-density (B magnitude) colour map PNG from the bulk arrays; the headless substitute for a screenshot. Needs solution. |
