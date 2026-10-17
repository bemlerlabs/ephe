"""Ephe – R39: create_video — wrapper around the existing demo media pipeline.

The pipeline (``scripts/create_demo_media.py`` v4, ``scripts/record_demo.py`` for
single clips) runs as a subprocess with the same interpreter and delivers the
README artifacts (GIFs + hero PNG). The wrapper is deliberately thin: parsing only
for the file listing, otherwise an honest pass-through of stdout/stderr.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys

#: Single-clip cases of record_demo.py; without a case => the v4 full pipeline.
_RECORD_CASES: frozenset[str] = frozenset({"chat", "shell", "help", "edit"})
_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
_PIPELINE = os.path.join(_ROOT, "scripts", "create_demo_media.py")
_RECORDER = os.path.join(_ROOT, "scripts", "record_demo.py")
_TIMEOUT_SECONDS = 180


async def create_video(case: str | None = None) -> str:
    """Records the demo clips and returns the artifact paths.

    Args:
        case: optional 'chat'|'shell'|'help'|'edit' => single clip via
            record_demo.py; without a value the v4 full pipeline runs
            (all clips + hero banner).

    Returns:
        Multi-line summary with the generated files;
        the hero banner additionally as a PNG_FILE marker.
    """
    if case is not None and case not in _RECORD_CASES:
        return (
            f"[video-error: unknown case '{case}' — allowed: "
            + ", ".join(sorted(_RECORD_CASES))
            + "]"
        )
    script = _RECORDER if case else _PIPELINE
    argv = [sys.executable, script] + ([case] if case else [])
    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            argv,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # TimeoutError / OSError — honest, no pseudo-complete
        return f"[video-error: {exc}]"
    if getattr(completed, "returncode", 1) != 0:
        tail = str(getattr(completed, "stderr", "") or "")[-300:]
        return f"[video-error: exit {completed.returncode} — {tail}]"

    stdout = str(getattr(completed, "stdout", "") or "")
    lines = [line for line in stdout.splitlines() if line.strip()]
    files = [line for line in lines if ".gif" in line or ".webm" in line or ".png" in line]
    summary = "\n".join(files) if files else stdout.strip()

    hero = os.path.join(_ROOT, "docs", "screenshots", "hero-banner.png")
    if os.path.isfile(hero):
        summary += f"\nPNG_FILE:{hero}"
    return summary or "[video-error: pipeline produced no output]"
