"""PERF-BE-FIX 3 — `GET /api/sessions` reads the registry once and counts each
transcript once, not once per list row.

With 45 registered sessions the endpoint read the registry 92 times (12.5 KB each,
~1.15 MB) because `session_info` looked the row up again per row and the active-id
question read the registry again; every transcript was then parsed in full to count
its messages. Measured: 137 file opens, p50 28 ms in `/tmp/rel/PERF-BE-REPORT.md`
§3.2.

Two changes are pinned here: the one registry read is passed to both the stats and
the rows, and a message count is derived from a cached `(mtime, size)` read of the
transcript, so a second list is answered without parsing the transcripts again. The
response keeps its exact shape.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_ROW_KEYS = {
    "id",
    "title",
    "created_at",
    "last_active",
    "message_count",
    "namespace",
}


@pytest.fixture()
def client():
    from server.main import create_app

    return TestClient(create_app())


def _sessions(count: int) -> list[str]:
    import core.multi_session as ms

    ids = []
    for index in range(count):
        entry = ms.create_session(f"probe {index}")
        ms.save_messages(
            str(entry["id"]),
            [{"role": "user", "content": f"turn {n}"} for n in range(index + 1)],
        )
        ids.append(str(entry["id"]))
    return ids


def _counted(monkeypatch) -> Counter:
    import core.multi_session as ms
    import core.session_lifecycle as life

    calls: Counter = Counter()
    for module, name, key in [
        (life, "read_registry", "read_registry"),
        (ms, "_load_registry", "_load_registry"),
        (ms, "load_messages", "load_messages"),
    ]:
        real = getattr(module, name)

        def counted(*args, __real=real, __key=key, **kwargs):
            calls[__key] += 1
            return __real(*args, **kwargs)

        monkeypatch.setattr(module, name, counted)
    return calls


def test_one_list_reads_the_registry_once(client, monkeypatch):
    """GIVEN five registered sessions WHEN the list answers THEN every row is served
    from one registry read, and the per-row registry lookup is gone."""
    ids = _sessions(5)
    calls = _counted(monkeypatch)

    response = client.get("/api/sessions")

    assert response.status_code == 200
    body = response.json()
    assert {row["id"] for row in body["sessions"]} == set(ids)
    assert calls["read_registry"] == 1, (
        f"the list read the registry {calls['read_registry']} times"
    )
    assert calls["_load_registry"] == 0, (
        f"a row looked itself up again {calls['_load_registry']} times"
    )
    assert calls["load_messages"] == 5


def test_a_second_list_reuses_the_message_counts(client, monkeypatch):
    """GIVEN a served list WHEN the store has not changed THEN the next list parses no
    transcript and answers the same rows."""
    _sessions(5)
    first = client.get("/api/sessions")
    assert first.status_code == 200

    calls = _counted(monkeypatch)
    second = client.get("/api/sessions")

    assert second.status_code == 200
    assert calls["load_messages"] == 0, (
        f"an unchanged transcript was parsed {calls['load_messages']} times"
    )
    assert second.content == first.content


def test_a_written_transcript_moves_its_count(client, monkeypatch):
    """GIVEN a cached count WHEN the transcript is written THEN the next list reads it
    again and reports the new count."""
    from core import multi_session as ms

    ids = _sessions(3)
    sid = ids[0]
    assert client.get("/api/sessions").status_code == 200

    ms.save_messages(
        sid, [{"role": "user", "content": f"extra {n}"} for n in range(7)]
    )
    calls = _counted(monkeypatch)
    rows = client.get("/api/sessions").json()["sessions"]

    assert calls["load_messages"] == 1, "the write did not retire one cached count"
    row = next(item for item in rows if item["id"] == sid)
    assert row["message_count"] == 7


def test_the_list_keeps_its_shape(client):
    """GIVEN a registered session WHEN the list answers THEN the stats block and every
    row carry the fields the surfaces read."""
    _sessions(1)
    body = client.get("/api/sessions").json()

    assert {"session_dir", "total", "bytes", "by_namespace", "sessions"} <= set(body)
    assert set(body["sessions"][0]) == _ROW_KEYS
