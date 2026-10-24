"""SC-02: an untrusted MCP child cannot reach the user's keys, secrets or code env.

The test runs a real child process, not a mock: one probe script reports what it
could read. On macOS the probe runs under the same Seatbelt profile the stdio
link uses; where that boundary is unavailable the test skips with the reason,
because a green result without the boundary would be the claim this wave exists
to stop.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from core import mcp_sandbox
from core.secret_broker import child_env

PROBE = r"""
import json, os, pathlib
def _can_read(path):
    if not path:
        return None
    try:
        pathlib.Path(path).read_text()
        return True
    except OSError:
        return False
home = pathlib.Path(os.environ["HOME"])
protected = json.loads(os.environ.get("PROTECTED_PATHS", "[]"))
result = {
    "home": str(home),
    "home_is_own": str(home) == os.environ.get("EXPECTED_HOME"),
    "home_readable": (home / "own.txt").read_text() == "ok",
    "engine_key": _can_read(os.environ.get("PROTECTED_KEY", "")),
    "ssh": _can_read(os.environ.get("PROTECTED_SSH", "")),
    "protected": {path: _can_read(path) for path in protected},
    "env_pythonpath": "PYTHONPATH" in os.environ,
    "env_node_options": "NODE_OPTIONS" in os.environ,
    "env_ld": [k for k in os.environ if k.startswith(("LD_", "DYLD_"))],
}
print(json.dumps(result))
"""


@pytest.fixture
def probe(tmp_path):
    script = tmp_path / "probe.py"
    script.write_text(PROBE, encoding="utf-8")
    return script


def _run(probe: Path, home: Path, protected: list[str] | None = None) -> dict:
    argv = mcp_sandbox.wrap(sys.executable, [str(probe)], str(home))
    if argv is None:
        pytest.skip(
            "no OS boundary on this platform "
            f"({sys.platform}, boundary={mcp_sandbox.platform_boundary()}): "
            "a green result would be the claim this test exists to stop"
        )
    (home / "own.txt").write_text("ok", encoding="utf-8")
    env = child_env(
        {
            "EXPECTED_HOME": str(home),
            "PROTECTED_KEY": str(Path(os.path.expanduser("~")) / ".ephe" / "engine.key"),
            "PROTECTED_SSH": str(Path(os.path.expanduser("~")) / ".ssh" / "id_rsa"),
            "PROTECTED_PATHS": json.dumps(protected or []),
        },
        home=str(home),
    )
    run = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_the_child_home_is_its_own_directory(probe):
    home = mcp_sandbox.home_for("probe-home")
    result = _run(probe, home)
    assert result["home_is_own"] and result["home_readable"]


def test_the_engine_key_and_ssh_are_unreadable_from_the_child(probe, monkeypatch, tmp_path):
    fake_home = tmp_path / "user"
    (fake_home / ".ssh").mkdir(parents=True)
    (fake_home / ".ssh" / "id_rsa").write_text("PRIVATE", encoding="utf-8")
    (fake_home / ".ephe").mkdir()
    (fake_home / ".ephe" / "engine.key").write_text("sk-test", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))
    home = mcp_sandbox.home_for("probe-secrets")
    result = _run(probe, home)
    assert result["engine_key"] is False, "the child could see the engine key"
    assert result["ssh"] is False, "the child could see ~/.ssh"


def test_code_loading_environment_is_not_inherited(probe, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/evil")
    monkeypatch.setenv("NODE_OPTIONS", "--require /evil.js")
    monkeypatch.setenv("DYLD_INSERT_LIBRARIES", "/evil.dylib")
    home = mcp_sandbox.home_for("probe-env")
    result = _run(probe, home)
    assert result["env_pythonpath"] is False
    assert result["env_node_options"] is False
    assert result["env_ld"] == []


def test_the_profile_denies_the_whole_home_and_reopens_only_the_child(monkeypatch, tmp_path):
    fake_home = tmp_path / "user"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("EPHE_CONFIG_DIR", raising=False)
    child_home = fake_home / ".ephe" / "mcp" / "homes" / "srv"
    child_home.mkdir(parents=True)
    profile = mcp_sandbox.build_profile(str(child_home))
    real_home = os.path.realpath(fake_home)
    child = os.path.realpath(child_home)
    assert "(deny file-read*" in profile
    assert f'(subpath "{real_home}")' in profile
    assert "(deny file-write*)" in profile
    # The child home sits under the denied home; its read rule must come after
    # the deny, or the child cannot read its own home.
    assert profile.rstrip().endswith(f'(allow file-read* (subpath "{child}"))')


def test_the_named_user_secrets_are_unreadable_from_the_child(probe, monkeypatch, tmp_path):
    """The enumeration that used to be the macOS boundary is now only a list;
    the profile denies the home and the probe checks each named path."""
    fake_home = tmp_path / "user"
    secrets = {
        ".ssh/id_rsa": "PRIVATE",
        ".ephe/engine.key": "sk-test",
        "Library/Safari/History.db": "history",
        "Library/Cookies/Cookies.binarycookies": "cookies",
        "Library/Mail/inbox.eml": "mail",
        "Library/Messages/chat.db": "messages",
        ".zsh_history": "history",
        ".gitconfig": "config",
    }
    for rel, content in secrets.items():
        target = fake_home / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("EPHE_CONFIG_DIR", raising=False)

    home = mcp_sandbox.home_for("probe-home-secrets")
    result = _run(
        probe,
        home,
        protected=[str(fake_home / rel) for rel in secrets],
    )

    assert result["home_readable"], "the child cannot read its own home"
    for path, readable in result["protected"].items():
        assert readable is False, f"the child could read {path}"


def test_the_runtime_exception_cannot_open_a_secret_subtree(monkeypatch, tmp_path):
    fake_home = tmp_path / "user"
    normal = fake_home / "venvs" / "app" / "bin" / "python"
    secret = fake_home / ".ssh" / "venv" / "bin" / "python"
    for path in (normal, secret):
        path.parent.mkdir(parents=True)
        path.write_text("", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))
    real_home = os.path.realpath(fake_home)

    inside = mcp_sandbox._runtime_prefixes(str(normal), real_home)
    outside = mcp_sandbox._runtime_prefixes(str(secret), real_home)

    assert os.path.realpath(normal.parent.parent) in inside
    assert not any(".ssh" in prefix for prefix in outside)


def test_a_prefix_with_only_a_minor_python_is_a_runtime(monkeypatch, tmp_path):
    """uv installs `bin/python3.<minor>` and, on the macOS runner, no bare aliases."""
    fake_home = tmp_path / "user"
    prefix = fake_home / ".local" / "share" / "uv" / "python" / "cpython-3.12.15"
    interpreter = prefix / "bin" / "python3.12"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))
    real_home = os.path.realpath(fake_home)

    assert mcp_sandbox._looks_like_runtime(str(prefix))
    assert os.path.realpath(prefix) in mcp_sandbox._runtime_prefixes(
        str(interpreter), real_home
    )


def test_a_minor_python_under_a_secret_subtree_is_refused(monkeypatch, tmp_path):
    fake_home = tmp_path / "user"
    prefix = fake_home / ".ssh" / "uv-venv"
    interpreter = prefix / "bin" / "python3.12"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))
    real_home = os.path.realpath(fake_home)

    assert mcp_sandbox._looks_like_runtime(str(prefix))
    assert mcp_sandbox._runtime_prefixes(str(interpreter), real_home) == []


def test_the_runtime_allow_follows_the_home_deny_and_the_child_home_is_last(
    monkeypatch, tmp_path
):
    fake_home = tmp_path / "user"
    prefix = fake_home / "runtimes" / "python"
    interpreter = prefix / "bin" / "python3.12"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("", encoding="utf-8")
    child_home = fake_home / ".ephe" / "mcp" / "homes" / "srv"
    child_home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("EPHE_CONFIG_DIR", raising=False)

    profile = mcp_sandbox.build_profile(str(child_home), str(interpreter))

    real_home = os.path.realpath(fake_home)
    real_prefix = os.path.realpath(prefix)
    real_child = os.path.realpath(child_home)
    home_deny = profile.index(f'(deny file-read*\n  (subpath "{real_home}")')
    runtime_allow = profile.index(f'(allow file-read* (subpath "{real_prefix}"))')
    child_allow = profile.index(f'(allow file-read* (subpath "{real_child}"))')
    assert home_deny < runtime_allow < child_allow
    assert profile.rstrip().endswith(f'(allow file-read* (subpath "{real_child}"))')


def test_node_and_python_start_under_the_boundary(monkeypatch, tmp_path):
    fake_home = tmp_path / "user"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    home = mcp_sandbox.home_for("probe-runtimes")
    env = child_env({"EXPECTED_HOME": str(home)}, home=str(home))
    commands = [[sys.executable, "-c", "print('py')"]]
    node = shutil.which("node")
    if node:
        commands.append([node, "-e", "process.exit(0)"])
    for command in commands:
        argv = mcp_sandbox.wrap(command[0], command[1:], str(home))
        if argv is None:
            pytest.skip("no OS boundary on this platform")
        run = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=60)
        assert run.returncode == 0, (command[0], run.stderr)


def test_the_child_home_under_the_default_config_root_is_readable(probe, monkeypatch, tmp_path):
    """The shipped layout: no EPHE_CONFIG_DIR, HOME points at the fake user, so
    the child home lives inside ~/.ephe — the subtree the profile denies. The
    child must read its home and still be refused the key."""
    fake_home = tmp_path / "user"
    (fake_home / ".ephe").mkdir(parents=True)
    (fake_home / ".ephe" / "engine.key").write_text("sk-test", encoding="utf-8")
    (fake_home / ".ssh").mkdir()
    (fake_home / ".ssh" / "id_rsa").write_text("PRIVATE", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("EPHE_CONFIG_DIR", raising=False)

    home = mcp_sandbox.home_for("probe-default-layout")
    assert str(fake_home / ".ephe") in str(home)
    result = _run(probe, home)

    assert result["home_readable"], "the child cannot read its own home"
    assert result["engine_key"] is False
    assert result["ssh"] is False


class TestLinuxBoundary:
    """bubblewrap mounts are a claim that can be read without a Linux host; the
    malicious-child probe above runs wherever the boundary actually exists."""

    @staticmethod
    def _order_is_safe(argv: list[str], real_home: str) -> bool:
        ro = argv.index("--ro-bind")
        home_mount = next(
            index
            for index, arg in enumerate(argv)
            if arg == "--tmpfs" and argv[index + 1] == real_home
        )
        bind = argv.index("--bind")
        chdir = argv.index("--chdir")
        return ro < home_mount < bind < chdir

    def _as_linux(self, monkeypatch, tmp_path):
        home = tmp_path / "user"
        (home / ".ephe").mkdir(parents=True)
        (home / ".ssh").mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setattr(mcp_sandbox.sys, "platform", "linux")
        monkeypatch.setattr(
            mcp_sandbox.shutil, "which",
            lambda name: "/usr/bin/bwrap" if name == "bwrap" else None,
        )
        return home

    def test_the_user_home_is_replaced_and_only_the_child_home_is_bound(
        self, monkeypatch, tmp_path
    ):
        home = self._as_linux(monkeypatch, tmp_path)
        child = home / ".ephe" / "mcp" / "homes" / "srv"
        child.mkdir(parents=True)
        real_home, real_child = os.path.realpath(home), os.path.realpath(child)
        assert mcp_sandbox.platform_boundary() == "bubblewrap"

        argv = mcp_sandbox.wrap("mcp-server", ["--flag"], str(child))

        assert argv[:1] == ["bwrap"]
        ro = argv.index("--ro-bind")
        assert argv[ro + 1 : ro + 3] == ["/", "/"]
        mounts = [argv[i + 1] for i, arg in enumerate(argv) if arg == "--tmpfs"]
        home_mount = argv.index(real_home)
        bind = argv.index("--bind")
        chdir = argv.index("--chdir")
        assert real_home in mounts, "the user's home is not replaced"
        assert "/tmp" not in mounts, (
            "the shared temp must stay readable: a server script may live under /tmp, "
            "and TMPDIR already points at the child's own tmp"
        )
        assert argv[bind + 1 : bind + 3] == [real_child, real_child]
        assert argv[chdir + 1] == real_child
        assert argv[-2:] == ["mcp-server", "--flag"]
        # Order is the boundary: a home tmpfs after the bind, or a ro-bind after
        # the tmpfs, would expose the very directory the mount hides.
        assert self._order_is_safe(argv, real_home)
        swapped = list(argv)
        ro_pair = swapped[ro : ro + 3]
        del swapped[ro : ro + 3]
        home_tmpfs = next(
            index
            for index, arg in enumerate(swapped)
            if arg == "--tmpfs" and swapped[index + 1] == real_home
        )
        swapped[home_tmpfs + 2 : home_tmpfs + 2] = ro_pair
        assert not self._order_is_safe(swapped, real_home), (
            "a ro-bind moved behind the home tmpfs must break the order check"
        )

    def test_a_config_root_outside_the_home_is_hidden_too(
        self, monkeypatch, tmp_path
    ):
        home = self._as_linux(monkeypatch, tmp_path)
        outside = tmp_path / "cfg-outside"
        outside.mkdir()
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(outside))
        child = home / ".ephe" / "mcp" / "homes" / "srv"
        child.mkdir(parents=True)

        argv = mcp_sandbox.wrap("mcp-server", [], str(child))

        mounts = [argv[i + 1] for i, arg in enumerate(argv) if arg == "--tmpfs"]
        assert os.path.realpath(outside) in mounts
        assert argv.index(os.path.realpath(outside)) < argv.index("--bind")

    def test_a_runtime_installed_under_the_home_is_reopened(self, monkeypatch, tmp_path):
        """The CI leg's interpreter lives under the runner's home; the home tmpfs hides it,
        so the command's own prefix is bound back read-only after the hides."""
        home = self._as_linux(monkeypatch, tmp_path)
        venv = home / "work" / "venv"
        (venv / "bin").mkdir(parents=True)
        (venv / "bin" / "python").write_text("", encoding="utf-8")
        child = home / ".ephe" / "mcp" / "homes" / "srv"
        child.mkdir(parents=True)

        argv = mcp_sandbox.wrap(str(venv / "bin" / "python"), ["server.py"], str(child))

        real_home, real_venv = os.path.realpath(home), os.path.realpath(venv)
        home_hide = next(
            i for i, arg in enumerate(argv) if arg == "--tmpfs" and argv[i + 1] == real_home
        )
        reopened = [
            i
            for i, arg in enumerate(argv)
            if arg == "--ro-bind" and argv[i + 1] == real_venv
        ]
        assert reopened, "an interpreter under the home is not reopened"
        assert reopened[0] > home_hide, "the runtime must be reopened after the home is hidden"
        assert reopened[0] < argv.index("--bind")

    def test_a_host_without_the_boundary_wraps_nothing(self, monkeypatch):
        monkeypatch.setattr(mcp_sandbox.shutil, "which", lambda name: None)
        assert mcp_sandbox.platform_boundary() == "unavailable"
        assert mcp_sandbox.wrap("mcp-server", [], "/tmp/x") is None
