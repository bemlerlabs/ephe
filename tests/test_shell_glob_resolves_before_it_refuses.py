"""A relative glob is judged on what it matches (F-3).

`_glob_refusal` refused any pattern whose parts held `..` before it looked at
where the pattern lands. The loop under it already expands the pattern with
`pathlib` — which walks a `..` the same way the shell the command spawns does —
and puts every match through the same door as a plain file argument. The ban
therefore answered a different question than the file-tool roots ask: it refused
`src/../docs/*.md`, which ends inside the workspace, on the same line as
`../.ssh/*.md`, which does not.

That costs the agent real moves. A note that names a file as `build/../src/*.py`
is the same folder the agent can reach as `src/*.py`, and the second spelling is
allowed — so the refusal taught nothing about the root and made the move look
impossible.

These tests pin both halves. The escape half cannot be shown beside the
workspace: the kernel lists the system temp folder among its allowed roots, so a
folder next to the workspace is a legal read. The folder a `..` walk has to
refuse is one `DENY_ROOTS` already names.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.tools._shell_validate import validate_shell_command


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A workspace inside a home whose `.ssh` the denylist owns."""
    home = tmp_path / "home"
    workspace = home / "proj"
    (workspace / "src").mkdir(parents=True)
    (workspace / "docs").mkdir()
    (workspace / "docs" / "a.md").write_text("INSIDE", encoding="utf-8")
    blocked = home / ".ssh"
    blocked.mkdir()
    (blocked / "note.md").write_text("OUTSIDE", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    return str(workspace)


def test_a_relative_glob_that_returns_inside_the_root_is_allowed(tree) -> None:
    """GIVEN `src/../docs` resolves inside the workspace WHEN the glob is checked THEN it passes."""
    assert validate_shell_command("cat docs/*.md", root=tree) is None
    assert validate_shell_command("cat src/../docs/*.md", root=tree) is None


def test_a_dot_prefixed_relative_glob_is_allowed(tree) -> None:
    assert validate_shell_command("cat ./docs/*.md", root=tree) is None
    assert validate_shell_command("cat ./src/../docs/a.md", root=tree) is None


def test_a_glob_that_walks_out_to_a_denied_root_is_refused(tree) -> None:
    """The escape the ban was written for stays shut — on the match, not the spelling."""
    refusal = validate_shell_command("cat ../.ssh/*.md", root=tree)
    assert refusal is not None
    assert "OUTSIDE" not in refusal


@pytest.mark.parametrize(
    "pattern",
    [
        "../.ssh/*.md",
        "../.ss*h/note.md",
        "../../home/.ssh/*.md",
        "../.ssh/id_rsa*",
    ],
)
def test_no_spelling_of_the_denied_folder_is_allowed(tree, pattern) -> None:
    """A wildcard inside the denied name, and a `..` behind a wildcard, both stay shut.

    The last spelling is refused for its name rather than its match: a pattern
    that matches nothing reads nothing, and a credential-shaped word in the text
    is refused without asking the filesystem.
    """
    refusal = validate_shell_command(f"cat {pattern}", root=tree)
    assert refusal is not None, pattern


def test_a_glob_that_names_a_credential_while_returning_inside_is_refused(tree) -> None:
    """Resolution does not retire the name check: `.env` is still a dotenv name."""
    (Path(tree) / ".env").write_text("MARKER_BODY", encoding="utf-8")
    refusal = validate_shell_command("cat src/../.env", root=tree)
    assert refusal is not None
    assert "MARKER_BODY" not in refusal
