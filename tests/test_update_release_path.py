"""The terminal update path is the release path.

`ephe update` moves the tree only to a published release tag, never to the tip
of `main`; between releases the checkout is left exactly where it is. The same
`apply_release` backs the PWA's release button, so the browser and the terminal
take the identical step.

A release update asks the release feed and the local git graph. It asks nothing
about `main`'s tip and never moves a checkout that is ahead of the newest tag.
"""
from __future__ import annotations

import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ephe_cli  # noqa: E402
from core import update_apply, update_check  # noqa: E402


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr or done.stdout
    return done.stdout.strip()


def commit(repo: Path, name: str, text: str) -> str:
    (repo / name).write_text(text)
    git(repo, "add", name)
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", name)
    return git(repo, "rev-parse", "HEAD")


def make_repo(tmp_path: Path) -> Path:
    """A main line with two tagged releases and one unreleased commit.

    A (v0.6.2) -> B (v0.6.3) -> C (v0.6.4) -> D (no tag)
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "a.txt", "a\n")
    git(repo, "tag", "v0.6.2")
    (repo / "install.sh").write_text("#!/bin/sh\nexit 0\n")
    (repo / "install.sh").chmod(0o755)
    git(repo, "add", "install.sh")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "installer")
    git(repo, "tag", "v0.6.3")
    commit(repo, "c.txt", "c\n")
    git(repo, "tag", "v0.6.4")
    commit(repo, "d.txt", "d\n")
    return repo


def pin(monkeypatch: pytest.MonkeyPatch, tag: str, current: str) -> None:
    monkeypatch.setattr(update_check, "current_version", lambda: current)
    monkeypatch.setattr(
        update_check,
        "_fetch_latest",
        lambda: {"tag": tag, "url": f"https://example.invalid/{tag}", "notes": "notes"},
    )
    update_check._reset_cache()





def test_the_terminal_update_uses_the_release_path(monkeypatch):
    seen: dict[str, object] = {}

    def release(root=None):
        seen["root"] = root
        return {"ok": True, "reason": "", "detail": "already current", "steps": []}

    monkeypatch.setattr(update_apply, "apply_release", release)
    monkeypatch.setattr(
        update_apply,
        "apply_update",
        lambda root=None: pytest.fail("ephe update must not take the commit path"),
    )

    code = ephe_cli.cmd_update(Namespace(json=False, model=None))

    assert code == 0
    assert seen["root"] == ephe_cli.PROJECT_ROOT


def test_the_command_defaults_to_release():
    parsed = ephe_cli.build_parser().parse_args(["update"])
    assert parsed.channel == "release"


def test_the_explicit_commit_flag_is_the_documented_exception(monkeypatch):
    """`--channel commit` moves a backend tree the desktop/PWA serves. It is not
    what the terminal does by default, and it has to be asked for by name."""
    seen: list[str] = []
    monkeypatch.setattr(
        update_apply,
        "apply_release",
        lambda root=None: pytest.fail("--channel commit must not use the release path"),
    )
    monkeypatch.setattr(
        update_apply,
        "apply_update",
        lambda root=None: seen.append("commit") or {"ok": True, "detail": "main", "steps": []},
    )

    code = ephe_cli.cmd_update(Namespace(json=False, model=None, channel="commit"))

    assert code == 0
    assert seen == ["commit"]





def test_a_newer_release_moves_to_the_tag_not_the_branch_tip(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "v0.6.3")
    pin(monkeypatch, "v0.6.4", "0.6.3")

    out = update_apply.apply_release(repo)

    assert out["ok"] is True, out
    assert out["tag"] == "v0.6.4"
    assert [step["name"] for step in out["steps"]] == ["release", "install"]
    assert (repo / "c.txt").exists()
    # D was committed after the tag: the release path must not reach it.
    assert not (repo / "d.txt").exists()
    assert out["before"] != out["after"]
    assert out["restart"] is True


def test_no_newer_release_leaves_the_tree_alone(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "v0.6.3")
    pin(monkeypatch, "v0.6.3", "0.6.3")
    monkeypatch.setattr(
        update_check,
        "_fetch_main_compare",
        lambda commit: pytest.fail("the release path asked the branch"),
    )

    out = update_apply.apply_release(repo)

    assert out["ok"] is True
    assert out["reason"] == "latest_release"
    assert out["steps"] == []
    assert git(repo, "rev-parse", "HEAD") == git(repo, "rev-parse", "v0.6.3")


def test_a_checkout_ahead_of_the_newest_release_is_not_moved_backwards(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)  # main is at D, the newest tag is C
    pin(monkeypatch, "v0.6.4", "0.6.3")
    before = git(repo, "rev-parse", "HEAD")

    out = update_apply.apply_release(repo)

    assert out["ok"] is False
    assert out["reason"] == "ahead_of_release"
    assert out["steps"] == []
    assert git(repo, "rev-parse", "HEAD") == before
    assert (repo / "d.txt").exists()


def test_an_unreachable_feed_stops_before_git(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)

    def offline():
        raise OSError("no network")

    monkeypatch.setattr(update_check, "_fetch_latest", offline)
    update_check._reset_cache()
    monkeypatch.setattr(
        update_apply, "_git", lambda *args, **kwargs: pytest.fail("git ran without an answer")
    )

    out = update_apply.apply_release(repo)

    assert out["ok"] is False
    assert out["reason"] == "release_unreachable"
    assert out["steps"] == []


def test_a_release_install_without_a_checkout_says_so(tmp_path, monkeypatch):
    pin(monkeypatch, "v9.9.9", "0.6.3")
    (tmp_path / "notgit").mkdir()
    out = update_apply.apply_release(tmp_path / "notgit")
    assert out["ok"] is False
    assert out["reason"] == "not_a_checkout"


def test_the_release_probe_allows_a_detached_tag_but_not_another_branch(tmp_path):
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "v0.6.3")
    assert update_apply.probe(repo, release=True) == {"ok": True, "code": ""}
    git(repo, "checkout", "-q", "-b", "feature")
    assert update_apply.probe(repo, release=True)["code"] == "not_on_main"





class TestReleaseRoute:
    def test_the_route_needs_the_browser_marker_and_the_word(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        from server.main import create_app

        with TestClient(create_app()) as client:
            refused = client.post("/api/update/release", json={"confirm": "release"})
            assert refused.status_code == 403
            missing = client.post(
                "/api/update/release",
                json={},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert missing.status_code == 400

    def test_the_route_runs_the_release_apply(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.setattr(
            update_apply,
            "apply_release",
            lambda: {"ok": True, "reason": "latest_release", "detail": "current", "steps": []},
        )
        from server.main import create_app

        with TestClient(create_app()) as client:
            r = client.post(
                "/api/update/release",
                json={"confirm": "release"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert r.status_code == 200
            assert r.json()["reason"] == "latest_release"
