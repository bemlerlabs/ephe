"""CLI seam for the work verbs `run` and `show` — from the terminal, without the app.

`ephe code` and `ephe goal` are batch entry points: they run the loop and print one record
at the end. `ephe run` is the other modality the coding-agent brief asks for
(``docs/CODING_AGENT_VS_PI_DESIGN.md``: interactive CLI, JSON one-shot, RPC, SDK) — it
streams the loop's phases, tool calls and answer to the terminal as they happen, keeps the
turn in a resumable session, and records the workspace's diff as a change set. `ephe show`
is the read half that closes the loop: it prints a stored change set's diff, so
`ephe show` / `ephe review` / `ephe publish` take a run to a landed change without the app.

What lives here is what a test reaches without a parser or an engine: the sink that turns
the loop's callbacks into terminal lines, the session read/write that makes a run
resumable, the change-set hand-off, and the change-set renderer. ``ephe_cli`` keeps the
argparse surface, the engine resolution and the exit codes — the split
``core/_cli_isolation.py`` uses.

Why this file and not ``core/change_set.py``: the store is at its 400-line cap, so the
renderer lives here. It regenerates each path's diff through the store's own readers rather
than a second git invocation — the text shown is then exactly the text the stored digest
covers, and ``store._head``/``store._status_entries``/``store._scope_of``/
``store._file_diff_text`` are read because they are that one source, not a private API.

Honesty rules: a run without a chosen engine does not start
(``ephe_cli.engine_for_headless_run``); ``--json`` leaves stdout for the single run record
and streams to stderr, as `ephe code` already does; a resume or a show against an unknown id
is refused with the id and the command that lists the real ones. A change set with no files
is not printed as one — a clean tree yields ``None`` and the caller says so in one line.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from core import change_set as store
from core._cli_common import short_sha
from core.types import Message

#: The coding directive `ephe run` shares with `ephe code`: plan, edit, verify.
CODING_DIRECTIVE = (
    "You are a coding agent working inside this workspace. "
    "Plan briefly, then implement: read the relevant files with read_file, "
    "edit with edit_file or write_file, and VERIFY with run_tests "
    "(pytest/vitest) until they pass. Keep changes minimal and focused."
)

#: How many characters of a tool argument or result one terminal line carries.
CLIP = 160


class RunError(RuntimeError):
    """A verb that cannot answer honestly: the refusal, and the command that would let it."""

    def __init__(self, message: str, fix: str = "", code: int = 1) -> None:
        super().__init__(message)
        self.fix = fix
        self.code = code


def _clip(text: Any) -> str:
    """One line's worth of a value: whitespace collapsed, over-long text ellipsised."""
    one = " ".join(str(text).split())
    return one if len(one) <= CLIP else one[: CLIP - 1] + "…"


def _emit(payload: dict, lines: list[str], as_json: bool) -> None:
    """One verb's answer: the payload under ``--json``, otherwise the lines a person reads."""
    if as_json:
        import json

        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for line in lines:
        print(line)


# the streaming sink: a run that prints as it happens


class StreamSink:
    """The loop's callbacks as terminal output, live.

    Phases and tool boundaries each get their own line; ``chunk`` writes the answer
    without added newlines so it appears token by token. With ``stream=False`` the answer
    is buffered and printed once at the end (``--no-stream``). Under ``--json`` every
    streamed line goes to stderr — stdout is reserved for the single run record.
    """

    def __init__(self, *, as_json: bool = False, stream: bool = True, out=None, err=None) -> None:
        self._out = out if out is not None else sys.stdout
        self._err = err if err is not None else sys.stderr
        self._json = as_json
        self._stream = stream
        self._buffer: list[str] = []
        self._mid_line = False

    def _write(self, text: str) -> None:
        sink = self._err if self._json else self._out
        sink.write(text)
        sink.flush()

    def _line(self, text: str) -> None:
        self._write(str(text) + "\n")

    def phase(self, text: str) -> None:
        self._line(f"◑ {text}")

    def tool_start(self, name: str, args: dict) -> None:
        self._line(f"→ {name} {_clip(args)}")

    def tool_done(self, name: str, result: str) -> None:
        self._line(f"✓ {name} {_clip(result)}")

    def chunk(self, text: str) -> None:
        if self._json:
            return  # the answer belongs in the record; progress is already on stderr
        if self._stream:
            self._write(text)
            self._mid_line = not text.endswith("\n")
        else:
            self._buffer.append(text)

    def finish(self) -> None:
        """Close a half-written line and flush a buffered answer, so the next print is clean."""
        if self._mid_line:
            self._write("\n")
            self._mid_line = False
        if not self._json and not self._stream and self._buffer:
            text = "".join(self._buffer)
            self._buffer.clear()
            self._write(text if text.endswith("\n") else text + "\n")


