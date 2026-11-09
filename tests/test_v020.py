"""0.2.0 behaviour: unchecked results are visible, experiment pre-flight, next-action hints, the
poles vocabulary, L(I), richer estimates, the force-vs-position restore state, femm_guide /
femm_doctor and the server instructions. Offline (fake engines), no FEMM needed."""
import json
import re
from pathlib import Path

import pytest

from femm_agent import doctor, estimate, estimate_meta, experiments as ex, guide, preflight, reporting
from femm_agent import femfile
from femm_agent.server import INSTRUCTIONS, build_server
from femm_agent.sessions import Session, SessionManager
from femm_agent.tools import _common
from femm_agent.tools import experiments as tool_exp
from femm_agent.tools.mesh_solve import next_check
from test_experiments import FIX, FakeFemm
from test_server_tools import FakeEngine, FakeSessions, tool


@pytest.fixture()
def full(tmp_path):
    eng = FakeEngine()
    mcp, ctx = build_server(FakeSessions(eng, tmp_path))
    assert not ctx.extras["skipped_groups"]
    yield mcp, ctx, eng
    ctx.sessions.close_all()


# ============================================================================= item 2: checked / next / doubts

def test_solve_marks_unchecked_and_names_next_call(full, monkeypatch):
    _mcp, ctx, _eng = full
    tool(ctx, "femm_new_document", physics="magnetics")
    r = tool(ctx, "femm_solve")
    assert r["ok"] and r["result"]["checked"] is False
    assert r["result"]["next"].startswith("femm_health_check(session='main'")
    s = ctx.sessions.get("main")
    assert s.solved and s.checked is False and s.info()["checked"] is False
    r = tool(ctx, "femm_load_solution")
    assert r["result"]["checked"] is False and "femm_health_check" in r["result"]["next"]

    from femm_agent import diagnostics
    monkeypatch.setattr(diagnostics, "run", lambda *a, **k: {"checks": [], "summary": {"verdict": "CHECK"}, "facts": {}})
    assert tool(ctx, "femm_health_check")["ok"]
    assert s.checked is True
    tool(ctx, "femm_solve")                       # a new solution makes the check stale
    assert s.checked is False


def test_next_check_lists_label_groups(tmp_path):
    s = Session(name="m", link=None, work_dir=tmp_path)
    s.physics = "magnetics"
    line = next_check(s, str(FIX / "spm_age.fem"))
    assert "rotor_groups=[...]" in line and "[1, 2, 3]" in line
    s.physics = "electrostatics"
    assert next_check(s).startswith("femm_check_rule")


def test_session_checked_resets_on_any_solution_change(tmp_path):
    s = Session(name="m", link=None, work_dir=tmp_path)
    s.checked = True
    s.solved = True
    assert s.checked is False


def test_status_next_steps(full):
    _mcp, ctx, _ = full
    st = tool(ctx, "femm_status", check_version=False)["result"]
    assert len(st["next_steps"]) == 7
    assert "femm_health_check" in st["next_steps"][5] and st["next_steps"][0].startswith("1. femm_status")


def test_doubts_pure():
    exp_bad = {"experiment": "cogging", "health": [{"name": "cogging_zero_mean", "ok": False}],
               "health_summary": {"failed": 1, "failing": ["cogging_zero_mean"]}, "files": {"json": "x.json"}}
    planar_default = {"problem_type": "planar", "problem": {"Depth": 1, "LengthUnits": "millimeters"}}
    d = reporting.doubts(experiments=[exp_bad], model_summary=planar_default, health_run=False)
    assert d[0].startswith("health check not run on this session")
    assert any(x.startswith("no analytic estimate attached") for x in d)
    assert any(x.startswith("planar depth left at default (1 millimeters)") for x in d)
    assert any("cogging_zero_mean" in x for x in d)
    ok = {"experiment": "back_emf", "health": [{"name": "psi_pm_vs_analytic", "ok": True}],
          "health_summary": {"failed": 0}}
    assert reporting.doubts(experiments=[ok], model_summary={"problem_type": "planar", "problem": {"Depth": 40}},
                            health_run=True) == []
    assert reporting.doubts(model_summary={"problem_type": "axisymmetric", "problem": {"Depth": 1}},
                            checks=[{"name": "x_vs_analytic"}]) == []


