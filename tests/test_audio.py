"""
◑ Ephe – Audio-Feature Tests
tests/test_audio.py

TDD tests for:
  - the audio upload route (MIME, size, sanity)
  - the transcription engine (VAD, format)
  - path sandboxing
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import struct
import sys
import types
import wave
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


# Fixtures

@pytest.fixture
def audio_client(tmp_path):
    """TestClient with an isolated audio directory."""
    os.environ["EPHE_AUDIO_DIR"] = os.environ["EPHE_AUDIO_DIR"] = str(tmp_path / "audio")
    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "memory")
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")
    # Reset the lru_cache on the memory singleton for test isolation
    from server.routes.memory import _get_memory
    _get_memory.cache_clear()

    from server.main import create_app
    app = create_app()
    with TestClient(app) as client:
        yield client


def _make_wav_bytes(duration_s: float = 1.0, frequency: int = 440, amplitude: int = 5000) -> bytes:
    """Produces valid WAV bytes for tests."""
    sample_rate = 16000
    n_samples = int(sample_rate * duration_s)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(n_samples):
            import math
            sample = int(amplitude * math.sin(2 * math.pi * frequency * i / sample_rate))
            wf.writeframes(struct.pack("<h", sample))
    return buf.getvalue()


def _make_silent_wav_bytes(duration_s: float = 1.0) -> bytes:
    """A zero-amplitude WAV: duration is the only knob."""
    return _make_wav_bytes(duration_s=duration_s, amplitude=0)


# Upload route tests

class TestAudioUpload:
    """Tests for POST /api/audio/transcribe."""

    def test_GIVEN_valid_wav_WHEN_uploaded_THEN_returns_200(self, audio_client):
        """
        GIVEN  a valid WAV file
        WHEN   sent to /api/audio/transcribe
        THEN   returns 200 + audio_url
        """
        wav = _make_wav_bytes(1.0)
        # Mock whisper availability to avoid needing the model
        with patch("core.transcribe.transcribe") as mock_t, \
             patch("core.transcribe.is_whisper_available", return_value=True):
            mock_t.return_value = "Test Transkription"
            files = {"file": ("test.wav", wav, "audio/wav")}
            resp = audio_client.post("/api/audio/transcribe", files=files)

        assert resp.status_code == 200
        data = resp.json()
        assert "audio_url" in data
        assert data["audio_url"].startswith("/audio/")

    def test_GIVEN_invalid_mimetype_WHEN_uploaded_THEN_returns_422(self, audio_client):
        """
        GIVEN  a file with an invalid MIME type (text/plain)
        WHEN   sent to /api/audio/transcribe
        THEN   422 Unprocessable Entity
        """
        files = {"file": ("test.txt", b"not audio", "text/plain")}
        resp = audio_client.post("/api/audio/transcribe", files=files)
        assert resp.status_code == 422
        assert "unsupported audio type" in resp.json()["error"]["message"]

    def test_GIVEN_oversized_file_WHEN_uploaded_THEN_returns_413(self, audio_client):
        """
        GIVEN  an audio file > 15 MB
        WHEN   sent to /api/audio/transcribe
        THEN   413 Payload Too Large
        """
        big = b"\x00" * (16 * 1024 * 1024)  # 16 MB
        files = {"file": ("big.webm", big, "audio/webm")}
        resp = audio_client.post("/api/audio/transcribe", files=files)
        assert resp.status_code == 413

    def test_GIVEN_empty_file_WHEN_uploaded_THEN_returns_422(self, audio_client):
        """
        GIVEN  an empty audio file
        WHEN   sent to /api/audio/transcribe
        THEN   422
        """
        files = {"file": ("empty.webm", b"", "audio/webm")}
        resp = audio_client.post("/api/audio/transcribe", files=files)
        assert resp.status_code == 422

    def test_GIVEN_webm_audio_WHEN_uploaded_THEN_saved_as_webm(self, audio_client, tmp_path):
        """
        GIVEN  WebM audio
        WHEN   uploaded
        THEN   the file is saved as .webm
        """
        with patch("core.transcribe.transcribe") as mock_t, \
             patch("core.transcribe.is_whisper_available", return_value=True):
            mock_t.return_value = "Hallo"
            files = {"file": ("test.webm", b"\x1a\x45\xdf\xa3" * 100, "audio/webm")}
            resp = audio_client.post("/api/audio/transcribe", files=files)

        assert resp.status_code == 200
        audio_url = resp.json()["audio_url"]
        assert audio_url.endswith(".webm")

    def test_GIVEN_mp4_safari_WHEN_uploaded_THEN_accepted(self, audio_client):
        """
        GIVEN  MP4 audio (Safari)
        WHEN   uploaded
        THEN   accepted (cross-browser support)
        """
        with patch("core.transcribe.transcribe") as mock_t, \
             patch("core.transcribe.is_whisper_available", return_value=True):
            mock_t.return_value = "Safari test"
            files = {"file": ("rec.mp4", b"\x00\x00\x00" * 100, "audio/mp4")}
            resp = audio_client.post("/api/audio/transcribe", files=files)

        assert resp.status_code == 200


# Transcription engine tests

class TestTranscribeEngine:
    """Tests for core/transcribe.py."""

    def test_GIVEN_nonexistent_file_WHEN_transcribed_THEN_raises(self):
        """FileNotFoundError when the file is missing."""
        from core.transcribe import _transcribe_sync
        with pytest.raises(FileNotFoundError):
            _transcribe_sync(Path("/nonexistent/audio.wav"))

    def test_GIVEN_whisper_not_installed_WHEN_checked_THEN_false(self):
        """`ephe doctor` prints STT OK or "missing (pip install faster-whisper)" off this answer."""
        from core.transcribe import is_whisper_available

        # A None entry in sys.modules makes `import faster_whisper` raise
        # ImportError: the state of a machine without the voice extra.
        with patch.dict("sys.modules", {"faster_whisper": None}):
            assert is_whisper_available() is False

    def test_GIVEN_whisper_installed_WHEN_checked_THEN_true(self):
        """The package answers this, never the model — weights may still be absent."""
        from core.transcribe import is_whisper_available

        stub = types.ModuleType("faster_whisper")
        with patch.dict("sys.modules", {"faster_whisper": stub}):
            assert is_whisper_available() is True


# VAD tests

class TestVAD:
    """Voice activity detection tests."""

    def test_GIVEN_silent_wav_WHEN_checked_THEN_no_voice(self, tmp_path):
        """Silent WAV → False."""
        from core.transcribe import _check_audio_has_voice
        wav = _make_silent_wav_bytes(1.0)
        path = tmp_path / "silent.wav"
        path.write_bytes(wav)
        assert _check_audio_has_voice(path) is False

    def test_GIVEN_loud_wav_WHEN_checked_THEN_has_voice(self, tmp_path):
        """Loud WAV → True."""
        from core.transcribe import _check_audio_has_voice
        wav = _make_wav_bytes(1.0, amplitude=10000)
        path = tmp_path / "loud.wav"
        path.write_bytes(wav)
        assert _check_audio_has_voice(path) is True

    def test_GIVEN_very_short_wav_WHEN_checked_THEN_no_voice(self, tmp_path):
        """Recording too short (< 0.5s) → False."""
        from core.transcribe import _check_audio_has_voice
        wav = _make_wav_bytes(0.2)
        path = tmp_path / "short.wav"
        path.write_bytes(wav)
        assert _check_audio_has_voice(path) is False

    def test_GIVEN_non_wav_WHEN_checked_THEN_returns_true(self, tmp_path):
        """Non-WAV formats → True (conservative)."""
        from core.transcribe import _check_audio_has_voice
        path = tmp_path / "audio.webm"
        path.write_bytes(b"\x1a\x45\xdf\xa3")
        assert _check_audio_has_voice(path) is True


# Path sandboxing tests

class TestAudioSandbox:
    """Audio files may only be stored inside the audio dir."""

    def test_GIVEN_upload_WHEN_saved_THEN_in_audio_dir(self, audio_client, tmp_path):
        """Uploaded files land in the configured audio directory."""
        with patch("core.transcribe.transcribe") as mock_t, \
             patch("core.transcribe.is_whisper_available", return_value=True):
            mock_t.return_value = "Test"
            files = {"file": ("test.webm", b"\x1a" * 500, "audio/webm")}
            resp = audio_client.post("/api/audio/transcribe", files=files)

        assert resp.status_code == 200
        audio_dir = tmp_path / "audio"
        saved_files = list(audio_dir.glob("*.webm"))
        assert len(saved_files) == 1
        assert saved_files[0].parent.resolve() == audio_dir.resolve()

    def test_GIVEN_filename_WHEN_saved_THEN_no_user_input_in_name(self, audio_client):
        """The file name carries no user input (only timestamp + uuid)."""
        with patch("core.transcribe.transcribe") as mock_t, \
             patch("core.transcribe.is_whisper_available", return_value=True):
            mock_t.return_value = "Test"
            files = {"file": ("../../etc/passwd.webm", b"\x1a" * 500, "audio/webm")}
            resp = audio_client.post("/api/audio/transcribe", files=files)

        assert resp.status_code == 200
        audio_url = resp.json()["audio_url"]
        assert "../" not in audio_url
        assert "passwd" not in audio_url


class TestEdgeSynthesisBound:
    """The Edge synthesis answers inside the client's patience or not at all.

    `app/src/lib/api/http.ts` sizes `RequestOptions.timeoutMs` by "the 90 s synthesis cap in
    server/routes/audio.py" and aborts at `advanced.api_timeout` (120 s). A synthesis that
    outlives the abort is reported to the reader as "the backend did not answer" while this
    server keeps writing the mp3, and the retry writes a second one.
    """

    class _SlowCommunicate:
        """A synthesis that starts writing and then stops answering, past any bound it is given."""

        def __init__(self, text, voice, past):
            self._past = past

        async def save(self, path):
            Path(path).write_bytes(b"\x00" * 2048)   # a real mp3 starts arriving
            await asyncio.sleep(self._past)

    def _post_synthesize(self, client, monkeypatch, *, bound):
        """The Edge path with a cloud that never finishes.

        The module is put into `sys.modules` rather than imported: `edge-tts` is an optional
        extra, installed on some machines and absent from CI, and the route imports it inside
        the handler — which is also why a missing module is a `tts_failed` and not a boot error.
        """
        import server.routes.audio as audio_route
        from core import voice_config

        fake = types.ModuleType("edge_tts")
        fake.Communicate = lambda text, voice: self._SlowCommunicate(text, voice, past=bound * 5)
        monkeypatch.setitem(sys.modules, "edge_tts", fake)
        monkeypatch.setattr(voice_config, "resolve_tts_engine", lambda: "edge")
        monkeypatch.setattr(audio_route, "TTS_SYNTHESIS_SECONDS", bound)
        return client.post("/api/audio/synthesize", json={"text": "Hallo Welt"})

    def test_GIVEN_a_synthesis_that_never_finishes_WHEN_the_bound_passes_THEN_it_refuses(
        self, audio_client, monkeypatch
    ):
        resp = self._post_synthesize(audio_client, monkeypatch, bound=0.2)

        body = resp.json()
        # tts_failed is a 5xx in server/refusals.py::REASONS; what the reader needs is the
        # reason code and one sentence, not the status line of a wrapped refusal.
        assert resp.status_code == 500, body
        assert body["error"]["reason_code"] == "tts_failed", body
        assert "0.2" in str(body["error"]["reason_params"]["error"]), body
        assert "500:" not in body["error"]["message"], body

    def test_GIVEN_a_refused_synthesis_WHEN_the_answer_lands_THEN_no_partial_file_is_left(
        self, audio_client, monkeypatch
    ):
        self._post_synthesize(audio_client, monkeypatch, bound=0.2)

        leftovers = list(Path(os.environ["EPHE_AUDIO_DIR"]).glob("tts_*.mp3"))
        assert leftovers == [], [p.name for p in leftovers]

    def test_GIVEN_the_bundles_THEN_the_refusal_renders_the_timeout_as_its_reason(self):
        from server.refusals import REASONS

        assert "tts_failed" in REASONS
        for locale in ("en", "de"):
            sentences = json.loads(
                (Path(__file__).resolve().parents[1] / "app/src/locales" / f"{locale}.json").read_text()
            )["serverError"]
            assert "{{error}}" in sentences["tts_failed"], locale

    def test_GIVEN_the_three_bounded_paths_THEN_the_server_answers_before_the_page_does(self):
        """Either local rung, then Edge, then the page's own abort, in that order: whichever
        engine `auto` picked, the reader gets a refusal with a reason and not a silence they
        sized. A second rung added without its bound here outruns the page silently."""
        from core.settings_schema import SCHEMA
        from core.voice_synth import PIPER_TIMEOUT_SECONDS, SUPERTONIC_SYNTHESIS_SECONDS
        from server.routes.audio import TTS_SYNTHESIS_SECONDS

        client_bound = SCHEMA["advanced.api_timeout"]["default"]
        local_bound = max(PIPER_TIMEOUT_SECONDS, SUPERTONIC_SYNTHESIS_SECONDS)
        assert 0 < local_bound < TTS_SYNTHESIS_SECONDS < client_bound


class TestTheSecondLocalRungStaysLocal:
    """A resolved supertonic is answered by this machine alone.

    The route special-cased piper, so the second rung fell through to the Edge
    branch below it: the strict choice `tts_engine: "supertonic"`, and every `auto`
    turn on a piper-less machine that has the assets, dialled out to an endpoint the
    user never named.
    """

    def _post(self, client, monkeypatch, *, engine, writer):
        from core import voice_config, voice_synth

        dialled: list[str] = []

        def _no_cloud(text, voice):
            dialled.append(voice)
            raise AssertionError("the cloud branch ran")

        fake = types.ModuleType("edge_tts")
        fake.Communicate = _no_cloud
        monkeypatch.setitem(sys.modules, "edge_tts", fake)
        monkeypatch.setattr(voice_config, "resolve_tts_engine", lambda: engine)
        monkeypatch.setattr(voice_synth, "write_supertonic_wav", writer)
        return client.post("/api/audio/synthesize", json={"text": "Ein Satz."}), dialled

    def _wav(self, name: str) -> Path:
        folder = Path(os.environ["EPHE_AUDIO_DIR"])
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / name
        target.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
        return target

    def test_a_resolved_local_rung_writes_its_wav_here(self, audio_client, monkeypatch):
        target = self._wav("tts_local_supertonic.wav")
        resp, dialled = self._post(
            audio_client, monkeypatch, engine="supertonic", writer=lambda text: target
        )

        assert resp.status_code == 200, resp.json()
        assert resp.json()["audio_url"] == "/audio/tts_local_supertonic.wav"
        assert dialled == []

    def test_the_missing_half_answers_with_its_own_sentence(self, audio_client, monkeypatch):
        def _refuse(text):
            raise RuntimeError(
                "supertonic is installed; the model assets are not — "
                "setup: 'ephe voice install supertonic'."
            )

        resp, dialled = self._post(
            audio_client, monkeypatch, engine="supertonic", writer=_refuse
        )

        assert resp.status_code == 400, resp.json()
        assert "ephe voice install supertonic" in resp.text, resp.text
        assert dialled == []

    def test_a_rung_that_overruns_its_wall_clock_is_answered_with_a_refusal(self, audio_client, monkeypatch):
        """GIVEN a local synthesis that does not finish inside the rung's own bound
        THEN the page gets a refusal it can render instead of a request left hanging until
        the browser gives up: the local path is bounded the way the cloud path is."""
        import time

        from core import voice_synth

        def slow(text):
            time.sleep(1.0)
            raise AssertionError("an overrun must not hand back a file")

        monkeypatch.setattr(voice_synth, "SUPERTONIC_SYNTHESIS_SECONDS", 0.05)
        resp, dialled = self._post(audio_client, monkeypatch, engine="supertonic", writer=slow)

        body = resp.json()
        assert resp.status_code == 500, body
        assert body["error"]["reason_code"] == "tts_failed", body
        assert "0.05" in str(body["error"]["reason_params"]["error"]), body
        assert dialled == []

    def test_the_first_rung_keeps_answering_first(self, audio_client, monkeypatch):
        from core import voice_config, voice_synth

        target = self._wav("tts_local_piper.wav")
        monkeypatch.setattr(voice_synth, "write_piper_wav", lambda text: target)
        monkeypatch.setattr(voice_config, "resolve_tts_engine", lambda: "piper")

        resp = audio_client.post("/api/audio/synthesize", json={"text": "Ein Satz."})

        assert resp.status_code == 200, resp.json()
        assert resp.json()["audio_url"] == "/audio/tts_local_piper.wav"
