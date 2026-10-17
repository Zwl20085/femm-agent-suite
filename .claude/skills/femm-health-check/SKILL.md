---
name: femm-health-check
description: Deciding whether a FEMM 5 result is physically sane through the femm MCP tools (femm_health_check, femm_check_rule, femm_estimate, femm_selftest) - what each health rule checks (mesh, solver precision, energy and coenergy identities, saturation, outer-boundary distance, torque and force action-reaction, AC power balance, flux conservation, magnet operating point), its tolerance, how to pass the right groups, how to compare against the 25 analytic estimates, and how to report PASS / FAIL / CHECK / not applicable. Use after every FEMM solve whose numbers will be reported, when a result looks suspicious, or when the user asks "is this right?" or "can I trust this FEMM result?".
---

# FEMM health check: proving the answer is physics

A converged FEMM solve only proves the matrix was solved. The health layer adds the invariants an
experienced engineer checks by habit, plus closed-form references. Every rule returns:

```
{"name", "ok": true | false | null, "value", "expected", "tolerance", "message", "detail"?}
```

`ok: null` means "not applicable" and the message says why (e.g. energy identities with magnets).

## The three tools

| Tool | Use |
|---|---|
| `femm_health_check` | All rules on the loaded **magnetics** solution (needs `femm_solve`). Saves the model if needed and reads the `.ans` for the element-to-material map. Nothing in the model is changed. |
| `femm_check_rule` | One rule on numbers you already have (no FEMM call). `femm_check_rule("list")` lists them. The route for electrostatics, heat and current flow, and for experiment numbers. |
| `femm_estimate` | Closed-form reference values (SI units). `femm_estimate()` lists the 25 formulas with their arguments. |

## femm_health_check: what runs, and what to pass

```
femm_health_check(
  checks=None,                 # subset of: mesh precision energy saturation boundary torque force ac flux pm
  rotor_groups=[1], stator_groups=[2, 3],       # torque balance (machines)
  force_groups=[1], reaction_groups=[2, 3],     # force balance (actuators)
  flux_lines=[[[x1, y1], [x2, y2]], [[x3, y3], [x4, y4]]],   # two cuts carrying the same flux
  b_limit=1.8)                 # saturation threshold, T
```

| Check | Rule(s) | Passes when | Applies to |
|---|---|---|---|
| mesh | `mesh_element_count`, `mesh_min_angle` | 1 000 <= elements <= 200 000; at most 0.1 % of triangles with a min angle below 10 deg | all |
| precision | `solver_precision` | probdef precision <= 1e-6 (1e-8 recommended) | all |
| energy | `energy_equals_coenergy`, `energy_vs_flux_linkage` | W = W' within 2 %; W = 1/2 sum I psi within 3 % | static, linear, no magnets (nonlinear: W' >= W is checked instead) |
| saturation | `saturation_steel`, `linear_iron_unphysical_B` | <= 5 % of nonlinear-steel area above `b_limit`; no linear iron (mu_r >= 50) above 2.2 T | steel present |
| boundary | `outer_boundary_far_enough` | max B at the outer boundary <= 2 % of max B (10 % with a mixed/open boundary) | waived for `mi_makeABC` shells and for flux contained by an iron yoke |
| torque | `torque_action_reaction`, `torque_route[...]` | rotor WST torque = -stator WST torque within 5 % | needs `rotor_groups` (+ `stator_groups`); with an air-gap element it reports the gap torque instead |
| force | `force_x_action_reaction`, `force_y_action_reaction` | force on `force_groups` = -force on `reaction_groups` within 5 % (scaled by the force magnitude) | needs both group lists |
| ac | `ac_power_balance` | 1/2 Re(sum V conj I) = total losses (block integral 6) within 5 % | frequency > 0 with circuits |
| flux | `flux_conservation` | the two `flux_lines` cuts carry the same flux within 5 % | needs `flux_lines` |
| pm | `pm_operating_point[...]` | min B_m along magdir >= 0.2 Br per magnet label | magnets present |

Extra rows: `solution_matches_model` fails when the `.ans` on disk does not match the loaded mesh
(re-solve). `summary` = {total, passed, failed, not_applicable, failing, all_ok}; `facts` carries
element count, max B, energy, coenergy, torques, forces, P_in, P_loss.

Known weak spot: when `rotor_groups` and `stator_groups` are complementary, the WST weights of the
two selections are 1 - w of each other, so the torque balance is close to automatic. Virtual work
(`femm_experiment_torque_vs_angle`, `femm_experiment_cogging`) is the independent check.

Rule details, formulas and what a failure usually means: `references/rules.md`.

## Analytic references (femm_estimate)

| Group | Names |
|---|---|
| coils and wires | `solenoid_b_infinite`, `solenoid_b_axis_finite`, `thick_solenoid_b_center`, `loop_b_axis`, `solenoid_inductance_long`, `wire_inductance_per_length`, `straight_wire_b` |
| magnetic circuits | `ccore_gap_b`, `ccore_inductance`, `reluctance`, `maxwell_force`, `carter_coefficient` |
| permanent magnets | `pm_load_line`, `spm_gap_b`, `spm_flux_linkage_fundamental`, `demag_margin` |
| machines | `dq_torque`, `dq_torque_from_inductances`, `emf_from_flux_linkage`, `cogging_period_deg` |
| electrostatics / conduction / AC | `parallel_plate_capacitance`, `coax_capacitance_per_length`, `bar_resistance`, `skin_depth`, `round_wire_internal_impedance` |

All arguments are SI (m, A, T, S/m); FEMM works in problem units and MS/m, so convert. Compare
with `femm_check_rule("compare_to_estimate", {"name": ..., "fem_value": ..., "estimate": ...,
"tolerance": 0.15, "why": "fringing"})`. The expected agreement is the idealisation error of the
formula, not solver precision: C-core gap B 1 %, C-core force 6 %, C-core inductance 1.55x the
formula (fringing and leakage), solenoid centre field 0.7 %, SPM flux linkage 7 %.

## How to report

For every result you hand over, give a short verdict table:

| Verdict | Use when |
|---|---|
| **PASS** | the rule ran and `ok` is true |
| **FAIL** | `ok` is false: give value, expected, tolerance and the likely cause from the message |
| **CHECK** | `ok` is true but the margin is thin, the rule is weak (complementary torque groups), or the FEM vs analytic gap is larger than you can explain |
| **n/a** | `ok` is null: say why (magnets, no circuits, no groups passed) |

Rules: never omit a FAIL or CHECK; never call a model validated when the force/torque rules were
skipped because no groups were passed; say which checks you built yourself with `femm_check_rule`
for non-magnetic physics; quote numbers with units. A result with an unexplained FAIL is a
finding, not a deliverable.

## Toolchain check

`femm_selftest(tolerance_pct=3)`: thick solenoid (a = 10 mm, b = 12 mm, L = 100 mm, 500 turns,
1 A, axisymmetric) vs B0 = mu0 J l ln[(b + sqrt(b^2 + l^2)) / (a + sqrt(a^2 + l^2))]; measured
0.695 % error. It also checks the FEMM 4.2 name error path, current density units (MA/m^2), bulk
getter shapes, circuit results and solve time. Run it when unrelated checks fail together.
