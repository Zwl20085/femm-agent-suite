"""Post-processing tools: point values, integrals, circuits, bulk arrays, field statistics,
air-gap results, line plots and screenshots. All need a loaded solution (femm_solve)."""
from __future__ import annotations

import csv
import math
import time
from pathlib import Path
from typing import Any

from .. import catalog
from ..sessions import Session
from ._common import ToolContext, ToolInputError, as_list, jsonable, run_tool
from .geometry import _pt

# (key, unit) in the order returned by xo_getpointvalues (manual 3.7 / 3.9 / 3.11 / 3.13).
# 1/2 components are x/y for planar problems and r/z for axisymmetric ones.
POINT_FIELDS = {
    "magnetics": [("A", "Wb/m"), ("B1", "T"), ("B2", "T"), ("sigma", "MS/m"), ("energy_density", "J/m^3"),
                  ("H1", "A/m"), ("H2", "A/m"), ("J_eddy", "MA/m^2"), ("J_source", "MA/m^2"), ("mu1", "relative"),
                  ("mu2", "relative"), ("P_ohmic", "W/m^3"), ("P_hyst", "W/m^3"), ("fill_factor", "")],
    "electrostatics": [("V", "V"), ("D1", "C/m^2"), ("D2", "C/m^2"), ("E1", "V/m"), ("E2", "V/m"),
                       ("eps1", "relative"), ("eps2", "relative"), ("energy_density", "J/m^3")],
    "heatflow": [("T", "K"), ("F1", "W/m^2"), ("F2", "W/m^2"), ("G1", "K/m"), ("G2", "K/m"),
                 ("k1", "W/(m K)"), ("k2", "W/(m K)")],
    "currentflow": [("V", "V"), ("J1", "A/m^2"), ("J2", "A/m^2"), ("K1", "S/m (AC conductivity)"),
                    ("K2", "S/m (AC conductivity)"), ("E1", "V/m"), ("E2", "V/m"), ("eps1", "relative"),
                    ("eps2", "relative"), ("Jd1", "A/m^2"), ("Jd2", "A/m^2"), ("sigma1", "S/m"),
                    ("sigma2", "S/m"), ("Jc1", "A/m^2"), ("Jc2", "A/m^2")],
}
MAGNITUDE_OF = {"magnetics": ("B", "B1", "B2", "T"), "electrostatics": ("E", "E1", "E2", "V/m"),
                "heatflow": ("F", "F1", "F2", "W/m^2"), "currentflow": ("J", "J1", "J2", "A/m^2")}
DEFAULT_BLOCK_CODES = {"magnetics": [2, 17, 5, 10, 7], "electrostatics": [0, 1, 2],
                       "heatflow": [0, 1, 2], "currentflow": [0, 1, 4, 5]}
DEFAULT_LINE_CODES = {"magnetics": [0, 1, 2], "electrostatics": [0, 1, 2], "heatflow": [0, 1, 2, 3],
                      "currentflow": [0, 1, 2]}
# bulk getters: name -> (command suffix, columns, column names, located on)
BULK = {
    "magnetics": {"nodes": ("getallnodes", 2, ["x", "y"], "node"),
                  "elements": ("getallelements", 7, ["n1", "n2", "n3", "cx", "cy", "area", "group"], "element"),
                  "b": ("getallb", 2, ["B1", "B2"], "element"), "a": ("getalla", 1, ["A"], "element")},
    "electrostatics": {"nodes": ("getallnodes", 2, ["x", "y"], "node"),
                       "elements": ("getallelements", 7, ["n1", "n2", "n3", "cx", "cy", "area", "group"], "element"),
                       "v": ("getallv", 1, ["V"], "node"), "d": ("getalld", 2, ["D1", "D2"], "element")},
    "heatflow": {"nodes": ("getallnodes", 2, ["x", "y"], "node"),
                 "elements": ("getallelements", 7, ["n1", "n2", "n3", "cx", "cy", "area", "group"], "element"),
                 "t": ("getallt", 1, ["T"], "node"), "f": ("getallf", 2, ["F1", "F2"], "element")},
    "currentflow": {"nodes": ("getallnodes", 2, ["x", "y"], "node"),
                    "elements": ("getallelements", 7, ["n1", "n2", "n3", "cx", "cy", "area", "group"], "element"),
                    "v": ("getallv", 1, ["V"], "node"), "j": ("getallj", 2, ["J1", "J2"], "element")},
}
VECTOR_KEY = {"magnetics": "b", "electrostatics": "d", "heatflow": "f", "currentflow": "j"}
GAP_INTEGRALS = {0: "torque_dc_Nm", 1: "force_dc_N", 2: "stored_energy_J", 3: "torque_2x_Nm", 4: "force_2x_N",
                 5: "interaction_torque_Nm", 6: "interaction_force_N"}
