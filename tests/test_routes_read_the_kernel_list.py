"""tests/test_routes_read_the_kernel_list.py — the browse guard asks the kernel, each time.

Run these two files as one batch and fourteen /api/fs tests went red:

    tests/test_r5_framed_document_isolation.py tests/test_routes_paths_extra.py

The measured state after the first of them finished:

    base._get_allowed_roots()  -> 13 roots, the real list
    fs._get_allowed_roots()    -> 1 root, the other test's temp folder

`server/routes/fs.py` bound that helper with `from core.tools.base import
_get_allowed_roots`, which copies the name into fs's own namespace at import time.
The other fixture patches the attribute on core.tools.base and mounts the app
inside that window, so the first import of the browse module captures the patched
lambda. monkeypatch then restores the kernel, and fs keeps the stale list of one
folder that no longer exists — which is why every browse request that ran after it
answered 403 `path not in allowed roots`.

Late binding is the fix: reach through the module, so a patch is honoured while it
is live and costs nothing once it is undone. The same capture sat in
`server/routes/network.py`, where it refused nothing but printed a stale folder
list on the network settings area — a row claiming what the guard no longer
enforced.
"""
from __future__ import annotations


def test_the_browse_guard_judges_by_the_kernels_current_list(tmp_path, monkeypatch):
    """GIVEN a patched allowed-roots list
    WHEN the browse guard judges two paths
    THEN the patch decides, and a folder the kernel excludes is refused."""
    import core.tools.base as base
    import server.routes.fs as fs

    inside = tmp_path / "inside"
    outside = tmp_path / "outside"
    inside.mkdir()
    outside.mkdir()
    monkeypatch.setattr(base, "_get_allowed_roots", lambda: [inside])

    assert fs._in_allowed_roots(inside) is True
    assert fs._in_allowed_roots(outside) is False, (
        "the browse guard judged this path against a root list it copied at import "
        "time, while the kernel was saying something else"
    )


def test_the_browse_guard_returns_to_the_real_list_when_a_patch_is_undone(tmp_path):
    """The other half of late binding: the window closing must restore the real answer.

    This is the direction the batch breaks in — fs holds the narrowed list after
    the test that patched it is gone.
    """
    from unittest import mock

    import core.tools.base as base
    import server.routes.fs as fs

    target = tmp_path / "browse-me"
    target.mkdir()
    granted = tmp_path / "granted"
    granted.mkdir()

    with mock.patch.object(base, "_get_allowed_roots", lambda: [granted]):
        assert fs._in_allowed_roots(target) is False

    # Undone: the kernel's real list covers the temp folder again, so the guard says yes.
    assert fs._in_allowed_roots(target) is True
