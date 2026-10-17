"""tests/test_voice_config.py — R18 offline voice loop: configuration + engine choice.

Given/When/Then. voice.json (no secret, still 0600 like every config file)
drives the TTS engine (auto|piper|edge), the voices and STT (faster-whisper).
"""
from __future__ import annotations

import pathlib
import stat

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    from core import engine_config

    cfg_dir = tmp_path / "ephe-config"
    cfg_dir.mkdir()
    monkeypatch.setattr(engine_config, "CONFIG_DIR", cfg_dir)
    return cfg_dir


class TestVoiceConfigStore:
    def test_given_nothing_when_loaded_then_defaults(self, config_dir):
        from core.voice_config import load_voice_config

        cfg = load_voice_config()
        assert cfg.tts_engine == "auto"
        assert cfg.piper_voice == "en_US-amy-medium"
        assert cfg.edge_voice == "de-DE-KillianNeural"
        assert cfg.stt_model == "tiny"
        assert cfg.stt_language == "auto"

    def test_given_saved_when_loaded_then_roundtrip(self, config_dir):
        from core.voice_config import load_voice_config, save_voice_config

        save_voice_config(tts_engine="piper", piper_voice="de_DE-thorsten-medium", stt_model="base")
        cfg = load_voice_config()
        assert cfg.tts_engine == "piper"
        assert cfg.piper_voice == "de_DE-thorsten-medium"
        assert cfg.stt_model == "base"

    def test_given_saved_when_inspected_then_owner_only(self, config_dir):
        from core.voice_config import save_voice_config, voice_config_path

        save_voice_config(tts_engine="auto")
        assert stat.S_IMODE(voice_config_path().stat().st_mode) == 0o600

    def test_given_invalid_engine_when_saved_then_rejected(self, config_dir):
        from core.voice_config import save_voice_config

        with pytest.raises(ValueError):
            save_voice_config(tts_engine="elevenlabs")

    def test_given_invalid_stt_model_when_saved_then_rejected(self, config_dir):
        from core.voice_config import save_voice_config

        with pytest.raises(ValueError):
            save_voice_config(stt_model="large-hypnotic")


class TestEngineResolution:
    def test_given_piper_binary_and_voice_when_auto_then_piper(self, config_dir, tmp_path, monkeypatch):
        from core.voice_config import load_voice_config, save_voice_config
        from core.voice_config import resolve_tts_engine

        save_voice_config(tts_engine="auto", piper_voice="en_US-amy-medium")
        monkeypatch.setattr("core.voice_config.piper_binary_available", lambda: True)
        monkeypatch.setattr(
            "core.voice_config.piper_voice_installed",
            lambda name: name == load_voice_config().piper_voice,
        )
        assert resolve_tts_engine() == "piper"

    def test_given_no_piper_when_auto_then_edge_fallback(self, config_dir, monkeypatch):
        from core.voice_config import save_voice_config, resolve_tts_engine

        save_voice_config(tts_engine="auto")
        monkeypatch.setattr("core.voice_config.piper_binary_available", lambda: False)
        assert resolve_tts_engine() == "edge", "THEN: Auto fällt auf Edge zurück (bestehendes Verhalten)"

    def test_given_strict_piper_without_binary_when_resolved_then_honest_error(self, config_dir, monkeypatch):
        from core.voice_config import save_voice_config, resolve_tts_engine

        save_voice_config(tts_engine="piper")
        monkeypatch.setattr("core.voice_config.piper_binary_available", lambda: False)
        with pytest.raises(RuntimeError, match="piper"):
            resolve_tts_engine()

    def test_given_strict_edge_when_resolved_then_edge(self, config_dir):
        from core.voice_config import save_voice_config, resolve_tts_engine

        save_voice_config(tts_engine="edge")
        assert resolve_tts_engine() == "edge"


@pytest.fixture
def client(config_dir, monkeypatch):
    from server.main import create_app

    return TestClient(create_app())


