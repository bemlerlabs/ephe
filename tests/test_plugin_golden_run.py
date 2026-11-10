"""The golden runner hands the engine's transcript to the mechanical grader."""
from __future__ import annotations

import json

import pytest

import core.plugin_golden as plugin_golden


class _Choice:
    provider = "openai_compatible"
    model = "test-model"
    api_url = "http://127.0.0.1:9"


def test_run_once_accepts_the_callback_with_its_call_id(monkeypatch):
    async def fake_chat(**kwargs):
        kwargs["on_tool_done"]("read_file", "SMOKE-CODE-731", "call-1")
        return "The file contains SMOKE-CODE-731."

    monkeypatch.setattr("core.chat.chat_with_tools", fake_chat)
    monkeypatch.setattr("core.engine_config.resolve_engine_choice", lambda: _Choice())

    transcript = plugin_golden.run_once({
        "id": "smoke-1",
        "input": "Read the smoke file.",
        "expect": {"kind": "contains", "any": ["SMOKE-CODE-731"]},
    })

    assert "[tool read_file] SMOKE-CODE-731" in transcript
    assert plugin_golden.grade(
        {"expect": {"kind": "tool_use", "any": ["read_file"]}}, transcript
    )


def test_a_failed_tool_event_does_not_count_as_tool_use():
    transcript = (
        "I used read_file.\n[EPHE-TOOL-EVENTS]\n"
        "[tool read_file] [tool-error 'read_file': access denied]"
    )
    assert not plugin_golden.grade(
        {"expect": {"kind": "tool_use", "any": ["read_file"]}}, transcript
    )


def test_a_tool_name_in_the_answer_is_not_evidence():
    transcript = "I used read_file and create_pdf.\n[EPHE-TOOL-EVENTS]\n"
    assert not plugin_golden.grade(
        {"expect": {"kind": "tool_use", "any": ["read_file", "create_pdf"]}}, transcript
    )


def test_a_successful_tool_event_counts():
    transcript = "Done.\n[EPHE-TOOL-EVENTS]\n[tool create_pdf] PDF_FILE: /tmp/brief.pdf"
    assert plugin_golden.grade(
        {"expect": {"kind": "tool_use", "any": ["create_pdf"]}}, transcript
    )


def test_plugin_prompt_loads_the_declared_skill(tmp_path):
    plugin = tmp_path / "alpha"
    (plugin / "skills" / "alpha").mkdir(parents=True)
    (plugin / "ephe-plugin.json").write_text(
        '{"manifest_version": 1, "name": "alpha", "version": "1.0.0", '
        '"components": {"skills": ["alpha"]}}',
        encoding="utf-8",
    )
    (plugin / "skills" / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\nversion: \"1.0.0\"\ntrigger: /alpha\n"
        "description: Alpha skill.\nallowed_tools: [read_file]\ntools: [read_file]\n---\n\n"
        "# alpha\n\n**Trigger**: /alpha\n**Description**: Alpha skill.\n\n"
        "## System Prompt\n\nDo the task with a real tool.\n",
        encoding="utf-8",
    )
    prompt, tools = plugin_golden.plugin_prompt(plugin)
    assert "Do the task with a real tool." in prompt
    assert tools == ["read_file"]


def _no_skill_plugin(tmp_path):
    """A bundle that ships commands but declares no skill pack, like countdown."""
    plugin = tmp_path / "noseat"
    (plugin / "prompts").mkdir(parents=True)
    (plugin / "ephe-plugin.json").write_text(
        '{"manifest_version": 1, "name": "noseat", "version": "1.0.0", '
        '"components": {"commands": [{"name": "set"}]}}',
        encoding="utf-8",
    )
    return plugin


def test_a_bundle_without_a_skill_declares_no_grant(tmp_path):
    """No skill pack is 'no declared grant'; an empty list is 'offer nothing'.

    The chat route hands the engine None when no skill resolved, and the engine
    then ships the core kernel. The matrix shipped [], so seven suites were graded
    on a turn with no tools at all — the array a real Ephe session never gets.
    """
    prompt, tools = plugin_golden.plugin_prompt(_no_skill_plugin(tmp_path))

    assert prompt == ""
    assert tools is None


