"""Sector models (0.2.1): the SPM sector builder's geometry (read back with the .fem parser from
fixtures written by FEMM 5 build 20261101), the sector/scale logic and the full_machine block.
Offline; the live comparison against the full machine is tests/live/test_live_sector.py."""
import math

import pytest

from femm_agent import benchmarks, benchmarks_sector as bs, femfile, preflight
from femm_agent import experiments as ex
from test_experiments import FIX, FakeFemm


@pytest.mark.parametrize("n, kind, btype, age_type, slots_in, labels", [
    (4, "antiperiodic", 5, 7, 3, 9), (2, "periodic", 4, 6, 6, 13)])
def test_sector_fixture_geometry(n, kind, btype, age_type, slots_in, labels):
    m = femfile.parse_file(FIX / f"spm_age_sector{n}.fem")
    s = m.summary()
    by = {b["name"]: b for b in s["boundaries"]}
    assert by["AGE"]["type"] == age_type and by["AGE"]["segments"] == 2           # inner + outer AGE arc
    per = [b for b in s["boundaries"] if b["name"].startswith("per_")]
    assert len(per) == 5 and all(b["type"] == btype and b["segments"] == 2 for b in per)   # one pair each
    assert preflight.sector_factor(m) == (pytest.approx(360 / n), n)
    labs = m.block_labels()
    assert len(labs) == labels
    coils = [lab for lab in labs if lab.get("circuit")]
    assert len(coils) == slots_in and {lab["circuit"] for lab in coils} <= {"A", "B", "C"}
    assert sorted(preflight.active_circuits(m)) == ["A", "B", "C"]
    for lab in labs:                                                            # every label inside the sector
        ang = math.degrees(math.atan2(lab["y"], lab["x"])) % 360
        assert -1e-9 <= ang <= 360 / n + 1e-9


def _phases():
    return benchmarks.spm_slot_phases(12, 2, 15.0)


def test_sector_kind_rules():
    assert bs.sector_kind(12, 4, 2, _phases()) == "periodic"
    assert bs.sector_kind(12, 4, 4, _phases()) == "antiperiodic"
    for n in (3, 5, 1):
        with pytest.raises(bs.SectorError):
            bs.sector_kind(12, 4, n, _phases())


class _Recorder:
    def __init__(self):
        self.calls = []

    def call(self, name, *args, timeout=None):
        self.calls.append((name, args))
        return None


def test_builder_commands(tmp_path):
    rec = _Recorder()
    meta = benchmarks.build_spm(rec, (tmp_path / "s.fem").as_posix(), sector=4)
    assert meta["sector_kind"] == "antiperiodic" and meta["scale_to_full_machine"] == 4
    assert meta["rotor_method"] == "age" and meta["air_gap_boundary"] == "AGE" and meta["rotate_groups"] == [1]
    bprops = {a[0]: a[9] for n, a in rec.calls if n == "mi_addboundprop"}
    assert bprops["AGE"] == 7 and sum(1 for k, v in bprops.items() if k.startswith("per_") and v == 5) == 5
    with pytest.raises(bs.SectorError, match="cannot run on a sector"):
        benchmarks.build_spm(_Recorder(), (tmp_path / "r.fem").as_posix(), sector=2, rotor_method="rotate")
    with pytest.raises(bs.SectorError):
        benchmarks.build_spm(_Recorder(), (tmp_path / "x.fem").as_posix(), sector=3)
    full = benchmarks.build_spm(_Recorder(), (tmp_path / "f.fem").as_posix())
    assert full["rotor_method"] == "rotate" and "sector" not in full


def test_full_machine_scaling_pure():
    summ = {"psi_fundamental_Wb": {"A": 0.012}, "emf_fundamental_peak_V": {"A": 2.5}, "rpm": 1000,
            "harmonics_phase1": [{"order": 1, "amplitude_V": 2.5}], "emf_thd": {"A": 0.01}}
    fm = preflight.full_machine("back_emf", summ, 4, True)
    assert fm["factor"] == 4 and fm["summary"]["psi_fundamental_Wb"] == {"A": 0.048}
    assert fm["summary"]["harmonics_phase1"] == [{"order": 1, "amplitude_V": 10.0}]      # orders unchanged
    assert "rpm" not in fm["summary"] and "emf_thd" not in fm["summary"]                    # x 1 quantities left out
    cog = preflight.full_machine("cogging", {"peak_to_peak_Nm": 0.38, "harmonics": [{"order_per_period": 1,
                                                                                     "amplitude_Nm": 0.19}]}, 4, True)
    assert cog["summary"]["peak_to_peak_Nm"] == 0.38                                       # gap torque already full
    wst = preflight.full_machine("cogging", {"peak_to_peak_Nm": 0.1}, 4, False)
    assert wst["summary"] == {} and "not measured" in wst["notes"][-1]
    ind = preflight.full_machine("inductance", {"self_H": {"A": 1e-4}, "torque_dq_at_iq_Nm": 1.4,
                                                "torque_fem_at_iq_Nm": 1.41}, 4, True)
    assert ind["summary"] == {"self_H": {"A": 4e-4}, "torque_dq_at_iq_Nm": 1.4, "torque_fem_at_iq_Nm": 1.41}


