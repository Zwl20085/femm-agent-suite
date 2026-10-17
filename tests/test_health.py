"""Offline tests for the pure physics rules in femm_agent.health."""
import math

import pytest

from femm_agent import health

KEYS = {"name", "ok", "value", "expected", "tolerance", "message"}


def test_shape_of_every_rule():
    checks = [
        health.energy_consistency(0.01, [0.01], [2.0]),
        health.energy_coenergy_linear(1.0, 1.0),
        health.flux_conservation(1e-3, 0.98e-3),
        health.saturation([1.0, 2.0], [1.0, 1.0]),
        health.linear_material_overflux([1.0, 2.5]),
        health.mesh_size(5000),
        health.mesh_quality([30, 25, 31]),
        health.solver_precision(1e-8),
        health.boundary_distance(0.001, 1.0),
        health.force_consistency(1.0, 1.02),
        health.curve_consistency([1, 2, 3], [1, 2, 3.1], "a", "b"),
        health.torque_ripple([1.0, 1.2, 0.9]),
        health.zero_mean([1, -1, 0.5, -0.5]),
        health.power_balance(1.0, 0.99),
        health.skin_depth_resolution(1e-3, 0.5e-3),
        health.pm_operating_point(0.9, 1.3, -3e5),
        health.compare_to_estimate("x", 1.0, 1.1),
        health.not_applicable("y", "because"),
    ]
    for c in checks:
        assert KEYS <= set(c), c
        assert c["ok"] in (True, False, None)


def test_energy_rules():
    # W = 1/2 L I^2 with L = psi / I
    assert health.energy_consistency(0.0149452, [0.0149452], [2.0])["ok"] is True
    assert health.energy_consistency(0.02, [0.0149452], [2.0])["ok"] is False
    assert health.energy_consistency(0.02, [0.01], [2.0], linear=False)["ok"] is None
    assert health.energy_consistency(0.0, [0.0], [0.0])["ok"] is None
    assert health.energy_coenergy_linear(1.0, 1.3)["ok"] is False
    assert health.energy_coenergy_linear(1.0, 1.3, linear=False)["ok"] is True
    assert health.energy_coenergy_linear(1.0, 0.8, linear=False)["ok"] is False
    assert health.energy_coenergy_linear(3.9, 9.3, linear=False, has_magnets=True)["ok"] is None


def test_saturation_and_mesh():
    r = health.saturation([1.0, 1.9, 2.0, 1.2], [1, 1, 1, 7], b_limit=1.8, max_fraction=0.05)
    assert r["value"] == pytest.approx(0.2) and r["ok"] is False
    assert health.saturation([], [])["ok"] is None
    assert health.mesh_size(200)["ok"] is False
    assert health.mesh_size(500_000)["ok"] is False
    nodes = [[0, 0], [1, 0], [0, 1], [10, 0.1]]
    ang = health.triangle_angles(nodes, [[0, 1, 2], [0, 1, 3]])
    assert ang[0] == pytest.approx(45)
    assert ang[1] < 1
    assert health.mesh_quality(ang)["ok"] is False
    assert health.solver_precision(1e-4)["ok"] is False


def test_boundary_and_flux():
    assert health.boundary_distance(0.1, 1.0)["ok"] is False
    assert health.boundary_distance(0.05, 1.0, has_open_boundary=True)["ok"] is True
    assert health.boundary_distance(0.5, 1.0, flux_contained=True)["ok"] is True
    assert health.flux_conservation(1.0, 0.8)["ok"] is False
    assert health.flux_conservation(1.0, 0.8, leakage_allowed=0.2)["ok"] is True


def test_force_and_virtual_work():
    # W'(x) = 0.5 k x^2 -> F = k x exactly with central differences
    xs = [0.001 * i for i in range(7)]
    k = 1234.0
    w = [0.5 * k * x * x for x in xs]
    f = health.virtual_work_derivative(xs, w)
    assert f[1:-1] == pytest.approx([k * x for x in xs[1:-1]])
    assert health.curve_consistency([k * x for x in xs[1:-1]], f[1:-1], "wst", "vw")["ok"] is True
    assert health.force_consistency(0.001, 0.0, scale=1.0)["ok"] is True
    assert health.force_consistency(1.0, 0.5)["ok"] is False


def test_cogging_rules_and_power():
    n = 24
    t = [math.sin(2 * math.pi * i / n) for i in range(n)]
    assert health.zero_mean(t)["ok"] is True
    assert health.zero_mean([x + 0.5 for x in t])["ok"] is False
    assert health.periodicity(t + [t[0]], n)["ok"] is True
    assert health.power_balance(1.0, 0.8)["ok"] is False
    assert health.skin_depth_resolution(1e-4, 1e-3)["ok"] is False


def test_pm_and_summary():
    assert health.pm_operating_point(0.1, 1.3)["ok"] is False
    r = health.pm_operating_point(0.92, 1.312, -2.95e5)
    assert r["ok"] is True and r["detail"]["permeance_coefficient"] == pytest.approx(2.48, rel=0.01)
    s = health.summarize([health.mesh_size(10), health.mesh_size(5000), health.not_applicable("x", "y")])
    assert s == {"total": 3, "passed": 1, "failed": 1, "not_applicable": 1, "failing": ["mesh_element_count"],
                 "all_ok": False}


# ============================================================================= live

@pytest.mark.live
def test_live_health_check_ccore(tmp_path):
    from femm_agent import benchmarks, config, diagnostics, ipc

    if config.find_femm() is None:
        pytest.skip("FEMM 5 not installed")
    link = ipc.launch(port=ipc.pick_free_port(49600))
    try:
        path = (tmp_path / "ccore.fem").as_posix()
        benchmarks.build_ccore(link, path)
        link.call("mi_analyze", 1)
        link.call("mi_loadsolution")
        # left gap and right gap carry the same flux (symmetry); armature force balances core + coil
        r = diagnostics.run(link, path, force_groups=[1], reaction_groups=[2, 3],
                            flux_lines=[[[-30, 40.5], [-20, 40.5]], [[20, 40.5], [30, 40.5]]])
        by = {c["name"]: c for c in r["checks"]}
        for name in ("energy_equals_coenergy", "energy_vs_flux_linkage", "force_y_action_reaction",
                     "flux_conservation", "mesh_min_angle", "outer_boundary_far_enough"):
            assert by[name]["ok"] is True, by[name]
        assert r["summary"]["failed"] == 0
        assert r["facts"]["force_N"][1] < 0  # the armature is pulled towards the core
    finally:
        link.close()
