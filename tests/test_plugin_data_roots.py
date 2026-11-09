"""Task #24, first half: what `permissions.data_roots` actually opens.

The manifest line existed long before this file, and two sentences were told about it. The
marketplace diff treats a new root as a permission change worth asking about, and
`core/tools/base.py` honours it when a plugin calls a kernel file tool. `docs/PLUGIN_SDK.md`
called it "for display/intent only", and the confined worker — the rail a v2 tool of the same
bundle runs on — read nothing of it. Both halves now answer to one resolution function, which
is what these tests hold: a declaration means the same set of paths whoever reads it.

The confined cases run a real child on this machine's boundary (Seatbelt here, the rail #9,
#47 and #23 proved live), because the claim is about what the OS lets the process open.

The second half of #24 is the ceiling beside that folder: 512 MiB per bundle unless the
manifest asks for another number, measured after every run and refused before the next one.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import mcp_sandbox, plugin_manifest
from core.capability_policy import resolved_data_roots
from core.plugin_state import usage as state_usage
from core.sandbox.runner import _data_roots, run_plugin_tool
from core.sandbox.worker_spec import build_spec

PLUGIN_ID = "acme-notebook"


def _install(tmp_path: Path, monkeypatch, roots: list[str], cap_mb: int | None = None) -> Path:
    """A manifest in the scanned portfolio that declares `roots`, with a runnable entry."""
    plugins = tmp_path / "plugins"
    root = plugins / PLUGIN_ID
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "manifest_version": 2, "name": PLUGIN_ID, "version": "1.0.0",
        "description": "Acme notebook", "publisher": {"name": "Acme"},
        "license": "MIT", "engines": {"ephe": ">=0.1.0"},
        "permissions": {"tool_families": ["read"], "data_roots": roots},
        "components": {"tools": [{
            "name": "note_read", "entry": "handlers.py:run", "family": "read",
            "description": "Read one declared folder.",
        }]},
    }
    if cap_mb is not None:
        manifest["permissions"]["state_cap_mb"] = cap_mb
    (root / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "handlers.py").write_text(
        "def run(arguments, state_dir):\n"
        "    import pathlib\n"
        "    folder = arguments.get('folder') or ''\n"
        "    try:\n"
        "        body = (pathlib.Path(folder) / 'note.md').read_text()\n"
        "    except OSError as exc:\n"
        "        return {'read': None, 'error': type(exc).__name__}\n"
        "    return {'read': body, 'error': None}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", plugins)
    return root


def _descriptor() -> object:
    from core.plugin_tools_contract import descriptors_for

    manifest, error = plugin_manifest.load_manifest(
        Path(plugin_manifest.PLUGINS_ROOT_OVERRIDE) / PLUGIN_ID
    )
    assert not error, error
    (descriptor,) = descriptors_for(manifest)
    return descriptor


@pytest.fixture()
def lane(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    config.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    return {"tmp": tmp_path, "config": config}


# the resolution


def test_an_absolute_root_is_taken_as_written(lane, monkeypatch):
    folder = lane["tmp"] / "given"
    folder.mkdir()
    _install(lane["tmp"], monkeypatch, [str(folder)])
    assert resolved_data_roots(PLUGIN_ID, None) == [folder.resolve()]


def test_a_relative_root_lands_inside_the_workspace(lane, monkeypatch):
    workspace = lane["tmp"] / "work"
    inside = workspace / "notes"
    inside.mkdir(parents=True)
    _install(lane["tmp"], monkeypatch, ["notes"])
    assert resolved_data_roots(PLUGIN_ID, workspace.resolve()) == [inside.resolve()]


def test_a_relative_root_that_escapes_refuses_the_whole_manifest(lane, monkeypatch):
    """The declaration is refused when the manifest loads, so the bundle is never scanned.

    Fail-closed is the rule the portfolio already holds: one broken manifest quarantines its
    own plugin, and a `..` in a data root is that kind of broken. Nothing downstream has to
    second-guess an escape, and resolution of an unloaded bundle answers with nothing.
    """
    workspace = lane["tmp"] / "work"
    workspace.mkdir(parents=True)
    root = _install(lane["tmp"], monkeypatch, ["../outside"])
    _, error = plugin_manifest.load_manifest(root)
    assert error and "outside" in error, error
    assert resolved_data_roots(PLUGIN_ID, workspace.resolve()) == []


def test_a_relative_root_without_a_workspace_resolves_to_nothing(lane, monkeypatch):
    _install(lane["tmp"], monkeypatch, ["notes"])
    assert resolved_data_roots(PLUGIN_ID, None) == []


def test_the_two_rails_read_the_same_declaration(lane, monkeypatch):
    """The kernel file scope and the confined worker must not hold two answers to one line."""
    from core.tools.base import PLUGIN_FILE_SCOPE, _get_allowed_roots

    workspace = lane["tmp"] / "work"
    inside = workspace / "notes"
    inside.mkdir(parents=True)
    _install(lane["tmp"], monkeypatch, ["notes"])
    monkeypatch.setattr("core.engine_config.get_workspace_dir", lambda: str(workspace))
    token = PLUGIN_FILE_SCOPE.set(PLUGIN_ID)
    try:
        scope = _get_allowed_roots()
    finally:
        PLUGIN_FILE_SCOPE.reset(token)
    assert inside.resolve() in scope
    assert inside.resolve() in resolved_data_roots(PLUGIN_ID, workspace.resolve())


def test_a_root_that_is_not_a_folder_never_reaches_the_worker(lane, monkeypatch):
    """Two doors on one rule: the manifest refuses the declaration, the runner binds nothing.

    `validate_data_roots` refuses a declared path that is not a directory when the manifest
    loads, and `_data_roots` filters the same shape again for the window between that read and
    the spawn. The scan that follows a bad declaration hides the bundle, so the worker never
    sees the path either way.
    """
    workspace = lane["tmp"] / "work"
    workspace.mkdir()
    gone = workspace / "gone"
    _install(lane["tmp"], monkeypatch, [str(gone)])
    _, error = plugin_manifest.load_manifest(Path(plugin_manifest.PLUGINS_ROOT_OVERRIDE) / PLUGIN_ID)
    assert error and "gone" in error, error
    assert _data_roots(PLUGIN_ID) == (), "an unloaded bundle grants no root"


def test_a_host_root_never_moves_the_plugin_directory(tmp_path):
    """The first run of this path rebound `root` inside `build_spec`, and the worker looked
    for its entry in the declared folder instead of the bundle's own. The anchor stays."""
    root = tmp_path / "plugin"
    root.mkdir()
    (root / "handlers.py").write_text("print(1)\n", encoding="utf-8")
    declared = tmp_path / "declared"
    declared.mkdir()
    spec, error = build_spec(
        plugin_id="acme", plugin_dir=root, entry="handlers.py",
        host_roots=(str(declared),),
    )
    assert error == "", error
    assert spec.plugin_dir == root
    assert spec.entry_path() == root.resolve() / "handlers.py"
    assert spec.read_roots()[0] == str(root.resolve())
    assert str(declared.resolve()) in spec.read_roots()


