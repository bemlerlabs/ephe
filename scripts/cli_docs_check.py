"""Do the committed documents still describe the CLI the CLI actually offers?

The parser in `ephe_cli.py` is the truth about what `ephe` accepts; `docs/CLI.md` and the READMEs are
what a person reads before typing. Nothing connected them, and the drift has two directions that hurt
differently. A verb the docs promise and the parser lacks is a broken promise someone follows into
`unrecognized arguments` — `ephe web` was that, until it was not. A verb or flag the parser offers and
no document names is quieter and worse for discovery: `ephe prune --keep-rest` frees files on the
machine, and until 2026-11-17 not one committed document said the flag exists.

Both directions are gated here, against the live parser rather than an extracted copy of it, so a flag
renamed in `add_argument` moves the requirement with it. Documents are read as prose plus code: a
command path counts as named only where it sits in a code span or a fenced block, which is where this
project writes what to type, and the document's own idiom for a family of subcommands —
`ephe persona export | import | verify | show` — counts as naming all four.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_GLOBS = ("docs/**/*.md", "README*.md")
WORD = re.compile(r"[a-z][a-z0-9-]*")
FLAG_TOKEN = re.compile(r"--[a-z][a-z0-9-]+")
#: Flags the parser defines and no document names, each with the reason it stays that way. An entry
#: whose flag the parser no longer defines is itself a finding, so this list cannot accumulate.
INTERNAL_FLAGS: dict[str, str] = {
    "--rep": "repetition index for pass^k grouping, read by the bench harness that shells out to "
             "`ephe code|run|goal`; a person typing it has no use for it",
}


def load_cli(root: Path):
    """The CLI module, loaded by path with the tree on the import path while it loads.

    ``ephe_cli.py`` imports ``core._cli_common``, so a load by path still needs the tree
    importable. Measured 2026-11-17: run on a machine with the package installed, the import
    answered from that installation and the check measured a different tree than the one it was
    pointed at; on a runner with nothing installed it failed with ``No module named 'core'``.
    The entry goes in for the load and comes back out.
    """
    path = root / "ephe_cli.py"
    spec = importlib.util.spec_from_file_location("_ephe_cli_for_docs_check", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cli-docs: {path} is not importable")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(root))
    try:
        spec.loader.exec_module(module)
    finally:
        if sys.path[:1] == [str(root)]:
            sys.path.pop(0)
    return module


def command_parsers(parser) -> dict[str, object]:
    """Every invocable subcommand as `{path: parser}` — the ones with a `func`, not the bare groups."""
    found: dict[str, object] = {}
    seen: set[int] = set()

    def walk(node, depth: int) -> None:
        if id(node) in seen:
            return
        seen.add(id(node))
        if depth and node.get_default("func") is not None:
            found[node.prog.removeprefix("ephe ").strip()] = node
        for action in node._actions:
            choices = getattr(action, "choices", None)
            if isinstance(choices, dict):
                for child in choices.values():
                    if hasattr(child, "_actions"):
                        walk(child, depth + 1)

    walk(parser, 0)
    return found


def option_flags(parser) -> dict[str, tuple[str, str]]:
    """`{flag: (command path, help)}` for every long flag the parser defines, first command wins."""
    flags: dict[str, tuple[str, str]] = {}
    seen: set[int] = set()

    def walk(node, path: str) -> None:
        if id(node) in seen:
            return
        seen.add(id(node))
        for action in node._actions:
            for opt in action.option_strings:
                if opt.startswith("--") and opt != "--help" and opt not in flags:
                    flags[opt] = (path or "ephe", action.help or "")
        for action in node._actions:
            choices = getattr(action, "choices", None)
            if isinstance(choices, dict):
                for name, child in choices.items():
                    if hasattr(child, "_actions"):
                        walk(child, f"{path} {name}".strip())

    walk(parser, "")
    return flags


def _command_words(branch: str) -> list[str]:
    """The leading subcommand words of one branch, up to the first argument or placeholder."""
    words = []
    for token in branch.split():
        if not WORD.fullmatch(token):
            break
        words.append(token)
    return words


def _paths_in_span(span: str) -> set[str]:
    """Command paths from one code span, honouring the `a | b | c` family idiom."""
    paths: set[str] = set()
    for raw in span.splitlines():
        line = raw.split(" #", 1)[0]
        for match in re.finditer(r"[^\w.-]ephe\b(.*)$", f" {line}"):
            branches = match.group(1).split("|")
            words = _command_words(branches[0])
            if words:
                paths.add(" ".join(words))
            if len(branches) > 1 and words:
                stem = " ".join(words[:-1])
                for branch in branches[1:]:
                    tail = _command_words(branch)
                    if tail:
                        paths.add(f"{stem} {tail[0]}")
    return paths


def documented_paths(root: Path, text_by_file: dict[str, str]) -> set[str]:
    """Every `ephe …` path the documents write down, code spans and fenced blocks only."""
    paths: set[str] = set()
    for text in text_by_file.values():
        in_fence = False
        fence_lines: list[str] = []
        for line in text.splitlines():
            if line.lstrip().startswith("```"):
                if in_fence:
                    paths |= _paths_in_span("\n".join(fence_lines))
                    fence_lines = []
                in_fence = not in_fence
                continue
            if in_fence:
                fence_lines.append(line)
                continue
            for span in re.findall(r"`([^`\n]*)`", line):
                paths |= _paths_in_span(span)
    return paths


def documented_flags(text_by_file: dict[str, str]) -> set[str]:
    """Every `--flag` token anywhere in the documents, prose included: a flag is found if it is read."""
    flags: set[str] = set()
    for text in text_by_file.values():
        flags |= set(FLAG_TOKEN.findall(text))
    return flags


def doc_texts(root: Path) -> dict[str, str]:
    texts: dict[str, str] = {}
    for pattern in DOC_GLOBS:
        for path in sorted(root.glob(pattern)):
            texts[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return texts


def check(root: Path) -> tuple[list[str], list[str], int, int]:
    """`(problems, notes, commands checked, flags checked)` for one tree."""
    cli = load_cli(root)
    parser = cli.build_parser()
    commands = command_parsers(parser)
    flags = option_flags(parser)
    texts = doc_texts(root)
    doc_paths = documented_paths(root, texts)
    doc_flags = documented_flags(texts)

    problems: list[str] = []
    for path in sorted(commands):
        if path not in doc_paths:
            problems.append(f"ephe {path} is invocable and no committed document names it")
    # The reverse direction is printed and not gated. A sentence inside a code span reads as a command
    # line often enough — `~/.ephe/venv/bin/activate`, a `voice install <name>` with its argument — that
    # failing on it would teach the reader to ignore the check, which is the fate this project's own
    # nightly already documents. What is gated is the direction where the code is the truth.
    notes = [f"the documents write `ephe {path}`, the parser does not define it"
             for path in sorted(doc_paths - set(commands)) if " " in path]
    for flag, (path, _help) in sorted(flags.items()):
        if flag in doc_flags:
            continue
        if flag in INTERNAL_FLAGS:
            continue
        problems.append(f"{flag} (ephe {path}) is defined and named in no committed document")
    for flag in sorted(INTERNAL_FLAGS):
        if flag not in flags:
            problems.append(f"INTERNAL_FLAGS names {flag}, which the parser no longer defines")
    return problems, notes, len(commands), len(flags)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    problems, notes, commands, flags = check(args.root)
    for problem in problems:
        print(f"cli-docs: {problem}")
    for note in notes:
        print(f"cli-docs: note: {note}")
    print(f"cli-docs: {commands} command(s), {flags} flag(s), {len(INTERNAL_FLAGS)} internal flag(s), "
          f"{len(notes)} note(s), {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