def test_report_and_compare_carry_doubts(full, tmp_path):
    _mcp, ctx, _ = full
    tool(ctx, "femm_new_document", physics="magnetics")
    r = tool(ctx, "femm_report", include=["experiments"])
    assert r["ok"], r
    assert any(d.startswith("health check not run") for d in r["result"]["doubts"])
    a = {"experiment": "cogging", "summary": {"pp": 1.0}, "columns": [], "rows": [],
         "health_summary": {"failed": 2, "failing": ["a", "b"]}}
    b = {"experiment": "cogging", "summary": {"pp": 1.0}, "columns": [], "rows": [], "health_summary": {"failed": 0}}
    c = tool(ctx, "femm_compare_results", a=json.dumps(a), b=json.dumps(b))["result"]
    assert c["same_within_rtol"] is True
    assert any(d.startswith("A: experiment cogging has failing checks") for d in c["doubts"])
    assert any(d.startswith("B: no analytic estimate attached") for d in c["doubts"])


# ============================================================================= item 3: pre-flight

def test_preflight_unknown_group_and_circuit(tmp_path):
    fake = FakeFemm("ccore.fem")
    with pytest.raises(ValueError, match=r"no objects in group \[7\].*groups present in the model: \[0, 1, 2, 3\]"):
        ex.force_vs_position(fake, [7], dy=0.5, steps=3, out_dir=tmp_path)
    assert not any(n == "mi_analyze" for n, _ in fake.calls)          # refused before any solve
    with pytest.raises(ValueError, match=r"circuit not in the model: \['X'\].*circuits present: \['coil'\]"):
        ex.force_vs_position(fake, [1], dy=0.5, steps=3, circuits=["X"], out_dir=tmp_path)
    fake = FakeFemm("spm_age.fem")
    with pytest.raises(preflight.PreflightError) as ei:
        ex.cogging(fake, [9], slots=12, poles=4, steps=5, out_dir=tmp_path)
    assert "femm_set_group" in ei.value.hint
    with pytest.raises(preflight.PreflightError, match="drive.circuits"):
        ex.torque_vs_angle(fake, [1], steps=3, drive={"circuits": ["U", "V", "W"], "poles": 4, "iq": 1},
                           out_dir=tmp_path)
    # method='age' does not rotate groups, so rotate_groups is not checked there
    ex.cogging(fake, [99], slots=12, poles=4, steps=5, method="age", gap_boundary="AGE", out_dir=tmp_path)


def test_preflight_error_is_an_input_error_in_the_envelope():
    def boom():
        raise preflight.PreflightError("no objects in group [7] (groups); groups present in the model: [0, 1]",
                                       "Use groups from [0, 1]")
    r = _common.envelope(boom)
    assert r["ok"] is False and r["error"]["hint"] == "Use groups from [0, 1]" and "trace" not in r["error"]
    assert r["error"]["message"].startswith("no objects in group")


class _Model:
    """Minimal parsed-model stand-in: a 90 deg sector with periodic radial edges."""

    def __init__(self, ptype=4):
        self.geometry = {"NumSegments": [[0, 1, -1, 1, 0, 0], [2, 3, -1, 1, 0, 0], [1, 3, -1, 0, 0, 0]]}
        self._pts = [(10, 0), (50, 0), (0, 10), (0, 50)]
        self._b = [{"BdryName": "per", "BdryType": ptype}]

    def points(self):
        return self._pts

    def boundaries(self):
        return self._b


def test_sector_detection_and_warning(tmp_path):
    assert preflight.sector_extent_deg(_Model()) == pytest.approx(90)
    assert preflight.sector_extent_deg(_Model(ptype=0)) is None
    w = preflight.sector_warnings(_Model(), slots=12, poles=4)
    assert len(w) == 1 and "90 deg sector (1/4 of the machine)" in w[0] and "x 4 for the full machine" in w[0]
    w = preflight.sector_warnings(_Model(), slots=12, poles=6)        # 1.5 poles per sector
    assert any(x.startswith("poles=6 gives 1.5 per") for x in w)
    full_model = femfile.parse_file(FIX / "spm_age.fem")
    assert preflight.sector_extent_deg(full_model) is None             # AGE alone is not a sector
    assert ex.cogging(FakeFemm("spm_age.fem"), [1], slots=12, poles=4, steps=5,
                      out_dir=tmp_path)["warnings"] == []


# ============================================================================= item 4: hints

