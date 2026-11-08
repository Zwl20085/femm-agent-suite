"""What each analytic estimate returns and how close a FEMM result should be (pure, no FEMM).

`expected_fea_tolerance_pct` is the agreement to expect between a correctly built FEMM model and the
formula: the formula's idealisation error (fringing, leakage, finite length, saturation), not solver
precision. Numbers come from this project's benchmarks (femm-health-check skill, rules.md, the
experiment checks); where no benchmark exists the default 10 % is used and the assumptions say so.

Verdict from a FEM value (see :func:`verdict`): PASS when |FEM - formula| / |formula| <= tol,
CHECK when it is within 2 x tol (larger than the idealisation explains: look for the cause before
using either number), FAIL beyond that (wrong units, wrong model or wrong formula).
"""
from __future__ import annotations

import inspect
import math
from typing import Any, Callable

from . import estimate

DEFAULT_TOL_PCT = 10.0
_NO_BENCH = f"no benchmark for this formula: default {DEFAULT_TOL_PCT:g} % tolerance"

# name -> (unit, assumptions, tolerance %, or None for the default)
META: dict[str, tuple[str, str, float | None]] = {
    "solenoid_b_infinite": ("T", "infinitely long thin solenoid; a real coil of length L / radius R < 10 reads lower "
                                 "at the centre (use solenoid_b_axis_finite)", None),
    "solenoid_b_axis_finite": ("T", "thin (single-layer) solenoid in air, on the axis", 2.0),
    "thick_solenoid_b_center": ("T", "uniform current density, air core, centre point; benchmark: femm_selftest "
                                     "solenoid 0.7 % (2 % allowed for coarse meshes)", 2.0),
    "loop_b_axis": ("T", "filamentary loop in air (wire radius << loop radius)", 2.0),
    "solenoid_inductance_long": ("H", "long-solenoid formula, no Nagaoka correction: short coils read lower in FEM", None),
    "wire_inductance_per_length": ("H/m", "round wire inside a coaxial return / A=0 circle, DC (uniform current)", 2.0),
    "straight_wire_b": ("T", "infinitely long straight wire, point outside the wire", 2.0),
    "ccore_gap_b": ("T", "no fringing, no leakage, uniform cross-section, unsaturated iron; benchmark ccore 1 % "
                         "(2 % allowed)", 2.0),
    "ccore_inductance": ("H", "no fringing and no leakage: FEM reads up to ~1.55x the formula on the ccore benchmark "
                              "(fringing widens the gap area), so the tolerance is wide", 60.0),
    "reluctance": ("A-turn/Wb", "uniform flux path, no fringing; " + _NO_BENCH, None),
    "maxwell_force": ("N", "uniform B over one pole face (two-gap circuits: twice this); benchmark ccore force 6 %", 6.0),
    "carter_coefficient": ("-", "2D conformal-map formula for open slots; FEM effective gap agrees to a few % on "
                                "plain slotted gaps; " + _NO_BENCH, None),
    "carter_factor": ("-", "alias of carter_coefficient; " + _NO_BENCH, None),
    "pm_load_line": ("{Pc: -, Bm: T, Hm: A/m, Bg: T}", "linear magnet, lumped circuit with leakage and reluctance "
                                                       "factors; " + _NO_BENCH, None),
    "spm_gap_b": ("T", "flat (unrolled) surface-PM gap, radial magnetisation, no slotting beyond the Carter factor; "
                       "the SPM benchmark gap field agrees to ~7 %", 15.0),
    "spm_flux_linkage_fundamental": ("Wb", "fundamental only, flat-gap SPM; leakage and slotting lower the FEM value; "
                                           "benchmark 7 %, the back-EMF experiment check allows 20 %", 20.0),
    "demag_margin": ("-", "ratio B_m / Br at the operating point (exact arithmetic, the inputs carry the error); "
                          + _NO_BENCH, None),
    "dq_torque": ("N*m", "amplitude-invariant dq, fundamental flux linkage; instantaneous FEM torque at one rotor "
                         "position differs by the ripple: compare the mean of a sweep (experiment check 8 %)", 8.0),
    "dq_torque_from_inductances": ("N*m", "constant Ld, Lq, psi_pm (no cross-saturation); the experiment check "
                                          "uses 15 % at one position", 15.0),
    "emf_from_flux_linkage": ("V", "sinusoidal flux linkage, peak phase EMF; " + _NO_BENCH, None),
    "cogging_period_deg": ("deg (mechanical)", "exact geometry: 360 / lcm(Q, 2p); a FEM period that differs means "
                                               "the model is not what you think; " + _NO_BENCH, None),
    "parallel_plate_capacitance": ("F", "no fringing: FEM is larger unless the plates are wide compared with the gap; "
                                        + _NO_BENCH, None),
    "coax_capacitance_per_length": ("F/m", "exact for coaxial cylinders; electrostatic spot checks agree within 1 % "
                                           "(2 % allowed)", 2.0),
    "bar_resistance": ("Ohm", "uniform current density (DC); current-flow spot checks within 1 % (2 % allowed)", 2.0),
    "skin_depth": ("m", "plane-wave skin depth of a good conductor; " + _NO_BENCH, None),
    "round_wire_internal_impedance": ("Ohm/m (complex)", "isolated round wire, exact Bessel solution; the AC sweep "
                                                         "R check uses 5 %", 5.0),
}

