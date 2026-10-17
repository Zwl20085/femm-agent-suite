"""Parametric benchmark models built from scratch through the FEMM command protocol.

Each builder takes anything with ``.call(name, *args)`` (a :class:`~femm_agent.ipc.FemmLink`),
creates a new magnetics document, draws, assigns properties, saves to ``path`` and returns a
metadata dict: the group numbers to move/rotate, circuit names, and the analytic inputs needed by
:mod:`femm_agent.estimate` to sanity-check the result. Material names are FEMM 5 library names.

* :func:`build_ccore`      planar U-core + armature (two gaps) -- gap B, inductance, force vs gap
* :func:`build_coilgun`    axisymmetric coil + iron slug (re-creation of the shipped coilgun.fem)
* :func:`build_spm`        planar surface-PM machine (default 12 slots / 4 poles), rotate-group or
                           air-gap-element ("age") rotor -- cogging, back-EMF, Ld/Lq, torque
* :func:`build_round_wire` planar copper wire in an A = 0 circle -- AC resistance / inductance
"""
from __future__ import annotations

import math
from typing import Any

from . import estimate
from .units import MU0, length_factor


# ----------------------------------------------------------------------------- drawing helpers

def _label(link, x, y, material, circuit="", magdir=0, group=0, turns=0, meshsize=0.0):
    link.call("mi_addblocklabel", x, y)
    link.call("mi_clearselected")
    link.call("mi_selectlabel", x, y)
    automesh = 0 if meshsize and meshsize > 0 else 1
    link.call("mi_setblockprop", material, automesh, float(meshsize or 0), circuit, magdir, group, turns)
    link.call("mi_clearselected")


def _polygon(link, pts):
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        link.call("mi_drawline", x1, y1, x2, y2)


def _set_group_rect(link, x1, y1, x2, y2, group):
    link.call("mi_clearselected")
    link.call("mi_selectrectangle", x1, y1, x2, y2, 4)
    link.call("mi_setgroup", group)
    link.call("mi_clearselected")


def _set_group_circle(link, x, y, r, group):
    link.call("mi_clearselected")
    link.call("mi_selectcircle", x, y, r, 4)
    link.call("mi_setgroup", group)
    link.call("mi_clearselected")


def _circle(link, r, maxseg=2.0, bdry="", group=0, start_deg=0.0):
    """Full circle of radius r about the origin as two 180-degree arcs."""
    a = math.radians(start_deg)
    x1, y1 = r * math.cos(a), r * math.sin(a)
    x2, y2 = -x1, -y1
    link.call("mi_addnode", x1, y1)
    link.call("mi_addnode", x2, y2)
    link.call("mi_addarc", x1, y1, x2, y2, 180, maxseg)
    link.call("mi_addarc", x2, y2, x1, y1, 180, maxseg)
    if bdry or group:
        for ang in (start_deg + 90, start_deg + 270):
            t = math.radians(ang)
            link.call("mi_clearselected")
            link.call("mi_selectarcsegment", r * math.cos(t), r * math.sin(t))
            link.call("mi_setarcsegmentprop", maxseg, bdry, 0, group)
        link.call("mi_clearselected")


def _material(link, name):
    """Load a library material, or define a linear one from ``'linear:<mu_r>'``."""
    if name.startswith("linear:"):
        mu = float(name.split(":", 1)[1])
        mname = f"Linear iron mu{mu:g}"
        link.call("mi_addmaterial", mname, mu, mu, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0)
        return mname
    link.call("mi_getmaterial", name)
    return name


def _save(link, path):
    link.call("mi_saveas", str(path).replace("\\", "/"))


# ----------------------------------------------------------------------------- C-core

