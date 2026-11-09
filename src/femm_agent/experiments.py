"""Standard magnetics experiments composed from FEMM commands (force vs position, torque vs angle,
cogging, back-EMF, inductance / Ld-Lq, AC sweep, parametric sweeps, PM operating points).

Every experiment talks to FEMM only through ``link.call(name, *args)`` (a
:class:`~femm_agent.ipc.FemmLink` or anything with the same method), works on a saved copy of the
current magnetics document inside ``out_dir``, restores geometry / currents / frequency at the end,
and returns a JSON-able dict::

    {"experiment", "model", "parameters", "columns", "rows", "summary", "health", "health_summary",
     "files": {"csv", "json", "png", ...}, "timing": {"total_s", "solves", "per_solve_s"}}

Units: lengths in the model's problem units (moves) and metres (virtual-work derivatives), angles
in mechanical degrees, forces N, torques N*m, flux linkage Wb-turn, inductance H, frequency Hz.
Planar results include the model depth (FEMM integrates over it).
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Sequence

from . import estimate, femfile, health, plotting
from .experiments_core import (  # noqa: F401  (re-exported: the public names of this module since 0.1)
    BI_AREA, BI_COENERGY, BI_CURRENT, BI_ENERGY, BI_FX, BI_FY, BI_LOSS_HYST, BI_LOSS_RES, BI_LOSS_TOTAL, BI_TORQUE,
    BI_VOLUME, POINT_FIELDS, _CPLX_RE, _SETUP_RE, ExperimentInputError, Ops, Run, _angles, _csv_cell, _flat,
    _jsonable, _named, _num, _restore_currents, _zero_currents, as_complex, as_float)
from .units import MU0

# ============================================================================= force vs position

def force_vs_position(link, groups: Sequence[int], dx: float = 0.0, dy: float = 0.0, steps: int = 11, *,
                      force_groups: Sequence[int] | None = None, start_offset: Sequence[float] = (0.0, 0.0),
                      circuits: Sequence[str] | None = None, out_dir=None, restore_path=None,
                      estimate_fn: Callable[[float], float] | None = None, tolerance: float = 0.08,
                      solve_timeout: float | None = 600.0, tag: str | None = None) -> dict:
    """Move ``groups`` by (dx, dy) problem units per step, re-solve, record the weighted-stress-tensor
    force (block integrals 18/19 on ``force_groups``, default ``groups``), the total coenergy (17)
    and circuit flux linkages. Health: WST force along the motion vs virtual work dW'/ds.

    Axisymmetric models: x = r, y = z (only the z-force is non-zero for a body on the axis).
    """
    run = Run(link, "force_vs_position", out_dir, restore_path, solve_timeout, tag)
    ops = run.ops
    if steps < 1:
        raise ExperimentInputError(f"steps must be >= 1, got {steps}", "Pass steps >= 3 (the virtual-work check needs "
                                                                         "three points).")
    run.require_groups(groups, "groups")
    run.require_groups(force_groups or groups, "force_groups" if force_groups else "groups (force)", need_labels=True)
    run.require_circuits(circuits)
    fg = list(force_groups or groups)
    circuits = list(circuits) if circuits is not None else run.circuit_names()
    step_len = math.hypot(dx, dy)
    if step_len == 0:
        raise ExperimentInputError("dx and dy cannot both be zero",
                                   "Pass the step per solve, e.g. dy=0.25 (problem units); position = k * step.")
    ux, uy = dx / step_len, dy / step_len
    ox, oy = start_offset
    rows, pos, fx, fy, wco = [], [], [], [], []
    moved = 0                # whole (dx, dy) steps actually applied: restore exactly these
    offset = False
    try:
        if ox or oy:
            ops.move_groups(groups, ox, oy)
            offset = True
        for k in range(steps):
            if k:
                ops.move_groups(groups, dx, dy)
                moved += 1
            ops.solve()
            s = (k * step_len) + (ox * ux + oy * uy)
            f_x = as_float(ops.block_integral(BI_FX, fg))
            f_y = as_float(ops.block_integral(BI_FY, fg))
            w = as_float(ops.block_integral(BI_COENERGY))
            fl = [as_float(ops.circuit(c)["flux"]) for c in circuits]
            pos.append(s)
            fx.append(f_x)
            fy.append(f_y)
            wco.append(w)
            rows.append([s, f_x, f_y, f_x * ux + f_y * uy, w] + fl)
            ops.close_post()
    finally:
        bx, by = -dx * moved - (ox if offset else 0.0), -dy * moved - (oy if offset else 0.0)
        if bx or by:
            ops.move_groups(groups, bx, by)
    f_par = [r[3] for r in rows]
    vw = health.virtual_work_derivative([p * run.unit_m for p in pos], wco)
    for r, v in zip(rows, vw):
        r.insert(4, v)
    if steps >= 3:
        run.checks.append(health.curve_consistency(f_par, vw, "WST force", "virtual work dW'/ds",
                                                   tolerance, name="force_wst_vs_virtual_work"))
    if estimate_fn is not None:
        est = [estimate_fn(p) for p in pos]
        run.checks.append(health.curve_consistency(f_par, est, "FEM", "analytic", 0.25, name="force_vs_analytic"))
    cols = ["position", "Fx_N", "Fy_N", "F_along_motion_N", "F_virtual_work_N", "coenergy_J"] + [f"psi_{c}_Wb" for c in circuits]
    summary = {"max_abs_force_N": max(abs(v) for v in f_par), "force_at_start_N": f_par[0], "force_at_end_N": f_par[-1],
               "position_units": run.model.units, "direction": [ux, uy]}
    plots = [("force", lambda p: plotting.plot_curves(p, pos, {"WST": f_par, "virtual work": vw},
                                                      title="Force vs position", xlabel=f"displacement ({run.model.units})",
                                                      ylabel="force along motion (N)", dashed=("virtual work",)))]
    return run.finish({"groups": list(groups), "force_groups": fg, "dx": dx, "dy": dy, "steps": steps,
                       "start_offset": list(start_offset)}, cols, rows, summary, plots)


# ============================================================================= rotation core

def _age_names(run: Run) -> list:
    return [b.get("BdryName") for b in run.model.boundaries() if int(b.get("BdryType", 0) or 0) in (6, 7)]


def _preflight_rotation(run: Run, rotate_groups: Sequence[int], method: str, torque_groups: Sequence[int] | None,
                        circuits: Sequence[str] | None, center: Sequence[float], drive: dict | None = None,
                        slots: int | None = None, poles: int | None = None) -> None:
    """Groups / circuits exist and the drive dict is complete, before the first solve."""
    if method == "rotate":
        run.require_groups(rotate_groups, "rotate_groups")
        run.require_groups(torque_groups or rotate_groups, "torque_groups" if torque_groups else "rotate_groups (torque)",
                           need_labels=True)
    run.require_circuits(circuits)
    if drive:
        estimate.pole_pairs_of(drive, "drive")
        run.require_circuits(list(drive.get("circuits", ["A", "B", "C"])), "drive.circuits")
    run.warn_sector(center, slots, poles, method)
    run.torque_from_gap = method == "age"


def _torque_scale(run: Run) -> int:
    """Factor that puts derived torques (virtual work from coenergy) on the footing of the measured
    torque: on a 1/N sector the air-gap element torque is already full-machine while coenergy is
    per sector (measured, docs/femm5-facts.md), so x N; 1 otherwise."""
    return run.flux_scale if run.torque_from_gap else 1


def _rotation_sweep(run: Run, angles: list[float], rotate_groups: Sequence[int], center: Sequence[float],
                    method: str, gap_boundary: str | None, torque_groups: Sequence[int] | None,
                    circuits: Sequence[str], drive: dict | None, record_coenergy: bool = True) -> list[dict]:
    """Shared loop: set rotor angle, (optionally) set dq currents for that angle, solve, read
    torque(s), flux linkages and coenergy. Restores the rotor angle afterwards."""
    ops = run.ops
    cx, cy = (float(center[0]), float(center[1])) if center else (0.0, 0.0)
    gap0 = 0.0
    if method == "age":
        if not gap_boundary:
            raise ExperimentInputError("method='age' needs gap_boundary (the periodic air gap boundary name)",
                                       "Pass gap_boundary=<name from femm_geometry_summary().boundaries>, or use "
                                       "method='rotate'.")
        for b in run.model.boundaries():
            if b.get("BdryName") == gap_boundary:
                gap0 = float(b.get("innerangle") or 0)
                if int(b.get("BdryType", 0)) not in (6, 7):
                    raise ExperimentInputError(f"boundary {gap_boundary!r} is not a (anti)periodic air gap (BdryFormat 6/7)",
                                               f"Air-gap boundaries in this model: {_age_names(run)}; pass one as "
                                               "gap_boundary, or use method='rotate'.")
                break
        else:
            raise ExperimentInputError(f"no boundary named {gap_boundary!r} in the model",
                                       f"Boundaries in this model: {[b.get('BdryName') for b in run.model.boundaries()]} "
                                       "(femm_geometry_summary().boundaries); pass one exactly.")
    elif method != "rotate":
        raise ExperimentInputError(f"method must be 'rotate' or 'age', got {method!r}",
                                   "Use method='rotate' (rotate the groups, re-mesh) or method='age' with gap_boundary=<name>.")
    tg = list(torque_groups or rotate_groups)
    out = []
    current_angle = 0.0
    try:
        for ang in angles:
            if method == "rotate":
                d = ang - current_angle
                if abs(d) > 0:
                    ops.rotate_groups(rotate_groups, d, cx, cy)
                current_angle = ang
            else:
                ops.set_gap_angle(gap_boundary, gap0 + ang)
            currents = {}
            if drive:
                currents = dq_currents(drive, ang)
                for name, i in currents.items():
                    ops.set_current(name, i)
            ops.solve()
            rec: dict[str, Any] = {"angle": ang, "currents": currents}
            if method == "age":
                rec["torque_gap"] = as_float(ops.gap_integral(gap_boundary, 0))
                rec["torque"] = rec["torque_gap"]
            else:
                rec["torque_wst"] = as_float(ops.block_integral(BI_TORQUE, tg))
                rec["torque"] = rec["torque_wst"]
                if gap_boundary:
                    try:
                        rec["torque_gap"] = as_float(ops.gap_integral(gap_boundary, 0))
                    except Exception:
                        pass
            if record_coenergy:
                rec["coenergy"] = as_float(ops.block_integral(BI_COENERGY))
            rec["flux"] = {c: as_float(ops.circuit(c)["flux"]) for c in circuits}
            out.append(rec)
            ops.close_post()
    finally:
        if method == "rotate" and current_angle:
            ops.rotate_groups(rotate_groups, -current_angle, cx, cy)
        elif method == "age":
            ops.set_gap_angle(gap_boundary, gap0)
    return out


def dq_currents(drive: dict, rotor_angle_deg: float) -> dict[str, float]:
    """Phase currents for a dq operating point at a rotor angle.

    ``drive = {"circuits": ["A","B","C"], "poles": 2p, "id": Id, "iq": Iq, "theta0_deg": 0}`` (``poles``
    preferred; ``"pole_pairs": p`` accepted; exactly one); theta_e = p * angle + theta0 (d-axis
    electrical angle w.r.t. phase A). Amplitude-invariant."""
    p = estimate.pole_pairs_of(drive, "drive")
    th = math.radians(p * rotor_angle_deg + float(drive.get("theta0_deg", 0.0)))
    ia, ib, ic = estimate.inverse_park(float(drive.get("id", 0.0)), float(drive.get("iq", 0.0)), th)
    names = list(drive.get("circuits", ["A", "B", "C"]))
    return dict(zip(names, (ia, ib, ic)))


# ============================================================================= torque vs angle

def torque_vs_angle(link, rotate_groups: Sequence[int] = (1,), *, angles: Sequence[float] | None = None,
                    start: float = 0.0, stop: float = 90.0, steps: int = 19, center: Sequence[float] = (0.0, 0.0),
                    method: str = "rotate", gap_boundary: str | None = None, torque_groups: Sequence[int] | None = None,
                    drive: dict | None = None, circuits: Sequence[str] | None = None, out_dir=None, restore_path=None,
                    tolerance: float = 0.1, solve_timeout: float | None = 600.0, tag: str | None = None) -> dict:
    """Rotor torque vs mechanical angle.

    ``method='rotate'`` rotates ``rotate_groups`` about ``center`` and re-meshes each step; torque is
    the WST torque (block integral 22) on ``torque_groups`` (default ``rotate_groups``; leave out the
    rotor-side air). ``method='age'`` uses a FEMM 5 periodic air-gap element boundary instead: the
    inner side is rotated with ``mi_modifyboundprop(gap_boundary, 10, angle)`` and torque comes from
    ``mo_gapintegral(gap_boundary, 0)``; the mesh never changes. ``drive`` (see :func:`dq_currents`)
    makes the stator currents follow the rotor; without it currents are left as set. Health: torque
    vs virtual work dW'/dtheta (fixed currents only)."""
    run = Run(link, "torque_vs_angle", out_dir, restore_path, solve_timeout, tag)
    _preflight_rotation(run, rotate_groups, method, torque_groups, circuits, center, drive)
    circuits = list(circuits) if circuits is not None else run.circuit_names()
    angs = _angles(angles, start, stop, steps, True)
    recs = _rotation_sweep(run, angs, rotate_groups, center, method, gap_boundary, torque_groups, circuits, drive)
    if drive:
        _restore_currents(run)
    tq = [r["torque"] for r in recs]
    k = _torque_scale(run)
    vw = [v * k for v in health.virtual_work_derivative([math.radians(a) for a in angs], [r["coenergy"] for r in recs])]
    rows = []
    for r, v in zip(recs, vw):
        row = [r["angle"], r["torque"], r.get("torque_gap"), v, r["coenergy"]] + [r["flux"][c] for c in circuits]
        if drive:
            row += [r["currents"].get(c) for c in circuits]
        rows.append(row)
    cols = ["angle_deg", "torque_Nm", "torque_gap_Nm", "torque_virtual_work_Nm", "coenergy_J"] + [f"psi_{c}_Wb" for c in circuits]
    if drive:
        cols += [f"i_{c}_A" for c in circuits]
    if not drive and len(angs) >= 3:
        run.checks.append(health.curve_consistency(tq, vw, "torque", "virtual work dW'/dtheta", tolerance,
                                                   name="torque_vs_virtual_work"))
    gaps = [r.get("torque_gap") for r in recs]
    if method == "rotate" and all(g is not None for g in gaps):
        run.checks.append(health.curve_consistency(tq, gaps, "WST", "air-gap element", tolerance, name="torque_wst_vs_gap"))
    run.checks.append(health.torque_ripple(tq))
    t_dq = None
    if drive and len(circuits) == 3 and all(c in circuits for c in drive.get("circuits", [])):
        p = estimate.pole_pairs_of(drive, "drive")
        names = list(drive.get("circuits"))
        t_dq = []
        for r in recs:
            th = math.radians(p * r["angle"] + float(drive.get("theta0_deg", 0.0)))
            pd, pq = estimate.park(*(r["flux"][c] * run.flux_scale for c in names), th)
            t_dq.append(estimate.dq_torque(p, pd, pq, float(drive.get("id", 0.0)), float(drive.get("iq", 0.0))))
        pts = tq[:-1] if len(tq) > 2 else tq
        dts = t_dq[:-1] if len(t_dq) > 2 else t_dq
        if run.sector_n and not run.torque_from_gap:
            run.checks.append(health.not_applicable("mean_torque_vs_dq", "WST torque of a sector: full-machine scale "
                                                    "not measured (use method='age')"))
        else:
            run.checks.append(health.force_consistency(sum(pts) / len(pts), sum(dts) / len(dts), "mean FEM torque",
                                                       "mean 3/2 p (psi_d i_q - psi_q i_d)", 0.08,
                                                       name="mean_torque_vs_dq"))
        for row, v in zip(rows, t_dq):
            row.append(v)
        cols.append("torque_dq_Nm")
    summary = {"mean_torque_Nm": sum(tq) / len(tq), "max_torque_Nm": max(tq), "min_torque_Nm": min(tq),
               "peak_to_peak_Nm": max(tq) - min(tq), "angle_at_max_deg": angs[tq.index(max(tq))], "method": method}
    series = {"torque": tq}
    if not drive:
        series["virtual work"] = vw
    elif t_dq:
        series["dq formula"] = t_dq
    plots = [("torque", lambda p: plotting.plot_curves(p, angs, series, title="Torque vs rotor angle",
                                                       xlabel="rotor angle (deg mech)", ylabel="torque (N*m)",
                                                       dashed=("virtual work", "dq formula")))]
    return run.finish({"rotate_groups": list(rotate_groups), "torque_groups": list(torque_groups or rotate_groups),
                       "angles": angs, "center": list(center), "method": method, "gap_boundary": gap_boundary,
                       "drive": drive}, cols, rows, summary, plots)


