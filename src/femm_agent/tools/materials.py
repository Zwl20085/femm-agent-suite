"""Material tools: library search, load from library (with FEMM 4.2 rename help), custom materials."""
from __future__ import annotations

from typing import Any

from .. import ipc
from ..config import PHYSICS
from ..materials import MaterialLibrary, library
from ..sessions import Session
from ._common import ToolContext, ToolInputError, as_complex, as_list, envelope, run_tool

# xi_modifymaterial propnum maps (data/commands.json enums; mi_ order follows mi_addmaterial)
MODIFY_PROPS = {
    "magnetics": {"name": 0, "mu_x": 1, "mu_y": 2, "h_c": 3, "j": 4, "sigma": 5, "lam_d": 6, "phi_hmax": 7,
                  "lam_fill": 8, "lam_type": 9, "phi_hx": 10, "phi_hy": 11, "n_strands": 12, "wire_d": 13},
    "electrostatics": {"name": 0, "eps_x": 1, "eps_y": 2, "qv": 3},
    "heatflow": {"name": 0, "k_x": 1, "k_y": 2, "qv": 3, "kt": 4},
    "currentflow": {"name": 0, "sigma_x": 1, "sigma_y": 2, "eps_x": 3, "eps_y": 4, "ltx": 5, "lty": 6},
}


def _lib(ctx: ToolContext) -> MaterialLibrary:
    return library(ctx.sessions.install)


def load_materials(ctx: ToolContext, s: Session, names: list[str], fallback: bool) -> dict[str, Any]:
    lib = _lib(ctx)
    loaded, failed, renamed = [], [], {}
    for n in names:
        try:
            s.pre_call("getmaterial", n)
            loaded.append(n)
        except ipc.FemmError as e:
            if "materials library" not in e.message:
                raise
            sug = lib.suggest(n, physics=s.physics)
            if fallback and sug.get("best"):
                s.pre_call("getmaterial", sug["best"])
                loaded.append(sug["best"])
                renamed[n] = sug["best"]
            else:
                failed.append({"name": n, "message": e.message, **sug})
    out: dict[str, Any] = {"loaded": loaded}
    if renamed:
        out["renamed"] = renamed
        out["note"] = "Block labels must use the FEMM 5 names in 'renamed'."
    if failed:
        out["failed"] = failed
    return out


