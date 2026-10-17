"""Physics invariants and sanity rules for FEMM results (pure: plain numbers / arrays in, dicts out).

Every rule returns the same shape::

    {"name": str, "ok": bool | None, "value": float | None, "expected": float | str | None,
     "tolerance": float | None, "message": str}

``ok`` is ``None`` when the rule does not apply (missing inputs); the message says why. Rules never
raise for physics reasons; they raise only on programming errors (wrong types).

Block-integral codes used by the live collectors (FEMM 5 manual 3.7.1, magnetics): 2 energy,
5 area, 6 total losses, 10 volume, 17 coenergy, 18/19 x/y weighted-stress-tensor (WST) force,
22 WST torque. ``mo_gapintegral(bdry, 0)`` is the air-gap-element torque.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from .units import MU0


def _check(name: str, ok: bool | None, value: Any, expected: Any, tolerance: Any, message: str, **detail: Any) -> dict:
    out = {"name": name, "ok": ok, "value": value, "expected": expected, "tolerance": tolerance, "message": message}
    if detail:
        out["detail"] = detail
    return out


def _rel_err(a: float, b: float, floor: float = 0.0) -> float:
    den = max(abs(a), abs(b), floor)
    return 0.0 if den == 0 else abs(a - b) / den


def not_applicable(name: str, why: str) -> dict:
    return _check(name, None, None, None, None, f"not applicable: {why}")


# ----------------------------------------------------------------------------- energy

def energy_consistency(energy: float, flux_linkages: Sequence[float], currents: Sequence[float],
                       linear: bool = True, tolerance: float = 0.03) -> dict:
    """Linear magnetostatics without magnets: W = 1/2 sum_k I_k psi_k (= 1/2 L I^2 for one coil).

    ``energy`` is the total field energy (block integral 2 over all blocks, J). Nonlinear or PM
    problems are skipped (the identity does not hold there).
    """
    name = "energy_vs_flux_linkage"
    if not linear:
        return not_applicable(name, "nonlinear or permanent-magnet problem (W != 1/2 sum I psi)")
    if not currents or all(abs(i) == 0 for i in currents):
        return not_applicable(name, "no circuit carries current")
    w_circ = 0.5 * sum(float(i) * float(p) for i, p in zip(currents, flux_linkages))
    err = _rel_err(energy, w_circ)
    ok = err <= tolerance
    msg = (f"field energy {energy:.6g} J vs 1/2 sum(I psi) {w_circ:.6g} J (rel err {err:.2%})"
           + ("" if ok else "; check that every current-carrying region is in a circuit, the outer boundary"
              " is far enough, and the mesh in the coil is fine enough"))
    return _check(name, ok, energy, w_circ, tolerance, msg)


def energy_coenergy_linear(energy: float, coenergy: float, linear: bool = True, tolerance: float = 0.02) -> dict:
    """For a linear problem without magnets the energy W and coenergy W' (codes 2 and 17) are equal.
    A big gap in a 'linear' model means something is saturating (a nonlinear B-H curve is active)."""
    name = "energy_equals_coenergy"
    if not linear:
        if coenergy < energy * 0.999 and energy > 0:
            return _check(name, False, coenergy, f">= {energy:.6g}", None,
                          "coenergy below energy in a nonlinear problem: inconsistent (should be W' >= W for saturating iron)")
        return _check(name, True, coenergy, energy, None,
                      f"nonlinear: W' = {coenergy:.6g} J >= W = {energy:.6g} J (ratio {coenergy / energy if energy else float('nan'):.3f}; >1 indicates saturation)")
    err = _rel_err(energy, coenergy)
    ok = err <= tolerance
    return _check(name, ok, coenergy, energy, tolerance,
                  f"W = {energy:.6g} J, W' = {coenergy:.6g} J (rel diff {err:.2%})"
                  + ("" if ok else "; a linear model should have W = W' (is a nonlinear material in use?)"))


# ----------------------------------------------------------------------------- flux

def flux_conservation(flux_in: float, flux_out: float, tolerance: float = 0.05, leakage_allowed: float = 0.0) -> dict:
    """Flux entering a region equals flux leaving it (minus allowed leakage fraction).

    In 2D planar, flux per depth across a cut from P1 to P2 is A(P2) - A(P1); multiply by depth.
    """
    name = "flux_conservation"
    if flux_in == 0 and flux_out == 0:
        return not_applicable(name, "no flux through either cut")
    err = _rel_err(abs(flux_in), abs(flux_out))
    ok = err <= tolerance + leakage_allowed
    return _check(name, ok, flux_out, flux_in, tolerance + leakage_allowed,
                  f"flux in {flux_in:.6g} Wb vs out {flux_out:.6g} Wb (diff {err:.2%})"
                  + ("" if ok else "; flux is leaking or a cut crosses a different branch"))


# ----------------------------------------------------------------------------- saturation

def saturation(b_magnitude: Sequence[float], areas: Sequence[float], b_limit: float = 1.8,
               max_fraction: float = 0.05, region: str = "steel") -> dict:
    """Fraction of steel area above ``b_limit`` (T). Electrical steels saturate around 1.6-2.0 T;
    a large saturated fraction is not necessarily wrong but must be intended."""
    name = f"saturation_{region}"
    total = float(sum(areas))
    if total <= 0:
        return not_applicable(name, f"no {region} elements")
    over = sum(a for b, a in zip(b_magnitude, areas) if b > b_limit)
    frac = over / total
    bmax = max(b_magnitude) if len(b_magnitude) else 0.0
    ok = frac <= max_fraction
    msg = (f"{frac:.1%} of {region} area above {b_limit} T (max |B| {bmax:.3f} T)"
           + ("" if ok else "; heavily saturated: check currents/ampere-turns and magnet grade, "
              "and make sure the steel uses a nonlinear B-H curve"))
    return _check(name, ok, frac, f"<= {max_fraction}", max_fraction, msg, b_max=bmax, b_limit=b_limit)


def linear_material_overflux(b_magnitude: Sequence[float], b_limit: float = 2.2) -> dict:
    """A *linear* iron (constant mu_r) carrying > ~2.2 T is unphysical: real steel would saturate."""
    name = "linear_iron_unphysical_B"
    if not len(b_magnitude):
        return not_applicable(name, "no linear-iron elements")
    bmax = max(b_magnitude)
    ok = bmax <= b_limit
    return _check(name, ok, bmax, f"<= {b_limit}", b_limit,
                  f"max |B| in linear-permeability iron {bmax:.3f} T"
                  + ("" if ok else "; real steel saturates: use a nonlinear library material (e.g. 'M-19 14 mil')"))


# ----------------------------------------------------------------------------- mesh

def mesh_size(n_elements: int, min_elements: int = 1000, max_elements: int = 200_000) -> dict:
    name = "mesh_element_count"
    ok = min_elements <= n_elements <= max_elements
    if n_elements < min_elements:
        msg = f"{n_elements} elements is coarse; forces/torques from WST need several element layers in the air gap"
    elif n_elements > max_elements:
        msg = f"{n_elements} elements is very fine; solves will be slow (consider symmetry or coarser far-field mesh)"
    else:
        msg = f"{n_elements} elements"
    return _check(name, ok, n_elements, f"{min_elements}..{max_elements}", None, msg)


def triangle_angles(nodes, elements):
    """Minimum interior angle (deg) of every triangle. ``nodes`` (N,2), ``elements`` (M,>=3) with
    0-based node indices in the first three columns."""
    import numpy as np

    p = np.asarray(nodes, dtype=float)
    t = np.asarray(elements)[:, :3].astype(int)
    a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]

    def ang(u, v, w):
        x, y = v - u, w - u
        cosv = (x * y).sum(1) / (np.linalg.norm(x, axis=1) * np.linalg.norm(y, axis=1) + 1e-300)
        return np.degrees(np.arccos(np.clip(cosv, -1.0, 1.0)))

    return np.minimum(np.minimum(ang(a, b, c), ang(b, c, a)), ang(c, a, b))


def mesh_quality(min_angles: Sequence[float], requested_min_angle: float = 30.0, bad_angle: float = 10.0,
                 max_bad_fraction: float = 0.001) -> dict:
    """Share of slivers (min angle < ``bad_angle``). FEMM's mesher targets ``MinAngle`` (probdef
    6th argument, default 30 deg) but small features can force worse triangles."""
    name = "mesh_min_angle"
    n = len(min_angles)
    if n == 0:
        return not_applicable(name, "no elements")
    worst = float(min(min_angles))
    bad = sum(1 for x in min_angles if x < bad_angle) / n
    ok = bad <= max_bad_fraction
    return _check(name, ok, worst, f">= {requested_min_angle} (target)", bad_angle,
                  f"worst triangle angle {worst:.1f} deg; {bad:.2%} of elements below {bad_angle} deg"
                  + ("" if ok else "; slivers: remove tiny edges / near-coincident nodes, or raise MinAngle"),
                  bad_fraction=bad)


def solver_precision(precision: float, max_precision: float = 1e-6) -> dict:
    """``mi_probdef`` precision is the RMS residual target of the linear/nonlinear solve. 1e-8 is
    FEMM's default; anything looser than 1e-6 makes forces/torques noisy."""
    name = "solver_precision"
    ok = precision <= max_precision
    return _check(name, ok, precision, f"<= {max_precision}", max_precision,
                  f"probdef precision {precision:g}" + ("" if ok else "; tighten to 1e-8 for force/torque work"))


