"""core/path_guard.py - one primitive for "is this path inside that root".

Two places in this tree take a path from outside and then act on it: the settings POST,
whose folder arrives as the owner's own choice, and the workspace register, whose id or
name arrives from a page. Both already resolved the value and compared it with their root,
and both comparisons were written as `Path.is_relative_to`.

The comparison is spelled out here instead, for a reason that shows up on the security tab
rather than in a test: CodeQL's path-injection query does not model `is_relative_to`, so
three sites stayed open as "uncontrolled data used in a path expression" while the guard
they carried was correct. A prefix test on a **separator boundary** is the shape the query
does recognise, and it is also the correct comparison: a bare prefix test would accept
`/srv/workspaces-evil` as a child of `/srv/workspaces`,
and a caller that never resolves lets `..` answer a question nobody asked.

Both functions are pure: they resolve the paths (the only syscall), and they decide. The
boundary cases live in `tests/test_path_guard.py`.
"""
from __future__ import annotations

import os
from pathlib import Path

#: Roots no agent tool may read, whatever approval it carries. The app's own state is
#: in here (`~/.ephe`), and so are the credential stores the machine already holds.
#: A path under one of these is refused before a tool can ask a human: the answer to
#: "may I read your SSH key" is no, not a dialog.
DENY_ROOTS: tuple[str, ...] = (
    "~/.ephe",
    "~/.ssh",
    "~/.aws",
    "~/.gnupg",
    "~/.kube",
    "~/.docker",
    "~/.tauri",
    "~/.password-store",
    "~/.config/gh",
    "~/.config/gcloud",
    "~/.config/sops",
    "~/.netrc",
    "~/.npmrc",
    "~/.pypirc",
    "~/Library/Keychains",
)

#: Names that hold credential material wherever they sit. Reading one needs a human's
#: yes even when the tool is classified read-only.
_SECRET_NAMES = frozenset(
    {
        ".env",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "credentials",
        "credentials.json",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "authorized_keys",
        "known_hosts",
    }
)

_SECRET_SUFFIXES = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".kdbx",
)

#: Argument keys whose value names a place on disk.
PATH_ARG_KEYS: tuple[str, ...] = (
    "path",
    "file",
    "filename",
    "directory",
    "dir",
    "target",
    "source",
    "workspace",
    "cwd",
    "wasm_path",
)


def within(child: Path | str, root: Path | str) -> bool:
    """Whether ``child`` is ``root`` or sits below it, on a separator boundary.

    Arguments are compared as given, so a caller holding an unresolved value resolves it
    first - `confine` exists to make that the easy path, because comparing an unresolved
    path is what lets `..` and symlinks answer the wrong question.
    """
    child_text = os.path.normpath(str(child))
    root_text = os.path.normpath(str(root))
    if root_text == os.sep:
        return os.path.isabs(child_text)
    return child_text == root_text or child_text.startswith(root_text + os.sep)


def confine(candidate: Path | str, root: Path | str) -> Path | None:
    """``candidate`` resolved and proven to sit inside ``root``, or ``None``.

    ``None`` is the refusal: a value that leaves the root, a symlink pointing out of it, a
    path that cannot be resolved, a name that is not a path at all. The returned path is the
    resolved one, so the caller acts on the path that was checked.

    Existence is deliberately not part of the decision - the output directory is created
    after this call - so a caller whose path must already be a directory checks that itself.
    A self-referential symlink is where the two platforms part: Linux raises on the loop and
    the refusal above catches it, macOS resolves it to its own text, which stays inside the
    root, and the caller's `is_dir()` sees that nothing is there. Both answers are safe, and
    neither lets a loop read as a usable folder.
    """
    try:
        # The candidate is confined by the two lines below, and the resolve is the first half
        # of that check: it is what turns `..` and a symlink into text that can be compared.
        # A folder the owner picks is not a name that can be reduced to a basename the way the
        # query's usual sanitizer does.
        real = Path(candidate).expanduser().resolve()  # codeql[py/path-injection]
        base = Path(root).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return real if within(real, base) else None


def denied(candidate: Path | str) -> bool:
    """Whether a path sits inside a root no agent tool may read (symlinks resolved)."""
    try:
        # The resolve is the check itself: `real` is compared against the deny roots
        # below and never opened, so there is no path here for the query's sink to reach.
        real = Path(candidate).expanduser().resolve()  # codeql[py/path-injection]
        roots = [Path(root).expanduser().resolve() for root in DENY_ROOTS]
    except (OSError, RuntimeError, ValueError):
        return False
    return any(within(real, root) for root in roots)


def secret_shaped(candidate: Path | str) -> bool:
    """Whether a file name is credential-shaped, wherever it sits."""
    name = Path(str(candidate)).name.lower()
    if name in _SECRET_NAMES:
        return True
    if name.startswith(".env."):
        return True
    if any(name.endswith(suffix) for suffix in _SECRET_SUFFIXES):
        return True
    return "credential" in name or "secret" in name or "token" in name


def _path_args(args: object) -> list[str]:
    data = args if isinstance(args, dict) else {}
    out: list[str] = []
    for key in PATH_ARG_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            out.append(value.strip())
    for key, value in data.items():
        if key in PATH_ARG_KEYS or not isinstance(value, str):
            continue
        text = value.strip()
        if text.startswith(("~/", "/")) and ("/" in text[1:] or text in {str(Path.home())}):
            out.append(text)
    return out


def deny_paths(args: object) -> list[str]:
    """Path arguments that fall under ``DENY_ROOTS``."""
    return [value for value in _path_args(args) if denied(value)]


def secret_paths(args: object) -> list[str]:
    """Path arguments whose file name is credential-shaped."""
    return [value for value in _path_args(args) if secret_shaped(value)]
