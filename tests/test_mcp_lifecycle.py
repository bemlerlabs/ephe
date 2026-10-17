"""I1-8: the MCP client keeps its child processes — and does not lie about them.

Four defects, four pins:

1. A dead stdio server was never restarted and never awaited: the client held on
   to a dead process (every later call hangs on closed pipes) and the child
   process stayed in the process table as a zombie. Now: ``returncode`` is seen,
   cleaned up (with ``wait``), and the restart follows an exponential backoff. The
   process side lives in ``core.tools.mcp_process``, the client stays the JSON-RPC
   side.
2. Backoff: a server with a missing binary was restarted on *every* tool call
   until then. Now there is a window that grows along (0.5 s to 30 s) and that the
   rejection itself names.
3. A JSON-RPC error was returned as ``(="", False)`` — a failure the agent took
   for an empty result. An error is an error.
4. ``sync_mcp_tools`` closed the stdio client right after ``tools/list``, even
   though the comment claimed the opposite: every tool call was a cold start
   without a session. Clients now live in the register and are cleaned up at
   server shutdown.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mcp_catalog import catalog_entries  # noqa: E402
from core.tools.mcp_client import (  # noqa: E402
    MCPClient,
    close_all_mcp_clients,
    parse_server_spec,
    sync_mcp_tools,
)
from core.tools.mcp_process import BACKOFF_MAX_SECONDS, StdioLink  # noqa: E402


class _Writer:
    def __init__(self):
        self.payload = b""

    def write(self, data):
        self.payload = data

    async def drain(self):
        return None


class _Reader:
    def __init__(self, lines: list[bytes], hang: bool = False):
        self._lines = list(lines)
        self._hang = hang

    async def readline(self):
        if self._hang:
            await asyncio.Event().wait()
        if not self._lines:
            return b""
        return self._lines.pop(0)


class _Proc:
    """asyncio subprocess in miniature: signals and waits become countable."""

    def __init__(self, lines: list[bytes] | None = None, returncode=None, hang: bool = False):
        self.stdin = _Writer()
        self.stdout = _Reader(lines or [], hang=hang)
        self.returncode = returncode
        self.signals: list[str] = []
        self.waited = 0

    def terminate(self):
        self.signals.append("terminate")

    def kill(self):
        self.signals.append("kill")

    async def wait(self):
        self.waited += 1
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


def _link(lines: list[bytes] | None = None, **kw) -> tuple[StdioLink, _Proc]:
    proc = _Proc(lines, **kw)
    link = StdioLink("fakeserver", timeout=0.05)
    link.proc = proc
    return link, proc


def _client_on(proc: _Proc) -> MCPClient:
    """A stdio client whose link holds exactly this process."""
    client = MCPClient("fakeserver", transport="stdio", timeout=0.05)
    client._link.proc = proc
    return client


def _spawner(procs: list[_Proc], calls: list[int]):
    async def fake_exec(*cmd, **kwargs):
        calls.append(list(cmd))
        return procs.pop(0)

    return fake_exec


_BODY = {"jsonrpc": "2.0", "id": 7, "method": "tools/list"}
_OK_LINE = [json.dumps({"jsonrpc": "2.0", "id": 7, "result": {"tools": []}}).encode()]


# 1. Cleanup and restart


@pytest.mark.asyncio
async def test_gestorbener_Prozess_wird_erkannt_und_sofort_neu_gestartet(monkeypatch):
    """A crash between two calls is not a crash loop: the restart is free."""
    dead = _Proc(returncode=1)
    calls: list[int] = []
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawner([_Proc(_OK_LINE)], calls))
    link = StdioLink("fakeserver", timeout=0.05)
    link.proc = dead

    resp = await link.send(_BODY)

    assert "result" in resp
    assert len(calls) == 1
    # returncode already set means: the child process was already reaped — no signal.
    assert dead.signals == [] and dead.waited == 0
    assert link.failures == 0


@pytest.mark.asyncio
async def test_Crash_Loop_zaehlt_die_Versuche_nicht_die_Erkennung():
    link, _ = _link(lines=[], returncode=1)
    assert link.backoff_seconds() == 0.0


@pytest.mark.asyncio
async def test_der_zweite_Fehlschlag_startt_nicht_mehr_und_sagt_es(monkeypatch):
    """Two failures: the second one does not even start — and says so."""
    calls: list[int] = []
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawner([_Proc([]), _Proc([])], calls))
    link = StdioLink("fakeserver", timeout=0.05)

    first = await link.send(_BODY)
    assert first["error"]["message"] == "stdio server closed"
    second = await link.send(_BODY)
    assert "restart deferred" in second["error"]["message"]
    assert len(calls) == 1, "der Backoff muss den Spawn zaehlen, nicht nur erwaehnen"


@pytest.mark.asyncio
async def test_backoff_verdoppelt_sich_und_kappt_bei_dreissig_Sekunden():
    link = StdioLink("fakeserver")
    delays = []
    for _ in range(9):
        link.note_failure()
        delays.append(round(link.backoff_seconds(), 3))
    assert delays[:4] == [0.5, 1.0, 2.0, 4.0]
    assert max(delays) == BACKOFF_MAX_SECONDS


@pytest.mark.asyncio
async def test_ein_gesunder_Call_macht_den_Backoff_wieder_auf():
    """The client is where success arrives — it has to calm the link down."""
    client = MCPClient("fakeserver", transport="stdio")
    client._link.note_failure()
    client._link.note_failure()
    assert client._link.backoff_seconds() > 0
    client.last_error = "alter Fehlschlag"
    client._extract_tool_result({"result": {"content": [{"type": "text", "text": "ok"}]}})
    assert client._link.backoff_seconds() == 0.0
    assert client._link.failures == 0 and client.last_error == ""


def test_der_stdio_Client_gibt_dem_Link_Befehl_Argumente_und_Timeout():
    client = MCPClient("npx", transport="stdio", args=["-y", "ein-server"], timeout=1.5)
    assert (client._link.command, client._link.args, client._link.timeout) == (
        "npx",
        ["-y", "ein-server"],
        1.5,
    )
    assert MCPClient("http://example.invalid/mcp")._link is None


@pytest.mark.asyncio
async def test_haengender_Server_wird_getoetet_nicht_nur_gemeldet():
    link, proc = _link(lines=[], hang=True)
    resp = await link.send(_BODY)
    assert resp["error"]["message"] == "stdio timeout"
    assert "terminate" in proc.signals
    assert link.proc is None


@pytest.mark.asyncio
async def test_die_Session_faellt_mit_dem_Prozess():
    client = _client_on(_Proc(lines=[]))
    client.session_id = "abc"
    await client.close()
    assert client.session_id is None
    assert client._link.proc is None


@pytest.mark.asyncio
async def test_close_wartet_auf_den_Exit_weil_ein_Zombie_ein_Leck_ist():
    proc = _Proc(lines=[])
    client = _client_on(proc)
    await client.close()
    assert proc.waited == 1


# 2. Errors are errors


def test_jsonrpc_Fehler_ist_kein_leerer_Erfolg():
    client = MCPClient("http://example.invalid/mcp")
    text, is_error = client._extract_tool_result(
        {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "boom"}}
    )
    assert is_error is True
    assert "boom" in text
    assert client.last_error == text


@pytest.mark.asyncio
async def test_call_tool_gibt_die_Fehlerursache_an_statt_schweigen(monkeypatch):
    client = MCPClient("http://example.invalid/mcp")

    async def fake_send(body):
        return {"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32601, "message": "no such tool"}}

    monkeypatch.setattr(client, "_send", fake_send)
    text, is_error = await client.call_tool("x", {})
    assert is_error is True and "no such tool" in text


@pytest.mark.asyncio
async def test_list_tools_nennt_den_Grund_und_nicht_nur_null_Tools(monkeypatch):
    client = MCPClient("http://example.invalid/mcp")

    async def fake_send(body):
        return {"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32002, "message": "unavailable"}}

    monkeypatch.setattr(client, "_send", fake_send)
    tools = await client.list_tools()
    assert tools and "unavailable" in tools[0]["error"]


# 3. Sync and register


class _Spy:
    instances: list["_Spy"] = []

    def __init__(self, endpoint, transport="http", label="", timeout=30.0, args=None):
        self.endpoint = endpoint
        self.transport = transport
        self.args = args
        self.closed = False
        self.listed = 0
        _Spy.instances.append(self)

    async def list_tools(self):
        self.listed += 1
        return []

    async def close(self):
        self.closed = True


def test_stdio_Server_bleibt_nach_dem_Listen_leben_und_wiederverwendet(monkeypatch):
    import core.tools.mcp_client as mcp_module

    _Spy.instances = []
    monkeypatch.setattr(mcp_module, "MCPClient", _Spy)
    spec = parse_server_spec("stdio:npx -y ein-server")
    asyncio.run(sync_mcp_tools([spec]))
    asyncio.run(sync_mcp_tools([spec]))

    assert len(_Spy.instances) == 1, "zwei Syncs, ein Prozess"
    assert _Spy.instances[0].listed == 2
    assert _Spy.instances[0].closed is False


def test_Spec_ausser_der_Konfiguration_wird_geschlossen(monkeypatch):
    import core.tools.mcp_client as mcp_module

    _Spy.instances = []
    monkeypatch.setattr(mcp_module, "MCPClient", _Spy)
    first = parse_server_spec("stdio:npx -y erster")
    second = parse_server_spec("stdio:npx -y zweiter")
    asyncio.run(sync_mcp_tools([first]))
    asyncio.run(sync_mcp_tools([second]))

    alive = _Spy.instances[-1]
    gone = _Spy.instances[0]
    assert gone.closed is True and alive.closed is False


def test_Shutdown_schliesst_jeden_lebenden_Client(monkeypatch):
    import core.tools.mcp_client as mcp_module

    _Spy.instances = []
    monkeypatch.setattr(mcp_module, "MCPClient", _Spy)
    asyncio.run(sync_mcp_tools([parse_server_spec("stdio:npx -y erster")]))
    assert len(mcp_module._LIVE_CLIENTS) == 1

    asyncio.run(close_all_mcp_clients())

    assert mcp_module._LIVE_CLIENTS == {}
    assert _Spy.instances[0].closed is True


def test_der_Server_Shutdown_ruft_den_Hook(monkeypatch, tmp_path):
    """The hook is the only place that keeps an MCP process from outliving the
    parent — which is why the mounting itself is checked, not only the
    function."""
    from fastapi.testclient import TestClient

    import core.tools.mcp_client as mcp_module
    from server.main import create_app

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("EPHE_MCP_SERVERS", raising=False)
    calls: list[str] = []

    async def spy():
        calls.append("closed")

    monkeypatch.setattr(mcp_module, "close_all_mcp_clients", spy)
    with TestClient(create_app()):
        pass

    assert calls == ["closed"]


# 4. License boundary in the catalog


def test_Katalog_weiss_von_der_eigenen_Cell_und_ihrer_Lizenzgrenze():
    entries = {e["id"]: e for e in catalog_entries()}
    assert "mcp-ephemora-cell" in entries, "die eigene Sandbox fehlt im Startkatalog"
    entry = entries["mcp-ephemora-cell"]
    assert {"id", "name", "description", "category"} <= set(entry)
    assert "1.0.4.3" in entry["description"] and "BUSL" in entry["description"]
    assert "ephemora-cell-mcp" in entry["install_hint"]


def test_Katalog_spricht_beide_Sprachen():
    """I7-4: the catalog texts are backend goods, but the surface is bilingual.

    An entry that describes only in German shows German sentences in the English
    interface — the same leak the register fields close via their bilingual
    option labels.
    """
    for entry in catalog_entries():
        de = entry.get("description") or ""
        en = entry.get("description_en") or ""
        assert de.strip(), f"{entry['id']} ohne deutsche description"
        assert en.strip(), f"{entry['id']} ohne englische description_en"
        assert en != de, f"{entry['id']} traegt deutschen Text in description_en"
        assert 20 <= len(en) <= 400, f"{entry['id']}: description_en ausserhalb 20-400"
