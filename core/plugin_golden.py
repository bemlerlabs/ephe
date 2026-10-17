"""
◑ Ephe – golden tests per plugin (E4, "measured, not promised")
core/plugin_golden.py

Every product plugin carries prompts/golden.jsonl — input → expected
artefact/behaviour, mechanically gradable. The matrix is measured with pass³
(3 runs per case, majority decision) against the configured engine; the reference
mark is Opus 5.5 / GPT Astra 6.

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


def grade(case: dict, transcript: str) -> bool:
    """Grade one case against one transcript — pure string physics."""
    expect = case["expect"]
    kind = expect["kind"]
    hay = transcript.lower()
    if kind == "artifact":
        pattern = re.compile(r"\S+" + re.escape(expect["suffix"].lower()) + r"\b")
        return bool(pattern.search(hay))
    any_list = [s.lower() for s in expect["any"]]
    if kind == "contains":
        return any(s in hay for s in any_list)
    if kind == "not_contains":
        return not any(s in hay for s in any_list)
    if kind == "tool_use":
        return any(s in hay for s in any_list)
    return False


def run_once(case: dict, engine=None) -> str:
    """Run one case through the product pipeline (the same chat_with_tools
    as the server, desktop and TUI — no special path in the benchmark). Returns the
    transcript: answer + tool events. Approves conservatively (interactive=False
    → tools that require confirmation are cleanly refused, never waved
    through silently). Fail-closed without a configured engine."""
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

    async def _turn() -> str:
        return await chat_with_tools(
            model=choice.model,
            history=[Message(role="user", content=case["input"])],
            on_chunk=chunks.append,
            on_tool_done=lambda name, out: tool_events.append(f"[tool {name}] {out}"),
            approval_policy=ApprovalPolicy(interactive=False),
            max_tool_iterations=8,
            session_id=f"bench-{case['id']}",
        )

    answer = asyncio.run(_turn())
    return answer + "\n" + "\n".join(tool_events)


def pass3_matrix(plugin_dir: Path, *, runs: list[str], report: Path | None = None) -> list[dict]:
    """pass³ in the repo semantics of evals/bench_option_b.py (TAU-
    Reliability): a case only counts when ALL runs pass — a majority
    is not reliability. rows: id/input/command/expect/passes/pass3."""
    plugin = plugin_dir.name
    cases = load_golden(plugin_dir / "prompts" / "golden.jsonl", plugin)
    rows: list[dict] = []
    for case in cases:
        passes = sum(1 for _ in runs if grade(case, run_once(case)))
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