def test_hint_table_and_defaults():
    assert "femm_add_circuit" in _common.ToolInputError("the model has no circuits").hint
    assert "femm_geometry_summary" in _common.ToolInputError("no boundary named 'X' in the model").hint
    assert _common.ToolInputError("something new").hint == _common.DEFAULT_INPUT_HINT
    assert _common.ToolInputError("x", "custom").hint == "custom"
    h = _common.hint_for(Exception("FEMM did not answer within 600 s (timeout)"))
    assert "timeout=<2x" in h and "femm_session_list" in h
    r = _common.envelope(lambda: (_ for _ in ()).throw(ValueError("method='age' needs gap_boundary")))
    assert "gap_boundary=<name" in r["error"]["hint"]
    r = _common.envelope(lambda: (_ for _ in ()).throw(ValueError("unrelated")))
    assert r["error"]["hint"] == "Check the argument types and units in the tool description." and "trace" in r["error"]


def test_experiment_value_errors_carry_hints(tmp_path):
    fake = FakeFemm("spm_age.fem")
    cases = [
        (lambda: ex.cogging(fake, [1], slots=12, poles=4, steps=5, method="age", out_dir=tmp_path), "gap_boundary=<name"),
        (lambda: ex.cogging(fake, [1], slots=12, poles=4, steps=5, method="age", gap_boundary="nope", out_dir=tmp_path),
         "['A=0', 'AGE']"),
        (lambda: ex.cogging(fake, [1], slots=12, poles=4, steps=5, method="age", gap_boundary="A=0", out_dir=tmp_path),
         "['AGE']"),
        (lambda: ex.cogging(fake, [1], slots=12, poles=4, steps=5, method="spin", out_dir=tmp_path), "method='rotate'"),
        (lambda: ex.force_vs_position(FakeFemm("ccore.fem"), [1], steps=3, out_dir=tmp_path), "dy=0.25"),
        (lambda: ex.collect_output(None, {"kind": "nope"}), "kind point"),
    ]
    for fn, frag in cases:
        r = _common.envelope(fn)
        assert r["ok"] is False and frag in r["error"]["hint"], (frag, r["error"])
        assert "trace" not in r["error"] and "Check the argument types" not in r["error"]["hint"]


# ============================================================================= item 5: vocabulary

def test_resolve_pole_pairs():
    assert estimate.resolve_pole_pairs(poles=4) == 2
    assert estimate.resolve_pole_pairs(pole_pairs=3) == 3
    for kw in ({}, {"poles": 4, "pole_pairs": 2}, {"poles": 5}, {"pole_pairs": 0}):
        with pytest.raises(estimate.EstimateInputError) as ei:
            estimate.resolve_pole_pairs(**kw)
        assert "poles" in ei.value.hint


def test_back_emf_accepts_both_spellings(tmp_path):
    a = ex.back_emf(FakeFemm("spm_age.fem", pole_pairs=2), [1], poles=4, rpm=1500, steps=24, out_dir=tmp_path)
    b = ex.back_emf(FakeFemm("spm_age.fem", pole_pairs=2), [1], pole_pairs=2, rpm=1500, steps=24, out_dir=tmp_path)
    assert a["experiment"] == "back_emf" and a["parameters"]["poles"] == 4 and a["parameters"]["pole_pairs"] == 2
    assert a["summary"]["emf_fundamental_peak_V"]["A"] == pytest.approx(b["summary"]["emf_fundamental_peak_V"]["A"])
    for kw in ({}, {"poles": 4, "pole_pairs": 2}):
        with pytest.raises(ValueError):
            ex.back_emf(FakeFemm("spm_age.fem"), [1], steps=6, out_dir=tmp_path, **kw)
    assert ex.backemf is ex.back_emf


def test_dq_dicts_accept_poles(tmp_path):
    c1 = ex.dq_currents({"circuits": ["A", "B", "C"], "poles": 4, "iq": 10}, 7.0)
    c2 = ex.dq_currents({"circuits": ["A", "B", "C"], "pole_pairs": 2, "iq": 10}, 7.0)
    assert c1 == pytest.approx(c2)
    with pytest.raises(ValueError):
        ex.dq_currents({"iq": 10}, 0.0)                     # neither: no silent p = 1 any more
    r = ex.inductance(FakeFemm("spm_age.fem", L=2e-3), dq={"circuits": ["A", "B", "C"], "poles": 4, "id": 2, "iq": 2},
                      out_dir=tmp_path)
    assert r["summary"]["torque_dq_at_iq_Nm"] == pytest.approx(1.5 * 2 * 0.05 * 2)


