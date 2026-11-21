"""Every `ephe <command>` the documentation shows is a promise the parser keeps.

`docs/SANDBOX_EXECUTION.md` told a reader to run `ephe chat` after registering an MCP
server; the CLI has no `chat` verb, so the documented first step of that path exited 2
before anything was mounted. The same class of error hides in any prose block that names
a verb somebody remembered rather than read, so this gate checks the whole `docs/` tree
instead of the one line: each `ephe <word>` in a fenced block or an inline code span must
resolve to a real subcommand of `ephe_cli.build_parser()`.

Prose is not code: a sentence that happens to contain the product name is not a command,
so only code regions are read. Placeholders (`ephe <title>`, `ephe run "<task>"`,
`ephe start --open`) carry no command word and are skipped by the extractor; the one verb
the docs name as future work is allowlisted by name, with the file that says so.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import ephe_cli

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"

#: A command word: lowercase start, then letters/digits/dashes. `ephe <title>` and
#: `ephe run "<task>"` never match because the next token is not a bare word.
_COMMAND = re.compile(r"(?:^|[\s$])ephe\s+([a-z][a-z0-9-]*)")
_FENCE = re.compile(r"```[a-zA-Z0-9_-]*\n(.*?)```", re.DOTALL)

#: Verbs the docs name as *not shipped*. PERSONA_PACKS.md:84 says an `ephe persona
#: export|import` verb "are the obvious next step" — the sentence is a roadmap, not an
#: instruction, so the extractor must not read it as a command a user can run.
FUTURE_VERBS = {
    "persona": "docs/PERSONA_PACKS.md names it as unshipped work",
}

#: Actions the docs name as work a *later* change adds. PLUGIN_EXPORT.md section
#: "Commands the next change adds" says both join the `plugin` subparser later.
FUTURE_ACTIONS = {
    ("plugin", "export"),
    ("plugin", "import"),
}

#: The extractor's floor: if the patterns below silently stop matching, the test fails
#: here instead of passing an empty set.
CORE_COMMANDS = {"start", "doctor", "tui", "configure", "session"}


def _code_lines() -> list[tuple[str, int, str]]:
    """(path, line number, line) for every line of a fenced block or inline code span."""
    found: list[tuple[str, int, str]] = []
    for path in sorted(DOCS.rglob("*.md")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        in_fence = False
        fence_start = 0
        for number, line in enumerate(lines, 1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                fence_start = number
                continue
            if in_fence:
                found.append((str(path.relative_to(REPO)), number, line))
                continue
            for span in re.findall(r"`([^`\n]+)`", line):
                found.append((str(path.relative_to(REPO)), number, span))
        assert not in_fence, f"{path}: unbalanced code fence opened at line {fence_start}"
    return found


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _child_names(parser: argparse.ArgumentParser) -> set[str]:
    """Subcommands plus any positional constrained by `choices` (`session`'s action)."""
    names: set[str] = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            names.update(action.choices.keys())
        elif action.choices is not None and not action.option_strings:
            names.update(str(choice) for choice in action.choices)
    return names


def _documented_commands() -> list[tuple[str, int, str]]:
    """(location, top-level word) for every `ephe <word>` the docs present as code."""
    documented: list[tuple[str, int, str]] = []
    for path, number, line in _code_lines():
        for match in _COMMAND.finditer(line):
            documented.append((f"{path}:{number}", match.group(1)))
    return documented


def test_given_docs_when_scanned_then_the_extractor_finds_the_core_commands():
    documented = {command for _where, command in _documented_commands()}

    assert CORE_COMMANDS <= documented, (
        "the extractor found no evidence for "
        f"{sorted(CORE_COMMANDS - documented)}; the pattern or the docs changed"
    )


def test_given_docs_when_scanned_then_every_documented_command_exists_in_the_cli():
    parser = ephe_cli.build_parser()
    real = _child_names(parser)

    missing = [
        (where, command)
        for where, command in _documented_commands()
        if command not in real and command not in FUTURE_VERBS
    ]

    assert missing == [], (
        "docs name commands the CLI does not have: "
        + ", ".join(f"`ephe {command}` ({where})" for where, command in missing)
        + ". Document a verb that exists, or add the subparser in ephe_cli.build_parser()."
    )


def test_given_docs_when_a_documented_action_follows_a_subcommand_then_it_exists():
    """`ephe plugin list` names a child action too, and this test catches a renamed one."""
    parser = ephe_cli.build_parser()
    parents = _subparsers(parser)

    problems: list[str] = []
    for path, number, line in _code_lines():
        for match in _COMMAND.finditer(line):
            parent = match.group(1)
            child_parser = parents.get(parent)
            if child_parser is None:
                continue
            children = _child_names(child_parser)
            rest = line[match.end():].strip()
            if not children or not rest:
                continue
            token = rest.split()[0]
            if token.startswith(("-", "<", '"', "'", "#")):
                continue
            # `ephe session list|new|switch|rm|rename` names every action in one span.
            for word in (part.strip() for part in token.split("|")):
                if word and word not in children and (parent, word) not in FUTURE_ACTIONS:
                    problems.append(f"`ephe {parent} {word}` ({path}:{number})")

    assert problems == [], (
        "docs name actions the CLI does not have: " + ", ".join(problems)
    )
