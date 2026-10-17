# FEMM 5: preliminary facts for an agent driver

Status: preliminary analysis, written while building `data/commands.json`. Date of the underlying
checks: build `FEMM headless engine v5.0 06Oct2026`.

Evidence tags used below:

- **[manual]** stated in the FEMM 5.0 User's Manual (October 1, 2026), cited by heading.
- **[source]** read from the femm-qt source tree (`ipc/tcp_server.cpp`, `libfemm/*.cpp`, `readme.txt`,
  `docs/*.md`); a source reading, not a behavioural guarantee of every build.
- **[live]** observed by talking to `femm_headless.exe` v5.0 06Oct2026 over TCP on a spare port.
- **unverified** could not be checked from the available material.

## 1. What FEMM 5 is

- Three programs plus solvers. [manual] *Chapter 1 Introduction*: `femm_gui` (MDI pre/post-processor),
  `femm_headless` (same engine without a GUI; Python REPL when run from a terminal), and the solvers
  `fkn` (magnetics), `belasolv` (electrostatics), `hsolv` (heat flow), `csolv` (current flow). The `tangle`
  mesher is built into each solver.
- On Windows a second copy, `femm_headlessw.exe`, is linked as a GUI-subsystem app so no console window
  opens; the language bindings launch that copy. Linux and macOS build only `femm_headless`.
  [manual] *Chapter 1 Introduction*. [live] all three executables are present in the install `bin` folder
  (`femm_gui.exe`, `femm_headless.exe`, `femm_headlessw.exe`) together with `femm-lua.bat`.
- Problems handled: linear/nonlinear magnetostatic, linear/nonlinear time-harmonic magnetic, linear
  electrostatic, steady-state and transient heat flow, current flow; 2-D planar and axisymmetric.
  [manual] *Chapter 1 Introduction*.
- Four physics map to command prefixes: `mi_`/`mo_` magnetics, `ei_`/`eo_` electrostatics, `hi_`/`ho_`
  heat flow, `ci_`/`co_` current flow (i = pre-processor, o = post-processor). Document types for
  `newdocument(n)`: 0 magnetics, 1 electrostatics, 2 heat flow, 3 current flow. [manual] *3.5 Common
  Scripting Command Set*.

## 2. Command-line options

[manual] *1.1 Running FEMM from the Command Line*:

```
femm_gui      [--port N] [file]
femm_gui      -run script.py [args...]
femm_headless [--port N] [script.py]          run script, then keep listening on the TCP port
femm_headless -run script.py [args...]        batch: run and exit
femm_headless -i [script.py]                  interactive REPL (script runs first)
femm_headless --version | --help
```

- Default port 48015. `-run` exit codes: 0 success, 1 script error, 130 interrupted with Ctrl+C (headless);
  an unrecognised option exits with code 2 and prints usage.
- Everything after the script name goes to the script as `sys.argv[1:]`, so FEMM switches such as `--port`
  must come BEFORE the script name.
- `femm_headless` with no arguments at a terminal enters the REPL; started with no terminal it serves TCP.
  [live] `--help` text agrees: "REPL if stdin is a terminal, else TCP server".
- [live] `femm_headless.exe --version` prints `FEMM headless engine v5.0 06Oct2026`; this works without
  starting the Python engine or opening a port.
- `femm-lua [-h] [-p PORT] [script.lua]` runs legacy Lua 4 scripts against the same TCP interface; Lua is
  compatibility only, new work should use Python. [manual] *1.1*.
- `FEMM_DIR` and the PATH search for the executables are conventions of the pyFEMM binding, not of FEMM
  itself. [source] `pyfemm/femm.py`.

## 3. TCP IPC protocol

[manual] *Chapter 6 TCP/IP Interface*; checked against `ipc/tcp_server.cpp` [source] and [live].

