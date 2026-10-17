---
name: femm-electrostatics-thermal-currentflow
description: FEMM 5 electrostatics, heat flow and current flow through the femm MCP tools (femm_*) - how the three non-magnetic physics differ from magnetics in problem definition, boundaries, conductors, materials, point-value layouts (eo 8, ho 7, co 15 values), block and line integral codes, and how to verify them against capacitance, conduction and resistance formulas (benchmarks within 1 %). Use when the user wants capacitance, electric field, insulation stress, temperature rise, heat flux, thermal resistance, conduction current, resistance, busbar current density or a dielectric/conductive AC current-flow model in FEMM, or opens a .fee/.feh/.fec/.res/.anh/.anc file.
---

# Electrostatics, heat flow and current flow in FEMM 5

The loop is the same as for magnetics (`femm-magnetics`): new document -> problem definition ->
geometry -> materials -> labels -> boundaries and conductors -> solve -> read -> verify. The
differences below are where agents go wrong.

## The three physics side by side

| | Electrostatics | Heat flow | Current flow |
|---|---|---|---|
| `femm_new_document` | `"electrostatics"` | `"heatflow"` | `"currentflow"` |
| prefixes / files | `ei_`/`eo_`, `.fee` -> `.res` | `hi_`/`ho_`, `.feh` -> `.anh` | `ci_`/`co_`, `.fec` -> `.anc` |
| probdef order (handled by `femm_problem_define`) | units, type, precision, depth, minangle | units, type, precision, depth, minangle, prevsoln, timestep | units, type, **frequency**, precision, depth, minangle |
| frequency | none (ignored with a warning) | none | yes (AC conduction + displacement current) |
| potential | V (volts) | T (kelvin) | V (volts) |
| material args (`femm_material_add`) | `eps_x`, `eps_y` (relative), `qv` (C/m^3) | `k_x`, `k_y` (W/m/K), `qv` (W/m^3), `kt` (volumetric heat capacity) | `sigma_x`, `sigma_y` (**S/m**), `eps_x`, `eps_y`, `ltx`, `lty` (loss tangents) |
| sources on edges/nodes | `femm_add_conductor`, `fixed` = voltage or charge | `fixed` = temperature or flux | `fixed` = voltage or current |
| circuits | none (use conductors) | none | none |
| block label | material, mesh size, group (4-argument `setblockprop`) | same | same |
| health tool | `femm_check_rule` + `femm_estimate` | same | same |
| experiment tools | magnetics only | magnetics only | magnetics only |

`femm_add_block_label` accepts `circuit`, `magdir` and `turns` for every physics but only sends them
for magnetics.

## Boundaries (`femm_add_boundary`)

| Physics | `bc_type` (BdryFormat) | Values |
|---|---|---|
| electrostatics | `fixed_voltage` (0), `mixed` (1), `surface_charge` (2), `periodic` (3), `antiperiodic` (4) | `value` = V, `flux` = C/m^2, `c0`, `c1` |
| current flow | `fixed_voltage` (0), `mixed` (1), `surface_current` (2), `periodic` (3), `antiperiodic` (4) | `value` = V, `flux`, `c0`, `c1` (complex allowed) |
| heat flow | `fixed_temperature` (0), `heat_flux` (1), `convection` (2), `radiation` (3), `periodic` (4), `antiperiodic` (5) | `value` = T (K), `flux` = W/m^2, `h` (W/m^2/K) and `t_inf` (K), `beta` (emissivity) and `t_inf_rad` (K) |

`hi_addboundprop` takes `BdryFormat` as its **second** argument (ahead of the values), the opposite
of `ei_`/`ci_`; `femm_add_boundary` orders it for you. If you call it yourself with `femm_call`,
check `femm_api_get("hi_addboundprop")`. An edge with no boundary keeps the solver default.

## Conductors

A conductor is a set of edges, arcs or nodes held at one potential (or carrying one total
charge, heat or current):

```
femm_add_conductor("hot", fixed="voltage", value=100)          # electrostatics, 100 V
femm_set_segment_prop(points=[[x, y], ...], conductor="hot")   # edges of the electrode
femm_set_arc_prop(points=[[x, y]], conductor="hot")
```

