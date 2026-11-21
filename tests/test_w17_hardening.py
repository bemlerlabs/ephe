"""
Ephe — W17 process & proxy hardening (audit catalogue P0-1, P0-2, P1-1..P1-3).

P0-1: shell exec runs in its own process group (start_new_session); on timeout
      the whole group is reaped via os.killpg — no zombie orphans.
P0-2: the REST/PWA mirror writes atomically (tmp + rename) — no .tmp leftovers,
      the last write wins, valid JSON.
P1-1: POST /api/shell/pty — PTY-backed execution (os.openpty) with
      stdin delivery and ANSI/CRLF preserved.
P1-3: GET /api/proxy/{port}/{full_path} — a narrow reverse proxy onto the
      loopback dev server for the preview panel.

Given / When / Then — strictly. Tests BEFORE implementation (WGT).
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess

import pytest
from fastapi.testclient import TestClient

import core.tools.shell_tools as shell_tools
from core.tools.base import ShellTimeoutError
from server.main import create_app

XHR_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def client():
    return TestClient(create_app())


# P0-1: process group reaping


class TestProcessGroupReaping:
    def test_exec_runs_in_new_process_group(self, tmp_path, monkeypatch):
        # Given: a Popen spy captures the configuration of the exec instance.
        captured: dict = {}
        real_popen = subprocess.Popen

        def spy(*args, **kwargs):
            inst = real_popen(*args, **kwargs)
            captured["kwargs"] = kwargs
            captured["pid"] = inst.pid
            return inst

        monkeypatch.setattr(subprocess, "Popen", spy)
        # When: a fast whitelisted command runs through the exec path.
        out = asyncio.run(shell_tools.execute_confirmed_shell("echo hallo-w17", True))
        # Then: a new process group (Py>=3.11: start_new_session; otherwise the
        # preexec os.setsid) — the foundation for the group reaping.
        assert "hallo-w17" in out
        kwargs = captured["kwargs"]
        new_group = kwargs.get("start_new_session") is True or kwargs.get(
            "preexec_fn"
        ) is os.setsid
        assert new_group, f"keine Prozessgruppe konfiguriert: {kwargs}"

    def test_timeout_kills_whole_group(self, tmp_path, monkeypatch):
        # Given: a hanger with a child process (script form; -c is blocked).
        script = tmp_path / "w17_hanger.py"
        script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        captured: dict = {}
        real_popen = subprocess.Popen

        def spy(*args, **kwargs):
            inst = real_popen(*args, **kwargs)
            captured["pid"] = inst.pid
            return inst

        monkeypatch.setattr(subprocess, "Popen", spy)
        import core.tools._shell_proc as _shell_proc
        monkeypatch.setattr(_shell_proc, "SHELL_TIMEOUT_SECONDS", 1)
        # When: the timeout fires after 1s → ShellTimeoutError.
        with pytest.raises(ShellTimeoutError):
            asyncio.run(shell_tools.execute_confirmed_shell(f"python3 {script}", True))
        # Then: the process group is gone — the leader pid no longer answers.
        pid = captured["pid"]
        assert pid
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


# P0-2: atomic REST-/PWA mirror


class TestRestMirrorAtomic:
    @pytest.fixture
    def ms(self, tmp_path, monkeypatch):
        import core.multi_session as ms

        root = tmp_path / "sessions"
        monkeypatch.setattr(ms, "SESSIONS_DIR", root)
        monkeypatch.setattr(ms, "REGISTRY_FILE", root / "registry.json")
        return ms

    def test_save_is_atomic_json_without_tmp_debris(self, ms):
        # Given/When: two messages persisted via save_messages.
        ms.save_messages("rest-w17", [
            {"role": "user", "content": "frage"},
            {"role": "assistant", "content": "antwort"},
        ])
        # Then: valid JSON + no .tmp_ leftovers in the session folder.
        f = ms.SESSIONS_DIR / "rest-w17.json"
        data = json.loads(f.read_text(encoding="utf-8"))
        assert [m["content"] for m in data] == ["frage", "antwort"]
        debris = [p.name for p in ms.SESSIONS_DIR.iterdir() if p.name.startswith(".tmp")]
        assert debris == []

    def test_sequential_saves_last_write_wins(self, ms):
        ms.save_messages("rest-w17", [{"role": "user", "content": "alt"}])
        ms.save_messages("rest-w17", [{"role": "user", "content": "neu"}])
        got = ms.load_messages("rest-w17")
        assert got[-1]["content"] == "neu"


# P1-1: PTY endpoint


class TestPtyRoute:
    def test_pty_requires_xhr_header(self, client):
        r = client.post("/api/shell/pty", json={"command": "echo x"})
        assert r.status_code == 403

    def test_pty_preserves_ansi_and_crlf(self, client):
        # Given: the PTY translates \n → \r\n (onlcr) — that sets it apart from
        # the PIPE path and proves the real PTY wiring (between the lines,
        # after the boundary newlines are stripped).
        r = client.post(
            "/api/shell/pty",
            json={"command": "echo hallo-pty; echo ende", "input": "", "approved": True},
            headers=XHR_HEADERS,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "hallo-pty" in data["output"]
        assert "\r\n" in data["output"]

    def test_pty_delivers_stdin_to_read(self, client, tmp_path):
        # Given: a script that reads one line off stdin.
        script = tmp_path / "w17_read.py"
        script.write_text(
            "n = input()\nprint('got ' + n.strip())\n", encoding="utf-8"
        )
        r = client.post(
            "/api/shell/pty",
            json={"command": f"python3 {script}", "input": "42\n", "approved": True},
            headers=XHR_HEADERS,
        )
        assert r.status_code == 200
        assert "got 42" in r.json()["output"]

    def test_pty_rejects_non_whitelisted(self, client):
        r = client.post(
            "/api/shell/pty",
            json={"command": "rm -rf /tmp/x", "input": "", "approved": True},
            headers=XHR_HEADERS,
        )
        assert r.status_code == 200
        assert r.json()["ok"] is False


# P1-3: reverse proxy route


class TestProxyRoute:
    @pytest.fixture
    def fake_http(self, monkeypatch):
        import httpx

        seen: dict = {}

        class _Resp:
            def __init__(self, status_code=200, text="<html>ok</html>"):
                self.status_code = status_code
                # I1-4: the proxy reads bytes (content) and caps them — so this
                # double mirrors httpx, not the old text path.
                self.content = text.encode()

            @property
            def text(self) -> str:
                return self.content.decode()

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, url):
                seen["url"] = url
                return _Resp()

        monkeypatch.setattr(httpx, "AsyncClient", _Client)
        return seen

    def test_proxy_forwards_to_loopback(self, client, fake_http):
        r = client.get("/api/proxy/5173/index.html")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["status"] == 200
        assert data["body"] == "<html>ok</html>"
        assert fake_http["url"] == "http://127.0.0.1:5173/index.html"

    def test_proxy_normalizes_root_path(self, client, fake_http):
        r = client.get("/api/proxy/3000/")
        assert r.status_code == 200
        assert fake_http["url"] == "http://127.0.0.1:3000/"

    def test_proxy_validates_port(self, client):
        for url in (
            "/api/proxy/abc/x",
            "/api/proxy/0/x",
            "/api/proxy/70000/x",
        ):
            r = client.get(url)
            assert r.status_code == 400, url

    def test_proxy_upstream_error_is_502(self, client, monkeypatch):
        import httpx

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, url):
                raise OSError("boom")

        monkeypatch.setattr(httpx, "AsyncClient", _Client)
        r = client.get("/api/proxy/5173/index.html")
        assert r.status_code == 502
