"""SOL phase 2 — the metacognitive check after a failed tool round.

A failed tool result is a signal, not an obstacle to retry: the loop used to
hand the error to the model and hope the next call differed. This module names
the class of failure, the assumption that turned out false and the correction
that follows from it, and adds any rule this project already learned about that
class. The block goes into the turn's context in front of the next model call.

Everything here is regex and table lookup — no model call, so the check costs
well under the latency floor the loop is held to.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: More specific classes come first: "sh: node: command not found" also contains
#: "not found", and the PATH correction is the useful one.
CLASSES: tuple[tuple[str, str, str, str], ...] = (
    (
        "command-not-found",
        r"(command not found|: not found\b|is not recognized as an internal or external command)",
        "the command is on this shell's PATH",
        "locate the binary (which -a, then the usual install prefixes) and call it by "
        "absolute path, or prepend its directory to PATH and repeat the call",
    ),
    (
        "port-in-use",
        r"(EADDRINUSE|address already in use|port \d+ is already in use)",
        "the port this command wanted is free",
        "pick another port and pass it explicitly, or stop the process that holds this one",
    ),
    (
        "permission-denied",
        r"(permission denied|EACCES|EPERM|operation not permitted)",
        "this path or command is writable by the current user",
        "keep the work inside the workspace; for a read that was refused, read it through "
        "the tool that owns that path instead of the shell",
    ),
    (
        "missing-module",
        r"(cannot find module|ModuleNotFoundError|no module named|could not resolve|"
        r"ERR_MODULE_NOT_FOUND)",
        "the dependency is installed in the environment this command runs in",
        "install it in the project's own environment (the runner the map names) or call "
        "the project's interpreter by path",
    ),
    (
        "timeout",
        r"(timed out|ETIMEDOUT|command timed out|deadline exceeded)",
        "the command finishes inside the tool's time limit",
        "split the work into smaller steps, or run the long part as a background command "
        "and read its output afterwards",
    ),
    (
        "network",
        r"(ENOTFOUND|ECONNREFUSED|getaddrinfo|temporary failure in name resolution|"
        r"could not resolve host)",
        "the endpoint this command reaches is reachable from here",
        "check the address and whether the service runs locally before repeating the call",
    ),
    (
        "compile-error",
        r"(SyntaxError|error TS\d+|error\[E\d+\]|compilation failed|parse error)",
        "the file as written parses and type-checks",
        "read the reported line, fix that file, and re-run the same command",
    ),
    (
        "test-failure",
        r"(\b\d+ failed\b|FAILED \(|AssertionError)",
        "the change leaves the existing checks passing",
        "read the failing assertion and fix the code it names; a test edit needs the "
        "reason the old expectation was wrong",
    ),
    (
        "file-missing",
        r"(no such file or directory|ENOENT|FileNotFoundError|does not exist)",
        "the path this command names exists",
        "list the parent directory first and call the real path; create the file only "
        "when the work is meant to create it",
    ),
)

_COMPILED = tuple(
    (kind, re.compile(pattern, re.IGNORECASE), assumption, correction)
    for kind, pattern, assumption, correction in CLASSES
)

#: The harness prefix a refused or failed tool result starts with.
_TOOL_ERROR_PREFIX = "[TOOL-ERROR] "

#: A block for every failed call would drown the context; one line per class.
MAX_REFLECTIONS = 4
MAX_SIGNAL_CHARS = 220


@dataclass(frozen=True)
class Reflection:
    kind: str
    tool: str
    signal: str
    assumption: str
    correction: str
    heuristic: str = ""


def _signal_line(text: str) -> str:
    """The most telling line of an error: the last non-empty one that carries
    digits or a colon, because runners put the verdict at the end."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if any(ch.isdigit() for ch in line) or ":" in line:
            return line[:MAX_SIGNAL_CHARS]
    return (lines[-1] if lines else "")[:MAX_SIGNAL_CHARS]


def classify(text: str) -> str | None:
    body = (text or "").strip()
    if body.startswith(_TOOL_ERROR_PREFIX):
        body = body[len(_TOOL_ERROR_PREFIX):]
    for kind, pattern, _assumption, _correction in _COMPILED:
        if pattern.search(body):
            return kind
    return None


def reflect(tool: str, result: str, heuristics: list | None = None) -> Reflection | None:
    """One reflection for one failed tool result, with a matching stored rule."""
    kind = classify(result)
    if kind is None:
        return None
    entry = next(item for item in _COMPILED if item[0] == kind)
    _kind, _pattern, assumption, correction = entry
    rule = ""
    for heuristic in heuristics or []:
        if getattr(heuristic, "kind", "") == kind:
            rule = f"[{getattr(heuristic, 'id', '')}] {getattr(heuristic, 'action', '')}"
            break
    return Reflection(
        kind=kind,
        tool=tool,
        signal=_signal_line(result),
        assumption=assumption,
        correction=correction,
        heuristic=rule,
    )


def render(reflections: list[Reflection]) -> str | None:
    """The system block for the next call; None when nothing was classified."""
    if not reflections:
        return None
    seen: set[str] = set()
    rows: list[str] = []
    for item in reflections:
        if item.kind in seen:
            continue
        seen.add(item.kind)
        row = [
            f"- class: {item.kind} (tool: {item.tool})",
            f"  signal: {item.signal or 'no line could be read'}",
            f"  assumption that failed: {item.assumption}",
            f"  correction: {item.correction}",
        ]
        if item.heuristic:
            row.append(f"  rule learned in this project: {item.heuristic}")
        rows.append("\n".join(row))
        if len(rows) >= MAX_REFLECTIONS:
            break
    return (
        "Tool failure reflection — the last round failed; change the call instead of "
        "repeating it:\n" + "\n".join(rows)
    )
