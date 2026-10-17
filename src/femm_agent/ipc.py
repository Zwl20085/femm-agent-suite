"""TCP link to a FEMM 5 engine (femm_headless or femm_gui).

Wire protocol (verified against femm-qt `ipc/tcp_server.cpp` and `pyfemm/femm.py`, build 06oct2026):

* single client, localhost only, newline-delimited UTF-8 text; default port 48015
* each request line is a Python expression evaluated inside FEMM's embedded MicroPython,
  e.g. ``mi_addnode(1.5,2)`` or ``mo_getpointvalues(0,0)``
* backslashes must be doubled before sending (the parser treats the line as a string literal)
* one reply line per request: ``error:<message>`` on failure, otherwise tab-separated values
  (numbers, complex numbers written with ``I``/``i`` for the imaginary unit, or bare strings);
  an empty line means "no return value"

This module speaks that protocol directly, so the suite has no dependency on where pyFEMM is
installed and can add timeouts, multi-instance ports and structured errors.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from .config import FemmInstall, find_femm

DEFAULT_PORT = 48015
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COMPLEX_RE = re.compile(r"^[0-9eE.+\-*Ii ]+$")  # e.g. 1+I*2, I*2.5, -I*3, 1.5+2I


class FemmError(Exception):
    """FEMM answered ``error:<message>`` for a command."""

    def __init__(self, message: str, command: str | None = None):
        super().__init__(message)
        self.message = message
        self.command = command


class FemmLinkError(Exception):
    """Transport problem: nothing listening, connection lost, timeout."""


# ----------------------------------------------------------------------------- encoding

def encode_arg(v: Any) -> str:
    """Encode one Python value as a MicroPython literal for the wire (same rules as pyFEMM's doargs)."""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v != v:
            raise ValueError("NaN cannot be sent to FEMM")
        return repr(v)
    if isinstance(v, complex):
        return f"({v.real!r}+{v.imag!r}j)" if v.imag >= 0 else f"({v.real!r}{v.imag!r}j)"
    if isinstance(v, str):
        s = v.replace("\\", "/").replace('"', '\\"')
        return f'"{s}"'
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(encode_arg(x) for x in v) + "]"
    if v is None:
        return "None"
    raise TypeError(f"cannot encode {type(v).__name__} for FEMM")


def build_command(name: str, args: Sequence[Any] = ()) -> str:
    """``build_command('mi_addnode', [1, 2]) -> 'mi_addnode(1,2)'``. Name is validated (no injection)."""
    if not _NAME_RE.match(name):
        raise ValueError(f"invalid FEMM command name: {name!r}")
    return name + "(" + ",".join(encode_arg(a) for a in args) + ")"


# ----------------------------------------------------------------------------- decoding

def _parse_scalar(p: str) -> Any:
    s = p.strip()
    if not s:
        return None
    try:
        if re.fullmatch(r"[+-]?\d+", s):
            return int(s)
        return float(s)
    except ValueError:
        pass
    # FEMM writes complex numbers as 1+I*2, I*2.5, -I*3 (older bindings also accept 1.5+2I)
    if ("I" in s or "i" in s) and _COMPLEX_RE.match(s) and any(ch.isdigit() for ch in s):
        expr = re.sub(r"(\d)\s*[Ii]\b", r"\1*1j", s)      # 2I -> 2*1j
        expr = re.sub(r"[Ii]", "1j", expr)                  # I*2 -> 1j*2
        try:
            v = eval(expr, {"__builtins__": {}}, {})  # charset is restricted by _COMPLEX_RE
            if isinstance(v, (int, float, complex)):
                return complex(v)
        except Exception:
            pass
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    return s


def parse_reply(line: str) -> Any:
    """Turn a reply line into Python values: scalar, list, or None for an empty reply."""
    if line == "":
        return None
    parts = [p for p in line.split("\t") if p.strip() != ""]
    values = [_parse_scalar(p) for p in parts]
    if len(values) == 1:
        return values[0]
    return values


# ----------------------------------------------------------------------------- link

@dataclass
class FemmLink:
    """One TCP connection to one FEMM engine. Create via :func:`connect` or :func:`launch`."""

    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    sock: socket.socket | None = None
    proc: subprocess.Popen | None = None
    headless: bool = True
    default_timeout: float | None = 600.0
    stats: dict = field(default_factory=lambda: {"calls": 0, "errors": 0, "seconds": 0.0})
    journal: list[str] = field(default_factory=list)
    journal_limit: int = 5000

    # -- lifecycle -------------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self.sock is not None

    @property
    def pid(self) -> int | None:
        return self.proc.pid if self.proc else None

    def close(self, quit_engine: bool = True) -> None:
        if self.sock is not None:
            if quit_engine:
                try:
                    self.raw("quit()", expect_reply=False, timeout=5)
                except Exception:
                    pass
            try:
                if self.sock is not None:
                    self.sock.close()
            finally:
                self.sock = None
        if self.proc is not None:
            try:
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

    # -- transport -------------------------------------------------------------------------
    def raw(self, line: str, expect_reply: bool = True, timeout: float | None = None) -> Any:
        """Send one raw command line (already-formed MicroPython expression) and parse the reply."""
        if self.sock is None:
            raise FemmLinkError("not connected to FEMM")
        if "\n" in line or "\r" in line:
            raise ValueError("a FEMM command must be a single line")
        payload = (line.replace("\\", "\\\\") + "\n").encode("utf-8")
        t0 = time.time()
        self.sock.settimeout(self.default_timeout if timeout is None else timeout)
        try:
            self.sock.sendall(payload)
            buf = b""
            while b"\n" not in buf:
                chunk = self.sock.recv(65536)
                if not chunk:
                    self.sock = None
                    raise FemmLinkError("connection to FEMM lost (engine exited?)")
                buf += chunk
        except socket.timeout as e:
            raise FemmLinkError(f"FEMM did not answer within {self.sock.gettimeout()} s: {line[:80]}") from e
        except OSError as e:
            self.sock = None
            raise FemmLinkError(f"socket error talking to FEMM: {e}") from e
        finally:
            self.stats["calls"] += 1
            self.stats["seconds"] += time.time() - t0
            if len(self.journal) < self.journal_limit:
                self.journal.append(line)
        reply = buf[: buf.index(b"\n")].decode("utf-8", errors="replace").rstrip("\r")
        if reply.startswith("error:"):
            self.stats["errors"] += 1
            raise FemmError(reply[6:].strip(), command=line)
        if not expect_reply:
            return None
        return parse_reply(reply)

    def call(self, name: str, *args: Any, timeout: float | None = None) -> Any:
        """Call a FEMM command by name: ``link.call('mi_probdef', 0, 'millimeters', 'planar', 1e-8, 10, 30)``."""
        return self.raw(build_command(name, args), timeout=timeout)

    def eval(self, expression: str, timeout: float | None = None) -> Any:
        """Evaluate one line of MicroPython inside FEMM and return its value (power-user path)."""
        return self.raw(expression, timeout=timeout)

    def ping(self) -> bool:
        try:
            self.raw("1+1", timeout=5)
            return True
        except Exception:
            return False


# ----------------------------------------------------------------------------- factories

def _try_connect(host: str, port: int, timeout: float) -> socket.socket | None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.settimeout(None)
        return s
    except OSError:
        s.close()
        return None


def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
    s = _try_connect(host, port, 0.2)
    if s is None:
        return True
    s.close()
    return False


def pick_free_port(start: int = DEFAULT_PORT + 1, count: int = 200) -> int:
    for p in range(start, start + count):
        if port_is_free(p):
            return p
    raise FemmLinkError("no free TCP port for a new FEMM instance")


def connect(port: int = DEFAULT_PORT, host: str = "127.0.0.1", timeout: float = 2.0) -> FemmLink:
    """Attach to an engine that is already listening (e.g. a femm_gui the user opened)."""
    s = _try_connect(host, port, timeout)
    if s is None:
        raise FemmLinkError(f"no FEMM engine listening on {host}:{port}")
    link = FemmLink(host=host, port=port, sock=s, proc=None)
    link.raw("setcurrentdirectory(" + encode_arg(os.getcwd().replace("\\", "/")) + ")")
    return link


def launch(install: FemmInstall | None = None, headless: bool = True, port: int | None = None,
           cwd: str | None = None, startup_timeout: float = 30.0) -> FemmLink:
    """Start femm_headless (or femm_gui) on a free port and connect to it."""
    install = install or find_femm()
    if install is None:
        raise FemmLinkError("FEMM 5 not found. Install it (https://www.femm.info) or set FEMM_DIR to its bin folder.")
    exe = install.headless if headless else (install.gui or install.headless)
    if port is None:
        port = DEFAULT_PORT if port_is_free(DEFAULT_PORT) else pick_free_port()
    elif not port_is_free(port):
        raise FemmLinkError(f"port {port} is already in use")
    kwargs: dict[str, Any] = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen([str(exe), "--port", str(port)], cwd=cwd or None, **kwargs)
    deadline = time.time() + startup_timeout
    sock = None
    while time.time() < deadline:
        if proc.poll() is not None:
            raise FemmLinkError(f"{exe.name} exited immediately with code {proc.returncode}")
        sock = _try_connect("127.0.0.1", port, 0.2)
        if sock is not None:
            break
        time.sleep(0.1)
    if sock is None:
        proc.kill()
        raise FemmLinkError(f"{exe.name} started but never listened on port {port}")
    link = FemmLink(host="127.0.0.1", port=port, sock=sock, proc=proc, headless=headless)
    link.raw("setcurrentdirectory(" + encode_arg((cwd or os.getcwd()).replace("\\", "/")) + ")")
    return link
