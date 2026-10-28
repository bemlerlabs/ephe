"""Ephe – core/review_gate: a change set publishes on a verdict it earned, and on nothing else.

Parallel writers are only safe when a refusal is possible. This module holds the refusal: a
change set reaches the trunk after a reviewer approved it, the reviewer is never its own
author, and an approval carrying no located reason is never recorded at all.

A reason names a path, a line and the sentence a reviewer would say, the dialect
``scripts/architecture_check.mjs`` and ``app/scripts/bundle_budget.py`` already print.

Three rules are enforced here rather than described:

- Every verdict carries at least one reason, and a reason names a path and a line above
  zero. A submission without one is refused in ``submit`` and never reaches the ledger, so
  ``decide`` cannot return a verdict whose content is a feeling.
- An author cannot approve its own change set. ``submit`` refuses it, and ``may_publish``
  refuses one it finds already written, so a hand-edited ledger buys no publish either.
- Every answer is fail-closed. No verdict, a verdict filed against another change set, a
  latest line the reader cannot parse, an approval from the author, an approval a later
  request_changes or reject replaced – each answers False. Only the latest verdict counts,
  and only ``approve`` from a reviewer other than the author sets ``may_publish`` True.

The ledger is append-only JSONL (``~/.ephe/reviews.jsonl``, env ``EPHE_REVIEW_LEDGER``), one
object per line, read the way ``core/audit_log.py`` reads its log. A verdict the disk refuses
raises instead of returning, because a verdict nobody recorded did not happen and reporting
one would let the caller believe a publish was earned.
"""
from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APPROVE = "approve"
REQUEST_CHANGES = "request_changes"
REJECT = "reject"
VERDICTS = (APPROVE, REQUEST_CHANGES, REJECT)

LEDGER_SCHEMA = 1
LEDGER_FILE = Path(
    os.environ.get("EPHE_REVIEW_LEDGER", str(Path.home() / ".ephe" / "reviews.jsonl"))
)
REASON_KEYS = frozenset({"path", "line", "why"})


class ReviewGateError(ValueError):
    """A submission the gate turns down before it becomes a verdict.

    ``code`` is stable: a self-signature answers ``self_sign_forbidden``, the rest
    ``review_refused``. Neither kind reaches the ledger.
    """

    def __init__(self, message: str, *, code: str = "review_refused") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Reason:
    """One finding against a change set: where the reviewer looked, and what is wrong there."""

    path: str
    line: int
    why: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path.strip():
            raise ReviewGateError("a reason needs the path it points at")
        object.__setattr__(self, "path", self.path.strip())
        line = self.line
        if isinstance(line, bool) or not isinstance(line, int) or line < 1:
            raise ReviewGateError(
                f"a reason needs a line number above zero for {self.path}, got {self.line!r}"
            )
        if not isinstance(self.why, str) or not self.why.strip():
            raise ReviewGateError(f"a reason needs a why for {self.path}:{self.line}")
        object.__setattr__(self, "why", self.why.strip())

    def where(self) -> str:
        """``path:line``, spelled the way a compiler and a reviewer both read a location."""
        return f"{self.path}:{self.line}"

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "line": self.line, "why": self.why}


@dataclass(frozen=True)
class ChangeSet:
    """The unit under review: an id, the agent that authored it, the files it touches."""

    change_set_id: str
    author: str
    paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (("change_set_id", self.change_set_id), ("author", self.author)):
            if not isinstance(value, str) or not value.strip():
                raise ReviewGateError(f"a change set needs a non-empty {name}")
        object.__setattr__(self, "change_set_id", self.change_set_id.strip())
        object.__setattr__(self, "author", self.author.strip())
        object.__setattr__(self, "paths", tuple(str(p).strip() for p in self.paths))


@dataclass(frozen=True)
class ReviewVerdict:
    """A reviewer's decision on one change set, with the located reasons that carry it."""

    change_set_id: str
    verdict: str
    reviewer: str
    reasons: tuple[Reason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.change_set_id, str) or not self.change_set_id.strip():
            raise ReviewGateError("a verdict needs the change set it decides")
        object.__setattr__(self, "change_set_id", self.change_set_id.strip())
        decision = str(self.verdict).strip().lower()
        if decision not in VERDICTS:
            raise ReviewGateError(
                f"unknown verdict {self.verdict!r}; one of {', '.join(VERDICTS)}"
            )
        object.__setattr__(self, "verdict", decision)
        if not isinstance(self.reviewer, str) or not self.reviewer.strip():
            raise ReviewGateError("a verdict needs the reviewer who reached it")
        object.__setattr__(self, "reviewer", self.reviewer.strip())
        reasons = tuple(self.reasons)
        if not reasons:
            raise ReviewGateError(
                "a verdict needs at least one reason naming a path and a line"
            )
        object.__setattr__(self, "reasons", reasons)

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_set_id": self.change_set_id,
            "verdict": self.verdict,
            "reviewer": self.reviewer,
            "reasons": [r.to_dict() for r in self.reasons],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReviewVerdict:
        return cls(
            change_set_id=str(data.get("change_set_id", "")),
            verdict=str(data.get("verdict", "")),
            reviewer=str(data.get("reviewer", "")),
            reasons=tuple(_as_reason(item) for item in (data.get("reasons") or ())),
        )


