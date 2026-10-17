"""API: /api/model/providers/probe — a REMOTE engine without a URL is not probed.

Root cause (on site, wave R8 onboarding): the PWA offers "Ollama remote
(z. B. DGX / LAN)". When the endpoint was empty, the probe internally fell back to  # language-gate: ignore (quoted German provider-preset label as it ships, app/src/locales/de.json:860)
http://127.0.0.1:11434 and reported "erreichbar · 6 Modelle" — the models of the  # language-gate: ignore (quoted probe report line as it ships, server/routes/model_provider.py:60)
LOCAL Ollama. The user therefore took an unprobed, empty remote entry for a
verified DGX/LAN engine and persisted custom_ollama without api_url. Exactly the
silent default AGENTS.md forbids.

GIVEN a custom_ollama probe without base_url (Ollama runs on this machine)
WHEN  POST /api/model/providers/probe
THEN  reachable=False, no models, no request to 127.0.0.1:11434 —
      so the surface can honestly say "kein Endpunkt angegeben".  # language-gate: ignore (quoted surface wording named by the THEN clause, kept verbatim)

GIVEN a local_ollama probe without base_url
WHEN  POST /api/model/providers/probe
THEN  the local default is still probed (this engine CLASS IS this machine — there
      the loopback endpoint is the answer, not a guess).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OLLAMA_MODELS = {"models": [{"name": "gemma4:12b"}, {"name": "nomic-embed-text"}]}


@pytest.fixture(autouse=True)
def _isolate_config_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Isolated engine.json — the tests NEVER write into ~/.ephe."""
    isolated = tmp_path / "config"
    isolated.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(isolated))
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", isolated)
    yield
    import core.model_provider as mp

    mp._ACTIVE_OVERRIDE = None


@pytest.fixture()
def client() -> TestClient:
    from server.routes import model_provider, settings

    app = FastAPI()
    app.include_router(model_provider.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    return TestClient(app)


@pytest.fixture()
def recorder():
    """httpx request recorder: logs every URL requested, answers like Ollama."""
    import httpx

    seen: list[str] = []

    async def fake_get(self, url, *a, **kw):
        seen.append(str(url))
        return httpx.Response(
            200, json=OLLAMA_MODELS, request=httpx.Request("GET", str(url))
        )

    with patch("httpx.AsyncClient.get", new=fake_get):
        yield seen


def test_probe_remote_ollama_without_url_does_not_test_this_machine(
    client: TestClient, recorder: list[str]
):
    """GIVEN remote Ollama without an endpoint, Ollama running locally
    WHEN  POST /api/model/providers/probe {provider: custom_ollama}
    THEN  not reachable, no models — and NO request went to the local
      machine (otherwise the report would be a false statement)."""
    resp = client.post(
        "/api/model/providers/probe", json={"provider": "custom_ollama"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is False
    assert body["models"] == []
    assert body["state"] == "unreachable"
    assert "127.0.0.1:11434" not in "".join(recorder)
    assert recorder == []


def test_probe_remote_ollama_detail_names_the_missing_endpoint(
    client: TestClient, recorder: list[str]
):
    """The report is actionable: it says that the endpoint is missing."""
    body = client.post(
        "/api/model/providers/probe", json={"provider": "custom_ollama"}
    ).json()
    assert "url" in body["detail"].lower() or "endpunkt" in body["detail"].lower()


def test_probe_remote_ollama_with_url_still_probes_that_url(
    client: TestClient, recorder: list[str]
):
    """GIVEN a stated remote URL
    WHEN  probe(custom_ollama, http://10.0.0.9:11434)
    THEN  exactly that endpoint is probed (the old behaviour stays)."""
    resp = client.post(
        "/api/model/providers/probe",
        json={"provider": "custom_ollama", "base_url": "http://10.0.0.9:11434"},
    )
    body = resp.json()
    assert body["reachable"] is True
    assert body["models"] == ["gemma4:12b", "nomic-embed-text"]
    assert any("10.0.0.9:11434" in u for u in recorder)


def test_probe_local_ollama_without_url_keeps_the_local_default(
    client: TestClient, recorder: list[str]
):
    """GIVEN local Ollama without a URL entry
    WHEN  probe(local_ollama)
    THEN  the local default is probed — the class IS this machine."""
    body = client.post(
        "/api/model/providers/probe", json={"provider": "local_ollama"}
    ).json()
    assert body["reachable"] is True
    assert any("127.0.0.1:11434" in u for u in recorder)
