"""Ephe — the per-mount credential a plugin surface carries inside its own URL.

server/plugin_surface_nonce.py

A plugin surface is an `<iframe>` or a native webview, and neither can send a
header — the W1-1 probe measured that on the icon route — so the credential every
surface load authenticates with has to be a value a URL can carry. R21
rules the long-lived LAN token out of URLs: it unlocks every `/api/*`, and logs,
history and screenshots all keep a query string. This module mints instead a
random value bound to one plugin id, dying on a timer, held in this process
alone: a restart takes every surface credential with it, which is the point of a
per-mount nonce.

The credential rides a path segment — `/api/plugins/ui/{plugin_id}/{nonce}/…` —
inside a directory-shaped URL. A query string cannot do the one job this
credential has: a browser attaches a path prefix to every sub-resource the
document derives from it, and a query belongs to one URL only. With the nonce in
the path, one mint covers the document and everything it loads, and a
hand-written request that keeps the credential out of the path arrives with no
credential at all.

`server/middleware.py` reads the *shape* (a GET or HEAD inside the family that
carries a nonce segment) and hands the request on; the value, the plugin binding
and the expiry are decided here, and `server/routes/plugin_ui.py` applies them
before it touches a byte of the plugin directory. That check holds on loopback
too. A desktop fetch of any other `/api` path does not carry this nonce. Reads
on that path stay token-free. A mutation there is the app's own origin, or the
LAN token.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import hmac
import re
import secrets
import threading
import time
from typing import NamedTuple

#: Every surface request lives under this path family; the middleware scopes the
#: credential to exactly it.
SURFACE_PATH_ROOT = "/api/plugins/ui/"

#: Five minutes. Long enough for one mount to load its document and its assets,
#: short enough that a nonce read out of a log is useless after the window.
#: A standing surface keeps this same value: the authenticated mint route moves
#: `issued_at` forward when the parent asks, and a fetch of the document does
#: not. Widening the number would turn a leaked URL into a longer credential.
#: A value that has already died is not brought back, so a URL left in history
#: stops answering at the end of this window.
SURFACE_NONCE_TTL_SECONDS = 300.0

#: `token_urlsafe(24)` is 32 characters, which is what a URL can carry and what a
#: guess cannot reach.
SURFACE_NONCE_BYTES = 24

#: Minting needs an authenticated caller, so this bound is a memory guard against
#: a plugin that re-mounts in a loop. The loop evicts its own oldest credential
#: first and never a live mount of another plugin (`mint_surface_nonce`).
MAX_SURFACE_NONCES = 64

#: `^/api/plugins/ui/` plus one slug segment plus a nonce segment. The second
#: segment is the credential slot; the family has no shape without it.
_SURFACE_PATH_RE = re.compile(r"^/api/plugins/ui/([^/]+)/([^/]+)(?:/.*)?$")


class SurfaceNonce(NamedTuple):
    """One minted credential: the plugin it was minted for, and when it dies."""

    nonce: str
    plugin_id: str
    issued_at: float
    ttl_seconds: float


_nonces: dict[str, SurfaceNonce] = {}
_nonce_lock = threading.Lock()


def surface_clock() -> float:
    """Monotonic now, behind one name so a test can move the clock forward.

    Monotonic because a wall clock that jumps backwards would otherwise extend a
    credential nobody asked to lengthen.
    """
    return time.monotonic()


def _expired(record: SurfaceNonce, now: float) -> bool:
    return now - record.issued_at >= record.ttl_seconds


def _prune_locked(now: float) -> None:
    for key, record in list(_nonces.items()):
        if _expired(record, now):
            _nonces.pop(key, None)


def mint_surface_nonce(plugin_id: str) -> SurfaceNonce:
    """A fresh credential bound to `plugin_id`, held in this process only.

    Nothing is signed against a session secret and nothing is persisted. At the
    memory bound the victim is the oldest credential *of this plugin* — a
    re-mount loop replaces its own mounts, and one plugin minting in a loop must
    never silently kill another plugin's live mount. Only when this plugin holds
    nothing older does the global oldest go, and the bound keeps that rare.
    """
    record = SurfaceNonce(
        nonce=secrets.token_urlsafe(SURFACE_NONCE_BYTES),
        plugin_id=plugin_id,
        issued_at=surface_clock(),
        ttl_seconds=SURFACE_NONCE_TTL_SECONDS,
    )
    with _nonce_lock:
        _prune_locked(record.issued_at)
        while len(_nonces) >= MAX_SURFACE_NONCES:
            own = next(
                (key for key, held in _nonces.items() if held.plugin_id == plugin_id),
                None,
            )
            _nonces.pop(own if own is not None else next(iter(_nonces)))
        _nonces[record.nonce] = record
    return record


def renew_surface_nonce(plugin_id: str, offered: str | None) -> SurfaceNonce | None:
    """Move a live credential's start to now. A dead or foreign value stays dead.

    Only the authenticated mint route calls this. A document fetch does not, so a
    URL copied into history cannot lengthen itself by being loaded. The update
    happens under the same lock as the expiry check: releasing the lock between
    the two would let a dead value be written back.
    """
    if not offered:
        return None
    with _nonce_lock:
        record = _nonces.get(offered)
        if record is None:
            return None
        if not hmac.compare_digest(record.nonce.encode("utf-8"), offered.encode("utf-8")):
            return None
        if not hmac.compare_digest(
            record.plugin_id.encode("utf-8"), plugin_id.encode("utf-8")
        ):
            return None
        now = surface_clock()
        if _expired(record, now):
            _nonces.pop(offered, None)
            return None
        renewed = record._replace(issued_at=now)
        _nonces[offered] = renewed
        return renewed


def surface_nonce_record(plugin_id: str, offered: str | None) -> SurfaceNonce | None:
    """The live record minted for `plugin_id` that answers to `offered`.

    The dictionary locates the candidate; `hmac.compare_digest` decides both the
    value and the plugin binding, the same constant-time comparison
    `server/middleware.py` applies to the LAN token, so neither a byte of the nonce
    nor the id it is bound to is answered by a timing difference. Both sides go to
    UTF-8 bytes first: `compare_digest` refuses non-ASCII strings with a ValueError,
    and a URL can carry a name that is one, which would be a 500 where a refusal is
    the answer. An expired record is dropped here, so a refusal and a clean-up share
    one path.
    """
    if not offered:
        return None
    with _nonce_lock:
        record = _nonces.get(offered)
        if record is None:
            return None
        if not hmac.compare_digest(
            record.nonce.encode("utf-8"), offered.encode("utf-8")
        ):
            return None
        if not hmac.compare_digest(
            record.plugin_id.encode("utf-8"), plugin_id.encode("utf-8")
        ):
            return None
        if _expired(record, surface_clock()):
            _nonces.pop(offered, None)
            return None
        return record


def verify_surface_nonce(plugin_id: str, offered: str | None) -> bool:
    """Whether `offered` is a live credential for exactly this plugin."""
    return surface_nonce_record(plugin_id, offered) is not None


def surface_nonce_candidate(path: str) -> tuple[str, str, str] | None:
    """`(plugin_id, nonce_segment, relative_path)` when the URL rides a credential.

    Presence only, and deliberately so: `server/middleware.py` reads this to decide
    whether to hand the request to the route, which owns the verification, the
    expiry and the plugin binding. A path that stops at the plugin id — the bare
    document URL of the old shape — names no credential slot and answers None, so
    an off-loopback request in that shape meets the token check it used to skip.
    """
    match = _SURFACE_PATH_RE.match(path or "")
    if match is None:
        return None
    # `re` keeps the family honest; the split carries the remainder through, so a
    # deeper asset path arrives whole instead of truncated at its first slash.
    parts = (path or "")[len(SURFACE_PATH_ROOT):].split("/")
    return parts[0], parts[1], "/".join(parts[2:])
