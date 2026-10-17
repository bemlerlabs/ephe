"""W19 F3 — the workspace dialog: create a folder (POST /api/fs/mkdir).

The workspace dialog gains "New folder" plus a Desktop quick-pick. The endpoint
is deliberately cut narrow: the parent lives inside the allowed roots, the name
is a single path segment, and no nested creation happens.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def _home(tmp_path, monkeypatch):
    """Isolated home — _get_allowed_roots reads Path.home() (the HOME env)."""
    home = tmp_path / "home"
    (home / "Desktop").mkdir(parents=True)
    (home / "Documents").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("EPHE_HOME_OVERRIDE", str(home))
    return home


@pytest.fixture
def client(_home):
    from server.main import app

    with TestClient(app) as c:
        yield c


def test_mkdir_inside_desktop_works(client, _home):
    r = client.post("/api/fs/mkdir", json={"parent": str(_home / "Desktop"), "name": "Mein Projekt"})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True
    assert (_home / "Desktop" / "Mein Projekt").is_dir()


def test_mkdir_is_idempotent_for_existing_dir(client, _home):
    parent = str(_home / "Documents")
    r1 = client.post("/api/fs/mkdir", json={"parent": parent, "name": "solo"})
    r2 = client.post("/api/fs/mkdir", json={"parent": parent, "name": "solo"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["created"] is False


def test_mkdir_rejects_outside_allowed_roots(client, tmp_path, monkeypatch):
    """A parent outside the allowed roots gets 403 — and inside them still works.

    The roots are pinned instead of inherited: core/tools/base.py lists `/tmp` as an
    allowed root unconditionally, and CI's `tmp_path` lives under
    /tmp/pytest-of-runner, so on every Linux leg the directory this case called
    "elsewhere" really WAS inside a root and the route answered 200. It passed on
    macOS only because pytest puts its basetemp in /var/folders there — the assertion
    was measuring the runner, not the boundary. Redirecting TMPDIR could not help:
    the literal /tmp entry is unconditional.
    """
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setattr("server.routes.fs._get_allowed_roots", lambda: [allowed])

    outside = tmp_path / "elsewhere"
    outside.mkdir()
    r = client.post("/api/fs/mkdir", json={"parent": str(outside), "name": "x"})
    assert r.status_code == 403, r.text
    assert not outside.joinpath("x").exists()

    inside = client.post("/api/fs/mkdir", json={"parent": str(allowed), "name": "ok"})
    assert inside.status_code == 200, inside.text


def test_mkdir_rejects_path_traversal_and_hidden_names(client, _home):
    parent = str(_home / "Desktop")
    for bad in ("../escape", "a/b", "a\\b", "..", ".", ".hidden", ""):
        r = client.post("/api/fs/mkdir", json={"parent": parent, "name": bad})
        assert r.status_code == 422, bad
    assert not (_home / "escape").exists()
    assert not (_home / "Desktop" / ".hidden").exists()


def test_mkdir_rejects_when_parent_is_a_file(client, _home):
    f = _home / "Desktop" / "file.txt"
    f.write_text("x", encoding="utf-8")
    r = client.post("/api/fs/mkdir", json={"parent": str(f), "name": "y"})
    assert r.status_code in (403, 404, 409)
