"""
Ephe — R36 DD-07: /api/context/budget honesty.

The deep-dive audit found the status bar showing "0 tok / 0%" after real
turns while the local "free" counter moved: the route counted
load_messages(sid) — which never sees the PWA mirror stored under the
`rest-<id>` namespace — and sized the percent against the legacy fixed
8192 window instead of the ACTIVE engine window (262k DGX).

RULE: tests written BEFORE the implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_bpe(monkeypatch):
    """W16: the 4.2 expectations hold on the fallback path — BPE backend off."""
    monkeypatch.setitem(sys.modules, "tiktoken", None)
    from core import usage
    usage.reset_tokenizer_cache()
    yield
    usage.reset_tokenizer_cache()


@pytest.fixture
def sessions_root(tmp_path, monkeypatch):
    """Redirect the whole multi-session store into a private tmp dir."""
    from core import multi_session as ms

    root = tmp_path / "sessions"
    monkeypatch.setattr(ms, "SESSIONS_DIR", root)
    monkeypatch.setattr(ms, "REGISTRY_FILE", root / "registry.json")
    monkeypatch.setattr(ms, "LEGACY_FILE", root / "default.json")
    return root


def _get(session_id: str):
    from server.main import app

    return TestClient(app).get("/api/context/budget", params={"session_id": session_id})


def _clean_env(monkeypatch):
    monkeypatch.delenv("EPHE_CONTEXT_WINDOW", raising=False)


def test_counts_the_rest_mirror_when_native_session_absent(sessions_root, monkeypatch):
    """GIVEN a PWA session persisted only under rest-<id>
    WHEN the budget route counts it
    THEN the mirrored turns are reflected, not zero."""
    _clean_env(monkeypatch)
    from core import multi_session as ms

    ms.save_messages("rest-pwa-1", [
        {"role": "user", "content": "a" * 420},
        {"role": "assistant", "content": "b" * 4200},
    ])

    r = _get("pwa-1")

    assert r.status_code == 200
    b = r.json()
    assert b["message_count"] == 2
    assert b["char_count"] == 4620
    assert b["estimated_tokens"] == int(4620 / 4.2)
    assert b["estimated_tokens"] > 0  # DD-07: never "0 tok" after real turns


def test_native_session_still_wins_over_mirror(sessions_root, monkeypatch):
    """GIVEN a native registry session AND a mirror exist
    WHEN counting
    THEN the native history is authoritative."""
    _clean_env(monkeypatch)
    from core import multi_session as ms

    ms.save_messages("dual-1", [{"role": "user", "content": "x" * 42}])
    ms.save_messages("rest-dual-1", [{"role": "user", "content": "y" * 4200}])

    b = _get("dual-1").json()

    assert b["message_count"] == 1
    assert b["char_count"] == 42


def test_env_window_override_wins(sessions_root, monkeypatch):
    """GIVEN EPHE_CONTEXT_WINDOW is set
    WHEN the route computes the window
    THEN the override beats engine probe and the legacy constant."""
    monkeypatch.setenv("EPHE_CONTEXT_WINDOW", "262144")
    from core import multi_session as ms

    ms.save_messages("rest-w1", [{"role": "user", "content": "z" * 420}])

    b = _get("w1").json()

    assert b["window_tokens"] == 262144
    assert b["percent"] == round(int(420 / 4.2) / 262144 * 100, 2)


def test_active_engine_window_beats_legacy_default(sessions_root, monkeypatch):
    """GIVEN the provider probe cached an engine window (262k DGX)
    WHEN no env override exists
    THEN the budget sizes against the REAL engine window, not 8192."""
    _clean_env(monkeypatch)
    from core import multi_session as ms

    ms.save_messages("rest-w2", [{"role": "user", "content": "q" * 42000}])  # ~10k tok

    import server.routes.context as ctx

    monkeypatch.setattr(ctx, "_engine_context_window", lambda: 262144, raising=False)

    b = _get("w2").json()

    assert b["window_tokens"] == 262144
    assert b["percent"] < 5  # 10k of 262k — with the old 8192 this read >100%


def test_known_model_fills_the_window_from_the_tier_table(sessions_root, monkeypatch):
    """GIVEN no cached probe and no override, but a model the user chose and put into
    the FAST tier
    WHEN the route resolves the window
    THEN the tier table carries it (P0-1: 16384), not the legacy constant."""
    _clean_env(monkeypatch)
    from core import multi_session as ms
    import core.model_config as m
    from core.model_config import ModelTier

    # Both sides of the lookup are the user's now: the tag he runs (engine env) and
    # the tier that names it (EPHE_FAST_MODEL) — nothing ships either (2026-10-11).
    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "local_ollama")
    monkeypatch.setenv("EPHE_MODEL", "gemma4:12b")
    monkeypatch.setattr(m, "TIER_MAP", {
        ModelTier.FAST: m.ModelConfig(name="gemma4:12b", tier=ModelTier.FAST),
    })

    ms.save_messages("rest-w3", [{"role": "user", "content": "m" * 420}])

    import server.routes.context as ctx

    monkeypatch.setattr(ctx, "_engine_context_window", lambda: None, raising=False)

    b = _get("w3").json()

    assert b["window_source"] == "tier"
    assert b["window_tokens"] == 16384


def test_unknown_model_falls_back_to_the_legacy_constant(sessions_root, monkeypatch):
    """GIVEN no probe, no override and an unknown model id
    WHEN the route resolves the window
    THEN it keeps the documented 8192 fallback (offline-first)."""
    _clean_env(monkeypatch)
    from core import multi_session as ms
    from core.model_provider import ModelProviderConfig

    import core.model_provider as mp
    import server.routes.context as ctx

    monkeypatch.setattr(ctx, "_engine_context_window", lambda: None, raising=False)
    monkeypatch.setattr(
        mp,
        "_ACTIVE_OVERRIDE",
        ModelProviderConfig(
            provider="local_ollama",
            model="irgendein-modell",
            base_url="http://localhost:11434",
            label="Unknown",
            offline_capable=True,
            requires_internet=False,
        ),
    )
    ms.save_messages("rest-w3b", [{"role": "user", "content": "m" * 420}])

    b = _get("w3b").json()

    assert b["window_source"] == "legacy"
    assert b["window_tokens"] == 8192


def test_compaction_flag_uses_counted_history(sessions_root, monkeypatch):
    """GIVEN a mirrored session longer than the compaction threshold
    WHEN counting via the mirror
    THEN compaction_active reflects the mirror length (was always False with
    the un-prefixed load)."""
    _clean_env(monkeypatch)
    from core import multi_session as ms
    from core.conversation_compactor import DEFAULT_MAX_MESSAGES

    ms.save_messages("rest-long-1", [
        {"role": "user", "content": "t"} for _ in range(DEFAULT_MAX_MESSAGES + 2)
    ])

    b = _get("long-1").json()

    assert b["message_count"] == DEFAULT_MAX_MESSAGES + 2
    assert b["compaction_active"] is True


# R8: what the engine really reports
# Measured on the active engine (2026-10-08): /v1/models answered
# {"id","object","owned_by"} — no window field at all. The probe then
# knows nothing, and the surface must not print 8.192 as the machine's
# window. So: every field name servers use, and nothing else.

def test_fenster_aus_modell_kennt_die_namen_der_Server():
    from server.routes.model_provider import fenster_aus_modell

    assert fenster_aus_modell({"id": "m", "max_model_len": 262144}) == 262144
    assert fenster_aus_modell({"context_length": 131072}) == 131072
    assert fenster_aus_modell({"max_context_length": 32768}) == 32768
    # No field, nonsense, null: the probe stays silent, it does not guess.
    assert fenster_aus_modell({"id": "m", "object": "model"}) is None
    assert fenster_aus_modell({"max_model_len": 0}) is None
    assert fenster_aus_modell({"max_model_len": "262144"}) is None
    assert fenster_aus_modell(None) is None
