"""Fixtures for live tests: a real FEMM 5 engine is launched (skipped if FEMM is not installed).

Run with:  .venv\\Scripts\\python -m pytest -m live
FEMM is located via FEMM_DIR or the default install folders (config.find_femm).
Set FEMM_AGENT_NO_GUI=1 to skip the tests that open a FEMM window (screenshots).
"""
import json

import pytest

from femm_agent.config import find_femm


@pytest.fixture(scope="session")
def femm_install():
    inst = find_femm()
    if inst is None:
        pytest.skip("FEMM 5 not installed (set FEMM_DIR to its bin folder)")
    return inst


@pytest.fixture(scope="module")
def server(femm_install, tmp_path_factory):
    from femm_agent.server import build_server
    from femm_agent.sessions import SessionManager

    work = tmp_path_factory.mktemp("femm_live")
    mcp, ctx = build_server(SessionManager(install=femm_install, default_work_dir=work))
    yield mcp, ctx
    ctx.sessions.close_all()


@pytest.fixture(scope="module")
def tools(server):
    _mcp, ctx = server
    reg = ctx.extras["tools"]

    def call(_name, **kw):
        r = reg[_name](**kw)
        assert isinstance(r, dict) and "ok" in r and "seconds" in r, r
        json.dumps(r)  # every reply must be JSON-serialisable
        return r

    def ok(_name, **kw):
        r = call(_name, **kw)
        assert r["ok"], f"{_name}({kw}) failed: {r.get('error')}"
        return r["result"]

    call.ok = ok
    return call