def test_tool_rename_and_aliases(full):
    _mcp, ctx, _ = full
    names = set(ctx.extras["tools"])
    assert "femm_experiment_back_emf" in names and "femm_experiment_backemf" not in names
    r = tool(ctx, "femm_estimate", name="dq_torque", args={"poles": 4, "psi_d": 0.05, "psi_q": 0, "i_d": 0, "i_q": 10})
    r2 = tool(ctx, "femm_estimate", name="dq_torque", args={"pole_pairs": 2, "psi_d": 0.05, "psi_q": 0, "i_d": 0, "i_q": 10})
    assert r["result"]["value"] == pytest.approx(1.5) == r2["result"]["value"]
    r = tool(ctx, "femm_estimate", name="dq_torque", args={"poles": 4, "pole_pairs": 2, "psi_d": 0.05, "psi_q": 0,
                                                            "i_d": 0, "i_q": 10})
    assert not r["ok"] and "exactly one" in r["error"]["hint"]
    r = tool(ctx, "femm_estimate", name="spm_flux_linkage_fundamental",
             args={"bg": 0.8, "radius": 0.02, "stack_length": 0.05, "poles": 4, "turns_per_phase": 100})
    assert r["result"]["value"] == pytest.approx(estimate.spm_flux_linkage_fundamental(0.8, 0.02, 0.05, 2, 100))
    assert tool(ctx, "femm_estimate", name="cogging_period_deg", args={"slots": 12, "poles": 4})["result"]["value"] == 30
    cf = tool(ctx, "femm_estimate", name="carter_factor", args={"slot_pitch": 0.01, "slot_opening": 0.002, "gap": 0.001})
    cc = tool(ctx, "femm_estimate", name="carter_coefficient", args={"slot_pitch": 0.01, "slot_opening": 0.002, "gap": 0.001})
    assert cf["result"]["value"] == cc["result"]["value"] > 1 and cf["result"]["alias_of"] == "carter_coefficient"
    lst = tool(ctx, "femm_check_rule", rule="list")["result"]
    assert "power_balance_ac (alias: power_balance)" in lst
    for rule in ("power_balance", "power_balance_ac"):
        assert tool(ctx, "femm_check_rule", rule=rule, args={"p_input": 1.0, "p_losses": 1.0})["result"]["ok"] is True


# ============================================================================= item 6: L(I)

def test_l_of_i_pure():
    cur = [1.0, 2.0, 3.0]
    psi0 = 0.1
    psis = [psi0 + 0.5 * i - 0.05 * i * i for i in cur]          # psi = psi0 + a I - b I^2 (saturating)
    from femm_agent.experiments_sweeps import l_of_i
    rows = l_of_i(cur, psis, psi0)
    assert [r["L_secant"] for r in rows] == pytest.approx([0.5 - 0.05 * i for i in cur])
    # central differences through the neighbours (0 A included), one-sided at the top end
    grid = [0.0] + cur
    f = [psi0] + psis
    expect = [(f[2] - f[0]) / 2, (f[3] - f[1]) / 2, (f[3] - f[2]) / 1]
    assert [r["L_incremental"] for r in rows] == pytest.approx(expect) and grid[-1] == 3.0


def test_inductance_currents_offline(tmp_path):
    fake = FakeFemm("spm_age.fem", L=2e-3)
    r = ex.inductance(fake, circuits=["A"], currents=[1, 2, 4], out_dir=tmp_path)
    assert r["columns"] == ["circuit", "current_A", "psi_Wb", "L_secant_H", "L_incremental_H"]
    assert [row[1] for row in r["rows"]] == [1, 2, 4]
    assert all(row[3] == pytest.approx(2e-3) and row[4] == pytest.approx(2e-3) for row in r["rows"])
    assert Path(r["files"]["csv"]).is_file() and Path(r["files"]["json"]).is_file()
    assert fake.currents["A"] == 0.0                                  # restored
    for bad in ([], [0, 1], [1, 1]):
        with pytest.raises(ValueError):
            ex.inductance(FakeFemm("spm_age.fem"), currents=bad, out_dir=tmp_path)


# ============================================================================= item 7: estimates