# ----------------------------------------------------------------------------- boundary

def boundary_distance(b_boundary_max: float, b_max: float, max_ratio: float = 0.02,
                      has_open_boundary: bool = False, flux_contained: bool = False) -> dict:
    """Field at the outer boundary relative to the peak field. With a Dirichlet A = 0 box the
    outer edge should see < ~2 % of the peak |B|; otherwise the box is too small (or use
    ``mi_makeABC`` for an open boundary). Machines whose flux is contained by back iron
    (``flux_contained``) are exempt."""
    name = "outer_boundary_far_enough"
    if flux_contained:
        return _check(name, True, None, None, None, "flux contained by an iron yoke at the outer boundary (rule waived)")
    if b_max <= 0:
        return not_applicable(name, "zero field")
    ratio = b_boundary_max / b_max
    lim = max_ratio * (5 if has_open_boundary else 1)
    ok = ratio <= lim
    return _check(name, ok, ratio, f"<= {lim}", lim,
                  f"|B| at outer boundary is {ratio:.2%} of max |B|"
                  + ("" if ok else "; enlarge the air box (>= 3-5x the device size) or use mi_makeABC"))


# ----------------------------------------------------------------------------- forces / torques

def force_consistency(f_a: float, f_b: float, label_a: str = "WST", label_b: str = "virtual work",
                      tolerance: float = 0.05, scale: float | None = None, name: str = "force_consistency") -> dict:
    """Two independent estimates of the same force (or torque) must agree.

    Typical pairs: weighted stress tensor (block integral 18/19/22) vs virtual work
    (dW'/dx at constant current, from coenergy code 17), or rotor torque vs minus stator torque, or
    WST torque vs air-gap-element torque (``mo_gapintegral(bdry,0)``). ``scale`` is a magnitude
    floor so near-zero values compare in absolute terms (e.g. peak of the curve)."""
    err = _rel_err(f_a, f_b, floor=scale or 0.0)
    ok = err <= tolerance
    return _check(name, ok, f_a, f_b, tolerance,
                  f"{label_a} {f_a:.6g} vs {label_b} {f_b:.6g} (rel diff {err:.2%})"
                  + ("" if ok else "; refine the air-gap mesh (>= 3 element layers) and check the selected group"))


