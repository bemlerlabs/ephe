"""Local speech the host can run.

Piper writes one WAV. The cloud fallback stays on the audio route.
A transcript reads one file already stored for this session.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from core.engine_config import config_root

_PIPER_SETUP = (
    "piper not found — setup: 'brew install piper' (or pipx install piper-tts) "
    "and 'ephe voice install <voice>'."
)


def audio_dir() -> Path:
    return Path(os.environ.get("EPHE_AUDIO_DIR") or config_root() / "sessions" / "audio")


def synthesize_local(text: str) -> str:
    spoken = (text or "").strip()
    if not spoken:
        return "[tool-error 'synthesize': text is empty]"
    try:
        target = write_piper_wav(spoken)
    except RuntimeError as exc:
        return f"[tool-error 'synthesize': {exc}]"
    return f"WAV_FILE:{target.name}"


def write_piper_wav(text: str) -> Path:
    """Write one local WAV and return its path. Raises RuntimeError when piper cannot."""
    from core.voice_config import (
        load_voice_config,
        piper_binary,
        piper_voice_installed,
        voices_dir,
    )

    cfg = load_voice_config()
    binary = piper_binary()
    if not binary or not piper_voice_installed(cfg.piper_voice):
        raise RuntimeError(_PIPER_SETUP)
    folder = audio_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = f"tts_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    target = folder / f"{stamp}_piper.wav"
    model = voices_dir() / f"{cfg.piper_voice}.onnx"
    proc = subprocess.run(
        [binary, "--model", str(model), "--output_file", str(target)],
        input=text.encode("utf-8"),
        capture_output=True,
        timeout=80,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="replace")[:200]
        raise RuntimeError(f"piper failed: {detail}")
    if not target.is_file() or target.stat().st_size <= 44:
        raise RuntimeError("piper delivered no audio data")
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
