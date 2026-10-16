#!/usr/bin/env python3
"""Prose inventory: where a file reads like generated text, with line numbers.

Owner rule 2026-10-09 (`AGENTS.md`, "Writing quality"): the repository may be read by
someone with no context and by tools that scan for AI-authored code, and both have to
find nothing. That is a rule about wording, so it needs an instrument. This module is
the measuring half of it: one file's developer prose in, findings out.

Only comments, docstrings and markdown body are read. A UI label, a German product
string or an asserted test value lives inside a literal, and a literal is outside the
law. `scripts/language_inventory.py` already drew that line, so its prose extraction is
the contract here; only the *positions* are re-derived, because a census has to name a
line. Each threshold is the number this tree measured on 2026-10-09, and says so.
"""
from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import NamedTuple

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

RESTATED_DOCSTRING = "restated-docstring"
NARRATING_COMMENT = "narrating-comment"
FILLER_BLOCK = "filler-block"
REPEATED_HEADER = "repeated-header"
DECORATIVE = "decorative"
STACKED_RHETORIC = "stacked-rhetoric"
SYMMETRIC_BLOCK = "symmetric-block"
MARKETING_ADJECTIVE = "marketing-adjective"
CLASSES = (
    RESTATED_DOCSTRING,
    NARRATING_COMMENT,
    FILLER_BLOCK,
    REPEATED_HEADER,
    DECORATIVE,
    STACKED_RHETORIC,
    SYMMETRIC_BLOCK,
    MARKETING_ADJECTIVE,
)


class Finding(NamedTuple):
    rel: str
    row: int
    cls: str
    quote: str


# A Given/When/Then docstring states the expectation a test proves. That shape is the
# test suite's own house style, so the name echo inside it carries information.
BDD_SHAPE = re.compile(r"^(?:G|W|T|A|DoD)\s*:|\b(?:Given|When|Then)\b", re.I)
STOP = frozenset(
    "a an the this that these those is are be been to of for and in on it its with as "
    "at by from or not no so if then does do did make made uses used use".split()
)


def words(text: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z][A-Za-z0-9_]*", text.lower()) if w not in STOP and len(w) > 2]


def _name_parts(name: str) -> set[str]:
    parts: set[str] = set()
    for chunk in re.split(r"[_\W]+", name.lower()):
        parts.update(w for w in re.findall(r"[a-z]+[0-9]*", chunk) if len(w) > 2)
    return parts


def _form_of(word: str, parts: Iterable[str]) -> bool:
    for part in parts:
        if word in (part, part + "s", part.rstrip("es"), part + "d", part + "ing", part + "tion"):
            return True
        if min(len(word), len(part)) >= 5 and word[:5] == part[:5]:
            return True
    return False


def restates(doc: str, name: str) -> bool:
    """Whether the opening line of `doc` repeats `name` and bounds nothing."""
    first = doc.strip().splitlines()[0]
    if BDD_SHAPE.search(first):
        return False
    parts = _name_parts(name)
    if not any(part in first.lower() for part in parts):
        return False
    return len([w for w in words(first) if not _form_of(w, parts)]) <= 1


NARRATION_VERB = re.compile(
    r"""^(?:now\s+)?(?:
        set|sets|create|creates|get|gets|return|returns|increment|increments|
        initialize|initializes|initialise|init|call|calls|assign|assigns|
        add|adds|append|appends|remove|removes|delete|deletes|update|updates|
        check|checks|loop|iterate|define|defines|import|imports|print|prints|
        open|opens|close|closes|build|builds|compute|computes|load|loads|
        save|saves|store|stores|render|renders|fetch|fetches|parse|parses|
        convert|converts|normalize|normalizes|mark|marks)\b""",
    re.I | re.X,
)
# A comment that bounds code says what limits it: a number, an arrow, an identifier, a
# wave tag, a path, a reason word. A line made of none of those and opening with a
# doing-verb is the one that repeats the statement under it.
CONSTRAINT_SIGNAL = re.compile(
    r"[\d—→_]|::|\be\.g\b|\bi\.e\b|[A-Za-z]{2,}-[A-Za-z]{2,}"
    r"|\b(?:must|never|only|not|cannot|if|when|because|since|otherwise|before|after|"
    r"while|owner|decision|measured|pinned|invariant|workaround|fallback|unless|"
    r"needed|allowed|test|tests|mock|stubs?|fails?|keeps?|holds?|gives?|means?|says?|shows?)"
    r"|\b(?:R|W|P|G|T|I|S|N|K|J|E|H)\d+\b|(?:^|\s)/[a-z]",
    re.I,
)
CODE_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
# Measured 2026-10-09: at this bar the class was 6 findings and all 6 restated the
# statement below them. Lower collected fragments of multi-line comments that do bound
# the code.
OVERLAP_BAR = 0.5


