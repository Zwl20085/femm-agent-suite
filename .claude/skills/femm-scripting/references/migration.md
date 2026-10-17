# Migrating FEMM 4.2 Lua and pyFEMM scripts to FEMM 5

## Decide first

| Situation | Route |
|---|---|
| run an old Lua script once, unchanged | `femm_run_lua(path)` |
| run an old pyFEMM script unchanged | `femm_run_script(path=..., mode="batch")` (pyFEMM scripts run inside FEMM: `import femm` resolves to a proxy, `openfemm`/`closefemm` are no-ops) - but see the helper list below |
| keep using the model and drive it from the agent | open the `.fem` (`femm_open`) and use the curated tools; port only the logic you need |
| hand the user a script of what the agent built | `femm_export_pyfemm_script` |

## Lua 4 -> MicroPython

| Lua 4 (FEMM 4.2) | MicroPython (FEMM 5) |
|---|---|
| `mi_addnode(0, 0)` | same call; commands keep their names (one underscore after the prefix) |
| `x = mo_getpointvalues(0, 0)` returns 14 values | `v = mo_getpointvalues(0, 0)`; index from 0: `v[1]` is B1 |
| `for k = 0, 10 do ... end` | `for k in range(11): ...` |
| `if a then ... elseif b then ... end` | `if a: ... elif b: ...` |
| `print(a, b)` | `print(a, b)` (tab separated, goes to the engine's stdout) |
| string concatenation `a .. b` | `a + b` or f-strings |
| `openfemm()` / `closefemm()` | not needed inside FEMM; outside use pyFEMM or this suite |
| `handle = openfile(name, "w"); write(handle, ...)` | `with open(name, "w") as f: f.write(...)` (`open` with one argument naming a .fem/.fee/.feh/.fec opens a FEMM document instead) |
| `mi_getmaterial("M-19 Steel")` | look the name up first: `femm_material_search("M-19 Steel")` -> `M-19 14 mil` |

## pyFEMM names the engine does not have (62)

They are Python-side conveniences in `femm.py`; over the wire they answer
`name '...' isn't defined`.

| pyFEMM helper | Replacement |
|---|---|
| `mo_getb`, `mo_geta`, `mo_geth`, `mo_getj`, `mo_getmu`, `mo_getpe`, `mo_getph`, `mo_getfill`, `mo_getconductivity`, `mo_getenergydensity` | `mo_getpointvalues(x, y)` and pick the value (order A, B1, B2, Sig, E, H1, H2, Je, Js, Mu1, Mu2, Pe, Ph, ff), or `femm_point_values` |
| `eo_getv`, `eo_getd`, `eo_gete`, `eo_getperm`, `eo_getenergydensity` | `eo_getpointvalues` (V, Dx, Dy, Ex, Ey, ex, ey, nrg) |
| `ho_gett`, `ho_getf`, `ho_getg`, `ho_getk` | `ho_getpointvalues` (T, Fx, Fy, Gx, Gy, kx, ky) |
| `co_getv`, `co_getj`, `co_getk`, `co_gete` | `co_getpointvalues` (15 values) |
| `*_hidenames` | `*_shownames(0)` |
| `*_snapgridon` / `*_snapgridoff`, `xo_snapgrid(flag)` | `*_gridsnap("on")` / `*_gridsnap("off")` |
| `xo_smoothon` / `xo_smoothoff` | `xo_smooth("on")` / `xo_smooth("off")` |
| `mi_setcurrent`, `mi_addbhpoints`, `hi_addtkpoints` | `mi_modifycircprop(name, 1, I)`; loop over `mi_addbhpoint` / `hi_addtkpoint` (or `femm_material_add_bh`) |

Also gone: `*_getnodeindex`, `*_getelementindex` (removed 2026-08-29).

## Other behaviour changes to expect

- Save before analysis: `mi_saveas(path)` then `mi_analyze(1)`, else `File must be saved before
  analysis`.
- `mi_createmesh()` returns nothing over IPC; use `mo_numelements()` after a solve.
- `mi_savebitmap` / `mo_savebitmap` write files only in `femm_gui`; `mo_savemetafile` writes nothing.
- `mo_selectblock(x, y)` toggles; selecting the same block twice deselects it, and
  `mo_blockintegral` then raises `No area selected for integration`. Call `mo_clearblock()` first.
- After `mi_loadsolution` the post-processor has focus: `mi_savebitmap` captures the solution plot
  until `mi_setfocus("<document stem>")`.
- `mi_getprobleminfo()` reports depth in problem units, `mo_getprobleminfo()` in metres.
- Meshes come from `tangle`, not Triangle: element counts and exact numbers differ from 4.2 runs.
- Standalone pyFEMM (outside FEMM) needs `FEMM_DIR` set to the bin folder; it does not search the
  default install folders.
- pyFEMM's `callfemm` replaces every `i`/`I` in a reply token with `1j` before `eval`, which mangles
  string results containing the letter i (paths, titles). This suite parses replies itself.
