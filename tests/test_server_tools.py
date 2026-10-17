"""Offline tests of the MCP server and the core tool groups against a fake FEMM engine.

The fake speaks the real wire protocol (one line in, one line out) and answers from a small
rule table, so tools run end to end without FEMM installed.
"""
import asyncio
import json
import re
import socket
import threading

import pytest

from femm_agent import ipc
from femm_agent.server import CORE_GROUPS, build_server
from femm_agent.sessions import Session, SessionManager

PV14 = "\t".join(["1e-5", "0.3", "0.4", "0", "12.5", "100", "200", "0", "2.5", "1000", "1000", "0", "0", "1"])


def fake_reply(line: str) -> str:
    rules = [
        (r'^mi_getmaterial\("(Air|Copper|M-19 14 mil)"\)$', ""),
        (r'^mi_getmaterial\("(.*)"\)$', 'error:Couldn\'t load "{0}" from the materials library'),
        (r"^mi_getprobleminfo\(\)$", "0\t0\t10\t0.001"),
        (r"^mo_getprobleminfo\(\)$", "0\t0\t0.01\t0.001"),
        (r"^mo_num(nodes|elements)\(\)$", "6"),
        (r"^mo_getpointvalues\(", PV14),
        (r"^mo_getallelements\(\)$", "\t".join(["1", "2", "3", "0.5", "0.5", "0.25", "1"] * 6)),
        (r"^mo_getallnodes\(\)$", "\t".join(["0", "0", "1", "0", "1", "1"] * 2)),
        (r"^mo_getallb\(\)$", "\t".join(["0.3", "0.4"] * 6)),
        (r"^mo_getcircuitproperties\(", "2\t0.5\t0.01"),
        (r"^mo_blockintegral\(2\)$", "0.125"),
        (r"^mo_getb\(", "error:name 'mo_getb' isn't defined"),
        (r"^mi_selectlabel\(([^)]*)\)$", "{0}"),
        (r"^1\+1$", "2"),
    ]
    for pat, rep in rules:
        m = re.match(pat, line)
        if m:
            return rep.format(*[g.replace(",", "\t") for g in m.groups()])
    return ""


class FakeEngine:
    def __init__(self):
        self.received: list[str] = []
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(4)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _client(self, conn):
        buf = b""
        with conn:
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    return
                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    line = raw.decode().replace("\\\\", "\\")
                    self.received.append(line)
                    if line.startswith("quit"):
                        return
                    conn.sendall((fake_reply(line) + "\n").encode())


class FakeSessions(SessionManager):
    def __init__(self, engine: FakeEngine, work):
        super().__init__(install=None, default_work_dir=work)
        self.engine = engine

    def open(self, name="main", headless=True, port=None, work_dir=None, attach=False):
        if name in self.sessions and self.sessions[name].link.connected:
            return self.sessions[name]
        wd = self.default_work_dir / name
        wd.mkdir(parents=True, exist_ok=True)
        link = ipc.FemmLink(port=self.engine.port, sock=socket.create_connection(("127.0.0.1", self.engine.port)))
        s = Session(name=name, link=link, work_dir=wd)
        self.sessions[name] = s
        return s


@pytest.fixture()
def server(tmp_path):
    eng = FakeEngine()
    mcp, ctx = build_server(FakeSessions(eng, tmp_path), include_engineering=False)
    yield mcp, ctx, eng
    ctx.sessions.close_all()


def tool(ctx, _tool, **kw):
    r = ctx.extras["tools"][_tool](**kw)
    json.dumps(r)
    assert set(r) >= {"ok", "seconds"}
    return r


def test_tool_inventory(server):
    mcp, ctx, _ = server
    groups = ctx.extras["groups"]
    assert set(groups) == set(CORE_GROUPS)
    names = [n for g in groups.values() for n in g]
    assert 55 <= len(names) <= 75, len(names)
    assert len(names) == len(set(names))
    assert all(re.fullmatch(r"femm_[a-z0-9_]+", n) for n in names)
    listed = asyncio.run(mcp.list_tools())
    assert sorted(t.name for t in listed) == sorted(names)
    assert all((t.description or "").strip() for t in listed)
    for must in ("femm_status", "femm_selftest", "femm_solve", "femm_point_values", "femm_call",
                 "femm_run_script", "femm_api_search", "femm_material_search", "femm_gap_results"):
        assert must in names


