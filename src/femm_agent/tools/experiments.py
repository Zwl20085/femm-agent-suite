"""Experiment tools: standard magnetics tests run on the open model (each returns a table, files,
health checks and timings), plus benchmark-model builders for validation."""
from __future__ import annotations

import filecmp
import time
from pathlib import Path
from typing import Any, Callable

from .. import benchmarks, experiments, experiments_core
from ..sessions import Session
from ._common import ToolContext, ToolInputError, run_tool

MAX_ROWS_INLINE = 120


def _need_magnetics(s: Session) -> None:
    if s.physics not in (None, "magnetics"):
        raise ToolInputError(f"experiments need a magnetics model, this session has {s.physics}",
                             "Open or create a magnetics document (femm_new_document(physics='magnetics')).")
    if s.physics is None:
        raise ToolInputError("no document is open in this session",
                             "Call femm_new_document(physics='magnetics') or femm_open(path), or femm_build_benchmark(kind).")


def _run(s: Session, fn: Callable[..., dict], **kw: Any) -> dict:
    """Run one experiment and make the session state truthful afterwards: `solved` only when the
    experiment left a solution of the restored model loaded (``left_solved``; None = the
    experiment's own last solve is still loaded, e.g. bh_check), and `checked` False either way
    (an experiment's health_summary covers its own rules, not femm_health_check)."""
    _need_magnetics(s)
    was_checked = s.checked
    started = time.time()
    s.checked = False            # from here on FEMM solves other geometries / currents
    try:
        res = fn(s.link, out_dir=s.work_dir / "experiments", restore_path=s.document, **kw)
    except Exception as e:
        if getattr(e, "tool_input", False):
            s.checked = was_checked  # refused before any solve: the loaded solution is untouched
            _point_back(s, started)
        else:
            s.solved = False         # failed mid-sweep: what is loaded (if anything) is not the saved model
        raise
    s.document = res.get("document") or s.document
    s.solved = res.get("left_solved") is not False
    s.checked = False
    s.notes.setdefault("experiments", []).append(res["files"]["json"])
    out = _compact(res)
    if not s.solved:
        out = {**out, "next": f"femm_solve(session={s.name!r})  # the final re-solve failed; nothing is loaded"}
    return out


def _point_back(s: Session, started: float) -> None:
    """After a pre-flight refusal: the experiment had saved FEMM's document as a working copy, so
    FEMM's current file is that copy. Point it back at the session document without rewriting it
    when the document on disk equals the copy (close, re-open, reload the solution if one was
    loaded); only when they differ (unsaved edits) save the edits to the session document, which is
    what the next femm_solve would do anyway."""
    run = experiments_core.Run.last
    if (not s.document or run is None or run.t0 < started or run.ops.link is not s.link
            or run.restore_path != s.document):
        return                       # refused before this experiment saved a working copy
    doc = str(s.document).replace("\\", "/")
    try:
        same = Path(doc).is_file() and filecmp.cmp(run.model_path, doc, shallow=False)
    except OSError:
        same = False
    try:
        if same:
            s.link.call("mi_close")
            s.link.call("opendocument", doc)
            if s.solved:
                try:
                    s.link.call("mi_loadsolution")
                except Exception:
                    s.solved = False
        else:
            s.link.call("mi_saveas", doc)
    except Exception:
        pass


