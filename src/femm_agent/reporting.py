"""Markdown + JSON report builder and A/B comparison of experiment results (pure; no FEMM needed).

``build_report`` takes plain dicts (a :func:`femm_agent.femfile.FemmFile.summary`, experiment
results from :mod:`femm_agent.experiments`, health checks) and figure paths, copies the figures next
to the report, and writes ``report.md`` + ``report.json``.
"""
from __future__ import annotations

import json
import math
import shutil
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

MAX_ROWS = 25


def _fmt(v: Any, digits: int = 5) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        if v != v:
            return "nan"
        if v == 0 or 1e-3 <= abs(v) < 1e5:
            return f"{v:.{digits}g}"
        return f"{v:.{digits - 1}e}"
    if isinstance(v, dict) and set(v) <= {"re", "im"}:
        return f"{_fmt(v.get('re'))}{'+' if (v.get('im') or 0) >= 0 else '-'}j{_fmt(abs(v.get('im') or 0))}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_fmt(x, 4) for x in v[:6]) + (", ..." if len(v) > 6 else "") + "]"
    s = str(v)
    return s.replace("|", "\\|").replace("\n", " ")


def md_table(columns: Sequence[str], rows: Sequence[Sequence[Any]], max_rows: int = MAX_ROWS) -> str:
    if not columns:
        return ""
    out = ["| " + " | ".join(_fmt(c) for c in columns) + " |", "|" + "---|" * len(columns)]
    shown = list(rows)
    skipped = 0
    if len(shown) > max_rows:
        step = math.ceil(len(shown) / max_rows)
        sub = shown[::step]
        if sub[-1] is not shown[-1]:
            sub.append(shown[-1])
        skipped = len(shown) - len(sub)
        shown = sub
    for r in shown:
        out.append("| " + " | ".join(_fmt(x) for x in r) + " |")
    if skipped:
        out.append(f"\n*{skipped} of {len(rows)} rows omitted; full table in the CSV.*")
    return "\n".join(out)


def checks_table(checks: Iterable[dict]) -> str:
    rows = []
    for c in checks:
        status = {True: "PASS", False: "FAIL", None: "n/a"}[c.get("ok")]
        rows.append([status, c.get("name"), c.get("value"), c.get("expected"), c.get("message")])
    return md_table(["status", "check", "value", "expected", "message"], rows, max_rows=200)


def model_section(summary: dict) -> str:
    p = summary.get("problem", {})
    lines = [f"- **File:** `{Path(summary['path']).name if summary.get('path') else '-'}`  ",
             f"- **Physics:** {summary.get('physics')} ({summary.get('problem_type')}), units {p.get('LengthUnits')}, "
             f"depth {p.get('Depth')}, frequency {p.get('Frequency', 0)} Hz, precision {p.get('Precision')}, "
             f"min angle {p.get('MinAngle')}",
             f"- **Counts:** " + ", ".join(f"{k} {v}" for k, v in summary.get("counts", {}).items())]
    bb = summary.get("bounding_box")
    if bb:
        lines.append(f"- **Bounding box:** x {_fmt(bb['xmin'])}..{_fmt(bb['xmax'])}, y {_fmt(bb['ymin'])}..{_fmt(bb['ymax'])}")
    if summary.get("solution"):
        s = summary["solution"]
        lines.append(f"- **Solution:** {s.get('nodes')} nodes, {s.get('elements')} elements"
                     + (f", air-gap elements {s.get('air_gap_elements')}" if s.get("air_gap_elements") else ""))
    out = "\n".join(lines) + "\n\n"
    mats = [m for m in summary.get("materials", []) if m.get("labels")]
    if mats:
        keys = [k for k in ("mu_x", "Hc_A_per_m", "J_MA_per_m2", "sigma_MS_per_m", "nonlinear", "magnet",
                            "eps_x", "kx") if any(k in m for m in mats)]
        out += "**Materials in use**\n\n" + md_table(["name", "labels"] + keys,
                                                     [[m["name"], m["labels"]] + [m.get(k) for k in keys] for m in mats]) + "\n\n"
    if summary.get("boundaries"):
        out += "**Boundaries**\n\n" + md_table(["name", "type", "segments"], [[b["name"], b["type_name"], b.get("segments")]
                                                                              for b in summary["boundaries"]]) + "\n\n"
    circ = [c for c in summary.get("circuits", []) if "name" in c]
    if circ:
        out += "**Circuits**\n\n" + md_table(["name", "current (A)", "type", "labels", "net turns"],
                                             [[c["name"], c.get("current_re"), c.get("type_name"), c.get("labels"), c.get("turns")]
                                              for c in circ]) + "\n\n"
    return out


