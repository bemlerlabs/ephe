"""evals/creation_transcript.py — what one Creator turn leaves behind for the grader.

`evals/creation_runner.py` grades a transcript and a staging root somebody else produced,
and this module is the half that produces them from the frames of a live turn. It is the
part of the creation eval that spends an engine, so its two contracts are proved here
against replayed frames instead:

* a transcript is the shape `core.plugin_golden.grade` reads — the answer, then the
  `[EPHE-TOOL-EVENTS]` marker, then one line per call that returned. A sentence naming a
  tool stays on the answer side of that marker and earns nothing.
* the staging root a case is graded against holds the bundles that case's turn wrote and
  nothing from the case before it, because `evals.creation_checks.staged_bundles` refuses a
  subject count other than one.
* every round of a turn carries the user's request in its model input. A turn is a
  sequence of model calls, and a round whose messages no longer hold the request grades an
  engine that was never asked the question — the shape six of the 24 paid turns returned
  as "I don't see an actual request".

It also owns the run home's declaration: the guard rules a contributed name by the family
its manifest declares, so the bundles a case names have to be declared in the home the
turn runs in, not found by accident in the operator's install (`engine_environment`).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_manifest

#: The literal `core.plugin_golden._events` splits on. Read as a constant here so a change
#: to the golden contract shows up as a failing test rather than as a transcript that
#: quietly stops carrying any evidence at all.
MARKER = "\n[EPHE-TOOL-EVENTS]\n"

#: Names the product reaches other tools with. They are plumbing: the call underneath them
#: is the one a case asks about, so `tool_call` contributes its inner name and the search
#: that produced it contributes no line.
from core.tools.discovery import META_TOOL_NAMES

_OK_STATUSES = {"completed", "ok", "done", "success", None, ""}

#: The record `engine_environment` writes into the run home's builtin root. A grader that
#: reads it adopts the declaration the turn ran with.
DECLARATION_FILENAME = "declaration.json"


def _content_text(content: object) -> str:
    """One message's text, whether the provider carries a string or content parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
            elif part is not None:
                parts.append(str(part))
        return " ".join(parts)
    return "" if content is None else str(content)


def rounds_without_request(
    requests: list[dict], request: str
) -> list[dict[str, Any]]:
    """The rounds of one turn whose model input no longer holds the user's request.

    `requests` is what the engine was handed, in order: the probe keeps every payload of
    a turn, and each one carries the messages the provider received. A round is reported
    with its index and the roles it does carry, because a reader needs to see what the
    engine was given instead of the question. An empty `request` names no round: there is
    nothing to look for, and a zero-round turn has no model input at all.
    """
    wanted = str(request or "").strip()
    if not wanted:
        return []
    rows: list[dict[str, Any]] = []
    for index, payload in enumerate(requests):
        messages = payload.get("messages") if isinstance(payload, dict) else None
        kept = [message for message in (messages or []) if isinstance(message, dict)]
        carried = any(
            str(message.get("role") or "") == "user"
            and wanted in _content_text(message.get("content"))
            for message in kept
        )
        if carried:
            continue
        rows.append(
            {
                "round": index,
                "messages": len(kept),
                "roles": sorted({str(message.get("role") or "") for message in kept}),
            }
        )
    return rows


def declared_bundles(tool_names) -> tuple[str, ...]:
    """The shipped bundles whose manifests declare one of `tool_names`, by folder name.

    `core.tools.creator_guard.judge` rules a contributed name by the family its manifest
    declares, so a name's privilege exists only while a declaration does. The declaration
    the product ships is the first-party root, and this reads it directly instead of the
    root the current process happens to scan: a run home that carries these bundles then
    rules the names the run's cases grade, whether or not the operator installed anything.
    """
    from core.plugin_tools_contract import tool_claims

    wanted = {str(name) for name in (tool_names or ()) if name}
    if not wanted:
        return ()
    try:
        scanned = plugin_manifest.scan_plugins(plugin_manifest.BUILTIN_PLUGINS_ROOT)
    except OSError:
        return ()
    found: list[str] = []
    for entry in scanned:
        manifest = entry.get("manifest")
        if entry.get("error") or not isinstance(manifest, dict):
            continue
        if wanted & {claim.name for claim in tool_claims(manifest)}:
            found.append(Path(str(entry.get("dir") or "")).name)
    return tuple(sorted(set(found)))


