"""One turn of self-organised learning: what failed, what changed, what stuck.

The tool loop binds a `SolTurn` for the duration of a turn. Failed rounds are
handed to the reflector, and the block it renders goes into the context in
front of the next model call. When the turn finishes cleanly, every failure
class that the later rounds did not repeat becomes a stored rule — the one
moment at which a correction is known to have worked.
"""
from __future__ import annotations

import contextvars
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from core.sol import consolidator, organizer, reflector

logger = logging.getLogger(__name__)

#: Common install prefixes, searched only when PATH does not answer.
_PREFIXES = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "~/.local/bin")

#: The shell reports a failed run as `[exit N]`; N == 0 is a pass.
_EXIT_MARKER = re.compile(r"\[exit\s+(\d+)\]")
#: A refusal is the user's decision, not a wrong assumption about the project.
_NOT_A_FAILURE = ("[TOOL-DENIED]", "⚠️ Security:")

_MISSING_COMMAND = re.compile(
    r"(?:command not found:\s*|:\s*([\w./+-]+):\s*command not found|"
    r"([\w./+-]+):\s*(?:command )?not found)",
    re.IGNORECASE,
)

_FAILURE_TITLES = {
    "command-not-found": "The project's tools are not on the shell PATH",
    "port-in-use": "A port the project needs is already held",
    "permission-denied": "The refused path needs another route",
    "missing-module": "The dependency lives in the project's own environment",
    "timeout": "Long commands have to be split or backgrounded",
    "network": "The endpoint has to be reachable before the call repeats",
    "compile-error": "The reported line marks what to change",
    "test-failure": "The failing assertion names what to change",
    "file-missing": "List the parent directory before naming the path",
}


def looks_failed(text: str) -> bool:
    """Whether a tool result reports a failed run.

    `normalize_tool_result` classifies a shell result by its prefix, and the
    shell marks a non-zero exit with `[exit N]` inside the text — the marker the
    run record and the goal loop already read. SOL uses the same marker, so a
    "command not found" that came back through the shell is a failure here too.
    """
    body = str(text or "")
    if any(marker in body for marker in _NOT_A_FAILURE):
        return False
    if body.startswith("[TOOL-ERROR]"):
        return True
    match = _EXIT_MARKER.search(body)
    return bool(match and match.group(1) != "0")


def enabled() -> bool:
    """The `sol.enabled` switch; a broken settings file keeps the default."""
    try:
        from core.settings_schema import deep_bool

        return bool(deep_bool("sol.enabled"))
    except Exception:
        return True


@dataclass(frozen=True)
class Failure:
    kind: str
    tool: str
    round: int
    signal: str
    reflection: reflector.Reflection


def _missing_command(signal: str) -> str:
    match = _MISSING_COMMAND.search(signal or "")
    if not match:
        return ""
    return (match.group(1) or match.group(2) or "").strip()


def resolve_binary(name: str) -> str:
    """Absolute path of `name`, from PATH first and the usual prefixes second."""
    if not name or "/" in name:
        return ""
    found = shutil.which(name)
    if found:
        return found
    for prefix in _PREFIXES:
        candidate = Path(prefix).expanduser() / name
        if candidate.is_file() and candidate.stat().st_mode & 0o111:
            return str(candidate)
    return ""


class SolTurn:
    """The turn's failure record and the rules it can contribute at the end."""

    def __init__(self, root: Path, heuristics: list[consolidator.Heuristic], *, active: bool = True):
        self.root = root
        self.heuristics = heuristics
        self.active = active
        self.failures: list[Failure] = []
        self.learned: list[consolidator.Heuristic] = []

    @classmethod
    def open(cls, root: Path | None = None, *, active: bool | None = None) -> "SolTurn":
        resolved = (root or organizer.workspace_root()).expanduser().resolve()
        on = enabled() if active is None else active
        return cls(resolved, consolidator.load(resolved) if on else [], active=on)

    def reflect_round(self, round_no: int, failed: list[tuple[str, str, str]]) -> str | None:
        """The reflection block for one round's failed calls, or None."""
        if not self.active or not failed:
            return None
        fresh: list[reflector.Reflection] = []
        known = {item.kind for item in self.failures}
        for tool, _args, result in failed:
            text = str(result)
            if not looks_failed(text):
                continue
            reflection = reflector.reflect(tool, text, self.heuristics)
            if reflection is None or reflection.kind in known:
                continue
            known.add(reflection.kind)
            self.failures.append(
                Failure(
                    kind=reflection.kind,
                    tool=tool,
                    round=round_no,
                    signal=reflection.signal,
                    reflection=reflection,
                )
            )
            fresh.append(reflection)
        return reflector.render(fresh)

    def _evidence(self, item: Failure) -> tuple[str, str]:
        """(insight, action) for the stored rule, as this project showed them.

        A missing command is the one case the turn can answer with a path: the
        binary exists on this machine and the failing shell did not look there.
        """
        if item.kind == "command-not-found":
            name = _missing_command(item.signal)
            path = resolve_binary(name)
            if path:
                parent = str(Path(path).parent)
                return (
                    f"`{name}` resolves to {path} on this machine; the failing "
                    "shell's PATH did not reach it",
                    f"Call `{name}` as `{path}`, or prepend `{parent}` to PATH "
                    "before the call",
                )
        signal = f"the round reported: {item.signal}" if item.signal else ""
        return signal, item.reflection.correction

    def finish(self, ok: bool, *, last_round: int | None = None) -> list[consolidator.Heuristic]:
        """Persist the rules this turn proved, newest first. A turn that did not
        finish proves nothing and writes nothing.

        `last_round` is the turn's final tool round: a failure that stood in it
        had no later round to show the correction working.
        """
        if not self.active or not ok or not self.failures:
            return []
        boundary = last_round if last_round is not None else max(item.round for item in self.failures)
        written: list[consolidator.Heuristic] = []
        for item in self.failures:
            if item.round >= boundary:
                continue
            insight, action = self._evidence(item)
            if not insight:
                continue
            try:
                rule = consolidator.record(
                    kind=item.kind,
                    title=_FAILURE_TITLES.get(item.kind, item.reflection.correction),
                    trigger=f"A tool call in this project fails with {item.kind}",
                    insight=insight,
                    action=action,
                    root=self.root,
                )
            except Exception as exc:
                logger.warning("SOL could not store a heuristic: %s", exc)
                continue
            if rule is not None:
                written.append(rule)
        self.learned = written
        return written


_CURRENT: contextvars.ContextVar[SolTurn | None] = contextvars.ContextVar("ephe_sol_turn", default=None)


def bind_sol_turn(turn: SolTurn | None) -> contextvars.Token:
    return _CURRENT.set(turn)


def reset_sol_turn(token: contextvars.Token) -> None:
    _CURRENT.reset(token)


def current_sol_turn() -> SolTurn | None:
    return _CURRENT.get()