def test_engineering_groups_optional(tmp_path):
    _mcp, ctx = build_server(FakeSessions(FakeEngine(), tmp_path))
    skipped = ctx.extras["skipped_groups"]
    for g in ("experiments", "health", "report"):
        assert g in ctx.extras["groups"] or g in skipped


def test_model_flow_and_envelopes(server):
    _mcp, ctx, eng = server
    r = tool(ctx, "femm_point_values", points=[[0, 0]])
    assert not r["ok"] and r["session"] == "main" and "femm_new_document" in r["error"]["hint"]
    assert tool(ctx, "femm_new_document", physics="magnetic")["result"]["prefix"] == "mi"
    r = tool(ctx, "femm_problem_define", units="mm", depth=10)
    assert r["ok"] and r["result"]["args"] == [0.0, "millimeters", "planar", 1e-8, 10, 30.0]
    assert "mi_probdef(0.0,\"millimeters\",\"planar\",1e-08,10,30.0)" in eng.received
    r = tool(ctx, "femm_point_values", points=[[0, 0]])
    assert not r["ok"] and "femm_solve" in r["error"]["hint"]
    r = tool(ctx, "femm_material_load", names=["Air", "M-19 Steel"])
    assert r["ok"] and r["result"]["loaded"] == ["Air"] and r["result"]["failed"][0]["best"] == "M-19 14 mil"
    r = tool(ctx, "femm_material_load", names=["M-19 Steel"], fallback_to_suggestion=True)
    assert r["result"]["renamed"] == {"M-19 Steel": "M-19 14 mil"}
    tool(ctx, "femm_draw_rectangle", x1=0, y1=0, x2=1, y2=1)
    r = tool(ctx, "femm_add_block_label", x=0.5, y=0.5, material="Air", group=3)
    assert r["result"]["setblockprop"] == ["Air", 1, 0, "", 0.0, 3, 1]
    r = tool(ctx, "femm_solve")
    assert r["ok"] and r["result"]["elements"] == 6
    assert any(x.startswith("mi_saveas(") for x in eng.received) and "mi_analyze(1)" in eng.received
    r = tool(ctx, "femm_point_values", points=[[0.5, 0.5]])
    v = r["result"]["values"][0]
    assert v["Bx"] == 0.3 and v["By"] == 0.4 and v["|B|"] == pytest.approx(0.5) and v["J_source"] == 2.5
    assert r["result"]["units"]["Bx"] == "T"
    r = tool(ctx, "femm_circuit_results", name="coil")
    assert r["result"]["inductance_H"] == pytest.approx(0.005) and r["result"]["resistance_ohm"] == 0.25
    r = tool(ctx, "femm_block_integral", points=[[0.5, 0.5]], codes=[2])
    assert list(r["result"]["results"].values()) == [0.125]
    assert eng.received.index("mo_clearblock()") < eng.received.index("mo_selectblock(0.5,0.5)")
    fs = tool(ctx, "femm_field_stats")["result"]
    assert fs["elements"] == 6 and fs["stats"]["max"] == pytest.approx(0.5)
    ma = tool(ctx, "femm_mesh_arrays", which="nodes,b", fmt="csv")["result"]
    assert ma["arrays"]["b"]["shape"] == [6, 2] and len(ma["files"]) == 2
    info = tool(ctx, "femm_problem_info")["result"]
    assert info["input"]["depth_problem_units"] == 10 and info["solution"]["depth_m"] == 0.01