# ============================================================================= cogging

def cogging(link, rotate_groups: Sequence[int] = (1,), *, slots: int, poles: int | None = None,
            pole_pairs: int | None = None, steps: int = 31,
            periods: float = 1.0, center: Sequence[float] = (0.0, 0.0), method: str = "rotate",
            gap_boundary: str | None = None, torque_groups: Sequence[int] | None = None,
            circuits: Sequence[str] | None = None, out_dir=None, restore_path=None,
            solve_timeout: float | None = 600.0, tag: str | None = None) -> dict:
    """Zero-current torque over ``periods`` cogging periods (360/lcm(Q, 2p) mech deg), with the
    end point included, plus its harmonic spectrum (order n = n * lcm(Q,2p) per revolution).
    All circuits are set to 0 A during the sweep and restored afterwards. Exactly one of ``poles``
    (2p, preferred) or ``pole_pairs``."""
    poles = 2 * estimate.resolve_pole_pairs(poles, pole_pairs, "cogging")
    run = Run(link, "cogging", out_dir, restore_path, solve_timeout, tag)
    _preflight_rotation(run, rotate_groups, method, torque_groups, circuits, center, slots=slots, poles=poles)
    circuits = list(circuits) if circuits is not None else run.circuit_names()
    period = estimate.cogging_period_deg(slots, poles)
    angs = _angles(None, 0.0, period * periods, steps, True)
    _zero_currents(run, run.circuit_names())
    try:
        recs = _rotation_sweep(run, angs, rotate_groups, center, method, gap_boundary, torque_groups, circuits, None)
    finally:
        _restore_currents(run)
    tq = [r["torque"] for r in recs]
    k = _torque_scale(run)
    vw = [v * k for v in health.virtual_work_derivative([math.radians(a) for a in angs], [r["coenergy"] for r in recs])]
    one = tq[:-1] if len(tq) > 2 else tq
    per_samples = int(round(len(one) / periods)) if periods >= 1 else len(one)
    h = estimate.harmonics(one[:per_samples])
    lcm = math.lcm(int(slots), int(poles))
    rows = [[r["angle"], r["torque"], v, r["coenergy"]] for r, v in zip(recs, vw)]
    cols = ["angle_deg", "cogging_torque_Nm", "torque_virtual_work_Nm", "coenergy_J"]
    pp = max(tq) - min(tq)
    run.checks.append(health.zero_mean(one))
    run.checks.append(health.periodicity(tq, len(tq) - 1, 0.1, name="cogging_periodic"))
    if method == "rotate" and len(tq) >= 3:
        run.checks.append(health.curve_consistency(tq, vw, "WST", "virtual work", 0.15,
                                                   name="cogging_vs_virtual_work"))
    top = sorted(((a, o) for o, a in zip(h["order"][1:], h["amplitude"][1:])), reverse=True)[:5]
    summary = {"peak_to_peak_Nm": pp, "rms_Nm": math.sqrt(sum(t * t for t in one) / len(one)),
               "period_deg": period, "lcm_Q_2p": lcm,
               "harmonics": [{"order_per_period": o, "order_per_rev": o * lcm / max(periods, 1) if periods >= 1 else o * lcm,
                              "amplitude_Nm": a} for a, o in top],
               "method": method}
    plots = [("torque", lambda p: plotting.plot_curves(p, angs, {"cogging torque": tq}, title="Cogging torque",
                                                       xlabel="rotor angle (deg mech)", ylabel="torque (N*m)")),
             ("harmonics", lambda p: plotting.plot_harmonics(p, h["order"], h["amplitude"], title="Cogging harmonics",
                                                             xlabel="order (per cogging period)", ylabel="amplitude (N*m)"))]
    return run.finish({"slots": slots, "poles": poles, "steps": steps, "periods": periods, "method": method,
                       "gap_boundary": gap_boundary, "rotate_groups": list(rotate_groups)}, cols, rows, summary, plots)


