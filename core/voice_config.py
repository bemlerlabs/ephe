"""Ephe – voice_config: voice settings (R18 offline voice loop).

One source: the ~/.ephe/image.json pattern → ~/.ephe/voice.json (no
secret, still 0600 like every config file). Kept separate from engine.json because
save_engine_config persists asdict(EngineChoice) and would discard foreign keys.

TTS engines (the ladder the owner approved 2026-11-18, then listened to on 2026-11-19 and
put the better voice first: supertonic → piper → edge):
  auto (default)  → supertonic when the package imports + model assets are installed, else piper when
                    binary + voice are installed, otherwise Edge (cloud fallback). `auto`
                    answers with Edge only after both local rungs have been looked at, so
                    a turn never leaves the machine while a local voice is available.
                    The chosen voice costs about fourteen times piper's wall time per
                    sentence; both numbers are printed by `ephe voice list`.
  piper           → strictly local; without setup an honest RuntimeError
  supertonic      → strictly local; without setup an honest RuntimeError
  edge            → explicit cloud opt-in (Edge-TTS fallback)

STT: faster-whisper (extra `voice`) — model tiny|base|small, language
auto|de|en (previously "de" was hardcoded — English inputs were made
worse by it).
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

# Read dynamically through the module (testable), as in core/image_config.py.
from core import engine_config

VALID_TTS_ENGINES = ("auto", "piper", "supertonic", "edge")
VALID_STT_MODELS = ("tiny", "base", "small")
VALID_STT_LANGUAGES = ("auto", "de", "en")
DEFAULT_PIPER_VOICE = "en_US-amy-medium"
DEFAULT_EDGE_VOICE = "de-DE-KillianNeural"
DEFAULT_SUPERTONIC_VOICE = "M1"
DEFAULT_SUPERTONIC_LANG = "de"
DEFAULT_SUPERTONIC_STEPS = 8

#: The model this product speaks with. The PyPI package ships no weights: the four graphs
#: below are what `ephe voice install supertonic` fetches (≈385 MB, OpenRAIL-M).
SUPERTONIC_MODEL = "supertonic-3"
SUPERTONIC_ONNX_GRAPHS = ("text_encoder", "duration_predictor", "vector_estimator", "vocoder")
#: The two non-graph files one synthesis opens, beside the four graphs, read from the folder a
#: real install leaves behind: the model config and the unicode indexer.
SUPERTONIC_SUPPORT_FILES = ("onnx/tts.json", "onnx/unicode_indexer.json")
#: The package's own bounds for the step count (supertonic.config MIN/MAX_TOTAL_STEPS).
SUPERTONIC_STEPS_MIN = 1
SUPERTONIC_STEPS_MAX = 100
#: One synthesis speaks a sentence, not a document. This is what keeps the wait inside the
#: page's patience, because a pass in this process cannot be interrupted from outside: measured
#: here 2026-11-19 on the reference machine, warm, 39,8 s at 3000 characters against 65,5 s at
#: 5000. The package would take 100 000; this product does not speak documents.
SUPERTONIC_TEXT_MAX = 3000


@dataclass
class VoiceConfig:
    tts_engine: str = "auto"
    piper_voice: str = DEFAULT_PIPER_VOICE
    edge_voice: str = DEFAULT_EDGE_VOICE
    #: The second local rung. A voice style name (`supertonic list-voices` lists them)
    #: and the language code handed to the CLI. `de` is the language this product's
    #: surface speaks; upstream's own default is `en`.
    supertonic_voice: str = DEFAULT_SUPERTONIC_VOICE
    supertonic_lang: str = DEFAULT_SUPERTONIC_LANG
    #: Vector-estimator steps, upstream's own default is 8. Measured here 2026-11-18:
    #: the same 3,34 s of German took 1,52 s wall at 8 and 2,28 s at 16.
    supertonic_steps: int = DEFAULT_SUPERTONIC_STEPS
    stt_model: str = "tiny"
    stt_language: str = "auto"
    #: Off by default: the speech model's weights are fetched from the hub, and
    #: nothing in this product reaches the network without the user saying so
    #: (README "optional online features are always opt-in"). Without it, the
    #: first transcription refuses and names the model, host and size instead of
    #: downloading. EPHE_STT_DOWNLOAD=1 is the shell-side spelling of the same
    #: consent (core/transcribe.stt_download_allowed).
    stt_allow_download: bool = False


def _int_or_default(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def voice_config_path():
    return engine_config.CONFIG_DIR / "voice.json"


def load_voice_config() -> VoiceConfig:
    try:
        raw = json.loads(voice_config_path().read_text(encoding="utf-8"))
        return VoiceConfig(
            tts_engine=str(raw.get("tts_engine", "auto") or "auto"),
            piper_voice=str(raw.get("piper_voice", "") or DEFAULT_PIPER_VOICE),
            edge_voice=str(raw.get("edge_voice", "") or DEFAULT_EDGE_VOICE),
            supertonic_voice=str(raw.get("supertonic_voice", "") or DEFAULT_SUPERTONIC_VOICE),
            supertonic_lang=str(raw.get("supertonic_lang", "") or DEFAULT_SUPERTONIC_LANG),
            supertonic_steps=_int_or_default(
                raw.get("supertonic_steps", DEFAULT_SUPERTONIC_STEPS), DEFAULT_SUPERTONIC_STEPS
            ),
            stt_model=str(raw.get("stt_model", "tiny") or "tiny"),
            stt_language=str(raw.get("stt_language", "auto") or "auto"),
            stt_allow_download=bool(raw.get("stt_allow_download", False)),
        )
    except Exception:
        return VoiceConfig()


def save_voice_config(
    tts_engine: str | None = None,
    piper_voice: str | None = None,
    edge_voice: str | None = None,
    supertonic_voice: str | None = None,
    supertonic_lang: str | None = None,
    supertonic_steps: int | None = None,
    stt_model: str | None = None,
    stt_language: str | None = None,
    stt_allow_download: bool | None = None,
    path=None,
) -> VoiceConfig:
    existing = load_voice_config()
    cfg = VoiceConfig(
        tts_engine=(tts_engine if tts_engine is not None else existing.tts_engine),
        piper_voice=(piper_voice if piper_voice is not None else existing.piper_voice),
        edge_voice=(edge_voice if edge_voice is not None else existing.edge_voice),
        supertonic_voice=(
            supertonic_voice if supertonic_voice is not None else existing.supertonic_voice
        ),
        supertonic_lang=(supertonic_lang if supertonic_lang is not None else existing.supertonic_lang),
        supertonic_steps=(
            _int_or_default(supertonic_steps, DEFAULT_SUPERTONIC_STEPS)
            if supertonic_steps is not None
            else existing.supertonic_steps
        ),
        stt_model=(stt_model if stt_model is not None else existing.stt_model),
        stt_language=(stt_language if stt_language is not None else existing.stt_language),
        stt_allow_download=(
            bool(stt_allow_download) if stt_allow_download is not None else existing.stt_allow_download
        ),
    )
    if cfg.tts_engine not in VALID_TTS_ENGINES:
        raise ValueError(f"Unknown TTS engine: {cfg.tts_engine!r} (allowed: {', '.join(VALID_TTS_ENGINES)})")
    if not cfg.supertonic_voice.strip():
        raise ValueError(
            "supertonic_voice is empty — set a voice style name, for example 'M1' "
            "(the CLI lists them: 'supertonic list-voices')."
        )
    if not cfg.supertonic_lang.strip():
        raise ValueError(
            "supertonic_lang is empty — set a language code Supertonic 3 knows, for example 'de'."
        )
    if not SUPERTONIC_STEPS_MIN <= cfg.supertonic_steps <= SUPERTONIC_STEPS_MAX:
        raise ValueError(
            f"supertonic_steps out of range: {cfg.supertonic_steps!r} "
            f"(allowed: {SUPERTONIC_STEPS_MIN}..{SUPERTONIC_STEPS_MAX}, the upstream CLI's own bounds)."
        )
    if cfg.stt_model not in VALID_STT_MODELS:
        raise ValueError(f"Unknown STT model: {cfg.stt_model!r} (allowed: {', '.join(VALID_STT_MODELS)})")
    if cfg.stt_language not in VALID_STT_LANGUAGES:
        raise ValueError(f"Unknown STT language: {cfg.stt_language!r} (allowed: {', '.join(VALID_STT_LANGUAGES)})")
    target = path or voice_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.parent.chmod(0o700)
    except OSError:
        pass
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return cfg


# Piper (local TTS)
# Deliberately NO piper-tts pip dependency (ONNX runtime is heavy — product promise:
# offline-first without forcing an ML framework). Instead the `piper` binary
# (pipx install piper-tts — Homebrew has no piper formula, measured 2026-11-18) + ONNX voices under
# ~/.ephe/voices, installable via `ephe voice install <name>`.

def piper_binary() -> str | None:
    # Stripped ONCE, before the truthiness test. The old `get(X) or get(X, "").strip()`
    # handed the un-stripped first operand to `Path(...).exists()`, so a path padded by a
    # quoted shell value (" /opt/bin/piper ") resolved to "no piper" and a whitespace-only
    # override shadowed the PATH lookup instead of reading as unset.
    override = os.environ.get("EPHE_PIPER_BIN", "").strip()
    if override:
        return override if Path(override).exists() else None
    return shutil.which("piper")


def piper_binary_available() -> bool:
    return piper_binary() is not None


def voices_dir() -> Path:
    """Where the Piper voices live. Reading this path must never create the folder:
    `ephe doctor` checks it on a fresh machine, and a probe that makes the state it
    reports turns "0 voices" into a folder the check itself brought into being."""
    return engine_config.CONFIG_DIR / "voices"


def ensure_voices_dir() -> Path:
    """The voices folder, created for the one caller that writes into it."""
    d = voices_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def piper_voice_installed(name: str) -> bool:
    return (voices_dir() / f"{name}.onnx").exists() and (voices_dir() / f"{name}.onnx.json").exists()


def list_installed_piper_voices() -> list[str]:
    return sorted(p.stem for p in voices_dir().glob("*.onnx"))


def piper_binary_setup() -> str:
    """The first piper refusal: the binary is the half that is missing."""
    return (
        "piper not found — setup: 'pipx install piper-tts' and 'ephe voice install <voice>'. "
        "Alternatively set tts_engine='edge' (cloud, opt-in)."
    )


def piper_voice_setup(voice: str, on_disk: list[str]) -> str:
    """The second piper refusal, for the half that is missing when piper itself is there.

    Both halves used to answer one sentence telling the reader to install piper, which
    sends someone who installed piper and never a voice to reinstall the binary they just
    installed. `ephe doctor` already separates the two checks; every caller reads them
    from here so the synth path, the resolver and the doctor cannot drift apart, and the
    sentence names what the folder does hold."""
    held = ", ".join(on_disk) if on_disk else "none"
    return (
        f"piper is installed; the voice '{voice}' is not — setup: "
        f"'ephe voice install {voice}'. Voices on disk: {held}."
    )


# Supertonic (the second local rung: supertonic-3, ONNX, 44 100 Hz mono output)
# Still no product dependency: the package pulls onnxruntime and the weights are a 385 MB
# OpenRAIL-M download, so both halves stay behind their own opt-in.

def supertonic_package_available() -> bool:
    """True when the synthesis package can be imported into the interpreter Ephe runs in.

    This rung speaks in process, the way the STT side loads faster-whisper: the sentence is a
    Python argument and no command line is built with it. The weights are the other half, so a
    machine with the package and no weights is not ready either.
    """
    import importlib.util

    try:
        return importlib.util.find_spec("supertonic") is not None
    except (ImportError, ValueError):
        return False


def supertonic_asset_dir() -> Path:
    """Where the Supertonic ONNX graphs live. Read-only like voices_dir(): a probe that
    creates the folder it reports turns "not installed" into installed."""
    override = os.environ.get("EPHE_SUPERTONIC_ASSET_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "supertonic3"


def supertonic_assets_installed() -> bool:
    """True only when the folder holds what one synthesis opens: the four graphs and the two
    files beside them. A partial folder is no engine. Nothing here downloads: the package's own
    loader would fetch the 385 MB weights on a first run, and that is never a side effect of a
    chat turn."""
    root = supertonic_asset_dir()
    graphs = all((root / "onnx" / f"{name}.onnx").is_file() for name in SUPERTONIC_ONNX_GRAPHS)
    support = all((root / name).is_file() for name in SUPERTONIC_SUPPORT_FILES)
    return graphs and support


def supertonic_package_setup() -> str:
    """The first supertonic refusal: the package is the half that is missing. It is optional,
    so the hint names the interpreter that has to carry it rather than installing anything."""
    return (
        "supertonic not importable — setup: install the package into the interpreter that runs "
        "Ephe ('python -m pip install supertonic' with it), then 'ephe voice install supertonic' "
        "for the weights. Alternatively set tts_engine='edge' (cloud, opt-in)."
    )


def supertonic_assets_setup() -> str:
    """The second supertonic refusal, for the half that is missing when the package
    imports: the weights. Names the folder the install verb writes into."""
    return (
        f"supertonic is installed; the model assets for '{SUPERTONIC_MODEL}' are not — setup: "
        f"'ephe voice install supertonic' (about 385 MB from HuggingFace into "
        f"{supertonic_asset_dir()})."
    )


#: The order the two local rungs are tried in, best voice first. The owner listened to all
#: five WAVs on 2026-11-18 and chose supertonic's voice over piper's, which costs time: on
#: this machine one sentence is 1,2 s of wall clock against piper's 0,42 s, 44.1 kHz against
#: 22.05 kHz. Both numbers are in `ephe voice list`, so the price stays visible.
LOCAL_RUNG_ORDER: tuple[str, ...] = ("supertonic", "piper")

#: Wall clock and sample rate per rung, measured on the reference machine with one and the
#: same sentence (the A/B WAVs in `ephe-demo/voice`), so the choice between the two voices is a
#: number and not a feeling: piper on 2026-11-18, supertonic on 2026-11-19 after the rung moved
#: in process, where the graphs stay loaded between sentences. `ephe voice list` prints these;
#: nothing re-measures them at run time, which would mean speaking a sentence to ask what a
#: sentence costs.
RUNG_MEASURED: dict[str, str] = {
    "supertonic": "1.2 s per sentence, 3.0 s with the graphs cold, 44.1 kHz (measured 2026-11-19)",
    "piper": "0.42 s per sentence, 22.05 kHz (measured 2026-11-18)",
}


def rung_ready(engine: str, voice: str) -> bool:
    """Whether one named rung can answer on this machine as it stands."""
    if engine == "supertonic":
        return supertonic_package_available() and supertonic_assets_installed()
    if engine == "piper":
        return piper_binary_available() and piper_voice_installed(voice)
    return False


def local_rungs() -> tuple[str, ...]:
    """The rungs that can answer here, in the order they should be tried."""
    cfg = load_voice_config()
    return tuple(
        engine for engine in LOCAL_RUNG_ORDER if rung_ready(engine, cfg.piper_voice)
    )


def resolve_tts_engine() -> str:
    """Effective engine after voice.json + system state (raises on a strict local engine
    without setup — honest instead of silent cloud use)."""
    cfg = load_voice_config()
    if cfg.tts_engine == "edge":
        return "edge"
    if cfg.tts_engine == "piper":
        if not piper_binary_available():
            raise RuntimeError(piper_binary_setup())
        if not piper_voice_installed(cfg.piper_voice):
            raise RuntimeError(piper_voice_setup(cfg.piper_voice, list_installed_piper_voices()))
        return "piper"
    if cfg.tts_engine == "supertonic":
        if not supertonic_package_available():
            raise RuntimeError(supertonic_package_setup())
        if not supertonic_assets_installed():
            raise RuntimeError(supertonic_assets_setup())
        return "supertonic"
    # auto: the local rungs answer before the cloud, best voice first, in one shared order.
    rungs = local_rungs()
    return rungs[0] if rungs else "edge"
