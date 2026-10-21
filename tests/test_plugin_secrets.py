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
}

BASE = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LANG": os.environ.get("LANG", "en_US.UTF-8"),
    "SSH_AUTH_SOCK": "/tmp/ssh-agent.sock",
}
if sys.platform == "darwin":
    BASE["DYLD_LIBRARY_PATH"] = "/opt/homebrew/lib"
else:
    BASE["LD_LIBRARY_PATH"] = "/usr/local/lib"


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
        assert env[name] == BASE[name], name
    assert env.get("TOKENIZERS_PARALLELISM") is None


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
    assert seen["PATH"] == BASE["PATH"]
    assert seen["HOME"] == BASE["HOME"]


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
    assert seen["PATH"] == BASE["PATH"]


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
    assert seen["PATH"] == BASE["PATH"]
    assert seen["HOME"] == BASE["HOME"]
    assert "sk-secret" not in proc.stdout
    assert "ghp_secret" not in proc.stdout