DENSITY_DEFAULT = {"magnetics": "bmag", "electrostatics": 0, "heatflow": 0, "currentflow": 3}


def _is_axi(s: Session) -> bool:
    if "axi" not in s.notes:
        try:
            info = s.pre_call("getprobleminfo")
            s.notes["axi"] = isinstance(info, list) and info[0] == 1
        except Exception:
            s.notes["axi"] = False
    return bool(s.notes["axi"])


def _rename(key: str, axi: bool) -> str:
    if key[-1:] in ("1", "2") and key[:-1] not in ("",):
        return key[:-1] + (("r" if key[-1] == "1" else "z") if axi else ("x" if key[-1] == "1" else "y"))
    return key


def _mag(a: Any, b: Any) -> float:
    return math.sqrt(abs(a) ** 2 + abs(b) ** 2)


def point_values(s: Session, x: float, y: float) -> dict[str, Any]:
    raw = s.post_call("getpointvalues", x, y)
    if raw is None:
        return {"x": x, "y": y, "outside": True}
    fields = POINT_FIELDS[s.physics]
    raw = as_list(raw)
    axi = _is_axi(s)
    vals: dict[str, Any] = {"x": x, "y": y}
    for (k, _u), v in zip(fields, raw):
        vals[_rename(k, axi)] = jsonable(v)
    mk, c1, c2, _u = MAGNITUDE_OF[s.physics]
    d = dict(zip([f[0] for f in fields], raw))
    if c1 in d and c2 in d:
        vals["|" + mk + "|"] = _mag(d[c1], d[c2])
    return vals


def units_table(s: Session) -> dict[str, str]:
    axi = _is_axi(s)
    t = {_rename(k, axi): u for k, u in POINT_FIELDS[s.physics]}
    mk, _a, _b, u = MAGNITUDE_OF[s.physics]
    t["|" + mk + "|"] = u
    return t


def _code_names(s: Session, cmd: str) -> dict[str, str]:
    c = catalog.get(f"{s.post}_{cmd}") or {}
    return (c.get("enums") or {}).get("type", {})


def _select_blocks(s: Session, points: Any, group: Any) -> int:
    s.post_call("clearblock")
    n = 0
    for p in as_list(points):
        s.post_call("selectblock", *_pt(p))   # NB: selectblock toggles; we start from a cleared selection
        n += 1
    for g in as_list(group):
        s.post_call("groupselectblock", int(g))
        n += 1
    return n


def _set_contour(s: Session, points: Any) -> int:
    pts = [_pt(p) for p in as_list(points)]
    if len(pts) < 2:
        raise ToolInputError("a contour needs at least 2 points", "Pass contour=[[x1, y1], [x2, y2], ...].")
    s.post_call("clearcontour")
    for p in pts:
        s.post_call("addcontour", *p)
    return len(pts)


def _stats(vals: list[float], weights: list[float] | None = None) -> dict[str, Any]:
    if not vals:
        return {"n": 0}
    n = len(vals)
    out: dict[str, Any] = {"n": n, "min": min(vals), "max": max(vals)}
    if weights:
        w = sum(weights)
        out["mean"] = sum(v * a for v, a in zip(vals, weights)) / w if w else sum(vals) / n
        out["rms"] = math.sqrt(sum(v * v * a for v, a in zip(vals, weights)) / w) if w else None
        out["weighted_by"] = "element area"
    else:
        out["mean"] = sum(vals) / n
        out["rms"] = math.sqrt(sum(v * v for v in vals) / n)
    sv = sorted(vals)
    out["p95"] = sv[min(n - 1, int(0.95 * n))]
    return out