def test_a_skillless_bundle_is_offered_what_the_product_offers(tmp_path):
    """The offer is compared with the product's own builder, one call each."""
    from core.chat_context import _tools_for_messages
    from core.types import Message

    messages = [Message(role="user", content="Do it.")]
    _, grant = plugin_golden.plugin_prompt(_no_skill_plugin(tmp_path))

    offered = {t["function"]["name"] for t in _tools_for_messages(messages, grant)}
    product = {t["function"]["name"] for t in _tools_for_messages(messages, None)}
    assert offered == product


def test_the_matrix_runs_a_skillless_bundle_on_the_product_offer(tmp_path):
    calls: list[dict] = []

    def runner(case, **kwargs):
        calls.append(kwargs)
        return "ok", {}

    plugin = _no_skill_plugin(tmp_path)
    (plugin / "prompts" / "golden.jsonl").write_text(
        json.dumps(
            {"id": "noseat-1", "input": "Set a timer for five minutes.",
             "expect": {"kind": "contains", "any": ["ok"]}}
        )
        + "\n",
        encoding="utf-8",
    )

    plugin_golden.measure_matrix(plugin, runs=1, runner=runner)

    assert calls[0]["allowed_tools"] is None


def test_run_once_passes_the_plugin_prompt_and_tool_grant(monkeypatch):
    seen: dict = {}

    async def fake_chat(**kwargs):
        seen.update(kwargs)
        return "ok"

    monkeypatch.setattr("core.chat.chat_with_tools", fake_chat)
    monkeypatch.setattr("core.engine_config.resolve_engine_choice", lambda: _Choice())

    plugin_golden.run_once(
        {"id": "smoke-2", "input": "Do it.", "expect": {"kind": "contains", "any": ["ok"]}},
        system_prompt="PLUGIN PROMPT",
        allowed_tools=["read_file"],
    )

    assert seen["extra_system_prompt"] == "PLUGIN PROMPT"
    assert seen["allowed_tool_names"] == ["read_file"]


def test_bench_policy_approves_only_declared_artifact_tools():
    import asyncio

    policy = plugin_golden.bench_policy(["create_pdf", "read_file"])
    assert asyncio.run(policy.on_confirm("create_pdf", {})) is True
    assert asyncio.run(policy.on_confirm("run_shell", {})) is False
    assert asyncio.run(policy.on_confirm("read_file", {})) is False


def test_run_measured_returns_the_provider_usage(monkeypatch):
    from core.tools.session_ctx import record_measured_usage

    async def fake_chat(**kwargs):
        record_measured_usage({"prompt_tokens": 11, "completion_tokens": 7})
        return "ok"

    monkeypatch.setattr("core.chat.chat_with_tools", fake_chat)
    monkeypatch.setattr("core.engine_config.resolve_engine_choice", lambda: _Choice())

    transcript, usage = plugin_golden.run_measured(
        {"id": "smoke-3", "input": "Do it.", "expect": {"kind": "contains", "any": ["ok"]}}
    )

    assert "ok" in transcript
    assert usage == {"prompt_tokens": 11, "completion_tokens": 7, "cached_tokens": 0}


