# Contributing

Thanks for helping make FEMM 5 agent-friendly.

## Ground rules

- **Verified facts only.** Anything written about FEMM behaviour (in docstrings, skills or
  `docs/femm5-facts.md`) must have been observed on a real FEMM 5 build. Mark the rest as
  *unverified*.
- **Offline tests must stay offline.** CI has no FEMM. Tests that need the engine carry
  `@pytest.mark.live` and are skipped by default.
- **No personal paths, no copied FEMM files.** The only hard-coded default is `C:\femm-qt`.
  Example models are ones we authored; solutions (`*.ans`) are never committed.
- **Every tool answers with the envelope** (`ok`, `result` or `error.message` + `error.hint`).
  Write hints as the next action the agent should take.

## Workflow

```powershell
python -m venv .venv; .venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -m pytest            # offline
.venv\Scripts\python -m pytest -m live    # with FEMM 5 installed
```

1. Open an issue describing the tool or fix.
2. Implement with tests (`tests/`), update `docs/femm5-facts.md` and the relevant skill under
   `.claude/skills/`.
3. `tests/test_tool_names.py` must pass: every `femm_*` name mentioned in README or skills has
   to be a registered tool.
4. Open a pull request. Keep the change focused.

## Adding a FEMM command

Most FEMM commands are reachable through `femm_call` and documented in
`data/commands.json`. Add a dedicated tool only when the agent needs orchestration,
validation or safer defaults around the raw command.
