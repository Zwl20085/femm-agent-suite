"""Offline tests for the wire protocol layer (a fake FEMM TCP server stands in for the engine)."""
import socket
import threading

import pytest

from femm_agent import ipc
from femm_agent.ipc import FemmError, FemmLink, build_command, encode_arg, parse_reply


def test_encode_args():
    assert encode_arg(1) == "1"
    assert encode_arg(1.5) == "1.5"
    assert encode_arg(True) == "1"
    assert encode_arg("Air") == '"Air"'
    assert encode_arg('a"b') == '"a\\"b"'
    assert encode_arg("C:\\x\\y.fem") == '"C:/x/y.fem"'
    assert encode_arg([1, "a"]) == '[1,"a"]'
    assert encode_arg(1 + 2j) == "(1.0+2.0j)"


def test_build_command_rejects_injection():
    assert build_command("mi_addnode", [1, 2]) == "mi_addnode(1,2)"
    with pytest.raises(ValueError):
        build_command("mi_addnode(1,2); quit", [])
    with pytest.raises(ValueError):
        build_command("import os", [])


def test_parse_reply():
    assert parse_reply("") is None
    assert parse_reply("3") == 3
    assert parse_reply("3.5") == 3.5
    assert parse_reply("1\t2\t3") == [1, 2, 3]
    assert parse_reply("millimeters") == "millimeters"
    assert parse_reply("0.5\tplanar") == [0.5, "planar"]
    z = parse_reply("1.5+2I")
    assert isinstance(z, complex) and z.real == 1.5 and z.imag == 2
    z = parse_reply("-3i")
    assert isinstance(z, complex) and z.imag == -3


class FakeFemm:
    """Minimal newline protocol server: echoes a canned reply per received command."""

    def __init__(self, replies):
        self.replies = replies
        self.received = []
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def _run(self):
        conn, _ = self.srv.accept()
        buf = b""
        with conn:
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.decode()
                    self.received.append(line)
                    if line.startswith("quit"):
                        return
                    conn.sendall((self.replies.get(line, "") + "\n").encode())


def test_link_roundtrip_and_error():
    fake = FakeFemm({"mi_getmaterial(\"Air\")": "", "mo_getb(1,2)": "0.5\t-0.25",
                     "mi_getmaterial(\"Nope\")": "error:Couldn't load \"Nope\" from the materials library",
                     "setcurrentdirectory(\"x\")": ""})
    s = socket.create_connection(("127.0.0.1", fake.port))
    link = FemmLink(port=fake.port, sock=s)
    assert link.call("mi_getmaterial", "Air") is None
    assert link.call("mo_getb", 1, 2) == [0.5, -0.25]
    with pytest.raises(FemmError) as ei:
        link.call("mi_getmaterial", "Nope")
    assert "materials library" in str(ei.value)
    assert link.stats["calls"] == 3 and link.stats["errors"] == 1
    link.close()
    assert fake.received[-1] == "quit()"


def test_backslashes_doubled_on_wire():
    fake = FakeFemm({})
    s = socket.create_connection(("127.0.0.1", fake.port))
    link = FemmLink(port=fake.port, sock=s)
    link.raw('mi_saveas("C:\\\\a\\\\b.fem")')
    link.close(quit_engine=False)
    assert fake.received[0].count("\\") == 8


def test_connect_refused():
    with pytest.raises(ipc.FemmLinkError):
        ipc.connect(port=1, timeout=0.2)