def curve_consistency(a: Sequence[float], b: Sequence[float], label_a: str, label_b: str, tolerance: float = 0.08,
                      name: str = "curve_consistency") -> dict:
    """Compare two sampled curves by RMS difference relative to the peak magnitude."""
    if not len(a) or len(a) != len(b):
        return not_applicable(name, "curves missing or of different length")
    peak = max(max(abs(x) for x in a), max(abs(x) for x in b))
    if peak == 0:
        return _check(name, True, 0.0, 0.0, tolerance, "both curves are zero")
    rms = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)) / len(a))
    rel = rms / peak
    ok = rel <= tolerance
    return _check(name, ok, rel, f"<= {tolerance}", tolerance,
                  f"RMS({label_a} - {label_b}) = {rel:.2%} of peak {peak:.4g}"
                  + ("" if ok else "; methods disagree: refine mesh / step size"))


def virtual_work_derivative(positions: Sequence[float], coenergy: Sequence[float]) -> list[float]:
    """Central-difference dW'/dx (one-sided at the ends). Positions in metres (or radians for torque)."""
    x = list(map(float, positions))
    w = list(map(float, coenergy))
    n = len(x)
    if n < 2:
        return [float("nan")] * n
    out = []
    for i in range(n):
        if i == 0:
            out.append((w[1] - w[0]) / (x[1] - x[0]))
        elif i == n - 1:
            out.append((w[-1] - w[-2]) / (x[-1] - x[-2]))
        else:
            out.append((w[i + 1] - w[i - 1]) / (x[i + 1] - x[i - 1]))
    return out


def torque_ripple(torque: Sequence[float]) -> dict:
    """Peak-to-peak / mean torque (for a loaded machine) -- informational."""
    name = "torque_ripple"
    if not len(torque):
        return not_applicable(name, "no samples")
    mean = sum(torque) / len(torque)
    pp = max(torque) - min(torque)
    rip = pp / abs(mean) if mean else float("inf")
    return _check(name, True, rip, None, None, f"mean {mean:.4g} N*m, peak-to-peak {pp:.4g} N*m (ripple {rip:.1%})")


