"""◑ Ephe – tests for engine selection/onboarding in the TUI CLI.

Covers the new capability: `ephe tui` starts without a model flag,
interactive engine selection (onboarding) and persistence to engine.json.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import patch

import core.engine_config as ec
import ephe_cli as cli

ROOT = Path(__file__).resolve().parents[1]


def _fake_input(*values: str):
    """Builds an input_fn that returns the given answers one after another."""
    queue = list(values)

    def fn(prompt: str) -> str:
        assert queue, f"input_fn wurde öfter aufgerufen als Antworten vorhanden: {prompt}"
        return queue.pop(0)

    return fn


def test_onboarding_local_ollama_persists_the_tag_that_was_typed(tmp_path, monkeypatch):
    """GIVEN the user picks engine 1 (local Ollama) and types a tag
    WHEN onboarding runs
    THEN local_ollama is persisted with exactly that tag and found again.

    The pair to this test used to press Enter on an empty model prompt and assert the
    stored tag equalled core._cli_common.DEFAULT_MODEL, a value RAM-sized on the
    machine that ran it. Since 2026-10-11 the product names no model, so an empty
    answer asks again and nothing is stored until the user answers
    (owner decision 2026-10-11).
    """
    monkeypatch.delenv("EPHE_MODEL", raising=False)

    choice = cli._run_engine_onboarding(
        input_fn=_fake_input("1", "mine:work"), config_path=tmp_path / "engine.json"
    )

    assert choice.provider == "local_ollama"
    assert choice.model == "mine:work"
    assert choice.api_url is None

    reloaded = ec.load_engine_config(tmp_path / "engine.json")
    assert reloaded is not None
    assert reloaded.provider == "local_ollama"
    assert reloaded.model == "mine:work"
    assert reloaded.api_url is None


def test_onboarding_shows_a_default_only_when_the_user_supplied_one(tmp_path, monkeypatch):
    """The offer and the stored value are one fact, and the only source of the offer is
    the user's own env.

    Onboarding prints `Modell [Default x]:`  # language-gate: ignore (quoted German surface prompt as it ships, core/_cli_onboarding.py:106)
    and stores x on an empty Enter. x used to come from the engine template and then
    from RAM sizing — a machine-shaped offer is not a user's choice, and on an 8 GB
    runner it stored a 12b tag that cannot load there.
    """
    monkeypatch.setenv("EPHE_MODEL", "mine:from-env")

    prompts: list[str] = []

    def input_fn(prompt: str) -> str:
        prompts.append(prompt)
        return "1" if len(prompts) == 1 else ""

    choice = cli._run_engine_onboarding(
        input_fn=input_fn, config_path=tmp_path / "engine.json"
    )

    shown = prompts[-1].partition("[default ")[2].partition("]")[0]
    assert shown == "mine:from-env", prompts
    assert choice.model == shown


def test_onboarding_openai_compat_preset_requires_url_and_model(tmp_path):
    """GIVEN the user picks engine 3 (preset "Your own OpenAI-compatible endpoint
              (DGX Spark / vLLM)")
    WHEN URL and model are typed in (without an API key)
    THEN openai_compatible is persisted with URL and model — the key
         stays empty (no implicit access grant, W18/A4)."""
    choice = cli._run_engine_onboarding(
        # Prompts: option → URL → API key (empty) → model
        input_fn=_fake_input("3", "http://10.1.2.3:8000/v1", "", "my-served-model"),
        config_path=tmp_path / "engine.json",
    )

    assert choice.provider == "openai_compatible"
    assert choice.model == "my-served-model"
    assert choice.api_url == "http://10.1.2.3:8000/v1"
    import os

    assert not os.environ.get("EPHE_OPENAI_COMPAT_API_KEY"), "kein Key gesetzt erwartet"

    reloaded = ec.load_engine_config(tmp_path / "engine.json")
    assert reloaded is not None
    assert reloaded.provider == "openai_compatible"
    assert reloaded.api_url == "http://10.1.2.3:8000/v1"


def test_onboarding_invalid_choice_retries_until_ok(tmp_path):
    """GIVEN the user types an invalid engine choice (9)
    WHEN onboarding answers with a valid choice the next time
    THEN it continues with the valid choice."""
    choice = cli._run_engine_onboarding(
        input_fn=_fake_input("9", "1", "mine:work"), config_path=tmp_path / "engine.json"
    )

    assert choice.provider == "local_ollama"
    assert choice.model == "mine:work"


def test_engine_config_roundtrip_and_clear(tmp_path):
    """GIVEN an engine selection is saved
    WHEN it is loaded and then removed
    THEN the roundtrip is identical and clear returns None."""
    cfg = tmp_path / "engine.json"
    assert ec.save_engine_config(
        ec.EngineChoice(provider="local_ollama", model="gemma4:12b"), cfg
    )

    loaded = ec.load_engine_config(cfg)
    assert loaded is not None
    assert loaded.model == "gemma4:12b"

    assert ec.clear_engine_config(cfg)
    assert ec.load_engine_config(cfg) is None


def test_cmd_tui_without_flags_uses_persisted_config(tmp_path):
    """GIVEN an engine config exists (DGX Spark)
    WHEN `cmd_tui` runs without model/URL flags
    THEN model and URL are forwarded to `ephe.main()` as flags."""
    cfg = tmp_path / "engine.json"
    ec.save_engine_config(
        ec.EngineChoice(
            provider="openai_compatible",
            model="deepseek-v4-flash",
            api_url="http://spark-...:8000/v1",
        ),
        cfg,
    )

    args = argparse.Namespace(model=None, api_url=None, configure=False, reset=False,
                              dry_run=False, yes=False, no=False)
    captured: list[list[str]] = []
    with patch("ephe.main", side_effect=lambda: captured.append(sys.argv.copy())):
        cli.cmd_tui(args, config_path=cfg)

    assert captured == [
        ["ephe", "--model", "deepseek-v4-flash", "--api-url", "http://spark-...:8000/v1"]
    ]


def test_cmd_tui_explicit_flags_skip_onboarding(tmp_path):
    """GIVEN the user passes --model and --api-url explicitly
    WHEN `cmd_tui` runs (even with --configure)
    THEN the flags win and no onboarding is triggered."""
    args = argparse.Namespace(
        model="gemma4:12b",
        api_url="http://custom:8000/v1",
        configure=True,
        reset=False,
        dry_run=False,
        yes=False,
        no=False,
    )
    captured: list[list[str]] = []
    with patch("ephe.main", side_effect=lambda: captured.append(sys.argv.copy())), patch(
        "ephe_cli._run_engine_onboarding"
    ) as onboarding:
        cli.cmd_tui(args, config_path=tmp_path / "engine.json")

    assert captured == [
        ["ephe", "--model", "gemma4:12b", "--api-url", "http://custom:8000/v1"]
    ]
    onboarding.assert_not_called()


# Phase 0: Security-Gate (AppSec/Least-Privilege)
import stat


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_saved_engine_config_file_permissions_0600(tmp_path):
    """GIVEN an engine selection is saved
    WHEN the file has been created
    THEN engine.json is 0600 (owner-only read/write) – least privilege."""
    cfg = tmp_path / "engine.json"
    assert ec.save_engine_config(
        ec.EngineChoice(provider="openai_compatible", model="deepseek-v4-flash", api_url="http://x/v1"), cfg
    )
    assert _mode(cfg) == 0o600


def test_saved_engine_config_dir_permissions_0700(tmp_path):
    """GIVEN an engine selection is saved
    WHEN the config directory is created
    THEN it is 0700 (owner only) – no side channels for other processes."""
    cfg_dir = tmp_path / "cfg"
    cfg = cfg_dir / "engine.json"
    assert ec.save_engine_config(ec.EngineChoice(provider="local_ollama", model="gemma4:12b"), cfg)
    assert _mode(cfg_dir) == 0o700


def test_saved_engine_config_never_persists_api_key(tmp_path):
    """GIVEN an OpenAI-compatible engine is saved together with an API key
    WHEN the file is written
    THEN engine.json contains NO key/secret field (keys stay in the session env)."""
    cfg = tmp_path / "engine.json"
    assert ec.save_engine_config(
        ec.EngineChoice(
            provider="openai_compatible", model="custom-model", api_url="https://api.example/v1"
        ),
        cfg,
    )
    raw = cfg.read_text(encoding="utf-8").lower()
    for forbidden in ("api_key", "apikey", "secret", "token", "key"):
        assert forbidden not in raw, f"engine.json darf kein '{forbidden}'-Feld enthalten: {raw}"
