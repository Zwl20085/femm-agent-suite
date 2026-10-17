"""Live tests of the core tool groups against a real FEMM 5 engine (pytest -m live).

Each model has an analytic or hand-calculable answer; tolerances are loose enough for FEA.
"""
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.live
MU0 = 4e-7 * math.pi
EPS0 = 8.8541878128e-12


def test_status_and_selftest(tools):
    st = tools.ok("femm_status")
    assert st["install"]["found"] and "v5" in (st["install"]["version"] or "")
    assert st["catalog"]["commands"] > 500
    r = tools.ok("femm_selftest")
    failed = [c for c in r["checks"] if not c["pass"]]
    assert r["passed"], failed
    b = next(c for c in r["checks"] if c["check"] == "solenoid_B_centre")
    assert b["error_pct"] < 2.0


def _c_core(tools, session="main"):
    """C-core, 1 mm gap in the right leg, 100 turns x 2 A around the left leg, depth 50 mm."""
    ok = tools.ok
    ok("femm_new_document", physics="magnetics", session=session)
    ok("femm_problem_define", units="mm", problem_type="planar", depth=50, session=session)
    r = ok("femm_material_load", names=["Air", "Copper", "M-19 Steel"], fallback_to_suggestion=True, session=session)
    assert r["renamed"] == {"M-19 Steel": "M-19 14 mil"}
    ok("femm_draw_rectangle", x1=0, y1=0, x2=60, y2=60, session=session)
    ok("femm_draw_rectangle", x1=15, y1=15, x2=45, y2=45, session=session)
    ok("femm_draw_rectangle", x1=45, y1=29.5, x2=60, y2=30.5, session=session)      # air gap
    ok("femm_draw_rectangle", x1=16, y1=20, x2=22, y2=40, session=session)          # coil side in window
    ok("femm_draw_rectangle", x1=-8, y1=20, x2=-2, y2=40, session=session)          # return side outside
    ok("femm_draw_circle", cx=30, cy=30, r=200, maxseg=2, session=session)
    ok("femm_add_circuit", name="coil", current=2.0, series=True, session=session)
    ok("femm_add_block_label", x=7, y=7, material="M-19 14 mil", group=1, session=session)
    ok("femm_add_block_label", x=52, y=50, material="M-19 14 mil", group=1, session=session)
    ok("femm_add_block_label", x=52, y=10, material="M-19 14 mil", group=1, session=session)
    ok("femm_add_block_label", x=52, y=30, material="Air", group=3, session=session)
    ok("femm_add_block_label", x=30, y=30, material="Air", session=session)
    ok("femm_add_block_label", x=19, y=30, material="Copper", circuit="coil", turns=100, group=2, session=session)
    ok("femm_add_block_label", x=-5, y=30, material="Copper", circuit="coil", turns=-100, group=2, session=session)
    ok("femm_add_block_label", x=-100, y=30, material="Air", session=session)
    ok("femm_add_boundary", name="A0", bc_type="prescribed_a",
       arcs=[[230, 30], [30, 230], [-170, 30], [30, -170]], session=session)