class TestVoiceSettingsRoutes:
    def test_given_get_when_nothing_configured_then_defaults_masked(self, client):
        body = client.get("/api/settings/voice").json()
        assert body["tts_engine"] == "auto"
        assert "piper_available" in body

    def test_given_put_then_get_roundtrip(self, client):
        r = client.put("/api/settings/voice", json={"tts_engine": "piper", "piper_voice": "de_DE-thorsten-medium", "stt_model": "base"})
        assert r.status_code == 200
        body = client.get("/api/settings/voice").json()
        assert body["tts_engine"] == "piper"
        assert body["piper_voice"] == "de_DE-thorsten-medium"
        assert body["stt_model"] == "base"

    def test_given_invalid_engine_when_put_then_422(self, client):
        assert client.put("/api/settings/voice", json={"tts_engine": "coqui"}).status_code == 422


class TestSynthesizeEngines:
    """R18: /api/audio/synthesize picks the engine from voice.json."""

    @pytest.fixture
    def audio_client(self, config_dir, monkeypatch, tmp_path):
        monkeypatch.setenv("EPHE_AUDIO_DIR", str(tmp_path / "audio"))
        from server.main import create_app

        return TestClient(create_app())

    def test_given_strict_piper_without_binary_when_synthesize_then_honest_400(self, audio_client, monkeypatch):
        from core.voice_config import save_voice_config

        save_voice_config(tts_engine="piper")
        monkeypatch.setattr("core.voice_config.piper_binary_available", lambda: False)
        r = audio_client.post("/api/audio/synthesize", json={"text": "Hallo Welt"})
        assert r.status_code == 400
        # the app error shape: {"error":{"message": ...}}
        assert "piper" in r.json()["error"]["message"].lower()

    def test_given_piper_binary_when_synthesize_then_wav_produced(self, audio_client, monkeypatch, tmp_path):
        import asyncio
        from core.voice_config import save_voice_config, voices_dir

        save_voice_config(tts_engine="piper", piper_voice="en_US-amy-medium")
        monkeypatch.setattr("core.voice_config.piper_binary", lambda: "/usr/local/bin/piper")
        # the voice counts as "installed"
        vdir = voices_dir()
        (vdir / "en_US-amy-medium.onnx").write_bytes(b"onnx")
        (vdir / "en_US-amy-medium.onnx.json").write_bytes(b"{}")

        class _Proc:
            returncode = 0

            async def communicate(self, stdin, timeout=None):
                return b"", b""

        async def _fake_exec(*cmd, **kw):
            # piper simulation: writes the WAV file to the --output_file argument
            out = cmd[cmd.index("--output_file") + 1]
            pathlib.Path(out).write_bytes(b"RIFF" + b"\x00" * 100)
            return _Proc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
        r = audio_client.post("/api/audio/synthesize", json={"text": "Hello local voice"})
        assert r.status_code == 200, r.text
        assert r.json()["audio_url"].endswith("_piper.wav")

    def test_given_auto_without_piper_when_synthesize_then_edge_fallback_used(self, audio_client, monkeypatch):
        pytest.importorskip("edge_tts")  # R18: edge-tts lives in the voice extra — the CI base install lacks it
        from core.voice_config import save_voice_config

        save_voice_config(tts_engine="auto")
        monkeypatch.setattr("core.voice_config.piper_binary_available", lambda: False)

        class _FakeCommunicate:
            def __init__(self, text, voice):
                self.voice = voice

            async def save(self, path):
                pathlib.Path(path).write_bytes(b"mp3-bytes")

        calls = {}

        def _fake_communicate(text, voice):
            calls["voice"] = voice
            return _FakeCommunicate(text, voice)

        monkeypatch.setattr("edge_tts.Communicate", _fake_communicate)
        r = audio_client.post("/api/audio/synthesize", json={"text": "Cloud fallback"})
        assert r.status_code == 200
        assert r.json()["audio_url"].endswith(".mp3")
        assert calls["voice"] == "de-DE-KillianNeural", "THEN: edge_voice aus voice.json"

    def test_given_empty_text_when_synthesize_then_400(self, audio_client):
        assert audio_client.post("/api/audio/synthesize", json={"text": "  "}).status_code == 400


