---
name: femm-materials
description: Choosing and defining materials in FEMM 5 through the femm MCP tools (femm_*) - searching the four FEMM 5 libraries (282 magnetic, 95 electrostatic, 136 thermal, 258 conduction materials), the FEMM 4.2 to FEMM 5 rename map (M-19 Steel -> M-19 14 mil, Pure Iron -> ARMCO Pure Iron, no NdFeB 32 MGOe), custom linear and nonlinear B-H materials, permanent magnets (H_c, magnetisation direction, grade conversion), lamination settings, magnet wire and litz, and the MS/m vs S/m conductivity pitfall. Use whenever a FEMM model needs a material, a material name fails with "Couldn't load ... from the materials library", or the user asks for steel, magnet, copper, insulation or thermal properties in FEMM.
---

# FEMM materials: find the right name, then load it

## Rule zero: search, then load

FEMM 5 renamed many magnetic library entries, and FEMM raises
`Couldn't load "<name>" from the materials library` for an unknown name. So:

```
femm_material_search("M-19 Steel")         # offline; maps the 4.2 name, ranks M-19 14 mil first
femm_material_get("M-19 14 mil", include_curve=False)   # check Mu, Sigma, d_lam, B-H points
femm_material_load(["Air", "Copper", "M-19 14 mil", "N42"])
```

`femm_material_load(..., fallback_to_suggestion=True)` loads the best suggestion instead of
failing and reports `renamed` (use those names on block labels). Prefer an explicit search: a
silent substitution of a steel or magnet grade changes the answer.

## The libraries

| Library | Physics | Materials | Search with `physics=` |
|---|---|---|---|
| `matlib.dat` | magnetics | 282 | `"magnetics"` |
| `statlib.dat` | electrostatics | 95 | `"electrostatics"` |
| `heatlib.dat` | heat flow | 136 | `"heatflow"` |
| `condlib.dat` | current flow | 258 | `"currentflow"` |

`femm_material_search("")` with no query returns the family index. Magnetic families include: Air,
M-grade silicon steel, cold-rolled lamination sheet, low-carbon steel (AISI 10xx), pure iron,
stainless steel, CoFe, nickel/permalloy, amorphous (Metglas), NdFeB sintered and bonded, SmCo,
Alnico, ceramic (US and CN grades), solid conductors, round copper magnet wire (AWG/SWG/mm),
copper-clad aluminium wire.

Name details that trip agents: wire gauges are `"18 AWG"` (space) but CCA wire is
`"18AWG 10% CCA"`; some names carry a degree sign (`1010 Steel (1400°F)`); `Ammonia` appears twice
in heatlib in different folders (names alone are not unique there).

FEMM 4.2 names and their FEMM 5 equivalents: `references/legacy-names.md`.

## What the library record means (magnetics)

`femm_material_get` returns the `.dat` keys:

| Key | Meaning | Unit |
|---|---|---|
| `Mu_x`, `Mu_y` | relative permeability (ignored when B-H points exist) | - |
| `H_c`, `H_cAngle` | coercivity (magnets) | A/m |
| `J_re`, `J_im` | source current density | MA/m^2 |
| `Sigma` | electrical conductivity | **MS/m** |
| `d_lam`, `LamFill`, `LamType` | lamination thickness, fill factor, type | mm, 0..1, code |
| `Phi_h`, `Phi_hx`, `Phi_hy` | hysteresis lag angle | degrees |
| `BHPoints` + `BH_curve` | nonlinear curve [B (T), H (A/m)] | |
| `WireD`, `NStrands` | wire diameter, strands | mm, - |

Values measured on build 06oct2026: `M-19 14 mil` is nonlinear (61 B-H points, Sigma 1.923 MS/m,
d_lam 0.3556 mm); `M-19` is the Metals Handbook DC curve (33 points, Sigma 2.03); `N42` is
**linear** (no B-H points); `Copper` is 58 MS/m.

## Custom materials

```
femm_material_add("Iron2000", mu_x=2000)                         # linear iron
femm_material_add("MySteel", sigma=2.0, lam_d=0.35, lam_fill=0.97, lam_type=0)
femm_material_add_bh("MySteel", [[0, 0], [1.0, 200], [1.5, 1000], [1.8, 8000], [2.0, 40000]])
```

`femm_material_add` takes the arguments of the current physics only (`mu_x mu_y h_c j sigma lam_d
phi_hmax lam_fill lam_type phi_hx phi_hy n_strands wire_d` for magnetics, the full 14-argument
`mi_addmaterial`). A B-H curve starts at [0, 0] with B and H strictly increasing;
`femm_material_add_bh` warns when it is not. `lam_type` codes as documented in the tool: 0 none,
1 laminated along x, 2 along y, 3 magnet wire, 4 stranded, 5 litz, 6 square wire.

Heat flow: `femm_material_add(k_x=, k_y=, qv=, kt=)` and `femm_material_add_bh(name, [[T, k], ...])`
for temperature-dependent conductivity. Electrostatics: `eps_x`, `eps_y`, `qv`. Current flow:
`sigma_x`, `sigma_y` in **S/m**, `eps_x`, `eps_y`, `ltx`, `lty`.

## Permanent magnets

- A linear magnet is `mu_x` (recoil permeability, about 1.05 for NdFeB) plus `h_c` (A/m); then
  Br = mu0 mu_r H_c. The SPM benchmark's N42 has mu_r 1.05 and H_c 994529 A/m, so Br = 1.312 T.
- From a grade or datasheet: `femm_units_convert("hc_from_br", 1.3, mu_r=1.05)`,
  `femm_units_convert("br_from_mgoe", 42)`, `"hc_from_mgoe"`, `"oersted_to_a_per_m"`.
- The direction is a property of the **block label**, not of the material:
  `femm_add_block_label(x, y, "N42", magdir=90)` magnetises towards +y (degrees from +x). A radial
  or other spatially varying direction needs a formula string in `mi_setblockprop`, reachable with
  `femm_call` (the experiment tools skip labels with a formula when computing operating points).
- Check the operating point after solving: `femm_experiment_bh_check()` (B_m, H_m, Pc, B_m/Br;
  flags min B_m < 0.2 Br).
- Temperature effects (Br drop, H_c drop) are not modelled by a linear library entry: change
  `h_c` with `femm_material_modify` for a hot case.

## Changing materials between solves

`femm_material_modify("N42", {"h_c": 900000})` or `{"mu_x": 1500, "sigma": 0}`; re-solve
afterwards. Verified property indices: 1 mu_x, 5 sigma, 8 lamination fill (and 4 accepted); the
others follow the `mi_addmaterial` argument order and are unverified. To swap a region's material,
`femm_set_block_prop(x, y, "<other material>")` (it must be loaded first).

## Conductivity units: the factor-of-a-million bug

| Where | Unit | Copper |
|---|---|---|
| magnetics `sigma`, library `Sigma` | MS/m | 58 |
| current flow `sigma_x`, `sigma_y` | S/m | 5.8e7 |
| `femm_estimate` (`skin_depth`, `bar_resistance`, `round_wire_internal_impedance`) | S/m | 5.8e7 |
| magnetic current density `j`, `J_source` | MA/m^2 | |

Convert explicitly whenever a number crosses one of these boundaries, and say which unit you used.
