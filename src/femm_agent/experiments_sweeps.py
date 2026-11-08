"""Sweep experiments split out of :mod:`femm_agent.experiments` (pure move in 0.2.0, plus the
inductance-vs-current mode): inductance / Ld-Lq / L(I), AC frequency sweep, generic parametric
study. Same conventions as the parent module; import them from ``femm_agent.experiments``."""
from __future__ import annotations

import math
from typing import Any, Callable, Sequence

from . import estimate, health, plotting
from .experiments_core import (BI_ENERGY, BI_LOSS_HYST, BI_LOSS_RES, BI_LOSS_TOTAL, BI_TORQUE, POINT_FIELDS, _SETUP_RE,
                          ExperimentInputError, Ops, Run, _flat, _jsonable, _named, _num, _restore_currents, as_complex,
                          as_float)


# ============================================================================= inductance

def inductance(link, circuits: Sequence[str] | None = None, current: float = 1.0, *, dq: dict | None = None,
               currents: Sequence[float] | None = None,
               torque_groups: Sequence[int] | None = None, gap_boundary: str | None = None, out_dir=None,
               restore_path=None, solve_timeout: float | None = 600.0, tag: str | None = None) -> dict:
    """Inductance matrix by flux-linkage differences: L_jk = (psi_j(I_k = current) - psi_j(0)) / current
    (subtracting the zero-current solve removes PM flux; for saturating iron this is the secant
    inductance about the PM operating point).

    ``dq = {"circuits": ["A","B","C"], "poles": 2p, "theta0_deg": 0, "id": 1, "iq": 1}`` (or
    ``"pole_pairs": p``) instead injects d- and q-axis currents at the present rotor position
    (theta0 = electrical angle of the d-axis w.r.t. phase A) and returns psi_pm, Ld, Lq, saliency
    and the dq torque, checked against the FEM torque (WST on ``torque_groups`` or
    ``mo_gapintegral(gap_boundary, 0)``).

    ``currents = [I1, I2, ...]`` (A) gives L(I) instead: for each circuit (default all) and each
    current, only that circuit carries the current; rows are (circuit, current, psi, L_secant =
    (psi(I) - psi(0)) / I, L_incremental = dpsi/dI by finite differences over 0 and the sorted
    currents). Self inductance only; use the default mode for mutuals."""
    run = Run(link, "inductance", out_dir, restore_path, solve_timeout, tag)
    ops = run.ops
    allc = run.circuit_names()
    run.require_circuits(circuits)
    if torque_groups:
        run.require_groups(torque_groups, "torque_groups", need_labels=True)
    if dq and currents is not None:
        raise ExperimentInputError("give dq or currents, not both",
                                   "Use dq={...} for Ld/Lq at one operating point, or currents=[...] for L(I).")
    if currents is not None:
        currents = _check_currents(currents)
    if dq:
        estimate.pole_pairs_of(dq, "dq")
        run.require_circuits(list(dq.get("circuits", ["A", "B", "C"])), "dq.circuits")
    rows: list[list] = []
    summary: dict[str, Any] = {}
    plots: list = []

    def solve_and_read(currents: dict[str, float], want_energy=False):
        for c in allc:
            ops.set_current(c, currents.get(c, 0.0))
        ops.solve()
        fl = {c: as_float(ops.circuit(c)["flux"]) for c in allc}
        extra = {}
        if want_energy:
            extra["energy"] = as_float(ops.block_integral(BI_ENERGY))
        if torque_groups:
            extra["torque"] = as_float(ops.block_integral(BI_TORQUE, torque_groups))
        elif gap_boundary:
            extra["torque"] = as_float(ops.gap_integral(gap_boundary, 0))
        ops.close_post()
        return fl, extra

    try:
        if dq:
            names = list(dq.get("circuits", ["A", "B", "C"]))
            p = estimate.pole_pairs_of(dq, "dq")
            th = math.radians(float(dq.get("theta0_deg", 0.0)))
            i_d = float(dq.get("id", current))
            i_q = float(dq.get("iq", current))
            cases = {"zero": (0.0, 0.0), "d": (i_d, 0.0), "q": (0.0, i_q), "dq": (i_d, i_q)}
            res = {}
            for key, (a, b) in cases.items():
                ia, ib, ic = estimate.inverse_park(a, b, th)
                fl, extra = solve_and_read(dict(zip(names, (ia, ib, ic))))
                pd, pq = estimate.park(fl[names[0]], fl[names[1]], fl[names[2]], th)
                res[key] = {"id": a, "iq": b, "psi_d": pd, "psi_q": pq, **extra}
                rows.append([key, a, b, pd, pq, extra.get("torque")])
            psi_pm = res["zero"]["psi_d"]
            ld = (res["d"]["psi_d"] - psi_pm) / i_d if i_d else None
            lq = (res["q"]["psi_q"] - res["zero"]["psi_q"]) / i_q if i_q else None
            t_dq = estimate.dq_torque(p, res["q"]["psi_d"], res["q"]["psi_q"], 0.0, i_q)
            summary = {"psi_pm_Wb": psi_pm, "Ld_H": ld, "Lq_H": lq, "saliency_Lq_over_Ld": (lq / ld) if ld and lq else None,
                       "torque_dq_at_iq_Nm": t_dq, "torque_fem_at_iq_Nm": res["q"].get("torque"),
                       "torque_dq_at_id_iq_Nm": estimate.dq_torque(p, res["dq"]["psi_d"], res["dq"]["psi_q"], i_d, i_q),
                       "torque_fem_at_id_iq_Nm": res["dq"].get("torque"), "cases": res}
            if res["q"].get("torque") is not None:
                chk = health.force_consistency(res["q"]["torque"], t_dq, "FEM torque", "3/2 p psi_d i_q", 0.15,
                                               name="torque_fem_vs_dq")
                chk["message"] += (" (single rotor position: EMF harmonics x current make the instantaneous torque"
                                   " differ from the fundamental dq value; compare the mean of a driven torque_vs_angle sweep)")
                run.checks.append(chk)
            cols = ["case", "id_A", "iq_A", "psi_d_Wb", "psi_q_Wb", "torque_Nm"]
        elif currents is not None:
            circuits = list(circuits) if circuits is not None else run.default_circuits()
            if not circuits:
                raise ExperimentInputError("no circuits in the model")
            base, _ = solve_and_read({})
            lin = run.linear_no_pm()
            curves = {}
            for ck in circuits:
                psis = []
                for i in currents:
                    fl, extra = solve_and_read({ck: i}, want_energy=True)
                    psis.append(fl[ck])
                    run.checks.append(_named(health.energy_consistency(extra["energy"], [fl[ck]], [i], linear=lin),
                                             f"energy_vs_flux_linkage[{ck}@{i:g}A]"))
                curve = l_of_i(currents, psis, base[ck])
                curves[ck] = curve
                run.warnings.extend(l_of_i_warnings(curve, ck))
                for r in curve:
                    rows.append([ck, r["current"], r["psi"], r["L_secant"], r["L_incremental"]])
            summary = {"circuits": circuits, "currents_A": sorted(currents), "linear_no_pm": lin,
                       "L_secant_H": {c: [r["L_secant"] for r in curves[c]] for c in circuits},
                       "L_incremental_H": {c: [r["L_incremental"] for r in curves[c]] for c in circuits},
                       "psi_at_zero_Wb": {c: base[c] for c in circuits},
                       "note": "self inductance of each circuit with the others at 0 A; L_incremental by finite "
                               "differences (accuracy limited by the current spacing)"}
            c0 = circuits[0]
            plots = [("L_of_I", lambda pth: plotting.plot_curves(
                pth, [r["current"] for r in curves[c0]], {"L secant": [r["L_secant"] for r in curves[c0]],
                                      "L incremental": [r["L_incremental"] for r in curves[c0]]},
                title=f"Inductance vs current, {c0}", xlabel="current (A)", ylabel="L (H)",
                dashed=("L incremental",)))]
            cols = ["circuit", "current_A", "psi_Wb", "L_secant_H", "L_incremental_H"]
        else:
            circuits = list(circuits) if circuits is not None else run.default_circuits()
            if not circuits:
                raise ExperimentInputError("no circuits in the model",
                                         "Add one with femm_add_circuit(name=...), then femm_set_block_prop(x=, y=, "
                                         "material=, circuit=<name>, turns=<N>) on each coil label.")
            base, _ = solve_and_read({})
            lin = run.linear_no_pm()
            M = []
            for ck in circuits:
                fl, extra = solve_and_read({ck: current}, want_energy=True)
                col = [(fl[cj] - base[cj]) / current for cj in circuits]
                M.append(col)
                rows.append([ck, current] + col)
                run.checks.append(_named(health.energy_consistency(extra["energy"], [fl[ck]], [current], linear=lin),
                                         f"energy_vs_flux_linkage[{ck}]"))
            Lmat = [[M[k][j] for k in range(len(circuits))] for j in range(len(circuits))]  # L[j][k]
            summary = {"circuits": circuits, "L_matrix_H": Lmat, "self_H": {c: Lmat[i][i] for i, c in enumerate(circuits)},
                       "linear_no_pm": lin}
            if len(circuits) > 1:
                asym = max(abs(Lmat[i][j] - Lmat[j][i]) / max(abs(Lmat[i][i]), abs(Lmat[j][j]), 1e-30)
                           for i in range(len(circuits)) for j in range(len(circuits)))
                run.checks.append({"name": "mutual_reciprocity", "ok": asym < 0.03, "value": asym, "expected": 0.0,
                                   "tolerance": 0.03, "message": f"max |L_jk - L_kj| / L_self = {asym:.2%}"})
            cols = ["excited_circuit", "current_A"] + [f"psi_{c}_per_A" for c in circuits]
    finally:
        _restore_currents(run)
    return run.finish({"circuits": circuits if not dq else dq.get("circuits"), "current": current, "dq": dq,
                       "currents": list(currents) if currents is not None else None,
                       "torque_groups": torque_groups, "gap_boundary": gap_boundary}, cols, rows, summary, plots)


