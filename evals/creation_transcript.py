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
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

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
) -> dict[str, str]:
    """The environment a proof server runs in: this engine, this root, this key, nowhere else.

    `EPHE_PORT` is the server's own port, and the route that accepts a local caller reads
    it to decide whether an `Origin` is one it holds; a harness that posted to a different
    number than the one it advertised would be refused by its own trust check.

    `EPHE_BUILTIN_PLUGINS_ROOT` points at an empty folder inside the run, so the plugin
    catalog a graded turn can read names no first-party bundle from the checkout (no
    absolute path from the working tree either). The folder is created here, because a
    run-owned root that does not exist would make the silence depend on a skip rule
    rather than on the run owning the root.
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
