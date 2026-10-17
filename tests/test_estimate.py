"""Offline tests for the analytic references in femm_agent.estimate."""
import math

import pytest

from femm_agent import estimate
from femm_agent.units import MU0


def test_solenoids_and_loops():
    assert estimate.solenoid_b_infinite(1000, 1, 1) == pytest.approx(MU0 * 1000)
    # a very long finite solenoid tends to the infinite value at its centre
    assert estimate.solenoid_b_axis_finite(1000, 1, 10, 0.01) == pytest.approx(MU0 * 100, rel=1e-4)
    assert estimate.loop_b_axis(1, 0.1) == pytest.approx(MU0 / 0.2)
    # thin-shell limit of the thick solenoid = finite solenoid with N/L = J * thickness
    r1, t, L, J = 0.05, 1e-5, 0.2, 1e8
    b_thick = estimate.thick_solenoid_b_center(J, r1, r1 + t, L)
    b_thin = estimate.solenoid_b_axis_finite(J * t * L, 1, L, r1)
    assert b_thick == pytest.approx(b_thin, rel=1e-3)
    assert estimate.solenoid_inductance_long(100, 1e-4, 0.1) == pytest.approx(MU0 * 1e4 * 1e-4 / 0.1)


def test_magnetic_circuits():
    bg = estimate.ccore_gap_b(200, 2, 0.002, 0.18, 2000)
    assert bg == pytest.approx(MU0 * 400 / (0.002 + 0.18 / 2000))
    assert estimate.ccore_inductance(200, 2e-4, 0.002) == pytest.approx(MU0 * 4e4 * 2e-4 / 0.002, rel=1e-6)
    assert estimate.maxwell_force(1.0, 1e-4) == pytest.approx(1e-4 / (2 * MU0))
    kc = estimate.carter_coefficient(0.013, 0.002, 0.0015)
    assert 1.0 < kc < 1.1
    assert estimate.carter_coefficient(0.01, 0.0, 0.001) == pytest.approx(1.0)


def test_pm_load_line_consistency():
    r = estimate.pm_load_line(1.3, 1.05, 0.003, 0.0015)
    assert r["Pc"] == pytest.approx(2.0)
    assert r["Bm"] == pytest.approx(1.3 * 2 / 3.05)
    assert -r["Bm"] / (MU0 * r["Hm"]) == pytest.approx(r["Pc"])
    assert estimate.spm_gap_b(1.3, 1.05, 3, 1.5) == pytest.approx(r["Bm"])


def test_machine_formulas():
    assert estimate.dq_torque(2, 0.05, 0.0, 0.0, 10) == pytest.approx(1.5)
    assert estimate.dq_torque_from_inductances(2, 0.05, 1e-3, 2e-3, -5, 10) == pytest.approx(1.5 * 2 * (0.5 + (-1e-3) * -50))
    assert estimate.cogging_period_deg(12, 4) == pytest.approx(30)
    assert estimate.cogging_period_deg(9, 8) == pytest.approx(5)
    assert estimate.emf_from_flux_linkage(0.05, 1000, 2) == pytest.approx(2 * math.pi * 2 * 1000 / 60 * 0.05)
    for th in (0.0, 0.7, 2.5):
        a, b, c = estimate.inverse_park(3.0, -2.0, th)
        assert a + b + c == pytest.approx(0, abs=1e-12)
        d, q = estimate.park(a, b, c, th)
        assert (d, q) == pytest.approx((3.0, -2.0))


def test_electrostatics_and_conduction():
    assert estimate.parallel_plate_capacitance(1.0, 1e-3) == pytest.approx(8.8541878128e-9)
    assert estimate.bar_resistance(1, 1e-6, 58e6) == pytest.approx(1 / 58)
    assert estimate.skin_depth(50, 58e6) == pytest.approx(9.35e-3, rel=5e-3)


def test_round_wire_impedance_limits():
    a, s = 5e-3, 58e6
    rdc = 1 / (s * math.pi * a * a)
    z = estimate.round_wire_internal_impedance(a, s, 1.0)
    assert z.real == pytest.approx(rdc, rel=1e-4)
    assert z.imag / (2 * math.pi) == pytest.approx(MU0 / (8 * math.pi), rel=1e-3)
    f = 2e5  # a/delta ~ 34: surface-impedance regime
    d = estimate.skin_depth(f, s)
    z = estimate.round_wire_internal_impedance(a, s, f)
    assert z.real == pytest.approx(1 / (s * 2 * math.pi * a * d), rel=0.03)
    f = 1e4  # series branch, a/delta ~ 7.6
    z = estimate.round_wire_internal_impedance(a, s, f)
    d = estimate.skin_depth(f, s)
    rdc_ratio = a / (2 * d) + 0.25 + 3 * d / (32 * a)  # Bessel asymptotic series
    assert z.real == pytest.approx(rdc * rdc_ratio, rel=0.01)


def test_harmonics():
    n = 36
    x = [2.0 + 3.0 * math.cos(2 * math.pi * k / n) + 0.5 * math.sin(2 * math.pi * 5 * k / n) for k in range(n)]
    h = estimate.harmonics(x)
    assert h["amplitude"][0] == pytest.approx(2.0)
    assert h["amplitude"][1] == pytest.approx(3.0)
    assert h["amplitude"][5] == pytest.approx(0.5)
    assert h["thd"] == pytest.approx(0.5 / 3.0)