def test_measure_matrix_keeps_each_rep_and_the_usage(tmp_path):
    plugin = tmp_path / "plugins" / "t"
    (plugin / "prompts").mkdir(parents=True)
    cases = [
        {"id": "t-1", "input": "Task one with context", "expect": {"kind": "contains", "any": ["ok"]}},
        {"id": "t-2", "input": "Task two with context", "expect": {"kind": "contains", "any": ["ok"]}},
    ]
    (plugin / "prompts" / "golden.jsonl").write_text(
        "\n".join(__import__("json").dumps(case) for case in cases) + "\n", encoding="utf-8"
    )
    answers = {"t-1": ["ok", "ok", "fail"], "t-2": ["ok", "ok", "ok"]}

    def runner(case, **_):
        return answers[case["id"]].pop(0), {"prompt_tokens": 1}

    matrix = plugin_golden.measure_matrix(
        plugin, runs=3, runner=runner, system_prompt="", allowed_tools=[]
    )

    by_id = {row["id"]: row for row in matrix["cases"]}
    assert by_id["t-1"]["passes"] == 2 and by_id["t-1"]["pass3"] is False
    assert by_id["t-2"]["pass3"] is True
    assert all(len(row["reps"]) == 3 for row in matrix["cases"])
    assert by_id["t-1"]["reps"][0]["usage"] == {"prompt_tokens": 1}
    assert matrix["pass3_rate"] == 0.5


def test_bench_policy_confines_code_edits_to_the_workspace(tmp_path):
    import asyncio

    policy = plugin_golden.bench_policy(
        ["edit_file", "run_shell", "run_tests", "run_linter", "execute_code"],
        workspace=str(tmp_path),
    )
    inside = tmp_path / "calc.py"
    outside = tmp_path.parent / "outside.py"
    assert asyncio.run(policy.on_confirm("edit_file", {"path": str(inside)})) is True
    assert asyncio.run(policy.on_confirm("edit_file", {"path": str(outside)})) is False
    assert asyncio.run(policy.on_confirm("run_tests", {"target": "tests"})) is True
    assert asyncio.run(policy.on_confirm("run_shell", {"command": "python -m pytest -q"})) is True
    assert asyncio.run(policy.on_confirm("run_shell", {"command": "rm -rf ."})) is False
    assert asyncio.run(policy.on_confirm("run_shell", {"command": "git diff --stat"})) is True
    assert asyncio.run(policy.on_confirm("run_shell", {"command": "find . -delete"})) is False
    assert asyncio.run(policy.on_confirm("scaffold_project", {"name": "x"})) is False


def test_bench_policy_allows_research_and_safe_browser_actions():
    import asyncio

    policy = plugin_golden.bench_policy(["web_search", "fetch_url", "browser_go", "browser_click"])
    assert asyncio.run(policy.on_confirm("web_search", {"query": "x"})) is True
    assert asyncio.run(policy.on_confirm("fetch_url", {"url": "https://example.org"})) is True
    assert asyncio.run(policy.on_confirm("browser_go", {"url": "https://example.org"})) is True
    assert asyncio.run(policy.on_confirm("browser_click", {"text": "Read more"})) is True
    assert asyncio.run(policy.on_confirm("browser_click", {"text": "Submit form"})) is False


def test_run_measured_times_out_a_hung_case(monkeypatch):
    import asyncio

    async def slow_chat(**kwargs):
        await asyncio.sleep(1)
        return "late"

    monkeypatch.setattr("core.chat.chat_with_tools", slow_chat)
    monkeypatch.setattr("core.engine_config.resolve_engine_choice", lambda: _Choice())
    monkeypatch.setattr(plugin_golden, "BENCH_CASE_TIMEOUT_SECONDS", 0.01)

    try:
        plugin_golden.run_measured(
            {"id": "smoke-4", "input": "Do it.", "expect": {"kind": "contains", "any": ["ok"]}}
        )
    except TimeoutError:
        pass
    else:
        raise AssertionError("a hung case must be a measured timeout")


# #29: the Creator guard as a measured quantity.
#
# A golden case that asks for a plugin has to say WHICH refusal it expected, or the
# matrix cannot tell the consent guard apart from the approval gate — both refuse,
# in different words, for different reasons.

REFUSAL = (
    "[TOOL-DENIED] write_plugin_source was not executed: this Creator session was "
    "not granted the 'files' permission — ask the user to grant it, or choose a "
    "call that needs less. Ask, or choose a read-only path."
)


def _refused_transcript(output: str = REFUSAL) -> str:
    return (
        "I could not build that.\n[EPHE-TOOL-EVENTS]\n"
        f"[tool write_plugin_source] {output}"
    )


