---
name: femm-scripting
description: Reaching any FEMM 5 command and running scripts through the femm MCP tools (femm_call, femm_eval, femm_run_script, femm_run_lua, femm_journal, femm_export_pyfemm_script, femm_api_search, femm_api_get) - the 677-command catalog, the one-line-per-request constraint, the exec(open(path).read()) pattern for multi-line MicroPython, batch runs with femm_headless -run, legacy FEMM 4.2 Lua scripts, exporting a standalone pyFEMM script from the session journal, which Python modules exist inside FEMM, and migrating FEMM 4.2 Lua or pyFEMM scripts. Use when no curated tool covers a FEMM command, when the user has a .lua or pyFEMM script, wants a loop inside FEMM, or wants a reproducible script of what the agent did.
---

# FEMM scripting: the escape hatches

The curated tools cover the common path. Everything else goes through four tools, in order of
preference.

| Tool | Use for | Returns |
|---|---|---|
| `femm_call(command, args)` | one FEMM command with positional arguments (`femm_call("mi_makeABC", [7, 50, 0, 0, 0])`) | `value`, catalog `warnings`, `returns` description |
| `femm_eval(expression)` | one line of MicroPython (`"mo_getpointvalues(0, 0)[1]"`, list comprehensions, arithmetic) | the value |
| `femm_run_script(code=...)` or `femm_run_script(path=...)` (mode "inprocess") | multi-line MicroPython inside this session's engine | the global `result` (or `result_var`) |
| `femm_run_script(..., mode="batch", args=[...])` | an independent job in a fresh engine (`femm_headless --port <free> -run script.py args`) | stdout, stderr, exit code |

## Finding commands

- `femm_api_search("air gap", physics="magnetics", phase="post")` - search names and descriptions.
- `femm_api_get("mi_addboundprop")` - arguments with types and optionality, return value, integer
  code tables (`enums`), notes, manual section.
- `femm_manual_section("3.7.1")` or a heading / keyword - the installed manual's text.
- `femm_examples_list(".py")` - FEMM's own example scripts and models.

The catalog holds 677 entries: 565 documented in the manual, engine-only aliases (for example
`mo_showdensity` -> `mo_showdensityplot`, British `*_analyse`), and 62 pyFEMM-only helper names
that the engine does **not** define (`femm_call` warns about those).

## The rules of the wire (verified)

1. **One line per request.** A request is a single MicroPython statement or expression; a newline
   is rejected by `femm_eval`. Statements return nothing (`null`), expressions their value.
2. **Keep lines short.** The engine's receive buffer is 65536 bytes; a 70 000-character line was
   split and its tail run as a separate command. Long code goes in a file.
3. **Multi-line code**: `femm_run_script(code=...)` writes it to `<work_dir>/scripts/` and sends
   `exec(open("<abs path>").read())`. The code sees every `mi_*`/`mo_*` command as a global, changes
   the session's model, and its variables persist for later calls. Set a global `result` to return
   data. `print()` output goes to the engine's stdout and is **not** captured; return values instead.
4. **Values come back as text**: tab-separated numbers become lists; a Python list or tuple value
   comes back as its repr (the tools parse it); complex numbers are spelled `1+I*2`; lists of
   non-numbers are cut near 256 bytes (return tab-joined strings or numbers).
5. **Strings and paths**: `femm_call` quotes strings for you. Inside `femm_eval` code, use forward
   slashes (or doubled backslashes) in paths.
6. **Commands appear with documents**: `mi_*` only after a magnetics document exists, `mo_*` only
   after a solution is loaded. Calling them earlier answers `name '...' isn't defined`.
7. **Complex arguments**: `femm_call` does not convert `[re, im]`; write the value as an
   expression with `femm_eval`, e.g. `femm_eval("mi_addcircprop('A', complex(8.78, 4.79), 1)")`
   (`complex(1, 2)` evaluates inside FEMM and prints back as `1+I*2` - verified). The curated
   tools (`femm_add_circuit`, `femm_add_boundary`, `femm_material_add`) accept `[re, im]` or
   `"1+2j"` themselves.

`femm_call` and `femm_eval` track `newdocument`, `opendocument`, `*_loadsolution` and `*_saveas`
in what they send, so the curated tools stay in sync with what you did by hand.

## What runs inside FEMM (manual, section 3.1-3.2)

MicroPython (an embedded Python 3). Available: `math`, `cmath`, `os`, `json`, `re`, `csv`, `time`,
and numpy/scipy-style arrays through `ulab`. `pandas`, `matplotlib`, `xlsxwriter`, `zipfile` are
forwarded to a CPython installation if one is present (not exercised by this project). Predefined
names: `pi`, `uo`/`muo`, `eo` (permittivity; do not confuse with the `eo_` prefix), unit
multipliers (`mm`, `inch`, `cm`, `um`, `mil`, `Tesla`, `Gauss`, `Oersted`), `AWG(n)` (mm).
`print` separates arguments with a tab.

A typical in-process loop:

```python
# femm_run_script(code=...)
out = []
for k in range(10):
    mi_modifycircprop("coil", 1, 0.5 * k)
    mi_analyze(1)
    mi_loadsolution()
    out.append(mo_getcircuitproperties("coil")[2])
    mo_close()
result = out
```

(`mo_close()` after each step of a sweep is accepted and the next `mi_analyze` + `mi_loadsolution`
work normally - verified.) Prefer `femm_experiment_parametric` when its output kinds cover what you
need: it records rows, files and errors for you.

## Batch mode

`femm_run_script(path="job.py", mode="batch", args=["a", "b"])` runs
`femm_headless --port <free> -run job.py a b` with `sys.argv == ["job.py", "a", "b"]`; exit code 0
on success, 1 on any script error (message in stderr as `Script error: ...`). Without `--port` the
engine would listen on 48015 even while batch-running, so the tool always passes a free port.

## Legacy and export

- `femm_run_lua(path)`: unchanged FEMM 4.2 Lua 4 script via the bundled `femm-lua` launcher
  (`femm-lua -h -p <port> script.lua`), its own engine, stdout and exit code returned. Verified on
  Windows.
- `femm_journal(save=True)`: the exact lines this session sent (refused ones prefixed `#! ` with the
  error), saved as `<work_dir>/scripts/journal.py` for `femm_run_script(path=...)`.
- `femm_export_pyfemm_script(path)`: the journal as a standalone pyFEMM script
  (`import femm; femm.openfemm(1); femm.mi_...(); femm.closefemm()`). pyFEMM finds the engine only
  through `FEMM_DIR`, so the script sets it to the detected bin folder. `femm_eval` expressions that
  are not plain calls are kept as comments.

Migrating FEMM 4.2 Lua and pyFEMM scripts command by command: `references/migration.md`.
