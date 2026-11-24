"""`ephe plugin remove` removes nothing until the reader says so, in a real tree.

The preview is the product's default, so the test that matters is the one that
compares a `tmp_path` directory before and after: same files, same bytes, same
rows. The commit test then demands the opposite — the folder, the registry row and
the lockfile entry gone, and the stored files kept or deleted exactly as the flags
said.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import ephe_cli
from core import plugin_versions
from core.plugin_store import installed_bundles, registry_path, sha256_hex
from tests.support.plugin_bundle import mark_installed, write_bundle

NAME = "hello-widget"


@pytest.fixture()
def device(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    config.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    from core import plugin_runtime
    from core.skills import invalidate_skill_cache

    plugin_runtime.invalidate_ownership_cache()
    invalidate_skill_cache()
    yield config
    plugin_runtime.invalidate_ownership_cache()
    invalidate_skill_cache()


def _install_in(config: Path, *, enabled: bool = False, with_data: bool = True) -> Path:
    from core.plugin_store import set_enabled

    bundle = write_bundle(config / "plugins", NAME, surface_title="Hello")
    set_enabled(NAME, enabled, path=registry_path())
    mark_installed(NAME, enabled=enabled)
    if with_data:
        data = config / plugin_versions.DATA_DIRNAME / NAME
        data.mkdir(parents=True, exist_ok=True)
        (data / "note.json").write_text('{"kept": true}\n', encoding="utf-8")
    return bundle


def _state(root: Path) -> dict[str, str]:
    """Every file below `root` with its digest — the comparison a preview must pass."""
    if not root.is_dir():
        return {}
    return {
        str(path.relative_to(root)): sha256_hex(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _run(argv: list[str], capsys) -> tuple[int, str, str]:
    code = ephe_cli.cmd_plugin(ephe_cli.build_parser().parse_args(list(argv)))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_a_remove_without_the_word_leaves_the_tree_byte_identical(device, capsys) -> None:
    """The default verb of `remove` is a preview: the config directory it prints
    about is the same directory it must not touch, file for file and byte for byte."""
    _install_in(device)
    before = {
        "plugins": _state(device / "plugins"),
        "data": _state(device / plugin_versions.DATA_DIRNAME),
        "root": _state(device),
    }

    code, out, err = _run(["plugin", "remove", NAME], capsys)

    assert code == 0, (out, err)
    assert "Nothing was removed" in out, out
    assert "--yes" in out, out
    after = {
        "plugins": _state(device / "plugins"),
        "data": _state(device / plugin_versions.DATA_DIRNAME),
        "root": _state(device),
    }
    assert after == before
    assert (device / "plugins" / NAME / "ephe-plugin.json").is_file()
    assert any(item["name"] == NAME for item in installed_bundles())


def test_the_preview_names_what_would_go_and_what_would_stay(device, capsys) -> None:
    """A preview that lists nothing is a preview nobody can decide on: the stored
    files, the switch and the state record each get a line of their own."""
    _install_in(device, enabled=True)

    code, out, err = _run(["plugin", "remove", NAME], capsys)

    assert code == 0, (out, err)
    assert "Would remove:" in out, out
    assert "the switch: it is on and would be turned off first" in out, out
    assert "the stored files" in out, out
    assert "Would keep:" in out, out
    assert "the lifecycle state record" in out, out


def test_the_json_preview_says_it_removed_nothing_and_writes_nothing(device, capsys) -> None:
    """`--json` is the same answer for a machine: `confirmed: false` and the tree
    unchanged, because a script must not need to know that the flag means preview."""
    _install_in(device)
    before = _state(device)

    code, out, err = _run(["plugin", "remove", NAME, "--json"], capsys)

    assert code == 0, (out, err)
    payload = json.loads(out)
    assert payload["status"] == "preview", payload
    assert payload["confirmed"] is False, payload
    assert payload["name"] == NAME, payload
    assert _state(device) == before


def test_named_dry_run_is_the_default_preview(device, capsys) -> None:
    """`--dry-run` is the default with a word on it: the same answer, the same
    untouched tree."""
    _install_in(device)
    before = _state(device)

    code, out, err = _run(["plugin", "remove", NAME, "--dry-run"], capsys)

    assert code == 0, (out, err)
    assert "Nothing was removed" in out, out
    assert _state(device) == before


def test_yes_takes_the_folder_the_row_and_the_lock_entry(device, capsys) -> None:
    """The commit removes all three records a bundle lives in, and says so."""
    _install_in(device)
    lock = device / "plugin-lock.json"
    lock.write_text(
        json.dumps({"format": 1, "plugins": [{"name": NAME, "version": "0.1.0", "sha256": "0" * 64}]}),
        encoding="utf-8",
    )

    code, out, err = _run(["plugin", "remove", NAME, "--yes"], capsys)

    assert code == 0, (out, err)
    assert "removed" in out.lower(), out
    assert not (device / "plugins" / NAME).exists()
    assert not any(item["name"] == NAME for item in installed_bundles())
    if lock.exists():
        assert NAME not in lock.read_text(encoding="utf-8"), lock.read_text(encoding="utf-8")


def test_yes_deletes_the_stored_files_and_keep_data_leaves_them(device, capsys) -> None:
    """The stored files are the reader's, so the flag that keeps them is the one
    that must survive the commit verbatim."""
    _install_in(device)
    data = device / plugin_versions.DATA_DIRNAME / NAME

    code, out, err = _run(["plugin", "remove", NAME, "--yes", "--keep-data"], capsys)

    assert code == 0, (out, err)
    assert (data / "note.json").is_file(), _state(device)

    _install_in(device)
    code, out, err = _run(["plugin", "remove", NAME, "--yes"], capsys)

    assert code == 0, (out, err)
    assert not data.exists(), _state(device)


def test_a_removal_of_a_name_that_is_not_installed_touches_nothing(device, capsys) -> None:
    """The refusal for an unknown name arrives before any path is opened, and the
    tree of an installed neighbour proves it."""
    _install_in(device)
    before = _state(device)

    code, out, err = _run(["plugin", "remove", "not-installed-at-all", "--yes"], capsys)

    assert code == 1, (out, err)
    assert "not installed" in (out + err), (out, err)
    assert _state(device) == before
