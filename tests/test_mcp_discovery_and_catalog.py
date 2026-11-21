"""W3-40 — MCP tool discovery across catalogue pages, and the MCP-catalog freshness check.

Two halves, one seam each:

* **Discovery** — the MCP standard paginates ``tools/list`` through ``nextCursor``. A client that
  sends one request discovers only the first page and silently drops every tool behind the cursor, so
  ``list_tools`` follows the cursor to the end (bounded, deduped, and fault-tolerant mid-way).
* **Catalog** — ``scripts/catalog_freshness.py`` gains ``mcp_catalog_drift``: the curated
  ``core/mcp_catalog.py`` is hand-written data with no generator, so what it checks is the *shape* the
  page and the register depend on, plus the first-party license fence. No network call is made — a
  named server answering is the runtime probe's question (``POST /api/mcp/health``), never a CI gate.

Every function is exercised against a plant (``tmp_path``) or a faked transport; the repository's own
surface is only ever read.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.tools.mcp_client import (
    MAX_TOOL_PAGES,
    MCPClient,
    parse_server_spec,
)

ROOT = Path(__file__).resolve().parents[1]


# discovery


def _page(tools: list[dict], next_cursor: str | None = None) -> dict:
    result: dict = {"tools": tools}
    if next_cursor:
        result["nextCursor"] = next_cursor
    return {"jsonrpc": "2.0", "id": 1, "result": result}


def _client_with_pages(pages: list[dict], sent: list[dict]) -> MCPClient:
    """A real client whose HTTP transport answers with ``pages`` in order."""
    client = MCPClient("http://127.0.0.1:8844/mcp")
    remaining = list(pages)

    async def fake_post(endpoint, headers, body):
        sent.append(body)
        return remaining.pop(0) if remaining else _page([])

    client._post = fake_post
    return client


@pytest.mark.asyncio
async def test_tools_list_follows_the_cursor_across_pages():
    sent: list[dict] = []
    client = _client_with_pages(
        [_page([{"name": "alpha"}], next_cursor="p2"), _page([{"name": "beta"}])],
        sent,
    )
    tools = await client.list_tools()
    assert [t["name"] for t in tools] == ["alpha", "beta"]
    assert len(sent) == 2, "one request per page"


@pytest.mark.asyncio
async def test_tools_list_passes_the_cursor_back_in_the_params():
    sent: list[dict] = []
    client = _client_with_pages(
        [_page([{"name": "alpha"}], next_cursor="p2"), _page([{"name": "beta"}])],
        sent,
    )
    await client.list_tools()
    assert sent[0]["method"] == "tools/list" and sent[0]["params"] == {}
    assert sent[1]["params"] == {"cursor": "p2"}, "the second page carries the cursor"


@pytest.mark.asyncio
async def test_tools_list_stops_when_the_cursor_repeats():
    """A server that answers every page with the same cursor must not spin the loop forever."""
    calls = {"n": 0}

    client = MCPClient("http://127.0.0.1:8844/mcp")

    async def fake_post(endpoint, headers, body):
        calls["n"] += 1
        return _page([{"name": "alpha"}], next_cursor="same")

    client._post = fake_post
    tools = await client.list_tools()
    assert calls["n"] == 2, "the first repeat cursor ends the walk"
    assert [t["name"] for t in tools] == ["alpha"]


@pytest.mark.asyncio
async def test_tools_list_is_bounded_by_max_tool_pages():
    """A server that never stops handing out a fresh cursor is cut off at the ceiling."""
    calls = {"n": 0}

    client = MCPClient("http://127.0.0.1:8844/mcp")

    async def fake_post(endpoint, headers, body):
        calls["n"] += 1
        return _page([{"name": f"t{calls['n']}"}], next_cursor=f"c{calls['n']}")

    client._post = fake_post
    tools = await client.list_tools()
    assert calls["n"] == MAX_TOOL_PAGES
    assert len(tools) == MAX_TOOL_PAGES


@pytest.mark.asyncio
async def test_tools_list_dedupes_a_name_repeated_across_pages():
    sent: list[dict] = []
    client = _client_with_pages(
        [_page([{"name": "alpha"}], next_cursor="p2"), _page([{"name": "alpha"}, {"name": "beta"}])],
        sent,
    )
    tools = await client.list_tools()
    assert [t["name"] for t in tools] == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_tools_list_keeps_earlier_pages_when_a_later_page_fails():
    """Dropping the pages already read is worse than a short list; ``last_error`` records the miss."""
    client = MCPClient("http://127.0.0.1:8844/mcp")
    calls = {"n": 0}

    async def fake_post(endpoint, headers, body):
        calls["n"] += 1
        if calls["n"] == 1:
            return _page([{"name": "alpha"}], next_cursor="p2")
        raise RuntimeError("connection reset")

    client._post = fake_post
    tools = await client.list_tools()
    assert [t["name"] for t in tools] == ["alpha"]
    assert "connection reset" in client.last_error


@pytest.mark.asyncio
async def test_tools_list_reports_the_error_when_the_first_page_fails():
    client = MCPClient("http://127.0.0.1:8844/mcp")

    async def fake_post(endpoint, headers, body):
        raise RuntimeError("no route")

    client._post = fake_post
    tools = await client.list_tools()
    assert len(tools) == 1 and "error" in tools[0]
    assert "no route" in tools[0]["error"]


def test_build_tools_list_without_a_cursor_keeps_empty_params():
    """Backward compatibility: the first page is the same request it always was."""
    client = MCPClient("http://127.0.0.1:8844/mcp")
    payload = client._build_tools_list(7)
    assert payload["params"] == {}


def test_parse_tools_cursor_reads_the_next_cursor():
    client = MCPClient("http://127.0.0.1:8844/mcp")
    assert client._parse_tools_cursor(_page([], next_cursor="abc")) == "abc"
    assert client._parse_tools_cursor(_page([])) is None
    assert client._parse_tools_cursor({"error": {"code": -1, "message": "x"}}) is None


def test_sync_registers_every_page(monkeypatch):
    """The seam: a paginated discovery reaches the registry as the full tool set."""
    import core.tools.mcp_client as mcp_module

    real_client = mcp_module.MCPClient

    def factory(**kwargs):
        client = real_client(**kwargs)

        async def fake_post(endpoint, headers, body):
            cursor = body["params"].get("cursor")
            if not cursor:
                return _page([{"name": "alpha"}], next_cursor="p2")
            return _page([{"name": "beta"}])

        client._post = fake_post
        return client

    monkeypatch.setattr(mcp_module, "MCPClient", factory)
    monkeypatch.setattr(mcp_module, "_LIVE_CLIENTS", {})
    try:
        registered = asyncio.run(mcp_module.sync_mcp_tools([parse_server_spec("http://127.0.0.1:9/mcp")]))
        assert registered == ["mcp_alpha", "mcp_beta"]
    finally:
        mcp_module.unregister_mcp_tools()


# catalogue check


def load_catalog_module():
    spec = importlib.util.spec_from_file_location(
        "catalog_freshness", ROOT / "scripts" / "catalog_freshness.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _entry(**over):
    base = {
        "id": "mcp-x", "name": "X", "description": "Deutsche Beschreibung",
        "description_en": "English description", "category": "utility",
        "install_hint": "uvx mcp-server-x (stdio)", "docs": "https://example.com/x",
    }
    base.update(over)
    return base


def _fence():
    return _entry(
        id="mcp-ephemora-cell", name="Ephemora Cell Server",
        description="Der Käfig: >=1.0.4.3,<1.0.5 (1.0.5 ist BUSL-1.1)",
        description_en="The cage, same license fence as Ephe", category="sandbox",
        install_hint='uvx --from "ephemora-cell>=1.0.4.3,<1.0.5" ephemora-cell-mcp (stdio)',
        docs="https://pypi.org/project/ephemora-cell/")


def plant_catalog(root: Path, entries: list[dict]) -> Path:
    """A ``core/mcp_catalog.py`` built from ``entries`` — the module loads by path, so a plant suffices."""
    core = root / "core"
    core.mkdir(parents=True, exist_ok=True)
    (core / "mcp_catalog.py").write_text(
        "CATALOG = " + json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return root


class TestMcpCatalogDrift:
    def test_the_committed_catalog_satisfies_its_contract(self):
        module = load_catalog_module()
        assert module.mcp_catalog_drift(ROOT) == []

    def test_the_mcp_catalog_leg_is_gated(self):
        module = load_catalog_module()
        assert "core/mcp_catalog.py" in module.GATED

    def test_a_well_formed_plant_is_clean(self, tmp_path):
        plant_catalog(tmp_path, [_entry(), _fence()])
        assert load_catalog_module().mcp_catalog_drift(tmp_path) == []

    def test_a_duplicate_id_is_a_finding(self, tmp_path):
        plant_catalog(tmp_path, [_entry(id="mcp-x"), _entry(id="mcp-x"), _fence()])
        problems = load_catalog_module().mcp_catalog_drift(tmp_path)
        assert any("declared twice" in p for p in problems), problems

    def test_an_entry_without_english_is_a_finding(self, tmp_path):
        plant_catalog(tmp_path, [_entry(description_en=""), _fence()])
        problems = load_catalog_module().mcp_catalog_drift(tmp_path)
        assert any("mcp-x: no description_en" in p for p in problems), problems

    def test_a_copied_english_is_a_finding(self, tmp_path):
        plant_catalog(tmp_path, [_entry(description_en="Deutsche Beschreibung"), _fence()])
        problems = load_catalog_module().mcp_catalog_drift(tmp_path)
        assert any("copy of description" in p for p in problems), problems

    def test_a_non_https_docs_link_is_a_finding(self, tmp_path):
        plant_catalog(tmp_path, [_entry(docs="http://example.com/x"), _fence()])
        problems = load_catalog_module().mcp_catalog_drift(tmp_path)
        assert any("not https" in p for p in problems), problems

    def test_an_entry_with_neither_spec_nor_install_hint_is_a_finding(self, tmp_path):
        plant_catalog(tmp_path, [_entry(install_hint=""), _fence()])
        problems = load_catalog_module().mcp_catalog_drift(tmp_path)
        assert any("neither a registerable spec nor an install_hint" in p for p in problems), problems

    def test_a_registerable_spec_passes_and_a_broken_one_is_a_finding(self, tmp_path):
        module = load_catalog_module()
        good = _entry(id="mcp-a", spec="stdio:npx -y pkg", install_hint="")
        plant_catalog(tmp_path, [good, _fence()])
        assert module.mcp_catalog_drift(tmp_path) == []
        broken = _entry(id="mcp-a", spec="ftp://nope", install_hint="")
        plant_catalog(tmp_path, [broken, _fence()])
        problems = module.mcp_catalog_drift(tmp_path)
        assert any("PUT contract" in p for p in problems), problems

    def test_a_lost_license_fence_is_a_finding(self, tmp_path):
        module = load_catalog_module()
        plant_catalog(tmp_path, [_entry()])  # no mcp-ephemora-cell at all
        assert any("license fence" in p for p in module.mcp_catalog_drift(tmp_path))
        drifted = _fence()
        drifted["description"] = "no fence here"
        drifted["description_en"] = "no fence here either"
        drifted["install_hint"] = "uvx ephemora-cell-mcp (stdio)"
        plant_catalog(tmp_path, [_entry(), drifted])
        problems = module.mcp_catalog_drift(tmp_path)
        assert any("license fence token" in p for p in problems), problems


class TestCatalogLegReportsTheMcpSurface:
    def test_the_script_prints_the_mcp_surface_and_stays_green(self):
        done = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "catalog_freshness.py")],
            text=True, capture_output=True, check=False, cwd=ROOT,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "core/mcp_catalog.py: fresh" in done.stdout, done.stdout
        assert "mcp-catalog finding(s)" in done.stdout, done.stdout

    def test_a_planted_break_turns_the_leg_red(self, tmp_path):
        """A plant that breaks the contract must fail the run, not only print — the gate is real."""
        plant_catalog(tmp_path, [{"id": "mcp-x"}])  # every required key missing, no fence
        (tmp_path / "knowledge").mkdir()
        done = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "catalog_freshness.py"), "--root", str(tmp_path)],
            text=True, capture_output=True, check=False, cwd=ROOT,
        )
        assert done.returncode == 1, done.stdout + done.stderr
        assert "core/mcp_catalog.py: mcp-x" in done.stdout, done.stdout
        assert "FAIL core/mcp_catalog.py" in done.stdout, done.stdout
