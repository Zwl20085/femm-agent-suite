# The feedback ladder in detail

Climb it in order; each rung is cheap in FEMM. Thresholds are the defaults of the health rules in
`femm_agent.health` (see skill `femm-health-check` for every rule).

## Rung 1: the call

- `ok: false` -> read `error.message` and `error.hint`; the hint is written as the next action.
- `femm_call` returns `warnings` from the catalog (wrong arity, unknown name, pyFEMM-only helper).
  Treat a warning as a likely bug even when the call succeeded.
- `femm_problem_define` warns when `depth` was not given for a planar model.
- `femm_material_load` lists `failed` names with suggestions, and `renamed` when it substituted.

## Rung 2: the model before meshing

`femm_geometry_summary` (it saves the file and reads it back):

| Look at | Normal | Abnormal means |
|---|---|---|
| `block_labels` + `holes` | equals the number of closed regions | a region without a label stops the solver; two labels in one region make its material ambiguous (FEMM's choice unverified) |
| `materials` | only the ones you meant | a leftover custom material, a 4.2 name |
| `circuits` | each coil's circuit | a coil label without a circuit carries no current |
| `boundaries` | the outer boundary (and AGE, periodic pairs) | no outer boundary assigned: the outer edge keeps the solver's default condition, which is not an open boundary |
| `bounding_box` | the device plus the air box | a stray node far away |

`femm_file_summary(path)` gives the same and more (net turns per circuit, magnets, groups)
offline.

## Rung 3: the solve

`femm_solve` reports `elements`, `nodes`, `solve_seconds`.

| Signal | Normal | Abnormal |
|---|---|---|
| elements | 1 000 - 200 000 for 2D | < 1 000: WST forces need several element layers in the gap; > 200 000: slow, use symmetry or coarser far field |
| solve time | 0.1-1 s for 10k static elements | minutes for small static models: check for very fine mesh sizes or smart mesh on a detailed model |
| errors | none | `a region has no material assigned`, `File must be saved`, mesh errors: see `femm-troubleshooting` |

## Rung 4: physics invariants

`femm_health_check(...)`; pass the groups so the force/torque rules can run:

- actuators: `force_groups=[moving]`, `reaction_groups=[everything else that carries force]`
- machines: `rotor_groups=[rotor]`, `stator_groups=[stator, coils]`
- flux paths: `flux_lines=[[p1, p2], [p3, p4]]` across two cuts that carry the same flux

Read `summary.failing` first, then every check's `message`. The energy identities (W = W' and
W = 1/2 sum I psi) only apply to linear models without magnets; the rule says "not applicable"
otherwise.

## Rung 5: hand estimates

`femm_estimate` with the device's numbers in SI units. Agreement is expected within the
idealisation, not to solver precision:

| Quantity | Measured FEM vs formula | Why they differ |
|---|---|---|
| C-core gap B | 0.238 vs 0.2405 T | fringing spreads gap flux |
| C-core force | -9.74 vs -9.21 N | fringing, leakage |
| C-core L | 7.47 vs 4.81 mH | the formula ignores fringing and slot leakage |
| solenoid centre B | +0.7 % | finite mesh and boundary |
| SPM gap B | 0.862 vs 0.843 T | flat-gap approximation |
| SPM psi_pm | 47.6 vs 51.0 mWb | flat gap, no leakage, ideal steel (builder note: FEM typically 5-15 % lower) |

A disagreement larger than the idealisation can explain is a FAIL until you understand it.

## Rung 6: look at it

`femm_plot_field(zoom=[xmin, xmax, ymin, ymax])` writes a |B| map from the mesh arrays (headless).
Look for flux in the intended path, no strong field in the far air, saturation only where
expected, magnets pointing the right way. `femm_field_stats(region="group:N")` puts numbers on
the same questions (peak, p95, saturated area fraction above 1.6 T).

## Rung 7: the toolchain

`femm_selftest` after an install change or when several unrelated things fail at once.
