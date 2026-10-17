# FEMM 4.2 -> FEMM 5 magnetic material names

The map used by `femm_material_search` and `femm_material_load(fallback_to_suggestion=True)`
(`femm_agent.materials`); entries whose target is missing from the installed `matlib.dat` are
dropped at load time. "Sintered NdFeB <n> MGOe" and "SmCo <n>" names are matched by pattern to the
nearest grade.

| FEMM 4.2 | FEMM 5 | Notes |
|---|---|---|
| M-14 Steel | M-14 | |
| M-15 Steel | M-15 14 mil | |
| M-19 Steel | M-19 14 mil | `M-19` is the Metals Handbook DC curve (33 points, Sigma 2.03) |
| M-22 Steel | M-22 14 mil | `M-22` also exists |
| M-27 Steel | M-27 14 mil | `M-27` also exists |
| M-36 Steel | M-36 14 mil | |
| M-43 Steel | M-43 18 mil | `M-43 and M-36` also exists |
| M-45 Steel | M-45 18 mil | |
| M-47 Steel | M-47 18 mil | |
| M-50 Steel | M-50 | |
| Pure Iron, Iron | ARMCO Pure Iron | `Pure iron, annealed` is the handbook curve |
| 1004 / 1006 / 1008 / 1010 / 1018 / 1020 / 1030 / 1117 Steel | `<grade> Steel (hot rolled)` | `<grade> Steel (1400°F)` is the annealed curve |
| 416 Stainless Steel | 416 stainless steel, annealed | |
| 304 Stainless Steel, 316 Stainless Steel | unchanged | |
| Alnico 5 | Cast Alnico 5 (LNG40) | LNG37 and LNG44 variants exist |
| Alnico 8 | Cast Alnico 8 (LNGT38) | |
| Ceramic 8 | Ceramic 8A | Ceramic 8B also exists |
| Hiperco-50, Hiperco 50 | CoFe 49Co-2V, magnetic anneal | |
| Silicon Core Iron | 3% Si strip, oriented | |
| NdFeB 32 MGOe | none: nearest N33 (or N30) | 4.2 example files embed it with H_c 883310 A/m, mu 1.045, Sigma 0.694 MS/m, between N30 (836420) and N33 (878619). Ask before substituting. |
| Air, Copper, 18 AWG (and other AWG), Aluminum 1100, Aluminum 6061-T6 | unchanged | |

Caveat (from the index): the 4.2 names come from the 4.2 library as remembered and were checked only
against example `.fem` files shipped with FEMM 5; the 4.2 library is not part of the install.

## Old models that embed their materials

A `.fem` written by FEMM 4.2 carries its materials inside the file, so opening it works even when
the name is no longer in the library (examples such as CoggingTorque.fem embed `M-19 Steel` and
`NdFeB 32 MGOe`). The names only fail when a script calls `mi_getmaterial` on them.
`femm_file_summary(path)` lists the embedded materials with their key values.
