"""Analytic sanity references (pure, SI units throughout: m, A, T, H, F, Ohm, N, N*m).

Use these to judge whether a FEMM number is in the right ballpark *before* trusting it.
Each function documents its formula and the idealisation behind it; FEMM results should agree
within the error of that idealisation (fringing, leakage, saturation, finite length), not to
solver precision.
"""
from __future__ import annotations

import cmath
import math
from typing import Sequence

from .units import EPS0, MU0


# ----------------------------------------------------------------------------- coils

def solenoid_b_infinite(turns: float, current: float, length: float) -> float:
    """B inside an infinitely long solenoid: B = mu0 N I / L  (T)."""
    return MU0 * turns * current / length


def solenoid_b_axis_finite(turns: float, current: float, length: float, radius: float, z: float = 0.0) -> float:
    """B on the axis of a thin finite solenoid centred at z = 0:
    B(z) = (mu0 N I / 2L) [ (z + L/2)/sqrt((z + L/2)^2 + R^2) - (z - L/2)/sqrt((z - L/2)^2 + R^2) ]."""
    a = z + length / 2.0
    b = z - length / 2.0
    return MU0 * turns * current / (2.0 * length) * (a / math.hypot(a, radius) - b / math.hypot(b, radius))


def thick_solenoid_b_center(current_density: float, r_inner: float, r_outer: float, length: float) -> float:
    """B at the centre of a thick solenoid with uniform current density J (A/m^2):
    B0 = mu0 J (L/2) ln[(a + sqrt(a^2 + b^2)) / (1 + sqrt(1 + b^2))],  a = r2/r1, b = L/(2 r1)."""
    a = r_outer / r_inner
    b = length / (2.0 * r_inner)
    return MU0 * current_density * (length / 2.0) * math.log((a + math.hypot(a, b)) / (1.0 + math.hypot(1.0, b)))


def loop_b_axis(current: float, radius: float, z: float = 0.0, turns: float = 1.0) -> float:
    """B on the axis of a circular loop: B(z) = mu0 N I R^2 / (2 (R^2 + z^2)^(3/2))."""
    return MU0 * turns * current * radius ** 2 / (2.0 * (radius ** 2 + z ** 2) ** 1.5)


def solenoid_inductance_long(turns: float, area: float, length: float, mu_r: float = 1.0) -> float:
    """Long-solenoid inductance: L = mu0 mu_r N^2 A / l  (H). Overestimates short coils
    (Nagaoka factor < 1)."""
    return MU0 * mu_r * turns ** 2 * area / length


def wire_inductance_per_length(radius: float, return_radius: float) -> float:
    """DC inductance per metre of a round wire inside a coaxial return (or an A = 0 circle)
    of radius Rb: L' = mu0/(2 pi) (ln(Rb/a) + 1/4)  (H/m); the 1/4 is the internal part."""
    return MU0 / (2.0 * math.pi) * (math.log(return_radius / radius) + 0.25)


def straight_wire_b(current: float, distance: float) -> float:
    """B around a long straight wire: B = mu0 I / (2 pi r)."""
    return MU0 * current / (2.0 * math.pi * distance)


# ----------------------------------------------------------------------------- magnetic circuits

def ccore_gap_b(turns: float, current: float, gap: float, iron_path: float = 0.0, mu_r: float = 1e9) -> float:
    """Gap flux density of a C-core (no fringing, no leakage, uniform cross-section):
    B_g = mu0 N I / (g + l_fe / mu_r)  (T). ``gap`` is the total gap length in the loop."""
    return MU0 * turns * current / (gap + iron_path / mu_r)


def ccore_inductance(turns: float, area: float, gap: float, iron_path: float = 0.0, mu_r: float = 1e9) -> float:
    """C-core inductance: L = mu0 N^2 A / (g + l_fe / mu_r)  (H). Fringing makes FEMM's value
    larger (effective gap area > core area)."""
    return MU0 * turns ** 2 * area / (gap + iron_path / mu_r)


