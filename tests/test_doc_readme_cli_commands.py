"""The CLI reference is the documentation a user reads for every command, and every
command it shows is a promise: typing `ephe <cmd>` must reach a real subparser, not an
argparse usage error. The README links this reference; the landing page carries the
first install path, the reference carries the command set.

This gate reads docs/CLI.md, extracts the commands it documents from its fenced blocks
and inline code spans (so prose that merely contains the word "ephe" is not mistaken
for a command), builds the real parser with `ephe_cli.build_parser()` and asserts each
documented command resolves — at the top level and, for the pipe-separated action
lists like `ephe session list|new|…`, one level below the parent command.

Given / When / Then, strictly.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import ephe_cli

REPO = Path(__file__).resolve().parent.parent
README = REPO / "README.md"
CLI_DOC = REPO / "docs" / "CLI.md"

# The lifecycle commands a real README cannot be missing. These guard the extractor:
# if the patterns below silently match nothing, this floor fails rather than passing
# an empty set.
CORE_LIFECYCLE = {"start", "configure", "doctor", "update", "tui", "serve"}


def _documented_code(readme: str) -> str:
    """The CLI reference's fenced code blocks and inline code spans joined into one blob.

    Command examples live in code; a prose mention of "ephe" must not be mistaken for
    a subcommand, so only the code regions are offered to the extractor.
    """
    fenced = re.findall(r"```[a-zA-Z0-9_-]*\n(.*?)```", readme, re.DOTALL)
    inline = re.findall(r"`([^`\n]+)`", readme)
    return "\n".join((*fenced, *inline))


def _documented_commands(code: str) -> set[str]:
    """Top-level command names the README invokes as `ephe <name>`."""
    return set(re.findall(r"\bephe\s+([a-z][a-z0-9-]+)", code))


def _documented_action_lists(code: str) -> dict[str, list[str]]:
    """`ephe <parent> a|b|c` forms, as {parent: [a, b, c]}.

    The README writes multi-action commands inline (`ephe session list|new|…`,
    `ephe plugin list | enable | …`); each action is a command in its own right.
    """
    found = re.findall(
        r"\bephe\s+([a-z][a-z0-9-]*)\s+([a-z][a-z0-9-]*(?:\s*\|\s*[a-z][a-z0-9-]*)+)",
        code,
    )
    return {parent: [a.strip() for a in actions.split("|")] for parent, actions in found}


def _parser() -> argparse.ArgumentParser:
    return ephe_cli.build_parser()


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return {}


def _child_names(parser: argparse.ArgumentParser) -> set[str]:
    """The tokens a parser accepts as its first positional: subcommands plus any
    positional whose values are constrained by `choices` (e.g. `session`'s action)."""
    names: set[str] = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            names.update(action.choices.keys())
        elif action.choices is not None and not action.option_strings:
            names.update(str(choice) for choice in action.choices)
    return names


def test_given_readme_when_scanned_then_it_documents_the_core_lifecycle_commands():
    code = _documented_code(CLI_DOC.read_text(encoding="utf-8"))
    documented = _documented_commands(code)

    assert "docs/CLI.md" in README.read_text(encoding="utf-8"), "the README does not link the CLI reference"
    assert CORE_LIFECYCLE <= documented, (
        "the CLI reference no longer documents the core commands "
        f"{sorted(CORE_LIFECYCLE - documented)}; the extractor or the README is broken"
    )


def test_given_readme_commands_when_resolved_then_every_command_exists_in_the_cli():
    code = _documented_code(CLI_DOC.read_text(encoding="utf-8"))
    documented = _documented_commands(code)
    # The reference also documents the bare `ephe` entry point.
    documented.discard("ephe")
    real = _child_names(_parser())

    missing = sorted(documented - real)

    assert missing == [], (
        f"docs/CLI.md documents commands the CLI does not have: {missing}. "
        "Add the subparser in ephe_cli.build_parser() or fix the README."
    )


def test_given_readme_action_lists_when_resolved_then_each_action_exists_under_its_parent():
    code = _documented_code(CLI_DOC.read_text(encoding="utf-8"))
    action_lists = _documented_action_lists(code)
    parser = _parser()

    assert action_lists, "no `ephe <cmd> a|b|c` action lists found in docs/CLI.md"

    problems: list[str] = []
    for parent, actions in action_lists.items():
        parent_parser = _subparsers(parser).get(parent)
        if parent_parser is None:
            problems.append(f"{parent}: parent command not in the CLI")
            continue
        children = _child_names(parent_parser)
        for action in actions:
            if action not in children:
                problems.append(f"{parent} {action}: not a command of `{parent}`")

    assert problems == [], "README documents actions the CLI does not have: " + "; ".join(problems)
