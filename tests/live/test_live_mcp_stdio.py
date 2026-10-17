"""Drive the real server over the MCP stdio protocol (python -m femm_agent) like a client would."""
import asyncio
import json
import os
import sys

import pytest

pytestmark = pytest.mark.live


def _payload(res):
    """Tool result -> envelope dict (structured content if present, else the JSON text block)."""
    sc = getattr(res, "structuredContent", None) or getattr(res, "structured_content", None)
    if isinstance(sc, dict):
        return sc.get("result", sc) if set(sc) == {"result"} else sc
    for block in res.content:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"no payload in {res!r}")


async def _session(work):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ, FEMM_AGENT_WORK=str(work))
    params = StdioServerParameters(command=sys.executable, args=["-m", "femm_agent"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            status = _payload(await session.call_tool("femm_status", {}))
            selftest = _payload(await session.call_tool("femm_selftest", {}))
            return tools, status, selftest


def test_stdio_roundtrip(femm_install, tmp_path):
    tools, status, selftest = asyncio.run(asyncio.wait_for(_session(tmp_path), 120))
    names = {t.name for t in tools.tools}
    assert {"femm_status", "femm_selftest", "femm_solve", "femm_call"} <= names
    assert status["ok"] and status["result"]["install"]["found"]
    assert selftest["ok"] and selftest["result"]["passed"], selftest
