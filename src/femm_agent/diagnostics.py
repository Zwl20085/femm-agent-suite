"""Live health check: read the loaded magnetics solution through ``link.call`` and run the pure rules
of :mod:`femm_agent.health` on it.

Inputs: a link with a solved, *saved* magnetics model (``model_path`` = its .fem; the matching .ans
next to it supplies the element -> block label -> material map). Nothing is modified in the model.
"""
from __future__ import annotations

import math
import re
from typing import Any, Sequence

from . import femfile, health
from .experiments import BI_COENERGY, BI_ENERGY, BI_LOSS_TOTAL, BI_TORQUE, BI_FX, BI_FY, Ops, as_complex, as_float, \
    magnet_operating_points

ALL_CHECKS = ("mesh", "precision", "energy", "saturation", "boundary", "torque", "force", "ac", "flux", "pm")
STEEL_MU = 50.0


_ABC_RE = re.compile(r"^u\d+$")


def is_abc_shell(name: str | None) -> bool:
    """Materials ``u1``, ``u2``, ... are the graded shells written by ``mi_makeABC``."""
    return bool(name) and bool(_ABC_RE.match(name))


def _steel_kind(m: dict) -> str | None:
    """'nonlinear' / 'linear' steel, or None (air, copper, magnets, ABC shells)."""
    if is_abc_shell(m.get("BlockName")):
        return None
    if float(m.get("H_c") or 0) > 0:
        return None
    if m.get("BHPoints_data"):
        return "nonlinear"
    if float(m.get("Mu_x") or 1) >= STEEL_MU:
        return "linear"
    return None


