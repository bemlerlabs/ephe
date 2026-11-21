"""tests/test_voice_supertonic.py — the second local rung of the TTS ladder.

Given/When/Then. The ladder the owner approved 2026-11-18 is supertonic → piper → edge:
`auto` answers with the cloud only after both local rungs were looked at, and the
`synthesize` tool never reaches the cloud at all. Supertonic speaks in process, so the
cases stand in the package's own class and pin what a synthesis is asked for — the
sentence, the style, the numbers and the folder it reads.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from core.voice_config import SUPERTONIC_ONNX_GRAPHS, SUPERTONIC_SUPPORT_FILES

SUPERSONIC_TEXT = "Pelikan. Diese Maschine spricht einen Satz."

#: What a stand-in engine can be told to do wrong, each one a shape the real package can
#: answer with: no voice style of that name, a failed synthesis, a WAV without samples, and
#: the writer reaching for a module a partial install left out.
_NO_AUDIO = "empty"
_HEADER_ONLY = "header"
_NO_SOUNDFILE = "import"
_BAD_HEADER = "junk"

#: The two styles the fake folder holds, the way a finished install ships them.
_KNOWN_STYLES = ("M1", "F1")


class FakePackage:
    """The seam the rung speaks through: records one synthesis, answers like the real class.

    `synthesize` returns the two-tuple the package returns and `save_audio` writes a real
    WAV, so the caller's own size check is exercised rather than stubbed away."""

    def __init__(self, recorder: dict):
        self.recorder = recorder

    def engine(self):
        recorder = self.recorder

        class Engine:
            def __init__(self, model=None, model_dir=None, auto_download=True):
                recorder.setdefault("inits", []).append(model)
                recorder["init"] = {
                    "model": model,
                    "model_dir": model_dir,
                    "auto_download": auto_download,
                }

            def get_voice_style(self, voice_name):
                recorder.setdefault("voices", []).append(voice_name)
                if voice_name not in _KNOWN_STYLES:
                    raise FileNotFoundError(f"Voice style file not found: {voice_name}")
                return {"name": voice_name}

            def synthesize(self, text, voice_style=None, total_steps=8, lang=None, **rest):
                recorder["call"] = {
                    "text": text,
                    "voice": (voice_style or {}).get("name"),
                    "total_steps": total_steps,
                    "lang": lang,
                    "rest": rest,
                }
                if recorder.get("raise"):
                    raise RuntimeError(recorder["raise"])
                return ("frames", 0.0)

            def save_audio(self, wav, output_path):
                recorder.setdefault("saved", []).append(str(output_path))
                target = Path(output_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                if recorder.get("write") == _NO_SOUNDFILE:
                    raise ImportError("soundfile library is required to save audio")
                if recorder.get("write") == _NO_AUDIO:
                    return
                if recorder.get("write") == _HEADER_ONLY:
                    target.write_bytes(b"RIFF" + b"\x00" * 40)
                    return
                if recorder.get("write") == _BAD_HEADER:
                    target.write_bytes(b"RIFF" + b"\x00" * 100)
                    return
                import wave

                with wave.open(str(target), "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(44100)
                    handle.writeframes(b"\x00\x01" * 4410)

        return Engine


@pytest.fixture
def fake_package(monkeypatch):
    """The second rung's package half: the class behind the seam and the import probe."""
    from core import voice_synth

    recorder: dict = {}
    monkeypatch.setattr(voice_synth, "_supertonic_engine", None)
    monkeypatch.setattr(voice_synth, "supertonic_backend", lambda: FakePackage(recorder).engine())
    monkeypatch.setattr("core.voice_config.supertonic_package_available", lambda: True)
    return recorder


_FAKE_PIPER = """
import os
import sys
import wave

argv = sys.argv[1:]
with open(os.environ["PIPER_ARGV_FILE"], "w", encoding="utf-8") as handle:
    handle.write("\\n".join(argv))
sys.stdin.buffer.read()
out = argv[argv.index("--output_file") + 1]
with wave.open(out, "wb") as handle:
    handle.setnchannels(1)
    handle.setsampwidth(2)
    handle.setframerate(22050)
    handle.writeframes(b"\\x00\\x01" * 2205)
raise SystemExit(0)
"""


def _executable(path: Path, body: str) -> str:
    path.write_text("#!" + sys.executable + "\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


@pytest.fixture
def voice_home(tmp_path, monkeypatch):
    """A home where neither rung exists until the case installs one: the PATH is emptied,
    both binary overrides are cleared and the asset folder points inside tmp_path."""
    from core import engine_config

    cfg_dir = tmp_path / "ephe-config"
    cfg_dir.mkdir()
    monkeypatch.setattr(engine_config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("EPHE_AUDIO_DIR", str(tmp_path / "audio"))
    monkeypatch.setenv("EPHE_SUPERTONIC_ASSET_DIR", str(cfg_dir / "assets"))
    monkeypatch.delenv("EPHE_PIPER_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    return cfg_dir


def write_assets(root: Path, skip: str | None = None) -> Path:
    """The folder one synthesis reads, as a finished `ephe voice install supertonic` leaves it.

    `skip` names one graph to leave out — a partial folder is the shape that has to be
    refused, and the support files are part of what a synthesis opens."""
    onnx = root / "onnx"
    onnx.mkdir(parents=True, exist_ok=True)
    for name in SUPERTONIC_ONNX_GRAPHS:
        if name != skip:
            (onnx / f"{name}.onnx").write_bytes(b"onnx")
    if skip not in SUPERTONIC_SUPPORT_FILES:
        for name in SUPERTONIC_SUPPORT_FILES:
            (root / name).write_bytes(b"{}")
    styles = root / "voice_styles"
    styles.mkdir(exist_ok=True)
    for name in ("M1", "F1"):
        (styles / f"{name}.json").write_bytes(b"{}")
    return onnx


@pytest.fixture
def supertonic_ready(voice_home, fake_package):
    """The second rung usable: the stand-in package and a complete asset folder."""
    write_assets(voice_home / "assets")
    return fake_package


def install_piper_voice(config_dir: Path, name: str = "en_US-amy-medium") -> None:
    from core.voice_config import ensure_voices_dir

    vdir = ensure_voices_dir()
    (vdir / f"{name}.onnx").write_bytes(b"onnx")
    (vdir / f"{name}.onnx.json").write_bytes(b"{}")


class TestSupertonicConfig:
    def test_given_nothing_when_loaded_then_supertonic_defaults(self, voice_home):
        """GIVEN no voice.json
        THEN the second rung carries the defaults the measured CLI was run with."""
        from core.voice_config import load_voice_config

        cfg = load_voice_config()
        assert cfg.supertonic_voice == "M1"
        assert cfg.supertonic_lang == "de"
        assert cfg.supertonic_steps == 8

    def test_given_saved_when_loaded_then_the_three_fields_round_trip(self, voice_home):
        """GIVEN the three new fields saved
        THEN a reload answers with the same values, so voice.json is their only home."""
        from core.voice_config import load_voice_config, save_voice_config

        save_voice_config(supertonic_voice="M3", supertonic_lang="en", supertonic_steps=16)
        cfg = load_voice_config()
        assert cfg.supertonic_voice == "M3"
        assert cfg.supertonic_lang == "en"
        assert cfg.supertonic_steps == 16

    def test_given_saved_when_another_field_changes_then_supertonic_survives(self, voice_home):
        """GIVEN the rung was configured and an unrelated field is saved afterwards
        THEN the rung keeps its values — a partial save must not reset the ladder."""
        from core.voice_config import load_voice_config, save_voice_config

        save_voice_config(supertonic_voice="M2", supertonic_steps=12)
        save_voice_config(tts_engine="edge")
        cfg = load_voice_config()
        assert cfg.supertonic_voice == "M2" and cfg.supertonic_steps == 12

    def test_given_steps_of_a_string_when_saved_then_stored_as_a_number(self, voice_home):
        """GIVEN a hand-edited voice.json carries "12" for the steps
        THEN the reload stores the number, because the argv needs one."""
        from core.voice_config import load_voice_config, voice_config_path

        voice_config_path().write_text('{"supertonic_steps": "12"}', encoding="utf-8")
        assert load_voice_config().supertonic_steps == 12

    @pytest.mark.parametrize("steps", [0, -3, 101, 5000])
    def test_given_steps_outside_the_bounds_when_saved_then_rejected(self, voice_home, steps):
        """GIVEN steps outside the upstream CLI's own 1..100
        THEN the save refuses and names the range it accepts."""
        from core.voice_config import save_voice_config

        with pytest.raises(ValueError, match="supertonic_steps out of range"):
            save_voice_config(supertonic_steps=steps)

    def test_given_steps_inside_the_bounds_when_saved_then_accepted(self, voice_home):
        """GIVEN steps at each end of the accepted range
        THEN both saves go through: the gate is the upstream range and nothing narrower."""
        from core.voice_config import save_voice_config

        assert save_voice_config(supertonic_steps=1).supertonic_steps == 1
        assert save_voice_config(supertonic_steps=100).supertonic_steps == 100

    @pytest.mark.parametrize("value", ["", "   "])
    def test_given_empty_voice_when_saved_then_rejected_with_the_list_verb(self, voice_home, value):
        """GIVEN an empty voice style name
        THEN the save refuses and names where the names come from."""
        from core.voice_config import save_voice_config

        with pytest.raises(ValueError, match="supertonic_voice is empty") as caught:
            save_voice_config(supertonic_voice=value)
        assert "supertonic list-voices" in str(caught.value)

    @pytest.mark.parametrize("value", ["", "  "])
    def test_given_empty_lang_when_saved_then_rejected_with_a_code_example(self, voice_home, value):
        """GIVEN an empty language code
        THEN the save refuses instead of handing the CLI an empty --lang."""
        from core.voice_config import save_voice_config

        with pytest.raises(ValueError, match="supertonic_lang is empty") as caught:
            save_voice_config(supertonic_lang=value)
        assert "'de'" in str(caught.value)


class TestSupertonicPackageProbe:
    def test_given_an_importable_package_when_probed_then_available(self, voice_home, monkeypatch):
        """GIVEN the package can be found by the interpreter
        THEN the rung's package half reports itself ready."""
        import importlib.util

        from core.voice_config import supertonic_package_available

        monkeypatch.setattr(importlib.util, "find_spec", lambda name: object() if name == "supertonic" else None)
        assert supertonic_package_available() is True

    def test_given_no_package_when_probed_then_not_available(self, voice_home, monkeypatch):
        """GIVEN the interpreter cannot find the package
        THEN the half reports itself missing rather than raising on the missing module."""
        import importlib.util

        from core.voice_config import supertonic_package_available

        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        assert supertonic_package_available() is False

    def test_given_a_broken_package_when_probed_then_not_available(self, voice_home, monkeypatch):
        """GIVEN the lookup itself fails, which a half-installed distribution does
        THEN the probe answers false: a doctor run must not die over a broken install."""
        import importlib.util

        from core.voice_config import supertonic_package_available

        def explode(name):
            raise ImportError("no metadata")

        monkeypatch.setattr(importlib.util, "find_spec", explode)
        assert supertonic_package_available() is False


class TestSupertonicAssetsProbe:
    def test_given_four_graphs_when_probed_then_installed(self, voice_home):
        """GIVEN all four ONNX graphs on disk
        THEN the rung counts as usable."""
        from core.voice_config import supertonic_assets_installed

        write_assets(voice_home / "assets")
        assert supertonic_assets_installed() is True

    @pytest.mark.parametrize("missing", SUPERTONIC_ONNX_GRAPHS)
    def test_given_one_graph_missing_when_probed_then_not_installed(self, voice_home, missing):
        """GIVEN one of the four graphs missing
        THEN the rung is not usable — a partial folder cannot synthesize."""
        from core.voice_config import supertonic_assets_installed

        write_assets(voice_home / "assets", skip=missing)
        assert supertonic_assets_installed() is False

    @pytest.mark.parametrize("missing", SUPERTONIC_SUPPORT_FILES)
    def test_given_one_support_file_missing_when_probed_then_not_installed(
        self, voice_home, missing
    ):
        """GIVEN the graphs complete and one of the two files beside them missing
        THEN the rung is still not usable: a synthesis opens the model config and the
        unicode indexer too, and would fail mid-sentence on a folder this probe called ready."""
        from core.voice_config import supertonic_assets_installed

        write_assets(voice_home / "assets", skip=missing)
        assert supertonic_assets_installed() is False

    def test_given_no_asset_dir_when_probed_then_false_and_nothing_created(self, voice_home):
        """GIVEN the asset folder does not exist
        THEN the probe answers false and leaves no folder behind — `ephe doctor` runs this
        read on a fresh machine, and a probe that manufactures the state it reports turns
        "not installed" into installed."""
        from core.voice_config import supertonic_assets_installed

        assets = voice_home / "assets"
        assert supertonic_assets_installed() is False
        assert not assets.exists()

    def test_given_override_when_dir_resolved_then_that_folder_is_read(self, voice_home, monkeypatch, tmp_path):
        """GIVEN EPHE_SUPERTONIC_ASSET_DIR points somewhere else
        THEN the probe reads that folder — a machine may keep the weights off the home disk."""
        from core.voice_config import supertonic_assets_installed

        other = tmp_path / "elsewhere"
        monkeypatch.setenv("EPHE_SUPERTONIC_ASSET_DIR", str(other))
        assert supertonic_assets_installed() is False
        write_assets(other)
        assert supertonic_assets_installed() is True


class TestLadder:
    def test_given_both_rungs_ready_when_auto_then_supertonic_first(self, voice_home, supertonic_ready, monkeypatch):
        """GIVEN piper and supertonic are both usable and the engine is auto
        THEN supertonic answers — the owner's ears picked its voice over piper's on
        2026-11-18, and piper stays the rung for a machine without those assets."""
        from core.voice_config import resolve_tts_engine, save_voice_config

        save_voice_config(tts_engine="auto", piper_voice="en_US-amy-medium")
        install_piper_voice(voice_home)
        monkeypatch.setattr("core.voice_config.piper_binary", lambda: "/usr/local/bin/piper")
        assert resolve_tts_engine() == "supertonic"

    def test_given_piper_voice_gone_when_auto_then_supertonic(self, voice_home, supertonic_ready, monkeypatch):
        """GIVEN piper's binary is there and its voice file is not
        THEN the ladder steps down to supertonic instead of the cloud."""
        from core.voice_config import resolve_tts_engine, save_voice_config

        save_voice_config(tts_engine="auto", piper_voice="de_DE-thorsten-medium")
        monkeypatch.setattr("core.voice_config.piper_binary", lambda: "/usr/local/bin/piper")
        assert resolve_tts_engine() == "supertonic"

    def test_given_piper_binary_gone_when_auto_then_supertonic(self, voice_home, supertonic_ready, monkeypatch):
        """GIVEN no piper binary at all and supertonic ready
        THEN the second local rung answers before any thought of the cloud."""
        from core.voice_config import resolve_tts_engine, save_voice_config

        save_voice_config(tts_engine="auto", piper_voice="en_US-amy-medium")
        install_piper_voice(voice_home)
        monkeypatch.setattr("core.voice_config.piper_binary", lambda: None)
        assert resolve_tts_engine() == "supertonic"

    def test_given_supertonic_assets_missing_when_auto_then_edge(self, voice_home, monkeypatch):
        """GIVEN neither rung is usable (piper absent, supertonic binary without weights)
        THEN auto falls to the cloud, which is the rung the user opted into by saying auto."""
        from core.voice_config import resolve_tts_engine, save_voice_config

        save_voice_config(tts_engine="auto")
        monkeypatch.setattr("core.voice_config.supertonic_package_available", lambda: True)
        assert resolve_tts_engine() == "edge"

    def test_given_nothing_local_when_auto_then_edge(self, voice_home):
        """GIVEN no local rung at all
        THEN auto still answers with the cloud: the ladder reordered the local rungs and left this floor alone."""
        from core.voice_config import resolve_tts_engine, save_voice_config

        save_voice_config(tts_engine="auto")
        assert resolve_tts_engine() == "edge"

    def test_given_explicit_edge_when_auto_rungs_ready_then_edge(self, voice_home, supertonic_ready, monkeypatch):
        """GIVEN both local rungs are usable but the user named the cloud
        THEN the named choice wins — the ladder never overrules an explicit remote choice."""
        from core.voice_config import resolve_tts_engine, save_voice_config

        save_voice_config(tts_engine="edge")
        monkeypatch.setattr("core.voice_config.piper_binary", lambda: "/usr/local/bin/piper")
        install_piper_voice(voice_home)
        assert resolve_tts_engine() == "edge"

    def test_given_strict_supertonic_without_package_when_resolved_then_the_package_half(
        self, voice_home, monkeypatch
    ):
        """GIVEN tts_engine=supertonic and no importable package, weights in place beside it
        THEN the refusal names the package, gives the install command, and says nothing about
        the assets half the machine already has."""
        from core.voice_config import resolve_tts_engine, save_voice_config

        save_voice_config(tts_engine="supertonic")
        write_assets(voice_home / "assets")
        monkeypatch.setattr("core.voice_config.supertonic_package_available", lambda: False)

        with pytest.raises(RuntimeError) as caught:
            resolve_tts_engine()

        message = str(caught.value)
        assert "supertonic not importable" in message
        assert "pip install supertonic" in message
        assert "model assets" not in message

    def test_given_strict_supertonic_without_assets_when_resolved_then_the_assets_half(
        self, voice_home, monkeypatch
    ):
        """GIVEN tts_engine=supertonic, the package importable and one graph missing
        THEN the refusal says the package is installed and names the install verb, without
        sending anyone to reinstall a package they installed."""
        from core.voice_config import resolve_tts_engine, save_voice_config

        save_voice_config(tts_engine="supertonic")
        write_assets(voice_home / "assets", skip="vocoder")
        monkeypatch.setattr("core.voice_config.supertonic_package_available", lambda: True)

        with pytest.raises(RuntimeError) as caught:
            resolve_tts_engine()

        message = str(caught.value)
        assert "supertonic is installed" in message
        assert "ephe voice install supertonic" in message
        assert "not importable" not in message
        assert "pip install supertonic" not in message

    def test_given_strict_supertonic_ready_when_resolved_then_supertonic(self, voice_home, supertonic_ready):
        """GIVEN tts_engine=supertonic with both halves present
        THEN the strict choice resolves to the local rung."""
        from core.voice_config import resolve_tts_engine, save_voice_config

        save_voice_config(tts_engine="supertonic")
        assert resolve_tts_engine() == "supertonic"

    def test_given_strict_piper_without_its_voice_when_resolved_then_the_voice_half(
        self, voice_home, monkeypatch
    ):
        """GIVEN tts_engine=piper, the binary there and the voice file missing
        THEN the refusal names the voice and its install verb — the shape PR #348 established,
        kept while the ladder grew around it."""
        from core.voice_config import resolve_tts_engine, save_voice_config

        save_voice_config(tts_engine="piper", piper_voice="de_DE-thorsten-medium")
        monkeypatch.setattr("core.voice_config.piper_binary", lambda: "/usr/local/bin/piper")

        with pytest.raises(RuntimeError) as caught:
            resolve_tts_engine()

        message = str(caught.value)
        assert "piper is installed" in message
        assert "ephe voice install de_DE-thorsten-medium" in message
        assert "pipx install piper-tts" not in message


class TestWriteSupertonicWav:
    def test_given_a_text_when_written_then_the_synthesis_carries_the_measured_contract(
        self, voice_home, supertonic_ready
    ):
        """GIVEN the second rung is usable
        THEN the package is built on this machine's asset folder without reaching for the
        network, and the synthesis is asked for exactly this sentence, style, language and
        step count — the stand-in engine is what records that."""
        from core.voice_config import SUPERTONIC_MODEL
        from core.voice_synth import write_supertonic_wav

        write_supertonic_wav(SUPERSONIC_TEXT)

        assert supertonic_ready["init"] == {
            "model": SUPERTONIC_MODEL,
            "model_dir": str(voice_home / "assets"),
            "auto_download": False,
        }
        call = supertonic_ready["call"]
        assert call["text"] == SUPERSONIC_TEXT
        assert call["voice"] == "M1"
        assert call["lang"] == "de"
        assert call["total_steps"] == 8

    def test_given_a_text_that_opens_with_a_dash_when_written_then_it_is_still_the_sentence(
        self, voice_home, supertonic_ready
    ):
        """GIVEN a sentence that opens with a dash, which a command-line parser would read
        as one of its own options
        THEN it still arrives as the sentence to speak: nothing here is a command line."""
        from core.voice_synth import write_supertonic_wav

        tricky = "--steps 9999"
        write_supertonic_wav(tricky)

        assert supertonic_ready["call"]["text"] == tricky
        assert supertonic_ready["call"]["total_steps"] == 8

    def test_given_a_synthesis_when_written_then_no_command_line_is_built(
        self, voice_home, supertonic_ready, monkeypatch
    ):
        """GIVEN the rung speaks in process
        THEN no process is started to speak it: this is the shape the old CLI call had, and
        the sentence must never be able to return to one."""
        import subprocess as _subprocess

        from core.voice_synth import write_supertonic_wav

        def refused(*_args, **_kwargs):
            raise AssertionError("the second rung started a process")

        monkeypatch.setattr(_subprocess, "run", refused)
        write_supertonic_wav(SUPERSONIC_TEXT)
        assert supertonic_ready["call"]["text"] == SUPERSONIC_TEXT

    def test_given_a_text_without_content_when_written_then_the_rung_refuses_it(
        self, voice_home, supertonic_ready
    ):
        """GIVEN a text that is empty or carries a NUL byte
        THEN the rung refuses before the package is asked for anything, because neither is
        a sentence."""
        import pytest

        from core.voice_synth import write_supertonic_wav

        for unusable in ("", "a sentence with \x00 in it"):
            with pytest.raises(RuntimeError):
                write_supertonic_wav(unusable)
        assert "call" not in supertonic_ready

    def test_given_a_text_past_the_bound_when_written_then_the_refusal_names_the_bound(
        self, voice_home, supertonic_ready
    ):
        """GIVEN a text longer than one synthesis is meant to speak
        THEN the refusal names both numbers, so the caller learns the limit from the answer."""
        import pytest

        from core.voice_config import SUPERTONIC_TEXT_MAX
        from core.voice_synth import write_supertonic_wav

        with pytest.raises(RuntimeError) as refused:
            write_supertonic_wav("a" * (SUPERTONIC_TEXT_MAX + 1))
        assert str(SUPERTONIC_TEXT_MAX) in str(refused.value)
        assert "call" not in supertonic_ready

    def test_given_configured_rung_when_written_then_the_synthesis_follows_the_config(
        self, voice_home, supertonic_ready
    ):
        """GIVEN voice.json carries another style, language and step count
        THEN those exact values reach the synthesis: the call is built from voice.json."""
        from core.voice_config import save_voice_config
        from core.voice_synth import write_supertonic_wav

        save_voice_config(supertonic_voice="F1", supertonic_lang="en", supertonic_steps=16)
        write_supertonic_wav(SUPERSONIC_TEXT)

        call = supertonic_ready["call"]
        assert call["voice"] == "F1"
        assert call["lang"] == "en"
        assert call["total_steps"] == 16

    @pytest.mark.parametrize("value", ["../etc/passwd", "-voice", "a b", "x" * 33])
    def test_given_a_name_the_package_cannot_look_up_when_written_then_no_synthesis_starts(
        self, voice_home, supertonic_ready, value
    ):
        """GIVEN voice.json holds a style name that is not one name to look up
        THEN the rung refuses before the package opens anything: the name becomes a file
        name inside the asset folder, so a separator or a dash is refused here, not there."""
        import pytest

        from core.voice_synth import write_supertonic_wav

        self._edit_the_file(voice_home, supertonic_voice=value)
        with pytest.raises(RuntimeError, match="supertonic_voice"):
            write_supertonic_wav(SUPERSONIC_TEXT)
        assert supertonic_ready.get("voices", []) == []

    def test_given_steps_outside_the_bounds_when_written_then_no_synthesis_starts(
        self, voice_home, supertonic_ready
    ):
        """GIVEN voice.json holds a step count past what the rung allows
        THEN the refusal names the field and the package is never asked to build a graph run."""
        import pytest

        from core.voice_synth import write_supertonic_wav

        self._edit_the_file(voice_home, supertonic_steps=999)
        with pytest.raises(RuntimeError, match="supertonic_steps"):
            write_supertonic_wav(SUPERSONIC_TEXT)
        assert "call" not in supertonic_ready

    def test_given_a_written_file_when_named_then_the_supertonic_stamp(self, voice_home, supertonic_ready):
        """GIVEN the rung wrote its WAV
        THEN it lands in the audio folder under a _supertonic.wav stamp, the way piper's
        _piper.wav names its own producer."""
        from core.voice_synth import audio_dir, write_supertonic_wav

        target = write_supertonic_wav(SUPERSONIC_TEXT)

        assert target.parent == audio_dir()
        assert target.name.startswith("tts_") and target.name.endswith("_supertonic.wav")

    def test_given_two_sentences_when_written_then_the_graphs_are_loaded_once(
        self, voice_home, supertonic_ready
    ):
        """GIVEN the same folder is asked for two syntheses
        THEN the model is built once: the graphs are the slow half of this rung and a call
        per sentence would pay the load again for every word the assistant speaks."""
        from core.voice_synth import write_supertonic_wav

        write_supertonic_wav(SUPERSONIC_TEXT)
        write_supertonic_wav("Zweiter Satz.")

        assert len(supertonic_ready["inits"]) == 1

    def test_given_a_voice_style_the_folder_does_not_hold_when_written_then_the_refusal_names_the_folder(
        self, voice_home, supertonic_ready
    ):
        """GIVEN voice.json names a style the install did not bring
        THEN the refusal says which name is missing and which folder was looked in."""
        import pytest

        from core.voice_synth import write_supertonic_wav

        self._edit_the_file(voice_home, supertonic_voice="M9")
        with pytest.raises(RuntimeError) as caught:
            write_supertonic_wav(SUPERSONIC_TEXT)

        message = str(caught.value)
        assert "M9" in message
        assert str(voice_home / "assets" / "voice_styles") in message

    def test_given_a_failing_synthesis_when_written_then_the_reason_is_named(
        self, voice_home, supertonic_ready
    ):
        """GIVEN the package raises while synthesizing
        THEN the caller gets the package's own words in a refusal rather than a traceback."""
        import pytest

        from core.voice_synth import write_supertonic_wav

        supertonic_ready["raise"] = "onnxruntime cannot load the graph"
        with pytest.raises(RuntimeError, match="onnxruntime cannot load the graph"):
            write_supertonic_wav(SUPERSONIC_TEXT)

    def test_given_a_writer_without_its_audio_module_when_written_then_the_module_is_named(
        self, voice_home, supertonic_ready
    ):
        """GIVEN a partial install where the WAV writer cannot import the module it needs
        THEN the refusal says what is missing, which is the one thing the user can install."""
        import pytest

        from core.voice_synth import write_supertonic_wav

        supertonic_ready["write"] = _NO_SOUNDFILE
        with pytest.raises(RuntimeError) as caught:
            write_supertonic_wav(SUPERSONIC_TEXT)
        assert "soundfile" in str(caught.value)

    def test_given_a_header_only_file_when_written_then_no_audio_data(self, voice_home, supertonic_ready, monkeypatch):
        """GIVEN the writer leaves a WAV with a header and no samples
        THEN the rung refuses its own output instead of handing back a silent file."""
        import pytest

        from core.voice_synth import write_supertonic_wav

        supertonic_ready["write"] = _HEADER_ONLY
        with pytest.raises(RuntimeError, match="no audio data"):
            write_supertonic_wav(SUPERSONIC_TEXT)

    def test_given_a_run_without_output_when_written_then_no_audio_data(self, voice_home, supertonic_ready, monkeypatch):
        """GIVEN the writer never produces a file at all
        THEN the same refusal answers, so a silent success cannot reach the chat as a clip."""
        import pytest

        from core.voice_synth import write_supertonic_wav

        supertonic_ready["write"] = _NO_AUDIO
        with pytest.raises(RuntimeError, match="no audio data"):
            write_supertonic_wav(SUPERSONIC_TEXT)

    def test_given_no_package_when_written_then_the_package_half_answers_first(
        self, voice_home, fake_package, monkeypatch
    ):
        """GIVEN the weights are on disk but the package cannot be imported
        THEN the refusal names the package and its install command, and says nothing about
        assets the machine already has."""
        import pytest

        from core.voice_synth import write_supertonic_wav

        write_assets(voice_home / "assets")
        monkeypatch.setattr("core.voice_config.supertonic_package_available", lambda: False)

        with pytest.raises(RuntimeError) as caught:
            write_supertonic_wav(SUPERSONIC_TEXT)

        message = str(caught.value)
        assert "not importable" in message
        assert "pip install supertonic" in message
        assert "model assets" not in message
        assert "call" not in fake_package

    def test_given_package_without_assets_when_written_then_the_assets_half(
        self, voice_home, fake_package
    ):
        """GIVEN the package imports and one graph is missing
        THEN the refusal names the weights and the install verb, without sending anyone to
        reinstall a package that is already there."""
        import pytest

        from core.voice_synth import write_supertonic_wav

        write_assets(voice_home / "assets", skip="vocoder")

        with pytest.raises(RuntimeError) as caught:
            write_supertonic_wav(SUPERSONIC_TEXT)

        message = str(caught.value)
        assert "ephe voice install supertonic" in message
        assert "pip install" not in message
        assert "call" not in fake_package

    def _edit_the_file(self, voice_home, **fields) -> None:
        """Write voice.json by hand, past the settings screen's own checks."""
        import json

        from core import voice_config

        path = voice_config.voice_config_path()
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        data.update(fields)
        path.write_text(json.dumps(data), encoding="utf-8")


class TestSynthesizeLocalStaysLocal:
    def test_given_both_rungs_when_synthesized_then_supertonic_answers(
        self, voice_home, supertonic_ready, monkeypatch
    ):
        """GIVEN piper and supertonic can both speak
        THEN the tool uses the voice the owner chose and never starts the other rung."""
        from core.voice_synth import synthesize_local

        piper_argv = voice_home / "piper-argv.txt"
        monkeypatch.setenv("PIPER_ARGV_FILE", str(piper_argv))
        monkeypatch.setattr("core.voice_config.piper_binary", lambda: _executable(voice_home / "piper", _FAKE_PIPER))
        install_piper_voice(voice_home)

        answer = synthesize_local(SUPERSONIC_TEXT)

        marker, rung_line = answer.splitlines()
        assert marker.startswith("WAV_FILE:") and marker.endswith("_supertonic.wav")
        assert rung_line == "Spoken by supertonic: 44100 Hz, 1 channel, 0.10 s"
        assert not piper_argv.exists()

    def test_given_piper_voice_gone_when_synthesized_then_supertonic_answers(
        self, voice_home, supertonic_ready, monkeypatch
    ):
        """GIVEN piper's binary is there and its voice file is not
        THEN the tool falls to the second local rung and still returns a WAV marker."""
        from core.voice_synth import synthesize_local

        piper_argv = voice_home / "piper-argv.txt"
        monkeypatch.setenv("PIPER_ARGV_FILE", str(piper_argv))
        monkeypatch.setattr("core.voice_config.piper_binary", lambda: _executable(voice_home / "piper", _FAKE_PIPER))

        answer = synthesize_local(SUPERSONIC_TEXT)

        assert answer.splitlines()[0].endswith("_supertonic.wav")
        assert answer.splitlines()[1] == "Spoken by supertonic: 44100 Hz, 1 channel, 0.10 s"
        assert supertonic_ready["call"]["text"] == SUPERSONIC_TEXT

    def test_given_the_preferred_rung_fails_at_runtime_when_synthesized_then_piper_answers(
        self, voice_home, supertonic_ready, monkeypatch
    ):
        """GIVEN the preferred rung is installed and its synthesis fails
        THEN the ladder still walks to the other rung — a failed rung is a rung that cannot."""
        from core.voice_synth import synthesize_local

        monkeypatch.setenv("PIPER_ARGV_FILE", str(voice_home / "piper-argv.txt"))
        monkeypatch.setattr("core.voice_config.piper_binary", lambda: _executable(voice_home / "piper", _FAKE_PIPER))
        install_piper_voice(voice_home)
        supertonic_ready["raise"] = "onnxruntime cannot load the graph"

        answer = synthesize_local(SUPERSONIC_TEXT)

        assert answer.splitlines()[0].endswith("_piper.wav"), answer
        assert answer.splitlines()[1] == "Spoken by piper: 22050 Hz, 1 channel, 0.10 s"
        assert supertonic_ready["call"]["text"] == SUPERSONIC_TEXT

    def test_given_a_file_without_a_header_when_synthesized_then_no_number_is_invented(
        self, voice_home, supertonic_ready, monkeypatch
    ):
        """GIVEN a rung delivered bytes whose header cannot be read
        THEN the answer says so where a sample rate would stand."""
        from core.voice_synth import synthesize_local

        monkeypatch.setenv("PIPER_ARGV_FILE", str(voice_home / "piper-argv.txt"))
        supertonic_ready["write"] = _BAD_HEADER

        answer = synthesize_local(SUPERSONIC_TEXT)

        assert answer.splitlines()[0].startswith("WAV_FILE:")
        assert answer.splitlines()[1] == "Spoken by supertonic: sample rate unreadable"

    def test_given_both_rungs_missing_when_synthesized_then_both_halves_are_named(
        self, voice_home, monkeypatch
    ):
        """GIVEN neither rung can speak
        THEN the tool error carries each half with its own setup command, so the reader
        fixes what is actually missing."""
        from core.voice_synth import synthesize_local

        monkeypatch.setattr("core.voice_config.piper_binary", lambda: None)
        monkeypatch.setattr("core.voice_config.supertonic_package_available", lambda: False)

        answer = synthesize_local(SUPERSONIC_TEXT)

        assert answer.startswith("[tool-error 'synthesize': supertonic: supertonic not importable")
        assert "pip install supertonic" in answer
        assert "piper not found" in answer
        assert "pipx install piper-tts" in answer

    def test_given_both_rungs_missing_when_synthesized_then_no_cloud_and_no_file(
        self, voice_home, monkeypatch
    ):
        """GIVEN neither rung can speak and the engine would resolve to the cloud
        THEN `synthesize` still answers with a refusal: nothing leaves the machine unless
        the user's choice names a remote endpoint, and this tool has no such choice."""
        from core.voice_synth import audio_dir, synthesize_local

        monkeypatch.setattr("core.voice_config.piper_binary", lambda: None)
        monkeypatch.setattr("core.voice_config.supertonic_package_available", lambda: False)
        started: list[str] = []

        def no_exec(argv, **_kwargs):
            started.append(str(argv[0]))
            raise AssertionError("a local refusal must not start a process")

        monkeypatch.setattr("core.voice_synth.subprocess.run", no_exec)

        def never() -> str:
            raise AssertionError("the local tool asked the resolver for an engine")

        monkeypatch.setattr("core.voice_config.resolve_tts_engine", never)
        answer = synthesize_local(SUPERSONIC_TEXT)

        assert answer.startswith("[tool-error 'synthesize':")
        assert started == []
        assert not any(audio_dir().glob("*.wav"))

    def test_given_nothing_to_say_when_synthesized_then_the_empty_text_line(self, voice_home, supertonic_ready):
        """GIVEN the text is blank
        THEN the tool answers with its own empty-text line before either rung is started."""
        from core.voice_synth import synthesize_local

        assert synthesize_local("   ") == "[tool-error 'synthesize': text is empty]"
        assert "call" not in supertonic_ready


class TestVoiceCliSupertonic:
    def _fake_downloader(self, monkeypatch, *, leaves: bool = True, raises: str = "") -> list:
        """The package's own HuggingFace fetch, injected where the verb imports it.

        `leaves` says whether the folder ends up complete afterwards and `raises` makes the
        fetch fail outright, which are the two ways a download can end badly."""
        import types

        calls: list = []

        def download_model(model_dir, model_name=None):
            calls.append((str(model_dir), model_name))
            if raises:
                raise RuntimeError(raises)
            if leaves:
                write_assets(Path(model_dir))

        module = types.ModuleType("supertonic.loader")
        module.download_model = download_model
        monkeypatch.setitem(sys.modules, "supertonic.loader", module)
        monkeypatch.setattr("core.voice_config.supertonic_package_available", lambda: True)
        return calls

    def test_given_no_confirmation_when_install_then_nothing_is_written(self, voice_home, monkeypatch, capsys):
        """GIVEN the package is there, the weights are not, and the answer is no
        THEN the verb stops without downloading and leaves the asset folder uncreated."""
        import argparse

        import ephe_cli

        self._fake_downloader(monkeypatch)
        monkeypatch.setattr(ephe_cli, "_ask_yes_no", lambda _prompt: False)

        code = ephe_cli.cmd_voice(
            argparse.Namespace(voice_command="install", voices=["supertonic"], yes=False)
        )

        out = capsys.readouterr().out
        assert code != 0
        assert "Cancelled" in out
        assert not (voice_home / "assets").exists()

    def test_given_no_confirmation_when_install_then_the_fetch_is_stated_first(
        self, voice_home, monkeypatch, capsys
    ):
        """GIVEN the verb is about to ask
        THEN it has already said what it fetches, from where, under which licence, into
        which folder, and that it installs no package of its own."""
        import argparse

        import ephe_cli

        self._fake_downloader(monkeypatch)
        monkeypatch.setattr(ephe_cli, "_ask_yes_no", lambda _prompt: False)

        ephe_cli.cmd_voice(argparse.Namespace(voice_command="install", voices=["supertonic"], yes=False))

        out = capsys.readouterr().out
        assert "385 MB" in out
        assert "Supertone/supertonic-3" in out and "OpenRAIL-M" in out
        assert str(voice_home / "assets") in out
        assert "installs nothing" in out

    def test_given_yes_when_install_then_the_weights_land(self, voice_home, monkeypatch, capsys):
        """GIVEN --yes and a fetch that answers
        THEN the graphs are on disk afterwards and the verb reports OK, naming the folder."""
        import argparse

        import ephe_cli

        calls = self._fake_downloader(monkeypatch)

        code = ephe_cli.cmd_voice(
            argparse.Namespace(voice_command="install", voices=["supertonic"], yes=True)
        )

        out = capsys.readouterr().out
        assert code == 0 and "OK: supertonic" in out
        assert calls == [(str(voice_home / "assets"), "supertonic-3")]
        assert (voice_home / "assets" / "onnx" / "vocoder.onnx").is_file()

    def test_given_already_installed_when_install_then_nothing_is_fetched(self, voice_home, monkeypatch, capsys):
        """GIVEN the weights are already on disk
        THEN the verb says so and never reaches for the downloader."""
        import argparse

        import ephe_cli

        write_assets(voice_home / "assets")
        calls = self._fake_downloader(monkeypatch)

        code = ephe_cli.cmd_voice(
            argparse.Namespace(voice_command="install", voices=["supertonic"], yes=True)
        )

        assert code == 0
        assert "already" in capsys.readouterr().out
        assert calls == []

    def test_given_no_package_when_install_then_the_install_hint_and_no_write(self, voice_home, monkeypatch, capsys):
        """GIVEN the package cannot be imported
        THEN the verb refuses with the command that installs it rather than fetching weights
        nobody can load, and the asset folder stays uncreated."""
        import argparse

        import ephe_cli

        monkeypatch.setattr("core.voice_config.supertonic_package_available", lambda: False)

        code = ephe_cli.cmd_voice(
            argparse.Namespace(voice_command="install", voices=["supertonic"], yes=True)
        )

        out = capsys.readouterr().out
        assert code == 1
        assert "pip install supertonic" in out
        assert not (voice_home / "assets").exists()

    @pytest.mark.parametrize("raises", ["", "network unreachable"])
    def test_given_a_download_that_leaves_no_graphs_when_install_then_exit_one(
        self, voice_home, monkeypatch, capsys, raises
    ):
        """GIVEN the fetch ends without the graphs on disk, by raising or by answering quietly
        THEN the verb reports a failed download and never says the assets are in place."""
        import argparse

        import ephe_cli

        self._fake_downloader(monkeypatch, leaves=False, raises=raises)

        code = ephe_cli.cmd_voice(
            argparse.Namespace(voice_command="install", voices=["supertonic"], yes=True)
        )

        out = capsys.readouterr().out
        assert code == 1
        assert "did not finish" in out
        assert "OK:" not in out

    @pytest.mark.parametrize("answer", ["", "n", "no", "maybe", "yep"])
    def test_given_anything_but_yes_when_asked_then_no(self, monkeypatch, answer):
        """GIVEN a terminal answer other than y or yes
        THEN the confirmation reads as no, which is the only answer a 385 MB fetch accepts."""
        import ephe_cli

        monkeypatch.setattr("builtins.input", lambda _prompt: answer)
        assert ephe_cli._ask_yes_no("Download now? [y/N] ") is False

    @pytest.mark.parametrize("answer", ["y", "Y", "yes", " yes "])
    def test_given_an_affirmation_when_asked_then_yes(self, monkeypatch, answer):
        """GIVEN y or yes, in either case and with stray spaces
        THEN the confirmation reads as yes."""
        import ephe_cli

        monkeypatch.setattr("builtins.input", lambda _prompt: answer)
        assert ephe_cli._ask_yes_no("Download now? [y/N] ") is True

    def test_given_no_terminal_at_all_when_asked_then_no(self, monkeypatch):
        """GIVEN stdin is closed, as it is under a service or a bot
        THEN the answer is no rather than an exception out of the verb."""
        import ephe_cli

        def closed(_prompt: str) -> str:
            raise EOFError

        monkeypatch.setattr("builtins.input", closed)
        assert ephe_cli._ask_yes_no("Download now? [y/N] ") is False

    def test_given_the_piper_path_when_install_then_the_rung_name_does_not_interfere(
        self, voice_home, monkeypatch, capsys
    ):
        """GIVEN a piper voice name and the rung name in one command
        THEN the voice still goes down the piper path, which is where a voice belongs."""
        import argparse

        import ephe_cli

        seen: list[str] = []
        monkeypatch.setattr(ephe_cli, "_download_piper_voice", lambda name: seen.append(name))
        monkeypatch.setattr(ephe_cli, "_install_supertonic_assets", lambda _yes: 0)

        code = ephe_cli.cmd_voice(
            argparse.Namespace(voice_command="install", voices=["en_US-amy-medium", "supertonic"], yes=True)
        )

        assert code == 0
        assert seen == ["en_US-amy-medium"]

    def test_given_list_when_run_then_both_rungs_are_reported_as_they_are(self, voice_home, monkeypatch, capsys):
        """GIVEN piper is missing and supertonic has its package without its weights
        THEN `voice list` states each half of both rungs, with the command that fixes it."""
        import argparse

        import ephe_cli

        monkeypatch.setattr("core.voice_config.piper_binary", lambda: None)
        monkeypatch.setattr("core.voice_config.supertonic_package_available", lambda: True)

        code = ephe_cli.cmd_voice(argparse.Namespace(voice_command="list", voices=[], yes=False))

        out = capsys.readouterr().out
        assert code == 0
        assert "piper binary: NOT found" in out and "pipx install piper-tts" in out
        assert "supertonic package: importable" in out
        assert "supertonic model assets: NOT installed" in out
        assert "ephe voice install supertonic" in out

    def test_given_list_when_run_then_the_ladder_names_the_preferred_rung_first(
        self, voice_home, supertonic_ready, monkeypatch, capsys
    ):
        """GIVEN the ladder has a preferred voice and a fallback
        THEN `voice list` prints that order and the price of each rung, so a user picking a
        voice sees the wall clock this machine produced before picking one."""
        import argparse

        import ephe_cli

        monkeypatch.setattr("core.voice_config.piper_binary", lambda: "/usr/local/bin/piper")

        ephe_cli.cmd_voice(argparse.Namespace(voice_command="list", voices=[], yes=False))

        out = capsys.readouterr().out
        ladder = [line for line in out.splitlines() if line.startswith("ladder (auto):")]
        assert ladder == ["ladder (auto): supertonic -> piper -> edge"]
        assert "supertonic: 1.2 s per sentence" in out
        assert "piper: 0.42 s per sentence" in out
        assert out.index("supertonic: 1.2") < out.index("piper: 0.42")

    def test_given_both_halves_when_list_then_the_rung_reads_ready(self, voice_home, supertonic_ready, monkeypatch, capsys):
        """GIVEN the second rung is complete
        THEN the list reports the package importable and the assets installed."""
        import argparse

        import ephe_cli

        monkeypatch.setattr("core.voice_config.piper_binary", lambda: None)

        ephe_cli.cmd_voice(argparse.Namespace(voice_command="list", voices=[], yes=False))

        out = capsys.readouterr().out
        assert "supertonic package: importable" in out
        assert "supertonic model assets: installed" in out


class TestDoctorSupertonicRung:
    def test_given_piper_running_when_doctor_then_the_second_rung_is_reported(self, voice_home, monkeypatch):
        """GIVEN piper is the running engine and the second rung has no weights
        THEN the doctor row names the active engine and reports the rung's missing half."""
        import ephe_cli
        from core.voice_config import save_voice_config

        save_voice_config(tts_engine="piper", piper_voice="en_US-amy-medium")
        install_piper_voice(voice_home)
        monkeypatch.setattr("core.voice_config.piper_binary", lambda: "/usr/local/bin/piper")
        monkeypatch.setattr("core.transcribe.is_whisper_available", lambda: True)

        ok, detail = ephe_cli._doctor_voice()

        assert ok is True and detail.startswith("piper local")
        assert "supertonic not ready" in detail
        assert "model assets missing" in detail

    def test_given_the_second_rung_complete_when_doctor_then_the_row_reads_ready(
        self, voice_home, supertonic_ready, monkeypatch
    ):
        """GIVEN piper is running and the second rung has its binary and its weights
        THEN the row calls that rung ready; a check that only ever names what is missing
        cannot tell a machine that is set up from one that was never tried."""
        import ephe_cli
        from core.voice_config import save_voice_config

        save_voice_config(tts_engine="piper", piper_voice="en_US-amy-medium")
        install_piper_voice(voice_home)
        monkeypatch.setattr("core.voice_config.piper_binary", lambda: "/usr/local/bin/piper")
        monkeypatch.setattr("core.transcribe.is_whisper_available", lambda: True)

        ok, detail = ephe_cli._doctor_voice()

        assert ok is True and detail.startswith("piper local")
        assert "supertonic local ready" in detail
        assert "not ready" not in detail

    def test_given_supertonic_running_when_doctor_then_the_rung_names_its_settings(
        self, voice_home, supertonic_ready, monkeypatch
    ):
        """GIVEN the second rung is the running engine
        THEN the row says so with the style, language and steps it will speak with."""
        import ephe_cli
        from core.voice_config import save_voice_config

        save_voice_config(tts_engine="supertonic", supertonic_voice="M3", supertonic_lang="en", supertonic_steps=16)
        monkeypatch.setattr("core.transcribe.is_whisper_available", lambda: True)

        ok, detail = ephe_cli._doctor_voice()

        assert ok is True
        assert detail.startswith("supertonic local (M3/en, steps 16)")

    def test_given_nothing_local_when_doctor_then_the_cloud_row_still_lists_the_rung(
        self, voice_home, monkeypatch
    ):
        """GIVEN auto fell through to the cloud
        THEN the row keeps the cloud wording and still says which half of the second rung
        is missing, so a local path is discoverable from the check that reports it."""
        import ephe_cli
        from core.voice_config import save_voice_config

        save_voice_config(tts_engine="auto")
        monkeypatch.setattr("core.voice_config.piper_binary", lambda: None)
        monkeypatch.setattr("core.voice_config.supertonic_package_available", lambda: False)
        monkeypatch.setattr("core.transcribe.is_whisper_available", lambda: False)

        ok, detail = ephe_cli._doctor_voice()

        assert ok is True and "Edge cloud fallback" in detail
        assert "supertonic not ready" in detail
        assert "pip install supertonic" in detail
