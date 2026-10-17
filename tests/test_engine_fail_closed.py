"""W18/A1+A2: engine choice is fail-closed — CLI AND server, one resolver.

GIVEN no ~/.ephe/engine.json and no engine env
WHEN  the engine is resolved (CLI `tui`/`start` or `run_server.py`)
THEN  the start aborts with an actionable instruction (exit 1) —
      NO silent fallback to local Ollama and NO silent remote default.

Interactive (TTY) starts the onboarding instead; an abort inside it is
also fail-closed (no hidden Ollama fallback).

Pinned additionally: CLI and server use the same resolver
(core.engine_config.resolve_engine_choice) — one source of truth.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.engine_config import (  # noqa: E402
    EngineChoice,
    EngineNotConfigured,
    resolve_engine_choice,
    save_engine_config,
    stdin_is_interactive,
)

PNG_URL = "http://10.1.2.3:8000/v1"
PNG_MODEL = "my-served-model"


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Isolated engine.json + no engine env (conftest clears the env)."""
    isolated = tmp_path / "config"
    isolated.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(isolated))
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", isolated)
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
    yield


def _cli_args(**overrides) -> argparse.Namespace:
    base = dict(
        model=None,
        api_url=None,
        configure=False,
        reset=False,
        dry_run=False,
        yes=False,
        no=False,
        json=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


# (i) fail-closed without config — CLI

class TestCliFailClosed:
    def test_resolver_without_config_raises_engine_not_configured(self):
        with pytest.raises(EngineNotConfigured):
            resolve_engine_choice()

    def test_cli_tui_without_config_exits_1_with_actionable_hint(self, capsys):
        import ephe_cli

        args = _cli_args()
        with pytest.raises(SystemExit) as exc:
            ephe_cli.resolve_engine_choice(args=args)

        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "No engine configured" in err
        # Actionable instruction: the onboarding command plus the env path
        assert "ephe configure" in err
        assert "EPHE_MODEL_PROVIDER" in err
        assert "EPHE_OPENAI_COMPAT_BASE_URL" in err

    def test_cli_start_without_config_leaves_the_setup_mode_to_the_server(
        self, capsys, monkeypatch
    ):
        """PWA-first, without inventing an engine: with no engine chosen `ephe start`
        spawns the server with NO engine env, so run_server's own W19 path enters
        setup mode (chat fail-closed) and the PWA takes the choice in the browser.

        The branch used to apply a placeholder local_ollama + the shipped default tag
        into the child env. The server then looked configured, EPHE_SETUP_MODE stayed
        unset, the chat gate at server/routes/chat.py never armed, and a first turn
        answered for a model nobody chose (H4 in docs/UNBACKED_CLAIMS_2026-10-10.md;
        closed 2026-10-11).
        """
        import ephe_cli

        captured: dict = {}

        class _Proc:
            returncode = 0

        def _fake_run(cmd, env=None):
            captured["env"] = env
            return _Proc()

        monkeypatch.setattr(ephe_cli, "ensure_pwa_built", lambda: None)
        monkeypatch.setattr(ephe_cli, "_run", _fake_run)
        args = _cli_args(host="127.0.0.1", port=8765, lan=False, reload=False,
                         open=False, skip_model_check=True)

        rc = ephe_cli.cmd_start(args)

        assert rc == 0
        for var in ("EPHE_MODEL_PROVIDER", "EPHE_MODEL", "EPHE_OPENAI_COMPAT_BASE_URL"):
            assert captured["env"].get(var) in (None, ""), var
        assert "No engine configured" in capsys.readouterr().out


# (i) fail-closed without config — SERVER

class TestServerFailClosed:
    def test_run_server_loopback_enters_setup_mode_without_engine(self, capsys, monkeypatch):
        """W19: loopback without an engine starts in setup mode instead of aborting —
        otherwise a complete newcomer never sees the UI. Fail-closed stays for the chat and
        (--lan) for the LAN start (see tests/test_w19_setup_start.py)."""
        import run_server

        monkeypatch.setattr(run_server.sys.stdin, "isatty", lambda: False, raising=False)
        monkeypatch.setattr(sys, "argv", ["run_server.py", "--port", "8765"])
        choice = run_server._bootstrap_engine_choice()

        assert choice is None  # no abort, no engine env built
        out = capsys.readouterr().out
        assert "SETUP MODE" in out
        assert os.environ.get("EPHE_MODEL_PROVIDER") in (None, "")

    def test_cli_and_server_report_the_same_failure(self, capsys, monkeypatch):
        """One source: both start paths fail with the identical cause + instruction."""
        import ephe_cli
        import run_server

        monkeypatch.setattr(run_server.sys.stdin, "isatty", lambda: False, raising=False)

        with pytest.raises(EngineNotConfigured) as cli_exc:
            resolve_engine_choice()
        # W19: a server path on loopback goes into setup mode; the identical
        # error message plus instruction shows up in the setup banner (stdout).
        monkeypatch.setattr(sys, "argv", ["run_server.py", "--port", "8765"])
        run_server._bootstrap_engine_choice()
        server_out = capsys.readouterr().out
        with pytest.raises(SystemExit):
            ephe_cli.resolve_engine_choice(args=_cli_args())
        cli_err = capsys.readouterr().err

        assert cli_exc.value.hint in server_out
        assert cli_exc.value.hint in cli_err

    def test_server_bootstrap_applies_persisted_engine(self, tmp_path, monkeypatch):
        """User WITH an engine.json: behaviour unchanged (the env gets set)."""
        cfg = tmp_path / "config" / "engine.json"
        save_engine_config(
            EngineChoice(provider="openai_compatible", model=PNG_MODEL, api_url=PNG_URL),
            cfg,
        )
        import run_server

        choice = run_server._bootstrap_engine_choice()
        assert choice is not None
        assert os.environ["EPHE_MODEL_PROVIDER"] == "openai_compatible"
        assert os.environ["EPHE_OPENAI_COMPAT_BASE_URL"] == PNG_URL
        assert os.environ["EPHE_OPENAI_COMPAT_MODEL"] == PNG_MODEL

    def test_explicit_env_still_wins_and_is_untouched(self, monkeypatch):
        """`ephe start`/Docker set EPHE_MODEL_PROVIDER themselves → no-op."""
        monkeypatch.setenv("EPHE_MODEL_PROVIDER", "local_ollama")
        monkeypatch.setenv("EPHE_MODEL", "gemma4:12b")
        import run_server

        assert run_server._bootstrap_engine_choice() is None
        assert os.environ["EPHE_MODEL_PROVIDER"] == "local_ollama"


# Interactive: onboarding instead of a silent default

class TestInteractiveOnboarding:
    def test_stdin_is_interactive_is_false_under_pytest(self):
        """Pytest's stdin is not a TTY → tests can never run into a prompt."""
        assert stdin_is_interactive() is False

    def test_cli_resolver_runs_onboarding_when_interactive(self, tmp_path, monkeypatch):
        import ephe_cli
        from core import _cli_onboarding

        called: list[str] = []

        def fake_onboarding(input_fn=None, config_path=None):
            called.append("onboarding")
            return EngineChoice(provider="openai_compatible", model=PNG_MODEL, api_url=PNG_URL)

        monkeypatch.setattr(_cli_onboarding, "_run_engine_onboarding", fake_onboarding)
        choice = ephe_cli.resolve_engine_choice(args=_cli_args(), configure=True)

        assert called == ["onboarding"]
        assert choice.model == PNG_MODEL

    def test_onboarding_abort_is_fail_closed(self, tmp_path):
        """Abort (Ctrl+C/EOF) does NOT secretly pick local Ollama."""
        import ephe_cli

        def abort_input(_prompt: str) -> str:
            raise KeyboardInterrupt

        with pytest.raises(EngineNotConfigured):
            ephe_cli._run_engine_onboarding(
                input_fn=abort_input, config_path=tmp_path / "engine.json"
            )
        # and nothing was persisted
        assert not (tmp_path / "engine.json").exists()

    def test_onboarding_preset_3_is_the_dgx_spark_vllm_endpoint(self, tmp_path, capsys):
        """A3 sign-off: the "DGX Spark / vLLM" preset exists in the onboarding."""
        import ephe_cli

        # Order of the prompts in preset 3: option → URL → API key → model
        answers = iter(["3", PNG_URL, "", PNG_MODEL])
        choice = ephe_cli._run_engine_onboarding(
            input_fn=lambda _p: next(answers),
            config_path=tmp_path / "engine.json",
        )

        out = capsys.readouterr().out
        assert "Your own OpenAI-compatible endpoint (DGX Spark / vLLM)" in out
        assert choice.provider == "openai_compatible"
        assert choice.api_url == PNG_URL
        assert choice.model == PNG_MODEL


# `ephe configure`: the way out of the fail-closed state

class TestConfigureCommand:
    def test_configure_persists_the_choice(self, tmp_path, monkeypatch, capsys):
        """Real onboarding flow (only stdin faked) → real persistence."""
        import ephe_cli
        from core import _cli_onboarding
        from core.engine_config import load_engine_config

        real_onboarding = ephe_cli._run_engine_onboarding
        answers = iter(["3", PNG_URL, "", PNG_MODEL])
        monkeypatch.setattr(_cli_onboarding, "_local_ollama_detected", lambda: False)
        monkeypatch.setattr(
            _cli_onboarding,
            "_run_engine_onboarding",
            lambda input_fn=None, config_path=None: real_onboarding(
                input_fn=lambda _p="": next(answers), config_path=config_path
            ),
        )
        args = argparse.Namespace(force=False, json=False)
        cfg = tmp_path / "engine.json"

        assert ephe_cli.cmd_configure(args, config_path=cfg) == 0
        assert cfg.exists(), "configure muss die Wahl persistieren"
        saved = load_engine_config(cfg)
        assert saved is not None
        assert saved.provider == "openai_compatible"
        assert saved.api_url == PNG_URL
        assert saved.model == PNG_MODEL
        assert "ephe start" in capsys.readouterr().out

    def test_configure_is_idempotent_without_force(self, tmp_path, monkeypatch, capsys):
        import ephe_cli

        cfg = tmp_path / "engine.json"
        save_engine_config(EngineChoice(provider="local_ollama", model="gemma4:12b"), cfg)
        monkeypatch.setattr(
            ephe_cli,
            "_run_engine_onboarding",
            lambda input_fn=None, config_path=None: pytest.fail("kein Onboarding ohne --force"),
        )

        assert ephe_cli.cmd_configure(argparse.Namespace(force=False, json=False), config_path=cfg) == 0
        out = capsys.readouterr().out
        assert "already configured" in out
        assert "ephe configure --force" in out

    def test_configure_unknown_flag_is_not_silently_accepted(self):
        """The parser knows the subcommand (otherwise the hint would be a dead end)."""
        import ephe_cli

        args = ephe_cli.build_parser().parse_args(["configure", "--force"])
        assert args.func is ephe_cli.cmd_configure
        assert args.force is True


# Fail-closed also applies to an incomplete engine env

class TestEnvFailClosed:
    def test_provider_without_endpoint_is_a_config_error(self, monkeypatch):
        monkeypatch.setenv("EPHE_MODEL_PROVIDER", "openai_compatible")
        with pytest.raises(EngineNotConfigured) as exc:
            resolve_engine_choice()
        assert "EPHE_OPENAI_COMPAT_BASE_URL" in str(exc.value)

    def test_provider_without_model_is_a_config_error(self, monkeypatch):
        monkeypatch.setenv("EPHE_MODEL_PROVIDER", "openai_compatible")
        monkeypatch.setenv("EPHE_OPENAI_COMPAT_BASE_URL", PNG_URL)
        with pytest.raises(EngineNotConfigured) as exc:
            resolve_engine_choice()
        assert "EPHE_OPENAI_COMPAT_MODEL" in str(exc.value)

    def test_unknown_provider_is_a_config_error(self, monkeypatch):
        monkeypatch.setenv("EPHE_MODEL_PROVIDER", "ollama")
        with pytest.raises(EngineNotConfigured) as exc:
            resolve_engine_choice()
        assert "EPHE_MODEL_PROVIDER" in str(exc.value)

    def test_complete_env_choice_resolves_without_config(self, monkeypatch):
        monkeypatch.setenv("EPHE_MODEL_PROVIDER", "openai_compatible")
        monkeypatch.setenv("EPHE_OPENAI_COMPAT_BASE_URL", PNG_URL)
        monkeypatch.setenv("EPHE_OPENAI_COMPAT_MODEL", PNG_MODEL)
        choice = resolve_engine_choice()
        assert choice.provider == "openai_compatible"
        assert choice.api_url == PNG_URL
        assert choice.model == PNG_MODEL


# (vi) fail-closed also applies to the headless agent runs

class TestHeadlessAgentFailClosed:
    """`ephe code`, `ephe goal` and `ephe serve` were the last silent paths:
    they called the agent without an engine having been chosen, and
    `core.model_provider` fell back to http://localhost:11434 with gemma4:12b.
    The rule knows no exception paths: no run, no port held without a choice."""

    def _react_spy(self, monkeypatch) -> list[dict]:
        import core.react

        calls: list[dict] = []

        async def _fake(**kwargs):
            calls.append(kwargs)
            return "fertig"

        monkeypatch.setattr(core.react, "react_loop", _fake)
        return calls

    def _persist_engine(self, tmp_path, model: str = PNG_MODEL) -> None:
        save_engine_config(
            EngineChoice(provider="openai_compatible", model=model, api_url=PNG_URL),
            tmp_path / "config" / "engine.json",
        )

    def test_ephe_code_ohne_wahl_bricht_und_laesst_den_Lauf_nicht_lo(self, monkeypatch, capsys):
        import ephe_cli

        calls = self._react_spy(monkeypatch)
        with pytest.raises(SystemExit) as exc:
            ephe_cli.cmd_code(argparse.Namespace(task=["mach", "die", "tests", "gruen"], model=None))

        assert exc.value.code == 1
        assert calls == [], "ein Agent gegen eine nicht gewählte Engine ist kein Agent"
        assert "ephe configure" in capsys.readouterr().err

    def test_ephe_goal_ohne_wahl_startt_keinen_runner(self, monkeypatch):
        import ephe_cli

        started: list[dict] = []

        class FakeRunner:
            def __init__(self, **kw):
                started.append(kw)

            async def run(self, goal):  # pragma: no cover — the abort happens before this line runs
                raise AssertionError("der Runner darf ohne Engine nicht laufen")

        monkeypatch.setattr(ephe_cli, "GoalRunner", FakeRunner)
        with pytest.raises(SystemExit) as exc:
            ephe_cli.cmd_goal(argparse.Namespace(
                goal_task=["ziel"], check="pytest -q", max_turns=3, model=None))

        assert exc.value.code == 1
        assert started == []

    def test_ephe_serve_ohne_wahl_haelt_keinen_port_offen(self, monkeypatch):
        import ephe_cli
        import uvicorn

        seen: list[tuple] = []
        monkeypatch.setattr(uvicorn, "run", lambda *a, **k: seen.append(a))
        with pytest.raises(SystemExit) as exc:
            ephe_cli.cmd_serve(argparse.Namespace(
                host="127.0.0.1", port=8766, lan=False, token="", model=None))

        assert exc.value.code == 1
        assert seen == [], "ein Server ohne Engine ist eine Zusage, die niemand haelt"

    def test_ephe_code_mit_gewaehlter_engine_laeuft_mit_ihrer_url(self, tmp_path, monkeypatch):
        import ephe_cli

        self._persist_engine(tmp_path)
        calls = self._react_spy(monkeypatch)
        rc = ephe_cli.cmd_code(argparse.Namespace(task=["x"], model=None))

        assert rc == 0
        assert os.environ["EPHE_MODEL_PROVIDER"] == "openai_compatible"
        assert os.environ["EPHE_OPENAI_COMPAT_BASE_URL"] == PNG_URL
        assert calls[0]["model"] == PNG_MODEL

    def test_model_flag_waehlt_das_Modell_nicht_die_Engine(self, tmp_path, monkeypatch):
        """`--model` is a model name, not an endpoint: it may not swap the engine and
        may not silently fall back to local Ollama."""
        import ephe_cli

        self._persist_engine(tmp_path)
        calls = self._react_spy(monkeypatch)
        rc = ephe_cli.cmd_code(argparse.Namespace(task=["x"], model="gpt-41-mini"))

        assert rc == 0
        assert calls[0]["model"] == "gpt-41-mini"
        assert os.environ["EPHE_MODEL_PROVIDER"] == "openai_compatible"
        assert os.environ["EPHE_OPENAI_COMPAT_BASE_URL"] == PNG_URL

    def test_vorbelegtes_model_flag_ist_keine_Engine_Wahl(self):
        """A default that looks like the flag is the reason for the
        silent runs: with no flag and no EPHE_MODEL the field stays empty."""
        import ephe_cli

        for argv in (["code", "task"], ["goal", "ziel"], ["serve"]):
            ns = ephe_cli.build_parser().parse_args(argv)
            assert ns.model is None, f"{argv[0]}--model ist vorbelegt — Vorbelegung ist keine Wahl"
