"""Regression tests for the review findings on 0.2.0 (offline, fake engines; live ones in
tests/live/test_live_v020.py)."""
import inspect
import math
import subprocess
import sys
from pathlib import Path

import pytest

from femm_agent import benchmarks, estimate_meta, health, preflight, reporting
from femm_agent import experiments as ex
from femm_agent.experiments_sweeps import l_of_i, l_of_i_warnings
from femm_agent.sessions import Session
from femm_agent.tools import experiments as tool_exp
from test_experiments import FIX, FakeFemm
from test_server_tools import FakeEngine, FakeSessions, tool
from test_v020 import _FailFinalSolve, _Model

CCORE = (FIX / "ccore.fem").read_text(encoding="utf-8")


def _variant(tmp_path: Path, name: str, text: str) -> str:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return name


def _fake(tmp_path, text, **kw) -> FakeFemm:
    f = FakeFemm("ccore.fem", **kw)
    f.fixture = tmp_path / _variant(tmp_path, "variant.fem", text)
    return f


CCORE_EMPTY_B = CCORE.replace("[CircuitProps]  = 1", "[CircuitProps]  = 2").replace(
    "  <EndCircuit>\n[NumPoints]",
    '  <EndCircuit>\n  <BeginCircuit>\n    <CircuitName> = "B"\n    <TotalAmps_re> = 0\n    <TotalAmps_im> = 0\n'
    "    <CircuitType> = 1\n  <EndCircuit>\n[NumPoints]")   # circuit B appended (label links stay on coil)


# ============================================================================= 1: empty circuits

def test_fixture_variant_has_an_empty_circuit():
    from femm_agent import femfile
    m = femfile.parse_text(CCORE_EMPTY_B, ext=".fem")
    assert [c["CircuitName"] for c in m.circuits()] == ["coil", "B"]
    assert preflight.circuit_turns(m)["B"] == 0 and preflight.circuit_turns(m)["coil"] == 400   # +200 / -200
    assert preflight.active_circuits(m) == ["coil"]


def test_circuit_without_labels_is_refused(tmp_path):
    fake = _fake(tmp_path, CCORE_EMPTY_B)
    with pytest.raises(preflight.PreflightError, match=r"circuit \['B'\].*no coil labels") as ei:
        ex.inductance(fake, circuits=["B"], current=1.0, out_dir=tmp_path)
    assert "femm_set_block_prop" in ei.value.hint
    assert not any(n == "mi_analyze" for n, _ in fake.calls)
    r = ex.inductance(_fake(tmp_path, CCORE_EMPTY_B), current=1.0, out_dir=tmp_path)   # default: empty one skipped
    assert r["summary"]["circuits"] == ["coil"] and "['B']" in r["warnings"][0]


def test_energy_consistency_zero_zero_is_not_a_pass():
    r = health.energy_consistency(0.0, [0.0], [1.0])
    assert r["ok"] is False and "femm_set_block_prop" in r["message"]
    assert health.energy_consistency(0.0, [0.0], [0.0])["ok"] is None          # nothing excited: n/a
    assert health.energy_consistency(0.5, [1.0], [1.0])["ok"] is True


# ============================================================================= 2: L_incremental

def test_l_of_i_sparse_nonuniform_grid_stays_positive():
    cur = [20.0, 1.0, 5.0, 2.0]                                     # unsorted on purpose
    psi = [0.03 * math.tanh(i / 3) for i in cur]
    rows = l_of_i(cur, psi, 0.0)
    assert [r["current"] for r in rows] == [1.0, 2.0, 5.0, 20.0]    # sorted by current
    assert all(r["L_incremental"] > 0 for r in rows)
    assert rows[-1]["L_incremental"] == pytest.approx((0.03 * math.tanh(20 / 3) - 0.03 * math.tanh(5 / 3)) / 15)
    assert rows[1]["L_incremental"] == pytest.approx((0.03 * math.tanh(5 / 3) - 0.03 * math.tanh(1 / 3)) / 4)


def test_l_of_i_warns_on_unreliable_increments():
    lin = l_of_i([1.0, 2.0, 3.0], [1e-3, 2e-3, 3e-3], 0.0)
    assert [r["L_incremental"] for r in lin] == pytest.approx([1e-3] * 3) and l_of_i_warnings(lin) == []
    odd = l_of_i([1.0, 2.0], [1e-3, 0.9e-3], 0.0)                   # psi falls: dpsi/dI < 0 at 2 A
    w = l_of_i_warnings(odd, "coil")
    assert w and "limited by the current spacing" in w[0] and "[2.0]" in w[0]


# ============================================================================= 3: session state on failure