def _check_currents(currents: Sequence[float]) -> list[float]:
    try:
        vals = [float(c) for c in currents]
    except (TypeError, ValueError):
        raise ExperimentInputError(f"currents must be numbers, got {currents!r}") from None
    if not vals or any(v == 0 or not math.isfinite(v) for v in vals) or len(set(vals)) != len(vals):
        raise ExperimentInputError(f"currents must be a non-empty list of distinct, non-zero amps, got {vals}")
    return vals


def l_of_i(currents: Sequence[float], psis: Sequence[float], psi0: float) -> list[dict]:
    """Secant and incremental inductance from flux linkage psi(I) (pure), rows sorted by current.

    L_secant = (psi(I) - psi(0)) / I. L_incremental = dpsi/dI on the grid {0} + currents: a central
    difference through the two neighbours inside, first-order one-sided at the ends. Both are
    monotone-safe (a rising psi never gives a negative slope), unlike second-order formulas on a
    sparse non-uniform grid; accuracy is limited by the current spacing (see l_of_i_warnings)."""
    pts = sorted(set([0.0] + [float(i) for i in currents]))
    lookup = {float(i): float(p) for i, p in zip(currents, psis)}
    lookup[0.0] = float(psi0)
    y = [lookup[v] for v in pts]
    inc: dict[float, float] = {}
    n = len(pts)
    for k, v in enumerate(pts):
        lo, hi = max(k - 1, 0), min(k + 1, n - 1)
        inc[v] = (y[hi] - y[lo]) / (pts[hi] - pts[lo]) if hi != lo else float("nan")
    return [{"current": v, "psi": lookup[v], "L_secant": (lookup[v] - float(psi0)) / v, "L_incremental": inc[v]}
            for v in pts if v != 0.0]