def experiment_section(res: dict, fig_map: dict[str, str]) -> str:
    name = res.get("experiment", "experiment")
    t = res.get("timing", {})
    out = [f"### {name.replace('_', ' ')}\n",
           f"{t.get('solves', '?')} solves in {t.get('total_s', '?')} s ({t.get('per_solve_s', '?')} s per solve).\n"]
    params = {k: v for k, v in (res.get("parameters") or {}).items() if v not in (None, [], {})}
    if params:
        out.append("**Parameters:** " + "; ".join(f"{k} = {_fmt(v)}" for k, v in params.items()) + "\n")
    summ = res.get("summary") or {}
    flat = [(k, v) for k, v in summ.items() if not isinstance(v, (list, dict)) or (isinstance(v, dict) and len(v) <= 4)]
    if flat:
        out.append(md_table(["quantity", "value"], [[k, v] for k, v in flat]) + "\n")
    for key, path in res.get("files", {}).items():
        if key.startswith("png_") and not key.endswith("_error") and path in fig_map:
            out.append(f"![{name} {key[4:]}]({fig_map[path]})\n")
    if res.get("columns") and res.get("rows"):
        out.append("<details><summary>data table</summary>\n\n" + md_table(res["columns"], res["rows"]) + "\n\n</details>\n")
    if res.get("health"):
        out.append("**Checks**\n\n" + checks_table(res["health"]) + "\n")
    return "\n".join(out) + "\n"


def build_report(out_dir: str | Path, title: str, *, model_summary: dict | None = None,
                 experiments: Sequence[dict] = (), checks: Sequence[dict] = (),
                 figures: Sequence[tuple[str, str]] = (), notes: str | None = None) -> dict[str, Any]:
    """Write ``report.md`` + ``report.json`` (+ ``figures/``) into ``out_dir``; returns their paths."""
    out = Path(out_dir)
    figdir = out / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    fig_map: dict[str, str] = {}

    def take(path: str) -> str | None:
        p = Path(path)
        if not p.is_file():
            return None
        dest = figdir / (p.parent.name + "_" + p.name if p.parent.name else p.name)
        if p.resolve() != dest.resolve():
            shutil.copyfile(p, dest)
        rel = f"figures/{dest.name}"
        fig_map[str(path)] = rel
        return rel

    for res in experiments:
        for key, path in (res.get("files") or {}).items():
            if key.startswith("png_") and not key.endswith("_error"):
                take(path)
    md = [f"# {title}\n", f"*Generated {time.strftime('%Y-%m-%d %H:%M')} by FEMM Agent Suite.*\n"]
    if notes:
        md.append(notes + "\n")
    if checks:
        fails = [c for c in checks if c.get("ok") is False]
        md.append("## Health checks\n")
        md.append(("All applicable checks pass." if not fails else f"**{len(fails)} check(s) failing:** "
                   + ", ".join(c["name"] for c in fails)) + "\n")
        md.append(checks_table(checks) + "\n")
    if model_summary:
        md.append("## Model\n")
        md.append(model_section(model_summary))
    figs = []
    for caption, path in figures:
        rel = take(path)
        if rel:
            figs.append((caption, rel))
    if figs:
        md.append("## Figures\n")
        for caption, rel in figs:
            md.append(f"![{caption}]({rel})\n\n*{caption}*\n")
    if experiments:
        md.append("## Experiments\n")
        for res in experiments:
            md.append(experiment_section(res, fig_map))
    md_path = out / "report.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    payload = {"title": title, "model": model_summary, "checks": list(checks),
               "experiments": [{k: v for k, v in r.items() if k != "rows"} | {"n_rows": len(r.get("rows") or [])}
                               for r in experiments],
               "figures": [{"caption": c, "path": str(out / r)} for c, r in figs]}
    json_path = out / "report.json"
    json_path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return {"markdown": str(md_path), "json": str(json_path), "figures": [str(out / r) for _, r in figs]
            + [str(out / v) for v in fig_map.values()]}