def test_failed_experiment_leaves_session_unsolved(tmp_path):
    s = Session(name="main", link=_FailFinalSolve("ccore.fem", fail_at=2), work_dir=tmp_path)
    s.physics = "magnetics"
    s.solved = True
    s.checked = True
    with pytest.raises(RuntimeError, match="solver crashed"):
        tool_exp._run(s, ex.force_vs_position, groups=[1], dy=0.5, steps=4)
    assert s.solved is False and s.checked is False
    assert s.link.y == pytest.approx(0)                             # geometry restored after the failure


def test_refused_experiment_keeps_session_state(tmp_path):
    s = Session(name="main", link=FakeFemm("ccore.fem"), work_dir=tmp_path)
    s.physics = "magnetics"
    s.solved = True
    s.checked = True
    with pytest.raises(preflight.PreflightError):
        tool_exp._run(s, ex.force_vs_position, groups=[7], dy=0.5, steps=3)
    assert s.solved is True and s.checked is True


# ============================================================================= 4: import order

def test_experiments_sweeps_imports_alone():
    src = str(Path(__file__).resolve().parents[1] / "src")
    for mod in ("femm_agent.experiments_sweeps", "femm_agent.experiments_core", "femm_agent.experiments"):
        r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {src!r}); import {mod}"],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, (mod, r.stderr)
    r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {src!r}); "
                        "from femm_agent.experiments_sweeps import l_of_i; print(l_of_i([1.0], [2.0], 0.0))"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "L_secant" in r.stdout, r.stderr


# ============================================================================= 5: poles everywhere

class _Recorder:
    def __init__(self):
        self.calls = []

    def call(self, name, *args, timeout=None):
        self.calls.append((name, args))
        return None


def test_build_spm_accepts_poles_and_pole_pairs(tmp_path):
    a = benchmarks.build_spm(_Recorder(), (tmp_path / "a.fem").as_posix(), poles=8)
    b = benchmarks.build_spm(_Recorder(), (tmp_path / "b.fem").as_posix(), pole_pairs=4)
    d = benchmarks.build_spm(_Recorder(), (tmp_path / "d.fem").as_posix())
    assert a["pole_pairs"] == b["pole_pairs"] == 4 and a["poles"] == 8 and d["poles"] == 4
    with pytest.raises(ValueError):
        benchmarks.build_spm(_Recorder(), (tmp_path / "c.fem").as_posix(), poles=8, pole_pairs=4)


def test_cogging_and_cogging_period_accept_pole_pairs(tmp_path):
    r = ex.cogging(FakeFemm("spm_age.fem"), [1], slots=12, pole_pairs=2, steps=7, out_dir=tmp_path)
    assert r["summary"]["period_deg"] == 30 and r["parameters"]["poles"] == 4
    with pytest.raises(ValueError):
        ex.cogging(FakeFemm("spm_age.fem"), [1], slots=12, steps=7, out_dir=tmp_path)
    assert estimate_meta.normalize_args("cogging_period_deg", {"slots": 12, "pole_pairs": 2}) == {"slots": 12, "poles": 4}
    assert estimate_meta.normalize_args("cogging_period_deg", {"slots": 12, "poles": 4}) == {"slots": 12, "poles": 4}
    with pytest.raises(ValueError):
        estimate_meta.normalize_args("cogging_period_deg", {"slots": 12, "poles": 4, "pole_pairs": 2})


@pytest.fixture()
def full(tmp_path):
    from femm_agent.server import build_server
    eng = FakeEngine()
    mcp, ctx = build_server(FakeSessions(eng, tmp_path))
    yield mcp, ctx, eng
    ctx.sessions.close_all()


def test_tools_accept_pole_pairs_for_poles_formulas(full):
    _mcp, ctx, _ = full
    r = tool(ctx, "femm_estimate", name="cogging_period_deg", args={"slots": 12, "pole_pairs": 2})
    assert r["ok"] and r["result"]["value"] == 30
    sig = inspect.signature(ctx.extras["tools"]["femm_experiment_cogging"]).parameters
    assert "pole_pairs" in sig and sig["poles"].default is None


# ============================================================================= 6: estimates recorded for the report

def test_estimate_with_session_clears_the_doubt(full):
    _mcp, ctx, _ = full
    tool(ctx, "femm_new_document", physics="magnetics")
    d0 = tool(ctx, "femm_report", include=["experiments"])["result"]["doubts"]
    assert any(d.startswith("no analytic estimate attached") for d in d0)
    args = {"turns": 200, "current": 2, "gap": 0.002}
    ref = 4e-7 * math.pi * 200 * 2 / 0.002
    r = tool(ctx, "femm_estimate", name="ccore_gap_b", args=args, fem_value=ref * 1.03, session="main")
    assert r["result"]["verdict"] == "CHECK" and r["result"]["recorded_for_session"] == "main"
    d1 = tool(ctx, "femm_report", include=["experiments"])["result"]["doubts"]
    assert not any(d.startswith("no analytic estimate attached") for d in d1)
    assert any(d.startswith("estimate ccore_gap_b: verdict CHECK") for d in d1)


