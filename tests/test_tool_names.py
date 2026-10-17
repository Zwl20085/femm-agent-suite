"""Every `femm_*` tool name mentioned in README.md or a skill must be a registered tool."""
import re
from pathlib import Path

from femm_agent.server import build_server
from femm_agent.sessions import SessionManager

ROOT = Path(__file__).resolve().parents[1]
# identifiers that look like tool names but are not tools
NOT_TOOLS = {"femm_agent", "femm_headless", "femm_headlessw", "femm_gui", "femm_dir", "femm_agent_work",
             "femm_agent_no_gui", "femm_lua", "femm_qt", "femm_mcp"}
TOKEN = re.compile(r"(?<![A-Za-z0-9_.\-/\\])femm_[a-z][a-z0-9_]*")


def _docs() -> list[Path]:
    files = [ROOT / "README.md"]
    skills = ROOT / ".claude" / "skills"
    if skills.is_dir():
        files += sorted(skills.rglob("*.md"))
    return [f for f in files if f.is_file()]


def test_documented_tool_names_exist(tmp_path):
    _mcp, ctx = build_server(SessionManager(install=None, default_work_dir=tmp_path))
    registered = set(ctx.extras["tools"])
    missing: dict[str, list[str]] = {}
    for f in _docs():
        for tok in set(TOKEN.findall(f.read_text(encoding="utf-8", errors="replace"))):
            tok = tok.rstrip("_")
            if tok in registered or tok in NOT_TOOLS:
                continue
            missing.setdefault(tok, []).append(str(f.relative_to(ROOT)))
    assert not missing, f"documented but not registered: {missing}"
