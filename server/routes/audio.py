"""
◑ Ephe – audio route
server/routes/audio.py

POST /api/audio/transcribe → upload + local STT transcription.

Security:
  - file size ≤ 15 MB
  - MIME-type whitelist
  - path sandboxing (only inside ~/.ephe/sessions/audio/)
  - file name: {timestamp}_{uuid}.{ext} (no user input)

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from server.refusals import Refused

router = APIRouter(tags=["Audio"])

# Configuration

MAX_AUDIO_SIZE = 15 * 1024 * 1024  # 15 MB
ALLOWED_CONTENT_TYPES = {
    "audio/webm",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/m4a",
    "audio/x-m4a",
    "audio/ogg",
    "video/webm",  # Chrome sometimes sends video/webm for pure audio
}

# Extension mapping
CONTENT_TYPE_EXT = {
    "audio/webm": ".webm",
    "video/webm": ".webm",
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/m4a": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/ogg": ".ogg",
}


def _get_audio_dir() -> Path:
    """Audio directory from the env variable (for test isolation)."""
    return Path(
        os.environ.get("EPHE_AUDIO_DIR", str(Path.home() / ".ephe" / "sessions" / "audio"))
    )


# Response Models

class TranscribeResponse(BaseModel):
    text: str
    audio_url: str
    duration_hint: str


@router.post("/audio/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(..., description="Audio-Datei (webm, mp4, wav, m4a)"),
):
    """
    Receives audio from the frontend, stores it safely and transcribes it locally.

    Returns:
        text: the transcribed text
        audio_url: path for playing it back in the frontend
        duration_hint: "Sprachnachricht" or "Stille erkannt"
    """
    # Cut off the codec parameter: "audio/webm;codecs=opus" → "audio/webm"
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported audio type: '{content_type}'. "
                   f"allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}",
        )

    audio_bytes = await file.read()
    if len(audio_bytes) > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"audio too large ({len(audio_bytes) // 1024 // 1024} MB). "
                   f"maximum: {MAX_AUDIO_SIZE // 1024 // 1024} MB.",
        )

    if len(audio_bytes) == 0:
        raise Refused("audio_empty")

    # Invariant: no user input anywhere in the stored path
    audio_dir = _get_audio_dir()
    audio_dir.mkdir(parents=True, exist_ok=True)

    ext = CONTENT_TYPE_EXT.get(content_type, ".webm")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{timestamp}_{unique_id}{ext}"

    # Path-traversal guard
    target = (audio_dir / filename).resolve()
    if not str(target).startswith(str(audio_dir.resolve())):
        raise HTTPException(status_code=400, detail="invalid file path.")

    target.write_bytes(audio_bytes)

    # Imported outside the try it is handled in: a name bound only inside a try
    # and read in its own `except` is unbound when that import is what failed.
    # Kept a function-level import on purpose — `test_audio` patches
    # `core.transcribe.transcribe`, which only takes effect on attribute lookup.
    from core.transcribe import STTModelNotAvailable

    try:
        from core.transcribe import is_whisper_available, transcribe

        if not is_whisper_available():
            # Fallback: file stored, but no transcription possible
            return TranscribeResponse(
                text="[voice message – transcription not available. "
                     "install with: pip install faster-whisper]",
                audio_url=f"/audio/{filename}",
                duration_hint="voice message",
            )

        text = await transcribe(target)

        if not text:
            return TranscribeResponse(
                text="",
                audio_url=f"/audio/{filename}",
                duration_hint="Stille erkannt",
            )

        return TranscribeResponse(
            text=text,
            audio_url=f"/audio/{filename}",
            duration_hint="voice message",
        )

    except STTModelNotAvailable as exc:
        # The speech model is not on this machine and Ephe does not fetch it on
        # its own — or the fetch was allowed and could not be made. Both are
        # states the reader can move, so they travel as coded refusals naming
        # model, host and size, instead of a bracket sentence in the audio field
        # (first-start probe, 2026-10-15).
        code = (
            "audio_model_fetch_failed"
            if exc.reason == "fetch_failed"
            else "audio_model_download_required"
        )
        raise Refused(
            code,
            model=exc.model,
            size_mb=exc.size_mb,
            host=exc.host,
        ) from exc

    except Exception as exc:
        # The file is stored, but the transcription failed
        return TranscribeResponse(
            text=f"[Transkriptions-Fehler: {exc}]",
            audio_url=f"/audio/{filename}",
            duration_hint="Fehler",
        )

# Speech synthesis (R18: Piper local first, Edge only as an opt-in fallback).
# RAM: edge_tts (pulls in aiohttp) is only imported on the Edge path. Piper
# runs as a binary subprocess (no ML pip dependency in the product).

class SynthesizeRequest(BaseModel):
    text: str
    # None → voice.json (edge_voice). Explicit override for existing clients.
    voice: str | None = None

class SynthesizeResponse(BaseModel):
    audio_url: str


@router.post("/audio/synthesize", response_model=SynthesizeResponse)
async def synthesize_audio(req: SynthesizeRequest):
    """
    R18: speech synthesis with the engine chosen from voice.json.

    auto (default): Piper (local) when the binary + a voice are there — otherwise
    Edge as the cloud fallback (the existing behaviour). piper: strictly local
    (an honest 400 without setup). edge: an explicit cloud opt-in.
    """
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")

    # E5: the tts plugin gate — only EXPLICIT registry entries take effect (stock
    # parity: without a toggle speech synthesis stays unrestricted).
    # Extensions v2: the slug is called voice now; legacy tts entries are migrated
    # automatically by plugin_store.migrate_registry_items.
    try:
        from core import plugin_runtime

        if not plugin_runtime.is_plugin_active("voice"):
            raise HTTPException(status_code=403, detail="Text-to-speech is disabled (plugin 'voice' is off — enable it in Settings → Plugins)")
    except HTTPException:
        raise
    except Exception:
        pass

    from core.voice_config import load_voice_config, resolve_tts_engine

    cfg = load_voice_config()
    try:
        engine = resolve_tts_engine()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    audio_dir = _get_audio_dir()
    audio_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"tts_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    if engine == "piper":
        target = audio_dir / f"{stamp}_piper.wav"
        try:
            from core.voice_config import piper_binary, voices_dir

            binary = piper_binary()
            model = voices_dir() / f"{cfg.piper_voice}.onnx"
            proc = await asyncio.create_subprocess_exec(
                binary, "--model", str(model), "--output_file", str(target),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(text.encode("utf-8")), timeout=90)
            if proc.returncode != 0:
                raise RuntimeError(f"piper failed: {stderr.decode(errors='replace')[:200]}")
            if not target.exists() or target.stat().st_size <= 44:
                raise RuntimeError("piper delivered no audio data")
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise Refused("tts_failed", error=str(exc))
        return SynthesizeResponse(audio_url=f"/audio/{target.name}")

    # Edge cloud fallback (opt-in behaviour: engine=edge or auto-without-piper)
    filename = f"{stamp}.mp3"
    target = audio_dir / filename
    try:
        import edge_tts
        voice = req.voice or cfg.edge_voice
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(target))
        return SynthesizeResponse(audio_url=f"/audio/{filename}")
    except Exception as exc:
        raise Refused("tts_failed", error=str(exc))
