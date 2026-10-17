---
name: femm-geometry
description: Drawing and editing FEMM 5 geometry through the femm MCP tools (femm_*) - drawing strategy with nodes, segments and arcs, closed regions and block labels, selecting objects by coordinates, groups, copy/rotate/mirror for slots, teeth and poles, DXF import and export, symmetry sectors with periodic boundaries, open boundaries, mesh size control and the common meshing failures. Use when the user wants to draw or import a 2D cross-section in FEMM, build a motor lamination, replicate slots, move or rotate a part, mesh a model, or fix "a region has no material assigned" and other mesh errors.
---

# FEMM geometry: draw, select, replicate, mesh

FEMM geometry is a planar straight-line graph: **nodes**, **segments** between nodes, **arcs**
between nodes, and **block labels** that mark each closed region with its properties. The mesher
(`tangle`, inside each solver) triangulates every closed region that has a label.

## Drawing strategy

1. Set the units first (`femm_problem_define`); every coordinate is in problem units.
   Axisymmetric: x = r >= 0, y = z; nothing may cross to r < 0.
2. Draw closed outlines with the shape tools; FEMM reuses a node that already exists at the same
   place, and splits segments that cross at the intersection. Shared edges are drawn once.
   - `femm_draw_rectangle(x1, y1, x2, y2)`; `femm_draw_polygon([[x, y], ...])` (closes back to the
     first point; the returned `vertex_centroid` is a valid label point only for convex shapes);
     `femm_draw_polyline` (open); `femm_draw_circle(cx, cy, r, maxseg)` (four 90-degree arcs).
   - `femm_add_arcs([[x1, y1, x2, y2, angle, maxseg], ...])`: counter-clockwise from point 1 to
     point 2, `0 < angle <= 180`; `maxseg` is the degrees per straight piece (1 fine, 5-10 coarse,
     <= 1 in air gaps).
3. Give **every closed region exactly one** block label (`femm_add_block_label`), including the air
   around the device. Holes that should not be meshed get the material `"<No Mesh>"` (saved as a
   hole, not a label).
4. Add the outer boundary (an A = 0 / fixed-potential box 3-5x the device, or
   `femm_call("mi_makeABC", [n, R, x, y, 0])` in magnetics).
5. `femm_geometry_summary` before meshing: node/segment/arc/label/hole counts, defined materials,
   boundaries and circuits, bounding box. FEMM 5 has no pre-processor count getters, so this tool
   saves the model and reads the file.

## Selecting by coordinates

Selections pick the object **nearest** to a point, so give a point that is unambiguously on the
object: the midpoint of a segment, a point on an arc away from its ends, a point inside a region
for its label.

| Need | Call |
|---|---|
| specific segments / arcs / nodes / labels | `femm_select(kind="segments", points=[[x, y], ...])` (also `arcs`, `nodes`, `labels`) |
| everything in a box | `femm_select(kind="rectangle", rectangle=[x1, y1, x2, y2], entities="all")` |
| everything in a circle | `femm_select(kind="circle", circle=[cx, cy, R])` |
| a group | `femm_select(kind="group", group=n)` |

`femm_select` clears the previous selection first (`clear_first=True`); pass `clear_first=False` to
add to it. The tools that assign properties by points (`femm_set_segment_prop`,
`femm_set_arc_prop`, `femm_set_node_prop`, the `segments`/`arcs` arguments of `femm_add_boundary`)
select, set and clear in one call. Each pick returns the coordinates FEMM picked: compare them with
what you meant.

## Groups

`femm_set_group(n)` puts the current selection in group n. Use groups for: parts that move
(experiments rotate or translate whole groups), block integrals over a part
(`femm_block_integral(group=[n])`), per-material field statistics (`femm_field_stats(region=
"group:n")`), and the health check's force/torque balances. Put the nodes, edges **and** the label
of a moving part in its group (a rectangle or circle selection catches them all). Group 0 is the
default for everything.

## Replicating slots, teeth and poles

Draw one slot (or pole), put it in a group, then copy-rotate the group:

```
femm_select(kind="rectangle", rectangle=[...], entities="all")
femm_set_group(5)
femm_select(kind="group", group=5)
femm_copy_selected(rotate_deg=360/Q, copies=Q-1, about=[0, 0], entities="group")
```

Always pass `entities` to move/copy/mirror/scale: FEMM's own default is ambiguous (the manual says
"current edit mode", the engine source uses 4 = group). If the slot's label is part of the selection it is copied too (whether its properties come along
is unverified): check the copies with `femm_geometry_summary` and set phases, turns and signs with
`femm_set_block_prop`. `femm_mirror_selected` copies about a line;
`femm_move_selected(rotate_deg=a, about=[0, 0], entities="group")` rotates a rotor.

Rotating a group by +a and back by -a leaves node coordinates rounded slightly differently (one
re-meshed model had 9786 instead of 9676 elements): re-solve after restoring geometry before
comparing numbers.

## DXF import and export

```
femm_import_dxf("drawing.dxf", tolerance=0.01)   # merge nodes closer than 0.01 problem units
femm_geometry_summary()                          # did regions close?
```

FEMM reads DXF revision 13 entities. The DXF carries no labels: add one per region afterwards, and
check for gaps and duplicate lines (a nonzero `tolerance` merges near-coincident nodes). Set `femm_problem_define(units=...)` to the drawing's units
before importing (how FEMM scales DXF units is unverified: check `bounding_box`).
`femm_export_dxf(path)` writes the current geometry.

## Symmetry

- A flux-parallel symmetry line in magnetics is an A = 0 (`prescribed_a`) boundary; a
  flux-normal line needs no boundary (the natural condition; standard FE practice, not checked
  live here). The same idea holds for the
  potentials of the other physics.
- Machines: model one or more pole pairs with `periodic` boundaries on the two sector edges (even
  number of poles in the sector) or `antiperiodic` (odd). Use one boundary property per pair of
  edges and assign it to both. This project did not exercise periodic sector models live: compare
  one sector against the full model once before relying on it.
- Axisymmetric models are a symmetry in themselves; do not put a boundary on the axis.

## Mesh size control

Mesh size lives on block labels (`mesh_size`, None = automatic), on segments
(`femm_set_segment_prop(mesh_size=...)`), on arcs (`max_seg_deg`) and on nodes (an undocumented
third argument of `mi_setnodeprop`, reachable through `femm_call`). Quality is the `min_angle` of
`femm_problem_define` (30 degrees default). Smart mesh (`femm_smartmesh`) refines near small
features automatically; turning it off cut the SPM benchmark from 33.5k to 9.7k elements with
the same gap field (0.2 %) and flux linkage (0.2 %), then set sizes explicitly.

Rules of thumb used by the benchmarks: at least 3 element layers across an air gap where forces
or torques are computed (0.5 mm in a 1.5 mm gap); conductor mesh below the skin depth at AC;
coarse far-field air. Meshing details and failures: `references/meshing.md`.
