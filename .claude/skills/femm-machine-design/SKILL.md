---
name: femm-machine-design
description: Hand sizing of electric machines and magnetic actuators before and alongside FEMM 5, and turning a sizing into a FEMM model fast through the femm MCP tools (femm_estimate, femm_units_convert, femm_build_benchmark) - slot/pole choice, slots per pole per phase, cogging period, winding factor, magnet sizing and the load line, Carter coefficient, air-gap flux density, flux linkage and back-EMF constant, torque from dq quantities, C-core and solenoid actuator sizing. Use when the user wants to design or sanity-check a surface-PM motor, choose slots and poles, size magnets, estimate torque or EMF by hand, or quickly get a parametrised FEMM motor or actuator model.
---

# Machine design: numbers by hand, then a FEMM model

Hand formulas tell you what FEMM should roughly say; FEMM tells you what the formulas leave out
(fringing, leakage, slotting, saturation, harmonics). Do both, and explain the gap. Formulas
marked **textbook** are standard design relations, not FEMM behaviour verified by this project;
the `femm_estimate` names are implemented and unit tested.

## 1. Slots and poles

- Poles 2p, slots Q, phases m = 3. Slots per pole per phase q = Q / (2p m).
  q = 1: integral-slot, full-pitch, large cogging and EMF harmonics with full-arc magnets (the
  12-slot / 4-pole benchmark: EMF THD 27 %). Fractional q (for example 12/10, 12/8, 9/8) with
  concentrated coils: shorter end windings, lower cogging (textbook).
- Cogging period = 360 / lcm(Q, 2p) mechanical degrees:
  `femm_estimate("cogging_period_deg", {"slots": 12, "poles": 4})` -> 30. A larger lcm generally
  means lower cogging amplitude (textbook).
- Electrical frequency f_e = p rpm / 60.

## 2. Winding factor (textbook)

k_w = k_d k_p, with distribution factor k_d = sin(q alpha / 2) / (q sin(alpha / 2)),
alpha = 2 pi p / Q (slot pitch in electrical radians), and pitch factor k_p = sin(pi y / (2 tau))
for a coil spanning y of a pole pitch tau. Full-pitch q = 1: k_w = 1 (the benchmark's single-layer
winding). Concentrated non-overlapping windings have k_w1 below 1 (about 0.87-0.95 for common
combinations); compute it for the winding you actually lay out.

## 3. Air gap, Carter and magnet sizing

- Carter coefficient for slot openings: `femm_estimate("carter_coefficient", {"slot_pitch": tau_s,
  "slot_opening": b0, "gap": g})`; effective gap g_eff = k_c g.
- Surface-PM gap flux density: `femm_estimate("spm_gap_b", {"br": 1.31, "mu_r": 1.05,
  "magnet_thickness": l_m, "gap": g, "carter": k_c})` = Br l_m / (l_m + mu_r k_c g). Benchmark:
  0.843 T formula vs 0.862 T FEM.
- Load line: `femm_estimate("pm_load_line", {"br", "mu_r", "magnet_length", "gap", "area_ratio",
  "leakage"})` -> Pc, B_m, H_m, B_g. Keep B_m / Br well above 0.2 at the worst (hot, maximum
  d-axis current) case; the benchmark sits at 0.70 with Pc about 2.5.
- Grade conversions: `femm_units_convert("br_from_mgoe", 42)`, `"hc_from_br"` (mu_r 1.05 default).

## 4. Flux linkage, EMF, torque

- Peak PM flux linkage per phase (fundamental):
  `femm_estimate("spm_flux_linkage_fundamental", {"bg", "radius", "stack_length", "pole_pairs",
  "turns_per_phase", "winding_factor", "magnet_arc_fraction"})`, from B_1 = (4/pi) B_g sin(alpha pi/2)
  and Phi_1 = 2 B_1 r L / p. Benchmark: 51.0 mWb formula vs 47.6 mWb FEM (flat gap, no leakage).
- Back-EMF: `femm_estimate("emf_from_flux_linkage", {"psi_peak", "rpm", "pole_pairs"})`
  (E = omega_e psi).
