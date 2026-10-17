"""Mesh and solve tools."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..sessions import Session
from ._common import ToolContext, ToolInputError, run_tool
from .document import save_document

SOLUTION_EXT = {"magnetics": ".ans", "electrostatics": ".res", "heatflow": ".anh", "currentflow": ".anc"}


def solve(s: Session, timeout: float = 600.0, hide_window: bool = True, load_solution: bool = True,
          path: str | None = None) -> dict[str, Any]:
    doc = save_document(s, path)
    t0 = time.time()
    s.pre_call("analyze", 1 if hide_window else 0, timeout=timeout)
    solve_s = time.time() - t0
    out: dict[str, Any] = {"document": doc, "solve_seconds": round(solve_s, 3)}
    sol = Path(doc).with_suffix(SOLUTION_EXT[s.physics])
    out["solution_file"] = sol.as_posix() if sol.is_file() else None
    s.solved = False
    if load_solution:
        s.pre_call("loadsolution")
        s.solved = True
        out["nodes"] = s.post_call("numnodes")
        out["elements"] = s.post_call("numelements")
    return out


def register(mcp, ctx: ToolContext) -> None:
    @mcp.tool()
    def femm_create_mesh(session: str = "main") -> dict:
        """Mesh the model without solving (xi_createmesh) to check that meshing succeeds. FEMM
        requires a saved file, so the model is saved first. FEMM 5 returns no element count from
        createmesh; the count is reported by femm_solve (fast: a 10k-element static solve takes
        well under a second). Meshing errors usually mean open regions or overlapping lines."""
        def run(s: Session):
            doc = save_document(s)
            r = s.pre_call("createmesh")
            return {"document": doc, "meshed": True, "elements": r if isinstance(r, int) else None,
                    "note": "element count available after femm_solve"}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_solve(timeout: float = 600.0, hide_window: bool = True, load_solution: bool = True,
                   path: str | None = None, session: str = "main") -> dict:
        """Save, solve and load the solution in one call (xi_saveas + xi_analyze + xi_loadsolution).
        path: where to save (default: current file or <work_dir>/model.<ext>). timeout in seconds
        for the solver (AC/nonlinear models with >100k elements can take minutes). Returns solve
        time, node and element counts and the solution file. After this the post-processing tools
        (femm_point_values, femm_block_integral, femm_circuit_results, ...) work. Re-run after
        every geometry/material/current change: the loaded solution does not update itself."""
        return run_tool(ctx, session, lambda s: solve(s, timeout, hide_window, load_solution, path), need="document")

    @mcp.tool()
    def femm_load_solution(session: str = "main") -> dict:
        """Load the existing solution of the current (already solved) model into the post-processor
        (xi_loadsolution) without re-solving. Fails if the model was never solved."""
        def run(s: Session):
            s.pre_call("loadsolution")
            s.solved = True
            return {"nodes": s.post_call("numnodes"), "elements": s.post_call("numelements")}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_smartmesh(state: str = "on", scope: str = "document", session: str = "main") -> dict:
        """Smart meshing (automatic refinement near small features). state: on | off | default.
        scope: document (xi_smartmesh, saved with the model) or global (smartmesh(), whole engine;
        'default' defers to each file). Turn off for very large models to cut element count, then
        set mesh sizes explicitly on block labels."""
        def run(s: Session):
            st = state.strip().lower()
            code = {"on": 1, "off": 0, "default": -1, "1": 1, "0": 0, "-1": -1}.get(st)
            if code is None:
                raise ToolInputError(f"state must be on/off/default, got {state!r}", "Use on, off or default.")
            if scope == "global":
                s.call("smartmesh", code)
            else:
                if s.physics is None:
                    raise ToolInputError("no document open", "Call femm_new_document first or use scope='global'.")
                if code == -1:
                    raise ToolInputError("'default' only applies to scope='global'", "Use on or off.")
                s.pre_call("smartmesh", code)
            return {"smartmesh": st, "scope": scope}
        return run_tool(ctx, session, run)