def test_estimate_listing_and_verdicts(full):
    _mcp, ctx, _ = full
    lst = tool(ctx, "femm_estimate")["result"]
    assert set(lst) == set(estimate_meta.names()) and "carter_factor" in lst
    assert lst["dq_torque"]["args"][0] == "poles (or pole_pairs)"
    assert all({"args", "unit", "formula", "assumptions", "expected_fea_tolerance_pct"} <= set(v) for v in lst.values())
    args = {"turns": 200, "current": 2, "gap": 0.002}
    ref = estimate.ccore_gap_b(**args)
    r = tool(ctx, "femm_estimate", name="ccore_gap_b", args=args)["result"]
    assert r["unit"] == "T" and r["expected_fea_tolerance_pct"] == 2.0 and "verdict" not in r
    assert tool(ctx, "femm_estimate", name="ccore_gap_b", args=args, fem_value=ref * 1.01)["result"]["verdict"] == "PASS"
    chk = tool(ctx, "femm_estimate", name="ccore_gap_b", args=args, fem_value=ref * 1.03)["result"]
    assert chk["verdict"] == "CHECK" and chk["ratio_fem_over_formula"] == pytest.approx(1.03)
    assert tool(ctx, "femm_estimate", name="ccore_gap_b", args=args, fem_value=ref * 2)["result"]["verdict"] == "FAIL"
    r = tool(ctx, "femm_estimate", name="skin_depth", args={"freq": 50, "sigma": 5.8e7})["result"]
    assert r["expected_fea_tolerance_pct"] == 10.0 and "default 10 %" in r["assumptions"]
    r = tool(ctx, "femm_estimate", name="pm_load_line", args={"br": 1.2, "mu_r": 1.05, "magnet_length": 0.003,
                                                              "gap": 0.001}, fem_value=0.9)
    assert not r["ok"] and "compare_to_estimate" in r["error"]["hint"]


# ============================================================================= item 8: force vs position state

class _FailFinalSolve(FakeFemm):
    def __init__(self, *a, fail_at: int, **k):
        super().__init__(*a, **k)
        self.fail_at, self.n = fail_at, 0

    def call(self, name, *args, timeout=None):
        if name == "mi_analyze":
            self.n += 1
            if self.n == self.fail_at:
                raise RuntimeError("solver crashed")
        return super().call(name, *args, timeout=timeout)


def test_force_vs_position_restore_state(tmp_path):
    ok = ex.force_vs_position(FakeFemm("ccore.fem"), [1], dy=0.5, steps=3, out_dir=tmp_path)
    assert ok["left_solved"] is True and ok["warnings"] == []
    bad = ex.force_vs_position(_FailFinalSolve("ccore.fem", fail_at=4), [1], dy=0.5, steps=3, out_dir=tmp_path)
    assert bad["left_solved"] is False and "femm_solve()" in bad["warnings"][0]
    assert len(bad["rows"]) == 3                                       # the sweep itself stands

    s = Session(name="main", link=_FailFinalSolve("ccore.fem", fail_at=4), work_dir=tmp_path)
    s.physics, s.document = "magnetics", None
    out = tool_exp._run(s, ex.force_vs_position, groups=[1], dy=0.5, steps=3)
    assert s.solved is False and s.checked is False and out["next"].startswith("femm_solve(session='main')")
    s2 = Session(name="main", link=FakeFemm("ccore.fem"), work_dir=tmp_path)
    s2.physics = "magnetics"
    out = tool_exp._run(s2, ex.force_vs_position, groups=[1], dy=0.5, steps=3)
    assert s2.solved is True and s2.checked is False and "next" not in out


# ============================================================================= item 9: guide, doctor, instructions

def test_guide_offline(full):
    _mcp, ctx, _ = full
    r = tool(ctx, "femm_guide")["result"]
    assert "femm-magnetics" in r["text"] and r["topic"] == "femm"
    assert {"femm", "femm-magnetics", "femm-health-check"} <= {s["name"] for s in r["skills"]}
    t = tool(ctx, "femm_guide", topic="femm-health-check")["result"]
    assert "rules.md" in t["references"] and t["text"].startswith("---")
    ref = tool(ctx, "femm_guide", topic="femm-health-check", reference="rules")["result"]
    assert "compare_to_estimate" in ref["text"]
    assert tool(ctx, "femm_guide", reference="rules.md")["result"]["topic"] == "femm-health-check"
    assert not tool(ctx, "femm_guide", topic="nope")["ok"]
    assert not tool(ctx, "femm_guide", topic="femm", reference="../../pyproject.toml")["ok"]
    assert guide.facts_path() is not None
    assert "FEMM" in tool(ctx, "femm_facts")["result"]["text"]


