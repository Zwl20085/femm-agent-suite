# FEMM 5 scripting command catalog: summary

Generated alongside `data/commands.json` (677 entries). Sources: the FEMM 5.0 manual (scripting chapters 3.5 to 3.13), the pyFEMM binding `femm.py` (`FemmSession`), the femm-qt engine source (`libfemm/py_*.cpp`), and live probes against `femm_headless.exe` v5.0 06Oct2026 (see "How this was verified").

## Counts

### Per physics and phase

| physics | pre | post | common | total |
|---|---:|---:|---:|---:|
| common | 0 | 0 | 17 | 17 |
| magnetics | 94 | 82 | 0 | 176 |
| electrostatics | 89 | 72 | 0 | 161 |
| heatflow | 92 | 71 | 0 | 163 |
| currentflow | 89 | 71 | 0 | 160 |
| **all** | 364 | 296 | 17 | 677 |

The totals include (a) 62 pyFEMM-only convenience names, (b) 30 undocumented engine aliases such as `mo_showdensity` and `eo_getconductorprops`, and (c) British-spelling `*_analyse` aliases. Documented-in-manual commands: 565.

### Per physics and category

| category | common | magnetics | electrostatics | heatflow | currentflow | total |
|---|---:|---:|---:|---:|---:|---:|
| document | 6 | 10 | 10 | 10 | 10 | 46 |
| problem | 0 | 5 | 4 | 4 | 4 | 17 |
| geometry | 0 | 20 | 20 | 20 | 20 | 80 |
| selection | 0 | 18 | 20 | 20 | 20 | 78 |
| properties | 0 | 11 | 11 | 11 | 11 | 44 |
| materials | 0 | 7 | 4 | 7 | 4 | 22 |
| boundaries | 0 | 5 | 5 | 5 | 5 | 20 |
| circuits | 0 | 5 | 0 | 0 | 0 | 5 |
| conductors | 0 | 0 | 5 | 5 | 5 | 15 |
| mesh | 1 | 4 | 4 | 4 | 4 | 17 |
| solve | 0 | 3 | 3 | 3 | 3 | 12 |
| view | 4 | 43 | 43 | 43 | 43 | 176 |
| point_values | 0 | 14 | 6 | 5 | 5 | 30 |
| integrals | 0 | 4 | 2 | 2 | 2 | 10 |
| bulk_getters | 0 | 11 | 8 | 8 | 8 | 35 |
| plotting | 0 | 11 | 11 | 11 | 11 | 44 |
| export | 0 | 5 | 5 | 5 | 5 | 20 |
| misc | 6 | 0 | 0 | 0 | 0 | 6 |

### Per physics, split by provenance

| physics | in manual | engine-only (not in manual, not a pyFEMM convenience) | pyFEMM-only | total |
|---|---:|---:|---:|---:|
| common | 9 | 8 | 0 | 17 |
| magnetics | 146 | 9 | 21 | 176 |
| electrostatics | 136 | 11 | 14 | 161 |
| heatflow | 138 | 11 | 14 | 163 |
| currentflow | 136 | 11 | 13 | 160 |

## Differences between sources

### In the manual, no pyFEMM method (reachable with `callfemm("...")`)

`clearconsole`, `open`, `print`, `quit`, `mo_setfocus`, `ei_getboundingbox`, `eo_setfocus`, `hi_getboundingbox`, `ho_setfocus`, `ci_getboundingbox`, `co_setfocus`

Note `open`, `quit`, `print`, `clearconsole` are plain globals; pyFEMM covers them with `opendocument()`, `closefemm()`/`close()` and nothing for the other two.

### In pyFEMM and in the engine, not in the manual

`AWG`, `main_maximize`, `main_minimize`, `main_resize`, `main_restore`, `opendocument`, `mi_analyse`, `mi_getprobleminfo`, `mi_newdocument`, `ei_analyse`, `hi_analyse`, `ci_analyse`

`*_analyse` are real engine aliases of `*_analyze`. `mi_getprobleminfo` and `mi_newdocument` exist in the engine for all four preprocessors (`ei_/hi_/ci_` variants have no pyFEMM method). `main_*` act on the main window (GUI build). `AWG` is a script-side helper.

### In the engine only (neither manual nor pyFEMM)

