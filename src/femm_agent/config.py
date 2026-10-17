"""Locate the FEMM 5 installation (femm_headless / femm_gui) on this machine."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

PHYSICS = ("magnetics", "electrostatics", "heatflow", "currentflow")
LIBRARY_FILES = {
    "magnetics": "matlib.dat",
    "electrostatics": "statlib.dat",
    "heatflow": "heatlib.dat",
    "currentflow": "condlib.dat",
}
DOC_EXTENSIONS = {"magnetics": ".fem", "electrostatics": ".fee", "heatflow": ".feh", "currentflow": ".fec"}
NEWDOCUMENT_CODES = {"magnetics": 0, "electrostatics": 1, "heatflow": 2, "currentflow": 3}
PREFIX = {"magnetics": ("mi", "mo"), "electrostatics": ("ei", "eo"), "heatflow": ("hi", "ho"), "currentflow": ("ci", "co")}


@dataclass(frozen=True)
class FemmInstall:
    bin_dir: Path          # directory holding femm_headless(.exe) / femm_gui(.exe)
    headless: Path         # executable to spawn for a windowless engine
    gui: Path | None       # executable to spawn for an interactive window (may be missing)
    root: Path             # install root (parent of bin on Windows/Linux, the .app on macOS)

    @property
    def manual_pdf(self) -> Path | None:
        for c in (self.bin_dir / "manual.pdf", self.root / "docs" / "manual.pdf",
                  self.root / "Contents" / "Resources" / "docs" / "manual.pdf"):
            if c.is_file():
                return c
        return None

    @property
    def examples_dir(self) -> Path | None:
        for c in (self.root / "examples", Path.home() / "Documents" / "FEMM" / "examples"):
            if c.is_dir():
                return c
        return None

    @property
    def pyfemm_dir(self) -> Path | None:
        for c in (self.root / "pyfemm", self.root / "Contents" / "Resources" / "bindings" / "pyfemm",
                  self.root / "bindings" / "pyfemm"):
            if c.is_dir():
                return c
        return None

    def material_library(self, physics: str) -> Path | None:
        """Path of the material library for `physics`; the per-user editable copy wins over the seed."""
        name = LIBRARY_FILES[physics]
        user_dirs: list[Path] = []
        if os.name == "nt" and os.environ.get("APPDATA"):
            user_dirs.append(Path(os.environ["APPDATA"]) / "FEMM")
        user_dirs.append(Path.home() / "Library" / "Application Support" / "FEMM")
        user_dirs.append(Path.home() / ".local" / "share" / "femm")
        for d in user_dirs:
            if (d / name).is_file():
                return d / name
        if (self.bin_dir / name).is_file():
            return self.bin_dir / name
        return None


def _candidate_bin_dirs() -> list[Path]:
    out: list[Path] = []
    env = os.environ.get("FEMM_DIR")
    if env:
        out.append(Path(env))
    if os.name == "nt":
        out += [Path(r"C:\femm-qt\bin"), Path(r"C:\femm-qt")]
        for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            if os.environ.get(var):
                out.append(Path(os.environ[var]) / "femm-qt" / "bin")
    elif platform.system() == "Darwin":
        out += [Path("/Applications/femm_gui.app/Contents/MacOS"),
                Path.home() / "Applications" / "femm_gui.app" / "Contents" / "MacOS"]
    else:
        out += [Path.home() / ".local" / "opt" / "femm-qt" / "bin", Path.home() / ".local" / "bin",
                Path("/opt/femm-qt/bin"), Path("/usr/local/bin")]
    for exe in ("femm_headless", "femm_headless.exe"):
        found = shutil.which(exe)
        if found:
            out.append(Path(found).resolve().parent)
    seen: set[Path] = set()
    uniq: list[Path] = []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def find_femm() -> FemmInstall | None:
    """Return the FEMM 5 install, or None. Honours FEMM_DIR first (same rule as the official bindings)."""
    for d in _candidate_bin_dirs():
        if not d.is_dir():
            continue
        headless = None
        for name in ("femm_headlessw.exe", "femm_headless.exe", "femm_headless"):
            if (d / name).is_file():
                headless = d / name
                break
        if headless is None:
            continue
        gui = None
        for name in ("femm_gui.exe", "femm_gui"):
            if (d / name).is_file():
                gui = d / name
                break
        if d.name == "MacOS":
            root = d.parent.parent  # femm_gui.app
        elif d.name == "bin":
            root = d.parent
        else:
            root = d
        return FemmInstall(bin_dir=d, headless=headless, gui=gui, root=root)
    return None


def femm_version(install: FemmInstall) -> str | None:
    """Output of `femm_headless --version` (console build; the Windows 'w' build has no stdout)."""
    exe = install.bin_dir / ("femm_headless.exe" if os.name == "nt" else "femm_headless")
    if not exe.is_file():
        exe = install.headless
    try:
        r = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=20)
        return (r.stdout or r.stderr).strip() or None
    except Exception:
        return None