def l_of_i_warnings(rows: Sequence[dict], circuit: str = "") -> list[str]:
    """Warn when an incremental inductance is non-positive or exceeds 1.5x the secant value: on a
    saturating curve dpsi/dI <= psi/I, so such a value is a finite-difference artefact."""
    bad = [r["current"] for r in rows
           if not (r["L_incremental"] > 0) or r["L_incremental"] > 1.5 * abs(r["L_secant"])]
    if not bad:
        return []
    at = f" of {circuit}" if circuit else ""
    return [f"L_incremental{at} at {bad} A is <= 0 or > 1.5 x L_secant: limited by the current spacing; add currents "
            "between those points (denser near the knee) before using it"]


# ============================================================================= AC sweep

def ac_sweep(link, frequencies: Sequence[float], circuits: Sequence[str] | None = None, *, current: float | None = None,
             estimate_fn: Callable[[float], complex] | None = None, out_dir=None, restore_path=None,
             solve_timeout: float | None = 600.0, tag: str | None = None) -> dict:
    """Time-harmonic sweep: for each frequency set ``mi_probdef(f, ...)`` (other probdef fields kept),
    solve, and read each circuit's phasors (FEMM phasors are peak amplitudes):
    Z = V/I, R = Re Z, L = Im Z / omega, plus block-integral losses over all blocks (6 total,
    4 resistive, 3 hysteresis/laminations). Health: 1/2 Re(sum V conj I) == total losses.
    ``estimate_fn(f) -> complex Z`` adds an analytic comparison column. Frequency restored after."""
    run = Run(link, "ac_sweep", out_dir, restore_path, solve_timeout, tag)
    ops = run.ops
    hdr = run.model.header
    units = run.model.units
    ptype = "axi" if run.model.problem_type == "axisymmetric" else "planar"
    prec = float(hdr.get("Precision", 1e-8))
    depth = float(hdr.get("Depth", 1))
    minang = float(hdr.get("MinAngle", 30))
    acs = int(hdr.get("ACSolver", 0) or 0)
    f0 = float(hdr.get("Frequency", 0) or 0)
    run.require_circuits(circuits)
    circuits = list(circuits) if circuits is not None else run.default_circuits()
    if not circuits:
        raise ExperimentInputError("no circuits in the model",
                                         "Add one with femm_add_circuit(name=...), then femm_set_block_prop(x=, y=, "
                                         "material=, circuit=<name>, turns=<N>) on each coil label.")
    if current is not None:
        for c in circuits:
            ops.set_current(c, current)
    rows, R, Lh, fs, est_r = [], {c: [] for c in circuits}, {c: [] for c in circuits}, [], []
    try:
        for f in frequencies:
            ops.call("mi_probdef", float(f), units, ptype, prec, depth, minang, acs)
            ops.solve()
            row = [float(f)]
            pin = 0.0
            for c in circuits:
                cp = ops.circuit(c)
                i, v = cp["current"], cp["voltage"]
                z = v / i if abs(i) > 0 else complex("nan")
                w = 2 * math.pi * f
                r = z.real
                l = (z.imag / w) if f > 0 else (cp["flux"].real / i.real if i.real else float("nan"))
                pin += 0.5 * (v * i.conjugate()).real
                R[c].append(r)
                Lh[c].append(l)
                row += [i, v, cp["flux"], r, l]
            ptot = as_float(ops.block_integral(BI_LOSS_TOTAL))
            pres = as_float(ops.block_integral(BI_LOSS_RES))
            phys = as_float(ops.block_integral(BI_LOSS_HYST))
            row += [pin, ptot, pres, phys]
            if estimate_fn is not None:
                ze = estimate_fn(float(f))
                row += [ze.real, ze.imag / (2 * math.pi * f) if f > 0 else None]
                est_r.append(ze.real)
            rows.append(row)
            fs.append(float(f))
            if f > 0:
                run.checks.append(_named(health.power_balance(pin, ptot), f"ac_power_balance[{f:g} Hz]"))
            ops.close_post()
    finally:
        ops.call("mi_probdef", f0, units, ptype, prec, depth, minang, acs)
        _restore_currents(run)
    cols = ["frequency_Hz"]
    for c in circuits:
        cols += [f"I_{c}_A", f"V_{c}_V", f"psi_{c}_Wb", f"R_{c}_ohm", f"L_{c}_H"]
    cols += ["P_in_W", "P_loss_total_W", "P_loss_resistive_W", "P_loss_hyst_W"]
    if estimate_fn is not None:
        cols += ["R_analytic_ohm", "L_analytic_H"]
        c0 = circuits[0]
        for f, r, re_ in zip(fs, R[c0], est_r):
            run.checks.append(_named(health.compare_to_estimate("R_vs_analytic", r, re_, 0.05), f"R_vs_analytic[{f:g} Hz]"))
    summary = {"R_ohm": R, "L_H": Lh, "frequencies_Hz": fs}
    c0 = circuits[0]
    plots = [("resistance", lambda p: plotting.plot_curves(p, fs, {"FEM": R[c0], **({"analytic": est_r} if est_r else {})},
                                                           title=f"Resistance vs frequency, {c0}", xlabel="frequency (Hz)",
                                                           ylabel="R (ohm)", dashed=("analytic",))),
             ("inductance", lambda p: plotting.plot_curves(p, fs, {"FEM": Lh[c0]}, title=f"Inductance vs frequency, {c0}",
                                                           xlabel="frequency (Hz)", ylabel="L (H)"))]
    return run.finish({"frequencies": list(map(float, frequencies)), "circuits": circuits, "current": current},
                      cols, rows, summary, plots)


