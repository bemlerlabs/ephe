#!/usr/bin/env python3
"""Message language: the sentences the test suite says about itself, checked for German.

`scripts/language_inventory.py:counts_for` scores every line of a file, string literals included —
its own docstring says the number "tracks growth alone". So the language gate did see these
sentences: it measured them into `scripts/language-baseline.json` and then stopped asking. A German
message in a file whose baseline entry still has room is free, and one that predates the entry is
free for as long as nobody raises the file. What no instrument did before this one is demand zero,
name the node the sentence sits in — an assert message, a skip reason, a raised sentence — and read
a message that was hoisted into a variable a line above.

That line is developer prose. It states what the developer believes broke, in the same words a
commit message would use, so it follows the owner rule of 2026-10-08: English in the tree. German
stays where it is the product's own surface — a fixture holding the refusal the product shows, a
locale value, a model answer in the language a user was asked in. That German is the subject of the
test, and translating it would destroy what the test proves.

The difference is not something a scanner can guess, so the file states it. A message is exempt
only by `MESSAGE_PRAGMA` on the line the message starts, or the line the statement around it
starts, followed by a reason. A bare marker is itself a finding: an exemption nobody can read is
how a rule gets overlooked. A marker costs no baseline line; the German message it excuses does.

The rule's audience is the suite: it reads `tests/` and nothing else. A gate script's own `print`
reaches an operator, not a developer reading a red leg, and is not read here — a gap on purpose,
and an open one.

Run as a script to print the findings over `tests/`; `scripts/language_gate.py` refuses on them.
"""
from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import language_inventory as inventory  # noqa: E402  (path bootstrap above)

REPO_ROOT = SCRIPTS_DIR.parent

#: The escape valve, in the shape `language_inventory.PRAGMA` already uses — a marker that states
#: what it exempts, on the line that needs it, with a reason a reader can check.
MESSAGE_PRAGMA = "language-gate: product German"

#: Developer-facing call names whose first positional argument or `reason=` is the developer's own
#: sentence. `pytest.raises(match=...)` is deliberately absent: that pattern is matched against the
#: product's output, so its German is the subject of the test by construction.
MESSAGE_KEYWORDS = ("reason", "msg", "message")


class Finding(NamedTuple):
    rel: str
    line: int
    kind: str
    quote: str


def _words(node: ast.AST) -> str:
    """The literal words of a message node. Interpolations and names carry no prose, so they
    vanish; adjacent literals and `+`-joins are read as the one sentence they are."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else ""
    if isinstance(node, ast.JoinedStr):
        return " ".join(
            value.value
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return " ".join(part for part in (_words(node.left), _words(node.right)) if part)
    if isinstance(node, ast.IfExp):
        return " ".join(part for part in (_words(node.body), _words(node.orelse)) if part)
    if isinstance(node, (ast.Tuple, ast.List)):
        return " ".join(part for part in (_words(element) for element in node.elts) if part)
    if isinstance(node, ast.BoolOp):
        return " ".join(part for part in (_words(value) for value in node.values) if part)
    return ""


def _german(text: str) -> list[str]:
    """The instrument's own high-recall vocabulary: umlaut words, the marker lists, the abbreviations."""
    found = [word for word in inventory.WIDE.findall(text) if word.lower() not in inventory.FALSE_FRIENDS]
    found += inventory.UMLAUT_WORD.findall(text)
    if inventory.GERMAN_ABBR.search(text):
        found.append("z. B.")
    return found


def _statement_line(node: ast.AST, parents: dict[int, ast.AST]) -> int:
    """The line the statement starts on, so a marker may sit beside `assert` for a wrapped message."""
    current: ast.AST | None = node
    while current is not None and not isinstance(current, ast.stmt):
        current = parents.get(id(current))
    return getattr(current, "lineno", getattr(node, "lineno", 0))


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return ""


def _literal_bindings(tree: ast.AST) -> dict[str, ast.expr]:
    """Names this file assigns exactly once to a literal string.

    `assert ok, msg` with `msg = "..."` a few lines above is the same developer sentence, and a
    checker that stops at the assert would be one hoist away from seeing nothing. Only an
    unambiguous single assignment is resolved; a name the file writes twice, or whose value is
    computed, is left unread instead of guessed at.
    """
    bound: dict[str, ast.expr] = {}
    ambiguous: set[str] = set()

    def claim(name: str, value: ast.expr | None) -> None:
        if name in bound or name in ambiguous:
            ambiguous.add(name)
            bound.pop(name, None)
        elif value is not None and isinstance(
                value, (ast.Constant, ast.JoinedStr, ast.BinOp, ast.IfExp, ast.Tuple, ast.List)
            ):
            bound[name] = value

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            claim(node.targets[0].id, node.value)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and isinstance(node.target, ast.Name):
            claim(node.target.id, None)
        elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            claim(node.target.id, None)
        elif isinstance(node, ast.arg):
            claim(node.arg, None)
        elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            claim(node.target.id, None)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            claim(node.name, None)
    return bound


