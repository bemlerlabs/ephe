"""CLI seam for the isolation verbs: agents, changes, review, publish, reap.

An operator running ten agents has to see the wave and hold the gate from one terminal, so
these five verbs read the isolation stores as they are and print what those report: the
worktree register (``core/workspace_lifecycle``), the change-set store
(``core/change_set``), the review ledger (``core/review_gate``) and the ref move
(``core/atomic_publish``). ``ephe_cli`` keeps the argparse surface; what a verb does lives
here, where a test reaches it without a parser.

Four honesty rules this module is written to (wave "Isolation", 2026-10-14):

- An empty answer is one line naming the store it read, never a plausible example, and a
  verb that cannot answer raises ``IsolationError`` with the refusal *and* the fix.
- The gate is ``core/review_gate``, not this module: a reasonless verdict, an author
  approving its own work and a publish without an approval print that module's sentence.
- The state and the tree come from ``core.publish_readiness``: a set that does not stand in
  ``approved``, and one whose tree moved or went missing, refuse with that module's reason code
  — the same code the web route refuses the same set with.
- ``ephe publish`` carries every field of ``PublishResult`` back to its caller, the landing's
  commit oid among them, because that oid names the branch state the set left behind.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core import atomic_publish as publisher
from core import change_set as store
from core import publish_readiness as preflight
from core import review_gate as gate
from core import workspace_lifecycle as workspaces
from core._cli_common import short_sha  # noqa: F401 — re-exported in __all__ below

#: The reviewer's decisions as an operator types them, and the gate's spelling of each.
DECISIONS = {
    "approve": gate.APPROVE,
    "request-changes": gate.REQUEST_CHANGES,
    "reject": gate.REJECT,
}

#: Where a verdict leaves a set. ``approve`` reaches ``approved``, the state the publish gate
#: reads: a terminal approval and a web approval leave the same record, or a set approved in one
#: surface could not be published in the other. ``request_changes`` stays in ``review`` — the
#: reviewer asked for work, which is what a set under review is — and ``reject`` closes it.
STATE_AFTER = {gate.APPROVE: "approved", gate.REQUEST_CHANGES: "review", gate.REJECT: "rejected"}

#: The state a landable change set reaches once its files are on the branch.
PUBLISHED = "published"

SECONDS_MINUTE = 60
SECONDS_HOUR = 3600
SECONDS_DAY = 86400

#: `ephe reap`'s grace period in minutes, taken from the lifecycle module so --help cannot drift.
DEFAULT_REAP_MINUTES = workspaces.DEFAULT_REAP_MINUTES


class IsolationError(RuntimeError):
    """A verb that cannot answer honestly: the refusal, and the fix that would let it."""

    def __init__(self, message: str, fix: str = "", code: int = 1) -> None:
        super().__init__(message)
        self.fix = fix
        self.code = code


def _emit(payload: dict, lines: list[str], as_json: bool) -> None:
    """One verb's answer: the payload under ``--json``, otherwise the lines a person reads."""
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for line in lines:
        print(line)


def _ledger() -> gate.ReviewLedger:
    """The gate's own ledger — the one factory a test repoints at a throwaway file."""
    return gate.default_ledger()


# ephe agents


def _age_seconds(created_at: str) -> int | None:
    """Seconds since a register row was written, or None for a stamp that will not parse."""
    try:
        stamp = datetime.fromisoformat(str(created_at))
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(tz=timezone.utc) - stamp).total_seconds()))


def age_text(seconds: int | None) -> str:
    """One row's age in a unit pair — ``42s``, ``17m``, ``3h04m``, ``2d06h``; ``?`` if unknown."""
    if seconds is None:
        return "?"
    if seconds < SECONDS_MINUTE:
        return f"{seconds}s"
    if seconds < SECONDS_HOUR:
        return f"{seconds // SECONDS_MINUTE}m"
    if seconds < SECONDS_DAY:
        return f"{seconds // SECONDS_HOUR}h{seconds % SECONDS_HOUR // SECONDS_MINUTE:02d}m"
    return f"{seconds // SECONDS_DAY}d{seconds % SECONDS_DAY // SECONDS_HOUR:02d}h"


def agents_payload() -> dict:
    """Every live workspace with its state refreshed from git, plus the register read."""
    rows = []
    for live in workspaces.list_live():
        # get() is what makes the state worth printing: a tree clean at creation and
        # carrying edits now reports `dirty` without a full list call.
        fresh = workspaces.get(live.id) or live
        rows.append({**fresh.as_dict(), "age_seconds": _age_seconds(fresh.created_at)})
    return {"count": len(rows), "register": str(workspaces.register_file()), "workspaces": rows}


def render_agents(payload: dict) -> list[str]:
    rows = payload["workspaces"]
    if not rows:
        return [f"no live workspaces (register {payload['register']})"]
    noun = "workspace" if payload["count"] == 1 else "workspaces"
    lines = [f"{payload['count']} live {noun} (register {payload['register']})"]
    for row in rows:
        lines.append(
            f"{row['id']}  {row['owner']}  {row['state']}  age {age_text(row['age_seconds'])}"
        )
    return lines


