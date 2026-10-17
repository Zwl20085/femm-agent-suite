# Magnetics recipes (exact tool calls)

All coordinates in millimeters unless noted. Each recipe ends with the checks that prove it.

## 1. Fastest route: a validated benchmark

```
femm_build_benchmark("ccore")                 # or "coilgun", "spm", "round_wire"
femm_solve()
femm_health_check(force_groups=[1], reaction_groups=[2, 3])
```

The builder returns groups, circuits, the probe point and analytic estimates. Edit it from there
(`femm_set_block_prop`, `femm_modify_circuit`, `femm_material_modify`) instead of starting from a
blank page when the user's device resembles one of them.

| kind | model | groups / circuits | key params (defaults) |
|---|---|---|---|
| `ccore` | planar U-core + I-armature, two gaps, `mi_makeABC` open boundary | armature 1, core 2, coil 3; circuit `coil` | `gap` 1.0, `core_width` 10, `depth` 20, `turns` 200, `current` 2, `iron` "linear:2000" or a library steel |
| `coilgun` | axisymmetric coil + spherical slug on the axis (inches) | slug 1, coil 3; circuit `coil` | `slug_z`, `turns` 1000, `current` 9.677, `slug_material` "linear:2500" |
| `spm` | 12-slot / 4-pole inner-rotor surface-PM machine | rotate route: rotor 1, rotor-side air 10, stator 2, coils 3; AGE route: rotor 1, boundary `AGE`; circuits A, B, C | see `femm-machine-design` |
| `round_wire` | copper wire in an A = 0 circle, 1 m deep, AC | wire 1; circuit `wire` | `radius` 5, `boundary_radius` 50, `frequency` 50, `mesh_wire` 0.25 |

## 2. C-core actuator by hand

```
femm_new_document("magnetics")
femm_problem_define(units="mm", problem_type="planar", depth=20)
femm_material_load(["Air", "Copper"])
femm_material_add("Iron2000", mu_x=2000)                 # or a library steel after femm_material_search
femm_add_circuit("coil", current=2, series=True)
femm_draw_polygon([[-30,0],[30,0],[30,40],[20,40],[20,10],[-20,10],[-20,40],[-30,40]])   # U-core
femm_draw_rectangle(-30, 41, 30, 51)                     # armature, 1 mm gaps
femm_draw_rectangle(-18, 11, 18, 19)                     # coil side above the base
femm_draw_rectangle(-18, -9, 18, -1)                     # coil side below the base
femm_call("mi_makeABC", [7, 180, 0, 25.5, 0])            # open boundary, R = 3 x size
femm_add_block_label(0, 5, "Iron2000", group=2)
femm_add_block_label(0, 46, "Iron2000", group=1)
femm_add_block_label(0, 15, "Copper", circuit="coil", turns=200, group=3)
femm_add_block_label(0, -5, "Copper", circuit="coil", turns=-200, group=3)
femm_add_block_label(0, 30, "Air")
femm_select(kind="rectangle", rectangle=[-30.01, 40.99, 30.01, 51.01])
femm_set_group(1)                                        # the armature edges move with its label
femm_geometry_summary()
femm_solve()
femm_point_values([[25, 40.5]])                          # in the right gap
femm_circuit_results("coil")
```

Checks: `femm_estimate("ccore_gap_b", {"turns": 200, "current": 2, "gap": 0.002, "iron_path": <m>,
"mu_r": 2000})` (the benchmark measured 0.238 T vs 0.2405 T); `femm_health_check(force_groups=[1],
reaction_groups=[2, 3], flux_lines=[[[-30, 40.5], [-20, 40.5]], [[20, 40.5], [30, 40.5]]])` (left
and right gap flux equal to 0.3 % on the benchmark).

## 3. Thick solenoid, axisymmetric (the self-test model)

```
femm_new_document("magnetics")
femm_problem_define(units="mm", problem_type="axi")
femm_material_load(["Air", "Copper"])
femm_add_circuit("coil", current=1)
femm_draw_rectangle(10, -50, 12, 50)
femm_add_block_label(11, 0, "Copper", circuit="coil", turns=500)
femm_call("mi_makeABC", [7, 300, 0, 0, 0])
femm_add_block_label(5, 70, "Air")
femm_solve()
femm_point_values([[0, 0]])
```

Check: `femm_estimate("thick_solenoid_b_center", {"current_density": 2.5e6, "r_inner": 0.010,
"r_outer": 0.012, "length": 0.100})`. Measured error 0.7 %. `J_source` at (11, 0) reads 2.5
(MA/m^2).

## 4. AC resistance of a round wire

```
femm_build_benchmark("round_wire", params={"frequency": 1000})
femm_experiment_ac_sweep(frequencies=[1, 10, 100, 1000, 3000, 10000])
```

Check: `femm_estimate("round_wire_internal_impedance", {"radius": 0.005, "sigma": 58e6, "freq":
1000})` per metre (the model is 1 m deep). Measured: 0.0 % at 1-100 Hz, 0.1 % at 1 kHz, 0.4 % at
3 kHz, 1.3 % at 10 kHz; L_dc 0.509 uH vs 0.5105 uH; every `ac_power_balance` 0.00 %.

## 5. Permanent magnet in an iron circuit

```
femm_material_search("N42")             # library N42 is linear (no B-H points)
femm_material_load(["N42", "M-19 14 mil", "Air"])
femm_add_block_label(x, y, "N42", magdir=90, group=1)    # magnetised towards +y
femm_solve()
femm_experiment_bh_check()                                # B_m, H_m, Pc, B_m/Br per magnet
```

Check: `femm_estimate("pm_load_line", {"br": 1.31, "mu_r": 1.05, "magnet_length": lm, "gap": g})`.
On the SPM benchmark B_m/Br was 0.70 with Pc about 2.5. W = W' does not hold with magnets; the
health check marks that rule not applicable.

## 6. Rotating machine

Use `femm-machine-design` for sizing and `femm_build_benchmark("spm", params=...)` for the model,
then `femm-experiments` for cogging, back-EMF, Ld/Lq and loaded torque. For a model of your own,
the two rotor routes are:

- **rotate and re-mesh**: a circle splits the air gap; the rotor and the rotor-side air layer carry
  groups (e.g. 1 and 10) and are rotated with `femm_select(kind="group")` +
  `femm_move_selected(rotate_deg=a, entities="group")`; torque = `femm_block_integral(group=[1],
  codes=[22])` (leave the air layer out of the torque group).
- **air-gap element**: the recipe in SKILL.md; rotate with `mi_modifyboundprop("AGE", 10, a)`, read
  torque with `femm_gap_results`.

Rotating by +a and then -a leaves node coordinates rounded slightly differently (9786 vs 9676
elements after re-meshing): re-solve after restoring a swept geometry before comparing numbers.
