"""Review round on 0.2.1 sector support: sector argument validation, rotate refused on a sector,
per-column footing of full-machine notes, non-dividing sectors, the refusal point-back path,
`center` on inductance / ac_sweep, stale text, and the builder against the FEMM-written fixtures.
Offline (fake engines); the live refusal check is in tests/live/test_live_sector.py."""
import json
import math
import re
import shutil
from pathlib import Path

import pytest

from femm_agent import benchmarks, benchmarks_sector as bs, femfile, preflight
from femm_agent import experiments as ex
from test_experiments import FIX, FakeFemm

ROOT = Path(__file__).resolve().parents[1]


class _Recorder:
    def __init__(self):
        self.calls = []

    def call(self, name, *args, timeout=None):
        self.calls.append((name, args))
        return None


# ============================================================================= item 1: sector validation

@pytest.mark.parametrize("bad", [2.5, 1.9, 0, -4, True, False, "2", float("nan")])
def test_bad_sector_values_are_refused_with_valid_list(tmp_path, bad):
    with pytest.raises(bs.SectorError) as ei:
        benchmarks.build_spm(_Recorder(), (tmp_path / "s.fem").as_posix(), sector=bad)
    assert "[2, 4]" in ei.value.hint and "None or 1" in ei.value.hint


@pytest.mark.parametrize("full", [None, 1, 1.0])
def test_none_or_one_is_the_full_machine(tmp_path, full):
    meta = benchmarks.build_spm(_Recorder(), (tmp_path / "f.fem").as_posix(), sector=full)
    assert "sector" not in meta and meta["rotor_method"] == "rotate"


def test_invalid_divisor_hint_lists_valid_sectors(tmp_path):
    with pytest.raises(bs.SectorError) as ei:
        benchmarks.build_spm(_Recorder(), (tmp_path / "s.fem").as_posix(), sector=3)
    assert "[2, 4]" in ei.value.hint
    assert bs.valid_sectors(12, 4, benchmarks.spm_slot_phases(12, 2, 15.0)) == [2, 4]
    meta = benchmarks.build_spm(_Recorder(), (tmp_path / "t.fem").as_posix(), sector=2.0)   # whole float accepted
    assert meta["sector"] == 2


def test_bad_sector_through_the_envelope_is_an_input_error(tmp_path):
    from femm_agent.tools._common import envelope
    r = envelope(lambda: benchmarks.build_spm(_Recorder(), (tmp_path / "s.fem").as_posix(), sector=2.5))
    assert r["ok"] is False and "trace" not in r["error"] and "[2, 4]" in r["error"]["hint"]


# ============================================================================= item 2: docstring footing

def test_build_spm_docstring_agrees_with_scale_rule():
    doc = " ".join(benchmarks.build_spm.__doc__.split())
    assert "torque and inductance are N x" not in doc
    assert "air-gap element torque" in doc and "already" in doc and "x 1" in doc


def test_no_text_says_sector_torque_scales_by_n():
    """Any sentence that names torque and 'x N' / 'N x' / 'multiply by N' must also say the
    air-gap element torque is x 1 / already full-machine, or be about virtual work / dq / WST."""
    paths = [*ROOT.joinpath("src").rglob("*.py"), *ROOT.joinpath(".claude", "skills").rglob("*.md"),
             *ROOT.joinpath("docs").rglob("*.md"), ROOT / "README.md", ROOT / "CLAUDE.md"]
    bad = []
    for p in paths:
        text = " ".join(p.read_text(encoding="utf-8").split())
        for sent in re.split(r"(?<=[.;])\s", text):
            if "torque" in sent and re.search(r"\bN x\b|\bx N\b|multiply by N|times N", sent):
                if not re.search(r"x 1\b|already|virtual work|dq|coenergy|stress tensor|WST|was wrong|"
                                 r"failed on sectors|scale not measured", sent):
                    bad.append(f"{p.relative_to(ROOT)}: {sent[:160]}")
    assert not bad, bad


# ============================================================================= item 3: rotate refused on a sector

