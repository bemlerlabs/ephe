"""GAP-05 / SEC-01..04 — host credentials never reach a plugin child.

The three process paths a plugin can cause — an MCP stdio server, a user hook
and a shell command — receive the same scrubbed environment. Loader and shell
basics survive; credential-shaped names, key files and the engine key do not.
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _boundary(monkeypatch):
    """The subject is the scrubbed environment; bind a passthrough wrapper so
    the spawn happens on every host."""
    from core.tools import mcp_process

    monkeypatch.setattr(mcp_process.mcp_sandbox, "platform_boundary", lambda: "seatbelt")
    monkeypatch.setattr(
        mcp_process.mcp_sandbox, "wrap",
        lambda command, args, home: [command, *args],
    )
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SECRETS = {
    "OPENAI_API_KEY": "sk-secret-openai",
    "EPHE_OPENAI_COMPAT_API_KEY": "sk-secret-engine",
    "GITHUB_TOKEN": "ghp_secret_github",
    "AWS_SECRET_ACCESS_KEY": "aws-secret",
    "MY_SERVICE_PASSWORD": "hunter2",
    "SOME_CREDENTIAL": "credential-value",
    "KUBECONFIG": "/home/user/.kube/config",
    "GH_PAT": "ghp_secret_pat",
    "OPENAI_KEY": "sk-secret-key",
    "ANTHROPIC_AUTH": "anthropic-secret",
    "STRIPE_KEY": "sk_live_secret",
    "DATABASE_URL": "postgres://user:password@db.example/app",
    "MY_PRIVATE_NOTE": "not-credential-shaped",
}

BASE = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LANG": os.environ.get("LANG", "en_US.UTF-8"),
}
# Dynamic-loader variables are code-loading channels and are not inherited.


def _assert_child_path(child_path: str) -> None:
    """QD-015 Y: the child keeps every inherited entry; macOS tool heads lead."""
    inherited = [p for p in BASE["PATH"].split(os.pathsep) if p]
    child = [p for p in child_path.split(os.pathsep) if p]
    assert set(inherited) <= set(child), "an inherited PATH entry was dropped"
    assert len(child) == len(set(child)), "a PATH entry is duplicated"
    if sys.platform == "darwin" and os.path.isdir("/opt/homebrew/bin"):
        assert child[0] == "/opt/homebrew/bin"
# Dynamic-loader variables are code-loading channels and are not inherited.


@pytest.fixture()
def secrets_env(monkeypatch):
    for name, value in {**SECRETS, **BASE}.items():
        monkeypatch.setenv(name, value)


def test_the_child_environment_keeps_basics_and_drops_credentials(secrets_env) -> None:
    from core.secret_broker import child_env

    env = child_env()
    for name in SECRETS:
        assert name not in env, name
    for name in BASE:
        if name != "PATH":
            assert env[name] == BASE[name], name
    _assert_child_path(env["PATH"])
    assert env.get("TOKENIZERS_PARALLELISM") is None


def test_an_unlisted_name_does_not_reach_the_child(monkeypatch) -> None:
    """The boundary is an allowlist, not a spelling guess."""
    from core.secret_broker import child_env

    monkeypatch.setenv("EPHE_UNLISTED_VALUE", "should-not-travel")
    assert "EPHE_UNLISTED_VALUE" not in child_env()


@pytest.mark.asyncio
async def test_mcp_stdio_does_not_inherit_host_secrets(secrets_env) -> None:
    from core.tools.mcp_process import StdioLink

    script = (
        "import json, os;"
        "print(json.dumps({'jsonrpc':'2.0','id':1,'result':{'env':"
        "{k: os.environ.get(k) for k in ('OPENAI_API_KEY','GITHUB_TOKEN','PATH','HOME')}}}))"
    )
    link = StdioLink(sys.executable, ["-c", script], timeout=5)
    try:
        response = await link.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    finally:
        await link.reap()
    seen = response["result"]["env"]
    assert seen["OPENAI_API_KEY"] is None
    assert seen["GITHUB_TOKEN"] is None
    _assert_child_path(seen["PATH"])
    assert seen["HOME"] != BASE["HOME"], "the child must not inherit the user's HOME"
    assert "mcp" in seen["HOME"] and "homes" in seen["HOME"]


def test_user_hook_does_not_inherit_host_secrets(secrets_env) -> None:
    from core.user_hooks import _run_command

    script = (
        "import json, os;"
        "print(json.dumps({'env': {k: os.environ.get(k) for k in "
        "('OPENAI_API_KEY','GITHUB_TOKEN','PATH','LD_LIBRARY_PATH')}}))"
    )
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
    result = _run_command({"command": command}, {})
    assert result is not None
    seen = result["env"]
    assert seen["OPENAI_API_KEY"] is None
    assert seen["GITHUB_TOKEN"] is None
    _assert_child_path(seen["PATH"])


def test_shell_child_does_not_inherit_host_secrets(secrets_env) -> None:
    from core.tools._shell_proc import _exec_sync

    script = (
        "import json, os;"
        "print(json.dumps({k: os.environ.get(k) for k in "
        "('OPENAI_API_KEY','GITHUB_TOKEN','PATH','HOME')}))"
    )
    proc = _exec_sync([sys.executable, "-c", script], None, False)
    assert proc.returncode == 0, proc.stderr
    seen = json.loads(proc.stdout)
    assert seen["OPENAI_API_KEY"] is None
    assert seen["GITHUB_TOKEN"] is None
    _assert_child_path(seen["PATH"])
    assert seen["HOME"] == BASE["HOME"]
    assert "sk-secret" not in proc.stdout
    assert "ghp_secret" not in proc.stdout


def test_the_ssh_agent_is_not_inherited_by_a_child(monkeypatch):
    """SC-02: a child that never asked for the agent cannot sign with the user's keys."""
    from core.secret_broker import child_env

    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")
    monkeypatch.setenv("SSH_AGENT_PID", "4242")
    assert "SSH_AUTH_SOCK" not in child_env()
    assert "SSH_AGENT_PID" not in child_env()


def test_an_owning_connector_may_name_the_agent_explicitly(monkeypatch):
    from core.secret_broker import child_env

    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")
    assert child_env({"SSH_AUTH_SOCK": "/tmp/agent.sock"})["SSH_AUTH_SOCK"] == "/tmp/agent.sock"
