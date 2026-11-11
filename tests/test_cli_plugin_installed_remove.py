"""PE2E finding 5b/8 — the CLI lists installed bundles and removes one.

`ephe plugin list` read `plugin-catalog.json` only, so a bundle Creator Mode installed
had no row in the terminal either, and `ephe plugin` had no remove verb. The list now
prints the installed set first (with the switch and the tools) and the catalog second;
`ephe plugin remove` previews without `--yes` and commits through the same product path
the market route calls.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import ephe_cli
from tests.support.plugin_bundle import mark_installed, write_bundle


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


def _parser() -> argparse.ArgumentParser:
    return ephe_cli.build_parser()


def _install(device: Path, name: str = "hello-widget", *, enabled: bool = False) -> Path:
    bundle = write_bundle(device / "plugins", name, surface_title="Hello")
    mark_installed(name, enabled=enabled)
    return bundle


def _json_output(capsys) -> dict:
    out = capsys.readouterr().out
    return json.loads(out)


def test_list_prints_the_installed_set_before_the_catalog(device, capsys) -> None:
    _install(device)

    assert ephe_cli.cmd_plugin(_parser().parse_args(["plugin", "list"])) == 0

    out = capsys.readouterr().out
    assert "Installed (" in out
    assert "Catalog (" in out
    installed_at = out.index("Installed (")
    catalog_at = out.index("Catalog (")
    row = out.index("hello-widget")
    assert installed_at < row < catalog_at
    assert "disabled" in out
    assert "now" in out


def test_list_json_separates_installed_rows_from_catalog_rows(device, capsys) -> None:
    _install(device)

    assert ephe_cli.cmd_plugin(_parser().parse_args(["plugin", "list", "--json"])) == 0

    payload = _json_output(capsys)
    assert set(payload) == {"installed", "catalog"}
    row = next(item for item in payload["installed"] if item["name"] == "hello-widget")
    assert row["version"] == "0.1.0"
    assert row["state"] == "disabled"
    assert [tool["name"] for tool in row["capabilities"]["tools"]] == ["now"]
    assert "hello-widget" not in [item["name"] for item in payload["catalog"]]
    shipped = next(item for item in payload["catalog"] if item["name"] == "web-research")
    assert shipped["installed"] is True


def test_remove_without_yes_is_a_preview(device, capsys) -> None:
    bundle = _install(device)

    assert ephe_cli.cmd_plugin(
        _parser().parse_args(["plugin", "remove", "hello-widget"])
    ) == 0

    out = capsys.readouterr().out
    assert "Nothing was removed" in out
    assert "--yes" in out
    assert "disabled" in out
    assert bundle.is_dir()


def test_remove_preview_names_the_switch_a_running_bundle_would_lose(device, capsys) -> None:
    bundle = _install(device, enabled=True)

    assert ephe_cli.cmd_plugin(
        _parser().parse_args(["plugin", "remove", "hello-widget"])
    ) == 0

    out = capsys.readouterr().out
    assert "off first" in out
    assert bundle.is_dir()


def test_remove_yes_removes_the_bundle(device, capsys) -> None:
    bundle = _install(device)

    assert ephe_cli.cmd_plugin(
        _parser().parse_args(["plugin", "remove", "hello-widget", "--yes"])
    ) == 0

    out = capsys.readouterr().out
    assert "Removed 'hello-widget'" in out
    assert "removed" in out
    assert not bundle.exists()


def test_remove_yes_deactivates_an_enabled_bundle_first(device, capsys) -> None:
    bundle = _install(device, enabled=True)

    assert ephe_cli.cmd_plugin(
        _parser().parse_args(["plugin", "remove", "hello-widget", "--yes"])
    ) == 0

    assert "off first" in capsys.readouterr().out
    assert not bundle.exists()


def test_keep_data_leaves_the_stored_files(device, capsys) -> None:
    from core import plugin_state

    _install(device)
    legacy = device / "plugin-data" / "hello-widget"
    legacy.mkdir(parents=True)
    (legacy / "x.json").write_text("{}", encoding="utf-8")
    state_home = plugin_state.state_home("hello-widget")
    state_home.mkdir(parents=True, exist_ok=True)
    (state_home / "client-store.json").write_text("{}", encoding="utf-8")

    assert ephe_cli.cmd_plugin(
        _parser().parse_args(
            ["plugin", "remove", "hello-widget", "--yes", "--keep-data"]
        )
    ) == 0

    assert "kept" in capsys.readouterr().out
    assert legacy.is_dir()
    assert state_home.is_dir()


def test_remove_deletes_the_stored_files_by_default(device, capsys) -> None:
    from core import plugin_state

    _install(device)
    state_home = plugin_state.state_home("hello-widget")
    state_home.mkdir(parents=True, exist_ok=True)
    (state_home / "client-store.json").write_text("{}", encoding="utf-8")

    assert ephe_cli.cmd_plugin(
        _parser().parse_args(["plugin", "remove", "hello-widget", "--yes"])
    ) == 0

    capsys.readouterr()
    assert not state_home.exists()


def test_remove_json_carries_the_same_result_as_the_route(device, capsys) -> None:
    _install(device)

    assert ephe_cli.cmd_plugin(
        _parser().parse_args(["plugin", "remove", "hello-widget", "--yes", "--json"])
    ) == 0

    payload = _json_output(capsys)
    assert payload["status"] == "removed"
    assert payload["name"] == "hello-widget"
    assert payload["removed"]["bundle"] is True
    # Removal clears every record; `remains` reports the state after it.
    assert payload["remains"]["state_record"] is False


def test_remove_preview_json_says_it_removed_nothing(device, capsys) -> None:
    _install(device)

    assert ephe_cli.cmd_plugin(
        _parser().parse_args(["plugin", "remove", "hello-widget", "--json"])
    ) == 0

    payload = _json_output(capsys)
    assert payload["status"] == "preview"
    assert payload["confirmed"] is False
    assert payload["name"] == "hello-widget"


def test_dry_run_is_the_named_preview(device, capsys) -> None:
    bundle = _install(device)

    assert ephe_cli.cmd_plugin(
        _parser().parse_args(["plugin", "remove", "hello-widget", "--dry-run"])
    ) == 0

    assert "Nothing was removed" in capsys.readouterr().out
    assert bundle.is_dir()


def test_an_unknown_name_is_a_runtime_error(device, capsys) -> None:
    assert ephe_cli.cmd_plugin(
        _parser().parse_args(["plugin", "remove", "ghost", "--yes"])
    ) == 1

    assert "not installed" in capsys.readouterr().err


def _subparser(verb: str) -> argparse.ArgumentParser:
    for action in _parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[verb]
    raise AssertionError(f"build_parser() registers no {verb!r} subparser")


def test_remove_help_names_the_preview_and_the_confirmation() -> None:
    plugin = _subparser("plugin")
    remove = next(
        action.choices["remove"]
        for action in plugin._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    text = " ".join(remove.format_help().split())
    assert "--yes" in text
    assert "--keep-data" in text
    assert "--dry-run" in text


def test_a_bundled_plugin_names_the_reason_it_stays(device, capsys) -> None:
    assert ephe_cli.cmd_plugin(
        _parser().parse_args(["plugin", "remove", "countdown", "--yes"])
    ) == 1

    err = capsys.readouterr().err
    assert "ships with Ephe" in err
    assert "cannot be removed" in err


def _installed(device: Path, name: str = "alpha") -> None:
    write_bundle(device / "plugins", name)
    mark_installed(name, enabled=False)


def test_remove_names_dependents_when_they_block_it(device, monkeypatch, capsys):
    """A remove that a dependent blocks names the dependent and the move."""
    from core import marketplace_service

    _installed(device)
    monkeypatch.setattr(
        marketplace_service,
        "remove",
        lambda name, **kw: {
            "status": "dependents_enabled",
            "name": name,
            "dependents": ["alpha", "beta"],
        },
        raising=True,
    )
    code = ephe_cli.cmd_plugin(
        ephe_cli.build_parser().parse_args(["plugin", "remove", "alpha", "--yes"])
    )
    out = capsys.readouterr()
    assert code == 1
    assert "required by enabled dependents" in (out.out + out.err)
    assert "alpha, beta" in (out.out + out.err)


def test_remove_reports_a_still_active_bundle_with_the_next_command(device, monkeypatch, capsys):
    from core import marketplace_service

    _installed(device)
    monkeypatch.setattr(
        marketplace_service,
        "remove",
        lambda name, **kw: {"status": "still_active", "name": name, "enabled": True},
        raising=True,
    )
    code = ephe_cli.cmd_plugin(
        ephe_cli.build_parser().parse_args(["plugin", "remove", "alpha", "--yes"])
    )
    out = capsys.readouterr()
    assert code == 1
    assert "still enabled" in (out.out + out.err)
    assert "ephe plugin disable alpha" in (out.out + out.err)


def test_remove_reports_an_unknown_failure_code(device, monkeypatch, capsys):
    from core import marketplace_service

    _installed(device)
    monkeypatch.setattr(
        marketplace_service,
        "remove",
        lambda name, **kw: {"status": "failed", "code": "lockfile_error", "name": name},
        raising=True,
    )
    code = ephe_cli.cmd_plugin(
        ephe_cli.build_parser().parse_args(["plugin", "remove", "alpha", "--yes"])
    )
    out = capsys.readouterr()
    assert code == 1
    assert "lockfile_error" in (out.out + out.err)


def _fake_install(status: dict):
    from core import plugin_market

    return lambda *a, **k: status


def test_install_success_names_the_version_and_the_switch(device, monkeypatch, capsys):
    from core import plugin_market

    monkeypatch.setattr(
        plugin_market,
        "install_from_marketplace",
        _fake_install(
            {"status": "extracted", "version": "2.0.0", "warning": "local_trust"}
        ),
        raising=True,
    )
    code = ephe_cli.cmd_plugin(
        ephe_cli.build_parser().parse_args(
            ["plugin", "install", "alpha", "--trust-local"]
        )
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "v2.0.0" in out and "local trust" in out


def test_install_refusal_names_the_trust_flag(device, monkeypatch, capsys):
    from core import plugin_market

    monkeypatch.setattr(
        plugin_market,
        "install_from_marketplace",
        _fake_install({"status": "local_trust_required", "error": "needs consent"}),
        raising=True,
    )
    code = ephe_cli.cmd_plugin(
        ephe_cli.build_parser().parse_args(["plugin", "install", "alpha"])
    )
    out = capsys.readouterr()
    assert code == 1
    assert "--trust-local" in (out.out + out.err)


def test_an_unknown_action_is_a_parser_error_not_a_silent_success(device):
    with pytest.raises(SystemExit) as excinfo:
        ephe_cli.build_parser().parse_args(["plugin", "frobnicate", "alpha"])
    assert excinfo.value.code != 0


def test_enable_success_reports_the_state(device, monkeypatch, capsys):
    from core import plugin_runtime

    _installed(device)

    class _Snapshot:
        state = type("S", (), {"value": "enabled"})()

    monkeypatch.setattr(
        plugin_runtime.lifecycle(), "set_enabled", lambda *a, **k: _Snapshot(), raising=False
    )
    code = ephe_cli.cmd_plugin(
        ephe_cli.build_parser().parse_args(["plugin", "enable", "alpha"])
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "next agent turn" in out


def test_an_unreachable_status_still_names_a_next_step(monkeypatch, capsys):
    """`local_trust_required` gets the flag hint even when no other branch matches."""
    from core import plugin_market

    monkeypatch.setattr(
        plugin_market,
        "install_from_marketplace",
        _fake_install({"status": "local_trust_required"}),
        raising=True,
    )
    code = ephe_cli.cmd_plugin(
        ephe_cli.build_parser().parse_args(["plugin", "install", "alpha"])
    )
    out = capsys.readouterr()
    assert code == 1
    assert "trust-local" in (out.out + out.err)


def test_install_of_an_unknown_id_names_the_listing(monkeypatch, capsys):
    from core import plugin_market

    monkeypatch.setattr(
        plugin_market,
        "install_from_marketplace",
        _fake_install({"status": "unknown_plugin", "error": "not listed"}),
        raising=True,
    )
    code = ephe_cli.cmd_plugin(
        ephe_cli.build_parser().parse_args(["plugin", "install", "nope"])
    )
    out = capsys.readouterr()
    assert code == 1
    assert "plugin-marketplace.json" in (out.out + out.err)
