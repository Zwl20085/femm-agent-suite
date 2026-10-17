# Every error hint the server gives

## FEMM errors translated by the server (`hint_for` in `tools/_common.py`)

When FEMM answers `error:<message>`, the tool returns `ok: false` with the message, the command that
failed, and one of these hints (first match wins):

| FEMM / link message contains | Hint (next action) |
|---|---|
| link error, "not found" | Install FEMM 5 from https://www.femm.info or set FEMM_DIR to its bin folder, then call femm_status. |
| any other link error | The engine is gone. Call femm_session_open to start a new one (unsaved work is lost). |
| `materials library` | Material name not in the FEMM 5 library (names changed since 4.2). Call femm_material_search with a partial name. |
| `name '...' isn't defined` / `not defined`, no document | No document is open. Call femm_new_document or femm_open first. |
| same, post-processor name or not solved | Postprocessor commands exist only after a solution is loaded. Call femm_solve (or femm_load_solution) first. |
| same, otherwise | Check the command name with femm_api_search. |
| `input in focus` / `output in focus` | That document was closed. Call femm_new_document or femm_open (pre-processor) or femm_solve/femm_load_solution (post-processor). |
| `no results file` | This model has no solution file yet. Call femm_solve. |
| `must be saved` | Save first with femm_save(path) (femm_solve and femm_create_mesh save automatically). |
| `no contour` | Pass contour points to femm_line_integral / femm_make_plot (at least two [x, y] points). |
| `no document` | Call femm_new_document(physics=...) or femm_open(path) first. |
| `could not open` / `no such file` / `cannot open` | Check the path (use forward slashes, absolute paths) and that the file was saved with femm_save. |
| `no material assigned` | A closed region has no block label. Add one with femm_add_block_label (use material '<No Mesh>' for holes and for the annulus of an air-gap element); femm_geometry_summary lists label counts. |
| `mesh` / `triang` / `tangle` | Meshing failed: look for overlapping segments, unclosed regions or labels outside regions (femm_geometry_summary helps). |
| `did not answer` / `timeout` | The call timed out. For long solves pass a larger timeout to femm_solve, or check femm_session_list. |
| anything else | Read the message; if the command signature is in doubt, call femm_api_search(name). |

An unexpected Python exception inside a tool still comes back as `ok: false` with
`TypeName: message`, a short `trace`, and "Check the argument types and units in the tool
description." The server never crashes on a bad call.

## FEMM messages observed live (build 06oct2026)

| Message | Where it comes from |
|---|---|
| `name 'mi_addnode' isn't defined` | no document yet, or a typo |
| `name 'mo_getb' isn't defined` | pyFEMM-only helper |
| `Couldn't load "NoSuchMat" from the materials library` | `mi_getmaterial` with an unknown name |
| `File must be saved before analysis` | `mi_analyze` on an unsaved model |
| `File must be saved before creating mesh` | `mi_createmesh` on an unsaved model |
| `Solver failed: a region has no material assigned ... (exit code 10)` | a region without a block label |
| `No results file: <path>.ans` | `mi_loadsolution` without a solution |
| `No current magnetics input in focus` | any `mi_*` after `mi_close()` |
| `No area selected for integration` | `mo_blockintegral` with nothing selected (block selection toggles) |
| `No contour defined for makeplot` | `mo_makeplot` without contour points |
| `femm-qt is already connected to another client` | a second TCP client on the same engine |
| `Script error: <message>` (stderr, exit code 1) | `femm_headless -run` script failure (batch mode) |

Not errors although they look like failures: `xo_savebitmap` in a headless engine (success, no
file), any air-gap command with an unknown boundary name (zeros), `mo_getpointvalues` outside the
mesh (empty reply -> `outside: true`).

## Input errors raised by the tools before FEMM is called

