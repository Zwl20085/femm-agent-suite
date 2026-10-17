"""Property tools: block labels, boundaries, segment/arc/node properties, circuits, conductors."""
from __future__ import annotations

from typing import Any

from ..sessions import Session
from ._common import ToolContext, ToolInputError, as_complex, as_list, run_tool
from .geometry import _pt

# Boundary types per physics -> BdryFormat code (manual 3.6.9 / 3.8.9 / 3.10.9 / 3.12.9).
MAG_BC = {"prescribed_a": 0, "small_skin_depth": 1, "mixed": 2, "strategic_dual_image": 3, "periodic": 4,
          "antiperiodic": 5, "periodic_air_gap": 6, "antiperiodic_air_gap": 7}
ES_BC = {"fixed_voltage": 0, "mixed": 1, "surface_charge": 2, "periodic": 3, "antiperiodic": 4}
HEAT_BC = {"fixed_temperature": 0, "heat_flux": 1, "convection": 2, "radiation": 3, "periodic": 4, "antiperiodic": 5}
CUR_BC = {"fixed_voltage": 0, "mixed": 1, "surface_current": 2, "periodic": 3, "antiperiodic": 4}
BC_TABLE = {"magnetics": MAG_BC, "electrostatics": ES_BC, "heatflow": HEAT_BC, "currentflow": CUR_BC}
_BC_ALIASES = {"a0": "prescribed_a", "a=0": "prescribed_a", "dirichlet": "prescribed_a", "prescribed": "prescribed_a",
               "sliding_band": "periodic_air_gap", "air_gap": "periodic_air_gap", "age": "periodic_air_gap",
               "anti_periodic": "antiperiodic", "anti-periodic": "antiperiodic",
               "anti_periodic_air_gap": "antiperiodic_air_gap", "voltage": "fixed_voltage", "temperature": "fixed_temperature",
               "flux": "heat_flux", "sdi": "strategic_dual_image"}
NONE = "<None>"


def _real(x: Any) -> float:
    z = as_complex(x)
    if isinstance(z, complex):
        if z.imag:
            raise ToolInputError(f"{x!r} must be real for this physics", "Pass a plain number.")
        return float(z.real)
    return float(z)


def _bc_code(physics: str, bc_type: str | int) -> int:
    table = BC_TABLE[physics]
    if isinstance(bc_type, int):
        if bc_type not in table.values():
            raise ToolInputError(f"BdryFormat {bc_type} invalid for {physics}", f"Use one of {table}.")
        return bc_type
    k = bc_type.strip().lower().replace(" ", "_")
    k = _BC_ALIASES.get(k, k)
    if physics != "magnetics" and k == "prescribed_a":
        k = "fixed_voltage" if physics != "heatflow" else "fixed_temperature"
    if k not in table:
        raise ToolInputError(f"unknown boundary type {bc_type!r} for {physics}", f"Use one of {list(table)}.")
    return table[k]


def set_block(s: Session, x: float, y: float, material: str, mesh_size: float | None, circuit: str,
              magdir: float, group: int, turns: int) -> list[Any]:
    automesh = 1 if mesh_size in (None, 0) else 0
    ms = 0 if mesh_size is None else float(mesh_size)
    s.pre_call("clearselected")
    s.pre_call("selectlabel", x, y)
    if s.physics == "magnetics":
        args: list[Any] = [material, automesh, ms, circuit or "", float(magdir), int(group), int(turns)]
    else:
        args = [material, automesh, ms, int(group)]
    s.pre_call("setblockprop", *args)
    s.pre_call("clearselected")
    return args


def _select_each(s: Session, fn: str, points: Any) -> list[Any]:
    s.pre_call("clearselected")
    picks = []
    for p in as_list(points):
        picks.append(s.pre_call(fn, *_pt(p)))
    return picks