def _as_reason(item: Any) -> Reason:
    """A ``Reason`` or a ``{path, line, why}`` mapping; anything else is refused."""
    if isinstance(item, Reason):
        return item
    if not isinstance(item, Mapping):
        raise ReviewGateError(
            f"a reason is a Reason or a mapping with path, line, why, got {type(item).__name__}"
        )
    keys = {str(k) for k in item}
    extra = keys - REASON_KEYS
    if extra:
        raise ReviewGateError(
            "a reason carries path, line and why only; unexpected " + ", ".join(sorted(extra))
        )
    missing = REASON_KEYS - keys
    if missing:
        raise ReviewGateError("a reason is missing " + ", ".join(sorted(missing)))
    return Reason(path=item["path"], line=item["line"], why=item["why"])


def _as_reasons(reasons: Any) -> tuple[Reason, ...]:
    if reasons is None or isinstance(reasons, (str, bytes)) or not isinstance(reasons, Iterable):
        raise ReviewGateError(
            "a verdict needs at least one reason naming a path and a line"
        )
    items = list(reasons)
    if not items:
        raise ReviewGateError("a verdict needs at least one reason naming a path and a line")
    return tuple(_as_reason(item) for item in items)


def _as_change_set(change_set: Any) -> ChangeSet:
    if isinstance(change_set, ChangeSet):
        return change_set
    if isinstance(change_set, Mapping):
        return ChangeSet(
            change_set_id=str(change_set.get("change_set_id", "")),
            author=str(change_set.get("author", "")),
            paths=tuple(change_set.get("paths") or ()),
        )
    raise ReviewGateError(
        f"a change set is a ChangeSet or a mapping with change_set_id and author, "
        f"got {type(change_set).__name__}"
    )


def _change_set_id_of(change_set: Any) -> str:
    if isinstance(change_set, str) and change_set.strip():
        return change_set.strip()
    return _as_change_set(change_set).change_set_id


def _author_of(change_set: Any) -> str | None:
    """The author the caller asserts, or None when it passed only an id."""
    if isinstance(change_set, ChangeSet):
        return change_set.author
    if isinstance(change_set, Mapping):
        author = change_set.get("author")
        return str(author).strip() or None if author is not None else None
    return None


def _parse_verdict(entry: Mapping[str, Any], change_set_id: str) -> ReviewVerdict | None:
    """A verdict out of one ledger line, or None when the line will not yield one."""
    try:
        return ReviewVerdict(
            change_set_id=str(entry.get("change_set_id", "")),
            verdict=str(entry.get("verdict", "")),
            reviewer=str(entry.get("reviewer", "")),
            reasons=tuple(_as_reason(item) for item in (entry.get("reasons") or ())),
        )
    except (ReviewGateError, TypeError):
        return None


