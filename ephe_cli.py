"""Command line helper for the Ephe local web app."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import secrets
import shutil
import subprocess
import sys
import textwrap
import time
import webbrowser
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from core._cli_common import (  # noqa: F401
    _run,
    _json_get,
    _json_post,
    _venv_python,
    _print_check,
    _emit_error,
    _abort_url,
    _ask_url,
    _fetch_served_models,
    _probe_remote_engine,
    _parse_tool_args,
    resolve_task,
    EPHE_VERSION,
    GoalRunner,
    EngineChoice,
    LOCAL_OLLAMA,
    OPENAI_COMPAT,
    load_engine_config,
    save_engine_config,
    DEFAULT_PORT,
    LOCAL_OLLAMA_HOST,
    LOCAL_OLLAMA_BASE_URL,
    PROJECT_ROOT,
    MAX_VOICE_BYTES,
)
from core._cli_ollama import (  # noqa: F401
    _ollama_binary,
    _ollama_model_candidates,
    _ollama_env,
    _local_ollama_detected,
    _model_installed,
    _model_loadable,
    _wait_for_ollama_service,
    _ensure_ollama_service,
    _pull_model,
    _upgrade_ollama,
    _ollama_version_detail,
    _repair_repo,
    _repair_dependencies,
    _ensure_model_ready_for_start,
    ensure_pwa_built,
    _download_piper_voice,
)
from core._cli_onboarding import (  # noqa: F401
    _run_engine_onboarding,
    resolve_engine_choice,
    engine_for_headless_run,
    cmd_configure,
    cmd_tui,
)
from core import _cli_isolation as isolation

_COMPLETION_SHELLS = ("bash", "zsh", "fish")

#: The tag flag as the engine resolver reads it, in one wording for every verb that takes it.
MODEL_FLAG_HELP = "Model id hint within the chosen engine; it is not an engine choice"

#: The OpenAI-compatible engine listens beside the PWA, on a port of its own.
OPENAI_ENGINE_PORT = 8766


async def _init_cli_mcp() -> list[str]:
    """Attach the configured MCP servers to this CLI run (fail-tolerant).

    The in-process agent commands (`ephe code` / `ephe goal` / `ephe tool`) run
    their own event loop; the PWA server wires MCP in its lifespan, this path
    never did. Called on that loop on purpose: a stdio client's pipes are bound
    to the loop that spawned the child, so a separate asyncio.run() would leave
    a dead client behind. Without configured servers this returns [] at once.
    """
    try:
        from core.mcp_config import init_mcp_from_config

        return await init_mcp_from_config()
    except Exception:
        return []


def _run_doctor_repairs(args: argparse.Namespace) -> list[tuple[str, bool, str]]:
    repairs: list[tuple[str, bool, str]] = []
    if os.environ.get("OLLAMA_HOST") not in (None, "", LOCAL_OLLAMA_HOST, LOCAL_OLLAMA_BASE_URL):
        repairs.append(("Normalize OLLAMA_HOST", True, f"Ephe commands use {LOCAL_OLLAMA_HOST}; shell value is ignored"))

    repo_ok, repo_detail = _repair_repo()
    repairs.append(("Repair repo", repo_ok, repo_detail))

    deps_ok, deps_detail = _repair_dependencies()
    repairs.append(("Repair dependencies", deps_ok, deps_detail))

    if args.model:
        model_ok, model_detail = _ensure_model_ready_for_start(args.model)
        repairs.append((f"Repair model {args.model}", model_ok, model_detail))
    else:
        repairs.append(
            ("Repair model", False, "no model chosen — ephe configure, EPHE_MODEL or --model")
        )

    pwa_ok = ensure_pwa_built()
    repairs.append(("Repair PWA build", pwa_ok, "app/dist/index.html vorhanden" if pwa_ok else "PWA build not possible (see output)"))
    return repairs


def cmd_voice(args: argparse.Namespace) -> int:
    """R18: Piper-Stimmen verwalten (list/install) — lokale TTS opt-in."""
    from core.voice_config import list_installed_piper_voices, piper_binary_available

    if args.voice_command == "list":
        binary = piper_binary_available()
        print(f"piper binary: {'found' if binary else 'NOT found (brew install piper)'}")
        installed = list_installed_piper_voices()
        if installed:
            print("Installed voices:")
            for v in installed:
                print(f"  - {v}")
        else:
            print("No voices installed. Examples:")
            print("  ephe voice install en_US-amy-medium    # EN, medium")
            print("  ephe voice install de_DE-thorsten-medium # DE, medium")
        return 0

    if args.voice_command == "install":
        ok = True
        for name in args.voices:
            try:
                _download_piper_voice(name)
                print(f"OK: {name}")
            except Exception as exc:
                ok = False
                print(f"FAIL: {name}: {exc}")
        return 0 if ok else 1

    print("Usage: ephe voice list | ephe voice install <voice>...")
    return 2


def _doctor_image_endpoint() -> tuple[bool, str]:
    """R16: image-endpoint check for `ephe doctor`.

    Probes the effective endpoint (env > image.json > chat-engine fallback).
    When nothing is explicitly configured and LocalAI is reachable on the default
    port :8080, that is reported as an opt-in SUGGESTION — nothing is ever written.
    """
    import httpx

    from core.image_config import load_image_config
    from core.tools.image_tools import _image_endpoint

    explicit = bool(os.environ.get("EPHE_IMAGE_BASE_URL", "").strip()) or bool(
        load_image_config().base_url
    )
    base, key, _model = _image_endpoint()
    if not base:
        return False, "no endpoint configured (setup: docs/LOCAL_IMAGE_ENGINE.md)"

    headers = {"Authorization": f"Bearer {key}"} if key else {}

    def _probe(url: str) -> bool:
        try:
            return httpx.get(f"{url.rstrip('/')}/models", headers=headers, timeout=4.0).status_code == 200
        except Exception:
            return False

    if _probe(base):
        source = "explicitly configured" if explicit else "fallback: active chat engine"
        return True, f"{base} reachable ({source})"
    if not explicit and _probe("http://127.0.0.1:8080/v1"):
        return False, (
            "not configured — LocalAI detected at http://127.0.0.1:8080/v1; enable with: export EPHE_IMAGE_BASE_URL=http://127.0.0.1:8080/v1 (or Settings -> Engine -> Image endpoint)"
        )
    return False, f"{base} not reachable — /image returns an honest error (setup: docs/LOCAL_IMAGE_ENGINE.md)"


def _doctor_voice() -> tuple[bool, str]:
    """R18: voice check — active engine, Piper setup, Whisper availability."""
    from core.transcribe import is_whisper_available
    from core.voice_config import load_voice_config, resolve_tts_engine

    cfg = load_voice_config()
    try:
        engine = resolve_tts_engine()
    except RuntimeError as exc:
        return False, str(exc)
    whisper = is_whisper_available()
    stt = f"STT: whisper {cfg.stt_model}/{'auto' if cfg.stt_language == 'auto' else cfg.stt_language} {'OK' if whisper else 'missing (pip install faster-whisper)'}"
    if engine == "piper":
        return True, f"piper local ({cfg.piper_voice}) — {stt}"
    mode = "auto fallback" if cfg.tts_engine == "auto" else "opt-in"
    return True, (
        f"Edge cloud fallback ({mode}) — switch to local: brew install piper, "
        f"ephe voice install {cfg.piper_voice}, then tts_engine=piper — {stt}"
    )


def _make_recorder(entrypoint: str, *, task: str, choice, gate_posture: str, rep: int):
    """B1: a run recorder for the engine that was actually chosen.

    The engine arrives as the resolved ``EngineChoice`` — this reads it, it never
    picks one, and it never writes the endpoint into the record.
    """
    from core.run_evidence import RunRecorder, new_turn_id

    return RunRecorder(
        entrypoint=entrypoint, task=task, provider=choice.provider, model=choice.model,
        api_url=getattr(choice, "api_url", None), turn_id=new_turn_id(entrypoint),
        gate_posture=gate_posture, rep=rep,
    )


def _record_targets(args: argparse.Namespace) -> tuple[bool, str | None]:
    """B1: the ``(--json, --run-record)`` pair of the coding entry points.

    Read with defaults, because a caller that passes its own namespace (the tests
    driving `code`/`goal` directly) simply gets the human path it always had.
    """
    return bool(getattr(args, "json", False)), (getattr(args, "run_record", None) or None)


def _progress(text: str, *, as_json: bool) -> None:
    """Progress goes to stderr while ``--json`` owns stdout.

    The same rule the machine-readable subcommands already follow: stdout carries
    exactly one object, so a stray progress line would break every consumer piping
    the run into a parser.
    """
    print(text, file=sys.stderr if as_json else sys.stdout)


def _emit_run_record(record: dict, *, as_json: bool, record_path: str | None) -> None:
    """One JSON object on stdout in machine mode, the same object in a file when asked."""
    from core.run_record import dump_record, write_record

    if record_path:
        write_record(record, record_path)
    if as_json:
        print(dump_record(record))


def cmd_code(args: argparse.Namespace) -> int:
    """R22: `ephe code "<task>"` — agent loop for coding tasks in the workspace.

    react_loop with a coding directive: read → edit (edit_file/write_file)
    → verify (run_tests). Every mutating step goes through the approval gate
    + audit log (R23).

    B1 (`docs/CODING_AGENT_VS_PI_DESIGN.md` §3.5): ``--json`` prints exactly one
    machine-readable run record on stdout (progress goes to stderr) and
    ``--run-record <path>`` writes that same object to a file, so any later claim
    about the run is audited from the file instead of from a terminal."""
    import asyncio

    from core.react import react_loop

    task = resolve_task(args.task)
    if not task:
        print("Usage: ephe code \"<task>\"  (e.g. 'make the failing test in tests/test_x.py green')")
        return 2

    # I2-2: no silent default — without a chosen engine the run aborts instead of
    # hammering away at http://localhost:11434.
    choice = engine_for_headless_run(args, getattr(args, "model", None))
    as_json, record_path = _record_targets(args)
    verify = (getattr(args, "verify", None) or "").strip() or None
    recorder = _make_recorder(
        "code", task=task, choice=choice,
        # The loop runs without a policy here, so every mutating tool passes the chat
        # gate — the record names that posture instead of pretending the gate was off.
        gate_posture="chat-gate", rep=int(getattr(args, "rep", 0) or 0),
    )

    prompt = (
        "You are a coding agent working inside this workspace. "
        "Plan briefly, then implement: read the relevant files with read_file, "
        "edit with edit_file or write_file, and VERIFY with run_tests "
        "(pytest/vitest) until they pass. Keep changes minimal and focused.\n\n"
        f"Task: {task}"
    )
    _progress(f"◑ ephe code: {task}", as_json=as_json)

    async def _run() -> tuple[str, dict | None, str | None]:
        await _init_cli_mcp()
        answer = await react_loop(
            question=prompt, model=choice.model,
            turn_id=recorder.turn_id, on_phase=recorder.on_phase,
        )
        # Read the measured usage INSIDE the loop: it is a ContextVar the agent task
        # set, and asyncio.run hands its context back to nobody.
        from core.tools.session_ctx import get_measured_usage

        usage = get_measured_usage()
        from core.run_evidence import run_verifier

        check_output = await run_verifier(verify) if verify else None
        return answer, usage, check_output

    try:
        result, usage, check_output = asyncio.run(_run())
    except Exception as exc:
        _emit_run_record(
            recorder.build(
                answer="", verifier_command=verify,
                exception=f"{type(exc).__name__}: {exc}",
            ),
            as_json=as_json, record_path=record_path,
        )
        raise

    _emit_run_record(
        recorder.build(
            answer=result or "", measured_usage=usage,
            verifier_command=verify, verifier_output=check_output,
        ),
        as_json=as_json, record_path=record_path,
    )
    if not as_json:
        print(result or "(no result)")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """`ephe run "<task>"` — a run from the terminal that streams and can be resumed.

    The interactive sibling of `ephe code`: the loop's phases, tool calls and answer reach
    the terminal as they happen (the batch verbs print at the end), the turn is kept in a
    session so `--resume` continues the thread, and the workspace's diff is recorded as a
    change set so `ephe show` / `ephe review` / `ephe publish` close the loop from here.

    I2-2 still holds: without a chosen engine the run aborts with instructions instead of
    guessing an endpoint. `--json` keeps stdout for one run record and streams to stderr.
    """
    import asyncio

    from core import _cli_run as run_seam
    from core.react import react_loop

    task = resolve_task(args.task)
    if not task:
        print('Usage: ephe run "<task>"  (e.g. \'take the failing test in tests/test_x.py to green\')')
        return 2

    # I2-2: no silent default — without a chosen engine the run aborts, override or not.
    choice = engine_for_headless_run(args, getattr(args, "model", None))
    as_json, record_path = _record_targets(args)
    from core.engine_config import get_workspace_dir

    workspace = os.path.expanduser(getattr(args, "workspace", None) or get_workspace_dir())
    verify = (getattr(args, "verify", None) or "").strip() or None
    resume = (getattr(args, "resume", None) or "").strip()

    try:
        history = run_seam.load_session(resume) if resume else []
    except run_seam.RunError as exc:
        _emit_error(args, exc.code, str(exc), exc.fix)
        return exc.code

    if getattr(args, "dry_run", False):
        for line in run_seam.plan_lines(
            choice, workspace=workspace, resume=resume,
            turns=len(history) // 2, stream=not args.no_stream, verify=verify,
        ):
            print(line)
        return 0

    session_id = resume or run_seam.open_session(f"run: {task[:40]}")
    sink = run_seam.StreamSink(as_json=as_json, stream=not args.no_stream)
    recorder = _make_recorder(
        "run", task=task, choice=choice,
        # No approval policy here either, so every mutating tool passes the chat gate —
        # the record names that posture, the way `ephe code` names it.
        gate_posture="chat-gate", rep=int(getattr(args, "rep", 0) or 0),
    )
    sink.phase(f"ephe run: {task}")

    def _phase(text: str) -> None:
        # The recorder keeps the round count from the line the sink prints.
        sink.phase(text)
        recorder.on_phase(text)

    async def _go() -> tuple[str, dict | None, str | None]:
        await _init_cli_mcp()
        answer = await react_loop(
            question=task, model=choice.model, context=[dict(m) for m in history],
            turn_id=recorder.turn_id,
            on_chunk=sink.chunk, on_phase=_phase,
            on_tool_start=sink.tool_start, on_tool_done=sink.tool_done,
            extra_system_prompt=run_seam.CODING_DIRECTIVE,
        )
        from core.tools.session_ctx import get_measured_usage

        usage = get_measured_usage()
        from core.run_evidence import run_verifier

        check_output = await run_verifier(verify) if verify else None
        return answer, usage, check_output

    try:
        answer, usage, check_output = asyncio.run(_go())
    except Exception as exc:
        sink.finish()
        _emit_run_record(
            recorder.build(
                answer="", verifier_command=verify,
                exception=f"{type(exc).__name__}: {exc}",
            ),
            as_json=as_json, record_path=record_path,
        )
        raise
    sink.finish()

    try:
        change_set = run_seam.record_change_set(
            workspace, session_id=session_id, why=f"ephe run: {task[:80]}"
        )
        change_note = ""
    except run_seam.RunError as exc:
        change_set, change_note = None, str(exc)

    run_seam.persist_turn(session_id, task, answer or "")

    _emit_run_record(
        recorder.build(
            answer=answer or "", measured_usage=usage,
            verifier_command=verify, verifier_output=check_output,
        ),
        as_json=as_json, record_path=record_path,
    )
    for line in run_seam.resume_lines(session_id):
        _progress(line, as_json=as_json)
    if change_set is not None:
        for line in run_seam.change_set_lines(change_set):
            _progress(line, as_json=as_json)
    elif change_note:
        _progress(change_note, as_json=as_json)
    else:
        _progress(f"no change set: {workspace} holds no diff", as_json=as_json)
    if not verify:
        return 0
    # A CI step branches on this process's exit code, so it carries the check's own
    # status: a turn that answered but failed `--verify` is a failed run.
    status = run_seam.verifier_exit(check_output)
    _progress(f"verifier exit {status}: {verify}", as_json=as_json)
    return status


def cmd_goal(args: argparse.Namespace) -> int:
    """W16: `ephe goal "<goal>"` — autonomous goal loop with a check command.

    Pattern: goal prompt → agent (chat_with_tools, tools included) → fixed check
    command (default: pytest -q) → on failure an automatic re-turn with the error
    output, until max_turns or success (GoalRunner, core.goal_loop).

    B1: the check command IS the verifier of §2.2, so the record of a goal run
    carries its verdict, exit marker and bounded output next to the effort axes."""
    import asyncio

    task = resolve_task(getattr(args, "goal_task", None))
    check = (getattr(args, "check", None) or "pytest -q").strip() or "pytest -q"
    max_turns = int(getattr(args, "max_turns", 10) or 10)
    if not task:
        print('Usage: ephe goal "<target>" [--check "pytest -q"] [--max-turns 10]')
        return 2

    runner_cls = globals().get("GoalRunner")
    if runner_cls is None:
        from core.goal_loop import GoalRunner as runner_cls
    # I2-2: the same fail-closed path as `ephe tui` — a goal loop that calls local
    # Ollama unprompted is a promise without cover.
    choice = engine_for_headless_run(args, getattr(args, "model", None))
    as_json, record_path = _record_targets(args)
    recorder = _make_recorder(
        "goal", task=task, choice=choice,
        # GoalRunner passes an ApprovalPolicy to the registry: the gate runs for
        # every tool there, so the record says `cli-policy` and not `not-gated`.
        gate_posture="cli-policy", rep=int(getattr(args, "rep", 0) or 0),
    )
    runner = runner_cls(
        model=choice.model, check_command=check, max_turns=max_turns,
        turn_id=recorder.turn_id, on_phase=recorder.on_phase,
    )

    async def _run() -> tuple[object, dict | None]:
        await _init_cli_mcp()
        outcome = await runner.run(task)
        from core.tools.session_ctx import get_measured_usage

        return outcome, get_measured_usage()

    try:
        result, usage = asyncio.run(_run())
    except Exception as exc:
        _emit_run_record(
            recorder.build(answer="", verifier_command=check,
                           exception=f"{type(exc).__name__}: {exc}"),
            as_json=as_json, record_path=record_path,
        )
        raise

    _emit_run_record(
        recorder.build(
            answer=getattr(result, "answer", "") or "", measured_usage=usage,
            verifier_command=check, verifier_output=getattr(result, "check_output", "") or "",
            solved=bool(getattr(result, "success", False)), turns=int(getattr(result, "turns", 0) or 0),
        ),
        as_json=as_json, record_path=record_path,
    )
    status = "GOAL OK" if result.success else "GOAL FAILED"
    _progress(f"{status} after {result.turns} turn(s) — check command: {check}", as_json=as_json)
    if result.check_output:
        _progress(result.check_output.strip()[:2000], as_json=as_json)
    return 0 if result.success else 1


def _version_tuple(value: str) -> tuple[int, ...]:
    """The first three number blocks of a version string, without an extra dependency.

    Enough for the pin question "is the PyPI release newer than the rung we measured";
    suffixes (-rc1, .post) are deliberately ignored — a pre-release must not put the
    doctor into alarm mode.
    """
    parts: list[int] = []
    for chunk in (value or "").split(".")[:3]:
        digits = ""
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:  # "1.0" and "1.0.0" are the same level
        parts.append(0)
    return tuple(parts)


def _cell_pinned_ceiling() -> str | None:
    """The upper bound Ephe itself declares for `ephemora-cell`.

    Read from our own installed package metadata instead of a constant, so the doctor
    quotes the pin that is actually in force; None when the distribution metadata does
    not carry it (a source tree without an install).
    """
    import importlib.metadata

    for req in importlib.metadata.metadata("ephe").get_all("Requires-Dist") or []:
        if not req.startswith("ephemora-cell"):
            continue
        for part in req[len("ephemora-cell"):].split(";")[0].split(","):
            clause = part.strip()
            if clause.startswith("<") and not clause.startswith("<="):
                return clause[1:].strip()
    return None


def _local_chosen_tag() -> str:
    """The tag of a local-Ollama engine choice, "" when there is none to probe.

    doctor's model checks are `ollama show` + a local generate, so only the local
    class answers them; a remote engine's tag is not this host's business and no tag
    here means no tag was chosen — the product names none on the user's behalf.
    """
    try:
        from core.engine_config import LOCAL_OLLAMA, resolve_engine_choice

        choice = resolve_engine_choice(allow_prompt=False)
    except Exception:
        return ""
    if choice is None or choice.provider != LOCAL_OLLAMA:
        return ""
    return (choice.model or "").strip()


def _active_engine_choice() -> EngineChoice | None:
    """The engine the user chose (``engine.json`` or the engine env), or None.

    The counterpart of `_local_chosen_tag` for the whole choice rather than the local
    tag: doctor asks the engine that is actually configured, and a remote one has to
    be probed at its own endpoint. A resolver that refuses (`EngineNotConfigured`, an
    unreadable config) reads as "no choice" — a diagnostic never dies on it, and the
    caller then reports the local-Ollama rows it always did (W10-24).
    """
    try:
        from core.engine_config import resolve_engine_choice

        return resolve_engine_choice(allow_prompt=False)
    except Exception:  # noqa: BLE001 — doctor must never fail on the resolver
        return None


def _probe_active_remote_engine(api_url: str, model: str) -> tuple[bool, str]:
    """Key-aware reachability of an OpenAI-compatible endpoint.

    Delegates to the shared `core._cli_common._probe_remote_engine`, which now sends the
    same bearer token the chat path uses (env, keychain, else ``~/.ephe/engine.key``). It
    used to read ``{base}/models`` with no credential itself; a hosted endpoint answers that
    with 401 — reachable, yet reported as "not reachable" (measured against
    ``https://api.deepseek.com/v1`` on 2026-10-13, the endpoint this repository's own
    engine.json names). One implementation now serves doctor and `ephe start`.
    """
    return _probe_remote_engine(api_url, model)


def cmd_doctor(args: argparse.Namespace) -> int:
    repairs: list[tuple[str, bool, str]] = []
    if args.fix:
        repairs = _run_doctor_repairs(args)

    checks: list[tuple[str, bool, str]] = []
    # Rows that describe a path the user has not taken yet. They are printed beside every
    # other row and never decide the exit code: a valid remote engine must not fail this
    # box's plan because the box has no local Ollama (W10-24, 2026-10-13).
    informational: list[tuple[str, bool, str]] = []
    checks.append(("Python", sys.version_info >= (3, 11), sys.version.split()[0]))
    checks.append(("Project files", (PROJECT_ROOT / "app" / "index.html").exists(), str(PROJECT_ROOT)))

    engine = _active_engine_choice()

    local_models: list[str] = []
    model_ready = False
    if engine is not None and engine.provider != LOCAL_OLLAMA:
        # The chosen engine is not this box's Ollama, so asking the local CLI, service and
        # tag about it reports a working setup as broken. Probe the endpoint the engine
        # actually lives at, and name the local rows as "not chosen yet" instead of
        # MISSING. A chosen engine that does not answer stays a genuine failure.
        probe_model = (args.model or "").strip() or engine.model
        model_ready, engine_detail = _probe_active_remote_engine(engine.api_url or "", probe_model)
        checks.append(
            (
                f"Engine {engine.provider}",
                model_ready,
                f"{probe_model} @ {engine.api_url} — {engine_detail}",
            )
        )
        for name in ("Ollama CLI", "Ollama service"):
            informational.append(
                (name, True, "not chosen yet (informational) — the active engine is remote")
            )
    else:
        ollama = _ollama_binary()
        checks.append(("Ollama CLI", bool(ollama), ollama or "not in PATH"))

        tags = _json_get(f"{LOCAL_OLLAMA_BASE_URL}/api/tags")
        if tags is not None:
            local_models = [item.get("name", "") for item in tags.get("models", [])]
        checks.append(("Ollama service", tags is not None, LOCAL_OLLAMA_BASE_URL))

        probe_model = (args.model or "").strip() or _local_chosen_tag()
        if probe_model:
            model_installed = _model_installed(probe_model)
            model_detail = "run: ephe update --model " + probe_model
            if model_installed and tags is not None:
                model_ready, model_detail = _model_loadable(probe_model)
                if not model_ready:
                    model_detail = f"{model_detail}; repair: ollama pull {probe_model}"
            elif model_installed:
                model_detail = "installed; start Ollama to verify loadability"
            checks.append((f"Model {probe_model}", model_installed, "installed" if model_installed else model_detail))
            checks.append((f"Model {probe_model} load test", model_ready, model_detail))
        else:
            checks.append(
                ("Model", False, "no model chosen — ephe configure, EPHE_MODEL or --model")
            )

    server_health = _json_get(f"http://127.0.0.1:{args.port}/api/health")
    checks.append(("Ephe server", server_health is not None, f"http://127.0.0.1:{args.port}"))

    # E0 (Extensions v2) + H1: dependency watch for ephemora-cell — PyPI latest
    # against the installed version, WITH the pin. The ceiling is read from our own
    # installed metadata, so the doctor quotes the bound that is actually in force
    # rather than a copy that can drift. Why the hint stops there: Ephemora Cell is
    # our own product, so a BUSL rung binds nobody here — what a rung above the pin
    # costs is measurement. `core/cell_policy.policy_snapshot()` reports max_fuel,
    # memory, timeout and network to the settings card and this doctor under one
    # rule (report == enforced), and that rule only holds for the release whose
    # enforcement this codebase read. So a release above the ceiling is a
    # re-measurement decision: informational, and no install command.
    # Purely informational and fail-soft: neither offline nor outdated flips the exit code.
    try:
        import importlib.metadata as _im
        import json as _json
        import urllib.request as _ur

        _installed = _im.version("ephemora-cell")
        with _ur.urlopen(
            "https://pypi.org/pypi/ephemora-cell/json", timeout=4
        ) as _resp:
            _info = _json.load(_resp)["info"]
        _latest = _info["version"]
        _license = (_info.get("license") or "unknown")
        _ceiling = _cell_pinned_ceiling()
        if _installed == _latest:
            checks.append(("ephemora-cell", True, f"{_installed} (PyPI current)"))
        elif _ceiling and _version_tuple(_latest) >= _version_tuple(_ceiling):
            checks.append(
                (
                    "ephemora-cell",
                    True,
                    f"{_installed} (measured) — PyPI latest {_latest} is above the pinned "
                    f"{_ceiling} and carries {_license}; upgrade = re-measure the cell "
                    "policy first, see docs/SANDBOX_EXECUTION.md",
                )
            )
        else:
            checks.append(
                ("ephemora-cell", False, f"{_installed} installed — PyPI has {_latest}: uv lock && uv pip install -U ephemora-cell")
            )
    except Exception:  # noqa: BLE001 — the watch must never break doctor
        checks.append(("ephemora-cell", True, "watch skipped (offline?)"))

    # E1: CPython-Cell — is the pinned guest there, and is it the right one?
    # Fail-soft like the other optional checks: without a guest execute_code stays
    # in the kernel (named visibly in the result), and a broken guest declines on
    # every run by itself. So never affecting the exit code, but with an actionable hint.
    try:
        from core import cell_policy

        cell_ok, cell_detail = cell_policy.doctor_snapshot()
        checks.append(("CPython-Cell", cell_ok, cell_detail))
    except Exception as exc:  # noqa: BLE001 — doctor must never fail on the sandbox
        checks.append(("CPython-Cell", True, f"cell check skipped ({exc.__class__.__name__})"))

    # B-wave: environment mirror — the user's detected agent tools (read-only,
    # secret-free). Purely informational, so always OK.
    try:
        from core.environment_mirror import installed_tools

        tools = installed_tools()
        checks.append(
            (
                "Environment (agent tools)",
                True,
                ", ".join(tools) if tools else "none further detected",
            )
        )
    except Exception:  # noqa: BLE001 — the mirror must never break doctor
        checks.append(("Environment (agent tools)", True, "mirror skipped"))

    # W4 S2: integrity check skills-lock.json vs. disk — one structured line per
    # deviation (skills_lock_mismatch pack=... status=...).
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "generate_skills_lock", str(PROJECT_ROOT / "scripts" / "generate_skills_lock.py")
        )
        _gen = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_gen)
        lock_ok, lock_diffs = _gen.verify(PROJECT_ROOT)
        checks.append((
            "skills-lock.json",
            lock_ok,
            "51 packs match" if lock_ok else "; ".join(lock_diffs),
        ))
    except Exception as exc:  # noqa: BLE001
        checks.append(("skills-lock.json", False, f"skills_lock_mismatch pack=? status={exc}"))

    # R16: image endpoint — informational check (deliberately AFTER the server check
    # so it does not enter payload["ok"]): a text-only setup without an image
    # endpoint is valid; the check only suggests LocalAI as an opt-in.
    image_ok, image_detail = _doctor_image_endpoint()
    checks.append(("Image endpoint", image_ok, image_detail))

    # R18: voice — informational check like the image endpoint (no exit-code
    # influence): the auto engine reports honestly whether it is local (piper) or a cloud fallback.
    voice_ok, voice_detail = _doctor_voice()
    checks.append(("Voice (TTS)", voice_ok, voice_detail))

    # R16/R18/E1: the informative checks (Image/Voice/ephemora-cell/CPython-Cell) do
    # NOT flow into `ok` — a text-only or cloud-fallback setup is valid, and an
    # updatable optional package contradicts no working setup (offline-first: the
    # exit code may never hang on how far PyPI reaches). Previously the checks[:-1]
    # slicing freed only the LAST check; with two informative checks the image check
    # slipped back into the exit-code calculation.
    _INFORMATIVE_CHECKS = {"Image endpoint", "Voice (TTS)", "ephemora-cell", "CPython-Cell"}
    # The informational rows are printed and machine-readable like the rest, but only
    # `checks` decides `ok`: "not chosen yet" is a state, not a failure.
    display = checks + informational
    payload = {
        "ok": all(ok for name, ok, _ in checks if name not in _INFORMATIVE_CHECKS)
        and model_ready
        and all(ok for _, ok, _ in repairs),
        "repairs": [{"name": name, "ok": ok, "detail": detail} for name, ok, detail in repairs],
        "checks": [{"name": name, "ok": ok, "detail": detail} for name, ok, detail in display],
        "informational": [name for name, _ok, _detail in informational],
        "local_models": local_models,
        "server": server_health,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        if repairs:
            for name, ok, detail in repairs:
                _print_check(ok, name, detail)
            print("")
        for name, ok, detail in display:
            _print_check(ok, name, detail)
        if local_models:
            print("Models  " + ", ".join(local_models))
        total = len(display) + len(repairs)
        passed = sum(1 for _, ok, _ in display if ok) + sum(1 for _, ok, _ in repairs if ok)
        print(f"Summary: {passed}/{total} checks OK")
    return 0 if payload["ok"] else 1


def cmd_start(args: argparse.Namespace, config_path=None) -> int:
    # Brand: orb banner (docs/BRAND.md) — one glyph, version, stance.
    print(f"  ◍ Ephe {EPHE_VERSION} — local & private")
    # Sky 2: one orbit per server start — the ephemeris records WHEN
    # Ephe was alive, never WHAT happened (d/h/k/n, without content).
    try:
        from core import ephemeris as _em
        _em.record("session")
    except Exception:
        pass  # the sky must never block the start
    # Engine selection (one source for the CLI and the PWA): engine.json → engine
    # env → onboarding (TTY) → fail-closed. A --model tag only overrides the model
    # inside the engine this resolution already chose; it never picks an engine
    # itself. With no chosen engine the tag is dropped and the server enters setup
    # mode, so the chat stays closed until the user chooses one in the browser.
    from core.engine_config import EngineNotConfigured
    try:
        choice = resolve_engine_choice(
            config_path=config_path, configure=False, args=args
        )
    except (EngineNotConfigured, SystemExit):
        # PWA-first: starting the server must never hang on terminal onboarding.
        # Without engine.json/env the TTY is NOT blocked and the CLI names no engine
        # for the user (H4 closed, 2026-10-11): it spawns the server with NO engine
        # env, and run_server.py's own W19 path enters setup mode — chat stays
        # fail-closed until the Setup page persists a choice. The TTY onboarding
        # continues to live in `ephe configure` / `ephe tui`.
        choice = None
        print(
            "  ⓘ No engine configured — the PWA opens the onboarding "
            "and picks the engine in the browser."
        )
    if choice is not None and args.model and args.model != choice.model:
        from dataclasses import replace

        choice = replace(choice, model=args.model)
    if choice is not None:
        try:
            choice.apply_env()
        except EngineNotConfigured as exc:
            # A persisted choice can be incomplete (for example openai_compatible
            # without api_url). Fall back to setup mode with the field named instead
            # of aborting the start on an uncaught configuration error.
            print(f"  ✗ {exc}")
            print(f"  Fix: {exc.hint}")
            choice = None

    if choice is not None and not args.skip_model_check:
        # Non-blocking readiness checks: Ephe is engine-agnostic —
        # the server starts ALWAYS, and the PWA walks the user through the
        # engine selection (/api/setup/status → setup UI). Root cause: an
        # unreachable engine in engine.json must not have blocked the start,
        # because then the UI in which the user could pick a different
        # engine would be unreachable. Ollama is not installed and
        # no models are pulled — the user chooses (local/remote) themselves.
        if choice.provider == OPENAI_COMPAT and choice.api_url:
            ready, detail = _probe_active_remote_engine(choice.api_url, choice.model)
            if ready:
                _print_check(True, f"Engine {choice.model} reachable", detail)
            else:
                _print_check(False, f"Engine {choice.model} reachable",
                             f"{detail} — the server starts anyway; choose the engine/model in the app.")
        else:
            service_ok, service_detail = _ensure_ollama_service()
            if service_ok and _model_installed(choice.model):
                ready, detail = _model_loadable(choice.model)
                _print_check(ready, f"Model {choice.model} ready", detail)
            elif service_ok:
                _print_check(False, f"Model {choice.model} ready",
                             f"Model not installed — choose the model in the app or: ollama pull {choice.model}")
            else:
                _print_check(False, "Ollama Service",
                             f"{service_detail} — the server starts anyway; choose the engine in the app (or install Ollama: ollama.com).")

    # Ensure the PWA build exists (fresh-clone path): app/dist is git-ignored, so a
    # missing one would make / a fallback page. We build here before the server
    # starts — so `ephe start` serves the PWA from the very first call.
    ensure_pwa_built()

    env = os.environ.copy()
    env["OLLAMA_HOST"] = LOCAL_OLLAMA_HOST
    if choice is not None:
        env["EPHE_MODEL"] = choice.model
    env.setdefault("EPHE_LOCAL_OLLAMA_BASE_URL", LOCAL_OLLAMA_BASE_URL)
    host = "0.0.0.0" if args.lan else args.host
    env["EPHE_HOST"] = host
    env["EPHE_PORT"] = str(args.port)
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "run_server.py"),
        "--host",
        host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        cmd.append("--reload")

    if args.open:
        process = subprocess.Popen(cmd, cwd=PROJECT_ROOT, env=env)
        browser_host = "127.0.0.1" if host == "0.0.0.0" else host
        url = f"http://{browser_host}:{args.port}"
        for _ in range(30):
            if _json_get(f"{url}/api/health", timeout=1.0) is not None:
                webbrowser.open(url)
                break
            time.sleep(1)
        return process.wait()

    return _run(cmd, env=env).returncode


def _desktop_bundle_path(target_dir: Path) -> Path | None:
    """Find the built desktop bundle inside the Tauri target (platform-dependent).
    Tauri writes per Cargo profile: target/release/bundle/macos/… — the
    profile-less patterns stay for foreign layouts (tests, flat bundles)."""
    subs = (
        "macos/*.app",
        "appimage/*.AppImage",
        "deb/*.deb",
        "msi/*.msi",
        "nsis/*.exe",
    )
    for profile in ("bundle/", "*/bundle/"):
        for sub in subs:
            hits = sorted(target_dir.glob(profile + sub))
            if hits:
                return hits[0]
    return None


def _backend_listening(port: int = 8765, host: str = "127.0.0.1") -> bool:
    """True when the product server listens on host:port (TCP probe, fail-soft)."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False


