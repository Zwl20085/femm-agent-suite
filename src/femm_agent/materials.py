"""FEMM 5 material libraries: lookup, fuzzy search and FEMM 4.2 name migration.

Sources, in priority order per physics:

1. the user's per-user editable library (``%APPDATA%/FEMM/matlib.dat`` etc., see
   :meth:`config.FemmInstall.material_library`) if it exists: parsed live, so materials the user
   added in the FEMM GUI are found;
2. ``data/materials/<physics>.json`` (parsed from the seed libraries shipped with FEMM 5).

FEMM 5 renamed many magnetic materials (``M-19 Steel`` -> ``M-19 14 mil``). :data:`LEGACY_MAP`
and :func:`suggest` turn a failed ``mi_getmaterial`` into concrete alternatives.
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from .catalog import data_dir
from .config import PHYSICS, FemmInstall

# FEMM 4.2 favourites -> FEMM 5 names (checked against matlib.dat build 06oct2026 at load time;
# entries whose target is missing are dropped). Regex rules below cover NdFeB/SmCo MGOe grades.
_LEGACY_RAW: dict[str, str] = {
    "M-19 Steel": "M-19 14 mil", "M-15 Steel": "M-15 14 mil", "M-22 Steel": "M-22 14 mil",
    "M-27 Steel": "M-27 14 mil", "M-36 Steel": "M-36 14 mil", "M-43 Steel": "M-43 18 mil",
    "M-45 Steel": "M-45 18 mil", "M-47 Steel": "M-47 18 mil", "M-50 Steel": "M-50",
    "M-14 Steel": "M-14",
    "Pure Iron": "ARMCO Pure Iron", "Iron": "ARMCO Pure Iron",
    "1006 Steel": "1006 Steel (hot rolled)", "1008 Steel": "1008 Steel (hot rolled)",
    "1010 Steel": "1010 Steel (hot rolled)", "1018 Steel": "1018 Steel (hot rolled)",
    "1020 Steel": "1020 Steel (hot rolled)", "1030 Steel": "1030 Steel (hot rolled)",
    "1117 Steel": "1117 Steel (hot rolled)", "1004 Steel": "1004 Steel (hot rolled)",
    "416 Stainless Steel": "416 stainless steel, annealed",
    "Alnico 5": "Cast Alnico 5 (LNG40)", "Alnico 8": "Cast Alnico 8 (LNGT38)",
    "Ceramic 8": "Ceramic 8A",
    "Hiperco-50": "CoFe 49Co-2V, magnetic anneal", "Hiperco 50": "CoFe 49Co-2V, magnetic anneal",
    "Silicon Core Iron": "3% Si strip, oriented",
    "Air": "Air", "Copper": "Copper",
    "Aluminum, 1100": "Aluminum, 1100", "Aluminum, 6061-T6": "Aluminum, 6061-T6",
    "304 Stainless Steel": "304 Stainless Steel", "316 Stainless Steel": "316 Stainless Steel",
}

_NDFEB_RE = re.compile(r"^\s*(?:sintered\s+)?ndfeb\s*(\d+(?:\.\d+)?)\s*(?:mgoe)?\s*$", re.I)
_SMCO_RE = re.compile(r"^\s*smco\s*(\d+(?:\.\d+)?)\s*(?:mgoe)?\s*$", re.I)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).replace("°", " deg ")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s.lower()).strip()


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", _norm(s)) if t]


# ----------------------------------------------------------------------------- .dat parsing

def _num(v: str) -> Any:
    v = v.strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return v[1:-1]
    try:
        if re.fullmatch(r"[+-]?\d+", v):
            return int(v)
        return float(v)
    except ValueError:
        return v


def parse_dat(path: str | Path, physics: str) -> list[dict[str, Any]]:
    """Parse a FEMM material library (.dat) with the rules in data/materials/README.md."""
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    folders: list[str] = []
    out: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    curve_key: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("<beginfolder>"):
            continue
        if low.startswith("<endfolder>"):
            if folders:
                folders.pop()
            continue
        if low.startswith("<foldername>") and cur is None:
            name = _num(line.split("=", 1)[1]) if "=" in line else ""
            folders.append(str(name))
            continue
        if low.startswith("<beginblock>"):
            cur = {}
            curve_key = None
            continue
        if low.startswith("<endblock>"):
            if cur is not None and "name" in cur:
                cur["folder"] = " / ".join(folders) if folders else None
                out.append(cur)
            cur = None
            curve_key = None
            continue
        if cur is None:
            continue
        m = re.match(r"^<([^>]+)>\s*=?\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2)
            if key.lower() == "blockname":
                cur["name"] = str(_num(val))
            else:
                cur[key] = _num(val)
            if key in ("BHPoints", "TKPoints"):
                curve_key = "BH_curve" if key == "BHPoints" else "TK_curve"
                cur[curve_key] = []
            else:
                curve_key = None
            continue
        if curve_key is not None:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    cur[curve_key].append([float(parts[0]), float(parts[1])])
                except ValueError:
                    pass
    return out


# ----------------------------------------------------------------------------- library

class MaterialLibrary:
    def __init__(self, data: str | Path | None = None, install: FemmInstall | None = None,
                 use_user_library: bool = True):
        self._data = Path(data) if data else data_dir()
        self._install = install
        self._use_user = use_user_library
        self._libs: dict[str, list[dict[str, Any]]] = {}
        self.sources: dict[str, str] = {}
        self._index: dict[str, Any] | None = None
        self.warnings: list[str] = []

    # -- loading ---------------------------------------------------------------------------
    def _load(self, physics: str) -> list[dict[str, Any]]:
        if physics not in PHYSICS:
            raise ValueError(f"physics must be one of {PHYSICS}, got {physics!r}")
        if physics in self._libs:
            return self._libs[physics]
        mats: list[dict[str, Any]] = []
        if self._use_user and self._install is not None:
            try:
                p = self._install.material_library(physics)
                if p is not None and p.parent != self._install.bin_dir:
                    mats = parse_dat(p, physics)
                    self.sources[physics] = f"user library {p.name} (per-user copy)"
            except Exception as e:
                self.warnings.append(f"could not parse user library for {physics}: {e}")
                mats = []
        if not mats:
            jp = self._data / "materials" / f"{physics}.json"
            if jp.is_file():
                mats = json.loads(jp.read_text(encoding="utf-8")).get("materials", [])
                self.sources[physics] = f"data/materials/{physics}.json"
            else:
                self.warnings.append(f"no material data for {physics} at {jp}")
                self.sources[physics] = "missing"
        for m in mats:
            m.setdefault("physics", physics)
        self._libs[physics] = mats
        return mats

    @property
    def index(self) -> dict[str, Any]:
        if self._index is None:
            p = self._data / "materials" / "name_index.json"
            self._index = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
        return self._index

    def names(self, physics: str = "magnetics") -> list[str]:
        return [m["name"] for m in self._load(physics)]

    def counts(self) -> dict[str, int]:
        return {p: len(self._load(p)) for p in PHYSICS}

    # -- lookup ----------------------------------------------------------------------------
    def get(self, name: str, physics: str | None = "magnetics", folder: str | None = None) -> dict[str, Any] | None:
        """Exact name (case-sensitive first, then case/space-insensitive). Use `folder` to
        disambiguate duplicates (heatflow 'Ammonia')."""
        phys = [physics] if physics else list(PHYSICS)
        for ph in phys:
            mats = self._load(ph)
            hits = [m for m in mats if m["name"] == name]
            if not hits:
                n = _norm(name)
                hits = [m for m in mats if _norm(m["name"]) == n]
            if folder:
                hits = [m for m in hits if (m.get("folder") or "").lower().startswith(folder.lower())] or hits
            if hits:
                return hits[0]
        return None

    def search(self, query: str, physics: str | None = "magnetics", limit: int = 15,
               folder: str | None = None) -> list[dict[str, Any]]:
        """Fuzzy search: exact > prefix > substring > token overlap > difflib similarity.
        Also searches the folder path (e.g. 'magnet', 'silicon iron', 'AWG')."""
        q = _norm(query or "")
        qt = _tokens(query or "")
        legacy = self.legacy_lookup(query) if query else None
        scored: list[tuple[float, dict[str, Any]]] = []
        for ph in ([physics] if physics else list(PHYSICS)):
            for m in self._load(ph):
                if folder and folder.lower() not in (m.get("folder") or "").lower():
                    continue
                n = _norm(m["name"])
                f = _norm(m.get("folder") or "")
                s = 0.0
                if not q:
                    s = 1.0
                elif n == q:
                    s = 100.0
                else:
                    if legacy and m["name"] == legacy:
                        s += 90
                    if n.startswith(q):
                        s += 50
                    elif q in n:
                        s += 35
                    nt = set(_tokens(m["name"]))
                    ft = set(_tokens(m.get("folder") or ""))
                    for t in qt:
                        if t in nt:
                            s += 12
                        elif any(x.startswith(t) for x in nt):
                            s += 7
                        elif t in ft or any(x.startswith(t) for x in ft):
                            s += 6
                    if len(q) > 3 and q in f:
                        s += 20
                    s += 25 * difflib.SequenceMatcher(None, q, n).ratio()
                    if s < 12:
                        continue
                scored.append((s, m))
        scored.sort(key=lambda x: (-x[0], x[1]["name"]))
        return [dict(self.brief(m), score=round(s, 1)) for s, m in scored[:limit]]

    @staticmethod
    def brief(m: dict[str, Any]) -> dict[str, Any]:
        """Compact one-line description (never the full BH curve)."""
        out: dict[str, Any] = {"name": m["name"], "physics": m.get("physics"), "folder": m.get("folder")}
        ph = m.get("physics")
        if ph == "magnetics":
            nbh = len(m.get("BH_curve") or [])
            out.update({"mu_r": m.get("Mu_x"), "H_c_A_per_m": m.get("H_c"), "sigma_MS_per_m": m.get("Sigma"),
                        "nonlinear": nbh > 0, "bh_points": nbh})
            if m.get("LamType") not in (None, 0):
                out["lam_type"] = m.get("LamType")
            if m.get("WireD"):
                out["wire_d_mm"] = m.get("WireD")
            if m.get("d_lam"):
                out["d_lam_mm"] = m.get("d_lam")
        elif ph == "electrostatics":
            out.update({"eps_x": m.get("ex"), "eps_y": m.get("ey"), "qv": m.get("qv")})
        elif ph == "heatflow":
            out.update({"k_x": m.get("Kx"), "k_y": m.get("Ky"), "kt": m.get("Kt"), "qv": m.get("qv"),
                        "tk_points": len(m.get("TK_curve") or [])})
        elif ph == "currentflow":
            out.update({"sigma_x_S_per_m": m.get("ox"), "sigma_y_S_per_m": m.get("oy"),
                        "eps_x": m.get("ex"), "eps_y": m.get("ey")})
        return out

    def families(self, physics: str = "magnetics") -> dict[str, list[str]]:
        """Material families. Magnetics uses name_index.json's curated families; other physics
        group by top-level folder."""
        if physics == "magnetics" and self.index.get("families"):
            return dict(self.index["families"])
        fam: dict[str, list[str]] = {}
        for m in self._load(physics):
            key = (m.get("folder") or "(top level)").split(" / ")[0]
            fam.setdefault(key, []).append(m["name"])
        return fam

    # -- migration -------------------------------------------------------------------------
    @property
    def legacy_map(self) -> dict[str, str]:
        names = set(self.names("magnetics"))
        out = {k: v for k, v in _LEGACY_RAW.items() if v in names}
        for k, v in (self.index.get("fem42_favourites") or {}).items():
            cands = [c for c in v.get("fem5_candidates", []) if c in names]
            if cands and k not in out:
                out[k] = cands[0]
        return out

    def legacy_lookup(self, name: str) -> str | None:
        """FEMM 4.2 name -> FEMM 5 name, including 'NdFeB 32 MGOe' -> nearest N grade."""
        lm = self.legacy_map
        if name in lm:
            return lm[name]
        low = {k.lower(): v for k, v in lm.items()}
        if name.strip().lower() in low:
            return low[name.strip().lower()]
        names = self.names("magnetics")
        m = _NDFEB_RE.match(name)
        if m:
            e = float(m.group(1))
            pool = [n for n in names if re.fullmatch(r"N\d+", n)] if e >= 20 else \
                   [n for n in names if re.fullmatch(r"BN\d+", n)]
            if pool:
                return min(pool, key=lambda n: (abs(float(re.sub(r"\D", "", n)) - e), n))
        m = _SMCO_RE.match(name)
        if m:
            e = float(m.group(1))
            pool = [n for n in names if n.startswith("SmCo")]

            def grade(n: str) -> float:
                return float(re.match(r"SmCo(\d+)", n).group(1))
            if pool:
                return min(pool, key=lambda n: (abs(grade(n) - e), "(" in n, n))
        return None

    def suggest(self, name: str, physics: str = "magnetics", limit: int = 5) -> dict[str, Any]:
        """For a name FEMM refused: the legacy mapping (if any) and the nearest library names."""
        legacy = self.legacy_lookup(name) if physics == "magnetics" else None
        near = [r["name"] for r in self.search(name, physics=physics, limit=limit + 1)]
        if legacy and legacy in near:
            near.remove(legacy)
        out: dict[str, Any] = {"requested": name, "physics": physics}
        if legacy:
            out["fem42_rename"] = legacy
            note = (self.index.get("fem42_favourites") or {}).get(name, {}).get("note")
            if note:
                out["note"] = note
        out["nearest"] = near[:limit]
        best = legacy or (near[0] if near else None)
        out["best"] = best
        return out


_DEFAULT: MaterialLibrary | None = None


def library(install: FemmInstall | None = None) -> MaterialLibrary:
    """Process-wide library (lazily created; picks up the FEMM install if one is found)."""
    global _DEFAULT
    if _DEFAULT is None:
        if install is None:
            try:
                from .config import find_femm
                install = find_femm()
            except Exception:
                install = None
        _DEFAULT = MaterialLibrary(install=install)
    return _DEFAULT


def search(query: str, physics: str | None = "magnetics", limit: int = 15) -> list[dict[str, Any]]:
    return library().search(query, physics=physics, limit=limit)


def get(name: str, physics: str | None = "magnetics") -> dict[str, Any] | None:
    return library().get(name, physics=physics)


def suggest(name: str, physics: str = "magnetics") -> dict[str, Any]:
    return library().suggest(name, physics=physics)


def families(physics: str = "magnetics") -> dict[str, list[str]]:
    return library().families(physics)


def legacy_map() -> dict[str, str]:
    return library().legacy_map
