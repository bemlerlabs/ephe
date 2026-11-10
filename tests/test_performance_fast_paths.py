from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_tool_calling import _make_ollama_response


@pytest.fixture(autouse=True)
def _hermetic_home(tmp_path, monkeypatch):
    """Pin HOME: a chat turn records its episode under the workspace, and the neutral
    workspace is ``~/Ephe`` (ticket #153)."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def test_given_warm_schema_cache_when_tool_schemas_are_read_then_only_the_gate_reruns(monkeypatch):
    """
    GIVEN the schema array is assembled once per TTL window while the plugin gate is a
        cheap post-filter that runs OUTSIDE that cache (core/tools/registry.py:
        _all_tool_schemas builds and caches, _apply_plugin_filter gates on every call)
    WHEN get_tool_schemas() is read repeatedly inside one window
    THEN the assembly runs exactly once — the catalogue is walked a single time and the
        cached array stays the same object — while the gate runs on every read, and only
        an expired window buys a second assembly.

    The shape this replaced pinned `first is second` on the returned list. That identity
    cannot hold by design: the plugin gate reads mutable per-plugin state, so it answers
    outside the cache and hands out a copy. The cost worth protecting is the assembly,
    never the copy.
    """
    import core.plugin_runtime as plugin_runtime
    import core.tools.registry as registry
    from core.tools import get_tool_schemas

    builds: list[str] = []
    gates: list[str] = []
    real_catalogue = registry.get_mcp_tools
    real_gate = plugin_runtime.filter_schemas

    def counted_catalogue():
        builds.append("catalogue")  # reached only on the cache-miss path
        return real_catalogue()

    def counted_gate(schemas, path=None):
        gates.append("gate")  # reached on every read, cache hit included
        return real_gate(schemas, path)

    monkeypatch.setattr(registry, "_TOOL_SCHEMA_CACHE", None)
    # The window is pinned wide, so the build count measures the cache and not the
    # clock of whatever machine runs the suite.
    monkeypatch.setattr(registry, "TOOL_SCHEMA_CACHE_TTL_SECONDS", 3600.0)
    monkeypatch.setattr(registry, "get_mcp_tools", counted_catalogue)
    monkeypatch.setattr(plugin_runtime, "filter_schemas", counted_gate)

    calls = 5
    views: list[list[dict]] = []
    cached: list[list[dict]] = []
    for _ in range(calls):
        views.append(get_tool_schemas())
        cached.append(registry._TOOL_SCHEMA_CACHE[1])

    assert len(builds) == 1, f"the array was assembled {len(builds)} times in one window"
    assert len(gates) == calls, "the plugin gate stopped running on the cache-hit path"
    assert all(entry is cached[0] for entry in cached), "the cached array was rebuilt"
    assert all(view == views[0] for view in views[1:]), "one window served two views"

    # The copy is what protects the cache: a caller editing the list it was handed
    # cannot move the array the next read is built from.
    built = cached[0]
    built_width = len(built)
    views[0].append({"type": "function", "function": {"name": "caller_mutation_probe"}})
    assert len(built) == built_width, (
        "a caller mutated the cached array through the view it was handed"
    )

    # The build counter is live rather than patched away: an expired window does
    # rebuild, so the single assembly above is the cache doing its job.
    monkeypatch.setattr(registry, "TOOL_SCHEMA_CACHE_TTL_SECONDS", 0.0)
    get_tool_schemas()
    assert len(builds) == 2, "the build probe never saw a rebuild — it pins nothing"


def test_given_skill_loader_when_load_all_called_twice_then_second_call_uses_cache(tmp_path):
    """
    GIVEN skills have already been loaded
    WHEN load_all is called again within 60 seconds
    THEN markdown files are not read again.
    """
    skills_dir = tmp_path / "skills"
    builtin_dir = tmp_path / "builtin"
    skills_dir.mkdir()
    builtin_dir.mkdir()
    (builtin_dir / "help.md").write_text(
        "# help\n\n**Trigger**: /help\n**Description**: Hilfe\n**Tools**: \n\n## System Prompt\nHallo",
        encoding="utf-8",
    )

    from core.skills import SkillLoader

    loader = SkillLoader(skills_dir=skills_dir, builtin_dir=builtin_dir)
    first = loader.load_all()
    with patch("pathlib.Path.read_text", side_effect=AssertionError("cache miss")):
        second = loader.load_all()

    assert first[0].name == second[0].name == "help"


def test_given_discover_projects_when_called_twice_then_second_call_uses_cache(monkeypatch, tmp_path):
    """
    GIVEN project discovery already scanned a root
    WHEN the same query runs within 60 seconds
    THEN os.walk is not called again.
    """
    project = tmp_path / "Documents" / "ephe-cache"
    project.mkdir(parents=True)
    (project / ".git").mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='ephe-cache'\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))

    from core.project_discovery import discover_project_records

    first = discover_project_records(query="ephe", roots=[tmp_path / "Documents"])
    with patch("core.project_discovery.os.walk", side_effect=AssertionError("cache miss")):
        second = discover_project_records(query="ephe", roots=[tmp_path / "Documents"])

    assert first == second


@pytest.mark.asyncio
async def test_given_long_answer_when_streamed_then_no_per_word_sleep_is_used():
    """
    GIVEN the final answer is long
    WHEN chat_with_tools streams the words to the UI
    THEN it does not add artificial per-word delay.
    """
    from core.chat import chat_with_tools

    long_text = " ".join(f"wort{i}" for i in range(120))
    pure_text = _make_ollama_response(content=long_text, tool_calls=[])

    with patch("core.chat.ollama.AsyncClient") as MockClient, patch("core.chat.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        client = MagicMock()
        client.chat = AsyncMock(return_value=pure_text)
        MockClient.return_value = client

        result = await chat_with_tools(
            model="gemma4:12b",
            history=[{"role": "user", "content": "lange antwort"}],
            on_chunk=lambda c: None,
        )

    assert result == long_text
    mock_sleep.assert_not_awaited()