def test_c_core_magnetostatic(tools):
    ok = tools.ok
    _c_core(tools)
    g = ok("femm_geometry_summary")
    assert g["block_labels"] == 8 and g["arcs"] == 4 and "A0" in g["boundaries"]
    assert set(g["materials"]) >= {"Air", "Copper", "M-19 14 mil"} and g["circuits"] == ["coil"]
    s = ok("femm_solve", timeout=120)
    assert s["elements"] > 1000 and s["solution_file"]
    info = ok("femm_problem_info")
    assert info["input"]["depth_problem_units"] == 50 and info["solution"]["depth_m"] == pytest.approx(0.05)
    # gap flux density vs magnetic-circuit estimate mu0*N*I/g = 0.251 T (iron drop + fringing lower it)
    pv = ok("femm_point_values", points=[[52.5, 30], [7.5, 30], [1e4, 1e4]])
    b_gap = pv["values"][0]["|B|"]
    assert 0.15 < b_gap < 0.26, b_gap
    assert pv["values"][1]["|B|"] > 0.1                       # flux in the left leg
    assert pv["values"][2].get("outside") is True
    assert pv["units"]["J_source"] == "MA/m^2"
    # inductance: gap-only estimate N^2 mu0 A / g, fringing raises it, iron lowers it
    c = ok("femm_circuit_results", name="coil")
    l_est = 100 ** 2 * MU0 * (15e-3 * 50e-3) / 1e-3
    assert 0.7 * l_est < c["inductance_H"] < 1.6 * l_est, (c, l_est)
    assert c["resistance_ohm"] > 0
    # energy in the gap block ~ B^2/(2 mu0) * volume
    bi = ok("femm_block_integral", points=[[52, 30]], codes=[2, 5, 10])
    e_gap = bi["results"]["2: magnetic field energy"]
    vol = bi["results"]["10: block volume"]
    assert vol == pytest.approx(15e-3 * 1e-3 * 50e-3, rel=1e-6)
    assert e_gap == pytest.approx(b_gap ** 2 / (2 * MU0) * vol, rel=0.25)
    # flux through the left leg via a line integral = flux linkage / turns (roughly: leakage)
    li = ok("femm_line_integral", contour=[[0, 30], [15, 30]], codes=[0, 2])
    flux_leg = abs(li["results"]["0: B.n (total, average)"][0])
    assert flux_leg > 0
    fs = ok("femm_field_stats", region="group:1")
    assert fs["elements"] > 100 and 0.05 < fs["stats"]["mean"] < 1.0 and fs["saturated_area_fraction"] == 0
    ma = ok("femm_mesh_arrays", which="all", name="ccore")
    assert Path(ma["files"][0]).is_file()
    assert ma["arrays"]["elements"]["shape"][0] == s["elements"]
    assert ma["arrays"]["b"]["shape"] == [s["elements"], 2]
    assert ma["arrays"]["elements"]["index_base"] == 1        # node indices in getallelements are 1-based
    mp = ok("femm_make_plot", contour=[[0, 30], [60, 30]], plot_type=1, npts=60)
    assert mp["points"] == 60 and mp["header"] == ["Position", "|B|"] and mp["stats"]["max"] > 0.1


def test_call_eval_scripts_journal(tools, femm_install, tmp_path):
    ok = tools.ok
    r = tools("femm_call", command="mo_getb", args=[7.5, 30])   # pyFEMM-only helper: engine lacks it
    assert not r["ok"] and "pyFEMM helper" in r["error"]["hint"]
    r = ok("femm_call", command="mo_numelements")
    assert r["value"] > 1000 and r["read_only"] is True
    assert ok("femm_eval", expression="mo_getpointvalues(52.5,30)[2]")["value"] != 0
    assert ok("femm_eval", expression="[1, 2.5, 'x']")["value"] == [1, 2.5, "x"]
    assert not tools("femm_eval", expression="1\n2")["ok"]
    r = ok("femm_run_script", code="x = 0\nfor i in range(5):\n    x += i\nresult = [x, mo_numnodes()]\n")
    assert r["result"][0] == 10 and r["result"][1] > 100
    r = ok("femm_run_script", code="import sys\nprint('args', sys.argv[1:])\n", mode="batch", args=["a", "7"])
    assert r["exit_code"] == 0 and "['a', '7']" in r["stdout"]
    r = ok("femm_run_script", code="print('before')\nraise ValueError('boom')\n", mode="batch")
    assert r["exit_code"] == 1 and "boom" in r["stderr"]
    j = ok("femm_journal", limit=3, save=True)
    assert j["total"] > 20 and Path(j["file"]).is_file()
    ex = ok("femm_export_pyfemm_script")
    text = Path(ex["file"]).read_text()
    assert "femm.mi_probdef(" in text and "femm.openfemm(1)" in text


@pytest.mark.skipif(os.name != "nt", reason="femm-lua.bat is the Windows launcher")
def test_run_lua(tools, tmp_path):
    p = tmp_path / "t.lua"
    p.write_text('newdocument(0)\nmi_probdef(0,"millimeters","planar",1e-8,10,30)\nmi_addnode(0,0)\nprint("lua ok", 1+2)\n')
    r = tools.ok("femm_run_lua", path=str(p))
    assert r["exit_code"] == 0 and "lua ok" in r["stdout"]