def narrates(text: str, following: str) -> bool:
    """Whether a short comment says what the statement under it does."""
    body = text.strip().strip("#/*").strip()
    if not NARRATION_VERB.match(body) or CONSTRAINT_SIGNAL.search(body):
        return False
    content = words(body)
    if not 1 <= len(content) <= 8:
        return False
    code = set(words(following))
    code |= {w.strip("()[]{}=+-*/<>!&|;:,.?~^%'\"") for w in CODE_TOKEN.findall(following)}
    code |= {w.replace("_", "") for w in code}
    shared = sum(1 for w in content if w in code or w + "s" in code)
    return shared / len(content) >= OVERLAP_BAR


FILLER_HEAD = re.compile(r"(?:^|\s)(?:[-*]\s*)?(?:NB|Note|Important|Warning|Caveat|Reminder|Observation)\s*:", re.I)
FILLER_TODO = re.compile(r"\bTODO\s*:?\s*(?:implement|add|finish|support|complete|write|refactor)\b", re.I)
FILLER_SELF = re.compile(r"^(?:[-*]\s*)?This\s+(?:function|method|class|module|file|helper|script|snippet)\b", re.I)

RULE_ASCII = re.compile(r"[=\-*_~^]{4,}")
RULE_BOX = re.compile(r"[─-╿▀-▟]{2,}")
UNICODE_BULLET = re.compile("[•‣⁃▪▫●○★☆☐☑✓-✘]")
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-⛿⬀-⯿︀]")

# The figure the law names, counted per file. Once states a boundary; the second in the
# same file is the rhythm a filler paragraph falls into.
RHETORIC = re.compile(r",\s*(?:not|rather than|instead of)\s+|\bnicht\b[^,;]{1,40},\s*sondern\s", re.I)  # language-gate: ignore (the German rhetorical figure this class detects, held as data)
RHETORIC_ALLOWED = 1

ADJECTIVES = re.compile(
    r"\b(?:robust|robustness|seamless\w*|powerful|blazing|blazingly|cutting[- ]edge|"
    r"state[- ]of[- ]the[- ]art|world[- ]class|effortless|hassle[- ]free|best[- ]in[- ]class|"
    r"game[- ]chang\w*|unleash\w*|supercharg\w*|empower\w*|elevat(?:e|es|ed|ing)\b|innovat\w*|"
    r"delv\w*|streamlin\w*|meticulous\w*|holistic\w*|plethora|bulletproof|future[- ]proof|"
    r"lightning[- ]fast|industry[- ]leading|best[- ]of[- ]breed|frictionless|next[- ]gen\w*|"
    r"reimag\w*|synerg\w*|paradigm[- ]shift\w*)\b",
    re.I,
)
# A tool pragma, a shebang and a module directive are not the wording of a file. The
# banner register reads it too, so `#!/usr/bin/env bash` never counts as a shared line.
HEADER_SKIP = re.compile(
    r"^(?:!\s*/|use\s+strict\b|use\s+client\b|eslint|prettier|global"
    r"|noqa\b|type\s*:|pylint\b|ruff\b|isort\b|language-gate:)",
    re.I,
)

TRIVIAL_BODY_SPAN = 14


