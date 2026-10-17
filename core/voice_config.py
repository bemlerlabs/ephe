"""Ephe – voice_config: voice settings (R18 offline voice loop).

One source: the ~/.ephe/image.json pattern → ~/.ephe/voice.json (no
secret, still 0600 like every config file). Kept separate from engine.json because
save_engine_config persists asdict(EngineChoice) and would discard foreign keys.

TTS engines:
  auto (default)  → piper when binary + voice are installed, otherwise Edge
                    (cloud fallback — preserves the existing behaviour)
  piper           → strictly local; without setup an honest RuntimeError
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

VALID_TTS_ENGINES = ("auto", "piper", "edge")
VALID_STT_MODELS = ("tiny", "base", "small")
VALID_STT_LANGUAGES = ("auto", "de", "en")
DEFAULT_PIPER_VOICE = "en_US-amy-medium"
DEFAULT_EDGE_VOICE = "de-DE-KillianNeural"


@dataclass
class VoiceConfig:
    tts_engine: str = "auto"
    piper_voice: str = DEFAULT_PIPER_VOICE
    edge_voice: str = DEFAULT_EDGE_VOICE
    stt_model: str = "tiny"
    stt_language: str = "auto"
    #: Off by default: the speech model's weights are fetched from the hub, and
    #: nothing in this product reaches the network without the user saying so
    #: (README "optional online features are always opt-in"). Without it, the
    #: first transcription refuses and names the model, host and size instead of
    #: downloading. EPHE_STT_DOWNLOAD=1 is the shell-side spelling of the same
    #: consent (core/transcribe.stt_download_allowed).
    stt_allow_download: bool = False


def voice_config_path():
    return engine_config.CONFIG_DIR / "voice.json"


def load_voice_config() -> VoiceConfig:
    try:
        raw = json.loads(voice_config_path().read_text(encoding="utf-8"))
        return VoiceConfig(
            tts_engine=str(raw.get("tts_engine", "auto") or "auto"),
            piper_voice=str(raw.get("piper_voice", "") or DEFAULT_PIPER_VOICE),
            edge_voice=str(raw.get("edge_voice", "") or DEFAULT_EDGE_VOICE),
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
        stt_model=(stt_model if stt_model is not None else existing.stt_model),
        stt_language=(stt_language if stt_language is not None else existing.stt_language),
        stt_allow_download=(
            bool(stt_allow_download) if stt_allow_download is not None else existing.stt_allow_download
        ),
    )
    if cfg.tts_engine not in VALID_TTS_ENGINES:
        raise ValueError(f"Unbekannte TTS-Engine: {cfg.tts_engine!r} (erlaubt: {', '.join(VALID_TTS_ENGINES)})")
    if cfg.stt_model not in VALID_STT_MODELS:
        raise ValueError(f"Unbekanntes STT-Modell: {cfg.stt_model!r} (erlaubt: {', '.join(VALID_STT_MODELS)})")
    if cfg.stt_language not in VALID_STT_LANGUAGES:
        raise ValueError(f"Unknown STT language: {cfg.stt_language!r} (erlaubt: {', '.join(VALID_STT_LANGUAGES)})")
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
# (brew install piper / pipx install piper-tts) + ONNX voices under
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
    d = engine_config.CONFIG_DIR / "voices"
    d.mkdir(parents=True, exist_ok=True)
    return d


def piper_voice_installed(name: str) -> bool:
    return (voices_dir() / f"{name}.onnx").exists() and (voices_dir() / f"{name}.onnx.json").exists()


def list_installed_piper_voices() -> list[str]:
    return sorted(p.stem for p in voices_dir().glob("*.onnx"))


def resolve_tts_engine() -> str:
    """Effective engine after voice.json + system state (raises on strict piper
    without setup — honest instead of silent cloud use)."""
    cfg = load_voice_config()
    if cfg.tts_engine == "edge":
        return "edge"
    if cfg.tts_engine == "piper":
        if not piper_binary_available():
            raise RuntimeError(
                "piper not found — setup: 'brew install piper' (or pipx install piper-tts) and 'ephe voice install <voice>'. Alternatively set tts_engine='edge' (cloud, opt-in)."
            )
        return "piper"
    # auto: local preferred, cloud as explicit fallback (existing behaviour)
    if piper_binary_available() and piper_voice_installed(cfg.piper_voice):
        return "piper"
    return "edge"
