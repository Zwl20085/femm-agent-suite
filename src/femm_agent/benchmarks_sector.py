"""Symmetry-sector variant of the SPM benchmark: 1/N of the machine of :func:`benchmarks.build_spm`
with the same dimensions, materials, winding and rotor orientation.

The sector spans [0, 360/N] deg. Its two radial cut lines carry one periodic (or antiperiodic)
boundary per crossed region - rotor iron, magnet, rotor-side air, stator-side air, stator iron;
the air-gap element annulus is unmeshed - and the gap is a FEMM 5 (anti)periodic air-gap element
(``AGE``, BdryFormat 6 / 7) spanning the sector. Periodic when the sector holds an even number of
poles, antiperiodic when odd.

Only the air-gap element route works on a sector: rotate-and-remesh turns the rotor's radial
edges off the stator's cut lines, so the periodic pairs no longer match. Rotate with
``mi_modifyboundprop("AGE", 10, angle)`` (what the experiments' ``method="age"`` does).

Every series circuit holds the coils of this sector only. Measured scale rule (docs/femm5-facts.md,
"Sector models", preflight.SCALE_RULE): flux linkage, EMF, coenergy, energy, circuit resistance and
coil resistive loss of the full machine are N x the sector value (within 0.05 %), inductance N x
(within 0.12 %); the air-gap element torque of the sector already is the full-machine torque;
currents, flux densities and angles (periods) are the same. Iron losses: N x expected, unmeasured.
"""
from __future__ import annotations

import math
from typing import Any

from . import estimate


class SectorError(ValueError):
    """The requested sector does not divide the machine; reported as an input error."""

    tool_input = True

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint


def sector_kind(slots: int, poles: int, sector: int, phases: list[tuple[str, int]]) -> str:
    """'periodic' or 'antiperiodic' for 1/`sector` of the machine; raises SectorError when the slot
    count, the pole count or the winding does not repeat over 360/sector degrees."""
    n = int(sector)
    if n < 2:
        raise SectorError(f"sector must be >= 2 (1/N of the machine), got {sector}")
    if slots % n or poles % n:
        raise SectorError(f"sector={n} does not divide slots={slots} and poles={poles}",
                          f"Use a common divisor of slots and poles, e.g. {math.gcd(slots, poles)} or one of its "
                          "divisors.")
    m = poles // n                                   # poles per sector
    sign = 1 if m % 2 == 0 else -1
    q = slots // n
    for k in range(slots - q):
        ph, s = phases[k]
        ph2, s2 = phases[k + q]
        if ph2 != ph or s2 != sign * s:
            raise SectorError(f"the winding does not repeat over 360/{n} deg (slot {k} {ph}{s:+d} vs slot {k + q} "
                              f"{ph2}{s2:+d})", "Use a smaller sector (a divisor of the machine periodicity).")
    return "periodic" if sign > 0 else "antiperiodic"


def _pol(r: float, deg: float) -> tuple[float, float]:
    t = math.radians(deg)
    return r * math.cos(t), r * math.sin(t)


