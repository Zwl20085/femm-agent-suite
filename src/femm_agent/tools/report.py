"""Reporting tools: live health check, markdown reports, A/B comparison, file summaries, field maps."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .. import diagnostics, experiments, femfile, reporting
from ..sessions import Session
from ._common import ToolContext, ToolInputError, envelope, run_tool, session_estimates


def _saved_model(s: Session) -> str:
    """Path of the saved current document (saves into the work dir if it was never saved)."""
    if s.document:
        return s.document
    p = (s.work_dir / "model.fem").as_posix()
    s.pre_call("saveas", p)
    s.document = p
    return p


def register(mcp: Any, ctx: ToolContext) -> None:

    @mcp.tool()
    def femm_health_check(checks: list[str] | None = None, rotor_groups: list[int] | None = None,
                          stator_groups: list[int] | None = None, force_groups: list[int] | None = None,
                          reaction_groups: list[int] | None = None, flux_lines: list[list[list[float]]] | None = None,
                          b_limit: float = 1.8, session: str = "main") -> dict:
        """Judge a loaded magnetics solution against physics invariants. Needs the model saved and femm_solve done.
        `checks`: subset of mesh, precision, energy, saturation, boundary, torque, force, ac, flux, pm (default all
        that apply). `rotor_groups` / `stator_groups`: group numbers for the torque check (WST on one vs minus the
        other); `force_groups` / `reaction_groups`: same for force; `flux_lines`: [[[x1,y1],[x2,y2]],
        [[x3,y3],[x4,y4]]], two cuts that must carry equal flux; `b_limit`: saturation threshold in T (default
        1.8). Returns {checks: [{name, ok, value, expected, tolerance, message}], summary, facts}; summary.verdict
        is PASS (none failed, >= 1 passed, none inconclusive), CHECK (nothing applicable or some ok=null) or FAIL
        (any failed). Marks the session `checked` until the next solve/load. Invariants pass self-consistent wrong
        models: also compare a key number with femm_estimate(name, args, fem_value=...)."""
        def go(s: Session) -> Any:
            if s.physics != "magnetics":
                raise ToolInputError("femm_health_check covers magnetics models", "Open a .fem model and solve it.")
            path = _saved_model(s)
            res = diagnostics.run(s.link, path, checks, rotor_groups=rotor_groups, stator_groups=stator_groups,
                                  force_groups=force_groups, reaction_groups=reaction_groups, flux_lines=flux_lines,
                                  b_limit=b_limit)
            s.checked = True
            return res
        return run_tool(ctx, session, go, need="solution")

    @mcp.tool()
    def femm_report(title: str = "FEMM analysis report", include: list[str] | None = None,
                    experiment_files: list[str] | None = None, zoom: list[float] | None = None,
                    notes: str | None = None, session: str = "main") -> dict:
        """Write report.md + report.json (+ figures/field_B.png) to <work_dir>/reports/<YYYYMMDD-HHMMSS>/. Needs a
        model; the health and field sections also need a magnetics solution (femm_solve), else they are skipped
        and named in `warnings`. `include` (default all): model, health, field, experiments; `experiment_files`:
        result .json paths (default this session's experiments); `zoom` [xmin,xmax,ymin,ymax] for the |B| map;
        `notes` free text. Returns the written paths, warnings, experiments_included and `doubts`: reasons not to
        take the numbers at face value ("health check not run on this session", "no analytic estimate
        attached", "planar depth left at default", experiments with failing checks). Relay every doubt to the
        user; open report.md to read it."""
        inc = set(include or ["model", "health", "field", "experiments"])

        def go(s: Session) -> Any:
            out_dir = s.work_dir / "reports" / time.strftime("%Y%m%d-%H%M%S")
            out_dir.mkdir(parents=True, exist_ok=True)
            summary = checks = None
            depth_summary = None
            figs: list[tuple[str, str]] = []
            warnings: list[str] = []
            if s.physics:
                path = _saved_model(s)
                sol = femfile.solution_path(path)
                try:
                    depth_summary = femfile.parse_file(sol if (s.solved and sol.is_file()) else path).summary()
                except Exception as e:
                    warnings.append(f"model summary unreadable: {e}")
                if "model" in inc:
                    summary = depth_summary
                if s.solved and s.physics == "magnetics":
                    if "health" in inc:
                        try:
                            checks = diagnostics.run(s.link, path)["checks"]
                        except Exception as e:
                            warnings.append(f"health check skipped: {e}")
                    if "field" in inc:
                        try:
                            snap = experiments.field_snapshot(s.link, out_dir / "field_B.png", zoom=zoom)
                            if snap.get("png"):
                                figs.append((f"|B| (max {snap['B_max_T']:.3g} T, {snap['elements']} elements)", snap["png"]))
                        except Exception as e:
                            warnings.append(f"field map skipped: {e}")
                elif "health" in inc or "field" in inc:
                    warnings.append("no solution loaded: health and field sections skipped (call femm_solve)")
            exps = []
            if "experiments" in inc:
                for f in (experiment_files or s.notes.get("experiments", [])):
                    try:
                        exps.append(json.loads(Path(f).read_text(encoding="utf-8")))
                    except Exception as e:
                        warnings.append(f"could not read {f}: {e}")
            res = reporting.build_report(out_dir, title, model_summary=summary, experiments=exps, checks=checks or [],
                                         figures=figs, notes=notes)
            res["warnings"] = warnings
            res["experiments_included"] = len(exps)
            ran_health = bool(s.checked or checks)
            res["doubts"] = reporting.doubts(experiments=exps, checks=checks or [], model_summary=depth_summary,
                                             health_run=ran_health if s.physics == "magnetics" else None,
                                             estimates=session_estimates(ctx, s))
            return res
        return run_tool(ctx, session, go)

    @mcp.tool()
    def femm_compare_results(a: str, b: str, rtol: float = 0.02, label_a: str = "A", label_b: str = "B") -> dict:
        """A/B comparison of two experiment results (paths to the experiment .json files, or JSON
        text): every numeric summary value and every common numeric column (rows matched on the first
        column, e.g. angle). Use it to compare mesh refinements, the rotate vs air-gap-element
        methods, or two designs. Differences beyond `rtol` are flagged. `doubts` (per side) lists
        failing experiment checks, a planar depth left at 1 unit and the lack of an analytic
        reference: a match between two unchecked results proves nothing."""
        return envelope(lambda: reporting.compare_results(a, b, rtol, label_a, label_b))

    @mcp.tool()
    def femm_file_summary(path: str, arrays: bool = False) -> dict:
        """Parse a FEMM text file offline (no engine): .fem/.fee/.feh/.fec models or .ans/.res/.anh/.anc
        solutions. Returns problem definition, materials (with use counts, nonlinear/magnet flags),
        boundaries (type names, segment counts), circuits (net turns), groups, counts, bounding box,
        magnets. arrays=True on a solution also writes <stem>_mesh.npz (nodes, elements) next to it."""
        def go() -> Any:
            p = Path(path)
            if not p.is_file():
                raise ToolInputError(f"no such file: {path}", "Pass an absolute path to a FEMM model or solution file.")
            m = femfile.parse_file(p)
            out = m.summary()
            if arrays and m.solution is not None:
                import numpy as np

                npz = p.with_name(p.stem + "_mesh.npz")
                np.savez_compressed(npz, nodes=m.nodes(), elements=m.elements())
                out["arrays"] = {"npz": str(npz), "nodes_shape": list(m.nodes().shape),
                                 "elements_shape": list(m.elements().shape)}
            return out
        return envelope(go)

    @mcp.tool()
    def femm_plot_field(path: str | None = None, zoom: list[float] | None = None, save_arrays: bool = False,
                        session: str = "main") -> dict:
        """|B| colour map of the loaded magnetics solution rendered from the bulk mesh arrays (works
        headless, no GUI screenshot). `zoom` = [xmin, xmax, ymin, ymax] in problem units; default file
        <work_dir>/field_B.png; save_arrays also writes the nodes/elements/B arrays as .npz."""
        def go(s: Session) -> Any:
            p = Path(path) if path else s.work_dir / "field_B.png"
            if not p.is_absolute():
                p = s.work_dir / p
            npz = p.with_suffix(".npz") if save_arrays else None
            return experiments.field_snapshot(s.link, p, npz, zoom=zoom)
        return run_tool(ctx, session, go, need="solution")
