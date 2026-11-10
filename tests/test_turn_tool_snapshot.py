"""Task #36 — one deterministic offer array per turn.

Three properties, measured the way the engine sees them:
1. the whole array (kernel, MCP and dynamic entries) carries one stable order —
   two builds of one state are byte-identical in name order, and a build already
   handed out never moves when the state changes underneath it;
2. a turn freezes the array at its first request: a mid-turn MCP tool or descriptor
   reaches the model on the NEXT turn, not to the one already offered an array;
3. both chat routes derive their array from the same inputs and hand the model the
   same bytes for one fixed state (they share ``_mode_context`` today).

The TTL caches are pinned to zero in these tests on purpose: without the freeze the
second read of a turn would then rebuild, so what stays equal across the two reads is
the freeze itself, never a window of the cache.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.tools import turn_snapshot
from core.tools.dynamic_registry import (
    ToolDescriptor,
    default_registry,
    fingerprint_for,
    served_tool_name,
)
from core.tools.mcp_client import register_mcp_tool, unregister_mcp_tools
from core.tools.registry import get_tool_schemas, invalidate_tool_schema_cache

_REGISTRY = default_registry()
_TOUCHED_PLUGINS: set[str] = set()
_TOUCHED_MCP = False


def _schema(name: str) -> dict:
    return {
        "name": name,
        "description": "Reports the tide level for one harbor.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }


def _descriptor(plugin_id: str, tool: str) -> ToolDescriptor:
    name = served_tool_name(plugin_id, tool)
    _TOUCHED_PLUGINS.add(plugin_id)
    schema = {"type": "function", "function": _schema(name)}
    return ToolDescriptor(
        name=name,
        plugin_id=plugin_id,
        schema=schema,
        transport="plugin",
        entry="handlers:run",
        tool_family="read",
        fingerprint=fingerprint_for(schema),
    )


def _register_mcp(name: str) -> None:
    global _TOUCHED_MCP
    _TOUCHED_MCP = True

    async def _call(arguments: dict) -> tuple[str, bool]:  # noqa: ARG001
        return "never called here", False

    register_mcp_tool(name, "tide-server", "tide", _call, _schema(name))


def _names(schemas: list[dict]) -> list[str]:
    return [
        entry["function"]["name"]
        for entry in schemas
        if isinstance(entry.get("function"), dict) and entry["function"].get("name")
    ]


def _text_response():
    message = MagicMock()
    message.content = "the turn answered"
    message.tool_calls = []
    response = MagicMock()
    response.message = message
    return response


@pytest.fixture(autouse=True)
def cfg(tmp_path, monkeypatch):
    """A hermetic config, cold caches, zero TTLs and no leftovers between tests."""
    root = tmp_path / "cfg"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(root))
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(root / "persona"))
    monkeypatch.setenv("EPHE_WORKSPACE", str(tmp_path / "workspace"))
    from core.tools import registry

    monkeypatch.setattr(registry, "TOOL_SCHEMA_CACHE_TTL_SECONDS", 0.0)
    turn_snapshot.clear_frozen_turns()
    invalidate_tool_schema_cache()
    yield root
    for plugin_id in _TOUCHED_PLUGINS:
        _REGISTRY.unregister_plugin(plugin_id)
    _TOUCHED_PLUGINS.clear()
    if _TOUCHED_MCP:
        unregister_mcp_tools()
    turn_snapshot.clear_frozen_turns()
    invalidate_tool_schema_cache()


class TestDeterministicOrder:
    def test_two_builds_of_one_state_are_byte_identical_in_name_order(self):
        """GIVEN one tool state built twice through different registration orders
        WHEN the two arrays are compared
        THEN they are byte-identical and every name sits in sorted order."""
        _register_mcp("mcp_zeta_probe")
        _register_mcp("mcp_alpha_probe")
        assert _REGISTRY.register(_descriptor("timer", "brake")).ok
        assert _REGISTRY.register(_descriptor("timer", "accelerate")).ok
        first = get_tool_schemas()
        first_bytes = json.dumps(first)

        unregister_mcp_tools()
        assert _REGISTRY.unregister_plugin("timer") == 2
        _register_mcp("mcp_alpha_probe")
        _register_mcp("mcp_zeta_probe")
        assert _REGISTRY.register(_descriptor("timer", "accelerate")).ok
        assert _REGISTRY.register(_descriptor("timer", "brake")).ok
        second = get_tool_schemas()

        assert json.dumps(second) == first_bytes
        names = _names(first)
        assert names == sorted(names)
        assert {"mcp_alpha_probe", "mcp_zeta_probe", "accelerate"} <= set(names)

    def test_a_handed_out_array_is_not_moved_by_a_refresh_and_a_registration(self):
        """GIVEN an array already handed to a caller
        WHEN an MCP refresh re-registers tools and a descriptor is added between
        this build and the next
        THEN the handed-out array keeps its bytes, and the new build stays in
        name order."""
        _register_mcp("mcp_beta_probe")
        handed_out = get_tool_schemas()
        handed_bytes = json.dumps(handed_out)

        unregister_mcp_tools()
        _register_mcp("mcp_gamma_probe")
        _register_mcp("mcp_beta_probe")
        assert _REGISTRY.register(_descriptor("alarmit", "ring")).ok
        moved = get_tool_schemas()

        assert json.dumps(handed_out) == handed_bytes
        moved_names = _names(moved)
        assert moved_names == sorted(moved_names)
        assert "ring" in moved_names
        assert "mcp_gamma_probe" not in _names(handed_out)
        assert "mcp_beta_probe" in _names(handed_out)


class TestPerTurnFreeze:
    @pytest.mark.asyncio
    async def test_a_mid_turn_change_reaches_the_next_turn_only(self, cfg):  # noqa: ARG002
        """GIVEN a turn whose first request registers a new MCP tool and descriptor
        WHEN the same turn makes its revision-half request, then a new turn runs
        THEN every request of the turn carries the array the turn started with,
        and only the new turn's request offers the change."""
        from core.chat import chat_with_tools

        class _Recorder:
            def __init__(self):
                self.arrays: list[list[str]] = []
                self.mutated = False

            async def chat(self, **kwargs):
                self.arrays.append(
                    json.dumps([t["function"]["name"] for t in kwargs.get("tools") or []])
                )
                if not self.mutated:
                    self.mutated = True
                    _register_mcp("mcp_zeta_probe")
                    assert _REGISTRY.register(_descriptor("turnprobe", "tick")).ok
                return _text_response()

        recorder = _Recorder()
        allowed = ["read_file", "tick", "mcp_zeta_probe"]
        turn_id = f"turn-{uuid.uuid4().hex}"
        history = [{"role": "user", "content": "check the tide"}]

        with patch("core.chat.build_provider_client", return_value=recorder):
            await chat_with_tools(
                model="gemma4:12b",
                history=history,
                on_chunk=lambda _c: None,
                allowed_tool_names=allowed,
                turn_id=turn_id,
            )
            # The revision half of the same user turn — the route shape at
            # server/routes/chat.py:2541 reuses the turn id.
            await chat_with_tools(
                model="gemma4:12b",
                history=history,
                on_chunk=lambda _c: None,
                allowed_tool_names=allowed,
                turn_id=turn_id,
            )
            assert recorder.arrays[0] == recorder.arrays[-1]
            offered = json.loads(recorder.arrays[0])
            assert "mcp_zeta_probe" not in offered
            assert "tick" not in offered
            assert offered == sorted(offered)

            recorder.arrays.clear()
            await chat_with_tools(
                model="gemma4:12b",
                history=history,
                on_chunk=lambda _c: None,
                allowed_tool_names=allowed,
                turn_id=f"turn-{uuid.uuid4().hex}",
            )
        next_names = json.loads(recorder.arrays[0])
        assert "mcp_zeta_probe" in next_names
        assert "tick" in next_names
        assert next_names == sorted(next_names)

    @pytest.mark.asyncio
    async def test_a_mount_mid_turn_becomes_visible_on_the_next_turn_only(
        self, cfg, tmp_path, monkeypatch
    ):  # noqa: ARG002
        """GIVEN a turn that hot-mounts a declared bundle while it is already running
        WHEN the same turn reads its tools again and a fresh turn follows
        THEN the running turn never sees the mounted name, and the next turn's array
        carries it — the freeze is what keeps a mid-turn growth from becoming a
        hallucination trigger, and #15 must not be the change that leaks past it."""
        import json as _json

        from core import plugin_manifest, plugin_runtime
        from core.chat import chat_with_tools

        root = tmp_path / "plugins"
        bundle = root / "mountprobe"
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / "ephe-plugin.json").write_text(
            _json.dumps(
                {
                    "manifest_version": 2,
                    "name": "mountprobe",
                    "version": "0.1.0",
                    "description": "A bundle mounted mid-turn.",
                    "publisher": {"name": "Ephe"},
                    "license": "MIT",
                    "permissions": {"tool_families": ["read"], "data_roots": []},
                    "components": {
                        "skills": [],
                        "commands": [],
                        "tools": [
                            {
                                "name": "tick",
                                "entry": "handlers.py:run",
                                "family": "read",
                                "description": "Report how many seconds are left.",
                            }
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        (bundle / "handlers.py").write_text(
            "def run(arguments, state_dir):\n    return {'unit': arguments.get('unit')}\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", root)
        plugin_runtime.invalidate_ownership_cache()
        served = served_tool_name("mountprobe", "tick")
        state = plugin_runtime.lifecycle()

        class _Recorder:
            def __init__(self):
                self.arrays: list[str] = []
                self.mounted = False

            async def chat(self, **kwargs):
                self.arrays.append(
                    _json.dumps([t["function"]["name"] for t in kwargs.get("tools") or []])
                )
                if not self.mounted:
                    self.mounted = True
                    assert state.mount("mountprobe").names == (served,)
                return _text_response()

        recorder = _Recorder()
        allowed = ["read_file", served]
        turn_id = f"turn-{uuid.uuid4().hex}"
        history = [{"role": "user", "content": "count the seconds"}]
        try:
            with patch("core.chat.build_provider_client", return_value=recorder):
                await chat_with_tools(
                    model="gemma4:12b", history=history, on_chunk=lambda _c: None,
                    allowed_tool_names=allowed, turn_id=turn_id,
                )
                await chat_with_tools(
                    model="gemma4:12b", history=history, on_chunk=lambda _c: None,
                    allowed_tool_names=allowed, turn_id=turn_id,
                )
                assert recorder.arrays[0] == recorder.arrays[-1]
                offered = _json.loads(recorder.arrays[0])
                assert served not in offered
                assert offered == sorted(offered)

                recorder.arrays.clear()
                await chat_with_tools(
                    model="gemma4:12b", history=history, on_chunk=lambda _c: None,
                    allowed_tool_names=allowed, turn_id=f"turn-{uuid.uuid4().hex}",
                )
            next_names = _json.loads(recorder.arrays[0])
            assert served in next_names
            assert next_names == sorted(next_names)
        finally:
            _REGISTRY.unregister_plugin("mountprobe")
            plugin_runtime.invalidate_ownership_cache()


class TestRouteParity:
    def test_both_chat_routes_build_the_identical_array_for_one_state(self, cfg):  # noqa: ARG002
        """GIVEN one fixed state and the same mode on both chat routes
        WHEN each route assembles its context and its array through the shared
        builders (/api/chat and /api/chat/stream today share _mode_context)
        THEN the arrays are byte-identical and in name order."""
        from core.chat_context import _tools_for_messages
        from server.routes.chat import _mode_context

        message = "plot the tide table"
        for mode in ("operator", "architect"):
            rest_ctx = _mode_context(mode, skill=None, message=message)
            stream_ctx = _mode_context(mode, skill=None, message=message)
            rest = _tools_for_messages(
                [{"role": "user", "content": message}],
                allowed_tool_names=rest_ctx[1],
            )
            stream = _tools_for_messages(
                [{"role": "user", "content": message}],
                allowed_tool_names=stream_ctx[1],
            )
            assert json.dumps(stream) == json.dumps(rest)
            assert rest, f"mode {mode} offered nothing"
            names = _names(rest)
            assert names == sorted(names)
