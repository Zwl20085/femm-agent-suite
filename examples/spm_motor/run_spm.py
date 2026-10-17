"""Surface-PM motor (12 slots / 4 poles): build -> check -> cogging (two rotor methods) -> back-EMF
-> Ld/Lq -> loaded torque -> magnet operating points -> report.

    python examples/spm_motor/run_spm.py [--out DIR] [--quick]

Everything is written under DIR (default: examples/spm_motor/out, git-ignored). The machine is
built from scratch with FEMM 5 library materials (M-19 14 mil, N42, Copper, Air): rotor radius
20 mm, 3 mm magnets, 1.5 mm gap, 50 mm outer radius, 50 mm stack, 20 turns per slot.
Two rotor-motion routes are run and compared:
  * 'rotate' - rotor groups are rotated and re-meshed each step (WST torque),
  * 'age'    - FEMM 5's periodic air-gap element boundary, stepped via mi_modifyboundprop(.., 10, angle)
               (mo_gapintegral torque; the mesh never changes).
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from femm_agent import benchmarks, diagnostics, estimate, experiments, ipc, reporting
from femm_agent.femfile import summarize_file


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(Path(__file__).parent / "out"))
    ap.add_argument("--quick", action="store_true", help="fewer steps")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--docs-image", default=None, help="also copy the |B| map here (used for the README)")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    exp_dir = out / "experiments"
    out.mkdir(parents=True, exist_ok=True)
    n_cog, n_emf, n_tq = (13, 18, 7) if a.quick else (31, 36, 13)

    link = ipc.launch(port=a.port or ipc.pick_free_port(49750), cwd=str(out))
    try:
        rot = (out / "spm.fem").as_posix()
        meta = benchmarks.build_spm(link, rot)
        est = meta["estimate"]
        print(f"analytic: Bg {est['gap_B_T']:.3f} T, psi_pm {est['psi_pm_peak_Wb'] * 1e3:.2f} mWb, "
              f"cogging period {est['cogging_period_deg']} deg, Carter {est['carter']:.3f}")
        link.call("mi_analyze", 1)
        link.call("mi_loadsolution")
        hc = diagnostics.run(link, rot, rotor_groups=[1], stator_groups=[2, 3])
        for c in hc["checks"]:
            print(f"  {'PASS' if c['ok'] else ('n/a ' if c['ok'] is None else 'FAIL')} {c['name']}: {c['message']}")
        snap = experiments.field_snapshot(link, out / "spm_field_B.png", title="SPM open-circuit |B| (T)")

        results = []
        cog_rot = experiments.cogging(link, [1, 10], torque_groups=[1], slots=12, poles=4, steps=n_cog,
                                      out_dir=exp_dir, restore_path=rot, tag="rotate")
        results.append(cog_rot)
        emf = experiments.backemf(link, [1, 10], pole_pairs=2, rpm=1000, steps=n_emf, out_dir=exp_dir,
                                  restore_path=rot, psi_estimate=est["psi_pm_peak_Wb"])
        results.append(emf)
        ldq = experiments.inductance(link, dq={"circuits": ["A", "B", "C"], "pole_pairs": 2, "id": 5, "iq": 5},
                                     torque_groups=[1], out_dir=exp_dir, restore_path=rot)
        results.append(ldq)
        tq = experiments.torque_vs_angle(link, [1, 10], torque_groups=[1], start=0, stop=30, steps=n_tq,
                                         drive={"circuits": ["A", "B", "C"], "pole_pairs": 2, "id": 0, "iq": 10},
                                         out_dir=exp_dir, restore_path=rot)
        results.append(tq)
        pm = experiments.bh_check(link, out_dir=exp_dir, restore_path=rot)
        results.append(pm)

        # the same machine with a periodic air-gap element
        age = (out / "spm_age.fem").as_posix()
        benchmarks.build_spm(link, age, rotor_method="age")
        cog_age = experiments.cogging(link, [1], slots=12, poles=4, steps=n_cog, method="age", gap_boundary="AGE",
                                      out_dir=exp_dir, restore_path=age, tag="age")
        results.append(cog_age)
        cmp = reporting.compare_results(cog_rot, cog_age, rtol=0.05, label_a="rotate", label_b="age")

        s_emf, s_ldq = emf["summary"], ldq["summary"]
        psi = s_emf["psi_fundamental_Wb"]["A"]
        lines = [
            f"cogging p-p: rotate {cog_rot['summary']['peak_to_peak_Nm']:.4f} N*m, "
            f"age {cog_age['summary']['peak_to_peak_Nm']:.4f} N*m ({cog_rot['timing']['per_solve_s']} vs "
            f"{cog_age['timing']['per_solve_s']} s per solve)",
            f"psi_pm fundamental {psi * 1e3:.2f} mWb (analytic {est['psi_pm_peak_Wb'] * 1e3:.2f}), "
            f"EMF {s_emf['emf_fundamental_peak_V']['A']:.3f} V peak at 1000 rpm, THD {s_emf['emf_thd']['A']:.1%}",
            f"Ld {s_ldq['Ld_H'] * 1e3:.3f} mH, Lq {s_ldq['Lq_H'] * 1e3:.3f} mH, psi_pm(dq) {s_ldq['psi_pm_Wb'] * 1e3:.2f} mWb",
            f"loaded torque (iq = 10 A): mean {tq['summary']['mean_torque_Nm']:.3f} N*m, "
            f"dq estimate {estimate.dq_torque(2, psi, 0, 0, 10):.3f} N*m, ripple {tq['summary']['peak_to_peak_Nm']:.3f} N*m",
            f"magnets: worst B_m {pm['summary']['worst_Bm_min_T']:.3f} T, mean Pc {pm['summary']['mean_Pc']:.2f}",
        ]
        for line in lines:
            print(line)
        rep = reporting.build_report(out / "report", "SPM motor, 12 slots / 4 poles", model_summary=summarize_file(rot),
                                     experiments=results, checks=hc["checks"], figures=[("open-circuit |B|", snap["png"])],
                                     notes="\n".join("- " + x for x in lines))
        print("report:", rep["markdown"])
        (out / "summary.json").write_text(json.dumps({"lines": lines, "compare_rotate_vs_age": cmp,
                                                      "estimate": est}, indent=1, default=str))
        if a.docs_image and snap.get("png"):
            shutil.copyfile(snap["png"], a.docs_image)
    finally:
        link.close()


if __name__ == "__main__":
    main()
