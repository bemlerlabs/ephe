"""
◑ Ephe – golden tests per plugin (E4, "measured, not promised")
core/plugin_golden.py

Every product plugin carries prompts/golden.jsonl — input → expected
artefact/behaviour, mechanically gradable. The matrix is measured with pass³
(3 runs per case, all must pass) against the engine named in the receipt;
a reference comparison is stated only after those models have run.

One golden case (one JSONL line, fail-closed):
  id        "<plugin>-<nr>"        unique, with the plugin prefix
  command   command name | null    must exist in the manifest
  input     the task (what the user would ask)
  expect    {"kind": …, …}         see KINDS — everything by string test
  note      optional, one sentence why

Kinds (mechanical, no model in the grader):
  artifact      <suffix> appears as an artefact path in the transcript
  tool_use      one of the tools in <any> was called
  contains      one of the fragments in <any> is in the answer
  not_contains  NOTHING from <any> may appear (anti-slop traps:
                placeholders, TODO, invented number disclaimers)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

KINDS: tuple[str, ...] = ("artifact", "tool_use", "contains", "not_contains")

_REQUIRED = frozenset({"id", "input", "expect"})


def _validate(case: dict, plugin: str, seen: set[str]) -> dict:
    missing = _REQUIRED - set(case)
    if missing:
        raise ValueError(f"{plugin}: case missing fields {sorted(missing)}")
    cid = case["id"]
    if not isinstance(cid, str) or not cid.startswith(plugin + "-"):
        raise ValueError(f"{plugin}: id {cid!r} does not carry the plugin prefix")
    if cid in seen:
        raise ValueError(f"{plugin}: duplicate id {cid!r}")
    seen.add(cid)
    if not isinstance(case["input"], str) or len(case["input"]) < 8:
        raise ValueError(f"{plugin}: {cid} input too short")
    expect = case["expect"]
    if not isinstance(expect, dict) or expect.get("kind") not in KINDS:
        raise ValueError(
            f"{plugin}: {cid} unknown expect.kind {expect.get('kind')!r} - allowed: {', '.join(KINDS)}"
        )
    kind = expect["kind"]
    if kind == "artifact":
        if not isinstance(expect.get("suffix"), str) or not expect["suffix"].startswith("."):
            raise ValueError(f"{plugin}: {cid} artifact needs a suffix like '.pdf'")
    else:
        any_list = expect.get("any")
        if not isinstance(any_list, list) or not any_list or not all(isinstance(s, str) for s in any_list):
            raise ValueError(f"{plugin}: {cid} {kind} needs any: [strings]")
    return case


def load_golden(path: Path, plugin: str) -> list[dict]:
    """Reads a golden suite fail-closed: one broken line is an
    error, not a skipped sentence — garbage never lands in the matrix."""
    seen: set[str] = set()
    cases: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{plugin}: line {i} is not JSON ({exc})") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"{plugin}: line {i} is not an object")
        cases.append(_validate(raw, plugin, seen))
    if not cases:
        raise ValueError(f"{plugin}: empty golden suite")
    return cases


def _command_names(plugin_dir: Path) -> set[str]:
    try:
        manifest = json.loads((plugin_dir / "ephe-plugin.json").read_text(encoding="utf-8"))
        return {c["name"] for c in manifest.get("components", {}).get("commands", [])}
    except Exception:
        return set()


def _events(transcript: str) -> list[tuple[str, str]]:
    """Tool events the harness observed, never what the answer claims.

    The runner separates its own event log from the model's answer with this
    marker, so a sentence that names a tool is not evidence that it ran.
    """
    marker = "\n[EPHE-TOOL-EVENTS]\n"
    if marker not in transcript:
        return []
    events: list[tuple[str, str]] = []
    for line in transcript.split(marker, 1)[1].splitlines():
        if not line.startswith("[tool "):
            continue
        name, _, output = line[len("[tool "):].partition("]")
        events.append((name.strip().lower(), output.strip()))
    return events


def _failed_output(output: str) -> bool:
    head = output[:120].lower()
    return head.startswith("[tool-error") or "refused" in head or "denied" in head


def grade(case: dict, transcript: str) -> bool:
    """Grade one case against one transcript — pure string physics."""
    expect = case["expect"]
    kind = expect["kind"]
    marker = "\n[EPHE-TOOL-EVENTS]\n"
    answer = (transcript.split(marker, 1)[0] if marker in transcript else transcript).lower()
    whole = transcript.lower()
    if kind == "artifact":
        pattern = re.compile(r"\S+" + re.escape(expect["suffix"].lower()) + r"\b")
        return bool(pattern.search(whole))
    any_list = [s.lower() for s in expect["any"]]
    if kind == "contains":
        return any(s in answer for s in any_list)
    if kind == "not_contains":
        return not any(s in answer for s in any_list)
    if kind == "tool_use":
        return any(
            name in any_list and not _failed_output(output)
            for name, output in _events(transcript)
        )
    return False


def plugin_prompt(plugin_dir: Path) -> tuple[str, list[str]]:
    """The declared skill prompt and tool grant of a plugin, for its matrix."""
    manifest = json.loads((plugin_dir / "ephe-plugin.json").read_text(encoding="utf-8"))
    packs = (manifest.get("components") or {}).get("skills") or []
    if not packs:
        return "", []
    path = plugin_dir / "skills" / str(packs[0]) / "SKILL.md"
    from core.skills import _parse_skill

    skill = _parse_skill(str(packs[0]), path.read_text(encoding="utf-8"), skill_dir=path.parent)
    return skill.system_prompt, list(skill.allowed_tools or skill.tools)


#: Tools a matrix may execute without a human: artifact production only. Every
#: other mutating tool keeps the conservative non-interactive refusal.
BENCH_ARTIFACT_TOOLS = frozenset({
    "create_pdf",
    "create_docx",
    "build_document",
    "create_qrcode",
    "create_svg",
    "create_pptx_deck",
    "create_pitch_deck",
    "qa_pptx_deck",
    "create_xlsx",
    "generate_chart",
    "create_source_notebook",
    "export_source_brief",
    "verify_artifact",
})


BENCH_CASE_TIMEOUT_SECONDS = float(os.environ.get("EPHE_BENCH_CASE_TIMEOUT", "180"))
BENCH_MAX_TOOL_ITERATIONS = int(os.environ.get("EPHE_BENCH_MAX_TOOL_ITERATIONS", "8"))

_SAFE_SHELL_PREFIXES = (
    "wc ",
    "python -m pytest",
    "pytest",
    "ruff ",
    "git diff",
    "git status",
    "find ",
    "rg ",
    "ls ",
    "cat ",
    "sed -n",
    "head ",
    "tail ",
)
_SHELL_REFUSE = ("rm ", "sudo", ">", "|", "&&", "||", ";", "$(", "`", "<", "-exec", "-delete")


def _safe_shell(command: str) -> bool:
    text = command.strip()
    return bool(text) and text.startswith(_SAFE_SHELL_PREFIXES) and not any(
        bad in text for bad in _SHELL_REFUSE
    )


def _inside_workspace(path: str, workspace: str) -> bool:
    from core.path_guard import within

    try:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = Path(workspace) / candidate
        return within(candidate.resolve(), Path(workspace).resolve())
    except (OSError, RuntimeError, ValueError):
        return False


def bench_policy(allowed_tools: list[str] | None, *, workspace: str | None = None) -> object:
    """Approval policy for a matrix run.

    Artifact tools are approved by name. With a sandbox workspace, file edits
    and test runs are approved only inside that workspace; shell commands must
    match a read-only allowlist. Everything else keeps the conservative denial.
    """
    from core.tools.approval import ApprovalPolicy

    allowed = set(allowed_tools or ())
    approved = BENCH_ARTIFACT_TOOLS & allowed

    async def confirm(name: str, arguments: dict) -> bool:
        if name in approved:
            return True
        if name == "run_tests" and name in allowed:
            return True
        if name == "run_linter" and name in allowed:
            return True
        if name == "format_code" and workspace and name in allowed:
            return _inside_workspace(str(arguments.get("path") or ""), workspace)
        if name in {"edit_file", "write_file"} and workspace and name in allowed:
            return _inside_workspace(str(arguments.get("path") or ""), workspace)
        if name == "run_shell" and name in allowed:
            return _safe_shell(str(arguments.get("command") or ""))
        if name == "execute_code" and name in allowed:
            return True
        if name == "memory" and name in allowed:
            return str(arguments.get("action") or "").lower() in {"add", "replace", "remove", "list"}
        if name in {"web_search", "fetch_url"} and name in allowed:
            return True
        if name in {"browser_go", "browser_screenshot", "browser_scroll", "browser_type", "browser_press", "browser_evaluate"} and name in allowed:
            return True
        if name == "browser_click" and name in allowed:
            target = str(arguments).lower()
            return not any(word in target for word in ("submit", "send", "delete", "confirm", "login", "buy", "purchase"))
        return False

    return ApprovalPolicy(interactive=False, on_confirm=confirm)


def run_measured(
    case: dict,
    engine=None,
    *,
    system_prompt: str | None = None,
    allowed_tools: list[str] | None = None,
    approval_policy=None,
) -> tuple[str, dict]:
    """Like :func:`run_once`, plus the provider usage block of the turn."""
    import asyncio

    from core.chat import chat_with_tools
    from core.engine_config import resolve_engine_choice
    from core.tools.approval import ApprovalPolicy
    from core.types import Message

    choice = engine or resolve_engine_choice()  # the engine choice belongs to the user
    if hasattr(choice, "apply_env"):
        choice.apply_env()
    chunks: list[str] = []
    tool_events: list[str] = []

    async def _turn() -> tuple[str, dict]:
        answer = ""
        for attempt in range(3):
            try:
                answer = await asyncio.wait_for(chat_with_tools(
                    model=choice.model,
                    history=[Message(role="user", content=case["input"])],
                    on_chunk=chunks.append,
                    on_tool_done=lambda name, out, *_: tool_events.append(f"[tool {name}] {out}"),
                    approval_policy=approval_policy or ApprovalPolicy(interactive=False),
                    max_tool_iterations=BENCH_MAX_TOOL_ITERATIONS,
                    session_id=f"bench-{case['id']}",
                    extra_system_prompt=system_prompt,
                    allowed_tool_names=allowed_tools,
                ), timeout=BENCH_CASE_TIMEOUT_SECONDS)
                break
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in {429, 500, 502, 503, 504} and attempt < 2:
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                raise
        from core.tools.session_ctx import get_measured_usage

        return answer, dict(get_measured_usage() or {})

    answer, usage = asyncio.run(_turn())
    return answer + "\n[EPHE-TOOL-EVENTS]\n" + "\n".join(tool_events), usage


def run_once(
    case: dict,
    engine=None,
    *,
    system_prompt: str | None = None,
    allowed_tools: list[str] | None = None,
    approval_policy=None,
) -> str:
    """Run one case through the product pipeline and return its transcript.

    Without a policy the run is conservative (interactive=False → tools that
    require confirmation are cleanly refused, never waved through silently).
    Fail-closed without a configured engine.
    """
    return run_measured(
        case,
        engine,
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        approval_policy=approval_policy,
    )[0]


def measure_matrix(
    plugin_dir: Path,
    *,
    runs: int = 3,
    runner=None,
    system_prompt: str | None = None,
    allowed_tools: list[str] | None = None,
    approval_policy=None,
    case_ids: list[str] | None = None,
    input_transform=None,
) -> dict:
    """Run every case ``runs`` times; each rep keeps its transcript, usage and verdict."""
    import time

    plugin = plugin_dir.name
    cases = load_golden(plugin_dir / "prompts" / "golden.jsonl", plugin)
    if case_ids:
        wanted = set(case_ids)
        cases = [case for case in cases if case["id"] in wanted]
    if input_transform:
        cases = [{**case, "input": input_transform(case["input"])} for case in cases]
    if system_prompt is None or allowed_tools is None:
        system_prompt, allowed_tools = plugin_prompt(plugin_dir)
    policy = approval_policy or bench_policy(allowed_tools)
    runner = runner or run_measured
    rows: list[dict] = []
    for case in cases:
        reps: list[dict] = []
        for index in range(runs):
            started = time.monotonic()
            transcript = ""
            usage: dict = {}
            error = ""
            try:
                result = runner(
                    case,
                    system_prompt=system_prompt,
                    allowed_tools=allowed_tools,
                    approval_policy=policy,
                )
                if isinstance(result, tuple):
                    transcript, usage = result
                else:
                    transcript = result
                passed = grade(case, transcript)
            except Exception as exc:  # a raised run still gets a failed verdict
                passed = False
                error = f"{type(exc).__name__}: {exc}"
            reps.append({
                "run": index + 1,
                "pass": passed,
                "seconds": round(time.monotonic() - started, 2),
                "usage": usage,
                "transcript": transcript,
                "error": error,
            })
        passes = sum(1 for rep in reps if rep["pass"])
        rows.append({
            "id": case["id"],
            "command": case.get("command"),
            "input": case["input"],
            "expect": case["expect"],
            "reps": reps,
            "passes": passes,
            "pass3": passes == runs,
        })
    return {
        "plugin": plugin,
        "runs": runs,
        "cases": rows,
        "pass3_rate": sum(1 for row in rows if row["pass3"]) / max(len(rows), 1),
    }


def pass3_matrix(plugin_dir: Path, *, runs: list[str], report: Path | None = None) -> list[dict]:
    """pass³ in the repo semantics of evals/bench_option_b.py (TAU-
    Reliability): a case only counts when ALL runs pass — a majority
    is not reliability. rows: id/input/command/expect/passes/pass3."""
    plugin = plugin_dir.name
    cases = load_golden(plugin_dir / "prompts" / "golden.jsonl", plugin)
    system_prompt, allowed_tools = plugin_prompt(plugin_dir)
    policy = bench_policy(allowed_tools)
    rows: list[dict] = []
    for case in cases:
        passes = sum(
            1
            for _ in runs
            if grade(
                case,
                run_once(
                    case,
                    system_prompt=system_prompt,
                    allowed_tools=allowed_tools,
                    approval_policy=policy,
                ),
            )
        )
        rows.append(
            {
                "id": case["id"],
                "input": case["input"],
                "command": case.get("command"),
                "expect": case["expect"],
                "passes": passes,
                "pass3": passes == len(runs),
            }
        )
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        rate = sum(1 for r in rows if r["pass3"]) / max(len(rows), 1)
        report.write_text(
            json.dumps({"plugin": plugin, "runs": len(runs), "pass3_rate": rate, "rows": rows},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return rows


def verify_all(plugins_dir: Path) -> list[dict]:
    """The CI gate: zero findings across all production plugins."""
    report: list[dict] = []
    for pdir in sorted(p for p in plugins_dir.iterdir() if (p / "ephe-plugin.json").is_file()):
        name = pdir.name
        issues: list[str] = []
        golden = pdir / "prompts" / "golden.jsonl"
        rubric = pdir / "prompts" / "rubric.md"
        try:
            cases = load_golden(golden, name) if golden.is_file() else []
        except ValueError as exc:
            cases = []
            issues.append(str(exc))
        if not golden.is_file():
            issues.append("prompts/golden.jsonl is missing")
        if not rubric.is_file():
            issues.append("prompts/rubric.md is missing")
        if len(cases) < 6:
            issues.append(f"only {len(cases)} cases (< 6)")
        if cases and not any(c["expect"]["kind"] == "not_contains" for c in cases):
            issues.append("no anti-slop trap (not_contains)")
        names = _command_names(pdir)
        for c in cases:
            cmd = c.get("command")
            if cmd is not None and cmd not in names:
                issues.append(f"{c['id']}: unknown command {cmd!r}")
        report.append({"plugin": name, "cases": len(cases), "issues": issues})
    return report