@pytest.fixture()
def fenced(lane, monkeypatch):
    """A home the boundary denies, so a declared root is a grant rather than a courtesy.

    `build_profile` denies `$HOME` whole and re-opens exactly what the descriptor declares.
    Under pytest's own temporary directory that deny covers nothing at all, and reading an
    undeclared folder there would succeed for a reason this test must not claim as a
    guarantee. The home moves into the lane, so the deny is real, and only the appended rule
    can undo it for one path.
    """
    home = lane["tmp"] / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    return home


# the confined child


def _skip_without_boundary():
    if mcp_sandbox.platform_boundary() == "unavailable":
        pytest.skip("no OS boundary on this machine — the confined child cannot start")


def test_the_declaration_opens_one_folder_and_leaves_its_sibling_shut(fenced, monkeypatch):
    """One confined child, two folders in the denied home, and the answer each one gets.

    The declared folder is readable because the profile carries a rule for it; the sibling
    beside it, in the same home and with the same handler, stays behind the whole-home deny.
    Measured on this machine with the real `sandbox-exec`, both directions in one test,
    because a grant proven only on the side that succeeds proves nothing.
    """
    _skip_without_boundary()
    notes = fenced / "notes"
    other = fenced / "other"
    notes.mkdir()
    other.mkdir()
    (notes / "note.md").write_text("the note the bundle was given", encoding="utf-8")
    (other / "note.md").write_text("the note nobody declared", encoding="utf-8")
    root = _install(fenced.parent, monkeypatch, [str(notes)])
    descriptor = _descriptor()

    opened = run_plugin_tool(
        descriptor, {"folder": str(notes)}, root, timeout_seconds=30.0
    )
    assert opened.status == "ok", opened.text
    assert json.loads(opened.text)["read"] == "the note the bundle was given"

    shut = run_plugin_tool(descriptor, {"folder": str(other)}, root, timeout_seconds=30.0)
    assert shut.status == "ok", shut.text
    payload = json.loads(shut.text)
    assert payload["read"] is None, f"an undeclared folder opened: {payload!r}"
    assert payload["error"] in {"PermissionError", "FileNotFoundError"}, payload


