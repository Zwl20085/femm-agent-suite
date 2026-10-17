"""Standalone live smoke run (no pytest): build the server in-process, run the self-test and a
C-core model through the tool functions, print a short report.

    .venv\\Scripts\\python tests\\live\\smoke_server.py [work_dir]

Needs FEMM 5 (FEMM_DIR or a default install location). Exit code 0 when everything passed.
"""
import json
import sys
import tempfile
from pathlib import Path

from femm_agent.server import build_server
from femm_agent.sessions import SessionManager


def main() -> int:
    work = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="femm_smoke_"))
    _mcp, ctx = build_server(SessionManager(default_work_dir=work))
    t = ctx.extras["tools"]
    print("tools:", {g: len(v) for g, v in ctx.extras["groups"].items()}, "skipped:", ctx.extras["skipped_groups"])
    failures = 0

    def call(_name, **kw):
        nonlocal failures
        r = t[_name](**kw)
        if not r["ok"]:
            failures += 1
        print(("OK  " if r["ok"] else "ERR ") + _name, json.dumps(r.get("result", r.get("error")), default=str)[:300])
        return r.get("result")

    try:
        st = call("femm_status")
        if not st or not st["install"]["found"]:
            print("FEMM 5 not found")
            return 2
        call("femm_selftest")
        call("femm_new_document", physics="magnetics")
        call("femm_problem_define", units="mm", depth=50)
        call("femm_material_load", names=["Air", "Copper", "M-19 14 mil"])
        call("femm_draw_rectangle", x1=0, y1=0, x2=60, y2=60)
        call("femm_draw_rectangle", x1=15, y1=15, x2=45, y2=45)
        call("femm_draw_rectangle", x1=45, y1=29.5, x2=60, y2=30.5)
        call("femm_draw_rectangle", x1=16, y1=20, x2=22, y2=40)
        call("femm_draw_rectangle", x1=-8, y1=20, x2=-2, y2=40)
        call("femm_draw_circle", cx=30, cy=30, r=200, maxseg=2)
        call("femm_add_circuit", name="coil", current=2.0)
        for x, y in ((7, 7), (52, 50), (52, 10)):
            call("femm_add_block_label", x=x, y=y, material="M-19 14 mil", group=1)
        for x, y in ((52, 30), (30, 30), (-100, 30)):
            call("femm_add_block_label", x=x, y=y, material="Air")
        call("femm_add_block_label", x=19, y=30, material="Copper", circuit="coil", turns=100)
        call("femm_add_block_label", x=-5, y=30, material="Copper", circuit="coil", turns=-100)
        call("femm_add_boundary", name="A0", arcs=[[230, 30], [30, 230], [-170, 30], [30, -170]])
        call("femm_solve")
        call("femm_point_values", points=[[52.5, 30]])
        call("femm_circuit_results", name="coil")
        call("femm_field_stats", region="group:1")
    finally:
        ctx.sessions.close_all()
    print("failures:", failures, "work dir:", work)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