def test_call_eval_and_scripts(server, tmp_path):
    _mcp, ctx, eng = server
    tool(ctx, "femm_new_document", physics="magnetics")
    r = tool(ctx, "femm_call", command="mi_addnode", args=[1, 2])
    assert r["ok"] and "warnings" not in r["result"] and "mi_addnode(1,2)" in eng.received
    r = tool(ctx, "femm_call", command="mi_probdef", args=["mm"])
    assert r["ok"] and r["result"]["warnings"]
    r = tool(ctx, "femm_call", command="mo_getb", args=[0, 0])
    assert not r["ok"] and "pyFEMM helper" in r["error"]["hint"]
    r = tool(ctx, "femm_call", command="mi_addnode); quit(", args=[])
    assert not r["ok"]
    assert not tool(ctx, "femm_eval", expression="a=1\nb=2")["ok"]
    r = tool(ctx, "femm_call", command="newdocument", args=[1])
    assert ctx.sessions.get("main").physics == "electrostatics"
    r = tool(ctx, "femm_run_script", code="a = 1\nresult = a\n")
    assert r["ok"] and any(x.startswith("exec(open(") for x in eng.received)
    r = tool(ctx, "femm_run_script", code="x", mode="weird")
    assert not r["ok"]
    j = tool(ctx, "femm_journal")["result"]
    assert "1+1" not in j["lines"]
    ex = tool(ctx, "femm_export_pyfemm_script", path=str(tmp_path / "out.py"))["result"]
    text = (tmp_path / "out.py").read_text()
    assert ex["calls"] > 0 and "femm.mi_addnode(1,2)" in text and "femm.openfemm(1)" in text


def test_offline_tools_need_no_engine(server):
    _mcp, ctx, eng = server
    n = len(eng.received)
    assert tool(ctx, "femm_api_search", query="addnode")["result"]["matches"][0]["name"].endswith("_addnode")
    assert tool(ctx, "femm_api_get", name="mo_blockintegral")["result"]["enums"]
    assert not tool(ctx, "femm_api_get", name="mi_nonsense")["ok"]
    assert tool(ctx, "femm_material_search", query="NdFeB 32 MGOe")["result"]["fem42_rename"] == {"NdFeB 32 MGOe": "N33"}
    assert "families" in tool(ctx, "femm_material_search")["result"]
    assert tool(ctx, "femm_material_get", name="N42")["result"]["H_c"] > 9e5
    r = tool(ctx, "femm_material_get", name="M-19 Steel")
    assert not r["ok"] and "M-19 14 mil" in r["error"]["hint"]
    assert len(eng.received) == n          # none of these touched the engine


def test_input_errors_are_enveloped(server):
    _mcp, ctx, _ = server
    tool(ctx, "femm_new_document", physics="magnetics")
    r = tool(ctx, "femm_problem_define", units="furlongs")
    assert not r["ok"] and "millimeters" in r["error"]["hint"]
    r = tool(ctx, "femm_add_boundary", name="b", bc_type="bogus")
    assert not r["ok"] and "prescribed_a" in r["error"]["hint"]
    r = tool(ctx, "femm_add_segments", segments=[[1, 2, 3]])
    assert not r["ok"]
    r = tool(ctx, "femm_new_document", physics="acoustics")
    assert not r["ok"]


def test_no_install(monkeypatch, tmp_path):
    import femm_agent.sessions as sessions_mod
    monkeypatch.setattr(sessions_mod, "find_femm", lambda: None)
    monkeypatch.setattr(ipc, "find_femm", lambda: None)
    _mcp, ctx = build_server(SessionManager(install=None, default_work_dir=tmp_path), include_engineering=False)
    st = ctx.extras["tools"]["femm_status"]()
    assert st["ok"] and st["result"]["install"]["found"] is False
    r = ctx.extras["tools"]["femm_new_document"](physics="magnetics")
    assert not r["ok"] and "FEMM_DIR" in r["error"]["hint"]


def test_mcp_call_tool_layer(server):
    mcp, _ctx, _ = server
    res = asyncio.run(mcp.call_tool("femm_api_search", {"query": "addnode", "limit": 3}))
    assert not getattr(res, "isError", getattr(res, "is_error", False))