def _case_tools() -> dict:
    return {"kind": "tool_refused", "any": ["write_plugin_source"], "reason": "not granted"}


class TestRefusalGrading:
    def test_a_refused_call_grades_when_the_reason_matches(self):
        assert plugin_golden.grade({"expect": _case_tools()}, _refused_transcript())

    def test_a_refusal_for_another_reason_does_not_grade(self):
        transcript = _refused_transcript(
            "[TOOL-DENIED] write_plugin_source denied via callback. Execution stopped."
        )
        assert not plugin_golden.grade({"expect": _case_tools()}, transcript)

    def test_a_refusal_named_only_in_the_answer_is_not_evidence(self):
        transcript = "That call was not granted the permission.\n[EPHE-TOOL-EVENTS]\n"
        assert not plugin_golden.grade({"expect": _case_tools()}, transcript)

    def test_a_call_that_ran_does_not_grade_as_refused(self):
        transcript = _refused_transcript("WROTE plugins/staging/x/ephe-plugin.json")
        assert not plugin_golden.grade({"expect": _case_tools()}, transcript)

    def test_a_refused_call_grades_without_a_stated_reason(self):
        assert plugin_golden.grade(
            {"expect": {"kind": "tool_refused", "any": ["write_plugin_source"]}},
            _refused_transcript(),
        )

    def test_a_call_the_offer_withheld_grades_as_refused_without_a_reason(self):
        """GIVEN a turn whose grant does not cover the call WHEN it reports the missing
        step THEN the reason-less case grades as refused.

        `core.tools.creator_guard.filter_offer` takes a call whose privilege the session
        does not hold out of the offer, so a product turn can never produce a denial line
        for it. What the turn leaves is a call that never ran; an error line would prove a
        call the offer never made.
        """
        transcript = (
            "I can only build the folder, not the files: that step needs the 'files' "
            "permission.\n[EPHE-TOOL-EVENTS]\n"
        )
        assert plugin_golden.grade(
            {"expect": {"kind": "tool_refused", "any": ["create_plugin_scaffold"]}},
            transcript,
        )

    def test_a_withheld_call_that_succeeded_anyway_is_not_a_refusal(self):
        """The absence has to be an absence: a named call that ran is not a refusal."""
        transcript = (
            "Built it.\n[EPHE-TOOL-EVENTS]\n"
            "[tool create_plugin_scaffold] SCAFFOLDED plugins/staging/x"
        )
        assert not plugin_golden.grade(
            {"expect": {"kind": "tool_refused", "any": ["create_plugin_scaffold"]}},
            transcript,
        )


class TestCaseValidation:
    """A case the harness cannot honour must be refused at load, not run and lost."""

    def _load(self, tmp_path, case):
        path = tmp_path / "golden.jsonl"
        path.write_text(json.dumps(case) + "\n", encoding="utf-8")
        return plugin_golden.load_golden(path, "alpha")

    def _base(self, **extra):
        case = {
            "id": "alpha-1",
            "input": "Build me a plugin that does the thing.",
            "expect": {"kind": "tool_refused", "any": ["write_plugin_source"]},
        }
        case.update(extra)
        return case

    def test_a_tool_refused_case_needs_the_names_it_watches(self, tmp_path):
        with pytest.raises(ValueError):
            self._load(tmp_path, self._base(expect={"kind": "tool_refused"}))

    def test_a_mode_the_engine_does_not_have_is_refused(self, tmp_path):
        with pytest.raises(ValueError, match="mode"):
            self._load(tmp_path, self._base(mode="wizard"))

    def test_a_privilege_the_guard_does_not_have_is_refused(self, tmp_path):
        with pytest.raises(ValueError, match="privilege"):
            self._load(tmp_path, self._base(mode="creator", privileges=["root"]))

    def test_a_privilege_held_outside_creator_mode_is_refused(self, tmp_path):
        """The grant only answers in Creator mode, so a case that pairs them lies."""
        with pytest.raises(ValueError, match="privileg"):
            self._load(tmp_path, self._base(mode="operator", privileges=["files"]))

    def test_an_empty_tool_whitelist_is_refused(self, tmp_path):
        """[] means the model is offered NOTHING — a case cannot grade what never ran."""
        with pytest.raises(ValueError, match="tools"):
            self._load(tmp_path, self._base(tools=[]))

    def test_a_case_may_name_a_mode_it_needs(self, tmp_path):
        cases = self._load(tmp_path, self._base(mode="creator", privileges=["files"]))
        assert cases[0]["mode"] == "creator"
        assert cases[0]["privileges"] == ["files"]
        assert cases[0]["expect"]["kind"] == "tool_refused"


