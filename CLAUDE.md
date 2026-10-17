# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

FEMM Agent Suite (repo `femm-agent-suite`, Python package `femm_agent`, MCP server name `femm`,
console script `femm-mcp`): an MCP server plus a family of Claude skills (`.claude/skills/`) that
let an agent drive **FEMM 5** (Finite Element Method Magnetics, femm-qt, by David Meeker; MIT app +
GPL solvers; Windows / macOS / Linux) across all four physics (magnetics, electrostatics, heat
flow, current flow), and judge whether a result is physically sane. Target: FEMM 5.0 build
06oct2026 or newer. The skills are the operating manual for *using* the tools; this file is for
*changing* the code. Verified FEMM 5 behaviour lives in `docs/femm5-facts.md`.

## Commands

```powershell
python -m venv .venv; .venv\Scripts\pip install -e ".[dev]"   # dev install (Python >= 3.10)
.venv\Scripts\python -m pytest                                 # offline tests (no FEMM needed)
.venv\Scripts\python -m pytest -m live                         # live tests (need FEMM 5 installed)
.venv\Scripts\python -m femm_agent                             # run the MCP server (stdio)
```

FEMM 5 is found via `FEMM_DIR` (bin folder) or the default install locations
(`C:\femm-qt\bin`, `/Applications/femm_gui.app/Contents/MacOS`, `~/.local/opt/femm-qt/bin`).

## Architecture

```
MCP client --stdio--> server.py (FastMCP, Python >= 3.10)
                        |-- sessions.py   named FEMM instances (port, pid, physics, open doc, cwd)
                        |     `-- ipc.py  FemmLink: TCP newline protocol, launch/connect, timeouts, journal
                        |-- catalog.py    loads data/commands.json (every FEMM command, args, docs)
                        |-- materials.py  loads data/materials/*.json + the installed .dat libraries
                        |-- tools/*.py    tool groups, each `register(mcp, ctx)`:
                        |      session, document, geometry, properties, materials, mesh_solve,
                        |      postproc, scripting, docs, experiments, health, report
                        |-- experiments.py  standard tests (cogging, torque-angle, back-EMF, inductance,
                        |                   force-vs-position, AC impedance) composed from ops
                        |-- health.py      pure physics invariants / sanity rules (unit tested)
                        |-- femfile.py     parse .fem/.fee/.feh/.fec text files to JSON summaries
                        |-- plotting.py / reporting.py  post-processing (pure, optional matplotlib)
                        `-- units.py / estimate.py      analytic layer (pure)
```

### Hard facts behind this design (verified live on build 06oct2026)

- **Transport.** FEMM 5's bindings all speak one protocol: TCP to `127.0.0.1:48015` (default),
  one request line = one MicroPython expression evaluated inside FEMM, one reply line =
  `error:<msg>` or tab-separated values; backslashes must be doubled. `femm_agent.ipc.FemmLink`
  implements it directly (no pyFEMM import needed). `femm_headlessw.exe --port N` (Windows,
  no console) / `femm_headless --port N` is spawned per session; several instances run on
  different ports. The engine exits when it receives `quit()`.
- **Errors are explicit.** Unlike JMAG, FEMM raises: a bad material name answers
  `error:Couldn't load "X" from the materials library`. `FemmError` carries the message and the
  command. Tools must convert it to `{"ok": false, "error": {"message", "hint"}}`.
- **Commands only exist once a document exists.** `newdocument`/`opendocument` are always
  defined; `mi_*` appears after a magnetics document is created, `mo_*` after `mi_loadsolution`.
  Calling `mo_getb` without a solution gives a NameError-style error. Tools should set the hint
  accordingly ("call femm_solve / femm_load_solution first").
- **Materials were renamed in FEMM 5** (282 magnetic entries). `M-19 Steel` -> `M-19 14 mil`
  (or `M-19`), `Pure Iron` -> `ARMCO Pure Iron`, `1010 Steel` -> `1010 Steel (hot rolled)`,
  `NdFeB 32 MGOe` has no library entry (nearest `N33`). `data/materials/name_index.json` holds
  the index; the materials tool must do fuzzy lookup and propose the nearest names.
- **Single line per call.** Multi-line MicroPython scripts cannot be sent as one request; write
  them to a temp file and send `exec(open(path).read())`, or use `femm_headless -run script.py`.
  Statements return `None`; expressions return their value.
- **Bulk getters** (`mo_getallnodes`, `mo_getallelements`, `mo_getallb`, `mo_getalla`, gap
  variants, and the eo/ho/co equivalents) return flat tab-separated arrays (nodes 2/row,
  elements 7/row, B 2/row). 10k elements come back in ~0.1 s. Tools must never dump these into
  the MCP reply: write `.npz`/`.csv` to the work dir and return path + shape + summary stats.
- **Speed.** A 10k-element magnetostatic solve takes ~0.25 s, launch ~0.5 s. Timeouts: default
  600 s per call, solve calls take an explicit `timeout`.
- **Lengths** are in problem units (`mi_probdef` units argument), angles in degrees,
  frequency in Hz; `mi_probdef(freq, units, type, precision, depth, minangle, acsolver)`.
- **`mo_getpointvalues(x,y)`** returns 14 values: A, B1, B2, Sig, E, H1, H2, Je, Js, Mu1, Mu2,
  Pe, Ph, ff (see manual 3.7). `mo_blockintegral(k)` integer codes are in `data/commands.json`.

### Tool envelope (every tool, no exceptions)

```json
{"ok": true, "result": ..., "session": "main", "seconds": 0.01}
{"ok": false, "error": {"message": "...", "hint": "next action for the agent"}, "session": "main"}
```

Hints are part of the UX: write them as the next action the agent should take. Docstrings are
written for an LLM caller: units, examples, pitfalls, which tool to call before/after.

### Adding a tool

1. If it is a thin FEMM command, prefer exposing it through `femm_call` (generic, validated
   against the catalog) and documenting it in the skill, rather than a new tool.
2. A curated tool goes in the right `tools/*.py` group with `@mcp.tool()`, uses
   `ctx.session(name)` to get the `FemmLink`, wraps everything in `envelope(...)`.
3. Pure logic (metrics, invariants, estimates) goes in its own module with tests in `tests/`.
4. Document verified behaviour in `docs/femm5-facts.md` and mention the tool in
   `.claude/skills/femm/references/tool-map.md`. Only write down behaviour observed on a real
   FEMM 5; mark anything else unverified.
5. `tests/test_tool_names.py` fails if README or any skill names a tool that is not registered.

## Repo hygiene

This repo is public: never commit personal paths (take paths as arguments; use `C:\femm-qt`
only as the documented default), never commit anything copied from the FEMM installation
except small example `.fem` files we authored ourselves, keep `.ans` solutions out of git.
Data files under `data/` are generated from the installed FEMM 5 by `scripts/` and are MIT like
the libraries they summarise.
