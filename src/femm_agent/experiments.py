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

import csv
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from . import estimate, femfile, health, plotting
from .units import MU0

# block-integral codes (FEMM 5 manual 3.7.1, magnetics)
BI_ENERGY, BI_LOSS_HYST, BI_LOSS_RES, BI_AREA, BI_LOSS_TOTAL, BI_CURRENT = 2, 3, 4, 5, 6, 7
BI_VOLUME, BI_COENERGY, BI_FX, BI_FY, BI_TORQUE = 10, 17, 18, 19, 22
POINT_FIELDS = ("A", "B1", "B2", "Sig", "E", "H1", "H2", "Je", "Js", "Mu1", "Mu2", "Pe", "Ph", "ff")
_SETUP_RE = re.compile(r"^(mi|ei|hi|ci)_[a-z0-9_]+$")
_CPLX_RE = re.compile(r"^\s*([+-]?[\d.eE+-]*?)\s*([+-])\s*I\s*\*\s*([\d.eE+-]+)\s*$")


# ============================================================================= value helpers

def as_complex(v: Any) -> complex:
    """FEMM replies: float, Python complex, or strings like ``'1.5+I*2'``."""
    if isinstance(v, complex):
        return v
    if isinstance(v, (int, float)):
        return complex(v, 0.0)
    if isinstance(v, str):
        s = v.strip().replace(" ", "")
        m = _CPLX_RE.match(s)
        if m:
            re_part = float(m.group(1)) if m.group(1) not in ("", "+", "-") else 0.0
            im = float(m.group(3)) * (-1 if m.group(2) == "-" else 1)
            return complex(re_part, im)
        try:
            return complex(s.replace("I*", "").replace("i", "j").replace("I", "j"))
        except ValueError:
            pass
    if isinstance(v, (list, tuple)) and v:
        return as_complex(v[0])
    raise ValueError(f"not a number from FEMM: {v!r}")


def as_float(v: Any) -> float:
    return as_complex(v).real


def _num(v: Any) -> float | dict:
    """JSON-friendly scalar (complex -> {'re','im'} only when the imaginary part matters)."""
    z = as_complex(v)
    if abs(z.imag) > 1e-12 * max(1.0, abs(z.real)):
        return {"re": z.real, "im": z.imag}
    return z.real


def _flat(v: Any) -> list:
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


# ============================================================================= FEMM operations

class Ops:
    """Thin, testable wrapper over ``link.call`` for the magnetics pre/post processor."""

    def __init__(self, link, solve_timeout: float | None = 600.0):
        self.link = link
        self.solve_timeout = solve_timeout
        self.solves = 0
        self.solve_seconds = 0.0

    def call(self, name, *args, **kw):
        return self.link.call(name, *args, **kw)

    # -- solving
    def solve(self) -> None:
        t0 = time.time()
        self.call("mi_analyze", 1, timeout=self.solve_timeout)
        self.call("mi_loadsolution")
        self.solves += 1
        self.solve_seconds += time.time() - t0

    def close_post(self) -> None:
        try:
            self.call("mo_close")
        except Exception:
            pass

    # -- postprocessing
    def block_integral(self, code: int, groups: Sequence[int] | None = None) -> Any:
        self.call("mo_clearblock")
        if groups is None:
            self.call("mo_groupselectblock")
        else:
            for g in groups:
                self.call("mo_groupselectblock", int(g))
        v = self.call("mo_blockintegral", int(code))
        self.call("mo_clearblock")
        return v

    def point(self, x: float, y: float) -> dict[str, Any]:
        vals = _flat(self.call("mo_getpointvalues", x, y))
        return dict(zip(POINT_FIELDS, vals))

    def circuit(self, name: str) -> dict[str, complex]:
        v = _flat(self.call("mo_getcircuitproperties", name))
        i, volt, flux = (as_complex(x) for x in (v + [0, 0, 0])[:3])
        return {"current": i, "voltage": volt, "flux": flux}

    def gap_integral(self, bdry: str, code: int = 0) -> Any:
        return self.call("mo_gapintegral", bdry, int(code))

    def line_integral(self, points: Sequence[Sequence[float]], code: int) -> list:
        self.call("mo_clearcontour")
        for x, y in points:
            self.call("mo_addcontour", x, y)
        v = _flat(self.call("mo_lineintegral", int(code)))
        self.call("mo_clearcontour")
        return v

    def bulk(self) -> dict[str, Any]:
        """Nodes (N,2), elements (M,3) 0-based + centroid/area/group, B (M,2 real) via the bulk getters."""
        import numpy as np

        nodes = np.asarray([as_float(x) for x in _flat(self.call("mo_getallnodes"))]).reshape(-1, 2)
        el = np.asarray([as_float(x) for x in _flat(self.call("mo_getallelements"))]).reshape(-1, 7)
        braw = _flat(self.call("mo_getallb"))
        b = np.asarray([as_complex(x) for x in braw]).reshape(-1, 2)
        return {"nodes": nodes, "tri": el[:, :3].astype(int) - 1, "centroid": el[:, 3:5], "area": el[:, 5],
                "group": el[:, 6].astype(int), "B": b.real, "B_complex": b}

    # -- preprocessor edits
    def move_groups(self, groups: Sequence[int], dx: float, dy: float) -> None:
        for g in groups:
            self.call("mi_clearselected")
            self.call("mi_selectgroup", int(g))
            self.call("mi_movetranslate", dx, dy, 4)
        self.call("mi_clearselected")

    def rotate_groups(self, groups: Sequence[int], angle_deg: float, cx: float = 0.0, cy: float = 0.0) -> None:
        for g in groups:
            self.call("mi_clearselected")
            self.call("mi_selectgroup", int(g))
            self.call("mi_moverotate", cx, cy, angle_deg, 4)
        self.call("mi_clearselected")

    def set_current(self, circuit: str, value: float | complex) -> None:
        self.call("mi_modifycircprop", circuit, 1, value)

    def set_gap_angle(self, bdry: str, inner_deg: float) -> None:
        self.call("mi_modifyboundprop", bdry, 10, inner_deg)

    def save_as(self, path: str | Path) -> None:
        self.call("mi_saveas", str(path).replace("\\", "/"))


