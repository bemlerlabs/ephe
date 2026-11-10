"""#59 — a plugin folder the process cannot read is an error line, not a 500.

Measured before the fix: one plugin directory at mode 000 made `scan_plugins` raise
`PermissionError` out of `mfile.is_file()` inside `load_manifest`, and because the settings
route, the store view and the runtime all read that scan, a folder whose metadata this
process may not touch took the whole Extensions page down. A half-finished install, a volume
mounted by another user, a folder someone chmod'ed — all ordinary states of a disk, and none
of them is a reason for the product to answer 500.

`Path.is_file()` and `Path.is_dir()` are the trap here, and they are worth naming: they
swallow the errors their authors expected (a missing path, a non-directory) and let the others
through. So the fix is not a bare `except Exception` around the loop, it is asking those
questions in a form that answers a boolean, and reading the manifest inside the same try the
read already needed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from core import plugin_manifest
from core.plugin_manifest import load_manifest, scan_plugins

VALID = {
    "manifest_version": 1,
    "name": "good",
    "version": "1.0.0",
    "description": "d",
    "components": {},
    "permissions": {"tool_families": []},
}


def _root(tmp_path: Path) -> Path:
    """Four broken folders and one good one, under the root the scanner is pointed at."""
    root = tmp_path / "plugins"
    root.mkdir()

    good = root / "good"
    good.mkdir()
    (good / "ephe-plugin.json").write_text(json.dumps(VALID), encoding="utf-8")

    unreadable = root / "unreadable"
    unreadable.mkdir()
    (unreadable / "ephe-plugin.json").write_text(json.dumps(VALID), encoding="utf-8")
    os.chmod(unreadable, 0o000)

    manifest_is_a_dir = root / "isdir"
    manifest_is_a_dir.mkdir()
    (manifest_is_a_dir / "ephe-plugin.json").mkdir()

    loop = root / "loopy"
    loop.mkdir()
    target = loop / "ephe-plugin.json"
    os.symlink(target, target)

    return root


def _restore(root: Path) -> None:
    for path in root.iterdir():
        try:
            os.chmod(path, 0o755)
        except OSError:
            pass


@pytest.fixture()
def broken_root(tmp_path: Path):
    if os.geteuid() == 0:
        pytest.skip("root reads any mode, so the unreadable case cannot be created here")
    root = _root(tmp_path)
    try:
        yield root
    finally:
        _restore(root)


def test_one_unreadable_folder_does_not_take_the_scan_down(broken_root: Path) -> None:
    entries = scan_plugins(broken_root)

    by_name = {entry["dir"].name: entry for entry in entries}
    assert "good" in by_name, "the valid plugin vanished beside a broken one"
    assert by_name["good"]["manifest"] is not None
    assert by_name["good"]["error"] is None

    assert by_name["unreadable"]["manifest"] is None
    assert "PermissionError" in (by_name["unreadable"]["error"] or "")
    # A directory and a self-referencing symlink are answered too, and no folder is lost:
    # four were built, four are reported.
    assert by_name["isdir"]["error"] and by_name["loopy"]["error"]
    assert len(entries) == 4


def test_load_manifest_answers_a_string_for_a_folder_it_cannot_read(broken_root: Path) -> None:
    manifest, error = load_manifest(broken_root / "unreadable")
    assert manifest is None
    assert error == "manifest unreadable: PermissionError"

    # The message names the failure class and carries no host path: it reaches the surface.
    assert "/" not in (error or "")


def test_the_store_view_survives_a_broken_folder(broken_root: Path, tmp_path: Path) -> None:
    """`plugins_view` is what the settings page renders, and it reads this scan."""
    from core import plugin_store

    plugin_manifest.PLUGINS_ROOT_OVERRIDE = broken_root
    try:
        view = plugin_store.plugins_view(tmp_path / "catalog.json", tmp_path / "registry.json")
        assert isinstance(view["public"], list)
        assert view["unproven"] is False, "a broken folder must not read as an unknown state"
    finally:
        plugin_manifest.PLUGINS_ROOT_OVERRIDE = None


def test_the_route_answers_200_with_a_broken_folder_on_disk(broken_root: Path, tmp_path: Path):
    """The request that produced the 500, made against the running app.

    The client is a loopback peer with a loopback Host, which is the desktop path the
    middleware trusts without a token — the token dance is another test's subject, and
    mixing it in would hide which half is being proved.
    """
    import asyncio

    from server.main import create_app

    from core import plugin_manifest as pm

    pm.PLUGINS_ROOT_OVERRIDE = broken_root
    try:
        app = create_app()
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 54321))

        async def call() -> int:
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8765") as c:
                response = await c.get("/api/plugins")
                return response.status_code

        status = asyncio.run(call())
        assert status == 200, status
    finally:
        pm.PLUGINS_ROOT_OVERRIDE = None
