"""The PyAV range the voice extra needs, and the installed stack actually opening a file.

PyAV 19 removed the `metadata_errors` argument to `av.open`; faster-whisper 1.2.1
still passes it when it decodes an upload. A fresh `pip install -e .[voice]` on
2026-10-27 resolved av 19.0.2 and every transcription answered
`[Transkriptions-Fehler: open() got an unexpected keyword argument
'metadata_errors']` — the second half of "nothing was transcribed" after the
recorder's webm-only MIME choice. The floor is verified from the source: av 14.4.0
declares `metadata_errors="strict"` in its open(), 19.0.0 removes it.
"""
from __future__ import annotations

import re
import tomllib
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_voice_extra_pins_pyav_below_the_release_that_removed_the_argument():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    voice = pyproject["project"]["optional-dependencies"]["voice"]
    specs = [req for req in voice if re.match(r"^av\b", req)]
    assert specs, f"the voice extra must name PyAV, got {voice}"

    from packaging.requirements import Requirement

    spec = Requirement(specs[0]).specifier
    assert spec.contains("14.4.0"), "the floor is where av.open gained metadata_errors"
    assert spec.contains("18.1.0"), "the version the lock resolves must stay allowed"
    assert not spec.contains("19.0.0"), "19 removed the argument faster-whisper passes"


def test_installed_pyav_opens_a_file_with_the_keyword_faster_whisper_passes(tmp_path):
    av = pytest.importorskip("av")

    probe = tmp_path / "probe.wav"
    with wave.open(str(probe), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 1600)

    container = av.open(str(probe), mode="r", metadata_errors="ignore")
    container.close()
