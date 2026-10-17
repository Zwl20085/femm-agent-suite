"""Experiments: offline orchestration tests against a fake engine, plus live validation runs.

The fake engine answers the handful of commands the experiments use with closed-form physics
(coenergy quadratic in position, sinusoidal flux linkage), so bookkeeping, restoring and the
virtual-work / harmonic maths are checked without FEMM. Live tests (``-m live``) build the
benchmark models from scratch in FEMM 5 and compare against analytic references.
"""
import math
import shutil
from pathlib import Path

import pytest

from femm_agent import benchmarks, estimate, experiments as ex

FIX = Path(__file__).parent / "fixtures"


class FakeFemm:
    """Just enough of FEMM: geometry offsets, currents, and analytic post-processing."""

    def __init__(self, fixture: str, k: float = 2000.0, psi0: float = 0.05, pole_pairs: int = 2, L: float = 1e-3):
        self.fixture = FIX / fixture
        self.y = 0.0          # translation of the moving group (problem units)
        self.angle = 0.0      # rotor angle (deg)
        self.gap_angle = 0.0
        self.k, self.psi0, self.p, self.L = k, psi0, pole_pairs, L
        self.currents = {}
        self.freq = 0.0
        self.calls = []
        self.saved = []

    # analytic model -------------------------------------------------------------------
    def _rotor(self):
        return self.angle + self.gap_angle

    def _psi(self, name):
        shift = {"A": 0.0, "B": -120.0, "C": 120.0}.get(name, 0.0)
        th = math.radians(self.p * self._rotor() + shift)
        own = self.L * self.currents.get(name, 0.0)
        return self.psi0 * math.cos(th) + own

    def call(self, name, *args, timeout=None):
        self.calls.append((name, args))
        if name == "mi_saveas":
            Path(args[0]).parent.mkdir(parents=True, exist_ok=True)
            if Path(args[0]).resolve() != self.fixture.resolve():
                shutil.copyfile(self.fixture, args[0])
            self.saved.append(args[0])
            return None
        if name == "mi_movetranslate":
            self.y += args[1]
            return None
        if name == "mi_moverotate":
            self.angle += args[2]
            return None
        if name == "mi_modifyboundprop":
            self.gap_angle = args[2]
            return None
        if name == "mi_modifycircprop":
            self.currents[args[0]] = complex(args[2]).real if not isinstance(args[2], (int, float)) else args[2]
            return None
        if name == "mi_probdef":
            self.freq = args[0]
            return None
        if name == "mo_blockintegral":
            s = self.y * 1e-3
            code = args[0]
            th = math.radians(self._rotor())
            if code == 17:   # coenergy: W' = 0.5 k s^2 + cogging term
                return 0.5 * self.k * s * s + 0.01 * (1 - math.cos(12 * th)) / 12
            if code == 19:
                return self.k * s
            if code == 18:
                return 0.0
            if code == 22:
                return 0.01 * math.sin(12 * th)
            if code == 2:
                return 0.5 * sum(self.L * i * i for i in self.currents.values())
            return 0.0
        if name == "mo_gapintegral":
            return 0.01 * math.sin(12 * math.radians(self._rotor()))
        if name == "mo_getcircuitproperties":
            i = self.currents.get(args[0], 0.0)
            return [i, 0.0, self._psi(args[0])]
        return None

    def eval(self, expr, timeout=None):
        self.calls.append(("eval", (expr,)))
        return None


def test_value_helpers():
    assert ex.as_complex("1.5+I*2") == complex(1.5, 2)
    assert ex.as_complex("-3-I*0.5") == complex(-3, -0.5)
    assert ex.as_complex(2) == 2 and ex.as_complex(1 + 1j) == 1 + 1j
    assert ex.as_float([0.25, 1]) == 0.25
    assert ex._num(complex(1, 1e-20)) == 1.0 and ex._num(1 + 2j) == {"re": 1.0, "im": 2.0}
    assert ex._angles(None, 0, 30, 4, True) == [0, 10, 20, 30]
    assert ex._angles(None, 0, 30, 3, False) == [0, 10, 20]
    cur = ex.dq_currents({"circuits": ["A", "B", "C"], "pole_pairs": 2, "id": 0, "iq": 10}, 0.0)
    assert cur["A"] == pytest.approx(0) and cur["B"] == pytest.approx(10 * math.sin(math.radians(120)))
    assert sum(cur.values()) == pytest.approx(0, abs=1e-12)


def test_force_vs_position_offline(tmp_path):
    fake = FakeFemm("ccore.fem", k=2000.0)
    r = ex.force_vs_position(fake, [1], dy=0.5, steps=5, out_dir=tmp_path)
    assert fake.y == pytest.approx(0)          # geometry restored
    assert [row[0] for row in r["rows"]] == pytest.approx([0, 0.5, 1.0, 1.5, 2.0])
    vw = [row[4] for row in r["rows"]]
    assert vw[1:-1] == pytest.approx([2000 * s * 1e-3 for s in (0.5, 1.0, 1.5)])
    chk = {c["name"]: c for c in r["health"]}
    assert chk["force_wst_vs_virtual_work"]["ok"] is True
    assert Path(r["files"]["csv"]).is_file() and Path(r["files"]["json"]).is_file()
    assert r["timing"]["solves"] == 6           # 5 steps + final re-solve at the start position
    assert r["columns"][:6] == ["position", "Fx_N", "Fy_N", "F_along_motion_N", "F_virtual_work_N", "coenergy_J"]