def test_sector_factor_not_dividing_360():
    from test_v020 import _Model
    m = _Model()
    m._pts = [(10, 0), (50, 0), (0.0, 10), (0.0, 50)]
    m._pts[2:] = [(10 * math.cos(math.radians(100)), 10 * math.sin(math.radians(100))),
                  (50 * math.cos(math.radians(100)), 50 * math.sin(math.radians(100)))]
    ext, n = preflight.sector_factor(m)
    assert ext == pytest.approx(100) and n is None
    assert "does not divide 360" in preflight.sector_warnings(m)[0]


def test_experiments_on_a_sector_report_full_machine(tmp_path):
    fake = FakeFemm("spm_age_sector4.fem", psi0=0.0125)
    r = ex.back_emf(fake, [1], poles=4, steps=12, method="age", gap_boundary="AGE", out_dir=tmp_path)
    fm = r["full_machine"]
    assert fm["factor"] == 4 and "measured" in fm["rule"]
    assert fm["summary"]["psi_fundamental_Wb"]["A"] == pytest.approx(4 * r["summary"]["psi_fundamental_Wb"]["A"])
    assert any("1/4 of the machine" in w for w in r["warnings"])
    c = ex.cogging(FakeFemm("spm_age_sector4.fem"), [1], slots=12, poles=4, steps=7, method="age", gap_boundary="AGE",
                   out_dir=tmp_path)
    assert c["full_machine"]["summary"]["peak_to_peak_Nm"] == c["summary"]["peak_to_peak_Nm"]
    vw_col = c["columns"].index("torque_virtual_work_Nm")
    plain = ex.cogging(FakeFemm("spm_age.fem"), [1], slots=12, poles=4, steps=7, method="age", gap_boundary="AGE",
                       out_dir=tmp_path)
    assert "full_machine" not in plain
    assert c["rows"][2][vw_col] == pytest.approx(4 * plain["rows"][2][vw_col])          # coenergy x N on a sector
    with pytest.raises(preflight.PreflightError, match="rotate-and-remesh"):    # refused since the 0.2.1 review
        ex.cogging(FakeFemm("spm_age_sector4.fem"), [1], slots=12, poles=4, steps=3, out_dir=tmp_path)


# ============================================================================= pre-flight refusal: no re-save

def test_refusal_points_femm_back_without_rewriting(tmp_path):
    import shutil
    from femm_agent import preflight as pf
    from femm_agent.sessions import Session
    from femm_agent.tools import experiments as tool_exp

    doc = tmp_path / "doc.fem"
    shutil.copyfile(FIX / "ccore.fem", doc)                 # on disk == what the fake engine "saves"
    fake = FakeFemm("ccore.fem")
    s = Session(name="main", link=fake, work_dir=tmp_path)
    s.physics, s.document = "magnetics", doc.as_posix()
    s.solved = True
    mtime = doc.stat().st_mtime_ns
    with pytest.raises(pf.PreflightError):
        tool_exp._run(s, ex.force_vs_position, groups=[7], dy=0.5, steps=3)
    after = fake.calls[[n for n, _ in fake.calls].index("mi_saveas") + 1:]
    names = [n for n, _ in after]
    assert "mi_saveas" not in names and names[-3:] == ["mi_close", "opendocument", "mi_loadsolution"]
    assert after[-2][1][0] == doc.as_posix() and doc.stat().st_mtime_ns == mtime and s.solved is True
    doc.write_text("changed on disk", encoding="utf-8")       # editor state differs from disk: save the edits
    fake2 = FakeFemm("ccore.fem")
    s.link = fake2
    with pytest.raises(pf.PreflightError):
        tool_exp._run(s, ex.force_vs_position, groups=[7], dy=0.5, steps=3)
    assert [a[0] for n, a in fake2.calls if n == "mi_saveas"][-1] == doc.as_posix()
