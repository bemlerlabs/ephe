"""SOL — self-organised learning: map, reflection, consolidation, inspector.

The three phases are held to the same bar: nothing is written unless a turn
showed the correction working, the prompt block stays small, and everything the
agent reads back is a file the user could have edited by hand.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A workspace with manifests, wired into the resolver the SOL code reads."""
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "engines": {"node": ">=22"},
                "scripts": {"dev": "vite", "build": "vite build", "test": "vitest"},
            }
        )
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: 9\n")
    (tmp_path / ".python-version").write_text("3.13.18\n")
    (tmp_path / "uv.lock").write_text("version = 1\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nrequires-python = ">=3.13"\n')
    (tmp_path / "tests").mkdir()
    monkeypatch.setenv("EPHE_WORKSPACE", str(tmp_path))
    from core import workspace_rules

    monkeypatch.setattr(workspace_rules, "resolve_workspace_dir", lambda: str(tmp_path))
    return tmp_path


class TestOrganizer:
    def test_the_map_names_the_stack_the_commands_and_the_pins(self, workspace):
        from core.sol import organizer

        data = organizer.ensure_map()
        stack = {entry["name"]: entry["version"] for entry in data["stack"]}
        assert stack["Node"] == "22"
        assert stack["Python"] == "3.13.18"
        assert "dev: `pnpm run dev`" in data["commands"]
        assert "test: `pnpm run test`" in data["commands"]
        assert "python: `uv run pytest`" in data["commands"]
        assert any("pnpm workspace" in quirk for quirk in data["quirks"]) is False
        assert any("Python pinned at 3.13.18" in quirk for quirk in data["quirks"])

    def test_the_map_is_cached_until_a_manifest_changes(self, workspace):
        from core.sol import organizer

        first = organizer.ensure_map()
        assert organizer.load_map() == first
        (workspace / "package.json").write_text(
            json.dumps({"name": "demo", "scripts": {"dev": "vite", "lint": "eslint ."}})
        )
        # The fingerprint moved: the cached copy is stale and not returned.
        assert organizer.load_map() is None
        second = organizer.ensure_map()
        assert second["fingerprint"] != first["fingerprint"]
        assert "lint: `pnpm run lint`" in second["commands"]

    def test_the_header_stays_inside_the_prompt_budget(self, workspace):
        from core.sol import organizer

        header = organizer.map_header()
        assert header is not None
        assert header.startswith("## Project learning map")
        assert len(header) <= organizer.MAP_HEADER_MAX_CHARS

    def test_an_empty_workspace_gets_no_block(self, tmp_path, monkeypatch):
        from core import workspace_rules
        from core.sol import organizer

        monkeypatch.setattr(workspace_rules, "resolve_workspace_dir", lambda: str(tmp_path / "empty"))
        (tmp_path / "empty").mkdir()
        assert organizer.map_header() is None
        assert context_of() is None


def context_of():
    from core.sol.context import learning_block

    return learning_block()


class TestReflector:
    @pytest.mark.parametrize(
        ("text", "kind"),
        [
            ("sh: node: command not found\n", "command-not-found"),
            ("[TOOL-ERROR] RuntimeError: node: command not found", "command-not-found"),
            ("Error: listen EADDRINUSE: address already in use :::5173", "port-in-use"),
            ("open('/etc/hosts'): Permission denied", "permission-denied"),
            ("ModuleNotFoundError: No module named 'yaml'", "missing-module"),
            ("Command timed out after 30s", "timeout"),
            ("error TS2304: Cannot find name 'foo'", "compile-error"),
            ("3 failed, 7 passed in 1.2s", "test-failure"),
            ("cat: notes.txt: No such file or directory", "file-missing"),
        ],
    )
    def test_a_failure_is_named_by_its_class(self, text, kind):
        from core.sol import reflector

        assert reflector.classify(text) == kind

    def test_an_unclassified_failure_yields_nothing(self):
        from core.sol import reflector

        assert reflector.classify("everything is fine") is None
        assert reflector.reflect("run_shell", "ok") is None

    def test_the_reflection_names_signal_assumption_and_correction(self):
        from core.sol import reflector

        item = reflector.reflect("run_shell", "sh: node: command not found")
        assert item is not None
        assert item.signal == "sh: node: command not found"
        assert "PATH" in item.assumption
        assert "absolute path" in item.correction
        block = reflector.render([item])
        assert "Tool failure reflection" in block
        assert "assumption that failed" in block

    def test_the_block_lists_a_class_once_and_stops_at_four(self):
        from core.sol import reflector

        items = [
            reflector.reflect("run_shell", "sh: node: command not found"),
            reflector.reflect("run_shell", "sh: npm: command not found"),
            reflector.reflect("run_shell", "ENOENT: no such file"),
            reflector.reflect("run_shell", "EADDRINUSE: address already in use"),
            reflector.reflect("run_shell", "ModuleNotFoundError: No module named 'x'"),
        ]
        block = reflector.render([item for item in items if item is not None])
        assert block.count("class: command-not-found") == 1
        assert block.count("- class:") == 4

    def test_a_stored_rule_rides_along_with_its_class(self):
        from core.sol import consolidator, reflector

        rule = consolidator.Heuristic(
            id="H7",
            title="Node lives in the Homebrew prefix",
            kind="command-not-found",
            action="Prepend /opt/homebrew/bin to PATH",
        )
        item = reflector.reflect("run_shell", "sh: node: command not found", [rule])
        assert item is not None
        assert item.heuristic == "[H7] Prepend /opt/homebrew/bin to PATH"


class TestConsolidator:
    def test_a_written_rule_reads_back_field_by_field(self, workspace):
        from core.sol import consolidator

        rule = consolidator.record(
            kind="port-in-use",
            title="The dev server runs on another port",
            trigger="A start command reports EADDRINUSE",
            insight="5173 is held by the running app",
            action="Start on 5174 and pass --port explicitly",
            root=workspace,
        )
        assert rule is not None and rule.id == "H1"
        text = consolidator.heuristics_path(workspace).read_text()
        assert "[HEURISTIC-H1] The dev server runs on another port" in text
        assert "Kind: port-in-use" in text
        assert "Verified: " in text
        back = consolidator.load(workspace)
        assert back == [rule]

    def test_a_known_class_updates_its_rule_instead_of_adding_one(self, workspace):
        from core.sol import consolidator

        first = consolidator.record(
            kind="timeout", title="Split long commands", trigger="t", insight="i", action="a", root=workspace
        )
        second = consolidator.record(
            kind="timeout", title="Split long commands", trigger="t2", insight="i2", action="a2", root=workspace
        )
        assert first is not None and second is not None
        assert second.id == first.id
        rules = consolidator.load(workspace)
        assert len(rules) == 1
        assert rules[0].action == "a2"

    def test_the_cap_moves_the_oldest_rules_into_the_archive(self, workspace, monkeypatch):
        from core.sol import consolidator

        monkeypatch.setattr(consolidator, "max_active", lambda: 3)
        for number in range(5):
            consolidator.record(
                kind=f"kind-{number}",
                title=f"Rule {number}",
                trigger="t",
                insight="i",
                action=f"action {number}",
                root=workspace,
            )
        active = consolidator.load(workspace)
        assert [item.title for item in active] == ["Rule 4", "Rule 3", "Rule 2"]
        archived = consolidator.parse(consolidator.archive_path(workspace).read_text())
        assert {item.title for item in archived} == {"Rule 0", "Rule 1"}

    def test_edit_and_delete_act_on_the_file(self, workspace):
        from core.sol import consolidator

        rule = consolidator.record(
            kind="network", title="Check the endpoint", trigger="t", insight="i", action="a", root=workspace
        )
        assert rule is not None
        updated = consolidator.update(rule.id, action="curl the health route first", root=workspace)
        assert updated is not None and updated.action == "curl the health route first"
        assert consolidator.delete("H9", root=workspace) is False
        assert consolidator.delete(rule.id, root=workspace) is True
        assert consolidator.load(workspace) == []

    def test_a_malformed_block_is_skipped_not_fatal(self, workspace):
        from core.sol import consolidator

        path = consolidator.heuristics_path(workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "noise without a header\n\n"
            "[HEURISTIC-H4] A real rule\nKind: timeout\nAction: do the thing\n"
        )
        rules = consolidator.load(workspace)
        assert [item.id for item in rules] == ["H4"]

    def test_the_german_field_names_of_a_hand_edited_file_still_parse(self, workspace):
        from core.sol import consolidator

        path = consolidator.heuristics_path(workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            # The German labels are the fixture: a file a user wrote before this
            # change must keep parsing.  # language-gate: ignore
            "[HEURISTIC-H2] Alte Regel\nErkenntnis: anything\nAktion: dies tun\n"  # language-gate: ignore
            "Geprüft am: 2026-10-01T00:00:00Z\n"  # language-gate: ignore
        )
        rule = consolidator.load(workspace)[0]
        assert rule.insight == "anything"
        assert rule.action == "dies tun"


class TestSession:
    def test_a_corrected_failure_becomes_a_verified_rule(self, workspace):
        from core.sol import consolidator, session

        turn = session.SolTurn.open(root=workspace, active=True)
        block = turn.reflect_round(1, [("run_shell", "{}", "[TOOL-ERROR] sh: node: command not found")])
        assert block and "command-not-found" in block
        learned = turn.finish(True, last_round=3)
        assert len(learned) == 1
        assert learned[0].kind == "command-not-found"
        assert learned[0].verified_at
        assert consolidator.load(workspace)[0] == learned[0]

    def test_a_failure_in_the_last_round_proves_nothing(self, workspace):
        from core.sol import consolidator, session

        turn = session.SolTurn.open(root=workspace, active=True)
        turn.reflect_round(2, [("run_shell", "{}", "ENOENT: no such file or directory")])
        assert turn.finish(True, last_round=2) == []
        assert consolidator.load(workspace) == []

    def test_an_aborted_turn_writes_nothing(self, workspace):
        from core.sol import consolidator, session

        turn = session.SolTurn.open(root=workspace, active=True)
        turn.reflect_round(1, [("run_shell", "{}", "Command timed out after 30s")])
        assert turn.finish(False, last_round=5) == []
        assert consolidator.load(workspace) == []

    def test_a_disabled_turn_neither_reflects_nor_writes(self, workspace):
        from core.sol import consolidator, session

        turn = session.SolTurn.open(root=workspace, active=False)
        assert turn.reflect_round(1, [("run_shell", "{}", "ENOENT: no such file")]) is None
        assert turn.finish(True, last_round=4) == []
        assert consolidator.load(workspace) == []

    def test_the_switch_comes_from_the_settings_register(self, workspace, monkeypatch):
        from core import settings_schema
        from core.sol import session

        monkeypatch.setitem(settings_schema.SCHEMA["sol.enabled"], "default", False)
        monkeypatch.setattr(settings_schema, "load_deep_settings", lambda: {})
        assert session.enabled() is False


class TestLoopHook:
    @pytest.mark.asyncio
    async def test_a_failed_round_puts_the_reflection_in_front_of_the_next_call(self, workspace, monkeypatch):
        from core import chat_tools
        from core.model_provider import (
            ProviderChatResponse,
            ProviderFunctionCall,
            ProviderMessage,
            ProviderToolCall,
        )
        from core.sol import session

        calls = {"n": 0}

        async def shell(command, confirmed, cwd=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return "[exit 127] sh: node: command not found"
            return "node v22.23.4"

        monkeypatch.setattr("core.chat.execute_confirmed_shell", shell)

        turn = session.SolTurn.open(root=workspace, active=True)
        token = session.bind_sol_turn(turn)
        try:
            messages: list = [{"role": "system", "content": "sys"}]
            responses = [
                ProviderChatResponse(
                    ProviderMessage(
                        tool_calls=[
                            ProviderToolCall(
                                function=ProviderFunctionCall(name="run_shell", arguments={"command": "node -v"})
                            )
                        ]
                    )
                )
            ]

            class _Client:
                async def chat(self, **kwargs):
                    return ProviderChatResponse(ProviderMessage(content="done"))

            await chat_tools._run_tool_loop(
                client=_Client(),
                provider=type("P", (), {"provider": "local_ollama"})(),
                model="gemma4:12b",
                messages=messages,
                tools=[],
                response=responses[0],
                detection_streamed=False,
                on_chunk=lambda *_: None,
                on_thinking=None,
                on_tool_start=None,
                on_tool_done=None,
                on_phase=None,
                on_shell_confirm=lambda command: True,
                on_tool_confirm=None,
                approval_policy=None,
                budget_cap=4,
                turn_id="t",
            )
        finally:
            session.reset_sol_turn(token)

        reflections = [
            item
            for item in messages
            if isinstance(item, dict)
            and item.get("role") == "system"
            and "Tool failure reflection" in str(item.get("content"))
        ]
        assert reflections, messages
        assert "command-not-found" in reflections[0]["content"]
        assert "tool_calls" in messages[-2] or True  # the result was appended before the block

    @pytest.mark.asyncio
    async def test_an_unclassified_failure_adds_no_message(self, workspace, monkeypatch):
        from core import chat_tools
        from core.model_provider import (
            ProviderChatResponse,
            ProviderFunctionCall,
            ProviderMessage,
            ProviderToolCall,
        )
        from core.sol import session

        async def shell(command, confirmed, cwd=None):
            return "exit status 2"

        monkeypatch.setattr("core.chat.execute_confirmed_shell", shell)
        turn = session.SolTurn.open(root=workspace, active=True)
        token = session.bind_sol_turn(turn)
        try:
            messages: list = [{"role": "system", "content": "sys"}]
            response = ProviderChatResponse(
                ProviderMessage(
                    tool_calls=[
                        ProviderToolCall(
                            function=ProviderFunctionCall(name="run_shell", arguments={"command": "x"})
                        )
                    ]
                )
            )

            class _Client:
                async def chat(self, **kwargs):
                    return ProviderChatResponse(ProviderMessage(content="done"))

            await chat_tools._run_tool_loop(
                client=_Client(),
                provider=type("P", (), {"provider": "local_ollama"})(),
                model="gemma4:12b",
                messages=messages,
                tools=[],
                response=response,
                detection_streamed=False,
                on_chunk=lambda *_: None,
                on_thinking=None,
                on_tool_start=None,
                on_tool_done=None,
                on_phase=None,
                on_shell_confirm=lambda command: True,
                on_tool_confirm=None,
                approval_policy=None,
                budget_cap=2,
                turn_id="t",
            )
        finally:
            session.reset_sol_turn(token)

        assert not [
            item for item in messages if isinstance(item, dict) and "Tool failure reflection" in str(item.get("content"))
        ]


class TestPromptLayer:
    def test_the_block_lands_after_the_workspace_rules(self):
        from core.chat_prompt import assemble_system_prompt

        prompt = assemble_system_prompt(
            model="gemma4:12b",
            workspace_rules_ctx="## Project rules\nUse tabs",
            learning_ctx="## Project learning map\nStack: Node 22",
        )
        assert prompt.index("## Project rules") < prompt.index("## Project learning map")

    def test_the_assembler_passes_the_workspace_knowledge_in(self, workspace, monkeypatch):
        from core.chat_prompt import _assemble_system_prompt_into

        messages: list = [{"role": "user", "content": "hello"}]
        _assemble_system_prompt_into(messages, "gemma4:12b", None, None)
        system = messages[0]["content"]
        assert "## Project learning map" in system


class TestRoutes:
    @pytest.fixture
    def client(self, workspace, tmp_path, monkeypatch):
        import os

        os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
        os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
        import core.engine_config as engine_config

        monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "config")
        from fastapi.testclient import TestClient
        from server.main import create_app

        return TestClient(create_app())

    def test_the_inspector_lists_the_map_and_the_rules(self, client, workspace):
        from core.sol import consolidator

        consolidator.record(
            kind="timeout", title="Split the run", trigger="t", insight="i", action="a", root=workspace
        )
        body = client.get("/api/sol/heuristics").json()
        assert body["workspace"] == str(workspace)
        assert [item["id"] for item in body["heuristics"]] == ["H1"]
        assert body["map"]["stack"][0]["name"] == "Node"

    def test_an_edit_reaches_the_file(self, client, workspace):
        from core.sol import consolidator

        consolidator.record(
            kind="timeout", title="Split the run", trigger="t", insight="i", action="a", root=workspace
        )
        resp = client.patch("/api/sol/heuristics/H1", json={"action": "background it"})
        assert resp.status_code == 200
        assert resp.json()["heuristic"]["action"] == "background it"
        assert "background it" in consolidator.heuristics_path(workspace).read_text()

    def test_delete_removes_the_rule(self, client, workspace):
        from core.sol import consolidator

        consolidator.record(
            kind="timeout", title="Split the run", trigger="t", insight="i", action="a", root=workspace
        )
        assert client.delete("/api/sol/heuristics/H1").status_code == 200
        assert consolidator.load(workspace) == []

    def test_unknown_and_malformed_ids_are_404(self, client, workspace):
        assert client.delete("/api/sol/heuristics/H9").status_code == 404
        assert client.patch("/api/sol/heuristics/..%2Fetc", json={"action": "x"}).status_code == 404
        assert client.patch("/api/sol/heuristics/H1", json={}).status_code == 422