`getcurrentdirectory`, `setcurrentdirectory`, `mo_hidecontour`, `mo_hidedensity`, `mo_showcontour`, `mo_showdensity`, `mo_smoothing`, `mo_vectorplot`, `ei_getprobleminfo`, `ei_newdocument`, `eo_getconductorprops`, `eo_hidecontour`, `eo_hidedensity`, `eo_selectline`, `eo_showcontour`, `eo_showdensity`, `eo_smoothing`, `eo_vectorplot`, `hi_getprobleminfo`, `hi_newdocument`, `ho_getconductorprops`, `ho_hidecontour`, `ho_hidedensity`, `ho_selectline`, `ho_showcontour`, `ho_showdensity`, `ho_smoothing`, `ho_vectorplot`, `ci_getprobleminfo`, `ci_newdocument`, `co_getconductorprops`, `co_hidecontour`, `co_hidedensity`, `co_selectline`, `co_showcontour`, `co_showdensity`, `co_smoothing`, `co_vectorplot`

Most are short-form aliases that resolve to documented commands (`xo_hidedensity` -> `xo_hidedensityplot`, `xo_showdensity`, `xo_showcontour`, `xo_hidecontour`, `xo_vectorplot` -> `xo_showvectorplot`, `xo_smoothing` -> `xo_smooth`, `xo_selectline` -> `xo_selectpoint`, `xo_getconductorprops` -> `xo_getconductorproperties`), taken from `m.alias(...)` in `libfemm/py_*_postproc.cpp`. `setcurrentdirectory`/`getcurrentdirectory` are mentioned in manual text (sections 3.2, 3.3) but not given a command entry.

### pyFEMM-only convenience names (62)

These exist only as Python methods in `femm.py` and do NOT exist in the engine (live check: `NameError` for all of them after opening a document). They are thin wrappers over real commands, so an MCP server should implement them itself or skip them.

- Point-value slices of `*_getpointvalues` (23): `mo_geta`, `mo_getb`, `mo_getconductivity`, `mo_getenergydensity`, `mo_getfill`, `mo_geth`, `mo_getj`, `mo_getmu`, `mo_getpe`, `mo_getph`, `eo_getd`, `eo_gete`, `eo_getenergydensity`, `eo_getperm`, `eo_getv`, `ho_getf`, `ho_getg`, `ho_getk`, `ho_gett`, `co_gete`, `co_getj`, `co_getk`, `co_getv`
- `*_hidenames` -> `*_shownames(0)` (8): `mi_hidenames`, `mo_hidenames`, `ei_hidenames`, `eo_hidenames`, `hi_hidenames`, `ho_hidenames`, `ci_hidenames`, `co_hidenames`
- `*_snapgridon/off` -> `*_gridsnap("on"/"off")` (16): `mi_snapgridoff`, `mi_snapgridon`, `mo_snapgridoff`, `mo_snapgridon`, `ei_snapgridoff`, `ei_snapgridon`, `eo_snapgridoff`, `eo_snapgridon`, `hi_snapgridoff`, `hi_snapgridon`, `ho_snapgridoff`, `ho_snapgridon`, `ci_snapgridoff`, `ci_snapgridon`, `co_snapgridoff`, `co_snapgridon`
- `xo_smoothon/off` -> `xo_smooth("on"/"off")` (8): `mo_smoothoff`, `mo_smoothon`, `eo_smoothoff`, `eo_smoothon`, `ho_smoothoff`, `ho_smoothon`, `co_smoothoff`, `co_smoothon`
- `xo_snapgrid(flag)` -> `xo_gridsnap(flag)` (4): `mo_snapgrid`, `eo_snapgrid`, `ho_snapgrid`, `co_snapgrid`
- Looping helpers and others (3): `mi_setcurrent`, `mi_addbhpoints`, `hi_addtkpoints`

The doc `pyfemm-inprocess-compat.md` says "62" and tabulates 24 point accessors plus 36 spellings; counting its own tables literally gives 23 accessors (10 mo, 5 eo, 4 ho, 4 co) + 36 spellings. The 62 here is 23 + 36 + `mi_setcurrent` + `mi_addbhpoints` + `hi_addtkpoints`. `*_getnodeindex` / `*_getelementindex` were removed from femm-qt on 2026-08-29 and do not appear in this catalog or in `femm.py`.

Not commands at all, so excluded from the catalog: `openfemm`, `closefemm`, `callfemm`, `callfemm_noeval`, `close` (session lifecycle), `showpointprops`/`hidepointprops` (no-op stubs), `num/numc/quote/quotec/doargs/_fixpath/_find_exe` (helpers), `IEC` (wire-gauge helper like `AWG`).