# sessions: a run that can be resumed


def _sessions():
    """The session store, imported lazily so a missing package fails only this verb."""
    from core import multi_session as ms

    return ms


def load_session(session_id: str) -> list[Message]:
    """The stored turns of one session, or ``RunError`` naming the store when unknown."""
    ms = _sessions()
    sid = str(session_id or "").strip()
    if not sid:
        raise RunError("`--resume` needs a session id.", "See ids with `ephe session list`.")
    if ms.get_session(sid) is None:
        raise RunError(
            f'session "{sid}" not found in {ms.SESSIONS_DIR}',
            "List the real ids with `ephe session list`.",
        )
    return ms.load_messages(sid)


def open_session(title: str) -> str:
    """Mint a session for a fresh run and make it active, so `--resume` can reach it."""
    ms = _sessions()
    entry = ms.create_session(title)
    ms.switch_to(str(entry["id"]))
    return str(entry["id"])


def persist_turn(session_id: str, task: str, answer: str) -> None:
    """Append this turn to the session, so the next `--resume` continues the thread."""
    if not str(session_id or "").strip():
        return
    ms = _sessions()
    history = ms.load_messages(session_id)
    history.append({"role": "user", "content": task})
    if str(answer or "").strip():
        history.append({"role": "assistant", "content": answer})
    ms.save_messages(session_id, history)


# the change set the run hands to the review loop


def record_change_set(workspace: str, *, session_id: str, why: str = "") -> store.ChangeSet | None:
    """The workspace's current diff as a draft change set, or None when the tree is clean.

    A path outside a git worktree raises ``RunError``, so the caller can report why the run
    recorded nothing instead of printing a set with zero files.
    """
    root = str(workspace or "").strip() or "."
    try:
        change_set = store.build(
            root,
            "ephe run: terminal session",
            {"session_id": session_id or "", "agent_id": "", "why": why or "the terminal run's diff"},
        )
    except store.ChangeSetError as exc:
        raise RunError(
            f"the workspace {Path(root).resolve()} holds no change to record: {exc}",
            "`ephe run` records a change set only inside a git worktree.",
        ) from exc
    return change_set if change_set.files else None


def change_set_lines(change_set: store.ChangeSet) -> list[str]:
    """The three commands that take the run's diff from here to a published tree."""
    return [
        f"change set {change_set.id}: {len(change_set.files)} file(s), state {change_set.state}",
        f"  see it:    ephe show {change_set.id}",
        f"  accept it: ephe review {change_set.id} approve --reviewer <you> --reason PATH:LINE:WHY",
        f"  land it:   ephe publish {change_set.id}",
    ]


def resume_lines(session_id: str) -> list[str]:
    """What to type to continue this thread — named only when the run kept one."""
    if not str(session_id or "").strip():
        return []
    return [f"session {session_id} — continue with: ephe run --resume {session_id} \"…\""]


def verifier_exit(output: str | None) -> int:
    """The verifier's own exit status, so a caller can branch on a run's outcome.

    ``[exit N]`` is the marker the record already reads; without one the goal loop's
    verdict decides, and an unmeasured verifier stays a pass — the same rule
    ``run_evidence.verifier_verdict`` applies to ``solved``.
    """
    from core.run_evidence import EXIT_RE, verifier_verdict

    found = EXIT_RE.search(output or "")
    if found:
        return int(found.group(1))
    return 1 if verifier_verdict(output, None) is False else 0


def plan_lines(
    choice: Any, *, workspace: str, resume: str, turns: int, stream: bool, verify: str | None
) -> list[str]:
    """What `--dry-run` prints: the engine, the tree and the resume target, nothing spent."""
    where = getattr(choice, "api_url", None) or "(the engine's own endpoint)"
    lines = [
        f"run plan:  {choice.provider} / {choice.model} @ {where}",
        f"workspace: {Path(str(workspace or '.')).resolve()}",
        f"resume:    {resume or 'a new session'} ({turns} prior turn(s))",
        f"stream:    {'live to the terminal' if stream else 'off — the answer prints once at the end'}",
    ]
    if verify:
        lines.append(f"verify:    {verify}")
    return lines


