"""C-core actuator: build -> solve -> check -> force vs gap -> inductance -> report.

Uses the suite's Python API directly (no MCP client needed):

    python examples/ccore/run_ccore.py [--out DIR] [--iron "linear:2000" | "1010 Steel (hot rolled)"]

Everything is written under DIR (default: examples/ccore/out, git-ignored). The model is a planar
U-core with an I-armature above it (two 1 mm gaps), 200 turns on the base, 2 A, 20 mm deep.
Analytic references: B_g = mu0 N I / (2g + l_fe/mu_r), L = N^2 mu0 A / (2g + l_fe/mu_r),
F = 2 * B_g^2 A / (2 mu0).
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from femm_agent import benchmarks, diagnostics, estimate, experiments, ipc, reporting
from femm_agent.femfile import summarize_file
from femm_agent.units import MU0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(Path(__file__).parent / "out"))
    ap.add_argument("--iron", default="linear:2000", help="'linear:<mu_r>' or a FEMM 5 library steel name")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--docs-image", default=None, help="also copy the force plot here (used for the README)")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    link = ipc.launch(port=a.port or ipc.pick_free_port(49700), cwd=str(out))
    try:
        model = (out / "ccore.fem").as_posix()
        meta = benchmarks.build_ccore(link, model, iron=a.iron)
        link.call("mi_analyze", 1)
        link.call("mi_loadsolution")

        # 1. sanity: gap flux density vs the magnetic-circuit estimate
        x, y = meta["probe_gap_point"]
        pv = link.call("mo_getpointvalues", x, y)
        bg = abs(pv[2])
        est = meta["estimate"]
        print(f"gap B  FEM {bg:.4f} T   analytic {est['gap_B_T']:.4f} T")

        # 2. health check of the solved model (energy, mesh, boundary, force balance, flux symmetry)
        hc = diagnostics.run(link, model, force_groups=[1], reaction_groups=[2, 3],
                             flux_lines=[[[-30, 40.5], [-20, 40.5]], [[20, 40.5], [30, 40.5]]])
        for c in hc["checks"]:
            print(f"  {'PASS' if c['ok'] else ('n/a ' if c['ok'] is None else 'FAIL')} {c['name']}: {c['message']}")

        # 3. force vs gap (armature = group 1 moves up), with the analytic curve as a reference
        area, l_fe, mu_r = meta["core_area_m2"], meta["iron_path_mm"], meta["mu_r"]

        def f_analytic(s_mm: float) -> float:
            g = (meta["gap_mm"] + s_mm) * 1e-3
            b = estimate.ccore_gap_b(meta["turns"], meta["current"], 2 * g, l_fe * 1e-3, mu_r)
            return -2 * estimate.maxwell_force(b, area)

        fr = experiments.force_vs_position(link, [1], dy=0.25, steps=9, out_dir=out / "experiments",
                                           restore_path=model, estimate_fn=f_analytic)
        gaps = [meta["gap_mm"] + r[0] for r in fr["rows"]]
        from femm_agent import plotting

        png = plotting.plot_curves(out / "force_vs_gap.png", gaps,
                                   {"FEMM (weighted stress tensor)": [r[3] for r in fr["rows"]],
                                    "FEMM (virtual work dW'/dx)": [r[4] for r in fr["rows"]],
                                    "analytic B^2 A / mu0": [f_analytic(r[0]) for r in fr["rows"]]},
                                   title="C-core armature force vs gap", xlabel="gap (mm)", ylabel="force on armature (N)",
                                   dashed=("FEMM (virtual work dW'/dx)", "analytic B^2 A / mu0"))
        for g, r in zip(gaps, fr["rows"]):
            print(f"  gap {g:5.2f} mm  F_wst {r[3]:8.3f} N  F_vw {r[4]:8.3f} N  analytic {f_analytic(r[0]):8.3f} N")

        # 4. inductance (energy check W = 1/2 L I^2 included)
        ind = experiments.inductance(link, current=meta["current"], out_dir=out / "experiments", restore_path=model)
        L = ind["summary"]["self_H"]["coil"]
        print(f"L  FEM {L * 1e3:.3f} mH   analytic (no fringing/leakage) {est['inductance_H'] * 1e3:.3f} mH")

        # 5. field map + report
        link.call("mi_analyze", 1)
        link.call("mi_loadsolution")
        snap = experiments.field_snapshot(link, out / "field_B.png", zoom=[-45, 45, -25, 65])
        rep = reporting.build_report(out / "report", "C-core actuator", model_summary=summarize_file(model),
                                     experiments=[fr, ind], checks=hc["checks"],
                                     figures=[("|B| map", snap["png"]), ("force vs gap", png)],
                                     notes=f"Gap B: FEM {bg:.4f} T vs analytic {est['gap_B_T']:.4f} T. "
                                           f"L: FEM {L * 1e3:.3f} mH vs analytic {est['inductance_H'] * 1e3:.3f} mH "
                                           f"(fringing and slot leakage raise the FEM value). mu0 = {MU0:.6e}.")
        print("report:", rep["markdown"])
        (out / "summary.json").write_text(json.dumps({"gap_B_T": bg, "estimate": est, "L_H": L,
                                                      "force_rows": fr["rows"], "timing": fr["timing"]}, indent=1))
        if a.docs_image and png:
            shutil.copyfile(png, a.docs_image)
    finally:
        link.close()


if __name__ == "__main__":
    main()
