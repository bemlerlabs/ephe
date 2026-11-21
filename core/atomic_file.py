"""One file into place, atomically — the doctrine of `atomic_publish` at file scale.

`atomic_publish.publish` moves a whole change set as one tree object. An adopted
artifact has no change set: it is a single file the reader asked to keep. The
same rule still applies — the destination either holds the previous bytes or the
complete new ones, never a half-written file.

The technique is the short form of the same idea: write beside the target under a
hidden temp name, flush and fsync it, then `os.replace` — one atomic rename on
the same filesystem. A crash before the rename leaves the destination untouched
and only a temp file that the next attempt overwrites.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
from pathlib import Path


def publish_file(source: str | Path, destination: str | Path) -> Path:
    """Copy ``source`` to ``destination`` atomically; return the destination.

    Raises whatever the copy hits (missing source, permissions) with the
    destination still at its previous state and no temp file left behind.
    """
    src = Path(source)
    dst = Path(destination)
    fd, temp_name = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".part", dir=str(dst.parent))
    try:
        with os.fdopen(fd, "wb") as out, src.open("rb") as inp:
            shutil.copyfileobj(inp, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_name, dst)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp_name)
        raise
    return dst