# ephe show: the read half of the accept loop


def regenerated_diffs(change_set: store.ChangeSet) -> list[dict]:
    """Each path's diff text, read the way the store's own ``build`` read the digest.

    ``core/change_set.py`` keeps a path's ``diff_sha`` and not its text, so the text is
    regenerated through the store's own readers. A path no longer part of the diff carries
    ``present: False`` — a stored set stays readable after the tree that made it moved.
    """
    root = store.worktree_root(change_set.workspace_id)
    head = store._head(root)
    live = {
        path: xy
        for _op, path, xy in store._status_entries(root, store._scope_of(change_set.workspace_id, root))
    }
    rows: list[dict] = []
    for change in change_set.files:
        xy = live.get(change.path)
        if xy is None:
            rows.append({"path": change.path, "op": change.op,
                         "diff_sha": change.diff_sha, "present": False, "text": ""})
            continue
        text = store._file_diff_text(root, change.path, tracked=xy != "??", head=head)
        rows.append({"path": change.path, "op": change.op,
                     "diff_sha": change.diff_sha, "present": True, "text": text})
    return rows


def load_change_set(change_set_id: str) -> store.ChangeSet:
    """The stored change set, or a refusal naming the store it was looked for in."""
    found = store.load(str(change_set_id or "").strip())
    if found is None:
        raise RunError(
            f"no change set {change_set_id!r} in {store.CHANGESETS_DIR}",
            "list them with `ephe changes <workspace>`",
        )
    return found


def show_payload(change_set_id: str) -> dict:
    """One stored change set with the unified diff each path currently contributes.

    The digests are the store's own; the text is regenerated from the worktree. A path that
    moved since the set was built is flagged as drifted rather than shown as if it still
    matched, and the provenance is printed too — a reviewer needs the author the gate holds
    a verdict against.
    """
    from core.change_set_read import verify_current

    change = load_change_set(change_set_id)
    provenance = change.provenance
    return {
        "id": change.id,
        "workspace": change.workspace_id,
        "summary": change.summary,
        "state": change.state,
        "created_at": change.created_at,
        "provenance": {
            "session_id": provenance.session_id,
            "agent_id": provenance.agent_id,
            "why": provenance.why,
        },
        "drift": verify_current(change),
        "files": regenerated_diffs(change),
    }


def render_show(payload: dict) -> list[str]:
    files = payload["files"]
    drifted = {str(row["path"]) for row in payload["drift"]}
    files_noun = "file" if len(files) == 1 else "files"
    provenance = payload["provenance"]
    author = provenance["agent_id"] or provenance["session_id"] or "no author recorded"
    lines = [
        f"{payload['id']}  {payload['summary']}  [{payload['state']}]",
        f"workspace {payload['workspace']}  ·  {len(files)} {files_noun}  ·  {payload['created_at']}",
        f"author    {author}  ·  why: {provenance['why'] or '—'}",
    ]
    if not files:
        lines.append("")
        lines.append("this change set touches no files")
        return lines
    for row in files:
        lines.append("")
        if not row["present"]:
            lines.append(
                f"--- {row['path']}  [{row['op']}]  {short_sha(row['diff_sha'])}  (gone from the tree)"
            )
            continue
        mark = "  (drifted since recorded)" if row["path"] in drifted else ""
        lines.append(f"--- {row['path']}  [{row['op']}]  {short_sha(row['diff_sha'])}{mark}")
        lines.extend(row["text"].splitlines() or ["(empty diff)"])
    if drifted:
        lines.append("")
        lines.append(
            f"{len(drifted)} path(s) drifted since this set was built — rebuild before you accept it:"
        )
        for row in payload["drift"]:
            now = short_sha(row["current"]) if row["current"] else "absent"
            lines.append(f"  {row['path']}: recorded {short_sha(row['recorded'])} now {now}")
    return lines


def run_show(change_set_id: str, *, as_json: bool) -> int:
    payload = show_payload(change_set_id)
    _emit(payload, render_show(payload), as_json)
    return 0