# ============================================================================= experiment scaffolding

class Run:
    """Bookkeeping for one experiment: snapshot the model, time it, write outputs."""

    def __init__(self, link, name: str, out_dir: str | Path | None, restore_path: str | None = None,
                 solve_timeout: float | None = 600.0, tag: str | None = None):
        self.name = name
        self.t0 = time.time()
        self.ops = Ops(link, solve_timeout)
        stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int((time.time() % 1) * 1000):03d}"
        base = Path(out_dir) if out_dir else Path.cwd() / "experiments"
        self.dir = base / f"{name}-{tag or stamp}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.restore_path = restore_path
        self.model_path = self.dir / "model.fem"
        self.ops.save_as(self.model_path)
        self.model = femfile.parse_file(self.model_path)
        if self.model.physics != "magnetics":
            raise ValueError("experiments need a magnetics (.fem) document; call femm_new_document(physics='magnetics')")
        self.files: dict[str, str] = {}
        self.checks: list[dict] = []

    # model facts
    @property
    def unit_m(self) -> float:
        return self.model.unit_to_m

    def circuit_names(self) -> list[str]:
        return [c.get("CircuitName") for c in self.model.circuits() if c.get("CircuitName")]

    def circuit_currents(self) -> dict[str, complex]:
        return {c["CircuitName"]: complex(float(c.get("TotalAmps_re", 0) or 0), float(c.get("TotalAmps_im", 0) or 0))
                for c in self.model.circuits() if c.get("CircuitName")}

    def linear_no_pm(self) -> bool:
        used = {lab["material"] for lab in self.model.block_labels()}
        for m in self.model.materials():
            if m.get("BlockName") in used and (m.get("BHPoints_data") or float(m.get("H_c") or 0) > 0):
                return False
        return True

    def finish(self, parameters: dict, columns: list[str], rows: list[list], summary: dict,
               plots: Iterable[tuple[str, Callable[[Path], Any]]] = (), leave_solved: bool = True) -> dict:
        if self.restore_path:
            try:
                self.ops.save_as(self.restore_path)
            except Exception:
                pass
        if leave_solved:
            try:
                self.ops.solve()
            except Exception:
                pass
        csv_path = self.dir / f"{self.name}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(columns)
            for r in rows:
                w.writerow([_csv_cell(x) for x in r])
        self.files["csv"] = str(csv_path)
        for key, fn in plots:
            try:
                p = fn(self.dir / f"{self.name}_{key}.png")
                if p:
                    self.files[f"png_{key}"] = str(p)
            except Exception as e:  # plotting must never sink an experiment
                self.files[f"png_{key}_error"] = f"{type(e).__name__}: {e}"
        total = time.time() - self.t0
        out = {
            "experiment": self.name, "model": str(self.model_path), "document": self.restore_path or str(self.model_path),
            "parameters": parameters, "columns": columns, "rows": [[_jsonable(x) for x in r] for r in rows],
            "summary": _jsonable(summary), "health": self.checks, "health_summary": health.summarize(self.checks),
            "files": self.files,
            "timing": {"total_s": round(total, 3), "solves": self.ops.solves,
                       "per_solve_s": round(self.ops.solve_seconds / self.ops.solves, 4) if self.ops.solves else None},
        }
        json_path = self.dir / f"{self.name}.json"
        out["files"]["json"] = str(json_path)
        json_path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        return out