def run(link, model_path: str, checks: Sequence[str] | None = None, *, rotor_groups: Sequence[int] | None = None,
        stator_groups: Sequence[int] | None = None, force_groups: Sequence[int] | None = None,
        reaction_groups: Sequence[int] | None = None, flux_lines: Sequence[Sequence[Sequence[float]]] | None = None,
        b_limit: float = 1.8, min_elements: int = 1000) -> dict[str, Any]:
    """Run the applicable checks; returns {"checks": [...], "summary": {...}, "facts": {...}}.

    ``rotor_groups`` / ``stator_groups``: WST torque on each must balance (T_rotor = -T_stator).
    ``force_groups`` / ``reaction_groups``: same for forces. ``flux_lines``: [[p1, p2], [p3, p4]]
    two cuts whose flux must match (e.g. a core leg and the gap). Skip rules with ``checks``."""
    import numpy as np

    want = set(checks or ALL_CHECKS)
    ops = Ops(link)
    model = femfile.parse_file(model_path)
    if model.physics != "magnetics":
        raise ValueError("the live health check currently covers magnetics models (.fem)")
    sol_path = femfile.solution_path(model_path)
    ans = femfile.parse_file(sol_path) if sol_path.is_file() else None
    out: list[dict] = []
    facts: dict[str, Any] = {"model": str(model_path), "solution": str(sol_path) if ans else None}

    bulk = ops.bulk()
    ne = len(bulk["tri"])
    facts["elements"] = ne
    facts["nodes"] = len(bulk["nodes"])
    bmag = np.hypot(bulk["B"][:, 0], bulk["B"][:, 1])
    facts["B_max_T"] = float(bmag.max()) if ne else 0.0
    if ans is not None and len(ans.element_labels()) != ne:
        out.append({"name": "solution_matches_model", "ok": False, "value": len(ans.element_labels()), "expected": ne,
                    "tolerance": 0, "message": "the .ans on disk does not match the loaded mesh: re-solve (femm_solve) first"})
        ans = None

    # -- mesh / precision
    if "mesh" in want:
        out.append(health.mesh_size(ne, min_elements=min_elements))
        ang = health.triangle_angles(bulk["nodes"], bulk["tri"])
        out.append(health.mesh_quality(ang, float(model.header.get("MinAngle", 30))))
        facts["min_angle_deg"] = float(ang.min()) if ne else None
    if "precision" in want:
        out.append(health.solver_precision(float(model.header.get("Precision", 1e-8))))

    # -- materials per element
    mats = {m.get("BlockName"): m for m in model.materials()}
    labels = model.block_labels()
    used = {lab["material"] for lab in labels}
    nonlinear = any(mats[n].get("BHPoints_data") for n in used if n in mats)
    has_pm = any(float(mats[n].get("H_c") or 0) > 0 for n in used if n in mats)
    linear = not nonlinear and not has_pm
    facts.update({"nonlinear": nonlinear, "has_magnets": has_pm, "frequency_Hz": model.frequency})
    elem_mat = None
    if ans is not None:
        li = ans.element_labels()
        names = [lab["material"] for lab in ans.block_labels()]
        elem_mat = np.array([names[i] if 0 <= i < len(names) else None for i in li], dtype=object)

    # -- energy
    circuits = [c.get("CircuitName") for c in model.circuits() if c.get("CircuitName")]
    if "energy" in want and model.frequency == 0:
        w = as_float(ops.block_integral(BI_ENERGY))
        wc = as_float(ops.block_integral(BI_COENERGY))
        facts.update({"energy_J": w, "coenergy_J": wc})
        out.append(health.energy_coenergy_linear(w, wc, linear, has_magnets=has_pm))
        cur, fl = [], []
        for c in circuits:
            cp = ops.circuit(c)
            cur.append(cp["current"].real)
            fl.append(cp["flux"].real)
        out.append(health.energy_consistency(w, fl, cur, linear=linear))

    # -- saturation
    if "saturation" in want and elem_mat is not None:
        kinds = np.array([_steel_kind(mats.get(n, {})) if n else None for n in elem_mat], dtype=object)
        nl = kinds == "nonlinear"
        if np.any(nl):
            out.append(health.saturation(bmag[nl], bulk["area"][nl], b_limit))
        lin = kinds == "linear"
        if np.any(lin):
            out.append(health.linear_material_overflux(bmag[lin]))

    # -- outer boundary
    if "boundary" in want:
        out.append(_boundary_check(model, ans, bulk, bmag, mats, elem_mat))

    # -- torque / force balance
    if "torque" in want and rotor_groups:
        tr = as_float(ops.block_integral(BI_TORQUE, rotor_groups))
        facts["torque_rotor_Nm"] = tr
        if stator_groups:
            ts = as_float(ops.block_integral(BI_TORQUE, stator_groups))
            facts["torque_stator_Nm"] = ts
            out.append(health.force_consistency(tr, -ts, "rotor WST torque", "-(stator WST torque)", 0.05,
                                                scale=max(abs(tr), abs(ts), 1e-3), name="torque_action_reaction"))
        ages = [b.get("BdryName") for b in model.boundaries() if int(b.get("BdryType", 0) or 0) in (6, 7)]
        for a in ages:
            tg = as_float(_first(ops.gap_integral(a, 0)))
            facts[f"torque_gap[{a}]_Nm"] = tg
            out.append({"name": f"torque_route[{a}]", "ok": None, "value": tg, "expected": None, "tolerance": None,
                        "message": f"air-gap element {a!r} present: use mo_gapintegral torque ({tg:.6g} N*m); the WST "
                                   "block integral does not see across an air-gap element (reads ~0)"})
    if "force" in want and force_groups:
        fx = as_float(ops.block_integral(BI_FX, force_groups))
        fy = as_float(ops.block_integral(BI_FY, force_groups))
        facts["force_N"] = [fx, fy]
        if reaction_groups:
            rx = as_float(ops.block_integral(BI_FX, reaction_groups))
            ry = as_float(ops.block_integral(BI_FY, reaction_groups))
            sc = max(math.hypot(fx, fy), 1e-6)
            out.append(health.force_consistency(fx, -rx, "Fx", "-(reaction Fx)", 0.05, scale=sc, name="force_x_action_reaction"))
            out.append(health.force_consistency(fy, -ry, "Fy", "-(reaction Fy)", 0.05, scale=sc, name="force_y_action_reaction"))

    # -- AC power balance
    if "ac" in want and model.frequency > 0 and circuits:
        pin = 0.0
        for c in circuits:
            cp = ops.circuit(c)
            pin += 0.5 * (cp["voltage"] * cp["current"].conjugate()).real
        ploss = as_float(ops.block_integral(BI_LOSS_TOTAL))
        facts.update({"P_in_W": pin, "P_loss_W": ploss})
        out.append(health.power_balance(pin, ploss))

    # -- flux conservation between two cuts
    if "flux" in want and flux_lines and len(flux_lines) >= 2:
        depth_m = float(model.header.get("Depth", 1) or 1) * model.unit_to_m
        f = [_cut_flux(ops, line, model, depth_m) for line in flux_lines[:2]]
        out.append(health.flux_conservation(f[0], f[1]))

    # -- permanent magnets
    if "pm" in want and has_pm and ans is not None:
        _, pm_checks = magnet_operating_points(ans, bulk["B"], bulk["area"])
        out.extend(pm_checks)

    try:
        ops.call("mo_clearblock")
    except Exception:
        pass
    return {"checks": out, "summary": health.summarize(out), "facts": facts}


