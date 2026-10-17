"""uninstall.sh is the way out of the product, and the one script in this repo
whose mistake cannot be undone.

install.sh puts a checkout in `EPHE_INSTALL_DIR` (default `$HOME/Documents/Ephe`)
and a state tree in `~/.ephe`; uninstall.sh is the supported way back out. The
tests below run it for real — always against a throwaway HOME inside `tmp_path`,
never the caller's, so no assertion here can reach a real checkout — and they pin
the three things a way out has to get right: a dry run and every refusal remove
nothing, a real run removes exactly the two trees it names, and the data tree
(sessions, memory, artifacts, the engine key) survives unless the caller asked for
it in so many words.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "uninstall.sh"
README = ROOT / "README.md"

# The script is bash-only (same posture as install.sh: `set -euo pipefail`, the
# `[[ ]]` guards, the ERR trap). On a host where /bin/sh IS bash — macOS — the
# documented `sh uninstall.sh --dry-run` works and is executed below; where /bin/sh
# is a pure POSIX shell (dash on Ubuntu) that leg is skipped WITH ITS REASON and
# never passed in silence.
_SH_IS_BASH = bool(
    subprocess.run(
        ["sh", "-c", "test -n \"${BASH_VERSION:-}\""], capture_output=True, text=True
    ).returncode
    == 0
)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(result: subprocess.CompletedProcess[str]) -> str:
    return _ANSI.sub("", result.stdout + result.stderr)


def _run(
    home: Path,
    *args: str,
    shell: str = "bash",
    checkout: str | Path | None = None,
    data: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run uninstall.sh with HOME pinned to `home`; nothing else is inherited.

    `checkout`/`data` are left unset by default so the run exercises the script's
    own defaults (`$HOME/Documents/Ephe`, `$HOME/.ephe`) rather than an override.
    """
    env = dict(os.environ)
    env["HOME"] = str(home)
    for key in (
        "EPHE_INSTALL_DIR",
        "EPHE_CONFIG_DIR",
        "EPHE_DRY_RUN",
        "EPHE_KEEP_DATA",
    ):
        env.pop(key, None)
    if checkout is not None:
        env["EPHE_INSTALL_DIR"] = str(checkout)
    if data is not None:
        env["EPHE_CONFIG_DIR"] = str(data)
    return subprocess.run(
        [shell, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
    )


@pytest.fixture
def fake(tmp_path: Path) -> dict[str, Path]:
    """A throwaway HOME with the two trees where the defaults put them, plus a
    decoy outside both — the decoy is what proves a run stays inside its lane."""
    home = tmp_path / "home"
    checkout = home / "Documents" / "Ephe"
    (checkout / "app" / "src").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text('name = "ephe"\n', encoding="utf-8")
    (checkout / "run_server.py").write_text("# entry point\n", encoding="utf-8")
    (checkout / "app" / "src" / "main.tsx").write_text("export const x = 1\n", encoding="utf-8")
    (checkout / ".venv" / "bin").mkdir(parents=True)
    (checkout / ".venv" / "bin" / "ephe").write_text("#!/bin/sh\necho ephe\n", encoding="utf-8")

    data = home / ".ephe"
    for sub in ("memory", "sessions/audio", "sessions/images", "artifacts", "changesets", "bench"):
        (data / sub).mkdir(parents=True, exist_ok=True)
    (data / "engine.json").write_text('{"provider": "openai_compatible"}\n', encoding="utf-8")
    (data / "engine.key").write_text("sk-not-a-real-key\n", encoding="utf-8")
    (data / "memory" / "user_profile.json").write_text('{"name": "probe"}\n', encoding="utf-8")
    (data / "sessions" / "audio" / "one.wav").write_text("a session\n", encoding="utf-8")

    decoy = tmp_path / "not-ephe"
    decoy.mkdir()
    (decoy / "keepme.txt").write_text("do not touch\n", encoding="utf-8")
    (tmp_path / "Documents-note.txt").write_text("do not touch\n", encoding="utf-8")
    return {"home": home, "checkout": checkout, "data": data, "decoy": decoy, "tmp": tmp_path}


def test_given_uninstall_sh_when_parsed_then_bash_and_sh_accept_it():
    """
    GIVEN uninstall.sh, the counterpart of the installer CI already syntax-checks
    WHEN `bash -n` parses it, and `sh -n` does the same where /bin/sh is bash
    THEN both accept it, so a user who runs it straight out of the checkout is not
         the first one to find a syntax error. On a host whose /bin/sh is dash the
         script's bash-only syntax is meant to fail that parse, so that leg is
         skipped with this reason rather than asserted.
    """
    assert SCRIPT.is_file(), "uninstall.sh is missing from the repository root"
    for shell in ("bash", "sh"):
        if shell == "sh" and not _SH_IS_BASH:
            # uninstall.sh is bash-only (`set -euo pipefail`, `[[ ]]`, here-strings), so a
            # dash /bin/sh is meant to reject it; the documented `sh uninstall.sh` path is a
            # macOS leg, and it is skipped with this reason rather than asserted.
            pytest.skip("/bin/sh here is not bash, and uninstall.sh is bash-only like install.sh")
        result = subprocess.run(
            [shell, "-n", str(SCRIPT)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"{shell} -n: {result.stdout}{result.stderr}"


@pytest.mark.parametrize("shell", ["bash", "sh"])
def test_given_dry_run_when_it_runs_then_it_names_both_trees_and_removes_nothing(fake, shell):
    """
    GIVEN a checkout and a state tree in their default places
    WHEN uninstall.sh runs with --dry-run
    THEN it names both trees with their size and file count, prints the `rm -rf` it
         would run, and leaves every byte of the fake HOME exactly where it was —
         a dry run that deletes something is the bug this test exists for
    """
    if shell == "sh" and not _SH_IS_BASH:
        pytest.skip("/bin/sh here is not bash, and uninstall.sh is bash-only like install.sh")
    before = sorted(p.relative_to(fake["home"]).as_posix() for p in fake["home"].rglob("*"))
    result = _run(fake["home"], "--dry-run", shell=shell)
    out = _plain(result)
    after = sorted(p.relative_to(fake["home"]).as_posix() for p in fake["home"].rglob("*"))

    assert result.returncode == 0, out
    assert "DRY-RUN: rm -rf" in out, out
    assert str(fake["checkout"]) in out, out
    assert str(fake["data"]) in out, out
    assert "Dry run — nothing was removed." in out, out
    assert "would remove" in out, out
    assert before == after, "the dry run changed the tree"
    assert fake["checkout"].is_dir() and fake["data"].is_dir()


def test_given_yes_when_it_runs_then_exactly_the_two_trees_go_and_the_neighbour_stays(fake):
    """
    GIVEN a checkout, a state tree and a neighbouring file neither of them owns
    WHEN uninstall.sh runs with --yes
    THEN both trees are gone, the neighbour is untouched, and the run reports what
         it removed — "exactly these two paths, nothing else" is the whole contract
    """
    result = _run(fake["home"], "--yes")
    out = _plain(result)

    assert result.returncode == 0, out
    assert not fake["checkout"].exists(), "the checkout survived --yes"
    assert not fake["data"].exists(), "the data tree survived --yes"
    assert fake["decoy"].is_dir() and (fake["decoy"] / "keepme.txt").is_file()
    assert (fake["tmp"] / "Documents-note.txt").is_file()
    assert f"checkout: removed {fake['checkout']}" in out, out
    assert f"data: removed {fake['data']}" in out, out
    assert "Ephe is gone from this machine." in out, out
    assert "curl -fsSL" in out and "install.sh" in out, "no way back is printed"


def test_given_no_yes_and_no_terminal_when_it_runs_then_the_data_tree_is_kept(fake):
    """
    GIVEN the caller did not say --yes and there is no terminal to prompt on
    WHEN uninstall.sh runs with stdin closed
    THEN the checkout goes, the state tree stays, and the run prints the exact
         command that would remove it — user data is never deleted by silence
    """
    result = _run(fake["home"])
    out = _plain(result)

    assert result.returncode == 0, out
    assert not fake["checkout"].exists(), "the checkout was not removed"
    assert fake["data"].is_dir(), "a non-interactive run deleted user data without being asked"
    assert (fake["data"] / "engine.key").is_file()
    assert str(fake["data"]) in out and "keeping" in out, out
    assert "./uninstall.sh --yes" in out, "no actionable line for removing the data"


def test_given_keep_data_when_it_runs_then_the_state_tree_survives_yes(fake):
    """
    GIVEN --keep-data next to --yes (the flags that would otherwise contradict)
    WHEN uninstall.sh runs
    THEN --keep-data wins and the state tree is left standing, so the flag cannot
         be swallowed by a later one
    """
    result = _run(fake["home"], "--yes", "--keep-data")
    out = _plain(result)

    assert result.returncode == 0, out
    assert not fake["checkout"].exists(), "the checkout was not removed"
    assert fake["data"].is_dir(), "--keep-data did not keep the data"
    assert "your data is still at" in out, out


# The depth rule is probed with `/usr`, not `/tmp`: on a Linux runner pytest's own
# tmp_path — and with it this fake HOME and its data tree — lives under /tmp, so /tmp
# also *contains* the data tree and the disjointness guard, a different refusal, is the
# one that answers. /usr is a top-level directory on both macOS and Linux and holds
# neither tree, so the depth rule is the one under test on either host.
@pytest.mark.parametrize(
    ("checkout", "data", "told"),
    [
        ("/", None, "filesystem root"),
        ("/usr", None, "top-level directory"),
        ("__home__", "__outside__", "is your home directory"),
    ],
)
def test_given_a_wrong_path_when_it_runs_then_it_refuses_and_removes_nothing(
    fake, checkout, data, told
):
    """
    GIVEN EPHE_INSTALL_DIR set to a filesystem root, a top-level directory, or the
         user's home directory — each reachable through one typo in an env var
    WHEN uninstall.sh runs, even with --dry-run
    THEN it exits 2, names the rule it refused on, and removes nothing: a guard that
         only holds in the non-dry path is not a guard
    """
    home = fake["home"]
    target = str(home) if checkout == "__home__" else checkout
    data_arg = str(fake["tmp"] / "elsewhere" / ".ephe") if data == "__outside__" else data
    result = _run(home, "--dry-run", checkout=target, data=data_arg)
    out = _plain(result)

    assert result.returncode == 2, out
    assert told in out, out
    assert home.is_dir() and fake["data"].is_dir()
    assert not (fake["tmp"] / "elsewhere" / ".ephe").exists()


def test_given_a_directory_that_is_no_checkout_when_it_runs_then_it_refuses(fake):
    """
    GIVEN EPHE_INSTALL_DIR points at a directory that carries no Ephe markers
    WHEN uninstall.sh runs
    THEN it refuses (exit 2) and leaves the directory alone, because "rm -rf what
         the env var says" is how an unrelated folder gets deleted
    """
    (fake["decoy"] / "notes.txt").write_text("mine\n", encoding="utf-8")
    result = _run(fake["home"], "--dry-run", checkout=fake["decoy"])
    out = _plain(result)

    assert result.returncode == 2, out
    assert "not an Ephe checkout" in out, out
    assert (fake["decoy"] / "notes.txt").is_file()
    assert (fake["decoy"] / "keepme.txt").is_file()


def test_given_the_readme_when_read_then_the_way_out_is_documented():
    """
    GIVEN the README is the front door a user reads before installing
    WHEN it is searched for the uninstall surface
    THEN uninstall.sh is named with its flags, so the documented way out of the
         product is the script that exists rather than the one a user has to guess
    """
    readme = README.read_text(encoding="utf-8")
    assert "uninstall.sh" in readme
    assert "--dry-run" in readme
    assert "--keep-data" in readme
    # The project-structure block lists the root scripts next to each other.
    assert "install.sh" in readme and "install.ps1" in readme
