"""The reason code of a refusal has to survive the tool return.

Step 1 of the wire: `core.reason.Reason` is a `str` that carries `code` and `params` beside its
sentence. Two places dropped it — the registry flattened every result with `str(result)`, and
`fetch_url` formatted the refusal into an f-string. Both are producer sides: the code is taken from the
object the guard built, never looked up from the finished text afterwards.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from core.reason import Reason
from core.tools import fetch_tools
from core.tools.fetch_tools import FetchRefused
from core.tools.registry import execute_tool


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "user_profile.json"))
    monkeypatch.setenv("EPHE_CORRECTIONS_PATH", str(tmp_path / "corrections.md"))
    monkeypatch.setenv("EPHE_FEEDBACK_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))
    from server.main import create_app

    return TestClient(create_app())


async def _refused(url: str):
    raise FetchRefused(Reason(
        "169.254.169.254 is the environment's metadata endpoint — blocked always.",
        "metadata_host",
        {"host": "169.254.169.254"},
    ))


async def _plain(url: str):
    raise FetchRefused("Redirect without a target.")


def _through_registry(monkeypatch, raiser, url: str) -> object:
    monkeypatch.setattr(fetch_tools, "_http_get", raiser)
    fetch_tools._FETCH_CACHE.pop(url, None)
    return asyncio.run(execute_tool("fetch_url", {"url": url, "prompt": ""}))


def test_the_guard_code_reaches_the_caller_through_the_registry(monkeypatch):
    """G: a fetch_url call the scope guard refuses with a known code
       W: the real execute_tool path, registry included
       T: the result still reads as its sentence and carries code and params"""
    url = "http://169.254.169.254/latest/meta-data/"
    result = _through_registry(monkeypatch, _refused, url)

    assert isinstance(result, str)
    assert "[fetch refused]" in result
    assert "metadata endpoint" in result
    assert getattr(result, "code", None) == "metadata_host"
    assert dict(getattr(result, "params", {}) or {}) == {"host": "169.254.169.254"}


def test_an_uncoded_refusal_stays_the_sentence_it_always_was(monkeypatch):
    """The redirect paths hand over a plain string: no code, and nothing invented."""
    url = "http://redirect-without-location.example/"
    result = _through_registry(monkeypatch, _plain, url)

    assert isinstance(result, str)
    assert "Redirect without a target." in result
    assert getattr(result, "code", None) is None


def test_a_coded_exception_arrives_with_its_code_through_the_error_sink(monkeypatch):
    """`core.reason.coded` leaves the exception class alone; the sink has to do the rest."""
    from core.reason import coded
    from core.tools import registry

    async def probe(query: str) -> str:
        raise coded("probe_refused", ValueError("the probe refuses"), query=query)

    monkeypatch.setitem(registry.TOOL_MAP, "probe", probe)
    result = asyncio.run(execute_tool("probe", {"query": "x"}))

    assert isinstance(result, Reason)
    assert str(result) == "[tool-error 'probe': the probe refuses]"
    assert result.code == "probe_refused"
    assert dict(result.params) == {"query": "x"}


def test_an_uncoded_exception_stays_the_plain_line_it_was(monkeypatch):
    from core.tools import registry

    async def probe(query: str) -> str:
        raise ValueError("the probe refuses")

    monkeypatch.setitem(registry.TOOL_MAP, "probe", probe)
    result = asyncio.run(execute_tool("probe", {"query": "x"}))

    assert isinstance(result, str)
    assert not isinstance(result, Reason)
    assert str(result) == "[tool-error 'probe': the probe refuses]"


def _locale_bundles() -> tuple[dict, dict]:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app" / "src" / "locales"
    return tuple(
        json.loads((root / f"{lng}.json").read_text(encoding="utf-8"))["reader"]
        for lng in ("de", "en")
    )


class TestToolDoneFrame:
    """The frame is additive: `result` keeps the text every client reads today."""

    def _stream(self, client, tool: str, result: object) -> list[dict]:
        import json
        from unittest.mock import patch

        async def fake_chat_with_tools(**kwargs):
            kwargs["on_tool_start"](tool, {"url": "http://x"})
            kwargs["on_tool_done"](tool, result)
            return "done"

        with patch("server.routes.chat.chat_with_tools", new=fake_chat_with_tools), \
             patch("server.routes.chat._ensure_engine_ready"):
            with client.stream(
                "POST", "/api/chat/stream",
                json={"model": "gemma4:12b", "history": [], "message": "hole die Seite",
                      "session_id": "refusal-channel-frame"},
            ) as response:
                assert response.status_code == 200
                text = "".join(response.iter_text())
        return [
            json.loads(line[5:].strip())
            for line in text.splitlines()
            if line.strip().startswith("data:")
        ]

    def test_a_coded_refusal_sets_reason_code_and_keeps_its_text(self, client):
        """G: a coded guard refusal reaches the stream callbacks
           W: POST /api/chat/stream on the real route
           T: reason_code is set, the code exists in de.json and en.json,
              and result still carries the sentence"""
        de, en = _locale_bundles()
        refusal = Reason(
            "[fetch refused] 169.254.169.254 is the environment's metadata endpoint — blocked always.",
            "metadata_host",
            {"host": "169.254.169.254"},
        )
        frames = self._stream(client, "fetch_url", refusal)
        done = [f for f in frames if f.get("type") == "tool_done"]
        assert done, f"no tool_done frame in {[f.get('type') for f in frames]}"
        assert done[0]["reason_code"] == "metadata_host"
        assert done[0]["reason_params"] == {"host": "169.254.169.254"}
        assert "metadata endpoint" in done[0]["result"]
        assert "metadata_host" in de and "metadata_host" in en

    def test_an_uncoded_result_adds_no_fields_the_card_has_to_guard(self, client):
        frames = self._stream(client, "read_file", "just a file body")
        done = [f for f in frames if f.get("type") == "tool_done"]
        assert done and done[0]["result"] == "just a file body"
        assert "reason_code" not in done[0] and "reason_params" not in done[0]

    def test_a_code_the_locales_do_not_carry_still_ships_its_sentence(self, client):
        """The card falls back to `result`, so an unmapped code cannot silence a pane."""
        de, en = _locale_bundles()
        refusal = Reason("[fetch refused] some brand new wording.", "not_in_any_bundle", {})
        assert "not_in_any_bundle" not in de and "not_in_any_bundle" not in en
        done = [f for f in self._stream(client, "fetch_url", refusal) if f.get("type") == "tool_done"]
        assert done[0]["reason_code"] == "not_in_any_bundle"
        assert "some brand new wording." in done[0]["result"]
