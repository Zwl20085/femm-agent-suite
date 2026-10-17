"""Unit conversions used by FEMM models (pure, no FEMM needed).

FEMM draws geometry in "problem units" chosen by ``mi_probdef(freq, units, ...)``: one of
``inches, millimeters, centimeters, mils, meters, micrometers`` (the file format also writes
``microns``). Every postprocessor result is SI (T, A/m, Wb, N, N*m, J, W), except source current
density ``Js`` in ``mo_getpointvalues`` and ``J`` in ``mi_addmaterial`` which are MA/m^2 (= A/mm^2),
and conductivity in ``mi_addmaterial`` which is MS/m.
"""
from __future__ import annotations

import math

MU0 = 4e-7 * math.pi            # H/m (FEMM uses the classical value)
EPS0 = 8.8541878128e-12         # F/m

LENGTH_TO_M = {
    "inches": 0.0254,
    "millimeters": 1e-3,
    "centimeters": 1e-2,
    "mils": 2.54e-5,
    "meters": 1.0,
    "micrometers": 1e-6,
    "microns": 1e-6,
}

_ALIASES = {
    "in": "inches", "inch": "inches", '"': "inches",
    "mm": "millimeters", "millimeter": "millimeters", "millimetres": "millimeters", "millimetre": "millimeters",
    "cm": "centimeters", "centimeter": "centimeters", "centimetres": "centimeters", "centimetre": "centimeters",
    "mil": "mils", "thou": "mils",
    "m": "meters", "meter": "meters", "metres": "meters", "metre": "meters",
    "um": "micrometers", "µm": "micrometers", "micrometer": "micrometers", "micron": "microns",
    "micrometres": "micrometers", "micrometre": "micrometers",
}


def normalize_length_unit(unit: str) -> str:
    """Return the FEMM spelling of a length unit (``'mm' -> 'millimeters'``). Raises ValueError."""
    u = unit.strip().lower()
    u = _ALIASES.get(u, u)
    if u not in LENGTH_TO_M:
        raise ValueError(f"unknown length unit {unit!r}; FEMM accepts {sorted(set(LENGTH_TO_M) - {'microns'})}")
    return u


def length_factor(unit: str) -> float:
    """Metres per one problem unit: ``length_factor('inches') == 0.0254``."""
    return LENGTH_TO_M[normalize_length_unit(unit)]


def to_meters(value: float, unit: str) -> float:
    return value * length_factor(unit)


def from_meters(value_m: float, unit: str) -> float:
    return value_m / length_factor(unit)


def convert_length(value: float, from_unit: str, to_unit: str) -> float:
    """``convert_length(1, 'inches', 'millimeters') == 25.4``."""
    return value * length_factor(from_unit) / length_factor(to_unit)


def area_factor(unit: str) -> float:
    """m^2 per (problem unit)^2."""
    return length_factor(unit) ** 2


# ----------------------------------------------------------------------------- angles

def deg2rad(d: float) -> float:
    return d * math.pi / 180.0


def rad2deg(r: float) -> float:
    return r * 180.0 / math.pi


def rpm_to_rad_s(rpm: float) -> float:
    """Mechanical speed: rev/min -> rad/s."""
    return rpm * 2.0 * math.pi / 60.0


def electrical_frequency(rpm: float, pole_pairs: int) -> float:
    """f_e = p * rpm / 60 (Hz)."""
    return pole_pairs * rpm / 60.0


# ----------------------------------------------------------------------------- wire gauges

def awg_diameter_mm(awg: float) -> float:
    """Bare copper diameter (mm) of an AWG gauge: d = 8.2514694 * exp(-0.115943 * AWG).

    Same fit as pyFEMM's ``AWG()``; matches the ASTM B258 formula 0.127 mm * 92^((36-AWG)/39)
    to < 0.1 %. Gauges 0000..00 are -3..-1.
    """
    return 8.2514694 * math.exp(-0.115943 * awg)


def iec_diameter_mm(iec: float) -> float:
    """Diameter (mm) for an IEC 60228-style gauge index: d = 7.959159641581004 * exp(-0.11519673572274754 * n).

    Same fit as pyFEMM's ``IEC()`` helper.
    """
    return 7.959159641581004 * math.exp(-0.11519673572274754 * iec)


