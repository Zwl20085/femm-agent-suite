---
name: femm-magnetics
description: The build, solve, read, verify loop for FEMM 5 magnetics through the femm MCP tools (femm_*) - magnetostatic and time-harmonic (AC) problems, planar or axisymmetric: problem definition, geometry, materials, block labels, boundaries (the 12-argument mi_addboundprop types, A=0, mi_makeABC open boundary, periodic, the air-gap element / sliding band), circuits and turns, meshing, solving and reading B, flux linkage, inductance, force, torque and losses, plus the feedback ladder that decides whether the result is normal. Use for any FEMM magnetic model - solenoid, C-core, actuator, inductor, transformer, magnet, motor - or when the user asks whether a FEMM magnetic result can be trusted.
---

# FEMM magnetics: the loop and the ladder

You are a magnetics FEA engineer driving FEMM 5 for the user. FEMM raises explicit errors and is
fast (a 10k-element static solve takes well under a second), so the cost of a check is tiny.
Build in small steps, read every reply, and back the final numbers with the ladder below.

## The loop

1. **Session**: `femm_status` (install found?) and, once per machine, `femm_selftest`.
2. **Document**: `femm_new_document("magnetics")`, or `femm_open(path)` + `femm_save(<copy>)` for a
   user model.
3. **Problem**: `femm_problem_define(units="millimeters", problem_type="planar"|"axi",
   depth=<stack length>, frequency=0)`. Frequency 0 = magnetostatic; > 0 = time-harmonic (complex,
   peak phasors). Always pass `depth` for planar models. Precision 1e-8 (the default) for force and
   torque work.
4. **Geometry**: closed regions from `femm_draw_rectangle`, `femm_draw_circle`, `femm_draw_polygon`,
   `femm_add_arcs`, or `femm_import_dxf` (skill `femm-geometry`).
5. **Materials**: `femm_material_search` -> `femm_material_load([...])` with the exact FEMM 5 names,
   or `femm_material_add` (skill `femm-materials`).
6. **Circuits**: `femm_add_circuit(name, current, series=True)` for stranded coils (turns on the
   labels); `series=False` for a solid conductor whose total current divides by impedance.
7. **Block labels**: `femm_add_block_label(x, y, material, circuit=, turns=, magdir=, group=,
   mesh_size=)` - exactly one per closed region. Return conductors get negative `turns`. Magnets
   get `magdir` (degrees). Give every moving part, and every material you want statistics for, its
   own `group`.
8. **Outer boundary**: either a Dirichlet A = 0 box or circle 3-5x the device size
   (`femm_add_boundary("A=0", "prescribed_a", segments=[...] | arcs=[...])`), or an open
   boundary: `femm_call("mi_makeABC", [7, R, x0, y0, 0])` (7 shells of radius R about (x0, y0)).
   Axisymmetric models: leave the r = 0 axis without a boundary (the benchmarks do).
9. **Check before solving**: `femm_geometry_summary` - label count = region count, materials,
   circuits and boundaries as intended.
10. **Solve**: `femm_solve()` (saves, analyses, loads). It returns node/element counts and time.
11. **Read**: `femm_point_values`, `femm_circuit_results` (current, voltage, flux linkage, L),
    `femm_block_integral` (energy, losses, force, torque), `femm_line_integral`, `femm_gap_results`
    (skill `femm-postprocess`).
12. **Verify**: `femm_health_check` + `femm_estimate` (the ladder). Then report.

A worked C-core, solenoid, AC wire and SPM recipe with exact calls: `references/recipes.md`.

## Boundaries (mi_addboundprop, 12 arguments)

`femm_add_boundary` writes `mi_addboundprop(name, A0, A1, A2, Phi, Mu, Sig, c0, c1, BdryFormat,
ia, oa)`; unused parameters stay 0, `ia`/`oa` are only sent for the air-gap types.

| `bc_type` | BdryFormat | Parameters | Use |
|---|---|---|---|
| `prescribed_a` | 0 | `a0`, `a1`, `a2`, `phi` (A = a0 + a1 x + a2 y) | A = 0 outer boundary; flux-parallel symmetry lines |
| `small_skin_depth` | 1 | `mu` (relative), `sigma` (MS/m) | conductor surface at high frequency |
| `mixed` | 2 | `c0`, `c1` (complex allowed) | Robin condition, asymptotic open boundary |
| `strategic_dual_image` | 3 | none | open-boundary approximation |
| `periodic` | 4 | none | one boundary per pair of matching edges, assigned to both |
| `antiperiodic` | 5 | none | as periodic, field reverses (odd pole count in the sector) |
| `periodic_air_gap` | 6 | `inner_angle`, `outer_angle` (deg) | air-gap element / sliding band (verified recipe below) |
| `antiperiodic_air_gap` | 7 | as 6 | sector models with an air-gap element (not exercised live) |

Assign while defining (`segments=[[x, y], ...]`, `arcs=[[x, y], ...]`: points ON the edges, e.g.
midpoints) or later with `femm_set_segment_prop(points, boundary=name)` / `femm_set_arc_prop`.
Periodic and antiperiodic types were not exercised live by this project; check the field
continuity across the pair before trusting a sector model.

