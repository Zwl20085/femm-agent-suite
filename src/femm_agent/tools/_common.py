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


# The canonical loop, shared by femm_status (next_steps) and the server INSTRUCTIONS.
NEXT_STEPS: tuple[str, ...] = (
    "1. femm_status (install found? first-run note?)",
    "2. femm_session_open (optional) -> femm_new_document(physics=...) or femm_open(path)",
    "3. geometry: femm_problem_define, femm_draw_rectangle / femm_draw_polygon / femm_add_nodes + femm_add_segments",
    "4. materials, labels, boundaries: femm_material_load, femm_add_block_label, femm_add_boundary, femm_add_circuit",
    "5. femm_create_mesh (optional) -> femm_solve",
    "6. femm_health_check (magnetics; femm_check_rule otherwise) - ok:false or verdict FAIL is a stop sign",
    "7. post-process and report: femm_point_values / femm_block_integral / femm_circuit_results / experiments "
    "-> femm_report (relay its doubts)",
)

# message fragment (lower case) -> next action. First match wins; used for ToolInputError without an
# explicit hint, for unrecognised FEMM errors and for plain ValueErrors from the engineering layer.
MESSAGE_HINTS: tuple[tuple[str, str], ...] = (
    ("no circuits", "Add one with femm_add_circuit(name=...), then put coil labels in it with "
                    "femm_set_block_prop(x=, y=, material=, circuit=<name>, turns=<N>)."),
    ("needs gap_boundary", "Pass gap_boundary=<name of the periodic air-gap boundary from "
                           "femm_geometry_summary().boundaries>, or use method='rotate'."),
    ("no boundary named", "List them: femm_geometry_summary() and read result.boundaries; pass one of "
                          "those names exactly."),
    ("not a (anti)periodic air gap", "Pick the boundary of type 'periodic air gap' / 'antiperiodic air gap' in "
                                     "femm_geometry_summary().boundaries, or use method='rotate'."),
    ("method must be", "Use method='rotate' (rotate the rotor groups and re-mesh) or method='age' "
                       "(with gap_boundary=<air-gap boundary name>)."),
    ("no objects in group", "Use a group listed in the message (femm_geometry_summary().groups), or tag the "
                            "moving parts first with femm_set_group."),
    ("circuit not in the model", "Use a circuit listed in the message, or create it with femm_add_circuit."),
    ("steps must be", "Pass steps >= 1 (>= 3 for the virtual-work check)."),
    ("dx and dy cannot both be zero", "Pass a non-zero step, e.g. dy=0.25 (problem units per step)."),
    ("setup command", "Only preprocessor commands (mi_*, ei_*, hi_*, ci_*) are allowed in case.commands; "
                      "use outputs=[...] for post-processing."),
    ("unknown point quantity", "Use quantity B, Bx, By, H, Hx, Hy, A, mu or J (or a raw field name such as Js)."),
    ("unknown output kind", "Use kind point, block, circuit, gap, line or expr."),
    ("element count mismatch", "Re-solve with femm_solve, then repeat the call."),
    ("magnetics (.fem) document", "Open or create a magnetics model: femm_new_document(physics='magnetics') "
                                  "or femm_open(path) or femm_build_benchmark(kind)."),
    ("exactly one of poles", "Give exactly one of poles (number of poles, 2p, preferred) or pole_pairs (p)."),
    ("currents must", "Pass currents as a list of non-zero amps, e.g. currents=[1, 2, 5, 10]."),
)
DEFAULT_INPUT_HINT = "Check the arguments against the tool description (units, list shapes, names)."


def message_hint(message: str) -> str | None:
    """Next-action hint for a known error message fragment, else None."""
    low = message.lower()
    for frag, hint in MESSAGE_HINTS:
        if frag in low:
            return hint
    return None


class ToolInputError(Exception):
    """Bad input or wrong state detected by a tool before FEMM is called; carries the hint.
    Without an explicit hint the message is looked up in MESSAGE_HINTS."""

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint or message_hint(message) or DEFAULT_INPUT_HINT


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
    if "no results file" in low:
        return "This model has no solution file yet. Call femm_solve."
    if "must be saved" in low:
        return "Save first with femm_save(path) (femm_solve and femm_create_mesh save automatically)."
    if "no contour" in low:
        return "Pass contour points to femm_line_integral / femm_make_plot (at least two [x, y] points)."
    if "no document" in low:
        return "Call femm_new_document(physics=...) or femm_open(path) first."
    if "could not open" in low or "no such file" in low or "cannot open" in low:
        return "Check the path (use forward slashes, absolute paths) and that the file was saved with femm_save."
    if "no material assigned" in low:
        return ("A closed region has no block label. Add one with femm_add_block_label (use material '<No Mesh>' "
                "for holes and for the annulus of an air-gap element); femm_geometry_summary lists label counts.")
    if "mesh" in low or "triang" in low or "tangle" in low:
        return "Meshing failed: look for overlapping segments, unclosed regions or labels outside regions (femm_geometry_summary helps)."
    if "did not answer" in low or "timeout" in low:
        return ("The call timed out: retry femm_solve(timeout=<2x the current value> s); if it times out again "
                "check femm_session_list for a stuck engine and femm_session_close it.")
    table = message_hint(msg)
    if table:
        return table
    return "Look the command up with femm_api_get(name) to check its arguments, then retry with corrected values."


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
    except ValueError as e:
        if not getattr(e, "tool_input", False):   # plain ValueError: programming/argument error below
            out["ok"] = False
            out["error"] = {"message": f"{type(e).__name__}: {e}",
                            "hint": getattr(e, "hint", None) or message_hint(str(e))
                            or "Check the argument types and units in the tool description.",
                            "trace": traceback.format_exc(limit=3)}
        else:                                       # input error raised by a pure engineering module
            out["ok"] = False
            out["error"] = {"message": str(e), "hint": getattr(e, "hint", None) or message_hint(str(e))
                            or DEFAULT_INPUT_HINT}
    except Exception as e:  # programming or input error: still answer, never crash the server
        out["ok"] = False
        out["error"] = {"message": f"{type(e).__name__}: {e}",
                        "hint": getattr(e, "hint", None) or message_hint(str(e))
                        or "Check the argument types and units in the tool description.",
                        "trace": traceback.format_exc(limit=3)}
    out["seconds"] = round(time.time() - t0, 3)
    out.update(extra)
    return out


def record_estimate(ctx: ToolContext, session: str, rec: dict) -> None:
    """Keep an estimate comparison for femm_report: in the open session's notes, else (session not
    started yet) in ctx.extras["estimates_pending"][session], merged when the report is built."""
    s = ctx.sessions.sessions.get(session)
    if s is not None:
        s.notes.setdefault("estimates", []).append(rec)
    else:
        ctx.extras.setdefault("estimates_pending", {}).setdefault(session, []).append(rec)


def session_estimates(ctx: ToolContext, s: Session) -> list[dict]:
    return list(s.notes.get("estimates", [])) + list(ctx.extras.get("estimates_pending", {}).get(s.name, []))