Results after solving: `femm_circuit_results("hot")` -> voltage and charge (electrostatics; also
`capacitance_F_if_other_conductor_at_0V`), temperature and heat flux (heat), voltage and current
(current flow). FEMM returns two values for each conductor.

## Reading results

`femm_point_values` labels the raw values (components x/y planar, r/z axisymmetric):

| Physics | Values in order | Count |
|---|---|---|
| electrostatics | V, D1, D2, E1, E2, eps1, eps2, energy density | 8 |
| heat flow | T, F1, F2 (heat flux), G1, G2 (temperature gradient), k1, k2 | 7 |
| current flow | V, J1, J2, K1, K2, E1, E2, eps1, eps2, Jd1, Jd2, sigma1, sigma2, Jc1, Jc2 | 15 |

The engine returns 15 values for current flow (pyFEMM comments claim 7). The manual labels
`ox, oy` "permittivity", which reads as a typo for conductivity (unverified).

Block integral codes (`femm_block_integral(points=..., group=..., codes=[...])`):

| Physics | Codes |
|---|---|
| electrostatics | 0 stored energy (returns `[W, 0]`), 1 cross-section, 2 volume, 3 average D, 4 average E, 5 WST force, 6 WST torque |
| heat flow | 0 average T, 1 cross-section, 2 volume, 3 average F, 4 average G |
| current flow | 0 real power, 1 reactive power, 2 apparent power, 3 time-average stored energy, 4 cross-section, 5 volume, 6/7 WST force DC, 8/9 WST force 2x, 10 WST torque DC, 11 WST torque 2x |

Line integral codes (`femm_line_integral(contour, codes)`): electrostatics 0 E.t, 1 D.n (charge),
2 length, 3 force, 4 torque; heat 0 G.t (temperature difference), 1 F.n (heat flow), 2 length,
3 average T; current flow 0 E.t, 1 J.n (current), 2 length, 3 average voltage, 4 force, 5 torque.

`femm_field_stats` gives area-weighted |D|, |F| or |J| per element plus node V or T statistics;
`femm_mesh_arrays` dumps `v`/`d`, `t`/`f` or `v`/`j` arrays; `femm_make_plot` samples along a
contour (electrostatics 0 V, 1 |D|, ... 4 |E|; heat 0 T, 1 |F|, ... 4 |G|; current 0 V, 1 |J|, ...).
Density plots for `femm_save_bitmap` (GUI only): electrostatics 0 V, 1 |D|, 2 |E|; heat 0 T,
1 |F|, 2 |G|; current flow 0..8 with 3 = |J|.

## Verified benchmarks (within 1 %)

| Model | Check | Formula |
|---|---|---|
| parallel-plate capacitor, eps_r 4 | conductor charge and `eo_blockintegral(0)` energy within 1 % | `femm_estimate("parallel_plate_capacitance", {"area", "gap", "eps_r"})`, W = 1/2 C V^2 |
| heat-flow slab | heat flux magnitude within 1 % of k dT / L | Fourier's law |
| current-flow strip | current density magnitude within 1 % of sigma V / L | `femm_estimate("bar_resistance", {"length", "area", "sigma"})` (sigma in S/m) |

Other references: `coax_capacitance_per_length`. Turn them into checks with
`femm_check_rule("compare_to_estimate", {"name": "C", "fem_value": ..., "estimate": ...,
"tolerance": 0.05})` or `femm_check_rule("energy_consistency", ...)`.

## Pitfalls

- Current-flow conductivity is **S/m** (copper about 5.8e7); magnetics uses MS/m (58). A factor of
  1e6 is the usual bug.
- Planar results include the depth. Capacitance from charge/voltage is for the full depth.
- Heat-flow temperatures and `t_inf` are in kelvin.
- Transient heat (`prev_solution`, `time_step` in `femm_problem_define`) is wired but was not
  exercised live: verify on a case with a known answer first.
- `femm_health_check` covers magnetics only; for these physics build the checks yourself from
  `femm_check_rule` and `femm_estimate`, and state that you did so.
- `ei_/hi_/ci_getprobleminfo` return three values `[type, depth, length unit]`; current flow has no
  frequency field there. `femm_problem_info` labels them.
- The electrostatic permittivity constant `eo` and the post-processor prefix `eo_` share a name in
  scripts; do not overwrite `eo` in `femm_eval`.