`mi_makeABC` adds a Dirichlet boundary named `A=0` and shell materials `u1`..`un` with labels. The
field inside the shells is not physical; the health check knows this and waives its
boundary-distance rule.

## The air-gap element (verified recipe)

Use it for rotating machines: the rotor is stepped by changing a boundary angle, the mesh never
changes, and torque comes from the gap integral.

1. In the middle of the mechanical gap, draw **two concentric circles** of radius `Ri < Ro`, each
   as two 180-degree arcs with fine discretisation:
   `femm_add_arcs([[Ri, 0, -Ri, 0, 180, 1], [-Ri, 0, Ri, 0, 180, 1], [Ro, 0, -Ro, 0, 180, 1], [-Ro, 0, Ro, 0, 180, 1]])`.
2. Define the boundary: `femm_add_boundary("AGE", "periodic_air_gap", inner_angle=0, outer_angle=0)`.
3. Assign it to **all four arcs** (both circles):
   `femm_set_arc_prop(points=[[0, Ri], [0, -Ri], [0, Ro], [0, -Ro]], max_seg_deg=1, boundary="AGE")`.
4. Put a `"<No Mesh>"` block label **in the thin annulus** between the circles:
   `femm_add_block_label((Ri + Ro) / 2, 0, "<No Mesh>")`. Without it the solver stops with
   `Solver failed: a region has no material assigned`.
5. Label the rotor-side air (between magnets and `Ri`) and the stator-side air (between `Ro` and
   the bore) as `Air`, with a gap mesh size (the SPM benchmark uses 0.5 mm in a 1.5 mm gap).
6. Rotate the rotor by `angle` degrees: `femm_call("mi_modifyboundprop", ["AGE", 10, angle])`
   (propnum 10 = inner angle), then `femm_solve`.
7. Torque: `femm_gap_results("AGE")` (integrals: torque, force, energy; Br/Bt distribution;
   harmonics) or `femm_call("mo_gapintegral", ["AGE", 0])`. **Do not** use the WST block integral
   (code 22) across an air-gap element: it reads about 1e-16 N*m.

Pitfalls: an unknown boundary name is not an error, every gap command returns zeros
(`femm_gap_results` warns); `femm_point_values` inside the annulus returns `outside: true`;
the outer-angle property (propnum 11) and BdryFormat 7 were not exercised. On the 12-slot / 4-pole
SPM this route gave cogging 0.3835 N*m peak to peak against 0.3824 N*m by rotate-and-re-mesh.
`femm_build_benchmark("spm", params={"rotor_method": "age"})` builds a complete example.

## Circuits, turns and units

- Series circuit: `current` is the current per turn; each label's `turns` multiplies it; negative
  turns = return side. Parallel: `current` is the total, shared between the blocks by impedance.
- `femm_circuit_results` flux linkage already includes turns and depth; L = psi / I for a circuit
  alone in the model (mutual effects are included when others carry current).
- `J_source`/`J_eddy` from `femm_point_values` are in **MA/m^2** (A/mm^2): 500 turns x 1 A over
  200 mm^2 reads 2.5. A source current density on a material (`femm_material_add(j=...)`) is in
  MA/m^2 too.
- AC: circuit currents and voltages are **peak** phasors. Real input power = 1/2 Re(V conj I); it
  equalled block integral 6 (total losses) to 0.00 % on the round-wire benchmark.

## AC (time-harmonic) checklist

- `femm_problem_define(frequency=f)`. Conductors need `sigma` (library Copper is 58 MS/m).
- Resolve the skin depth: `femm_estimate("skin_depth", {"freq": f, "sigma": 58e6})`, then a mesh
  size well below it on conductor labels. Round wire r 5 mm, 0.25 mm mesh: R(f) within 0.1 % at
  1 kHz, 0.4 % at 3 kHz, 1.3 % at 10 kHz (skin depth 0.66 mm).
- Laminated steel: library entries carry `d_lam` and `LamFill`; FEMM uses them for lamination
  losses in AC problems (behaviour of the lamination model itself not checked by this project).
- `femm_experiment_ac_sweep` runs the frequencies and checks the power balance for you.
- `ac_solver` (0 successive approximation, 1 Newton) matters only for nonlinear AC; its exact
  effect is unverified.

## The feedback ladder: normal or abnormal

Cheapest first. Stop at the first rung that fails and fix it. Details, thresholds and what each
failure usually means: `references/feedback-ladder.md`.

| # | Rung | Signal | Normal looks like |
|---|---|---|---|
| 1 | Call | `ok`, `error.hint`, `warnings` | ok = true on every call |
| 2 | Model | `femm_geometry_summary` | one label per region, intended materials/circuits/boundaries |
| 3 | Solve | `femm_solve` result | element count sensible (1k-200k), solve time under a few seconds for 2D |
| 4 | Physics | `femm_health_check` | every applicable rule ok; n/a rules explained |
| 5 | Engineering | `femm_estimate` vs FEM | same order; the difference explained by fringing, leakage, saturation |
| 6 | Visual | `femm_plot_field` | flux where expected, no flux-density hot spots in air, saturation where intended |
| 7 | Toolchain | `femm_selftest` | all checks pass |

Report the rung results with numbers. "The solve finished" is rung 3, not a result.
