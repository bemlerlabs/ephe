"""A fresh install starts with nothing fetched, and the feature that needs a model asks first.

The class this pins (first-start probe, 2026-10-15): `ephe start` on a fresh checkout with a
throwaway HOME logged

    INFO:httpx2:HTTP Request: GET https://huggingface.co/api/resolve-cache/models/Systran/...
    INFO:core.transcribe:Whisper model loaded.

— a transcription model fetched from a third-party host with no prompt and no setting
consulted, from the server lifespan's warmup. It contradicts the README in three sentences at
once ("local-first", "no account requirement", "optional online features are always opt-in")
and AGENTS.md's no-silent-default rule.

Four assertions, in the shape the defect was found in:
  * the start path loads a model only when it is already on disk — an uncached one is left
    alone, so no request to a model host can come out of `lifespan`;
  * a first transcription with no consent refuses with the model, the host and the size named,
    plus the two ways to allow it (never a silent download, never an obscure failure);
  * consent turns the fetch on, and it happens on the feature's call, not the process's;
  * `EPHE_OFFLINE=1` outranks consent and the rest of the product still starts.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

MODEL = "tiny"
REPO = "Systran/faster-whisper-tiny"
HOST = "huggingface.co"


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """A HOME-less, cache-less install: no config dir, no model cache, no consent."""
    import core.engine_config as ec

    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    # CONFIG_DIR is bound at import; the env alone would leave the constant on the
    # real ~/.ephe (the same seam tests/conftest.empty_ephe_home patches).
    monkeypatch.setattr(ec, "CONFIG_DIR", cfg, raising=False)
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    monkeypatch.setenv("EPHE_AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    for name in ("EPHE_STT_DOWNLOAD", "EPHE_OFFLINE"):
        monkeypatch.delenv(name, raising=False)
    os.environ.pop("EPHE_SETUP_MODE", None)
    return tmp_path


@pytest.fixture()
def no_cache(monkeypatch):
    """Every model counts as absent — the state a fresh install is in."""
    import core.transcribe as tr

    monkeypatch.setattr(tr, "model_is_cached", lambda _name: False)
    monkeypatch.setattr(tr, "_models", {})
    return tr


class _BuildRecorder:
    """Stands in for the WhisperModel constructor; records whether a fetch was allowed."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def __call__(self, model_name, *, fetch: bool):
        self.calls.append((model_name, fetch))
        return object()


# 1. The start path

def test_the_start_warmup_never_builds_a_model_when_it_is_not_cached(isolated, no_cache, monkeypatch):
    """`warm_if_cached` is the start's only STT call, and it cannot reach out."""
    def explode(*args, **kwargs):  # pragma: no cover - the assertion is that it never runs
        raise AssertionError("the start path tried to build a model")

    monkeypatch.setattr(no_cache, "_load", explode)
    assert no_cache.warm_if_cached() is False


def test_the_lifespan_calls_the_cached_only_warmup_and_not_the_loading_one(isolated, monkeypatch):
    """The regression itself: `lifespan` must not call `_get_model()`.

    `_get_model()` on an uncached model is the download. The lifespan's warmup
    has to be the cached-only entry point.
    """
    import time

    import core.transcribe as tr

    seen: list[str] = []
    monkeypatch.setattr(tr, "warm_if_cached", lambda: seen.append("warm_if_cached") or False)
    monkeypatch.setattr(tr, "_get_model", lambda *a, **k: seen.append("_get_model"))

    from server.main import create_app

    with TestClient(create_app()):
        # The lifespan starts the warmup as a task, so give that task its turn.
        deadline = time.monotonic() + 5.0
        while not seen and time.monotonic() < deadline:
            time.sleep(0.02)

    assert "warm_if_cached" in seen, "the lifespan no longer warms the cache-only path"
    assert "_get_model" not in seen, "the lifespan calls the loader again — that is the download"


# 2. The first use asks

def test_an_uncached_model_with_no_consent_is_refused_with_the_facts(isolated, no_cache):
    with pytest.raises(no_cache.STTModelNotAvailable) as excinfo:
        no_cache._get_model()

    exc = excinfo.value
    assert (exc.model, exc.repo, exc.host) == (MODEL, REPO, HOST)
    assert exc.size_mb > 0, "the reader is told the size before a byte moves"
    assert exc.reason == "not_opted_in"
    message = str(exc)
    assert MODEL in message and HOST in message
    assert f"{exc.size_mb}" in message
    assert "EPHE_STT_DOWNLOAD=1" in message
    assert "stt_allow_download" in message


def test_consent_is_not_read_from_the_environment_alone(isolated, no_cache):
    """Without either source the answer stays refused — there is no silent default."""
    assert no_cache.stt_download_allowed() is False
    with pytest.raises(no_cache.STTModelNotAvailable):
        no_cache._get_model()


