"""Document tools: new/open/save/close, problem definition and problem info (all four physics)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import DOC_EXTENSIONS, NEWDOCUMENT_CODES, PHYSICS
from ..sessions import PHYSICS_BY_EXT, Session
from ._common import ToolContext, ToolInputError, run_tool

SOLUTION_EXT = {".ans": "magnetics", ".res": "electrostatics", ".anh": "heatflow", ".anc": "currentflow"}
UNITS = ("inches", "millimeters", "centimeters", "mils", "meters", "micrometers")
UNIT_ALIASES = {"mm": "millimeters", "cm": "centimeters", "m": "meters", "in": "inches", "inch": "inches",
                "um": "micrometers", "mil": "mils", "millimetres": "millimeters", "metres": "meters",
                "centimetres": "centimeters", "micrometres": "micrometers"}
UNIT_TO_M = {"inches": 0.0254, "millimeters": 1e-3, "centimeters": 1e-2, "mils": 2.54e-5, "meters": 1.0,
             "micrometers": 1e-6}


def norm_physics(p: str) -> str:
    q = (p or "").strip().lower().replace(" ", "").replace("_", "")
    alias = {"magnetic": "magnetics", "mag": "magnetics", "electrostatic": "electrostatics", "es": "electrostatics",
             "heat": "heatflow", "thermal": "heatflow", "current": "currentflow", "conduction": "currentflow"}
    q = alias.get(q, q)
    if q not in PHYSICS:
        raise ToolInputError(f"unknown physics {p!r}", f"Use one of {', '.join(PHYSICS)}.")
    return q


def norm_units(u: str) -> str:
    v = UNIT_ALIASES.get(u.strip().lower(), u.strip().lower())
    if v not in UNITS:
        raise ToolInputError(f"unknown length unit {u!r}", f"Use one of {', '.join(UNITS)}.")
    return v


def resolve_path(s: Session, path: str | None, default_stem: str = "model") -> str:
    """Absolute forward-slash path; relative paths resolve against the session work dir."""
    ext = DOC_EXTENSIONS[s.physics] if s.physics else ".fem"
    if not path:
        p = s.work_dir / f"{default_stem}{ext}"
    else:
        p = Path(path)
        if not p.is_absolute():
            p = s.work_dir / p
        if not p.suffix:
            p = p.with_suffix(ext)
    return p.resolve().as_posix()


def save_document(s: Session, path: str | None = None) -> str:
    """Save the current pre-processor document (to `path`, the current document, or work_dir/model.<ext>)."""
    target = resolve_path(s, path) if path else (s.document or resolve_path(s, None))
    s.pre_call("saveas", target)
    s.document = target
    return target


def problem_info(s: Session) -> dict[str, Any]:
    """Labelled xi_getprobleminfo (and xo_ if solved). Verified layout for magnetics:
    [type(0 planar,1 axi), frequency Hz, depth (problem units in mi_, metres in mo_), length unit in m]."""
    out: dict[str, Any] = {"physics": s.physics, "document": s.document, "solved": s.solved}

    def label(v: Any, post: bool) -> Any:
        if not isinstance(v, list):
            return v
        if s.physics in ("magnetics", "currentflow") and len(v) >= 4:
            d = {"problem_type": "axi" if v[0] == 1 else "planar", "frequency_hz": v[1],
                 "depth" + ("_m" if post else "_problem_units"): v[2], "length_unit_m": v[3]}
        elif len(v) >= 3:
            d = {"problem_type": "axi" if v[0] == 1 else "planar",
                 "depth" + ("_m" if post else "_problem_units"): v[1], "length_unit_m": v[2]}
        else:
            return v
        units = {round(m, 12): k for k, m in UNIT_TO_M.items()}
        d["units"] = units.get(round(float(d["length_unit_m"]), 12))
        d["raw"] = v
        return d

    out["input"] = label(s.pre_call("getprobleminfo"), post=False)
    try:
        bb = s.pre_call("getboundingbox")
        if isinstance(bb, list) and len(bb) == 4:
            out["bounding_box"] = {"x_min": bb[0], "x_max": bb[1], "y_min": bb[2], "y_max": bb[3]}
    except Exception:
        pass
    if s.solved:
        try:
            out["solution"] = label(s.post_call("getprobleminfo"), post=True)
            out["nodes"] = s.post_call("numnodes")
            out["elements"] = s.post_call("numelements")
        except Exception as e:  # solution closed meanwhile
            out["solution_error"] = str(e)
    return out


def register(mcp, ctx: ToolContext) -> None:
    @mcp.tool()
    def femm_new_document(physics: str = "magnetics", session: str = "main") -> dict:
        """Create a new empty model: physics = magnetics | electrostatics | heatflow | currentflow.
        This defines the mi_/ei_/hi_/ci_ commands. Next: femm_problem_define (units, planar/axi,
        depth, frequency), then geometry, materials, labels, boundaries, femm_solve."""
        def run(s: Session):
            ph = norm_physics(physics)
            s.call("newdocument", NEWDOCUMENT_CODES[ph])
            s.physics, s.document, s.solved = ph, None, False
            s.notes.pop("axi", None)
            return {"physics": ph, "prefix": s.pre, "post_prefix": s.post, "default_extension": DOC_EXTENSIONS[ph]}
        return run_tool(ctx, session, run)

    @mcp.tool()
    def femm_open(path: str, session: str = "main") -> dict:
        """Open a FEMM model (.fem/.fee/.feh/.fec) or a solution (.ans/.res/.anh/.anc).
        Relative paths resolve against the session work dir; use forward slashes. Opening a
        solution makes the post-processor tools (femm_point_values, ...) available directly."""
        def run(s: Session):
            p = Path(path)
            if not p.is_absolute():
                p = s.work_dir / p
            if not p.is_file():
                raise ToolInputError(f"file not found: {p}", "Check the path; relative paths resolve against the session work_dir (see femm_session_list).")
            ext = p.suffix.lower()
            s.notes.pop("axi", None)
            s.call("opendocument", p.resolve().as_posix())
            if ext in PHYSICS_BY_EXT:
                s.physics, s.document, s.solved = PHYSICS_BY_EXT[ext], p.resolve().as_posix(), False
            elif ext in SOLUTION_EXT:
                s.physics, s.solved = SOLUTION_EXT[ext], True
                cand = p.with_suffix(DOC_EXTENSIONS[s.physics])
                s.document = cand.resolve().as_posix() if cand.is_file() else None
            else:
                raise ToolInputError(f"unknown FEMM file type {ext}", "Use .fem .fee .feh .fec or a solution .ans .res .anh .anc.")
            return {"opened": p.resolve().as_posix(), "physics": s.physics, "solved": s.solved}
        return run_tool(ctx, session, run)

    @mcp.tool()
    def femm_save(path: str | None = None, session: str = "main") -> dict:
        """Save the current model (xi_saveas). `path` absolute or relative to the work dir; the
        extension is added if missing. Without `path`: re-save the current file, or
        <work_dir>/model.<ext> for a new model. femm_solve saves automatically."""
        return run_tool(ctx, session, lambda s: {"saved": save_document(s, path)}, need="document")

    @mcp.tool()
    def femm_close_document(session: str = "main") -> dict:
        """Close the current pre-processor document and its post-processor (if any). The engine
        keeps running; call femm_new_document or femm_open next."""
        def run(s: Session):
            closed = []
            if s.physics:
                for label, prefix in (("post", s.post), ("pre", s.pre)):
                    try:
                        s.call(f"{prefix}_close")
                        closed.append(label)
                    except Exception:
                        pass
            s.physics, s.document, s.solved = None, None, False
            return {"closed": closed}
        return run_tool(ctx, session, run)

    @mcp.tool()
    def femm_problem_define(units: str = "millimeters", problem_type: str = "planar", depth: float | None = None,
                            frequency: float = 0.0, precision: float = 1e-8, min_angle: float = 30.0,
                            ac_solver: int | None = None, prev_solution: str | None = None,
                            time_step: float | None = None, session: str = "main") -> dict:
        """Define the problem for the current physics (wraps xi_probdef with the right argument order).

        units: millimeters|centimeters|meters|inches|mils|micrometers (aliases mm, cm, m, in, um).
        problem_type: planar | axi (axisymmetric: x is r >= 0, y is z, depth ignored).
        depth: out-of-plane length for planar models, in `units` (defaults to 1 unit with a warning:
          set it! e.g. stack length). frequency (Hz): magnetics (0 = magnetostatic) and currentflow
          only. precision: solver tolerance (1e-8 typical). min_angle: mesh quality, 30 deg default.
        ac_solver: magnetics only, 0 or 1 (successive approximation / Newton; see manual 2.2.6).
        prev_solution, time_step: heatflow transient only (previous .anh file, seconds).
        Orders used: mi(freq,units,type,prec,depth,minang,acsolver); ei(units,type,prec,depth,minang);
        hi(units,type,prec,depth,minang,prevsoln,dt); ci(units,type,freq,prec,depth,minang)."""
        def run(s: Session):
            ph = s.physics
            u = norm_units(units)
            pt = {"planar": "planar", "axi": "axi", "axisymmetric": "axi"}.get(problem_type.strip().lower())
            if pt is None:
                raise ToolInputError(f"problem_type must be planar or axi, got {problem_type!r}", "Use planar or axi.")
            warnings: list[str] = []
            d = depth
            if d is None:
                d = 1.0
                if pt == "planar":
                    warnings.append(f"depth not given: using 1 {u}. Results per unit depth are rarely what you want; pass depth.")
            if frequency and ph in ("electrostatics", "heatflow"):
                warnings.append(f"frequency ignored: {ph} problems are static")
            if ph == "magnetics":
                args: list[Any] = [float(frequency), u, pt, precision, d, min_angle]
                if ac_solver is not None:
                    args.append(int(ac_solver))
            elif ph == "electrostatics":
                args = [u, pt, precision, d, min_angle]
            elif ph == "heatflow":
                args = [u, pt, precision, d, min_angle]
                if prev_solution is not None or time_step is not None:
                    args += [prev_solution or "", float(time_step or 0)]
            else:
                args = [u, pt, float(frequency), precision, d, min_angle]
            s.pre_call("probdef", *args)
            s.notes["units"] = u
            s.notes["axi"] = pt == "axi"
            return {"command": f"{s.pre}_probdef", "args": args, "warnings": warnings}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_problem_info(session: str = "main") -> dict:
        """Problem definition as FEMM reports it (xi_getprobleminfo, and xo_getprobleminfo after a
        solve: note the post-processor reports depth in metres), the geometry bounding box, and
        node/element counts when solved."""
        return run_tool(ctx, session, problem_info, need="document")

    @mcp.tool()
    def femm_set_comment(comment: str, session: str = "main") -> dict:
        """Store a free-text comment/description in the model file (xi_setcomment). Single line."""
        def run(s: Session):
            s.pre_call("setcomment", comment.replace("\n", " "))
            return {"comment": comment}
        return run_tool(ctx, session, run, need="document")
