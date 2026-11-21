"""
Tests for core/commands.py
"""

from __future__ import annotations

import pytest

from core.commands import (
    COMMANDS,
    get_command_help,
    get_completions,
    is_command,
    resolve_command,
)


# resolve_command – happy path


def test_resolve_post_command():
    result = resolve_command("/post AI productivity")
    assert "AI productivity" in result
    assert "LinkedIn" in result  # template content


def test_resolve_debug_command():
    result = resolve_command("/debug def foo(): pass")
    assert "def foo(): pass" in result
    assert "engineer" in result.lower()


def test_resolve_idea_command():
    result = resolve_command("/idea sustainable energy")
    assert "sustainable energy" in result


def test_resolve_explain_command():
    result = resolve_command("/explain async/await")
    assert "async/await" in result


def test_resolve_commit_command():
    result = resolve_command("/commit added auth module")
    assert "added auth module" in result


# resolve_command – edge cases


def test_unknown_command_is_passthrough():
    raw = "/unknowncmd foo bar"
    assert resolve_command(raw) == raw


def test_plain_text_is_passthrough():
    raw = "hello world"
    assert resolve_command(raw) == raw


def test_empty_string_is_passthrough():
    assert resolve_command("") == ""


def test_command_without_argument_gives_usage_hint():
    result = resolve_command("/post")
    # Should not crash and should give a helpful hint
    assert "/post" in result
    assert len(result) > 0


def test_command_without_argument_explain():
    result = resolve_command("/explain")
    assert "/explain" in result


def test_resolve_command_case_insensitive():
    result_lower = resolve_command("/post hello")
    result_upper = resolve_command("/POST hello")
    # Both should resolve the same way
    assert "hello" in result_lower
    assert "hello" in result_upper


def test_resolve_command_strips_whitespace():
    result = resolve_command("  /post  my topic  ")
    assert "my topic" in result


# get_completions


def test_completions_prefix_p():
    completions = get_completions("/p")
    assert "/post" in completions


def test_completions_exact_match():
    completions = get_completions("/post")
    assert "/post" in completions


def test_completions_slash_only():
    completions = get_completions("/")
    assert len(completions) == len(COMMANDS)


def test_completions_no_match():
    completions = get_completions("/zzz")
    assert completions == []


def test_completions_returns_list():
    assert isinstance(get_completions("/"), list)


# get_command_help


def test_command_help_returns_all():
    help_items = get_command_help()
    assert len(help_items) == len(COMMANDS)


def test_command_help_format():
    help_items = get_command_help()
    for cmd, desc in help_items:
        assert cmd.startswith("/")
        assert isinstance(desc, str)


# is_command


def test_is_command_true():
    assert is_command("/post hello") is True


def test_is_command_false_plain():
    assert is_command("hello world") is False


def test_is_command_false_unknown():
    assert is_command("/unknown") is False


def test_is_command_empty():
    assert is_command("") is False


# Commands dict integrity


def test_all_commands_have_template():
    for cmd, template in COMMANDS.items():
        assert isinstance(template, str)
        assert len(template) > 10, f"{cmd} template is too short"


def test_all_templates_have_input_placeholder_or_not():
    """Commands with {input} must resolve correctly; those without must not err."""
    for cmd, template in COMMANDS.items():
        result = resolve_command(f"{cmd} test input")
        assert isinstance(result, str)
        assert len(result) > 0
