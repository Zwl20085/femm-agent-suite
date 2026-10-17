"""Reporting tools: live health check, markdown reports, A/B comparison, file summaries, field maps."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .. import diagnostics, experiments, femfile, reporting
from ..sessions import Session
from ._common import ToolContext, ToolInputError, envelope, run_tool


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
        """Judge whether the loaded magnetics solution is physically sane. Needs femm_solve first.
        Runs (subset via `checks`): mesh (element count, worst triangle angle), precision, energy
        (W = W' and W = 1/2 sum I psi for linear models without magnets), saturation (share of steel
        above `b_limit` T; linear iron over 2.2 T), boundary (|B| at the outer boundary vs peak),
        torque (WST on rotor_groups vs -stator_groups; air-gap element torque if present), force
        (force_groups vs -reaction_groups), ac (1/2 Re(V conj I) = losses), flux (two cuts
        [[p1,p2],[p3,p4]] must carry the same flux), pm (magnet operating points).
        Returns {checks: [{name, ok, value, expected, tolerance, message}], summary, facts}."""
        def go(s: Session) -> Any:
            if s.physics != "magnetics":
                raise ToolInputError("femm_health_check covers magnetics models", "Open a .fem model and solve it.")
            path = _saved_model(s)
            return diagnostics.run(s.link, path, checks, rotor_groups=rotor_groups, stator_groups=stator_groups,
                                   force_groups=force_groups, reaction_groups=reaction_groups, flux_lines=flux_lines,
                                   b_limit=b_limit)
        return run_tool(ctx, session, go, need="solution")

    @mcp.tool()
    def femm_report(title: str = "FEMM analysis report", include: list[str] | None = None,
                    experiment_files: list[str] | None = None, zoom: list[float] | None = None,
                    notes: str | None = None, session: str = "main") -> dict:
        """Write report.md + report.json (+ figures/) to <work_dir>/reports/<timestamp>/.
        include (default all): "model" (parsed model summary), "health" (femm_health_check on the
        loaded solution), "field" (|B| map PNG from the bulk mesh arrays, `zoom` = [xmin, xmax, ymin,
        ymax] in problem units), "experiments" (this session's experiment results, or the result
        .json paths in `experiment_files`). Returns the paths; open report.md to read it."""
        inc = set(include or ["model", "health", "field", "experiments"])

        def go(s: Session) -> Any:
            out_dir = s.work_dir / "reports" / time.strftime("%Y%m%d-%H%M%S")
            out_dir.mkdir(parents=True, exist_ok=True)
            summary = checks = None
            figs: list[tuple[str, str]] = []
            warnings: list[str] = []
            if s.physics:
                path = _saved_model(s)
                if "model" in inc:
                    sol = femfile.solution_path(path)
                    summary = femfile.parse_file(sol if (s.solved and sol.is_file()) else path).summary()
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
            return res
        return run_tool(ctx, session, go)

    @mcp.tool()
    def femm_compare_results(a: str, b: str, rtol: float = 0.02, label_a: str = "A", label_b: str = "B") -> dict:
        """A/B comparison of two experiment results (paths to the experiment .json files, or JSON
        text): every numeric summary value and every common numeric column (rows matched on the first
        column, e.g. angle). Use it to compare mesh refinements, the rotate vs air-gap-element
        methods, or two designs. Differences beyond `rtol` are flagged."""
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
