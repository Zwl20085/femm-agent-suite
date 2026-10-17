---
name: femm-postprocess
description: Reading FEMM 5 results through the femm MCP tools (femm_*) - point values with the 14-value magnetic layout (and 8 / 7 / 15 for electrostatics, heat, current flow), block integral and line integral codes (energy, coenergy, losses, Lorentz and weighted-stress-tensor force and torque), circuit and conductor results, bulk mesh arrays and area-weighted field statistics, air-gap element results, contour plots, field maps, screenshots, reports and A/B comparison of results. Use when the user wants B, H, J, flux, flux linkage, inductance, force, torque, losses, temperature, charge or current out of a solved FEMM model, a plot or report of it, or a comparison between two runs.
---

# FEMM post-processing: getting numbers and pictures out

Everything here needs a loaded solution (`femm_solve`, `femm_load_solution`, or `femm_open` on a
solution file). Re-solve after every change: the post-processor shows the old solution otherwise.

## Point values

`femm_point_values([[x, y], ...])` returns labelled values plus the magnitude, and a `units` table.
Components are x/y in planar models and r/z in axisymmetric ones (keys renamed accordingly).

| # | Magnetics raw value | Key | Unit |
|---|---|---|---|
| 1 | A | `A` | Wb/m |
| 2-3 | B1, B2 | `Bx`, `By` (`Br`, `Bz` axi) | T |
| 4 | Sig | `sigma` | MS/m |
| 5 | E | `energy_density` | J/m^3 |
| 6-7 | H1, H2 | `Hx`, `Hy` | A/m |
| 8 | Je | `J_eddy` | MA/m^2 (verified) |
| 9 | Js | `J_source` | MA/m^2 (verified) |
| 10-11 | Mu1, Mu2 | `mux`, `muy` | relative |
| 12 | Pe | `P_ohmic` | W/m^3 |
| 13 | Ph | `P_hyst` | W/m^3 |
| 14 | ff | `fill_factor` | - |
| + | magnitude | key is B between vertical bars | T |

AC values are `{"re", "im"}` peak phasors; the magnitude is sqrt(abs(B1)^2 + abs(B2)^2). A point
outside the mesh (also inside an air-gap element annulus) gives `outside: true`. A few hundred
points per call are fine (about 1 ms each). The other physics: electrostatics 8 values, heat flow
7, current flow 15 (table in `femm-electrostatics-thermal-currentflow`).

The pyFEMM helpers `mo_getb`, `mo_geth`, `mo_getj`, ... do not exist in the engine
(`name 'mo_getb' isn't defined`): use `femm_point_values` or `femm_call("mo_getpointvalues", [x, y])`.

## Block integrals

`femm_block_integral(points=[[x, y]], group=[n], codes=[...])` clears the selection, selects the
blocks containing the points and all blocks of the groups, evaluates each code, and clears again
(post-processor selection toggles, so selecting twice deselects; the tool avoids that).
Magnetics defaults: `[2, 17, 5, 10, 7]`. Planar results are for the full depth.

| Code | Magnetics quantity | Code | Magnetics quantity |
|---|---|---|---|
| 0 | A.J | 16 | 2x Lorentz torque |
| 1 | A | 17 | magnetic coenergy (J) |
| 2 | magnetic field energy (J) | 18 / 19 | weighted stress tensor force x/r, y/z (N), steady-state |
| 3 | hysteresis and/or lamination losses (W) | 20 / 21 | WST force x/r, y/z, 2x |
| 4 | resistive losses (W) | 22 | WST torque (N*m), steady-state |
| 5 | cross-section area | 23 | WST torque, 2x |
| 6 | total losses (W) | 24 | R^2 (moment of inertia / density) |
| 7 | total current (A) | 25 / 26 | WST force x/r, y/z, 1x |
| 8 / 9 | integral of Bx (Br), By (Bz) | 27 | WST torque, 1x |
| 10 | volume | 28 / 29 | Lorentz force x/r, y/z, 1x |
| 11 / 12 | Lorentz force x/r, y/z, steady-state | 30 | Lorentz torque, 1x |
| 13 / 14 | Lorentz force x/r, y/z, 2x | | |
| 15 | Lorentz torque, steady-state | | |

Rules for force and torque:

- WST (18/19/22) on a part **surrounded by air**; select the moving part only, not the air around
  it. In axisymmetric models only the z-force (19) of a body on the axis is non-zero.
