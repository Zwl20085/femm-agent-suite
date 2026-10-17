# Experiment recipes and sanity anchors

Numbers measured on FEMM 5.0 build 06oct2026 (Windows, headless) by `examples/` and the live tests.
Your own model will differ; these anchor the order of magnitude and the size of the method errors.

## C-core actuator (`femm_build_benchmark("ccore")`)

Planar U-core + I-armature, two 1 mm gaps, 200 turns, 2 A, 20 mm deep, linear iron mu_r 2000.
Groups: armature 1, core 2, coil 3.

```
femm_build_benchmark("ccore")
femm_solve()
femm_health_check(force_groups=[1], reaction_groups=[2, 3],
                  flux_lines=[[[-30, 40.5], [-20, 40.5]], [[20, 40.5], [30, 40.5]]])
femm_experiment_force_vs_position(groups=[1], dy=0.25, steps=9)     # gap 1 -> 3 mm
femm_experiment_inductance(current=2)
```

| Quantity | FEMM 5 | Reference |
|---|---|---|
| gap B | 0.238 T | mu0 N I / (2g + l_fe/mu_r) = 0.2405 T |
| health check | all 10 applicable rules pass; W = W' = 1/2 L I^2 to 0.00 %; left/right gap flux equal to 0.3 % | |
| force at 1 mm | -9.74 N; WST vs virtual work 1.6 % RMS over 1-3 mm | 2 B^2 A / 2 mu0 = -9.21 N |
| inductance | 7.47 mH | 4.81 mH without fringing and leakage |
| energy | block integral 2 = 17 = 1/2 psi I = 0.0149452 J at 2 A | |
| solve time | 0.13-0.20 s, about 15k elements | |

## Coilgun (`femm_build_benchmark("coilgun")`, axisymmetric, inches)

Slug = group 1 on the axis; move along z with `dy`. WST force (code 19 is the z-force in axi) vs
virtual work agreed to 5 %. The coil's centre field (thick-solenoid check, ABC R = 4 in) was
0.2305 T vs 0.2289 T from the formula (+0.7 %). The step size below is an example, not the
measured run.

```
femm_build_benchmark("coilgun")
femm_experiment_force_vs_position(groups=[1], dy=0.1, steps=11)
```

## SPM machine (`femm_build_benchmark("spm")`)

12 slots, 4 poles, inner rotor, M-19 14 mil, N42 (linear, mu_r 1.05, H_c 994529 A/m, Br 1.312 T),
50 mm outer radius, 50 mm stack, about 9.7k elements (smart mesh off). Circuits A, B, C (series,
0 A). Rotate route: `rotate_groups=[1, 10]`, `torque_groups=[1]`; stator 2, coils 3.

```
femm_build_benchmark("spm")
femm_solve()
femm_health_check(rotor_groups=[1], stator_groups=[2, 3])
femm_experiment_cogging(rotate_groups=[1, 10], torque_groups=[1], slots=12, poles=4, steps=31)
femm_experiment_backemf(rotate_groups=[1, 10], pole_pairs=2, rpm=1000, steps=36)
femm_experiment_inductance(dq={"circuits": ["A", "B", "C"], "pole_pairs": 2, "id": 5, "iq": 5},
                           torque_groups=[1])
femm_experiment_torque_vs_angle(rotate_groups=[1, 10], torque_groups=[1], start=0, stop=30, steps=13,
                                drive={"circuits": ["A", "B", "C"], "pole_pairs": 2, "id": 0, "iq": 10})
femm_experiment_bh_check()
```

Air-gap element route (same machine):

```
femm_build_benchmark("spm", path="spm_age.fem", params={"rotor_method": "age"})
femm_experiment_cogging(rotate_groups=[1], slots=12, poles=4, steps=31, method="age", gap_boundary="AGE")
femm_compare_results(<rotate cogging json>, <age cogging json>, rtol=0.05, label_a="rotate", label_b="age")
```

| Quantity | FEMM 5 | Reference / note |
|---|---|---|
| gap B | 0.862 T | Br lm / (lm + mu_r kc g) = 0.843 T |
| cogging peak to peak | 0.3824 N*m (rotate) / 0.3835 N*m (AGE) | the two routes agree to 0.3 %; period 30 deg |
| cogging, WST vs virtual work | 6.6 % RMS (2 deg steps) | inside the 15 % tolerance |
| psi_pm fundamental | 47.6 mWb | flat-gap estimate 51.0 mWb |
| back-EMF at 1000 rpm | 9.97 V peak (9.977 AGE vs 9.973 rotate), THD 27 % | full-pitch winding, full-arc magnets |
| Ld / Lq | 0.427 / 0.421 mH | SPM: Ld close to Lq; mutuals reciprocal to 0.4 % |
| torque at iq = 10 A, one position | about 12 % off the dq value | EMF harmonics x current |
| mean torque at iq = 10 A over 0-30 deg | 1.415 N*m | 3/2 p psi_d iq with the FEM flux linkage = 1.428 N*m |
| magnet operating point | B_m / Br = 0.70, Pc about 2.5 | load line B_m = Br Pc / (Pc + mu_r) |
| per step | 0.15 s rotate (incl. re-mesh), 0.19 s AGE | |
| whole example, about 130 solves | 24.5 s | |

## Round wire AC (`femm_build_benchmark("round_wire")`)

Copper r 5 mm in an A = 0 circle of 50 mm, 1 m deep, wire mesh 0.25 mm, circuit `wire`.

```
femm_build_benchmark("round_wire")
femm_experiment_ac_sweep(frequencies=[1, 10, 100, 1000, 3000, 10000])
```

| Quantity | FEMM 5 | Reference |
|---|---|---|
| L_dc | 0.509 uH | mu0/2pi (ln(Rb/a) + 1/4) x 1 m = 0.5105 uH |
| R(f) vs exact Bessel impedance | 0.0 % (1-100 Hz), 0.1 % (1 kHz), 0.4 % (3 kHz), 1.3 % (10 kHz) | `femm_estimate("round_wire_internal_impedance")` |
| power balance | 1/2 Re(V conj I) = total losses to 0.00 % | phasors are peak |
| solve | 0.13 s, 10.7k elements | |

## Parametric example: magnet coercivity

```
femm_experiment_parametric(
  cases=[{"name": "Hc 900k", "params": {"hc": 9e5}, "commands": [{"command": "mi_modifymaterial", "args": ["N42", 3, 9e5]}]},
         {"name": "Hc 994k", "params": {"hc": 994529}, "commands": [{"command": "mi_modifymaterial", "args": ["N42", 3, 994529]}]}],
  outputs=[{"name": "Bgap", "kind": "point", "x": 23.4, "y": 0, "quantity": "B"},
           {"name": "psiA", "kind": "circuit", "circuit": "A", "quantity": "flux"}])
```

`mi_modifymaterial` property 3 is H_c by the `mi_addmaterial` order (indices other than 1, 4, 5 and 8
are unverified: confirm with a saved file or `femm_material_get` after one case). The probe point
(23.4, 0) lies in the gap of the default SPM (magnet outer radius 23 mm, bore 24.5 mm, sliding
circle at 23.75 mm); pick a probe inside the gap of the model you actually built, away from
boundary circles.