def register(mcp, ctx: ToolContext) -> None:
    @mcp.tool()
    def femm_add_block_label(x: float, y: float, material: str, mesh_size: float | None = None, circuit: str = "",
                             magdir: float = 0.0, group: int = 0, turns: int = 1, session: str = "main") -> dict:
        """Add a block label at (x, y) inside a closed region and assign its properties in one call.

        material: a name already loaded/defined (femm_material_load / femm_material_add), or
          "<No Mesh>" for a hole. mesh_size: max element size in problem units, None = automatic.
        Magnetics only: circuit (name from femm_add_circuit, "" for none), magdir (magnetisation
          direction in degrees for magnets), turns (number of turns of this block in the circuit;
          negative = opposite direction). group: integer group for selection/integrals.
        Each closed region needs exactly one label; a label in the wrong region is a common bug
        (check with femm_geometry_summary)."""
        def run(s: Session):
            s.pre_call("addblocklabel", x, y)
            args = set_block(s, x, y, material, mesh_size, circuit, magdir, group, turns)
            return {"label": [x, y], "setblockprop": args}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_set_block_prop(x: float, y: float, material: str, mesh_size: float | None = None, circuit: str = "",
                            magdir: float = 0.0, group: int = 0, turns: int = 1, session: str = "main") -> dict:
        """Change the properties of the existing block label nearest (x, y) (same arguments as
        femm_add_block_label). Use to swap materials or currents between solves."""
        def run(s: Session):
            args = set_block(s, x, y, material, mesh_size, circuit, magdir, group, turns)
            return {"label": [x, y], "setblockprop": args}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_add_boundary(name: str, bc_type: str = "prescribed_a", a0: float = 0.0, a1: float = 0.0, a2: float = 0.0,
                          phi: float = 0.0, mu: float = 0.0, sigma: float = 0.0, c0: Any = 0.0, c1: Any = 0.0,
                          inner_angle: float = 0.0, outer_angle: float = 0.0, value: Any = 0.0, flux: Any = 0.0,
                          h: float = 0.0, t_inf: float = 0.0, beta: float = 0.0, t_inf_rad: float = 0.0,
                          segments: list[list[float]] | None = None, arcs: list[list[float]] | None = None,
                          arc_maxseg: float = 1.0, session: str = "main") -> dict:
        """Define a boundary condition for the current physics and (optionally) assign it.

        Magnetics bc_type (mi_addboundprop, 12 args):
          prescribed_a (A = a0 + a1*x + a2*y, phase phi; A=0 is the usual outer boundary),
          small_skin_depth (mu = relative permeability, sigma MS/m), mixed (c0, c1 complex OK),
          strategic_dual_image, periodic, antiperiodic, periodic_air_gap / antiperiodic_air_gap
          (sliding band: inner_angle/outer_angle = rotor/stator shift in degrees). Assign it to
          BOTH concentric arcs of the gap annulus and put a "<No Mesh>" block label inside the
          annulus (verified: without it the solver stops with "a region has no material assigned").
        Electrostatics: fixed_voltage (value = V), mixed (c0, c1), surface_charge (flux = C/m^2),
          periodic, antiperiodic. Currentflow: fixed_voltage (value), mixed, surface_current (flux),
          periodic, antiperiodic. Heatflow: fixed_temperature (value = K), heat_flux (flux W/m^2),
          convection (h W/m^2K, t_inf K), radiation (beta emissivity, t_inf_rad K), periodic, antiperiodic.
        segments / arcs: [[x, y], ...] points ON the segments/arcs (e.g. midpoints) to assign this
        boundary to (each picks the nearest). Periodic pairs need one boundary per pair, assigned
        to both sides. For an unbounded open boundary see femm_call('mi_makeABC')."""
        def run(s: Session):
            ph = s.physics
            code = _bc_code(ph, bc_type)
            if ph == "magnetics":
                args: list[Any] = [name, a0, a1, a2, phi, mu, sigma, as_complex(c0), as_complex(c1), code]
                if code in (6, 7) or inner_angle or outer_angle:
                    args += [inner_angle, outer_angle]
            elif ph == "electrostatics":
                args = [name, _real(value), _real(flux), _real(c0), _real(c1), code]
            elif ph == "currentflow":
                args = [name, as_complex(value), as_complex(flux), as_complex(c0), as_complex(c1), code]
            else:
                args = [name, code, _real(value), _real(flux), t_inf, h, beta, t_inf_rad]
            s.pre_call("addboundprop", *args)
            assigned = {"segments": 0, "arcs": 0}
            if segments:
                _select_each(s, "selectsegment", segments)
                if ph == "magnetics":
                    s.pre_call("setsegmentprop", name, 0, 1, 0, 0)
                else:
                    s.pre_call("setsegmentprop", name, 0, 1, 0, 0, NONE)
                s.pre_call("clearselected")
                assigned["segments"] = len(segments)
            if arcs:
                _select_each(s, "selectarcsegment", arcs)
                if ph == "magnetics":
                    s.pre_call("setarcsegmentprop", arc_maxseg, name, 0, 0)
                else:
                    s.pre_call("setarcsegmentprop", arc_maxseg, name, 0, 0, NONE)
                s.pre_call("clearselected")
                assigned["arcs"] = len(arcs)
            return {"command": f"{s.pre}_addboundprop", "BdryFormat": code, "args": [str(a) if isinstance(a, complex) else a for a in args],
                    "assigned": assigned}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_set_segment_prop(points: list[list[float]], boundary: str = "", mesh_size: float | None = None,
                              hide: bool = False, group: int = 0, conductor: str = "", session: str = "main") -> dict:
        """Select the segments nearest each of `points` (e.g. midpoints) and set boundary name ("" = none),
        mesh_size (max element size along the segment; None = automatic), hide-in-postprocessor flag,
        group, and (non-magnetics) conductor name."""
        def run(s: Session):
            picks = _select_each(s, "selectsegment", points)
            auto = 1 if mesh_size in (None, 0) else 0
            args: list[Any] = [boundary, 0 if mesh_size is None else float(mesh_size), auto, int(hide), int(group)]
            if s.physics != "magnetics":
                args.append(conductor or NONE)
            s.pre_call("setsegmentprop", *args)
            s.pre_call("clearselected")
            return {"segments": len(picks), "picked": picks, "args": args}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_set_arc_prop(points: list[list[float]], max_seg_deg: float = 1.0, boundary: str = "", hide: bool = False,
                          group: int = 0, conductor: str = "", session: str = "main") -> dict:
        """Select the arcs nearest each of `points` and set discretisation (max_seg_deg, degrees per
        straight piece; air gaps want <= 1), boundary name, hide flag, group, (non-magnetics) conductor."""
        def run(s: Session):
            picks = _select_each(s, "selectarcsegment", points)
            args: list[Any] = [float(max_seg_deg), boundary, int(hide), int(group)]
            if s.physics != "magnetics":
                args.append(conductor or NONE)
            s.pre_call("setarcsegmentprop", *args)
            s.pre_call("clearselected")
            return {"arcs": len(picks), "picked": picks, "args": args}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_set_node_prop(points: list[list[float]], prop: str = "", group: int = 0, conductor: str = "",
                           session: str = "main") -> dict:
        """Select the nodes nearest each of `points` and set a point property (from
        femm_add_point_prop, "" = none), group and (non-magnetics) conductor."""
        def run(s: Session):
            picks = _select_each(s, "selectnode", points)
            args: list[Any] = [prop, int(group)]
            if s.physics != "magnetics":
                args.append(conductor or NONE)
            s.pre_call("setnodeprop", *args)
            s.pre_call("clearselected")
            return {"nodes": len(picks), "picked": picks, "args": args}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_add_circuit(name: str, current: Any = 0.0, series: bool = True, session: str = "main") -> dict:
        """Magnetics: define a circuit carrying `current` amps (peak for AC; [re, im] or "1+2j" for
        phase). series=True: every block in it carries `current` per turn (set turns on the block
        labels; stranded coils). series=False (parallel): `current` is the total, split between
        blocks by impedance (solid conductors). Results: femm_circuit_results."""
        def run(s: Session):
            if s.physics != "magnetics":
                raise ToolInputError("circuits are magnetics-only", "For other physics use femm_add_conductor.")
            i = as_complex(current)
            s.pre_call("addcircprop", name, i, 1 if series else 0)
            return {"circuit": name, "current": str(i) if isinstance(i, complex) else i, "series": series}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_modify_circuit(name: str, current: float | None = None, series: bool | None = None,
                            new_name: str | None = None, session: str = "main") -> dict:
        """Change a circuit: current (A, real; for complex use femm_call('mi_modifycircprop', ...)),
        series/parallel, or rename (mi_modifycircprop propnum 1 / 2 / 0). Re-solve afterwards."""
        def run(s: Session):
            done = {}
            if current is not None:
                s.pre_call("modifycircprop", name, 1, float(current))
                done["current"] = current
            if series is not None:
                s.pre_call("modifycircprop", name, 2, 1 if series else 0)
                done["series"] = series
            if new_name:
                s.pre_call("modifycircprop", name, 0, new_name)
                done["name"] = new_name
            if not done:
                raise ToolInputError("nothing to change", "Pass current, series or new_name.")
            return done
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_add_conductor(name: str, fixed: str = "voltage", value: Any = 0.0, session: str = "main") -> dict:
        """Electrostatics / heat flow / current flow: define a conductor property.
        fixed: electrostatics 'voltage' (value V) or 'charge' (value C/m);
               heatflow 'temperature' (value K) or 'flux' (value W/m, total heat);
               currentflow 'voltage' (V) or 'current' (A; complex OK at AC).
        Assign it to segments/arcs/nodes with femm_set_segment_prop(conductor=name) etc.
        Results after solving: femm_circuit_results(name)."""
        def run(s: Session):
            ph = s.physics
            if ph == "magnetics":
                raise ToolInputError("magnetics uses circuits", "Use femm_add_circuit.")
            f = fixed.strip().lower()
            allowed = {"electrostatics": {"voltage": 1, "charge": 0},
                       "heatflow": {"temperature": 1, "flux": 0, "heat": 0},
                       "currentflow": {"voltage": 1, "current": 0}}[ph]
            typ = allowed.get(f)
            if typ is None:
                raise ToolInputError(f"unknown fixed={fixed!r} for {ph}", f"Use one of {list(allowed)}.")
            v: Any = as_complex(value) if ph == "currentflow" else _real(value)
            args: list[Any] = [name, v if typ == 1 else 0, v if typ == 0 else 0, typ]
            s.pre_call("addconductorprop", *args)
            return {"conductor": name, "args": [str(a) if isinstance(a, complex) else a for a in args]}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_add_point_prop(name: str, value: Any = 0.0, source: Any = 0.0, points: list[list[float]] | None = None,
                            session: str = "main") -> dict:
        """Define a nodal point property and optionally assign it to the nodes nearest `points`.
        magnetics: value = prescribed A (Wb/m), source = point current (A).
        electrostatics: value = V, source = point charge (C/m). heatflow: value = T (K),
        source = point heat (W/m). currentflow: value = V, source = point current (A/m)."""
        def run(s: Session):
            if s.physics in ("electrostatics", "heatflow"):
                v, q = _real(value), _real(source)
            else:
                v, q = as_complex(value), as_complex(source)
            s.pre_call("addpointprop", name, v, q)
            n = 0
            if points:
                _select_each(s, "selectnode", points)
                args: list[Any] = [name, 0]
                if s.physics != "magnetics":
                    args.append(NONE)
                s.pre_call("setnodeprop", *args)
                s.pre_call("clearselected")
                n = len(points)
            return {"point_prop": name, "assigned_nodes": n}
        return run_tool(ctx, session, run, need="document")