def reluctance(length: float, area: float, mu_r: float = 1.0) -> float:
    """R = l / (mu0 mu_r A)  (A-turn/Wb)."""
    return length / (MU0 * mu_r * area)


def maxwell_force(b: float, area: float) -> float:
    """Attraction across one pole face: F = B^2 A / (2 mu0)  (N). Two-gap circuits (C-core +
    armature) see twice this for the total force."""
    return b * b * area / (2.0 * MU0)


def carter_coefficient(slot_pitch: float, slot_opening: float, gap: float) -> float:
    """Carter coefficient k_c = tau_s / (tau_s - gamma g) with
    gamma = (4/pi) [ (b/2g) atan(b/2g) - ln sqrt(1 + (b/2g)^2) ]  (b = slot opening).
    Effective gap g_eff = k_c g."""
    u = slot_opening / (2.0 * gap)
    gamma = (4.0 / math.pi) * (u * math.atan(u) - math.log(math.sqrt(1.0 + u * u)))
    return slot_pitch / (slot_pitch - gamma * gap)


# ----------------------------------------------------------------------------- permanent magnets

def pm_load_line(br: float, mu_r: float, magnet_length: float, gap: float,
                 area_ratio: float = 1.0, leakage: float = 1.0, reluctance_factor: float = 1.0) -> dict:
    """Operating point of a linear magnet driving an air gap (Hendershot form).

    Permeance coefficient  Pc = (l_m / g) * (A_g / A_m) / (leakage * reluctance_factor)  with
    ``area_ratio = A_g / A_m``. Then  B_m = Br * Pc / (Pc + mu_r),  H_m = -(Br - B_m) / (mu0 mu_r),
    gap flux density B_g = B_m * A_m / A_g / leakage.
    Returns {Pc, Bm, Hm, Bg} in SI. Pc = -B_m / (mu0 H_m) at the operating point.
    """
    pc = (magnet_length / gap) * area_ratio / (leakage * reluctance_factor)
    bm = br * pc / (pc + mu_r)
    hm = -(br - bm) / (MU0 * mu_r)
    bg = bm / area_ratio / leakage
    return {"Pc": pc, "Bm": bm, "Hm": hm, "Bg": bg}


def spm_gap_b(br: float, mu_r: float, magnet_thickness: float, gap: float, carter: float = 1.0) -> float:
    """Surface-PM air-gap flux density (radial, flat approximation):
    B_g = Br * l_m / (l_m + mu_r * k_c * g)."""
    return br * magnet_thickness / (magnet_thickness + mu_r * carter * gap)


def spm_flux_linkage_fundamental(bg: float, radius: float, stack_length: float, pole_pairs: int,
                                 turns_per_phase: float, winding_factor: float = 1.0,
                                 magnet_arc_fraction: float = 1.0) -> float:
    """Peak PM flux linkage per phase of an SPM machine (fundamental only):
    B_1 = (4/pi) B_g sin(alpha pi / 2),  Phi_1 = 2 B_1 r L / p,  psi_1 = k_w N_ph Phi_1,
    where alpha is the magnet arc / pole pitch and N_ph the series turns per phase."""
    b1 = 4.0 / math.pi * bg * math.sin(magnet_arc_fraction * math.pi / 2.0)
    phi1 = 2.0 * b1 * radius * stack_length / pole_pairs
    return winding_factor * turns_per_phase * phi1


def demag_margin(bm: float, br: float) -> float:
    """Fraction of remanence still present at the operating point (B_m / Br). < 0.2 is a demag risk
    for ferrites and hot NdFeB; negative means the magnet is driven past zero flux."""
    return bm / br


# ----------------------------------------------------------------------------- machines

