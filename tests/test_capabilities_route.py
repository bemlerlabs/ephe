"""The capability route states the sub-agent boundary the guard enforces."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.subagent import SUBAGENT_MAX_ITERATIONS, SUBAGENT_TOOL_WHITELIST


@pytest.fixture()
def client() -> TestClient:
    from server.main import create_app

    return TestClient(create_app())


def test_subagent_capability_is_the_guard_list(client: TestClient) -> None:
    body = client.get("/api/capabilities").json()
    subagent = body["subagent"]
    assert subagent["tools"] == SUBAGENT_TOOL_WHITELIST
    assert subagent["tool_count"] == len(SUBAGENT_TOOL_WHITELIST)
    assert subagent["max_iterations"] == SUBAGENT_MAX_ITERATIONS
    assert subagent["read_only"] is True


def test_the_main_agent_is_not_read_only(client: TestClient) -> None:
    body = client.get("/api/capabilities").json()
    assert body["main_agent"]["read_only"] is False


def test_the_mcp_sandbox_block_names_its_boundaries(client: TestClient) -> None:
    """G9: the strip states what the sandbox module enforces, not a wish list."""
    from core.mcp_sandbox import platform_boundary

    sandbox = client.get("/api/capabilities").json()["mcp_sandbox"]
    assert sandbox["platform"] == platform_boundary()
    assert sandbox["available"] is (platform_boundary() != "unavailable")
    assert sandbox["home_root"].endswith("/mcp/homes")
    # build_bwrap omits --unshare-net on purpose; only bubblewrap unshares the pid space
    assert sandbox["network_isolated"] is False
    assert sandbox["pid_isolated"] is (sandbox["platform"] == "bubblewrap")
