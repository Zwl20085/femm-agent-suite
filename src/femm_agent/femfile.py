"""Parse FEMM's text model files (.fem/.fee/.feh/.fec) and solution files (.ans/.res/.anh/.anc).

Format reference: the "FEMM <physics> File Formats" PDFs shipped with FEMM 5 (docs/formats).
Layout: ``[Tag] = value`` header lines, property collections ``[BdryProps] = n`` followed by
``<BeginBdry> <Key> = value ... <EndBdry>`` blocks (B-H points follow ``<BHPoints> = n``), geometry
tables ``[NumPoints] = n`` followed by n rows, and for solutions a ``[Solution]`` section with node,
element and circuit/conductor tables. Property indices in geometry rows are 1-based (0 = none);
node indices are 0-based. Pure Python (numpy only for the solution arrays).

Usage::

    m = parse_file("motor.fem");  m.summary()      # JSON-able dict
    s = parse_file("motor.ans");  s.nodes(), s.elements(), s.element_labels()
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .units import LENGTH_TO_M

_HDR = re.compile(r"^\[(\w+)\]\s*=\s*(.*)$")
_KV = re.compile(r"<(\w+)>\s*=\s*(\"[^\"]*\"|[^\s<]+)")
_TOK = re.compile(r'"[^"]*"|\S+')

EXT_PHYSICS = {".fem": "magnetics", ".ans": "magnetics", ".fee": "electrostatics", ".res": "electrostatics",
               ".feh": "heatflow", ".anh": "heatflow", ".fec": "currentflow", ".anc": "currentflow"}
SOLUTION_EXT = {".ans", ".res", ".anh", ".anc"}
MODEL_FOR_SOLUTION = {".ans": ".fem", ".res": ".fee", ".anh": ".feh", ".anc": ".fec"}
SOLUTION_FOR_MODEL = {v: k for k, v in MODEL_FOR_SOLUTION.items()}

MAG_BDRY_TYPES = {0: "prescribed A", 1: "small skin depth", 2: "mixed", 3: "strategic dual image",
                  4: "periodic", 5: "antiperiodic", 6: "periodic air gap", 7: "antiperiodic air gap"}
ES_BDRY_TYPES = {0: "fixed voltage", 1: "mixed", 2: "surface charge", 3: "periodic", 4: "antiperiodic"}
HEAT_BDRY_TYPES = {0: "fixed temperature", 1: "heat flux", 2: "convection", 3: "radiation",
                   4: "periodic", 5: "antiperiodic"}
CF_BDRY_TYPES = {0: "fixed voltage", 1: "mixed", 2: "surface current density", 3: "periodic", 4: "antiperiodic"}
BDRY_TYPES = {"magnetics": MAG_BDRY_TYPES, "electrostatics": ES_BDRY_TYPES, "heatflow": HEAT_BDRY_TYPES,
              "currentflow": CF_BDRY_TYPES}

GEOMETRY_TAGS = ("NumPoints", "NumSegments", "NumArcSegments", "NumHoles", "NumBlockLabels")
_CURVE_KEYS = {"bhpoints", "tkpoints"}


def _value(s: str) -> Any:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    try:
        if re.fullmatch(r"[+-]?\d+", s):
            return int(s)
        return float(s)
    except ValueError:
        return s


def _row(line: str) -> list[Any]:
    return [_value(t) for t in _TOK.findall(line)]


@dataclass
class FemmFile:
    """Parsed FEMM file. ``header`` holds the ``[Tag]`` scalars; ``props`` the property collections
    (``props['BlockProps']`` is a list of dicts); ``geometry`` the raw rows; ``solution`` the raw
    solution tables (solution files only)."""

    path: str | None
    physics: str
    header: dict[str, Any] = field(default_factory=dict)
    props: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    geometry: dict[str, list[list[Any]]] = field(default_factory=dict)
    solution: dict[str, Any] | None = None

    # ------------------------------------------------------------------ convenience
    @property
    def units(self) -> str:
        return str(self.header.get("LengthUnits", "millimeters")).lower()

    @property
    def unit_to_m(self) -> float:
        return LENGTH_TO_M.get(self.units, 1e-3)

    @property
    def problem_type(self) -> str:
        p = str(self.header.get("ProblemType", "planar")).lower()
        return "axisymmetric" if p.startswith("axi") else "planar"

    @property
    def frequency(self) -> float:
        return float(self.header.get("Frequency", 0) or 0)

    def materials(self) -> list[dict[str, Any]]:
        return self.props.get("BlockProps", [])

    def boundaries(self) -> list[dict[str, Any]]:
        return self.props.get("BdryProps", [])

    def circuits(self) -> list[dict[str, Any]]:
        return self.props.get("CircuitProps", []) or self.props.get("ConductorProps", [])

    def block_labels(self) -> list[dict[str, Any]]:
        """Block labels as dicts with resolved material/circuit names (1-based indices resolved)."""
        mats = self.materials()
        circs = self.circuits()
        out = []
        for r in self.geometry.get("NumBlockLabels", []):
            d: dict[str, Any] = {"x": float(r[0]), "y": float(r[1])}
            bi = int(r[2]) if len(r) > 2 else 0
            d["material"] = mats[bi - 1].get("BlockName") if 0 < bi <= len(mats) else ("<No Mesh>" if bi < 0 else None)
            d["mesh_size"] = float(r[3]) if len(r) > 3 else 0.0
            if self.physics == "magnetics":
                ci = int(r[4]) if len(r) > 4 else 0
                d["circuit"] = circs[ci - 1].get("CircuitName") if 0 < ci <= len(circs) else None
                d["magdir"] = float(r[5]) if len(r) > 5 and not isinstance(r[5], str) else 0.0
                d["group"] = int(r[6]) if len(r) > 6 else 0
                d["turns"] = float(r[7]) if len(r) > 7 else 1.0
                ext = int(r[8]) if len(r) > 8 and not isinstance(r[8], str) else 0
                if len(r) > 9 and isinstance(r[9], str):
                    d["magdir_formula"] = r[9]
            else:
                d["group"] = int(r[4]) if len(r) > 4 else 0
                ext = int(r[5]) if len(r) > 5 and not isinstance(r[5], str) else 0
            d["external"] = bool(ext & 1)
            d["default"] = bool(ext & 2)
            out.append(d)
        return out

    def points(self):
        return [(float(r[0]), float(r[1])) for r in self.geometry.get("NumPoints", [])]

    def bounding_box(self) -> dict[str, float] | None:
        """Extents of nodes and arcs (arc bulges included), in problem units."""
        pts = self.points()
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        for r in self.geometry.get("NumArcSegments", []):
            try:
                n0, n1, ang = int(r[0]), int(r[1]), float(r[2])
                for x, y in _arc_samples(pts[n0], pts[n1], ang, 16):
                    xs.append(x)
                    ys.append(y)
            except (IndexError, ValueError, ZeroDivisionError):
                continue
        return {"xmin": min(xs), "xmax": max(xs), "ymin": min(ys), "ymax": max(ys)}

    def groups(self) -> dict[int, dict[str, int]]:
        """Group number -> counts of entities in it."""
        g: dict[int, dict[str, int]] = {}

        def bump(n, kind):
            g.setdefault(int(n), {"nodes": 0, "segments": 0, "arcs": 0, "labels": 0})[kind] += 1

        for r in self.geometry.get("NumPoints", []):
            if len(r) > 3:
                bump(r[3], "nodes")
        for r in self.geometry.get("NumSegments", []):
            if len(r) > 5:
                bump(r[5], "segments")
        for r in self.geometry.get("NumArcSegments", []):
            if len(r) > 6:
                bump(r[6], "arcs")
        for lab in self.block_labels():
            bump(lab["group"], "labels")
        return dict(sorted(g.items()))

    # ------------------------------------------------------------------ summary
    def summary(self) -> dict[str, Any]:
        """JSON-able overview: problem definition, materials used, boundaries, circuits, counts, bbox."""
        labels = self.block_labels()
        use: dict[str, int] = {}
        for lab in labels:
            if lab["material"]:
                use[lab["material"]] = use.get(lab["material"], 0) + 1
        mats = []
        for m in self.materials():
            name = m.get("BlockName")
            d = {"name": name, "labels": use.get(name, 0)}
            if self.physics == "magnetics":
                d.update({"mu_x": m.get("Mu_x"), "mu_y": m.get("Mu_y"), "Hc_A_per_m": m.get("H_c"),
                          "J_MA_per_m2": m.get("J_re"), "sigma_MS_per_m": m.get("Sigma"),
                          "lam_type": m.get("LamType"), "bh_points": len(m.get("BHPoints_data", []))})
                d["nonlinear"] = d["bh_points"] > 0
                d["magnet"] = float(m.get("H_c") or 0) > 0
            elif self.physics == "electrostatics":
                d.update({"eps_x": m.get("ex"), "eps_y": m.get("ey"), "qv": m.get("qv")})
            elif self.physics == "heatflow":
                d.update({"kx": m.get("Kx"), "ky": m.get("Ky"), "qv": m.get("qv"),
                          "tk_points": len(m.get("TKPoints_data", []))})
            else:
                d.update({k: m.get(k) for k in m if k not in ("BlockName",)})
            mats.append(d)
        btypes = BDRY_TYPES.get(self.physics, {})
        bdry_use = self._boundary_use()
        bdrys = []
        for b in self.boundaries():
            t = int(b.get("BdryType", 0) or 0)
            bd = {"name": b.get("BdryName"), "type": t, "type_name": btypes.get(t, str(t)),
                  "segments": bdry_use.get(b.get("BdryName"), 0)}
            if self.physics == "magnetics" and t in (6, 7):
                bd["inner_angle"] = b.get("innerangle")
                bd["outer_angle"] = b.get("outerangle")
            bdrys.append(bd)
        circs = []
        for c in self.circuits():
            if "CircuitName" in c:
                ctype = int(c.get("CircuitType", 0) or 0)
                circs.append({"name": c.get("CircuitName"), "current_re": c.get("TotalAmps_re"),
                              "current_im": c.get("TotalAmps_im"), "type": ctype,
                              "type_name": "series" if ctype == 1 else "parallel",
                              "labels": sum(1 for lab in labels if lab.get("circuit") == c.get("CircuitName")),
                              "turns": sum(lab.get("turns", 0) for lab in labels if lab.get("circuit") == c.get("CircuitName"))})
            else:
                circs.append({k: v for k, v in c.items()})
        problem = {k: self.header[k] for k in ("Format", "Frequency", "Precision", "MinAngle", "DoSmartMesh", "Depth",
                                                "LengthUnits", "ProblemType", "Coordinates", "ACSolver", "PrevType",
                                                "PrevSoln", "Comment", "dT") if k in self.header}
        out = {
            "path": self.path, "physics": self.physics, "problem": problem,
            "units_to_m": self.unit_to_m, "problem_type": self.problem_type,
            "counts": {"points": len(self.geometry.get("NumPoints", [])),
                       "segments": len(self.geometry.get("NumSegments", [])),
                       "arcs": len(self.geometry.get("NumArcSegments", [])),
                       "holes": len(self.geometry.get("NumHoles", [])),
                       "block_labels": len(labels)},
            "materials": mats, "materials_used": sorted(use), "boundaries": bdrys, "circuits": circs,
            "groups": {str(k): v for k, v in self.groups().items()},
            "bounding_box": self.bounding_box(),
            "unlabelled_materials": [m["name"] for m in mats if m["labels"] == 0],
            "magnets": [{"x": lab["x"], "y": lab["y"], "material": lab["material"], "magdir": lab.get("magdir"),
                         "group": lab["group"]}
                        for lab in labels if any(m["name"] == lab["material"] and m.get("magnet") for m in mats)],
        }
        if self.solution is not None:
            out["solution"] = {"nodes": len(self.solution.get("nodes", [])),
                               "elements": len(self.solution.get("elements", [])),
                               "circuit_rows": len(self.solution.get("circuits", [])),
                               "air_gap_elements": [a.get("name") for a in self.solution.get("ages", [])]}
        return out

    def _boundary_use(self) -> dict[str, int]:
        names = [b.get("BdryName") for b in self.boundaries()]
        cnt: dict[str, int] = {}
        for r in self.geometry.get("NumSegments", []):
            if len(r) > 3 and 0 < int(r[3]) <= len(names):
                cnt[names[int(r[3]) - 1]] = cnt.get(names[int(r[3]) - 1], 0) + 1
        for r in self.geometry.get("NumArcSegments", []):
            if len(r) > 4 and 0 < int(r[4]) <= len(names):
                cnt[names[int(r[4]) - 1]] = cnt.get(names[int(r[4]) - 1], 0) + 1
        return cnt

    # ------------------------------------------------------------------ solution arrays
    def _need_solution(self):
        if self.solution is None:
            raise ValueError("not a solution file (.ans/.res/.anh/.anc)")
        return self.solution

    def nodes(self):
        """(N, k) float array of solution node rows: x, y, then potential(s) (A_re[, A_im] for magnetics,
        V for electrostatics, T for heat, V_re V_im for current flow), then markers."""
        import numpy as np

        return np.asarray(self._need_solution()["nodes"], dtype=float)

    def elements(self):
        """(M, k) int array: p0 p1 p2 (0-based nodes), label index (0-based), [edge bc x3, ...]."""
        import numpy as np

        rows = self._need_solution()["elements"]
        w = min(len(r) for r in rows) if rows else 4
        return np.asarray([r[:w] for r in rows], dtype=float).astype(int)

    def element_labels(self):
        """0-based block-label index of every element (column 3)."""
        return self.elements()[:, 3]

    def element_materials(self) -> list[str | None]:
        labs = self.block_labels()
        return [labs[i]["material"] if 0 <= i < len(labs) else None for i in self.element_labels()]

    def element_b_planar(self):
        """Element-constant B (T) from nodal A for a planar magnetics solution: Bx = dA/dy, By = -dA/dx
        (coordinates converted to metres). Returns (M, 2) array (real part for AC)."""
        import numpy as np

        if self.physics != "magnetics" or self.problem_type != "planar":
            raise ValueError("element_b_planar needs a planar magnetics solution")
        nd = self.nodes()
        el = self.elements()
        xy = nd[:, :2] * self.unit_to_m
        a = nd[:, 2]
        p0, p1, p2 = el[:, 0], el[:, 1], el[:, 2]
        x0, y0 = xy[p0, 0], xy[p0, 1]
        x1, y1 = xy[p1, 0], xy[p1, 1]
        x2, y2 = xy[p2, 0], xy[p2, 1]
        det = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        dadx = ((a[p1] - a[p0]) * (y2 - y0) - (a[p2] - a[p0]) * (y1 - y0)) / det
        dady = ((a[p2] - a[p0]) * (x1 - x0) - (a[p1] - a[p0]) * (x2 - x0)) / det
        return np.column_stack([dady, -dadx])

    def element_areas(self):
        """Element areas in (problem units)^2."""
        import numpy as np

        nd = self.nodes()
        el = self.elements()
        p = nd[:, :2]
        a, b, c = p[el[:, 0]], p[el[:, 1]], p[el[:, 2]]
        return 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))


def _arc_samples(p0, p1, angle_deg: float, n: int = 16):
    """Points along a FEMM arc from p0 to p1 sweeping ``angle_deg`` counter-clockwise."""
    th = math.radians(angle_deg)
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    chord = math.hypot(dx, dy)
    if chord == 0 or th == 0:
        return [p0, p1]
    r = chord / (2 * math.sin(th / 2))
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    h = r * math.cos(th / 2)
    # centre lies to the left of the chord direction for a CCW arc
    cx, cy = mx - h * dy / chord, my + h * dx / chord
    a0 = math.atan2(p0[1] - cy, p0[0] - cx)
    return [(cx + r * math.cos(a0 + th * k / n), cy + r * math.sin(a0 + th * k / n)) for k in range(n + 1)]


def arc_center(p0, p1, angle_deg: float) -> tuple[float, float, float]:
    """(cx, cy, r) of the CCW arc from p0 to p1 spanning ``angle_deg``."""
    th = math.radians(angle_deg)
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    chord = math.hypot(dx, dy)
    r = chord / (2 * math.sin(th / 2))
    h = r * math.cos(th / 2)
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    return mx - h * dy / chord, my + h * dx / chord, r


# ----------------------------------------------------------------------------- parsing

def _detect_physics(header: dict, props: dict, ext: str | None) -> str:
    if ext and ext.lower() in EXT_PHYSICS:
        return EXT_PHYSICS[ext.lower()]
    blocks = props.get("BlockProps", [])
    keys = {k.lower() for b in blocks for k in b}
    if "mu_x" in keys or "CircuitProps" in props:
        return "magnetics"
    if "kx" in keys:
        return "heatflow"
    if "ox" in keys:
        return "currentflow"
    if "ex" in keys:
        return "electrostatics"
    return "magnetics"


def parse_text(text: str, path: str | None = None, ext: str | None = None) -> FemmFile:
    """Parse the contents of any FEMM model or solution file."""
    lines = text.splitlines()
    n = len(lines)
    i = 0
    header: dict[str, Any] = {}
    props: dict[str, list[dict[str, Any]]] = {}
    geometry: dict[str, list[list[Any]]] = {}
    solution: dict[str, Any] | None = None
    while i < n:
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        if line.lower().startswith("[solution]"):
            solution, i = _parse_solution(lines, i, ext)
            continue
        if line.lower().startswith("[agerings]"):
            continue
        m = _HDR.match(line)
        if not m:
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag in GEOMETRY_TAGS:
            cnt = int(float(val or 0))
            rows = []
            while len(rows) < cnt and i < n:
                s = lines[i].strip()
                i += 1
                if s:
                    rows.append(_row(s))
            geometry[tag] = rows
        elif tag.endswith("Props"):
            items: list[dict[str, Any]] = []
            cur: dict[str, Any] | None = None
            while i < n:
                s = lines[i].strip()
                if s.startswith("["):
                    break
                i += 1
                if not s:
                    continue
                low = s.lower()
                if low.startswith("<begin"):
                    cur = {}
                    s = s[s.index(">") + 1:]
                if cur is None:
                    continue
                if low.startswith("<end"):
                    items.append(cur)
                    cur = None
                    continue
                for k, v in _KV.findall(s):
                    cur[k] = _value(v)
                    if k.lower() in _CURVE_KEYS:
                        npts = int(float(v))
                        pts = []
                        while len(pts) < npts and i < n:
                            t = lines[i].strip()
                            i += 1
                            if t:
                                pts.append([float(x) for x in t.split()[:2]])
                        cur[k + "_data"] = pts
            props[tag] = items
            header[tag] = len(items)
        else:
            header[tag] = _value(val)
    phys = _detect_physics(header, props, ext)
    return FemmFile(path=path, physics=phys, header=header, props=props, geometry=geometry, solution=solution)


def _parse_solution(lines: list[str], i: int, ext: str | None) -> tuple[dict[str, Any], int]:
    n = len(lines)

    def next_nonempty(j):
        while j < n and not lines[j].strip():
            j += 1
        return j

    def table(j):
        j = next_nonempty(j)
        if j >= n:
            return [], j
        try:
            cnt = int(float(lines[j].split()[0]))
        except (ValueError, IndexError):
            return [], j
        j += 1
        rows = []
        while len(rows) < cnt and j < n:
            s = lines[j].strip()
            j += 1
            if s:
                rows.append([float(x) if not x.startswith('"') else x for x in _TOK.findall(s)])
        return rows, j

    sol: dict[str, Any] = {}
    sol["nodes"], i = table(i)
    sol["elements"], i = table(i)
    sol["circuits"], i = table(i)
    if (ext or ".ans").lower() == ".ans":
        try:
            sol["pbcs"], i = table(i)
            j = next_nonempty(i)
            ages = []
            if j < n and lines[j].strip() and not lines[j].strip().startswith("["):
                cnt = int(float(lines[j].split()[0]))
                j += 1
                for _ in range(cnt):
                    j = next_nonempty(j)
                    name = lines[j].strip().strip('"')
                    j += 1
                    j = next_nonempty(j)
                    par = [float(x) for x in lines[j].split()]
                    j += 1
                    narc = int(par[8]) if len(par) > 8 else 0
                    ages.append({"name": name, "format": int(par[0]), "inner_angle": par[1], "outer_angle": par[2],
                                 "ri": par[3], "ro": par[4], "total_arc": par[5], "n_arc_elements": narc})
                    k = 0
                    while k < narc + 1 and j < n:
                        if lines[j].strip():
                            k += 1
                        j += 1
                i = j
            sol["ages"] = ages
        except (ValueError, IndexError):
            sol.setdefault("ages", [])
    return sol, n


def parse_file(path: str | Path) -> FemmFile:
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    return parse_text(text, path=str(p), ext=p.suffix)


def summarize_file(path: str | Path) -> dict[str, Any]:
    return parse_file(path).summary()


def solution_path(model_path: str | Path) -> Path:
    """``motor.fem -> motor.ans`` (and .fee -> .res, .feh -> .anh, .fec -> .anc)."""
    p = Path(model_path)
    return p.with_suffix(SOLUTION_FOR_MODEL.get(p.suffix.lower(), ".ans"))
