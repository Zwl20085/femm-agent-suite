"""Offline tests for femm_agent.units."""
import math

import pytest

from femm_agent import units


def test_length_conversions():
    assert units.convert_length(1, "inches", "millimeters") == pytest.approx(25.4)
    assert units.convert_length(1000, "mils", "inches") == pytest.approx(1.0)
    assert units.length_factor("mm") == 1e-3
    assert units.length_factor("microns") == units.length_factor("um") == 1e-6
    assert units.normalize_length_unit("Metres") == "meters"
    with pytest.raises(ValueError):
        units.length_factor("furlongs")


def test_angles_and_speed():
    assert units.deg2rad(180) == pytest.approx(math.pi)
    assert units.rad2deg(math.pi / 2) == pytest.approx(90)
    assert units.rpm_to_rad_s(60) == pytest.approx(2 * math.pi)
    assert units.electrical_frequency(3000, 2) == pytest.approx(100)


def test_wire_gauges_match_pyfemm_fits():
    # pyFEMM: AWG(n) = 8.2514694*exp(-0.115943 n); ASTM: 0.127 mm * 92^((36-n)/39)
    for n in (0, 10, 18, 24, 36):
        astm = 0.127 * 92 ** ((36 - n) / 39)
        assert units.awg_diameter_mm(n) == pytest.approx(astm, rel=2e-3)
    assert units.awg_diameter_mm(18) == pytest.approx(1.024, rel=2e-3)
    assert units.nearest_awg(units.awg_diameter_mm(22)) == 22
    assert units.iec_diameter_mm(0) == pytest.approx(7.959159641581004)


def test_magnet_conversions():
    assert units.tesla_to_gauss(1.2) == pytest.approx(12000)
    assert units.oersted_to_a_per_m(1) == pytest.approx(79.5775, rel=1e-5)
    assert units.mgoe_to_j_per_m3(1) == pytest.approx(7957.75, rel=1e-5)
    br = units.br_from_mgoe(42, 1.05)
    assert 1.30 < br < 1.36
    assert units.mgoe_from_br(br, 1.05) == pytest.approx(42)
    hc = units.hc_from_br(1.3122501, 1.05)
    assert hc == pytest.approx(994529, rel=1e-4)  # FEMM 5 library N42 H_c
    assert units.br_from_hc(hc, 1.05) == pytest.approx(1.3122501)
