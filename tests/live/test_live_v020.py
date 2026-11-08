"""Live checks behind the facts settled in 0.2.0 (docs/femm5-facts.md, "Settled in 0.2.0").

pytest -m live; FEMM 5 via FEMM_DIR or the default install folders.
"""
import math

import pytest

from femm_agent import benchmarks, femfile, ipc
from femm_agent.units import EPS0

pytestmark = pytest.mark.live


@pytest.fixture()
def link(femm_install):
    lk = ipc.launch(femm_install, port=ipc.pick_free_port(49850))
    yield lk
    lk.close()


def _first(v):
    return v[0] if isinstance(v, list) else v


def _bi(link, code, group):
    link.call("mo_clearblock")
    link.call("mo_groupselectblock", group)
    v = _first(link.call("mo_blockintegral", code))
    link.call("mo_clearblock")
    return v


def test_wst_torque_is_about_the_origin_ccw_positive(link, tmp_path):
    benchmarks.build_ccore(link, (tmp_path / "c.fem").as_posix(), gap=1.5)
    link.call("mi_analyze", 1)
    link.call("mi_loadsolution")
    t0, fx, fy = _bi(link, 22, 1), _bi(link, 18, 1), _bi(link, 19, 1)
    link.call("mo_close")
    link.call("mi_selectrectangle", -1000, -1000, 1000, 1000, 4)
    link.call("mi_movetranslate", 100, 0)                     # whole model +100 mm in x
    link.call("mi_clearselected")
    link.call("mi_saveas", (tmp_path / "c_shift.fem").as_posix())
    link.call("mi_analyze", 1)
    link.call("mi_loadsolution")
    t1 = _bi(link, 22, 1)
    assert abs(fy) > 1.0
    assert t1 == pytest.approx(t0 + 0.1 * fy - 0.0 * fx, rel=1e-3)   # r x F about (0, 0), +z = CCW


def test_ccore_benchmark_gap_is_per_gap(link, tmp_path):
    benchmarks.build_ccore(link, (tmp_path / "c.fem").as_posix(), gap=1.5)
    link.call("mi_analyze", 1)
    link.call("mi_loadsolution")
    left = link.call("mo_getpointvalues", -25, 40.75)
    right = link.call("mo_getpointvalues", 25, 40.75)
    assert math.hypot(left[1], left[2]) == pytest.approx(math.hypot(right[1], right[2]), rel=0.01)


def _coax(link, tmp_path, physics, depth=100.0, a=1.0, b=10.0):
    pre = {"electrostatics": "ei", "heatflow": "hi"}[physics]
    link.call("newdocument", {"electrostatics": 1, "heatflow": 2}[physics])
    link.call(f"{pre}_probdef", "millimeters", "planar", 1e-8, depth, 30)
    for r in (a, b):
        link.call(f"{pre}_drawarc", r, 0, -r, 0, 180, 1)
        link.call(f"{pre}_drawarc", -r, 0, r, 0, 180, 1)
    link.call(f"{pre}_addmaterial", "m", 1, 1, 0)
    link.call(f"{pre}_addconductorprop", "in", 1, 0, 1)
    link.call(f"{pre}_addconductorprop", "out", 0, 0, 1)
    for r, c in ((a, "in"), (b, "out")):
        for y in (r, -r):
            link.call(f"{pre}_selectarcsegment", 0, y)
            link.call(f"{pre}_setarcsegmentprop", 1, "", 0, 0, c)
            link.call(f"{pre}_clearselected")
    for (x, y), mat in (((5, 0), "m"), ((0, 0), "<No Mesh>")):
        link.call(f"{pre}_addblocklabel", x, y)
        link.call(f"{pre}_selectlabel", x, y)
        link.call(f"{pre}_setblockprop", mat, 1, 0, 0)
        link.call(f"{pre}_clearselected")
    ext = {"electrostatics": ".fee", "heatflow": ".feh"}[physics]
    link.call(f"{pre}_saveas", (tmp_path / f"coax{ext}").as_posix())
    link.call(f"{pre}_analyze", 1)
    link.call(f"{pre}_loadsolution")
    post = {"electrostatics": "eo", "heatflow": "ho"}[physics]
    return link.call(f"{post}_getconductorproperties", "in")


def test_planar_conductor_results_are_totals_over_depth(link, tmp_path):
    depth_m = 0.1
    q = _coax(link, tmp_path, "electrostatics")[1]
    assert q == pytest.approx(2 * math.pi * EPS0 / math.log(10) * depth_m, rel=0.01)
    h = _coax(link, tmp_path, "heatflow")[1]
    assert h == pytest.approx(2 * math.pi * 1.0 / math.log(10) * depth_m, rel=0.01)


