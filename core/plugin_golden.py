"""
◑ Ephe – golden tests per plugin (E4, "measured, not promised")
core/plugin_golden.py

Every product plugin carries prompts/golden.jsonl — input → expected
artefact/behaviour, mechanically gradable. The matrix is measured with pass³
(3 runs per case, all must pass) against the engine named in the receipt;
a reference comparison is stated only after those models have run.

One golden case (one JSONL line, fail-closed):
  id          "<plugin>-<nr>"      unique, with the plugin prefix
  command     command name | null  must exist in the manifest
  input       the task (what the user would ask)
  expect      {"kind": …, …}       see KINDS — everything by string test
  note        optional, one sentence why
  mode        one of plugin_scope.MODES — the turn is run IN this mode
  privileges  code|files|network, with mode "creator" only — the consent the
              turn holds, written into a config dir the run then removes
  tools       non-empty name list — what this case offers the model, so a
              name the mode hides is not graded on a call it could not make

Kinds (mechanical, no model in the grader):
  artifact      <suffix> appears as an artefact path in the transcript
  tool_use      one of the tools in <any> was called and did not come back failed
  contains      one of the fragments in <any> is in the answer
  not_contains  NOTHING from <any> may appear (anti-slop traps:
                placeholders, TODO, invented number disclaimers)
  tool_refused  no tool in <any> ran. With a <reason>, the refusal's own text in a
                returned call has to carry it — the difference between the consent
                guard and the approval gate is in the words, so naming the reason is
                what makes a refusal attributable. Without one, the case only says
                the call did not happen, which is also the shape a call the offer
                withheld leaves: the Creator guard takes a name the session holds no
                privilege for out of the offer (`core.tools.creator_guard.filter_offer`),
                so that turn can never return a denial line for it

A case may instead name a preset its own bundle declares in
`capabilities.evaluator` (`core/plugin_evaluator_contract.py`). The preset is a name for
one of the kinds above, resolved from the manifest beside the suite, and the manifest —
never the case — writes its fragments. The loader records the resolved primitive on the
case as `matcher` and where it came from as `kind_source`, so a receipt names what the
author wrote and the primitive that graded it.

A case may also compose two or more of those presets: `expect` is
`{"kind": "all_of" | "none_of", "of": [preset id, …]}`, every member resolves to the
primitive it names, and the case passes only when all of them pass (or none does). A
composition that names a primitive or another composition is refused at load time, so the
manifest stays the one place a fragment list is written.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
from pathlib import Path

from core.plugin_evaluator_contract import COMPOSITIONS
from core.plugin_evaluator_contract import KINDS as KINDS
from core.plugin_evaluator_contract import (
    MIN_COMPOSITION_MEMBERS,
    EvaluatorKind,
    argument_error,
    preset_matcher,
)

_REQUIRED = frozenset({"id", "input", "expect"})

#: Optional case keys that say WHICH turn the harness has to build. A plain case
#: constrains the answer; these constrain the situation the engine is asked in, and
#: a Creator case without them grades a mode the engine was never in.
_OPTIONAL = ("mode", "privileges", "tools")

#: The two case fields only the loader writes. `matcher` is the primitive a declared
#: preset resolves to; `kind_source` says where it came from. A case that wrote either
#: one would hand the grader a rule no manifest declared, so both are refused by name
#: instead of being overwritten on the way in.
_LOADER_FIELDS = frozenset({"matcher", "kind_source"})


def _validate(
    case: dict, plugin: str, seen: set[str], kinds: dict[str, EvaluatorKind]
) -> dict:
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
    _validate_context(case, plugin, cid)
    forged = sorted(set(case) & _LOADER_FIELDS)
    if forged:
        raise ValueError(
            f"{plugin}: {cid} may not carry {', '.join(forged)} - the loader sets it"
        )
    expect = case["expect"]
    if not isinstance(expect, dict):
        raise ValueError(f"{plugin}: {cid} expect must be an object")
    declared = expect.get("kind")
    if declared in COMPOSITIONS:
        matcher, source = _composition(
            declared, expect, plugin=plugin, cid=cid, kinds=kinds
        )
    elif declared in kinds:
        # The manifest is the one place a preset's arguments are written; a case that
        # restated any of them could silently disagree with the check it names.
        extra = sorted(set(expect) - {"kind"})
        if extra:
            raise ValueError(
                f"{plugin}: {cid} declared kind {declared!r} takes no arguments "
                f"beside kind ({', '.join(extra)})"
            )
        preset = kinds[declared]
        matcher = preset_matcher(preset)
        source = preset.kind_id
    elif declared in KINDS:
        if "of" in expect:
            raise ValueError(
                f"{plugin}: {cid} {declared} does not compose - "
                "of belongs to all_of and none_of"
            )
        error = argument_error(declared, expect)
        if error:
            raise ValueError(f"{plugin}: {cid} {error}")
        matcher = _matcher(declared, expect)
        source = "kernel"
    else:
        allowed = ", ".join(KINDS)
        if kinds:
            allowed += f"; declared here: {', '.join(sorted(kinds))}"
        raise ValueError(
            f"{plugin}: {cid} unknown expect.kind {declared!r} - allowed: {allowed}"
        )
    return {**case, "matcher": matcher, "kind_source": source}


def _composition(
    kind: str,
    expect: dict,
    *,
    plugin: str,
    cid: str,
    kinds: dict[str, EvaluatorKind],
) -> tuple[dict, str]:
    """Resolve one `all_of` / `none_of` case into the primitives it combines.

    A member is a preset id this bundle declares: naming a primitive here would write a
    fragment list outside the manifest, and a preset id is the one reference whose
    arguments already resolved. Every member appears once, and the list holds at least
    `MIN_COMPOSITION_MEMBERS`; it cannot outgrow the eight presets a manifest may declare.
    """
    extra = sorted(set(expect) - {"kind", "of"})
    if extra:
        raise ValueError(
            f"{plugin}: {cid} {kind} takes only of beside kind ({', '.join(extra)})"
        )
    members = expect.get("of")
    if not isinstance(members, list) or not all(
        isinstance(member, str) for member in members
    ):
        raise ValueError(f"{plugin}: {cid} {kind} needs of: [preset ids]")
    if len(members) < MIN_COMPOSITION_MEMBERS:
        raise ValueError(
            f"{plugin}: {cid} {kind} needs at least "
            f"{MIN_COMPOSITION_MEMBERS} presets in of"
        )
    names: set[str] = set()
    matchers: list[dict] = []
    for member in members:
        if member in names:
            raise ValueError(f"{plugin}: {cid} {kind} names {member!r} twice")
        names.add(member)
        if member in KINDS:
            raise ValueError(
                f"{plugin}: {cid} {kind} member {member!r} is a kernel kind, "
                "not a declared preset"
            )
        if member in COMPOSITIONS:
            raise ValueError(
                f"{plugin}: {cid} {kind} member {member!r} is a composition id, "
                "not a declared preset"
            )
        preset = kinds.get(member)
        if preset is None:
            declared = ", ".join(sorted(kinds)) or "none"
            raise ValueError(
                f"{plugin}: {cid} {kind} member {member!r} is not a declared preset - "
                f"declared here: {declared}"
            )
        matchers.append(preset_matcher(preset))
    return {"kind": kind, "of": matchers}, f"{kind}({', '.join(members)})"


def _matcher(kind: str, expect: dict) -> dict:
    """The primitive a validated kernel case grades with, its arguments copied off it."""
    if kind == "artifact":
        return {"kind": kind, "suffix": expect["suffix"]}
    matcher = {"kind": kind, "any": list(expect["any"])}
    if kind == "tool_refused" and "reason" in expect:
        matcher["reason"] = expect["reason"]
    return matcher


def _validate_context(case: dict, plugin: str, cid: str) -> None:
    """Check the three keys that say which turn to build, before an engine is spent on it.

    Each one is a claim about the engine's situation, and a wrong claim is not a
    failed case but an unmeasurable one: a mode the engine does not have is dropped
    silently, a privilege outside Creator mode is never asked for, an empty tool
    list means the model is offered nothing. All three would grade as an answer
    that merely did not try.
    """
    from core.plugin_scope import MODES
    from core.tools.creator_guard import PRIVILEGES

    mode = case.get("mode")
    if mode is not None and mode not in MODES:
        raise ValueError(f"{plugin}: {cid} mode {mode!r} is not one of {', '.join(MODES)}")
    privileges = case.get("privileges")
    if privileges is not None:
        if not isinstance(privileges, list) or not all(p in PRIVILEGES for p in privileges):
            raise ValueError(
                f"{plugin}: {cid} privileges must be from {', '.join(sorted(PRIVILEGES))}"
            )
        if mode != "creator":
            raise ValueError(
                f"{plugin}: {cid} privileges are only held in creator mode - set mode or drop them"
            )
    tools = case.get("tools")
    if tools is not None and (
        not isinstance(tools, list) or not tools or not all(isinstance(t, str) for t in tools)
    ):
        raise ValueError(f"{plugin}: {cid} tools must be a non-empty list of names")


def _declared_kinds(path: Path) -> dict[str, EvaluatorKind]:
    """The presets the manifest beside a suite declares.

    The suite path is fixed by construction (`<plugin>/prompts/golden.jsonl`), so the
    manifest is too. One question is asked of it: does the section this loader reads
    declare a preset the kernel cannot honour? A manifest the rest of the contract refuses
    stays the scanner's and the DoD gate's finding, so `ephe bench` does not report one
    manifest violation twice; an absent or unreadable manifest declares no presets, and a
    case that names one is refused as an unknown kind.
    """
    from core.plugin_evaluator_contract import evaluator_kinds, validate_evaluator
    from core.plugin_manifest import MANIFEST_FILENAME

    if path.parent.name != "prompts":
        return {}
    plugin_dir = path.parent.parent
    try:
        manifest = json.loads(
            (plugin_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}
    if not isinstance(manifest, dict):
        return {}
    error = validate_evaluator(manifest)
    if error:
        raise ValueError(f"{plugin_dir.name}: {error}")
    return evaluator_kinds(manifest)


def load_golden(path: Path, plugin: str) -> list[dict]:
    """Reads a golden suite fail-closed: one broken line is an
    error, not a skipped sentence — garbage never lands in the matrix.

    A case may name a preset the sibling manifest declares; the loader resolves it once
    per suite and records the primitive and its source on every case.
    """
    kinds = _declared_kinds(path)
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
        cases.append(_validate(raw, plugin, seen, kinds))
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
    """Grade one case against one transcript — pure string physics.

    A case the loader read carries `matcher`, the primitive a declared preset resolved to
    or the composition of primitives its case names; a hand-built case is graded on its
    own `expect`. A matcher that is neither a primitive nor a composition is a failure, and
    so is every malformed one: only the loader writes a matcher, so anything else never
    passed the loader and grades false rather than by accident.
    """
    matcher = case.get("matcher") or case["expect"]
    marker = "\n[EPHE-TOOL-EVENTS]\n"
    answer = (transcript.split(marker, 1)[0] if marker in transcript else transcript).lower()
    return _grade_matcher(
        matcher, answer=answer, whole=transcript.lower(), events=_events(transcript)
    )


def _grade_matcher(
    matcher: object, *, answer: str, whole: str, events: list[tuple[str, str]]
) -> bool:
    """One primitive or one composition against an already-lowercased transcript."""
    if not isinstance(matcher, dict):
        return False
    kind = matcher.get("kind")
    if kind in COMPOSITIONS:
        members = matcher.get("of")
        if (
            not isinstance(members, list)
            or not members
            or not all(isinstance(member, dict) for member in members)
        ):
            return False
        passed = [
            _grade_matcher(member, answer=answer, whole=whole, events=events)
            for member in members
        ]
        return all(passed) if kind == "all_of" else not any(passed)
    if kind not in KINDS:
        return False
    if kind == "artifact":
        suffix = matcher.get("suffix")
        if not isinstance(suffix, str) or not suffix:
            return False
        pattern = re.compile(r"\S+" + re.escape(suffix.lower()) + r"\b")
        return bool(pattern.search(whole))
    fragments = matcher.get("any")
    if (
        not isinstance(fragments, list)
        or not fragments
        or not all(isinstance(fragment, str) for fragment in fragments)
    ):
        return False
    any_list = [fragment.lower() for fragment in fragments]
    if kind == "contains":
        return any(fragment in answer for fragment in any_list)
    if kind == "not_contains":
        return not any(fragment in answer for fragment in any_list)
    if kind == "tool_use":
        return any(
            name in any_list and not _failed_output(output)
            for name, output in events
        )
    if kind == "tool_refused":
        return _refused(any_list, matcher.get("reason"), events)
    return False


def _refused(any_list: list[str], reason: object, events: list[tuple[str, str]]) -> bool:
    """Whether the named call was refused, in the shape the case asked for.

    A case that names a reason asks for the refusal's own words, and only a returned
    call can carry them: that is what tells the consent guard from the approval gate.
    A case that names no reason only says the call did not happen. That is also what a
    call withheld from the offer leaves behind — the Creator guard removes every name
    whose privilege the session lacks (`core.tools.creator_guard.filter_offer`), so a
    turn holding no grant for a call can never produce a denial line for it, and
    grading it on an error line would grade a case the product made unmeasurable.
    """
    phrase = str(reason or "").lower()
    if phrase:
        return any(
            name in any_list and _failed_output(output) and phrase in output.lower()
            for name, output in events
        )
    return not any(
        name in any_list and not _failed_output(output) for name, output in events
    )


def _rejects_listed_fragments(matcher: object) -> bool:
    """Whether the check fails when a fragment it names reaches the answer.

    The anti-slop gate asks for that shape in one of three: the kernel's `not_contains`
    primitive, an `all_of` that carries one, or a `none_of` over `contains` checks — no
    member may match, so every listed fragment is forbidden. A `none_of` over
    `not_contains` presets passes only when the trap fails, and one that also names
    another kind is not a text trap, so neither counts.
    """
    if not isinstance(matcher, dict):
        return False
    kind = matcher.get("kind")
    if kind == "not_contains":
        return True
    members = matcher.get("of")
    if not isinstance(members, list) or not members:
        return False
    if kind == "all_of":
        return any(_rejects_listed_fragments(member) for member in members)
    if kind == "none_of":
        return all(
            isinstance(member, dict) and member.get("kind") == "contains"
            for member in members
        )
    return False


def plugin_prompt(plugin_dir: Path) -> tuple[str, list[str] | None]:
    """The declared skill prompt and tool grant of a plugin, for its matrix.

    A bundle without a skill pack has no grant, which is not the same turn as a
    grant of nothing: the chat route hands ``None`` when no skill resolved and the
    engine then ships its core kernel, while an empty list ships an empty array.
    """
    manifest = json.loads((plugin_dir / "ephe-plugin.json").read_text(encoding="utf-8"))
    packs = (manifest.get("components") or {}).get("skills") or []
    if not packs:
        return "", None
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


#: What no unattended matrix executes, whatever the case declares as granted.
#: Installing mounts code into the running app — the consent dialog is where that
#: is decided, and a bench run has no person in front of it.
BENCH_NEVER_APPROVES = frozenset({"install_plugin_bundle"})


def bench_policy(
    allowed_tools: list[str] | None,
    *,
    workspace: str | None = None,
    privileges: list[str] | None = None,
) -> object:
    """Approval policy for a matrix run.

    Artifact tools are approved by name. With a sandbox workspace, file edits
    and test runs are approved only inside that workspace; shell commands must
    match a read-only allowlist. A case that declares a Creator grant stands in
    for the dialog that person answered, so the staging calls whose privilege is
    in that grant are approved — and everything that reaches the running app is
    not. Anything else keeps the conservative denial.
    """
    from core.tools.approval import ApprovalPolicy

    allowed = set(allowed_tools or ())
    approved = BENCH_ARTIFACT_TOOLS & allowed
    granted = set(privileges or ())

    def _staging_is_granted(name: str) -> bool:
        from core.tools.creator_guard import KERNEL_PRIVILEGES

        if name in BENCH_NEVER_APPROVES:
            return False
        privilege = KERNEL_PRIVILEGES.get(name)
        return bool(privilege) and name in allowed and privilege in granted

    async def confirm(name: str, arguments: dict) -> bool:
        if name in approved:
            return True
        if privileges is not None and _staging_is_granted(name):
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


@contextlib.contextmanager
def _case_context(case: dict, session_id: str, mode: str, privileges):
    """Hold the turn the case declared, then leave no trace of it.

    The grant is a real file the guard reads by path, so it goes in a directory the
    run removes; the user's own consent rows cannot be reached from here.
    """
    import shutil
    import tempfile

    from core.tools import session_ctx

    config_dir = os.environ.get("EPHE_CONFIG_DIR")
    sandbox = None
    if privileges:
        sandbox = tempfile.mkdtemp(prefix="ephe-bench-creator-config-")
        os.environ["EPHE_CONFIG_DIR"] = sandbox
        from core.tools import creator_guard

        creator_guard.set_privileges(session_id, set(privileges))
    token = session_ctx.set_current_mode(mode) if mode else None
    try:
        yield
    finally:
        if token is not None:
            session_ctx.reset_current_mode(token)
        if sandbox is not None:
            if config_dir is None:
                os.environ.pop("EPHE_CONFIG_DIR", None)
            else:
                os.environ["EPHE_CONFIG_DIR"] = config_dir
            shutil.rmtree(sandbox, ignore_errors=True)


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

    # A case may declare the turn it has to be measured in. The mode travels to
    # where the tool is EXECUTED (the same seam the chat route publishes), the
    # privilege grant goes into a throwaway config dir so the run cannot answer
    # for a real session, and the engine is already resolved before that dir moves.
    mode = case.get("mode") or ""
    privileges = case.get("privileges")
    tools = case.get("tools") or allowed_tools
    session_id = f"bench-{case['id']}"
    if privileges is not None:
        # The suite-level policy was built without this case's grant, and the
        # gate that refuses a staging call would otherwise outrank the dialog the
        # case says the person answered. The workspace the run was given still
        # confines every file the turn touches.
        approval_policy = bench_policy(
            tools,
            workspace=os.environ.get("EPHE_WORKSPACE") or None,
            privileges=privileges,
        )

    async def _turn() -> tuple[str, dict]:
        answer = ""
        for attempt in range(3):
            try:
                # `asyncio.timeout` awaits in this task; `wait_for` wraps the call in a
                # child task on 3.11, so the usage ContextVar set inside the provider
                # call never reaches this scope and a valid turn reads as unmeasured.
                async with asyncio.timeout(BENCH_CASE_TIMEOUT_SECONDS):
                    answer = await chat_with_tools(
                        model=choice.model,
                        history=[Message(role="user", content=case["input"])],
                        on_chunk=chunks.append,
                        on_tool_done=lambda name, out, *_: tool_events.append(f"[tool {name}] {out}"),
                        approval_policy=approval_policy or ApprovalPolicy(interactive=False),
                        max_tool_iterations=BENCH_MAX_TOOL_ITERATIONS,
                        session_id=session_id,
                        extra_system_prompt=system_prompt,
                        allowed_tool_names=tools,
                    )
                break
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in {429, 500, 502, 503, 504} and attempt < 2:
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                raise
        from core.tools.session_ctx import get_measured_usage

        return answer, dict(get_measured_usage() or {})

    from core import plugin_turn_hooks

    with _case_context(case, session_id, mode, privileges), plugin_turn_hooks.suppressed():
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
            "matcher": case.get("matcher"),
            "kind_source": case.get("kind_source", "kernel"),
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
    is not reliability. rows: id/input/command/expect/matcher/kind_source/
    passes/pass3."""
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
                "matcher": case.get("matcher"),
                "kind_source": case.get("kind_source", "kernel"),
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
        if cases and not any(
            _rejects_listed_fragments(c.get("matcher") or c["expect"]) for c in cases
        ):
            issues.append("no anti-slop trap (not_contains)")
        names = _command_names(pdir)
        for c in cases:
            cmd = c.get("command")
            if cmd is not None and cmd not in names:
                issues.append(f"{c['id']}: unknown command {cmd!r}")
        report.append({"plugin": name, "cases": len(cases), "issues": issues})
    return report
