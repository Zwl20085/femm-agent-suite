"""Offline tests for the report builder and A/B comparison."""
import json
from pathlib import Path

from femm_agent import femfile, health, reporting

FIX = Path(__file__).parent / "fixtures"


def _result(scale=1.0, name="cogging"):
    rows = [[a, scale * 0.1 * (a - 15) / 15, a * 0.0] for a in range(0, 31, 5)]
    return {"experiment": name, "parameters": {"slots": 12, "poles": 4}, "columns": ["angle_deg", "torque_Nm", "zero"],
            "rows": rows, "summary": {"peak_to_peak_Nm": 0.2 * scale, "period_deg": 30.0, "nested": {"a": 1.0}},
            "health": [health.zero_mean([r[1] for r in rows])], "files": {},
            "timing": {"total_s": 1.0, "solves": 7, "per_solve_s": 0.14}}


def test_md_table_downsamples():
    t = reporting.md_table(["a", "b"], [[i, i * 0.5] for i in range(100)], max_rows=10)
    assert "rows omitted" in t
    assert "| 99 |" in t
    assert t.count("\n| ") <= 13


def test_build_report(tmp_path):
    summ = femfile.summarize_file(FIX / "ccore.fem")
    fig = tmp_path / "f.png"
    fig.write_bytes(b"\x89PNG\r\n\x1a\n")
    res = _result()
    res["files"] = {"png_torque": str(fig)}
    out = reporting.build_report(tmp_path / "rep", "Test report", model_summary=summ, experiments=[res],
                                 checks=[health.mesh_size(10), health.mesh_size(5000)], figures=[("a figure", str(fig))])
    md = Path(out["markdown"]).read_text(encoding="utf-8")
    assert md.startswith("# Test report")
    assert "FAIL" in md and "PASS" in md and "mesh_element_count" in md
    assert "Linear iron mu2000" in md and "### cogging" in md
    assert "figures/" in md
    data = json.loads(Path(out["json"]).read_text(encoding="utf-8"))
    assert data["experiments"][0]["n_rows"] == 7 and "rows" not in data["experiments"][0]
    assert all(Path(p).is_file() for p in out["figures"])


def test_compare_results(tmp_path):
    a, b = _result(1.0), _result(1.1)
    same = reporting.compare_results(a, a)
    assert same["same_within_rtol"] and same["n_differences"] == 0
    diff = reporting.compare_results(a, b, rtol=0.02)
    keys = {s["key"]: s for s in diff["summary"]}
    assert keys["peak_to_peak_Nm"]["differs"] and not keys["period_deg"]["differs"]
    assert "nested.a" in keys
    col = {c["column"]: c for c in diff["columns"]}
    assert col["torque_Nm"]["differs"] and col["torque_Nm"]["rows_compared"] == 7
    p = tmp_path / "a.json"
    p.write_text(json.dumps(a))
    assert reporting.compare_results(str(p), json.dumps(a))["same_within_rtol"]
