"""One portfolio scan per window, so one request asks the folders once.

`plugins_view` reads the same scan three times — the installed rows, the catalogue
manifest facts and the state usage — and each read parsed every manifest in the
portfolio (3 scans, 69 parses, measured in `/tmp/rel/PERF-BE-REPORT.md` §3.3). This
module holds one scan for a short window and hands out copies of its rows.

The window is keyed by the folders themselves: each root's children and each
manifest's `(mtime, size)`, which is exactly what `scan_plugins` reads. A bundle
copied in, removed or edited moves the signature and the next read scans again; the
time window is the ceiling for a change the signature cannot see, such as a rewrite
that keeps both `mtime` and size. The switch state is not part of the scan and is
read per request, so a toggle never waits for this window.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

#: Upper bound on how long a scan may be reused. A signature change retires it sooner.
SCAN_TTL_SECONDS = 2.0

_lock = threading.Lock()
_cached: tuple[tuple[Any, ...], float, list[dict[str, Any]]] | None = None


def _roots() -> list[Path]:
    """The roots `scan_plugins(None)` would read, resolved the same way."""
    from core import plugin_manifest

    if plugin_manifest.PLUGINS_ROOT_OVERRIDE is not None:
        return [Path(plugin_manifest.PLUGINS_ROOT_OVERRIDE)]
    return [plugin_manifest.plugins_root(), plugin_manifest.builtin_plugins_root()]


def _signature() -> tuple[Any, ...]:
    """What one scan reads, without parsing a manifest: names and manifest metadata."""
    from core import plugin_manifest

    manifests = []
    for base in _roots():
        try:
            children = sorted(path for path in base.iterdir() if path.is_dir())
        except OSError:
            manifests.append((str(base), None))
            continue
        rows = []
        for child in children:
            try:
                stat = (child / plugin_manifest.MANIFEST_FILENAME).stat()
                rows.append((child.name, stat.st_mtime_ns, stat.st_size))
            except OSError:
                rows.append((child.name, None, None))
        manifests.append((str(base), tuple(rows)))
    return tuple(manifests)


def scan() -> list[dict[str, Any]]:
    """The portfolio rows, scanned at most once per signature and window.

    Each caller gets its own list of entry dicts, so a caller that annotates a row
    cannot move the rows the next caller reads. A manifest body is shared and read-only.
    """
    global _cached
    with _lock:
        signature = _signature()
        now = time.monotonic()
        if _cached is not None:
            cached_signature, cached_at, rows = _cached
            if cached_signature == signature and now - cached_at <= SCAN_TTL_SECONDS:
                return [dict(row) for row in rows]
        from core import plugin_manifest

        rows = plugin_manifest.scan_plugins()
        _cached = (signature, time.monotonic(), rows)
        return [dict(row) for row in rows]


def invalidate() -> None:
    """Drop the held scan; the next read walks the folders."""
    global _cached
    with _lock:
        _cached = None
