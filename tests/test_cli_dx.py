"""Phase 1 DX gate: shell completions, --version, exit codes, JSON error hardening."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.subprocess_env import hermetic_env

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "ephe_cli.py"
DOCS_CLI = ROOT / "docs" / "CLI.md"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Runs the real CLI (integration)."""
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        env=hermetic_env(PYTHONPATH=""),
    )


def test_completion_bash():
    r = _run("completion", "bash")
    assert r.returncode == 0
    assert "complete -F _ephe_complete ephe" in r.stdout
    for cmd in ("start", "doctor", "update", "tui", "completion"):
        assert cmd in r.stdout


def test_completion_zsh():
    r = _run("completion", "zsh")
    assert r.returncode == 0
    assert "_describe 'command' cmds" in r.stdout
    assert "compdef _ephe ephe" in r.stdout


def test_completion_fish():
    r = _run("completion", "fish")
    assert r.returncode == 0
    assert "complete -c ephe" in r.stdout


def test_completion_bad_shell_usage_error():
    r = _run("completion", "tcsh")
    assert r.returncode == 2
    assert "invalid choice" in r.stderr


def test_version_flag():
    r = _run("--version")
    assert r.returncode == 0
    assert "ephe" in r.stdout


def test_unknown_subcommand_usage_error():
    r = _run("nonsense")
    assert r.returncode == 2


def test_update_accepts_json_flag():
    r = _run("update", "--json")
    # The flag is accepted (no usage error about an unknown flag).
    assert r.returncode in (0, 1)


def test_main_hardening_returns_exit_1_with_json_error(monkeypatch, capsys):
    """An unexpected exception in a cmd function → exit 1; --json returns a stable error JSON."""
    import ephe_cli

    def boom(_args):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(ephe_cli, "cmd_doctor", boom)
    monkeypatch.setattr(sys, "argv", ["ephe", "doctor", "--json"])
    with pytest.raises(SystemExit) as exc:
        ephe_cli.main()
    assert exc.value.code == 1
    # The JSON error feedback goes to stdout; no secrets, a clear cause + fix.
    data = json.loads(capsys.readouterr().out)
    assert data["error"]["code"] == 1
    assert "kaputt" in data["error"]["message"]


def test_cli_keeps_heavy_imports_lazy():
    """
    Startup budget gate (phase 1 item 4): the CLI must be quick to
    import (< 100 ms). Heavy modules (fastapi, uvicorn, ollama, rich,
    textual, server) may NOT be loaded by the top-level import —
    they stay lazy (only inside cmd_serve/cmd_start).
    """
    code = (
        "import sys; import ephe_cli; "
        "print(' '.join(m for m in "
        "['fastapi','uvicorn','ollama','rich','textual','server'] "
        "if m in sys.modules))"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=hermetic_env(PYTHONPATH=""),
    )
    assert r.returncode == 0
    # No heavy module may have been imported at load time.
    assert r.stdout.strip() == ""


# Usage errors answer on the channel the caller asked for.
#
# Measured 2026-10-15: `ephe doctor --bogus --json` exited 2 with argparse's text on
# stderr and no JSON at all, so a script that branches on the envelope could not tell a
# mistyped flag from a crash. The text it printed was the ROOT usage line — the one that
# lists all 28 subcommands — so `ephe doctor --bogus` read as a mistyped command.


def test_a_usage_error_is_json_when_json_was_asked_for():
    """
    GIVEN `ephe doctor --bogus --json`
    WHEN it runs
    THEN exit 2 and the same {"error": …} envelope the other failures print on stdout.
    """
    r = _run("doctor", "--bogus", "--json")

    assert r.returncode == 2
    assert r.stderr == ""
    data = json.loads(r.stdout)
    assert data["error"]["code"] == 2
    assert data["error"]["code_id"] == "usage_error"
    assert "--bogus" in data["error"]["message"]


def test_a_usage_error_quotes_the_command_the_user_typed():
    """
    GIVEN `ephe doctor --bogus`
    WHEN it runs
    THEN the usage line names doctor and its flags, not the root command list.
    """
    r = _run("doctor", "--bogus")

    assert r.returncode == 2
    assert "usage: ephe doctor" in r.stderr
    assert "usage: ephe [-h]" not in r.stderr


