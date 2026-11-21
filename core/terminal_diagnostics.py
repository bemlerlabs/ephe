"""Turn a failed shell result into a named failure with one repair step.

The model sees tool output verbatim. A raw traceback names the symptom and
leaves the cause implicit, so a small model retries the same command. Each rule
here recognises one failure class and appends the sentence that class needs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_OUTPUT_SCAN = 8000


@dataclass(frozen=True)
class Diagnosis:
    code: str
    hint: str


_MODULE = re.compile(r"ModuleNotFoundError: No module named '([^']+)'")
_IMPORT_NAME = re.compile(r"ImportError: cannot import name '([^']+)' from '([^']+)'")
_NODE_MODULE = re.compile(r'Cannot find module "([^"]+)"')
_COMMAND = re.compile(r"(?:^|\n)\s*(?:[^\n:]+: )?([\w.+-]+): command not found")
_COMMAND_ZSH = re.compile(r"command not found:\s*([\w.+-]+)")
_SEATBELT = re.compile(r"sandbox-exec|Operation not permitted|deny file-write|sandbox violation", re.I)
_PORT = re.compile(r"EADDRINUSE[^\n]*?(?::|\bport\s+)(\d{2,5})", re.I)
_ADDR_IN_USE = re.compile(r"address already in use[^\n]*?:(\d{2,5})", re.I)
_PERMISSION = re.compile(r"Permission denied", re.I)
_GIT = re.compile(r"fatal: not a git repository", re.I)


def _module_rule(output: str) -> Diagnosis | None:
    match = _MODULE.search(output)
    if match:
        package = match.group(1).split(".")[0]
        return Diagnosis(
            "missing-python-package",
            f"The package `{package}` is not installed in this interpreter. "
            f"Install it (`python -m pip install {package}`) or use an import that exists.",
        )
    match = _IMPORT_NAME.search(output)
    if match:
        return Diagnosis(
            "missing-import-name",
            f"`{match.group(2)}` does not export `{match.group(1)}`. Read that module "
            "before importing a name it does not define.",
        )
    return None


def _node_rule(output: str) -> Diagnosis | None:
    match = _NODE_MODULE.search(output)
    if match:
        return Diagnosis(
            "missing-node-module",
            f"`{match.group(1)}` is not installed in this project. Run `npm install` "
            "in the workspace, or import a package the project already depends on.",
        )
    return None


def _command_rule(output: str) -> Diagnosis | None:
    match = _COMMAND_ZSH.search(output) or _COMMAND.search(output)
    if match:
        name = match.group(1)
        return Diagnosis(
            "command-not-found",
            f"`{name}` is not on PATH. Install it or call it by its absolute path; "
            "`command -v` shows nothing for a missing binary.",
        )
    return None


def _port_rule(output: str) -> Diagnosis | None:
    match = _PORT.search(output) or _ADDR_IN_USE.search(output)
    if match:
        port = match.group(1)
        return Diagnosis(
            "port-in-use",
            f"Port {port} already has a listener. Find it with "
            f"`lsof -nP -iTCP:{port} -sTCP:LISTEN`, stop that exact PID if it is yours, "
            f"or start this process on another port.",
        )
    return None


def _sandbox_rule(output: str) -> Diagnosis | None:
    if _SEATBELT.search(output):
        return Diagnosis(
            "sandbox-denied",
            "The sandbox refused the access. Reads and writes are allowed inside the "
            "workspace, TMPDIR and the home directory; the network is off. Move the "
            "operation into the workspace instead of retrying it unchanged.",
        )
    return None


def _permission_rule(output: str) -> Diagnosis | None:
    if _PERMISSION.search(output):
        return Diagnosis(
            "permission-denied",
            "The file mode refuses this user. Check the mode (`ls -l`) and fix it with "
            "an explicit `chmod` on the file you own.",
        )
    return None


def _git_rule(output: str) -> Diagnosis | None:
    if _GIT.search(output):
        return Diagnosis(
            "not-a-git-repository",
            "The working directory is outside a git repository. Run the command from "
            "the repository root, or initialise one with `git init` if that was intended.",
        )
    return None


_RULES = (
    _module_rule,
    _node_rule,
    _command_rule,
    _port_rule,
    _sandbox_rule,
    _permission_rule,
    _git_rule,
)


def diagnose(output: str) -> Diagnosis | None:
    """First matching failure class, or None when the output names none of them."""
    text = (output or "")[:MAX_OUTPUT_SCAN]
    for rule in _RULES:
        found = rule(text)
        if found is not None:
            return found
    return None


def annotate(result: str, command: str = "") -> str:
    """Append the diagnosis to a failed result; unchanged strings stay untouched."""
    if not result or "[diagnosis " in result:
        return result
    found = diagnose(result)
    if found is None:
        return result
    head = f"\n\n[diagnosis {found.code}]"
    if command:
        head += f" after `{command.strip()[:200]}`"
    return f"{result}{head}\n{found.hint}"


SHELL_TOOL_NAMES = frozenset({"run_shell", "bash", "execute_confirmed_shell"})


def annotate_tool_result(name: str, arguments: dict | None, result: str) -> str:
    """The registry's hook: only shell results carry a shell diagnosis."""
    if name not in SHELL_TOOL_NAMES:
        return result
    command = str((arguments or {}).get("command", ""))
    return annotate(result, command)
