"""`ephe plugin` says what it does: the help text and the answers are the same truth.

Two defects this pins. `ephe plugin list` read the curated catalog only, so a bundle the
author had just put under the plugins root — the one `enable` accepts — was invisible, while
`enable`'s help said the id comes from that list. And an install that refused printed a
status and a reason and stopped; the flag that would have carried it (`--trust-local`) was
in the parser and in no help text, so the reader had to find it in the source.

Held together: every action the `--help` text names is a parser choice, the list shows what
the scanner reads, and every refusal names the code, the reason and the next command.
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

import ephe_cli
from core import plugin_manifest


def _parser():
    return ephe_cli.build_parser()


def _help_text(*argv: str) -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), pytest.raises(SystemExit):
        _parser().parse_args([*argv, "--help"])
    return buffer.getvalue()


def _subparser(name: str):
    for action in _parser()._actions:
        if hasattr(action, "choices") and action.choices and name in action.choices:
            return action.choices[name]
    raise AssertionError(f"no subparser {name}")


def _actions(parser) -> list[str]:
    for action in parser._actions:
        if hasattr(action, "choices") and action.choices:
            return list(action.choices)
    return []


def test_the_help_names_every_action_the_parser_takes():
    """GIVEN the `plugin` subparser and its help
    WHEN both are read
    THEN the help names exactly the actions a reader can type, plus what list shows."""
    help_text = _help_text("plugin")
    actions = _actions(_subparser("plugin"))

    assert actions == ["list", "enable", "disable", "install", "remove"]
    for name in actions:
        assert name in help_text, f"`{name}` is a parser action the help does not name"
    for word in ("installed", "catalog", "switch state"):
        assert word in help_text.lower(), word


def test_the_help_names_the_flag_an_unsigned_local_artifact_needs():
    """`--trust-local` is the difference between an install and a refusal; a help text
    without it sends the reader into the refusal to find it."""
    help_text = _help_text("plugin")

    assert "--trust-local" in help_text
    assert "Example:" in help_text


def test_each_action_help_says_what_the_action_changes():
    """The one-line help is the only sentence a reader sees at the prompt, and the parent
    listing is where every one of them is shown."""
    parent = _help_text("plugin")
    assert "next agent turn" in parent.lower()
    assert "unsigned" in parent.lower()
    assert "installed" in parent.lower()
    flat = " ".join(parent.split())
    plugin_parser = _subparser("plugin")
    for action in plugin_parser._actions:
        for entry in getattr(action, "_choices_actions", []):
            one_line = str(entry.help or "").strip()
            assert one_line, f"{entry.dest}: no one-line help"
            # the listing wraps at the terminal width; the sentence is still the same one
            assert one_line in flat, f"{entry.dest}: help is not in the listing"


@pytest.fixture()
def device(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    (config / "plugins").mkdir(parents=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", None)
    return config


def _write_bundle(root: Path, name: str, *, broken: bool = False) -> None:
    directory = root / name
    (directory / "ui").mkdir(parents=True)
    if broken:
        (directory / "ephe-plugin.json").write_text("{not json", encoding="utf-8")
        return
    (directory / "ephe-plugin.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "name": name,
                "version": "0.1.0",
                "description": "Says hello.",
                "permissions": {"tool_families": [], "data_roots": []},
                "components": {
                    "ui": {"type": "floating-window", "entry": "ui/index.html"},
                    "skills": [],
                    "commands": [],
                },
            }
        ),
        encoding="utf-8",
    )
    (directory / "ui" / "index.html").write_text(
        "<!doctype html><p>Hello.</p>\n", encoding="utf-8"
    )


def test_the_list_shows_a_bundle_the_scanner_reads(device, capsys):
    """GIVEN a bundle placed under the plugins root by hand
    WHEN `ephe plugin list` runs
    THEN the bundle is a row — it is the id `enable` accepts."""
    _write_bundle(device / "plugins", "hello-card")

    assert ephe_cli.cmd_plugin(_parser().parse_args(["plugin", "list"])) == 0
    out = capsys.readouterr().out

    assert "hello-card" in out
    assert "0.1.0" in out


def test_the_list_explains_a_bundle_the_scanner_refuses(device, capsys):
    """GIVEN a folder whose manifest the loader refuses
    WHEN the list runs
    THEN the row is there, with the loader's reason and the step that fixes it."""
    _write_bundle(device / "plugins", "broken-card", broken=True)

    assert ephe_cli.cmd_plugin(_parser().parse_args(["plugin", "list"])) == 0
    out = capsys.readouterr().out

    assert "broken-card" in out
    assert "ephe-plugin.json" in out
    assert "`ephe plugin list`" in out


def test_an_install_refusal_names_the_code_the_reason_and_the_next_command(
    device, monkeypatch, capsys
):
    """GIVEN an install path that refuses an unsigned local artifact
    WHEN `ephe plugin install` runs
    THEN stderr carries the status, the reason and `--trust-local`."""
    import core.plugin_market as market

    monkeypatch.setattr(
        market,
        "install_from_marketplace",
        lambda pid, **kwargs: {
            "status": "local_trust_required",
            "name": pid,
            "error": "a local unsigned artifact needs explicit trust",
        },
    )

    code = ephe_cli.cmd_plugin(_parser().parse_args(["plugin", "install", "countdown"]))
    captured = capsys.readouterr()

    assert code == 1
    assert "local_trust_required" in captured.err
    assert "explicit trust" in captured.err
    assert "--trust-local" in captured.err


def test_an_unknown_plugin_install_names_the_listing(device, monkeypatch, capsys):
    import core.plugin_market as market

    monkeypatch.setattr(
        market,
        "install_from_marketplace",
        lambda pid, **kwargs: {
            "status": "unknown_plugin",
            "name": pid,
            "error": "not in marketplace listing",
        },
    )

    assert ephe_cli.cmd_plugin(_parser().parse_args(["plugin", "install", "nope"])) == 1
    err = capsys.readouterr().err
    assert "unknown_plugin" in err
    assert "plugin-marketplace.json" in err


def test_an_enable_refusal_names_the_list_that_holds_the_ids(device, monkeypatch, capsys):
    import core.plugin_lifecycle as lifecycle_module
    import core.plugin_runtime as runtime

    class Deny:
        def set_enabled(self, *args, **kwargs):
            raise lifecycle_module.LifecycleError("unknown_plugin", 404, "not installed")

    monkeypatch.setattr(runtime, "lifecycle", lambda *a, **k: Deny())

    assert ephe_cli.cmd_plugin(_parser().parse_args(["plugin", "enable", "nope"])) == 1
    err = capsys.readouterr().err
    assert "unknown_plugin" in err
    assert "ephe plugin list" in err
