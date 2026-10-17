"""
tests/test_memory_store_availability.py — B1 of the 2026-10-10 persona audit.

The store and the empty store used to be the same answer: an unreachable brain
raised out of the route, the route became a 500, the PWA catch turned that into
`rows = []` and the surface printed "Nothing noted yet." about facts it could not
read. These tests keep the two answers apart where they are produced.

The unreachable case is the product's own supported configuration: the
`kepta-bridge` provider reads a Kepta instance over HTTP, so pointing it at a
closed port is the same failure a user gets when that instance is not running.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

#: Discard port — nothing listens, so the refusal is immediate and no test waits
#: on a provider timeout.
DEAD_URL = "http://127.0.0.1:9"

READS = (
    "/api/memory/list",
    "/api/memory/deleted",
    "/api/memory/search?q=port&top_k=5",
    "/api/memory/stats",
)


def _clear_memory_caches() -> None:
    from core.memory import Memory
    from server.routes.memory import _get_memory

    _get_memory.cache_clear()
    Memory.reset_scoped_instances()


@pytest.fixture
def unreachable_store(tmp_path, monkeypatch):
    """A memory read that cannot reach its brain, served by the real app."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "ephe-home"))
    monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "kepta-bridge")
    monkeypatch.setenv("EPHE_MEMORY_KEPTA_URL", DEAD_URL)
    _clear_memory_caches()
    from server.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    yield client
    _clear_memory_caches()


@pytest.fixture
def reachable_empty_store(tmp_path, monkeypatch):
    """The same reads against a store that answers and genuinely holds nothing."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "ephe-home"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma_db"))
    _clear_memory_caches()
    from server.main import create_app

    client = TestClient(create_app())
    yield client
    _clear_memory_caches()


class TestUnreachableIsNotEmpty:
    @pytest.mark.parametrize("path", READS)
    def test_every_read_answers_service_unavailable(self, unreachable_store, path):
        """503 says "not readable now"; 500 said "Ephe is broken" and let the
        client fall through to an empty list."""
        response = unreachable_store.get(path)
        assert response.status_code == 503

    @pytest.mark.parametrize("path", READS)
    def test_the_failure_carries_a_stable_availability_code(self, unreachable_store, path):
        """The envelope code is what a surface branches on — `internal_error`
        would be indistinguishable from a bug in Ephe's own code."""
        body = unreachable_store.get(path).json()
        assert body["error"]["code"] == "upstream_error"

    @pytest.mark.parametrize("path", ("/api/memory/list", "/api/memory/deleted"))
    def test_no_rows_are_sent_when_the_store_cannot_be_read(self, unreachable_store, path):
        """The invariant in one assertion: an unreachable store is not
        representable as an empty list, because the empty list is never sent."""
        body = unreachable_store.get(path).json()
        assert "entries" not in body
        assert "total" not in body

    def test_search_sends_no_results_when_the_store_cannot_be_read(self, unreachable_store):
        body = unreachable_store.get("/api/memory/search", params={"q": "port"}).json()
        assert "results" not in body

    def test_the_reason_names_the_store_that_did_not_answer(self, unreachable_store):
        """A user needs to know which brain is silent; the technical sentence
        stays English because it is machine-facing artifact prose."""
        message = unreachable_store.get("/api/memory/list").json()["error"]["message"]
        assert "kepta-bridge" in message


class TestReachableStoreKeepsItsOwnAnswers:
    @pytest.mark.parametrize("path", ("/api/memory/list", "/api/memory/deleted"))
    def test_an_empty_store_still_answers_zero_rows(self, reachable_empty_store, path):
        body = reachable_empty_store.get(path).json()
        assert body["entries"] == []
        assert body["total"] == 0

    def test_stats_still_counts_the_empty_store(self, reachable_empty_store):
        body = reachable_empty_store.get("/api/memory/stats").json()
        assert body["total"] == 0