def _spawn_backend(port: int = 8765) -> None:
    """Starts the product server detached (survives the CLI window)."""
    log_dir = Path.home() / ".ephe" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "desktop-backend.log", "ab") as log:
        subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            [sys.executable, str(PROJECT_ROOT / "run_server.py"), "--port", str(port)],
            cwd=PROJECT_ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _ensure_backend(port: int = 8765, timeout_s: float = 25.0) -> bool:
    """Is the backend running? Otherwise start it detached and wait for health.

    True = ready; False = start failed — the app opens anyway
    and shows the offline gate (chat stays fail-closed until engine + server are there).
    """
    if _backend_listening(port):
        return True
    try:
        _spawn_backend(port)
    except OSError:
        return False
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _backend_listening(port):
            return True
        time.sleep(0.5)
    return False


#: Where `ephe desktop` puts the app, and where the replaced one goes.
#: Module constants instead of literals so the path can be moved in tests.
APPLICATIONS_DIR = Path("/Applications")
TRASH_DIR = Path.home() / ".Trash"


def _app_stempel(bundle: Path) -> str:
    """Hash of the executable core — enough to recognise two identically spread
    .app bundles (the frontend part is inside that file)."""
    import hashlib

    bin_dir = bundle / "Contents" / "MacOS"
    try:
        kerne = sorted(p for p in bin_dir.iterdir() if p.is_file())
    except OSError:
        return ""
    if not kerne:
        return ""
    return hashlib.sha256(kerne[0].read_bytes()).hexdigest()