def run_agents(*, as_json: bool) -> int:
    payload = agents_payload()
    _emit(payload, render_agents(payload), as_json)
    return 0


# ephe changes


def resolve_workspace(token: str) -> str:
    """The workspace root a token names: a live tree's id, else a directory on disk."""
    text = str(token or "").strip()
    if not text:
        raise IsolationError(
            "a workspace is an id or a path",
            "ephe changes <workspace>   (ids come from `ephe agents`)",
            code=2,
        )
    tree = workspaces.get(text)
    if tree is not None:
        return tree.path
    path = Path(text).expanduser()
    if path.is_dir():
        return str(path.resolve())
    raise IsolationError(
        f"unknown workspace {text!r}: no live tree carries that id and no directory is there",
        "use an id from `ephe agents`, or the path of a workspace",
    )


def changes_payload(workspace: str) -> dict:
    """A workspace's stored change sets, newest first, exactly as ``core.change_set`` holds them."""
    from core import change_set_read

    root = resolve_workspace(workspace)
    rows = []
    for change in change_set_read.list_for(root):
        rows.append({
            "id": change.id,
            "state": change.state,
            "summary": change.summary,
            "created_at": change.created_at,
            "file_count": len(change.files),
            "files": [
                {"path": file.path, "op": file.op, "diff_sha": file.diff_sha}
                for file in change.files
            ],
        })
    return {"workspace": root, "count": len(rows), "change_sets": rows}


def render_changes(payload: dict) -> list[str]:
    rows = payload["change_sets"]
    if not rows:
        return [f"no change sets for {payload['workspace']}"]
    noun = "change set" if payload["count"] == 1 else "change sets"
    lines = [f"{payload['count']} {noun} for {payload['workspace']} (newest first)"]
    for row in rows:
        files = "file" if row["file_count"] == 1 else "files"
        lines.append(
            f"{row['id']}  {row['state']}  {row['file_count']} {files}  "
            f"{row['created_at']}  {row['summary']}"
        )
        for entry in row["files"]:
            lines.append(f"    {entry['op']:<7} {entry['path']}  {short_sha(entry['diff_sha'])}")
    return lines


def run_changes(workspace: str, *, as_json: bool) -> int:
    payload = changes_payload(workspace)
    _emit(payload, render_changes(payload), as_json)
    return 0


# ephe review


def parse_reason(text: str) -> gate.Reason:
    """One ``path:line:why`` flag as the gate reads a location; a malformed one is a usage error."""
    raw = str(text or "")
    path, _, rest = raw.partition(":")
    line_text, _, why = rest.partition(":")
    if not path.strip() or not why.strip() or not line_text.strip().isdigit():
        raise IsolationError(
            f"a reason is path:line:why, got {raw!r}",
            "--reason core/change_set.py:120:the digest ignores the rename case",
            code=2,
        )
    try:
        return gate.Reason(path=path.strip(), line=int(line_text.strip()), why=why.strip())
    except gate.ReviewGateError as exc:
        raise IsolationError(str(exc), "--reason <path>:<line>:<why>, line above zero", code=2) from exc


def load_change_set(change_set_id: str) -> store.ChangeSet:
    """The stored change set, or a refusal naming the store it was looked for in."""
    found = store.load(str(change_set_id or "").strip())
    if found is None:
        raise IsolationError(
            f"no change set {change_set_id!r} in {store.CHANGESETS_DIR}",
            "list them with `ephe changes <workspace>`",
        )
    return found


def author_of(change: store.ChangeSet) -> str:
    """The author the change set records: the agent that wrote it, else the session that did."""
    author = (change.provenance.agent_id or change.provenance.session_id or "").strip()
    if not author:
        raise IsolationError(
            f"change set {change.id} records no author, so no verdict can name one",
            "its provenance carries neither an agent_id nor a session_id",
        )
    return author


def gate_change_set(change: store.ChangeSet) -> gate.ChangeSet:
    """The gate's view of a stored change set: its id, its author, the paths it touches."""
    return gate.ChangeSet(
        change_set_id=change.id,
        author=author_of(change),
        paths=tuple(file.path for file in change.files),
    )


def run_review(
    change_set_id: str,
    decision: str,
    reviewer: str,
    reasons: list[str],
    *,
    as_json: bool,
) -> int:
    verdict = DECISIONS.get(str(decision or "").strip())
    if verdict is None:
        raise IsolationError(
            f"unknown decision {decision!r}", f"one of {', '.join(DECISIONS)}", code=2
        )
    change = load_change_set(change_set_id)
    target = gate_change_set(change)
    try:
        recorded = _ledger().submit(target, verdict, reviewer, [parse_reason(r) for r in reasons])
    except gate.ReviewGateError as exc:
        raise IsolationError(
            str(exc),
            "nothing was recorded: a verdict needs a reason inside the change set and a "
            "reviewer other than its author",
        ) from exc
    moved = (
        change
        if change.state == PUBLISHED
        else (store.set_state(change.id, STATE_AFTER[verdict]) or change)
    )
    noun = "reason" if len(recorded.reasons) == 1 else "reasons"
    headline = f"{recorded.verdict} recorded for {recorded.change_set_id} by {recorded.reviewer}"
    lines = [f"{headline} ({len(recorded.reasons)} {noun})"]
    lines += [f"    {reason.where()}  {reason.why}" for reason in recorded.reasons]
    if moved is change and change.state == PUBLISHED:
        lines.append(f"{change.id} stays published: a verdict cannot unwrite a landed change set")
    else:
        lines.append(f"{change.id} state: {change.state} -> {moved.state}")
    payload = {**recorded.to_dict(), "state": moved.state}
    _emit(payload, lines, as_json)
    return 0