def test_unassigned_edges_are_zero_flux(link, tmp_path):
    link.call("newdocument", 2)
    link.call("hi_probdef", "millimeters", "planar", 1e-8, 100, 30)
    link.call("hi_drawrectangle", 0, 0, 20, 10)
    link.call("hi_addmaterial", "k1", 1, 1, 0)
    link.call("hi_addboundprop", "hot", 0, 1, 0, 0, 0, 0, 0)
    link.call("hi_addboundprop", "cold", 0, 0, 0, 0, 0, 0, 0)
    for x, nm in ((0, "hot"), (20, "cold")):
        link.call("hi_selectsegment", x, 5)
        link.call("hi_setsegmentprop", nm, 0, 1, 0, 0, "")
        link.call("hi_clearselected")
    link.call("hi_addblocklabel", 10, 5)
    link.call("hi_selectlabel", 10, 5)
    link.call("hi_setblockprop", "k1", 1, 0, 0)
    link.call("hi_clearselected")
    link.call("hi_saveas", (tmp_path / "slab.feh").as_posix())
    link.call("hi_analyze", 1)
    link.call("hi_loadsolution")
    for x, t in ((5, 0.75), (15, 0.25)):
        for y in (0.2, 9.8):
            assert _first(link.call("ho_getpointvalues", x, y)) == pytest.approx(t, abs=1e-4)


def test_force_vs_position_leaves_the_saved_position_solved(tools):
    b = tools.ok("femm_build_benchmark", kind="ccore", params={"gap": 1.0}, session="fvp")
    probe = b["probe_gap_point"]
    s = tools.ok("femm_solve", session="fvp")
    assert s["checked"] is False and s["next"].startswith("femm_health_check(session='fvp'")
    b0 = tools.ok("femm_point_values", points=[probe], session="fvp")["values"][0]["|B|"]
    r = tools.ok("femm_experiment_force_vs_position", groups=[1], dy=0.25, steps=3, session="fvp")
    assert r["left_solved"] is True and r["health_summary"]["verdict"] == "PASS"
    b1 = tools.ok("femm_point_values", points=[probe], session="fvp")["values"][0]["|B|"]
    assert b1 == pytest.approx(b0, rel=1e-9)
    bad = tools("femm_experiment_force_vs_position", groups=[7], dy=0.25, steps=3, session="fvp")
    assert not bad["ok"] and "groups present in the model: [0, 1, 2, 3]" in bad["error"]["message"]


def test_inductance_currents_live(tools):
    tools.ok("femm_build_benchmark", kind="ccore", session="lofi")
    r = tools.ok("femm_experiment_inductance", currents=[0.5, 1, 2], session="lofi")
    ls = [row[3] for row in r["rows"]]
    assert max(ls) == pytest.approx(min(ls), rel=1e-6)               # linear iron: L independent of I
    est = tools.ok("femm_estimate", name="ccore_inductance",
                   args={"turns": 200, "area": 2e-4, "gap": 0.002, "iron_path": 0.18, "mu_r": 2000}, fem_value=ls[0])
    assert est["verdict"] in ("PASS", "CHECK") and est["ratio_fem_over_formula"] > 1     # fringing raises L


def test_planar_currentflow_current_is_total_over_depth(link, tmp_path):
    link.call("newdocument", 3)
    link.call("ci_probdef", "millimeters", "planar", 0, 1e-8, 100, 30)
    link.call("ci_drawrectangle", 0, 0, 20, 10)
    link.call("ci_addmaterial", "s1", 1, 1, 0, 0, 0, 0)          # 1 S/m
    link.call("ci_addconductorprop", "in", 1, 0, 1)
    link.call("ci_addconductorprop", "out", 0, 0, 1)
    for x, c in ((0, "in"), (20, "out")):
        link.call("ci_selectsegment", x, 5)
        link.call("ci_setsegmentprop", "", 0, 1, 0, 0, c)
        link.call("ci_clearselected")
    link.call("ci_addblocklabel", 10, 5)
    link.call("ci_selectlabel", 10, 5)
    link.call("ci_setblockprop", "s1", 1, 0, 0)
    link.call("ci_clearselected")
    link.call("ci_saveas", (tmp_path / "slab.fec").as_posix())
    link.call("ci_analyze", 1)
    link.call("ci_loadsolution")
    i = link.call("co_getconductorproperties", "in")[1]
    assert i == pytest.approx(1.0 * 1.0 / 0.020 * 0.010 * 0.100, rel=1e-3)   # sigma V / L x h x depth