def marker_body(text: str) -> str:
    return re.sub(r"^[ \t]*(?:#+|//+|/\*+|<!--|\*)[ \t]*", "", text).strip()


def strip_rule_runs(text: str) -> str:
    """A line of box-drawing rule has no words, so it may not key a header group."""
    return RULE_BOX.sub(" ", RULE_ASCII.sub(" ", text))


def chunk_lines(start: int, text: str) -> Iterator[tuple[int, str]]:
    for offset, line in enumerate(text.splitlines()):
        yield start + offset, line


def clike_chunks(text: str) -> list[tuple[int, str]]:
    """`//` and `/* … */` chunks with their opening row, string state honoured.

    `language_inventory.clike_prose` has the walking rule and no positions, since it
    only needed the words. The rule is copied: a quote opens a string only when it
    closes again on that line, so a JSX apostrophe cannot eat the code behind it, and a
    backtick may span lines.
    """
    found: list[tuple[int, str]] = []
    i, n, row = 0, len(text), 1
    while i < n:
        ch = text[i]
        if ch == "\n":
            row, i = row + 1, i + 1
            continue
        if text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            found.append((row, text[i:end]))
            i = end
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n - 2 if end < 0 else end
            found.append((row, text[i : end + 2]))
            row += text.count("\n", i, end + 2)
            i = end + 2
            continue
        if ch in "\"'":
            line_end = text.find("\n", i)
            limit = n if line_end < 0 else line_end
            close = text.find(ch, i + 1, limit)
            while 0 < close < limit and text[close - 1] == "\\":
                close = text.find(ch, close + 1, limit)
            if close > 0:
                i = close + 1
                continue
        if ch == "`":
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "`":
                    break
                j += 1
            row += text.count("\n", i, min(j + 1, n))
            i = min(j + 1, n)
            continue
        i += 1
    return found


def python_chunks(text: str) -> list[tuple[int, str, str]]:
    """Comments from tokenize plus docstrings from the tree, each with its row.

    The two sets are disjoint by construction, so a docstring is never also a comment.
    A file that will not tokenize falls back to a `#` line scan, because a half-written
    file must not read as clean.
    """
    try:
        comments = [(t.start[0], t.string) for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type == tokenize.COMMENT]
    except (tokenize.TokenError, SyntaxError, IndentationError):
        comments = [(n, line) for n, line in enumerate(text.splitlines(), 1) if line.lstrip().startswith("#")]
    chunks: list[tuple[int, str, str]] = [(row, "comment", body) for row, body in comments]
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return chunks
    for node in (n for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))):
        doc = ast.get_docstring(node, clean=False)
        if doc and node.body:
            chunks.append((node.body[0].lineno, "docstring", doc))
    # Source order, because a trailing pragma comment on an import line would otherwise
    # sort before the module docstring and become the head of the file.
    chunks.sort(key=lambda c: c[0])
    return chunks


def chunks_of(rel: str, text: str) -> list[tuple[int, str, str]]:
    """Prose chunks of a file: (opening row, kind, text). Kind is comment, docstring or
    markdown line. A file type with no comment syntax has no developer prose here."""
    suffix = Path(rel).suffix.lower()
    if suffix == ".py":
        return python_chunks(text)
    if suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".scss", ".rs"}:
        return [(row, "comment", chunk) for row, chunk in clike_chunks(text)]
    if suffix in {".sh", ".bash", ".yaml", ".yml", ".toml"}:
        return [(n, "comment", line) for n, line in enumerate(text.splitlines(), 1) if line.lstrip().startswith("#")]
    if suffix in {".md", ".markdown", ".txt"}:
        return [(n, "prose", line) for n, line in enumerate(text.splitlines(), 1) if line.strip()]
    return []


