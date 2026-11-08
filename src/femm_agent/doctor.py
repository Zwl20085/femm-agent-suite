"""Environment diagnostics: why the MCP server, the FEMM engine or the Claude integration does not work.

No ``mcp`` import, no FEMM session, no network, so it runs even when the server cannot start:
``python -m femm_agent --doctor [--json]`` and the ``femm_doctor`` MCP tool share :func:`run_checks`.
Every check is isolated: an exception inside one becomes a FAIL row for that check. Row shape
mirrors ``jmag_bridge.doctor`` in the sibling suite: {name, status PASS|WARN|FAIL, detail, fix}.
"""
from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import socket
import sys
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from . import __version__

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
MIN_HOST = (3, 10)
MIN_MCP = (1, 10)
DEFAULT_PORT = 48015          # ipc.DEFAULT_PORT (kept literal so this module imports nothing heavy)


@dataclass
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""


def _vtuple(v: str) -> tuple:
    out = []
    for part in v.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            break
        out.append(int(digits))
    return tuple(out)


# =========================================================================== checks

def check_host_python() -> Check:
    v = sys.version_info
    detail = f"{sys.executable} (Python {v.major}.{v.minor}.{v.micro})"
    if (v.major, v.minor) < MIN_HOST:
        return Check("host python", FAIL, detail, "the server needs Python >= 3.10: install it and recreate .venv")
    return Check("host python", PASS, detail)


def check_mcp() -> Check:
    try:
        ver = importlib.metadata.version("mcp")
    except importlib.metadata.PackageNotFoundError:
        return Check("mcp package", FAIL, "not installed in " + sys.executable,
                     "pip install -e . in the repo venv (or rerun scripts/install.ps1 / install.sh)")
    if importlib.util.find_spec("mcp.server") is None:
        return Check("mcp package", FAIL, f"mcp {ver} installed but mcp.server is not importable",
                     'reinstall: pip install --force-reinstall "mcp>=1.10"')
    if _vtuple(ver) < MIN_MCP:
        return Check("mcp package", WARN, f"mcp {ver} (needs >= 1.10)", 'pip install -U "mcp>=1.10"')
    return Check("mcp package", PASS, f"mcp {ver}")


def check_femm_install(find: Callable | None = None, candidates: Callable | None = None) -> Check:
    from . import config

    find = find or config.find_femm
    inst = find()
    if inst is None:
        tried = [str(p) for p in (candidates or config._candidate_bin_dirs)()]
        env = os.environ.get("FEMM_DIR")
        where = f"FEMM_DIR={env} holds no femm_headless" if env else "FEMM_DIR not set and no default location matched"
        return Check("femm install", FAIL, f"{where}; tried {tried[:6]}",
                     "install FEMM 5 from https://www.femm.info or set FEMM_DIR to its bin folder "
                     "(the one holding femm_headless)")
    return Check("femm install", PASS, f"{inst.bin_dir} (FEMM_DIR={'set' if os.environ.get('FEMM_DIR') else 'unset'})")


def check_executables(install) -> Check:
    if install is None:
        return Check("femm executables", FAIL, "no install found", "see the 'femm install' row")
    bin_dir = Path(install.bin_dir)
    have = {n: (bin_dir / n).is_file() for n in ("femm_headlessw.exe", "femm_headless.exe", "femm_headless",
                                                   "femm_gui.exe", "femm_gui", "femm-lua.bat", "femm-lua")}
    present = [n for n, ok in have.items() if ok]
    if not Path(install.headless).is_file():
        return Check("femm executables", FAIL, f"headless engine {install.headless} missing", "repair or reinstall FEMM 5")
    gui = any(have[n] for n in ("femm_gui.exe", "femm_gui"))
    if not gui:
        return Check("femm executables", WARN, f"present: {present}; no femm_gui",
                     "headless work is fine; femm_session_open(headless=False) and femm_save_bitmap need femm_gui")
    return Check("femm executables", PASS, f"present: {present}")


def check_port(port: int = DEFAULT_PORT) -> Check:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
    except OSError as e:
        return Check("default port", WARN, f"127.0.0.1:{port} in use ({e.__class__.__name__})",
                     "an engine or femm_gui is already listening: attach with femm_session_open(attach=True) or pass "
                     "another port; sessions pick a free port automatically")
    finally:
        s.close()
    return Check("default port", PASS, f"127.0.0.1:{port} free")


def check_optional(module: str, purpose: str) -> Check:
    if importlib.util.find_spec(module) is None:
        return Check(module, WARN, f"not installed (optional: {purpose})", f"pip install {module}")
    try:
        ver = importlib.metadata.version(module)
    except importlib.metadata.PackageNotFoundError:
        ver = "?"
    return Check(module, PASS, f"{module} {ver}")


