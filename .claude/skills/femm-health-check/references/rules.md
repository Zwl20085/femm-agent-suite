# Health rules: formulas, defaults, usual causes of failure

All rules live in `femm_agent.health` (pure functions, unit tested). `femm_check_rule(rule, args)`
runs any of the ones listed here on your own numbers.

| Rule (`femm_check_rule` name) | Formula / test | Default tolerance | Usual cause of a FAIL |
|---|---|---|---|
| `energy_consistency` | W = 1/2 sum I_k psi_k | 3 % | a current-carrying region outside every circuit; outer boundary too close; coarse coil mesh |
| `energy_coenergy_linear` | W = W' (codes 2 and 17), linear without magnets | 2 % | a nonlinear material is active in a "linear" model |
| `flux_conservation` | abs(flux in) = abs(flux out); planar flux across a cut = (A(P2) - A(P1)) x depth | 5 % (+ allowed leakage) | leakage, or a cut that crosses a different branch |
| `saturation` | area fraction of steel with B > b_limit | <= 5 % above 1.8 T | too many ampere-turns, wrong magnet grade, intended saturation (then report it) |
| `linear_material_overflux` | max B in linear iron | <= 2.2 T | linear iron hides saturation: use a library B-H steel |
| `mesh_size` | element count | 1 000 .. 200 000 | coarse gap (forces noisy) / needless refinement |
| `mesh_quality` | share of triangles with min angle < 10 deg | <= 0.1 % | tiny edges, near-coincident nodes |
| `solver_precision` | probdef precision | <= 1e-6 | loose precision makes forces and torques noisy |
| `boundary_distance` | max B at the outer boundary / max B | <= 2 % (x5 for open/mixed) | air box too small: make it 3-5x the device or use `mi_makeABC` |
| `force_consistency` | two estimates of one force or torque agree | 5 % | gap mesh too coarse; the selected group is wrong (air in the group) |
| `curve_consistency` | RMS(a - b) / peak of two sampled curves | 8 % | step too coarse for the virtual-work derivative; mesh noise |
| `torque_ripple` | peak-to-peak / mean | informational | |
| `zero_mean` | mean / peak of cogging | 5 % | a current left on; sweep not a whole number of periods |
| `power_balance` | 1/2 Re(sum V conj I) = losses | 5 % | a conductor outside every circuit; an eddy region not counted |
| `skin_depth_resolution` | skin depth / element size | >= 1 | conductor mesh coarser than the skin depth |
| `pm_operating_point` | B_m / Br per magnet | >= 0.2 | thin magnet, big gap, strong d-axis current |
| `compare_to_estimate` | relative difference FEM vs formula | 15 % | wrong units, wrong formula, or a modelling error; the idealisation can explain only so much |

Experiments add their own named checks built from these (for example
`force_wst_vs_virtual_work`, `cogging_vs_virtual_work`, `three_phase_balance`,
`half_wave_antisymmetry`, `mutual_reciprocity`, `torque_fem_vs_dq`, `mean_torque_vs_dq`,
`ac_power_balance[<f> Hz]`, `R_vs_analytic[<f> Hz]`, `parametric_errors`).

## Measured margins (build 06oct2026)

- C-core: W = W' = 1/2 L I^2 to all printed digits (0.0149452 J at 2 A); left/right gap flux 0.3 %;
  WST vs virtual work 1.6 % RMS.
- Coilgun (axisymmetric): WST vs virtual work 5 %.
- SPM cogging: WST vs dW'/dtheta 6.6 % RMS with 2 degree steps; rotate vs air-gap element 0.3 %;
  mutual inductances reciprocal to 0.4 %.
- Round wire AC: power balance 0.00 %.
- Thick solenoid self-test: 0.695 %.
- Electrostatics, heat and current-flow spot checks: within 1 %.

## Things the rules cannot see

- A wrong but self-consistent model (wrong material, wrong turns, wrong depth) passes every
  invariant. Only the analytic estimate and a review of `femm_file_summary` catch it.
- Inside `mi_makeABC` shells the field is not physical; do not judge field decay there.
- The WST block integral does not see across an air-gap element (reads about 1e-16 N*m); the health
  check reports the gap torque instead.
