"""Experiment pre-flight checks on a parsed model (pure, no FEMM): do the requested groups and
circuits exist, and is the model a symmetry sector?

An experiment that rotates or moves a group with no objects in it, or reads a circuit that is not
in the model, would otherwise run to the end and return numbers that look plausible (zero torque,
zero flux). These checks run before the first solve and raise with the list of what *is* there.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

# magnetics boundary types (mi_addboundprop BdryFormat): 4 periodic, 5 antiperiodic
PERIODIC_TYPES = (4, 5)


class PreflightError(ValueError):
    """Requested group/circuit absent; the envelope reports it as ok:false with `hint`."""

    tool_input = True

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint


def populated_groups(model: Any) -> list[int]:
    """Group numbers that hold at least one node, segment, arc or block label."""
    return [g for g, cnt in model.groups().items() if any(cnt.values())]


def require_groups(model: Any, groups: Iterable[int] | None, what: str = "groups") -> None:
    """Raise PreflightError naming the groups present when any requested group has no objects."""
    if groups is None:
        return
    want = [int(g) for g in groups]
    if not want:
        raise PreflightError(f"{what} is empty", f"Pass the group numbers of the moving parts; groups present: "
                                                 f"{populated_groups(model)}.")
    present = populated_groups(model)
    missing = [g for g in want if g not in present]
    if missing:
        raise PreflightError(
            f"no objects in group {missing} ({what}); groups present in the model: {present}",
            f"Use groups from {present} (femm_geometry_summary().groups shows what each holds), or tag the parts "
            "first with femm_set_group.")


def require_circuits(model: Any, circuits: Iterable[str] | None, what: str = "circuits") -> None:
    """Raise PreflightError naming the circuits present when a requested circuit is absent."""
    if circuits is None:
        return
    present = [c.get("CircuitName") for c in model.circuits() if c.get("CircuitName")]
    missing = [c for c in circuits if c not in present]
    if missing:
        raise PreflightError(
            f"circuit not in the model: {missing} ({what}); circuits present: {present}",
            (f"Use circuits from {present}, or create the missing one with femm_add_circuit."
             if present else "The model has no circuits: add one with femm_add_circuit(name=...), then "
                             "femm_set_block_prop(x=, y=, material=, circuit=<name>, turns=<N>)."))


def _angle_span(angles: Sequence[float]) -> float:
    """Smallest arc (deg) containing all `angles` (deg, any range)."""
    a = sorted(x % 360.0 for x in angles)
    if len(a) < 2:
        return 0.0
    gaps = [(a[(i + 1) % len(a)] - a[i]) % 360.0 for i in range(len(a))]
    return 360.0 - max(gaps)


def sector_extent_deg(model: Any, center: Sequence[float] = (0.0, 0.0)) -> float | None:
    """Angular extent (deg) of a rotational sector, read from the nodes of segments that carry a
    periodic / antiperiodic boundary (the two radial cut lines). None when the model has no such
    segments, i.e. no evidence of a sector (a full model, or a sector built another way)."""
    names = [b.get("BdryName") for b in model.boundaries()]
    types = [int(b.get("BdryType", 0) or 0) for b in model.boundaries()]
    pts = model.points()
    cx, cy = float(center[0]), float(center[1])
    angles: list[float] = []
    for r in model.geometry.get("NumSegments", []):
        if len(r) <= 3:
            continue
        bi = int(r[3])
        if not (0 < bi <= len(names)) or types[bi - 1] not in PERIODIC_TYPES:
            continue
        for ni in (int(r[0]), int(r[1])):
            if 0 <= ni < len(pts):
                x, y = pts[ni][0] - cx, pts[ni][1] - cy
                if math.hypot(x, y) > 1e-9:
                    angles.append(math.degrees(math.atan2(y, x)))
    if len(angles) < 2:
        return None
    span = _angle_span(angles)
    return span if 1.0 < span < 359.0 else None


def sector_warnings(model: Any, center: Sequence[float] = (0.0, 0.0), slots: int | None = None,
                    poles: int | None = None) -> list[str]:
    """Warnings when the model is a sector but the experiment is described by full-machine counts:
    the FEM torque / flux linkage are for the sector as drawn (scale by 360/extent unless the
    circuits already hold the full-machine turns), and Q, 2p must be whole numbers per sector."""
    ext = sector_extent_deg(model, center)
    if ext is None:
        return []
    k = 360.0 / ext
    out = [f"model is a {ext:.4g} deg sector (periodic/antiperiodic boundaries found): torque and flux linkage are "
           f"for the sector as drawn; multiply by {k:.4g} for the full machine unless the circuit turns already "
           "represent the full machine."]
    for label, n in (("slots", slots), ("poles", poles)):
        if n:
            per = n / k
            if abs(per - round(per)) > 1e-6 or round(per) == 0:
                out.append(f"{label}={n} gives {per:.3g} per {ext:.4g} deg sector (not a whole number): pass the "
                           f"full-machine {label} count, or check the sector angle.")
    return out