def _first(v):
    return v[0] if isinstance(v, (list, tuple)) and v else v


def _cut_flux(ops: Ops, line, model, depth_m: float) -> float:
    (x1, y1), (x2, y2) = line[0], line[1]
    a1 = as_complex(ops.point(x1, y1)["A"]).real
    a2 = as_complex(ops.point(x2, y2)["A"]).real
    if model.problem_type == "axisymmetric":
        um = model.unit_to_m
        return 2 * math.pi * (x2 * um * a2 - x1 * um * a1)
    return (a2 - a1) * depth_m


def _boundary_check(model, ans, bulk, bmag, mats, elem_mat) -> dict:
    """Max |B| in elements touching the outer boundary vs the global max."""
    import numpy as np

    bdry = model.boundaries()
    abc = any(is_abc_shell(lab.get("material")) for lab in model.block_labels())
    open_bc = any(int(b.get("BdryType", 0) or 0) == 2 for b in bdry)
    edge_sel = None
    if ans is not None:
        el = ans.elements()
        if el.shape[1] >= 7:
            ex = el[:, 4:7]
            outer_ids = {i for i, b in enumerate(bdry) if int(b.get("BdryType", 0) or 0) in (0, 1, 2, 3)}
            if outer_ids:
                edge_sel = np.isin(ex, list(outer_ids)).any(axis=1)
    if edge_sel is None or not np.any(edge_sel):
        c = bulk["centroid"]
        xmin, xmax = c[:, 0].min(), c[:, 0].max()
        ymin, ymax = c[:, 1].min(), c[:, 1].max()
        tol = 0.02 * max(xmax - xmin, ymax - ymin)
        d = np.minimum.reduce([c[:, 0] - xmin, xmax - c[:, 0], c[:, 1] - ymin, ymax - c[:, 1]])
        edge_sel = d < tol
        if model.problem_type == "axisymmetric":
            edge_sel &= c[:, 0] > tol  # the axis is not an outer boundary
    contained = False
    if elem_mat is not None and np.any(edge_sel):
        steel = np.array([_steel_kind(mats.get(n, {})) is not None if n else False for n in elem_mat[edge_sel]])
        contained = bool(steel.mean() > 0.5)
    bb = float(bmag[edge_sel].max()) if np.any(edge_sel) else 0.0
    return health.boundary_distance(bb, float(bmag.max()) if len(bmag) else 0.0, has_open_boundary=open_bc,
                                    flux_contained=contained, abc_shells=abc)