| property | value |
|---|---|
| transport | TCP, one connection, plain text |
| address | localhost only: bound to `INADDR_LOOPBACK` [source] |
| port | default 48015; `--port N` overrides |
| framing | one request = one `\n`-terminated line; reply = exactly one `\n`-terminated line (`\r\n` tolerated on input) |
| request content | any statement or expression accepted by FEMM's MicroPython interpreter, e.g. `mi_addnode(0,0)` or `x=5` |
| success reply | the value rendered as text; empty line if the command produced no value |
| failure reply | one line starting with `error:` followed by the message, no space after the colon |
| tuples / multiple results | items separated by TAB characters |
| clients | single-client: a second connection gets `error:femm-qt is already connected to another client` and is closed [source][live] |
| lifetime | the FEMM process exits when its client disconnects [manual][source][live: exit within 0.5 s of close]; `quit()` also exits |
| receive buffer | 65536 bytes [source]. A longer line is not safe [live: a 70 000 character line was truncated and the tail was evaluated as a separate command] |
| TCP_NODELAY | set on the server socket; clients should set it too [source] |

Value rendering, [manual] *Chapter 6* plus [live]:

- Booleans are `true` / `false` (lower case). Strings are returned unquoted. `None` becomes an empty line.
  [live] `True` -> `true`, `"abc"` -> `abc`, `[1,2,3]` -> `[1, 2, 3]`.
- Real numbers are printed in shortest round-trip form (`0.1`, not `0.10000000000000001`); integers print
  without a decimal point. [source] `libfemm/py_state.cpp` (`append_g`).
- Complex numbers use the imaginary-unit spelling `I` (capital), never `j`: `1+I*2`, `I*2.5`, `I`, `-I`,
  `3+I`, `3-I*0.5`. [live] `complex(1,2)` -> `1+I*2`; `2.5*I` -> `I*2.5`. A complex value whose imaginary
  part is exactly 0 prints as a plain real. Magnetics and current-flow results are complex when the
  frequency is nonzero. [source]
- Statement output (`print`) and tracebacks go to FEMM's own console, not into the reply. [manual] *Chapter 6*.
- Reply value for non-numeric Python lists is truncated at about 256 bytes (a design note in
  `docs/bulk-getters-design.md`; [live] enumerating `globals()` as a list of strings was cut off
  mid-string). Return tab-joined strings or use the documented flat getters instead of printing big lists.