def test_cogging_and_torque_offline(tmp_path):
    fake = FakeFemm("spm_age.fem")
    fake.currents = {"A": 3.0, "B": -1.5, "C": -1.5}
    r = ex.cogging(fake, [1], slots=12, poles=4, steps=25, out_dir=tmp_path)
    assert fake.angle == pytest.approx(0)
    assert fake.currents == {"A": 0.0, "B": 0.0, "C": 0.0}  # fixture currents restored (0 A in the file)
    assert r["summary"]["period_deg"] == 30
    assert r["summary"]["harmonics"][0]["order_per_period"] == 1
    assert r["summary"]["harmonics"][0]["amplitude_Nm"] == pytest.approx(0.01, rel=1e-6)
    chk = {c["name"]: c for c in r["health"]}
    assert chk["cogging_zero_mean"]["ok"] and chk["cogging_vs_virtual_work"]["ok"]
    # air-gap element route: boundary angle restored, torque from mo_gapintegral
    r2 = ex.cogging(fake, [1], slots=12, poles=4, steps=13, method="age", gap_boundary="AGE", out_dir=tmp_path)
    assert fake.gap_angle == pytest.approx(0)
    assert r2["summary"]["peak_to_peak_Nm"] == pytest.approx(0.02, rel=1e-3)
    with pytest.raises(ValueError):
        ex.cogging(fake, [1], slots=12, poles=4, steps=5, method="age", gap_boundary="nope", out_dir=tmp_path)


def test_backemf_offline(tmp_path):
    fake = FakeFemm("spm_age.fem", psi0=0.05, pole_pairs=2)
    r = ex.backemf(fake, [1], pole_pairs=2, rpm=1500, steps=24, out_dir=tmp_path)
    s = r["summary"]
    assert s["psi_fundamental_Wb"]["A"] == pytest.approx(0.05)
    assert s["emf_fundamental_peak_V"]["A"] == pytest.approx(estimate.emf_from_flux_linkage(0.05, 1500, 2), rel=1e-9)
    assert s["emf_line_line_fundamental_V"] == pytest.approx(math.sqrt(3) * s["emf_fundamental_peak_V"]["A"], rel=1e-9)
    chk = {c["name"]: c for c in r["health"]}
    assert chk["three_phase_balance"]["ok"] and chk["half_wave_antisymmetry"]["ok"]
    assert fake.angle == pytest.approx(0)


def test_inductance_offline(tmp_path):
    fake = FakeFemm("spm_age.fem", L=2e-3)
    r = ex.inductance(fake, current=4.0, out_dir=tmp_path)
    assert r["summary"]["self_H"]["A"] == pytest.approx(2e-3)
    assert r["summary"]["L_matrix_H"][0][1] == pytest.approx(0.0, abs=1e-12)
    r = ex.inductance(fake, dq={"circuits": ["A", "B", "C"], "pole_pairs": 2, "id": 2, "iq": 2}, out_dir=tmp_path)
    s = r["summary"]
    assert s["psi_pm_Wb"] == pytest.approx(0.05)
    assert s["Ld_H"] == pytest.approx(2e-3) and s["Lq_H"] == pytest.approx(2e-3)
    assert s["torque_dq_at_iq_Nm"] == pytest.approx(1.5 * 2 * 0.05 * 2)


def test_parametric_offline(tmp_path):
    fake = FakeFemm("ccore.fem")
    cases = [{"name": f"c{i}", "params": {"I": i}, "commands": [{"command": "mi_modifycircprop", "args": ["coil", 1, i]}]}
             for i in (1, 2)]
    outs = [{"name": "psi", "kind": "circuit", "circuit": "coil", "quantity": "flux"},
            {"name": "T", "kind": "block", "code": 22, "groups": [1]}]
    r = ex.parametric(fake, cases, outs, template="x = {I}\n", out_dir=tmp_path)
    assert r["columns"] == ["case", "I", "psi", "T"]
    assert len(r["rows"]) == 2 and not r["summary"]["errors"]
    assert any(c[0] == "eval" for c in fake.calls)
    bad = ex.parametric(fake, [{"name": "x", "commands": [{"command": "quit", "args": []}]}], outs, out_dir=tmp_path)
    assert bad["summary"]["errors"] and bad["health"][0]["ok"] is False


# ============================================================================= live

def _link():
    from femm_agent import config, ipc

    if config.find_femm() is None:
        pytest.skip("FEMM 5 not installed")
    return ipc.launch(port=ipc.pick_free_port(49400))


@pytest.fixture
def link():
    lk = _link()
    yield lk
    lk.close()