def build_ccore(link, path: str, *, gap: float = 1.0, core_width: float = 10.0, outer_w: float = 60.0,
                outer_h: float = 40.0, armature_h: float = 10.0, depth: float = 20.0, turns: int = 200,
                current: float = 2.0, iron: str = "linear:2000", precision: float = 1e-8,
                abc_radius: float | None = None) -> dict[str, Any]:
    """Planar U-core (legs up) with an I-armature above it and a coil around the base (mm).

    Groups: armature = 1 (move it in +y to open the gaps), core = 2, coil = 3. Circuit ``coil``
    (series, ``turns`` per side). ``iron`` is a library name or ``'linear:<mu_r>'``.
    """
    w, W, H, g = core_width, outer_w, outer_h, gap
    link.call("newdocument", 0)
    link.call("mi_probdef", 0, "millimeters", "planar", precision, depth, 30)
    link.call("mi_getmaterial", "Air")
    link.call("mi_getmaterial", "Copper")
    iron_name = _material(link, iron)
    link.call("mi_addcircprop", "coil", current, 1)
    x0 = W / 2
    core = [(-x0, 0), (x0, 0), (x0, H), (x0 - w, H), (x0 - w, w), (-x0 + w, w), (-x0 + w, H), (-x0, H)]
    _polygon(link, core)
    link.call("mi_drawrectangle", -x0, H + g, x0, H + g + armature_h)
    ci = x0 - w - 2  # coil inner half width
    ch = min(8.0, H - w - 4)
    link.call("mi_drawrectangle", -ci, w + 1, ci, w + 1 + ch)
    link.call("mi_drawrectangle", -ci, -1 - ch, ci, -1)
    size = max(W, H + g + armature_h)
    R = abc_radius or 3.0 * size
    cy = (H + g + armature_h) / 2
    link.call("mi_makeABC", 7, R, 0, cy, 0)
    _label(link, 0, w / 2, iron_name, group=2)
    _label(link, 0, H + g + armature_h / 2, iron_name, group=1)
    _label(link, 0, w + 1 + ch / 2, "Copper", "coil", group=3, turns=turns)
    _label(link, 0, -1 - ch / 2, "Copper", "coil", group=3, turns=-turns)
    _label(link, 0, w + 1 + ch + (H - w - 1 - ch) / 2, "Air")
    _set_group_rect(link, -x0 - 0.01, H + g - 0.01 * g, x0 + 0.01, H + g + armature_h + 0.01, 1)
    _save(link, path)
    l_fe = 2 * (W - w) + 2 * (H - w / 2 + armature_h / 2)
    mu_r = float(iron.split(":")[1]) if iron.startswith("linear:") else 1e9
    area = w * 1e-3 * depth * 1e-3
    bg = estimate.ccore_gap_b(turns, current, 2 * g * 1e-3, l_fe * 1e-3, mu_r)
    return {
        "kind": "ccore", "path": str(path), "units": "millimeters", "depth_mm": depth,
        "groups": {"armature": 1, "core": 2, "coil": 3}, "circuits": ["coil"], "turns": turns, "current": current,
        "gap_mm": g, "iron": iron_name, "linear": iron.startswith("linear:"),
        "probe_gap_point": [x0 - w / 2, H + g / 2],
        "estimate": {
            "gap_B_T": bg,
            "inductance_H": estimate.ccore_inductance(turns, area, 2 * g * 1e-3, l_fe * 1e-3, mu_r),
            "force_N": -2 * estimate.maxwell_force(bg, area),
            "notes": "no fringing/leakage; FEMM gap B lower and L higher by fringing, force within ~20%",
        },
    }


# ----------------------------------------------------------------------------- coilgun (axisymmetric)

def build_coilgun(link, path: str, *, slug_radius: float = 0.15625, slug_z: float = 0.0, coil_ri: float = 0.25,
                  coil_ro: float = 1.25, coil_len: float = 1.5, turns: int = 1000, current: float = 9.677,
                  slug_material: str = "linear:2500", domain_radius: float = 4.0,
                  precision: float = 1e-8) -> dict[str, Any]:
    """Axisymmetric coil with a spherical iron slug on the axis (inches), like FEMM's coilgun.fem,
    but with a circuit (so flux linkage is available) and an ``mi_makeABC`` open boundary in place
    of the Kelvin region. Slug = group 1 (move along z = dy). Defaults give J = 10 A/mm^2."""
    link.call("newdocument", 0)
    link.call("mi_probdef", 0, "inches", "axi", precision, 0, 30)
    link.call("mi_getmaterial", "Air")
    link.call("mi_getmaterial", "Copper")
    slug = _material(link, slug_material)
    link.call("mi_addcircprop", "coil", current, 1)
    link.call("mi_drawrectangle", coil_ri, -coil_len / 2, coil_ro, coil_len / 2)
    R = slug_radius
    link.call("mi_addnode", 0, slug_z - R)
    link.call("mi_addnode", 0, slug_z + R)
    link.call("mi_addarc", 0, slug_z - R, 0, slug_z + R, 180, 2)
    link.call("mi_addsegment", 0, slug_z - R, 0, slug_z + R)
    link.call("mi_makeABC", 7, domain_radius, 0, 0, 0)
    # axis segments from the ABC's poles to the slug
    link.call("mi_addsegment", 0, -domain_radius, 0, slug_z - R)
    link.call("mi_addsegment", 0, slug_z + R, 0, domain_radius)
    _label(link, R / 3, slug_z, slug, group=1)
    _label(link, (coil_ri + coil_ro) / 2, 0, "Copper", "coil", group=3, turns=turns)
    _label(link, coil_ro + 0.5, coil_len, "Air")
    _set_group_rect(link, -0.001, slug_z - R - 1e-3, R + 1e-3, slug_z + R + 1e-3, 1)
    _save(link, path)
    area_in2 = (coil_ro - coil_ri) * coil_len
    j = turns * current / (area_in2 * 645.16)  # A/mm^2
    b0 = estimate.thick_solenoid_b_center(j * 1e6, coil_ri * 0.0254, coil_ro * 0.0254, coil_len * 0.0254)
    return {"kind": "coilgun", "path": str(path), "units": "inches", "groups": {"slug": 1, "coil": 3},
            "circuits": ["coil"], "turns": turns, "current": current, "J_A_per_mm2": j,
            "estimate": {"B_center_no_slug_T": b0,
                         "notes": "thick-solenoid centre field (slug perturbs it locally)"}}