- Lorentz (11-15) is the force on currents in the selected blocks (not on iron or magnets).
- Across an air-gap element the WST torque reads about 1e-16 N*m; use `femm_gap_results`.
- Verified identities: linear C-core code 2 = code 17 = 1/2 psi I; WST vs virtual work 1.6 % RMS.

Other physics codes: `femm_api_get("eo_blockintegral")` (and `ho_`, `co_`), tabled in
`femm-electrostatics-thermal-currentflow`. Hand-rolled selection for `femm_call`:
`femm_select_block(points | group)` then `femm_call("mo_blockintegral", [code])`, then
`femm_select_block(action="clear")`. `mo_groupselectblock` calls accumulate.

## Line integrals and contour plots

`femm_line_integral(contour=[[x, y], ...], codes)` (straight pieces through the points; use many
points to follow a curve). Magnetics: 0 B.n (flux: total, average), 1 H.t (MMF), 2 length and
surface area, 3 stress-tensor force (DC x, DC y, 2x x, 2x y), 4 stress-tensor torque (DC, 2x),
5 (B.n)^2.

`femm_make_plot(contour, plot_type, npts, path)` samples a quantity along the contour into a text
file (header like `Position, |B|`, then rows) and returns stats; works headless. Magnetics
plot types: 0 A, 1 abs(B), 2 B.n, 3 B.t, 4 abs(H), 5 H.n, 6 H.t, 7 J eddy, 8 J source + eddy.

## Circuits and conductors

`femm_circuit_results(name)`: magnetics current (A), voltage (V), flux linkage (Wb, including turns
and depth), plus `inductance_H` = psi / I and `resistance_ohm` (DC) or `impedance_ohm` (AC).
Other physics: the two conductor values (voltage and charge, temperature and heat flux, voltage and
current). For a multi-coil machine use `femm_experiment_inductance` instead of psi / I.

## Bulk arrays and field statistics

- `femm_field_stats(region="all" | "group:1,2", threshold=1.6)`: area-weighted min / max / mean /
  rms / p95 of the field magnitude per element; magnetics adds the saturated area fraction and the
  count of elements above 2 T; other physics add node V or T statistics. Fast, no file.
- `femm_mesh_arrays(which="all" | "nodes,elements,b", fmt="npz" | "csv")`: writes to
  `<work_dir>/arrays/` and returns path, shape and per-column stats, never the raw arrays.
  Elements are `n1, n2, n3, cx, cy, area, group` with **1-based** node indices; B is 2 values per
  element; nodes 2 per node. 10k elements come back in about 0.1 s.
- `femm_file_summary(path, arrays=True)` reads a solution file offline and writes the mesh as .npz.

## Air-gap element results

`femm_gap_results("AGE", angle=15, harmonics=10, npts=360, include_ac=False)`: torque, force and
energy (`mo_gapintegral` 0/1/2; with `include_ac` also 2x and interaction terms), Br/Bt at an
angle, the Br/Bt distribution over `npts` angles saved as CSV with stats, and the largest Br
harmonics (row index = harmonic number; verified on a 2-pole magnet: row 1 carried the 1.2165 T
fundamental). An unknown boundary name gives zeros, not an error; the tool warns.

## Pictures and reports

| Need | Tool | Note |
|---|---|---|
| B map, headless | `femm_plot_field(path, zoom=[xmin, xmax, ymin, ymax])` | rendered from the bulk arrays; `save_arrays` adds .npz |
| FEMM's own view | `femm_save_bitmap(path, view="post")` | **GUI session only** (`femm_session_open(name="gui", headless=False)`, then open and solve there). `zoom=[x1, y1, x2, y2]` here, a different order than `femm_plot_field` |
| curve along a line | `femm_make_plot` | text file + stats |
| experiment plots | `files.png` of each experiment | |
| report | `femm_report(title, include=["model", "health", "field", "experiments"])` | report.md + report.json + figures in `<work_dir>/reports/<timestamp>/` |
| A/B comparison | `femm_compare_results(a, b, rtol=0.02)` | two experiment JSON files (or JSON text); rows matched on the first column; differences beyond rtol flagged |

GUI screenshots: after a solve the post-processor has focus; `view="pre"` switches back to the
geometry. FEMM's default density plot (legend -1) auto-scales; explicit bounds of 0/0 give a legend
that reads 0 everywhere, so pass real `lower`/`upper` when you set `plot_type`.

## A report-ready result

State: the quantity with units, where and how it was obtained (point, block and code, contour),
the model depth used, the mesh size, the health verdicts, the analytic reference, and the files.
