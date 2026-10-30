"""Bare `ephe` opens the terminal app; without a terminal it stays a usage call.

The call that names no verb is the one a user types first, so it must reach
the terminal surface. A pipe or a CI step gets the usage page instead of a
terminal app that has no terminal to draw on.
"""

from __future__ import annotations

import os
import sys

import pytest

import core.engine_config as ec
import ephe_cli

PROVIDER_ENV = (
    "EPHE_MODEL_PROVIDER",
    "EPHE_OPENAI_COMPAT_BASE_URL",
    "EPHE_OPENAI_COMPAT_MODEL",
    "EPHE_OPENAI_COMPAT_API_KEY",
    "EPHE_CUSTOM_OLLAMA_BASE_URL",
    "EPHE_LOCAL_OLLAMA_BASE_URL",
    "EPHE_MODEL",
)


class _Stream:
    """A stream that answers ``isatty()`` the way the test needs and forwards the rest."""

    def __init__(self, inner: object, interactive: bool) -> None:
        self._inner = inner
        self._interactive = interactive

    def isatty(self) -> bool:
        return self._interactive

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


def _terminal(monkeypatch: pytest.MonkeyPatch, interactive: bool) -> None:
    monkeypatch.setattr(sys, "stdin", _Stream(sys.stdin, interactive))
    monkeypatch.setattr(sys, "stdout", _Stream(sys.stdout, interactive))


def test_bare_ephe_opens_the_terminal_app(monkeypatch: pytest.MonkeyPatch) -> None:
    _terminal(monkeypatch, True)
    args = ephe_cli._default_command(ephe_cli.build_parser())
    assert args.command == "tui"
    assert args.model is None
    assert args.api_url is None


def test_bare_ephe_without_a_terminal_is_a_usage_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _terminal(monkeypatch, False)
    with pytest.raises(SystemExit) as exc:
        ephe_cli._default_command(ephe_cli.build_parser())
    assert exc.value.code == 2
    assert "usage: ephe" in capsys.readouterr().out


def test_no_subcommand_parses_as_no_command() -> None:
    assert ephe_cli.build_parser().parse_args([]).command is None


def test_a_named_verb_is_untouched() -> None:
    assert ephe_cli.build_parser().parse_args(["doctor"]).command == "doctor"


def test_the_terminal_app_starts_without_a_chosen_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """No engine is no abort any more: the app opens and offers the setup.

    What survives is the stricter half of the rule — no provider is named in the
    environment, so nothing can be sent before the user picks one.
    """
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path)
    for var in PROVIDER_ENV:
        monkeypatch.delenv(var, raising=False)

    import ephe

    seen: dict = {}
    monkeypatch.setattr(ephe, "main", lambda: seen.update(argv=list(sys.argv)))

    args = ephe_cli.build_parser().parse_args(["tui"])
    assert ephe_cli.cmd_tui(args) == 0
    assert seen["argv"] == ["ephe"]
    assert os.environ.get("EPHE_MODEL_PROVIDER") in (None, "")


def test_configure_rewrites_a_half_written_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`ephe configure` is the command that writes the choice; a broken file is no answer."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path)
    ec.save_engine_config(
        ec.EngineChoice(provider="openai_compatible", model="a-tag", api_url=None)
    )

    from core import _cli_onboarding

    asked: list[bool] = []

    def _onboarding(config_path=None):
        asked.append(True)
        return ec.EngineChoice(provider="local_ollama", model="llama3")

    monkeypatch.setattr(_cli_onboarding, "_run_engine_onboarding", _onboarding)
    monkeypatch.setattr(_cli_onboarding, "_print_code_exec_runtime", lambda: None)

    assert _cli_onboarding.cmd_configure(_configure_args()) == 0
    assert asked == [True]
    assert "already configured" not in capsys.readouterr().out


def _configure_args():
    import argparse

    return argparse.Namespace(force=False, json=False)


def test_a_half_written_config_counts_as_no_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A remote provider without its endpoint cannot start; the setup opens instead."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path)
    for var in PROVIDER_ENV:
        monkeypatch.delenv(var, raising=False)
    ec.save_engine_config(
        ec.EngineChoice(provider="openai_compatible", model="a-tag", api_url=None)
    )

    import ephe

    seen: dict = {}
    monkeypatch.setattr(ephe, "main", lambda: seen.update(argv=list(sys.argv)))

    args = ephe_cli.build_parser().parse_args(["tui"])
    assert ephe_cli.cmd_tui(args) == 0
    assert seen["argv"] == ["ephe"]
    assert os.environ.get("EPHE_OPENAI_COMPAT_BASE_URL") in (None, "")