class TestVoiceCli:
    """ephe voice list / install — opt-in download with a size cap."""

    def test_given_valid_name_when_install_then_voice_installed(self, config_dir, monkeypatch):
        import argparse

        import ephe_cli

        class _Resp:
            status_code = 200
            content = b"fake-onnx-or-json"

            def raise_for_status(self):
                return None

        monkeypatch.setattr("httpx.get", lambda url, **kw: _Resp())
        args = argparse.Namespace(voice_command="install", voices=["en_US-amy-medium"])
        assert ephe_cli.cmd_voice(args) == 0
        from core.voice_config import list_installed_piper_voices, piper_voice_installed

        assert piper_voice_installed("en_US-amy-medium")
        assert list_installed_piper_voices() == ["en_US-amy-medium"]

    def test_given_invalid_name_when_install_then_fails_without_download(self, config_dir):
        import argparse

        import ephe_cli

        args = argparse.Namespace(voice_command="install", voices=["bogus"])
        assert ephe_cli.cmd_voice(args) == 1
        from core.voice_config import list_installed_piper_voices

        assert list_installed_piper_voices() == []

    def test_given_list_when_run_then_honest_binary_status(self, config_dir, monkeypatch, capsys):
        import argparse

        import ephe_cli

        monkeypatch.setattr("core.voice_config.piper_binary_available", lambda: False)
        args = argparse.Namespace(voice_command="list", voices=[])
        assert ephe_cli.cmd_voice(args) == 0
        out = capsys.readouterr().out
        assert "NOT found" in out and "brew install piper" in out


class TestDoctorVoice:
    def test_given_auto_without_piper_then_honest_edge_fallback(self, config_dir, monkeypatch):
        import ephe_cli

        monkeypatch.setattr("core.voice_config.piper_binary_available", lambda: False)
        monkeypatch.setattr("core.transcribe.is_whisper_available", lambda: False)
        ok, detail = ephe_cli._doctor_voice()
        assert ok is True, "THEN: Cloud-Fallback ist kein Setup-Fehler"
        assert "Edge cloud fallback" in detail and "brew install piper" in detail
        assert "missing" in detail, "THEN: fehlender STT wird sichtbar gemeldet"

    def test_given_full_piper_setup_then_local_ok(self, config_dir, monkeypatch, tmp_path):
        import ephe_cli
        from core.voice_config import save_voice_config, voices_dir

        save_voice_config(tts_engine="piper", piper_voice="de_DE-thorsten-medium")
        monkeypatch.setattr("core.voice_config.piper_binary_available", lambda: True)
        vdir = voices_dir()
        (vdir / "de_DE-thorsten-medium.onnx").write_bytes(b"x")
        (vdir / "de_DE-thorsten-medium.onnx.json").write_bytes(b"{}")
        monkeypatch.setattr("core.transcribe.is_whisper_available", lambda: True)
        ok, detail = ephe_cli._doctor_voice()
        assert ok is True and "piper local" in detail and "OK" in detail


