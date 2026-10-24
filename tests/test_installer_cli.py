from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from tests.toml_compat import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _no_frontend_build_side_effects():
    """No test in this file may build the frontend into the checkout.

    `ephe start` and `ephe doctor --fix` both reach `ensure_pwa_built()`
    (ephe_cli.py:618 and :85), which runs `npm ci` / `npm install` / `npm run build` in
    `app/` whenever `app/dist/index.html` is missing — the state of a fresh CI checkout,
    since app/dist is git-ignored. The tests here patch `ephe_cli._run`, and that does
    not cover it: `ensure_pwa_built` calls `core._cli_ollama._run`, its own module
    binding. Proved against a simulated fresh checkout (PROJECT_ROOT moved to a tmp
    repo, `core._cli_ollama._run` recorded) — with only the patch set this file used
    before, `npm ci --prefix <repo>/app` and `npm run build --prefix <repo>/app` came
    out of `doctor --fix` as well as out of `start`.

    Measured, not assumed: this file was green on a machine that had already built the
    PWA and red where it had not, and `npm install` leaves `app/package-lock.json`
    behind, which is the assertion of
    `tests/test_r46_pnpm_single_source.py::test_single_lockfile_pnpm_only` — a later
    test in the same run, failing for what this file did to the working tree.

    The artifacts are compared before and after the test, so the build a developer
    already has is not reported and one this file caused is.
    """
    watched = ("app/dist", "app/node_modules", "app/package-lock.json")
    before = {name: (ROOT / name).exists() for name in watched}
    yield
    created = [name for name, existed in before.items() if not existed and (ROOT / name).exists()]
    assert not created, (
        f"This test built the frontend into the checkout (created {', '.join(created)}). "
        "Patch the seam it runs on: `patch('ephe_cli.ensure_pwa_built')` for the CLI "
        "command, or `core._cli_ollama._run` / `PROJECT_ROOT` when the build step itself "
        "is under test."
    )


@pytest.fixture(autouse=True)
def _local_engine_seam(monkeypatch):
    """Pin the engine seam: every test in this file sets up a local Ollama world.

    `cmd_doctor` and `cmd_start` resolve the active engine from `~/.ephe/engine.json`
    when one exists and probe that endpoint instead. On a machine with a remote engine
    configured, these tests would read the remote path's lines and miss the local ones
    they set up; the suite is green on a fresh CI checkout and was red on the machine
    where the engine had already been chosen.
    """
    import ephe_cli

    monkeypatch.setattr(ephe_cli, "_active_engine_choice", lambda: None)


def test_given_install_script_when_checked_then_one_command_bootstrap_installs_app_not_model():
    """
    GIVEN Josef runs the public installer
    WHEN the script is inspected
    THEN it bootstraps into Documents and starts the local app — without
         installing Ollama or pulling any model (Mandat 2026-08-21).
    """
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "EPHE_INSTALL_DIR:-$HOME/Documents/Ephe" in script
    assert 'git clone "$REPO_URL" "$INSTALL_DIR"' in script
    assert "ephe start" in script
    assert "brew install python" in script
    assert "astral.sh/uv/install.sh" in script
    assert "python3-venv" in script

    # Mandate: no Ollama installation, no model pull (both platforms)
    for s in (script, ps1):
        assert "ollama pull" not in s
        assert "gemma4" not in s
        assert "nomic-embed-text" not in s
        assert "hardware-adaptiv" not in s
    assert "install_ollama" not in script


def test_given_install_scripts_when_checked_then_no_ollama_install_or_model_pull():
    """
    GIVEN the public installer (mandate 2026-08-21: Ollama is NOT installed,
    NO models are pulled — the engine is chosen in the app)
    WHEN install.sh and install.ps1 are inspected
    THEN neither script installs Ollama nor pulls a model.
    """
    sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")

    # No Ollama installation (download/hash/winget cask)
    assert "install_ollama" not in sh
    assert "OLLAMA_INSTALL_SHA256" not in sh
    assert "Ollama.Ollama" not in ps1
    # No model pull in either script
    assert "ollama pull" not in sh
    assert "ollama pull" not in ps1
    assert "gemma4" not in ps1
    assert "nomic-embed-text" not in ps1


def test_given_ollama_missing_when_installer_runs_then_it_warns_and_continues():
    """
    GIVEN Ollama is not installed on the machine
    WHEN the installer reaches the AI-engine step
    THEN it warns ONLY (never blocking) and continues — no abort, no installation.
    """
    sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")

    # install.sh: info/warning path when Ollama is missing
    assert "No Ollama detected" in sh
    assert "does not install an AI of its own" in sh
    # install.ps1: the identical warning path
    assert "No Ollama detected" in ps1
    assert "does not install an AI of its own" in ps1
    # Both mark the step as info (not blocking)
    assert "Checking the AI engine (info)" in sh
    assert "Check AI engine (info)" in ps1


def test_given_low_disk_space_when_installer_runs_then_it_warns_not_fails():
    """
    GIVEN less than ~4 GB of free disk space
    WHEN the installer runs the disk check
    THEN it warns (does not fail) — the model is not pulled here anyway.
    """
    sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")

    # install.sh: ~4 GB (4096000 KB) threshold, a warning instead of an abort
    assert "4096000" in sh
    assert "Less than ~4 GB free disk" in sh
    # install.ps1: the identical warning (4 GB threshold)
    assert "Less than ~4 GB free disk" in ps1
    assert "Win32_LogicalDisk" in ps1


def test_given_install_scripts_when_parsed_then_shell_syntax_is_valid():
    """
    GIVEN install scripts are a critical first-run surface
    WHEN syntax is checked
    THEN macOS/Linux shell syntax is valid and Windows script exists.
    """
    subprocess.run(["bash", "-n", str(ROOT / "install.sh")], check=True)
    powershell_script = (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert "Python.Python.3.12" in powershell_script

    if shutil.which("pwsh"):
        subprocess.run(
            ["pwsh", "-NoProfile", "-Command", f"$null = [scriptblock]::Create((Get-Content -Raw '{ROOT / 'install.ps1'}'))"],
            check=True,
        )


@pytest.mark.parametrize("version, exit_code", [((3, 10, 99), 1), ((3, 11, 0), 0), ((3, 13, 17), 0)])
def test_windows_python_probe_rejects_unsupported_interpreters(monkeypatch, version, exit_code):
    script = (ROOT / "install.ps1").read_text(encoding="utf-8")
    probe = re.search(r'& \$Candidate\.Source -c "([^"]+)"', script)
    assert probe is not None
    with monkeypatch.context() as context:
        context.setattr(sys, "version_info", version)
        with pytest.raises(SystemExit) as result:
            exec(probe.group(1), {})
    assert result.value.code == exit_code


def test_given_pyproject_when_loaded_then_ephe_cli_commands_are_exposed():
    """
    GIVEN the package metadata
    WHEN console scripts are checked
    THEN the new ephe CLI is installable without replacing the legacy TUI command.
    """
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]

    assert scripts["ephe"] == "ephe_cli:main"
    assert scripts["ephe-app"] == "ephe:main"
    assert "ephe_cli.py" in pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["include"]


