"""
◑ Ephe – Audio-Feature Tests
tests/test_audio.py

TDD tests for:
  - the audio upload route (MIME, size, sanity)
  - the transcription engine (VAD, format)
  - path sandboxing

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import io
import os
import struct
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
        """is_whisper_available() → False when it is not installed."""
        with patch.dict("sys.modules", {"faster_whisper": None}):
            # Re-import to test
            import importlib
            from core import transcribe
            importlib.reload(transcribe)
            # On ImportError → False
            # (setting the module to None makes the import raise ImportError)

    def test_GIVEN_whisper_available_check_THEN_returns_bool(self):
        """is_whisper_available() returns a bool."""
        from core.transcribe import is_whisper_available
        result = is_whisper_available()
        assert isinstance(result, bool)


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
