# Recipes: electrostatics, heat flow, current flow

Exact call sequences for the three standard checks. Dimensions are examples; replace them, keep
the order. Session is `main` throughout. After each recipe, compare with the estimate named in the
last step and report the ratio (see `femm-troubleshooting` for ratio -> cause).

General order for all three: `femm_new_document` -> `femm_problem_define` (set the depth!) ->
materials -> geometry -> one block label per closed region -> boundaries / conductors on the
edges -> `femm_geometry_summary` -> `femm_solve` -> read -> compare.

Edges with no boundary and no conductor are zero-normal-flux (natural) edges: verified on FEMM 5
build 20261101 for heat flow and electrostatics (a slab with T or V fixed on two opposite edges and
nothing on the other two gives an exactly linear profile, 0.75 / 0.50 / 0.25 at the quarter points,
at the free edges too). Planar conductor results (charge, heat flux, current) are totals over the
depth, not per metre (verified on the same build, below).

## 1. Parallel-plate capacitor with a dielectric (electrostatics)

Model: dielectric slab between two plates. Plate 1 is the left edge (x = 0), plate 2 the right
edge (x = d). Sides are left unassigned (no fringing), so the result is comparable with the ideal
formula. Units mm, planar, depth w_z = 50 mm, d = 2 mm, plate height h = 20 mm, eps_r = 4.

```
femm_new_document(physics="electrostatics")
femm_problem_define(units="millimeters", problem_type="planar", depth=50)
femm_material_add(name="Diel", eps_x=4)                  # relative permittivity; eps_y defaults to eps_x
femm_draw_rectangle(0, 0, 2, 20)                         # one closed region: the dielectric
femm_add_block_label(1, 10, "Diel")                      # exactly one label in the region
femm_add_conductor("plate1", fixed="voltage", value=100) # V
femm_add_conductor("plate2", fixed="voltage", value=0)
femm_set_segment_prop(points=[[0, 10]], conductor="plate1")   # midpoint of the left edge
femm_set_segment_prop(points=[[2, 10]], conductor="plate2")   # midpoint of the right edge
femm_geometry_summary()                                  # 1 label, 2 conductors, 4 segments
femm_solve()
femm_circuit_results("plate1")                           # voltage_V, charge_C, capacitance_F_if_other_conductor_at_0V
femm_circuit_results("plate2")
```

- Several dielectric layers: one rectangle per layer sharing the edge between them, one label
  each with its own material. The shared edge needs no property.
- Outer boundary: none is needed for this closed dielectric. For an open capacitor (fringing
  included) surround the plates with air, put `femm_add_boundary(name="V0", bc_type="fixed_voltage",
  value=0)` on the outer box (3-5x the plate size) and label the air region; then the result
  exceeds the ideal formula by the fringing share.
- C = Q / (V1 - V2), with V1 - V2 = 100 here. The key `capacitance_F_if_other_conductor_at_0V`
  equals Q / V1 and is only C when the other conductor is at 0 V, as above; with both conductors
  at nonzero voltages divide by the difference yourself.
- Charge in a planar model is the total over the depth in C (verified on build 20261101: a coax
  with depth 100 mm gave 2.4221e-12 C against 2 pi eps0 / ln(b/a) x 0.1 m = 2.4161e-12 C). The
  per-metre value is `charge_C` / depth in metres.
- Energy cross-check: `femm_block_integral(group=[0], codes=[0])` (stored energy) = 1/2 C V^2;
  or `femm_check_rule("energy_consistency", ...)` style comparison by hand.

Compare with: `femm_estimate("parallel_plate_capacitance", {"area": 0.020 * 0.050, "gap": 0.002,
"eps_r": 4}, fem_value=<C from FEMM>)` (SI: area in m^2, gap in m).

## 2. Heat slab with convection (heat flow)

Model: slab of thickness L along x, conductivity k, held at T1 on the left edge, convecting to
ambient T_inf on the right edge, top and bottom unassigned (1D conduction). Units mm, planar,
depth 100 mm, L = 20 mm, height 10 mm, k = 50 W/m/K, T1 = 400 K, h = 25 W/m^2/K, T_inf = 300 K.
Temperatures are in kelvin.

