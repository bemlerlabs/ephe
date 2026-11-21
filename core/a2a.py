"""core/a2a.py - minimal Agent-to-Agent (A2A) task protocol.

P3-A: a small, in-process structured message layer on top of the existing
agent continuation mechanism (core.swarm_v2.agent_message). It gives swarm and
multi-agent runs a traceable task lifecycle:

    submitted -> working -> (input-required <-> working) -> completed | failed

Every unit of work carries a stable ``task_id`` so tool loops and hand-offs are
reconstructible. The module is dependency-free and self-contained; it only adds
an observable ledger and does not change any existing call path.

Status names follow the open A2A convention: SUBMITTED, WORKING,
INPUT_REQUIRED, COMPLETED, FAILED.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.engine_config import config_subdir

#: Where the task ledger is persisted (survives a process restart when set).
A2A_LEDGER_FILE = config_subdir("a2a_ledger.json")

#: Closed set of lifecycle states a task may hold.
STATUS_SUBMITTED = "submitted"
STATUS_WORKING = "working"
STATUS_INPUT_REQUIRED = "input-required"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

_VALID_STATUS = frozenset(
    (STATUS_SUBMITTED, STATUS_WORKING, STATUS_INPUT_REQUIRED, STATUS_COMPLETED, STATUS_FAILED)
)
#: Terminal states end a task's lifecycle.
_TERMINAL_STATUS = frozenset((STATUS_COMPLETED, STATUS_FAILED))


@dataclass
class AgentCard:
    """Discovery record an agent publishes about itself (the A2A AgentCard)."""

    name: str
    description: str = ""
    version: str = "1.0.0"
    skills: list[str] = field(default_factory=list)
    #: tool names the agent may call (its declared whitelist).
    tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "skills": list(self.skills),
            "tools": list(self.tools),
        }


@dataclass
class A2ATask:
    """One tracked unit of work with a stable id and a lifecycle state."""

    id: str
    context_id: str
    agent: str
    status: str = STATUS_SUBMITTED
    #: accumulated artifacts (tool outputs / final texts), in step order.
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    #: short log of state transitions.
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "context_id": self.context_id,
            "agent": self.agent,
            "status": self.status,
            "artifacts": list(self.artifacts),
            "history": list(self.history),
        }


class A2AProtocol:
    """In-memory task ledger with an optional JSON persistence sink.

    A single instance is exposed as ``PROTOCOL``.
    """

    def __init__(self, *, persist: bool = True) -> None:
        self._cards: dict[str, AgentCard] = {}
        self._tasks: dict[str, A2ATask] = {}
        self._persist = persist

    # -- Discovery --

    def register(self, card: AgentCard) -> None:
        """Publish an agent card so tasks can reference it by name."""
        self._cards[card.name] = card

    def card(self, name: str) -> AgentCard | None:
        return self._cards.get(name)

    def list_cards(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self._cards.values()]

    # -- Lifecycle --

    def new_task(self, agent: str, *, context_id: str = "") -> A2ATask:
        """Create a task in the SUBMITTED state and return it."""
        task = A2ATask(
            id=f"task-{uuid.uuid4().hex[:8]}",
            context_id=context_id or f"ctx-{uuid.uuid4().hex[:6]}",
            agent=agent,
            status=STATUS_SUBMITTED,
        )
        task.history.append({"status": STATUS_SUBMITTED, "ts": time.time()})
        self._tasks[task.id] = task
        self._flush()
        return task

    def get(self, task_id: str) -> dict[str, Any] | None:
        task = self._tasks.get(task_id)
        return task.to_dict() if task is not None else None

    def set_status(self, task_id: str, status: str) -> dict[str, Any] | None:
        """Move a task to ``status``; terminal tasks accept no further change."""
        if status not in _VALID_STATUS:
            raise ValueError(f"unknown A2A status: {status!r}")
        task = self._tasks.get(task_id)
        if task is None:
            return None
        if task.status in _TERMINAL_STATUS:
            return task.to_dict()
        task.status = status
        task.history.append({"status": status, "ts": time.time()})
        self._flush()
        return task.to_dict()

    def add_artifact(self, task_id: str, artifact: dict[str, Any]) -> dict[str, Any] | None:
        """Append one artifact (a step tool result or final text) to a task."""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        task.artifacts.append(dict(artifact))
        self._flush()
        return task.to_dict()

    def tasks_for_context(self, context_id: str) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self._tasks.values() if t.context_id == context_id]

    # -- Persistence --

    def _flush(self) -> None:
        if not self._persist:
            return
        try:
            A2A_LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "cards": {name: card.to_dict() for name, card in self._cards.items()},
                "tasks": {tid: task.to_dict() for tid, task in self._tasks.items()},
            }
            tmp = A2A_LEDGER_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(A2A_LEDGER_FILE)
        except OSError:
            pass  # best-effort; the in-memory ledger stays authoritative

    def load(self) -> None:
        """Rehydrate cards and tasks from the persisted ledger, if present."""
        if not self._persist or not A2A_LEDGER_FILE.exists():
            return
        try:
            payload = json.loads(A2A_LEDGER_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for name, raw in (payload.get("cards") or {}).items():
            self._cards[name] = AgentCard(
                name=raw.get("name", name),
                description=raw.get("description", ""),
                version=raw.get("version", "1.0.0"),
                skills=list(raw.get("skills") or []),
                tools=list(raw.get("tools") or []),
            )
        for tid, raw in (payload.get("tasks") or {}).items():
            self._tasks[tid] = A2ATask(
                id=raw.get("id", tid),
                context_id=raw.get("context_id", ""),
                agent=raw.get("agent", ""),
                status=raw.get("status", STATUS_SUBMITTED),
                artifacts=list(raw.get("artifacts") or []),
                history=list(raw.get("history") or []),
            )


#: Shared process-wide protocol instance.
PROTOCOL = A2AProtocol()
