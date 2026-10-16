"""W3-38 — byte-stable prompt prefixes so the engine's prefix cache can hit.

The system prompt is the *front* of every request: one byte that changes
between turns invalidates the engine's KV/prefix cache for everything after it
— the rest of the system text *and the whole conversation*. These tests pin the
assembly so the longest possible prefix is byte-identical turn over turn and
only the genuinely volatile blocks (per-turn memory, the daily date) sit at the
tail.

``_shared_prefix_len`` is the "prefix-stability counter" item 10 of
``docs/RESEARCH_ADOPTION_2026-10-09.md`` asks for — measured here, not taken
from a docstring.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def persona_home(tmp_path, monkeypatch):
    """A hermetic home: persona materializes here, and no host workspace,
    profile or plugin-registry bytes leak into the assembled prefix."""
    home = tmp_path / "ephe-home"
    home.mkdir()
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(home))
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("EPHE_WORKSPACE", str(ws))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    # Isolated plugin registry (no host plugins.json → every tool family
    # visible), then a warm-up: the schema cache is global and not keyed on the
    # config dir, and the first get_tool_schemas() after a cold cache can differ
    # from later ones (the plugin gate runs on the cache-miss path only). Force a
    # rebuild under this config, then take the steady-state list the turn-to-turn
    # cache actually sees.
    from core.tools.registry import get_tool_schemas, invalidate_tool_schema_cache

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    invalidate_tool_schema_cache()
    get_tool_schemas()
    get_tool_schemas()
    return home


def _shared_prefix_len(a: str, b: str) -> int:
    """Characters the two prompts share from offset 0 — the cacheable prefix."""
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def _turn(memory_ctx: str | None = None) -> str:
    """One assembled system prompt with every block filled, so byte offsets are
    all present to compare."""
    from core.chat import assemble_system_prompt

    return assemble_system_prompt(
        model="test-model",
        incoming_system="[Skill]",
        extra_system_prompt="[Extra]",
        workspace_rules_ctx="[Workspace]",
        profile_ctx="[Profile]",
        corrections_ctx="[Corrections]",
        feedback_ctx="[Feedback]",
        memory_ctx=memory_ctx,
    )


class TestIdentityBlockIsStatic:
    def test_identity_block_consults_no_clock(self, monkeypatch):
        """The very front of every request must not depend on the wall clock."""
        from core import persona

        def _boom(*_a, **_k):  # pragma: no cover - only fires on a regression
            raise AssertionError("identity consulted the clock — the prefix is not byte-stable")

        monkeypatch.setattr(persona, "_dt_now", _boom)
        block = persona.build_identity_block("test-model")
        assert "Current date" not in block
        assert block == persona.build_identity_block("test-model")

    def test_the_date_is_its_own_block(self):
        from datetime import datetime

        from core.persona import build_date_block

        assert build_date_block(datetime(2026, 10, 11)) == "Current date: 2026-10-11."


class TestAssemblyOrdersStableFirst:
    def test_block_order_is_most_stable_to_least_stable(self, persona_home):
        from core.chat_prompt import KNOWLEDGE_GAP_PROTOCOL

        prompt = _turn(memory_ctx="[Memory]")
        offsets = [
            prompt.index("IDENTITY:"),              # static core
            prompt.index("[Skill]"),
            prompt.index("[Extra]"),
            prompt.index(KNOWLEDGE_GAP_PROTOCOL),   # constant
            prompt.index("[Workspace]"),            # per workspace
            prompt.index("[Profile]"),              # per profile
            prompt.index("[Corrections]"),          # rarely change
            prompt.index("[Feedback]"),
            prompt.index("[Memory]"),               # per turn (volatile)
            prompt.index("Current date:"),          # per day, last
        ]
        assert offsets == sorted(offsets), "a volatile block slipped in front of a stabler one"

    def test_the_constant_protocol_sits_in_the_stable_prefix(self, persona_home):
        """The constant protocol must precede every per-turn block — otherwise a
        memory change would push it out of the cache every turn."""
        from core.chat_prompt import KNOWLEDGE_GAP_PROTOCOL

        prompt = _turn(memory_ctx="[Memory]")
        assert KNOWLEDGE_GAP_PROTOCOL in prompt
        assert prompt.index(KNOWLEDGE_GAP_PROTOCOL) < prompt.index("[Workspace]")
        assert prompt.index(KNOWLEDGE_GAP_PROTOCOL) < prompt.index("[Memory]")


class TestPrefixIsByteStable:
    def test_identical_inputs_are_byte_identical(self, persona_home):
        assert _turn(memory_ctx="[Memory]") == _turn(memory_ctx="[Memory]")

    def test_only_the_per_turn_memory_breaks_the_prefix(self, persona_home):
        """Two turns that differ only in retrieved memory must share every byte
        up to the memory block — the stable core, the constant protocol and the
        four context blocks all survive the cache."""
        a = _turn(memory_ctx="[Memory: alpha]")
        b = _turn(memory_ctx="[Memory: beta]")
        assert a != b

        memory_at = a.index("[Memory")
        shared = _shared_prefix_len(a, b)
        assert shared >= memory_at, f"prefix broke at {shared}, before the memory block at {memory_at}"
        for marker in ("IDENTITY:", "[Skill]", "[Extra]", "[Workspace]", "[Profile]", "[Corrections]", "[Feedback]"):
            end = a.index(marker) + len(marker)
            assert end <= shared, f"{marker!r} ended at {end} but the prefix broke at {shared}"

    def test_the_daily_date_is_the_last_thing_that_rotates(self, monkeypatch, persona_home):
        """With no per-turn memory the only moving part is the date, and it must
        be the tail — otherwise the daily rotation would cut the prefix short."""
        from core import persona

        class _Clock:
            iso = "2026-10-11"

            @classmethod
            def now(cls):
                from datetime import datetime

                return datetime.strptime(cls.iso, "%Y-%m-%d")

        monkeypatch.setattr(persona, "_dt_now", _Clock)

        from core.chat import assemble_system_prompt

        day1 = assemble_system_prompt(model="test-model", incoming_system="[Skill]", profile_ctx="[Profile]")
        _Clock.iso = "2026-10-12"
        day2 = assemble_system_prompt(model="test-model", incoming_system="[Skill]", profile_ctx="[Profile]")

        assert day1 != day2, "the date block stopped tracking the day"
        date_at = day1.index("Current date:")
        assert date_at > 0
        assert day1[:date_at] == day2[:date_at], "a block before the date changed on the daily rotation"
        assert _shared_prefix_len(day1, day2) >= date_at
        assert day1.rstrip().endswith("Current date: 2026-10-11.")