| Tool(s) | Message | Fix |
|---|---|---|
| any tool needing a model | no document is open in this session | `femm_new_document(physics=...)` or `femm_open(path)` |
| post-processing tools | no solution is loaded in the post-processor | `femm_solve` (or `femm_load_solution`) |
| complex inputs | cannot read ... as a number or complex | a number, `[re, im]` or `"1+2j"` |
| `femm_new_document`, `femm_material_search` | unknown physics | magnetics, electrostatics, heatflow, currentflow |
| `femm_problem_define` | unknown length unit / problem_type must be planar or axi | inches, millimeters, centimeters, mils, meters, micrometers (aliases mm, cm, m, in, um) |
| `femm_open` | file not found / unknown FEMM file type | relative paths resolve in the session work_dir; .fem .fee .feh .fec .ans .res .anh .anc |
| geometry tools | point must be [x, y]; segment must be ...; arc must be [x1,y1,x2,y2,angle,maxseg]; need at least 2 points; radius must be > 0 | pass the shape documented in the tool |
| `femm_select` | unknown selection kind; kind=group needs group; rectangle must be [x1, y1, x2, y2]; circle must be [cx, cy, R] | |
| move/copy/mirror/scale | unknown entity kind | nodes, segments, labels, arcs or group |
| `femm_delete_selected` | unknown kind | all, nodes, segments, arcs, labels |
| `femm_import_dxf` | DXF not found | an existing .dxf |
| `femm_add_boundary` | unknown boundary type / BdryFormat invalid for this physics | the per-physics list in the hint |
| electrostatics/heat values | must be real for this physics | a plain number |
| `femm_add_circuit` / `femm_add_conductor` | circuits are magnetics-only / magnetics uses circuits / unknown fixed | conductors for ES/heat/current; circuits for magnetics |
| `femm_modify_circuit` | nothing to change | pass current, series or new_name |
| `femm_material_get` | not in the library | "Did you mean ..." with the nearest names |
| `femm_material_add` / `femm_material_add_bh` | bh_points is magnetics-only / no nonlinear material curves | B-H for magnetics, T-k for heat flow only |
| `femm_material_modify` | unknown property | the key list for the physics |
| `femm_smartmesh` | state must be on/off/default; 'default' only applies to scope='global'; no document open | |
| `femm_block_integral` | nothing selected | points inside the blocks or `group=[n]` |
| `femm_line_integral`, `femm_make_plot` | a contour needs at least 2 points | |
| `femm_mesh_arrays` | not available for this physics | nodes, elements, plus b/a, v/d, t/f, v/j |
| `femm_mesh_arrays`, `femm_field_stats` | returned N values, not a multiple of ...; field values for ... elements | unexpected bulk layout: report it |
| `femm_field_stats` | bad region / unknown region / no elements in region | `'all'`, `'group:3'`, `'group:1,2'`; check the label group numbers |
| `femm_gap_results` | air-gap elements are magnetics-only | `femm_line_integral` for other physics |
| `femm_save_bitmap` | no solution loaded; give lower and upper with an explicit plot_type; FEMM wrote no image | solve; pass bounds or leave `plot_type` unset; open a GUI session (`headless=False`), re-open and solve there |
| `femm_call` | FEMM error + "Catalog warnings: ..." | the warnings usually name the wrong argument |
| `femm_eval` | expression must be a single line | `femm_run_script(code=...)` |
| `femm_run_script` | script not found; give code or path; result_var must be an identifier; batch script exceeded N s; unknown mode | |
| `femm_run_lua` | script not found; femm-lua launcher not found in the FEMM bin folder | port the script to MicroPython |
| experiment tools | experiments need a magnetics model / no document is open | open or create a magnetics model, or `femm_build_benchmark` |
| experiment tools (as `ValueError: ...`) | method='age' needs gap_boundary; boundary ... is not a (anti)periodic air gap (BdryFormat 6/7); no boundary named ... in the model; method must be 'rotate' or 'age'; dx and dy cannot both be zero; no circuits in the model; setup command ... not allowed (pre-processor commands only); element count mismatch between the .ans file and the live mesh | pass the AGE name exactly as defined; use a BdryFormat 6/7 boundary; give a nonzero step; add circuits; use `mi_`/`ei_`/`hi_`/`ci_` setup commands; re-solve |
| `femm_build_benchmark` | unknown benchmark | ccore, coilgun, round_wire, spm |
| `femm_health_check` | covers magnetics models | other physics: `femm_check_rule` |
| `femm_file_summary` | no such file | an absolute path |
| `femm_estimate`, `femm_units_convert`, `femm_check_rule` | unknown estimate / conversion / rule; argument errors | call with no name, or `"list"`, to see names and arguments |
| `femm_manual_section` | manual not found; cannot extract (no pdftotext or pypdf); not found in the manual | `femm_api_search`; `pip install pypdf`; a shorter keyword or a section number |
| `femm_api_get` | not in the catalog | the closest names are in the hint |
| `femm_facts` | docs/femm5-facts.md not found | `femm_manual_section` / `femm_api_get` |
