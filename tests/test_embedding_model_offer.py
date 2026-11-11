"""The embedding model is offered, never fetched on its own.

The install ships without the 542 MB weights; a first start must not pull them. The
memory degrades to the lexical leg, `/api/models/embedding` says why, and the fetch
happens only because a person pressed a button — one click, no setting written.
"""
from __future__ import annotations

import json
import threading
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


def test_a_click_starts_one_fetch_and_writes_no_consent(tmp_path, monkeypatch) -> None:
    _home(tmp_path, monkeypatch, with_weights=False)
    started = threading.Event()

    def fake_ensure() -> Path:
        started.set()
        return tmp_path

    monkeypatch.setattr("core.memory_embed_gemma.ensure_model", fake_ensure)
    with _client(monkeypatch) as client:
        answer = client.post("/api/models/embedding/download", json={"confirm": "download"})
    assert answer.status_code == 200
    assert answer.json()["started"] is True
    assert started.wait(2.0)
    from core import memory_embed_gemma

    assert memory_embed_gemma.download_consent() is False, "a click is not a standing opt-in"


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
