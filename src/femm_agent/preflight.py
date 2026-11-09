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


def labelled_groups(model: Any) -> list[int]:
    """Group numbers that hold at least one block label (what block integrals select by)."""
    return [g for g, cnt in model.groups().items() if cnt.get("labels")]


def require_groups(model: Any, groups: Iterable[int] | None, what: str = "groups", need_labels: bool = False) -> None:
    """Raise PreflightError naming the groups present when any requested group has no objects.

    `need_labels` (torque_groups / force_groups): the group must hold a block label, because the
    weighted-stress-tensor integrals select blocks by the group of their label; geometry alone in
    the group (enough to move or rotate it) would integrate nothing."""
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
    if need_labels:
        lab = labelled_groups(model)
        unlabelled = [g for g in want if g not in lab]
        if unlabelled:
            raise PreflightError(
                f"no block label in group {unlabelled} ({what}): the force/torque integral selects blocks by the "
                f"group of their label and would integrate nothing; groups with labels: {lab}",
                "Put the block labels of the part in the group too: femm_select(kind='labels', points=[[x, y]]) "
                "then femm_set_group(n), or femm_set_block_prop(x, y, ..., group=n).")


def circuit_turns(model: Any) -> dict[str, float]:
    """Circuit name -> sum of |turns| over the block labels assigned to it (0 = no coil labels)."""
    out = {c.get("CircuitName"): 0.0 for c in model.circuits() if c.get("CircuitName")}
    for lab in model.block_labels():
        c = lab.get("circuit")
        if c in out:
            out[c] += abs(float(lab.get("turns", 1.0) or 0.0))
    return out


def active_circuits(model: Any) -> list[str]:
    """Circuits that have at least one block label with non-zero turns."""
    return [c for c, n in circuit_turns(model).items() if n > 0]


def require_circuits(model: Any, circuits: Iterable[str] | None, what: str = "circuits") -> None:
    """Raise PreflightError naming the circuits present when a requested circuit is absent, or
    holds no coil labels (a defined circuit without labels reads psi = 0 and L = 0; FEMM 5 also
    drops the label links when a circuit is renamed with mi_modifycircprop)."""
    if circuits is None:
        return
    turns = circuit_turns(model)
    present = list(turns)
    missing = [c for c in circuits if c not in turns]
    if missing:
        raise PreflightError(
            f"circuit not in the model: {missing} ({what}); circuits present: {present}",
            (f"Use circuits from {present}, or create the missing one with femm_add_circuit."
             if present else "The model has no circuits: add one with femm_add_circuit(name=...), then "
                             "femm_set_block_prop(x=, y=, material=, circuit=<name>, turns=<N>)."))
    empty = [c for c in circuits if turns.get(c, 0) <= 0]
    if empty:
        raise PreflightError(
            f"circuit {empty} ({what}) has no coil labels (or zero turns): its flux linkage and inductance "
            f"would read 0; circuits with coil labels: {active_circuits(model)}",
            "Assign coil labels with femm_set_block_prop(x, y, material, circuit=<name>, turns=<N>) (after renaming "
            "a circuit, re-assign its labels), then retry.")


def _angle_span(angles: Sequence[float]) -> float:
    """Smallest arc (deg) containing all `angles` (deg, any range)."""
    a = sorted(x % 360.0 for x in angles)
    if len(a) < 2:
        return 0.0
    gaps = [(a[(i + 1) % len(a)] - a[i]) % 360.0 for i in range(len(a))]
    return 360.0 - max(gaps)


RAY_TOL_DEG = 0.5


def sector_extent_deg(model: Any, center: Sequence[float] = (0.0, 0.0)) -> float | None:
    """Angular extent (deg) of a rotational sector, read from the nodes of segments that carry a
    periodic / antiperiodic boundary (the two radial cut lines). None when there are no such
    segments, or when one of them is not radial (its two end points must lie on one ray through
    `center` within RAY_TOL_DEG; the periodic left/right edges of a linear model do not), i.e. no
    evidence of a rotational sector."""
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
        seg = []
        for ni in (int(r[0]), int(r[1])):
            if 0 <= ni < len(pts):
                x, y = pts[ni][0] - cx, pts[ni][1] - cy
                if math.hypot(x, y) > 1e-9:          # a node at the centre lies on every ray
                    seg.append(math.degrees(math.atan2(y, x)))
        if len(seg) == 2 and abs((seg[0] - seg[1] + 180.0) % 360.0 - 180.0) > RAY_TOL_DEG:
            return None                              # a periodic segment that is not radial: not a sector
        angles.extend(seg)
    if len(angles) < 2:
        return None
    span = _angle_span(angles)
    return span if 1.0 < span < 359.0 else None


SCALE_RULE = ("sector model, N = 360 / sector angle. Measured on FEMM 5 build 20261101 (12-slot 4-pole SPM, "
              "N = 2 and 4) against the full machine: flux linkage, EMF, Ke, coenergy, energy, circuit resistance "
              "(DC and 50 Hz) and coil resistive loss of the series circuits x N within 0.05 %, inductance x N "
              "within 0.12 %; air-gap element torque (mo_gapintegral) is already the full-machine torque (x 1, "
              "within 0.05 %); flux density, currents and angles x 1. Iron (hysteresis / eddy) losses: x N "
              "expected (integral over the drawn blocks), unmeasured")

