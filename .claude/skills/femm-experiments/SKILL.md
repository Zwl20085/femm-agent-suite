---
name: femm-experiments
description: Running and interpreting the standard FEMM 5 magnetics experiments through the femm MCP tools (femm_experiment_force_vs_position, femm_experiment_torque_vs_angle, femm_experiment_cogging, femm_experiment_backemf, femm_experiment_inductance, femm_experiment_ac_sweep, femm_experiment_parametric, femm_experiment_bh_check, femm_build_benchmark) - force-stroke curves, torque vs rotor angle, cogging torque by rotate-and-remesh and by the air-gap element, back-EMF and THD, Ld/Lq and inductance matrices, AC impedance sweeps, parametric studies and magnet operating points, with the numbers the benchmarks produced as sanity anchors. Use when the user asks for any sweep or characterisation of an actuator, solenoid, inductor or PM motor in FEMM.
---

# FEMM experiments: standard tests with built-in checks

Every experiment tool works on the open **magnetics** model, saves its own copy under
`<work_dir>/experiments/`, sweeps, restores geometry, currents and frequency at the end, and
returns:

```
{"experiment", "model", "parameters", "columns", "rows", "summary", "health", "health_summary",
 "files": {"csv", "json", "png"}, "timing": {"total_s", "solves", "per_solve_s"}}
```

Read `health_summary` first: each experiment carries its own consistency checks. More than 120 rows
are thinned in the reply (the CSV has all). The JSON paths feed `femm_report` and
`femm_compare_results`.

## Before any experiment

1. A solved, checked model: run `femm_solve` and `femm_health_check` once at the start position.
2. Moving parts in their own groups (nodes, edges and labels): `femm-geometry`.
3. Rotating machines need either a mid-gap circle that splits the air (rotate route; the rotor and
   the rotor-side air layer in groups, the air layer **left out** of `torque_groups`) or an
   air-gap element boundary (`method="age"`, `gap_boundary=...`).
4. Precision 1e-8 and at least 3 element layers across the gap; forces and torques are
   differences of large numbers.
5. Estimate the cost: solves x per-solve time (0.15-0.2 s for a 10k-element machine). Ask before
   hundreds of solves.

## The tools

| Tool | Key arguments | What you get | Built-in checks |
|---|---|---|---|
| `femm_experiment_force_vs_position` | `groups`, `dx`/`dy` per step (problem units), `steps`, `force_groups`, `start_offset` | position, Fx, Fy, force along motion, virtual-work force, coenergy, psi per circuit | WST force vs virtual work dW'/ds (8 % RMS of peak) |
| `femm_experiment_torque_vs_angle` | `rotate_groups`, `start`/`stop`/`steps` or `angles`, `center`, `method` ("rotate"/"age"), `gap_boundary`, `torque_groups`, `drive` | torque, gap torque, virtual-work torque, coenergy, psi, currents (driven), dq torque | torque vs virtual work (10 % RMS of peak, fixed currents only), WST vs gap torque (10 %), ripple (informational), mean torque vs 3/2 p (psi_d iq - psi_q id) (8 %, driven) |
| `femm_experiment_cogging` | `rotate_groups`, `slots`, `poles` (= 2p), `steps`, `periods`, `method`, `gap_boundary`, `torque_groups` | cogging torque over 360/lcm(Q, 2p) degrees, peak to peak, rms, harmonics per period and per revolution | zero mean (5 %), periodic end points (10 %), WST vs virtual work (15 %, rotate route) |
| `femm_experiment_backemf` | `rotate_groups`, `pole_pairs`, `rpm`, `steps`, `circuits`, `method`, `gap_boundary`, `psi_estimate` | psi and EMF per phase over one electrical period, fundamental (peak, rms), THD, harmonics, line-line EMF, Ke | three-phase balance (3 %), half-wave antisymmetry (5 %), psi vs analytic (20 %) |
| `femm_experiment_inductance` | `circuits`, `current`, or `dq` = {circuits, pole_pairs, theta0_deg, id, iq}, `torque_groups`/`gap_boundary` | L matrix from (psi(I) - psi(0)) / I; or psi_pm, Ld, Lq, saliency, dq torque vs FEM torque | W = 1/2 L I^2 (linear, no magnets), mutual reciprocity (3 %), FEM torque vs dq (15 %) |
| `femm_experiment_ac_sweep` | `frequencies` (Hz), `circuits`, `current` | Z, R(f), L(f) = Im Z / omega, losses total/resistive/hysteresis | 1/2 Re(V conj I) = total losses per frequency (5 %) |
| `femm_experiment_parametric` | `cases` [{name, params, commands}], `outputs` [{kind: point/block/circuit/gap/line/expr, ...}], `template` | one row per case | collected errors per case |
| `femm_experiment_bh_check` | `min_fraction` (0.2) | per magnet label: mean and min B_m along magdir, H_m, Pc, B_m/Br | min B_m >= 0.2 Br (demagnetisation risk) |
| `femm_build_benchmark` | `kind` (ccore, coilgun, spm, round_wire), `path`, `params` | a saved, validated model + groups, circuits, analytic estimates | (the anchors below) |

