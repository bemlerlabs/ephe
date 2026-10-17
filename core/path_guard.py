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
