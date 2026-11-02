"""Taking the newest commits from inside the app.

`ephe update` has a body now: the same pull and the same installer, reachable
from the dialog. The contract is that it stops before the first command when it
cannot finish — a dirty tree, another branch, a second click — and that a
successful run names what moved.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import update_apply  # noqa: E402


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def commit(cwd: Path, name: str, text: str) -> None:
    (cwd / name).write_text(text)
    git(cwd, "add", name)
    git(cwd, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", name)


def make_checkout(tmp_path: Path, *, installer_exit: int = 0) -> Path:
    """A clone with one upstream commit waiting: the pull has something to do."""
    upstream = tmp_path / "upstream"
    upstream.mkdir(exist_ok=True)
    git(upstream, "init", "-q", "-b", "main")
    commit(upstream, "a.txt", "one\n")
    (upstream / "install.sh").write_text(f"#!/usr/bin/env bash\nexit {installer_exit}\n")
    git(upstream, "add", "install.sh")
    git(upstream, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "installer")
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(upstream), str(work))
    commit(upstream, "b.txt", "two\n")
    return work


@pytest.fixture
def checkout(tmp_path):
    return make_checkout(tmp_path)


def test_a_clean_checkout_pulls_and_reinstalls(tmp_path, checkout):
    out = update_apply.apply_update(checkout)
    assert out["ok"] is True, out
    assert out["before"] != out["after"]
    assert [s["name"] for s in out["steps"]] == ["pull", "install"]
    assert (checkout / "b.txt").exists()


def test_a_dirty_tree_stops_before_the_pull(checkout):
    (checkout / "a.txt").write_text("changed\n")
    out = update_apply.apply_update(checkout)
    assert out["ok"] is False and out["reason"] == "dirty_tree"
    assert out["steps"] == []
    assert not (checkout / "b.txt").exists()


def test_another_branch_is_not_updated(checkout):
    git(checkout, "checkout", "-q", "-b", "feature")
    out = update_apply.apply_update(checkout)
    assert out["ok"] is False and out["reason"] == "not_on_main"


def test_an_installation_without_a_checkout_says_so(tmp_path):
    (tmp_path / "notgit").mkdir()
    out = update_apply.apply_update(tmp_path / "notgit")
    assert out["ok"] is False and out["reason"] == "not_a_checkout"


def test_a_second_click_is_refused_while_one_runs(checkout):
    assert update_apply._BUSY.acquire(blocking=False)
    try:
        out = update_apply.apply_update(checkout)
    finally:
        update_apply._BUSY.release()
    assert out["ok"] is False and out["reason"] == "busy"


def test_a_failing_installer_is_reported_with_its_steps(tmp_path):
    out = update_apply.apply_update(make_checkout(tmp_path, installer_exit=3))
    assert out["ok"] is False and out["reason"] == "install_failed"
    assert out["steps"][0]["name"] == "pull" and out["steps"][0]["ok"] is True
    assert out["steps"][1]["ok"] is False


class TestRoute:

    def test_the_route_needs_the_browser_marker(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        from server.main import create_app

        with TestClient(create_app()) as client:
            r = client.post("/api/update/apply", json={"confirm": "update"})
            assert r.status_code == 403

    def test_the_route_requires_the_confirm_word(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        from server.main import create_app

        with TestClient(create_app()) as client:
            r = client.post(
                "/api/update/apply", json={}, headers={"X-Requested-With": "XMLHttpRequest"}
            )
            assert r.status_code == 400

    def test_the_route_runs_the_apply(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        seen: list[bool] = []

        def fake(**_: object) -> dict:
            seen.append(True)
            return {"ok": True, "steps": [], "detail": "abc → def", "restart": True}

        monkeypatch.setattr(update_apply, "apply_update", fake)
        from server.main import create_app

        with TestClient(create_app()) as client:
            r = client.post(
                "/api/update/apply",
                json={"confirm": "update"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert r.status_code == 200
            assert r.json()["ok"] is True
        assert seen == [True]


# The environment step on its own
# The desktop updater replaces the app bundle and the shell then moves the
# checkout. That leaves the tree newer than the packages beside it, which a
# version number cannot show. `reinstall` is that one step, without the git.


def test_the_environment_step_runs_the_installer_and_no_git(tmp_path):
    work = make_checkout(tmp_path)
    out = update_apply.reinstall(work)
    assert out["ok"] is True, out
    assert [s["name"] for s in out["steps"]] == ["install"]
    assert out["restart"] is True
    # moving the tree is not this step's job: what upstream added stays away
    assert not (work / "b.txt").exists()


def test_the_environment_step_needs_a_checkout(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    out = update_apply.reinstall(plain)
    assert out["ok"] is False and out["reason"] == "not_a_checkout"


def test_a_tree_without_an_installer_says_so(tmp_path):
    plain = tmp_path / "nogit-here"
    plain.mkdir()
    git(plain, "init", "-q", "-b", "main")
    commit(plain, "a.txt", "one\n")
    out = update_apply.reinstall(plain)
    assert out["ok"] is False and out["reason"] == "no_installer"


def test_a_dirty_tree_is_not_reinstalled_over(tmp_path):
    work = make_checkout(tmp_path)
    (work / "a.txt").write_text("changed\n")
    out = update_apply.reinstall(work)
    assert out["ok"] is False and out["reason"] == "dirty_tree"


def test_a_failing_installer_is_reported_with_its_step(tmp_path):
    work = make_checkout(tmp_path, installer_exit=4)
    out = update_apply.reinstall(work)
    assert out["ok"] is False and out["reason"] == "install_failed"
    assert out["steps"][0]["name"] == "install" and out["steps"][0]["ok"] is False


def test_a_second_refresh_is_refused_while_one_runs(tmp_path):
    work = make_checkout(tmp_path)
    assert update_apply._BUSY.acquire(blocking=False)
    try:
        out = update_apply.reinstall(work)
    finally:
        update_apply._BUSY.release()
    assert out["ok"] is False and out["reason"] == "busy"


class TestInstallRoute:

    def _client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        from server.main import create_app

        return TestClient(create_app())

    def test_the_route_needs_the_browser_marker(self, tmp_path, monkeypatch):
        with self._client(tmp_path, monkeypatch) as client:
            r = client.post("/api/update/install", json={"confirm": "install"})
            assert r.status_code == 403

    def test_the_route_requires_the_confirm_word(self, tmp_path, monkeypatch):
        with self._client(tmp_path, monkeypatch) as client:
            r = client.post(
                "/api/update/install", json={}, headers={"X-Requested-With": "XMLHttpRequest"}
            )
            assert r.status_code == 400

    def test_the_route_runs_the_reinstall(self, tmp_path, monkeypatch):
        seen: list[bool] = []

        def fake(**_: object) -> dict:
            seen.append(True)
            return {"ok": True, "steps": [{"name": "install", "ok": True, "detail": ""}]}

        monkeypatch.setattr(update_apply, "reinstall", fake)
        with self._client(tmp_path, monkeypatch) as client:
            r = client.post(
                "/api/update/install",
                json={"confirm": "install"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert r.status_code == 200
            assert r.json()["ok"] is True
        assert seen == [True]

    def test_the_route_runs_even_when_the_check_is_switched_off(self, tmp_path, monkeypatch):
        """The shell moved the tree already; refusing here would leave it half-updated."""
        seen: list[bool] = []

        def fake(**_: object) -> dict:
            seen.append(True)
            return {"ok": True, "steps": []}

        monkeypatch.setattr(update_apply, "reinstall", fake)
        monkeypatch.setattr("core.update_check.update_check_enabled", lambda: False)
        with self._client(tmp_path, monkeypatch) as client:
            r = client.post(
                "/api/update/install",
                json={"confirm": "install"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert r.status_code == 200
        assert seen == [True]