@pytest.mark.parametrize("fn, kw", [
    (ex.cogging, dict(slots=12, poles=4, steps=5)),
    (ex.torque_vs_angle, dict(steps=3)),
    (ex.back_emf, dict(poles=4, steps=6)),
])
def test_rotate_on_a_sector_is_refused_before_any_move(tmp_path, fn, kw):
    fake = FakeFemm("spm_age_sector4.fem")
    with pytest.raises(preflight.PreflightError) as ei:
        fn(fake, [1], method="rotate", out_dir=tmp_path, **kw)
    names = [n for n, _ in fake.calls]
    assert "mi_moverotate" not in names and "mi_analyze" not in names and "mi_modifycircprop" not in names
    assert "method='age'" in ei.value.hint and "gap_boundary='AGE'" in ei.value.hint


def test_age_on_a_sector_still_runs(tmp_path):
    r = ex.cogging(FakeFemm("spm_age_sector4.fem"), [1], slots=12, poles=4, steps=5, method="age",
                   gap_boundary="AGE", out_dir=tmp_path)
    assert r["full_machine"]["factor"] == 4


# ============================================================================= item 4: per-column footing

def test_full_machine_notes_name_the_footing_of_every_column():
    cols = ["angle_deg", "torque_Nm", "torque_gap_Nm", "torque_virtual_work_Nm", "coenergy_J", "psi_A_Wb",
            "i_A_A", "torque_dq_Nm"]
    wst = preflight.full_machine("torque_vs_angle", {"mean_torque_Nm": 0.3}, 4, False, cols)
    foot = wst["columns"]
    assert foot["full_machine"] == ["torque_gap_Nm", "torque_dq_Nm"]
    assert foot["as_drawn"] == ["torque_Nm", "torque_virtual_work_Nm", "coenergy_J", "psi_A_Wb"]
    assert foot["same"] == ["angle_deg", "i_A_A"]
    assert any("torque_dq_Nm" in n and "full-machine" in n for n in wst["notes"])
    assert "not measured" in wst["notes"][-1]
    age = preflight.full_machine("torque_vs_angle", {"mean_torque_Nm": 0.3}, 4, True, cols)
    assert age["columns"]["full_machine"] == ["torque_Nm", "torque_gap_Nm", "torque_virtual_work_Nm",
                                              "torque_dq_Nm"]
    ind = preflight.full_machine("inductance", {"torque_dq_at_iq_Nm": 1.4, "torque_fem_at_iq_Nm": 0.35,
                                                "Ld_H": 1e-4}, 4, False,
                                 ["case", "id_A", "iq_A", "psi_d_Wb", "psi_q_Wb", "torque_Nm"])
    assert any("torque_dq_at_iq_Nm" in n and "torque_fem_at_iq_Nm" in n for n in ind["notes"])


def test_driven_torque_on_a_sector_states_column_footing(tmp_path):
    r = ex.torque_vs_angle(FakeFemm("spm_age_sector4.fem"), [1], steps=3, stop=10, method="age", gap_boundary="AGE",
                           drive={"circuits": ["A", "B", "C"], "poles": 4, "iq": 10}, out_dir=tmp_path)
    foot = r["full_machine"]["columns"]
    assert "torque_dq_Nm" in foot["full_machine"] and "torque_Nm" in foot["full_machine"]
    assert "psi_A_Wb" in foot["as_drawn"] and "coenergy_J" in foot["as_drawn"]
    assert set(foot["full_machine"]) | set(foot["as_drawn"]) | set(foot["same"]) == set(r["columns"])


# ============================================================================= item 5: sector angle not dividing 360

@pytest.fixture
def non_dividing(monkeypatch):
    monkeypatch.setattr(preflight, "sector_factor", lambda model, center=(0.0, 0.0): (100.0, None))