def _messages(tree: ast.AST) -> list[tuple[str, ast.expr]]:
    """Every (kind, node) pair where the file says something about itself in a literal."""
    found: list[tuple[str, ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            if node.msg is not None:
                found.append(("assert message", node.msg))
        elif isinstance(node, ast.Raise):
            exc = node.exc
            if isinstance(exc, ast.Call) and _call_name(exc) in {"AssertionError", "RuntimeError", "ValueError"}:
                for arg in exc.args[:1]:
                    found.append(("raised message", arg))
                for keyword in exc.keywords:
                    if keyword.arg in MESSAGE_KEYWORDS:
                        found.append(("raised message", keyword.value))
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name in {"fail", "skip", "xfail"}:
                for arg in node.args[:1]:
                    found.append((f"pytest.{name} text", arg))
            if name in {"fail", "skip", "xfail", "skipif", "param"}:
                for keyword in node.keywords:
                    if keyword.arg in MESSAGE_KEYWORDS:
                        found.append((f"{name} reason", keyword.value))
    return found


def check(rel: str, text: str) -> tuple[list[Finding], int, int]:
    """Findings for one file, the messages it read, and the messages it could not read.

    The last number is the honest half: a message built at runtime — a helper's return value, a
    name computed in a loop — carries no literal for any instrument to look at, and a scan that
    quietly counted only what it could parse would look like a clean tree.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, UnicodeDecodeError):
        # A file that does not parse is not silently clean: the line gate measures it as raw text
        # (language_inventory.python_prose says why), so an unreadable file is reported here too.
        return ([Finding(rel, 0, "unparsable", "the message scan could not read this file")], 0, 0)
    lines = text.splitlines()
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    bindings = _literal_bindings(tree)

    findings: list[Finding] = []
    read = 0
    unread = 0
    for kind, node in _messages(tree):
        words = _words(node)
        if not words.strip() and isinstance(node, ast.Name):
            words = _words(bindings[node.id]) if node.id in bindings else ""
        if not words.strip():
            unread += 1
            continue
        read += 1
        line = getattr(node, "lineno", 0)
        marked = any(
            MESSAGE_PRAGMA in (lines[number - 1] if 0 < number <= len(lines) else "")
            for number in {line, _statement_line(node, parents)}
        )
        if marked:
            explanation = next(
                (
                    lines[number - 1].split(MESSAGE_PRAGMA, 1)[1]
                    for number in {line, _statement_line(node, parents)}
                    if 0 < number <= len(lines) and MESSAGE_PRAGMA in lines[number - 1]
                ),
                "",
            )
            if len(explanation.strip(" :#-\t")) < 4:
                findings.append(
                    Finding(rel, line, "unexplained exemption", f"{MESSAGE_PRAGMA} carries no reason")
                )
            continue
        hits = _german(words)
        if hits:
            quote = " ".join(words.split())
            findings.append(
                Finding(rel, line, kind, f"{quote[:90]}  [{', '.join(sorted(set(hits))[:6])}]")
            )
    return findings, read, unread


def check_pairs(pairs: Iterable[tuple[str, str | None]]) -> tuple[list[Finding], int, int]:
    """Findings, messages read and messages unread over `(path, text)` pairs.

    A file that cannot be read is a finding, never a skip: a leg that passes because it read
    nothing is the exact failure this file exists to prevent.
    """
    findings: list[Finding] = []
    read = 0
    unread = 0
    for rel, text in pairs:
        if text is None:
            findings.append(Finding(rel, 0, "unreadable", "the file could not be read as UTF-8 text"))
            continue
        found, count, count_unread = check(rel, text)
        findings += found
        read += count
        unread += count_unread
    return findings, read, unread


def scan(paths: list[Path], root: Path) -> tuple[list[Finding], int, int, int]:
    """Findings, messages read, messages unread, files read — the last three so an empty run
    cannot be mistaken for a pass."""
    wanted = list(paths)

    def pairs():
        for path in wanted:
            try:
                rel = str(path.relative_to(root))
            except ValueError:
                rel = str(path)
            try:
                yield rel, path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                yield rel, None

    findings, read, unread = check_pairs(pairs())
    return findings, read, unread, len(wanted)


def test_paths(root: Path) -> list[Path]:
    """The suite's own files. Its voice is what this rule is about."""
    return sorted((root / "tests").rglob("*.py"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="tree to read")
    parser.add_argument("--limit", type=int, default=40, help="findings to print (all are counted)")
    args = parser.parse_args(argv)
    findings, read, unread, files = scan(test_paths(args.root), args.root)
    for finding in findings[: args.limit]:
        print(f"  {finding.rel}:{finding.line} {finding.kind}: {finding.quote}")
    if len(findings) > args.limit:
        print(f"  ... {len(findings) - args.limit} more")
    print(
        f"message language: {len(findings)} finding(s) over {files} file(s); "
        f"{read} message(s) read, {unread} built at runtime and unreadable by any word check"
    )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