def _fold(text: object) -> str:
    """One line per call: `core.plugin_golden._events` reads lines, so a result is folded."""
    return " ".join(str(text or "").split())


def _failed(status: object, result: object, code: str) -> bool:
    """Whether this call did not do the thing, asked of the product's own classifiers.

    The status field is the route's answer and `core.quality` is the audit's, and a
    transcript that disagreed with either would grade a refusal as a success.
    """
    from core.quality import is_error_result, result_decision

    text = str(result or "")
    if status not in _OK_STATUSES:
        return True
    if code:
        return True
    return bool(is_error_result(text) or result_decision(text) == "blocked")


def _inner_name(args: object) -> str:
    if isinstance(args, dict):
        return str(args.get("name") or "").strip().lower()
    return ""


def tool_events(events: list[dict]) -> list[tuple[str, str]]:
    """The calls a turn actually ran, as (name, line) pairs in the order they returned.

    A `tool_call` frame is replaced by the tool it dispatched; `tool_search` and
    `tool_describe` frames are dropped. A call that started and never returned is kept and
    says so, because a missing frame is a fact about the run.
    """
    started: dict[str, dict] = {}
    out: list[tuple[str, str]] = []
    for event in events:
        kind = event.get("type")
        name = str(event.get("tool") or "").strip().lower()
        call_id = str(event.get("call_id") or "")
        if kind == "tool_start":
            started[call_id] = event
            continue
        if kind != "tool_done":
            continue
        inner = _inner_name(started.get(call_id, {}).get("args")) if name == "tool_call" else ""
        subject = inner or name
        if not subject or subject in META_TOOL_NAMES:
            continue
        code = str(event.get("reason_code") or "")
        result = event.get("result")
        if _failed(event.get("status"), result, code):
            label = code or str(event.get("status") or "no_result")
            line = f"[tool {subject}] [tool-error {label}] {_fold(result)}".rstrip()
        else:
            line = f"[tool {subject}] {_fold(result)}".rstrip()
        out.append((subject, line))
    missing = [
        e for cid, e in started.items()
        if cid not in {str(e.get("call_id") or "") for e in events if e.get("type") == "tool_done"}
    ]
    for event in missing:
        name = str(event.get("tool") or "").strip().lower()
        inner = _inner_name(event.get("args")) if name == "tool_call" else ""
        subject = inner or name
        if not subject or subject in META_TOOL_NAMES:
            continue
        out.append((subject, f"[tool {subject}] [tool-error no_result] the call never returned"))
    return out


def answer_text(events: list[dict]) -> str:
    """The visible answer, in stream order, with nothing the tools said mixed into it."""
    parts: list[str] = []
    for event in events:
        kind = event.get("type")
        if kind == "chunk":
            parts.append(str(event.get("data") or ""))
        elif kind in ("assistant", "answer"):
            parts.append(str(event.get("text") or event.get("data") or ""))
    return "".join(parts).strip()


def build_transcript(events: list[dict]) -> str:
    """The transcript `grade()` reads for one turn: answer, marker, one line per call."""
    lines = [line for _, line in tool_events(events)]
    return f"{answer_text(events)}{MARKER}" + "\n".join(lines)


def bundles_root(config: Path | str | None = None) -> Path:
    """The staging folder the creator tools write into, read from the product itself."""
    from core.tools.creator_tools import bundles_root as product_bundles_root

    return product_bundles_root(config)


def take_staged_bundles(config: Path | str, dest: Path | str) -> list[str]:
    """Move what this turn staged into `dest` and leave the folder empty for the next one.

    The move is the isolation: the runner grades one subject per case, so a bundle that
    stayed behind would be counted twice, and a case that was refused has to be seen with
    an empty folder rather than its neighbour's output.
    """
    root = bundles_root(config)
    target = Path(dest)
    target.mkdir(parents=True, exist_ok=True)
    names = sorted(p.name for p in root.iterdir() if p.is_dir())
    for name in names:
        shutil.move(str(root / name), str(target / name))
    return names


