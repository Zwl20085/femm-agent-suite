"""The FEMM command catalog: every scripting command with its physics, phase, args and docs.

Loaded lazily from ``data/commands.json`` (generated from the FEMM 5 manual, the pyFEMM binding and
the engine source). If the file is missing the catalog is empty and :attr:`Catalog.warning` says
why; every function still works (search returns nothing, validation returns a warning).
"""
from __future__ import annotations

import difflib
import json
import re
import warnings
from pathlib import Path
from typing import Any, Iterable

PREFIX_PHYSICS = {
    "mi": ("magnetics", "pre"), "mo": ("magnetics", "post"),
    "ei": ("electrostatics", "pre"), "eo": ("electrostatics", "post"),
    "hi": ("heatflow", "pre"), "ho": ("heatflow", "post"),
    "ci": ("currentflow", "pre"), "co": ("currentflow", "post"),
}


def data_dir() -> Path:
    """The suite's data folder: packaged copy (wheel) first, then the repo's ``data/``."""
    here = Path(__file__).resolve().parent
    for c in (here / "data", here.parent.parent / "data"):
        if c.is_dir():
            return c
    return here / "data"


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


class Catalog:
    def __init__(self, path: str | Path | None = None):
        self._path = Path(path) if path else None
        self._commands: dict[str, dict[str, Any]] | None = None
        self._alias: dict[str, str] = {}
        self.warning: str | None = None

    @property
    def path(self) -> Path:
        return self._path or (data_dir() / "commands.json")

    # -- loading ---------------------------------------------------------------------------
    def _load(self) -> dict[str, dict[str, Any]]:
        if self._commands is not None and self._commands:
            return self._commands
        p = self.path
        cmds: dict[str, dict[str, Any]] = {}
        alias: dict[str, str] = {}
        if not p.is_file():
            msg = f"command catalog not found at {p}; search/validation unavailable"
            if self.warning != msg:
                warnings.warn(msg)
            self.warning = msg
            self._commands = {}
            return self._commands      # re-checked on the next call (the file may land later)
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # corrupt file: degrade, don't crash the server
            self.warning = f"command catalog at {p} could not be read: {e}"
            warnings.warn(self.warning)
            self._commands = {}
            return self._commands
        entries = raw.get("commands", raw) if isinstance(raw, dict) else raw
        for c in entries:
            if isinstance(c, dict) and c.get("name"):
                cmds[c["name"]] = c
        for c in cmds.values():
            for a in c.get("aliases") or []:
                if a not in cmds:
                    alias[a] = c["name"]
        self._commands, self._alias, self.warning = cmds, alias, None
        return cmds

    def reload(self) -> int:
        self._commands = None
        return len(self._load())

    @property
    def commands(self) -> dict[str, dict[str, Any]]:
        return self._load()

    def __len__(self) -> int:
        return len(self._load())

    # -- lookup ----------------------------------------------------------------------------
    def get(self, name: str) -> dict[str, Any] | None:
        cmds = self._load()
        if name in cmds:
            return cmds[name]
        if name in self._alias:
            return cmds.get(self._alias[name])
        low = name.lower()
        for k, v in cmds.items():
            if k.lower() == low:
                return v
        return None

    def names(self, physics: str | None = None, phase: str | None = None) -> list[str]:
        return sorted(n for n, c in self._load().items()
                      if (physics is None or c.get("physics") in (physics, "common"))
                      and (phase is None or c.get("phase") in (phase, "common")))

    def search(self, query: str, physics: str | None = None, phase: str | None = None,
               category: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Rank commands by match of `query` against name (strongest), category and description.

        Returns compact entries ``{name, physics, phase, category, signature, description, score}``.
        ``physics`` is one of magnetics/electrostatics/heatflow/currentflow (common commands are
        always included); ``phase`` is pre/post.
        """
        q = (query or "").strip().lower()
        qt = _tokens(q)
        out: list[tuple[float, dict[str, Any]]] = []
        for name, c in self._load().items():
            if physics and c.get("physics") not in (physics, "common"):
                continue
            if phase and c.get("phase") not in (phase, "common"):
                continue
            if category and c.get("category") != category:
                continue
            n = name.lower()
            bare = n.split("_", 1)[1] if re.match(r"^[mehc][io]_", n) else n
            desc = (c.get("description") or "").lower()
            cat = (c.get("category") or "").lower()
            argtxt = " ".join((a.get("name", "") + " " + a.get("description", "")) for a in c.get("args", [])).lower()
            s = 0.0
            if not q:
                s = 1.0
            else:
                if n == q or bare == q:
                    s += 100
                elif n.startswith(q) or bare.startswith(q):
                    s += 40
                elif q in n:
                    s += 25
                if q in desc:
                    s += 10
                for t in qt:
                    if t in bare:
                        s += 8
                    if t == cat or t in cat:
                        s += 4
                    if re.search(r"\b" + re.escape(t), desc):
                        s += 3
                    elif t in argtxt:
                        s += 1
                for a in c.get("aliases") or []:
                    if q == a.lower():
                        s += 90
            if s > 0:
                out.append((s, c))
        out.sort(key=lambda x: (-x[0], x[1]["name"]))
        return [dict(self.summary(c), score=round(s, 1)) for s, c in out[:limit]]

    @staticmethod
    def signature(c: dict[str, Any]) -> str:
        parts = []
        for a in c.get("args", []):
            parts.append(("[" + a["name"] + "]") if a.get("optional") else a["name"])
        return f"{c['name']}({', '.join(parts)})"

    def summary(self, c: dict[str, Any]) -> dict[str, Any]:
        return {"name": c["name"], "physics": c.get("physics"), "phase": c.get("phase"),
                "category": c.get("category"), "signature": self.signature(c),
                "read_only": c.get("read_only"), "description": c.get("description")}

    def is_read_only(self, name: str) -> bool | None:
        """True if the command only reads state (getters, post-processing values); None if unknown."""
        c = self.get(name)
        if c is None:
            return None
        return bool(c.get("read_only"))

    # -- validation ------------------------------------------------------------------------
    def validate_args(self, name: str, args: Iterable[Any] | None) -> list[str]:
        """Warnings (never errors) about calling `name` with `args`: unknown command, arity, types,
        pyFEMM-only helpers the engine does not define, enum values out of range."""
        args = list(args or [])
        cmds = self._load()
        if not cmds:
            return [self.warning or "command catalog unavailable; arguments not validated"]
        c = self.get(name)
        if c is None:
            near = difflib.get_close_matches(name, list(cmds), n=5, cutoff=0.6) or                 [r["name"] for r in self.search(name, limit=5)]
            return [f"'{name}' is not in the FEMM 5 catalog" + (f"; did you mean {', '.join(near)}?" if near else "")]
        w: list[str] = []
        if c["name"] != name and name not in (c.get("aliases") or []):
            w.append(f"'{name}' matched catalog entry '{c['name']}' only case-insensitively; FEMM is case-sensitive")
        if c.get("pyfemm_only"):
            note = c.get("notes") or ""
            w.append(f"{c['name']} is a pyFEMM helper, not an engine command; over the wire it raises NameError. {note}".strip())
        spec = c.get("args", [])
        required = [a for a in spec if not a.get("optional")]
        if len(args) < len(required):
            w.append(f"{c['name']} expects at least {len(required)} argument(s) ({self.signature(c)}), got {len(args)}")
        if len(args) > len(spec) and not any(a.get("type") == "list" for a in spec):
            w.append(f"{c['name']} takes at most {len(spec)} argument(s) ({self.signature(c)}), got {len(args)}")
        enums = c.get("enums") or {}
        for a, v in zip(spec, args):
            t = a.get("type")
            ok = True
            if t == "number":
                ok = isinstance(v, (int, float)) and not isinstance(v, bool)
            elif t == "int":
                ok = (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer())
            elif t == "complex":
                ok = isinstance(v, (int, float, complex)) and not isinstance(v, bool)
            elif t == "string":
                ok = isinstance(v, str)
            elif t == "list":
                ok = isinstance(v, (list, tuple))
            if not ok:
                w.append(f"argument '{a['name']}' of {c['name']} should be {t}, got {type(v).__name__} {v!r}")
            e = enums.get(a["name"])
            if e and ok and t in ("int", "number") and str(int(v)) not in e:
                w.append(f"argument '{a['name']}'={v!r} is not one of the documented codes {sorted(e, key=lambda k: int(k) if k.lstrip('-').isdigit() else 0)}")
        return w


CATALOG = Catalog()


def search(query: str, physics: str | None = None, phase: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    return CATALOG.search(query, physics=physics, phase=phase, limit=limit)


def get(name: str) -> dict[str, Any] | None:
    return CATALOG.get(name)


def validate_args(name: str, args: Iterable[Any] | None) -> list[str]:
    return CATALOG.validate_args(name, args)


def is_read_only(name: str) -> bool | None:
    return CATALOG.is_read_only(name)


def physics_of(name: str) -> tuple[str, str] | None:
    """('magnetics','pre') for 'mi_addnode' etc., from the prefix; None for common commands."""
    m = re.match(r"^([mehc][io])_", name)
    return PREFIX_PHYSICS.get(m.group(1)) if m else None