def check_writable(name: str, d: Path, env: str) -> Check:
    probe = d / f".doctor-{os.getpid()}.tmp"
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok")
        probe.unlink()
    except OSError as e:
        return Check(name, FAIL, f"{d} not writable: {e}", f"set {env} to a writable folder")
    return Check(name, PASS, str(d))


def user_skills_dir() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.path.expanduser("~")) / ".claude" / "skills"


def check_skills(dest: Path | None = None, plugin_dirs: list[Path] | None = None) -> Check:
    dest = dest or user_skills_dir()
    installed = sorted(p.name for p in dest.glob("femm*") if (p / "SKILL.md").is_file()) if dest.is_dir() else []
    if installed:
        return Check("skills", PASS, f"{len(installed)} in {dest}: {', '.join(installed)}")
    home = Path(os.path.expanduser("~")) / ".claude" / "plugins"
    for root in (plugin_dirs if plugin_dirs is not None else [home]):
        if root.is_dir() and any(p.is_file() for p in root.rglob("femm/SKILL.md")):
            return Check("skills", PASS, f"femm skills found in a Claude Code plugin under {root}")
    return Check("skills", WARN, f"no femm* skills in {dest} and no femm plugin",
                 "run scripts/install.ps1 (Windows) or scripts/install.sh, or install the plugin; clients without "
                 "skills call femm_guide instead")


def check_catalogs() -> Check:
    from . import catalog
    from .catalog import data_dir

    n = len(catalog.CATALOG)
    idx = data_dir() / "materials" / "name_index.json"
    if n == 0:
        return Check("catalogs", FAIL, catalog.CATALOG.warning or "command catalog empty",
                     "reinstall femm-agent-suite (data/commands.json is missing)")
    if not idx.is_file():
        return Check("catalogs", WARN, f"{n} commands; material name index missing at {idx}",
                     "reinstall femm-agent-suite; material renames will not be suggested")
    return Check("catalogs", PASS, f"{n} commands; material index {idx.name}")


def _guard(name: str, fn: Callable[..., Check], *args) -> Check:
    try:
        return fn(*args)
    except Exception as e:  # one broken check must not hide the others
        return Check(name, FAIL, f"check crashed: {type(e).__name__}: {e}",
                     "report this with the traceback: " + traceback.format_exc(limit=2).replace("\n", " | "))


def run_checks() -> list[Check]:
    from . import config, star

    install = None
    try:
        install = config.find_femm()
    except Exception:
        pass
    work = Path(os.environ.get("FEMM_AGENT_WORK", Path.home() / "femm-agent-work"))
    return [
        _guard("host python", check_host_python),
        _guard("mcp package", check_mcp),
        _guard("femm install", check_femm_install),
        _guard("femm executables", check_executables, install),
        _guard("default port", check_port),
        _guard("numpy", check_optional, "numpy", "experiments, bulk arrays, field maps"),
        _guard("matplotlib", check_optional, "matplotlib", "plots in experiments and reports"),
        _guard("pypdf", check_optional, "pypdf", "femm_manual_section when pdftotext is absent"),
        _guard("state dir", lambda: check_writable("state dir", star.state_dir(), "FEMM_AGENT_HOME")),
        _guard("work dir", lambda: check_writable("work dir", work, "FEMM_AGENT_WORK")),
        _guard("skills", check_skills),
        _guard("catalogs", check_catalogs),
    ]


def summarize(checks: list[Check]) -> str:
    n = {s: sum(c.status == s for c in checks) for s in (PASS, WARN, FAIL)}
    return f"{n[PASS]} pass / {n[WARN]} warn / {n[FAIL]} fail"


def report(checks: list[Check]) -> dict:
    return {"version": __version__, "summary": summarize(checks), "ok": not any(c.status == FAIL for c in checks),
            "checks": [asdict(c) for c in checks]}


def format_table(checks: list[Check]) -> str:
    w = max(len(c.name) for c in checks)
    lines = [f"femm-agent-suite {__version__} doctor: {summarize(checks)}"]
    for c in checks:
        lines.append(f"  {c.status:<4}  {c.name:<{w}}  {c.detail}")
        if c.status != PASS and c.fix:
            lines.append(f"        {'':<{w}}  fix: {c.fix}")
    return "\n".join(lines)


def cli(as_json: bool = False) -> int:
    checks = run_checks()
    print(json.dumps(report(checks), indent=1) if as_json else format_table(checks))
    return 1 if any(c.status == FAIL for c in checks) else 0