@pytest.mark.live
def test_live_ccore_force_inductance(link, tmp_path):
    m = benchmarks.build_ccore(link, (tmp_path / "ccore.fem").as_posix())
    r = ex.force_vs_position(link, [1], dy=0.25, steps=5, out_dir=tmp_path)
    f0 = r["rows"][0][3]
    assert f0 == pytest.approx(m["estimate"]["force_N"], rel=0.15)        # B^2 A / mu0 for two gaps
    assert {c["name"]: c for c in r["health"]}["force_wst_vs_virtual_work"]["ok"]
    r = ex.inductance(link, current=2.0, out_dir=tmp_path)
    assert r["health"][0]["ok"] is True                                     # W = 1/2 L I^2
    L = r["summary"]["self_H"]["coil"]
    assert m["estimate"]["inductance_H"] < L < 2.0 * m["estimate"]["inductance_H"]  # fringing + leakage add


@pytest.mark.live
def test_live_spm_cogging_both_routes(link, tmp_path):
    benchmarks.build_spm(link, (tmp_path / "spm.fem").as_posix())
    a = ex.cogging(link, [1, 10], torque_groups=[1], slots=12, poles=4, steps=13, out_dir=tmp_path)
    benchmarks.build_spm(link, (tmp_path / "spm_age.fem").as_posix(), rotor_method="age")
    b = ex.cogging(link, [1], slots=12, poles=4, steps=13, method="age", gap_boundary="AGE", out_dir=tmp_path)
    ppa, ppb = a["summary"]["peak_to_peak_Nm"], b["summary"]["peak_to_peak_Nm"]
    assert 0.2 < ppa < 0.6 and ppb == pytest.approx(ppa, rel=0.1)
    assert all(c["ok"] is not False for c in b["health"])


@pytest.mark.live
def test_live_spm_backemf_and_dq(link, tmp_path):
    m = benchmarks.build_spm(link, (tmp_path / "spm.fem").as_posix())
    r = ex.backemf(link, [1, 10], pole_pairs=2, rpm=1000, steps=24, out_dir=tmp_path,
                   psi_estimate=m["estimate"]["psi_pm_peak_Wb"])
    psi1 = r["summary"]["psi_fundamental_Wb"]["A"]
    assert psi1 == pytest.approx(m["estimate"]["psi_pm_peak_Wb"], rel=0.15)
    assert all(c["ok"] for c in r["health"])
    t = ex.torque_vs_angle(link, [1, 10], torque_groups=[1], start=0, stop=30, steps=7,
                           drive={"circuits": ["A", "B", "C"], "pole_pairs": 2, "id": 0, "iq": 10}, out_dir=tmp_path)
    chk = {c["name"]: c for c in t["health"]}
    assert chk["mean_torque_vs_dq"]["ok"]
    assert t["summary"]["mean_torque_Nm"] == pytest.approx(estimate.dq_torque(2, psi1, 0, 0, 10), rel=0.1)


@pytest.mark.live
def test_live_round_wire_ac(link, tmp_path):
    m = benchmarks.build_round_wire(link, (tmp_path / "wire.fem").as_posix())
    a, dep = m["radius_mm"] * 1e-3, m["depth_mm"] * 1e-3

    def z(f):
        return estimate.round_wire_internal_impedance(a, 58e6, f) * dep + 2j * math.pi * f * m["estimate"]["L_external_H"]

    r = ex.ac_sweep(link, [10, 1000, 5000], estimate_fn=z, out_dir=tmp_path)
    assert all(c["ok"] for c in r["health"]), r["health"]


@pytest.mark.live
def test_live_bh_check(link, tmp_path):
    benchmarks.build_spm(link, (tmp_path / "spm.fem").as_posix())
    r = ex.bh_check(link, out_dir=tmp_path)
    assert r["summary"]["magnets"] == 4
    for row in r["rows"]:
        assert 0.6 < row[9] < 0.8          # B_m / Br for this geometry (Pc ~ 2.5)


@pytest.mark.live
def test_live_coilgun_axisymmetric(link, tmp_path):
    m = benchmarks.build_coilgun(link, (tmp_path / "far.fem").as_posix(), slug_z=3.0)
    link.call("mi_analyze", 1)
    link.call("mi_loadsolution")
    bz = link.call("mo_getpointvalues", 0.001, 0)[2]
    assert bz == pytest.approx(m["estimate"]["B_center_no_slug_T"], rel=0.03)   # thick-solenoid formula
    benchmarks.build_coilgun(link, (tmp_path / "coilgun.fem").as_posix())
    r = ex.force_vs_position(link, [1], dy=-0.1, steps=12, out_dir=tmp_path)
    f = [row[2] for row in r["rows"]]
    assert abs(f[0]) < 0.05 * max(abs(x) for x in f)    # no axial force with the slug centred
    assert min(f) < 0                                   # pulled back towards the centre (-z offset -> +z force? sign)
    assert {c["name"]: c for c in r["health"]}["force_wst_vs_virtual_work"]["ok"]
