"""
Ephe — R33 / stress triage P2: honest token accounting.

The OpenAI-compatible surface used to return hardcoded zeros in the usage
block (server/openai.py) and the main server only answered /v1/* with the
SPA catch-all's bare 404. This suite pins the honest replacement:

  * provider-measured metrics (Ollama's final stream chunk, OpenAI usage
    frames) are passed through untouched with usage_estimated == False;
  * when nothing was measured, a documented character-based estimate is
    returned and openly flagged via usage_estimated == True plus the
    X-Usage-Estimated response header;
  * /v1/* on the main PWA server answers with a helpful 404 hint (the
    OpenAI-compatible engine runs via ``ephe serve``);
  * GET /api/metrics is an honest alias of GET /api/system/metrics.

Given / When / Then — strikt. Tests BEFORE implementation (WGT).
"""
from __future__ import annotations

import json
import sys

import pytest
from fastapi.testclient import TestClient

from core.usage import build_usage, estimate_tokens, serialize_prompt


@pytest.fixture(autouse=True)
def _no_bpe(monkeypatch):
    """W16: the 4.2 calibration expectations hold on the fallback path —
    so switch the BPE backend off hermetically (neutralise a real tiktoken in the env)."""
    monkeypatch.setitem(sys.modules, "tiktoken", None)
    from core import usage
    usage.reset_tokenizer_cache()
    yield
    usage.reset_tokenizer_cache()


# core/usage: single source of truth for the estimator

class TestEstimator:
    def test_empty_text_estimates_zero(self):
        """GIVEN empty text WHEN estimate_tokens THEN 0."""
        assert estimate_tokens("") == 0

    def test_estimate_uses_documented_chars_per_token_ratio(self):
        """GIVEN 420 chars WHEN estimate_tokens THEN ratio-consistent count."""
        # 4.2 chars/token documented constant → 420 chars ≈ 100 tokens
        assert estimate_tokens("x" * 420) == 100

    def test_serialize_prompt_covers_roles_and_content(self):
        """GIVEN messages WHEN serialize_prompt THEN content is included."""
        text = serialize_prompt([{"role": "user", "content": "hallo welt"}])
        assert "hallo welt" in text


class TestBuildUsage:
    def test_measured_metrics_pass_through_unflagged(self):
        """GIVEN measured prompt/completion counts WHEN build_usage THEN used, not estimated."""
        u = build_usage("some prompt", "some answer", prompt_tokens=91, completion_tokens=42)
        assert u == {
            "prompt_tokens": 91,
            "completion_tokens": 42,
            "total_tokens": 133,
            "usage_estimated": False,
        }

    def test_missing_metrics_are_estimated_and_flagged(self):
        """GIVEN no metrics WHEN build_usage THEN estimates + usage_estimated True."""
        u = build_usage("p" * 42, "a" * 84)
        assert u["usage_estimated"] is True
        assert u["prompt_tokens"] == estimate_tokens("p" * 42)
        assert u["completion_tokens"] == estimate_tokens("a" * 84)
        assert u["total_tokens"] == u["prompt_tokens"] + u["completion_tokens"]


# /v1/chat/completions usage block (OpenAI-compatible app)

CHUNKS = ["Hallo", " vom", " Schwarzwald"]
FULL = "".join(CHUNKS)
MESSAGES = [{"role": "user", "content": "Erzaehl mir was kurzes ueber den Wald"}]


class FakeClient:
    """Streams a fixed list of raw chunk dicts, like the provider adapters."""

    def __init__(self, chunks):
        self._chunks = chunks

    def chat(self, *a, **k):
        chunks = self._chunks

        async def _gen():
            for chunk in chunks:
                yield chunk

        return _gen()


def _content_chunks(extra=None):
    out = [{"message": {"content": c}} for c in CHUNKS]
    if extra:
        out.extend(extra)
    return out


@pytest.fixture
def measured_app(monkeypatch):
    """Provider reported native metrics in the final chunk (Ollama style)."""
    import server.openai as so

    chunks = _content_chunks([{"message": {"content": ""}, "prompt_eval_count": 91, "eval_count": 42, "done": True}])
    monkeypatch.setattr(so, "build_provider_client", lambda *a, **k: FakeClient(chunks))
    return so


@pytest.fixture
def unmeasured_app(monkeypatch):
    """Provider yields content only — no metrics anywhere in the stream."""
    import server.openai as so

    monkeypatch.setattr(so, "build_provider_client", lambda *a, **k: FakeClient(_content_chunks()))
    return so


