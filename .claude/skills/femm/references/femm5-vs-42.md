# FEMM 5 versus FEMM 4.2: what changed and which habits break

Tags: **[verified]** observed live on FEMM 5.0 build 06oct2026 by this project; **[manual]** stated
in the FEMM 5.0 manual; **[release notes]** from the femm-qt `readme.txt`; **unverified** not
checked. Source of everything here: `femm_facts` (docs/femm5-facts.md).

## At a glance

| Topic | FEMM 4.2 | FEMM 5 | What it means for you |
|---|---|---|---|
| Platforms | Windows only | Qt port: Windows, Linux, macOS (FreeBSD builds) [release notes] | Same tools on every OS; default install paths differ (`femm_status`). |
| Programs | `femm.exe` | `femm_gui`, `femm_headless` (no window), `femm_headlessw.exe` on Windows (no console) [verified] | The suite spawns one headless engine per session. |
| Scripting transport | ActiveX/COM (Windows) | TCP on `127.0.0.1:48015`, one line per request, one line per reply [verified] | Several engines can run at once on different ports. |
| Embedded language | Lua 4 | MicroPython (an embedded Python 3) [manual] | New scripts are Python; Lua survives as `femm-lua` [verified]. |
| Mesher | Triangle | `tangle`, built into each solver [release notes] | Element counts and node positions differ from 4.2 runs of the same model. |
| Solver speed | block-SSOR | whole-matrix incomplete-LDL^T preconditioner, "2-3x faster", bit-deterministic [release notes] | The often-quoted "3-5x" is **unverified**. A 10k-element static solve takes about 0.1-0.25 s [verified]. |
| Material library | 4.2 names | many magnetic entries renamed; 282 / 95 / 136 / 258 materials [verified] | Search before loading (table below). |
| Bulk results | per-element loops | `xo_getallnodes`, `xo_getallelements`, `xo_getallb`, ... [manual][verified] | 10k elements in about 0.1 s; `femm_mesh_arrays`, `femm_field_stats`, `femm_plot_field` are built on them. |
| Air-gap element | see note | Periodic / anti-periodic air-gap boundaries (`BdryFormat` 6 / 7) with `mo_getgapb`, `mo_gapintegral`, `mo_getallgapharmonics` [verified for format 6] | Rotor stepping without re-meshing. Whether it is new relative to your 4.2 build is **unverified** (the FEMM 5 notes cite a 2018 paper). |
| Command names | some long spellings | exactly one underscore after the prefix (`mi_addnode`) [manual] | Old multi-underscore spellings fail. |
| Screenshots | `mo_savebitmap`, `mo_savemetafile` | `savebitmap` writes only from `femm_gui`; headless accepts it and writes nothing; `savemetafile` is a no-op [verified] | Use `femm_plot_field`, or a GUI session for `femm_save_bitmap`. |
| Files | text formats | still plain text; solution starts with a copy of the input [verified] | `femm_file_summary` parses them offline. |
| Licence | freeware | app MIT, solvers GPLv3 [release notes] | This suite talks TCP and redistributes nothing from FEMM. |

## The protocol in one paragraph [verified]

One request is one newline-terminated MicroPython statement or expression; the reply is one line:
the value (tab-separated for several values), an empty line for `None`, or `error:<message>`.
Complex numbers are spelled with a capital `I` (`1+I*2`). Lists of non-numbers are truncated near
256 bytes; a request line longer than the 65536-byte receive buffer is split and the tail is run
as a separate command (keep lines short; use `femm_run_script` for long code). One client per
engine: a second connection gets `femm-qt is already connected to another client`. The headless
engine exits within about 0.5 s of its client disconnecting, and on `quit()`.

## Renamed materials (FEMM 4.2 -> FEMM 5)

`femm_material_search` and `femm_material_load(fallback_to_suggestion=True)` apply this map; it is
checked against the installed `matlib.dat` at load time.

| FEMM 4.2 name | FEMM 5 name | Note |
|---|---|---|
| `M-19 Steel` | `M-19 14 mil` | 61 B-H points, Sigma 1.923 MS/m, d_lam 0.3556 mm. `M-19` alone is the Metals Handbook DC curve. |
| `M-15 Steel`, `M-22 Steel`, `M-27 Steel`, `M-36 Steel` | `M-15 14 mil`, `M-22 14 mil`, `M-27 14 mil`, `M-36 14 mil` | |
| `M-43 Steel`, `M-45 Steel`, `M-47 Steel` | `M-43 18 mil`, `M-45 18 mil`, `M-47 18 mil` | |
| `M-14 Steel`, `M-50 Steel` | `M-14`, `M-50` | |
| `Pure Iron`, `Iron` | `ARMCO Pure Iron` | `Pure iron, annealed` is the handbook curve. |
| `1010 Steel` (and 1004 ... 1117) | `1010 Steel (hot rolled)` | a `(1400°F)` annealed variant also exists. |
| `416 Stainless Steel` | `416 stainless steel, annealed` | |
| `Alnico 5`, `Alnico 8` | `Cast Alnico 5 (LNG40)`, `Cast Alnico 8 (LNGT38)` | |
| `Ceramic 8` | `Ceramic 8A` | |
| `Hiperco-50` | `CoFe 49Co-2V, magnetic anneal` | |
| `Silicon Core Iron` | `3% Si strip, oriented` | |
| `NdFeB 32 MGOe` | none; nearest `N33` (or `N30`) | Embedded copies in old examples have H_c 883310 A/m. Confirm with the user before substituting. |
| `Air`, `Copper`, `18 AWG`, `Aluminum, 1100`, `304 Stainless Steel` | unchanged | |

The 4.2 names came from the 4.2 library as remembered and checked against the example `.fem`
files shipped with FEMM 5; the 4.2 library itself is not in the install. When in doubt, compare
`femm_material_get` of the new name with the values the user expects.

## Script migration checklist

- **Lua 4 script, run once**: `femm_run_lua(path)` runs it unchanged against a fresh engine
  [verified]. To keep using it, port it to MicroPython (`femm-scripting`).
- **pyFEMM script**: runs unchanged inside FEMM (`import femm` resolves to a proxy, `openfemm`/
  `closefemm` become no-ops) [source] except 62 Python-side helpers that the engine lacks:
  `mo_getb`, `mo_geta`, `mo_geth`, `mo_getj`, `mo_getmu`, ... (point-value slices), `*_hidenames`,
  `*_snapgridon/off`, `*_smoothon/off`, `mi_setcurrent`, `mi_addbhpoints`, `hi_addtkpoints`. Over
  the wire they answer `name 'mo_getb' isn't defined` [verified]. Replace with
  `mo_getpointvalues` (14 values) or `femm_point_values`.
- **Standalone pyFEMM** finds the engine only through `FEMM_DIR` [verified];
  `femm_export_pyfemm_script` writes that default for you.
- **Material names**: run every `mi_getmaterial("...")` name through `femm_material_search`.
- **`*_getnodeindex` / `*_getelementindex`** were removed (2026-08-29) [source].
- **Saving before analysis** is enforced: `File must be saved before analysis` [verified].
- **`mi_createmesh()`** returns nothing over IPC; element counts come from `mo_numelements` after a
  solve [verified].