def build_spm_sector(link, path: str, *, sector: int, slots: int, p: int, rotor_r: float, magnet_t: float,
                     gap: float, stator_or: float, slot_open: float, tip_h: float, slot_w: float, slot_depth: float,
                     depth: float, turns_per_slot: int, steel: str, magnet: str, mesh_gap: float, mesh_magnet: float,
                     mesh_iron: float, mesh_coil: float, smartmesh: bool, precision: float,
                     helpers: Any) -> dict[str, Any]:
    """Draw and save 1/`sector` of the SPM machine (called by build_spm(sector=N)). `helpers` is the
    benchmarks module (drawing helpers and spm_slot_phases)."""
    poles = 2 * p
    pitch = 360.0 / slots
    offset = pitch / 2.0
    phases = helpers.spm_slot_phases(slots, p, offset)
    kind = sector_kind(slots, poles, sector, phases)
    per = kind == "periodic"
    alpha = 360.0 / sector
    q = slots // sector
    m = poles // sector
    Rm = rotor_r + magnet_t
    Rs = Rm + gap
    Ri, Ro = Rm + gap * 0.4, Rm + gap * 0.6
    call = link.call
    call("newdocument", 0)
    call("mi_probdef", 0, "millimeters", "planar", precision, depth, 30)
    call("mi_smartmesh", 1 if smartmesh else 0)
    for mat in ("Air", "Copper", steel, magnet):
        call("mi_getmaterial", mat)
    call("mi_addboundprop", "A=0", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    call("mi_addboundprop", "AGE", 0, 0, 0, 0, 0, 0, 0, 0, 6 if per else 7, 0, 0)
    for ph in ("A", "B", "C"):
        call("mi_addcircprop", ph, 0, 1)

    # ---- radial cut lines: one (anti)periodic pair per crossed region
    radii = [0.0, rotor_r, Rm, Ri, Ro, Rs, stator_or]
    for ang in (0.0, alpha):
        for r in radii:
            call("mi_addnode", *_pol(r, ang))
    regions = [(0, 1, "per_rotor_iron", 1), (1, 2, "per_magnet", 1), (2, 3, "per_rotor_air", 1),
               (3, 4, None, 0), (4, 5, "per_stator_air", 0), (5, 6, "per_stator_iron", 2)]
    for i, j, name, grp in regions:
        if name:
            call("mi_addboundprop", name, 0, 0, 0, 0, 0, 0, 0, 0, 4 if per else 5, 0, 0)
        for ang in (0.0, alpha):
            a, b = _pol(radii[i], ang), _pol(radii[j], ang)
            call("mi_addsegment", *a, *b)
            call("mi_clearselected")
            call("mi_selectsegment", (a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            call("mi_setsegmentprop", name or "", 0, 1, 0, grp)
            call("mi_clearselected")

    def arc(r, a0, a1, maxseg, bdry="", grp=0):
        call("mi_addnode", *_pol(r, a0))
        call("mi_addnode", *_pol(r, a1))
        call("mi_addarc", *_pol(r, a0), *_pol(r, a1), a1 - a0, maxseg)
        call("mi_clearselected")
        call("mi_selectarcsegment", *_pol(r, (a0 + a1) / 2))
        call("mi_setarcsegmentprop", maxseg, bdry, 0, grp)
        call("mi_clearselected")

    # ---- stator: q slots, bore arcs between them, outer A = 0 arc
    half_open = slot_open / 2.0
    xb = math.sqrt(Rs * Rs - half_open * half_open)
    x_tip, x_bot, hw = Rs + tip_h, Rs + tip_h + slot_depth, slot_w / 2.0
    local = [(xb, -half_open), (x_tip, -half_open), (x_tip, -hw), (x_bot, -hw), (x_bot, hw), (x_tip, hw),
             (x_tip, half_open), (xb, half_open)]

    def rot(pt, deg):
        t = math.radians(deg)
        return (pt[0] * math.cos(t) - pt[1] * math.sin(t), pt[0] * math.sin(t) + pt[1] * math.cos(t))

    open_ang = 2 * math.degrees(math.asin(half_open / Rs))
    for k in range(q):
        P = [rot(pt, offset + k * pitch) for pt in local]
        for pt in P:
            call("mi_addnode", *pt)
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (1, 6)):
            call("mi_addsegment", *P[a], *P[b])
    bore = [0.0] + [a for k in range(q) for a in (offset + k * pitch - open_ang / 2, offset + k * pitch + open_ang / 2)] \
        + [alpha]
    for a0, a1 in zip(bore[0::2], bore[1::2]):
        arc(Rs, a0, a1, 1, grp=2)
    for k in range(q):
        ph, sign = phases[k]
        helpers._label(link, *rot(((x_tip + x_bot) / 2, 0), offset + k * pitch), "Copper", ph, group=3,
                       turns=sign * turns_per_slot, meshsize=mesh_coil)
    arc(stator_or, 0.0, alpha, 3, "A=0", 2)
    helpers._label(link, *_pol((x_bot + stator_or) / 2, offset), steel, group=2, meshsize=mesh_iron)

    # ---- rotor: iron, m poles (half magnets at both cut lines), rotor-side air, AGE arcs
    span = 360.0 / poles
    edges = [span / 2 + j * span for j in range(m)]            # boundaries between magnets inside the sector
    breaks = [0.0] + edges + [alpha]
    for a0, a1 in zip(breaks[:-1], breaks[1:]):
        arc(rotor_r, a0, a1, 2, grp=1)
        arc(Rm, a0, a1, 1, grp=1)
    for e in edges:
        call("mi_addsegment", *_pol(rotor_r, e), *_pol(Rm, e))
        call("mi_clearselected")
        call("mi_selectsegment", *_pol((rotor_r + Rm) / 2, e))
        call("mi_setsegmentprop", "", 0, 1, 0, 1)
        call("mi_clearselected")
    helpers._label(link, *_pol(rotor_r / 2, alpha / 2), steel, group=1, meshsize=mesh_iron)
    for a0, a1 in zip(breaks[:-1], breaks[1:]):
        mid = (a0 + a1) / 2
        j = round(mid / span)                                   # magnet j is centred at j * span
        mdir = (j * span if j % 2 == 0 else j * span + 180.0) % 360
        helpers._label(link, *_pol((rotor_r + Rm) / 2, mid), magnet, magdir=mdir, group=1, meshsize=mesh_magnet)
    arc(Ri, 0.0, alpha, 1, "AGE", 1)
    arc(Ro, 0.0, alpha, 1, "AGE", 0)
    helpers._label(link, *_pol((Rm + Ri) / 2, alpha / 2), "Air", group=1, meshsize=mesh_gap)
    helpers._label(link, *_pol((Ro + Rs) / 2, offset), "Air", group=0, meshsize=mesh_gap)
    helpers._label(link, *_pol((Ri + Ro) / 2, alpha / 2), "<No Mesh>", group=0)
    helpers._save(link, path)
    return {"sector": int(sector), "sector_angle_deg": alpha, "sector_kind": kind, "slots_in_model": q,
            "poles_in_model": m, "scale_to_full_machine": int(sector),
            "scale_rule": "measured: flux linkage, EMF, coenergy, energy, resistance, copper loss x N (0.05 %), "
                          "inductance x N (0.12 %), air-gap element torque x 1 (0.05 %); currents, B, angles x 1; "
                          "iron losses x N unmeasured"}