def test_estimate_for_an_unopened_session_is_kept(full):
    _mcp, ctx, _ = full
    r = tool(ctx, "femm_estimate", name="skin_depth", args={"freq": 50, "sigma": 5.8e7}, fem_value=9.35e-3, session="s2")
    assert r["ok"] and "s2" not in ctx.sessions.sessions                       # no engine started
    tool(ctx, "femm_new_document", physics="magnetics", session="s2")
    d = tool(ctx, "femm_report", include=["experiments"], session="s2")["result"]["doubts"]
    assert not any(x.startswith("no analytic estimate attached") for x in d)


def test_health_fail_is_a_doubt():
    checks = [{"name": "mesh_min_angle", "ok": False}, {"name": "x_vs_analytic", "ok": True}]
    d = reporting.doubts(checks=checks, health_run=True)
    assert d == ["health check verdict FAIL: failing rules ['mesh_min_angle']"]


# ============================================================================= 7: verdict rounding

def test_verdict_band_edges_do_not_flip_on_rounding():
    assert estimate_meta.verdict(1.05, 1.0, 5)["verdict"] == "PASS"
    assert estimate_meta.verdict(1.10, 1.0, 5)["verdict"] == "CHECK"
    assert estimate_meta.verdict(1.1001, 1.0, 5)["verdict"] == "FAIL"
    assert estimate_meta.verdict(0.95, 1.0, 5)["verdict"] == "PASS"


# ============================================================================= 9: label groups for WST

def _geom_only_group(text: str, group: int = 7) -> str:
    """Put the first node of the model into `group` (geometry only, no label)."""
    lines = text.split("\n")
    i = next(k for k, ln in enumerate(lines) if ln.startswith("[NumPoints]"))
    parts = lines[i + 1].split("\t")
    parts[3] = str(group)
    lines[i + 1] = "\t".join(parts)
    return "\n".join(lines)


def test_wst_groups_need_labels(tmp_path):
    text = _geom_only_group(CCORE)
    from femm_agent import femfile
    m = femfile.parse_text(text, ext=".fem")
    assert 7 in preflight.populated_groups(m) and 7 not in preflight.labelled_groups(m)
    preflight.require_groups(m, [7], "rotate_groups")                        # moving geometry: fine
    with pytest.raises(preflight.PreflightError, match=r"no block label in group \[7\]") as ei:
        preflight.require_groups(m, [7], "torque_groups", need_labels=True)
    assert "femm_set_group" in ei.value.hint
    with pytest.raises(preflight.PreflightError, match="no block label"):
        ex.force_vs_position(_fake(tmp_path, text), [1], dy=0.5, steps=3, force_groups=[7], out_dir=tmp_path)
    with pytest.raises(preflight.PreflightError, match="no block label"):
        ex.force_vs_position(_fake(tmp_path, text), [7], dy=0.5, steps=3, out_dir=tmp_path)   # groups = force groups


# ============================================================================= 10: linear periodic models

def test_linear_periodic_model_is_not_a_sector():
    m = _Model()
    m.geometry = {"NumSegments": [[0, 1, -1, 1, 0, 0], [2, 3, -1, 1, 0, 0]]}
    m._pts = [(5, 0), (5, 10), (25, 0), (25, 10)]                  # left/right edges of a linear strip
    assert preflight.sector_extent_deg(m) is None and preflight.sector_warnings(m, slots=12, poles=4) == []
    m._pts = [(10, 0), (50, 0), (0, 10), (0, 50)]                  # radial edges: a 90 deg sector
    assert preflight.sector_extent_deg(m) == pytest.approx(90)


# ============================================================================= 11: force_vs_position restore

def test_force_vs_position_restores_only_the_steps_taken(tmp_path):
    fake = _FailFinalSolve("ccore.fem", fail_at=3)                  # dies on the third step's solve
    with pytest.raises(RuntimeError):
        ex.force_vs_position(fake, [1], dy=0.5, steps=6, start_offset=(0.0, 1.0), out_dir=tmp_path)
    assert fake.y == pytest.approx(0)
    fake = _FailFinalSolve("ccore.fem", fail_at=1)                  # dies on the first solve, after the offset
    with pytest.raises(RuntimeError):
        ex.force_vs_position(fake, [1], dy=0.5, steps=6, start_offset=(0.0, 1.0), out_dir=tmp_path)
    assert fake.y == pytest.approx(0)
    for bad in (0, -1):
        with pytest.raises(ex.ExperimentInputError, match="steps must be >= 1"):
            ex.force_vs_position(FakeFemm("ccore.fem"), [1], dy=0.5, steps=bad, out_dir=tmp_path)