- Torque (amplitude-invariant dq): `femm_estimate("dq_torque", {"pole_pairs", "psi_d", "psi_q",
  "i_d", "i_q"})` = 3/2 p (psi_d i_q - psi_q i_d); with inductances
  `dq_torque_from_inductances` = 3/2 p (psi_pm i_q + (L_d - L_q) i_d i_q). SPM: L_d close to L_q, so
  torque is almost all PM torque. Benchmark: 1.428 N*m from the formula vs 1.415 N*m FEM mean at
  iq = 10 A.
- First-cut rotor volume (textbook): T = 2 sigma_t V_r with air-gap shear stress sigma_t, or
  T = k D^2 L; take the shear-stress value from the user's application class, not from here.

## 5. Actuators

- C-core / gap circuits: `ccore_gap_b` (B_g = mu0 N I / (g + l_fe/mu_r), g = total gap),
  `ccore_inductance`, `reluctance`, and the pull `maxwell_force` (B^2 A / 2 mu0 per pole face; a
  two-gap armature sees twice that).
- Solenoids and coils: `solenoid_b_infinite`, `solenoid_b_axis_finite`, `thick_solenoid_b_center`,
  `loop_b_axis`, `solenoid_inductance_long`.
- Wire: `femm_units_convert("awg_diameter_mm", 18)`; copper resistance `bar_resistance` (S/m);
  `skin_depth` before an AC design.

## 6. From sizing to a FEMM model in one call

`femm_build_benchmark("spm", path="design1.fem", params={...})` builds the inner-rotor SPM from
these parameters (mm, defaults in brackets):

| Param | Meaning | Default |
|---|---|---|
| `slots`, `pole_pairs` | Q and p | 12, 2 |
| `rotor_r` | rotor iron radius | 20 |
| `magnet_t` | magnet thickness (full-arc magnets) | 3 |
| `gap` | mechanical air gap | 1.5 |
| `stator_or` | stator outer radius | 50 |
| `slot_open`, `tip_h`, `slot_w`, `slot_depth` | slot geometry | 2, 1, 5, 12 |
| `depth` | stack length | 50 |
| `turns_per_slot` | turns per coil side | 20 |
| `steel`, `magnet` | library names | "M-19 14 mil", "N42" |
| `rotor_method` | "rotate" (groups [1, 10]) or "age" (boundary `AGE`) | "rotate" |
| `mesh_gap`, `mesh_magnet`, `mesh_iron`, `mesh_coil` | mesh sizes | 0.5, 1.5, 2.5, 2.5 |
| `smartmesh`, `precision` | | false, 1e-8 |

It returns radii, groups (`rotate_groups`, `torque_groups` [1]), circuits A/B/C, the slot phase
table, and estimates (Br, Carter, gap B, turns per phase, psi_pm, cogging period, EMF at 1000 rpm).
The winding is single-layer, laid out by `spm_slot_phases` (phase A's axis and the rotor d-axis at
0 degrees). Only the 12-slot / 4-pole layout was validated against FEM; for other Q/p check the
slot phase table and the three-phase balance of `femm_experiment_backemf` before trusting it.
Interior-PM rotors, double-layer windings and outer rotors are not built by the tool: draw them
with `femm-geometry`, or ask for them as a new builder.

Actuators: `femm_build_benchmark("ccore", params={"gap": 0.5, "turns": 100, "iron": "M-19 14 mil"})`
or `"coilgun"` (axisymmetric).

## 7. Design loop

1. Hand-size (sections 1-5), write the numbers down.
2. `femm_build_benchmark` (or draw it), `femm_solve`, `femm_health_check`.
3. Compare FEM with the estimates; explain each gap (Carter, leakage, saturation, harmonics).
4. `femm-experiments`: cogging, back-EMF, Ld/Lq, loaded torque, magnet operating point.
5. Iterate with `femm_experiment_parametric` or by rebuilding with new `params`; compare runs with
   `femm_compare_results`; finish with `femm_report`.