def dq_torque(pole_pairs: int, psi_d: float, psi_q: float, i_d: float, i_q: float) -> float:
    """Synchronous machine electromagnetic torque (amplitude-invariant dq):
    T = 3/2 p (psi_d i_q - psi_q i_d)  (N*m)."""
    return 1.5 * pole_pairs * (psi_d * i_q - psi_q * i_d)


def dq_torque_from_inductances(pole_pairs: int, psi_pm: float, ld: float, lq: float, i_d: float, i_q: float) -> float:
    """T = 3/2 p (psi_pm i_q + (L_d - L_q) i_d i_q)."""
    return 1.5 * pole_pairs * (psi_pm * i_q + (ld - lq) * i_d * i_q)


def emf_from_flux_linkage(psi_peak: float, rpm: float, pole_pairs: int) -> float:
    """Peak phase back-EMF of a sinusoidal flux linkage: E = omega_e psi = 2 pi p rpm/60 psi."""
    return 2.0 * math.pi * pole_pairs * rpm / 60.0 * psi_peak


def cogging_period_deg(slots: int, poles: int) -> float:
    """Mechanical cogging period = 360 / lcm(Q, 2p) degrees."""
    return 360.0 / math.lcm(int(slots), int(poles))


def park(ia: float, ib: float, ic: float, theta_e: float) -> tuple[float, float]:
    """Amplitude-invariant Park transform (theta_e in radians, phase B lags A by 120 deg):
    d = 2/3 [a cos t + b cos(t - 2pi/3) + c cos(t + 2pi/3)],
    q = -2/3 [a sin t + b sin(t - 2pi/3) + c sin(t + 2pi/3)]."""
    a2 = 2.0 * math.pi / 3.0
    d = 2.0 / 3.0 * (ia * math.cos(theta_e) + ib * math.cos(theta_e - a2) + ic * math.cos(theta_e + a2))
    q = -2.0 / 3.0 * (ia * math.sin(theta_e) + ib * math.sin(theta_e - a2) + ic * math.sin(theta_e + a2))
    return d, q


def inverse_park(i_d: float, i_q: float, theta_e: float) -> tuple[float, float, float]:
    """x_k = d cos(t - k 2pi/3) - q sin(t - k 2pi/3) for k = 0, 1, -1 (phases a, b, c)."""
    a2 = 2.0 * math.pi / 3.0
    out = []
    for sh in (0.0, a2, -a2):
        out.append(i_d * math.cos(theta_e - sh) - i_q * math.sin(theta_e - sh))
    return out[0], out[1], out[2]


# ----------------------------------------------------------------------------- electrostatics / conduction

def parallel_plate_capacitance(area: float, gap: float, eps_r: float = 1.0) -> float:
    """C = eps0 eps_r A / d  (F), no fringing."""
    return EPS0 * eps_r * area / gap


def coax_capacitance_per_length(inner_radius: float, outer_radius: float, eps_r: float = 1.0) -> float:
    """C' = 2 pi eps0 eps_r / ln(b/a)  (F/m)."""
    return 2.0 * math.pi * EPS0 * eps_r / math.log(outer_radius / inner_radius)


def bar_resistance(length: float, area: float, sigma: float) -> float:
    """R = l / (sigma A)  (Ohm); sigma in S/m (FEMM's MS/m * 1e6)."""
    return length / (sigma * area)


def skin_depth(freq: float, sigma: float, mu_r: float = 1.0) -> float:
    """delta = sqrt(2 / (omega mu sigma))  (m)."""
    return math.sqrt(2.0 / (2.0 * math.pi * freq * MU0 * mu_r * sigma))


def _bessel_j(n: int, z: complex, terms: int = 200) -> complex:
    """J_n(z) for complex z by power series (fine for |z| < ~25)."""
    s = 0j
    half = z / 2.0
    term = half ** n / math.factorial(n)
    for m in range(terms):
        s += term
        term *= -(half * half) / ((m + 1) * (m + 1 + n))
        if abs(term) < 1e-18 * max(abs(s), 1e-300) and m > 5:
            break
    return s


