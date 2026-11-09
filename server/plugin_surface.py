"""Ephe — the serving policy behind a plugin's webview surface.

server/plugin_surface.py

`server/routes/plugin_ui.py` (#42) delivers the document a plugin declares in
`components.ui.entry` and the files beside it. The decisions that document rests
on live here, kept out of the HTTP layer; the per-mount credential has its own
module (`server/plugin_surface_nonce.py`) for the same reason.

Origin — a plugin document must not run on the app's own origin with the user's
authority intact, and the isolation mechanism chosen for it is the *opaque
origin* a `sandbox` directive without `allow-same-origin` produces. Two
alternatives were weighed and rejected: a cookie is a credential the Origin and
Host guards in `server/middleware.py` were never designed to see, and a
per-plugin custom URI scheme cannot be allow-listed per webview in Tauri 2 today
(an open upstream issue), so the confinement it promises would be an unenforced
claim. The opaque origin is enforceable from the one place this product already
controls — the response header of this route — and a sandboxed document's
requests stop being same-origin, so `/api/*` answers them cross-origin and the
read fails before the user's token, cookies or mutation guard are ever consulted.
Whether a given engine honours the directive is a measured question, answered in
`tests/test_plugin_surface_isolation_browser.py` for every engine that lane can
drive, and recorded as unmeasured for every engine it cannot.

Honest limit of that claim, stated where the mechanism is. Confined: the readability of
a response, because the engine hands a null-origin document no body; every mutation,
which the Origin guard of `server/middleware.py` refuses by method plus origin before
a route runs and the LAN token refuses off loopback; every GET that writes state or
opens another local service, refused with that same `untrusted_origin` when the origin
is present and disallowed, a literal `null` included; and the surface family, which
requires a live path nonce on loopback too, so a mount URL without one returns no
bytes. Unconfined on purpose: a read-only GET. A null-origin document on loopback can
still cause `/api/settings` and its read-only siblings to run, and the server still
answers them. The desktop path stays token-free for those fetches. The body stays
unreadable to the document. An opaque origin says which response the engine will hand
back, and which of the requests above this server now refuses. It does not say that
no request can reach the API. A local process that sends no Origin header may still
read. A mutation, a WebSocket handshake, and a GET that spends authority require an
origin this server serves or the LAN token. Copying that origin is a header a program
can type; `docs/SECURITY_AND_PRIVACY.md` names the limit. The desktop shell's own
plugin windows stay unmeasured, as `app/src-tauri/src/plugin_window.rs` states at its top.

Nonce — a plugin surface is an `<iframe>` or a native webview, and neither can
send a header, so the credential rides a path segment inside a directory-shaped
mount URL: the browser attaches a path prefix to every sub-resource the document
derives, and a query string attaches to one URL only. The minting, the plugin
binding, the expiry and the per-plugin eviction live in
`server/plugin_surface_nonce.py`.

CSP — the desktop shell's own policy comes from `app/src-tauri/tauri.conf.json`
and applies per document, so the plugin document gets its policy from this route.
The assembly — the closed baseline, the widening a capability paid for, the
sandbox directive, the `frame-ancestors` allow-set — is its own responsibility in
`server/plugin_surface_policy.py`; `SVG_DOCUMENT_CSP` is the one policy a caller
outside the mount needs and is named there too.

MIME — the whitelist is a table, so an unknown suffix has no answer here. Nothing
that is not on it leaves the plugin directory, plugin state files included.

Containment — a path from a URL is decided by `core/plugin_manifest._under` and
`core/path_guard.confine`, the two helpers the manifest contract already uses, after
the shapes a scanner is meant to see (`..`, an absolute path, a backslash, a NUL) are
refused by their text. The read walks the same segments itself: the plugin root opens
as a directory descriptor, every component after it opens on its parent's descriptor
with `O_NOFOLLOW`, and a step that is a symlink dies at that step. Keep the two
mechanisms apart. `realpath`, inside `_under` and `confine`, *follows* every link and
answers where the file sits, which is what proves the request stayed inside the
directory at the moment of the check. `O_NOFOLLOW`, inside the read, *refuses* to
follow a link at any step, and stops an author who swaps a directory (or a leaf) for a
link after that check from being walked out of it. A link the check resolved is blessed
there and refused here, and this is the layer that returns bytes.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

from core import path_guard
from core.plugin_manifest import _under

#: One asset read into memory per request. A plugin bundling a larger file gets a
#: refusal, a 2 GB file would be a stall on the request.
MAX_SURFACE_ASSET_BYTES = 8 * 1024 * 1024

#: The suffixes a surface may load, and the media type each arrives with. Anything
#: absent here is refused: no `application/json` state file, no `.py` tool, no
#: guessing through `mimetypes` what a plugin could name.
ASSET_MEDIA_TYPES: dict[str, str] = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".wasm": "application/wasm",
}

#: A served media type the mount may load only when its descriptor declared the
#: capability that runs it. `application/wasm` is the one today: WebAssembly compiles
#: bytes into code, and `server/plugin_surface_policy.py` adds `'wasm-unsafe-eval'` to
#: `script-src` only for a surface that declared `wasm`. Delivering those bytes to a
#: surface that cannot compile them would be a download of something that never runs,
#: so the capability decides arrival here as well as execution in the header. A
#: declared vendored library of this type is refused earlier, at validation
#: (`core/plugin_libraries.py`), where the reason can still name the manifest field.
ASSET_REQUIRED_CAPABILITIES: dict[str, str] = {"application/wasm": "wasm"}

#: The refusal texts a reader sees in the `{reason}` slot of a coded refusal. One
#: place, so the audit line and the envelope cannot tell two stories.
REFUSED_SHAPES = {
    "empty": "the path names nothing",
    "shape": "the path holds a segment a URL may not carry",
    "walkout": "the path leaves the plugin directory",
    "listing": "a directory is never served",
    "missing": "there is no file at that path",
    "unreadable": "the file is not readable",
    "irregular": "this path is not a regular file",
    "size": "the file is larger than a surface may load",
    "media": "this file type is not served to a surface",
    "capability": "this file type needs a capability the surface did not declare",
}

#: The open flags of the component walk. `O_NOFOLLOW` is the mechanism, so a
#: defaulted `getattr` would hide its absence: a platform without it, without
#: `O_DIRECTORY`, or without `dir_fd` for `os.open` gets a coded refusal.
_HARDENED_OPEN = (
    hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY")
    and os.open in getattr(os, "supports_dir_fd", frozenset())
)
_ROOT_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
_ROOT_FLAGS |= getattr(os, "O_NOFOLLOW", 0)
#: Every component after the root opens with these, and `O_DIRECTORY` is deliberately
#: absent: measured on macOS, that flag answers a symlinked step with `ENOTDIR`, the
#: same answer a step running through a regular file gives, so the refusal would be
#: ambiguous. Without it a link is `ELOOP` at any step, and each opened descriptor
#: carries the `fstat` that says whether it may be walked into.
_STEP_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)


def _request_parts(relative: str) -> tuple[list[str], str]:
    """`(segments, "")` for a URL remainder a filesystem call may be built from.

    Every shape a scanner is meant to see is decided by its text here, before any
    syscall: an absolute path, a backslash (a POSIX filename may legally hold one, so
    the resolution layers would read it as an ordinary name inside the directory), a
    NUL (which raises `ValueError` inside `os.path.realpath`, and a route letting that
    travel answers 500). `""` and `.` drop out; `..` is a refusal, because the walk
    below opens its segments on directory descriptors and `..` opens legally there.
    """
    if not isinstance(relative, str) or not relative.strip():
        return [], REFUSED_SHAPES["empty"]
    if "\x00" in relative or "\\" in relative or relative.startswith("/"):
        return [], REFUSED_SHAPES["shape"]
    parts = [part for part in relative.split("/") if part not in ("", ".")]
    if not parts:
        return [], REFUSED_SHAPES["empty"]
    if ".." in parts:
        return [], REFUSED_SHAPES["walkout"]
    return parts, ""


def resolve_surface_file(plugin_dir: Path, relative: str) -> tuple[Path | None, str]:
    """`(file, "")` when the request stays inside the plugin directory.

    Refused paths answer `(None, reason)` with a key of `REFUSED_SHAPES`, and the
    shapes a scanner is meant to see go to `_request_parts` first. The two helpers the
    manifest contract uses then decide the rest: `_under` builds from the real path of
    the plugin directory, `path_guard.confine` re-proves the candidate, so a symlink
    pointing out of the directory lands in the same refusal. This layer resolves links
    and the read refuses them, and only the read opens the file. A directory is refused
    on its own: this route never lists one.
    """
    parts, shape = _request_parts(relative)
    if not parts:
        return None, shape
    ships = _under(plugin_dir, *parts)
    if ships is None:
        return None, REFUSED_SHAPES["walkout"]
    held = path_guard.confine(ships, plugin_dir)
    if held is None:
        return None, REFUSED_SHAPES["walkout"]
    # One `stat` answers existence, type and size, and it is the only syscall here.
    # `pathlib` lets an `EACCES` travel out of `exists()`, `is_dir()` and `is_file()`,
    # and a directory the owner closed is a normal state on a desktop: a route that
    # let it escape answers 500 with the absolute path in the body. The two errors
    # naming an absent path keep their own refusal; every other failure to look is
    # unreadable, which is what the reader is told.
    try:
        held_stat = held.stat()
    except (FileNotFoundError, NotADirectoryError):
        return None, REFUSED_SHAPES["missing"]
    except OSError:
        return None, REFUSED_SHAPES["unreadable"]
    if stat.S_ISDIR(held_stat.st_mode):
        return None, REFUSED_SHAPES["listing"]
    if not stat.S_ISREG(held_stat.st_mode):
        return None, REFUSED_SHAPES["irregular"]
    if held_stat.st_size > MAX_SURFACE_ASSET_BYTES:
        return None, REFUSED_SHAPES["size"]
    return held, ""


def _refusal_for(refused: OSError) -> str:
    """The `REFUSED_SHAPES` name for an `OSError` raised by a step of the walk.

    The mapping is the shape the closed TOCTOU finding left: a link at any component
    is `walkout` (`ELOOP`), a path that stops existing is `missing`, a directory asked
    for as a leaf is `listing`, any other failure to look is `unreadable`.
    """
    if getattr(refused, "errno", None) == errno.ELOOP:
        return REFUSED_SHAPES["walkout"]
    if isinstance(refused, (FileNotFoundError, NotADirectoryError)):
        return REFUSED_SHAPES["missing"]
    if isinstance(refused, IsADirectoryError):
        return REFUSED_SHAPES["listing"]
    return REFUSED_SHAPES["unreadable"]


def _open_below(plugin_dir: Path, parts: list[str]) -> tuple[int | None, str]:
    """A descriptor for the last segment, opened one component at a time.

    The plugin root opens by path, as its real path (the answer `_under` built the
    containment proof from), so a root that is itself a link stays the blessed starting
    point. From there the root's descriptor opens the first segment, that descriptor
    opens the second, and each step carries `O_NOFOLLOW`, so a swapped component dies
    at the step that is a link. A step that is no directory gives `missing`. Every
    descriptor but the returned one is closed here, refusal and exception alike.

    The join is also proven as text before the walk, on the separator boundary: the
    segments arrive in a URL, and the path-injection query does not model `dir_fd`, so
    the shape it recognises is stated here instead of being left to the descriptor walk.
    It cannot refuse a request that reached this function (`_request_parts` has already
    refused `..`, a separator and a NUL), and it is not what makes the walk safe — the
    `O_NOFOLLOW` steps are. It is the assertion that the two agree, one string compare
    wide, and a `None` here is the same `walkout` the text layer answers.
    """
    root = os.path.realpath(plugin_dir)
    reached = os.path.normpath(os.path.join(root, *parts))
    if reached != root and not reached.startswith(root + os.sep):
        return None, REFUSED_SHAPES["walkout"]
    try:
        current = os.open(root, _ROOT_FLAGS)
    except OSError as refused:
        return None, _refusal_for(refused)
    leaf = None
    handed_off = False
    try:
        for depth, part in enumerate(parts):
            leaf = os.open(part, _STEP_FLAGS, dir_fd=current)
            if depth == len(parts) - 1:
                handed_off = True
                break
            if not stat.S_ISDIR(os.fstat(leaf).st_mode):
                return None, REFUSED_SHAPES["missing"]
            os.close(current)
            current, leaf = leaf, None
    except OSError as refused:
        return None, _refusal_for(refused)
    finally:
        os.close(current)
        if leaf is not None and not handed_off:
            os.close(leaf)
    return leaf, ""


def read_surface_bytes(plugin_dir: Path, relative: str) -> tuple[bytes | None, str]:
    """The bytes of a contained file, with every path component refused as a link.

    The gap between the containment check and the read is writable by the plugin
    author: a plain `read_bytes()` by path after the proof follows a symlink the author
    swapped in during that window, and an escaping swap turns the asset route into an
    arbitrary-read primitive. `O_NOFOLLOW` on the last component alone left that open,
    because the flag does not apply to the parent components of an open, so an author
    who swapped `ui/` itself for a link was still followed. The read now resolves no
    component by path: `_open_below` refuses a link at each step, `fstat` re-proves
    regular-file and size on the descriptor that was opened, and the bytes come from
    that same descriptor, so the file read is the file the walk reached.
    """
    parts, shape = _request_parts(relative)
    if not parts:
        return None, shape
    if not _HARDENED_OPEN:
        # A refusal is the honest answer on a platform that cannot open relative to a
        # descriptor, because a path-based re-check is the mechanism this replaced.
        return None, REFUSED_SHAPES["unreadable"]
    fd, reason = _open_below(plugin_dir, parts)
    if fd is None:
        return None, reason
    handed_off = False
    try:
        # `fstat` first: `os.fdopen` over a directory descriptor raises on macOS
        # before the file object exists, and the descriptor is the honest answer to
        # "this path is a directory".
        info = os.fstat(fd)
        if stat.S_ISDIR(info.st_mode):
            return None, REFUSED_SHAPES["listing"]
        if not stat.S_ISREG(info.st_mode):
            return None, REFUSED_SHAPES["irregular"]
        if info.st_size > MAX_SURFACE_ASSET_BYTES:
            return None, REFUSED_SHAPES["size"]
        handle = os.fdopen(fd, "rb")
        handed_off = True
        with handle:
            data = handle.read(MAX_SURFACE_ASSET_BYTES + 1)
    except OSError:
        return None, REFUSED_SHAPES["unreadable"]
    finally:
        if not handed_off:
            os.close(fd)
    if len(data) > MAX_SURFACE_ASSET_BYTES:
        return None, REFUSED_SHAPES["size"]
    return data, ""


def surface_media_type(target: Path) -> str | None:
    """The whitelisted media type for one resolved file, or None.

    The suffix decides, never the content: a plugin that renames its state file to
    `.html` is serving itself a document under its own declaration.
    """
    return ASSET_MEDIA_TYPES.get(target.suffix.lower())
