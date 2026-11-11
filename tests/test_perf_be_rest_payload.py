"""PERF-BE-REST: the prompt payload is sized by what the round needs.

Two blocks dominated a no-skill turn: the compact skill index (~7.9 KB) in the
system prompt and the browser/vision/clipboard schemas inside the 43-tool base
array (~7.6 KB). The index is a fallback for a near miss, not for a greeting; the
three families ship when the message asks for them. Both cuts keep the stable
prompt prefix untouched and the omitted tools reachable through the discovery
meta tools.
"""
from __future__ import annotations

import json

import pytest

from core.skill_router import SkillRoute
from server.routes import chat as chat_mod


def _names(messages: list, allowed_tool_names: list[str] | None = None) -> set[str]:
    from core.chat_context import _tools_for_messages

    return {
        entry["function"]["name"]
        for entry in _tools_for_messages(messages, allowed_tool_names=allowed_tool_names)
    }


# The skill index

def test_a_message_no_skill_shares_a_term_with_gets_no_index():
    out = chat_mod._compose_extra_system(
        None, ask_mode=False, message="zzz qqq xyzzy plugh quux"
    )
    assert not (out and "## Skill-Index" in out), out


def test_a_near_miss_keeps_the_index():
    route = SkillRoute(None, None, 0.75)
    out = chat_mod._compose_extra_system(
        None, ask_mode=False, route=route, message="summarize the quarterly numbers"
    )
    assert "## Skill-Index" in (out or "")


def test_a_route_hit_that_reaches_the_fallback_still_keeps_the_index():
    """The REST route passes no skill prompt, so it keeps the catalog as before."""
    route = SkillRoute(object(), None, 4.0)
    out = chat_mod._compose_extra_system(
        None, ask_mode=False, route=route, message="write a test"
    )
    assert "## Skill-Index" in (out or "")


def test_the_stream_route_is_not_routed_twice(monkeypatch):
    calls: list[str] = []

    def _route(_self, message: str) -> SkillRoute:
        calls.append(message)
        return SkillRoute(None, None, 0.0)

    monkeypatch.setattr(chat_mod.SkillLoader, "route_for_message", _route)
    skill, content, route = chat_mod._resolve_skill_invocation("zzz qqq xyzzy")
    out = chat_mod._compose_extra_system(
        skill, ask_mode=False, route=route, message=content
    )
    assert calls == ["zzz qqq xyzzy"], "the resolver routed the same message twice"
    assert not (out and "## Skill-Index" in out)


def test_ask_mode_and_a_skill_hit_still_send_no_index():
    assert "## Skill-Index" not in (
        chat_mod._compose_extra_system(None, ask_mode=True, message="write a test") or ""
    )


# The tool families

def test_a_plain_turn_carries_no_browser_vision_or_clipboard_schema():
    names = _names([{"role": "user", "content": "hello, how are you today?"}])
    assert "browser_go" not in names
    assert "take_screenshot" not in names
    assert "clipboard_read" not in names
    assert {"read_file", "run_shell", "tool_search", "ask_user"} <= names


def test_a_browser_turn_carries_the_browser_family():
    names = _names([{"role": "user", "content": "open the browser and click login"}])
    assert {"browser_go", "browser_click", "browser_exec"} <= names


def test_a_screenshot_turn_carries_the_vision_family():
    names = _names([{"role": "user", "content": "take a screenshot of my display"}])
    assert {"take_screenshot", "get_display_info"} <= names


def test_a_clipboard_turn_carries_the_clipboard_family():
    names = _names([{"role": "user", "content": "paste from my clipboard"}])
    assert {"clipboard_read", "clipboard_write"} <= names


def test_an_image_turn_carries_the_vision_family():
    names = _names([{"role": "user", "content": "what is this?", "images": ["abc"]}])
    assert "vision_click" in names


def test_a_follow_up_keeps_the_family_the_earlier_turn_used():
    messages = [
        {"role": "user", "content": "open example.org in the browser"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "function": {"name": "browser_go", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        {"role": "user", "content": "continue please"},
    ]
    assert "browser_go" in _names(messages)


def test_a_skill_whitelist_is_not_family_filtered():
    names = _names([{"role": "user", "content": "hello"}], ["browser_go", "read_file"])
    assert {"browser_go", "read_file"} <= names


def test_an_omitted_family_stays_reachable_through_tool_search():
    from core.tools.discovery import search

    _names([{"role": "user", "content": "hello there"}])
    out = search("screenshot")
    assert "take_screenshot" in out, out


def test_a_gated_session_names_the_omitted_families_on_a_dead_end_search():
    from core.tools.discovery import search

    _names([{"role": "user", "content": "hello there"}])
    out = search("qqzz wwyymm")
    assert "not in this session's array" in out
    assert "browser_go" in out


def test_the_gated_array_is_still_valid_json_with_full_schemas():
    from core.chat_context import _tools_for_messages

    tools = _tools_for_messages([{"role": "user", "content": "hello"}])
    payload = json.dumps(tools)
    assert "browser_go" not in payload
    for entry in tools:
        assert entry["function"]["parameters"]["type"] == "object"