## Argument-order and arity pitfalls

All arities below were confirmed live against femm_headless v5.0 06Oct2026 by calling with increasing numbers of arguments (the engine rejects too many; many trailing arguments are optional).

| command | positional signature | pitfall |
|---|---|---|
| `mi_probdef` | (frequency, units, type, precision, depth?, minangle?, acsolver?) = 7 | frequency is FIRST. units: "inches","millimeters","centimeters","mils","meters","micrometers"; type: "planar"|"axi". precision is clamped to <= 1e-8 by the engine. |
| `ei_probdef` | (units, type, precision, depth?, minangle?) = 5 | no frequency at all. |
| `hi_probdef` | (units, type, precision, depth?, minangle?, prevsoln?, timestep?) = 7 | last two are transient-analysis inputs (previous-step solution file, step length). No frequency. |
| `ci_probdef` | (units, type, frequency, precision, depth?, minangle?) = 6 | frequency is THIRD here (unlike mi_probdef). |
| `mi_setblockprop` | ("blockname", automesh, meshsize, "incircuit", magdirection, group, turns) = 7 | automesh=1 makes the mesher ignore meshsize; magdirection may be a string formula; circuit name is a string ("<None>" for none). The ei_/hi_/ci_ versions have only 4 arguments ("blockname", automesh, meshsize, group). |
| `mi_setsegmentprop` | ("propname", elementsize, automesh, hide, group) = 5 | ei/hi/ci add a 6th, "inconductor". mi_setarcsegmentprop has maxsegdeg FIRST: (maxsegdeg, "propname", hide, group[, "inconductor"]). |
| `mi_setnodeprop` | ("propname", groupno[, lfs])  | manual lists 2 arguments; the engine accepts an undocumented 3rd (lfs, local mesh size, number). ei/hi/ci take ("propname", groupno, "inconductor"). |
| `mi_addboundprop` | ("name", A0, A1, A2, Phi, Mu, Sig, c0, c1, BdryFormat, ia, oa) = 12 incl. name (11 parameters) | the brief said 10; the manual and the engine both accept up to 12 (live: accepts 1..12). A 10-argument call still works because the last two are optional. BdryFormat: 0 prescribed A, 1 small skin depth, 2 mixed, 3 strategic dual image, 4 periodic, 5 anti-periodic, 6 periodic air gap, 7 anti-periodic air gap. Unused parameters must be 0. |
| `ei_addboundprop / ci_addboundprop` | ("name", Vs, qs, c0, c1, BdryFormat) = 6 | BdryFormat: 0 fixed voltage, 1 mixed, 2 surface charge (or current) density, 3 periodic, 4 anti-periodic. |
| `hi_addboundprop` | ("name", BdryFormat, Tset, qs, Tinf, h, beta, TinfRad) = 8 | BdryFormat is the SECOND argument, ahead of the values (opposite of ei/ci). 0 fixed T, 1 heat flux, 2 convection, 3 radiation, 4 periodic, 5 anti-periodic. |
| `mi_addmaterial` | ("name", mu_x, mu_y, H_c, J, Cduct, Lam_d, Phi_hmax, lam_fill, LamType, Phi_hx, Phi_hy, NStrands, WireD) = 14 incl. name (13 properties) | the brief said 13; live engine accepts 1..14. J is complex (MA/m^2 = A/mm^2). Phi_hx/Phi_hy default to Phi_hmax when omitted. Conductivity MS/m, lamination thickness mm, coercivity A/m. |
| `ei_addmaterial / hi_addmaterial / ci_addmaterial` | (name, ex, ey, qv) / (name, kx, ky, qv, kt) / (name, ox, oy, ex, ey, ltx, lty) | ci conductivity ox, oy is in S/m (mi Cduct is MS/m). hi_addtkpoint("name", T, k) adds a temperature-dependent conductivity point. |
| `mi_addpointprop / mi_addcircprop` | ("name", a, j) / ("name", i, circuittype) | circuittype 0 = parallel, 1 = series. ei/hi/ci have no circuits; they use *_addconductorprop("name", V|T, q, conductortype) where conductortype 0 = prescribed charge/flux/current, 1 = prescribed voltage/temperature. |
| `mi_modifymaterial / modifyboundprop / modifycircprop / ...` | ("name", propnum, value) | propnum is an integer index into a table. The manual tables are column-misaligned in the plain-text conversion (symbols vs descriptions offset), so the indices in commands.json follow the add-command argument order. propnum 0 renames. Unverified against the engine except mi_modifycircprop (1 = current) and mi_modifymaterial(name, 4, value) accepted live. |
| `mi_selectgroup(n)` | (n) | the engine ADDS group n to the current selection (manual says it clears first) and leaves edit mode at 4. mi_setgroup(n) deselects everything afterwards. |
| `mi_copyrotate / copytranslate / moverotate / movetranslate / scale / mirror` | (..., editaction?) | editaction: 0 nodes, 1 segments, 2 labels, 3 arcs, 4 group. When omitted the manual says the current edit mode applies; the engine source defaults to 4 (group). Always pass it, and note mi_seteditmode takes strings ("nodes","segments","blocks","arcsegments","group") while editaction takes integers. |
| `mi_selectcircle / mi_selectrectangle` | (x,y,R[,editmode]) / (x1,y1,x2,y2[,editmode]) | editmode here uses 0 nodes, 1 segments, 2 labels, 3 arcs, 4 all types. |
| `mi_addarc / mi_drawarc` | (x1,y1,x2,y2,angle,maxseg) | angle in degrees; maxseg is the maximum degrees per discretisation segment in practice (the manual words it as "divided into maxseg segments"). |
| `mi_analyze(flag)` | (flag?) | 1 = solver window minimised. Blocks until the solve finishes. The model must have been saved first: otherwise "error:File must be saved before analysis" (observed live). |
| `mo_selectblock / xo_groupselectblock` | (x,y) / (n?) | selection is a TOGGLE: calling mo_selectblock twice at the same point deselects it and mo_blockintegral then raises "No area selected for integration" (observed live). |
| `mo_getpointvalues(x,y)` | returns 14 values | order: A, B1, B2, Sig, E, H1, H2, Je, Js, Mu1, Mu2, Pe, Ph, ff. Complex at AC (wire form a+I*b). eo: V, Dx, Dy, Ex, Ey, ex, ey, nrg (8). ho: T, Fx, Fy, Gx, Gy, kx, ky (7). co: V, Jx, Jy, Kx, Ky, Ex, Ey, ex, ey, Jdx, Jdy, ox, oy, Jcx, Jcy (15; the manual labels ox, oy "permittivity", which is evidently a typo for conductivity: unverified). pyFEMM comments claim 7 for co_, but the engine returns 15. |
| `xo_getprobleminfo` | mo: 4 values, eo: 3, ho: 3, co: 4 | mo/co: problem type, frequency (Hz), depth (m), length unit (m per unit); eo/ho: problem type, depth (m), length unit (m). Live: mi_getprobleminfo() after mi_probdef(0,"millimeters","planar",1e-8,10) returned 0, 0, 10, 0.001; mo_getprobleminfo() returned depth 0.01, i.e. depth is converted to meters by the post-processor but is in problem units in the pre-processor. |
| `xo_showdensityplot` | mo: (legend, gscale, upper_B, lower_B, type:"bmag"...) ; eo/ho/co: (legend, gscale, type:int, upper, lower) | upper/lower and type swap places between mo_ and the other three. Pass legend = -1 to use defaults. |
| `xo_showcontourplot` | mo: (numcontours, lower_A, upper_A, type) ; eo/ho: (numcontours, lower_V, upper_V) ; co: (numcontours, lower_V, upper_V, type) | lower comes BEFORE upper. numcontours = -1 uses defaults. |
| `xo_makeplot` | (plottype, numpoints[, filename[, fileformat]]) | engine requires numpoints even though the manual says PlotType alone is allowed. With a filename it writes CSV and returns the point count (observed live). Code tables are listed below. |
| `mo_getcircuitproperties("name")` | returns current, voltage, flux linkage | eo/ho/co_getconductorproperties return 2 values: (voltage|temperature, charge|heat flux|current). |
| `mo_getgapb / mo_getgapa / mo_getgapharmonics / mo_gapintegral` | ("BdryName", angle) / ... / ("BdryName"[, n]) / ("BdryName", inttype) | angle in degrees; the boundary must be a Periodic/Anti-periodic Air Gap property. gapintegral: 0 DC torque, 1 DC force, 2 stored energy, 3 2x torque, 4 2x force, 5 interaction torque, 6 interaction force (force returns 2 values). |

