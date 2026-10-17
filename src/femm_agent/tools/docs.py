"""Documentation tools: command catalog, the installed FEMM manual, examples and verified facts."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .. import catalog
from ..catalog import data_dir
from ._common import ToolContext, ToolInputError, envelope

_HEADING = re.compile(r"^\s*(\d+(?:\.\d+){1,3})\.?\s+([A-Z][^.+=]{2,90}?)\s*$")


def manual_text(ctx: ToolContext, refresh: bool = False) -> tuple[str, str]:
    """Extract the installed manual.pdf to text once (pdftotext if on PATH, else pypdf); cached in
    <work root>/_cache/manual.txt. Returns (text, how)."""
    inst = ctx.sessions.install
    cache = ctx.sessions.default_work_dir / "_cache" / "manual.txt"
    if cache.is_file() and not refresh:
        return cache.read_text(encoding="utf-8", errors="replace"), f"cache {cache.as_posix()}"
    pdf = inst.manual_pdf if inst else None
    if pdf is None:
        raise ToolInputError("the FEMM manual (manual.pdf) was not found in the install",
                             "Use femm_api_search / femm_api_get (the catalog is built from the manual).")
    cache.parent.mkdir(parents=True, exist_ok=True)
    exe = shutil.which("pdftotext")
    if exe:
        r = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(pdf), str(cache)], capture_output=True, timeout=120)
        if r.returncode == 0 and cache.is_file():
            return cache.read_text(encoding="utf-8", errors="replace"), "pdftotext"
    try:
        from pypdf import PdfReader  # optional
    except Exception:
        raise ToolInputError("cannot extract the manual: neither pdftotext nor pypdf is available",
                             "pip install pypdf (or install poppler's pdftotext), or use femm_api_search.")
    text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(pdf)).pages)
    cache.write_text(text, encoding="utf-8")
    return text, "pypdf"


def sections(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    out = []
    for i, ln in enumerate(lines):
        if ". . ." in ln or "...." in ln:
            continue          # table of contents
        m = _HEADING.match(ln)
        if m and len(ln.strip()) < 100:
            out.append({"number": m.group(1), "title": m.group(2).strip(), "line": i})
    return out


def find_section(text: str, query: str, max_chars: int = 6000) -> dict[str, Any]:
    lines = text.splitlines()
    secs = sections(text)
    q = query.strip().lower()

    def body(k: int) -> str:
        start = secs[k]["line"]
        level = secs[k]["number"].count(".")
        end = len(lines)
        for j in range(k + 1, len(secs)):
            if secs[j]["number"].count(".") <= level:
                end = secs[j]["line"]
                break
        return "\n".join(lines[start:end])

    hit = None
    for k, sct in enumerate(secs):
        if q == sct["number"] or q == f"{sct['number']} {sct['title']}".lower():
            hit = k
            break
    if hit is None:
        for k, sct in enumerate(secs):
            if q in sct["title"].lower():
                hit = k
                break
    if hit is not None:
        txt = body(hit)
        return {"match": "heading", "section": f"{secs[hit]['number']} {secs[hit]['title']}",
                "text": txt[:max_chars], "truncated": len(txt) > max_chars, "chars": len(txt)}
    # keyword search: rank sections by number of hits, return snippets
    idx = [i for i, ln in enumerate(lines) if q in ln.lower()]
    if not idx:
        raise ToolInputError(f"{query!r} not found in the manual",
                             "Try a shorter keyword, a section number like '3.7.1', or femm_api_search.")

    def owner(i: int) -> str:
        best = None
        for sct in secs:
            if sct["line"] <= i:
                best = sct
            else:
                break
        return f"{best['number']} {best['title']}" if best else "(front matter)"

    snippets, used, budget = [], set(), max_chars
    for i in idx:
        if any(abs(i - u) < 12 for u in used):
            continue
        used.add(i)
        snip = "\n".join(lines[max(0, i - 4): i + 12])
        if budget - len(snip) < 0:
            break
        budget -= len(snip)
        snippets.append({"section": owner(i), "line": i + 1, "text": snip})
    return {"match": "keyword", "hits": len(idx), "snippets": snippets}


def register(mcp, ctx: ToolContext) -> None:
    @mcp.tool()
    def femm_api_search(query: str, physics: str | None = None, phase: str | None = None, limit: int = 15) -> dict:
        """Search the catalog of every FEMM 5 scripting command (name, signature, description).
        physics: magnetics|electrostatics|heatflow|currentflow (common commands always included);
        phase: pre (mi_/ei_/hi_/ci_) or post (mo_/eo_/ho_/co_). Examples: 'block integral',
        'air gap', 'boundary', 'bitmap', 'mi_addmaterial'. Then femm_api_get(name) for full args."""
        def run():
            hits = catalog.search(query, physics=physics, phase=phase, limit=limit)
            out: dict[str, Any] = {"matches": hits, "catalog_size": len(catalog.CATALOG)}
            if catalog.CATALOG.warning:
                out["warning"] = catalog.CATALOG.warning
            return out
        return envelope(run)

    @mcp.tool()
    def femm_api_get(name: str) -> dict:
        """Full catalog entry of one command: args (name, type, optional, description), return
        value, integer code tables (enums), read_only flag, notes (e.g. pyFEMM-only helpers the
        engine does not define), and where it is documented in the manual."""
        def run():
            c = catalog.get(name)
            if c is None:
                near = [r["name"] for r in catalog.search(name, limit=6)]
                raise ToolInputError(f"{name!r} is not in the catalog", f"Closest: {near}. Use femm_api_search.")
            return dict(c, signature=catalog.Catalog.signature(c))
        return envelope(run)

    @mcp.tool()
    def femm_manual_section(query: str, max_chars: int = 6000, refresh: bool = False) -> dict:
        """Read the installed FEMM 5 manual (manual.pdf, extracted to text once and cached).
        query: a section number ('3.7.1'), a heading ('Data Extraction Commands', 'Boundary
        Conditions', 'Air Gap'), or a keyword ('mo_gapintegral', 'Kelvin'): headings return the
        section text, keywords return snippets with their section names."""
        def run():
            text, how = manual_text(ctx, refresh)
            r = find_section(text, query, max_chars)
            r["source"] = how
            return r
        return envelope(run)

    @mcp.tool()
    def femm_examples_list(query: str = "", extension: str | None = None) -> dict:
        """Example models and scripts shipped with FEMM 5 (examples/ and pyfemm/examples/): name,
        path, size, and for models the header (problem type, units, frequency, depth). Filter by
        substring `query` and/or `extension` ('.fem', '.py', '.lua', ...). Open one with femm_open."""
        def run():
            files: list[dict[str, Any]] = []
            idx = data_dir() / "examples_index.json"
            if idx.is_file():
                files = json.loads(idx.read_text(encoding="utf-8")).get("files", [])
            known = {Path(f.get("path", "")).name.lower() for f in files}
            inst = ctx.sessions.install
            roots = []
            if inst is not None:
                if inst.examples_dir:
                    roots.append(inst.examples_dir)
                if inst.pyfemm_dir and (inst.pyfemm_dir / "examples").is_dir():
                    roots.append(inst.pyfemm_dir / "examples")
            for r in roots:
                for p in sorted(r.iterdir()):
                    if p.is_file() and p.name.lower() not in known:
                        files.append({"name": p.name, "path": p.as_posix(), "size_bytes": p.stat().st_size,
                                      "extension": p.suffix.lower(), "tree": r.name})
            # point indexed entries at the actual install if it moved
            for f in files:
                if inst is not None and f.get("path") and not Path(f["path"]).is_file():
                    for r in roots:
                        cand = r / f["name"]
                        if cand.is_file():
                            f["path"] = cand.as_posix()
            q = query.lower()
            sel = [f for f in files if (not q or q in f["name"].lower() or q in json.dumps(f).lower())
                   and (not extension or f.get("extension", "").lower() == extension.lower())]
            return {"count": len(sel), "files": sel}
        return envelope(run)

    @mcp.tool()
    def femm_facts(query: str | None = None) -> dict:
        """Verified FEMM 5 behaviour collected by this project (docs/femm5-facts.md): command
        quirks, units, what works headless, renamed materials. `query` returns only the sections
        that mention it. Read this before trusting FEMM 4.2 habits."""
        def run():
            cands = [data_dir().parent / "docs" / "femm5-facts.md", data_dir() / "femm5-facts.md"]
            p = next((c for c in cands if c.is_file()), None)
            if p is None:
                raise ToolInputError("docs/femm5-facts.md not found", "Use femm_manual_section or femm_api_get.")
            text = p.read_text(encoding="utf-8")
            if not query:
                return {"file": p.name, "text": text}
            parts = re.split(r"(?m)^(?=#{2,3} )", text)
            hits = [part for part in parts if query.lower() in part.lower()]
            return {"file": p.name, "sections": hits, "matched": len(hits)}
        return envelope(run)
