"""Re-embedding: the chunks written before a model fetch get the new vectors too.

A finished download changes the model, not the store. The ranking leg selects on
`chunks.embedding_model`, so without this pass a fresh model covers every new note
and none of the old ones — and the coverage line would keep saying so. The pass is
idempotent and resumable because it selects only the rows whose label differs and
commits each batch.

No ONNX graph runs here: the small fake embedder replaces the factory, which is
the same seam the search uses.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest


def _model_dir(cfg: Path) -> Path:
    """A present model directory; file presence is all `model_status()` reads."""
    root = cfg / "models" / "embeddinggemma-2"
    (root / "onnx").mkdir(parents=True)
    (root / "tokenizer.json").write_text("{}")
    (root / "onnx" / "model_fp16.onnx").write_bytes(b"\x08\x01")
    return root


def _fake_embedder(texts: list[str]) -> list[list[float]]:
    return [[1.0, 0.0, 0.0] for _ in texts]


def _seed(tmp_path, monkeypatch, texts: list[str]) -> tuple[str, Path, dict]:
    """A Kepta store in the workspace scope the memory routes open, without vectors."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "mem"))
    monkeypatch.delenv("EPHE_MEMORY_EMBEDDER", raising=False)
    _model_dir(tmp_path / "cfg")
    from core.engine_config import workspace_hash
    from core.memory_kepta import KeptaProvider
    from core.memory_provider import kepta_db_path

    scope = workspace_hash()
    path = kepta_db_path(scope, str(tmp_path / "mem"))
    provider = KeptaProvider(db_path=str(path), scope=scope, embedder=None)
    for text in texts:
        provider.store(text)
    stats = provider.stats()
    provider.close()
    return scope, path, stats


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch, tmp_path):
    from core import memory_reembed

    memory_reembed.reset_state()
    monkeypatch.setattr("core.memory_embed.get_embedder", lambda: _fake_embedder)
    monkeypatch.setattr("core.memory_embed.model_name", lambda: "fake-embedder")
    yield
    deadline = time.monotonic() + 2.0
    while memory_reembed.status()["running"] and time.monotonic() < deadline:
        time.sleep(0.01)
    memory_reembed.reset_state()
    from core.memory import Memory
    from server.routes.memory import _get_memory

    _get_memory.cache_clear()
    Memory.reset_scoped_instances()


def _client():
    from fastapi.testclient import TestClient
    from server.main import create_app

    client = TestClient(create_app())
    client.headers.update({"X-Requested-With": "XMLHttpRequest"})
    return client


