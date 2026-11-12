"""Shell file arguments use the same door as the file tools.

A whitelisted head such as cat used to skip that door. These cases refuse a
credential-shaped name and a path outside the file-tool roots, and they do
not open the file.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.tools.base import ALLOWED_COMMANDS
from core.tools.shell_tools import execute_confirmed_shell, validate_shell_command


def test_bash_is_an_interpreter_and_near_is_not_a_command() -> None:
    """bash joins the interpreter heads. No command named near is invented."""
    assert "bash" in ALLOWED_COMMANDS
    assert "near" not in ALLOWED_COMMANDS
    assert "curl" not in ALLOWED_COMMANDS
    assert "wget" not in ALLOWED_COMMANDS
    assert validate_shell_command("bash --version") is None
    assert validate_shell_command("bash script.sh") is None


def test_a_dotenv_name_on_cat_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """cat of a dotenv name is refused before the file is opened."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / ".env"
    target.write_text("MARKER_BODY", encoding="utf-8")
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: (_ for _ in ()).throw(AssertionError("read")))
    monkeypatch.setattr(Path, "read_bytes", lambda *a, **k: (_ for _ in ()).throw(AssertionError("read")))

    refusal = validate_shell_command("cat .env", root=str(workspace))

    assert refusal is not None
    assert "file-tool roots" in refusal
    assert "MARKER_BODY" not in refusal


def test_the_same_name_is_refused_when_the_sandbox_is_on(tmp_path: Path) -> None:
    """The seatbelt profile allows reads, so the file door stays shut."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    assert validate_shell_command("cat .env", sandboxed=True, root=str(workspace)) is not None
    assert validate_shell_command("head -n 5 .env", root=str(workspace)) is not None
    assert validate_shell_command("head --lines=5 .env", root=str(workspace)) is not None
    assert validate_shell_command("grep -n pattern .env", root=str(workspace)) is not None
    assert validate_shell_command("cp .env notes.txt", root=str(workspace)) is not None
    assert validate_shell_command("cat ../.env", root=str(workspace)) is not None
    assert validate_shell_command("cat id_rsa", root=str(workspace)) is not None


def test_an_ordinary_project_file_still_passes(tmp_path: Path) -> None:
    """A name inside the file-tool roots that is not credential-shaped passes."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    root = str(workspace)
    assert validate_shell_command("cat notes.txt", root=root) is None
    assert validate_shell_command("grep secret notes.txt", root=root) is None
    assert validate_shell_command("head -n 20 notes.txt", root=root) is None
    assert validate_shell_command("cat notes.txt | grep foo | sort", root=root) is None
    assert validate_shell_command("ls", root=root) is None
    assert validate_shell_command("git status", root=root) is None
    assert validate_shell_command('git commit -m "fix a && deploy b"', root=root) is None
    assert validate_shell_command("echo hello", root=root) is None
    assert validate_shell_command("tail -f /dev/null", root=root) is None


def test_a_path_outside_the_file_roots_is_refused(tmp_path: Path) -> None:
    """An absolute path the file tools refuse is refused on cat too."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    refusal = validate_shell_command("cat /etc/hosts", root=str(workspace))
    assert refusal is not None
    assert "file-tool roots" in refusal


def test_a_symlink_to_a_dotenv_name_is_refused(tmp_path: Path) -> None:
    """The resolved target is what the door sees."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / ".env"
    target.write_text("MARKER_BODY", encoding="utf-8")
    link = workspace / "notes.txt"
    link.symlink_to(target)

    refusal = validate_shell_command("cat notes.txt", root=str(workspace))

    assert refusal is not None
    assert "MARKER_BODY" not in refusal