# ============================================================================= back-EMF

def back_emf(link, rotate_groups: Sequence[int] = (1,), *, poles: int | None = None, pole_pairs: int | None = None,
             rpm: float = 1000.0, steps: int = 36,
            circuits: Sequence[str] | None = None, center: Sequence[float] = (0.0, 0.0), method: str = "rotate",
            gap_boundary: str | None = None, psi_estimate: float | None = None, out_dir=None, restore_path=None,
            solve_timeout: float | None = 600.0, tag: str | None = None) -> dict:
    """Open-circuit flux linkage per circuit over one electrical period (360/p mech deg, ``steps``
    samples, end point excluded) and the back-EMF e = dpsi/dt = omega_m * dpsi/dtheta_m, computed
    spectrally (exact for periodic samples). Reports fundamental, THD, line-line EMF, harmonics.
    Health: balanced phases (sum ~ 0 for three phases), half-period antisymmetry. Give exactly one
    of ``poles`` (2p, preferred) or ``pole_pairs`` (p)."""
    import numpy as np

    pole_pairs = estimate.resolve_pole_pairs(poles, pole_pairs, "back_emf")
    run = Run(link, "back_emf", out_dir, restore_path, solve_timeout, tag)
    _preflight_rotation(run, rotate_groups, method, None, circuits, center, poles=2 * pole_pairs)
    circuits = list(circuits) if circuits is not None else run.default_circuits()
    if not circuits:
        raise ExperimentInputError("the model has no circuits",
                                   "Add one with femm_add_circuit(name=...), then femm_set_block_prop(x=, y=, material=, "
                                   "circuit=<name>, turns=<N>) on each coil label.")
    period = 360.0 / pole_pairs
    angs = _angles(None, 0.0, period, steps, False)
    _zero_currents(run, run.circuit_names())
    try:
        recs = _rotation_sweep(run, angs, rotate_groups, center, method, gap_boundary, None, circuits, None,
                               record_coenergy=False)
    finally:
        _restore_currents(run)
    omega_m = rpm * 2 * math.pi / 60
    psi = {c: np.array([r["flux"][c] for r in recs]) for c in circuits}
    emf, harm = {}, {}
    k = np.fft.rfftfreq(steps, d=1.0 / steps)  # electrical harmonic orders
    for c in circuits:
        X = np.fft.rfft(psi[c])
        # d/dtheta_m with theta_m = 2 pi n / (p * steps): factor j * order * p
        dX = X * 1j * k * pole_pairs
        if steps % 2 == 0:
            dX[-1] = 0
        emf[c] = np.fft.irfft(dX, n=steps) * omega_m
        harm[c] = estimate.harmonics(emf[c])
    rows = []
    for i, a in enumerate(angs):
        rows.append([a, pole_pairs * a] + [float(psi[c][i]) for c in circuits] + [float(emf[c][i]) for c in circuits])
    cols = ["angle_deg_mech", "angle_deg_elec"] + [f"psi_{c}_Wb" for c in circuits] + [f"emf_{c}_V" for c in circuits]
    psi1 = {c: estimate.harmonics(psi[c])["amplitude"][1] for c in circuits}
    e1 = {c: harm[c]["amplitude"][1] for c in circuits}
    summary: dict[str, Any] = {"rpm": rpm, "electrical_frequency_Hz": pole_pairs * rpm / 60,
                               "psi_fundamental_Wb": psi1, "emf_fundamental_peak_V": e1,
                               "emf_fundamental_rms_V": {c: v / math.sqrt(2) for c, v in e1.items()},
                               "emf_thd": {c: harm[c]["thd"] for c in circuits},
                               "ke_V_per_rad_s": {c: v / omega_m for c, v in e1.items()},
                               "harmonics_phase1": [{"order": o, "amplitude_V": a} for o, a in
                                                    zip(harm[circuits[0]]["order"][:16], harm[circuits[0]]["amplitude"][:16])]}
    if len(circuits) >= 2:
        ll = emf[circuits[0]] - emf[circuits[1]]
        summary["emf_line_line_peak_V"] = float(np.max(np.abs(ll)))
        summary["emf_line_line_fundamental_V"] = estimate.harmonics(ll)["amplitude"][1]
    if len(circuits) == 3:
        ph = [np.fft.rfft(psi[c])[1] for c in circuits]
        amp = max(abs(z) for z in ph) or 1.0
        bal = float(abs(sum(ph)) / amp)
        run.checks.append({"name": "three_phase_balance", "ok": bal < 0.03, "value": bal, "expected": 0.0,
                           "tolerance": 0.03, "message": f"|sum of fundamental flux phasors| = {bal:.2%} of one phase"
                           + ("" if bal < 0.03 else " (phases not 120 deg apart / unequal: check the winding layout)")})
    if steps % 2 == 0:
        p0 = psi[circuits[0]]
        anti = float(np.max(np.abs(p0[: steps // 2] + p0[steps // 2:]))) / (float(np.max(np.abs(p0))) or 1.0)
        run.checks.append({"name": "half_wave_antisymmetry", "ok": anti < 0.05, "value": anti, "expected": 0.0,
                           "tolerance": 0.05, "message": f"psi(theta + T/2) + psi(theta) peaks at {anti:.2%} of peak psi"})
    if psi_estimate:
        run.checks.append(health.compare_to_estimate("psi_pm_vs_analytic", psi1[circuits[0]] * run.flux_scale,
                                                     psi_estimate, 0.2,
                                                     "flat-gap SPM estimate; leakage and slotting lower the FEM value"))
    el = [pole_pairs * a for a in angs]
    plots = [("psi", lambda p: plotting.plot_curves(p, el, {c: psi[c].tolist() for c in circuits},
                                                    title="Open-circuit flux linkage", xlabel="rotor angle (deg elec)",
                                                    ylabel="flux linkage (Wb)", markers=False)),
             ("emf", lambda p: plotting.plot_curves(p, el, {c: emf[c].tolist() for c in circuits},
                                                    title=f"Back-EMF at {rpm:g} rpm", xlabel="rotor angle (deg elec)",
                                                    ylabel="EMF (V)", markers=False)),
             ("harmonics", lambda p: plotting.plot_harmonics(p, harm[circuits[0]]["order"], harm[circuits[0]]["amplitude"],
                                                             title=f"Back-EMF harmonics, {circuits[0]}",
                                                             xlabel="electrical order", ylabel="amplitude (V)", max_order=19))]
    return run.finish({"poles": 2 * pole_pairs, "pole_pairs": pole_pairs, "rpm": rpm, "steps": steps, "circuits": circuits, "method": method,
                       "gap_boundary": gap_boundary}, cols, rows, summary, plots)


# ============================================================================= PM operating points

def bh_check(link, *, out_dir=None, restore_path=None, min_fraction: float = 0.2, solve_timeout: float | None = 600.0,
             tag: str | None = None) -> dict:
    """Operating point of every permanent-magnet block label: solve, then combine the .ans element
    -> block-label map with ``mo_getallb`` to get, per magnet, the area-weighted mean and minimum
    flux density along the magnetisation direction B_m, the field H_m = B_m/(mu0 mu_r) - Hc (linear
    magnets) or from the B-H curve, the permeance coefficient Pc = -B_m/(mu0 H_m) and B_m/Br.
    Health: every magnet keeps min B_m >= ``min_fraction`` * Br (demagnetisation risk)."""
    run = Run(link, "bh_check", out_dir, restore_path, solve_timeout, tag)
    ops = run.ops
    ops.solve()
    ans = femfile.parse_file(femfile.solution_path(run.model_path))
    bulk = ops.bulk()
    rows, checks = magnet_operating_points(ans, bulk["B"], bulk["area"], min_fraction)
    run.checks.extend(checks)
    cols = ["label_index", "material", "x", "y", "Bm_mean_T", "Bm_min_T", "Hm_mean_A_per_m", "Pc", "Br_T",
            "Bm_over_Br", "note"]
    ok_rows = [r for r in rows if r[4] is not None]
    summary = {"magnets": len(rows),
               "worst_Bm_min_T": min((r[5] for r in ok_rows), default=None),
               "mean_Pc": (sum(r[7] for r in ok_rows if r[7]) / len(ok_rows)) if ok_rows else None}
    if not rows:
        run.checks.append(health.not_applicable("pm_operating_point", "no permanent-magnet block labels (H_c = 0 everywhere)"))
    return run.finish({"min_fraction": min_fraction}, cols, rows, summary, [], leave_solved=False)


def magnet_operating_points(ans: "femfile.FemmFile", B, area, min_fraction: float = 0.2) -> tuple[list[list], list[dict]]:
    """Per permanent-magnet block label: area-weighted mean / min B along the magnetisation
    direction, H_m, Pc and B_m/Br, from a parsed solution (element -> label map) and element B
    (M,2, e.g. ``mo_getallb``) and areas. Returns (rows, health checks)."""
    import numpy as np

    labels = ans.block_labels()
    mats = {m.get("BlockName"): m for m in ans.materials()}
    lab_idx = ans.element_labels()
    B = np.asarray(B, dtype=float)
    area = np.asarray(area, dtype=float)
    if len(lab_idx) != len(B):
        raise ExperimentInputError("element count mismatch between the .ans file and the live mesh",
                                   "Re-solve with femm_solve(), then repeat the call.")
    rows, checks = [], []
    for li, lab in enumerate(labels):
        m = mats.get(lab["material"])
        if not m or float(m.get("H_c") or 0) <= 0:
            continue
        sel = lab_idx == li
        if not np.any(sel):
            continue
        if "magdir_formula" in lab:
            rows.append([li, lab["material"], lab["x"], lab["y"], None, None, None, None, None, None,
                         "magdir formula: skipped"])
            continue
        hc = float(m["H_c"])
        mur = float(m.get("Mu_x") or 1.0)
        bh = m.get("BHPoints_data") or []
        t = math.radians(lab.get("magdir", 0.0))
        ux, uy = math.cos(t), math.sin(t)
        bpar = B[sel, 0] * ux + B[sel, 1] * uy
        w = area[sel]
        bm = float(np.sum(bpar * w) / np.sum(w))
        bmin = float(np.min(bpar))
        if bh:
            curve = np.asarray(bh, dtype=float)
            br = float(np.interp(hc, curve[:, 1], curve[:, 0]))

            def h_of(b, curve=curve, hc=hc):
                return float(np.interp(abs(b), curve[:, 0], curve[:, 1])) * (1 if b >= 0 else -1) - hc
        else:
            br = MU0 * mur * hc

            def h_of(b, mur=mur, hc=hc):
                return b / (MU0 * mur) - hc
        hm = h_of(bm)
        pc = -bm / (MU0 * hm) if hm else None
        rows.append([li, lab["material"], lab["x"], lab["y"], bm, bmin, hm, pc, br, bm / br if br else None,
                     "nonlinear magnet: H from B-H curve (approx.)" if bh else ""])
        checks.append(health.pm_operating_point(bmin, br, h_of(bmin), min_fraction,
                                                label=f"{lab['material']}@({lab['x']:.3g},{lab['y']:.3g})"))
    return rows, checks


# ============================================================================= field snapshot

def field_snapshot(link, out_path_png: str | Path, npz_path: str | Path | None = None, *, zoom=None,
                   title: str = "|B| (T)") -> dict:
    """Bulk |B| map of the loaded solution (no GUI): ``mo_getallnodes/elements/b`` -> PNG (+ .npz)."""
    import numpy as np

    ops = Ops(link)
    bulk = ops.bulk()
    bmag = np.hypot(bulk["B"][:, 0], bulk["B"][:, 1])
    out: dict[str, Any] = {"nodes": int(len(bulk["nodes"])), "elements": int(len(bulk["tri"])),
                           "B_max_T": float(bmag.max()) if len(bmag) else 0.0,
                           "B_p99_T": float(np.percentile(bmag, 99)) if len(bmag) else 0.0}
    if npz_path:
        np.savez_compressed(npz_path, nodes=bulk["nodes"], elements=bulk["tri"], area=bulk["area"], group=bulk["group"],
                            B=bulk["B"])
        out["npz"] = str(npz_path)
    xlim = ylim = None
    if zoom:
        xlim, ylim = (zoom[0], zoom[1]), (zoom[2], zoom[3])
    png = plotting.plot_field(out_path_png, bulk["nodes"], bulk["tri"], bmag, title=title, xlim=xlim, ylim=ylim)
    out["png"] = png
    return out


def b_along_line(link, p1: Sequence[float], p2: Sequence[float], n: int = 101) -> dict:
    """|B|, Bn, Bt sampled at n points on the segment p1 -> p2 (mo_getpointvalues per point)."""
    ops = Ops(link)
    (x1, y1), (x2, y2) = p1, p2
    L = math.hypot(x2 - x1, y2 - y1)
    tx, ty = ((x2 - x1) / L, (y2 - y1) / L) if L else (1.0, 0.0)
    d, bmag, bn, bt = [], [], [], []
    for k in range(n):
        s = k / (n - 1) if n > 1 else 0.0
        pv = ops.point(x1 + s * (x2 - x1), y1 + s * (y2 - y1))
        b1, b2 = as_float(pv["B1"]), as_float(pv["B2"])
        d.append(s * L)
        bmag.append(math.hypot(b1, b2))
        bt.append(b1 * tx + b2 * ty)
        bn.append(-b1 * ty + b2 * tx)
    return {"distance": d, "B": bmag, "Bn": bn, "Bt": bt}


from .experiments_sweeps import _named, ac_sweep, collect_output, inductance, parametric  # noqa: E402

EXPERIMENTS = {"force_vs_position": force_vs_position, "torque_vs_angle": torque_vs_angle, "cogging": cogging,
               "back_emf": back_emf, "inductance": inductance, "ac_sweep": ac_sweep, "parametric": parametric,
               "bh_check": bh_check}


backemf = back_emf   # pre-0.2.0 name of the module function (the MCP tool is femm_experiment_back_emf)