```
femm_new_document(physics="heatflow")
femm_problem_define(units="millimeters", problem_type="planar", depth=100)
femm_material_add(name="Slab", k_x=50)                   # W/m/K; k_y defaults to k_x
femm_draw_rectangle(0, 0, 20, 10)
femm_add_block_label(10, 5, "Slab")
femm_add_boundary(name="Hot", bc_type="fixed_temperature", value=400, segments=[[0, 5]])
femm_add_boundary(name="Conv", bc_type="convection", h=25, t_inf=300, segments=[[20, 5]])
femm_geometry_summary()
femm_solve()
femm_point_values(10, 5)                                 # T and heat flux F1, F2 (W/m^2)
femm_point_values(20, 5)                                 # T at the convecting face
```

- Read the heat flux density F1 at mid-slab (W/m^2): independent of the depth, so no unit
  ambiguity. Total heat flow = F1 x height x depth (SI).
- Textbook 1D result: q'' = (T1 - T_inf) / (L/k + 1/h), surface temperature
  T_s = T_inf + q''/h.
- A conductor result (`femm_add_conductor(..., fixed="temperature")` then `femm_circuit_results`)
  gives `heat_flux_W`, the total in W over the depth of a planar model (verified on build
  20261101: coax, k = 1 W/(m K), 1 K, depth 0.1 m: 0.27355 W against 2 pi k dT / ln(b/a) x 0.1 =
  0.27288 W). Compare it with q'' x height x depth.
- Transient heat (`prev_solution`, `time_step`) is not covered here and was not exercised live.

Compare with: there is no heat-flow entry in `femm_estimate`. The thermal resistance has the
same form as the electrical bar: `femm_estimate("bar_resistance", {"length": 0.020, "area": 0.010 *
0.100, "sigma": 50})` returns L/(k A) in K/W (the function does not know it is thermal). Add
1/(h A) for the convection film, then q = (T1 - T_inf) / R_total and compare with the FEM heat
flow with `femm_check_rule("compare_to_estimate", {...})`.

## 3. Strip resistance (current flow, DC)

Model: conducting strip of length L along x, V1 on the left edge, 0 V on the right edge, sides
unassigned. Units mm, planar, depth 2 mm (copper foil), L = 100 mm, width 10 mm, sigma in S/m
(copper about 5.8e7, not 58: current flow is not MS/m).

```
femm_new_document(physics="currentflow")
femm_problem_define(units="millimeters", problem_type="planar", depth=2, frequency=0)
femm_material_add(name="Strip", sigma_x=5.8e7)           # S/m
femm_draw_rectangle(0, 0, 100, 10)
femm_add_block_label(50, 5, "Strip")
femm_add_conductor("in", fixed="voltage", value=1)       # 1 V
femm_add_conductor("out", fixed="voltage", value=0)
femm_set_segment_prop(points=[[0, 5]], conductor="in")
femm_set_segment_prop(points=[[100, 5]], conductor="out")
femm_geometry_summary()
femm_solve()
femm_circuit_results("in")                               # voltage_V, current_A
femm_point_values(50, 5)                                 # V and current density J1, J2 (A/m^2)
```

- R = V / I. Take I from `femm_circuit_results("in")["current_A"]`, and cross-check it with the
  current density: I = J1 x width x depth (SI: 0.010 m x 0.002 m). `current_A` is the total over
  the depth of a planar model (verified on build 20261101: a 20 x 10 mm slab, sigma 1 S/m, 1 V,
  depth 100 mm gave 0.0500 A = sigma V / L x height x depth).
- Current flow with frequency > 0 adds displacement current (`eps_x`, loss tangents); keep
  `frequency=0` for a resistance.

Compare with: `femm_estimate("bar_resistance", {"length": 0.100, "area": 0.010 * 0.002,
"sigma": 5.8e7}, fem_value=<V / I from FEMM>)` (SI).
