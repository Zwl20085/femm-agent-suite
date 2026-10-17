---
name: femm-troubleshooting
description: Diagnosing FEMM 5 problems through the femm MCP tools (femm_*) - every error message and hint the server produces, FEMM install and FEMM_DIR detection, engine sessions and ports ("already connected to another client", port in use, engine exits on disconnect), GUI vs headless behaviour (no screenshots headless), missing commands before a document or solution exists, save-before-analysis, meshing and "region has no material assigned" failures, unknown material names, zero air-gap results, wrong or suspicious numbers. Use when a femm tool returns ok false, FEMM cannot be found, a solve fails, results are zero, empty or implausible, or the user reports FEMM misbehaving.
---

# FEMM troubleshooting

## First moves

1. Read `error.message` and `error.hint` of the failing call. The hint is the next action.
2. `femm_session_list` - is the session alive, which physics/document is open, is it solved?
3. `femm_status` - install found? version? `tool_groups` loaded (and `skipped_groups`)?
4. Narrow it down: repeat the failing FEMM command alone with `femm_call` and read `warnings`.
5. `femm_journal(limit=30)` - exactly what was sent; refused lines are prefixed `#! ` with the error.
6. When several unrelated things fail: `femm_selftest`.

## Install and engine

| Symptom | Cause | Fix |
|---|---|---|
| `femm_status` shows `install.found: false`; tools answer "FEMM 5 not found" | FEMM not installed, or not in a default location | install FEMM 5 (https://www.femm.info/doku/doku.php?id=download5) or set `FEMM_DIR` to the bin folder holding `femm_headless` and restart the MCP server |
| default locations | | Windows `C:\femm-qt\bin` (also Program Files / LOCALAPPDATA `femm-qt\bin`), macOS `/Applications/femm_gui.app/Contents/MacOS`, Linux `~/.local/opt/femm-qt/bin`, `/opt/femm-qt/bin`, or `femm_headless` on PATH |
| `... exited immediately with code N` / `started but never listened on port N` | the engine crashed at start or another program holds the port | `femm_session_open(port=<free port>)`; check the FEMM install runs `femm_headless --version` |
| `port N is already in use` | a fixed `port` that another engine (or anything else) uses | omit `port` (a free one is picked) or choose another |
| `femm-qt is already connected to another client` | one FEMM engine serves exactly one TCP client | do not attach to an engine another client uses; open your own session |
| "The engine is gone. Call femm_session_open ..." | the engine exited (crash, `quit()`, or its client disconnected: headless engines exit within about 0.5 s of a disconnect) | the next call relaunches a fresh engine with **no document**: `femm_open` the last saved file; unsaved work is lost, so save often |
| a tool says "no document is open" right after you built a model | same as above: the session was relaunched | `femm_open(<saved path>)` |
| standalone pyFEMM: `Cannot find femm_headlessw executable` | pyFEMM finds the engine only through `FEMM_DIR` | set `FEMM_DIR`; `femm_export_pyfemm_script` writes it into the script |

## Commands and state

| Message | Meaning | Fix |
|---|---|---|
| `name 'mi_addnode' isn't defined` | no document of that physics exists yet (or a typo) | `femm_new_document` / `femm_open`; check spelling with `femm_api_search` |
| `name 'mo_getb' isn't defined` | `mo_getb`, `mo_geth`, ... are pyFEMM-only helpers | `femm_point_values` or `mo_getpointvalues` |
| `name 'mo_...' isn't defined` | post-processor commands exist only after a solution is loaded | `femm_solve` or `femm_load_solution` |
| "no solution is loaded in the post-processor" | a post tool before solving | `femm_solve` |
| `No current magnetics input in focus` (or output) | that document was closed | `femm_open` / `femm_new_document`; `femm_solve` |
| `File must be saved before analysis` / `before creating mesh` | raw analyse/mesh on an unsaved model | `femm_solve` / `femm_create_mesh` save for you; or `femm_save` |
| `No results file: <path>.ans` | `femm_load_solution` on a never-solved model | `femm_solve` |
| `No area selected for integration` | block selection toggled off (selected twice) or nothing selected | `femm_block_integral` handles selection; by hand, `femm_select_block(action="clear")` first |
| `No contour defined for makeplot` | no contour points | pass `contour=[[x1, y1], [x2, y2], ...]` to `femm_line_integral` / `femm_make_plot` |
| `Couldn't load "X" from the materials library` | name not in the FEMM 5 library (names changed since 4.2) | `femm_material_search("X")`, load the exact FEMM 5 name |
| `could not open` / `no such file` | wrong path | absolute paths with forward slashes; relative paths resolve in the session `work_dir` |
| `did not answer` / timeout | a long solve or a hung call | pass a larger `timeout` to `femm_solve`; check `femm_session_list` |

Full list of server hints and input-validation errors with their fixes: `references/errors.md`.

## Meshing and solving

| Message / symptom | Fix |
|---|---|
| `Solver failed: a region has no material assigned ... (exit code 10)` | a closed region has no block label: often the outer air, a hole, or the annulus of an air-gap element. `femm_geometry_summary`, then `femm_add_block_label` (`"<No Mesh>"` for holes and the AGE annulus) |
| mesh / triangulation error | overlapping segments, an unclosed outline, a label outside every region, near-coincident nodes (`femm-geometry` references/meshing.md) |
| very slow solve, huge element count | `femm_smartmesh("off")` plus explicit mesh sizes; symmetry; coarser far field |
| numbers jump between sweep steps | gap mesh too coarse (>= 3 layers), precision looser than 1e-8, or comparing against a geometry that was rotated back without re-solving |

## Results that look wrong

| Symptom | Likely cause |
|---|---|
| everything exactly 0 from `femm_gap_results` / `mo_gapintegral` | the boundary name is not an air-gap boundary of this model (FEMM does not raise) |
| torque about 1e-16 N*m with an air-gap element | WST block integral 22 does not see across the AGE: use `femm_gap_results` |
| `outside: true` from `femm_point_values` | the point is outside the mesh, or inside a `<No Mesh>` region such as the AGE annulus |
| results scale with a strange factor | depth not set (default 1 unit), or units mixed (MS/m vs S/m, MA/m^2 vs A/m^2, mm vs m in `femm_estimate`) |
| flux linkage 0 for a coil | coil labels have no circuit, or +N and -N turns of a series circuit cancel because both sides were given the same sign |
| inductance far above the formula | fringing and leakage (C-core: 7.47 mH FEM vs 4.81 mH formula is normal) |
| boundary health rule fails | air box too small; use 3-5x the device or `mi_makeABC` |
| W != W' in a "linear" model | a nonlinear B-H material is in use somewhere |
| AC losses do not match 1/2 Re(V conj I) | a conductor outside every circuit, or remember phasors are peak, not rms |
| old numbers after a change | the solution is not re-solved: `femm_solve` |

## GUI vs headless

| | headless (default) | GUI (`femm_session_open(name="gui", headless=False)`) |
|---|---|---|
| speed | fastest | window overhead |
| `femm_save_bitmap` | accepted, **writes no file** | writes PNG (1994x1330 RGBA in the test) or BMP |
| `femm_plot_field` | works | works |
| view commands (`mo_zoom`, `mo_showdensityplot`, ...) | registered; effect without a window unverified | work |
| exits on client disconnect | yes (verified) | unverified |

After a solve in the GUI, the post-processor window has the focus; `femm_save_bitmap(view="pre")`
switches back to the geometry. `mo_showdensityplot` with legend 0 and explicit 0/0 bounds draws a
legend that reads 0; the tool uses FEMM's defaults (legend -1) unless you pass bounds.