## Integral and plot code tables (as encoded in commands.json `enums`)

**`mo_blockintegral(type)` (returns one value, possibly complex)**

| code | meaning |
|---:|---|
| 0 | A.J |
| 1 | A |
| 2 | magnetic field energy |
| 3 | hysteresis and/or lamination losses |
| 4 | resistive losses |
| 5 | block cross-section area |
| 6 | total losses |
| 7 | total current |
| 8 | integral of Bx (Br) |
| 9 | integral of By (Bz) |
| 10 | block volume |
| 11 | x/r steady-state Lorentz force |
| 12 | y/z steady-state Lorentz force |
| 13 | x/r 2x Lorentz force |
| 14 | y/z 2x Lorentz force |
| 15 | steady-state Lorentz torque |
| 16 | 2x Lorentz torque |
| 17 | magnetic field coenergy |
| 18 | x/r steady-state weighted stress tensor force |
| 19 | y/z steady-state weighted stress tensor force |
| 20 | x/r 2x weighted stress tensor force |
| 21 | y/z 2x weighted stress tensor force |
| 22 | steady-state weighted stress tensor torque |
| 23 | 2x weighted stress tensor torque |
| 24 | R^2 (moment of inertia / density) |
| 25 | x/r 1x weighted stress tensor force |
| 26 | y/z 1x weighted stress tensor force |
| 27 | 1x weighted stress tensor torque |
| 28 | x/r 1x Lorentz force |
| 29 | y/z 1x Lorentz force |
| 30 | 1x Lorentz torque |

