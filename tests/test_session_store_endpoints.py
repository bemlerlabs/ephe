"""The server-authoritative session store: create, read, rename, activate, write-through.

The store decision is in `docs/SESSION_STORE_DECISION.md`; these tests pin the
0.1.0 behavior the surfaces share.
"""
from __future__ import annotations

import stat

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    import os

    os.environ["EPHE_CONFIG_DIR"] = str(tmp_path)
    from server.main import create_app

    return TestClient(create_app())


def _create(client: TestClient, title: str = "Store proof") -> dict:
    response = client.post("/api/sessions", json={"title": title})
    assert response.status_code == 200, response.text
    return response.json()


class TestSessionStoreRoutes:
    def test_create_list_read_rename_activate(self, client: TestClient) -> None:
        created = _create(client)
        sid = created["id"]
        assert created["title"] == "Store proof"
        assert created["message_count"] == 0
        assert created["namespace"] == "user"

        listed = client.get("/api/sessions").json()["sessions"]
        row = next(item for item in listed if item["id"] == sid)
        assert row["title"] == "Store proof"
        assert row["message_count"] == 0
        assert row["namespace"] == "user"

        read = client.get(f"/api/sessions/{sid}")
        assert read.status_code == 200, read.text
        assert read.json()["messages"] == []

        renamed = client.patch(f"/api/sessions/{sid}", json={"title": "Renamed"})
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["title"] == "Renamed"
        assert client.get(f"/api/sessions/{sid}").json()["title"] == "Renamed"

        activated = client.post(f"/api/sessions/{sid}/activate")
        assert activated.status_code == 200, activated.text
        assert activated.json()["active_id"] == sid

    def test_invalid_and_unknown_ids_are_refused(self, client: TestClient) -> None:
        assert client.get("/api/sessions/bad.id").status_code == 400
        assert client.get("/api/sessions/does-not-exist").status_code == 404
        assert client.patch("/api/sessions/does-not-exist", json={"title": "x"}).status_code == 404
        assert client.post("/api/sessions/does-not-exist/activate").status_code == 404
        assert client.patch("/api/sessions/bad.id", json={"title": "x"}).status_code == 400

    def test_a_registered_turn_writes_through_no_rest_copy(self, client: TestClient) -> None:
        from core import multi_session as ms
        from server.routes.chat import _load_rest_history, _persist_rest_turn

        sid = _create(client, "Turn proof")["id"]
        _persist_rest_turn(sid, "hello", "hi there")

        own = ms.SESSIONS_DIR / f"{sid}.json"
        assert own.exists()
        assert not (ms.SESSIONS_DIR / f"rest-{sid}.json").exists()
        messages = client.get(f"/api/sessions/{sid}").json()["messages"]
        assert [m["content"] for m in messages] == ["hello", "hi there"]
        assert _load_rest_history(sid) == messages

    def test_unknown_ids_keep_the_rest_mirror(self, client: TestClient) -> None:
        from core import multi_session as ms
        from server.routes.chat import _persist_rest_turn

        _persist_rest_turn("caller-1", "hello", "hi there")
        assert (ms.SESSIONS_DIR / "rest-caller-1.json").exists()
        assert not (ms.SESSIONS_DIR / "caller-1.json").exists()

    def test_the_transcript_keeps_the_extra_turn_fields(self, client: TestClient) -> None:
        from core import multi_session as ms

        sid = _create(client, "Rich turn")["id"]
        ms.save_messages(
            sid,
            [
                {
                    "role": "assistant",
                    "content": "answer",
                    "id": "m1",
                    "timestamp": 123.0,
                    "blocks": [{"kind": "text", "text": "answer"}],
                    "turnId": "t1",
                    "tool_calls": [{"name": "read_file", "result": "x"}],
                }
            ],
        )
        message = client.get(f"/api/sessions/{sid}").json()["messages"][0]
        assert message["id"] == "m1"
        assert message["timestamp"] == 123.0
        assert message["blocks"] == [{"kind": "text", "text": "answer"}]
        assert message["turnId"] == "t1"
        assert message["tool_calls"] == [{"name": "read_file", "result": "x"}]

    def test_store_files_are_owner_only(self, client: TestClient) -> None:
        from core import multi_session as ms

        sid = _create(client, "Private")["id"]
        ms.save_messages(sid, [{"role": "user", "content": "secret"}])
        for path in (ms.SESSIONS_DIR / f"{sid}.json", ms.REGISTRY_FILE):
            mode = stat.S_IMODE(path.stat().st_mode)
            assert mode == 0o600, f"{path}: {oct(mode)}"