def test_an_absolute_path_inside_the_plugin_directory_needs_no_declaration(fenced, monkeypatch):
    """The bundle's own folder is readable without a declaration; that is the plugin directory."""
    _skip_without_boundary()
    root = _install(fenced.parent, monkeypatch, [])
    (root / "note.md").write_text("shipped with the bundle")
    result = run_plugin_tool(_descriptor(), {"folder": str(root)}, root, timeout_seconds=30.0)
    assert json.loads(result.text)["read"] == "shipped with the bundle", result.text


# the number a cap needs


def test_the_state_directory_is_measured_after_the_run(lane, monkeypatch):
    """Bytes and files of the child's own home, read off the disk the run left behind."""
    _skip_without_boundary()
    workspace = lane["tmp"] / "work"
    workspace.mkdir()
    root = _install(lane["tmp"], monkeypatch, [])
    (root / "handlers.py").write_text(
        "def run(arguments, state_dir):\n"
        "    import os\n"
        "    with open(os.path.join(state_dir, 'kept.txt'), 'w') as handle:\n"
        "        handle.write('x' * 4096)\n"
        "    return {'written': True}\n",
        encoding="utf-8",
    )
    home = mcp_sandbox.home_for(f"plugin_{PLUGIN_ID}")
    before_bytes, _before_files = state_usage(home)
    result = run_plugin_tool(_descriptor(), {}, root, timeout_seconds=30.0)
    assert result.status == "ok", result.text
    after_bytes, after_files = state_usage(home)
    assert after_bytes - before_bytes >= 4096, (before_bytes, after_bytes)
    assert after_files >= 1


def test_a_broken_subtree_counts_as_nothing_instead_of_raising(tmp_path):
    folder = tmp_path / "state"
    (folder / "deep").mkdir(parents=True)
    (folder / "deep" / "one.txt").write_text("abc", encoding="utf-8")
    (folder / "dangling.txt").symlink_to(folder / "gone.txt")
    bytes_used, files = state_usage(folder)
    assert bytes_used == 3 and files == 1, "a path with no bytes behind it counts as nothing"


def test_the_row_that_states_the_state_is_the_row_the_surface_reads(lane, monkeypatch):
    """The audit detail carries the measurement, so a reader can ask where the bytes are."""
    from core import audit_log

    log = lane["tmp"] / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log)
    _skip_without_boundary()
    workspace = lane["tmp"] / "work"
    workspace.mkdir()
    root = _install(lane["tmp"], monkeypatch, [])
    result = run_plugin_tool(_descriptor(), {}, root, timeout_seconds=30.0)
    assert result.status == "ok", result.text
    rows = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if '"tool_exec"' in line
    ]
    assert rows, log.read_text(encoding="utf-8")
    detail = rows[-1]["detail"]
    for token in ("state_bytes=", "state_files=", "state_roots="):
        assert token in detail, detail
    assert "/" not in detail.split("state_roots=")[1], "no host path belongs in the trail"


# the ceiling beside the folder