def test_an_unknown_subcommand_still_quotes_the_root_usage():
    """
    GIVEN `ephe nonsense`
    WHEN it runs
    THEN the root usage is right, because the typo is a command name — and --json
         reports it in the envelope like any other usage error.
    """
    r = _run("nonsense")
    assert r.returncode == 2
    assert "usage: ephe [-h]" in r.stderr

    r = _run("nonsense", "--json")
    assert r.returncode == 2
    assert "invalid choice" in json.loads(r.stdout)["error"]["message"]


def test_help_and_version_are_answers_not_usage_errors():
    """
    GIVEN a call that carries --json next to --help, or --version alone
    WHEN it runs
    THEN the answer is printed on stdout with exit 0 — no envelope, no error path.
    """
    r = _run("doctor", "--bogus", "--help")
    assert r.returncode == 0
    assert "usage: ephe doctor" in r.stdout
    assert r.stderr == ""

    r = _run("--version", "--json")
    assert r.returncode == 0
    assert "ephe" in r.stdout



# The version number has one home (pyproject.toml); these three surfaces must read it
# from there or say nothing at all.
_STANDALONE_VERSION_PROBE = (
    "import importlib.abc, importlib.util, sys\n"
    "from pathlib import Path\n"
    "\n"
    "class NoCore(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'core' or name.startswith('core.'):\n"
    "            raise ModuleNotFoundError('this probe runs without core/')\n"
    "        return None\n"
    "\n"
    "sys.meta_path.insert(0, NoCore())\n"
    "spec = importlib.util.spec_from_file_location(\n"
    "    'cli_common_standalone', Path('core') / '_cli_common.py'\n"
    ")\n"
    "module = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(module)\n"
    "print(module.EPHE_VERSION)\n"
)


def _run_code(code: str) -> subprocess.CompletedProcess[str]:
    """Runs an inline program from the repo root in the same scrubbed environment."""
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=hermetic_env(PYTHONPATH=""),
    )


def test_version_flag_prints_the_version_the_tree_declares():
    """The flag and the module constant both answer with pyproject's number."""
    import core._cli_common as common
    import core._version as version

    assert _run("--version").stdout.strip() == f"ephe {version.__version__}"
    assert common.EPHE_VERSION == version.__version__


def test_the_standalone_fallback_names_no_version_at_all():
    """A run without core/ answers with the sentinel core/_version.py itself uses."""
    r = _run_code(_STANDALONE_VERSION_PROBE)

    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "0.0.0+unknown"
    assert '"0.0.0+unknown"' in (ROOT / "core" / "_version.py").read_text(encoding="utf-8")


def _documented_version_line() -> str:
    for line in DOCS_CLI.read_text(encoding="utf-8").splitlines():
        if "ephe --version" in line:
            return line
    raise AssertionError("docs/CLI.md shows no `ephe --version` line")


def test_the_documented_version_example_pins_no_literal():
    """A number written into the doc is a second home that the next bump leaves stale."""
    line = _documented_version_line()

    assert "pyproject" in line, line
    assert re.search(r"\d+\.\d+", line) is None, line


# Exit codes: what the tree returns, what every help surface claims.
def _exit_code_rows(text: str) -> list[str]:
    """The codes an `Exit codes:` block lists, in the order the block lists them."""
    return re.findall(r"^\s+(\d)\s", text.split("Exit codes:", 1)[1], re.M)


def _documented_exit_code_line() -> str:
    for line in DOCS_CLI.read_text(encoding="utf-8").splitlines():
        if "Exit codes:" in line:
            return line
    raise AssertionError("docs/CLI.md carries no exit-code line")


def test_the_root_help_lists_the_codes_the_cli_returns():
    assert _exit_code_rows(_run("--help").stdout) == ["0", "1", "2"]


def test_no_help_surface_claims_a_blocked_code_of_three():
    """No path returns 3, and cmd_tool answers 1 for a policy denial."""
    doc = _documented_exit_code_line()
    tool_help = _run("tool", "--help").stdout

    assert re.findall(r"`(\d)`", doc) == ["0", "1", "2"], doc
    assert re.search(r"\b3\s*=", tool_help) is None, tool_help
    assert re.search(r"1 = blocked", tool_help), tool_help