# ============================================================================= parametric

def _check_setup_command(name: str) -> None:
    if not _SETUP_RE.match(name or ""):
        raise ExperimentInputError(f"setup command {name!r} not allowed: use preprocessor commands (mi_/ei_/hi_/ci_ ...)",
                                   "Only mi_*/ei_*/hi_*/ci_* commands go in case.commands; read results through outputs=[...].")


def collect_output(ops: Ops, spec: dict, unit_m: float = 1e-3) -> Any:
    """Evaluate one output spec on the loaded solution.

    kinds: ``point`` {x, y, quantity: A|B|Bx|By|H|Hx|Hy|mu|J|any POINT_FIELDS name},
    ``block`` {code, groups?}, ``circuit`` {circuit, quantity: flux|current|voltage|L|R},
    ``gap`` {boundary, code}, ``line`` {points, code, index?}, ``expr`` {expression} (one line of
    MicroPython evaluated inside FEMM)."""
    kind = spec.get("kind")
    if kind == "point":
        pv = ops.point(float(spec["x"]), float(spec["y"]))
        q = spec.get("quantity", "B")
        b1, b2 = as_complex(pv["B1"]), as_complex(pv["B2"])
        h1, h2 = as_complex(pv["H1"]), as_complex(pv["H2"])
        table = {"B": math.hypot(abs(b1), abs(b2)), "Bx": b1, "By": b2, "Br": b1, "Bz": b2,
                 "H": math.hypot(abs(h1), abs(h2)), "Hx": h1, "Hy": h2, "mu": pv["Mu1"], "J": pv["Js"]}
        v = table.get(q, pv.get(q))
        if v is None:
            raise ExperimentInputError(f"unknown point quantity {q!r}",
                                       f"Use one of B, Bx, By, Br, Bz, H, Hx, Hy, mu, J or a raw field {list(POINT_FIELDS)}.")
        return _num(v)
    if kind == "block":
        return _num(ops.block_integral(int(spec["code"]), spec.get("groups")))
    if kind == "circuit":
        cp = ops.circuit(spec["circuit"])
        q = spec.get("quantity", "flux")
        if q == "L":
            return (cp["flux"] / cp["current"]).real if abs(cp["current"]) else None
        if q == "R":
            return (cp["voltage"] / cp["current"]).real if abs(cp["current"]) else None
        return _num(cp[q])
    if kind == "gap":
        return [_num(x) for x in _flat(ops.gap_integral(spec["boundary"], int(spec.get("code", 0))))]
    if kind == "line":
        v = ops.line_integral(spec["points"], int(spec.get("code", 0)))
        idx = spec.get("index")
        return _num(v[int(idx)]) if idx is not None else [_num(x) for x in v]
    if kind == "expr":
        return _jsonable(ops.link.eval(str(spec["expression"])) if hasattr(ops.link, "eval") else None)
    raise ExperimentInputError(f"unknown output kind {kind!r} (point, block, circuit, gap, line, expr)",
                               "Use kind point, block, circuit, gap, line or expr (see femm_experiment_parametric).")


