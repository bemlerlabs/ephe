"""The engine key is write-only: the settings read reports presence, never the value.

The image block already answers this way (`has_api_key` / `api_key_hint`). The engine block
returned the stored secret in every `GET /api/settings`, so the value sat in proxy logs,
browser devtools panels and screen shares on whatever network the server was bound to — and
the settings screen did not need it, because the engine health answer already carries
`engine_key_configured`.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from server.routes import settings as settings_routes


@pytest.fixture
def active(monkeypatch):
    monkeypatch.setattr(
        settings_routes,
        "get_active_provider",
        lambda: SimpleNamespace(
            provider="openai_compatible",
            base_url="http://127.0.0.1:8000/v1",
            model="a-served-model",
        ),
    )


def test_the_block_reports_presence_and_the_last_four(active, monkeypatch):
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_API_KEY", "sk-live-abcdefgh")
    block = settings_routes._active_provider_dict()
    assert "api_key" not in block
    assert block["api_key_configured"] is True
    assert block["api_key_hint"] == "efgh"


def test_an_absent_key_is_reported_as_absent(active, monkeypatch):
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)
    block = settings_routes._active_provider_dict()
    assert block["api_key_configured"] is False
    assert block["api_key_hint"] == ""


def test_a_short_key_leaves_the_hint_empty(active, monkeypatch):
    """Three characters are not a hint, they are most of the key."""
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_API_KEY", "abc")
    block = settings_routes._active_provider_dict()
    assert block["api_key_configured"] is True
    assert block["api_key_hint"] == ""
