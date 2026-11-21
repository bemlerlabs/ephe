"""Ephe – R39: create_video — wrapper around the demo media recorder.

``scripts/record_demo.py`` runs as a subprocess with the same interpreter and
delivers the README artifacts (WebP clips + hero PNG). The wrapper is deliberately
thin: parsing only for the file listing, otherwise an honest pass-through of
stdout/stderr.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys

#: Single-clip cases of record_demo.py. Without a case the same script runs with no
#: argument, which is its own "all cases" mode.
_RECORD_CASES: frozenset[str] = frozenset({"chat", "shell", "help", "edit"})
_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
_RECORDER = os.path.join(_ROOT, "scripts", "record_demo.py")
_TIMEOUT_SECONDS = 180


#: A produced file reaches the artifact library only through its marker; the
#: recorder's stdout names paths inside prose, and prose is what the store cannot open.
_OUTPUT_PATH = re.compile(r"(\S+\.(?:png|gif|webp|webm))", re.IGNORECASE)
_OUTPUT_MARKERS: dict[str, str] = {
    ".png": "PNG_FILE:",
    ".gif": "VIDEO_FILE:",
    ".webp": "VIDEO_FILE:",
    ".webm": "VIDEO_FILE:",
}


def _marked_files(stdout: str) -> list[str]:
    """One marker line per produced file the recorder's stdout named.

    The recorder prints prose around the path (``WEBP chat: /out/t.webp (12 KB, 40
    Frames)``, ``chat: video=/out/t.webm``), and only the path may follow the colon:
    that is what ``artifact_store.register_artifact`` opens.
    """
    marked: list[str] = []
    for line in str(stdout or "").splitlines():
        found = _OUTPUT_PATH.search(line)
        if found is None:
            continue
        path = found.group(1).rsplit("=", 1)[-1].rstrip(").,")
        marker = _OUTPUT_MARKERS.get(os.path.splitext(path)[1].lower())
        if marker is None:
            continue
        entry = f"{marker}{path}"
        if entry not in marked:
            marked.append(entry)
    return marked


async def create_video(case: str | None = None) -> str:
    """Records the demo clips and returns the artifact paths.

    Args:
        case: optional 'chat'|'shell'|'help'|'edit' => single clip;
            without a value the recorder runs all four cases.

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
    if not os.path.isfile(_RECORDER):
        return f"[video-error: recorder missing — {_RECORDER} is not in this checkout]"
    argv = [sys.executable, _RECORDER] + ([case] if case else [])
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
    files = _marked_files(stdout)
    summary = "\n".join(files) if files else stdout.strip()

    hero = os.path.join(_ROOT, "docs", "screenshots", "hero-banner.png")
    if os.path.isfile(hero):
        summary += f"\nPNG_FILE:{hero}"
    return summary or "[video-error: pipeline produced no output]"
