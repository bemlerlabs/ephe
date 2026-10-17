"""
◑ Ephe – r72 (B-wave B2/B3): environment route — opt-in scan for the UI.
tests/test_r72_environment_route.py

Pins:
1. POST /api/environment/scan returns tools[] (5 entries) + summary;
   missing tools are installed=False, never an error.
2. Opt-in contract: GET on the same route returns NO scan data —
   the scan reads the home directory and must never run automatically
   when the page loads. (Repo-wide the router class answers
   method-mismatch with 404 instead of 405 — what is pinned is the contract "no
   data via GET", not the concrete status.)
3. Secret contract end-to-end: no string in the response contains the
   secret value from the fixture (value equality over the JSON).
4. No network: the route call only performs filesystem reads (scan()
   is local; a pinned monkeypatched network-symbol ban would be unnecessary —
   instead a fail-soft pin: damaged configs → the installed flag stays,
   models empty).
5. summary counts installed tools and tools with models.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SECRET = "sk-SUPERSECRET-r72"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fixture home with one installed opencode (including the secret branch)."""
    h = tmp_path / "home"
    cfg = h / ".config" / "opencode"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "opencode.jsonc").write_text(
        "// user config\n"
        "{\n"
        '  "provider": { "anthropic": { "models": { "claude-x": {} } } },\n'
        '  "model": "anthropic/claude-x",\n'
        '  "apiKey": "' + SECRET + '"\n'
        "}\n",
        encoding="utf-8",
    )
    # The scan reads Path.home() — bend it onto the fixture home.
    monkeypatch.setattr(Path, "home", staticmethod(lambda: h))
    return h


class TestEnvironmentRoute:

    def test_post_scan_contract(self, home: Path):
        from fastapi.testclient import TestClient
        from server.main import create_app

        with TestClient(create_app()) as client:
            r = client.post("/api/environment/scan")
            assert r.status_code == 200, r.text
            body = r.json()
            assert isinstance(body["tools"], list) and len(body["tools"]) == 5
            by_tool = {t["tool"]: t for t in body["tools"]}
            assert by_tool["opencode"]["installed"] is True
            assert "anthropic/claude-x" in by_tool["opencode"]["models"]
            assert by_tool["codex"]["installed"] is False
            # summary
            assert body["summary"]["installed"] == 1
            assert body["summary"]["with_models"] == ["opencode"]

    def test_get_returns_no_scan_data(self, home: Path):
        from fastapi.testclient import TestClient
        from server.main import create_app

        with TestClient(create_app()) as client:
            r = client.get("/api/environment/scan")
            assert r.status_code in (404, 405)
            assert "tools" not in r.json()

    def test_secret_value_never_in_response(self, home: Path):
        from fastapi.testclient import TestClient
        from server.main import create_app

        with TestClient(create_app()) as client:
            raw = client.post("/api/environment/scan").text
            assert SECRET not in raw
            # Key names such as "apiKey" must not appear as a field either.
            data = json.loads(raw)
            def _walk(node: object) -> None:
                if isinstance(node, dict):
                    for k, v in node.items():
                        assert not any(
                            s in k.lower() for s in ("secret", "password", "apikey", "api_key", "token")
                        ), f"Secret-artiger Schlüssel in Antwort: {k}"
                        _walk(v)
                elif isinstance(node, list):
                    for item in node:
                        _walk(item)
            _walk(data)

    def test_fail_soft_on_broken_config(self, home: Path, monkeypatch: pytest.MonkeyPatch):
        (home / ".config" / "opencode" / "opencode.jsonc").write_text(
            "{ broken json !!", encoding="utf-8"
        )
        from fastapi.testclient import TestClient
        from server.main import create_app

        with TestClient(create_app()) as client:
            r = client.post("/api/environment/scan")
            assert r.status_code == 200
            body = r.json()
            oc = next(t for t in body["tools"] if t["tool"] == "opencode")
            assert oc["installed"] is True
            assert oc["models"] == []