# summary keys per experiment that scale with N ("flux") or follow the torque source ("torque")
_SCALED = {
    "back_emf": {"flux": ("psi_fundamental_Wb", "emf_fundamental_peak_V", "emf_fundamental_rms_V", "ke_V_per_rad_s",
                          "emf_line_line_peak_V", "emf_line_line_fundamental_V", "harmonics_phase1"), "torque": ()},
    "cogging": {"flux": (), "torque": ("peak_to_peak_Nm", "rms_Nm", "harmonics")},
    "torque_vs_angle": {"flux": (), "torque": ("mean_torque_Nm", "max_torque_Nm", "min_torque_Nm", "peak_to_peak_Nm")},
    "inductance": {"flux": ("L_matrix_H", "self_H", "psi_pm_Wb", "Ld_H", "Lq_H", "L_secant_H", "L_incremental_H",
                            "psi_at_zero_Wb"),
                   "torque": ("torque_fem_at_iq_Nm", "torque_fem_at_id_iq_Nm"),
                   "full": ("torque_dq_at_iq_Nm", "torque_dq_at_id_iq_Nm", "saliency_Lq_over_Ld")},
    "ac_sweep": {"flux": ("R_ohm", "L_H"), "torque": ()},
}


def sector_factor(model: Any, center: Sequence[float] = (0.0, 0.0)) -> tuple[float | None, int | None]:
    """(sector angle in deg, N) for a rotational sector whose angle divides 360; (angle, None) when it
    does not divide 360; (None, None) for no sector."""
    ext = sector_extent_deg(model, center)
    if ext is None:
        return None, None
    n = 360.0 / ext
    return ext, (int(round(n)) if abs(n - round(n)) < 1e-3 and round(n) >= 2 else None)


def _scale(v: Any, k: float) -> Any:
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return v * k
    if isinstance(v, dict):
        return {a: (_scale(b, k) if a not in ("order", "order_per_period", "order_per_rev") else b) for a, b in v.items()}
    if isinstance(v, (list, tuple)):
        return [_scale(x, k) for x in v]
    return v


def full_machine(experiment: str, summary: dict, n: int, torque_from_gap: bool) -> dict:
    """Full-machine values of a sector experiment (pure): the `flux` keys of `summary` times N, the
    `torque` keys times 1 when the torque comes from the air-gap element (already full machine),
    omitted otherwise (weighted-stress-tensor torque of a sector: scale not measured); `full` keys
    (dq torques computed from N x psi) as they are."""
    keys = _SCALED.get(experiment, {"flux": (), "torque": ()})
    vals = {k: _scale(summary[k], n) for k in keys["flux"] if k in summary}
    vals.update({k: summary[k] for k in keys.get("full", ()) if k in summary})   # computed full-machine already
    note = ["torque columns in rows (air-gap element, virtual work x N, dq from N x psi) are full-machine"
            if torque_from_gap else "rows are as drawn"]
    if torque_from_gap:
        vals.update({k: summary[k] for k in keys["torque"] if k in summary})
    elif keys["torque"]:
        note.append("torque from the weighted stress tensor of a sector: full-machine scale not measured, not given")
    return {"factor": int(n), "rule": SCALE_RULE, "summary": vals, "notes": note}


def sector_warnings(model: Any, center: Sequence[float] = (0.0, 0.0), slots: int | None = None,
                    poles: int | None = None, method: str | None = None) -> list[str]:
    """Warnings for a sector model: what the as-drawn numbers mean (see SCALE_RULE; the experiments
    add a `full_machine` block), that the rotate route cannot work on one, and that Q, 2p must be
    whole numbers per sector (they are full-machine counts)."""
    ext, n = sector_factor(model, center)
    if ext is None:
        return []
    k = 360.0 / ext
    if n:
        out = [f"model is a {ext:.4g} deg sector (1/{n} of the machine): rows and summary are as drawn; flux linkage, "
               f"EMF, inductance, coenergy, resistance and copper loss are x {n} for the full machine (measured), "
               "iron losses x N expected but unmeasured, air-gap element torque is "
               "already full-machine; `full_machine` holds the scaled values."]
    else:
        out = [f"model is a {ext:.4g} deg sector, which does not divide 360: no full-machine values are given."]
    if method == "rotate":
        out.append("rotate-and-remesh on a sector turns the rotor's periodic cut lines off the stator's: use "
                   "method='age' with an (anti)periodic air-gap element.")
    for label, cnt in (("slots", slots), ("poles", poles)):
        if cnt:
            per = cnt / k
            if abs(per - round(per)) > 1e-6 or round(per) == 0:
                out.append(f"{label}={cnt} gives {per:.3g} per {ext:.4g} deg sector (not a whole number): pass the "
                           f"full-machine {label} count, or check the sector angle.")
    return out