def test_pyfemm_export_replays(server, tools, femm_install, tmp_path):
    """The exported pyFEMM script rebuilds and solves the C-core without the agent."""
    if femm_install.pyfemm_dir is None:
        pytest.skip("pyfemm binding not found in the install")
    _mcp, ctx = server
    ok = tools.ok
    ctx.sessions.close("replay")
    _c_core(tools, session="replay")
    ok("femm_solve", session="replay")
    out = tmp_path / "replay.py"
    ok("femm_export_pyfemm_script", path=str(out), session="replay")
    ctx.sessions.close("replay")
    text = out.read_text() .replace("femm.closefemm()", "femm.mi_loadsolution()\nprint('B', femm.mo_getpointvalues(52.5, 30)[2])\nfemm.closefemm()")
    out.write_text(text)
    env = dict(os.environ, PYTHONPATH=str(femm_install.pyfemm_dir))
    ctx.sessions.close_all()     # pyFEMM uses the default port
    r = subprocess.run([sys.executable, str(out)], capture_output=True, text=True, timeout=300, env=env, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr[-2000:]
    assert "B " in r.stdout


def test_editing_tools(tools):
    ok = tools.ok
    ok("femm_new_document", physics="magnetics")
    ok("femm_problem_define", units="mm", depth=10)
    ok("femm_draw_rectangle", x1=0, y1=0, x2=10, y2=10)
    ok("femm_select", kind="rectangle", rectangle=[-1, -1, 11, 11], entities="all")
    ok("femm_copy_selected", dx=20, dy=0, copies=2)
    g = ok("femm_geometry_summary")
    assert g["nodes"] == 12 and g["segments"] == 12, g
    ok("femm_select", kind="rectangle", rectangle=[39, -1, 51, 11])
    ok("femm_delete_selected")
    assert ok("femm_geometry_summary")["nodes"] == 8
    ok("femm_select", kind="segments", points=[[5, 0]])
    ok("femm_mirror_selected", x1=0, y1=-5, x2=10, y2=-5)
    assert ok("femm_geometry_summary")["segments"] == 9
    ok("femm_draw_polygon", points=[[100, 0], [110, 0], [105, 8]])
    ok("femm_draw_polyline", points=[[200, 0], [210, 0], [210, 10]])
    ok("femm_add_segments", segments=[[[300, 0], [310, 0]], [300, 5, 310, 5]])
    ok("femm_add_arcs", arcs=[[400, 0, 390, 10, 90, 2]])
    ok("femm_add_nodes", points=[[500, 500]])
    g = ok("femm_geometry_summary")
    assert g["arcs"] == 1 and g["nodes"] == 8 + 2 + 3 + 3 + 4 + 2 + 1
    # material modify propnum mapping is checked in the saved file
    ok("femm_material_add", name="mine", mu_x=1500, sigma=2, lam_d=0.35, lam_fill=0.97)
    ok("femm_material_modify", name="mine", changes={"mu_x": 900, "sigma": 3, "lam_fill": 0.95})
    ok("femm_material_add_bh", name="mine", points=[[0, 0], [1, 300], [1.5, 2000], [1.8, 20000]])
    ok("femm_add_block_label", x=5, y=5, material="mine")
    path = ok("femm_save", path="edit_test")["saved"]
    txt = Path(path).read_text()
    blk = txt[txt.index('<BlockName> = "mine"'):]
    blk = blk[: blk.index("<EndBlock>")]
    def val(key):
        return float(blk.split(f"<{key}> = ", 1)[1].split()[0])
    # verifies the xi_modifymaterial propnum map: 1 mu_x, 5 sigma, 8 lam_fill
    assert val("Mu_x") == 900 and val("Mu_y") == 1500 and val("Sigma") == 3 and val("LamFill") == pytest.approx(0.95), blk
    assert "<BHPoints> = 4" in blk
    ok("femm_close_document")
    assert not tools("femm_add_nodes", points=[[0, 0]])["ok"]


def test_gap_element(tools):
    """2-pole N42 rotor in an iron stator with a sliding-band air gap."""
    ok = tools.ok
    ok("femm_new_document", physics="magnetics")
    ok("femm_problem_define", units="mm", depth=50)
    ok("femm_material_load", names=["Air", "N42", "M-19 14 mil"])
    for r in (20, 21, 40, 60):
        ok("femm_draw_circle", cx=0, cy=0, r=r, maxseg=1)
    ok("femm_add_block_label", x=0, y=0, material="N42", magdir=0, group=1)
    ok("femm_add_block_label", x=30, y=0, material="M-19 14 mil", group=2)
    ok("femm_add_block_label", x=50, y=0, material="Air")
    ok("femm_add_block_label", x=20.5, y=0, material="<No Mesh>")
    c = math.cos(math.pi / 4)
    pts = lambda r: [[r * c, r * c], [-r * c, r * c], [-r * c, -r * c], [r * c, -r * c]]  # noqa: E731
    ok("femm_add_boundary", name="AGE", bc_type="periodic_air_gap", arcs=pts(20) + pts(21))
    ok("femm_add_boundary", name="A0", bc_type="prescribed_a", arcs=pts(60))
    ok("femm_solve")
    g = ok("femm_gap_results", boundary="AGE", angle=0, harmonics=3)
    assert 1.0 < g["at_angle"]["Br_T"] < 1.35
    assert abs(g["integrals"]["torque_dc_Nm"]) < 1e-3
    assert g["harmonics"]["largest"][0]["n"] == 1
    assert g["distribution"]["Br"]["max"] == pytest.approx(g["at_angle"]["Br_T"], rel=0.02)
    bad = ok("femm_gap_results", boundary="NOPE", harmonics=0)
    assert "warning" in bad


def _strip(tools, physics, material_kw, left, right, conductor_kind=None):
    ok = tools.ok
    ok("femm_new_document", physics=physics)
    ok("femm_problem_define", units="mm", depth=100)
    ok("femm_draw_rectangle", x1=0, y1=0, x2=10, y2=1)
    ok("femm_material_add", name="m", **material_kw)
    ok("femm_add_block_label", x=5, y=0.5, material="m")
    ok("femm_add_boundary", name="left", bc_type=left[0], value=left[1], segments=[[0, 0.5]])
    ok("femm_add_boundary", name="right", bc_type=right[0], value=right[1], segments=[[10, 0.5]])
    return ok("femm_solve")


def test_electrostatics_capacitor(tools):
    """Plates are the 10 mm sides (y=0 and y=1 mm), gap 1 mm, depth 100 mm, eps_r 4: C = eps A / d."""
    ok = tools.ok
    ok("femm_new_document", physics="electrostatics")
    ok("femm_problem_define", units="mm", depth=100)
    ok("femm_draw_rectangle", x1=0, y1=0, x2=10, y2=1)
    ok("femm_material_add", name="diel", eps_x=4)
    ok("femm_add_block_label", x=5, y=0.5, material="diel")
    ok("femm_add_conductor", name="gnd", fixed="voltage", value=0)
    ok("femm_add_conductor", name="hot", fixed="voltage", value=10)
    ok("femm_set_segment_prop", points=[[5, 0]], conductor="gnd")
    ok("femm_set_segment_prop", points=[[5, 1]], conductor="hot")
    ok("femm_solve")
    info = ok("femm_problem_info")
    assert info["solution"]["depth_m"] == pytest.approx(0.1)
    c_an = EPS0 * 4 * (10e-3 * 0.1) / 1e-3
    r = ok("femm_circuit_results", name="hot")
    assert r["voltage_V"] == pytest.approx(10)
    assert r["charge_C"] == pytest.approx(c_an * 10, rel=0.01)
    pv = ok("femm_point_values", points=[[5, 0.5]])["values"][0]
    assert pv["V"] == pytest.approx(5, rel=0.01) and pv["|E|"] == pytest.approx(10 / 1e-3, rel=0.01)
    bi = ok("femm_block_integral", points=[[5, 0.5]], codes=[0])
    energy = list(bi["results"].values())[0]
    energy = energy[0] if isinstance(energy, list) else energy     # eo_blockintegral(0) returns [W, 0]
    assert energy == pytest.approx(0.5 * c_an * 100, rel=0.01)
    fs = ok("femm_field_stats")
    assert fs["node_V"]["max"] == pytest.approx(10)


def test_heatflow_slab(tools):
    """k = 2 W/m/K slab, 10 mm long, 300 K -> 400 K: |F| = k dT / L = 2e4 W/m^2."""
    tools.ok
    _strip(tools, "heatflow", {"k_x": 2}, ("fixed_temperature", 300), ("fixed_temperature", 400))
    pv = tools.ok("femm_point_values", points=[[5, 0.5]])["values"][0]
    assert pv["T"] == pytest.approx(350, rel=1e-3)
    assert pv["|F|"] == pytest.approx(2e4, rel=0.01)


def test_currentflow_resistor(tools):
    """sigma = 1e6 S/m strip, 10 mm long, 1 V: |J| = sigma V / L = 1e8 A/m^2; I = J * 1 mm * 100 mm."""
    _strip(tools, "currentflow", {"sigma_x": 1e6}, ("fixed_voltage", 0), ("fixed_voltage", 1))
    pv = tools.ok("femm_point_values", points=[[5, 0.5]])["values"][0]
    assert pv["|J|"] == pytest.approx(1e8, rel=0.01)
    li = tools.ok("femm_line_integral", contour=[[5, 0], [5, 1]], codes=[1])
    i = list(li["results"].values())[0]
    i = i[0] if isinstance(i, list) else i
    i = i["re"] if isinstance(i, dict) else i
    assert abs(i) == pytest.approx(1e8 * 1e-3 * 0.1, rel=0.02)


@pytest.mark.skipif(bool(os.environ.get("FEMM_AGENT_NO_GUI")), reason="FEMM_AGENT_NO_GUI set")
def test_bitmap_needs_gui(server, tools):
    _mcp, ctx = server
    ok = tools.ok
    _c_core(tools)
    ok("femm_solve")
    r = tools("femm_save_bitmap", path="headless.png")
    assert not r["ok"] and "headless=False" in r["error"]["hint"]
    ok("femm_session_open", name="gui", headless=False)
    try:
        _c_core(tools, session="gui")
        ok("femm_solve", session="gui")
        post = ok("femm_save_bitmap", path="post.png", session="gui")
        pre = ok("femm_save_bitmap", path="pre.png", view="pre", session="gui")
        assert post["bytes"] > 10000 and pre["bytes"] > 10000 and post["bytes"] != pre["bytes"]
        with open(post["file"], "rb") as f:
            assert f.read(4) == b"\x89PNG"
    finally:
        ctx.sessions.close("gui")


def test_docs_tools(tools):
    ok = tools.ok
    assert ok("femm_api_search", query="air gap", physics="magnetics")["matches"]
    assert ok("femm_api_get", name="mo_blockintegral")["enums"]["type"]["2"]
    sec = ok("femm_manual_section", query="3.7.1", max_chars=2000)
    assert sec["match"] == "heading" and "Data Extraction" in sec["section"]
    kw = ok("femm_manual_section", query="mo_gapintegral")
    assert kw["snippets"]
    ex = ok("femm_examples_list", extension=".fem")
    assert ex["count"] >= 10


def test_errors_have_hints(tools):
    ok = tools.ok
    ok("femm_new_document", physics="magnetics")
    r = tools("femm_point_values", points=[[0, 0]])
    assert not r["ok"] and "femm_solve" in r["error"]["hint"]
    r = tools("femm_material_load", names=["NdFeB 32 MGOe"])
    assert r["ok"] and r["result"]["failed"][0]["best"] == "N33"
    r = tools("femm_open", path="does_not_exist.fem")
    assert not r["ok"] and r["error"]["hint"]
    r = tools("femm_add_boundary", name="x", bc_type="nonsense")
    assert not r["ok"] and "prescribed_a" in r["error"]["hint"]