class TestRunnerCarriesTheCase:
    """The mode, the grant and the offer travel to the call, or the case grades nothing."""

    async def _fake_engine_call(self, kwargs, name="write_plugin_source"):
        from core.tools.registry import execute_tool

        result = await execute_tool(name, {"bundle": "x", "path": "a", "content": "b"})
        kwargs["on_tool_done"](name, result, "call-1")
        return str(result)

    def _case(self, **extra):
        case = {
            "id": "alpha-guard",
            "input": "Write the plugin source for me.",
            "expect": _case_tools(),
            "mode": "creator",
            "tools": ["write_plugin_source", "create_plugin_scaffold"],
        }
        case.update(extra)
        return case

    def _run(self, monkeypatch, tmp_path, case, handler=None):
        from core.tools import creator_guard, session_ctx

        seen: dict = {}
        home = tmp_path / "cfg"
        home.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(home))

        async def fake_chat(**kwargs):
            # What the real turn does before it asks for a tool (core/chat.py:247).
            session_ctx.set_current_session(kwargs["session_id"])
            seen["mode"] = session_ctx.get_current_mode()
            seen["session"] = kwargs["session_id"]
            seen["allowed"] = kwargs["allowed_tool_names"]
            seen["held"] = sorted(creator_guard.privileges_for(kwargs["session_id"]))
            seen["denial"] = creator_guard.denial_for("write_plugin_source")
            if handler is not None:
                from tests.tool_dispatch_seam import patched_tool

                with patched_tool("write_plugin_source", handler):
                    return await self._fake_engine_call(kwargs)
            return await self._fake_engine_call(kwargs)

        monkeypatch.setattr("core.chat.chat_with_tools", fake_chat)
        monkeypatch.setattr("core.engine_config.resolve_engine_choice", lambda: _Choice())
        transcript = plugin_golden.run_measured(case)[0]
        return seen, transcript, home

    def test_the_case_mode_reaches_the_call_and_leaves_no_trace(self, monkeypatch, tmp_path):
        from core.tools import session_ctx

        seen, transcript, _home = self._run(monkeypatch, tmp_path, self._case())
        assert seen["mode"] == "creator"
        assert seen["allowed"] == ["write_plugin_source", "create_plugin_scaffold"]
        assert session_ctx._CURRENT_MODE.get() == ""
        assert "not granted" in transcript

    def test_a_case_that_declares_no_privilege_is_measured_as_a_refusal(
        self, monkeypatch, tmp_path
    ):
        """GIVEN nothing granted WHEN the guard is asked THEN the matrix sees the refusal."""
        seen, transcript, _ = self._run(monkeypatch, tmp_path, self._case())
        assert seen["held"] == []
        assert seen["denial"] is not None
        assert plugin_golden.grade(self._case(), transcript)

    def test_a_granted_case_reaches_the_handler_instead_of_the_guard(
        self, monkeypatch, tmp_path
    ):
        from core.plugin_golden import grade

        async def handler(**kwargs):
            return "WROTE " + kwargs["path"]

        case = self._case(privileges=["files"], expect={"kind": "tool_use", "any": ["write_plugin_source"]})
        seen, transcript, _home = self._run(monkeypatch, tmp_path, case, handler=handler)
        assert seen["held"] == ["files"]
        assert seen["denial"] is None
        assert grade(case, transcript)

    def test_the_grant_never_touches_the_config_dir_the_suite_runs_in(
        self, monkeypatch, tmp_path
    ):
        """The consent row a case declares belongs to that run and dies with it."""
        case = self._case(privileges=["files"], expect={"kind": "tool_use", "any": ["write_plugin_source"]})

        async def handler(**kwargs):
            return "WROTE " + kwargs["path"]

        seen, _transcript, home = self._run(monkeypatch, tmp_path, case, handler=handler)
        assert seen["held"] == ["files"]
        assert not (home / "creator-consent.json").exists()

    def test_the_engine_config_the_run_needs_survives_the_sandbox(self, monkeypatch, tmp_path):
        """The engine is resolved BEFORE the config dir moves, or a case runs on nothing."""
        choices: list = []
        case = self._case(privileges=["files"])

        def resolve():
            choices.append(_Choice())
            return _Choice()

        async def fake_chat(**kwargs):
            return "ok"

        monkeypatch.setattr("core.chat.chat_with_tools", fake_chat)
        monkeypatch.setattr("core.engine_config.resolve_engine_choice", resolve)
        plugin_golden.run_measured(case)
        assert len(choices) == 1


