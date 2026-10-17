"""
◑ Ephe – Audio transcription
core/transcribe.py

Local speech-to-text processing via faster-whisper.
100% local processing – no cloud call, no API key needed.

The model is *not* part of the install and *not* part of the start. A fresh
Ephe has no speech model on disk, and this module never fetches one on its
own: `faster_whisper.WhisperModel(<name>)` resolves its weights through
huggingface_hub and pulls them from huggingface.co on the first call (the
2026-10-15 first-start probe caught that, triggered from the server lifespan).
That is a network fetch the user never asked for, in a product whose front door
says "local-first", "no account requirement" and "optional online features are
always opt-in" (README), and whose AGENTS.md forbids a silent default. So the
fetch is gated the way the engine choice is (core/engine_config.py): explicit,
fail-closed, with an actionable hint and never a silent fallback.

Three states, one rule each:
  * the model is in the local cache  → load it, `local_files_only=True`, no network;
  * the model is missing, no consent → raise `STTModelNotAvailable`, naming the
    model, its repo, its host and its download size, plus how to allow it;
  * the model is missing, consent given (`EPHE_STT_DOWNLOAD=1` or the
    `stt_allow_download` setting in voice.json) → fetch it, and say so first.
`EPHE_OFFLINE=1` outranks consent: an offline process never reaches out.

Features:
  - Voice Activity Detection (VAD): silence → no expensive STT call
  - Async-compatible via asyncio.to_thread()
  - Cross-browser audio formats (webm, mp4, wav, m4a)

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import asyncio
import os
import wave
import struct
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Configuration

# R18: model + language come from voice.json (Settings → Voice).
# Before: "tiny"/"de" were hardcoded — English input got bent into German.
# "auto" lets faster-whisper detect the language.
WHISPER_MODEL = "tiny"  # Legacy default (voice.json wins)
WHISPER_LANGUAGE = "de"  # Legacy default (voice.json wins)
MIN_AUDIO_DURATION_S = 0.5  # Minimum length in seconds
VAD_SILENCE_THRESHOLD = 300  # RMS threshold for silence detection

#: The host faster-whisper resolves a model name against. Named here so the
#: refusal can tell the reader where the bytes would come from.
MODEL_HOST = "huggingface.co"

#: faster-whisper's own name → repository mapping (faster_whisper.utils._MODELS).
MODEL_REPOS: dict[str, str] = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
}

#: Download size per model, in MB — the sum of the repository's files as the
#: hub reports them (2026-10-15: tiny 78.2, base 147.9, small 486.2 MB). Shown
#: to the reader before anything is fetched, so it is worth being blunt about.
MODEL_SIZE_MB: dict[str, int] = {"tiny": 78, "base": 148, "small": 486}


def _env_flag(name: str) -> bool:
    """Same reading as core/net_guard.py `_env_flag` — one spelling of a flag."""
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def ephe_offline() -> bool:
    """``EPHE_OFFLINE=1`` — this process may not fetch anything, ever.

    Outranks every opt-in: a machine that declares itself offline must not
    reach out because a second setting said it could.
    """
    return _env_flag("EPHE_OFFLINE")


def _voice_stt_settings() -> tuple[str, str | None]:
    """(model, language|None) from voice.json — legacy constants as fallback."""
    try:
        from core.voice_config import load_voice_config

        cfg = load_voice_config()
        return cfg.stt_model, (None if cfg.stt_language == "auto" else cfg.stt_language)
    except Exception:
        return WHISPER_MODEL, WHISPER_LANGUAGE


def stt_download_allowed() -> bool:
    """Has the user allowed the speech model to be fetched?

    Two explicit sources, no default: ``EPHE_STT_DOWNLOAD=1`` for a shell, and
    the ``stt_allow_download`` switch in voice.json (Settings → Audio) for the
    desktop app, which inherits no shell environment.
    """
    if _env_flag("EPHE_STT_DOWNLOAD"):
        return True
    try:
        from core.voice_config import load_voice_config

        return bool(load_voice_config().stt_allow_download)
    except Exception:
        return False


# Model cache — read, never written, by this module.

def hf_cache_dir() -> Path:
    """The hub cache faster-whisper downloads into.

    Mirrors huggingface_hub's own resolution (HF_HUB_CACHE → HF_HOME/hub →
    $XDG_CACHE_HOME/huggingface/hub → ~/.cache/huggingface/hub) without
    importing it: this module has to import cleanly in an install that does
    not carry the `voice` extra.
    """
    hub = os.environ.get("HF_HUB_CACHE", "").strip()
    if hub:
        return Path(hub)
    hf_home = os.environ.get("HF_HOME", "").strip()
    if hf_home:
        return Path(hf_home) / "hub"
    xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "huggingface" / "hub"


def model_repo(model_name: str) -> str:
    """The hub repository a model name resolves to (a path/ref passes through)."""
    return MODEL_REPOS.get(model_name, model_name)


def model_is_cached(model_name: str) -> bool:
    """Is this model already on disk?

    A snapshot whose `model.bin` exists and is non-empty is the test: that is
    the file whose absence makes faster-whisper go to the network.
    """
    local = Path(model_name)
    if local.is_dir():
        return True
    repo = MODEL_REPOS.get(model_name)
    if repo is None:
        return False
    snapshots = hf_cache_dir() / ("models--" + repo.replace("/", "--")) / "snapshots"
    if not snapshots.is_dir():
        return False
    for revision in snapshots.iterdir():
        weights = revision / "model.bin"
        if weights.is_file() and weights.stat().st_size > 0:
            return True
    return False


class STTModelNotAvailable(RuntimeError):
    """The speech model is not on this machine and was not allowed to be fetched.

    Carries the facts the reader needs (model, repo, host, size) so a surface
    can name them without parsing a sentence, and its own message is already
    actionable for the log or an escaping traceback.
    """

    def __init__(self, model: str, *, reason: str = "not_opted_in") -> None:
        self.model = model
        self.repo = model_repo(model)
        self.host = MODEL_HOST
        self.size_mb = MODEL_SIZE_MB.get(model, 0)
        self.reason = reason
        super().__init__(self._sentence())

    def _sentence(self) -> str:
        where = f"~{self.size_mb} MB from {self.host}/{self.repo}" if self.size_mb else f"from {self.host}/{self.repo}"
        if self.reason == "offline":
            return (
                f"Speech model '{self.model}' ({where}) is not on this machine and "
                f"EPHE_OFFLINE=1 forbids the download — unset EPHE_OFFLINE to fetch it, "
                f"or put the model into the local cache first."
            )
        if self.reason == "fetch_failed":
            return (
                f"Speech model '{self.model}' ({where}) could not be fetched — check the "
                f"connection or the proxy settings, then try the transcription again."
            )
        return (
            f"Speech model '{self.model}' ({where}) is not on this machine, and Ephe does "
            f"not download it on its own — set EPHE_STT_DOWNLOAD=1 (with EPHE_OFFLINE unset) "
            f"or set stt_allow_download in voice.json, then try the transcription again."
        )


# Lazy loading of the Whisper model

_models: dict[str, object] = {}


def _load(model_name: str, *, fetch: bool):
    """Build the WhisperModel. `fetch=False` pins it to the local cache."""
    from faster_whisper import WhisperModel

    if fetch:
        logger.info(
            "Fetching speech model '%s' (%s, ~%s MB) from %s — allowed by EPHE_STT_DOWNLOAD "
            "or the stt_allow_download setting.",
            model_name,
            model_repo(model_name),
            MODEL_SIZE_MB.get(model_name, 0),
            MODEL_HOST,
        )
    return WhisperModel(
        model_name,
        device="cpu",
        compute_type="int8",
        local_files_only=not fetch,
    )


def _get_model(*, allow_download: bool | None = None):
    """
    Lazy-load of the faster-whisper model — cached per model name (R18:
    stt_model is selectable from voice.json, switching loads the other model).

    `allow_download=None` reads the user's setting; `False` never fetches (the
    turn-away path); `True` is an explicit caller consent. A cached model is
    always loaded with `local_files_only=True`, so the offline promise holds
    on the load path too.
    """
    model_name, _ = _voice_stt_settings()
    if model_name in _models:
        return _models[model_name]

    cached = model_is_cached(model_name)
    if not cached:
        if allow_download is False:
            raise STTModelNotAvailable(model_name, reason="not_opted_in")
        if ephe_offline():
            raise STTModelNotAvailable(model_name, reason="offline")
        if allow_download is None and not stt_download_allowed():
            raise STTModelNotAvailable(model_name, reason="not_opted_in")

    try:
        _models[model_name] = _load(model_name, fetch=not cached)
    except ImportError:
        raise RuntimeError(
            "faster-whisper is not installed. Install with: pip install faster-whisper"
        )
    except Exception as exc:
        # With nothing on disk the load *is* the fetch, so any failure here is the
        # fetch failing — and an obscure one. The route turns it into a sentence
        # that names the model and says to check the connection, instead of the
        # bracket line a bare exception used to become.
        if not cached:
            raise STTModelNotAvailable(model_name, reason="fetch_failed") from exc
        raise
    logger.info("Whisper model loaded.")
    return _models[model_name]


def warm_if_cached() -> bool:
    """Load the model only when it is already on disk — never fetches.

    The server's startup warmup used to call `_get_model()` unconditionally,
    which is what turned a fresh start into a download. This keeps the latency
    win for a machine that already has the model and drops the network path.
    """
    model_name, _ = _voice_stt_settings()
    if model_name in _models:
        return True
    if not model_is_cached(model_name):
        return False
    try:
        _get_model(allow_download=False)
        return True
    except Exception:  # a warmup may never break the start
        logger.debug("Whisper warmup skipped", exc_info=True)
        return False


# Voice Activity Detection

def _check_audio_has_voice(audio_path: Path) -> bool:
    """VAD check: does the audio carry speech?

    WAV files are measured (RMS); other formats pass conservatively, since
    Whisper runs its own VAD on them anyway.
    """
    if audio_path.suffix.lower() != ".wav":
        # For non-WAV: conservatively True (Whisper runs its own VAD)
        return True

    try:
        with wave.open(str(audio_path), "rb") as wf:
            n_frames = wf.getnframes()
            if n_frames == 0:
                return False

            framerate = wf.getframerate()
            duration = n_frames / framerate
            if duration < MIN_AUDIO_DURATION_S:
                return False

            # Compute RMS volume (sample taken from the middle)
            sample_frames = min(n_frames, framerate)  # at most 1 second
            wf.setpos(max(0, n_frames // 2 - sample_frames // 2))
            raw = wf.readframes(sample_frames)

            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()

            if sample_width == 2:
                fmt = f"<{len(raw) // 2}h"
                samples = struct.unpack(fmt, raw)
                # Mono mix
                if n_channels == 2:
                    samples = samples[::2]
                rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
                return rms > VAD_SILENCE_THRESHOLD

        return True  # Fallback: assume it is OK
    except Exception:
        return True  # In doubt: transcribe


# Transcription

def _transcribe_sync(audio_path: Path) -> str:
    """Synchronous transcription, called via asyncio.to_thread().

    Returns the transcribed text, or an empty string on silence.
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"audio file not found: {audio_path}")

    # VAD check: skip silence
    if not _check_audio_has_voice(audio_path):
        logger.info("VAD: no speech detected in %s", audio_path.name)
        return ""

    model = _get_model()

    _, language = _voice_stt_settings()
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=5,
        vad_filter=True,  # Whisper's own VAD filter
    )

    text_parts = []
    for segment in segments:
        text_parts.append(segment.text.strip())

    result = " ".join(text_parts).strip()
    logger.info(
        "Transkription (%s, %.1fs): '%s'",
        audio_path.name,
        info.duration,
        result[:80] + "…" if len(result) > 80 else result,
    )
    return result


async def transcribe(audio_path: Path) -> str:
    """Asynchronous transcription of an audio file.

    Runs in asyncio.to_thread() so the event loop is not blocked. The VAD check
    runs first: on pure silence no STT call and no model load happens.

    Raises:
        FileNotFoundError: audio file does not exist
        STTModelNotAvailable: the model is not on disk and no consent was given
        RuntimeError: faster-whisper not installed
    """
    return await asyncio.to_thread(_transcribe_sync, audio_path)


def is_whisper_available() -> bool:
    """Checks whether faster-whisper is installed and usable.

    Deliberately says nothing about the model: the package can be installed
    while the model is absent, which is the state a fresh install is in.
    """
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False