def test_a_glob_that_matches_a_dotenv_name_is_refused(tmp_path: Path) -> None:
    """A shell glob is expanded inside the workspace before the command runs."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".env").write_text("MARKER_BODY", encoding="utf-8")
    (workspace / "notes.txt").write_text("hello", encoding="utf-8")
    root = str(workspace)

    dotted = validate_shell_command("cat .*", root=root)
    assert dotted is not None and "MARKER_BODY" not in dotted
    assert validate_shell_command("cat *.txt", root=root) is None
    assert validate_shell_command("cat *.env", root=root) is not None


def test_find_exec_is_refused_and_git_show_of_a_dotenv_name_is_refused(tmp_path: Path) -> None:
    """find -exec and a git path that names the dotenv file are refused."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    root = str(workspace)
    assert validate_shell_command("find . -name notes.txt", root=root) is None
    assert validate_shell_command("find . -exec cat {} \\;", root=root) is not None
    assert validate_shell_command("find /etc -name hosts", root=root) is not None
    assert validate_shell_command("git show HEAD:.env", root=root) is not None
    assert validate_shell_command("git diff .env", root=root) is not None


def test_bash_eval_cannot_name_a_dotenv_file(tmp_path: Path) -> None:
    """bash -c stays locked, and a sandboxed eval body is scanned too."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    root = str(workspace)
    assert validate_shell_command("bash -c 'cat .env'", root=root) is not None
    assert validate_shell_command("bash -c 'cat .env'", sandboxed=True, root=root) is not None
    assert validate_shell_command("printf 'x' | bash", root=root) is not None
    assert validate_shell_command("python3 -c 'print(1)'", sandboxed=True, root=root) is None
    opened = "python3 -c 'open(\".env\")'"
    assert validate_shell_command(opened, sandboxed=True, root=root) is not None


def test_an_unknown_head_names_the_closest_allowed_command() -> None:
    """A near-miss head is told the closest allowed command."""
    refusal = validate_shell_command("pyton script.py")
    assert refusal is not None
    assert "Closest allowed command: python" in refusal


@pytest.mark.asyncio
async def test_cat_of_a_dotenv_name_does_not_spawn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The refusal returns before a process is started."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))

    with patch("subprocess.Popen") as mocked:
        out = await execute_confirmed_shell("cat .env", confirmed=True)

    mocked.assert_not_called()
    assert "file-tool roots" in out


@pytest.fixture()
def plugin_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A plugin call's workspace and its declared (read-only) data root."""
    from core.tools.base import PLUGIN_FILE_SCOPE

    workspace = tmp_path / "ws"
    declared = tmp_path / "declared"
    workspace.mkdir()
    declared.mkdir()
    (workspace / "notes.txt").write_text("notes\n", encoding="utf-8")
    (declared / "note.md").write_text("read me\n", encoding="utf-8")
    monkeypatch.setattr("core.engine_config.get_workspace_dir", lambda: str(workspace))
    monkeypatch.setattr(
        "core.capability_policy.resolved_data_roots",
        lambda plugin, root: [declared.resolve()],
    )
    token = PLUGIN_FILE_SCOPE.set("acme-research")
    try:
        yield SimpleNamespace(workspace=workspace, declared=declared)
    finally:
        PLUGIN_FILE_SCOPE.reset(token)


@pytest.mark.parametrize(
    "template",
    [
        "mkdir {declared}/new",
        "cp {workspace}/notes.txt {declared}/copy.txt",
        "mv {workspace}/notes.txt {declared}/moved.txt",
        "touch {declared}/touched.txt",
        "chmod 600 {declared}/note.md",
    ],
)
def test_a_shell_writer_cannot_use_a_declared_data_root(template: str, plugin_scope) -> None:
    """A read grant is not a write target — the command is refused before it runs."""
    command = template.format(
        workspace=plugin_scope.workspace, declared=plugin_scope.declared
    )
    refusal = validate_shell_command(command, root=str(plugin_scope.workspace))
    assert refusal is not None, command
    assert "read grant" in refusal


def test_a_shell_writer_still_works_in_the_workspace(plugin_scope) -> None:
    """The rail that matters keeps working: reads of the data root and writes of the workspace."""
    root = str(plugin_scope.workspace)
    assert validate_shell_command(f"cat {plugin_scope.declared}/note.md", root=root) is None
    assert validate_shell_command("mkdir build", root=root) is None
    assert validate_shell_command("cp notes.txt copy.txt", root=root) is None
    assert validate_shell_command("mv notes.txt moved.txt", root=root) is None
    assert validate_shell_command("touch fresh.txt", root=root) is None
    assert validate_shell_command("chmod 600 notes.txt", root=root) is None