def _install_desktop_bundle(bundle: Path, destination: Path, trash: Path) -> Path:
    """One Ephe: put the built bundle where an app lives, and remove the build leftovers.

    The reason is the command itself: `ephe desktop` used to build and open
    `target/release/bundle/macos/Ephe.app`. Spotlight and Finder therefore know
    two app bundles — the installed one in Applications and the built one in the
    target folder (`…/bundle/macos/`). Re-registering does not help against that,
    it only finds login items; the duplicate *file* stays.

    An already installed bundle with identical content is not put
    in the trash a second time; the build leftovers disappear in both cases.
    """
    ziel = destination / bundle.name
    identisch = ziel.is_dir() and _app_stempel(ziel) == _app_stempel(bundle)
    if ziel.exists() and not identisch:
        trash.mkdir(parents=True, exist_ok=True)
        name = f"{ziel.stem}-vor-{time.strftime('%Y%m%d-%H%M%S')}{ziel.suffix}"
        ziel.rename(trash / name)
    if not identisch:
        shutil.copytree(bundle, ziel, symlinks=True)
    if bundle.exists() and bundle != ziel:
        shutil.rmtree(bundle, ignore_errors=True)
    return ziel


def _schreibe_desktop_konfig(
    project_root: Path, python: str, port: int = 8765, home: Path | None = None
) -> Path:
    """The line the app icon needs.

    `ephe desktop` always started the backend itself — from the Dock and from the
    desktop, opening the window only hit a closed door (reported as "Disconnected").
    The app now probes its port at start and starts what is written here: interpreter,
    project, port. Without this line it touches nothing.
    """
    ziel_dir = (home or Path.home()) / ".ephe"
    ziel_dir.mkdir(parents=True, exist_ok=True)
    pfad = ziel_dir / "desktop.json"
    pfad.write_text(
        json.dumps(
            {"python": python, "project_root": str(project_root), "port": port},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return pfad


def cmd_desktop(args: argparse.Namespace) -> int:
    """Desktop app (Tauri): `--dev` starts the live shell against the
    dev URL; otherwise build the release bundle and open the app. Fail-closed
    with actionable hints when the toolchain is missing."""
    npm = shutil.which("npm")
    if not npm:
        print("  ✗ npm not found — install Node.js: https://nodejs.org")
        return 1
    app_dir = PROJECT_ROOT / "app"
    if not (app_dir / "src-tauri" / "tauri.conf.json").is_file():
        print("  ✗ app/src-tauri/tauri.conf.json missing — incomplete checkout?")
        return 1

    if args.dev:
        if _ensure_backend():
            print("  ✓ Backend ready (127.0.0.1:8765)")
        else:
            print("  ⚠ Backend unreachable — the shell starts anyway (offline gate in the UI).")
        print("  Tauri dev shell (Ctrl+C stops it; Vite reload included)")
        return _run([npm, "run", "tauri", "dev"], cwd=app_dir).returncode

    if not shutil.which("cargo"):
        print("  ✗ cargo not found — install Rust: https://rustup.rs")
        return 1
    print("  … Tauri release build (the first build takes several minutes)")
    build = [npm, "run", "tauri", "build"]
    if not getattr(args, "dmg", False):
        # Default: only the .app — the DMG step (AppleScript window cosmetics in
        # the installer) needs Finder automation and must never block the start.
        build += ["--", "--bundles", "app"]
    r = _run(build, cwd=app_dir)
    if r.returncode != 0:
        return r.returncode
    bundle = _desktop_bundle_path(app_dir / "src-tauri" / "target")
    if bundle is None:
        print("  ⚠ Build finished, but no bundle found under src-tauri/target/bundle.")
        return 0
    print(f"  ✓ Desktop app built: {bundle}")
    if sys.platform == "darwin" and bundle.name.endswith(".app"):
        _schreibe_desktop_konfig(PROJECT_ROOT, sys.executable)
        if getattr(args, "install", True):
            try:
                bundle = _install_desktop_bundle(
                    bundle, APPLICATIONS_DIR, TRASH_DIR
                )
                print(f"  ✓ installed to {bundle} — build leftover removed, there is exactly one Ephe")
            except OSError as exc:
                print(f"  ⚠ Could not install ({exc}) — opening the build bundle instead.")
        if _ensure_backend():
            print("  ✓ Backend ready (127.0.0.1:8765)")
        else:
            print("  ⚠ Backend unreachable — the app starts anyway (offline gate in the UI).")
        subprocess.run(["open", str(bundle)], check=False)
    return 0


def cmd_sky(args: argparse.Namespace) -> int:
    """The ephemerides: orbits of the last days — WHEN, never WHAT."""
    from core import ephemeris as ephemeris  # function import: test seams stay monkeypatchable

    events = ephemeris.load(ephemeris.default_store())
    print(ephemeris.chart(events, days=args.days))
    return 0


def cmd_amber(args: argparse.Namespace) -> int:
    """Monthly crystal of the ephemeris as an amber file (JSON)."""
    from core import ephemeris as ephemeris

    month = args.month or datetime.now().strftime("%Y-%m")
    amber = ephemeris.crystallize(
        ephemeris.load(ephemeris.default_store()),
        month=month,
        amber_dir=Path.home() / ".ephe" / "amber",
    )
    print(f"◍ Bernstein {month}")
    print(f"  sitzungen  {amber['sitzungen']}")
    print(f"  werkzeuge  {amber['werkzeuge']}")
    print(f"  artefakte  {amber['artefakte']}")
    print(f"  bahnen     {amber['bahnen']}")
    print(f"  tage_aktiv {amber['tage_aktiv']}")
    print(f"  spitzstunde {amber['spitzstunde'] or '—'}")
    print(f"  abgelegt   ~/.ephe/amber/{month}.json")
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    """E4 Golden-Matrix: verify gate (default) or the pass³ measurement (--run)."""
    from core import plugin_golden as pg

    plugins_dir = PROJECT_ROOT / "plugins"
    if args.run is None:
        report = pg.verify_all(plugins_dir)
        total = 0
        fails = 0
        for row in report:
            total += row["cases"]
            mark = "✓" if not row["issues"] else "✗"
            if row["issues"]:
                fails += 1
            print(f"  {mark} {row['plugin']:<16} {row['cases']} cases")
            for issue in row["issues"]:
                print(f"      · {issue}")
        print(f"  ── {total} cases over {len(report)} plugins; {fails} plugins with findings")
        return 1 if fails else 0

    names = args.run or sorted(p.name for p in plugins_dir.iterdir() if (p / "ephe-plugin.json").is_file())
    out_dir = Path.home() / ".ephe" / "benchmarks"
    gate_failures = 0
    for name in names:
        pdir = plugins_dir / name
        if not (pdir / "ephe-plugin.json").is_file():
            print(f"  ✗ {name}: not a product plugin, expected plugins/{name}")
            gate_failures += 1
            continue
        rows = pg.pass3_matrix(pdir, runs=["1", "2", "3"], report=out_dir / f"{name}.json")
        rate = sum(1 for r in rows if r["pass3"]) / max(len(rows), 1)
        mark = "✓" if rate >= args.min_rate else "✗"
        if rate < args.min_rate:
            gate_failures += 1
        print(f"  {mark} {name:<16} pass³ {rate:.0%} ({sum(1 for r in rows if r['pass3'])}/{len(rows)}) → {out_dir / (name + '.json')}")
        for r in rows:
            if not r["pass3"]:
                print(f"      · {r['id']}: {r['passes']}/3")
    if gate_failures:
        print(f"  ✗ Gate FAILED: {gate_failures} plugin(s) below {args.min_rate:.0%}")
    else:
        print("  ✓ Gate passed")
    return 1 if gate_failures else 0


def cmd_update(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps({"ok": True, "message": "update gestartet"}, indent=2))
    if (PROJECT_ROOT / ".git").exists():
        _run(["git", "pull", "--ff-only"])

    installer = PROJECT_ROOT / "install.sh"
    if not installer.exists():
        _emit_error(args, 1, "install.sh not found", "Check the project directory or run `git pull`")
        return 1

    env = os.environ.copy()
    env["OLLAMA_HOST"] = LOCAL_OLLAMA_HOST
    if args.model:
        env["EPHE_MODEL"] = args.model
    env["EPHE_NO_START"] = "1"
    rc = _run(["bash", str(installer), "--no-start"], env=env).returncode
    if args.json:
        print(json.dumps({"ok": rc == 0, "exit_code": rc}, indent=2))
    return rc


def _completion_subcommands() -> list[str]:
    names = []
    for action in build_parser()._actions:
        if getattr(action, "choices", None) is not None:
            names = sorted(action.choices)
    return names or ["start", "doctor", "update", "tui", "completion"]


def _completion_script(shell: str, cmds: list[str]) -> str:
    joined = " ".join(cmds)
    if shell == "bash":
        return (
            f"# bash completion for ephe\n"
            f"_ephe_complete() {{\n"
            f"    local cur=\"${{COMP_WORDS[COMP_CWORD]}}\"\n"
            f"    COMPREPLY=( $(compgen -W '{joined}' -- \"$cur\") )\n"
            f"}}\n"
            f"complete -F _ephe_complete ephe\n"
        )
    if shell == "zsh":
        quoted = " ".join(f'"{c}"' for c in cmds)
        return (
            f"#compdef ephe\n"
            f"_ephe() {{\n"
            f"    local -a cmds\n"
            f"    cmds=({quoted})\n"
            f"    _describe 'command' cmds\n"
            f"}}\n"
            f"compdef _ephe ephe\n"
        )
    # fish
    return (
        f"# fish completion for ephe\n"
        f"complete -c ephe -f -n 'not __fish_use_subcommand' \\\n"
        f"  -a '{joined}' -d 'command'\n"
    )


def cmd_completion(args: argparse.Namespace) -> int:
    shell = (args.shell or "").lower()
    if shell not in _COMPLETION_SHELLS:
        _emit_error(
            args,
            2,
            f"Unknown shell: {shell!r}",
            f"Available: {', '.join(_COMPLETION_SHELLS)} (e.g. `ephe completion bash`)",
        )
        return 2
    print(_completion_script(shell, _completion_subcommands()), end="")
    return 0


def cmd_session(args: argparse.Namespace) -> int:
    """Phase 2 Item 7: multi-session management.

    Subcommands: list / new / switch / rm / rename.
    Lazy import of core.multi_session, so a missing package fails this subcommand alone.
    """
    try:
        from core import multi_session as ms
    except ImportError as e:
        _emit_error(
            args,
            1,
            f"Multi-session not available: {e}",
            "Install the complete package: `pip install -e .`",
        )
        return 1

    action = args.session_action
    as_json = getattr(args, "json", False)

    if action == "list":
        sessions = ms.list_sessions()
        if as_json:
            print(json.dumps(sessions, ensure_ascii=False, indent=2))
            return 0
        if not sessions:
            print("No sessions. Create one with `ephe session new <title>`.")
            return 0
        active_id = ms.get_active_id()
        print("Sessions (newest first):")
        for s in sessions:
            marker = "●" if s.get("id") == active_id else " "
            info = ms.session_info(s["id"]) or {}
            print(
                f" {marker} {s.get('id'):<8}  {s.get('title', '?'):<30}  "
                f"Nachrichten: {info.get('message_count', 0):>3}   "
                f"Update: {info.get('updated_at', '')[:19]}"
            )
        return 0

    if action == "new":
        if not args.title:
            _emit_error(
                args, 2,
                "`ephe session new` expects a title.",
                "Example: `ephe session new --title 'Projekt Alpha'`",
            )
            return 2
        entry = ms.create_session(args.title)
        ms.switch_to(entry["id"])
        if as_json:
            print(json.dumps(entry, ensure_ascii=False, indent=2))
        else:
            print(f"New session: {entry['id']} (\"{entry['title']}\")")
        return 0

    if action == "switch":
        if not args.id:
            _emit_error(
                args, 2,
                "`ephe session switch` expects a session id.",
                "See IDs with `ephe session list`.",
            )
            return 2
        if ms.get_session(args.id) is None:
            _emit_error(
                args, 2,
                f'Session "{args.id}" not found.',
                "IDs: `ephe session list`",
            )
            return 2
        ms.switch_to(args.id)
        if as_json:
            print(json.dumps({"active_id": ms.get_active_id()}, indent=2))
        else:
            print(f"Active session: {ms.get_active_id()}")
        return 0

    if action == "rm":
        if not args.id:
            _emit_error(
                args, 2,
                "`ephe session rm` expects a session id.",
                "See IDs with `ephe session list`.",
            )
            return 2
        if ms.get_session(args.id) is None:
            _emit_error(
                args, 2,
                f'Session "{args.id}" not found.',
                "IDs: `ephe session list`",
            )
            return 2
        ms.delete_session(args.id)
        if as_json:
            print(json.dumps({"deleted": args.id}, indent=2))
        else:
            print(f'Session "{args.id}" deleted.')
        return 0

    if action == "rename":
        if not args.id or not args.title:
            _emit_error(
                args, 2,
                "`ephe session rename` expects an ID and a new title.",
                "Example: `ephe session rename --id abc12345 --title 'new name'`",
            )
            return 2
        if ms.get_session(args.id) is None:
            _emit_error(
                args, 2,
                f'Session "{args.id}" not found.',
                "IDs: `ephe session list`",
            )
            return 2
        ms.rename_session(args.id, args.title)
        if as_json:
            print(json.dumps(ms.get_session(args.id), ensure_ascii=False, indent=2))
        else:
            print(f'Session "{args.id}" is now called "{args.title}".')
        return 0

    _emit_error(args, 2, f"Unknown session action: {action!r}",
               "Available: list · new · switch · rm · rename")
    return 2


def cmd_plugin(args: argparse.Namespace) -> int:
    """E4a: plugin management (list / enable / disable / install)."""
    from core import plugin_market, plugin_runtime
    from core.plugin_lifecycle import LifecycleError
    from core.plugin_store import load_catalog

    action = getattr(args, "action", "list")

    if action == "list":
        catalog = load_catalog()
        rows = []
        for seg in ("public", "personal"):
            for entry in catalog[seg]:
                name = str(entry["name"])
                rows.append(
                    (
                        name,
                        "on" if plugin_runtime.effective_enabled(name) else "off",
                        entry.get("version", "-"),
                    )
                )
        print(f"{'PLUGIN':<22} STATE  VERSION")
        for name, state, version in sorted(rows):
            print(f"{name:<22} {state:<6} {version}")
        return 0

    if action in ("enable", "disable"):
        pid = str(args.plugin_id)
        try:
            snapshot = plugin_runtime.lifecycle().set_enabled(
                pid, action == "enable", actor="cli", reason="cli plugin command"
            )
        except LifecycleError as exc:
            print(f"[error] {pid}: {exc.code} ({exc.detail})")
            return 1
        from core.skills import invalidate_skill_cache

        invalidate_skill_cache()
        print(
            f"{pid}: {snapshot.state.value} — takes effect on the next agent turn"
        )
        return 0

    if action == "install":
        pid = str(args.plugin_id)
        status = plugin_market.install_from_marketplace(
            pid,
            allow_local_trust=bool(getattr(args, "trust_local", False)),
        )
        if status["status"] == "extracted":
            suffix = " (local trust)" if status.get("warning") == "local_trust" else ""
            print(
                f"installed: {pid} (v{status.get('version', '?')}){suffix} — "
                "disabled until you enable it"
            )
            return 0
        reason = status.get("error") or status["status"]
        print(f"[error] install of '{pid}' failed: {status['status']} ({reason})")
        return 1

    print(f"[error] unknown plugin action: {action}")
    return 2


def cmd_import(args: argparse.Namespace) -> int:
    """E6: vendor-neutral reference-client import (plan first, --apply writes)."""
    from core import importer

    source = Path(str(args.source)).expanduser()
    if not source.is_dir():
        print(f"[error] source directory not found: {source}")
        return 2
    plan = importer.build_import_plan(source)
    print(f"Import plan for {source}:")
    print(f"  persona : {'YES — ' + plan['persona']['source_file'] if plan['persona']['found'] else 'not found'}")
    print(f"  skills  : {', '.join(s['name'] + ' (disabled)' for s in plan['skills']) or 'none'}")
    print(f"  mcp     : {', '.join(plan['mcp']['servers']) or 'none'}")
    print(f"  settings: {', '.join(plan['settings']['mapped']) or 'none mappable'}")
    if plan["settings"]["unmapped_keys"]:
        print(f"  unmapped: {', '.join(plan['settings']['unmapped_keys'])} (left out)")
    if not getattr(args, "apply", False):
        print("\nDry run — nothing written. Re-run with --apply to import.")
        return 0
    result = importer.apply_import(source)
    print(
        "\nApplied:"
        f"\n  persona written : {'yes' if result['persona'] else 'no (already present)'}"
        f"\n  skills imported : {', '.join(result['skills']) or 'none'} (DISABLED — enable in Settings → Skills)"
        f"\n  mcp servers     : {', '.join(result['mcp_servers']) or 'none new'}"
        f"\n  settings mapped : {', '.join(result['settings']) or 'none'}"
    )
    return 0


def cmd_tool(args: argparse.Namespace) -> int:
    """P0-1 E1: run a single tool deterministically (without an LLM loop).

    Conservative defaults (threat model E1):
        - SAFE tools (read-only): always allowed, no flag needed.
        - MUTATING/NETWORK tools:
            * --dry-run → preview only, no execution (the file is not touched)
            * --yes     → explicit approval, the tool runs
            * --no      → explicit refusal, the tool does NOT run
            * no flag + non-interactive TTY → BLOCKED (approval is mandatory)
    """
    import asyncio

    from core.tools.approval import ApprovalPolicy
    from core.tools.registry import execute_tool, get_tool_schemas

    try:
        tool_args = _parse_tool_args(args.arg)
    except ValueError as exc:
        _emit_error(args, 2, str(exc), "--arg expects key=value pairs")
        return 2

    # Build the conservative policy from the CLI flags.
    # --yes/--no contradict each other → argparse mutual exclusion
    # (parse-time) is the barrier; here we only derive the policy.
    policy = ApprovalPolicy(
        auto_approve=args.yes,
        dry_run=args.dry_run,
        interactive=False,  # CLI mode: --yes or --dry-run are the explicit levers
        declined=args.no,
    )

    async def _run() -> tuple[str | None, list[str]]:
        # CLI startup on this loop: attach the configured MCP servers before the
        # schema check, so a remote tool name is known here too. result is None
        # when the name is unknown; the second slot carries what is available.
        await _init_cli_mcp()
        schemas = {s.get("function", {}).get("name") for s in get_tool_schemas()}
        if args.tool_name not in schemas:
            return None, sorted(name for name in schemas if name)
        return await execute_tool(args.tool_name, tool_args, policy=policy), []

    try:
        result, available = asyncio.run(_run())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _emit_error(args, 1, str(exc) or "tool error", "Check the tool arguments")
        return 1

    # Schema check: tool exists + parameter name is correct
    if result is None:
        _emit_error(
            args, 1,
            f"Unbekanntes Tool: '{args.tool_name}'",
            "Available tools: " + ", ".join(available),
        )
        return 1

    if args.json:
        print(json.dumps({"tool": args.tool_name, "result": result}, ensure_ascii=False))
    else:
        print(result)

    # Exit-code contract:
    #   0 = executed, dry-run preview, or SAFE auto-approval
    #   1 = blocked by the approval policy (mutating, no --yes / --no / non-interactive)
    if result.startswith("[Denied]"):
        return 1
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Start the OpenAI-compatible engine (/v1/chat/completions)."""
    import uvicorn  # lazy import — keeps the startup budget small

    from server.openai import create_openai_app

    # I2-2: a port that hums without a chosen engine promises an engine
    # nobody selected.
    choice = engine_for_headless_run(args, getattr(args, "model", None))

    token = args.token
    if args.lan and not token:
        token = secrets.token_urlsafe(16)
    host = "0.0.0.0" if args.lan else args.host

    app = create_openai_app(api_token=token or None)
    print("  ─────────────────────────────────────")
    print(f"  Engine:  {choice.provider} / {choice.model}")
    print(f"  URL:     http://{host}:{args.port}/v1/chat/completions")
    print(f"  Models:  http://{host}:{args.port}/v1/models")
    if token:
        print(f"  Auth:    X-Auth-Token: {token}")
    else:
        print("  Auth:    none (localhost only — use --lan to require a token)")
    # Read the paths off the app just built: the banner used to print the PWA's
    # /api/docs, a route this engine app never serves.
    print(f"  Docs:    http://{host}:{args.port}{app.docs_url}")
    print(f"  Schema:  http://{host}:{args.port}{app.openapi_url}")
    print("  ─────────────────────────────────────\n")

    uvicorn.run(app, host=host, port=args.port, log_level="info")
    return 0


def cmd_memory_mcp(args: argparse.Namespace) -> int:
    """Wave D4b: `ephe memory-mcp` — Ephe's memory as an MCP server over stdio.

    Read-only by default: an outside agent may read but must not quietly write
    into long-term memory. --allow-write is the permission, --scope
    picks *one* brain (never all). The flags map 1:1 onto the module — a user
    should not have to learn two vocabularies for the same server.
    """
    from core.memory_mcp_server import main as serve_memory

    forwarded: list[str] = []
    if args.allow_write:
        forwarded.append("--allow-write")
    if args.read_only:
        forwarded.append("--read-only")
    if args.scope:
        forwarded += ["--scope", args.scope]
    return serve_memory(forwarded)


def _isolation_cmd(args: argparse.Namespace, run: Callable[[], int]) -> int:
    """Run one isolation verb; a refusal prints its cause and its fix, never a stack trace."""
    try:
        return run()
    except isolation.IsolationError as exc:
        _emit_error(args, exc.code, str(exc), exc.fix)
        return exc.code


def cmd_agents(args: argparse.Namespace) -> int:
    """Welle 1 "Isolation": what is running on this machine right now.

    The worktree register, read through core/_cli_isolation.py. An idle machine prints
    one line naming the register it read — a status verb does not invent a row.
    """
    return _isolation_cmd(args, lambda: isolation.run_agents(as_json=args.json))


def cmd_changes(args: argparse.Namespace) -> int:
    """Welle 1 "Isolation": the change sets one workspace has built, newest first.

    The argument is an id from `ephe agents` or the workspace path; the store is
    core/change_set.py, so the order and the digests are the store's own.
    """
    return _isolation_cmd(args, lambda: isolation.run_changes(args.workspace, as_json=args.json))


def cmd_show(args: argparse.Namespace) -> int:
    """The read half of the isolation story: one change set's diff, file by file.

    `ephe changes` lists the sets and their digests; this prints the diff those digests
    were taken from, regenerated from the worktree, so a reviewer can read a set without
    the app. The accept half stays `ephe review` + `ephe publish`.
    """
    from core import _cli_run as run_seam

    try:
        return run_seam.run_show(args.change_set, as_json=args.json)
    except run_seam.RunError as exc:
        _emit_error(args, exc.code, str(exc), exc.fix)
        return exc.code


def cmd_review(args: argparse.Namespace) -> int:
    """Welle 1 "Isolation": file a reviewer's verdict on one change set.

    Every verdict carries a located reason, and an author cannot approve its own work —
    both rules live in core/review_gate.py, which refuses the submission and records
    nothing. What it refuses, this prints verbatim.
    """
    return _isolation_cmd(
        args,
        lambda: isolation.run_review(
            args.change_set, args.decision, args.reviewer, args.reason, as_json=args.json
        ),
    )


def cmd_publish(args: argparse.Namespace) -> int:
    """Welle 1 "Isolation": move one approved change set onto a branch, atomically.

    The gate decides first; core/atomic_publish.py then applies every file or none and
    returns a PublishResult, which is printed field for field — applied paths, what an
    abort rolled back, and the module's own sentence.
    """
    return _isolation_cmd(
        args,
        lambda: isolation.run_publish(
            args.change_set, target=args.target, dry_run=args.dry_run, as_json=args.json
        ),
    )


def cmd_reap(args: argparse.Namespace) -> int:
    """Welle 1 "Isolation": adopt the registered trees whose owning process is gone.

    core/workspace_lifecycle.py deletes only inside its managed directory and only
    after the grace period; the ids it returns are the ones printed.
    """
    return _isolation_cmd(
        args, lambda: isolation.run_reap(older_than=args.older_than, as_json=args.json)
    )


def _mb(n: int) -> str:
    """Bytes as the one unit the store is read in — MB, one decimal."""
    return f"{n / (1024 * 1024):.1f} MB"


def _n(count: int, word: str) -> str:
    """`5 files` / `1 file` — the report counts files and tasks, and both read."""
    return f"1 {word[:-1]}" if abs(count) == 1 else f"{count} {word}"


def prune_report(stats: dict, keep: dict, result: dict, *, applied: bool) -> list[str]:
    """The prune verb's words — pure, so a test reads the lines the user reads.

    Nothing here recomputes what went: the two dicts are ``store_stats()`` before
    and ``prune_store()``'s answer, and every number printed is one of their
    fields. That matters for the count this verb is honest about — ``total``
    counts *files*, all three groups, and is larger than the task list, which is
    the ``registered_sessions`` beside it. Both are printed, named.
    """
    freed = int(result.get("bytes_freed") or 0)
    gone = len(result.get("deleted") or [])
    remaining = sum(int(v) for v in (result.get("remaining") or {}).values())
    bounds = ", ".join(f"{ns or 'registered'}<={int(n)}" for ns, n in keep.items())
    lines = [
        f"Session store: {stats.get('session_dir')}",
        (
            f"Holds {_n(int(stats.get('total') or 0), 'files')} "
            f"({_mb(int(stats.get('bytes') or 0))}): "
            f"{_n(int(stats.get('registered_sessions') or 0), 'tasks')} a list shows, "
            f"{_n(int(stats.get('unreachable_by_list') or 0), 'files')} no list reaches."
        ),
        f"Retention: {bounds} — the newest N per group stay, older files go.",
    ]
    if applied:
        lines.append(
            f"Deleted {_n(gone, 'files')}, freed {_mb(freed)}. "
            f"The store now holds {_n(remaining, 'files')}."
        )
    else:
        lines.append(
            f"Dry run: would delete {_n(gone, 'files')}, freeing {_mb(freed)}. "
            "Nothing was changed — repeat with --apply to do it."
        )
    return lines


def store_prune_report(result: dict, *, applied: bool) -> list[str]:
    """The config-dir store prune's words — the same dry-run-first contract, its own line.

    ``result`` is ``core.store_retention.prune_stores``'s answer. The build scratch is
    the store its count bounds; while no guest is installed the run declines instead of
    removing the only fast path back to one.
    """
    gone = len(result.get("deleted") or [])
    freed = int(result.get("bytes_freed") or 0)
    if applied:
        lines = [f"Build scratch: deleted {_n(gone, 'trees')}, freed {_mb(freed)}."]
    else:
        lines = [
            f"Build scratch: dry run — would delete {_n(gone, 'trees')}, freeing {_mb(freed)}."
        ]
    if result.get("declined"):
        lines.append(f"  {result['declined']}")
    return lines


def cmd_prune(args: argparse.Namespace) -> int:
    """Wave 4 "Retention": bound the session store — the caller `prune_store` lacked.

    Dry run first, always: the verb reports what the counts would free and touches
    nothing until `--apply` says so. The groups and their counts are the same ones
    `POST /api/sessions/prune` takes, read from `core/session_lifecycle.py` (so a
    default that moves there moves here too), and the run never removes the task
    the register marks active.
    """
    from core import session_lifecycle as life
    from core import store_retention

    keep: dict[str, int] = dict(life.DEFAULT_KEEP)
    if args.keep_rest is not None:
        keep["rest-"] = args.keep_rest
    if args.keep_pwa is not None:
        keep["pwa-"] = args.keep_pwa
    if args.keep_registered is not None:
        keep[""] = args.keep_registered

    stats = life.store_stats()
    result = life.prune_store(keep, dry_run=not args.apply)
    # The same deliberate, dry-run-first call bounds the config-dir caches the session
    # store's verb never reached — the build scratch is the largest store beside it
    # (core/store_retention.py); it declines while no guest is installed.
    stores = store_retention.prune_stores(dry_run=not args.apply)
    if args.json:
        print(
            json.dumps(
                {"store": stats, "keep": keep, "result": result, "config_stores": stores},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    for line in prune_report(stats, keep, result, applied=args.apply):
        print(line)
    for line in store_prune_report(stores, applied=args.apply):
        print(line)
    return 0


def _life_defaults() -> dict:
    """`core.session_lifecycle.DEFAULT_KEEP`, read where the parser needs it.

    The import stays inside the function, so the parser does not pull the store in
    for every verb. The retention defaults belong to the store; a copy kept here
    would be a second number that could drift from a run.
    """
    from core import session_lifecycle as life

    return life.DEFAULT_KEEP


def _named_subparser(
    parser: argparse.ArgumentParser, argv: list[str]
) -> argparse.ArgumentParser | None:
    """The subparser ``argv`` calls, when its first word names one."""
    if not argv:
        return None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices.get(argv[0])
    return None


def _usage_text(parser: argparse.ArgumentParser, argv: list[str], captured: str) -> str:
    """argparse's own text for the command the arguments named.

    Every failure the root parser reports prints its usage line, and that line lists
    all subcommands, so `ephe doctor --bogus` reads as a mistyped command rather than
    a mistyped flag. Re-running the named subparser on its own words lets argparse
    write the usage that belongs to it.
    """
    sub = _named_subparser(parser, argv)
    if sub is None:
        return captured
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stderr(buffer):
            sub.parse_args(argv[1:])
    except SystemExit:
        pass
    return buffer.getvalue() or captured


def _usage_message(text: str) -> str:
    """argparse's diagnostic line without its program prefix."""
    rows = [row for row in text.splitlines() if row.strip()]
    if not rows:
        return "invalid arguments"
    head, marker, tail = rows[-1].partition(": error: ")
    return (tail if marker else head).strip() or "invalid arguments"


def _parse_args(parser: argparse.ArgumentParser) -> argparse.Namespace:
    """Parse the call, with a usage error answered the way the caller asked for it.

    argparse writes to stderr and exits 2. A call that carried ``--json`` gets the
    same ``{"error": …}`` envelope every other failure uses; one that did not gets
    argparse's text for the command it typed.
    """
    argv = sys.argv[1:]
    captured = io.StringIO()
    try:
        with contextlib.redirect_stderr(captured):
            return parser.parse_args()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        if code == 0:  # --help and --version answered already
            raise
        text = _usage_text(parser, argv, captured.getvalue())
        if "--json" in argv:
            where = f"ephe {argv[0]} --help" if _named_subparser(parser, argv) else "ephe --help"
            _emit_error(
                argparse.Namespace(json=True), 2, _usage_message(text), f"See `{where}`"
            )
        else:
            sys.stderr.write(text if text.strip() else "ephe: error: invalid arguments\n")
        raise SystemExit(2) from None


def available_tool_names() -> list[str]:
    """The tool names this run may execute, sorted; empty when the registry cannot be read.

    Read through the same registry the execution path uses, so a plugin switch that
    hides a tool hides it from the help too.
    """
    try:
        from core.tools.registry import get_tool_schemas

        offered = {str(s.get("function", {}).get("name") or "") for s in get_tool_schemas()}
        return sorted(name for name in offered if name)
    except Exception:  # noqa: BLE001 — the help prints without the registry
        return []


class _ToolHelpParser(argparse.ArgumentParser):
    """A subparser that names the tools in its own help when asked to.

    The registry is read while the help is rendered, so `ephe --help` and a verb that
    is not `tool` never pay for the import.
    """

    def __init__(self, *args: Any, _lists_tools: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._lists_tools = _lists_tools

    def format_help(self) -> str:
        text = super().format_help()
        names = available_tool_names() if self._lists_tools else []
        if not names:
            return text
        listed = textwrap.fill(
            ", ".join(names), width=78, initial_indent="  ", subsequent_indent="  "
        )
        return f"{text}\nAvailable tools ({len(names)}):\n{listed}\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ephe",
        description="Ephe local assistant CLI",
        epilog=(
            "Examples:\n"
            "  ephe configure                 Choose the engine once (saved to ~/.ephe/engine.json)\n"
            "  ephe start                     Start the local web app (default port 8765)\n"
            "  ephe start --lan --open        Expose on LAN for QR mobile pairing, open browser\n"
            "  ephe doctor --fix              Check setup and repair safe local drift\n"
            "  ephe update                    Pull latest, reinstall deps, update model\n"
            "  ephe tui --model <tag>         Start the terminal UI on your own tag\n"
            "  ephe serve                      Run OpenAI-compatible engine (/v1/chat/completions)\n"
            "  ephe serve --lan                Expose engine on LAN with a generated auth token\n\n"
            "Exit codes:\n"
            "  0  success\n"
            "  1  runtime/repair failure\n"
            "  2  usage error (unknown flag or subcommand)\n"
            "  with --verify, `ephe run` exits with the verifier's own status"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ephe {EPHE_VERSION}",
    )
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_ToolHelpParser)

    start = sub.add_parser(
        "start",
        help="Start the local web app",
        description="Start the local PWA (offline-first by default; optional --lan for QR mobile pairing).",
    )
    start.add_argument("--host", default="127.0.0.1", help="Bind address (default: localhost)")
    start.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"Port (default: {DEFAULT_PORT})"
    )
    start.add_argument(
        "--model",
        default=None,
        help="Model tag within the chosen engine (engine.json or the engine env); "
             "it is not an engine choice — without a chosen engine the PWA starts in setup mode",
    )
    start.add_argument("--lan", action="store_true", help="Expose on the local network for QR mobile pairing")
    start.add_argument(
        "--reload",
        action="store_true",
        help="Restart the server on every file change (development mode)",
    )
    start.add_argument("--open", action="store_true", help="Open the browser after startup")
    start.add_argument("--skip-model-check", action="store_true", help="Start without Ollama/model preflight")
    start.set_defaults(func=cmd_start)

    # W4 S1: `web` is a pure alias onto the start path — parents=[start]
    # inherits every flag, no duplicated logic, identical func.
    web = sub.add_parser(
        "web",
        help="Alias for 'start' (local web app)",
        description="Alias of 'start' — same flags, same code path.",
        parents=[start],
        add_help=False,
    )
    web.set_defaults(func=cmd_start)

    # Desktop app (Tauri) — one command like the competition: `ephe desktop`.
    desktop = sub.add_parser(
        "desktop",
        help="Build, install to /Applications and open the desktop app (Tauri)",
        description=(
            "Build the Ephe desktop app (Tauri), install it to /Applications "
            "and open it — one Ephe on the Mac, not two. --dev runs the live "
            "dev shell instead (no release build)."
        ),
    )
    desktop.add_argument(
        "--dev", action="store_true", help="Live dev shell (no release build)"
    )
    desktop.add_argument(
        "--dmg",
        action="store_true",
        help="Also build the DMG (needs Finder automation; default: app bundle only)",
    )
    desktop.add_argument(
        "--no-install",
        dest="install",
        action="store_false",
        help=(
            "Open the freshly built bundle where it was built, instead of "
            "installing it to /Applications and removing the build residue "
            "(default installs, so the Mac has exactly one Ephe)."
        ),
    )
    desktop.set_defaults(func=cmd_desktop)

    sky = sub.add_parser(
        "sky",
        help="the Ephemeriden — orbits of the last days",
        description=(
            "The Ephemeriden show WHEN Ephe was alive, never WHAT happened. "
            "Each day is a line, its Spitzstunde the bright block."
        ),
    )
    sky.add_argument(
        "--days", type=int, default=7, help="window in days (default: 7)"
    )
    sky.set_defaults(func=cmd_sky)

    amber = sub.add_parser(
        "amber",
        help="monthly crystal of the ephemeris (Bernstein JSON)",
        description=(
            "Crystallises one month into Bernstein: monthly sums, active days, "
            "Spitzstunde — filed under ~/.ephe/amber/<month>.json."
        ),
    )
    amber.add_argument(
        "--month",
        default=None,
        help="month as YYYY-MM (default: the current month)",
    )
    amber.set_defaults(func=cmd_amber)

    bench = sub.add_parser(
        "bench",
        help="golden matrix: verify gate or pass³ measurement per plugin",
        description=(
            "Without --run: structural verify-gate check of every golden suite. "
            "With --run: pass³ measurement against the configured engine (target "
            "Opus 5.5 / GPT Astra 6) — reports under ~/.ephe/benchmarks/."
        ),
    )
    bench.add_argument(
        "--run",
        nargs="*",
        default=None,
        metavar="PLUGIN",
        help="run the pass³ measurement (optionally limited to plugins)",
    )
    bench.add_argument(
        "--min-rate",
        type=float,
        default=0.9,
        help="pass³ gate per plugin (default: 0.90)",
    )
    bench.set_defaults(func=cmd_bench)

    doctor = sub.add_parser(
        "doctor",
        help="Check local setup",
        description="Diagnose the local setup. --fix repairs safe drift (fast-forward, deps, Ollama).",
    )
    doctor.add_argument(
        "--model",
        default=os.environ.get("EPHE_MODEL") or None,
        help="Tag to probe; without it the chosen engine's tag is used, and with no "
             "choice at all doctor reports that instead of testing a model nobody named",
    )
    doctor.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"Port the local app is probed on (default: {DEFAULT_PORT})",
    )
    doctor.add_argument("--json", action="store_true", help="Machine-readable output")
    doctor.add_argument("--fix", action="store_true", help="Repair safe local drift: repo fast-forward, dependencies, Ollama service and model")
    doctor.set_defaults(func=cmd_doctor)

    code = sub.add_parser(
        "code",
        help="agent loop for code tasks in the workspace (R22)",
        description="Reads, edits and verifies code in the workspace — every mutating step with an approval gate.",
    )
    code.add_argument("task", nargs="*", help="Task in natural language; `-` or a pipe (stdin) supplies it instead")
    # An empty EPHE_MODEL means no hint: the model stays the one from engine.json/env.
    code.add_argument("--model", default=os.environ.get("EPHE_MODEL") or None, help=MODEL_FLAG_HELP)
    code.add_argument("--json", action="store_true", help="Machine-readable output")
    code.add_argument(
        "--run-record",
        default=None,
        metavar="PATH",
        help="write the run record JSON to PATH (B1)",
    )
    code.add_argument(
        "--verify",
        default=None,
        metavar="COMMAND",
        help="verifier command run after the loop; its exit decides `solved` (B1)",
    )
    code.add_argument("--rep", type=int, default=0, help="repetition index for pass^k grouping (B1)")
    code.set_defaults(func=cmd_code)

    run = sub.add_parser(
        "run",
        help="Run a task in the terminal, streaming live; resumable",
        description=(
            "A task run in this workspace where every phase, tool call and answer token\n"
            "streams to the terminal as it happens — the interactive sibling of `ephe code`,\n"
            "which prints its record at the end. The turn is kept in a resumable session\n"
            "(`--resume <id>` continues the same thread) and the workspace's diff is recorded\n"
            "as a change set, so `ephe show` reads it, `ephe review` accepts it and\n"
            "`ephe publish` lands it. `--dry-run` prints the plan and spends no turn."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run.add_argument(
        "task", nargs="*",
        help="Task in natural language; `-` or a pipe (stdin) supplies it instead",
    )
    # An empty EPHE_MODEL means no hint: the model stays the one from engine.json/env.
    run.add_argument("--model", default=os.environ.get("EPHE_MODEL") or None, help=MODEL_FLAG_HELP)
    run.add_argument(
        "--workspace", default=None, metavar="PATH",
        help="Tree the run edits and records a change set from (default: cwd)",
    )
    run.add_argument(
        "--resume", default=None, metavar="SESSION",
        help="Continue a saved session by id; without it a fresh session is opened",
    )
    run.add_argument(
        "--verify", default=None, metavar="COMMAND",
        help="Verifier command run after the loop; its exit decides `solved` (B1)",
    )
    run.add_argument(
        "--no-stream", action="store_true",
        help="Buffer the answer and print it once at the end instead of streaming it",
    )
    run.add_argument(
        "--dry-run", action="store_true",
        help="Resolve the engine and print the plan (engine, tree, resume) without a turn",
    )
    run.add_argument("--json", action="store_true", help="Machine-readable record on stdout; stream to stderr")
    run.add_argument(
        "--run-record", default=None, metavar="PATH",
        help="write the run record JSON to PATH (B1)",
    )
    run.add_argument("--rep", type=int, default=0, help="repetition index for pass^k grouping (B1)")
    run.set_defaults(func=cmd_run)

    goal = sub.add_parser(
        "goal",
        help="autonomous goal loop with a check command (W16)",
        description="target -> agent tools -> check command; on failure an automatic re-turn until max-turns or success.",
    )
    goal.add_argument(
        "goal_task", nargs="*",
        help="the goal in natural language; `-` or a pipe (stdin) supplies it instead",
    )
    goal.add_argument("--check", default="pytest -q", help="check command (default: pytest -q)")
    goal.add_argument("--max-turns", type=int, default=10, help="upper bound on turn repetitions")
    # An empty EPHE_MODEL means no hint: the model stays the one from engine.json/env.
    goal.add_argument("--model", default=os.environ.get("EPHE_MODEL") or None, help=MODEL_FLAG_HELP)
    goal.add_argument("--json", action="store_true", help="Machine-readable output")
    goal.add_argument(
        "--run-record",
        default=None,
        metavar="PATH",
        help="write the run record JSON to PATH (B1)",
    )
    goal.add_argument("--rep", type=int, default=0, help="repetition index for pass^k grouping (B1)")
    goal.set_defaults(func=cmd_goal)

    voice = sub.add_parser(
        "voice",
        help="Manage local Piper voices (R18 offline TTS)",
        description="list: shows binary and voice status. install: downloads Piper voices from the model repo (opt-in, network).",
    )
    voice.add_argument("voice_command", choices=["list", "install"])
    voice.add_argument("voices", nargs="*", help="Stimmen-Namen (locale-name-quality), z. B. en_US-amy-medium")
    voice.set_defaults(func=cmd_voice)

    update = sub.add_parser("update", help="Update repo, dependencies and local model")
    update.add_argument(
        "--model",
        default=os.environ.get("EPHE_MODEL") or None,
        help="Tag to pull; without it nothing is pulled — `ephe update` names no model "
             "on the user's behalf",
    )
    update.add_argument("--json", action="store_true", help="Machine-readable output")
    update.set_defaults(func=cmd_update)

    configure = sub.add_parser(
        "configure",
        help="Choose the engine once and save it (~/.ephe/engine.json)",
        description=(
            "Interactive engine selection (W18: no silent default).\n"
            "Without a saved engine.json — or an explicit engine env — the "
            "server and `ephe start` refuse to start with an actionable hint; "
            "this command is the way out. API keys are never persisted."
        ),
    )
    configure.add_argument(
        "--force",
        action="store_true",
        help="Re-run the selection even if an engine is already configured",
    )
    configure.set_defaults(func=cmd_configure)

    tui = sub.add_parser("tui", help="Start the terminal UI")
    tui.add_argument(
        "--model",
        default=None,
        help="Model tag within the chosen engine (engine.json, the engine env or onboarding); "
             "it is not an engine choice",
    )
    tui.add_argument(
        "--api-url",
        default=None,
        help="OpenAI-compatible engine base URL (e.g. http://your-engine-host:8000/v1) — "
        "an explicit engine. The tag must come from --model or EPHE_OPENAI_COMPAT_MODEL.",
    )
    tui.add_argument(
        "--configure",
        action="store_true",
        help="Force engine selection even if a config already exists",
    )
    tui.add_argument("--reset", action="store_true", help="Clear previous session on start")
    # P0-1 E1: approval flags (passed on by cmd_tui to the TUI)
    tui.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only; mutating tools are NOT executed (Approval-Gate)",
    )
    yes_no = tui.add_mutually_exclusive_group()
    yes_no.add_argument(
        "--yes",
        action="store_true",
        help="Explicitly approve execution of MUTATING/NETWORK tools",
    )
    yes_no.add_argument(
        "--no",
        action="store_true",
        help="Explicitly decline; MUTATING/NETWORK tools are NOT executed",
    )
    tui.set_defaults(func=cmd_tui)

    completion = sub.add_parser(
        "completion",
        help="Generate shell completions (bash | zsh | fish)",
    )
    completion.add_argument("shell", nargs="?", choices=_COMPLETION_SHELLS)
    completion.set_defaults(func=cmd_completion)

    session = sub.add_parser(
        "session",
        help="Multi-session management (list / new / switch / rm / rename)",
    )
    session.add_argument(
        "session_action",
        choices=["list", "new", "switch", "rm", "rename"],
        help="Action: list (show all), new (create), switch (activate), rm (delete), rename (rename)",
    )
    session.add_argument(
        "--id",
        default=None,
        metavar="ID",
        help="Session ID (for switch / rm / rename)",
    )
    session.add_argument(
        "--title",
        default=None,
        metavar="TITEL",
        help="Title (for new) or new title (for rename)",
    )
    session.add_argument("--json", action="store_true", help="Machine-readable JSON")
    session.set_defaults(func=cmd_session)

    serve = sub.add_parser(
        "serve",
        help="Run the OpenAI-compatible engine (/v1/chat/completions)",
    )
    serve.add_argument("--host", default="127.0.0.1", help="Bind address (default: localhost)")
    serve.add_argument(
        "--port", type=int, default=OPENAI_ENGINE_PORT,
        help=f"Port (default: {OPENAI_ENGINE_PORT})",
    )
    serve.add_argument("--lan", action="store_true", help="Expose on LAN with a generated auth token")
    serve.add_argument("--token", default=os.environ.get("EPHE_SERVE_TOKEN", ""), help="Require this X-Auth-Token for every request")
    serve.add_argument(
        "--model",
        # An empty EPHE_MODEL means no hint: the model stays the one from engine.json/env.
        default=os.environ.get("EPHE_MODEL") or None,
        help=MODEL_FLAG_HELP,
    )
    serve.set_defaults(func=cmd_serve)

    # Wave D4b: a memory door for foreign MCP agents. stdio, not HTTP — the
    # user starts the server themselves, the command line is the consent.
    memory_mcp = sub.add_parser(
        "memory-mcp",
        help="Serve this workspace's memory over MCP on stdin/stdout (read-only by default)",
        description=(
            "Speak MCP (JSON-RPC over stdio) against Ephe's memory: memory_search, "
            "memory_list, memory_stats are open; memory_store, memory_update and "
            "memory_delete need --allow-write. One scope per process — add the "
            "command to another agent's MCP config, and it reads what Ephe knows."
        ),
    )
    memory_mcp.add_argument(
        "--allow-write", action="store_true",
        help="let the connected agent store, correct and remove facts",
    )
    memory_mcp.add_argument(
        "--read-only", action="store_true",
        help="refuse writes even when EPHE_MEMORY_MCP_WRITE is set",
    )
    memory_mcp.add_argument(
        "--scope", default=None,
        help="workspace scope to serve (default: the active Ephe workspace)",
    )
    memory_mcp.set_defaults(func=cmd_memory_mcp)

    # P0-1 E1: deterministic tool mode
    tool = sub.add_parser(
        "tool",
        help="Execute a single tool with approval-gates (P0-1 E1: diff / --dry-run / --yes / --no)",
        description=(
            "Execute one tool deterministically (no LLM loop).\n"
            "Approval-gates (conservative defaults, Threat-Model E1):\n"
            "  SAFE tools (read-only)    → always allowed\n"
            "  MUTATING / NETWORK tools → require --yes or --dry-run\n\n"
            "Flags:\n"
            "  --dry-run  Show what WOULD happen; file is NOT touched\n"
            "  --yes      Explicitly approve and execute\n"
            "  --no       Explicitly decline (tool is NOT executed)\n"
            "  --arg K=V  Tool argument (repeatable, JSON-parsed)\n"
            "  --json     Machine-readable output\n\n"
            "Exit codes: 0 = executed / dry-run shown, 1 = blocked by the approval policy, 2 = usage error"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        _lists_tools=True,
    )
    tool.add_argument("tool_name", help="Tool name (see `ephe tool --help` for the list)")
    tool.add_argument(
        "--arg",
        action="append",
        dest="arg",
        default=[],
        metavar="KEY=VALUE",
        help="Tool argument (repeatable, value JSON-parsed if possible)",
    )
    tool.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only; the tool is NOT executed and no file is touched",
    )
    yes_no = tool.add_mutually_exclusive_group()
    yes_no.add_argument(
        "--yes",
        action="store_true",
        help="Explicitly approve execution of a MUTATING/NETWORK tool",
    )
    yes_no.add_argument(
        "--no",
        action="store_true",
        help="Explicitly decline; the tool is NOT executed",
    )
    tool.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    tool.set_defaults(func=cmd_tool)

    # E4a: Plugin marketplace + management
    plugin = sub.add_parser(
        "plugin",
        help="Manage plugins: list / enable / disable / install (marketplace)",
        description=(
            "List, toggle and install plugins.\n"
            "list       show catalog plugins with their enabled state\n"
            "enable     turn a plugin on  (affects the next agent turn)\n"
            "disable    turn a plugin off (its tools stop being offered)\n"
            "install    install an artifact from plugin-marketplace.json\n"
            "           (sha256-verified, manifest-validated, quarantined on error)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    psub = plugin.add_subparsers(dest="action", required=True)
    plist = psub.add_parser("list", help="List known plugins")
    plist.set_defaults(func=cmd_plugin)
    penable = psub.add_parser("enable", help="Enable a plugin")
    penable.add_argument("plugin_id", help="Plugin id from `ephe plugin list`")
    penable.set_defaults(func=cmd_plugin)
    pdisable = psub.add_parser("disable", help="Disable a plugin")
    pdisable.add_argument("plugin_id", help="Plugin id from `ephe plugin list`")
    pdisable.set_defaults(func=cmd_plugin)
    pinstall = psub.add_parser("install", help="Install a marketplace plugin")
    pinstall.add_argument("plugin_id", help="Plugin id from plugin-marketplace.json")
    pinstall.add_argument(
        "--trust-local",
        action="store_true",
        help="Explicitly trust an unsigned local artifact",
    )
    pinstall.set_defaults(func=cmd_plugin)

    # E6: vendor-neutral reference-client import
    imp = sub.add_parser(
        "import",
        help="Import settings/persona/skills/tool-servers from a reference client directory",
        description=(
            "Vendor-neutral switcher import: detects persona files, SKILL.md skill\n"
            "trees, tool-server configs and settings keys in a source directory and\n"
            "maps them onto Ephe's formats. Without --apply this is a dry plan —\n"
            "nothing is written. Applied skills land DISABLED; existing Ephe state\n"
            "is never overwritten."
        ),
    )
    imp.add_argument("source", help="Source directory of the other local agent setup")
    imp.add_argument("--apply", action="store_true", help="Write the import (default: plan only; --dry-run names it)")
    imp.add_argument(
        "--dry-run",
        dest="apply",
        action="store_false",
        default=False,
        help="The default, named: write nothing and print the plan",
    )
    imp.set_defaults(func=cmd_import)

    # Welle 1 "Isolation": the five verbs an operator running a wave needs from a terminal.
    # The module behind them is core/_cli_isolation.py; the stores they read are the worktree
    # register, the change-set store, the review ledger and the ref move.
    agents = sub.add_parser(
        "agents",
        help="List the live workspaces of this machine (id, owner, state, age)",
        description=(
            "One line per live workspace from the worktree register: its id, its owner,\n"
            "its state refreshed from git, and how long it has been there. An idle\n"
            "machine prints one line naming the register — no row is invented."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    agents.add_argument("--json", action="store_true", help="Machine-readable output")
    agents.set_defaults(func=cmd_agents)

    changes = sub.add_parser(
        "changes",
        help="List a workspace's change sets, newest first",
        description=(
            "The change sets one workspace has built, newest first, with each set's file\n"
            "count and the diff-sha of every path it touches. WORKSPACE is an id from\n"
            "`ephe agents` or a workspace path."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    changes.add_argument("workspace", metavar="WORKSPACE", help="Workspace id or path")
    changes.add_argument("--json", action="store_true", help="Machine-readable output")
    changes.set_defaults(func=cmd_changes)

    show = sub.add_parser(
        "show",
        help="Print one change set's unified diff, file by file",
        description=(
            "Print one stored change set's unified diff, regenerated from the worktree, so a\n"
            "reader sees what `ephe changes` names only by digest. A path that moved since the\n"
            "set was built is flagged as drifted rather than shown as if it still matched. The\n"
            "accept half stays `ephe review` (a located reason per verdict) and `ephe publish`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    show.add_argument("change_set", metavar="CHANGE_SET", help="Id from `ephe changes <workspace>`")
    show.add_argument("--json", action="store_true", help="Machine-readable output")
    show.set_defaults(func=cmd_show)

    review = sub.add_parser(
        "review",
        help="Record a reviewer's verdict on a change set",
        description=(
            "File one verdict against a stored change set. Every verdict carries at least\n"
            "one located reason (PATH:LINE:WHY) — the gate refuses a verdict without one —\n"
            "and an author cannot approve its own change set: both refusals are printed\n"
            "with the gate's own sentence, and nothing is recorded when it refuses.\n"
            "  approve            the change set may publish once nothing replaces this\n"
            "  request-changes    it goes back to its author; publish stays refused\n"
            "  reject             it is recorded as rejected"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    review.add_argument("change_set", metavar="CHANGE_SET", help="Id from `ephe changes <workspace>`")
    review.add_argument(
        "decision", choices=tuple(isolation.DECISIONS), help="What the review decides"
    )
    review.add_argument(
        "--reviewer", required=True, help="Who reached this verdict; never the author"
    )
    review.add_argument(
        "--reason",
        required=True,
        action="append",
        metavar="PATH:LINE:WHY",
        help="Repeatable; e.g. core/change_set.py:120:the digest ignores a rename",
    )
    review.add_argument("--json", action="store_true", help="Machine-readable output")
    review.set_defaults(func=cmd_review)

    publish = sub.add_parser(
        "publish",
        help="Publish one approved change set to a branch, atomically",
        description=(
            "Every file of the change set or none of them: the branch ref moves once, by\n"
            "compare-and-swap, and an abort leaves it, its tree and the object store where\n"
            "they were. The review gate decides first — without a recorded approve from\n"
            "someone other than the author nothing publishes, a dry run included, because a\n"
            "dry run that answers 'this would land' for a set the gate refuses answers the\n"
            "wrong question. `core.publish_readiness` then reads the state and the tree, so a\n"
            "set that does not stand in `approved`, one whose tree moved since it was recorded\n"
            "and one whose workspace is gone refuse with the code the Workspaces page refuses\n"
            "that same set with."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    publish.add_argument("change_set", metavar="CHANGE_SET", help="Id from `ephe changes <workspace>`")
    publish.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the identical tree, discard it, move nothing",
    )
    publish.add_argument("--target", default="main", help="Branch to publish to (default: main)")
    publish.add_argument("--json", action="store_true", help="Machine-readable output")
    publish.set_defaults(func=cmd_publish)

    reap = sub.add_parser(
        "reap",
        help="Remove the registered workspaces whose owning process is gone",
        description=(
            "Adopt the orphans: a register row whose owning process no longer exists, or\n"
            "whose create already failed, has its tree removed — never outside the managed\n"
            "directory, and never one younger than the grace period."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    reap.add_argument(
        "--older-than",
        type=float,
        default=None,
        metavar="MINUTES",
        help=f"Grace period in minutes (default: {isolation.DEFAULT_REAP_MINUTES:g})",
    )
    reap.add_argument("--json", action="store_true", help="Machine-readable output")
    reap.set_defaults(func=cmd_reap)

    # Wave 4 "Retention": the store's own verb, beside the isolation verbs. Dry run
    # is the default — a verb that frees files on the machine has to be told twice.
    prune = sub.add_parser(
        "prune",
        help="Bound the session store (dry run unless --apply)",
        description=(
            "Keep the newest N files per group and remove the rest. The groups are the\n"
            "REST mirror (one file per caller), the browser mirror (one per sync) and the\n"
            "registered tasks. Without --apply the run only reports what it would free.\n"
            "The task the register marks active is never removed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    prune.add_argument(
        "--keep-rest",
        type=int,
        default=None,
        metavar="N",
        help=f"Files to keep in the REST mirror (default: {_life_defaults()['rest-']})",
    )
    prune.add_argument(
        "--keep-pwa",
        type=int,
        default=None,
        metavar="N",
        help=f"Files to keep in the browser mirror (default: {_life_defaults()['pwa-']})",
    )
    prune.add_argument(
        "--keep-registered",
        type=int,
        default=None,
        metavar="N",
        help="Files to keep of the registered tasks (no default: left alone unless named)",
    )
    prune.add_argument(
        "--apply",
        action="store_true",
        help="Delete for real; without it — or with --dry-run — the run changes nothing",
    )
    prune.add_argument(
        "--dry-run",
        dest="apply",
        action="store_false",
        default=False,
        help="The default, named: report what would be freed and remove nothing",
    )
    prune.add_argument("--json", action="store_true", help="Machine-readable output")
    prune.set_defaults(func=cmd_prune)

    return parser


def _resolved_endpoint() -> str:
    """The endpoint the engine resolution picked, or this box's local Ollama."""
    choice = _active_engine_choice()
    url = (getattr(choice, "api_url", "") or "") if choice is not None else ""
    return (url or LOCAL_OLLAMA_BASE_URL).rstrip("/")


def _failure_fix(exc: BaseException) -> str:
    """The fix line for a failure that reached the top of the CLI.

    A resolver that refused carries its own instruction, and a transport failure is
    worth the endpoint that did not answer plus the two commands that lead out of it.
    Both say more than the message above them, which is what this line replaces.
    """
    hint = str(getattr(exc, "hint", "") or "").strip()
    if hint:
        return hint
    from core import provider_errors

    if provider_errors.classify(exc).kind is not provider_errors.ProviderFailureKind.TRANSPORT:
        return "Check the last output and try again"
    endpoint = _resolved_endpoint()
    where = f" {endpoint}" if endpoint else ""
    return (
        f"No engine answered{where} — run `ephe doctor` to check the setup, "
        "and `ephe configure` to point Ephe at a reachable engine."
    )


def main() -> None:
    parser = build_parser()
    args = _parse_args(parser)
    try:
        raise SystemExit(args.func(args))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        # One classifier for every surface: the CLI reports a provider failure with the
        # same stable code and exit code the serve and chat surfaces report.
        from core import provider_errors

        _emit_error(
            args, 1, str(exc) or "unexpected error",
            _failure_fix(exc), error=exc,
        )
        raise SystemExit(provider_errors.exit_code_for(exc)) from exc


if __name__ == "__main__":
    main()
