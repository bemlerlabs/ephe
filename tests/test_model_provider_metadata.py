"""
◑ Ephe – Wave 1 (S1): the model list carries what the endpoint said, and nothing more.
tests/test_model_provider_metadata.py

Every field of `model_details` is read out of the entry the engine wrote. Unknown is
None — never 0, never inferred from the model's name. These run against payload fixtures
(an OpenRouter-style rich entry, a vLLM-style minimal one, malformed pricing) rather than
a live engine, and one case proves the probe's credential source still travels with the
new fields.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = "http://engine.test:8000/v1"


def answer_for(entries: list[dict], api_key: str | None = None) -> dict:
    """POST /model/providers/probe with the engine answering exactly these entries."""
    import httpx
    from unittest.mock import patch

    from server.routes import model_provider as mp

    async def fake_get(self, url, *a, **kw):
        return httpx.Response(200, json={"data": entries}, request=httpx.Request("GET", url))

    app = FastAPI()
    app.include_router(mp.router, prefix="/api")
    with patch("httpx.AsyncClient.get", new=fake_get):
        return TestClient(app).post(
            "/api/model/providers/probe",
            json={"provider": "openai_compatible", "base_url": BASE, "api_key": api_key},
        ).json()


RICH = {
    "id": "vendor/muse-4",
    "name": "Muse 4",
    "created": 1700000000,
    "description": "A capable model.",
    "context_length": 262144,
    "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
    "pricing": {"prompt": "0.0000005", "completion": "0.000002"},
    "top_provider": {"context_length": 262144},
    "supported_parameters": ["tools", "temperature", "max_tokens"],
}

FREE = {
    "id": "vendor/muse-4:free",
    "name": "Muse 4 (free)",
    "context_length": 131072,
    "pricing": {"prompt": "0", "completion": "0"},
    "supported_parameters": ["temperature"],
}

VLLM_MINIMAL = {"id": "qwen38-27b", "object": "model", "owned_by": "vllm", "max_model_len": 262144}


class TestMetadataMapping:

    def test_rich_entry_maps_every_field(self):
        body = answer_for([RICH])
        assert body["models"] == ["vendor/muse-4"]
        row = body["model_details"][0]
        assert row["id"] == "vendor/muse-4"
        assert row["name"] == "Muse 4"
        assert row["context_window"] == 262144
        assert row["price_in_per_m"] == pytest.approx(0.5)
        assert row["price_out_per_m"] == pytest.approx(2.0)
        assert row["is_free"] is False
        assert row["supports_tools"] is True
        assert row["supports_vision"] is True

    def test_free_suffix_is_only_free_when_the_price_says_so(self):
        """The name is never read: ':free' with a price on it is a priced model."""
        free = answer_for([FREE])["model_details"][0]
        assert free["is_free"] is True
        assert free["supports_tools"] is False
        assert free["supports_vision"] is None

        priced = dict(FREE, pricing={"prompt": "0.0000002", "completion": "0"})
        row = answer_for([priced])["model_details"][0]
        assert row["id"].endswith(":free")
        assert row["is_free"] is False

    def test_vllm_minimal_entry_knows_only_its_window(self):
        row = answer_for([VLLM_MINIMAL])["model_details"][0]
        assert row["context_window"] == 262144
        assert row["name"] is None
        assert row["price_in_per_m"] is None
        assert row["price_out_per_m"] is None
        assert row["is_free"] is None
        assert row["supports_tools"] is None
        assert row["supports_vision"] is None

    def test_malformed_pricing_is_unknown_rather_than_zero(self):
        for broken in ("", "free", None, "abc", "-1"):
            entry = dict(VLLM_MINIMAL, pricing={"prompt": broken, "completion": "0"})
            row = answer_for([entry])["model_details"][0]
            assert row["price_in_per_m"] is None, broken
            assert row["is_free"] is None, broken

    def test_partial_pricing_table_stays_unknown(self):
        entry = dict(VLLM_MINIMAL, pricing={"prompt": "0"})
        row = answer_for([entry])["model_details"][0]
        assert row["price_in_per_m"] == 0
        assert row["price_out_per_m"] is None
        assert row["is_free"] is None

    def test_a_capable_looking_name_supports_nothing_until_the_engine_says_so(self):
        entry = {"id": "great-tool-caller-vision", "name": "Tool & Vision model"}
        row = answer_for([entry])["model_details"][0]
        assert row["supports_tools"] is None
        assert row["supports_vision"] is None
        assert row["is_free"] is None
        assert row["context_window"] is None

    def test_flat_input_modalities_are_read_where_the_engine_writes_them(self):
        """DeepSeek names the field at the entry root, not under architecture."""
        entry = {"id": "deepseek-v4-pro", "context_window": 1048576,
                 "input_modalities": ["text", "image"]}
        row = answer_for([entry])["model_details"][0]
        assert row["context_window"] == 1048576
        assert row["supports_vision"] is True

        text_only = dict(entry, input_modalities=["text"])
        assert answer_for([text_only])["model_details"][0]["supports_vision"] is False


class TestShapeAndCompatibility:

    def test_models_list_is_unchanged_and_details_align_with_it(self):
        body = answer_for([RICH, FREE, VLLM_MINIMAL])
        assert body["models"] == ["vendor/muse-4", "vendor/muse-4:free", "qwen38-27b"]
        assert [d["id"] for d in body["model_details"]] == body["models"]

    def test_a_key_offered_by_the_user_still_reports_itself(self):
        """S4's visibility is not dropped by S1's extra fields."""
        body = answer_for([VLLM_MINIMAL], api_key="given-key-1")
        assert body["key_source"] == "given"
        assert body["model_details"][0]["context_window"] == 262144

    def test_ollama_names_arrive_with_unknown_metadata(self):
        import httpx
        from unittest.mock import patch

        from server.routes import model_provider as mp

        async def fake_get(self, url, *a, **kw):
            return httpx.Response(
                200, json={"models": [{"name": "gemma4:12b"}, {"name": "qwen3:4b"}]},
                request=httpx.Request("GET", url),
            )

        app = FastAPI()
        app.include_router(mp.router, prefix="/api")
        with patch("httpx.AsyncClient.get", new=fake_get):
            body = TestClient(app).post(
                "/api/model/providers/probe",
                json={"provider": "local_ollama", "base_url": "http://127.0.0.1:11434"},
            ).json()
        assert body["models"] == ["gemma4:12b", "qwen3:4b"]
        assert [d["id"] for d in body["model_details"]] == body["models"]
        assert all(d["context_window"] is None for d in body["model_details"])
        assert all(d["is_free"] is None for d in body["model_details"])
        assert "key_source" not in body

    def test_a_broken_body_answers_reachable_with_no_models(self):
        """A 200 whose body is not the list shape answers "nothing known" and stays off the crash path."""
        import httpx
        from unittest.mock import patch

        from server.routes import model_provider as mp

        async def fake_get(self, url, *a, **kw):
            return httpx.Response(200, json={"data": None}, request=httpx.Request("GET", url))

        app = FastAPI()
        app.include_router(mp.router, prefix="/api")
        with patch("httpx.AsyncClient.get", new=fake_get):
            body = TestClient(app).post(
                "/api/model/providers/probe",
                json={"provider": "openai_compatible", "base_url": BASE},
            ).json()
        assert body["state"] == "ok"
        assert body["models"] == []
        assert body["model_details"] == []


class TestProvidersListCarriesTheSameKeys:

    def _body(self, entries, ollama_options=None, provider="openai_compatible", model="m"):
        import httpx
        from unittest.mock import patch

        from core.model_provider import ModelProviderConfig
        from server.routes import model_provider as mp

        async def fake_get(self, url, *a, **kw):
            return httpx.Response(200, json={"data": entries}, request=httpx.Request("GET", url))

        async def no_ollama():
            return ollama_options or []

        active = ModelProviderConfig(
            provider=provider,
            model=model,
            base_url=BASE if provider == "openai_compatible" else "",
            label="test",
            offline_capable=provider != "openai_compatible",
            requires_internet=provider == "openai_compatible",
        )
        mp._CONTEXT_WINDOW_CACHE.clear()
        app = FastAPI()
        app.include_router(mp.router, prefix="/api")
        with (
            patch("httpx.AsyncClient.get", new=fake_get),
            patch.object(mp, "list_local_model_options", no_ollama),
            patch.object(mp, "get_active_provider", lambda: active),
        ):
            return TestClient(app).get("/api/model/providers").json()

    def test_openai_compatible_options_gain_the_nullable_keys(self):
        body = self._body([RICH])
        option = body["local_model_options"][0]
        assert option["name"] == "vendor/muse-4"
        assert option["label"] == "Muse 4"
        assert option["context_window"] == 262144
        assert option["is_free"] is False
        assert option["supports_vision"] is True

    def test_ollama_options_carry_the_keys_as_unknown(self):
        body = self._body(
            [],
            ollama_options=[{"name": "gemma4:12b", "label": "gemma4:12b"}],
            provider="local_ollama",
            model="gemma4:12b",
        )
        option = body["local_model_options"][0]
        assert option["label"] == "gemma4:12b"
        assert option["context_window"] is None
        assert option["supports_tools"] is None


def test_the_metadata_module_reads_nothing_off_a_name():
    """Guards the rule itself: this file contains no name parsing at all.

    The prose names the suffix it refuses, so the check looks for the calls a suffix
    detector would need.
    """
    source = (ROOT / "core" / "model_metadata.py").read_text(encoding="utf-8")
    assert "endswith(" not in source
    assert "startswith(" not in source
    assert ".lower().find(" not in source


def test_metadata_records_are_built_from_one_key_list():
    from core.model_metadata import METADATA_KEYS, bare_metadata

    assert set(METADATA_KEYS) == set(bare_metadata())
    assert all(value is None for value in bare_metadata().values())