def _jsonable(x):
    if isinstance(x, complex):
        return _num(x)
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if hasattr(x, "tolist"):
        return x.tolist()
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


def _csv_cell(x):
    if isinstance(x, complex):
        return f"{x.real:.10g}{x.imag:+.10g}j"
    if isinstance(x, float):
        return f"{x:.10g}"
    return x


def _angles(angles: Sequence[float] | None, start: float, stop: float, steps: int, endpoint: bool) -> list[float]:
    if angles is not None:
        return [float(a) for a in angles]
    if steps < 1:
        raise ValueError("steps must be >= 1")
    if steps == 1:
        return [float(start)]
    n = steps - 1 if endpoint else steps
    return [start + (stop - start) * k / n for k in range(steps)]


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
    fg = list(force_groups or groups)
    circuits = list(circuits) if circuits is not None else run.circuit_names()
    step_len = math.hypot(dx, dy)
    if step_len == 0:
        raise ValueError("dx and dy cannot both be zero")
    ux, uy = dx / step_len, dy / step_len
    ox, oy = start_offset
    if ox or oy:
        ops.move_groups(groups, ox, oy)
    rows, pos, fx, fy, wco = [], [], [], [], []
    try:
        for k in range(steps):
            if k:
                ops.move_groups(groups, dx, dy)
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
        back = steps - 1
        ops.move_groups(groups, -dx * back - ox, -dy * back - oy)
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
            raise ValueError("method='age' needs gap_boundary (the periodic air gap boundary name)")
        for b in run.model.boundaries():
            if b.get("BdryName") == gap_boundary:
                gap0 = float(b.get("innerangle") or 0)
                if int(b.get("BdryType", 0)) not in (6, 7):
                    raise ValueError(f"boundary {gap_boundary!r} is not a (anti)periodic air gap (BdryFormat 6/7)")
                break
        else:
            raise ValueError(f"no boundary named {gap_boundary!r} in the model")
    elif method != "rotate":
        raise ValueError("method must be 'rotate' or 'age'")
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

    ``drive = {"circuits": ["A","B","C"], "pole_pairs": p, "id": Id, "iq": Iq, "theta0_deg": 0}``;
    theta_e = p * angle + theta0 (d-axis electrical angle w.r.t. phase A). Amplitude-invariant."""
    p = int(drive.get("pole_pairs", 1))
    th = math.radians(p * rotor_angle_deg + float(drive.get("theta0_deg", 0.0)))
    ia, ib, ic = estimate.inverse_park(float(drive.get("id", 0.0)), float(drive.get("iq", 0.0)), th)
    names = list(drive.get("circuits", ["A", "B", "C"]))
    return dict(zip(names, (ia, ib, ic)))


def _zero_currents(run: Run, circuits: Sequence[str]) -> None:
    for c in circuits:
        run.ops.set_current(c, 0)


def _restore_currents(run: Run) -> None:
    for name, i in run.circuit_currents().items():
        run.ops.set_current(name, i.real if i.imag == 0 else i)


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
    circuits = list(circuits) if circuits is not None else run.circuit_names()
    angs = _angles(angles, start, stop, steps, True)
    recs = _rotation_sweep(run, angs, rotate_groups, center, method, gap_boundary, torque_groups, circuits, drive)
    if drive:
        _restore_currents(run)
    tq = [r["torque"] for r in recs]
    vw = health.virtual_work_derivative([math.radians(a) for a in angs], [r["coenergy"] for r in recs])
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
        p = int(drive.get("pole_pairs", 1))
        names = list(drive.get("circuits"))
        t_dq = []
        for r in recs:
            th = math.radians(p * r["angle"] + float(drive.get("theta0_deg", 0.0)))
            pd, pq = estimate.park(*(r["flux"][c] for c in names), th)
            t_dq.append(estimate.dq_torque(p, pd, pq, float(drive.get("id", 0.0)), float(drive.get("iq", 0.0))))
        pts = tq[:-1] if len(tq) > 2 else tq
        dts = t_dq[:-1] if len(t_dq) > 2 else t_dq
        run.checks.append(health.force_consistency(sum(pts) / len(pts), sum(dts) / len(dts), "mean FEM torque",
                                                   "mean 3/2 p (psi_d i_q - psi_q i_d)", 0.08, name="mean_torque_vs_dq"))
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

def cogging(link, rotate_groups: Sequence[int] = (1,), *, slots: int, poles: int, steps: int = 31,
            periods: float = 1.0, center: Sequence[float] = (0.0, 0.0), method: str = "rotate",
            gap_boundary: str | None = None, torque_groups: Sequence[int] | None = None,
            circuits: Sequence[str] | None = None, out_dir=None, restore_path=None,
            solve_timeout: float | None = 600.0, tag: str | None = None) -> dict:
    """Zero-current torque over ``periods`` cogging periods (360/lcm(Q, 2p) mech deg), with the
    end point included, plus its harmonic spectrum (order n = n * lcm(Q,2p) per revolution).
    All circuits are set to 0 A during the sweep and restored afterwards."""
    run = Run(link, "cogging", out_dir, restore_path, solve_timeout, tag)
    circuits = list(circuits) if circuits is not None else run.circuit_names()
    period = estimate.cogging_period_deg(slots, poles)
    angs = _angles(None, 0.0, period * periods, steps, True)
    _zero_currents(run, run.circuit_names())
    try:
        recs = _rotation_sweep(run, angs, rotate_groups, center, method, gap_boundary, torque_groups, circuits, None)
    finally:
        _restore_currents(run)
    tq = [r["torque"] for r in recs]
    vw = health.virtual_work_derivative([math.radians(a) for a in angs], [r["coenergy"] for r in recs])
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

def backemf(link, rotate_groups: Sequence[int] = (1,), *, pole_pairs: int, rpm: float = 1000.0, steps: int = 36,
            circuits: Sequence[str] | None = None, center: Sequence[float] = (0.0, 0.0), method: str = "rotate",
            gap_boundary: str | None = None, psi_estimate: float | None = None, out_dir=None, restore_path=None,
            solve_timeout: float | None = 600.0, tag: str | None = None) -> dict:
    """Open-circuit flux linkage per circuit over one electrical period (360/p mech deg, ``steps``
    samples, end point excluded) and the back-EMF e = dpsi/dt = omega_m * dpsi/dtheta_m, computed
    spectrally (exact for periodic samples). Reports fundamental, THD, line-line EMF, harmonics.
    Health: balanced phases (sum ~ 0 for three phases), half-period antisymmetry."""
    import numpy as np

    run = Run(link, "backemf", out_dir, restore_path, solve_timeout, tag)
    circuits = list(circuits) if circuits is not None else run.circuit_names()
    if not circuits:
        raise ValueError("the model has no circuits; add mi_addcircprop + labels in the circuit first")
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
        run.checks.append(health.compare_to_estimate("psi_pm_vs_analytic", psi1[circuits[0]], psi_estimate, 0.2,
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
    return run.finish({"pole_pairs": pole_pairs, "rpm": rpm, "steps": steps, "circuits": circuits, "method": method,
                       "gap_boundary": gap_boundary}, cols, rows, summary, plots)


# ============================================================================= inductance

def inductance(link, circuits: Sequence[str] | None = None, current: float = 1.0, *, dq: dict | None = None,
               torque_groups: Sequence[int] | None = None, gap_boundary: str | None = None, out_dir=None,
               restore_path=None, solve_timeout: float | None = 600.0, tag: str | None = None) -> dict:
    """Inductance matrix by flux-linkage differences: L_jk = (psi_j(I_k = current) - psi_j(0)) / current
    (subtracting the zero-current solve removes PM flux; for saturating iron this is the secant
    inductance about the PM operating point).

    ``dq = {"circuits": ["A","B","C"], "pole_pairs": p, "theta0_deg": 0, "id": 1, "iq": 1}`` instead
    injects d- and q-axis currents at the present rotor position (theta0 = electrical angle of the
    d-axis w.r.t. phase A) and returns psi_pm, Ld, Lq, saliency and the dq torque, checked against
    the FEM torque (WST on ``torque_groups`` or ``mo_gapintegral(gap_boundary, 0)``)."""
    run = Run(link, "inductance", out_dir, restore_path, solve_timeout, tag)
    ops = run.ops
    allc = run.circuit_names()
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
            p = int(dq.get("pole_pairs", 1))
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
        else:
            circuits = list(circuits) if circuits is not None else allc
            if not circuits:
                raise ValueError("no circuits in the model")
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
                       "torque_groups": torque_groups, "gap_boundary": gap_boundary}, cols, rows, summary, plots)


def _named(check: dict, name: str) -> dict:
    check = dict(check)
    check["name"] = name
    return check


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
    circuits = list(circuits) if circuits is not None else run.circuit_names()
    if not circuits:
        raise ValueError("no circuits in the model")
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
        raise ValueError(f"setup command {name!r} not allowed: use preprocessor commands (mi_/ei_/hi_/ci_ ...)")


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
            raise ValueError(f"unknown point quantity {q!r}")
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
    raise ValueError(f"unknown output kind {kind!r} (point, block, circuit, gap, line, expr)")


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
        raise RuntimeError("element count mismatch between the .ans file and the live mesh (re-solve first)")
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


EXPERIMENTS = {"force_vs_position": force_vs_position, "torque_vs_angle": torque_vs_angle, "cogging": cogging,
               "backemf": backemf, "inductance": inductance, "ac_sweep": ac_sweep, "parametric": parametric,
               "bh_check": bh_check}
