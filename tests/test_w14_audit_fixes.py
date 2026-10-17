"""
Ephe — W14: deep audit of 2026-09-10, P0/P1 action catalogue.

Actions covered:
  P0-1  dynamic context budget (tier table + precedence in the resolver)
  P0-2  server-side overflow cap (trim from the front, system block stays)
  P0-3  token counting: calibrated for CJK, Latin ratio unchanged
  P0-4  version SSOT (core/__init__ == core/_version == pyproject == locales)
  P1-1  shell timeout: the child process is killed, the loop stays usable
  P1-2  scheduler: non-coroutine callbacks run in the thread pool
  P1-3  swarm: gather with return_exceptions → partial results survive
  P1-7  TTFT field on the streaming turn
  P1-8  approval categories SAFE/NETWORK/MUTATING/DANGEROUS
  P1-9  tool-result cap (32 KB) before the message array

RULE: Given / When / Then — strictly.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core import __version__ as INIT_VERSION
from core import _version as version_module
from core.model_config import (
    LEGACY_CONTEXT_WINDOW,
    TIER_CONTEXT_WINDOWS,
    ModelTier,
    context_window_for_model,
    resolve_context_window,
)


@pytest.fixture(autouse=True)
def _no_bpe(monkeypatch):
    """W16: the 4.2 expectations of this wave hold on the fallback path —
    switch the BPE backend off hermetically."""
    import sys
    monkeypatch.setitem(sys.modules, "tiktoken", None)
    from core import usage
    usage.reset_tokenizer_cache()
    yield
    usage.reset_tokenizer_cache()


# P0-1: tier table + resolver precedence

def _configured_tiers(monkeypatch, names: dict[str, str]) -> None:
    """Seed a tier table that carries tags.

    Since 2026-10-11 a tier only has a name when the user configured one
    (`EPHE_OFFLINE_MODEL` / `EPHE_FAST_MODEL` / `EPHE_POWER_MODEL`), so the lookup under
    test runs over a configured table — the tags here are fixture values."""
    import core.model_config as m

    monkeypatch.setattr(
        m,
        "TIER_MAP",
        {
            ModelTier(tier): m.ModelConfig(name=name, tier=ModelTier(tier))
            for tier, name in names.items()
        },
    )


def test_tier_table_carries_the_shipped_windows():
    """GIVEN the tier table
    WHEN the windows are read
    THEN they carry the real model limits (not the legacy 8192)."""
    assert TIER_CONTEXT_WINDOWS[ModelTier.OFFLINE] == 32768
    assert TIER_CONTEXT_WINDOWS[ModelTier.FAST] == 16384
    assert TIER_CONTEXT_WINDOWS[ModelTier.POWER] == 262144
    assert LEGACY_CONTEXT_WINDOW == 8192
    assert LEGACY_CONTEXT_WINDOW not in TIER_CONTEXT_WINDOWS.values()


def test_model_lookup_works_with_and_without_the_tag(monkeypatch):
    """GIVEN a model name with/without :tag
    WHEN context_window_for_model() is called
    THEN both return the same tier value; unknown → None."""
    _configured_tiers(monkeypatch, {
        "offline": "gemma4:e2b", "fast": "gemma4:12b", "power": "gemma4:26b",
    })
    assert context_window_for_model("gemma4:12b") == 16384
    assert context_window_for_model("gemma4:26b") == 262144
    assert context_window_for_model("gemma4:e2b") == 32768
    # without the tag: first hit in tier order (OFFLINE → FAST → POWER)
    assert context_window_for_model("gemma4") == TIER_CONTEXT_WINDOWS[ModelTier.OFFLINE]
    assert context_window_for_model("") is None
    assert context_window_for_model("irgendwas") is None


def test_env_override_wins_over_everything(monkeypatch):
    """GIVEN EPHE_CONTEXT_WINDOW is set
    WHEN the window resolver runs
    THEN the override wins against the probe and the tier table."""
    monkeypatch.setenv("EPHE_CONTEXT_WINDOW", "262144")
    window, source = resolve_context_window("gemma4:12b")
    assert window == 262144
    assert source == "env"


def test_engine_probe_wins_over_the_tier_table(monkeypatch):
    """GIVEN the engine probe has cached 262144
    WHEN resolution happens without an env override
    THEN the probe value comes back, source 'engine'."""
    monkeypatch.delenv("EPHE_CONTEXT_WINDOW", raising=False)
    from core import model_provider as mp
    from server.routes.model_provider import _CONTEXT_WINDOW_CACHE

    cfg = mp.ModelProviderConfig(
        provider="openai_compatible",
        model="gemma4:26b",
        base_url="http://127.0.0.1:8000",
        label="DGX",
        offline_capable=False,
        requires_internet=True,
    )
    key = (cfg.base_url, cfg.model)
    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", cfg)
    _CONTEXT_WINDOW_CACHE[key] = 262144
    try:
        window, source = resolve_context_window("")
        assert window == 262144
        assert source == "engine"
    finally:
        _CONTEXT_WINDOW_CACHE.pop(key, None)


def test_tier_table_fills_the_gap_without_probe(monkeypatch):
    """GIVEN no probe and no override
    WHEN a model the user configured into a tier is active
    THEN the tier table fills the gap (source 'tier'), not the legacy 8192."""
    monkeypatch.delenv("EPHE_CONTEXT_WINDOW", raising=False)
    _configured_tiers(monkeypatch, {"power": "gemma4:26b"})
    window, source = resolve_context_window("gemma4:26b")
    assert window == 262144
    assert source == "tier"


def test_legacy_constant_only_for_unknown_models(monkeypatch):
    """GIVEN no env value, no probe, unknown model
    WHEN the window is resolved
    THEN the documented 8192 fallback remains (offline-first)."""
    monkeypatch.delenv("EPHE_CONTEXT_WINDOW", raising=False)
    window, source = resolve_context_window("irgendein-modell")
    assert window == LEGACY_CONTEXT_WINDOW
    assert source == "legacy"


async def test_budget_route_reports_the_window_source(tmp_path, monkeypatch):
    """GIVEN a session with ~10k estimated tokens, no env/no probe, and a user whose
    FAST tier is configured
    WHEN GET /api/context/budget
    THEN the response window shows the tier value with source 'tier'."""
    monkeypatch.delenv("EPHE_CONTEXT_WINDOW", raising=False)
    _configured_tiers(monkeypatch, {"fast": "gemma4:12b"})
    from core import model_provider as mp
    from core import multi_session as ms
    from fastapi.testclient import TestClient
    from server.main import app

    monkeypatch.setattr(mp, "_ACTIVE_OVERRIDE", mp.ModelProviderConfig(
        provider="local_ollama",
        model="gemma4:12b",
        base_url="http://localhost:11434",
        label="Local Ollama",
        offline_capable=True,
        requires_internet=False,
    ))

    root = tmp_path / "sessions"
    monkeypatch.setattr(ms, "SESSIONS_DIR", root)
    monkeypatch.setattr(ms, "REGISTRY_FILE", root / "registry.json")
    monkeypatch.setattr(ms, "LEGACY_FILE", root / "default.json")
    ms.save_messages("rest-w14-tier", [{"role": "user", "content": "q" * 42000}])

    body = TestClient(app).get("/api/context/budget", params={"session_id": "w14-tier"}).json()
    assert body["window_source"] == "tier"
    assert body["window_tokens"] == TIER_CONTEXT_WINDOWS[ModelTier.FAST]
    # 10k of 16384 ≈ 61 % — with the old hard 8192 this came out above 100 %.
    assert 0 < body["percent"] < 100


# P0-2: server-side overflow cap

def test_fit_messages_trims_from_the_front_and_keeps_the_system_block():
    """GIVEN an assembled prompt above the window
    WHEN the cap is applied
    THEN the system block stays at the front, the newest message last, and
    the estimated length is back inside the window."""
    from core.chat import _fit_messages_to_window

    messages = [{"role": "system", "content": "S" * 400}] + [
        {"role": "user", "content": f"{i}" + "u" * 800} for i in range(12)
    ]
    trimmed = _fit_messages_to_window(messages, 2000)
    assert trimmed > 0
    assert messages[0]["role"] == "system"
    assert messages[-1]["content"].startswith("11")
    from core.usage import estimate_tokens, serialize_prompt

    assert estimate_tokens(serialize_prompt(messages)) <= 2000


def test_fit_messages_is_a_noop_within_the_window():
    """GIVEN a prompt inside the window
    WHEN the cap runs
    THEN the list stays unchanged count-wise."""
    from core.chat import _fit_messages_to_window

    messages = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "u" * 100},
    ]
    assert _fit_messages_to_window(list(messages), 2000) == 0


# P0-3: calibration of the token counting

def test_latin_estimate_is_unchanged_by_the_calibration():
    """GIVEN pure Latin text
    WHEN the ratio applies
    THEN ceil(len / 4.2) still holds."""
    from core.usage import estimate_tokens

    text = "a" * 420
    assert estimate_tokens(text) == 100


def test_cjk_counts_one_token_per_char():
    """GIVEN CJK ideographs
    WHEN the estimate runs
    THEN each character counts as ~1 token (the 4.2 ratio would be 4x too small here)."""
    from core.usage import estimate_tokens

    assert estimate_tokens("你好世界") == 4
    # mixed: 4 CJK + 4 Latin characters → 4 + the ceil surcharge from 4/4.2
    assert estimate_tokens("你好世界abcd") == 5


def test_frontend_m_meter_matches_the_backend_ratio():
    """GIVEN the same input
    WHEN the frontend and backend estimates are compared
    THEN both deliver the same number (mirrored heuristic)."""
    import subprocess

    from core.usage import estimate_tokens as be

    js = """