# ephe publish


def gate_refusal(target: gate.ChangeSet) -> str:
    """Why the gate will not let this change set publish, in the gate's own terms."""
    latest = _ledger().decide(target)
    if latest is None:
        return "no verdict is recorded"
    if latest.verdict != gate.APPROVE:
        return f"the latest verdict is {latest.verdict} by {latest.reviewer}"
    if latest.reviewer == target.author:
        return f"the approve is {latest.reviewer}'s own change set, which the gate refuses"
    return f"the verdict on record was filed against someone other than {target.author}"


def publish_lines(change: store.ChangeSet, result, target: str, dry_run: bool, state: str) -> list[str]:
    """``PublishResult`` as lines: the module's own sentence, the paths, and nothing invented."""
    lines = [f"{change.id} -> {target}: {result.reason or 'no reason reported'}"]
    lines += [f"    {path}" for path in result.applied]
    if result.rolled_back:
        noun = "file" if len(result.rolled_back) == 1 else "files"
        lines.append(f"rolled back before the ref moved ({len(result.rolled_back)} {noun}):")
        lines += [f"    {path}" for path in result.rolled_back]
    if dry_run:
        lines.append("dry run: no ref moved and no object was promoted into the real store")
    elif not result.ok:
        lines.append("nothing landed: the target ref, its tree and the real object store are unchanged")
    else:
        lines.append(f"{change.id} state: {change.state} -> {state}")
    return lines


def run_publish(change_set_id: str, *, target: str, dry_run: bool, as_json: bool) -> int:
    change = load_change_set(change_set_id)
    if change.state == PUBLISHED:
        raise IsolationError(
            f"{change.id} is already {PUBLISHED}: its files are on the branch it landed on, "
            "and publishing it again would commit an unchanged tree",
            "build the next edit into a new change set; a second landing needs its own id",
        )
    target_set = gate_change_set(change)
    if not _ledger().may_publish(target_set):
        raise IsolationError(
            f"{change.id} may not publish: {gate_refusal(target_set)}",
            f"ephe review {change.id} approve --reviewer <reviewer> --reason <path:line:why>",
        )
    refusal = preflight.refusal(change)
    if refusal is not None:
        raise IsolationError(
            f"{change.id} may not publish [{refusal.code}]: {refusal.reason}", refusal.fix
        )
    result = publisher.publish(change, target=target, dry_run=dry_run)
    state = change.state
    if result.ok and not dry_run:
        state = (store.set_state(change.id, PUBLISHED, published_oid=result.oid) or change).state
    payload = {
        "change_set": change.id,
        "target": target,
        "dry_run": dry_run,
        "ok": result.ok,
        "applied": result.applied,
        "rolled_back": result.rolled_back,
        "reason": result.reason,
        "oid": result.oid,
        "state": state,
    }
    _emit(payload, publish_lines(change, result, target, dry_run, state), as_json)
    return 0 if result.ok else 1


# ephe reap


def run_reap(*, older_than: float | None, as_json: bool) -> int:
    grace = workspaces.DEFAULT_REAP_MINUTES if older_than is None else float(older_than)
    if grace < 0:
        raise IsolationError(
            f"--older-than needs zero or more minutes, got {grace:g}",
            f"--older-than 30; the default is {workspaces.DEFAULT_REAP_MINUTES:g} minutes",
            code=2,
        )
    reaped = workspaces.reap_orphans(grace)
    payload = {"grace_minutes": grace, "count": len(reaped), "reaped": reaped}
    if reaped:
        noun = "workspace" if len(reaped) == 1 else "workspaces"
        lines = [f"reaped {len(reaped)} orphaned {noun} (grace {grace:g}m)"]
        lines += [f"    {tree_id}" for tree_id in reaped]
    else:
        why = "every row is younger than the grace, or its owning process is still alive"
        lines = [f"no orphans to reap (grace {grace:g}m): {why}"]
    _emit(payload, lines, as_json)
    return 0


__all__ = [
    "DECISIONS", "DEFAULT_REAP_MINUTES", "PUBLISHED", "STATE_AFTER", "IsolationError", "age_text",
    "agents_payload", "author_of", "changes_payload", "gate_change_set", "gate_refusal",
    "load_change_set", "parse_reason", "publish_lines", "render_agents", "render_changes",
    "resolve_workspace", "run_agents", "run_changes", "run_publish", "run_reap", "run_review",
    "short_sha",
]
