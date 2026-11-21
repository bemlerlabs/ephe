"""fetch_url is bound to the active engine only in the sense that it uses none.

A direct client inside a tool is the same class of defect as a silent engine
default, one layer down: the call cannot see the user's choice. The runtime test
plants a client that raises on construction; the source test fails if a future
edit re-introduces one anywhere in the module.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import sys
import types

from core.tools import fetch_tools


def test_fetch_succeeds_without_constructing_a_local_client(monkeypatch):
    constructed: list[str] = []

    class Boom:
        def __init__(self, *args, **kwargs):
            constructed.append("constructed")
            raise AssertionError("fetch_url must not construct a local client")

    fake = types.ModuleType("ollama")
    fake.AsyncClient = Boom
    monkeypatch.setitem(sys.modules, "ollama", fake)

    async def fake_get(url):
        return 200, "<p>Der Text.</p>"

    monkeypatch.setattr(fetch_tools, "_http_get", fake_get)
    fetch_tools._FETCH_CACHE.clear()

    out = asyncio.run(fetch_tools.fetch_url("https://example.test/page", "summarize"))

    assert "Der Text." in out
    assert constructed == []


def test_module_source_names_no_model_client():
    source = pathlib.Path(fetch_tools.__file__).read_text(encoding="utf-8")

    assert not re.search(r"\bAsyncClient\b", source)
    assert not re.search(r"^\s*(?:import|from)\s+ollama\b", source, re.MULTILINE)
    assert "_chat_once" not in source