def round_wire_internal_impedance(radius: float, sigma: float, freq: float, mu_r: float = 1.0) -> complex:
    """Exact internal impedance per metre of an isolated round wire (no proximity effect):
    Z' = k J0(k a) / (2 pi a sigma J1(k a)),  k = (1 - j)/delta  (Ohm/m, e^{j w t} convention).
    Real part -> 1/(sigma pi a^2) at DC and -> 1/(sigma 2 pi a delta) when a >> delta;
    imaginary part / omega -> mu0/(8 pi) at DC."""
    if freq <= 0:
        return complex(1.0 / (sigma * math.pi * radius ** 2), 0.0)
    delta = skin_depth(freq, sigma, mu_r)
    k = (1 - 1j) / delta
    ka = k * radius
    if abs(ka) > 25:  # asymptotic: J0/J1 -> -j for this branch (surface impedance)
        zs = (1 + 1j) / (sigma * delta)
        return zs / (2.0 * math.pi * radius)
    return k * _bessel_j(0, ka) / (2.0 * math.pi * radius * sigma * _bessel_j(1, ka))


# ----------------------------------------------------------------------------- signal helpers

def harmonics(samples: Sequence[float], period_samples: int | None = None) -> dict:
    """Single-sided amplitude spectrum of one period of samples (endpoint excluded).

    Returns {"order": [0..N/2], "amplitude": [...], "phase_deg": [...], "thd": float}. Order 1 is
    the fundamental of the sampled period; amplitude[0] is the mean.
    """
    import numpy as np  # local import keeps the module importable without numpy

    x = np.asarray(samples, dtype=float)
    if period_samples:
        x = x[:period_samples]
    n = len(x)
    if n < 2:
        return {"order": [0], "amplitude": [float(x.mean()) if n else 0.0], "phase_deg": [0.0], "thd": 0.0}
    X = np.fft.rfft(x) / n
    amp = np.abs(X) * 2.0
    amp[0] = abs(X[0].real)
    if n % 2 == 0:
        amp[-1] /= 2.0
    ph = np.degrees(np.angle(X))
    fund = amp[1] if len(amp) > 1 else 0.0
    thd = float(np.sqrt(np.sum(amp[2:] ** 2)) / fund) if fund > 0 else 0.0
    return {"order": list(range(len(amp))), "amplitude": amp.tolist(), "phase_deg": ph.tolist(), "thd": thd}


ESTIMATES = {
    "solenoid_b_infinite": solenoid_b_infinite,
    "solenoid_b_axis_finite": solenoid_b_axis_finite,
    "thick_solenoid_b_center": thick_solenoid_b_center,
    "loop_b_axis": loop_b_axis,
    "solenoid_inductance_long": solenoid_inductance_long,
    "wire_inductance_per_length": wire_inductance_per_length,
    "straight_wire_b": straight_wire_b,
    "ccore_gap_b": ccore_gap_b,
    "ccore_inductance": ccore_inductance,
    "reluctance": reluctance,
    "maxwell_force": maxwell_force,
    "carter_coefficient": carter_coefficient,
    "pm_load_line": pm_load_line,
    "spm_gap_b": spm_gap_b,
    "spm_flux_linkage_fundamental": spm_flux_linkage_fundamental,
    "demag_margin": demag_margin,
    "dq_torque": dq_torque,
    "dq_torque_from_inductances": dq_torque_from_inductances,
    "emf_from_flux_linkage": emf_from_flux_linkage,
    "cogging_period_deg": cogging_period_deg,
    "parallel_plate_capacitance": parallel_plate_capacitance,
    "coax_capacitance_per_length": coax_capacitance_per_length,
    "bar_resistance": bar_resistance,
    "skin_depth": skin_depth,
    "round_wire_internal_impedance": round_wire_internal_impedance,
}
