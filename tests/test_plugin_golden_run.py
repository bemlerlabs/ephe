"""The golden runner hands the engine's transcript to the mechanical grader."""
from __future__ import annotations

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