# ----------------------------------------------------------------------------- SPM machine

def spm_slot_phases(slots: int, pole_pairs: int, slot_offset_deg: float) -> list[tuple[str, int]]:
    """(phase, sign) per slot for a single-layer distributed winding whose phase-A axis is at 0 deg.

    Slot k sits at theta_k = offset + k*360/Q (mech), electrical angle phi = p*theta_k. A coil side
    with +turns at electrical angle alpha + 90 and -turns at alpha - 90 has its magnetic axis at
    alpha (A = 0, B = 120, C = 240 deg elec, so a positive phase sequence rotates CCW)."""
    out = []
    for k in range(slots):
        phi = pole_pairs * (slot_offset_deg + k * 360.0 / slots)
        best = None
        for ph, alpha in (("A", 0.0), ("B", 120.0), ("C", 240.0)):
            v = math.cos(math.radians(phi - alpha - 90.0))
            if best is None or abs(v) > abs(best[2]) + 1e-9:
                best = (ph, 1 if v > 0 else -1, v)
        out.append((best[0], best[1]))
    return out


def build_spm(link, path: str, *, slots: int = 12, pole_pairs: int = 2, rotor_r: float = 20.0,
              magnet_t: float = 3.0, gap: float = 1.5, stator_or: float = 50.0, slot_open: float = 2.0,
              tip_h: float = 1.0, slot_w: float = 5.0, slot_depth: float = 12.0, depth: float = 50.0,
              turns_per_slot: int = 20, steel: str = "M-19 14 mil", magnet: str = "N42",
              rotor_method: str = "rotate", mesh_gap: float = 0.5, mesh_magnet: float = 1.5, mesh_iron: float = 2.5,
              mesh_coil: float = 2.5, smartmesh: bool = False,
              precision: float = 1e-8) -> dict[str, Any]:
    """Planar inner-rotor surface-PM machine (mm). Defaults: 12 slots, 4 poles, N42, M-19 14 mil,
    ~8-10k elements.

    * ``rotor_method='rotate'``: rotor iron + magnets are group 1, rotor-side air layer group 10;
      a sliding interface circle sits mid-gap. Rotate groups [1, 10] about (0, 0).
    * ``rotor_method='age'``: a FEMM 5 periodic air-gap element (boundary ``AGE``, BdryFormat 6)
      between two mid-gap circles; rotate by ``mi_modifyboundprop('AGE', 10, angle)``.

    Phase A's magnetic axis and the d-axis (north pole of magnet 0) are both at 0 deg mechanical
    when the rotor angle is 0. Circuits ``A``, ``B``, ``C`` (series, 0 A)."""
    p = pole_pairs
    Rm = rotor_r + magnet_t          # magnet outer radius
    Rs = Rm + gap                   # stator bore
    link.call("newdocument", 0)
    link.call("mi_probdef", 0, "millimeters", "planar", precision, depth, 30)
    link.call("mi_smartmesh", 1 if smartmesh else 0)
    for m in ("Air", "Copper", steel, magnet):
        link.call("mi_getmaterial", m)
    link.call("mi_addboundprop", "A=0", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    for ph in ("A", "B", "C"):
        link.call("mi_addcircprop", ph, 0, 1)

    # ---- stator: slots + bore arcs
    pitch = 360.0 / slots
    offset = pitch / 2.0
    half_open = slot_open / 2.0
    xb = math.sqrt(Rs * Rs - half_open * half_open)
    x_tip = Rs + tip_h
    x_bot = x_tip + slot_depth
    hw = slot_w / 2.0
    local = [(xb, -half_open), (x_tip, -half_open), (x_tip, -hw), (x_bot, -hw), (x_bot, hw), (x_tip, hw),
             (x_tip, half_open), (xb, half_open)]

    def rot(pt, deg):
        t = math.radians(deg)
        return (pt[0] * math.cos(t) - pt[1] * math.sin(t), pt[0] * math.sin(t) + pt[1] * math.cos(t))

    phases = spm_slot_phases(slots, p, offset)
    open_ang = 2 * math.degrees(math.asin(half_open / Rs))
    for k in range(slots):
        th = offset + k * pitch
        P = [rot(q, th) for q in local]
        for q in P:
            link.call("mi_addnode", *q)
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (1, 6)):
            link.call("mi_addsegment", *P[a], *P[b])
    for k in range(slots):
        th = offset + k * pitch
        P8 = rot(local[7], th)
        P1n = rot(local[0], th + pitch)
        link.call("mi_addarc", *P8, *P1n, pitch - open_ang, 1)
    for k in range(slots):
        th = offset + k * pitch
        ph, sign = phases[k]
        cx, cy = rot(((x_tip + x_bot) / 2, 0), th)
        _label(link, cx, cy, "Copper", ph, group=3, turns=sign * turns_per_slot, meshsize=mesh_coil)
    _circle(link, stator_or, maxseg=3, bdry="A=0", group=2)
    _label(link, *rot(((x_bot + stator_or) / 2, 0), 0), steel, group=2, meshsize=mesh_iron)

    # ---- rotor: iron disk + 2p magnets
    npole = 2 * p
    edges = [180.0 / npole + j * 360.0 / npole for j in range(npole)]
    for r in (rotor_r, Rm):
        for e in edges:
            link.call("mi_addnode", r * math.cos(math.radians(e)), r * math.sin(math.radians(e)))
    for j, e in enumerate(edges):
        e2 = edges[(j + 1) % npole]
        span = 360.0 / npole
        for r, seg in ((rotor_r, 2), (Rm, 1)):
            link.call("mi_addarc", r * math.cos(math.radians(e)), r * math.sin(math.radians(e)),
                      r * math.cos(math.radians(e2)), r * math.sin(math.radians(e2)), span, seg)
        link.call("mi_addsegment", rotor_r * math.cos(math.radians(e)), rotor_r * math.sin(math.radians(e)),
                  Rm * math.cos(math.radians(e)), Rm * math.sin(math.radians(e)))
    _label(link, rotor_r / 2, 0, steel, group=1, meshsize=mesh_iron)
    for j in range(npole):
        ac = j * 360.0 / npole
        mdir = ac if j % 2 == 0 else ac + 180.0
        r = (rotor_r + Rm) / 2
        _label(link, r * math.cos(math.radians(ac)), r * math.sin(math.radians(ac)), magnet, magdir=mdir % 360,
               group=1, meshsize=mesh_magnet)

    # ---- air gap
    if rotor_method == "rotate":
        Ri = Rm + gap / 2
        _circle(link, Ri, maxseg=1, group=10, start_deg=0)
        _set_group_circle(link, 0, 0, Rm + 1e-3, 1)
        _set_group_circle_ring(link, Ri, 10)
        _label(link, (Rm + Ri) / 2 * math.cos(math.radians(1)), (Rm + Ri) / 2 * math.sin(math.radians(1)), "Air",
               group=10, meshsize=mesh_gap)
        _label(link, (Ri + Rs) / 2, 0, "Air", group=0, meshsize=mesh_gap)
        rotate_groups = [1, 10]
        bdry = None
    elif rotor_method == "age":
        Ri = Rm + gap * 0.4
        Ro = Rm + gap * 0.6
        link.call("mi_addboundprop", "AGE", 0, 0, 0, 0, 0, 0, 0, 0, 6, 0, 0)
        _circle(link, Ri, maxseg=1, bdry="AGE", group=1)
        _circle(link, Ro, maxseg=1, bdry="AGE", group=0)
        _set_group_circle(link, 0, 0, Rm + 1e-3, 1)
        _label(link, (Rm + Ri) / 2, 0, "Air", group=1, meshsize=mesh_gap)
        _label(link, (Ro + Rs) / 2, 0, "Air", group=0, meshsize=mesh_gap)
        _label(link, (Ri + Ro) / 2, 0, "<No Mesh>", group=0)  # the AGE annulus itself is not meshed
        rotate_groups = [1]
        bdry = "AGE"
    else:
        raise ValueError("rotor_method must be 'rotate' or 'age'")
    _save(link, path)

    # ---- analytic references
    br = 1.30 if magnet.upper().startswith("N4") else 1.2
    kc = estimate.carter_coefficient(2 * math.pi * Rs / slots, slot_open, gap)
    bg = estimate.spm_gap_b(br, 1.05, magnet_t, gap, kc)
    n_ph = turns_per_slot * slots / 3 / 2  # series turns per phase (single layer: 2 coil sides per turn)
    psi1 = estimate.spm_flux_linkage_fundamental(bg, (Rm + Rs) / 2 * 1e-3, depth * 1e-3, p, n_ph)
    return {
        "kind": "spm", "path": str(path), "units": "millimeters", "depth_mm": depth, "slots": slots,
        "pole_pairs": p, "poles": 2 * p, "circuits": ["A", "B", "C"], "turns_per_slot": turns_per_slot,
        "slot_phases": phases, "rotor_method": rotor_method, "rotate_groups": rotate_groups,
        "torque_groups": [1], "air_gap_boundary": bdry, "center": [0.0, 0.0],
        "radii_mm": {"rotor": rotor_r, "magnet": Rm, "bore": Rs, "outer": stator_or},
        "magnet": magnet, "steel": steel,
        "estimate": {"Br_T": br, "carter": kc, "gap_B_T": bg, "turns_per_phase": n_ph,
                     "psi_pm_peak_Wb": psi1,
                     "cogging_period_deg": estimate.cogging_period_deg(slots, 2 * p),
                     "emf_peak_V_at_1000rpm": estimate.emf_from_flux_linkage(psi1, 1000, p),
                     "notes": "flat-gap, no leakage, ideal steel: FEMM psi typically 5-15% lower"},
    }