Manual caveat: the plain-text conversion shifts some table rows by one line. For `co_blockintegral` the shipped `docs/co_blockintegral_cases.csv` confirms the order used here. 1x/2x/DC components: "2x" are the double-frequency parts and only meaningful for AC problems.

**`mo_lineintegral(type)` (returns 2 values typically; type 3 returns 4: DC r/x, DC y/z, 2x r/x, 2x y/z)**

| code | meaning |
|---:|---|
| 0 | B.n (total, average) |
| 1 | H.t (total, average) |
| 2 | contour length (and surface area) |
| 3 | stress tensor force (DC x/r, DC y/z, 2x x/r, 2x y/z) |
| 4 | stress tensor torque (DC, 2x) |
| 5 | (B.n)^2 (total, average) |

**`eo_lineintegral(type)`**

| code | meaning |
|---:|---|
| 0 | E.t |
| 1 | D.n |
| 2 | contour length |
| 3 | force from stress tensor |
| 4 | torque from stress tensor |

**`ho_lineintegral(type)`**

| code | meaning |
|---:|---|
| 0 | temperature difference (G.t) |
| 1 | heat flux through contour (F.n) |
| 2 | contour length |
| 3 | average temperature |

**`co_lineintegral(type)`**

| code | meaning |
|---:|---|
| 0 | E.t |
| 1 | J.n |
| 2 | contour length |
| 3 | average voltage over contour |
| 4 | force from stress tensor |
| 5 | torque from stress tensor |

**`eo_blockintegral(type)`**

| code | meaning |
|---:|---|
| 0 | stored energy |
| 1 | block cross-section |
| 2 | block volume |
| 3 | average D over block (2 values) |
| 4 | average E over block (2 values) |
| 5 | weighted stress tensor force (2 values) |
| 6 | weighted stress tensor torque |

**`ho_blockintegral(type)`**

| code | meaning |
|---:|---|
| 0 | average T over block |
| 1 | block cross-section |
| 2 | block volume |
| 3 | average F over block (2 values) |
| 4 | average G over block (2 values) |

**`co_blockintegral(type)`**

| code | meaning |
|---:|---|
| 0 | real power |
| 1 | reactive power |
| 2 | apparent power |
| 3 | time-average stored energy |
| 4 | block cross-section area |
| 5 | block volume |
| 6 | x/r weighted stress tensor force, DC |
| 7 | y/z weighted stress tensor force, DC |
| 8 | x/r weighted stress tensor force, 2x |
| 9 | y/z weighted stress tensor force, 2x |
| 10 | weighted stress tensor torque, DC |
| 11 | weighted stress tensor torque, 2x |

**`mo_makeplot(plottype, ...)`**

| code | meaning |
|---:|---|
| 0 | potential A |
| 1 | |B| |
| 2 | B.n |
| 3 | B.t |
| 4 | |H| |
| 5 | H.n |
| 6 | H.t |
| 7 | J eddy |
| 8 | J source + J eddy |

