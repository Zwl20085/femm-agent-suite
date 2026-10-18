"""Session tools: install status, engine sessions, and a known-answer self-test."""
from __future__ import annotations

import logging
import math
import time
from typing import Any

from .. import __version__, catalog, ipc, star
from ..config import femm_version
from ..materials import library
from ._common import ToolContext, ToolInputError, envelope, jsonable

_VERSION_CACHE: dict[str, Any] = {}
log = logging.getLogger("femm_agent")


def with_first_run_note(out: dict[str, Any]) -> dict[str, Any]:
    """Return `out` plus `first_run_note` on the first use on this machine (never raises)."""
    try:
        note = star.first_run_prompt()
    except Exception as e:  # the star offer must never break status or selftest
        log.warning("first-run check failed: %s", e)
        return out
    return {**out, "first_run_note": note} if note else out


def thick_solenoid_center_b(a: float, b: float, length: float, n_turns: float, current: float) -> float:
    """Analytic |B| (T) at the centre of a thick solenoid (SI units: radii and length in m).

    B0 = mu0 * J * l * ln[(b + sqrt(b^2 + l^2)) / (a + sqrt(a^2 + l^2))], l = length/2,
    J = N*I / ((b - a) * length).
    """
    mu0 = 4e-7 * math.pi
    l = length / 2.0
    j = n_turns * current / ((b - a) * length)
    return mu0 * j * l * math.log((b + math.sqrt(b * b + l * l)) / (a + math.sqrt(a * a + l * l)))


def run_selftest(ctx: ToolContext, session: str = "selftest", keep: bool = False, tolerance_pct: float = 3.0) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, **info: Any) -> None:
        checks.append({"check": name, "pass": bool(ok), **jsonable(info)})

    inst = ctx.sessions.install
    check("install_found", inst is not None, bin_dir=str(inst.bin_dir) if inst else None)
    if inst is None:
        return {"passed": False, "checks": checks}
    check("catalog_loaded", len(catalog.CATALOG) > 0, commands=len(catalog.CATALOG), warning=catalog.CATALOG.warning)
    lib = library(inst)
    sug = lib.suggest("M-19 Steel")
    check("material_rename_map", sug.get("best") == "M-19 14 mil", suggestion=sug.get("best"))

    t0 = time.time()
    try:
        ctx.sessions.close(session)
        s = ctx.sessions.open(session)
    except Exception as e:
        check("engine_launch", False, error=str(e))
        return {"passed": False, "checks": checks}
    check("engine_launch", s.link.ping(), seconds=round(time.time() - t0, 3), port=s.link.port)
    try:
        # thick solenoid, axisymmetric: a=10 mm, b=12 mm, length 100 mm, 500 turns, 1 A
        a, b, length, turns, cur = 10.0, 12.0, 100.0, 500, 1.0
        s.call("newdocument", 0)
        s.physics, s.document, s.solved = "magnetics", None, False
        s.call("mi_probdef", 0, "millimeters", "axi", 1e-8, 0, 30)
        for m in ("Air", "Copper"):
            s.call("mi_getmaterial", m)
        check("material_load", True, materials=["Air", "Copper"])
        try:
            s.call("mi_getmaterial", "M-19 Steel")
            check("error_path", False, note="FEMM accepted a FEMM 4.2 name; expected an error")
        except ipc.FemmError as e:
            check("error_path", "materials library" in e.message, message=e.message)
        s.call("mi_drawrectangle", a, -length / 2, b, length / 2)
        s.call("mi_addcircprop", "coil", cur, 1)
        s.call("mi_addblocklabel", (a + b) / 2, 0)
        s.call("mi_selectlabel", (a + b) / 2, 0)
        s.call("mi_setblockprop", "Copper", 1, 0, "coil", 0, 0, turns)
        s.call("mi_clearselected")
        s.call("mi_makeABC", 7, 300, 0, 0, 0)
        s.call("mi_addblocklabel", 5, 70)
        s.call("mi_selectlabel", 5, 70)
        s.call("mi_setblockprop", "Air", 1, 0, "", 0, 0, 0)
        s.call("mi_clearselected")
        path = (s.work_dir / "selftest_solenoid.fem").as_posix()
        s.call("mi_saveas", path)
        s.document = path
        t1 = time.time()
        s.call("mi_analyze", 1, timeout=120)
        s.call("mi_loadsolution")
        s.solved = True
        solve_s = time.time() - t1
        pv = s.call("mo_getpointvalues", 0, 0)
        b_fea = math.hypot(abs(pv[1]), abs(pv[2]))
        b_an = thick_solenoid_center_b(a / 1000, b / 1000, length / 1000, turns, cur)
        err = 100 * abs(b_fea - b_an) / b_an
        check("solenoid_B_centre", err <= tolerance_pct, fea_T=b_fea, analytic_T=b_an, error_pct=round(err, 3),
              tolerance_pct=tolerance_pct)
        ne = s.call("mo_numelements")
        check("solve_timing", solve_s < 30, seconds=round(solve_s, 3), elements=ne)
        j_expected = turns * cur / ((b - a) * length * 1e-6) / 1e6   # MA/m^2 (FEMM reports J in MA/m^2)
        pvc = s.call("mo_getpointvalues", (a + b) / 2, 0)
        check("current_density_units", abs(abs(pvc[8]) - j_expected) / j_expected < 0.01,
              Js_reported=pvc[8], J_expected_MA_per_m2=j_expected)
        allb = s.call("mo_getallb")
        alle = s.call("mo_getallelements")
        check("bulk_getters", isinstance(allb, list) and len(allb) == 2 * ne and len(alle) == 7 * ne,
              b_values=len(allb) if isinstance(allb, list) else None,
              element_values=len(alle) if isinstance(alle, list) else None, elements=ne)
        circ = s.call("mo_getcircuitproperties", "coil")
        flux = circ[2] if isinstance(circ, list) else None
        check("circuit_results", flux is not None and abs(flux) > 0, current=circ[0], volts=circ[1], flux_linkage_Wb=flux,
              inductance_H=(abs(flux) / cur if flux is not None else None))
    except Exception as e:
        check("model_run", False, error=f"{type(e).__name__}: {e}")
    finally:
        if not keep:
            ctx.sessions.close(session)
    passed = all(c["pass"] for c in checks)
    return {"passed": passed, "n_pass": sum(c["pass"] for c in checks), "n_checks": len(checks),
            "total_seconds": round(time.time() - t0, 3), "checks": checks,
            "session_kept": session if keep else None}


