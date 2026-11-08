"""Release plumbing: one version everywhere, the CHANGELOG heads with it, README counts match the registry."""
import json
import re
from pathlib import Path

from femm_agent import __version__
from femm_agent.server import build_server
from femm_agent.sessions import SessionManager

ROOT = Path(__file__).resolve().parents[1]


def test_versions_agree():
    py = re.search(r'(?m)^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8")).group(1)
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    assert py == plugin == __version__


def test_changelog_top_heading_is_this_version():
    heads = re.findall(r"(?m)^## (.+)$", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert heads and re.fullmatch(re.escape(__version__) + r" \(\d{4}-\d{2}-\d{2}\)", heads[0]), heads[:2]


def test_readme_tool_counts_match_registry(tmp_path):
    _mcp, ctx = build_server(SessionManager(install=None, default_work_dir=tmp_path))
    n = len(ctx.extras["tools"])
    groups = ctx.extras["groups"]
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"MCP%20tools-{n}-" in text
    claims = [int(x) for x in re.findall(r"(\d+) tools\b", text)]
    assert claims and all(c == n for c in claims), (claims, n)
    assert f"{len(groups)} tool groups" in text or f"in {len(groups)} groups" in text
    rows = dict(re.findall(r"(?m)^\| ([a-z -]+) \| (\d+) \| `femm_", text))
    readme_names = {"mesh and solve": "mesh_solve", "post-processing": "postproc"}
    for label, cnt in rows.items():
        g = readme_names.get(label, label)
        assert len(groups[g]) == int(cnt), (label, cnt, len(groups[g]))
    assert sum(int(c) for c in rows.values()) == n