def register(mcp, ctx: ToolContext) -> None:
    @mcp.tool()
    def femm_material_search(query: str = "", physics: str = "magnetics", folder: str | None = None,
                             limit: int = 15) -> dict:
        """Fuzzy search of the FEMM 5 material library (no engine needed). Matches names and
        folders: 'M-19', 'silicon iron', 'N42', 'NdFeB', 'AWG 18', 'stainless', 'pure iron'.
        FEMM 4.2 names ('M-19 Steel', 'NdFeB 32 MGOe') are mapped to their FEMM 5 equivalents
        and ranked first. physics: magnetics|electrostatics|heatflow|currentflow. Returns name,
        folder and key properties (mu_r, Hc, sigma, nonlinear?). Empty query + folder lists a folder;
        empty query alone returns the family index."""
        def run():
            lib = _lib(ctx)
            if physics not in PHYSICS:
                raise ToolInputError(f"unknown physics {physics!r}", f"Use one of {PHYSICS}.")
            if not query and not folder:
                fam = lib.families(physics)
                return {"families": {k: (v if len(v) <= 12 else v[:12] + [f"... {len(v) - 12} more"]) for k, v in fam.items()},
                        "count": len(lib.names(physics)), "source": lib.sources.get(physics)}
            hits = lib.search(query, physics=physics, limit=limit, folder=folder)
            out: dict[str, Any] = {"matches": hits}
            if query and physics == "magnetics":
                leg = lib.legacy_lookup(query)
                if leg and leg != query:
                    out["fem42_rename"] = {query: leg}
            return out
        return envelope(run)

    @mcp.tool()
    def femm_material_get(name: str, physics: str = "magnetics", include_curve: bool = False) -> dict:
        """Full library record of one material (all keys of the .dat block: Mu_x, H_c, Sigma in MS/m,
        d_lam in mm, LamFill, LamType, WireD, ...). include_curve=True adds the B-H (or T-k) points.
        On a miss, returns suggestions (and the FEMM 4.2 -> 5 rename if known)."""
        def run():
            lib = _lib(ctx)
            m = lib.get(name, physics=physics)
            if m is None:
                sug = lib.suggest(name, physics=physics)
                raise ToolInputError(f"{name!r} is not in the {physics} library",
                                     f"Did you mean {sug.get('best')!r}? Nearest: {sug.get('nearest')}.")
            rec = {k: v for k, v in m.items() if include_curve or k not in ("BH_curve", "TK_curve")}
            for k in ("BH_curve", "TK_curve"):
                if k in m and not include_curve:
                    rec[k + "_points"] = len(m[k])
                    if m[k]:
                        rec[k + "_max"] = m[k][-1]
            return rec
        return envelope(run)

    @mcp.tool()
    def femm_material_load(names: list[str], fallback_to_suggestion: bool = False, session: str = "main") -> dict:
        """Copy materials from the FEMM 5 library into the current model (xi_getmaterial), for the
        session's physics. Names must match FEMM 5 exactly ('M-19 14 mil', 'N42', 'Copper', 'Air',
        '18 AWG'). On a miss the result lists suggestions; with fallback_to_suggestion=True the best
        suggestion (e.g. FEMM 4.2 'M-19 Steel' -> 'M-19 14 mil') is loaded instead and reported in
        'renamed' (use those names in femm_add_block_label)."""
        return run_tool(ctx, session, lambda s: load_materials(ctx, s, as_list(names), fallback_to_suggestion),
                        need="document")

    @mcp.tool()
    def femm_material_add(name: str, mu_x: float = 1.0, mu_y: float | None = None, h_c: float = 0.0, j: Any = 0.0,
                          sigma: float = 0.0, lam_d: float = 0.0, phi_hmax: float = 0.0, lam_fill: float = 1.0,
                          lam_type: int = 0, phi_hx: float = 0.0, phi_hy: float = 0.0, n_strands: int = 0,
                          wire_d: float = 0.0, eps_x: float = 1.0, eps_y: float | None = None, qv: float = 0.0,
                          k_x: float = 1.0, k_y: float | None = None, kt: float = 0.0,
                          sigma_x: float = 0.0, sigma_y: float | None = None, ltx: float = 0.0, lty: float = 0.0,
                          bh_points: list[list[float]] | None = None, session: str = "main") -> dict:
        """Define a custom material for the session's physics (xi_addmaterial). Only the arguments
        of that physics are used; *_y defaults to *_x.
        magnetics: mu_x, mu_y (relative), h_c (A/m, magnets), j (source current density MA/m^2,
          complex OK), sigma (MS/m), lam_d (lamination thickness mm), phi_hmax (hysteresis angle deg),
          lam_fill (0..1), lam_type (0 none, 1 laminated x, 2 laminated y, 3 magnet wire, 4 stranded,
          5 litz, 6 square wire), phi_hx, phi_hy, n_strands, wire_d (mm); bh_points [[B_T, H_A/m], ...]
          makes it nonlinear (mu ignored).
        electrostatics: eps_x, eps_y (relative), qv (C/m^3).
        heatflow: k_x, k_y (W/m/K), qv (W/m^3), kt (volumetric heat capacity MJ/m^3/K).
        currentflow: sigma_x, sigma_y (S/m), eps_x, eps_y, ltx, lty (loss tangents)."""
        def run(s: Session):
            ph = s.physics
            if ph == "magnetics":
                args: list[Any] = [name, mu_x, mu_x if mu_y is None else mu_y, h_c, as_complex(j), sigma, lam_d,
                                   phi_hmax, lam_fill, int(lam_type), phi_hx, phi_hy, int(n_strands), wire_d]
            elif ph == "electrostatics":
                args = [name, eps_x, eps_x if eps_y is None else eps_y, qv]
            elif ph == "heatflow":
                args = [name, k_x, k_x if k_y is None else k_y, qv, kt]
            else:
                args = [name, sigma_x, sigma_x if sigma_y is None else sigma_y, eps_x, eps_x if eps_y is None else eps_y, ltx, lty]
            s.pre_call("addmaterial", *args)
            out: dict[str, Any] = {"material": name, "command": f"{s.pre}_addmaterial",
                                   "args": [str(a) if isinstance(a, complex) else a for a in args]}
            if bh_points:
                if ph != "magnetics":
                    raise ToolInputError("bh_points is magnetics-only", "Use femm_material_add_bh for T-k curves in heat flow.")
                for b, hh in bh_points:
                    s.pre_call("addbhpoint", name, float(b), float(hh))
                out["bh_points"] = len(bh_points)
            return out
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_material_add_bh(name: str, points: list[list[float]], clear_first: bool = True,
                             session: str = "main") -> dict:
        """Give material `name` a nonlinear curve. Magnetics: points = [[B (T), H (A/m)], ...]
        starting at [0, 0], B and H strictly increasing (mi_addbhpoint). Heat flow: points =
        [[T (K), k (W/m/K)], ...] (hi_addtkpoint). clear_first removes the existing curve.
        The material must already exist in the model (femm_material_add or femm_material_load)."""
        def run(s: Session):
            ph = s.physics
            if ph not in ("magnetics", "heatflow"):
                raise ToolInputError(f"{ph} has no nonlinear material curves", "Only magnetics (B-H) and heatflow (T-k).")
            pts = [(float(a), float(b)) for a, b in points]
            warnings = []
            for (a0, b0), (a1, b1) in zip(pts, pts[1:]):
                if a1 <= a0 or b1 <= b0:
                    warnings.append(f"curve not strictly increasing between {[a0, b0]} and {[a1, b1]}")
                    break
            if ph == "magnetics" and pts and pts[0] != (0.0, 0.0):
                warnings.append("B-H curve should start at [0, 0]")
            if clear_first:
                s.pre_call("clearbhpoints" if ph == "magnetics" else "cleartkpoints", name)
            cmd = "addbhpoint" if ph == "magnetics" else "addtkpoint"
            for a, b in pts:
                s.pre_call(cmd, name, a, b)
            return {"material": name, "points": len(pts), "warnings": warnings}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_material_modify(name: str, changes: dict[str, Any], session: str = "main") -> dict:
        """Change properties of a material already in the model (xi_modifymaterial), e.g.
        {"mu_x": 2000, "sigma": 0} or {"name": "M19-hot"}. Keys per physics:
        magnetics name mu_x mu_y h_c j sigma lam_d phi_hmax lam_fill lam_type phi_hx phi_hy n_strands wire_d;
        electrostatics name eps_x eps_y qv; heatflow name k_x k_y qv kt;
        currentflow name sigma_x sigma_y eps_x eps_y ltx lty. Re-solve afterwards."""
        def run(s: Session):
            table = MODIFY_PROPS[s.physics]
            done = {}
            for k, v in changes.items():
                key = k.strip().lower()
                if key not in table:
                    raise ToolInputError(f"unknown property {k!r} for {s.physics}", f"Use one of {list(table)}.")
                s.pre_call("modifymaterial", name, table[key], v if key == "name" else as_complex(v))
                done[key] = v
            return {"material": name, "changed": done}
        return run_tool(ctx, session, run, need="document")