def _compact(res: dict) -> dict:
    rows = res.get("rows") or []
    if len(rows) > MAX_ROWS_INLINE:
        step = -(-len(rows) // MAX_ROWS_INLINE)
        res = dict(res)
        res["rows"] = rows[::step]
        res["rows_note"] = f"{len(rows)} rows, every {step}th shown; full table in files.csv"
    return res


def register(mcp: Any, ctx: ToolContext) -> None:

    @mcp.tool()
    def femm_experiment_force_vs_position(groups: list[int], dx: float = 0.0, dy: float = 0.0, steps: int = 11,
                                          force_groups: list[int] | None = None,
                                          start_offset: list[float] | None = None, session: str = "main") -> dict:
        """Move `groups` by (dx, dy) problem units per step (not both 0), re-solve, record WST force (codes 18/19 on
        `force_groups`, default `groups`), coenergy and circuit flux linkages; health: WST vs virtual work
        dW'/ds. `position` (problem units) = distance moved along (dx, dy) from the model AS SAVED plus
        `start_offset` [ox, oy]; it is not an absolute coordinate and not the gap: if the motion opens the gap,
        gap = g0 + position (g0 = gap in the saved model; a two-gap armature has total gap 2 (g0 + position)).
        Moving parts need air around them and their own group (femm_set_group); a group with no objects is
        refused before any solve, listing the groups present. Axisymmetric: x = r, y = z. Afterwards the geometry
        is moved back and the model re-solved at the saved position (verified on FEMM 5 build 20261101: B and
        force identical to the pre-experiment solve); result `left_solved` is true, or false with `next:
        femm_solve(...)` if that last solve failed. The session is left unchecked.
        Example: femm_experiment_force_vs_position(groups=[1], dy=0.25, steps=9). Returns rows
        [position, Fx, Fy, F_along_motion, F_virtual_work, coenergy, psi_*] and csv/json/png paths."""
        return run_tool(ctx, session, lambda s: _run(s, experiments.force_vs_position, groups=groups, dx=dx, dy=dy,
                                                     steps=steps, force_groups=force_groups,
                                                     start_offset=tuple(start_offset or (0.0, 0.0))), need="document")

    @mcp.tool()
    def femm_experiment_torque_vs_angle(rotate_groups: list[int], start: float = 0.0, stop: float = 90.0,
                                        steps: int = 19, angles: list[float] | None = None,
                                        center: list[float] | None = None, method: str = "rotate",
                                        gap_boundary: str | None = None, torque_groups: list[int] | None = None,
                                        drive: dict | None = None, session: str = "main") -> dict:
        """Rotor torque vs mechanical angle (degrees, end point included).

        method='rotate': rotates `rotate_groups` about `center` (default [0, 0]) each step and re-meshes;
        torque = WST block integral on `torque_groups` (default rotate_groups; exclude a rotor-side air
        layer from torque_groups). Needs an air layer split by a circle in the gap so the rotor can turn.
        method='age': the model has a FEMM 5 'Periodic Air Gap' boundary (BdryFormat 6) named
        `gap_boundary`; its inner angle is stepped and torque = mo_gapintegral (mesh never changes).
        `drive` = {"circuits": ["A","B","C"], "poles": 4, "id": 0, "iq": 10, "theta0_deg": 0} ("poles" = 2p
        preferred, "pole_pairs": p accepted, exactly one)
        makes the phase currents follow the rotor (amplitude-invariant dq; theta_e = p*angle + theta0)
        and adds a mean-torque check against 3/2 p (psi_d iq - psi_q id)."""
        return run_tool(ctx, session, lambda s: _run(s, experiments.torque_vs_angle, rotate_groups=rotate_groups,
                                                     angles=angles, start=start, stop=stop, steps=steps,
                                                     center=tuple(center or (0.0, 0.0)), method=method,
                                                     gap_boundary=gap_boundary, torque_groups=torque_groups,
                                                     drive=drive), need="document")

    @mcp.tool()
    def femm_experiment_cogging(rotate_groups: list[int], slots: int, poles: int | None = None, steps: int = 31,
                                periods: float = 1.0, center: list[float] | None = None, method: str = "rotate",
                                gap_boundary: str | None = None, torque_groups: list[int] | None = None,
                                pole_pairs: int | None = None, session: str = "main") -> dict:
        """Cogging torque: all circuit currents set to 0, torque over `periods` cogging periods
        (360/lcm(slots, poles) mech deg, `steps` samples incl. end point) and its harmonics.
        Give exactly one of `poles` (number of poles, 2p; preferred) or `pole_pairs` (p). `slots`
        and `poles` are full-machine counts. Same rotor options as femm_experiment_torque_vs_angle.
        Checks: zero mean, periodic end points, WST vs virtual work. Currents are restored."""
        return run_tool(ctx, session, lambda s: _run(s, experiments.cogging, rotate_groups=rotate_groups, slots=slots,
                                                     poles=poles, pole_pairs=pole_pairs, steps=steps, periods=periods,
                                                     center=tuple(center or (0.0, 0.0)), method=method,
                                                     gap_boundary=gap_boundary, torque_groups=torque_groups),
                        need="document")

    @mcp.tool()
    def femm_experiment_back_emf(rotate_groups: list[int], poles: int | None = None, pole_pairs: int | None = None,
                                 rpm: float = 1000.0, steps: int = 36,
                                 circuits: list[str] | None = None, center: list[float] | None = None,
                                 method: str = "rotate", gap_boundary: str | None = None,
                                 psi_estimate: float | None = None, session: str = "main") -> dict:
        """Open-circuit back-EMF: flux linkage of each circuit (default all) over one electrical period
        (720/poles mech deg, `steps` samples), EMF = omega * dpsi/dtheta (spectral derivative),
        fundamental / THD / harmonics / line-line EMF / Ke. Currents are zeroed and restored.
        Give exactly one of `poles` (number of magnet poles, 2p; preferred) or `pole_pairs` (p).
        Example: femm_experiment_back_emf(rotate_groups=[1, 10], poles=4, rpm=1500).
        `psi_estimate` (Wb, peak) adds an analytic comparison (femm_estimate spm_flux_linkage_fundamental).
        On a 1/N sector model (periodic boundaries) rows and summary are as drawn and `full_machine`
        gives the full-machine values (flux linkage and EMF x N; measured to 0.02 % on build 20261101).
        (Renamed from femm_experiment_backemf in 0.2.0.)"""
        return run_tool(ctx, session, lambda s: _run(s, experiments.back_emf, rotate_groups=rotate_groups,
                                                     poles=poles, pole_pairs=pole_pairs, rpm=rpm, steps=steps,
                                                     circuits=circuits,
                                                     center=tuple(center or (0.0, 0.0)), method=method,
                                                     gap_boundary=gap_boundary, psi_estimate=psi_estimate),
                        need="document")

    @mcp.tool()
    def femm_experiment_inductance(circuits: list[str] | None = None, current: float = 1.0, dq: dict | None = None,
                                   currents: list[float] | None = None,
                                   torque_groups: list[int] | None = None, gap_boundary: str | None = None,
                                   session: str = "main") -> dict:
        """Inductance from flux linkage. Default: self/mutual matrix L_jk = (psi_j(I_k=current) - psi_j(0)) / current
        for `circuits` (default all) - subtracting the zero-current solve removes magnet flux. Linear
        models get an energy check (W = 1/2 L I^2).
        L(I) mode: currents=[1, 2, 5, 10] (A) excites each circuit alone at each current and returns rows
        [circuit, current_A, psi_Wb, L_secant_H, L_incremental_H] (secant (psi(I)-psi(0))/I, incremental
        dpsi/dI by finite differences including the 0 A point) plus csv/json/png.
        dq mode: dq = {"circuits": ["A","B","C"], "poles": 4, "theta0_deg": 0, "id": 5, "iq": 5} ("poles"
        = 2p preferred, "pole_pairs" accepted)
        at the present rotor position (theta0 = electrical angle of the d-axis from phase A) gives
        psi_pm, Ld, Lq, saliency and the dq torque, checked against the FEM torque on `torque_groups`
        (WST) or `gap_boundary` (air-gap element)."""
        return run_tool(ctx, session, lambda s: _run(s, experiments.inductance, circuits=circuits, current=current,
                                                     dq=dq, currents=currents, torque_groups=torque_groups, gap_boundary=gap_boundary),
                        need="document")

    @mcp.tool()
    def femm_experiment_ac_sweep(frequencies: list[float], circuits: list[str] | None = None,
                                 current: float | None = None, session: str = "main") -> dict:
        """Time-harmonic frequency sweep (Hz): per frequency, circuit phasors (peak amplitudes) ->
        Z = V/I, R(f), L(f) = Im Z / omega, and losses (total / resistive / hysteresis) over all blocks.
        Check: 1/2 Re(V conj I) equals total losses. Other probdef settings are kept and the original
        frequency restored. `current` overrides every swept circuit's current. Conductors must have
        conductivity and the mesh must resolve the skin depth (femm_estimate skin_depth)."""
        return run_tool(ctx, session, lambda s: _run(s, experiments.ac_sweep, frequencies=frequencies,
                                                     circuits=circuits, current=current), need="document")

    @mcp.tool()
    def femm_experiment_parametric(cases: list[dict], outputs: list[dict], template: str | None = None,
                                   session: str = "main") -> dict:
        """Generic sweep: each case re-opens the saved base model, applies its setup, solves, collects outputs.
        case = {"name", "params": {...}, "commands": [{"command": "mi_modifycircprop", "args": ["A", 1, 5.0]}]}
        (pre-processor mi_/ei_/hi_/ci_ only). mi_modifycircprop propnum: 0 name, 1 current (A), 2 type (1 series,
        0 parallel). `template`: multi-line MicroPython run per case after the commands, formatted in the server
        with str.format(**params): double every literal brace ({{ }}) and give every {name} a key in params - a
        single brace or a missing key fails that case with KeyError in summary.errors (verified); the other
        cases still run. outputs: {"name", "kind": "point", "x", "y", "quantity": "B|Bx|By|A|H|mu|J"} |
        {"kind": "block", "code": 22, "groups": [1]} | {"kind": "circuit", "circuit": "A", "quantity":
        "flux|current|voltage|L|R"} | {"kind": "gap", "boundary": "AGE", "code": 0} | {"kind": "line",
        "points": [[x,y],...], "code": 3} | {"kind": "expr", "expression": "..."}. Rows are [case, params...,
        outputs...]; the plot x-axis is the first params key if numeric in every case. The model is reopened at
        the end."""
        return run_tool(ctx, session, lambda s: _run(s, experiments.parametric, cases=cases, outputs=outputs,
                                                     template=template), need="document")

    @mcp.tool()
    def femm_experiment_bh_check(min_fraction: float = 0.2, session: str = "main") -> dict:
        """Permanent-magnet operating points: solves, then per magnet block label the mean and minimum
        flux density along its magnetisation direction (B_m), H_m, permeance coefficient Pc and B_m/Br.
        Flags demagnetisation risk when min B_m < min_fraction * Br. Labels with a magdir formula are
        skipped."""
        return run_tool(ctx, session, lambda s: _run(s, experiments.bh_check, min_fraction=min_fraction),
                        need="document")

    @mcp.tool()
    def femm_build_benchmark(kind: str, path: str | None = None, params: dict | None = None,
                             session: str = "main") -> dict:
        """Build a validated benchmark model from scratch (new magnetics document, saved to `path`,
        default <work_dir>/<kind>.fem) and return its groups, circuits and analytic estimates:
        'ccore' (planar U-core + armature, groups armature=1 core=2 coil=3, circuit 'coil'),
        'coilgun' (axisymmetric coil + iron slug group 1), 'spm' (12-slot 4-pole surface PM machine;
        params {"sector": N} draws 1/N of it with (anti)periodic cut lines and an air-gap element, AGE
        route only, result `scale_to_full_machine` = N;
        params rotor_method='rotate'|'age', rotor groups [1,10] or AGE boundary 'AGE', circuits A/B/C),
        'round_wire' (copper wire in an A=0 circle for AC sweeps). `params` are the builder keyword
        arguments (e.g. {"gap": 0.5, "turns": 100}); see femm_agent.benchmarks."""
        def go(s: Session) -> Any:
            if kind not in benchmarks.BUILDERS:
                raise ToolInputError(f"unknown benchmark {kind!r}", f"Use one of {sorted(benchmarks.BUILDERS)}.")
            p = Path(path) if path else s.work_dir / f"{kind}.fem"
            if not p.is_absolute():
                p = s.work_dir / p
            p.parent.mkdir(parents=True, exist_ok=True)
            meta = benchmarks.BUILDERS[kind](s.link, p.as_posix(), **(params or {}))
            s.physics = "magnetics"
            s.document = p.as_posix()
            s.solved = False
            return meta
        return run_tool(ctx, session, go)
