"""Live: a 1/N sector of the SPM benchmark against the full machine (pytest -m live).

Measured on FEMM 5.0 build 20261101 (1144), 12-slot 4-pole SPM, air-gap element route: flux
linkage, EMF, resistance, copper loss (x N, within 0.05 %) and inductance (x N, within 0.12 %) of the
sector, and the air-gap element torque as is (within 0.05 %), agree with the
full machine (docs/femm5-facts.md, "Sector models"). The tolerance here is 0.5 %.
"""
import pytest

from femm_agent import benchmarks, ipc
from femm_agent import experiments as ex

pytestmark = pytest.mark.live
TOL = 0.005


def _measure(femm_install, tmp_path, sector):
    link = ipc.launch(femm_install, port=ipc.pick_free_port(49880))
    try:
        d = tmp_path / f"s{sector or 1}"
        d.mkdir()
        path = (d / "spm.fem").as_posix()
        benchmarks.build_spm(link, path, rotor_method="age", sector=sector)
        kw = dict(method="age", gap_boundary="AGE", out_dir=d, restore_path=path)
        emf = ex.back_emf(link, [1], poles=4, rpm=1000, steps=12, **kw)
        cog = ex.cogging(link, [1], slots=12, poles=4, steps=13, **kw)
        tq = ex.torque_vs_angle(link, [1], start=0, stop=30, steps=4,
                                drive={"circuits": ["A", "B", "C"], "poles": 4, "id": 0, "iq": 10}, **kw)
        ind = ex.inductance(link, circuits=["A"], current=5.0, out_dir=d, restore_path=path)
        return emf, cog, tq, ind
    finally:
        link.close()


@pytest.fixture(scope="module")
def full(femm_install, tmp_path_factory):
    return _measure(femm_install, tmp_path_factory.mktemp("full"), None)


@pytest.mark.parametrize("n", [2, 4])
def test_sector_times_n_equals_full_machine(full, femm_install, tmp_path, n):
    emf, cog, tq, ind = _measure(femm_install, tmp_path, n)
    femf, fcog, ftq, find = full
    for r in (emf, cog, tq, ind):
        assert r["full_machine"]["factor"] == n
        assert r["health_summary"]["failed"] == 0, r["health_summary"]
    fm = emf["full_machine"]["summary"]
    assert fm["psi_fundamental_Wb"]["A"] == pytest.approx(femf["summary"]["psi_fundamental_Wb"]["A"], rel=TOL)
    assert fm["emf_fundamental_peak_V"]["A"] == pytest.approx(femf["summary"]["emf_fundamental_peak_V"]["A"], rel=TOL)
    # air-gap element torque of a sector is already the full-machine torque
    assert cog["summary"]["peak_to_peak_Nm"] == pytest.approx(fcog["summary"]["peak_to_peak_Nm"], rel=TOL)
    assert tq["summary"]["mean_torque_Nm"] == pytest.approx(ftq["summary"]["mean_torque_Nm"], rel=TOL)
    assert ind["full_machine"]["summary"]["self_H"]["A"] == pytest.approx(find["summary"]["self_H"]["A"], rel=TOL)
    assert {c["name"]: c for c in tq["health"]}["mean_torque_vs_dq"]["ok"] is True


def _r_and_loss(femm_install, tmp_path, sector, freq):
    link = ipc.launch(femm_install, port=ipc.pick_free_port(49890))
    try:
        path = (tmp_path / f"r{sector or 1}_{freq}.fem").as_posix()
        benchmarks.build_spm(link, path, rotor_method="age", sector=sector)
        link.call("mi_probdef", freq, "millimeters", "planar", 1e-8, 50, 30)
        for c, i in ex.dq_currents({"circuits": ["A", "B", "C"], "poles": 4, "iq": 10}, 5.0).items():
            link.call("mi_modifycircprop", c, 1, i)
        link.call("mi_saveas", path)
        link.call("mi_analyze", 1)
        link.call("mi_loadsolution")
        cp = link.call("mo_getcircuitproperties", "A")
        r = (complex(cp[1]) / complex(cp[0])).real
        link.call("mo_clearblock")
        link.call("mo_groupselectblock", 3)
        loss = link.call("mo_blockintegral", 4)
        loss = complex(loss[0] if isinstance(loss, list) else loss).real
        return r, loss
    finally:
        link.close()


@pytest.mark.parametrize("freq", [0, 50])
def test_sector_resistance_and_copper_loss_times_n(femm_install, tmp_path, freq):
    r_full, p_full = _r_and_loss(femm_install, tmp_path, None, freq)
    for n in (2, 4):
        r, p = _r_and_loss(femm_install, tmp_path, n, freq)
        assert n * r == pytest.approx(r_full, rel=TOL) and n * p == pytest.approx(p_full, rel=TOL)
