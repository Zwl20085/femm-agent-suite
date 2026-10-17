"""Named FEMM engine sessions. One `FemmLink` per session; the default session is "main"."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import ipc
from .config import FemmInstall, find_femm

PHYSICS_BY_CODE = {0: "magnetics", 1: "electrostatics", 2: "heatflow", 3: "currentflow"}
PHYSICS_BY_EXT = {".fem": "magnetics", ".fee": "electrostatics", ".feh": "heatflow", ".fec": "currentflow"}


@dataclass
class Session:
    name: str
    link: ipc.FemmLink
    work_dir: Path
    physics: str | None = None        # set by newdocument/opendocument
    document: str | None = None       # path of the current document (after save/open)
    solved: bool = False              # a solution has been loaded into the postprocessor
    created: float = field(default_factory=time.time)
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def pre(self) -> str:
        """Preprocessor prefix for the current physics: mi / ei / hi / ci."""
        return {"magnetics": "mi", "electrostatics": "ei", "heatflow": "hi", "currentflow": "ci"}[self._need_physics()]

    @property
    def post(self) -> str:
        """Postprocessor prefix for the current physics: mo / eo / ho / co."""
        return {"magnetics": "mo", "electrostatics": "eo", "heatflow": "ho", "currentflow": "co"}[self._need_physics()]

    def _need_physics(self) -> str:
        if self.physics is None:
            raise ipc.FemmError("no document open in this session", command=None)
        return self.physics

    def call(self, name: str, *args: Any, timeout: float | None = None) -> Any:
        return self.link.call(name, *args, timeout=timeout)

    def pre_call(self, cmd: str, *args: Any, timeout: float | None = None) -> Any:
        """`pre_call('addnode', 1, 2)` -> `mi_addnode(1,2)` for the current physics."""
        return self.link.call(f"{self.pre}_{cmd}", *args, timeout=timeout)

    def post_call(self, cmd: str, *args: Any, timeout: float | None = None) -> Any:
        return self.link.call(f"{self.post}_{cmd}", *args, timeout=timeout)

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name, "port": self.link.port, "pid": self.link.pid, "headless": self.link.headless,
            "connected": self.link.connected, "physics": self.physics, "document": self.document,
            "solved": self.solved, "work_dir": str(self.work_dir), "calls": self.link.stats["calls"],
            "errors": self.link.stats["errors"], "uptime_s": round(time.time() - self.created, 1),
        }


class SessionManager:
    """Owns all sessions; `get()` lazily launches the default headless engine."""

    def __init__(self, install: FemmInstall | None = None, default_work_dir: str | Path | None = None):
        self._install = install
        self.sessions: dict[str, Session] = {}
        root = Path(default_work_dir) if default_work_dir else Path(
            os.environ.get("FEMM_AGENT_WORK", Path.home() / "femm-agent-work"))
        self.default_work_dir = root

    @property
    def install(self) -> FemmInstall | None:
        if self._install is None:
            self._install = find_femm()
        return self._install

    def open(self, name: str = "main", headless: bool = True, port: int | None = None,
             work_dir: str | Path | None = None, attach: bool = False) -> Session:
        if name in self.sessions and self.sessions[name].link.connected:
            return self.sessions[name]
        wd = Path(work_dir) if work_dir else self.default_work_dir / name
        wd.mkdir(parents=True, exist_ok=True)
        if attach:
            link = ipc.connect(port=port or ipc.DEFAULT_PORT)
            link.raw("setcurrentdirectory(" + ipc.encode_arg(str(wd).replace("\\", "/")) + ")")
        else:
            link = ipc.launch(self.install, headless=headless, port=port, cwd=str(wd))
        s = Session(name=name, link=link, work_dir=wd)
        self.sessions[name] = s
        return s

    def get(self, name: str = "main") -> Session:
        s = self.sessions.get(name)
        if s is None or not s.link.connected:
            s = self.open(name)
        return s

    def close(self, name: str = "main") -> bool:
        s = self.sessions.pop(name, None)
        if s is None:
            return False
        s.link.close()
        return True

    def close_all(self) -> None:
        for name in list(self.sessions):
            self.close(name)

    def list(self) -> list[dict[str, Any]]:
        return [s.info() for s in self.sessions.values()]
