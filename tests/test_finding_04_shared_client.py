"""
tests/test_finding_04_shared_client.py

Finding 4: analyze_image() created a new AsyncClient per call.
Fix: Shared module-level client via _get_shared_client().

Given-When-Then Tests:
  1. GIVEN _get_shared_client() called twice WHEN comparing instances THEN same object
  2. GIVEN shared client is None WHEN first call THEN creates new client
  3. GIVEN shared client already exists WHEN second call THEN reuses it (no new client)
"""
from unittest.mock import patch, MagicMock

import pytest

from core.tools.base import (
    _get_shared_client,
    _shared_client as _base_shared_client,
)


def _reset_state():
    """Reset the shared client state in base module."""
    import core.tools.base as tb
    tb._shared_client = None


# Test 1: GIVEN two calls WHEN getting client THEN same instance

def test_given_two_calls_when_get_shared_client_then_same_instance():
    """GIVEN _get_shared_client() called twice WHEN comparing THEN same object returned."""
    _reset_state()

    client1 = _get_shared_client()
    client2 = _get_shared_client()

    assert client1 is client2, "Expected same client instance, got different objects"

    _reset_state()


# Test 2: GIVEN client is None WHEN first call THEN creates new

def test_given_client_none_when_first_call_then_creates_new():
    """GIVEN _shared_client is None WHEN _get_shared_client() THEN creates AsyncClient."""
    _reset_state()

    client = _get_shared_client()

    assert client is not None

    import core.tools.base as tb
    assert tb._shared_client is client

    _reset_state()


# Test 3: GIVEN client exists WHEN second call THEN no new creation

def test_given_client_exists_when_second_call_then_no_new_creation():
    """GIVEN _shared_client already set WHEN _get_shared_client() THEN AsyncClient() not called again."""
    _reset_state()

    # base.py imports `ollama` LAZY inside _get_shared_client()
    # (there is no module-global `core.tools.base.ollama`) — so the
    # REAL module `ollama.AsyncClient` has to be patched, not the
    # non-existent attribute path `core.tools.base.ollama.AsyncClient`.
    with patch("ollama.AsyncClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        _get_shared_client()
        assert MockClient.call_count == 1

        _get_shared_client()
        assert MockClient.call_count == 1, "AsyncClient() should not be called twice"

    _reset_state()