# ----------------------------------------------------------------------------- A/B comparison

def _scalar(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict) and "re" in v:
        return float(v["re"])
    return None


def _walk(prefix: str, v: Any, out: dict[str, float]) -> None:
    s = _scalar(v)
    if s is not None:
        out[prefix] = s
    elif isinstance(v, dict):
        for k, x in v.items():
            _walk(f"{prefix}.{k}" if prefix else str(k), x, out)


def load_result(obj: Any) -> dict:
    """Accept a result dict, a JSON string, or a path to an experiment .json file."""
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith("{"):
            return json.loads(s)
        return json.loads(Path(s).read_text(encoding="utf-8"))
    raise TypeError("expected a result dict, JSON text, or a path to a result .json")


def compare_results(a: Any, b: Any, rtol: float = 0.02, label_a: str = "A", label_b: str = "B") -> dict[str, Any]:
    """Compare two experiment outputs: every numeric summary value, and every common numeric column
    (rows matched on the first column, e.g. angle or position). A difference counts when
    |a - b| > rtol * max(|a|, |b|) (columns: relative to the column's peak magnitude)."""
    A, B = load_result(a), load_result(b)
    sa, sb = {}, {}
    _walk("", A.get("summary") or {}, sa)
    _walk("", B.get("summary") or {}, sb)
    summ = []
    for k in sorted(set(sa) & set(sb)):
        x, y = sa[k], sb[k]
        den = max(abs(x), abs(y))
        rel = abs(x - y) / den if den else 0.0
        summ.append({"key": k, label_a: x, label_b: y, "diff": y - x, "rel_diff": rel, "differs": rel > rtol})
    cols = []
    ca, cb = A.get("columns") or [], B.get("columns") or []
    ra, rb = A.get("rows") or [], B.get("rows") or []
    if ca and cb and ra and rb:
        key_a = {(_scalar(r[0]) if _scalar(r[0]) is not None else r[0]): r for r in ra}
        common_rows = [(key_a[k], r) for r in rb for k in [(_scalar(r[0]) if _scalar(r[0]) is not None else r[0])] if k in key_a]
        for name in ca[1:]:
            if name not in cb:
                continue
            ia, ib = ca.index(name), cb.index(name)
            pairs = [(_scalar(x[ia]), _scalar(y[ib])) for x, y in common_rows]
            pairs = [(p, q) for p, q in pairs if p is not None and q is not None]
            if not pairs:
                continue
            peak = max(max(abs(p), abs(q)) for p, q in pairs) or 1.0
            mx = max(abs(p - q) for p, q in pairs)
            rms = math.sqrt(sum((p - q) ** 2 for p, q in pairs) / len(pairs))
            cols.append({"column": name, "rows_compared": len(pairs), "max_abs_diff": mx, "rms_diff": rms,
                         "max_rel_to_peak": mx / peak, "differs": mx / peak > rtol})
    nd = sum(1 for s in summ if s["differs"]) + sum(1 for c in cols if c["differs"])
    return {"experiment": [A.get("experiment"), B.get("experiment")], "rtol": rtol, "summary": summ, "columns": cols,
            "n_differences": nd, "same_within_rtol": nd == 0,
            "timing": {label_a: A.get("timing"), label_b: B.get("timing")}}