def _wait(client, predicate, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    seen: dict = {}
    while time.monotonic() < deadline:
        seen = client.get("/api/models/embedding").json()
        if predicate(seen):
            return seen
        time.sleep(0.02)
    raise AssertionError(f"status never matched: {seen}")


class TestProviderReembed:
    def test_every_chunk_gets_the_active_label(self, tmp_path) -> None:
        from core.memory_kepta import KeptaProvider

        provider = KeptaProvider(db_path=str(tmp_path / "s.db"), scope="s", embedder=None)
        provider.store("The projector in the meeting room has a broken HDMI cable.")
        provider.store("The launch is on Friday. The room is booked.")
        before = provider.stats()
        assert before["chunks"] > 0
        assert before["chunks_embedded"] == 0

        progress: list[tuple[int, int]] = []
        result = provider.reembed_missing(
            _fake_embedder, "fake-embedder", batch_size=1, on_progress=lambda d, t: progress.append((d, t))
        )
        assert result == {"total": before["chunks"], "embedded": before["chunks"], "label": "fake-embedder"}
        assert progress[0] == (0, before["chunks"])
        assert progress[-1] == (before["chunks"], before["chunks"])
        assert provider.stats()["chunks_embedded"] == before["chunks"]
        provider.close()

    def test_a_second_pass_finds_nothing_to_do(self, tmp_path) -> None:
        from core.memory_kepta import KeptaProvider

        provider = KeptaProvider(db_path=str(tmp_path / "s.db"), scope="s", embedder=None)
        provider.store("One fact.")
        provider.reembed_missing(_fake_embedder, "fake-embedder")
        assert provider.reembed_missing(_fake_embedder, "fake-embedder") == {
            "total": 0,
            "embedded": 0,
            "label": "fake-embedder",
        }
        provider.close()

    def test_a_failed_batch_leaves_the_done_batches_and_the_next_run_resumes(self, tmp_path) -> None:
        from core.memory_kepta import KeptaProvider

        provider = KeptaProvider(db_path=str(tmp_path / "s.db"), scope="s", embedder=None)
        for text in ("First fact.", "Second fact.", "Third fact."):
            provider.store(text)
        total = provider.stats()["chunks"]
        calls: list[int] = []

        def flaky(texts: list[str]) -> list[list[float]]:
            calls.append(len(texts))
            if len(calls) == 2:
                raise RuntimeError("the embedder died")
            return _fake_embedder(texts)

        with pytest.raises(RuntimeError):
            provider.reembed_missing(flaky, "fake-embedder", batch_size=1)
        covered = provider.stats()["chunks_embedded"]
        assert 0 < covered < total

        result = provider.reembed_missing(_fake_embedder, "fake-embedder", batch_size=1)
        assert result["total"] == total - covered, "the finished batches must not be embedded twice"
        assert provider.stats()["chunks_embedded"] == total
        provider.close()


class TestMemoryFacade:
    def test_the_facade_uses_the_label_the_search_filters_on(self, tmp_path, monkeypatch) -> None:
        _seed(tmp_path, monkeypatch, ["The swap file lives on the external disk."])
        from core.memory import Memory

        result = Memory(persist_dir=str(tmp_path / "mem")).reembed_missing()
        assert result["label"] == "fake-embedder"
        assert result["embedded"] == result["total"] > 0
        assert Memory(persist_dir=str(tmp_path / "mem")).provider_stats()["chunks_embedded"] == result["total"]


class TestReembedRoute:
    def test_the_status_carries_the_default_counters(self, tmp_path, monkeypatch) -> None:
        _seed(tmp_path, monkeypatch, ["A fact."])
        with _client() as client:
            body = client.get("/api/models/embedding").json()
        assert body["reembed"] == {
            "running": False,
            "done": False,
            "total": 0,
            "embedded": 0,
            "remaining": 0,
            "label": "",
            "error": "",
            "started_at": 0.0,
            "finished_at": 0.0,
        }

    def test_the_route_needs_the_marker_and_the_word(self, tmp_path, monkeypatch) -> None:
        _seed(tmp_path, monkeypatch, ["A fact."])
        from fastapi.testclient import TestClient
        from server.main import create_app

        with TestClient(create_app()) as client:
            assert client.post("/api/models/embedding/reembed", json={"confirm": "reembed"}).status_code == 403
            client.headers.update({"X-Requested-With": "XMLHttpRequest"})
            assert client.post("/api/models/embedding/reembed", json={}).status_code == 400

    def test_a_missing_model_is_refused_before_a_pass_starts(self, tmp_path, monkeypatch) -> None:
        _seed(tmp_path, monkeypatch, ["A fact."])
        from core import memory_embed_gemma

        monkeypatch.setattr(memory_embed_gemma, "model_present", lambda: False)
        with _client() as client:
            answer = client.post("/api/models/embedding/reembed", json={"confirm": "reembed"})
        assert answer.status_code == 409
        assert "model_missing" in answer.text

    def test_the_route_reembeds_the_store_and_reports_progress(self, tmp_path, monkeypatch) -> None:
        _scope, _path, before = _seed(
            tmp_path,
            monkeypatch,
            [
                "Der API-Gateway läuft auf Port 8765.",
                "The projector needs a new HDMI cable.",
                "The launch is on Friday.",
            ],
        )
        assert before["chunks"] > 0
        with _client() as client:
            started = client.post("/api/models/embedding/reembed", json={"confirm": "reembed"}).json()
            assert started["started"] is True and started["reembed"]["running"] is True
            status = _wait(client, lambda body: body["reembed"]["done"])
            assert status["reembed"]["embedded"] == status["reembed"]["total"] == before["chunks"]

            stats = client.get("/api/memory/stats").json()
            assert stats["chunks_embedded"] == stats["chunks"] == before["chunks"]

            again = client.post("/api/models/embedding/reembed", json={"confirm": "reembed"}).json()
            assert again["started"] is True
            second = _wait(client, lambda body: body["reembed"]["done"])
            assert second["reembed"]["total"] == 0, "a finished store must cost one count query"


class TestBackground:
    def test_the_pass_does_not_hold_the_caller(self) -> None:
        from core import memory_reembed

        started = threading.Event()
        release = threading.Event()

        def runner(_memory):
            started.set()
            release.wait(2.0)
            return {"total": 1, "embedded": 1, "label": "fake-embedder"}

        assert memory_reembed.start(memory_factory=lambda: object(), runner=runner) is True
        assert started.wait(2.0)
        assert memory_reembed.status()["running"] is True
        assert memory_reembed.start(memory_factory=lambda: object(), runner=runner) is False
        release.set()

        deadline = time.monotonic() + 2.0
        while memory_reembed.status()["running"] and time.monotonic() < deadline:
            time.sleep(0.01)
        state = memory_reembed.status()
        assert state["done"] is True and state["embedded"] == 1 and state["remaining"] == 0

    def test_a_failure_becomes_a_reason_in_the_status(self) -> None:
        from core import memory_reembed

        def runner(_memory):
            raise RuntimeError("the embedder returned no vectors")

        assert memory_reembed.start(memory_factory=lambda: object(), runner=runner) is True
        deadline = time.monotonic() + 2.0
        while memory_reembed.status()["running"] and time.monotonic() < deadline:
            time.sleep(0.01)
        state = memory_reembed.status()
        assert state["done"] is False
        assert state["error"] == "the embedder returned no vectors"
