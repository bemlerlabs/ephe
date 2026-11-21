"""WG-48: the artifact lifecycle over the shipped HTTP API.

A real chat turn births an artifact: the real agent loop runs the real
``create_svg`` tool, which writes the file into the workbench and registers it
in the library. That artifact is then listed, read back by id, and deleted with
``DELETE /api/artifacts/{id}?delete_file=true`` — the row and the bytes both go.

Only the engine client is faked. The engine fake and the turn helper live in
``test_e2e_install_chat_tool_artifact`` and are imported here, so the wave keeps
a single engine fake instead of a second copy.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.e2e.test_e2e_install_chat_tool_artifact import (  # noqa: F401
    ARTIFACT_FILENAME,
    SESSION_ID,
    _first,
    _run_turn,
    client,
)

# The turn flips the shipped approval profile, which does not survive parallel
# workers — the same serial-leg reason the helper module carries.
pytestmark = pytest.mark.skipif(
    bool(os.environ.get("PYTEST_XDIST_WORKER")),
    reason="serial leg only: drives the shipped approval profile",
)


def _birth_artifact(http_client) -> dict:
    """One real turn; the ``file_result`` event of the registered svg."""
    events = _run_turn(http_client)
    born = _first(events, type="file_result", file_type="svg")
    assert born is not None, f"the turn registered no artifact: {events}"
    assert born.get("id"), f"file_result carries no artifact id: {born}"
    return born


def test_artifact_lifecycle_create_list_detail_delete(client):
    born = _birth_artifact(client)
    artifact_id = born["id"]
    on_disk = Path(born["path"])
    assert on_disk.is_file(), f"create registered {on_disk}, nothing on disk"

    listed = client.get("/api/artifacts", params={"session_id": SESSION_ID}).json()
    assert [a["id"] for a in listed["artifacts"]] == [artifact_id], listed
    assert listed["total"] == 1

    detail = client.get(f"/api/artifacts/{artifact_id}")
    assert detail.status_code == 200
    card = detail.json()
    assert card["id"] == artifact_id
    assert card["kind"] == "svg"
    assert card["name"] == ARTIFACT_FILENAME
    assert card["session_id"] == SESSION_ID

    gone = client.delete(f"/api/artifacts/{artifact_id}", params={"delete_file": True})
    assert gone.status_code == 200
    assert gone.json() == {"deleted": artifact_id, "file_removed": True}
    assert not on_disk.exists(), "delete_file removed the row but left the bytes"

    assert client.get(f"/api/artifacts/{artifact_id}").status_code == 404
    after = client.get("/api/artifacts", params={"session_id": SESSION_ID}).json()
    assert after == {"artifacts": [], "total": 0}, after


def test_delete_without_the_file_flag_keeps_the_bytes(client, tmp_path):
    """delete_file defaults to False: the row goes, the user's file stays."""
    from core import artifact_store

    kept = tmp_path / "kept.pdf"
    kept.write_bytes(b"kept bytes")
    row = artifact_store.register_artifact(path=str(kept), kind="pdf", session_id=SESSION_ID)
    assert row is not None

    gone = client.delete(f"/api/artifacts/{row['id']}")
    assert gone.status_code == 200
    assert gone.json() == {"deleted": row["id"], "file_removed": False}
    assert kept.is_file(), "the conservative default deleted the user's file"
    assert client.get(f"/api/artifacts/{row['id']}").status_code == 404


def test_delete_unknown_artifact_is_404(client):
    assert client.delete("/api/artifacts/does-not-exist").status_code == 404