def _set_group_circle_ring(link, r, group):
    """Assign ``group`` to the two arcs of the circle of radius r (and their nodes)."""
    for ang in (90, 270):
        t = math.radians(ang)
        link.call("mi_clearselected")
        link.call("mi_selectarcsegment", r * math.cos(t), r * math.sin(t))
        link.call("mi_setgroup", group)
    for ang in (0, 180):
        t = math.radians(ang)
        link.call("mi_clearselected")
        link.call("mi_selectnode", r * math.cos(t), r * math.sin(t))
        link.call("mi_setgroup", group)
    link.call("mi_clearselected")


# ----------------------------------------------------------------------------- round wire (AC)

def build_round_wire(link, path: str, *, radius: float = 5.0, boundary_radius: float = 50.0, depth: float = 1000.0,
                     current: float = 1.0, frequency: float = 50.0, mesh_wire: float = 0.25,
                     precision: float = 1e-8) -> dict[str, Any]:
    """Planar copper wire (mm) of ``radius`` inside an A = 0 circle (return path at Rb), 1 m deep
    by default. Circuit ``wire`` (series, 1 turn). Analytic: R_dc = 1/(sigma pi a^2) per metre,
    L_dc = mu0/2pi (ln(Rb/a) + 1/4), and the exact Bessel internal impedance at any f."""
    link.call("newdocument", 0)
    link.call("mi_probdef", frequency, "millimeters", "planar", precision, depth, 30)
    link.call("mi_getmaterial", "Air")
    link.call("mi_getmaterial", "Copper")
    link.call("mi_addboundprop", "A=0", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    link.call("mi_addcircprop", "wire", current, 1)
    _circle(link, radius, maxseg=2)
    _circle(link, boundary_radius, maxseg=3, bdry="A=0")
    _label(link, 0, 0, "Copper", "wire", group=1, turns=1, meshsize=mesh_wire)
    _label(link, (radius + boundary_radius) / 2, 0, "Air")
    _save(link, path)
    sigma = 58e6
    a = radius * 1e-3
    lm = depth * 1e-3
    return {"kind": "round_wire", "path": str(path), "units": "millimeters", "circuits": ["wire"],
            "radius_mm": radius, "boundary_radius_mm": boundary_radius, "depth_mm": depth, "sigma_S_per_m": sigma,
            "estimate": {"R_dc_ohm": lm / (sigma * math.pi * a * a),
                         "L_dc_H": lm * estimate.wire_inductance_per_length(a, boundary_radius * 1e-3),
                         "L_external_H": lm * MU0 / (2 * math.pi) * math.log(boundary_radius / radius),
                         "notes": "FEMM Copper is 58 MS/m; use estimate.round_wire_internal_impedance for f > 0"}}


BUILDERS = {"ccore": build_ccore, "coilgun": build_coilgun, "spm": build_spm, "round_wire": build_round_wire}


def unit_factor(units: str) -> float:
    return length_factor(units)