class TestPiperBinaryFromEnv:
    """EPHE_PIPER_BIN resolved at the ENV level.

    Every other test in this file monkeypatches `piper_binary`/`piper_binary_available`
    itself, so the real body of the resolver — and the doubled read it carried — was
    never exercised: `get(X) or get(X, "").strip()` returned the UNSTRIPPED first
    operand whenever it was non-empty, so a path padded by a shell (`" /opt/bin/piper "`)
    failed `Path(...).exists()` and the override silently became "no piper at all".
    """

    @pytest.fixture
    def piper_on_path(self, tmp_path, monkeypatch):
        """A stub piper on PATH, so the `shutil.which` branch has a deterministic answer."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "piper"
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
        monkeypatch.setenv("PATH", str(bin_dir))
        return str(stub)

    def test_given_exact_override_when_resolved_then_that_binary(self, monkeypatch, tmp_path):
        """GIVEN EPHE_PIPER_BIN points at an existing file
        THEN that exact path is the binary (the override beats the PATH lookup)."""
        from core.voice_config import piper_binary

        real = tmp_path / "my-piper"
        real.write_text("x", encoding="utf-8")
        monkeypatch.setenv("EPHE_PIPER_BIN", str(real))
        assert piper_binary() == str(real)

    @pytest.mark.parametrize("pattern", ["  {p}  ", "\t{p}", "{p} ", "\n{p}\t"])
    def test_given_padded_override_when_resolved_then_stripped(self, monkeypatch, tmp_path, pattern):
        """GIVEN the override carries the whitespace a quoted shell value brings along
        THEN it is stripped once and the binary is FOUND — today the padded string went
        straight into `Path(...).exists()`, which said no, and the user lost their
        local TTS engine without any message about it."""
        from core.voice_config import piper_binary

        real = tmp_path / "my-piper"
        real.write_text("x", encoding="utf-8")
        monkeypatch.setenv("EPHE_PIPER_BIN", pattern.format(p=str(real)))
        assert piper_binary() == str(real)

    @pytest.mark.parametrize("pattern", ["  {p}  ", "{p}"])
    def test_given_missing_override_when_resolved_then_none(self, monkeypatch, tmp_path, pattern):
        """GIVEN the override names a path that does not exist
        THEN there is no binary — a stripped path is checked, not trusted, and the
        PATH lookup does not silently win over an explicit (broken) choice."""
        from core.voice_config import piper_binary

        monkeypatch.setenv("EPHE_PIPER_BIN", pattern.format(p=str(tmp_path / "nowhere")))
        assert piper_binary() is None

    @pytest.mark.parametrize("value", ["", "   ", " \t "])
    def test_given_blank_override_when_resolved_then_path_lookup(self, monkeypatch, piper_on_path, value):
        """GIVEN EPHE_PIPER_BIN holds only whitespace
        THEN it reads as unset and the PATH lookup runs — the un-stripped first operand
        used to short-circuit the `or` and return "no piper" instead."""
        from core.voice_config import piper_binary

        monkeypatch.setenv("EPHE_PIPER_BIN", value)
        assert piper_binary() == piper_on_path

    def test_given_blank_override_and_no_piper_on_path_when_resolved_then_none(self, monkeypatch, tmp_path):
        """GIVEN a whitespace-only override and no piper anywhere on PATH
        THEN still no binary, reached through the `which` branch rather than the
        exists() check on a string of spaces."""
        from core.voice_config import piper_binary

        monkeypatch.setenv("EPHE_PIPER_BIN", "   ")
        monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
        assert piper_binary() is None

    def test_given_no_override_when_resolved_then_path_lookup(self, monkeypatch, piper_on_path):
        """GIVEN nobody set the variable
        THEN the installed binary is found via PATH."""
        from core.voice_config import piper_binary

        monkeypatch.delenv("EPHE_PIPER_BIN", raising=False)
        assert piper_binary() == piper_on_path

    def test_given_override_when_availability_checked_then_env_is_honoured(self, monkeypatch, tmp_path):
        """GIVEN the resolver is asked through `piper_binary_available`
        THEN the same stripped answer comes back — the availability flag the doctor and
        the audio route read is the one this fix changed."""
        from core.voice_config import piper_binary_available

        real = tmp_path / "my-piper"
        real.write_text("x", encoding="utf-8")
        monkeypatch.setenv("EPHE_PIPER_BIN", f"  {real}  ")
        assert piper_binary_available() is True