def awg_area_mm2(awg: float) -> float:
    d = awg_diameter_mm(awg)
    return math.pi * d * d / 4.0


def nearest_awg(diameter_mm: float) -> int:
    """Inverse of :func:`awg_diameter_mm`, rounded to the nearest integer gauge."""
    return int(round(-math.log(diameter_mm / 8.2514694) / 0.115943))


# ----------------------------------------------------------------------------- magnetics

def tesla_to_gauss(b: float) -> float:
    return b * 1e4


def gauss_to_tesla(g: float) -> float:
    return g * 1e-4


def oersted_to_a_per_m(oe: float) -> float:
    """1 Oe = 1000/(4 pi) A/m ~= 79.577 A/m."""
    return oe * 1000.0 / (4.0 * math.pi)


def a_per_m_to_oersted(h: float) -> float:
    return h * 4.0 * math.pi / 1000.0


def hc_from_br(br: float, mu_r: float = 1.05) -> float:
    """Coercivity (A/m) of a linear magnet with remanence Br (T) and recoil permeability mu_r:
    Hc = Br / (mu0 * mu_r). This is the H_c FEMM wants in ``mi_addmaterial``."""
    return br / (MU0 * mu_r)


def br_from_hc(hc: float, mu_r: float = 1.05) -> float:
    """Br = mu0 * mu_r * Hc."""
    return MU0 * mu_r * hc


def bhmax_from_br(br: float, mu_r: float = 1.05) -> float:
    """(BH)max in J/m^3 of a linear magnet: Br^2 / (4 mu0 mu_r)."""
    return br * br / (4.0 * MU0 * mu_r)


def mgoe_to_j_per_m3(mgoe: float) -> float:
    """1 MGOe = 1e6 G*Oe = 1e6 * 1e-4 T * 79.577 A/m = 7957.7 J/m^3."""
    return mgoe * 1e6 * 1e-4 * 1000.0 / (4.0 * math.pi)


def j_per_m3_to_mgoe(e: float) -> float:
    return e / mgoe_to_j_per_m3(1.0)


def br_from_mgoe(mgoe: float, mu_r: float = 1.05) -> float:
    """Remanence (T) of a linear magnet whose (BH)max is ``mgoe``: Br = sqrt(4 mu0 mu_r (BH)max).

    Example: N42 (42 MGOe, mu_r 1.05) -> ~1.33 T; FEMM 4.2's old "NdFeB 32 MGOe" -> ~1.16 T.
    """
    return math.sqrt(4.0 * MU0 * mu_r * mgoe_to_j_per_m3(mgoe))


def hc_from_mgoe(mgoe: float, mu_r: float = 1.05) -> float:
    """Coercivity (A/m) for :func:`br_from_mgoe`."""
    return hc_from_br(br_from_mgoe(mgoe, mu_r), mu_r)


def mgoe_from_br(br: float, mu_r: float = 1.05) -> float:
    return j_per_m3_to_mgoe(bhmax_from_br(br, mu_r))


# ----------------------------------------------------------------------------- other

def ms_per_m_to_s_per_m(ms: float) -> float:
    """FEMM conductivities are entered in MS/m."""
    return ms * 1e6


def current_density_a_mm2(current_a: float, area_mm2: float) -> float:
    """A/mm^2 == MA/m^2, FEMM's unit for source current density."""
    return current_a / area_mm2


CONVERSIONS = {
    "length": convert_length,
    "deg2rad": deg2rad,
    "rad2deg": rad2deg,
    "rpm_to_rad_s": rpm_to_rad_s,
    "awg_diameter_mm": awg_diameter_mm,
    "iec_diameter_mm": iec_diameter_mm,
    "tesla_to_gauss": tesla_to_gauss,
    "gauss_to_tesla": gauss_to_tesla,
    "oersted_to_a_per_m": oersted_to_a_per_m,
    "a_per_m_to_oersted": a_per_m_to_oersted,
    "hc_from_br": hc_from_br,
    "br_from_hc": br_from_hc,
    "br_from_mgoe": br_from_mgoe,
    "hc_from_mgoe": hc_from_mgoe,
    "mgoe_from_br": mgoe_from_br,
    "mgoe_to_j_per_m3": mgoe_to_j_per_m3,
}