class TestV1Usage:
    def test_non_stream_reports_measured_usage_unflagged(self, measured_app):
        """GIVEN measured provider metrics WHEN non-stream completion THEN real usage, not estimated."""
        with TestClient(measured_app.create_openai_app()) as client:
            resp = client.post("/v1/chat/completions", json={"model": "gemma4:12b", "messages": MESSAGES})
        assert resp.status_code == 200
        usage = resp.json()["usage"]
        assert usage["prompt_tokens"] == 91
        assert usage["completion_tokens"] == 42
        assert usage["total_tokens"] == 133
        assert usage["usage_estimated"] is False
        assert resp.headers.get("x-usage-estimated") == "false"

    def test_non_stream_estimates_and_flags_honestly(self, unmeasured_app):
        """GIVEN no provider metrics WHEN non-stream completion THEN estimate openly flagged."""
        with TestClient(unmeasured_app.create_openai_app()) as client:
            resp = client.post("/v1/chat/completions", json={"model": "gemma4:12b", "messages": MESSAGES})
        usage = resp.json()["usage"]
        assert usage["usage_estimated"] is True
        assert usage["completion_tokens"] == estimate_tokens(FULL)
        assert usage["completion_tokens"] > 0  # never the old hardcoded 0
        assert usage["prompt_tokens"] > 0
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
        assert resp.headers.get("x-usage-estimated") == "true"

    def test_stream_emits_usage_frame_only_when_requested(self, unmeasured_app):
        """GIVEN stream_options.include_usage WHEN SSE THEN final usage frame before [DONE]."""
        with TestClient(unmeasured_app.create_openai_app()) as client:
            resp = client.post(
                "/v1/chat/completions",
                json={
                    "model": "gemma4:12b",
                    "messages": MESSAGES,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                },
            )
        frames = [line.removeprefix("data:").strip() for line in resp.text.splitlines() if line.startswith("data:")]
        assert frames[-1] == "[DONE]"
        usage_frame = json.loads(frames[-2])
        assert usage_frame["usage"]["usage_estimated"] is True
        assert usage_frame["usage"]["completion_tokens"] == estimate_tokens(FULL)

    def test_stream_without_include_usage_keeps_old_shape(self, unmeasured_app):
        """GIVEN plain stream WHEN SSE THEN no extra frames (backward compatible)."""
        with TestClient(unmeasured_app.create_openai_app()) as client:
            resp = client.post(
                "/v1/chat/completions",
                json={"model": "gemma4:12b", "messages": MESSAGES, "stream": True},
            )
        frames = [line.removeprefix("data:").strip() for line in resp.text.splitlines() if line.startswith("data:")]
        assert frames[-1] == "[DONE]"
        assert all("usage" not in json.loads(f) for f in frames[:-1])


# Main server: honest /v1/* hint + metrics alias

@pytest.fixture
def main_client(tmp_path):
    import os

    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")
    from server.routes.memory import _get_memory

    _get_memory.cache_clear()
    from server.main import create_app

    return TestClient(create_app())


class TestMainServerHonestSurface:
    def test_v1_post_answers_helpful_404(self, main_client):
        """GIVEN the main PWA server WHEN POST /v1/chat/completions THEN 404 with a real hint."""
        resp = main_client.post("/v1/chat/completions", json={"messages": MESSAGES})
        assert resp.status_code == 404
        assert "ephe serve" in resp.text

    def test_v1_get_answers_helpful_404(self, main_client):
        """GIVEN the main PWA server WHEN GET /v1/models THEN 404 with a real hint."""
        resp = main_client.get("/v1/models")
        assert resp.status_code == 404
        assert "ephe serve" in resp.text

    def test_metrics_alias_matches_canonical_route(self, main_client):
        """GIVEN metrics exposed at /api/system/metrics WHEN GET /api/metrics THEN same payload."""
        canonical = main_client.get("/api/system/metrics")
        alias = main_client.get("/api/metrics")
        assert canonical.status_code == 200
        assert alias.status_code == 200
        # cpu_percent/uptime/mem/disk samples are live readings — compare
        # everything but the inherently volatile readings; the key sets must
        # match exactly. (W19: mem_percent + disk_* are live readings too and
        # move between two GETs as soon as the suite run writes.)
        volatile = {
            "cpu_percent", "uptime_s", "mem_used_mb", "mem_percent",
            "disk_free_bytes", "disk_free_gb", "disk_percent",
        }
        a, c = alias.json(), canonical.json()
        assert set(a) == set(c)
        assert {k: v for k, v in a.items() if k not in volatile} == {
            k: v for k, v in c.items() if k not in volatile
        }
