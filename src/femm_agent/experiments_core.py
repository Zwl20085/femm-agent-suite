"""Shared scaffolding of the experiments (pure Python over ``link.call``): block-integral codes,
value helpers, :class:`Ops` (thin FEMM operations), :class:`Run` (snapshot, pre-flight, outputs),
the input-error type and current helpers. Imported by :mod:`femm_agent.experiments` and
:mod:`femm_agent.experiments_sweeps`; it imports neither, so either can be imported first."""
from __future__ import annotations

import csv
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from . import femfile, health, preflight

# block-integral codes (FEMM 5 manual 3.7.1, magnetics)
BI_ENERGY, BI_LOSS_HYST, BI_LOSS_RES, BI_AREA, BI_LOSS_TOTAL, BI_CURRENT = 2, 3, 4, 5, 6, 7
BI_VOLUME, BI_COENERGY, BI_FX, BI_FY, BI_TORQUE = 10, 17, 18, 19, 22
POINT_FIELDS = ("A", "B1", "B2", "Sig", "E", "H1", "H2", "Je", "Js", "Mu1", "Mu2", "Pe", "Ph", "ff")
_SETUP_RE = re.compile(r"^(mi|ei|hi|ci)_[a-z0-9_]+$")
_CPLX_RE = re.compile(r"^\s*([+-]?[\d.eE+-]*?)\s*([+-])\s*I\s*\*\s*([\d.eE+-]+)\s*$")


# ============================================================================= errors

class ExperimentInputError(ValueError):
    """Bad experiment input detected before (or instead of) solving. Still a ValueError for callers of
    this pure module; the tool envelope reports it as ``ok: false`` with ``hint`` (no traceback)."""

    tool_input = True

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint


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
    last: "Run | None" = None
    """Bookkeeping for one experiment: snapshot the model, time it, write outputs."""

    def __init__(self, link, name: str, out_dir: str | Path | None, restore_path: str | None = None,
                 solve_timeout: float | None = 600.0, tag: str | None = None):
        self.name = name
        self.t0 = time.time()
        self.ops = Ops(link, solve_timeout)
        Run.last = self          # lets the tool layer undo the working-copy switch if pre-flight refuses
        stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int((time.time() % 1) * 1000):03d}"
        base = Path(out_dir) if out_dir else Path.cwd() / "experiments"
        self.dir = base / f"{name}-{tag or stamp}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.restore_path = restore_path
        self.model_path = self.dir / "model.fem"
        self.ops.save_as(self.model_path)
        self.model = femfile.parse_file(self.model_path)
        if self.model.physics != "magnetics":
            raise ExperimentInputError("experiments need a magnetics (.fem) document",
                                       "Open or create one: femm_new_document(physics='magnetics'), femm_open(path) or "
                                       "femm_build_benchmark(kind).")
        self.files: dict[str, str] = {}
        self.checks: list[dict] = []
        self.warnings: list[str] = []
        self.left_solved: bool | None = None
        self.sector_n: int | None = None        # 1/N rotational sector (set by warn_sector)
        self.sector_angle: float | None = None  # sector angle in deg, also when it does not divide 360
        self.torque_from_gap = False            # torque read with mo_gapintegral (full machine on a sector)

    # pre-flight (before the first solve)
    def require_groups(self, groups: Sequence[int] | None, what: str = "groups", need_labels: bool = False) -> None:
        preflight.require_groups(self.model, groups, what, need_labels)

    def require_circuits(self, circuits: Sequence[str] | None, what: str = "circuits") -> None:
        preflight.require_circuits(self.model, circuits, what)

    def warn_sector(self, center: Sequence[float] = (0.0, 0.0), slots: int | None = None,
                    poles: int | None = None, method: str | None = None) -> None:
        """Detect a rotational sector (sets `sector_n`) and add the warnings that go with it."""
        self.sector_angle, self.sector_n = preflight.sector_factor(self.model, center)
        self.warnings.extend(preflight.sector_warnings(self.model, center, slots, poles, method))

    def refuse_rotate_on_sector(self, center: Sequence[float] = (0.0, 0.0)) -> None:
        """Pre-flight: method='rotate' on any rotational sector is refused (preflight.refuse_rotate_on_sector)."""
        preflight.refuse_rotate_on_sector(self.model, center)

    def sector_mismatch(self) -> str | None:
        """Why a check that compares a torque with flux linkage / coenergy (dq formula, virtual work,
        analytic psi) cannot be put on one footing, or None when it can: a sector whose angle does
        not divide 360 (full-machine factor unknown), or weighted-stress-tensor torque on a 1/N
        sector (its full-machine scale is not measured)."""
        if self.sector_angle is None:
            return None
        if self.sector_n is None:
            return self.scale_unknown
        if not self.torque_from_gap:
            return "WST torque of a sector: full-machine scale not measured (use method='age' / gap_boundary)"
        return None

    @property
    def scale_unknown(self) -> str | None:
        """Reason text when the model is a sector whose angle does not divide 360 (no full-machine
        factor for flux linkage / coenergy), else None."""
        if self.sector_angle is None or self.sector_n:
            return None
        return (f"{self.sector_angle:.4g} deg sector does not divide 360: the full-machine factor of flux linkage "
                "and coenergy is unknown, so they cannot be put on the footing of the air-gap element torque or a "
                "full-machine estimate")

    @property
    def flux_scale(self) -> int:
        """Factor from as-drawn flux linkage / coenergy to full machine (1 unless a 1/N sector)."""
        return self.sector_n or 1

    # model facts
    @property
    def unit_m(self) -> float:
        return self.model.unit_to_m

    def circuit_names(self) -> list[str]:
        return [c.get("CircuitName") for c in self.model.circuits() if c.get("CircuitName")]

    def default_circuits(self) -> list[str]:
        """Circuits used when the caller names none: those with coil labels; skipped empty ones are
        listed in `warnings` (an empty circuit would read psi = 0 and L = 0)."""
        active = preflight.active_circuits(self.model)
        empty = [c for c in self.circuit_names() if c not in active]
        if empty:
            self.warnings.append(f"circuits {empty} have no coil labels (or zero turns) and were left out")
        return active

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
                self.left_solved = True
            except Exception as e:  # the experiment's numbers stand; the post-processor state does not
                self.left_solved = False
                self.warnings.append(f"final re-solve at the restored model failed ({type(e).__name__}: {e}); "
                                     "no solution is loaded: call femm_solve() before post-processing")
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
            "files": self.files, "warnings": self.warnings, "left_solved": self.left_solved,
            "timing": {"total_s": round(total, 3), "solves": self.ops.solves,
                       "per_solve_s": round(self.ops.solve_seconds / self.ops.solves, 4) if self.ops.solves else None},
        }
        if self.sector_n:
            out["full_machine"] = _jsonable(preflight.full_machine(self.name, out["summary"], self.sector_n,
                                                                   self.torque_from_gap, columns))
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
        raise ExperimentInputError(f"steps must be >= 1, got {steps}", "Pass steps >= 3 (the virtual-work check needs three points).")
    if steps == 1:
        return [float(start)]
    n = steps - 1 if endpoint else steps
    return [start + (stop - start) * k / n for k in range(steps)]


def _zero_currents(run: Run, circuits: Sequence[str]) -> None:
    for c in circuits:
        run.ops.set_current(c, 0)


def _restore_currents(run: Run) -> None:
    for name, i in run.circuit_currents().items():
        run.ops.set_current(name, i.real if i.imag == 0 else i)


def _named(check: dict, name: str) -> dict:
    check = dict(check)
    check["name"] = name
    return check
