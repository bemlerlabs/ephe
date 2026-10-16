from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_tool_calling import _make_ollama_response


def test_given_tool_schemas_when_called_twice_then_same_cached_object_is_reused():
    """
    GIVEN tool schemas are static for the process
    WHEN get_tool_schemas is called repeatedly inside the TTL
    THEN it reuses the cached schema object.
    """
    from core.tools import get_tool_schemas

    first = get_tool_schemas()
    second = get_tool_schemas()

    assert first is second


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
