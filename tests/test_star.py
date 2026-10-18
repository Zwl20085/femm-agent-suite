"""Offline tests of the one-time star offer. No network, no real `gh`, no real browser."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from femm_agent import star
from femm_agent.server import build_server
from femm_agent.sessions import SessionManager

GH = "C:/fake/gh.exe"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    d = tmp_path / "state"
    monkeypatch.setenv("FEMM_AGENT_HOME", str(d))
    return d


class FakeRun:
    """Records argv lists; answers each with the exit code given for its key."""

    def __init__(self, codes=None, raise_on=None):
        self.calls, self.kwargs = [], []
        self.codes = {"auth": 0, "GET": 1, "PUT": 0, **(codes or {})}
        self.raise_on = raise_on

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        self.kwargs.append(kwargs)
        key = "auth" if argv[1] == "auth" else argv[3]
        if key == self.raise_on:
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))
        return SimpleNamespace(returncode=self.codes[key], stdout="", stderr="HTTP 404" if self.codes[key] else "")


class FakeBrowser:
    def __init__(self, result=True):
        self.urls, self.result = [], result

    def __call__(self, url):
        self.urls.append(url)
        return self.result


def which_gh(name):
    return GH if name == "gh" else None


def recorded():
    return star.load_state()[star.STATE_KEY]


def test_state_dir_env_override(home):
    assert star.state_dir() == home
    assert star.state_file() == home / "state.json"


def test_first_run_prompt_before_and_after():
    msg = star.first_run_prompt()
    assert msg and star.REPO_URL in msg and "femm_star_repo" in msg
    assert "Never call femm_star_repo without" in msg
    star.star_repo("dismiss", run=FakeRun(), which=which_gh, open_url=FakeBrowser())
    assert star.first_run_prompt() is None


def test_star_via_gh_puts_without_leading_slash():
    run, browser = FakeRun(), FakeBrowser()
    r = star.star_repo("star", run=run, which=which_gh, open_url=browser)
    assert r["ok"] and r["method"] == "gh" and r["url"] == star.REPO_URL
    assert run.calls == [
        [GH, "auth", "status"],
        [GH, "api", "-X", "GET", "user/starred/Zwl20085/femm-agent-suite"],
        [GH, "api", "-X", "PUT", "user/starred/Zwl20085/femm-agent-suite"],
    ]
    assert all(not c[-1].startswith("/") for c in run.calls)
    assert all(k["timeout"] == 15 and "shell" not in k for k in run.kwargs)
    assert browser.urls == []
    rec = recorded()
    assert rec["action"] == "star" and rec["method"] == "gh" and rec["when"].endswith("+00:00")


def test_already_starred_skips_put():
    run = FakeRun(codes={"GET": 0})
    r = star.star_repo("star", run=run, which=which_gh, open_url=FakeBrowser())
    assert r["ok"] and r["method"] == "already_starred"
    assert [c[3] for c in run.calls[1:]] == ["GET"]
    assert recorded()["method"] == "already_starred"


@pytest.mark.parametrize("which, run", [
    (lambda name: None, FakeRun()),                       # gh missing
    (which_gh, FakeRun(codes={"auth": 1})),               # gh not logged in
    (which_gh, FakeRun(raise_on="GET")),                  # gh times out
    (which_gh, FakeRun(codes={"PUT": 1})),                # PUT refused
], ids=["gh_missing", "auth_fails", "gh_exception", "put_fails"])
def test_star_falls_back_to_browser(which, run):
    browser = FakeBrowser()
    r = star.star_repo("star", run=run, which=which, open_url=browser)
    assert r["ok"] and r["method"] == "browser"
    assert browser.urls == [star.REPO_URL]
    assert "nothing was starred" in r["message"]
    assert (recorded()["action"], recorded()["method"]) == ("star", "browser")


def test_gh_missing_runs_nothing():
    run = FakeRun()
    star.star_repo("star", run=run, which=lambda name: None, open_url=FakeBrowser())
    assert run.calls == []


def test_browser_unavailable_still_records():
    r = star.star_repo("star", run=FakeRun(), which=lambda n: None, open_url=FakeBrowser(result=False))
    assert not r["ok"] and star.REPO_URL in r["message"]
    assert star.first_run_prompt() is None


def test_open_only_uses_browser():
    run, browser = FakeRun(), FakeBrowser()
    r = star.star_repo("open", run=run, which=which_gh, open_url=browser)
    assert r["ok"] and r["method"] == "browser" and browser.urls == [star.REPO_URL]
    assert run.calls == []
    assert recorded()["action"] == "open"


def test_dismiss_touches_nothing():
    run, browser = FakeRun(), FakeBrowser()
    r = star.star_repo("dismiss", run=run, which=which_gh, open_url=browser)
    assert r["ok"] and r["method"] == "dismissed"
    assert run.calls == [] and browser.urls == []
    assert recorded()["action"] == "dismiss"


@pytest.mark.parametrize("action", ["yes", "", "STAR", None])
def test_invalid_action(action):
    with pytest.raises(ValueError):
        star.star_repo(action, run=FakeRun(), which=which_gh, open_url=FakeBrowser())
    assert star.load_state() == {}


@pytest.mark.parametrize("content", ["{not json", "[1, 2]"])
def test_corrupt_state_is_empty(home, content, caplog):
    home.mkdir(parents=True)
    (home / "state.json").write_text(content, encoding="utf-8")
    assert star.load_state() == {}
    assert "ignoring" in caplog.text
    assert star.first_run_prompt() is not None
    star.star_repo("dismiss")
    assert json.loads((home / "state.json").read_text(encoding="utf-8"))[star.STATE_KEY]["action"] == "dismiss"


def test_save_state_returns_new_dict_and_keeps_other_keys():
    first = star.save_state(other=1)
    second = star.save_state(**{star.STATE_KEY: {"action": "dismiss"}})
    assert first == {"other": 1}
    assert second == {"other": 1, star.STATE_KEY: {"action": "dismiss"}}


def test_status_and_selftest_carry_note_only_on_first_run(tmp_path, monkeypatch):
    from femm_agent import ipc
    monkeypatch.setattr(ipc, "find_femm", lambda: None)
    _mcp, ctx = build_server(SessionManager(install=None, default_work_dir=tmp_path), include_engineering=False)
    tools = ctx.extras["tools"]
    st = tools["femm_status"]()
    assert st["ok"] and "install" in st["result"]
    assert st["first_run_note"] == star.first_run_prompt()
    assert "first_run_note" in tools["femm_selftest"]()

    bad = tools["femm_star_repo"](action="maybe")
    assert not bad["ok"] and "dismiss" in bad["error"]["hint"]
    assert star.first_run_prompt() is not None
    done = tools["femm_star_repo"](action="dismiss")
    assert done["ok"] and done["result"]["method"] == "dismissed"

    assert "first_run_note" not in tools["femm_status"]()
    assert "first_run_note" not in tools["femm_selftest"]()
