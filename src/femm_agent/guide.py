"""The femm skills (operating manual) for clients that did not load them (pure, no FEMM).

The single source of truth is ``.claude/skills/`` in the repo. Wheels ship a copy as package data at
``femm_agent/skills/`` (hatch force-include, see pyproject.toml). The packaged copy is read first and
the repo copy otherwise; an editable install has no packaged copy, so it always reads the live repo
files. Same layout and API as ``jmag_bridge.guide`` in the sibling jmag suite.
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path

try:
    from importlib.resources.abc import Traversable
except ImportError:  # Python 3.10
    from importlib.abc import Traversable

ROUTER = "femm"  # entry-point skill: safety rules, routing, tool map


def _has_skills(root: Traversable) -> bool:
    try:
        return root.is_dir() and root.joinpath(ROUTER, "SKILL.md").is_file()
    except (OSError, ValueError):
        return False


def skills_root() -> Traversable:
    """Packaged ``femm_agent/skills`` (wheel) if present, else the repo checkout's ``.claude/skills``."""
    packaged = resources.files("femm_agent").joinpath("skills")
    if _has_skills(packaged):
        return packaged
    repo = Path(__file__).resolve().parent.parent.parent / ".claude" / "skills"
    if _has_skills(repo):
        return repo
    raise FileNotFoundError("femm skills not found: neither packaged femm_agent/skills nor a repo checkout "
                            "(.claude/skills) - reinstall femm-agent-suite from a wheel built with the skills")


def facts_path() -> Path | None:
    """docs/femm5-facts.md: packaged ``femm_agent/docs`` copy first, then the repo's ``docs/``."""
    here = Path(__file__).resolve().parent
    for c in (here / "docs" / "femm5-facts.md", here / "data" / "femm5-facts.md",
              here.parent.parent / "docs" / "femm5-facts.md"):
        if c.is_file():
            return c
    return None


def _check_name(name: str, what: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{what} must be a non-empty name")
    name = name.strip()
    if "/" in name or "\\" in name or ".." in name or ":" in name or name.startswith("."):
        raise ValueError(f"invalid {what} {name!r}: plain names only (no path separators or '..')")
    return name


def _front_matter(text: str) -> dict[str, str]:
    """name/description from the ``---`` YAML header (flat keys; indented lines continue the previous value)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    key = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line[:1] in (" ", "\t") and key:
            out[key] = (out[key] + " " + line.strip()).strip()
            continue
        k, sep, v = line.partition(":")
        if sep and k.strip():
            key = k.strip()
            v = v.strip()
            out[key] = "" if v in (">", "|", ">-", "|-") else v.strip("\"'")
    return out


def _skill_dir(name: str) -> Traversable:
    name = _check_name(name, "skill")
    d = skills_root().joinpath(name)
    if not d.joinpath("SKILL.md").is_file():
        raise KeyError(name)
    return d


def list_skills() -> list[dict[str, str]]:
    """[{name, description}] for every skill folder with a SKILL.md, router first, then alphabetical."""
    out = []
    for d in skills_root().iterdir():
        f = d.joinpath("SKILL.md")
        if d.is_dir() and f.is_file():
            fm = _front_matter(f.read_text(encoding="utf-8"))
            out.append({"name": fm.get("name") or d.name, "description": fm.get("description", "")})
    return sorted(out, key=lambda s: (s["name"] != ROUTER, s["name"]))


def skill_names() -> list[str]:
    return [s["name"] for s in list_skills()]


def list_references(name: str) -> list[str]:
    """File names under ``<skill>/references/`` (empty when the skill has none)."""
    refs = _skill_dir(name).joinpath("references")
    if not refs.is_dir():
        return []
    return sorted(f.name for f in refs.iterdir() if f.is_file())


def read_skill(name: str, reference: str | None = None) -> str:
    """SKILL.md text of ``name``, or ``references/<reference>`` (``.md`` may be omitted).

    Raises KeyError for an unknown skill or reference, ValueError for a name with a path in it.
    """
    d = _skill_dir(name)
    if reference is None:
        return d.joinpath("SKILL.md").read_text(encoding="utf-8")
    ref = _check_name(reference, "reference")
    refs = d.joinpath("references")
    for cand in (ref, ref + ".md"):
        f = refs.joinpath(cand)
        if f.is_file():
            return f.read_text(encoding="utf-8")
    raise KeyError(reference)
