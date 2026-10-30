"""SOL phase 4 — the two runs a workspace compares before it keeps a rule.

An episode is one turn's outcome as a few numbers: did the verifier pass, how
many rounds it took, which failure classes showed up, which learned rules were
in play. Episodes land in `.ephe/learning/episodes.jsonl`, one object per line,
so a workspace can answer "did the rule we learned make the next attempt
cheaper?" without keeping a transcript — the run log stays the transcript, this
file only counts.

`should_keep_rule` is the gate the consolidator needs: a rule is believed only
when a later attempt on the same task beat the earlier one. Twice the same
failure is not a lesson, and a faster failure is not one either.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

EPISODES_NAME = "episodes.jsonl"
TASK_CHARS = 120


@dataclass(frozen=True)
class Episode:
    task: str
    ok: bool
    rounds: int
    failures: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def as_json(self) -> dict:
        payload = asdict(self)
        payload["failures"] = list(self.failures)
        payload["rules"] = list(self.rules)
        return payload


def _store(root: Path) -> Path:
    return Path(root) / ".ephe" / "learning" / EPISODES_NAME


def task_key(task: str) -> str:
    """The comparison key: whitespace-normalised, cut short, no prompt body."""
    return " ".join(task.split())[:TASK_CHARS]


def record(root: Path, episode: Episode) -> None:
    target = _store(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(episode.as_json(), task=task_key(episode.task))
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def read(root: Path) -> list[dict]:
    target = _store(root)
    if not target.is_file():
        return []
    out: list[dict] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def previous_for(root: Path, task: str) -> dict | None:
    key = task_key(task)
    for row in reversed(read(root)):
        if row.get("task") == key:
            return row
    return None


def better(before: dict, after: dict) -> str:
    """Return 'after', 'before' or 'tie' — a pass beats a fail, then fewer rounds."""
    if bool(after.get("ok")) != bool(before.get("ok")):
        return "after" if after.get("ok") else "before"
    first = int(before.get("rounds") or 0)
    second = int(after.get("rounds") or 0)
    if second != first:
        return "after" if second < first else "before"
    return "tie"


def should_keep_rule(before: dict | None, after: dict) -> bool:
    """A rule is worth writing only when the later attempt actually improved."""
    if not after.get("ok"):
        return False
    if before is None:
        return False
    if not before.get("ok"):
        return True
    return better(before, after) == "after"