def test_given_ephe_cli_when_help_requested_then_core_commands_exist():
    """
    GIVEN a user installs Ephe
    WHEN the CLI help is shown
    THEN start, doctor and update are first-class commands.
    """
    result = subprocess.run(
        [sys.executable, str(ROOT / "ephe_cli.py"), "--help"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "start" in result.stdout
    assert "doctor" in result.stdout
    assert "update" in result.stdout


def test_given_ephe_doctor_help_when_checked_then_fix_mode_is_documented():
    """
    GIVEN doctor should be able to repair common local drift
    WHEN doctor help is shown
    THEN --fix is available as an explicit opt-in action.
    """
    result = subprocess.run(
        [sys.executable, str(ROOT / "ephe_cli.py"), "doctor", "--help"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "--fix" in result.stdout


def test_given_ephe_doctor_when_model_is_listed_but_not_loadable_then_reports_repair_action(capsys):
    """
    GIVEN Ollama lists Gemma but a test generation fails
    WHEN ephe doctor runs
    THEN it reports the model as not loadable and tells the user how to repair it.
    """
    import ephe_cli

    args = ephe_cli.build_parser().parse_args(["doctor", "--model", "gemma4:12b"])
    with patch("ephe_cli._ollama_binary", return_value="/usr/local/bin/ollama"), \
         patch("ephe_cli._model_installed", return_value=True), \
         patch("ephe_cli._json_get") as json_get, \
         patch("ephe_cli._model_loadable", return_value=(False, "unable to load model: missing blob")):
        json_get.side_effect = [
            {"models": [{"name": "gemma4:12b"}]},
            {"status": "ok"},
        ]
        code = args.func(args)

    out = capsys.readouterr().out
    assert code == 1
    assert "Model gemma4:12b load test" in out
    assert "repair: ollama pull gemma4:12b" in out


def test_given_ephe_doctor_when_model_load_test_passes_then_setup_is_ok(capsys):
    """
    GIVEN Ollama is running and Gemma can generate a token
    WHEN ephe doctor runs
    THEN the local offline setup is considered healthy.
    """
    import ephe_cli

    args = ephe_cli.build_parser().parse_args(["doctor", "--model", "gemma4:12b"])
    with patch("ephe_cli._ollama_binary", return_value="/usr/local/bin/ollama"), \
         patch("ephe_cli._model_installed", return_value=True), \
         patch("ephe_cli._json_get") as json_get, \
         patch("ephe_cli._model_loadable", return_value=(True, "test generation ok")), \
         patch("ephe_cli._active_engine_choice", return_value=None):
        json_get.side_effect = [
            {"models": [{"name": "gemma4:12b"}]},
            {"status": "ok"},
        ]
        code = args.func(args)

    out = capsys.readouterr().out
    assert code == 0
    assert "Model gemma4:12b load test" in out
    assert "test generation ok" in out


@pytest.mark.parametrize(
    ("reachable", "detail", "expected_code"),
    [(True, "2 models served", 0), (False, "connection refused", 1)],
)
def test_cmd_doctor_probes_the_engine_the_user_chose(
    monkeypatch, capsys, reachable, detail, expected_code
):
    """The chosen engine is asked at its own endpoint, never through the local rows.

    Asking the local Ollama CLI, service and tag about an OpenAI-compatible endpoint
    reports a working hosted setup as broken — the defect this branch answers. The
    autouse `_local_engine_seam` above pins the choice to None for the rest of this
    file, so a test of the remote path has to re-pin it. A chosen engine that does not
    answer stays a genuine failure, so the second case is exit 1.
    """
    import ephe_cli
    from core.engine_config import EngineChoice

    monkeypatch.setattr(
        ephe_cli,
        "_active_engine_choice",
        lambda: EngineChoice(
            provider="openai_compatible",
            model="served-model",
            api_url="http://10.0.0.5:8000/v1",
        ),
    )
    monkeypatch.setattr(
        ephe_cli, "_probe_active_remote_engine", lambda _url, _model: (reachable, detail)
    )
    monkeypatch.setattr(ephe_cli, "_doctor_image_endpoint", lambda: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "_doctor_voice", lambda: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "_json_get", lambda _u, **_k: {"models": [{"name": "m"}]})
    monkeypatch.setattr(ephe_cli, "_cell_pinned_ceiling", lambda: None)

    args = ephe_cli.build_parser().parse_args(["doctor"])
    code = args.func(args)
    out = capsys.readouterr().out

    assert "Engine openai_compatible" in out
    assert f"served-model @ http://10.0.0.5:8000/v1 — {detail}" in out
    assert out.count("not chosen yet (informational)") == 2
    assert code == expected_code


def test_given_ephe_doctor_fix_when_invoked_then_repairs_repo_deps_and_model(capsys):
    """
    GIVEN the user runs ephe doctor --fix after repo/runtime drift
    WHEN repairs are mocked as successful
    THEN doctor runs repo, dependency and model repair before reporting checks.
    """
    import ephe_cli

    args = ephe_cli.build_parser().parse_args(["doctor", "--fix", "--model", "gemma4:12b"])
    # The PWA repair is pinned like the other three: ensure_pwa_built() runs npm
    # through core._cli_ollama._run — NOT the ephe_cli._run these tests patch — and
    # in a fresh CI checkout (app/dist is git-ignored) it does `npm ci` /
    # `npm install` / `npm run build` in the real app/. Besides being slow and
    # network-bound, `npm install` creates app/package-lock.json, which is what made
    # tests/test_r46_pnpm_single_source.py::test_single_lockfile_pnpm_only fail in the
    # same run: one test's npm call asserted against another test's working tree.
    with patch("ephe_cli._repair_repo", return_value=(True, "repo up to date")) as repo, \
         patch("ephe_cli._repair_dependencies", return_value=(True, "dependencies installed")) as deps, \
         patch("ephe_cli._ensure_model_ready_for_start", return_value=(True, "test generation ok")) as model, \
         patch("ephe_cli.ensure_pwa_built", return_value=True), \
         patch("ephe_cli._ollama_binary", return_value="/usr/local/bin/ollama"), \
         patch("ephe_cli._model_installed", return_value=True), \
         patch("ephe_cli._json_get") as json_get, \
         patch("ephe_cli._model_loadable", return_value=(True, "test generation ok")), \
         patch("ephe_cli._active_engine_choice", return_value=None):
        json_get.side_effect = [
            {"models": [{"name": "gemma4:12b"}]},
            {"status": "ok"},
        ]
        code = args.func(args)

    out = capsys.readouterr().out
    assert code == 0
    repo.assert_called_once()
    deps.assert_called_once()
    model.assert_called_once_with("gemma4:12b")
    assert "Repair repo" in out
    assert "Repair dependencies" in out
    assert "Repair model gemma4:12b" in out


def test_given_dirty_repo_when_repair_repo_runs_then_it_does_not_pull():
    """
    GIVEN local user edits exist
    WHEN doctor --fix considers updating the repo
    THEN it refuses to git pull instead of overwriting local work.
    """
    import ephe_cli

    with patch("core._cli_ollama._run") as run:
        run.side_effect = [
            subprocess.CompletedProcess(["git", "status"], 0, stdout=" M README.md\n"),
        ]
        ok, detail = ephe_cli._repair_repo()

    assert ok is False
    assert "local changes" in detail
    assert len(run.call_args_list) == 1


def test_given_ephe_start_when_model_is_missing_then_it_reports_and_still_starts(capsys):
    """
    GIVEN the engine model is not installed and Ollama is running
    WHEN ephe start runs (engine already chosen) without --skip-model-check
    THEN it does NOT PULL, but reports the status (non-blocking) and starts anyway —
         an unreachable model must never block the start, or the UI where the user
         could pick a different engine would be unreachable.
    """
    import ephe_cli
    from core.engine_config import LOCAL_OLLAMA, EngineChoice

    args = ephe_cli.build_parser().parse_args(["start", "--model", "gemma4:12b"])
    args.open = False
    args.reload = False
    args.host = "127.0.0.1"
    args.lan = False
    args.port = 8765

    # W4 S1: --model no longer selects the engine, so a chosen engine must be
    # supplied here for the local-model readiness check to run at all.
    with patch("ephe_cli.resolve_engine_choice",
               return_value=EngineChoice(provider=LOCAL_OLLAMA, model="gemma4:12b")), \
         patch("ephe_cli._ensure_ollama_service", return_value=(True, "Ollama service is running")), \
         patch("ephe_cli._model_installed", return_value=False), \
         patch("ephe_cli._pull_model", return_value=(True, "pulled gemma4:12b")) as pull_model, \
         patch("ephe_cli.ensure_pwa_built", return_value=True), \
         patch("ephe_cli._run") as run:
        run.return_value.returncode = 0
        code = args.func(args)

    assert code == 0
    pull_model.assert_not_called()
    assert "Model gemma4:12b ready" in capsys.readouterr().out


def test_given_ephe_cli_when_shell_has_bad_ollama_host_then_ollama_commands_use_loopback(monkeypatch):
    """
    GIVEN OLLAMA_HOST points to a stale non-local address
    WHEN ephe checks or pulls models
    THEN subprocesses get OLLAMA_HOST=127.0.0.1:11434 explicitly.
    """
    import ephe_cli

    monkeypatch.setenv("OLLAMA_HOST", "192.168.1.50:11434")
    # The probe is patched where it LIVES. `ephe_cli._ollama_binary` is the re-export
    # from the God-file split (fdc0d650) and cb59e5be renamed the patch strings
    # mechanically, so this seam has been dead since 2026-09-22: _model_installed reads
    # core._cli_ollama's own binding. On a machine without Ollama the real probe answered
    # None, the recorded call list stayed empty and the test failed with
    # `assert False is True` on every CI leg — while passing on any dev box that has
    # Ollama installed, which is how it survived four years.
    with patch("core._cli_ollama._ollama_binary", return_value="/usr/local/bin/ollama"), \
         patch("ephe_cli.subprocess.run") as run:
        run.return_value.returncode = 0
        assert ephe_cli._model_installed("gemma4:12b") is True
        ok, _ = ephe_cli._pull_model("gemma4:12b")

    assert ok is True
    assert run.call_args_list, "the patched probe never reached the subprocess"
    for call_args in run.call_args_list:
        assert call_args.kwargs["env"]["OLLAMA_HOST"] == "127.0.0.1:11434"


def test_given_old_ollama_when_pull_model_runs_then_cli_upgrades_and_retries(monkeypatch):
    """
    GIVEN Ollama says the model requires a newer Ollama version
    WHEN the CLI pulls a model
    THEN it upgrades Ollama and retries the pull once.
    """
    import ephe_cli

    monkeypatch.setenv("OLLAMA_HOST", "192.168.1.50:11434")
    old = subprocess.CompletedProcess(
        ["ollama", "pull", "gemma4:12b"],
        1,
        stdout="",
        stderr="The model you are attempting to pull requires a newer version of Ollama.",
    )
    ok = subprocess.CompletedProcess(["ollama", "pull", "gemma4:12b"], 0, stdout="pulled", stderr="")
    with patch("core._cli_ollama._ollama_binary", return_value="/usr/local/bin/ollama"), \
         patch("core._cli_ollama._upgrade_ollama", return_value=(True, "Ollama updated")) as upgrade, \
         patch("core._cli_ollama.subprocess.run", side_effect=[old, ok]) as run:
        success, detail = ephe_cli._pull_model("gemma4:12b")

    assert success is True
    assert "after Ollama update" in detail
    upgrade.assert_called_once()
    assert run.call_count == 2


def test_given_macos_gemma4_12b_when_cli_pulls_then_it_knows_12b_fallback_candidates(monkeypatch):
    """
    GIVEN a Mac user requests the default Gemma 4 12B model
    WHEN the CLI builds local pull candidates
    THEN it keeps the requested model first and includes MLX-compatible 12B variants.
    """
    import ephe_cli

    monkeypatch.setattr(sys, "platform", "darwin")

    assert ephe_cli._ollama_model_candidates("gemma4:12b") == [
        "gemma4:12b",
        "gemma4:12b-mlx",
        "gemma4:12b-nvfp4",
    ]


def test_given_all_gemma4_12b_candidates_need_newer_ollama_when_cli_pulls_then_error_is_actionable(monkeypatch):
    """
    GIVEN every 12B candidate is rejected by the manifest-version gate
    WHEN the CLI pull finishes
    THEN it reports the Ollama upgrade requirement clearly instead of a generic pull failure.
    """
    import ephe_cli

    monkeypatch.setattr(sys, "platform", "darwin")
    old = subprocess.CompletedProcess(
        ["ollama", "pull", "gemma4:12b"],
        1,
        stdout="",
        stderr="The model you are attempting to pull requires a newer version of Ollama.",
    )
    version = subprocess.CompletedProcess(["ollama", "--version"], 0, stdout="client version is 0.30.5", stderr="")
    with patch("core._cli_ollama._ollama_binary", return_value="/usr/local/bin/ollama"), \
         patch("core._cli_ollama._upgrade_ollama", return_value=(False, "update failed")), \
         patch("core._cli_ollama.subprocess.run", side_effect=[old, old, old, version]):
        success, detail = ephe_cli._pull_model("gemma4:12b")

    assert success is False
    assert "latest Ollama" in detail
    assert "0.30.5" in detail


def test_given_ephe_start_when_model_is_broken_then_it_reports_and_still_starts(capsys):
    """
    GIVEN Ollama lists a model blob that cannot be loaded
    WHEN ephe start runs (engine already chosen) without --skip-model-check
    THEN it does NOT RE-PULL, but reports the status (non-blocking) and starts anyway —
         root cause: a broken engine must not block the start, because otherwise the
         UI where the user can choose a different engine would be unreachable.
    """
    import ephe_cli
    from core.engine_config import LOCAL_OLLAMA, EngineChoice

    args = ephe_cli.build_parser().parse_args(["start", "--model", "gemma4:12b"])
    args.open = False
    args.reload = False
    args.host = "127.0.0.1"
    args.lan = False
    args.port = 8765

    # W4 S1: --model no longer selects the engine, so a chosen engine must be
    # supplied here for the local-model readiness check to run at all.
    with patch("ephe_cli.resolve_engine_choice",
               return_value=EngineChoice(provider=LOCAL_OLLAMA, model="gemma4:12b")), \
         patch("ephe_cli._ensure_ollama_service", return_value=(True, "Ollama service is running")), \
         patch("ephe_cli._model_installed", return_value=True), \
         patch("ephe_cli._model_loadable", return_value=(False, "unable to load model: missing blob")), \
         patch("ephe_cli._pull_model", return_value=(True, "pulled gemma4:12b")) as pull_model, \
         patch("ephe_cli.ensure_pwa_built", return_value=True), \
         patch("ephe_cli._run") as run:
        run.return_value.returncode = 0
        code = args.func(args)

    assert code == 0
    pull_model.assert_not_called()
    assert "Model gemma4:12b ready" in capsys.readouterr().out


def test_given_ephe_start_lan_when_invoked_then_server_binds_to_all_interfaces():
    """
    GIVEN the user wants phone QR pairing
    WHEN ephe start --lan is invoked
    THEN the server starts on 0.0.0.0 while preserving local-model preflight.
    """
    import ephe_cli

    args = ephe_cli.build_parser().parse_args(["start", "--lan", "--skip-model-check"])

    # ensure_pwa_built() is on this path too (ephe_cli.py:618) and reaches npm
    # through core._cli_ollama._run, which the ephe_cli._run patch below does not
    # cover — same reason as the doctor --fix case above.
    with patch("ephe_cli.ensure_pwa_built", return_value=True), \
         patch("ephe_cli._run") as run:
        run.return_value.returncode = 0
        code = args.func(args)
        cmd = run.call_args.args[0]
        env = run.call_args.kwargs["env"]

    assert code == 0
    assert cmd[cmd.index("--host") + 1] == "0.0.0.0"
    assert env["EPHE_HOST"] == "0.0.0.0"


def test_given_readme_quickstart_when_checked_then_first_path_is_one_command():
    """
    GIVEN a new user opens the README
    WHEN the Quick Start section is read
    THEN the first install path is exactly one terminal command.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quickstart = readme.split("## Quick start", 1)[1].split("## What you need", 1)[0]
    bash_blocks = re.findall(r"```bash\n(.*?)\n```", quickstart, flags=re.DOTALL)

    assert bash_blocks
    first_command = bash_blocks[0].strip()
    assert re.fullmatch(
        r"curl -fsSL https://raw\.githubusercontent\.com/bemlerlabs/ephe/"
        r"v\d+\.\d+\.\d+/install\.sh \| bash",
        first_command,
    )
    assert "\n" not in first_command
    assert "docker compose" not in quickstart.lower()


def test_given_readme_hero_when_checked_then_first_terminal_command_is_installer():
    """
    GIVEN a new user lands on GitHub
    WHEN they scan the hero and first success path
    THEN the first terminal command is the one-command offline-first installer, Docker later.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    bash_blocks = re.findall(r"```bash\n(.*?)\n```", readme, flags=re.DOTALL)

    assert bash_blocks
    assert re.fullmatch(
        r"curl -fsSL https://raw\.githubusercontent\.com/bemlerlabs/ephe/"
        r"v\d+\.\d+\.\d+/install\.sh \| bash",
        bash_blocks[0].strip(),
    )
    assert "local-first workspace for an AI agent" in readme[:1500]
    assert "Online paths are opt-in" in readme[:1500]


def test_given_install_sh_when_cli_mode_then_minimal_tui_path_is_offered():
    """
    GIVEN a user wants only the terminal UI
    WHEN install.sh runs in CLI mode
    THEN it installs only the minimal tui extra and starts `ephe tui` instead of the browser.
    """
    script = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "--cli|--headless|--tui) INSTALL_MODE=\"cli\"" in script
    assert "--desktop|--gui|--web|--pwa) INSTALL_MODE=\"desktop\"" in script
    assert 'INSTALL_MODE="$EPHE_MODE"' in script
    assert 'pip install -e ".[tui]"' in script
    assert 'pip install -e ".[gui,voice]"' in script
    # Start WITHOUT --model: the engine is chosen in the app (mandate 2026-08-21)
    assert 'exec .venv/bin/ephe tui' in script
    assert 'exec .venv/bin/ephe start --port "$PORT" --open' in script
    assert '--model' not in script


def test_given_install_sh_when_no_flag_then_interactive_mode_prompt_is_available():
    """
    GIVEN install.sh runs without a mode flag on a TTY
    WHEN the interactive prompt is reached
    THEN it offers Desktop/PWA, CLI and Skip-start choices with desktop as default.
    """
    script = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert 'How do you want to use Ephe? [D]esktop/PWA, [C]li (TUI), or [S]kip start' in script
    assert 'INSTALL_MODE="cli"' in script
    assert 'NO_START=1' in script


def test_given_install_ps1_when_checked_then_windows_has_cli_mode_and_engine_info():
    """
    GIVEN a Windows user runs install.ps1
    WHEN the script is inspected
    THEN it supports a minimal CLI path and an info-only AI-engine check —
         no RAM-adaptive model default, no Ollama install, no model pull (Mandat 2026-08-21).
    """
    script = (ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "[switch]$Cli" in script
    assert 'install -e ".[tui]"' in script
    assert 'install -e ".[gui,voice]"' in script
    # Info-only engine check (never blocking)
    assert "Check AI engine (info)" in script
    assert "No Ollama detected" in script
    # Start WITHOUT --model (the engine is chosen in the app)
    assert 'ephe.exe" tui' in script
    assert 'ephe.exe" start --port $Port --open' in script
    assert "--model" not in script
    # No RAM-based model choice / Ollama installation / model pull
    assert "Win32_ComputerSystem" not in script
    assert "gemma4" not in script
    assert "Ollama.Ollama" not in script


def test_given_readme_when_checked_then_windows_one_liner_and_cli_flags_are_documented():
    """
    GIVEN a Windows or CLI-first user reads the README
    WHEN the install docs are checked
    THEN the PowerShell one-liner and the --cli/--desktop mode flags are documented.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert re.search(
        r"irm https://raw\.githubusercontent\.com/bemlerlabs/ephe/"
        r"v\d+\.\d+\.\d+/install\.ps1",
        readme,
    )
    assert "powershell -ExecutionPolicy Bypass -File .\\install.ps1" in readme
    assert "ephe tui" in readme
    assert "--cli" in readme
    assert "--desktop" in readme


def test_given_install_scripts_when_desktop_mode_then_pwa_build_is_created():
    """
    GIVEN a new user installs Ephe in desktop/PWA mode
    WHEN the installer runs
    THEN it builds the PWA so the server's frontend mount (app/dist) actually exists
         after install — on pnpm where it is available, on npm where it is not, and in
         the npm case with `install --no-package-lock` (see the two tests below: `npm
         ci` cannot run in a fresh clone, and bare `npm install` writes the second
         lockfile this repository forbids).
    """
    sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")

    # install.sh: PWA build step in desktop mode
    assert "build_pwa()" in sh
    assert 'npm --prefix "$PROJECT_DIR/app" install --no-package-lock' in sh
    assert 'npm --prefix "$PROJECT_DIR/app" run build' in sh
    # The build result is verified (dist/index.html has to exist)
    assert 'app/dist/index.html' in sh

    # install.ps1: the npm shape — this script has no pnpm branch at all, it builds
    # with npm wherever it runs, so the fallback rules apply to it outright.
    assert "npm install --no-package-lock" in ps1
    assert "npm run build" in ps1


def test_given_install_scripts_when_checked_then_npm_ci_is_nowhere_and_no_npm_call_writes_a_lockfile():
    """
    GIVEN the repository pins pnpm as its only package manager
    WHEN the installer scripts are inspected
    THEN `npm ci` appears in neither script, and every npm *install* call they make
         carries `--no-package-lock`.

    Two measured reasons, both from a throwaway app/ that holds package.json +
    pnpm-lock.yaml and no package-lock.json — the state of a fresh clone:
      * `npm ci --prefix <app>` exits 1 with `npm error code EUSAGE / The `npm ci`
        command can only install with an existing package-lock.json` (npm 11.18.0).
        The fallback branch that reaches it is the one taken when pnpm is ABSENT, so
        the branch could never have worked where it is needed.
      * bare `npm install --prefix <app>` exits 0 and writes package-lock.json next
        to pnpm-lock.yaml — the second lockfile
        tests/test_r46_pnpm_single_source.py::test_single_lockfile_pnpm_only forbids.
    `npm install --no-package-lock` was measured to exit 0, produce app/dist through
    `npm run build`, and write no package-lock.json.
    """
    for name in ("install.sh", "install.ps1"):
        text = (ROOT / name).read_text(encoding="utf-8")
        # Comments may explain why a command was rejected; only executed lines count.
        code_lines = [line for line in text.splitlines() if not line.strip().startswith("#")]
        assert not [line for line in code_lines if "npm ci" in line], name
        install_lines = [
            line.strip()
            for line in code_lines
            if re.search(r"\bnpm\b[^\n]*\binstall\b", line)
        ]
        assert install_lines, f"{name} lost its npm fallback entirely"
        for line in install_lines:
            assert "--no-package-lock" in line, f"{name}: {line}"


def _build_pwa_runnable(tmp_path, tools, dry_run="0"):
    """Extract install.sh's real `build_pwa()` and run it against stub tools.

    Strings are not enough for this branch: the assertions this file had before read
    the same `npm ci` out of install.sh that install.sh then ran, and that command is
    the one which fails with EUSAGE in every fresh clone. So the shipped function body
    is executed with the package managers stubbed to record their argv — the same idea
    as pinning `shutil.which` further down this file: the environment the test declares
    decides the branch here, where the machine's own tools do not.

    `tools` are the executables created in a private bin dir on `PATH = <bin>:/usr/bin:/bin`.
    Leaving "pnpm" out of that list is the missing-pnpm host: neither this Mac
    (/opt/homebrew/bin/pnpm) nor a GitHub runner puts a pnpm in those two directories.
    Nothing real is installed and no network is touched.
    """
    sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    body = re.search(r"^  build_pwa\(\) \{\n(?P<body>.*?)\n  \}$", sh, re.S | re.M)
    assert body, "install.sh no longer defines build_pwa() in the shape this test extracts"

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "package.json").write_text('{"name":"pwa"}', encoding="utf-8")
    (app_dir / "pnpm-lock.yaml").write_text('lockfileVersion: "9.0"\n', encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    for tool in tools:
        (bin_dir / tool).write_text(
            "#!/bin/sh\n"
            f'echo "{tool} $*" >> "{calls}"\n'
            'for arg in "$@"; do\n'
            '  if [ "$arg" = "build" ]; then\n'
            '    mkdir -p "$APP_DIR/dist"\n'
            '    printf "<html>ok</html>" > "$APP_DIR/dist/index.html"\n'
            "  fi\n"
            "done\n"
            "exit 0\n",
            encoding="utf-8",
        )
        (bin_dir / tool).chmod(0o755)

    harness = "\n".join(
        [
            "set -u",
            f'DRY_RUN="{dry_run}"',
            'step() { echo "STEP $*"; }',
            'info() { echo "INFO $*"; }',
            'warn() { echo "WARN $*"; }',
            'ok() { echo "OK $*"; }',
            'fail() { echo "FAIL $*" >&2; exit 1; }',
            'run() { if [[ "$DRY_RUN" == "1" ]]; then echo "DRY-RUN: $*"; else "$@"; fi; }',
            f'PROJECT_DIR="{tmp_path}"',
            f'APP_DIR="{app_dir}"',
            "build_pwa() {",
            body.group("body"),
            "}",
            "build_pwa",
        ]
    )
    env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin", "APP_DIR": str(app_dir)}
    result = subprocess.run(["bash", "-c", harness], capture_output=True, text=True, env=env)

    recorded = [line.split() for line in calls.read_text(encoding="utf-8").splitlines()] if calls.exists() else []
    return recorded, result, app_dir


def test_given_install_sh_build_pwa_when_pnpm_is_absent_then_the_branch_that_runs_is_the_one_that_works(
    tmp_path
):
    """
    GIVEN install.sh's real build_pwa() and a PATH without pnpm
    WHEN it runs against a fresh-clone app/ (package.json + pnpm-lock.yaml, no
         package-lock.json)
    THEN it calls `npm --prefix <app> install --no-package-lock` and then
         `npm --prefix <app> run build`, never `npm ci`, and reports success.
    """
    recorded, result, app_dir = _build_pwa_runnable(tmp_path, ("npm",))

    assert ["npm", "--prefix", str(app_dir), "install", "--no-package-lock"] in recorded, recorded
    assert ["npm", "--prefix", str(app_dir), "run", "build"] in recorded, recorded
    assert not [c for c in recorded if c[0] == "npm" and "ci" in c], recorded
    assert (app_dir / "dist" / "index.html").is_file(), result.stdout + result.stderr
    assert result.returncode == 0, result.stdout + result.stderr


def test_given_install_sh_build_pwa_when_pnpm_is_present_then_the_pinned_lockfile_path_is_unchanged(
    tmp_path
):
    """The npm fallback is only reached without pnpm. With pnpm on PATH the shipped
    behaviour must not move: `install --frozen-lockfile` then `run build`, and no npm
    call at all — which is what keeps app/pnpm-lock.yaml the only lockfile."""
    recorded, result, app_dir = _build_pwa_runnable(tmp_path, ("npm", "pnpm"))

    assert ["pnpm", "--dir", str(app_dir), "install", "--frozen-lockfile"] in recorded, recorded
    assert ["pnpm", "--dir", str(app_dir), "run", "build"] in recorded, recorded
    assert not [c for c in recorded if c[0] == "npm"], recorded
    assert result.returncode == 0, result.stdout + result.stderr


def test_given_install_sh_build_pwa_dry_run_without_dist_then_it_passes_without_building(tmp_path):
    """
    GIVEN a dry run on a fresh app/ where no build has produced app/dist
    WHEN build_pwa() runs
    THEN no tool is invoked and the missing-dist check does not stop the run
    """
    recorded, result, app_dir = _build_pwa_runnable(tmp_path, ("npm", "pnpm"), dry_run="1")

    assert result.returncode == 0, result.stdout + result.stderr
    assert recorded == [], recorded
    assert not (app_dir / "dist" / "index.html").exists()


def test_given_install_script_when_cli_mode_then_pwa_build_is_skipped():
    """
    GIVEN a user installs in --cli (TUI) mode
    WHEN the installer runs
    THEN the PWA build is skipped (the TUI needs no frontend → a faster install).
    """
    sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    # The build step hangs off the desktop mode (not in the cli branch)
    assert 'if [[ "$INSTALL_MODE" != "cli" ]]' in sh


# ephe start: making sure the PWA is built (fresh-clone path)

def _fresh_app_without_dist(tmp_path, monkeypatch):
    """The state of a fresh checkout: `app/` with a package.json, no `app/dist`.

    The seam is `core._cli_ollama.PROJECT_ROOT`, the binding `ensure_pwa_built` reads
    at call time; `ephe_cli.PROJECT_ROOT` is a re-export. Patching the re-export
    instead left the function on the real repository — where a developer's own build
    made the skip-test pass without testing anything, and where the CI checkout has
    no build, so the same test ran `npm ci` and `npm run build` for real and failed as
    `Expected 'run' to not have been called. Called 2 times` (run 37920432535).
    """
    from core import _cli_ollama

    monkeypatch.setattr(_cli_ollama, "PROJECT_ROOT", tmp_path)
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "package.json").write_text('{"name":"pwa"}', encoding="utf-8")
    return _cli_ollama, app_dir


def _which_answers(*names):
    """Pin `core._cli_ollama`'s package-manager probe instead of reading the host.

    `ensure_pwa_built` chooses between building and warning at
    `shutil.which("pnpm") is None` (core/_cli_ollama.py:285). While that call was
    left unpatched, the two build-path tests inherited whatever machine ran them:
    green on a Mac with `/opt/homebrew/bin/pnpm`, `assert False is True` on the
    GitHub Actions runners, which have none — so the documented missing-pnpm branch
    answered instead of the build path (run 37940886343, all five matrix legs). The
    probe decides the branch, which is why the build-path tests below pass
    `_which_answers("pnpm")`, the missing-pnpm test passes `_which_answers()`.

    A name outside the list answers None rather than delegating to the real
    `shutil.which`, so a probe these tests do not pin fails closed instead of
    passing by accident on a host that happens to have the tool.
    """
    return patch(
        "core._cli_ollama.shutil.which",
        side_effect=lambda name: f"/usr/local/bin/{name}" if name in names else None,
    )


def test_given_start_when_pwa_missing_then_it_builds_frontend_through_pnpm(
    capsys, tmp_path, monkeypatch
):
    """
    GIVEN a fresh clone without app/dist (the build artefact is git-ignored)
    WHEN ensure_pwa_built() runs
    THEN it builds through pnpm — the repo's only package manager (`packageManager`
         in app/package.json, pinned by tests/test_r46_pnpm_single_source) — and never
         through npm. This is the path that broke that other test from the inside: npm
         writes app/package-lock.json while it runs, so a single `ephe start` on a
         fresh clone destroyed the one-lockfile contract the same suite asserts.
    """
    _cli_ollama, app_dir = _fresh_app_without_dist(tmp_path, monkeypatch)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if "build" in cmd:
            dist = app_dir / "dist"
            dist.mkdir(parents=True, exist_ok=True)
            (dist / "index.html").write_text("<html>ok</html>", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    with _which_answers("pnpm"), patch("core._cli_ollama._run", side_effect=fake_run):
        assert _cli_ollama.ensure_pwa_built() is True

    assert ["pnpm", "--dir", str(app_dir), "install", "--frozen-lockfile"] in calls, calls
    assert ["pnpm", "--dir", str(app_dir), "run", "build"] in calls, calls
    assert not [c for c in calls if c[0] == "npm"], calls
    assert not (app_dir / "package-lock.json").exists()


def test_given_start_when_frozen_lockfile_fails_then_it_retries_without_the_pin(
    capsys, tmp_path, monkeypatch
):
    """`--frozen-lockfile` is the conservative first try; a lockfile that legitimately
    drifted must not strand the user. The retry is the same shape install.sh's
    build_pwa() uses (`install --frozen-lockfile || install`) — and it stays on pnpm."""
    _cli_ollama, app_dir = _fresh_app_without_dist(tmp_path, monkeypatch)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        rc = 1 if "--frozen-lockfile" in cmd else 0
        if rc == 0 and "build" in cmd:
            dist = app_dir / "dist"
            dist.mkdir(parents=True, exist_ok=True)
            (dist / "index.html").write_text("<html>ok</html>", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, rc)

    with _which_answers("pnpm"), patch("core._cli_ollama._run", side_effect=fake_run):
        assert _cli_ollama.ensure_pwa_built() is True

    assert ["pnpm", "--dir", str(app_dir), "install", "--frozen-lockfile"] in calls, calls
    assert ["pnpm", "--dir", str(app_dir), "install"] in calls, calls
    assert ["pnpm", "--dir", str(app_dir), "run", "build"] in calls, calls
    assert calls.index(["pnpm", "--dir", str(app_dir), "install"]) > calls.index(
        ["pnpm", "--dir", str(app_dir), "install", "--frozen-lockfile"]
    ), calls
    assert not [c for c in calls if c[0] == "npm"], calls
    assert not (app_dir / "package-lock.json").exists()


def test_given_start_when_pwa_present_then_it_skips_build(capsys, tmp_path, monkeypatch):
    """
    GIVEN app/dist/index.html already exists
    WHEN ensure_pwa_built() runs
    THEN it does NOT build again (idempotent, saves time)
    """
    _cli_ollama, app_dir = _fresh_app_without_dist(tmp_path, monkeypatch)
    dist = app_dir / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>ok</html>", encoding="utf-8")

    with patch("core._cli_ollama._run") as run:
        assert _cli_ollama.ensure_pwa_built() is True

    run.assert_not_called()


def test_given_start_when_pnpm_missing_then_it_warns_and_never_falls_back_to_npm(
    capsys, tmp_path, monkeypatch
):
    """
    GIVEN pnpm is not installed and app/dist is missing
    WHEN ensure_pwa_built() runs
    THEN it does NOT abort (warns), but shows the fallback instructions — and does not
         quietly use npm instead. There is no silent package-manager default here any
         more than there is a silent engine default: the hint names the command the
         repository actually documents.
    """
    _cli_ollama, app_dir = _fresh_app_without_dist(tmp_path, monkeypatch)

    with _which_answers(), patch("core._cli_ollama._run") as run:
        assert _cli_ollama.ensure_pwa_built() is False

    run.assert_not_called()
    out = capsys.readouterr().out
    assert "pnpm" in out, out
    assert "npm ci" not in out, out


def _extract_install_function(name: str) -> str:
    """The body of one top-level function in install.sh, so a test can run it in isolation."""
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    match = re.search(rf"^{name}\(\) \{{\n(.*?)\n\}}$", script, re.MULTILINE | re.DOTALL)
    assert match, f"install.sh no longer defines {name}() in the shape this test extracts"
    return match.group(1)


def _fetch_verify_runnable(tmp_path, *, vendor_exit: int, sha_out: str, expected: str):
    """A sandbox with stub curl/shasum and a private TMPDIR around fetch_verify_run()."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    tmpdir = tmp_path / "vendor-tmp"
    tmpdir.mkdir()
    curl = bindir / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        'while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; *) shift;; esac; done\n'
        f"printf '#!/bin/sh\\necho VENDOR_RAN\\nexit {vendor_exit}\\n' > \"$out\"\n",
        encoding="utf-8",
    )
    shasum = bindir / "shasum"
    shasum.write_text('#!/bin/sh\necho "$SHA_OUT  $3"\n', encoding="utf-8")
    curl.chmod(0o755)
    shasum.chmod(0o755)
    runner = tmp_path / "runner.sh"
    runner.write_text(
        "set -euo pipefail\n"
        "DRY_RUN=0\n"
        "info() { :; }\n"
        "ok() { :; }\n"
        "YELLOW=''\n"
        "NC=''\n"
        'fail() { echo "fail: $1" >&2; exit 1; }\n'
        'EPHE_VENDOR_TMP=""\n'
        f"sha256_of() {{\n{_extract_install_function('sha256_of')}\n}}\n"
        f"fetch_verify_run() {{\n{_extract_install_function('fetch_verify_run')}\n}}\n"
        "rc=0\n"
        'fetch_verify_run "https://vendor.invalid/uv" "$EXPECTED" uv EPHE_UV_INSTALL_SHA256 || rc=$?\n'
        'echo "RETURNED $rc"\n',
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "TMPDIR": str(tmpdir),
        "SHA_OUT": sha_out,
        "EXPECTED": expected,
    }
    result = subprocess.run(["bash", str(runner)], capture_output=True, text=True, env=env)
    return result, tmpdir


@pytest.mark.parametrize(
    ("key", "value"),
    [("EPHE_PORT", "notaport"), ("EPHE_PORT", "70000"), ("EPHE_MODE", "bogus")],
)
def test_given_bad_env_when_the_installer_starts_then_it_refuses_before_any_step(
    tmp_path, key, value
):
    """
    GIVEN EPHE_PORT outside 1..65535 or EPHE_MODE outside cli/desktop
    WHEN install.sh runs
    THEN it exits 2 and names the bad variable before the first step prints
    """
    env = {**os.environ, key: value, "EPHE_DRY_RUN": "1"}
    result = subprocess.run(
        ["bash", str(ROOT / "install.sh")],
        cwd=tmp_path, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "offline-first installer" not in result.stdout, result.stdout
    assert key in result.stderr, result.stderr


def test_given_dry_run_off_a_repo_root_then_the_installer_previews_and_creates_nothing(tmp_path):
    """
    GIVEN install.sh runs from a directory that is not the repository
    WHEN the user passes --dry-run
    THEN the clone is only reported, no folder is created and the exit code is 0
    """
    install_dir = tmp_path / "nested" / "Ephe"
    env = {
        **os.environ,
        "EPHE_DRY_RUN": "1",
        "EPHE_PORT": "9001",
        "EPHE_INSTALL_DIR": str(install_dir),
        "EPHE_REPO_URL": "https://example.invalid/ephe.git",
    }
    result = subprocess.run(
        ["bash", str(ROOT / "install.sh")],
        cwd=tmp_path, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DRY-RUN: git clone" in result.stdout, result.stdout
    assert "Dry run stops here" in result.stdout, result.stdout
    assert not install_dir.exists()
    assert not (tmp_path / "nested").exists(), "a dry run created folders"


def test_given_fresh_checkout_when_dry_run_then_it_completes_without_a_pwa_build(tmp_path):
    """
    GIVEN a repository checkout where no build has produced app/dist
    WHEN install.sh runs with EPHE_DRY_RUN=1 from that checkout
    THEN the run reaches the end with exit 0 and reports the build it would do
    """
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "app" / "src").mkdir(parents=True)
    (tmp_path / "run_server.py").write_text("", encoding="utf-8")
    env = {**os.environ, "EPHE_DRY_RUN": "1", "EPHE_NO_START": "1"}
    result = subprocess.run(
        ["bash", str(ROOT / "install.sh")],
        cwd=tmp_path, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Building the PWA" in result.stdout, result.stdout
    assert not (tmp_path / "app" / "dist").exists()


def test_given_existing_checkout_when_the_update_fails_then_the_install_continues():
    """A dirty or offline clone must not stop the one-command install at the pull."""
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "run git pull --ff-only || warn" in script


def test_given_install_sh_when_a_command_fails_then_the_error_trap_names_the_line(tmp_path):
    """
    GIVEN a command inside install.sh returns non-zero under set -e
    WHEN the ERR trap fires
    THEN stderr carries the failing line number and the command text
    """
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    trap_line = next((ln for ln in script.splitlines() if ln.startswith("trap ") and "ERR" in ln), "")
    assert trap_line, "install.sh installs no ERR trap"
    runner = tmp_path / "trap.sh"
    runner.write_text(
        'set -euo pipefail\nRED=""\nNC=""\n' + trap_line + "\nfalse\necho reachable\n",
        encoding="utf-8",
    )
    result = subprocess.run(["bash", str(runner)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "install.sh failed at line" in result.stderr, result.stderr
    assert "false" in result.stderr, result.stderr
    assert "reachable" not in result.stdout


def test_given_a_run_wrapped_command_fails_when_install_sh_aborts_then_the_err_trap_still_names_it(tmp_path):
    """
    GIVEN a step routed through install.sh's own run() helper returns non-zero
    WHEN the ERR trap is judged
    THEN it names the line and the command — the trap must survive a shell function.
         The trap is NOT inherited by functions without `set -E`, and nearly every
         step (venv, pip, pnpm) runs through run(); without `-E` a failed dependency
         install printed the tool's own error and no diagnostic line, while
         docs/INSTALL.md promises the line. Verified red before `set -E` (only the
         tool's `No module named pip` reached stderr) and green after.
    """
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert re.search(r"^set -E\b", script, re.MULTILINE), (
        "install.sh dropped `set -E`: the ERR trap no longer fires for run()-wrapped steps"
    )
    trap_line = next((ln for ln in script.splitlines() if ln.startswith("trap ") and "ERR" in ln), "")
    assert trap_line, "install.sh installs no ERR trap"
    runner = tmp_path / "trap-run.sh"
    runner.write_text(
        'set -euo pipefail\nset -E\nDRY_RUN=0\nRED=""\nNC=""\n'
        + trap_line
        + "\n"
        + f"run() {{\n{_extract_install_function('run')}\n}}\n"
        + "run false\necho reachable\n",
        encoding="utf-8",
    )
    result = subprocess.run(["bash", str(runner)], capture_output=True, text=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "install.sh failed at line" in result.stderr, result.stderr
    assert "reachable" not in result.stdout


def test_given_a_pip_less_existing_venv_when_the_installer_runs_then_it_seeds_pip():
    """
    GIVEN a checkout that already carries a `.venv` with no pip (a `uv venv` shape —
         the repository's own `.venv` is exactly this)
    WHEN install.sh sets up the Python environment
    THEN it seeds pip via ensurepip behind a probe, and calls pip as a module
         everywhere, so the editable install cannot die on `No module named pip`
         or a missing `bin/pip`. Reproduced: the pre-fix script exited 1 at the pip
         step with only `.venv/bin/python: No module named pip` on stderr.
    """
    sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert ".venv/bin/python -m ensurepip --upgrade" in sh, sh
    assert ".venv/bin/python -m pip --version" in sh, "the ensurepip seed is not guarded by a pip probe"
    assert ".venv/bin/pip" not in sh, (
        "install.sh still calls `.venv/bin/pip`, which a uv-created venv does not ship"
    )
    assert '.venv/bin/python -m pip install -e ".[tui]"' in sh
    assert '.venv/bin/python -m pip install -e ".[gui,voice]"' in sh


def test_the_installers_bootstrap_pip_through_the_hash_pinned_wheel():
    """A pip below 26.2.2 trusts the compromised eMudhra intermediates itself.

    The fix is the advisory's direct wheel URL with its SHA-256, so the bootstrap
    is verified before the new pip exists. A plain index upgrade would travel the
    trust path the advisory says is broken.
    """
    sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
    wheel = "pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"
    for text in (sh, ps1):
        assert wheel in text
        assert "pip install --upgrade pip" not in text
        assert "pip bootstrap did not reach 26.2.2" in text


@pytest.mark.parametrize("vendor_exit", [0, 3])
def test_given_vendor_script_when_it_exits_then_status_returns_and_no_temp_file_survives(
    tmp_path, vendor_exit
):
    """
    GIVEN the uv installer downloads, verifies and exits with `vendor_exit`
    WHEN fetch_verify_run() returns
    THEN the code reaches the caller and its temp file is gone from TMPDIR
    """
    sha = "a" * 64
    result, tmpdir = _fetch_verify_runnable(
        tmp_path, vendor_exit=vendor_exit, sha_out=sha, expected=sha
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"RETURNED {vendor_exit}" in result.stdout, result.stdout
    assert list(tmpdir.iterdir()) == [], "the vendor temp file survived the call"


def test_given_vendor_hash_mismatch_when_run_then_it_reports_both_hashes_and_does_not_abort(
    tmp_path,
):
    """
    GIVEN the downloaded vendor script hashes to something other than the pin
    WHEN fetch_verify_run() runs
    THEN it names BOTH hashes on stderr, executes nothing, returns non-zero so the
    caller can fall back to the distro interpreter, and leaves no temp file —
    a rotated vendor hash must not abort a bare box before it has an interpreter
    """
    pinned, live = "b" * 64, "a" * 64
    result, tmpdir = _fetch_verify_runnable(
        tmp_path, vendor_exit=0, sha_out=live, expected=pinned
    )
    # The shell survives the mismatch (no abort) and the status reaches the caller.
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RETURNED 3" in result.stdout, result.stdout
    assert "SHA256 integrity check FAILED" in result.stderr, result.stderr
    assert pinned in result.stderr, "the pinned hash is not named in the report"
    assert live in result.stderr, "the live hash is not named in the report"
    assert "independently verified" in result.stderr.lower(), result.stderr
    assert "to the live sha256" not in result.stderr.lower(), result.stderr
    assert "VENDOR_RAN" not in result.stdout, "the mismatching script was executed"
    assert list(tmpdir.iterdir()) == [], "the vendor temp file survived the refusal"


# Windows route: install.ps1
#
# install.ps1 is the Windows counterpart of install.sh and had none of the hardening
# install.sh received (env validation, --dry-run, an error trap). This host is macOS
# with no Windows, so anything that needs Windows itself (git clone, the winget Python
# install, the venv/pip build, the npm PWA build, ephe start) cannot run here at all.
# What is platform-independent — the parse gate and the argument/env pre-flight — is
# executed against a real PowerShell when one is on PATH and skipped WITH ITS REASON
# when it is not, never passed in silence (the older gate in this file did exactly
# that, which is how a `$var:` scope slip reached the tree on 2026-10-09).

_PWSH = shutil.which("pwsh") or shutil.which("powershell") or ""
requires_pwsh = pytest.mark.skipif(
    not _PWSH,
    reason="no PowerShell interpreter on this host (pwsh/powershell): install.ps1 cannot be "
    "parsed or executed here, so the Windows execution path stays unverified on macOS",
)


def _run_ps1(args, tmp_path, env=None):
    """Run install.ps1 under the host PowerShell with a controlled environment."""
    merged = {**os.environ}
    if env:
        merged.update(env)
    exec_args = ["-ExecutionPolicy", "Bypass"] if os.name == "nt" else []
    return subprocess.run(
        [_PWSH, "-NoProfile", *exec_args, "-File", str(ROOT / "install.ps1"), *args],
        cwd=tmp_path, capture_output=True, text=True, env=merged, stdin=subprocess.DEVNULL,
    )


@requires_pwsh
def test_given_install_ps1_when_parsed_by_powershell_then_it_is_syntactically_valid(tmp_path):
    """
    GIVEN install.ps1 is the first surface a Windows user runs
    WHEN a real PowerShell parser reads it (not a string scan)
    THEN it parses without error — the gate a `$letter:` scope slip defeated while the
         host's pwsh silently skipped the check.
    """
    script_path = str(ROOT / "install.ps1").replace("'", "''")
    expr = (
        f"$null = [scriptblock]::Create((Get-Content -Raw -LiteralPath '{script_path}')); "
        "'PARSE_OK'"
    )
    result = subprocess.run([_PWSH, "-NoProfile", "-Command", expr], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PARSE_OK" in result.stdout, result.stdout


@requires_pwsh
@pytest.mark.parametrize(
    ("key", "value"),
    [("EPHE_PORT", "notaport"), ("EPHE_PORT", "70000"), ("EPHE_MODE", "bogus")],
)
def test_given_bad_env_when_ps1_runs_then_it_refuses_before_any_step(tmp_path, key, value):
    """
    GIVEN EPHE_PORT outside 1..65535 or EPHE_MODE outside cli/desktop
    WHEN install.ps1 runs
    THEN it exits 2 and names the bad variable before the first step prints,
         the same pre-flight install.sh performs.
    """
    result = _run_ps1([], tmp_path, env={key: value, "EPHE_DRY_RUN": "1"})
    assert result.returncode == 2, result.stdout + result.stderr
    assert "offline-first installer" not in result.stdout, result.stdout
    assert key in (result.stderr + result.stdout), result.stdout + result.stderr


@requires_pwsh
def test_given_dry_run_off_a_checkout_when_ps1_runs_then_it_previews_and_creates_nothing(tmp_path):
    """
    GIVEN install.ps1 runs from a directory that is not the repository
    WHEN EPHE_DRY_RUN=1
    THEN the clone is only reported, no folder is created and the exit code is 0.
    """
    install_dir = tmp_path / "nested" / "Ephe"
    result = _run_ps1([], tmp_path, env={
        "EPHE_DRY_RUN": "1",
        "EPHE_PORT": "9001",
        "EPHE_INSTALL_DIR": str(install_dir),
        "EPHE_REPO_URL": "https://example.invalid/ephe.git",
    })
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DRY-RUN: git clone" in result.stdout, result.stdout
    assert "Dry run stops here" in result.stdout, result.stdout
    assert not install_dir.exists()
    assert not (tmp_path / "nested").exists(), "a dry run created folders"


@requires_pwsh
def test_given_fresh_checkout_when_ps1_dry_run_then_it_reports_the_build_and_touches_nothing(tmp_path):
    """
    GIVEN a checkout where no build has produced app/dist
    WHEN install.ps1 runs with EPHE_DRY_RUN=1 and EPHE_NO_START=1
    THEN the run reaches the end with exit 0, reports the build it would do, and
         creates neither app/dist nor .venv.
    """
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "app" / "src").mkdir(parents=True)
    (tmp_path / "run_server.py").write_text("", encoding="utf-8")
    result = _run_ps1([], tmp_path, env={"EPHE_DRY_RUN": "1", "EPHE_NO_START": "1"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Building the PWA" in result.stdout, result.stdout
    assert not (tmp_path / "app" / "dist").exists()
    assert not (tmp_path / ".venv").exists()


def test_given_a_pip_less_existing_venv_when_the_ps1_installer_runs_then_it_seeds_pip():
    """
    GIVEN a checkout that already carries a `.venv` with no pip (a `uv venv` shape —
         no pip module and no Scripts\\pip.exe)
    WHEN install.ps1 sets up the Python environment
    THEN it seeds pip via ensurepip behind a probe and calls pip as a module
         everywhere, so the editable install cannot die on `No module named pip`
         or a missing Scripts\\pip.exe — the guard install.sh already carries.
    """
    ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert '.venv\\Scripts\\python.exe" -m ensurepip --upgrade' in ps1, ps1
    assert '.venv\\Scripts\\python.exe" -m pip --version' in ps1, (
        "the ensurepip seed is not guarded by a pip probe"
    )
    assert ".venv\\Scripts\\pip.exe" not in ps1, (
        "install.ps1 still calls `.venv\\Scripts\\pip.exe`, which a uv-created venv does not ship"
    )
    assert '.venv\\Scripts\\python.exe" -m pip install -e ".[tui]"' in ps1
    assert '.venv\\Scripts\\python.exe" -m pip install -e ".[gui,voice]"' in ps1


def _extract_ps1_function(name):
    """One top-level function body from install.ps1, to run it in isolation.

    Mirrors _extract_install_function for install.sh: a substring scan cannot judge
    a branch, so the shipped body is executed."""
    ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
    match = re.search(
        rf"^function {re.escape(name)}\([^\n]*\) \{{\n(?P<body>.*?)\n\}}$",
        ps1,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"install.ps1 no longer defines {name}() in the shape this test extracts"
    return match.group(0)


def _ps1_venv_block_runnable(tmp_path, cli):
    """Run install.ps1's real venv block under the host PowerShell against a pip-less
    venv laid out the way Windows sees it (Scripts\\python.exe, no Scripts\\pip.exe).

    Windows itself is not available on macOS, so the venv is a `python -m venv
    --without-pip` environment (the same no-pip shape `uv venv` produces) and its
    Scripts\\python.exe is a POSIX shim to the real interpreter. PIP_NO_INDEX keeps
    the run offline: the editable install stops for lack of a project, and the block's
    pip handling — the branch under test — runs for real."""
    ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
    start = 'Step "Setting up the local Python environment"'
    end = 'Ok "Dependencies installed"'
    match = re.search(re.escape(start) + r"(?P<block>.*?)" + re.escape(end), ps1, re.DOTALL)
    assert match, "install.ps1 no longer defines the venv block in the shape this test extracts"

    venv = tmp_path / ".venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)],
        check=True,
        capture_output=True,
        text=True,
    )
    scripts = venv / "Scripts"
    scripts.mkdir()
    shim = scripts / "python.exe"
    shim.write_text(f'#!/bin/sh\nexec "{venv / "bin" / "python"}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)

    harness = tmp_path / "venv-block.ps1"
    harness.write_text(
        "$script:DryRun = $false\n"
        f"$Cli = ${str(cli).lower()}\n"
        '$ErrorActionPreference = "Stop"\n'
        'function Step([string]$Text) { Write-Host "> $Text" }\n'
        'function Ok([string]$Text) { Write-Host "  OK $Text" }\n'
        'function Warn([string]$Text) { Write-Host "  WARN $Text" }\n'
        'function Info([string]$Text) { Write-Host "  $Text" }\n'
        'function Fail([string]$Text) { [Console]::Error.WriteLine("  FAIL $Text"); exit 1 }\n'
        + _extract_ps1_function("Run")
        + "\n"
        + start
        + match.group("block")
        + end
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [_PWSH, "-NoProfile", "-File", str(harness)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
    )
    return result, venv


@requires_pwsh
@pytest.mark.skipif(
    os.name == "nt",
    reason="the Scripts\\python.exe shim is a POSIX shell script; there is no pip-less "
    "interpreter to hand Windows here",
)
@pytest.mark.parametrize("cli", [False, True])
def test_given_a_pip_less_venv_when_the_ps1_block_runs_then_it_seeds_pip_and_never_uses_pip_exe(
    tmp_path, cli
):
    """
    GIVEN a checkout that already carries a `.venv` with no pip (a `uv venv` shape)
    WHEN install.ps1's own venv block runs under a real PowerShell
    THEN it seeds pip with ensurepip and never reaches for Scripts\\pip.exe.

    Measured on this host with pwsh 7.4.6 and Python 3.13: the pre-fix block exited 1
    with only `No module named pip` (pip-less venv), and once pip was seeded by hand it
    died again with a CommandNotFound on Scripts\\pip.exe — both are gone here.
    """
    result, venv = _ps1_venv_block_runnable(tmp_path, cli=cli)
    out = result.stdout + result.stderr
    assert "No module named pip" not in out, out
    assert "pip.exe' is not recognized" not in out, out
    assert not (venv / "Scripts" / "pip.exe").exists()
    # ensurepip ran: the pip that was absent is now installed.
    assert "Successfully installed pip" in out, out
    # and the block carried on into the editable-install branch it was heading for.
    assert ("CLI mode: installing minimal dependencies" in out) == cli, out


# `install.sh` installs the `ephe` console script into `.venv/bin` and edits no shell rc,
# so `ephe configure` typed into a fresh terminal answered "command not found" — the
# finding recorded in docs/UI_AUDIT_2026-10-12.md. The closing block prints the
# activation line first and the commands after it, and docs/INSTALL.md repeats exactly
# those lines. The three tests below pin the path end to end: the printed set is a subset
# of the documented set, which is a subset of the real subparsers of
# `ephe_cli.build_parser()`, and the activation line precedes the first command in both.

_EPHE_COMMAND = re.compile(r"\bephe\s+([a-z][a-z0-9-]+)")
#: The activation line as it appears inside install.sh's `echo`, quotes escaped.
_ACTIVATION_ECHOED = 'source \\"$PROJECT_DIR/.venv/bin/activate\\"'
_ACTIVATION_DOCUMENTED = "source ~/Documents/Ephe/.venv/bin/activate"
_AFTER_INSTALL_HEADING = "## After install"


def _installer_closing_block(script: str) -> str:
    """Everything install.sh prints once the install has succeeded."""
    assert "Setup complete." in script, "install.sh no longer prints a closing block"
    return script.split("Setup complete.", 1)[1]


def _documented_commands(markdown: str) -> set[str]:
    """Top-level `ephe <sub>` commands docs/INSTALL.md shows inside code.

    Only fenced blocks and inline code spans are read, so prose that merely contains
    the word "ephe" is not mistaken for a command — the extractor of
    `tests/test_doc_readme_cli_commands.py`, applied to the install page. Each piece
    is searched line by line: joined into one blob, ``a bare `ephe` answers
    `command not found``` would hand the regex the pair "ephe command".
    """
    pieces = re.findall(r"```[a-zA-Z0-9_-]*\n(.*?)```", markdown, re.DOTALL)
    pieces += re.findall(r"`([^`\n]+)`", markdown)
    found: set[str] = set()
    for piece in pieces:
        for line in piece.splitlines():
            found.update(_EPHE_COMMAND.findall(line))
    return found


def _after_install_section(docs: str) -> str:
    """The body of the "After install" heading, up to the next `##` heading."""
    assert _AFTER_INSTALL_HEADING in docs, f"docs/INSTALL.md lost its {_AFTER_INSTALL_HEADING!r} section"
    return docs.split(_AFTER_INSTALL_HEADING, 1)[1].split("\n## ", 1)[0]


def _subcommand_names(parser) -> set[str]:
    """The tokens `ephe` accepts as its first argument."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def test_given_the_installers_closing_block_when_checked_then_its_commands_are_documented_and_real():
    """
    GIVEN install.sh has finished and prints the commands to run next
    WHEN the printed set is compared to docs/INSTALL.md and to the real CLI
    THEN printed <= documented <= subparsers of build_parser(), so the first command
         a user is told to run cannot be one the parser or the docs never had.
    """
    import ephe_cli

    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")

    printed = set(_EPHE_COMMAND.findall(_installer_closing_block(script)))
    documented = _documented_commands(docs)
    real = _subcommand_names(ephe_cli.build_parser())

    # A floor for the extractors: an empty printed set would pass the subset checks
    # below while promising nothing at all.
    assert {"configure", "doctor"} <= printed, (
        f"the closing block no longer prints the first two commands; found {sorted(printed)}"
    )
    assert printed <= documented, (
        "install.sh prints commands docs/INSTALL.md never shows: "
        f"{sorted(printed - documented)}"
    )
    assert documented <= real, (
        f"docs/INSTALL.md documents commands the CLI does not have: {sorted(documented - real)}"
    )


def test_given_the_documented_after_install_block_when_checked_then_it_repeats_the_installer_exactly():
    """
    GIVEN the "After install" section a newcomer reads
    WHEN its first fenced block is compared to what the installer printed
    THEN the two carry the same command set, so a chapter edited on one side alone
         fails here.
    """
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")

    section = _after_install_section(docs)
    block = re.search(r"```(?:bash)?\n(.*?)```", section, re.DOTALL)
    assert block, "the After install section has no fenced command block"

    printed = set(_EPHE_COMMAND.findall(_installer_closing_block(script)))
    shown = set(_EPHE_COMMAND.findall(block.group(1)))

    assert shown == printed, (
        "the After install block and install.sh's closing block disagree: "
        f"documented only {sorted(shown - printed)}, printed only {sorted(printed - shown)}"
    )


def test_given_a_fresh_terminal_when_the_installer_finishes_then_activation_precedes_the_commands():
    """
    GIVEN the user opens a new terminal after the install
    WHEN the installer's closing block and the docs are read
    THEN both put `source …/.venv/bin/activate` before the first `ephe` command, and the
         docs name the failure that skipping it produces (`command not found`).
    """
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")

    closing = _installer_closing_block(script)
    assert _ACTIVATION_ECHOED in closing, "the closing block no longer prints the activation line"
    assert closing.index(_ACTIVATION_ECHOED) < closing.index("ephe configure")

    section = _after_install_section(docs)
    assert _ACTIVATION_DOCUMENTED in section, "the After install section lost the activation line"
    assert section.index(_ACTIVATION_DOCUMENTED) < section.index("ephe configure")
    assert "command not found" in section


# The same PATH gap opens on Windows: install.ps1 installs the `ephe` console script into
# .venv\Scripts and edits no PowerShell profile, so `ephe configure` typed into a fresh window
# is "not recognized". The closing block now prints the activation line first and the ephe
# commands after it, and docs/INSTALL.md's Windows section repeats exactly those lines. The
# Windows leg is checked by extraction only — this suite runs no PowerShell.

_EPHE_PS1_ACTIVATION_ECHOED = "\\\\.venv\\\\Scripts\\\\Activate.ps1"
_EPHE_PS1_ACTIVATION_DOCUMENTED = "\\.venv\\Scripts\\Activate.ps1"
_PS1_WINDOWS_HEADING = "### Windows (PowerShell)"


def _windows_section(docs: str) -> str:
    """The Windows (PowerShell) section of docs/INSTALL.md, up to the next `###` heading."""
    assert _PS1_WINDOWS_HEADING in docs, f"docs/INSTALL.md lost its {_PS1_WINDOWS_HEADING!r} section"
    return docs.split(_PS1_WINDOWS_HEADING, 1)[1].split("\n### ", 1)[0]


def test_given_the_powershell_installer_closing_block_when_checked_then_its_commands_are_documented_and_real():
    """
    GIVEN install.ps1 has finished and prints the commands to run next
    WHEN the printed set is compared to docs/INSTALL.md and to the real CLI
    THEN printed <= documented <= subparsers of build_parser(), so the first command a
         Windows user is told to run cannot be one the parser or the docs never had.
    """
    import ephe_cli

    script = (ROOT / "install.ps1").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")

    printed = set(_EPHE_COMMAND.findall(_installer_closing_block(script)))
    documented = _documented_commands(docs)
    real = _subcommand_names(ephe_cli.build_parser())

    assert {"configure", "doctor"} <= printed, (
        f"the PowerShell closing block no longer prints the first two commands; found {sorted(printed)}"
    )
    assert printed <= documented, (
        "install.ps1 prints commands docs/INSTALL.md never shows: "
        f"{sorted(printed - documented)}"
    )
    assert documented <= real, (
        f"docs/INSTALL.md documents commands the CLI does not have: {sorted(documented - real)}"
    )


def test_given_a_fresh_powershell_when_the_installer_finishes_then_activation_precedes_the_commands():
    """
    GIVEN a Windows user opens a new PowerShell window after the install
    WHEN the installer's closing block and the docs are read
    THEN both put the activation line before the first `ephe` command.
    """
    script = (ROOT / "install.ps1").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "INSTALL.md").read_text(encoding="utf-8")

    closing = _installer_closing_block(script)
    assert _EPHE_PS1_ACTIVATION_ECHOED in closing, "the PowerShell closing block no longer prints the activation line"
    assert closing.index(_EPHE_PS1_ACTIVATION_ECHOED) < closing.index("ephe configure")

    section = _windows_section(docs)
    assert _EPHE_PS1_ACTIVATION_DOCUMENTED in section, "the Windows section lost the activation line"
    assert section.index(_EPHE_PS1_ACTIVATION_DOCUMENTED) < section.index("ephe configure")