def test_dq_and_analytic_checks_not_applicable_on_non_dividing_sector(tmp_path, non_dividing):
    r = ex.torque_vs_angle(FakeFemm("spm_age_sector4.fem"), [1], steps=3, stop=10, method="age", gap_boundary="AGE",
                           drive={"circuits": ["A", "B", "C"], "poles": 4, "iq": 10}, out_dir=tmp_path)
    chk = {c["name"]: c for c in r["health"]}
    assert chk["mean_torque_vs_dq"]["ok"] is None and "does not divide 360" in chk["mean_torque_vs_dq"]["message"]
    assert "full_machine" not in r
    r2 = ex.torque_vs_angle(FakeFemm("spm_age_sector4.fem"), [1], steps=3, stop=10, method="age", gap_boundary="AGE",
                            out_dir=tmp_path)
    assert {c["name"]: c for c in r2["health"]}["torque_vs_virtual_work"]["ok"] is None
    e = ex.back_emf(FakeFemm("spm_age_sector4.fem", psi0=0.0125), [1], poles=4, steps=12, method="age",
                    gap_boundary="AGE", psi_estimate=0.05, out_dir=tmp_path)
    c = {c["name"]: c for c in e["health"]}["psi_pm_vs_analytic"]
    assert c["ok"] is None and "does not divide 360" in c["message"]
    i = ex.inductance(FakeFemm("spm_age_sector4.fem"), dq={"circuits": ["A", "B", "C"], "poles": 4, "id": 1,
                                                          "iq": 1}, gap_boundary="AGE", out_dir=tmp_path)
    assert {c["name"]: c for c in i["health"]}["torque_fem_vs_dq"]["ok"] is None


# ============================================================================= item 6: point-back failure

class _FailingReopen(FakeFemm):
    def call(self, name, *args, timeout=None):
        if name == "opendocument":
            self.calls.append((name, args))
            raise RuntimeError("engine refused to open")
        return super().call(name, *args, timeout=timeout)


def test_point_back_failure_is_reported_not_swallowed(tmp_path):
    from femm_agent.sessions import Session
    from femm_agent.tools import experiments as tool_exp

    doc = tmp_path / "doc.fem"
    shutil.copyfile(FIX / "ccore.fem", doc)
    s = Session(name="main", link=_FailingReopen("ccore.fem"), work_dir=tmp_path)
    s.physics, s.document = "magnetics", doc.as_posix()
    s.solved = True
    with pytest.raises(preflight.PreflightError) as ei:
        tool_exp._run(s, ex.force_vs_position, groups=[7], dy=0.5, steps=3)
    assert "femm_open" in ei.value.hint and "engine refused to open" in ei.value.hint
    assert s.physics is None and s.solved is False and s.document == doc.as_posix()
    assert "engine refused to open" in s.notes["point_back_error"]


def test_point_back_docstring_mentions_resave():
    from femm_agent.tools import experiments as tool_exp
    assert "re-saved unedited" in " ".join(tool_exp._point_back.__doc__.split())


# ============================================================================= item 7: center on inductance / ac_sweep

def test_inductance_and_ac_sweep_take_center(tmp_path):
    r = ex.inductance(FakeFemm("spm_age_sector4.fem"), circuits=["A"], out_dir=tmp_path)
    assert r["full_machine"]["factor"] == 4
    off = ex.inductance(FakeFemm("spm_age_sector4.fem"), circuits=["A"], center=(100.0, 100.0), out_dir=tmp_path)
    assert "full_machine" not in off and off["parameters"]["center"] == [100.0, 100.0]
    a = ex.ac_sweep(FakeFemm("spm_age_sector4.fem"), [0.0], circuits=["A"], center=(100.0, 100.0), out_dir=tmp_path)
    assert "full_machine" not in a and a["parameters"]["center"] == [100.0, 100.0]
    a0 = ex.ac_sweep(FakeFemm("spm_age_sector4.fem"), [0.0], circuits=["A"], out_dir=tmp_path)
    assert a0["full_machine"]["factor"] == 4


def test_tool_layer_passes_center():
    import inspect
    from femm_agent.tools import experiments as tool_exp
    src = inspect.getsource(tool_exp.register)
    for tool in ("femm_experiment_inductance", "femm_experiment_ac_sweep"):
        body = src[src.index(f"def {tool}("):]
        body = body[:body.index("@mcp.tool()")]
        assert "center: list[float] | None = None" in body and "center=tuple(center or (0.0, 0.0))" in body


# ============================================================================= item 8: stale text

