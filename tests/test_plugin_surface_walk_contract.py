"""
The surface read's own refusals: the shapes no syscall may see, and the states a
descriptor answers on its own.

`server/plugin_surface.py` decides a request in layers, and `tests/test_plugin_ui_serving.py`
drives them through the mount. This file pins the layer boundaries the route cannot
show, because the outer layer refuses first in production:

* `_request_parts` names the empty remainder — the route never asks for it, a caller of
  the module can.
* `_open_below`'s segment gate refuses a pre-split part that is empty, a dot, a walkout
  or carries a separator *before* `os.open` — the text layer above it already refuses
  these on the wire, so only a direct call can hold the gate to its own contract.
* the walk and the read answer a directory that vanished (the `missing` shape), a
  platform without `O_NOFOLLOW`/`dir_fd` (the honest `unreadable`), and a file above
  the cap (the `size` shape) rather than letting the failure travel.

The containment pair is pinned too: `_under` proves the path and `path_guard.confine`
re-proves it, so a root re-pointed between the two proofs is the same `walkout` refusal
a link inside one proof gets.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from server import plugin_surface

PLUGIN = "acme-walk-contract"
OUTSIDE_MARK = "OUTSIDE-THE-PLUGIN-DIRECTORY"


def _plugin(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    plugin = tmp_path / "cfg" / "plugins" / PLUGIN
    (plugin / "ui").mkdir(parents=True)
    (plugin / "ui" / "app.js").write_text("console.log('inside');", encoding="utf-8")
    return plugin


def test_an_empty_remainder_names_nothing(tmp_path, monkeypatch):
    """GIVEN the empty, the blank, the dot-only and the non-text remainder
    WHEN either layer is asked to resolve it
    THEN the refusal is the empty shape — not a directory listing and not a 500."""
    plugin = _plugin(tmp_path, monkeypatch)

    for remainder in ("", "   ", ".", "./", None):
        assert plugin_surface.read_surface_bytes(plugin, remainder) == (
            None,
            plugin_surface.REFUSED_SHAPES["empty"],
        ), remainder
        assert plugin_surface.resolve_surface_file(plugin, remainder) == (
            None,
            plugin_surface.REFUSED_SHAPES["empty"],
        ), remainder


@pytest.mark.parametrize(
    "parts",
    [
        ["ui", ""],
        ["ui", "."],
        ["ui", ".."],
        ["ui", "app.js/../app.js"],
        ["ui", "sub\\app.js"],
    ],
)
def test_the_segment_gate_refuses_a_part_that_would_open_legally(parts, tmp_path, monkeypatch):
    """GIVEN a segment list an `os.open(..., dir_fd=...)` would accept as it stands
    WHEN the descriptor walk is handed it directly
    THEN the gate refuses it as a walkout before any open — an empty part and a dot
    are legal names, `..` walks up through the descriptor, a separator and a backslash
    name another path than the one the text layer checked."""
    plugin = _plugin(tmp_path, monkeypatch)

    assert plugin_surface._open_below(plugin, parts) == (
        None,
        plugin_surface.REFUSED_SHAPES["walkout"],
    )


def test_the_segment_gate_still_opens_the_name_it_is_handed(tmp_path, monkeypatch):
    """The control beside the gate: a legal segment list opens the file, so the refusal
    above is the gate and not the walk refusing everything."""
    plugin = _plugin(tmp_path, monkeypatch)

    fd, reason = plugin_surface._open_below(plugin, ["ui", "app.js"])

    assert reason == ""
    assert fd is not None
    import os

    try:
        assert os.read(fd, 64) == b"console.log('inside');"
    finally:
        os.close(fd)


def test_a_directory_that_vanished_is_the_missing_shape(tmp_path, monkeypatch):
    """GIVEN the plugin directory is removed between the containment proof and the read
    WHEN the read opens its root
    THEN the answer is `missing` — a desktop with an uninstalled bundle is a state, not
    an exception travelling out of the route."""
    plugin = _plugin(tmp_path, monkeypatch)
    held, reason = plugin_surface.resolve_surface_file(plugin, "ui/app.js")
    assert (held, reason) == ((plugin / "ui" / "app.js").resolve(), "")
    shutil.rmtree(plugin)

    assert plugin_surface.read_surface_bytes(plugin, "ui/app.js") == (
        None,
        plugin_surface.REFUSED_SHAPES["missing"],
    )


def test_a_platform_without_the_hardened_open_refuses_instead_of_reading_by_path(
    tmp_path, monkeypatch
):
    """GIVEN a platform without `O_NOFOLLOW`, `O_DIRECTORY` or `dir_fd`
    WHEN a surface file is read
    THEN the read refuses as unreadable instead of falling back to the path-based
    check the descriptor walk replaced — the file is really there and stays unread."""
    plugin = _plugin(tmp_path, monkeypatch)
    monkeypatch.setattr(plugin_surface, "_HARDENED_OPEN", False)

    assert plugin_surface.read_surface_bytes(plugin, "ui/app.js") == (
        None,
        plugin_surface.REFUSED_SHAPES["unreadable"],
    )


def test_a_file_above_the_cap_is_refused_on_the_descriptor(tmp_path, monkeypatch):
    """GIVEN a file larger than a surface may load
    WHEN the bytes are read
    THEN the cap refuses it as `size` — measured on the descriptor the walk reached, so
    a size that changed after the containment check cannot slip through here."""
    plugin = _plugin(tmp_path, monkeypatch)
    (plugin / "ui" / "big.js").write_bytes(b"x" * 32)
    monkeypatch.setattr(plugin_surface, "MAX_SURFACE_ASSET_BYTES", 8)

    assert plugin_surface.read_surface_bytes(plugin, "ui/big.js") == (
        None,
        plugin_surface.REFUSED_SHAPES["size"],
    )


def test_a_root_repointed_between_the_two_proofs_is_a_walkout(tmp_path, monkeypatch):
    """GIVEN `_under` proves a path under the plugin root's first target and the root is
    then re-pointed at another tree, before `path_guard.confine` re-proves it
    WHEN the surface path is resolved
    THEN the second proof refuses: the path proven under the old target is not accepted
    as under the new one, and the refusal is the same `walkout` a link inside one proof
    gets. (A root that is a link *before* the first proof is the blessed starting point
    `_open_below` documents; this is the root moving after it.)"""
    first = tmp_path / "first"
    second = tmp_path / "second"
    for tree, mark in ((first, "FIRST"), (second, OUTSIDE_MARK)):
        (tree / "ui").mkdir(parents=True)
        (tree / "ui" / "app.js").write_text(mark, encoding="utf-8")
    root = tmp_path / "cfg" / "plugins" / PLUGIN
    root.parent.mkdir(parents=True)
    root.symlink_to(first)
    under = plugin_surface._under

    def _repoint_after_the_first_proof(directory, *parts):
        ships = under(directory, *parts)
        root.unlink()
        root.symlink_to(second)
        return ships

    monkeypatch.setattr(plugin_surface, "_under", _repoint_after_the_first_proof)

    assert plugin_surface.resolve_surface_file(root, "ui/app.js") == (
        None,
        plugin_surface.REFUSED_SHAPES["walkout"],
    )