def test_doctor_rows(monkeypatch, tmp_path):
    c = doctor.check_femm_install(find=lambda: None, candidates=lambda: [tmp_path])
    assert c.status == doctor.FAIL and "FEMM_DIR" in c.fix
    assert doctor.check_executables(None).status == doctor.FAIL
    (tmp_path / "femm_headless.exe").write_text("")

    class Inst:
        bin_dir, headless = tmp_path, tmp_path / "femm_headless.exe"
    assert doctor.check_executables(Inst()).status == doctor.WARN          # no femm_gui
    (tmp_path / "femm_gui.exe").write_text("")
    assert doctor.check_executables(Inst()).status == doctor.PASS
    sk = tmp_path / "skills"
    assert doctor.check_skills(sk, plugin_dirs=[]).status == doctor.WARN
    (sk / "femm").mkdir(parents=True)
    (sk / "femm" / "SKILL.md").write_text("x")
    assert doctor.check_skills(sk, plugin_dirs=[]).status == doctor.PASS
    assert doctor.check_writable("w", tmp_path / "w", "X").status == doctor.PASS
    assert doctor.check_optional("surely_not_a_module_xyz", "t").status == doctor.WARN
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    try:
        assert doctor.check_port(s.getsockname()[1]).status == doctor.WARN
    finally:
        s.close()
    assert doctor.check_catalogs().status == doctor.PASS
    monkeypatch.setattr(doctor, "check_mcp", lambda: 1 / 0)
    rows = doctor.run_checks()
    assert {r.name for r in rows} >= {"femm install", "default port", "state dir", "skills", "catalogs"}
    crashed = [r for r in rows if r.name == "mcp package"][0]
    assert crashed.status == doctor.FAIL and "crashed" in crashed.detail
    rep = doctor.report(rows)
    assert rep["ok"] is False and rep["version"] and all(set(r) == {"name", "status", "detail", "fix"} for r in rep["checks"])
    assert "fix:" in doctor.format_table(rows)


def test_doctor_tool_and_cli(full, capsys, monkeypatch):
    _mcp, ctx, _ = full
    r = tool(ctx, "femm_doctor")
    assert r["ok"] and r["result"]["checks"]
    import sys
    from femm_agent import __main__ as main_mod
    monkeypatch.setattr(sys, "argv", ["femm_agent", "--version"])
    with pytest.raises(SystemExit) as e:
        main_mod.main()
    assert e.value.code == 0 and __import__("femm_agent").__version__ in capsys.readouterr().out
    monkeypatch.setattr(doctor, "run_checks", lambda: [doctor.Check("x", doctor.PASS, "ok")])
    monkeypatch.setattr(sys, "argv", ["femm_agent", "--doctor", "--json"])
    with pytest.raises(SystemExit) as e:
        main_mod.main()
    assert e.value.code == 0 and json.loads(capsys.readouterr().out)["ok"] is True


def test_instructions_name_registered_tools(full):
    _mcp, ctx, _ = full
    registered = set(ctx.extras["tools"])
    tokens = set(re.findall(r"femm_[a-z0-9_]+\*?", INSTRUCTIONS))
    exact = {t for t in tokens if not t.endswith("*")}
    wildcards = {t[:-1] for t in tokens if t.endswith("*")}
    assert exact and not (exact - registered), exact - registered
    assert wildcards and all(any(t.startswith(w) for t in registered) for w in wildcards)
    assert "femm_guide" in INSTRUCTIONS and "ok:false is a stop sign" in INSTRUCTIONS


def test_parametric_template_errors_are_per_case(tmp_path):
    fake = FakeFemm("ccore.fem")
    outs = [{"name": "psi", "kind": "circuit", "circuit": "coil", "quantity": "flux"}]
    cases = [{"name": "nokey", "params": {"J": 1}}, {"name": "good", "params": {"I": 2}}]
    r = ex.parametric(fake, cases, outs, template="x = {I}", out_dir=tmp_path)
    errs = r["summary"]["errors"]
    assert errs == [{"case": "nokey", "error": "KeyError: 'I'"}]
    assert r["rows"][1][-1] is not None                                 # the next case still ran
    r = ex.parametric(fake, cases[1:], outs, template="d = {'a': 1}", out_dir=tmp_path)
    assert r["summary"]["errors"][0]["error"] == "KeyError: \"'a'\""     # single braces
    r = ex.parametric(fake, cases[1:], outs, template="d = {{'a': 1}}", out_dir=tmp_path)
    assert not r["summary"]["errors"]                                   # doubled braces are literal