def test_a_denied_tool_exits_with_the_code_the_help_documents():
    r = _run(
        "tool", "write_file",
        "--arg", "path=/tmp/ephe-cli-dx-denied.txt", "--arg", "content=x",
    )

    assert r.returncode == 1, r.stdout + r.stderr
    assert "[Denied]" in r.stdout


# The failure at the top of main(): an engine that did not answer is worth the endpoint.
class _EndpointChoice:
    """The part of an EngineChoice the endpoint line reads."""

    api_url = "http://127.0.0.1:9/v1"


def test_a_transport_failure_names_the_endpoint_and_the_way_to_it(monkeypatch, capsys):
    import ephe_cli

    def unreachable(_args):
        raise ConnectionRefusedError(61, "Connection refused")

    monkeypatch.setattr(ephe_cli, "_active_engine_choice", lambda: _EndpointChoice())
    monkeypatch.setattr(ephe_cli, "cmd_doctor", unreachable)
    monkeypatch.setattr(sys, "argv", ["ephe", "doctor"])

    with pytest.raises(SystemExit) as exc:
        ephe_cli.main()

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "127.0.0.1:9/v1" in err, err
    assert "ephe doctor" in err and "ephe configure" in err, err
    assert "Check the last output and try again" not in err


def test_a_missing_engine_keeps_the_instruction_the_resolver_carried(monkeypatch, capsys):
    import ephe_cli
    from core.engine_config import ENGINE_SETUP_HINT, EngineNotConfigured

    def no_engine(_args):
        raise EngineNotConfigured()

    monkeypatch.setattr(ephe_cli, "cmd_code", no_engine)
    monkeypatch.setattr(sys, "argv", ["ephe", "code", "hello"])

    with pytest.raises(SystemExit) as exc:
        ephe_cli.main()

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert ENGINE_SETUP_HINT in err, err
    assert "Check the last output and try again" not in err


# docs/CLI.md claims the parser can keep: the flags it calls global and the tool example.
def _docs_paragraph_with(needle: str) -> str:
    for chunk in DOCS_CLI.read_text(encoding="utf-8").split("\n\n"):
        if needle in chunk:
            return " ".join(chunk.split())
    raise AssertionError(f"docs/CLI.md carries no paragraph mentioning {needle!r}")


def _subparser(verb: str) -> argparse.ArgumentParser:
    import ephe_cli

    for action in ephe_cli.build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[verb]
    raise AssertionError(f"build_parser() registers no `{verb}` subparser")


def test_the_documented_global_flags_are_the_root_parser_flags():
    import ephe_cli

    root = {option for action in ephe_cli.build_parser()._actions for option in action.option_strings}
    sentence = _docs_paragraph_with("Global flags:").split("Global flags:", 1)[1].split(".", 1)[0]
    declared = set(re.findall(r"`(--[a-z-]+)", sentence))

    assert declared, "docs/CLI.md no longer names a global flag"
    assert declared <= root, f"docs/CLI.md calls {sorted(declared - root)} global; the root parser takes {sorted(root)}"


def test_the_documented_flag_owners_really_carry_those_flags():
    for flag in ("--model", "--port"):
        paragraph = _docs_paragraph_with("Global flags:")
        tail = paragraph.split(f"`{flag}", 1)[1].split("`--", 1)[0]
        owners = re.findall(r"`([a-z][a-z-]*)`", tail)
        assert owners, f"docs/CLI.md names no verb for {flag}"
        for verb in owners:
            options = {option for action in _subparser(verb)._actions for option in action.option_strings}
            assert flag in options, f"docs/CLI.md gives `{flag}` to `{verb}`, which does not take it"


def test_the_documented_tool_example_names_the_plugin_that_can_hide_it():
    """A plugin switch can take a tool out of the list; the example says which one."""
    from core.plugin_registry import PluginRegistry

    root = Path(__file__).resolve().parents[1]
    owners = dict(PluginRegistry.load(root / "plugins", root / "skills").tool_activations())
    section = _docs_paragraph_with("ephe tool <name>")
    examples = re.findall(r"ephe tool ([a-z_][a-z0-9_]*)", section)

    assert examples, "docs/CLI.md shows no `ephe tool <name>` example"
    for name in examples:
        plugin = owners.get(name)
        if plugin is not None:
            assert plugin in section, (
                f"docs/CLI.md runs `ephe tool {name}` without naming the `{plugin}` plugin "
                "whose switch hides it"
            )
