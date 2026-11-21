"""Local speech the host can run.

Piper and supertonic each write one WAV; the ladder stops with them. The cloud fallback
stays on the audio route, where the user's choice named a remote endpoint.
A transcript reads one file already stored for this session.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path

from core.engine_config import config_root


def audio_dir() -> Path:
    return Path(os.environ.get("EPHE_AUDIO_DIR") or config_root() / "sessions" / "audio")


def _spoken_facts(target: Path) -> str:
    """Sample rate, channels and length, read back from the header the writer just produced.

    The tool answer names the rung because the answer is what the model reads. Measured
    2026-11-19: a report of a bare path left the model to guess, and it told the owner a cloud
    service had spoken while the local rung had written the file in 1,2 s on this machine.
    """
    import wave

    try:
        with wave.open(str(target), "rb") as handle:
            frames, rate, channels = (
                handle.getnframes(),
                handle.getframerate(),
                handle.getnchannels(),
            )
    except Exception:
        return "sample rate unreadable"
    if not rate:
        return "sample rate unreadable"
    return f"{rate} Hz, {channels} channel{'s' if channels != 1 else ''}, {frames / rate:.2f} s"


def synthesize_local(text: str) -> str:
    spoken = (text or "").strip()
    if not spoken:
        return "[tool-error 'synthesize': text is empty]"
    # Local-only by contract: `edge` is a remote endpoint, so when every local rung fails this
    # answers with a refusal naming each half instead of letting the text leave. The order is
    # the one `voice_config` owns, so the route and the tool never disagree about who speaks.
    from core.voice_config import LOCAL_RUNG_ORDER, local_rungs

    writers = {"supertonic": write_supertonic_wav, "piper": write_piper_wav}
    # When the readiness probe finds nothing, both writers are still asked, because the
    # refusal that reaches the model has to carry the reason each one gave.
    rungs = local_rungs() or LOCAL_RUNG_ORDER
    failures: list[str] = []
    for engine in rungs:
        try:
            target = writers[engine](spoken)
        except RuntimeError as exc:
            failures.append(f"{engine}: {exc}")
            continue
        # The full path, not the file name: the artifact registration resolves what the
        # marker carries, and a bare name resolves against the server's working directory.
        # The marker stays alone on its line; the rung line is the second one.
        return f"WAV_FILE:{target}\nSpoken by {engine}: {_spoken_facts(target)}"
    return f"[tool-error 'synthesize': {' | '.join(failures)}]"


#: Piper's own bound. The cloud path's bound in `server/routes/audio.py` sits above this
#: one and below the page's `advanced.api_timeout`, so a synthesis always answers first.
PIPER_TIMEOUT_SECONDS = 80


def _stamp() -> str:
    return f"tts_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def write_piper_wav(text: str) -> Path:
    """Write one local WAV and return its path. Raises RuntimeError when piper cannot."""
    from core.voice_config import (
        list_installed_piper_voices,
        load_voice_config,
        piper_binary,
        piper_binary_setup,
        piper_voice_installed,
        piper_voice_setup,
        voices_dir,
    )

    cfg = load_voice_config()
    binary = piper_binary()
    if binary is None:
        raise RuntimeError(piper_binary_setup())
    if not piper_voice_installed(cfg.piper_voice):
        raise RuntimeError(piper_voice_setup(cfg.piper_voice, list_installed_piper_voices()))
    folder = audio_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{_stamp()}_piper.wav"
    model = voices_dir() / f"{cfg.piper_voice}.onnx"
    proc = subprocess.run(
        [binary, "--model", str(model), "--output_file", str(target)],
        input=text.encode("utf-8"),
        capture_output=True,
        timeout=PIPER_TIMEOUT_SECONDS,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="replace")[:200]
        raise RuntimeError(f"piper failed: {detail}")
    if not target.is_file() or target.stat().st_size <= 44:
        raise RuntimeError("piper delivered no audio data")
    return target


#: The wall clock one local synthesis may spend before the route answers with a refusal. The
#: second rung runs its graphs in this process, where a pass cannot be stopped from outside, so
#: its bound is the sentence length and this net over it. Measured here 2026-11-19 on the
#: reference machine: 1,2 s for a sentence with the graphs warm, 3,0 s with them cold, 39,8 s
#: at the text bound — all inside this, and inside the route's own bound below.
SUPERTONIC_SYNTHESIS_SECONDS = 60

#: What a voice style name and a language code may look like. Both arrive from a config file the
#: user can edit, and the voice name becomes a file name inside the asset folder, so a path
#: separator or a leading dot has to be refused before anything opens it.
_SUPERTONIC_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}")

#: One synthesis at a time. The graphs stay loaded in this process, so two passes would ask the
#: machine for that memory twice while a cut is rendering beside them.
_SUPERTONIC_LOCK = threading.Lock()
_supertonic_engine: "tuple[str, object] | None" = None


def check_supertonic_request(text: str, cfg) -> None:
    """The bounds one supertonic call may carry, checked on every call.

    `voice_config` enforces the same numbers when the settings screen saves; they are repeated
    here because voice.json is a file the user can edit by hand.
    """
    from core.voice_config import SUPERTONIC_STEPS_MAX, SUPERTONIC_STEPS_MIN, SUPERTONIC_TEXT_MAX

    if not text or "\x00" in text:
        raise RuntimeError("supertonic needs a sentence without a NUL byte to speak")
    if len(text) > SUPERTONIC_TEXT_MAX:
        raise RuntimeError(
            f"text is too long for one synthesis: {len(text)} characters "
            f"(allowed: {SUPERTONIC_TEXT_MAX})."
        )
    for name, value in (
        ("supertonic_voice", cfg.supertonic_voice),
        ("supertonic_lang", cfg.supertonic_lang),
    ):
        if not _SUPERTONIC_TOKEN.fullmatch(value):
            raise RuntimeError(
                f"{name} is not a name supertonic can look up: {value!r} "
                "(letters, digits, dot, dash, underscore, 1-32 characters, starting with a letter "
                "or digit)."
            )
    if not SUPERTONIC_STEPS_MIN <= int(cfg.supertonic_steps) <= SUPERTONIC_STEPS_MAX:
        raise RuntimeError(
            f"supertonic_steps out of range: {cfg.supertonic_steps!r} "
            f"(allowed: {SUPERTONIC_STEPS_MIN}..{SUPERTONIC_STEPS_MAX})."
        )


def supertonic_backend():
    """The synthesis class behind one import, which is also the seam the suite speaks through."""
    from supertonic import TTS

    return TTS


def supertonic_engine(model_dir: Path):
    """The loaded graphs, kept for the life of the process.

    `auto_download=False` is the point: a chat turn that finds the weights missing gets the
    refusal from `supertonic_assets_setup`, never a 385 MB fetch as a side effect.
    """
    global _supertonic_engine

    from core.voice_config import SUPERTONIC_MODEL

    key = str(model_dir)
    cached = _supertonic_engine
    if cached is not None and cached[0] == key:
        return cached[1]
    engine = supertonic_backend()(model=SUPERTONIC_MODEL, model_dir=key, auto_download=False)
    _supertonic_engine = (key, engine)
    return engine


def write_supertonic_wav(text: str) -> Path:
    """Write one local WAV through the package's own synthesis and return its path.

    The sentence is a Python argument here, never a word of a command line; the STT side has
    always loaded its model the same way. Raises RuntimeError when supertonic cannot, the two
    halves answering separately the way the piper path does."""
    from core.voice_config import (
        load_voice_config,
        supertonic_asset_dir,
        supertonic_assets_installed,
        supertonic_assets_setup,
        supertonic_package_available,
        supertonic_package_setup,
    )

    cfg = load_voice_config()
    if not supertonic_package_available():
        raise RuntimeError(supertonic_package_setup())
    if not supertonic_assets_installed():
        raise RuntimeError(supertonic_assets_setup())
    check_supertonic_request(text, cfg)
    folder = audio_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{_stamp()}_supertonic.wav"
    model_dir = supertonic_asset_dir()
    with _SUPERTONIC_LOCK:
        engine = supertonic_engine(model_dir)
        try:
            style = engine.get_voice_style(cfg.supertonic_voice)
            wav, _duration = engine.synthesize(
                text,
                voice_style=style,
                total_steps=int(cfg.supertonic_steps),
                lang=cfg.supertonic_lang,
            )
            engine.save_audio(wav, str(target))
        except ImportError as exc:
            # save_audio reaches for soundfile, which the package needs and a partial
            # install can still leave out; the caller learns which piece is missing.
            raise RuntimeError(f"supertonic could not write the WAV: {exc}") from exc
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"supertonic has no voice style '{cfg.supertonic_voice}' in "
                f"{model_dir / 'voice_styles'}: {str(exc)[:200]}"
            ) from exc
    # 44 100 Hz mono PCM carries the same 44-byte header as piper's 22 050 Hz output, so
    # that floor means what it means there: a WAV with no samples in it.
    if not target.is_file() or target.stat().st_size <= 44:
        raise RuntimeError("supertonic delivered no audio data")
    return target


def resolve_audio_name(name: str) -> Path:
    raw = (name or "").strip()
    if not raw or raw in {".", ".."} or "/" in raw or "\\" in raw:
        raise ValueError("that audio file is not in this session")
    root = audio_dir().resolve()
    path = (root / raw).resolve()
    if path.parent != root:
        raise ValueError("that audio file is not in this session")
    return path


def transcribe_file(name: str) -> str:
    try:
        path = resolve_audio_name(name)
    except ValueError as exc:
        return f"[tool-error 'transcribe': {exc}]"
    if not path.is_file():
        return "[tool-error 'transcribe': audio file not found]"
    try:
        from core.transcribe import _transcribe_sync

        text = _transcribe_sync(path)
    except Exception as exc:
        return f"[tool-error 'transcribe': {type(exc).__name__}]"
    if not (text or "").strip():
        return "[tool-error 'transcribe': no speech detected]"
    return text