**`co_makeplot(plottype, ...)` (eo/ho tables are in commands.json)**

| code | meaning |
|---:|---|
| 0 | V |
| 1 | |J| |
| 2 | J.n |
| 3 | J.t |
| 4 | |E| |
| 5 | E.n |
| 6 | E.t |
| 7 | |Jc| |
| 8 | Jc.n |
| 9 | Jc.t |
| 10 | |Jd| |
| 11 | Jd.n |
| 12 | Jd.t |

## Bulk getters: names and return shapes

Over the TCP wire every bulk getter returns ONE tab-separated line holding a flat row-major array; the pyFEMM wrapper reshapes it. Inside FEMM they return numpy arrays. Mesh indices are 1-based. Confirmed live on a 4674-node, 9082-element magnetostatic mesh: `mo_getallnodes` -> 9348 tokens (2N), `mo_getallelements` -> 63574 (7E), `mo_getalla` -> 9082 (E).

| name | wire tokens | reshape | element type | notes |
|---|---|---|---|---|
| mo_getallnodes / eo_ / ho_ / co_ | 2N | (N,2) | real | x, y (or r, z) |
| mo_getallelements / eo_ / ho_ / co_ | 7E | (E,7) | n1, n2, n3 (int, 1-based), cx, cy, area, group | same fields as xo_getelement(k) |
| mo_getallb | 2E | (E,2) | real at DC, complex at AC | B1, B2 per element (unsmoothed) |
| mo_getalla | E | (E,) | real at DC, complex at AC | A at element centroids (per ELEMENT) |
| eo_getalld | 2E | (E,2) | real | Dx, Dy per element |
| eo_getallv | N | (N,) | real | V per NODE |
| ho_getallf | 2E | (E,2) | real | Fx, Fy per element |
| ho_getallt | N | (N,) | real | T per NODE |
| co_getallj | 2E | (E,2) | real at DC, complex at AC | Jx, Jy per element |
| co_getallv | N | (N,) | real at DC, complex at AC | V per NODE |
| mo_getallgapb("name"[,npts]) | 2*npts (default 360) | (npts,2) | real/complex | Br, Bt per angle |
| mo_getallgapa("name"[,npts]) | npts | (npts,) | real/complex | A per angle |
| mo_getallgapharmonics("name") | 6*nh | (nh,6) | real/complex | acc, acs, brc, brs, btc, bts per harmonic |

Pitfalls: a field quantity is per element but potentials (V, T) are per node, so array lengths differ. With one element, pyFEMM `mo_getalla` returns a scalar not a list (its wrapper checks `isinstance(raw, list)`). The single-item getters are `xo_numnodes()`, `xo_numelements()`, `xo_getnode(k)`, `xo_getelement(k)`. The engine returns at most ~256 bytes for repr of non-numeric list/tuple results (observed: a long list of strings was truncated), so use tab-joined strings or the documented flat getters, not `repr` of lists.

## How this was verified

1. Manual: the bullet entries of sections 3.5 to 3.13 were parsed (563 distinct names, plus `eo_gridsnap`, `ho_gridsnap`, `co_gridsnap` whose list items lack a bullet marker and were added by hand) and compared with the catalog; every manual command is in the catalog (565 manual entries). The catalog names, argument lists and return orders were transcribed from the manual text and tables.
2. pyFEMM: every `FemmSession` method matching `xx_name` is in the catalog (checked by `tests/test_catalog_vs_pyfemm.py`).
3. Engine source: the femm-qt checkout under the scratch directory (`libfemm/py_*_editor.cpp`, `py_*_postproc.cpp`, `py_editor_common.h`) was scanned for `m.def`/`m.alias` registrations to mark which arguments are optional and to find undocumented aliases. This is a source read, not a binary guarantee.
4. Live: `femm_headless.exe` v5.0 06Oct2026 was started on spare ports and queried over TCP (read-only with respect to the install). `globals()` was enumerated after opening one example document per physics, analysing and loading the solution: 598 prefixed names exist; every one is in the catalog, and the only catalog names missing live are the 62 pyFEMM-only names. Argument counts of the add/probdef/setprop commands were measured by calling with increasing argument counts.
5. Not verified live: view-only GUI commands in headless mode, the semantics of undocumented `lfs`, `mi_newdocument`, `*_getprobleminfo` for pre-processors of ei/hi/ci, propnum index maps for the modify* commands, and the exact meaning of `acsolver` values.
