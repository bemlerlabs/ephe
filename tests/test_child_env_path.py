"""QD-015 Y: the child PATH must contain the tools the user's terminal has.

A Finder-launched app inherits launchd's minimal PATH, so `node`, `npm`,
`git` (Homebrew) and `pnpm` were "command not found" inside the shell tool
while the same user's terminal found them. On macOS the Homebrew heads now go
in front when they exist; an inherited entry is kept, never duplicated.
"""

from __future__ import annotations

import os

import pytest

from core.secret_broker import child_env, hydrate_path

DARWIN = "darwin"


def _existing(*dirs: str):
    return lambda path: path in dirs


class TestHydratePath:
    def test_macos_puts_homebrew_in_front(self):
        path = hydrate_path(
            "/usr/bin:/bin",
            platform=DARWIN,
            exists=_existing("/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin"),
        )
        entries = path.split(os.pathsep)
        assert entries[:3] == ["/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin"]
        assert "/usr/bin" in entries
        assert entries.index("/opt/homebrew/bin") < entries.index("/usr/bin")

    def test_a_directory_that_does_not_exist_is_not_added(self):
        path = hydrate_path("/usr/bin", platform=DARWIN, exists=_existing("/opt/homebrew/bin"))
        assert "/opt/homebrew/bin" in path.split(os.pathsep)
        assert "/usr/local/bin" not in path.split(os.pathsep)

    def test_an_inherited_entry_is_not_duplicated(self):
        path = hydrate_path(
            "/opt/homebrew/bin:/usr/bin",
            platform=DARWIN,
            exists=_existing("/opt/homebrew/bin"),
        )
        entries = path.split(os.pathsep)
        assert entries.count("/opt/homebrew/bin") == 1
        assert entries[0] == "/opt/homebrew/bin"

    def test_linux_keeps_the_inherited_path_first(self):
        path = hydrate_path("/usr/local/bin:/usr/bin", platform="linux", exists=_existing())
        entries = path.split(os.pathsep)
        assert entries[0] == "/usr/local/bin"
        assert "/opt/homebrew/bin" not in entries

    def test_the_posix_core_is_always_reachable(self):
        path = hydrate_path("", platform="linux", exists=_existing())
        assert path.split(os.pathsep) == ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]


class TestChildEnv:
    def test_path_is_present_even_when_the_parent_has_none(self, monkeypatch):
        monkeypatch.delenv("PATH", raising=False)
        env = child_env()
        assert env["PATH"]

    def test_a_declared_path_wins(self, monkeypatch):
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        env = child_env({"PATH": "/opt/custom/bin"})
        assert env["PATH"] == "/opt/custom/bin"

    def test_credentials_still_do_not_leak(self, monkeypatch):
        monkeypatch.setenv("MY_PRIVATE_TOKEN", "do-not-pass")
        assert "MY_PRIVATE_TOKEN" not in child_env()