# 3. Consent, and only then

def test_env_consent_lets_the_feature_fetch(isolated, no_cache, monkeypatch):
    recorder = _BuildRecorder()
    monkeypatch.setattr(no_cache, "_load", recorder)
    monkeypatch.setenv("EPHE_STT_DOWNLOAD", "1")

    no_cache._get_model()

    assert recorder.calls == [(MODEL, True)], "consent did not reach the loader"


def test_the_setting_consent_lets_the_feature_fetch(isolated, no_cache, monkeypatch):
    from core.voice_config import save_voice_config

    recorder = _BuildRecorder()
    monkeypatch.setattr(no_cache, "_load", recorder)
    save_voice_config(stt_allow_download=True)

    assert no_cache.stt_download_allowed() is True
    no_cache._get_model()
    assert recorder.calls == [(MODEL, True)]


def test_a_cached_model_loads_with_local_files_only(isolated, monkeypatch):
    import core.transcribe as tr

    recorder = _BuildRecorder()
    monkeypatch.setattr(tr, "_models", {})
    monkeypatch.setattr(tr, "model_is_cached", lambda _name: True)
    monkeypatch.setattr(tr, "_load", recorder)

    tr._get_model()

    assert recorder.calls == [(MODEL, False)], "a cached model was loaded for a fetch"


# 4. Offline outranks everything, and the product still starts

def test_offline_refuses_even_when_consent_was_given(isolated, no_cache, monkeypatch):
    monkeypatch.setenv("EPHE_STT_DOWNLOAD", "1")
    monkeypatch.setenv("EPHE_OFFLINE", "1")

    with pytest.raises(no_cache.STTModelNotAvailable) as excinfo:
        no_cache._get_model()

    assert excinfo.value.reason == "offline"
    assert "EPHE_OFFLINE" in str(excinfo.value)


def test_the_rest_of_the_product_starts_offline(isolated, no_cache, monkeypatch):
    """No model host reachable, no model on disk: the server comes up regardless."""
    monkeypatch.setenv("EPHE_OFFLINE", "1")

    from server.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/api/health").status_code == 200


# 5. The route reports what it needs instead of failing obscurely

def test_the_transcribe_route_answers_with_a_coded_refusal(isolated, monkeypatch):
    import core.transcribe as tr

    async def _refuse(_path):
        raise tr.STTModelNotAvailable(MODEL)

    monkeypatch.setattr(tr, "is_whisper_available", lambda: True)
    monkeypatch.setattr(tr, "transcribe", _refuse)

    from server.main import create_app

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/audio/transcribe",
            files={"file": ("note.webm", b"RIFF....WAVEfmt ", "audio/webm")},
        )

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["reason_code"] == "audio_model_download_required"
    assert error["reason_params"]["model"] == MODEL
    assert error["reason_params"]["host"] == HOST
    assert error["reason_params"]["size_mb"] > 0
    assert "EPHE_STT_DOWNLOAD=1" in error["message"]


def test_a_failed_fetch_asks_again_and_names_the_connection(isolated, no_cache, monkeypatch):
    """Consent given and the host unreachable: the feature reports the connection."""
    def unreachable(*args, **kwargs):
        raise ConnectionRefusedError("no route to the model host")

    monkeypatch.setattr(no_cache, "_load", unreachable)
    monkeypatch.setenv("EPHE_STT_DOWNLOAD", "1")

    with pytest.raises(no_cache.STTModelNotAvailable) as excinfo:
        no_cache._get_model()

    exc = excinfo.value
    assert exc.reason == "fetch_failed"
    assert MODEL in str(exc) and HOST in str(exc)
    assert "connection" in str(exc)


def test_the_route_answers_a_failed_fetch_with_its_own_code(isolated, monkeypatch):
    import core.transcribe as tr

    async def _refuse(_path):
        raise tr.STTModelNotAvailable(MODEL, reason="fetch_failed")

    monkeypatch.setattr(tr, "is_whisper_available", lambda: True)
    monkeypatch.setattr(tr, "transcribe", _refuse)

    from server.main import create_app

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/audio/transcribe",
            files={"file": ("note.webm", b"RIFF....WAVEfmt ", "audio/webm")},
        )

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["reason_code"] == "audio_model_fetch_failed"
    assert "connection" in error["message"]


def test_the_voice_settings_expose_the_consent_and_the_cache_state(isolated):
    from server.main import create_app

    with TestClient(create_app()) as client:
        body = client.get("/api/settings/voice").json()
        assert body["stt_allow_download"] is False
        assert body["stt_model_cached"] is False

        updated = client.put("/api/settings/voice", json={"stt_allow_download": True}).json()
        assert updated["stt_allow_download"] is True