def fetch_bulk(s: Session, key: str) -> tuple[list[list[Any]], list[str], str]:
    table = BULK[s.physics]
    if key not in table:
        raise ToolInputError(f"{key!r} is not available for {s.physics}", f"Use one of {list(table)} or 'all'.")
    cmd, ncol, cols, where = table[key]
    flat = as_list(s.post_call(cmd))
    if len(flat) % ncol:
        raise ToolInputError(f"{s.post}_{cmd} returned {len(flat)} values, not a multiple of {ncol}",
                             "Report this: unexpected bulk getter layout.")
    rows = [flat[i:i + ncol] for i in range(0, len(flat), ncol)]
    return rows, cols, where


def save_arrays(path: Path, arrays: dict[str, tuple[list[list[Any]], list[str]]], fmt: str) -> list[str]:
    written = []
    try:
        import numpy as np  # optional
    except Exception:
        np = None
    if fmt == "npz" and np is not None:
        data = {}
        for k, (rows, _cols) in arrays.items():
            cplx = any(isinstance(v, complex) for r in rows for v in r)
            data[k] = np.array(rows, dtype=complex if cplx else float)
        target = path.with_suffix(".npz")
        np.savez_compressed(target, **data)
        written.append(target.as_posix())
        return written
    for k, (rows, cols) in arrays.items():
        target = path.with_name(f"{path.stem}_{k}.csv")
        with open(target, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in rows:
                w.writerow([(f"{v.real}{v.imag:+}j" if isinstance(v, complex) else v) for v in r])
        written.append(target.as_posix())
    return written


def field_stats(s: Session, region: str = "all", threshold: float | None = None) -> dict[str, Any]:
    ph = s.physics
    elems, _c, _w = fetch_bulk(s, "elements")
    vec, cols, _w = fetch_bulk(s, VECTOR_KEY[ph])
    if len(vec) != len(elems):
        raise ToolInputError(f"{len(vec)} field values for {len(elems)} elements", "Unexpected layout; report this.")
    groups: set[int] | None = None
    r = (region or "all").strip().lower()
    if r.startswith("group"):
        try:
            groups = {int(g) for g in r.split(":", 1)[1].replace(";", ",").split(",") if g.strip()}
        except Exception:
            raise ToolInputError(f"bad region {region!r}", "Use 'all', 'group:3' or 'group:1,2'.")
    elif r != "all":
        raise ToolInputError(f"unknown region {region!r}",
                             "Use 'all' or 'group:N' (to restrict to one material, give its block labels a group number).")
    mags, areas = [], []
    for e, v in zip(elems, vec):
        if groups is not None and int(e[6]) not in groups:
            continue
        mags.append(_mag(v[0], v[1]))
        areas.append(float(e[5]))
    if not mags:
        raise ToolInputError(f"no elements in region {region!r}", "Check the group numbers (femm_add_block_label(group=...)).")
    name = {"magnetics": "|B| (T)", "electrostatics": "|D| (C/m^2)", "heatflow": "|F| (W/m^2)",
            "currentflow": "|J| (A/m^2)"}[ph]
    out: dict[str, Any] = {"region": region, "elements": len(mags), "area_problem_units2": sum(areas),
                           "quantity": name, "stats": _stats(mags, areas)}
    if ph == "magnetics":
        thr = 1.6 if threshold is None else threshold
        sat = sum(a for m, a in zip(mags, areas) if m >= thr)
        out["saturation_threshold_T"] = thr
        out["saturated_area_fraction"] = sat / sum(areas) if sum(areas) else 0.0
        out["elements_above_2T"] = sum(1 for m in mags if m >= 2.0)
        out["note"] = "complex (AC) fields use the peak magnitude sqrt(|B1|^2+|B2|^2)"
    elif threshold is not None:
        above = sum(a for m, a in zip(mags, areas) if m >= threshold)
        out["threshold"] = threshold
        out["area_fraction_above"] = above / sum(areas) if sum(areas) else 0.0
    if ph in ("electrostatics", "heatflow", "currentflow"):
        node_key = {"electrostatics": "v", "heatflow": "t", "currentflow": "v"}[ph]
        nodes, _c, _w = fetch_bulk(s, node_key)
        vals = [abs(v[0]) if isinstance(v[0], complex) else v[0] for v in nodes]
        out["node_" + node_key.upper()] = _stats(vals)
        if region != "all":
            out["node_note"] = "node statistics cover the whole model"
    return out


def register(mcp, ctx: ToolContext) -> None:
    @mcp.tool()
    def femm_point_values(points: list[list[float]], session: str = "main") -> dict:
        """Field values at [[x, y], ...] (problem units), labelled for the physics, plus the
        magnitude (|B|, |E|, |F| or |J|). Components are x/y for planar and r/z for axisymmetric
        models. Magnetics keys: A, Bx/By (T), sigma (MS/m), energy_density (J/m^3), Hx/Hy (A/m),
        J_eddy, J_source (MA/m^2, verified), mux/muy (relative), P_ohmic, P_hyst (W/m^3), fill_factor.
        Complex (AC) values come back as {"re", "im"} (peak). A point outside the model gives
        outside=true. Up to a few hundred points per call is fine (~1 ms each)."""
        def run(s: Session):
            return {"units": units_table(s), "values": [point_values(s, *_pt(p)) for p in as_list(points)]}
        return run_tool(ctx, session, run, need="solution")

    @mcp.tool()
    def femm_block_integral(points: list[list[float]] | None = None, group: list[int] | None = None,
                            codes: list[int] | None = None, session: str = "main") -> dict:
        """Integrate over blocks: select the blocks containing `points` and/or every block in
        `group` (list of group numbers), then evaluate xo_blockintegral for each code.
        Magnetics codes (manual 3.7.1): 0 A.J, 1 A, 2 field energy (J), 3 hysteresis/lamination
        loss, 4 resistive loss (W), 5 area, 6 total loss, 7 total current, 8/9 integral of Bx/By,
        10 volume, 11/12 Lorentz force x/y, 15 Lorentz torque, 17 coenergy, 18/19 weighted
        stress tensor force x/y (N, select the moving part surrounded by air), 22 stress tensor
        torque (N m), 24 R^2... Other physics: see femm_api_get('eo_blockintegral') etc.
        Defaults: magnetics [2,17,5,10,7]; electrostatics [0,1,2]; heatflow [0,1,2]; currentflow [0,1,4,5].
        Planar results are per the problem depth (total, not per metre)."""
        def run(s: Session):
            if not points and not group:
                raise ToolInputError("nothing selected", "Pass points=[[x, y]] inside the blocks or group=[n].")
            n = _select_blocks(s, points, group)
            names = _code_names(s, "blockintegral")
            res = {}
            for c in (codes or DEFAULT_BLOCK_CODES[s.physics]):
                v = s.post_call("blockintegral", int(c))
                res[f"{c}: {names.get(str(c), 'code ' + str(c))}"] = jsonable(v)
            s.post_call("clearblock")
            return {"selected": n, "results": res}
        return run_tool(ctx, session, run, need="solution")

    @mcp.tool()
    def femm_line_integral(contour: list[list[float]], codes: list[int] | None = None, session: str = "main") -> dict:
        """Line integrals along a contour of straight pieces through [[x, y], ...] (use many points
        to follow a curve). Magnetics codes: 0 B.n (flux; total, average), 1 H.t (MMF), 2 length
        (and surface area), 3 stress tensor force, 4 stress tensor torque, 5 (B.n)^2.
        Electrostatics: 0 E.t, 1 D.n (charge), 2 length, 3 force, 4 torque. Heat: 0 G.t (dT),
        1 F.n (heat flow), 2 length, 3 average T. Current: 0 E.t, 1 J.n (current), 2 length, ...
        Defaults: the first three/four."""
        def run(s: Session):
            n = _set_contour(s, contour)
            names = _code_names(s, "lineintegral")
            res = {}
            for c in (codes or DEFAULT_LINE_CODES[s.physics]):
                v = s.post_call("lineintegral", int(c))
                res[f"{c}: {names.get(str(c), 'code ' + str(c))}"] = jsonable(v)
            return {"contour_points": n, "results": res}
        return run_tool(ctx, session, run, need="solution")

    @mcp.tool()
    def femm_circuit_results(name: str, session: str = "main") -> dict:
        """Magnetics: current (A), voltage drop (V) and flux linkage (Wb) of circuit `name`
        (mo_getcircuitproperties), with derived inductance L = flux/current (for a circuit alone in
        the model; mutual effects included), resistance (DC) or impedance V/I (AC).
        Electrostatics/heat/current: conductor results (xo_getconductorproperties): voltage &
        charge, temperature & heat flux, or voltage & current."""
        def run(s: Session):
            if s.physics == "magnetics":
                r = as_list(s.post_call("getcircuitproperties", name))
                i, v, flux = (r + [None, None, None])[:3]
                out: dict[str, Any] = {"current_A": jsonable(i), "voltage_V": jsonable(v), "flux_linkage_Wb": jsonable(flux)}
                if i not in (None, 0):
                    out["inductance_H"] = jsonable(flux / i) if flux is not None else None
                    out["impedance_ohm" if isinstance(v, complex) or isinstance(i, complex) else "resistance_ohm"] = jsonable(v / i)
                return out
            r = as_list(s.post_call("getconductorproperties", name))
            labels = {"electrostatics": ("voltage_V", "charge_C"), "heatflow": ("temperature_K", "heat_flux_W"),
                      "currentflow": ("voltage_V", "current_A")}[s.physics]
            out = {labels[0]: jsonable(r[0] if r else None), labels[1]: jsonable(r[1] if len(r) > 1 else None)}
            if s.physics == "electrostatics" and len(r) > 1 and r[0]:
                out["capacitance_F_if_other_conductor_at_0V"] = r[1] / r[0]
            return out
        return run_tool(ctx, session, run, need="solution")

    @mcp.tool()
    def femm_select_block(points: list[list[float]] | None = None, group: list[int] | None = None,
                          action: str = "select", session: str = "main") -> dict:
        """Post-processor block selection for femm_call('mo_blockintegral', [code]) workflows.
        action=select clears, then selects the blocks containing `points` and/or `group`s;
        action=clear clears the selection. (femm_block_integral does select+integrate+clear itself.)"""
        def run(s: Session):
            if action == "clear":
                s.post_call("clearblock")
                return {"cleared": True}
            return {"selected": _select_blocks(s, points, group)}
        return run_tool(ctx, session, run, need="solution")

    @mcp.tool()
    def femm_mesh_arrays(which: str = "all", fmt: str = "npz", name: str | None = None, session: str = "main") -> dict:
        """Dump the solution mesh and fields to a file in the session work dir and return the path,
        shape and min/max/mean per column (never the raw arrays). which: all, or a comma list of
        nodes, elements, and per physics: magnetics b (B1,B2 per element), a (A per element);
        electrostatics v (per node), d; heatflow t (per node), f; currentflow v (per node), j.
        Element rows are n1,n2,n3 (node indices), cx, cy, area, group. fmt: npz (numpy) or csv.
        Load with numpy.load(path)."""
        def run(s: Session):
            keys = list(BULK[s.physics]) if which == "all" else [k.strip().lower() for k in which.split(",") if k.strip()]
            arrays, summary = {}, {}
            t0 = time.time()
            for k in keys:
                rows, cols, where = fetch_bulk(s, k)
                arrays[k] = (rows, cols)
                colstats = {}
                for j, c in enumerate(cols):
                    col = [abs(r[j]) if isinstance(r[j], complex) else r[j] for r in rows]
                    if col:
                        colstats[c] = {"min": min(col), "max": max(col), "mean": sum(col) / len(col)}
                summary[k] = {"shape": [len(rows), len(cols)], "columns": cols, "per": where, "stats": colstats}
            if "elements" in arrays and "nodes" in arrays:
                mx = max(max(int(r[0]), int(r[1]), int(r[2])) for r in arrays["elements"][0])
                mn = min(min(int(r[0]), int(r[1]), int(r[2])) for r in arrays["elements"][0])
                summary["elements"]["node_index_range"] = [mn, mx]
                summary["elements"]["index_base"] = 0 if mx == len(arrays["nodes"][0]) - 1 else (1 if mx == len(arrays["nodes"][0]) else None)
            stem = name or f"mesh_{int(time.time())}"
            out_dir = s.work_dir / "arrays"
            out_dir.mkdir(parents=True, exist_ok=True)
            files = save_arrays(out_dir / stem, arrays, fmt)
            return {"files": files, "arrays": summary, "fetch_seconds": round(time.time() - t0, 3)}
        return run_tool(ctx, session, run, need="solution")

    @mcp.tool()
    def femm_field_stats(region: str = "all", threshold: float | None = None, session: str = "main") -> dict:
        """Area-weighted statistics of the main field over the mesh, from the bulk arrays (fast,
        no file). Magnetics: |B| min/max/mean/rms/p95, saturated area fraction (|B| >= threshold,
        default 1.6 T) and number of elements above 2 T. Other physics: |D|, |F| or |J| per element
        and V/T at nodes. region: 'all' or 'group:N[,M]' (give the blocks of one material a group
        number with femm_add_block_label(group=N) to get per-material stats)."""
        return run_tool(ctx, session, lambda s: field_stats(s, region, threshold), need="solution")

    @mcp.tool()
    def femm_gap_results(boundary: str, angle: float | None = None, harmonics: int | None = 10, npts: int = 360,
                         include_ac: bool = False, session: str = "main") -> dict:
        """Air-gap (sliding band) results for a periodic/antiperiodic air-gap boundary `boundary`
        (femm_add_boundary bc_type='periodic_air_gap'): torque (mo_gapintegral 0), force (1),
        stored energy (2) [include_ac adds 2x torque/force and interaction terms]; Br/Bt at
        `angle` (deg); the Br/Bt distribution at `npts` angles saved to CSV with stats; and the
        `harmonics` largest Br harmonics (mo_getallgapharmonics). Magnetics only.
        Warning: FEMM returns zeros (not an error) for an unknown boundary name."""
        def run(s: Session):
            if s.physics != "magnetics":
                raise ToolInputError("air-gap elements are magnetics-only", "Use femm_line_integral instead.")
            out: dict[str, Any] = {"boundary": boundary}
            ints = {}
            for c in ([0, 1, 2, 3, 4, 5, 6] if include_ac else [0, 1, 2]):
                ints[GAP_INTEGRALS[c]] = jsonable(s.post_call("gapintegral", boundary, c))
            out["integrals"] = ints
            if all(v == 0 for v in ints.values()):
                out["warning"] = (f"all gap integrals are exactly 0: {boundary!r} is probably not an air-gap boundary "
                                  "of this model (FEMM does not raise for unknown names)")
            if angle is not None:
                b = as_list(s.post_call("getgapb", boundary, float(angle)))
                out["at_angle"] = {"angle_deg": angle, "Br_T": jsonable(b[0] if b else None),
                                   "Bt_T": jsonable(b[1] if len(b) > 1 else None)}
            flat = as_list(s.post_call("getallgapb", boundary, int(npts)))
            if flat:
                rows = [[i * 360.0 / (len(flat) // 2), flat[2 * i], flat[2 * i + 1]] for i in range(len(flat) // 2)]
                d = s.work_dir / "arrays"
                d.mkdir(parents=True, exist_ok=True)
                p = d / f"gap_{boundary}_{int(time.time())}.csv"
                with open(p, "w", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(["angle_deg", "Br_T", "Bt_T"])
                    for r in rows:
                        w.writerow([(str(v) if isinstance(v, complex) else v) for v in r])
                br = [abs(r[1]) if isinstance(r[1], complex) else r[1] for r in rows]
                bt = [abs(r[2]) if isinstance(r[2], complex) else r[2] for r in rows]
                out["distribution"] = {"file": p.as_posix(), "points": len(rows), "Br": _stats(br), "Bt": _stats(bt)}
                if all(abs(v) == 0 for v in br + bt):
                    out["warning"] = f"all-zero gap field: is {boundary!r} really an air-gap boundary of this model?"
            if harmonics:
                hf = as_list(s.post_call("getallgapharmonics", boundary))
                rows = [hf[i:i + 6] for i in range(0, len(hf) - len(hf) % 6, 6)]
                table = []
                for n, r in enumerate(rows):
                    acc, acs, brc, brs, btc, bts = [abs(v) if isinstance(v, complex) else v for v in r]
                    table.append({"n": n, "Br_amp_T": math.hypot(brc, brs), "Bt_amp_T": math.hypot(btc, bts),
                                  "brc": brc, "brs": brs})
                table.sort(key=lambda t: -t["Br_amp_T"])
                out["harmonics"] = {"count": len(rows), "largest": table[:harmonics],
                                    "note": "row index = harmonic number n (row 0 = DC); verified on a 2-pole magnet model"}
            return out
        return run_tool(ctx, session, run, need="solution")

    @mcp.tool()
    def femm_save_bitmap(path: str, view: str = "post", density: bool = True, plot_type: Any = None,
                         lower: float = 0.0, upper: float = 0.0, legend: bool = True, grayscale: bool = False,
                         contours: int | None = None, zoom: list[float] | None = None, session: str = "main") -> dict:
        """Screenshot of the current view to an image file (xo_savebitmap / xi_savebitmap), .png or
        .bmp. VERIFIED: works only in a session opened with femm_session_open(headless=False)
        (a GUI window); the headless engine accepts the command but writes nothing.
        view: post (solution plot) or pre (geometry). density: show a density plot of plot_type
        (magnetics 'bmag','breal','bimag','hmag','jmag',...; electrostatics 0 V,1 |D|,2 |E|;
        heatflow 0 T,1 |F|,2 |G|; currentflow 0..8, 3 = |J|). Leave plot_type, lower and upper
        unset for FEMM's default auto-scaled plot (|B|, V, T or |J|); an explicit plot_type needs
        lower/upper limits. view='pre' after a solve switches focus back to the geometry window.
        contours: number of flux/equipotential lines. zoom: [x1, y1, x2, y2] or None = natural.
        For data plots that work headless use femm_make_plot or femm_mesh_arrays."""
        def run(s: Session):
            p = Path(path)
            if not p.is_absolute():
                p = s.work_dir / p
            if p.suffix.lower() not in (".png", ".bmp", ".jpg", ".jpeg"):
                p = p.with_suffix(".png")
            p.parent.mkdir(parents=True, exist_ok=True)
            target = p.resolve().as_posix()
            if p.exists():
                p.unlink()
            stem = Path(s.document).stem if s.document else None
            if view == "pre":
                if stem:
                    try:   # after a solve the post-processor window has the focus (verified)
                        s.pre_call("setfocus", stem)
                    except Exception:
                        pass
                if zoom:
                    s.pre_call("zoom", *[float(v) for v in zoom])
                else:
                    s.pre_call("zoomnatural")
                s.pre_call("savebitmap", target)
            else:
                if not s.solved:
                    raise ToolInputError("no solution loaded", "Call femm_solve first, or use view='pre'.")
                if stem:
                    try:
                        s.post_call("setfocus", stem)
                    except Exception:
                        pass
                if zoom:
                    s.post_call("zoom", *[float(v) for v in zoom])
                else:
                    s.post_call("zoomnatural")
                if density and plot_type is None and not lower and not upper:
                    # legend=-1: FEMM's own defaults, auto range and a correct legend (explicit
                    # 0/0 bounds give a legend that reads 0 everywhere: verified)
                    if s.physics == "magnetics":
                        s.post_call("showdensityplot", -1, 0, 0, 0, "bmag")
                    else:
                        s.post_call("showdensityplot", -1, 0, int(DENSITY_DEFAULT[s.physics]), 0, 0)
                elif density:
                    pt = DENSITY_DEFAULT[s.physics] if plot_type is None else plot_type
                    if not lower and not upper:
                        raise ToolInputError("give lower and upper with an explicit plot_type",
                                             "Pass lower/upper limits (e.g. 0 and 2 T), or leave plot_type unset for auto-scale.")
                    if s.physics == "magnetics":
                        s.post_call("showdensityplot", int(legend), int(grayscale), float(upper), float(lower), str(pt))
                    else:
                        s.post_call("showdensityplot", int(legend), int(grayscale), int(pt), float(upper), float(lower))
                if contours:
                    if s.physics in ("magnetics", "currentflow"):
                        s.post_call("showcontourplot", int(contours), 0, 0, "real")
                    else:
                        s.post_call("showcontourplot", int(contours), 0, 0)
                s.post_call("savebitmap", target)
            exists = Path(target).is_file()
            if not exists:
                raise ToolInputError(f"FEMM wrote no image to {target}",
                                     "Screenshots need a GUI engine: femm_session_open(name='gui', headless=False), "
                                     "re-open/solve the model there (femm_open + femm_solve with session='gui'), then retry.")
            return {"file": target, "bytes": Path(target).stat().st_size}
        return run_tool(ctx, session, run, need="document")

    @mcp.tool()
    def femm_make_plot(contour: list[list[float]], plot_type: int = 1, npts: int = 200, path: str | None = None,
                       session: str = "main") -> dict:
        """Sample a quantity along a contour (straight pieces through [[x, y], ...]) to a text
        file (xo_makeplot with a filename; works headless). Magnetics plot_type: 0 A, 1 |B|,
        2 B.n, 3 B.t, 4 |H|, 5 H.n, 6 H.t, 7 J eddy, 8 J source+eddy. Electrostatics: 0 V, 1 |D|,
        2 D.n, 3 D.t, 4 |E|, 5 E.n, 6 E.t. Heat: 0 T, 1 |F|, 2 F.n, 3 F.t, 4 |G|, 5 G.n, 6 G.t.
        Current: 0 V, 1 |J|, 2 J.n, 3 J.t, 4 |E|, ... Returns the file path, column header and
        min/max/mean of the sampled values (position is distance along the contour)."""
        def run(s: Session):
            _set_contour(s, contour)
            if path:
                p = Path(path)
                if not p.is_absolute():
                    p = s.work_dir / p
            else:
                (s.work_dir / "plots").mkdir(parents=True, exist_ok=True)
                p = s.work_dir / "plots" / f"plot_{plot_type}_{int(time.time())}.txt"
            p.parent.mkdir(parents=True, exist_ok=True)
            target = p.resolve().as_posix()
            n = s.post_call("makeplot", int(plot_type), int(npts), target, 0)
            header, xs, ys = None, [], []
            if Path(target).is_file():
                for line in Path(target).read_text(errors="replace").splitlines():
                    parts = [q.strip() for q in line.replace("\t", ",").split(",") if q.strip()]
                    if not parts:
                        continue
                    try:
                        vals = [float(q) for q in parts]
                    except ValueError:
                        header = header or parts
                        continue
                    xs.append(vals[0])
                    ys.append(vals[1:] if len(vals) > 2 else vals[1] if len(vals) > 1 else None)
            names = (catalog.get(f"{s.post}_makeplot") or {}).get("enums", {}).get("plottype", {})
            out: dict[str, Any] = {"file": target, "points": n if isinstance(n, int) else len(xs),
                                   "quantity": names.get(str(plot_type)), "header": header}
            scalar = [y for y in ys if isinstance(y, float)]
            if scalar:
                out["stats"] = _stats(scalar)
                out["length"] = xs[-1] - xs[0] if xs else None
            return out
        return run_tool(ctx, session, run, need="solution")
