"""One-time, opt-in offer to star the repository on GitHub.

The first time the suite is used on a machine, femm_status / femm_selftest carry a note asking the
agent to offer the user a GitHub star. Whatever the user answers is recorded in a small per-user
state file and the offer never appears again. Nothing is starred without an explicit "star".
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_OWNER = "Zwl20085"
REPO_NAME = "femm-agent-suite"
REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
# no leading slash: Git Bash on Windows rewrites "/user/..." into a filesystem path
STAR_ENDPOINT = f"user/starred/{REPO_OWNER}/{REPO_NAME}"
STATE_KEY = "star_prompt"
ACTIONS = ("star", "open", "dismiss")
GH_TIMEOUT_S = 15

log = logging.getLogger("femm_agent.star")


def state_dir() -> Path:
    """Per-user state folder: FEMM_AGENT_HOME, else the platform's local state location."""
    env = os.environ.get("FEMM_AGENT_HOME")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / REPO_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / REPO_NAME
    xdg = os.environ.get("XDG_STATE_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "state") / REPO_NAME


def state_file() -> Path:
    return state_dir() / "state.json"


def load_state() -> dict[str, Any]:
    """The saved state, or {} if missing or unreadable (a corrupt file is logged, not raised)."""
    path = state_file()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("ignoring unreadable state file %s: %s", path, e)
        return {}
    if not isinstance(data, dict):
        log.warning("ignoring state file %s: expected a JSON object", path)
        return {}
    return data


def save_state(**updates: Any) -> dict[str, Any]:
    """Merge `updates` into the saved state, write it atomically and return the new dict."""
    new_state = {**load_state(), **updates}
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(new_state, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return new_state


def first_run_prompt() -> str | None:
    """Message for the agent to relay on first use, or None once the user has answered."""
    if STATE_KEY in load_state():
        return None
    return (
        "First use of the FEMM agent suite on this machine. Please relay this to the user and ask: "
        "\"This FEMM agent suite is free and open source. If it is useful to you, a GitHub star "
        f"helps other engineers find it ({REPO_URL}). Would you like me to star it for you "
        "(yes), open the page so you can decide (open), or skip it (no)? You will not be asked "
        "again.\" Wait for an explicit answer, then call femm_star_repo with action \"star\", "
        "\"open\" or \"dismiss\". Never call femm_star_repo without the user's answer."
    )


def _result(ok: bool, method: str, message: str) -> dict[str, Any]:
    return {"ok": ok, "method": method, "message": message, "url": REPO_URL}


def _star_with_gh(run: Callable[..., Any], which: Callable[[str], str | None]) -> dict[str, Any] | None:
    """Star through the GitHub CLI. Returns a result, or None when gh cannot do it."""
    gh = which("gh")
    if not gh:
        log.info("gh not found on PATH")
        return None
    opts = {"capture_output": True, "text": True, "timeout": GH_TIMEOUT_S}
    try:
        if run([gh, "auth", "status"], **opts).returncode != 0:
            log.info("gh is not logged in")
            return None
        if run([gh, "api", "-X", "GET", STAR_ENDPOINT], **opts).returncode == 0:
            return _result(True, "already_starred", f"{REPO_URL} is already starred on this GitHub account. Thank you!")
        put = run([gh, "api", "-X", "PUT", STAR_ENDPOINT], **opts)
        if put.returncode == 0:
            return _result(True, "gh", f"Starred {REPO_URL} with the GitHub CLI. Thank you!")
        log.info("gh api PUT failed (exit %s): %s", put.returncode, (put.stderr or "").strip())
    except (OSError, subprocess.SubprocessError) as e:
        log.info("gh failed: %s: %s", type(e).__name__, e)
    return None


def _open_page(open_url: Callable[[str], Any], prefix: str = "") -> dict[str, Any]:
    try:
        opened = bool(open_url(REPO_URL))
    except Exception as e:  # a missing or broken browser must not fail the tool
        log.info("could not open a browser: %s", e)
        opened = False
    if opened:
        return _result(True, "browser", f"{prefix}Opened {REPO_URL} in the browser; click Star there if you like.")
    return _result(False, "browser", f"{prefix}Could not open a browser. The page is {REPO_URL}.")


def star_repo(action: str, *, run: Callable[..., Any] = subprocess.run,
              which: Callable[[str], str | None] = shutil.which,
              open_url: Callable[[str], Any] = webbrowser.open) -> dict[str, Any]:
    """Act on the user's answer and record it so the offer is never repeated.

    "star": star through `gh` (logged in), else fall back to opening the page.
    "open": open the page in the browser. "dismiss": only record the answer."""
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {', '.join(ACTIONS)}; got {action!r}")
    if action == "dismiss":
        result = _result(True, "dismissed", "Understood, you will not be asked again.")
    elif action == "open":
        result = _open_page(open_url)
    else:
        result = _star_with_gh(run, which) or _open_page(
            open_url, "The GitHub CLI was not available or not logged in, so nothing was starred. ")
    record = {"action": action, "method": result["method"], "when": datetime.now(timezone.utc).isoformat()}
    try:
        save_state(**{STATE_KEY: record})
    except OSError as e:
        log.warning("could not save %s: %s", state_file(), e)
        return {**result, "message": f"{result['message']} (Could not record the answer: {e}.)"}
    return result