def _read_key(key_file: Path | str) -> str:
    """The one line of the key file, or a refusal naming what was found instead.

    A multi-line file is not a key: the env would carry a trailing newline into an
    `Authorization` header and the engine would answer 401 for a mistake in this harness.
    """
    path = Path(key_file)
    if not path.is_file():
        raise ValueError(f"engine key file does not exist: {path}")
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError(f"engine key must be exactly one line, found {len(lines)} in {path}")
    return lines[0]


def engine_environment(
    *,
    key_file: Path | str,
    config_dir: Path | str,
    base_url: str,
    model: str,
    port: int,
    declared_bundles: object = (),
) -> dict[str, str]:
    """The environment a proof server runs in: this engine, this root, this key, nowhere else.

    `EPHE_PORT` is the server's own port, and the route that accepts a local caller reads
    it to decide whether an `Origin` is one it holds; a harness that posted to a different
    number than the one it advertised would be refused by its own trust check.

    `EPHE_BUILTIN_PLUGINS_ROOT` points at a folder inside the run, so the catalog a graded
    turn can read is a copy the run owns and never a path into the working tree. It carries
    exactly the `declared_bundles`, and `DECLARATION_FILENAME` records which ones. A name the cases grade
    needs its declaration to be ruled at all — `core.tools.creator_guard.judge` answers
    `network` for `fetch_url` only while a manifest declares it — so the run home declares
    the bundles its cases name instead of inheriting whatever the operator installed.
    """
    key = _read_key(key_file)
    config = Path(config_dir)
    persisted = config / "engine.json"
    if persisted.exists():
        raise ValueError(
            f"{persisted} chooses an engine of its own and outranks this environment; "
            "point config_dir at an empty root"
        )
    builtin_root = config / "builtin-plugins"
    builtin_root.mkdir(parents=True, exist_ok=True)
    declared = tuple(sorted({str(name) for name in (declared_bundles or ()) if name}))
    _declare_bundles(builtin_root, declared)
    env = dict(os.environ)
    env.update(
        {
            "EPHE_CONFIG_DIR": str(config),
            plugin_manifest.ENV_BUILTIN_PLUGINS_ROOT: str(builtin_root),
            "EPHE_MODEL_PROVIDER": "openai_compatible",
            "EPHE_OPENAI_COMPAT_BASE_URL": base_url,
            "EPHE_OPENAI_COMPAT_MODEL": model,
            "EPHE_OPENAI_COMPAT_API_KEY": key,
            "EPHE_PORT": str(port),
        }
    )
    return env


def _declare_bundles(builtin_root: Path, declared: tuple[str, ...]) -> None:
    """Copy the declared bundles into the run's own root, and record the list.

    A declaration whose bundle is missing from the product's first-party root is an error
    rather than a silently empty root: a case that grades the name would then read as
    unmeasurable turn after turn, and the run would not say why.
    """
    for name in declared:
        source = plugin_manifest.BUILTIN_PLUGINS_ROOT / name
        if not (source / plugin_manifest.MANIFEST_FILENAME).is_file():
            raise ValueError(
                f"the declared bundle {name!r} is not shipped at {source}; a run home "
                "can only declare a bundle the product ships"
            )
        target = builtin_root / name
        if not target.exists():
            shutil.copytree(source, target)
    (builtin_root / DECLARATION_FILENAME).write_text(
        json.dumps({"bundles": list(declared)}, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def adopt_declaration(config: Path | str) -> str:
    """Point this process at the declaration the turn ran with, and answer that root.

    The grader runs in the operator's process, whose roots are the operator's install and
    the checkout. A run home that recorded a non-empty declaration is the home the offer
    was built in, so the guard has to answer from it — otherwise the receipt grades the
    turn against a portfolio the turn never saw. A home that recorded nothing (an older
    run, a probe) is left alone and the product's own declaration stands.
    """
    root = Path(config) / "builtin-plugins"
    record = root / DECLARATION_FILENAME
    try:
        declared = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    bundles = declared.get("bundles") if isinstance(declared, dict) else None
    if not isinstance(bundles, list) or not bundles:
        return ""
    os.environ[plugin_manifest.ENV_BUILTIN_PLUGINS_ROOT] = str(root)
    from core.tools import creator_guard

    creator_guard.invalidate_family_map()
    return str(root)
