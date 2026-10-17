"""Shared plumbing for every tool group: the envelope, hints, and the tool context."""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..ipc import FemmError, FemmLinkError
from ..sessions import Session, SessionManager


@dataclass
class ToolContext:
    sessions: SessionManager
    repo_data: Path                    # the package's data/ folder (commands.json, materials/*.json)

    def session(self, name: str = "main") -> Session:
        return self.sessions.get(name)


def hint_for(err: Exception, session: Session | None = None) -> str:
    """Translate a FEMM error message into the next action the agent should take."""
    msg = str(err)
    low = msg.lower()
    if isinstance(err, FemmLinkError):
        if "not found" in low:
            return "Install FEMM 5 from https://www.femm.info or set FEMM_DIR to its bin folder, then call femm_status."
        return "The engine is gone. Call femm_session_open to start a new one (unsaved work is lost)."
    if "materials library" in low:
        return "Material name not in the FEMM 5 library (names changed since 4.2). Call femm_material_search with a partial name."
    if "name '" in low and "isn't defined" in low or "not defined" in low:
        if session is not None and session.physics is None:
            return "No document is open. Call femm_new_document or femm_open first."
        if "o_" in low[:12] or (session is not None and not session.solved):
            return "Postprocessor commands exist only after a solution is loaded. Call femm_solve (or femm_load_solution) first."
        return "Check the command name with femm_api_search."
    if "no document" in low:
        return "Call femm_new_document(physics=...) or femm_open(path) first."
    if "could not open" in low or "no such file" in low or "cannot open" in low:
        return "Check the path (use forward slashes, absolute paths) and that the file was saved with femm_save."
    if "mesh" in low or "triang" in low or "tangle" in low:
        return "Meshing failed: look for overlapping segments, unclosed regions or labels outside regions (femm_geometry_summary helps)."
    if "did not answer" in low or "timeout" in low:
        return "The call timed out. For long solves pass a larger timeout, or check femm_session_status."
    return "Read the message; if the command signature is in doubt, call femm_api_search(name)."


def envelope(fn: Callable[[], Any], session: Session | None = None, **extra: Any) -> dict[str, Any]:
    """Run `fn` and wrap it in the standard tool envelope."""
    t0 = time.time()
    out: dict[str, Any] = {"ok": True}
    if session is not None:
        out["session"] = session.name
    try:
        out["result"] = fn()
    except (FemmError, FemmLinkError) as e:
        out["ok"] = False
        out["error"] = {"message": str(e), "hint": hint_for(e, session)}
        if isinstance(e, FemmError) and e.command:
            out["error"]["command"] = e.command
    except Exception as e:  # programming or input error: still answer, never crash the server
        out["ok"] = False
        out["error"] = {"message": f"{type(e).__name__}: {e}", "hint": "Check the argument types and units in the tool description.",
                        "trace": traceback.format_exc(limit=3)}
    out["seconds"] = round(time.time() - t0, 3)
    out.update(extra)
    return out