def _line_findings(rel: str, chunks: list[tuple[int, str, str]]) -> list[Finding]:
    patterns = (
        (FILLER_HEAD, FILLER_BLOCK),
        (FILLER_TODO, FILLER_BLOCK),
        (FILLER_SELF, FILLER_BLOCK),
        (RULE_ASCII, DECORATIVE),
        (RULE_BOX, DECORATIVE),
        (UNICODE_BULLET, DECORATIVE),
        (EMOJI, DECORATIVE),
        (ADJECTIVES, MARKETING_ADJECTIVE),
    )
    found: list[Finding] = []
    for row, _kind, chunk in chunks:
        for line_row, line in chunk_lines(row, chunk):
            body = marker_body(line)
            if body:
                for pattern, cls in patterns:
                    if pattern.search(body):
                        found.append(Finding(rel, line_row, cls, body[:90]))
                        break
    return found


def _narration_findings(rel: str, chunks: list[tuple[int, str, str]], src: list[str]) -> list[Finding]:
    found: list[Finding] = []
    for row, _kind, chunk in chunks:
        lines = chunk.splitlines()
        if len(lines) > 2:
            continue
        below = " ".join(src[row + len(lines) - 1 : row + len(lines) + 2])
        if narrates(" ".join(lines), below):
            found.append(Finding(rel, row, NARRATING_COMMENT, marker_body(lines[0])[:90]))
    return found


def _rhetoric_findings(rel: str, chunks: list[tuple[int, str, str]]) -> list[Finding]:
    seen = [(row, line) for cr, _k, chunk in chunks for row, line in chunk_lines(cr, chunk) if RHETORIC.search(line)]
    return [Finding(rel, row, STACKED_RHETORIC, marker_body(line)[:90]) for row, line in seen[RHETORIC_ALLOWED:]]


def docstring_of(node: ast.AST) -> str | None:
    body = getattr(node, "body", None) or []
    first = body[0] if body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return first.value.value
    return None


def _symmetric(rel: str, node: ast.FunctionDef, comment_rows: Counter[int], src: list[str]) -> Finding | None:
    """One comment line for every line of a short body.

    A docstring inside the window counts toward `code`, which only raises the bar.
    """
    body = node.body[1:] if docstring_of(node) is not None else node.body
    if not body:
        return None
    start = body[0].lineno
    while start > node.lineno + 1 and src[start - 2].lstrip().startswith("#"):
        start -= 1
    stop = max(getattr(stmt, "end_lineno", stmt.lineno) for stmt in body)
    if stop - start > TRIVIAL_BODY_SPAN:
        return None
    window = src[start - 1 : stop]
    code = sum(1 for line in window if line.strip() and not line.lstrip().startswith("#"))
    comments = sum(comment_rows[row] for row in range(start, stop + 1))
    if comments < 2 or code < 2 or comments < code:
        return None
    return Finding(rel, start, SYMMETRIC_BLOCK, f"{node.name}: {comments} comment lines over {code} code lines")


def python_findings(rel: str, text: str, chunks: list[tuple[int, str, str]]) -> list[Finding]:
    """The two classes that need the tree: restated docstrings, symmetric blocks."""
    src = text.splitlines()
    rows: Counter[int] = Counter()
    for row, kind, chunk in chunks:
        if kind == "comment":
            rows.update(r for r, line in chunk_lines(row, chunk) if line.strip())
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    found: list[Finding] = []
    stem = Path(rel).stem
    for node in (n for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))):
        doc = docstring_of(node)
        name = getattr(node, "name", stem)
        if doc is None or name.startswith("test_") or not restates(doc, name):
            continue
        found.append(Finding(rel, node.body[0].lineno, RESTATED_DOCSTRING, doc.strip().splitlines()[0][:90]))
    for node in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        block = _symmetric(rel, node, rows, src)
        if block:
            found.append(block)
    return found


def findings_for(rel: str, text: str) -> list[Finding]:
    """Every tell this file's developer prose carries, in source order."""
    chunks = chunks_of(rel, text)
    src = text.splitlines()
    found = _line_findings(rel, chunks)
    found.extend(_narration_findings(rel, chunks, src))
    found.extend(_rhetoric_findings(rel, chunks))
    if Path(rel).suffix == ".py":
        found.extend(python_findings(rel, text, chunks))
    return sorted(found, key=lambda f: (f.row, f.cls))