def parametric(link, cases: Sequence[dict], outputs: Sequence[dict], *, template: str | None = None,
               out_dir=None, restore_path=None, solve_timeout: float | None = 600.0, tag: str | None = None) -> dict:
    """Generic sweep. Each case starts from the same saved base model (re-opened), applies its setup,
    solves and collects ``outputs`` (see :func:`collect_output`).

    case = {"name": "g=1.5", "params": {"g": 1.5}, "commands": [{"command": "mi_modifymaterial",
    "args": ["Magnet", 3, 1e6]}]}. ``template`` is an optional multi-line MicroPython snippet run
    inside FEMM before solving, formatted with the case params (``{g}``); it is written to a file in
    the run folder and executed via ``exec(open(path).read())``. Setup commands must be
    preprocessor commands (mi_/ei_/hi_/ci_)."""
    run = Run(link, "parametric", out_dir, restore_path, solve_timeout, tag)
    ops = run.ops
    base = run.model_path
    names = [o.get("name") or f"out{k}" for k, o in enumerate(outputs)]
    rows, errors = [], []
    pkeys: list[str] = []
    for c in cases:
        for k in (c.get("params") or {}):
            if k not in pkeys:
                pkeys.append(k)
    for n, case in enumerate(cases):
        cname = case.get("name") or f"case{n}"
        params = case.get("params") or {}
        try:
            ops.call("mi_close")
        except Exception:
            pass
        ops.call("opendocument", str(base).replace("\\", "/"))
        case_path = run.dir / f"case{n:03d}.fem"
        ops.save_as(case_path)
        try:
            for cmd in case.get("commands") or []:
                _check_setup_command(cmd.get("command"))
                ops.call(cmd["command"], *cmd.get("args", []))
            if template:
                script = run.dir / f"case{n:03d}.py"
                script.write_text(template.format(**params), encoding="utf-8")
                ops.link.eval('exec(open("' + str(script).replace("\\", "/") + '").read())')
            ops.save_as(case_path)
            ops.solve()
            vals = []
            for spec in outputs:
                try:
                    vals.append(collect_output(ops, spec, run.unit_m))
                except Exception as e:
                    vals.append(None)
                    errors.append({"case": cname, "output": spec.get("name"), "error": str(e)})
            ops.close_post()
            rows.append([cname] + [params.get(k) for k in pkeys] + vals)
        except Exception as e:
            errors.append({"case": cname, "error": f"{type(e).__name__}: {e}"})
            rows.append([cname] + [params.get(k) for k in pkeys] + [None] * len(outputs))
    try:
        ops.call("mi_close")
    except Exception:
        pass
    ops.call("opendocument", str(base).replace("\\", "/"))
    cols = ["case"] + pkeys + names
    summary = {"cases": len(cases), "errors": errors}
    numeric = [i for i, nm in enumerate(names) if all(isinstance(r[1 + len(pkeys) + i], (int, float)) for r in rows)]
    plots = []
    if len(rows) >= 2 and pkeys and numeric and all(isinstance(r[1], (int, float)) for r in rows):
        xs = [r[1] for r in rows]
        for i in numeric[:3]:
            nm = names[i]
            ys = [r[1 + len(pkeys) + i] for r in rows]
            plots.append((nm, lambda p, ys=ys, nm=nm: plotting.plot_curves(p, xs, {nm: ys}, title=f"{nm} vs {pkeys[0]}",
                                                                           xlabel=pkeys[0], ylabel=nm)))
    if errors:
        run.checks.append({"name": "parametric_errors", "ok": False, "value": len(errors), "expected": 0, "tolerance": 0,
                           "message": f"{len(errors)} case/output errors (see summary.errors)"})
    return run.finish({"cases": list(cases), "outputs": list(outputs), "template": template}, cols, rows, summary, plots)
