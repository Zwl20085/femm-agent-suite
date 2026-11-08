"""Analytic layer tools: closed-form sanity estimates and unit conversions (no FEMM needed)."""
from __future__ import annotations

import inspect
from typing import Any

from .. import estimate_meta, health, units
from ._common import ToolContext, ToolInputError, envelope


def _doc(fn) -> str:
    return " ".join((inspect.getdoc(fn) or "").split())


def register(mcp: Any, ctx: ToolContext) -> None:

    @mcp.tool()
    def femm_estimate(name: str | None = None, args: dict | None = None, fem_value: float | None = None) -> dict:
        """Analytic sanity references in SI units (m, A, T, H, N, N*m). Call with no name to list every
        formula with its argument names, unit and expected FEM agreement. Examples:
        femm_estimate("ccore_gap_b", {"turns": 200, "current": 2, "gap": 0.002, "iron_path": 0.18, "mu_r": 2000});
        femm_estimate("dq_torque", {"poles": 4, "psi_d": 0.05, "psi_q": 0, "i_d": 0, "i_q": 10});
        femm_estimate("skin_depth", {"freq": 1000, "sigma": 58e6}). Pole counts: `poles` (= 2p, preferred)
        or `pole_pairs` (alias), exactly one. `carter_factor` is an alias of `carter_coefficient`.
        Returns {name, value, unit, formula, assumptions, expected_fea_tolerance_pct}. Pass your FEMM
        number as `fem_value` (same SI unit) to also get `verdict`: PASS (within the tolerance), CHECK
        (within 2x: explain the gap before using it) or FAIL, with diff_pct and the FEM/formula ratio -
        this replaces a separate femm_check_rule("compare_to_estimate", ...)."""
        def go() -> Any:
            if not name:
                # same shape as 0.1 ({name: {args, formula}}), richer entries
                return {k: {kk: v for kk, v in estimate_meta.describe(k).items() if kk != "name"}
                        for k in estimate_meta.names()}
            f = estimate_meta.function(name)
            if f is None:
                raise ToolInputError(f"unknown estimate {name!r}",
                                     f"Use one of {estimate_meta.names()} (femm_estimate() lists their arguments).")
            a = estimate_meta.normalize_args(name, args)
            try:
                v = f(**a)
            except TypeError as e:
                raise ToolInputError(str(e), f"Arguments of {name}: {estimate_meta.args_of(name)} (SI units).")
            out = estimate_meta.describe(name)
            out.pop("args", None)
            if fem_value is not None:
                out.update(estimate_meta.verdict(fem_value, v, out["expected_fea_tolerance_pct"]))
            if isinstance(v, complex):
                v = {"re": v.real, "im": v.imag}
            elif isinstance(v, tuple):
                v = list(v)
            return {"name": name, "value": v, **{k: x for k, x in out.items() if k != "name"}}
        return envelope(go)

    @mcp.tool()
    def femm_units_convert(conversion: str, value: float, from_unit: str | None = None, to_unit: str | None = None,
                           mu_r: float | None = None) -> dict:
        """Unit conversions used with FEMM. conversion='length' needs from_unit/to_unit among
        inches, millimeters, centimeters, mils, meters, micrometers (aliases mm, in, um ...).
        Others (value in, result out): deg2rad, rad2deg, rpm_to_rad_s, awg_diameter_mm (AWG gauge ->
        mm, pyFEMM AWG()), iec_diameter_mm, tesla_to_gauss, gauss_to_tesla, oersted_to_a_per_m,
        a_per_m_to_oersted, hc_from_br (T -> A/m, needs mu_r, default 1.05), br_from_hc,
        br_from_mgoe / hc_from_mgoe (grade -> Br or Hc for mi_addmaterial), mgoe_from_br,
        mgoe_to_j_per_m3."""
        def go() -> Any:
            f = units.CONVERSIONS.get(conversion)
            if f is None:
                raise ToolInputError(f"unknown conversion {conversion!r}", f"Use one of {sorted(units.CONVERSIONS)}.")
            if conversion == "length":
                if not from_unit or not to_unit:
                    raise ToolInputError("length conversion needs from_unit and to_unit", "e.g. from_unit='in', to_unit='mm'.")
                return {"value": f(value, from_unit, to_unit), "unit": units.normalize_length_unit(to_unit)}
            params = inspect.signature(f).parameters
            if "mu_r" in params and mu_r is not None:
                return {"value": f(value, mu_r=mu_r)}
            return {"value": f(value)}
        return envelope(go)

    @mcp.tool()
    def femm_check_rule(rule: str, args: dict | None = None) -> dict:
        """Run one pure physics rule on numbers you already have (no FEMM call, SI units). rule="list" lists them.
        Names include energy_consistency, power_balance_ac (alias power_balance), force_consistency. Examples:
        femm_check_rule("energy_consistency", {"energy":0.0149,"flux_linkages":[0.0149],"currents":[2]});
        femm_check_rule("power_balance_ac", {"p_input":1.2,"p_losses":1.19});
        femm_check_rule("force_consistency", {"f_a":-9.7,"f_b":-9.2,"tolerance":0.1}).
        Returns {name, ok, value, expected, tolerance, message}."""
        rules = {k: getattr(health, k) for k in (
            "energy_consistency", "energy_coenergy_linear", "flux_conservation", "saturation", "linear_material_overflux",
            "mesh_size", "mesh_quality", "solver_precision", "boundary_distance", "force_consistency",
            "curve_consistency", "torque_ripple", "zero_mean", "power_balance", "skin_depth_resolution",
            "pm_operating_point", "compare_to_estimate")}
        rules["power_balance_ac"] = rules.pop("power_balance")
        aliases = {"power_balance": "power_balance_ac"}

        def go() -> Any:
            if rule == "list":
                listed = {}
                for k, f in rules.items():
                    al = [a for a, t in aliases.items() if t == k]
                    key = f"{k} (alias: {', '.join(al)})" if al else k
                    listed[key] = {"args": list(inspect.signature(f).parameters), "doc": _doc(f)}
                return listed
            f = rules.get(aliases.get(rule, rule))
            if f is None:
                raise ToolInputError(f"unknown rule {rule!r}", "Call femm_check_rule('list').")
            try:
                return f(**(args or {}))
            except TypeError as e:
                raise ToolInputError(str(e), f"Arguments of {rule}: {list(inspect.signature(f).parameters)}")
        return envelope(go)