def test_the_default_ceiling_is_the_number_the_owner_set(lane, monkeypatch):
    """A bundle that says nothing is still bounded, so the default is the policy."""
    from core.plugin_state import DEFAULT_STATE_CAP_MB, MB, cap_bytes

    _install(lane["tmp"], monkeypatch, [])
    assert DEFAULT_STATE_CAP_MB == 512
    assert cap_bytes(PLUGIN_ID) == 512 * MB


def test_a_bundle_may_ask_for_a_different_ceiling(lane, monkeypatch):
    from core.plugin_state import MB, cap_bytes

    _install(lane["tmp"], monkeypatch, [], cap_mb=2)
    assert cap_bytes(PLUGIN_ID) == 2 * MB


@pytest.mark.parametrize("value", [0, -4, "8", True, 999_999])
def test_a_ceiling_that_is_not_a_stated_number_of_megabytes_refuses_the_manifest(
    lane, monkeypatch, value
):
    root = _install(lane["tmp"], monkeypatch, [])
    manifest = json.loads((root / "ephe-plugin.json").read_text(encoding="utf-8"))
    manifest["permissions"]["state_cap_mb"] = value
    (root / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    _, error = plugin_manifest.load_manifest(root)
    assert error and "state_cap_mb" in error, error


def _fill(home: Path, mb: int) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "kept.bin").write_bytes(b"x" * (mb * 1024 * 1024))


def test_a_bundle_at_its_ceiling_is_refused_before_a_worker_starts(lane, monkeypatch):
    """Nothing spawns, so nothing writes: the ceiling is a gate, and the sentence says both."""
    _skip_without_boundary()
    root = _install(lane["tmp"], monkeypatch, [], cap_mb=1)
    _fill(mcp_sandbox.home_for(f"plugin_{PLUGIN_ID}"), 2)
    result = run_plugin_tool(_descriptor(), {"marker": "ran.txt"}, root, timeout_seconds=30.0)
    assert result.status == "state_full", result.text
    assert result.code == "plugin_state_full"
    assert "[TOOL-DENIED]" in result.text and "512" not in result.text
    assert "1 MB" in result.text and "Extensions" in result.text, result.text
    assert not (mcp_sandbox.home_for(f"plugin_{PLUGIN_ID}") / "ran.txt").exists(), (
        "the refusal still ran the tool it refused"
    )


def test_the_run_that_crosses_is_stated_and_the_next_one_is_refused(lane, monkeypatch):
    """A ceiling enforced mid-write would need a quota no rail here offers. So the row first.

    The child writes 1 MiB into its own folder under a 1 MiB ceiling: the run that crosses is
    allowed and measured, the call after it is refused, and both rows carry the two numbers a
    reader needs to see the crossing rather than be told about it.
    """
    from core import audit_log

    log = lane["tmp"] / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log)
    _skip_without_boundary()
    root = _install(lane["tmp"], monkeypatch, [], cap_mb=1)
    (root / "handlers.py").write_text(
        "def run(arguments, state_dir):\n"
        "    import os\n"
        "    with open(os.path.join(state_dir, 'grown.bin'), 'wb') as handle:\n"
        "        handle.write(b'y' * (1024 * 1024))\n"
        "    return {'grew': True}\n",
        encoding="utf-8",
    )
    descriptor = _descriptor()
    home = mcp_sandbox.home_for(f"plugin_{PLUGIN_ID}")
    first = run_plugin_tool(descriptor, {}, root, timeout_seconds=30.0)
    assert first.status == "ok", first.text
    assert (home / "grown.bin").is_file()

    second = run_plugin_tool(descriptor, {}, root, timeout_seconds=30.0)
    assert second.code == "plugin_state_full", second.text

    rows = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if '"tool_exec"' in line or '"tool_refused"' in line
    ]
    details = [row["detail"] for row in rows]
    assert any("state_cap_bytes=1048576" in d for d in details), details
    crossed = [d for d in details if "state_cap_bytes=1048576" in d][-1]
    assert int(crossed.split("state_bytes=")[1].split()[0]) >= 1024 * 1024, crossed
    assert not any("/Users" in d or "/private" in d for d in details), details


