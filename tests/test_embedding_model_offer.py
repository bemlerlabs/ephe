"""The embedding model is offered, never fetched on its own.

The install ships without the 542 MB weights; a first start must not pull them. The
memory degrades to the lexical leg, `/api/models/embedding` says why, and the fetch
happens only because a person pressed a button — one click, no setting written.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest


def _home(tmp_path: Path, monkeypatch, *, with_weights: bool) -> Path:
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    model = tmp_path / "cfg" / "models" / "embeddinggemma-2" / "onnx"
    model.mkdir(parents=True)
    (tmp_path / "cfg" / "models" / "embeddinggemma-2" / "tokenizer.json").write_text("{}")
    # A graph that names an external weight file, exactly like the shipped export.
    (model / "model_fp16.onnx").write_bytes(b'\x08\x01"\x1amodel_fp16.onnx_data')
    if with_weights:
        (model / "model_fp16.onnx_data").write_bytes(b"weights")
    return tmp_path / "cfg"


def _client(monkeypatch):
    from fastapi.testclient import TestClient
    from server.main import create_app

    test_client = TestClient(create_app())
    test_client.headers.update({"X-Requested-With": "XMLHttpRequest"})
    return test_client


def test_a_graph_without_its_weights_is_not_present(tmp_path, monkeypatch) -> None:
    """The half-fetched directory is the defect: graph there, weights missing."""
    _home(tmp_path, monkeypatch, with_weights=False)
    from core import memory_embed_gemma

    assert memory_embed_gemma.model_present() is False
    assert memory_embed_gemma.missing_files() == ["onnx/model_fp16.onnx_data"]


def test_a_complete_directory_is_present(tmp_path, monkeypatch) -> None:
    _home(tmp_path, monkeypatch, with_weights=True)
    from core import memory_embed_gemma

    assert memory_embed_gemma.model_present() is True


def test_the_status_offers_the_fetch_without_starting_it(tmp_path, monkeypatch) -> None:
    _home(tmp_path, monkeypatch, with_weights=False)
    monkeypatch.setattr(
        "core.memory_embed_gemma.ensure_model",
        lambda: pytest.fail("the status must not fetch"),
    )
    with _client(monkeypatch) as client:
        body = client.get("/api/models/embedding").json()
    assert body["present"] is False
    assert body["missing"] == ["onnx/model_fp16.onnx_data"]
    assert body["size_mb"] > 0
    assert body["downloading"] is False
    assert body["consent"] is False


def _wait_for(client, predicate, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    seen: dict = {}
    while time.monotonic() < deadline:
        seen = client.get("/api/models/embedding").json()
        if predicate(seen):
            return seen
        time.sleep(0.02)
    raise AssertionError(f"status never matched: {seen}")


def test_a_click_fetches_the_weights_and_writes_no_consent(tmp_path, monkeypatch) -> None:
    """The button has to start the fetch the backend actually performs.

    The old test replaced `ensure_model` itself, so the consent gate inside it was
    never reached and a click that fetched nothing still looked green.
    """
    _home(tmp_path, monkeypatch, with_weights=False)
    started = threading.Event()
    fetched: list[str] = []

    def fake_fetch(repo_id: str, target: Path, allow_patterns: tuple[str, ...]) -> None:
        fetched.append(repo_id)
        (target / "onnx" / "model_fp16.onnx_data").write_bytes(b"weights")
        started.set()

    monkeypatch.setattr("core.memory_embed_gemma._fetch", fake_fetch)
    reset: list[int] = []
    rebound: list[int] = []
    monkeypatch.setattr("core.memory_embed.reset_cache", lambda: reset.append(1))
    from core.memory import Memory

    monkeypatch.setattr(
        Memory, "reset_scoped_instances", classmethod(lambda cls: rebound.append(1))
    )
    from server.routes.memory import _get_memory

    _get_memory()  # populate the route cache; the fetch has to clear it
    with _client(monkeypatch) as client:
        answer = client.post("/api/models/embedding/download", json={"confirm": "download"})
        assert answer.status_code == 200
        assert answer.json()["started"] is True
        assert started.wait(2.0)
        body = _wait_for(client, lambda status: status["downloaded"])

    from core import memory_embed_gemma

    assert fetched, "the click must reach the fetch, not stop at the consent gate"
    assert body["present"] is True
    assert body["error"] == ""
    assert reset and rebound, "a finished fetch has to hand the running process the new model"
    assert _get_memory.cache_info().currsize == 0, "the route cache must not keep the stale facade"
    assert memory_embed_gemma.download_consent() is False, "a click is not a standing opt-in"


def test_ensure_model_without_consent_names_the_reason(tmp_path, monkeypatch) -> None:
    _home(tmp_path, monkeypatch, with_weights=False)
    from core import memory_embed_gemma

    with pytest.raises(memory_embed_gemma.EmbeddingGemmaNotAvailable) as refused:
        memory_embed_gemma.ensure_model()
    text = str(refused.value)
    assert "no consent given" in text
    assert "EmbeddingGemmaNotAvailable" not in text


def test_one_click_may_fetch_once_without_writing_the_setting(tmp_path, monkeypatch) -> None:
    _home(tmp_path, monkeypatch, with_weights=False)
    fetched: list[Path] = []

    def fake_fetch(repo_id: str, target: Path, allow_patterns: tuple[str, ...]) -> None:
        fetched.append(target)
        (target / "onnx" / "model_fp16.onnx_data").write_bytes(b"weights")

    monkeypatch.setattr("core.memory_embed_gemma._fetch", fake_fetch)
    from core import memory_embed_gemma

    memory_embed_gemma.ensure_model(allow_fetch=True)
    assert fetched and memory_embed_gemma.model_present() is True
    assert memory_embed_gemma.download_consent() is False


def test_a_failed_fetch_reports_its_reason_not_its_class(tmp_path, monkeypatch) -> None:
    _home(tmp_path, monkeypatch, with_weights=False)

    def refusing_fetch(repo_id: str, target: Path, allow_patterns: tuple[str, ...]) -> None:
        raise RuntimeError("the hub answered 503")

    monkeypatch.setattr("core.memory_embed_gemma._fetch", refusing_fetch)
    with _client(monkeypatch) as client:
        client.post("/api/models/embedding/download", json={"confirm": "download"})
        body = _wait_for(client, lambda status: bool(status["error"]) and not status["downloading"])

    assert body["error"] != "RuntimeError"
    assert "the hub answered 503" in body["error"]


def test_a_click_after_a_failure_tries_again(tmp_path, monkeypatch) -> None:
    _home(tmp_path, monkeypatch, with_weights=False)
    attempts: list[int] = []

    def first_fails(repo_id: str, target: Path, allow_patterns: tuple[str, ...]) -> None:
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("the hub answered 503")
        (target / "onnx" / "model_fp16.onnx_data").write_bytes(b"weights")

    monkeypatch.setattr("core.memory_embed_gemma._fetch", first_fails)
    with _client(monkeypatch) as client:
        client.post("/api/models/embedding/download", json={"confirm": "download"})
        failed = _wait_for(
            client, lambda status: bool(status["error"]) and not status["downloading"]
        )
        assert "503" in failed["error"]
        again = client.post("/api/models/embedding/download", json={"confirm": "download"})
        assert again.status_code == 200
        body = _wait_for(client, lambda status: status["downloaded"])
    assert len(attempts) == 2
    assert body["error"] == ""


def test_the_fetch_needs_the_marker_and_the_word(tmp_path, monkeypatch) -> None:
    _home(tmp_path, monkeypatch, with_weights=False)
    from fastapi.testclient import TestClient
    from server.main import create_app

    app = create_app()
    with TestClient(app) as client:
        assert client.post("/api/models/embedding/download", json={"confirm": "download"}).status_code == 403
        client.headers.update({"X-Requested-With": "XMLHttpRequest"})
        assert client.post("/api/models/embedding/download", json={}).status_code == 400


def test_an_offline_process_refuses_to_fetch(tmp_path, monkeypatch) -> None:
    _home(tmp_path, monkeypatch, with_weights=False)
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    with _client(monkeypatch) as client:
        answer = client.post("/api/models/embedding/download", json={"confirm": "download"})
    assert answer.status_code == 409
    body = answer.json()
    assert "offline" in json.dumps(body), body