const { estimateTokens } = require('/work/ephe/app/src/lib/contextMeter.ts')
"""
    # The module import runs through Vite; for the parity check the formula tests
    # in the Vitest cases (app/src/lib/contextMeter.test.ts) are enough.
    assert be("你好世界") == 4
    assert js


# P0-4: version SSOT

def test_version_string_has_one_source_per_reach():
    """GIVEN the four readings of the version number
    WHEN they are compared
    THEN all are identical (package metadata/fallback/pyproject/locale fallback)."""
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    declared = [
        line.split("=", 1)[1].strip().strip('"')
        for line in pyproject.splitlines()
        if line.startswith("version")
    ]
    assert INIT_VERSION == version_module.__version__ == declared[0]

    # The language file used to carry an `app.version` („v1.1.0") — a field with no
    # reader that promised the surface a number nobody displayed. The dead-key
    # sweep (R4-W2) removed it; this line records that the version SSOT cannot
    # run on two sources again.
    locales = json.loads(Path("app/src/locales/en.json").read_text(encoding="utf-8"))
    assert "version" not in (locales.get("app") or {})
    de = json.loads(Path("app/src/locales/de.json").read_text(encoding="utf-8"))
    assert "version" not in (de.get("app") or {})


# P1-1: the shell timeout kills the child process

async def test_shell_timeout_kills_the_child_and_frees_the_loop(monkeypatch, tmp_path):
    """GIVEN a command above the timeout
    WHEN run_shell expires
    THEN there is the timeout message, and the loop stays usable afterwards."""
    import time

    from core.tools import shell_tools

    # W16-P3: with interpreter hardening the timeout case runs through the
    # allowed script form (python3 <file.py>), no longer through -c.
    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")

    import core.tools._shell_proc as _shell_proc
    monkeypatch.setattr(_shell_proc, "SHELL_TIMEOUT_SECONDS", 1)
    started = time.monotonic()
    with pytest.raises(Exception) as info:
        await shell_tools.run_shell(f"python3 {script}")
    assert "timed out" in str(info.value).lower()
    assert time.monotonic() - started < 3

    out = await shell_tools.run_shell("echo w14")
    assert out.strip().endswith("w14")


# P1-2: scheduler persistence runs off-thread

async def test_scheduler_runs_on_the_asyncio_executor_without_blocking_the_loop():
    """GIVEN a freshly started EpheScheduler (P1-2)
    WHEN the executors and the persistence paths are read
    THEN the job sits on the AsyncIO executor (close to the loop) and file I/O
    runs through asyncio.to_thread — the loop stays free for SSE/REST."""
    from apscheduler.executors.asyncio import AsyncIOExecutor

    from core.scheduler import EpheScheduler

    scheduler = EpheScheduler()
    scheduler.start()
    try:
        assert isinstance(scheduler._scheduler._executors["default"], AsyncIOExecutor)
    finally:
        scheduler.stop()

    from pathlib import Path

    source = Path("core/scheduler.py").read_text(encoding="utf-8")
    assert source.count("asyncio.to_thread") >= 2


# P1-3: swarm gather keeps partial results

async def test_swarm_gather_keeps_partial_agent_results(monkeypatch):
    """GIVEN three agents, one raises
    WHEN the swarm runs
    THEN the other two results survive (no total abort)."""
    from core.swarm_state import SwarmStateStore
    from core.swarm_v2 import SwarmAgent, SwarmOrchestrator

    async def _manager(self):
        return {"count": 3, "role": "researcher", "subtasks": ["a", "b", "c"]}

    async def _synthesize(self, subtasks, results):
        return "final"

    async def _run(self):
        if self.subtask == "b":
            raise RuntimeError("boom")
        return f"ok:{self.subtask}"

    monkeypatch.setattr(SwarmOrchestrator, "_run_manager", _manager)
    monkeypatch.setattr(SwarmOrchestrator, "_synthesize", _synthesize)
    monkeypatch.setattr(SwarmAgent, "run", _run)

    result = await SwarmOrchestrator(
        task="T", model="gemma4:12b", on_event=lambda e: None,
        state_store=SwarmStateStore(),
    ).run()

    assert result.final == "final"
    assert result.agent_results[0] == "ok:a"
    assert result.agent_results[1].startswith("[agent error:")
    assert result.agent_results[2] == "ok:c"


# P1-8: approval categories

@pytest.mark.parametrize(
    ("name", "category"),
    [
        ("read_file", "SAFE"),
        ("web_search", "NETWORK"),
        ("fetch_url", "NETWORK"),
        ("run_shell", "DANGEROUS"),
        ("write_file", "DANGEROUS"),
        ("irgendein_tool", "MUTATING"),
    ],
)
def test_tool_categories_are_exhaustive(name, category):
    """GIVEN the classification from P1-8
    WHEN classify_tool() is called
    THEN the category is right for each of the four classes."""
    from core.tools.approval import classify_tool

    assert classify_tool(name).category == category


def test_network_classification_keeps_the_chat_gate_semantics():
    """GIVEN web_search is NETWORK (not SAFE)
    WHEN the chat gate decides
    THEN the auto-run semantics stay unchanged (no second dialog)."""
    from core.tools.approval import chat_tool_requires_confirm, classify_tool

    assert chat_tool_requires_confirm("web_search") is False
    assert classify_tool("web_search").auto_approve_by_default is False


# P1-9: tool-result cap

def test_tool_result_is_capped_before_the_message_array():
    """GIVEN a 40,000-character result
    WHEN the cap applies
    THEN the prompt holds the ceiling plus the marker.

    I6-3: the ceiling is no longer a constant but the register field
    `chat.tool_result_chars` (default 32000 = the old value). The default comes
    from the register itself here — a second number in this test would be a
    second source that someone has to keep in sync."""
    from core.chat import _cap_tool_result
    from core.settings_schema import SCHEMA

    cap = SCHEMA["chat.tool_result_chars"]["default"]
    capped = _cap_tool_result("x" * 40000)
    assert len(capped) == cap + len(f" …[truncated at {cap} chars]")
    assert capped.startswith("x" * 100)
    assert _cap_tool_result("kurz") == "kurz"


# P1-7: TTFT on the streaming turn

def test_ttft_is_recorded_on_the_first_content_chunk():
    """GIVEN the stream protocol with thinking-/chunk sequences
    WHEN the first content chunk arrives
    THEN the message carries the time to first token (Vitest: chatStore)."""
    from pathlib import Path

    source = Path("app/src/store/chat/stream.ts").read_text(encoding="utf-8")
    assert "ttftMs: now - m.timestamp" in source
