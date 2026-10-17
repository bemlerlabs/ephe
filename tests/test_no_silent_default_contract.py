"""W3-17 — the no-silent-default contract, end to end (engine, launch, docs).

One rule, stated in README.md:11/233, AGENTS.md:6, docs/CLI.md:3/5:

    A model name is not an engine choice. Nothing picks an engine on the user's
    behalf; without a chosen engine the surface fails closed instead of falling
    back to local Ollama.

`engine_for_headless_run` implements exactly that for `ephe code` / `ephe goal`
/ `ephe serve` (pinned by tests/test_engine_fail_closed.py). The launch paths
`ephe start` (cmd_start) and `ephe tui` (cmd_tui) now resolve their engine the
same way, so a model/url flag can no longer force one.

The file is the executable half of the audit: the control test pins the rule on
the path that respects it, and the four hole tests pin it on the launch paths.
Each stood behind `xfail(strict=True)` — green while the hole was open, RED
(XPASS) the moment a fix landed — so the contract cannot regress in silence. All
four were closed in wave 4; see the `# HOLE n — CLOSED` notes below.
"""

import argparse
import os
import pathlib

import pytest

from core.engine_config import EngineChoice, save_engine_config

REMOTE_URL = "http://10.1.2.3:8000/v1"
REMOTE_MODEL = "my-served-model"


@pytest.fixture(autouse=True)
def _isolated_engine(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """A clean device: isolated engine.json, no engine env, no session override."""
    isolated = tmp_path / "config"
    isolated.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(isolated))
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", isolated, raising=False)
    for var in (
        "EPHE_MODEL_PROVIDER",
        "EPHE_OPENAI_COMPAT_BASE_URL",
        "EPHE_OPENAI_COMPAT_MODEL",
        "EPHE_OPENAI_COMPAT_API_KEY",
        "EPHE_CUSTOM_OLLAMA_BASE_URL",
        "EPHE_LOCAL_OLLAMA_BASE_URL",
        "EPHE_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)
    import core.model_provider as mp

    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", None, raising=False)
    yield isolated


def _persist_remote(config_dir: pathlib.Path) -> None:
    save_engine_config(
        EngineChoice(provider="openai_compatible", model=REMOTE_MODEL, api_url=REMOTE_URL),
        config_dir / "engine.json",
    )


def _start_args(*argv: str) -> argparse.Namespace:
    import ephe_cli

    args = ephe_cli.build_parser().parse_args(["start", *argv])
    args.skip_model_check = True
    return args


def _tui_args(*argv: str) -> argparse.Namespace:
    import ephe_cli

    return ephe_cli.build_parser().parse_args(["tui", *argv])


# CONTROL — the path that respects the rule (must pass today)


def test_control_headless_model_flag_keeps_the_chosen_engine(tmp_path):
    """`engine_for_headless_run` — the contract the launch paths must match.

    `--model` picks the model *inside* the chosen engine; it may not swap the
    engine and may not fall back to local Ollama.
    """
    from core._cli_onboarding import engine_for_headless_run

    _persist_remote(tmp_path / "config")
    choice = engine_for_headless_run(args=_tui_args(), model_override="gpt-41-mini")

    assert choice.provider == "openai_compatible"
    assert choice.api_url == REMOTE_URL
    assert choice.model == "gpt-41-mini"
    assert os.environ["EPHE_MODEL_PROVIDER"] == "openai_compatible"


# HOLE 1 — CLOSED (W4-9): `ephe start --model <tag>` keeps the chosen engine


def test_start_model_flag_may_not_swap_the_chosen_engine(monkeypatch, tmp_path):
    """A bare `--model` picks the model *inside* the chosen engine (R15 H1).

    `cmd_start` resolves the engine first (`engine.json` → engine env →
    onboarding → fail-closed) and then applies the tag to that engine, so a
    model flag can no longer swap a persisted remote engine for local Ollama.
    """
    import ephe_cli

    _persist_remote(tmp_path / "config")
    captured: dict = {}

    class _Proc:
        returncode = 0

    monkeypatch.setattr(ephe_cli, "ensure_pwa_built", lambda: None)
    monkeypatch.setattr(
        ephe_cli, "_run", lambda cmd, env=None: (captured.update(env=env), _Proc())[1]
    )

    rc = ephe_cli.cmd_start(_start_args("--model", "gpt-41-mini"))

    assert rc == 0
    child = captured["env"]
    # The persisted remote engine must survive a mere model flag.
    assert child.get("EPHE_MODEL_PROVIDER") == "openai_compatible"
    assert child.get("EPHE_OPENAI_COMPAT_BASE_URL") == REMOTE_URL


# HOLE 1b — CLOSED (W4-9): `--model` without an engine leaves setup mode to the server


def test_start_model_flag_without_any_engine_must_not_open_the_chat(
    monkeypatch, tmp_path
):
    """With no chosen engine a `--model` tag stays out of the child env (R15 H1b).

    The tag is applied only to an engine resolution already produced; with no
    `engine.json`/env the start drops it, so the server enters setup mode and the
    chat stays closed instead of answering against localhost:11434.
    """
    import ephe_cli

    captured: dict = {}

    class _Proc:
        returncode = 0

    monkeypatch.setattr(ephe_cli, "ensure_pwa_built", lambda: None)
    monkeypatch.setattr(
        ephe_cli, "_run", lambda cmd, env=None: (captured.update(env=env), _Proc())[1]
    )

    rc = ephe_cli.cmd_start(_start_args("--model", "ghost-tag"))

    assert rc == 0
    # No engine chosen → no engine may be named in the child env, so the server
    # enters setup mode (EPHE_SETUP_MODE) and the chat stays closed.
    assert captured["env"].get("EPHE_MODEL_PROVIDER") in (None, "")


# HOLE 2 — CLOSED (W4-10): `ephe tui --model <tag>` keeps the chosen engine


def test_tui_model_flag_may_not_swap_the_chosen_engine(monkeypatch, tmp_path):
    """A bare `--model` picks the model *inside* the chosen engine (R15 H2).

    `cmd_tui` routes `ephe tui --model` through `engine_for_headless_run` — the
    same resolver (`engine.json` → engine env → onboarding → abort) that
    `ephe code`/`ephe goal`/`ephe serve` use — so a model flag can no longer
    swap a persisted remote engine for local Ollama.
    """
    import ephe
    import ephe_cli

    _persist_remote(tmp_path / "config")
    monkeypatch.setattr(ephe, "main", lambda: None)

    rc = ephe_cli.cmd_tui(_tui_args("--model", "gpt-41-mini"))

    assert rc == 0
    assert os.environ["EPHE_MODEL_PROVIDER"] == "openai_compatible"
    assert os.environ.get("EPHE_OPENAI_COMPAT_BASE_URL") == REMOTE_URL


# HOLE 3 — CLOSED (W4-11): `ephe tui --api-url <url>` without `--model` names an
# engine ENDPOINT but no tag; it must fail closed with the missing variable's name
# (EPHE_OPENAI_COMPAT_MODEL, cf. README.md:233) instead of letting
# EngineChoice(model=None) crash with a bare AttributeError from __post_init__.


def test_tui_api_url_without_model_fails_closed_with_a_named_variable(monkeypatch, tmp_path):
    from core.engine_config import EngineNotConfigured
    import ephe
    import ephe_cli

    monkeypatch.setattr(ephe, "main", lambda: None)

    with pytest.raises(EngineNotConfigured) as exc:
        ephe_cli.cmd_tui(_tui_args("--api-url", REMOTE_URL))

    assert "EPHE_OPENAI_COMPAT_MODEL" in str(exc.value)