ALIASES = {"carter_factor": "carter_coefficient"}


def function(name: str) -> Callable[..., Any] | None:
    """The estimate function for `name` (aliases resolved), None if unknown."""
    return estimate.ESTIMATES.get(ALIASES.get(name, name))


def names() -> list[str]:
    return sorted(set(estimate.ESTIMATES) | set(ALIASES))


def args_of(name: str) -> list[str]:
    """Argument names, with `poles` listed first where the formula takes pole_pairs (poles preferred)."""
    params = list(inspect.signature(function(name)).parameters)
    if "pole_pairs" in params:
        params = ["poles (or pole_pairs)" if p == "pole_pairs" else p for p in params]
    return params


def formula_text(name: str) -> str:
    return " ".join((inspect.getdoc(function(name)) or "").split())


def tolerance_pct(name: str) -> float:
    tol = META.get(name, ("", "", None))[2]
    return DEFAULT_TOL_PCT if tol is None else tol


def describe(name: str) -> dict[str, Any]:
    unit, assumptions, _tol = META.get(name, ("SI", _NO_BENCH, None))
    out = {"name": name, "args": args_of(name), "unit": unit, "formula": formula_text(name),
           "assumptions": assumptions, "expected_fea_tolerance_pct": tolerance_pct(name)}
    if name in ALIASES:
        out["alias_of"] = ALIASES[name]
    return out


def normalize_args(name: str, args: dict | None) -> dict:
    """Copy of `args` with ``poles`` turned into ``pole_pairs`` for formulas that take pole pairs
    (exactly one of the two must be given). Formulas whose argument already is `poles`
    (cogging_period_deg) are left alone."""
    a = dict(args or {})
    params = inspect.signature(function(name)).parameters
    if "pole_pairs" in params and "poles" not in params:
        if "poles" in a or "pole_pairs" in a:
            a["pole_pairs"] = estimate.resolve_pole_pairs(a.pop("poles", None), a.pop("pole_pairs", None), name)
        else:
            raise estimate.EstimateInputError(f"{name} needs poles (2p) or pole_pairs", estimate.POLES_HINT)
    return a


def verdict(fem_value: float, value: float, tol_pct: float) -> dict[str, Any]:
    """PASS (<= tol), CHECK (<= 2 tol) or FAIL, with the relative difference and the ratio FEM / formula."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise estimate.EstimateInputError("fem_value needs a formula with one real result",
                                          "Compare a single component by hand with femm_check_rule('compare_to_estimate', ...).")
    fem = float(fem_value)
    den = abs(value) if value else max(abs(fem), 1e-300)
    rel = abs(fem - value) / den
    pct = 100.0 * rel
    word = "PASS" if pct <= tol_pct else ("CHECK" if pct <= 2 * tol_pct else "FAIL")
    out = {"verdict": word, "fem_value": fem, "diff_pct": pct, "ratio_fem_over_formula": (fem / value) if value else None,
           "tolerance_pct": tol_pct}
    if word == "CHECK":
        out["message"] = (f"FEM differs by {pct:.3g} %, more than the formula's {tol_pct:g} % idealisation error: find the "
                          "cause (units, depth, fringing, saturation) before using either number")
    elif word == "FAIL":
        out["message"] = (f"FEM differs by {pct:.3g} % (> 2 x {tol_pct:g} %): check units (SI here, problem units in FEMM), "
                          "the planar depth, turns and the formula choice")
    if math.isnan(pct):
        out["verdict"] = "FAIL"
    return out