def test_the_refusal_hands_the_surface_both_numbers(lane, monkeypatch):
    """`reason()` is how a card resolves its own words, and the slots have to arrive filled."""
    from core.sandbox import runner

    _skip_without_boundary()
    root = _install(lane["tmp"], monkeypatch, [], cap_mb=1)
    _fill(mcp_sandbox.home_for(f"plugin_{PLUGIN_ID}"), 3)
    answered = runner.execute(_descriptor(), {})
    assert answered.code == "plugin_state_full"
    assert answered.params["plugin"] == PLUGIN_ID
    assert answered.params["cap_mb"] == "1"
    assert int(answered.params["used_mb"]) >= 3


def test_asking_for_the_state_folder_does_not_create_it(lane):
    home = mcp_sandbox.home_path(f"plugin_{PLUGIN_ID}")
    assert not home.exists()


def test_the_extensions_row_carries_usage_and_the_route_removes_one_file(lane, monkeypatch):
    """The row states both numbers. The route lists names and deletes one file.

    A host path stays out of both payloads. A name that leaves the state folder
    does not delete anything, and asking which files exist does not mint the folder.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from core import plugin_state, plugin_store
    from server.routes.plugins import router

    _install(lane["tmp"], monkeypatch, [], cap_mb=2)
    home = mcp_sandbox.home_path(f"plugin_{PLUGIN_ID}")
    assert not home.exists()
    home.mkdir(parents=True)
    (home / "kept.bin").write_bytes(b"x" * 3000)
    nested = home / "nested"
    nested.mkdir()
    (nested / "note.txt").write_text("hello", encoding="utf-8")
    outside = lane["tmp"] / "outside.txt"
    outside.write_text("leave-me", encoding="utf-8")
    (home / "link.txt").symlink_to(outside)

    catalog = {
        "public": [{
            "name": PLUGIN_ID,
            "description": "Acme",
            "tags": [],
            "example_prompts": [],
            "enabled": True,
        }],
        "personal": [],
    }
    monkeypatch.setattr(plugin_store, "load_catalog", lambda *_args, **_kwargs: catalog)
    monkeypatch.setattr(plugin_store, "load_registry", lambda *_args, **_kwargs: [])
    view = plugin_store.plugins_view()
    usage = view["public"][0]["state_usage"]
    assert usage["file_count"] == 3
    assert usage["cap_mb"] == 2
    assert "kept.bin" not in json.dumps(usage)
    assert str(home) not in json.dumps(view["public"][0])

    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    listed = client.get(f"/api/plugins/{PLUGIN_ID}/state")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    names = {entry["name"] for entry in body["entries"]}
    assert names == {"kept.bin", "link.txt", "nested/note.txt"}
    dumped = json.dumps(body)
    assert str(home) not in dumped
    assert "outside.txt" not in dumped
    assert "/Users" not in dumped
    assert body["cap_mb"] == 2

    header = {"X-Requested-With": "XMLHttpRequest"}
    escaped = client.post(
        f"/api/plugins/{PLUGIN_ID}/state/remove",
        json={"name": "../outside.txt"},
        headers=header,
    )
    assert escaped.status_code == 400
    assert outside.read_text(encoding="utf-8") == "leave-me"
    assert (home / "kept.bin").is_file()

    bare = client.post(
        f"/api/plugins/{PLUGIN_ID}/state/remove",
        json={"name": "kept.bin"},
    )
    assert bare.status_code == 403
    assert (home / "kept.bin").is_file()

    removed = client.post(
        f"/api/plugins/{PLUGIN_ID}/state/remove",
        json={"name": "link.txt"},
        headers=header,
    )
    assert removed.status_code == 200, removed.text
    assert not (home / "link.txt").exists()
    assert outside.read_text(encoding="utf-8") == "leave-me"
    assert "link.txt" not in {entry["name"] for entry in removed.json()["entries"]}

    missing = client.get("/api/plugins/not-a-bundle/state")
    assert missing.status_code == 404
    assert plugin_state.LISTED_FILES == 200