def periodicity(values: Sequence[float], expected_period_samples: int, tolerance: float = 0.05,
                name: str = "periodicity") -> dict:
    """A cogging curve over one period should start and end on the same value; an antiperiodic
    flux linkage should satisfy psi(theta + T/2) = -psi(theta)."""
    if len(values) < 2:
        return not_applicable(name, "too few samples")
    peak = max(abs(v) for v in values) or 1.0
    d = abs(values[0] - values[-1]) / peak if len(values) > expected_period_samples else 0.0
    ok = d <= tolerance
    return _check(name, ok, d, 0.0, tolerance, f"end-to-start mismatch {d:.2%} of peak")


def zero_mean(values: Sequence[float], tolerance: float = 0.05, name: str = "cogging_zero_mean") -> dict:
    """Cogging torque (no current) averages to zero over a period: mean / peak small."""
    if not len(values):
        return not_applicable(name, "no samples")
    peak = max(abs(v) for v in values)
    if peak == 0:
        return _check(name, True, 0.0, 0.0, tolerance, "all zero")
    m = sum(values) / len(values)
    rel = abs(m) / peak
    ok = rel <= tolerance
    return _check(name, ok, rel, 0.0, tolerance, f"mean {m:.4g} vs peak {peak:.4g} ({rel:.1%})"
                  + ("" if ok else "; non-zero mean cogging: currents not all zero, or sweep does not span a whole period"))


# ----------------------------------------------------------------------------- AC

def power_balance(p_input: float, p_losses: float, tolerance: float = 0.05) -> dict:
    """Time-harmonic problems: real input power 1/2 Re(sum V_k conj(I_k)) (FEMM phasors are peak
    amplitudes) must equal the total losses (block integral 6 over all blocks)."""
    name = "ac_power_balance"
    if p_input == 0 and p_losses == 0:
        return not_applicable(name, "no power")
    err = _rel_err(p_input, p_losses)
    ok = err <= tolerance
    return _check(name, ok, p_losses, p_input, tolerance,
                  f"losses {p_losses:.6g} W vs circuit input {p_input:.6g} W (diff {err:.2%})"
                  + ("" if ok else "; a conductor outside any circuit, or an eddy region not selected"))


def skin_depth_resolution(delta: float, min_element_size: float, min_ratio: float = 1.0) -> dict:
    """Eddy-current problems need elements smaller than the skin depth in conductors."""
    name = "skin_depth_resolved"
    ratio = delta / min_element_size if min_element_size > 0 else float("inf")
    ok = ratio >= min_ratio
    return _check(name, ok, ratio, f">= {min_ratio}", min_ratio,
                  f"skin depth / element size = {ratio:.2f}" + ("" if ok else "; refine the conductor mesh near its surface"))


# ----------------------------------------------------------------------------- magnets

def pm_operating_point(bm: float, br: float, hm: float | None = None, min_fraction: float = 0.2,
                       label: str = "magnet") -> dict:
    """B along the magnetisation direction should stay a healthy fraction of Br. Below ~20 % (or
    negative) the magnet risks irreversible demagnetisation, especially when hot."""
    name = f"pm_operating_point[{label}]"
    frac = bm / br if br else float("nan")
    ok = frac >= min_fraction
    pc = (-bm / (MU0 * hm)) if hm not in (None, 0) else None
    msg = f"B_m = {bm:.3f} T = {frac:.0%} of Br {br:.3f} T" + (f", Pc = {pc:.2f}" if pc is not None else "")
    if not ok:
        msg += "; demagnetisation risk (thicker magnet, smaller gap, or less d-axis current)"
    return _check(name, ok, bm, f">= {min_fraction * br:.3g}", min_fraction, msg, permeance_coefficient=pc)


# ----------------------------------------------------------------------------- analytic comparison

def compare_to_estimate(name: str, fem_value: float, estimate: float, tolerance: float = 0.15, why: str = "") -> dict:
    """FEM vs analytic estimate; tolerance reflects the idealisation (fringing, leakage, saturation)."""
    err = _rel_err(fem_value, estimate)
    ok = err <= tolerance
    return _check(name, ok, fem_value, estimate, tolerance,
                  f"FEM {fem_value:.6g} vs analytic {estimate:.6g} (diff {err:.1%})" + (f" -- {why}" if why else ""))


def summarize(checks: Iterable[dict]) -> dict:
    """Roll-up: counts and the names of failing checks."""
    checks = list(checks)
    fails = [c["name"] for c in checks if c.get("ok") is False]
    return {"total": len(checks), "passed": sum(1 for c in checks if c.get("ok") is True),
            "failed": len(fails), "not_applicable": sum(1 for c in checks if c.get("ok") is None),
            "failing": fails, "all_ok": not fails}