def register(mcp, ctx: ToolContext) -> None:
    @mcp.tool()
    def femm_status(check_version: bool = True) -> dict:
        """Where FEMM 5 is installed, its version, open sessions, work dir, catalog/material counts.

        Call this first. If `install.found` is false, nothing else can run: install FEMM 5
        (https://www.femm.info) or set FEMM_DIR to the folder holding femm_headless.
        `check_version` runs `femm_headless --version` once (cached, ~0.3 s)."""
        def run():
            inst = ctx.sessions.install
            info: dict[str, Any] = {"suite_version": __version__, "install": {"found": inst is not None}}
            if inst is not None:
                ver = _VERSION_CACHE.get(str(inst.bin_dir))
                if ver is None and check_version:
                    ver = femm_version(inst)
                    _VERSION_CACHE[str(inst.bin_dir)] = ver
                info["install"].update({
                    "bin_dir": str(inst.bin_dir), "headless": str(inst.headless),
                    "gui": str(inst.gui) if inst.gui else None, "version": ver,
                    "manual_pdf": str(inst.manual_pdf) if inst.manual_pdf else None,
                    "examples_dir": str(inst.examples_dir) if inst.examples_dir else None,
                    "pyfemm_dir": str(inst.pyfemm_dir) if inst.pyfemm_dir else None,
                })
            info["work_dir"] = str(ctx.sessions.default_work_dir)
            info["sessions"] = ctx.sessions.list()
            info["catalog"] = {"commands": len(catalog.CATALOG), "warning": catalog.CATALOG.warning}
            lib = library(inst)
            info["materials"] = {"counts": lib.counts(), "sources": lib.sources}
            info["tool_groups"] = ctx.extras.get("groups", {})
            return info
        return with_first_run_note(envelope(run))

    @mcp.tool()
    def femm_session_open(name: str = "main", headless: bool = True, port: int | None = None,
                          work_dir: str | None = None, attach: bool = False) -> dict:
        """Start (or reuse) a named FEMM engine. Every other tool takes `session` (default "main")
        and opens it lazily, so call this only to choose options.

        headless=True spawns femm_headlessw (no window, fastest). headless=False opens the
        femm_gui window: needed for femm_save_bitmap (screenshots are not written headless).
        attach=True connects to an engine already listening on `port` (e.g. a GUI the user
        started) instead of spawning one. `work_dir` is the engine's current directory; relative
        paths in other tools resolve there (default ~/femm-agent-work/<name>, env FEMM_AGENT_WORK)."""
        def run():
            s = ctx.sessions.open(name, headless=headless, port=port, work_dir=work_dir, attach=attach)
            return s.info()
        return {**envelope(run), "session": name}

    @mcp.tool()
    def femm_session_close(name: str = "main") -> dict:
        """Quit the FEMM engine of session `name` (unsaved work is lost: call femm_save first)."""
        return {**envelope(lambda: {"closed": ctx.sessions.close(name)}), "session": name}

    @mcp.tool()
    def femm_session_list() -> dict:
        """All open sessions: port, pid, physics, document, solved flag, call/error counts."""
        return envelope(lambda: ctx.sessions.list())

    @mcp.tool()
    def femm_selftest(keep_session: bool = False, tolerance_pct: float = 3.0) -> dict:
        """End-to-end check of the install with a known answer (~1-2 s). In a separate session
        "selftest" it builds an axisymmetric thick solenoid (a=10 mm, b=12 mm, L=100 mm, 500 turns,
        1 A), solves, and compares |B| at the centre with the analytic formula
        B0 = mu0*J*l*ln[(b+sqrt(b^2+l^2))/(a+sqrt(a^2+l^2))] (expect < 1 % error). Also checks
        library material loading, the error path for a FEMM 4.2 name, current-density units,
        bulk getters, circuit results and timing. Returns pass/fail per check."""
        return with_first_run_note(
            {**envelope(lambda: run_selftest(ctx, "selftest", keep_session, tolerance_pct)), "session": "selftest"})

    @mcp.tool()
    def femm_star_repo(action: str) -> dict:
        """Act on the user's answer to the one-time "star the repo on GitHub" offer
        (shown as `first_run_note` by femm_status / femm_selftest).

        ONLY call this after the user explicitly answered that question; never on your own.
        action: "star" (user said yes: stars through the GitHub CLI `gh` if installed and
        logged in, otherwise opens the repo page in the browser), "open" (just open the page),
        "dismiss" (user said no). Any answer is recorded and the offer is never shown again."""
        def run():
            if action not in star.ACTIONS:
                raise ToolInputError(f"unknown action {action!r}",
                                     'Use "star", "open" or "dismiss", matching what the user answered.')
            return star.star_repo(action)
        return envelope(run)
