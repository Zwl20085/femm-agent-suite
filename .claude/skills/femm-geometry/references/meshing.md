# Meshing: control and failures

## How to mesh

- `femm_create_mesh()` meshes without solving to prove the geometry meshes. It saves the model
  first (`mi_createmesh` on an unsaved model fails with `File must be saved before creating mesh`)
  and returns **no element count** in FEMM 5.
- `femm_solve()` meshes, solves and reports `nodes` and `elements`. A 10k-element magnetostatic
  solve takes 0.1-0.25 s, so solving is a cheap way to test meshing.
- Counts after a solve: `femm_problem_info` (nodes, elements), and the triangle quality is in the
  `mesh` rule of `femm_health_check` (worst angle, share of slivers below 10 degrees).

## Size controls

| Where | Tool | Unit |
|---|---|---|
| region | `femm_add_block_label(mesh_size=h)` / `femm_set_block_prop` | problem units; None or 0 = automatic |
| edge | `femm_set_segment_prop(points, mesh_size=h)` | problem units |
| arc | `femm_set_arc_prop(points, max_seg_deg=d)`, or `maxseg` in `femm_add_arcs` / `femm_draw_circle` | degrees per straight piece |
| node | `femm_call("mi_setnodeprop", ["<None>", 0, h])` after selecting the node | problem units (third argument undocumented, accepted by the engine) |
| quality | `femm_problem_define(min_angle=30)` | degrees |
| automatic refinement | `femm_smartmesh("on"/"off", scope="document"/"global")` | |

Element budget: the health rule flags fewer than 1 000 elements (stress-tensor forces need
several element layers in the gap) and more than 200 000 (slow; use symmetry or a coarser far
field).

## Failures and fixes

| Message or symptom | Cause | Fix |
|---|---|---|
| `Solver failed: a region has no material assigned ... (exit code 10)` | a closed region without a block label: often the air, a hole, or the annulus of an air-gap element | `femm_geometry_summary` to count labels; add one (`"<No Mesh>"` for holes and for the AGE annulus) |
| `File must be saved before creating mesh` / `before analysis` | raw `mi_createmesh` / `mi_analyze` on an unsaved model | use `femm_create_mesh` / `femm_solve` (they save), or `femm_save` first |
| mesh error mentioning the mesher or triangulation | overlapping or duplicate segments, an outline that does not close, a label outside every region, nodes almost on top of each other | redraw the region; for DXF imports pass a `tolerance`; delete stray objects with `femm_select` + `femm_delete_selected` |
| many slivers (worst angle < 10 degrees) | tiny edges, near-coincident nodes, a very thin region | remove the tiny feature, or merge nodes; raise `min_angle` only after that |
| element count explodes | smart mesh on a detailed model; very small `mesh_size` | `femm_smartmesh("off")` and explicit sizes |
| forces or torques noisy between steps | too few elements across the gap; loose precision | finer gap mesh (>= 3 layers), precision 1e-8 |
| after rotating back, results differ slightly | rounding of rotated node coordinates changes the mesh | re-solve after restoring geometry |

When `ok: false` comes back from `femm_solve`, read `error.hint`: the server maps the FEMM
message to the next action. The full error list is in `femm-troubleshooting`.