class ReviewLedger:
    """Verdicts on disk, append-only, latest per change set. ``path=None`` keeps them in memory."""

    def __init__(self, path: Path | str | None = LEDGER_FILE) -> None:
        self.path = Path(path) if path is not None else None
        self._lock = threading.Lock()
        self._memory: list[dict[str, Any]] = []

    def entries(self) -> list[dict[str, Any]]:
        """Every recorded line, oldest first.

        The read rule of ``core/audit_log.py``, applied to this file: an entry is a JSON
        object on its own line, and a blank, unparseable or non-object line is skipped. A
        line that is a JSON object but will not yield a verdict for the change set stays
        visible to the reader below, which is where fail-closed is decided.
        """
        if self.path is None:
            return list(self._memory)
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return []
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                rows.append(entry)
        return rows

    def _latest_entry(self, change_set_id: str) -> dict[str, Any] | None:
        """The last line filed against this change set, readable or not."""
        found: dict[str, Any] | None = None
        for entry in self.entries():
            if str(entry.get("change_set_id", "")) == change_set_id:
                found = entry
        return found

    def submit(
        self,
        change_set: ChangeSet | Mapping[str, Any],
        verdict: str,
        reviewer: str,
        reasons: Iterable[Reason | Mapping[str, Any]],
    ) -> ReviewVerdict:
        """Record a verdict, or refuse the submission.

        The shape of the submission is checked before its authority: reasons first, then the
        author rule and the change set's own file list. Nothing is written when any check
        fails, so a refused submission leaves ``decide`` where it was.
        """
        target = _as_change_set(change_set)
        recorded = ReviewVerdict(
            change_set_id=target.change_set_id,
            verdict=str(verdict),
            reviewer=str(reviewer) if reviewer is not None else "",
            reasons=_as_reasons(reasons),
        )
        if recorded.verdict == APPROVE and recorded.reviewer == target.author:
            raise ReviewGateError(
                f"{recorded.reviewer} authored {target.change_set_id} and cannot approve it",
                code="self_sign_forbidden",
            )
        outside = [r.where() for r in recorded.reasons if target.paths and r.path not in target.paths]
        if outside:
            raise ReviewGateError(
                f"{target.change_set_id} does not touch {', '.join(outside)}; "
                "a reason names a file in the change set"
            )
        entry = {
            "schema": LEDGER_SCHEMA,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "change_set_id": target.change_set_id,
            "author": target.author,
            **recorded.to_dict(),
        }
        with self._lock:
            if self.path is not None:
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    with self.path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except OSError as exc:
                    raise ReviewGateError(
                        f"the verdict on {target.change_set_id} was not recorded: {exc}"
                    ) from exc
            else:
                self._memory.append(entry)
        return recorded

    def decide(self, change_set: ChangeSet | Mapping[str, Any] | str) -> ReviewVerdict | None:
        """The latest verdict on this change set, or None when there is none to read.

        A latest line that will not yield a verdict answers None rather than falling back to
        the round before it: the reader cannot tell an approval from a request_changes that
        arrived there, so it reports nothing.
        """
        change_set_id = _change_set_id_of(change_set)
        entry = self._latest_entry(change_set_id)
        return None if entry is None else _parse_verdict(entry, change_set_id)

    def latest_by_id(self) -> dict[str, ReviewVerdict]:
        """The latest readable verdict per change set, from one read of the ledger.

        A review list asks this per row; ``decide`` per row would read the file once per set.
        """
        latest: dict[str, ReviewVerdict] = {}
        for entry in self.entries():
            verdict = _parse_verdict(entry, str(entry.get("change_set_id", "")))
            if verdict is not None:
                latest[verdict.change_set_id] = verdict
        return latest

    def may_publish(self, change_set: ChangeSet | Mapping[str, Any] | str) -> bool:
        """True for the latest approve from a reviewer other than the author, False otherwise.

        The author check reads the ledger's own record and re-checks an author the caller
        asserts, so neither a hand-written approval line nor a change set presented under
        another name reaches the trunk.
        """
        change_set_id = _change_set_id_of(change_set)
        entry = self._latest_entry(change_set_id)
        if entry is None:
            return False
        verdict = _parse_verdict(entry, change_set_id)
        if verdict is None or verdict.verdict != APPROVE:
            return False
        if verdict.reviewer == str(entry.get("author", "")):
            return False
        author = _author_of(change_set)
        return author is None or author == str(entry.get("author", ""))


_default_ledger = ReviewLedger()


def default_ledger() -> ReviewLedger:
    return _default_ledger


def submit(
    change_set: ChangeSet | Mapping[str, Any],
    verdict: str,
    reviewer: str,
    reasons: Iterable[Reason | Mapping[str, Any]],
) -> ReviewVerdict:
    return _default_ledger.submit(change_set, verdict, reviewer, reasons)


def decide(change_set: ChangeSet | Mapping[str, Any] | str) -> ReviewVerdict | None:
    return _default_ledger.decide(change_set)


def may_publish(change_set: ChangeSet | Mapping[str, Any] | str) -> bool:
    return _default_ledger.may_publish(change_set)


def latest_by_id() -> dict[str, ReviewVerdict]:
    return _default_ledger.latest_by_id()


__all__ = [
    "APPROVE", "LEDGER_FILE", "LEDGER_SCHEMA", "REASON_KEYS", "REJECT", "REQUEST_CHANGES",
    "VERDICTS", "ChangeSet", "Reason", "ReviewGateError", "ReviewLedger", "ReviewVerdict",
    "decide", "default_ledger", "latest_by_id", "may_publish", "submit",
]