def test_catalog_descriptions_do_not_contradict_verified_returns():
    cmds = json.loads((ROOT / "data" / "commands.json").read_text(encoding="utf-8"))
    cmds = cmds["commands"] if isinstance(cmds, dict) else cmds
    bad = [c["name"] for c in cmds if "(verified" in (c.get("returns") or "")
           and (c.get("description") or "").rstrip(". ").endswith("unverified")]
    assert not bad, bad


def test_tool_docstring_percentages_agree_with_scale_rule():
    from femm_agent.tools import experiments as tool_exp
    import inspect
    src = inspect.getsource(tool_exp.register)
    body = src[src.index("def femm_experiment_back_emf("):]
    body = body[:body.index('"""', body.index('"""') + 3)]
    for pct in re.findall(r"(\d+(?:\.\d+)?) %", body):
        assert f"{pct} %" in preflight.SCALE_RULE, pct


# ============================================================================= item 9: builder vs FEMM-written fixtures

def _from_builder(n):
    rec = _Recorder()
    meta = benchmarks.build_spm(rec, "unused.fem", sector=n)
    bprops = {a[0]: int(a[9]) for name, a in rec.calls if name == "mi_addboundprop"}
    circuits = [a[0] for name, a in rec.calls if name == "mi_addcircprop"]
    segs: dict[str, int] = {}
    for name, a in rec.calls:
        if name == "mi_setsegmentprop" and a[0]:
            segs[a[0]] = segs.get(a[0], 0) + 1
        elif name == "mi_setarcsegmentprop" and a[1]:
            segs[a[1]] = segs.get(a[1], 0) + 1
    labels, pos = [], None
    for name, a in rec.calls:
        if name == "mi_addblocklabel":
            pos = a
        elif name == "mi_setblockprop":
            mat, _auto, mesh, circ, magdir, grp, turns = a
            labels.append((round(pos[0], 6), round(pos[1], 6), mat, circ or "", round(float(magdir), 6) % 360,
                           int(grp), float(turns) if circ else None, float(mesh)))
    angles = [math.degrees(math.atan2(a[1], a[0])) % 360 for name, a in rec.calls
              if name == "mi_addnode" and math.hypot(a[0], a[1]) > 1e-9]
    holes = sorted((x, y, g) for x, y, m, _c, _d, g, _t, _s in labels if m == "<No Mesh>")
    labels = [lab for lab in labels if lab[2] != "<No Mesh>"]
    return meta, bprops, circuits, segs, sorted(labels), holes, max(angles)


@pytest.mark.parametrize("n", [2, 4])
def test_builder_matches_femm_written_fixture(n):
    meta, bprops, circuits, segs, labels, holes, ext = _from_builder(n)
    m = femfile.parse_file(FIX / f"spm_age_sector{n}.fem")
    assert bprops == {b["BdryName"]: int(b["BdryType"]) for b in m.boundaries()}
    assert circuits == [c["CircuitName"] for c in m.circuits()]
    fix_segs = {b["name"]: b["segments"] for b in m.summary()["boundaries"] if b["segments"]}
    assert segs == fix_segs
    fix_labels = sorted((round(lab["x"], 6), round(lab["y"], 6), lab["material"], lab.get("circuit") or "",
                         round(float(lab.get("magdir") or 0), 6) % 360, int(lab["group"]),
                         float(lab["turns"]) if lab.get("circuit") else None, float(lab["mesh_size"]))
                        for lab in m.block_labels())
    assert labels == fix_labels
    # FEMM 5 saves a "<No Mesh>" label as a [NumHoles] row (x, y, group), not as a block label
    assert holes == sorted((round(x, 6), round(y, 6), int(g)) for x, y, g in m.geometry.get("NumHoles", []))
    assert ext == pytest.approx(360 / n) and meta["sector_angle_deg"] == pytest.approx(360 / n)
    assert preflight.sector_factor(m) == (pytest.approx(360 / n), n)
    hdr = m.header
    assert float(hdr["Depth"]) == 50 and hdr["LengthUnits"] == "millimeters" and hdr["ProblemType"] == "planar"