Units: moves in problem units, angles in mechanical degrees, forces N, torque N*m, flux linkage
Wb-turn, inductance H. Planar results include the model depth.

## Choosing the rotor route

| | rotate and re-mesh (`method="rotate"`) | air-gap element (`method="age"`) |
|---|---|---|
| model | mid-gap circle splits the air; rotor + rotor-side air in groups | two mid-gap circles with BdryFormat 6 + `<No Mesh>` annulus |
| per step | rotate groups, re-mesh, solve (0.15 s on the SPM) | `mi_modifyboundprop(name, 10, angle)`, solve (0.19 s) |
| torque | WST block integral 22 on `torque_groups` | `mo_gapintegral(name, 0)` (WST reads ~0 here) |
| mesh noise | mesh changes every step | mesh fixed |
| agreement on the SPM | cogging 0.3824 N*m p-p | 0.3835 N*m p-p (0.3 %) |

Run both on important results and compare with `femm_compare_results(a_json, b_json, rtol=0.05)`.

## Interpreting results

- **Force vs position**: the WST force and the virtual-work force (derivative of coenergy at
  constant current) are independent; agreement within a few % RMS is the real check. Sign: the
  force on `force_groups`; an attracting armature moved away from the core shows negative force.
- **Cogging**: the period is 360 / lcm(Q, 2p) mechanical degrees (`femm_estimate
  ("cogging_period_deg")`). A non-zero mean means a current is still on or the sweep does not span
  whole periods. Use enough steps per period (31 by default) and both routes when the number matters.
- **Back-EMF**: EMF = omega x dpsi/dtheta by spectral derivative. A large THD is normal for full-pitch
  windings with full-arc magnets (27 % on the SPM). Use the fundamental for dq work.
- **Ld / Lq**: subtracting the zero-current solve removes magnet flux; with saturating iron these are
  secant inductances about the PM operating point. At a single rotor position the FEM torque can
  differ from the dq value (12 % on the SPM because of the 27 % THD); the driven
  `femm_experiment_torque_vs_angle` mean is the fair comparison.
- **Loaded torque**: `drive={"circuits": ["A","B","C"], "pole_pairs": p, "id": 0, "iq": 10,
  "theta0_deg": 0}` makes the currents follow the rotor (amplitude-invariant dq, theta_e = p x angle +
  theta0, theta0 = electrical angle of the d-axis from phase A). The SPM benchmark has phase A's axis
  and the d-axis both at 0 degrees, so theta0 = 0 there.
- **AC sweep**: phasors are peak. Mesh must resolve the skin depth (`femm_estimate("skin_depth")`).
- **Parametric**: setup commands must be pre-processor commands (`mi_`/`ei_`/`hi_`/`ci_`); every case
  re-opens the same saved base model, so cases do not leak into each other.

Calls and anchors for each benchmark: `references/anchors.md`.

## After the experiment

Report: what was swept, the table or plot (`files.png`), every check in `health` with its value and
tolerance, the analytic anchor, and the run time. Then `femm_report(title=...)` bundles the model
summary, health check, field map and this session's experiments into report.md.