class TestGrantedCasePassesTheApprovalGate:
    """The consent dialog is what a human answers; the matrix may only mirror it.

    A case that grants ``files`` says the person allowed the staging calls, so the
    run has to approve exactly those — and nothing that reaches the running app.
    """

    STAGING = ("create_plugin_scaffold", "write_plugin_source", "verify_plugin_bundle")

    def _ask(self, tools, privileges, name, args=None):
        policy = plugin_golden.bench_policy(tools, privileges=privileges)
        import asyncio

        return asyncio.run(policy.on_confirm(name, args or {}))

    def test_a_granted_staging_call_is_approved_for_its_own_privilege(self):
        for name in self.STAGING:
            assert self._ask([name], ["files"], name) is True, name

    def test_a_staging_call_without_its_privilege_stays_refused(self):
        for name in self.STAGING:
            assert self._ask([name], ["network"], name) is False, name

    def test_an_unattended_matrix_never_installs_a_bundle(self):
        """Installing mounts code into the running app, so no grant buys it here."""
        assert self._ask(["install_plugin_bundle"], ["code"], "install_plugin_bundle") is False

    def test_a_policy_without_a_grant_approves_no_creator_call(self):
        """The old signature is the old answer: nothing mutating waves through."""
        import asyncio

        policy = plugin_golden.bench_policy(self.STAGING)
        for name in self.STAGING:
            assert asyncio.run(policy.on_confirm(name, {})) is False

    def test_a_granted_case_reaches_the_handler_rather_than_the_approval_gate(
        self, monkeypatch, tmp_path
    ):
        from core.tools import session_ctx

        async def handler(**kwargs):
            return "WROTE " + kwargs["path"]

        case = {
            "id": "alpha-honoured",
            "input": "Write the plugin source for me.",
            "expect": {"kind": "tool_use", "any": ["write_plugin_source"]},
            "mode": "creator",
            "privileges": ["files"],
            "tools": ["write_plugin_source"],
        }
        home = tmp_path / "cfg"
        home.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(home))

        async def fake_chat(**kwargs):
            from core.tools.registry import execute_tool
            from tests.tool_dispatch_seam import patched_tool

            session_ctx.set_current_session(kwargs["session_id"])
            with patched_tool("write_plugin_source", handler):
                result = await execute_tool(case["tools"][0], {"bundle": "x", "path": "a"})
            kwargs["on_tool_done"]("write_plugin_source", result, "call-1")
            return str(result)

        monkeypatch.setattr("core.chat.chat_with_tools", fake_chat)
        monkeypatch.setattr("core.engine_config.resolve_engine_choice", lambda: _Choice())

        transcript = plugin_golden.run_measured(case)[0]

        assert "denied" not in transcript.lower(), transcript
        assert plugin_golden.grade(case, transcript)
