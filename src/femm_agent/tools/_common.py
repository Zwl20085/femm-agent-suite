"""Shared plumbing for every tool group: the envelope, hints, and the tool context."""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..ipc import FemmError, FemmLinkError
from ..sessions import Session, SessionManager


@dataclass
class ToolContext:
    sessions: SessionManager
    repo_data: Path                    # the package's data/ folder (commands.json, materials/*.json)
    extras: dict = field(default_factory=dict)   # server-wide registry (tool groups loaded etc.)

    def session(self, name: str = "main") -> Session:
        return self.sessions.get(name)


class ToolInputError(Exception):
    """Bad input or wrong state detected by a tool before FEMM is called; carries the hint."""

    def __init__(self, message: str, hint: str = "Check the arguments in the tool description."):
        super().__init__(message)
        self.hint = hint


def require_document(s: Session) -> str:
    """Return the session physics or raise a ToolInputError with the right hint."""
    if s.physics is None:
        raise ToolInputError("no document is open in this session",
                             "Call femm_new_document(physics=...) or femm_open(path) first.")
    return s.physics


def require_solution(s: Session) -> str:
    ph = require_document(s)
    if not s.solved:
        raise ToolInputError("no solution is loaded in the post-processor",
                             "Call femm_solve (or femm_load_solution if the model was already solved) first.")
    return ph


def run_tool(ctx: "ToolContext", session: str, fn: Callable[[Session], Any], need: str | None = None,
             **extra: Any) -> dict[str, Any]:
    """Envelope + session acquisition: launches the session lazily *inside* the envelope so a missing
    FEMM install comes back as ``ok: false`` with an install hint. `need` is None, "document" or
    "solution"."""
    holder: dict[str, Session] = {}

    def inner() -> Any:
        s = ctx.session(session)
        holder["s"] = s
        if need == "document":
            require_document(s)
        elif need == "solution":
            require_solution(s)
        return fn(s)

    out = envelope(inner, None, **extra)
    s = holder.get("s")
    if not out["ok"] and s is not None:
        err = out.get("error", {})
        if isinstance(err, dict) and err.get("command") is not None:   # re-derive with session state
            err["hint"] = hint_for(FemmError(err["message"], err.get("command")), s)
    out = {"ok": out["ok"], "session": session, **{k: v for k, v in out.items() if k != "ok"}}
    return out


def as_complex(v: Any) -> Any:
    """Accept 1.5, [re, im], {"re":..,"im":..} or "1+2j"; return float or complex."""
    if v is None:
        return 0
    if isinstance(v, (int, float, complex)) and not isinstance(v, bool):
        return v
    if isinstance(v, (list, tuple)) and len(v) == 2:
        z = complex(float(v[0]), float(v[1]))
        return z if z.imag else z.real
    if isinstance(v, dict) and "re" in v:
        z = complex(float(v.get("re", 0)), float(v.get("im", 0)))
        return z if z.imag else z.real
    if isinstance(v, str):
        z = complex(v.replace(" ", "").replace("i", "j").replace("I", "j"))
        return z if z.imag else z.real
    raise ToolInputError(f"cannot read {v!r} as a number or complex", "Use a number, [re, im] or \"1+2j\".")


def jsonable(v: Any) -> Any:
    """Make FEMM replies JSON-safe: complex -> {"re", "im"} (or a float if purely real)."""
    if isinstance(v, complex):
        return {"re": v.real, "im": v.imag} if v.imag else v.real
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    return v


def as_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, tuple):
        return list(v)
    return [v]


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
    if "input in focus" in low or "output in focus" in low:
        return "That document was closed. Call femm_new_document or femm_open (pre-processor) or femm_solve/femm_load_solution (post-processor)."
    if "must be saved" in low:
        return "Save first with femm_save(path) (femm_solve and femm_create_mesh save automatically)."
    if "no contour" in low:
        return "Pass contour points to femm_line_integral / femm_make_plot (at least two [x, y] points)."
    if "no document" in low:
        return "Call femm_new_document(physics=...) or femm_open(path) first."
    if "could not open" in low or "no such file" in low or "cannot open" in low:
        return "Check the path (use forward slashes, absolute paths) and that the file was saved with femm_save."
    if "mesh" in low or "triang" in low or "tangle" in low:
        return "Meshing failed: look for overlapping segments, unclosed regions or labels outside regions (femm_geometry_summary helps)."
    if "did not answer" in low or "timeout" in low:
        return "The call timed out. For long solves pass a larger timeout to femm_solve, or check femm_session_list."
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
    except ToolInputError as e:
        out["ok"] = False
        out["error"] = {"message": str(e), "hint": e.hint}
    except Exception as e:  # programming or input error: still answer, never crash the server
        out["ok"] = False
        out["error"] = {"message": f"{type(e).__name__}: {e}",
                        "hint": getattr(e, "hint", None) or "Check the argument types and units in the tool description.",
                        "trace": traceback.format_exc(limit=3)}
    out["seconds"] = round(time.time() - t0, 3)
    out.update(extra)
    return out