- Backslashes in file names: a script string needs them doubled (the pyFEMM binding doubles every `\`
  before sending). Forward slashes are accepted on all platforms and results come back with forward
  slashes. [manual] *3.3 Files and Directories*, `mi_saveas` entry.
- Tab-separated replies of unknown length (bulk getters) are flat arrays; reshape on the client. [manual]
  *3.7.5 Miscellaneous*; [live] 4674 nodes -> 9348 tokens.

Parsing pitfall in pyFEMM: `FemmSession.callfemm` replaces every `I` and `i` in each token with `1j` before
`eval`, so a string result containing a letter `i` (for example a path or title from `mo_gettitle()`) comes
back mangled. A new client should parse tokens with a numeric/complex regex and otherwise return the raw
string. [source] `pyfemm/femm.py`.

Error text examples [live]: `error:name 'mi_addnode' isn't defined` (no document yet, or typo),
`error:Couldn't load "NoSuchMat" from the materials library`, `error:File must be saved before analysis`,
`error:No area selected for integration`.

## 4. How the command set behaves

- Commands appear only when a document exists: `newdocument`, `open`/`opendocument`, `quit`,
  `setcurrentdirectory`, `getcurrentdirectory` and the console helpers are always defined; `mi_*` appears
  after a magnetics document is created or opened, `mo_*` after `mi_loadsolution()` (or opening a solution).
  [live] before `newdocument(0)` even `mi_addnode(0,0)` fails with a name error; after loading a solution
  all `mo_*` names exist. [source] `docs/pyfemm-inprocess-compat.md`.
- Enumeration over all four physics (opening an example, analysing and loading each) found 598 distinct
  `xx_` names, all present in `data/commands.json`. [live]
- Typical solve sequence: `newdocument(0)`, `mi_probdef(...)`, geometry, properties, `mi_saveas(path)`,
  `mi_analyze(1)`, `mi_loadsolution()`, then `mo_*`. The model must be saved before analysis. [manual]
  *3.6.4 Problem Commands*; [live] unsaved -> `File must be saved before analysis`. `mi_analyze` blocks until
  the solver finishes. `mi_createmesh()` is optional (analyze remeshes) and returns the element count.
  [manual] *3.6.5 Mesh Commands*.
- Post-processing selections are stateful: `mo_selectblock(x,y)` TOGGLES, so selecting the same block twice
  deselects it and a following `mo_blockintegral` raises `No area selected for integration`. [live]
  Contours are built with `mo_addcontour`/`mo_bendcontour` and cleared with `mo_clearcontour`; the
  contour integral then reads them. [manual] *3.7.2 Selection Commands*.
- Multiple documents: `xi_setfocus("name")` / `xo_setfocus("name")` choose which open document later
  commands address; the solution extension may be omitted. [manual] *3.6.4*, *3.7.5*.
- Units: lengths in problem units (set in `xi_probdef`: "inches", "millimeters", "centimeters", "mils",
  "meters", "micrometers"), angles in degrees, frequency in Hz, current in A, conductivity of magnetic
  materials in MS/m, depth in problem units (the post-processor reports depth and length scale in metres).
  [manual] *3.6.4*, *3.6.9*; [live] `mi_getprobleminfo()` -> `0 0 10 0.001`, `mo_getprobleminfo()` ->
  `0 0 0.01 0.001` for depth 10 mm.
- Bulk getters return the whole mesh in one call and are far faster than per-item loops. Node and element
  indices are 1-based. [manual] *3.7.5 Miscellaneous* and the corresponding sections for the other
  physics; shapes are tabulated in `data/commands_summary.md`.
- Scripting uses MicroPython (an embedded Python 3). The script can define loops, functions and use
  `numpy`/`scipy` (provided by ulab), `math`, `cmath`, `os`, `json`, `re`, `csv`, `time` and more; `pandas`,
  `matplotlib`, `xlsxwriter`, `zipfile` are forwarded to a CPython installation if present. [manual]
  *3.1 What is Python Scripting?*, *3.2 Importing Python Modules*. `print` separates arguments with a TAB.
- `open("file")` with one argument naming a `.fem/.fee/.feh/.fec` is the FEMM document open (same as
  `opendocument`); any other call is Python's file `open`. [manual] *3.3 Files and Directories*.
- `smartmesh(state)` is a session-wide override (1 on, 0 off, -1 defer to the per-document
  `xi_smartmesh`). [manual] *3.5*.
- Predefined script names: `pi`, `uo`/`muo`, `eo`, unit multipliers (`mm`, `inch`, `cm`, `um`, `mil`, `Tesla`,
  `Gauss`, `Oersted`, ...), `AWG(n)` (mm). [manual] *3.4 Predefined Constants and Units*. Note `eo` is also a
  command prefix: the permittivity constant `eo` and the electrostatics post-processor prefix `eo_` do not
  collide, but it is a naming trap.

## 5. FEMM 5 versus FEMM 4.2

Items 1 to 6 come from the top-level `readme.txt` of the femm-qt tree [source] (author's release notes);
items 7 onward come from the manual and engine source.

1. Qt port of the Windows MDI program; builds on Windows, Linux, FreeBSD and macOS.
2. Meshing by `tangle`, compiled in as an internal library, instead of Triangle.
3. Solvers rebuilt around a whole-matrix incomplete-LDL^T preconditioner: stated as "2-3x faster than the
   previous block-SSOR scheme" and bit-deterministic run to run. The brief mentions 3-5x; **unverified**
   (no document in the checked material says 3-5x; the readme says 2-3x for the solvers). [source]
4. TCP IPC (localhost, newline-delimited) replaces the Windows-only ActiveX/COM server. [manual] *Chapter 6*.
5. MicroPython replaces Lua 4 as the embedded language; Lua 4 survives only as the `femm-lua` client for
   old scripts. [manual] *1.1*, *3.1*.
6. Bindings shipped: MATLAB/Octave, Python (pyFEMM), Mathematica, Scilab, Julia, Lua 4.
7. Bulk getters (`xo_getall...`, about 50x faster than per-item loops for nodes) and `xo_getnode`,
   `xo_getelement`, `xo_numnodes`, `xo_numelements`. [manual] *3.7.5* (and the same section in 3.9, 3.11,
   3.13). Whether `getnode`/`getelement` already existed in 4.2 is **unverified** here.
8. Periodic and anti-periodic air-gap boundaries (the sliding-band machinery used for rotating machines:
   `BdryFormat` 6 and 7 with inner/outer angles `ia`, `oa`, plus `mo_getgapb`, `mo_getgapa`,
   `mo_gapintegral`, `mo_getgapharmonics`, `mo_getallgap*`). [manual] *2.2.7 Definition of Properties*,
   *3.6.9*, *3.7.1*; `docs/eccentric-sliding-band.md` calls it "AGE" and cites Meeker 2018. Whether it is new
   relative to 4.2 is **unverified**: only that it is present in 5.0.
9. Command names carry exactly one underscore (`mi_addnode`); the longer 4.2-era spelling that broke names
   with more underscores is no longer accepted. [manual] *3.6 Magnetics Preprocessor Scripting Command Set*.
10. In-process pyFEMM compatibility: scripts written for pyFEMM run unchanged inside FEMM (`import femm`
    resolves to a proxy; `openfemm`/`closefemm` become no-ops), except 62 pyFEMM names that are Python-side
    conveniences and do not exist in the engine (listed in `data/commands_summary.md`). [source]
    `docs/pyfemm-inprocess-compat.md`. The compat note says "62"; counting its own tables literally gives
    23 + 36 + 3 helpers = 62 in the catalog. `*_getnodeindex`/`*_getelementindex` were invented in the port and
    removed on 2026-08-29.
11. Solution and input files are plain text (see section 7); results and plots can be written to CSV
    (`xo_makeplot(type, n, "file.csv")`); `xo_savemetafile` is a no-op, `xo_savebitmap` saves a bitmap
    screenshot of the current view. [manual] *3.7.5*, *3.6.10*.
12. Material library renames: the project notes (`CLAUDE.md`) record that many magnetic library names changed
    in FEMM 5 (for example `M-19 Steel` -> `M-19 14 mil`); the shipped libraries are `matlib.dat`,
    `statlib.dat`, `heatlib.dat`, `condlib.dat` and a user copy is kept under the personal FEMM directory.
    [manual] *Material Library* (2.2.7). The rename claim is **unverified** by me; it is quoted from the repo
    notes, and `mi_getmaterial("NoSuchName")` raises `Couldn't load "NoSuchName" from the materials library`
    [live].

## 6. Licensing

[source] `readme.txt` (femm-qt root) and `LICENSE-MIT`, `LICENSE-GPL`:

- MIT License: the femm-qt application (GUI, `libfemm` engine, IPC server, `tangle` mesher, shared math,
  language bindings) and the material libraries (`matlibs/README.md`).
- GNU GPL v3 or later: the finite-element solvers in `solvers/` (`fkn`, `belasolv`, `hsolv`, `csolv`).
  Alternative licences for the solvers are available from the author on request.
- Bundled third parties keep their own licences (Qt under LGPL-3.0, MicroPython, micropython-lib, ulab, the
  Boehm GC, Lua 4, LuaSocket, complexEigenPairSolver).
- Implication for this project: an MCP server that talks to FEMM over TCP and does not link the GPL solvers
  can be MIT. Redistributing FEMM binaries (or solver code) carries the GPL obligations for those parts.
  This is an engineering reading, not legal advice.

## 7. File formats

[manual] *2.2.9 Analysis Tasks* and the sibling sections for the other physics; the author's format
specifications (`docs/*-file-formats.pdf`, text versions of each `*-fmt` note) describe them in full:

| physics | input | output (solution) | solver |
|---|---|---|---|
| magnetics | `.fem` | `.ans` | `fkn` |
| electrostatics | `.fee` | `.res` | `belasolv` |
| heat flow | `.feh` | `.anh` | `hsolv` |
| current flow | `.fec` | `.anc` | `csolv` |

- Plain text, section headers in `[Tag]` form and property blocks in `<BeginBlock>`/`<EndBlock>`; floats are
  written with 17 significant digits; string comparison while parsing is case-insensitive. The solution
  file starts with a verbatim copy of the input file followed by a `[Solution]` section holding the mesh
  and field values. Element indices inside the file are 0-based, the scripting interface adds one.
  [format notes; manual *3.7.5*]
- `[LengthUnits]` in the file uses `microns`, while `xi_probdef` takes `"micrometers"`; `mils` appears in
  both (the engine also tolerates `"mills"`). [format notes; source]
- A solution can be reopened by `open("x.ans")` and `mi_setprevious("x.ans", 1|2)` uses a previous `.ans`
  for incremental or frozen permeability. [manual] *3.6.10 Miscellaneous*.
- DXF (revision 13 reading) can be imported and the geometry exported: `xi_readdxf`, `xi_savedxf`.
  [manual] *2.1 DXF Import/Export*.
- Material libraries `.dat` live beside the executables (read-only) and in the personal FEMM directory once
  edited (`%APPDATA%\FEMM\`, `~/Library/Application Support/FEMM/`, `~/.local/share/FEMM/`). [manual]
  *Material Library*.

## 8. Things an agent driver must remember

1. Every reply is exactly one line: check each for the `error:` prefix (a failed command leaves earlier edits in place).
2. Reply types are only text. Complex uses `I`; arrays are flat; strings are unquoted. Parse by command.
3. `mi_probdef` puts frequency first; `ci_probdef` third; `ei_`/`hi_` have none. `hi_addboundprop` takes
   `BdryFormat` second. `mi_addboundprop` has 12 positional parameters, `mi_addmaterial` 14.
4. Save before `*_analyze`; call `*_loadsolution` before any `xo_*`.
5. Always pass `editaction` to transform commands, and clear the selection between operations.
6. Block selection in the post-processor toggles. Clear it (`xo_clearblock`) before selecting.
7. One FEMM process serves one client; use one port per parallel session; the process dies with the socket.
8. Keep request lines well under 64 KiB; write long scripts to a file and `exec(open(path).read())` or use
   `femm_headless -run`.
9. Long calls (`analyze`, big meshes) block the reply; use per-call timeouts.

## 9. Unverified or open items

- Return layout of `ei_/hi_/ci_getprobleminfo` (assumed to mirror `eo_/ho_/co_getprobleminfo`); only
  `mi_getprobleminfo` was observed.
- Meaning of the `acsolver` values 0/1 in `mi_probdef` beyond the file-format note (0 successive
  approximation, 1 Newton, from the `.fem` format table `[ACSolver]`).
- `propnum` index maps of the `*_modify*prop` commands: the manual tables are column-misaligned in the
  plain-text conversion; the maps in `commands.json` follow the argument order of the matching `add` command
  (only `mi_modifycircprop` index 1 and `mi_modifymaterial` index 4 were exercised live).
- Whether `xo_makeplot` returns the number of sampled points (observed `10` for 10 points) is undocumented.
- Typos in the manual's plain-text tables: `co_getpointvalues` calls `ox, oy` "permittivity"; the
  `*_makeplot` and `co_blockintegral` tables are shifted by one row in the extracted text (the order used in
  the catalog was confirmed for `co_blockintegral` against `docs/co_blockintegral_cases.csv`).
- Headless behaviour of GUI-only view commands (`xo_zoom`, `xo_showdensityplot`, `main_*`): registered, but
  their effect without a window was not tested.
- 3-5x speed-up claim and "material renames" are unverified (see section 5).

## Verified by the core-server build

All items below were observed live on `FEMM headless engine v5.0 06Oct2026` (Windows 11) while
building and testing the core tool groups (`tests/live/`). Tags as above: everything here is **[live]**.

**Scripting and processes**

- `exec(open("<abs path>.py").read())` works as one request: multi-line MicroPython runs inside the
  engine, sees all `mi_*`/`mo_*` commands as globals, and its variables persist for later requests.
  `open()` with one argument naming a `.py` file is Python's `open`; naming a FEMM document it opens
  the document. `print()` output of in-process code goes to the engine's stdout, not to the reply.
- A Python list or tuple *value* comes back as its repr in a single field (`"[6, 4958.0]"`), not
  tab-separated; the tools turn it back into data with `ast.literal_eval`.
- `femm_headless --port N -run script.py a b` runs the script with `sys.argv == [script, 'a', 'b']`
  and exits: code 0 on success, 1 on any script error (stderr: `Script error: <message>`). Without
  `--port` it still listens on 48015 while running, so pass a free port when sessions are open.
  `print(a, b)` separates with a tab.
- `femm-lua.bat -h -p PORT script.lua` (bin folder) runs an unchanged FEMM 4.2 Lua 4 script against a
  fresh headless engine, prints to stdout, returns exit code 0, and leaves no process behind.
- The bundled pyFEMM (`<install>/pyfemm/femm.py`) finds the engine only through `FEMM_DIR`; it does
  not search the default install folders (`RuntimeError: Cannot find femm_headlessw executable`).
- Launch of `femm_headlessw --port N` to first reply: ~0.5 s.

**Problem info, meshing, solving**

- `mi_getprobleminfo()` returns `[type (0 planar, 1 axi), frequency Hz, depth in problem units,
  length unit in m]`, e.g. `[0, 0, 100, 0.001]`; `mo_getprobleminfo()` gives the same but depth in
  metres (`0.1`). `ei_/hi_getprobleminfo()` and `ci_getprobleminfo()` return three values
  `[type, depth, length unit in m]`: the current-flow one has no frequency field.
- `mi_getboundingbox()` returns `[x_min, x_max, y_min, y_max]` (nothing for an empty model).
- `mi_createmesh()` on an unsaved model fails with `File must be saved before creating mesh`; after a
  save it returns nothing (no element count). Counts come from `mo_numnodes/mo_numelements` after a solve.
- A region without a block label stops the solver: `Solver failed: a region has no material assigned
  ... (exit code 10)`. `mi_loadsolution()` without a solution: `No results file: <path>.ans`.
- After `mi_close()` any `mi_*` call fails with `No current magnetics input in focus`.
- Speed: thick-solenoid self-test, 8914 elements, axisymmetric magnetostatic: 0.06-0.1 s solve.

**Post-processing**

- `mo_getpointvalues` reports `Je` and `Js` in **MA/m^2** (a 500-turn, 1 A coil of 200 mm^2 gives
  `2.5`). It returns an empty reply for a point outside the mesh (also inside an air-gap annulus).
- `mo_getallelements()` returns 7 values per element `n1, n2, n3, cx, cy, area, group` with
  **1-based** node indices; `mo_getallb()` 2 values per element; `mo_getallnodes()` 2 per node.
- pyFEMM helpers such as `mo_getb` are not engine commands: over the wire `name 'mo_getb' isn't defined`.
- `mo_blockintegral(2)` returns one value; `eo_blockintegral(0)` (stored energy) returns two values `[W, 0]`.
- `xo_makeplot(type, npts, file, 0)` works headless, writes a text file with a header line
  (`Position, |B|`) and `x, y` rows, and returns `npts`. Without a contour: `No contour defined for makeplot`.
- `mi_modifymaterial` propnum 1 = mu_x, 5 = sigma, 8 = lamination fill (checked in the saved `.fem`).
- `mi_selectlabel/selectnode` return the picked coordinates; `mi_selectsegment/selectarcsegment`
  return `[x1, y1, x2, y2]` of the picked edge.

**Air-gap element (sliding band)**

- `mi_addboundprop(name, 0,0,0,0,0,0,0,0, 6, inner_angle, outer_angle)` (12 args) assigned to both
  concentric arcs works, but the annulus needs a `<No Mesh>` block label (otherwise the solver error
  above). `mo_getgapb`, `mo_gapintegral`, `mo_getallgapb` and `mo_getallgapharmonics` then work:
  2-pole N42 rotor, 1 mm gap, iron stator: Br = 1.217 T at 0 deg, torque ~6e-6 N m.
- `mo_getallgapharmonics` row index = harmonic number (row 1 carried the 1.2165 T fundamental).
- An unknown air-gap boundary name is **not** an error: every gap command returns zeros.

**Screenshots**

- `mi_savebitmap` / `mo_savebitmap` return success in the headless engine but write **no file**. In
  `femm_gui` (`femm_session_open(headless=False)`) they write PNG (1994x1330 RGBA) or BMP.
  `mo_savemetafile` writes nothing in either.
- After `mi_loadsolution` the post-processor window has the focus: `mi_savebitmap` captures the
  solution plot until `mi_setfocus("<document stem>")` is called.
- `mo_showdensityplot(1, 0, 0, 0, "bmag")` draws a legend that reads 0 everywhere; legend `-1`
  (FEMM defaults) auto-scales correctly and adds flux lines.

**Accuracy spot checks (tests/live/test_live_core.py)**

- Thick solenoid centre field: 0.695 % above the analytic value (mi_makeABC open boundary).
- Parallel-plate capacitor (eps_r 4): conductor charge and `eo_blockintegral(0)` energy within 1 %.
- Heat-flow slab and current-flow strip: |F| and |J| within 1 % of k dT/L and sigma V/L.

Resolves from section 9: the `ei_/hi_/ci_getprobleminfo` layout, three `mi_modifymaterial` indices,
and the `xo_makeplot` return value.

## Verified by the engineering build

Observed live on FEMM 5 build 06oct2026 (Windows, `femm_headlessw.exe`) while building the
experiments, health rules and file parser. Numbers come from `tests/test_experiments.py`,
`tests/test_health.py` (`-m live`) and `examples/`.

**Solution files (.ans and the other physics)**

- The element order in the `.ans` `[Solution]` section is the order of `mo_getallelements`; node
  indices are 0-based in the file and 1-based over IPC. Element B computed from the nodal A of a
  planar `.ans` (Bx = dA/dy, By = -dA/dx, coordinates in metres) matches `mo_getallb` to print
  precision, so the `.ans` element -> block-label column can be combined with live bulk arrays.
- DC magnetostatic node rows have 4 columns; element rows have 8 (DC) or 7 (time-harmonic) columns.
  The three edge columns are 0-based indices into `[BdryProps]`, -1 for none.
- `.res`, `.anh`, `.anc` written by `ei_/hi_/ci_analyze` parse with the same reader: node rows have
  4, 4 and 5 columns, element rows 4.
- A block label given the material `"<No Mesh>"` is saved as a `[NumHoles]` row, not a block label.
- `mi_makeABC(n, R, x, y, 0)` adds a Dirichlet boundary named `A=0` (BdryType 0) and n shell
  materials `u1`..`un` with labels. The field inside the shells is not physical, so "field at the
  outer boundary is small" must not be judged inside them.

**Commands**

- `mo_getb`, `mo_geta`, `mo_geth`, `mo_getj`, `mo_getmu` are pyFEMM-side helpers: over IPC they
  answer `name 'mo_getb' isn't defined`. Use `mo_getpointvalues`.
- `mi_createmesh()` returns nothing over IPC (not the element count); use `mo_numelements` after a solve.
- `mo_groupselectblock(n)` calls accumulate (several groups can be selected before one
  `mo_blockintegral`); `mi_selectgroup(n)` clears the previous selection.
- `mo_close()` after each step of a sweep is accepted and the next `mi_analyze` +
  `mi_loadsolution` work normally. `mi_close()` followed by `opendocument(path)` works headless.
- A multi-line MicroPython snippet runs per case via `exec(open("<path>").read())`.
- `mi_smartmesh(0)` before meshing cut the SPM benchmark from 33.5k to 9.7k elements (same field to
  about 0.2 % in the gap, same flux linkage to 0.2 %).
- Rotating a group by +a and then -a leaves node coordinates rounded slightly differently, and the
  re-meshed model had 9786 instead of 9676 elements. Re-solve after restoring a swept geometry.

**Block integrals and forces**

- Linear C-core: block integral 2 (energy) = 17 (coenergy) = 1/2 psi I from
  `mo_getcircuitproperties` to all printed digits (0.0149452 J at 2 A).
- Weighted stress tensor force (18/19) vs virtual work dW'/dx from coenergy (17): 1.6 % RMS on the
  C-core over 1-3 mm gaps, 5 % on the axisymmetric coilgun (19 is the z-force there). WST torque
  (22) vs dW'/dtheta: 6.6 % RMS for cogging with 2 deg steps.
- The WST torque of a group and of its complement are equal and opposite almost by construction
  (complementary weights), so that is a weak check; virtual work is the independent one.
- `mo_getcircuitproperties` flux linkage includes turns and depth. For a series circuit with +N
  and -N turn labels the parser's net-turns sum is 0, which is correct.

**Periodic air-gap element (BdryFormat 6)**

- Geometry that works: two concentric circles (each two 180 deg arcs) carrying the same
  BdryFormat 6 boundary, with a `"<No Mesh>"` label in the thin annulus between them. Without that
  label the solver fails with `a region has no material assigned`.
- `mi_modifyboundprop("AGE", 10, angle)` rotates the inner side (the rotor) by `angle` degrees and
  the mesh does not change between steps. `mo_gapintegral("AGE", 0)` returns the torque as one value.
- The WST block integral (22) on the rotor reads about 1e-16 N*m across an air-gap element. Use
  `mo_gapintegral` for torque with this route.
- Against the rotate-and-re-mesh route on the same 12-slot / 4-pole SPM: cogging peak to peak
  0.3835 vs 0.3824 N*m (0.3 %), back-EMF fundamental 9.977 vs 9.973 V. Each step took 0.19 s vs
  0.15 s (the rotate figure includes re-meshing).
- Not exercised: antiperiodic air gap (BdryFormat 7), the outer-angle property (propnum 11),
  `mo_getgapharmonics` / `mo_getallgapb` in the experiments.

**Accuracy against analytic references**

- C-core (planar, linear iron mu_r 2000, two 1 mm gaps): gap B 0.238 T vs 0.2405 T; force -9.74 N vs
  -9.21 N (two-gap B^2 A / 2 mu0); L 7.47 mH vs 4.81 mH (the formula ignores fringing and slot leakage).
- Thick solenoid (coilgun coil, inches, axisymmetric, ABC R = 4 in): centre B 0.2305 T vs 0.2289 T (+0.7 %).
- Round copper wire (r 5 mm, A = 0 at 50 mm, 1 m deep): L_dc 0.509 uH vs 0.5105 uH; R(f) vs the
  exact Bessel internal impedance: 0.0 % at 1-100 Hz, 0.1 % at 1 kHz, 0.4 % at 3 kHz, 1.3 % at
  10 kHz (0.25 mm mesh, skin depth 0.66 mm). 1/2 Re(V conj I) equals block integral 6 (total
  losses) to 0.00 %, so circuit phasors are peak amplitudes.
- SPM (N42 linear, mu_r 1.05, Hc 994529 A/m -> Br 1.312 T): gap B 0.862 T vs 0.843 T
  (Br lm / (lm + mu_r kc g)); PM flux-linkage fundamental 47.6 mWb vs 51.0 mWb (flat-gap
  estimate); Ld 0.427 mH, Lq 0.421 mH; mutual inductances reciprocal to 0.4 %. Mean torque at
  iq = 10 A was 1.415 N*m against 1.428 N*m from 3/2 p (psi_d iq - psi_q id) with the FEM flux
  linkages (0.2 %). At a single rotor position the dq formula is off by 12 % because the EMF has
  27 % THD. Magnet operating point B_m/Br 0.70, Pc 2.5.
- Library materials used: `N42` is linear (no B-H points); `M-19 14 mil` is nonlinear with
  sigma 1.923 MS/m; `Copper` is 58 MS/m.

**Timings (this machine)**

- Engine launch about 0.55 s. Solves: 15k-element planar C-core 0.13-0.20 s, 9.7k-element SPM about
  0.15 s per rotor step including re-mesh, 10.7k-element AC wire 0.13 s.
- Full SPM example (cogging with 2 methods, back-EMF, Ld/Lq, loaded torque, PM check, report, about
  130 solves): 24.5 s. Live engineering tests: about 20 s.

**Concurrency**

- If another client is already connected to an engine's port, a second connect gets
  `femm-qt is already connected to another client`. Tests and examples pick their own free port
  (`ipc.pick_free_port(49xxx)`) so that they can run next to other sessions.
