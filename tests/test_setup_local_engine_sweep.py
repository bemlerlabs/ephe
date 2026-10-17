"""I4-1: a locally running inference server is found without the user typing it.

The onboarding used to know only what was stored somewhere (engine.json, env,
endpoint history) plus Ollama. Anyone who had vLLM, SGLang, TensorRT-LLM, LM
Studio or another OpenAI-compatible server running on the machine still saw
'nothing found' in setup. New: a pure loopback scan of the known standard
ports. No network scan, no persist, no pull.

The product names appear only as 'typical for' on the candidate — what is
recognised is an OpenAI-compatible endpoint, not the software behind it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.routes import settings as settings_route

SWEEP_URLS = {
    "http://127.0.0.1:8000/v1",
    "http://127.0.0.1:30000/v1",
    "http://127.0.0.1:1234/v1",
}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """No engine.json, no engine env — the state of a fresh Mac."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path)
    for name in (
        "EPHE_MODEL_PROVIDER", "EPHE_MODEL", "EPHE_OPENAI_COMPAT_BASE_URL",
        "EPHE_OPENAI_COMPAT_API_KEY", "EPHE_OPENAI_COMPAT_MODEL",
        "EPHE_LOCAL_OLLAMA_BASE_URL", "EPHE_CUSTOM_OLLAMA_BASE_URL",
        "OLLAMA_HOST", "ANTHROPIC_BASE_URL", "OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    yield tmp_path


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(settings_route.router, prefix="/api")
    return TestClient(app)


# Candidate list

def test_loopback_ports_sind_kandidaten() -> None:
    urls = {c["url"] for c in settings_route._setup_candidates()}
    assert SWEEP_URLS <= urls, sorted(SWEEP_URLS - urls)


def test_sweep_kandidaten_traegen_provider_und_hinweis() -> None:
    sweep = [
        c for c in settings_route._setup_candidates()
        if (c.get("url") or "").startswith("http://127.0.0.1:")
    ]
    assert sweep, "kein Loopback-Kandidat"
    table = {code for _port, code, hint in settings_route._ENGINE_PORTS if hint}
    for c in sweep:
        assert c["provider"] == "openai_compatible", c
        # The hint names a likelihood. The code is the half the pane maps to a locale
        # entry, so a sentence without its code would be untranslated copy.
        assert bool(c.get("hint")) == bool(c.get("hint_code")), c
        assert not c.get("hint_code") or c["hint_code"] in table, c


def test_kein_blinder_netzscan(tmp_path: Path) -> None:
    """A stored LAN URL creates no further foreign hosts in the list."""
    (tmp_path / "engine.json").write_text(
        json.dumps({"provider": "openai_compatible", "model": "m",
                    "api_url": "http://192.168.1.20:8000/v1"}),
        encoding="utf-8",
    )
    hosts = {(c.get("url") or "").split("//")[-1].split(":")[0].split("/")[0]
             for c in settings_route._setup_candidates()}
    hosts.discard("")  # the Ollama candidate without URL (implicit default)
    assert "192.168.1.20" in hosts
    assert hosts <= {"192.168.1.20", "127.0.0.1", "localhost"}, hosts


def test_dedup_gegen_persistierte_url(tmp_path: Path) -> None:
    """The loopback port that already is the active engine must not appear twice."""
    (tmp_path / "engine.json").write_text(
        json.dumps({"provider": "openai_compatible", "model": "m",
                    "api_url": "http://127.0.0.1:8000/v1"}),
        encoding="utf-8",
    )
    urls = [c["url"] for c in settings_route._setup_candidates()]
    assert urls.count("http://127.0.0.1:8000/v1") == 1


# The scan itself

@pytest.mark.asyncio
async def test_detect_findet_antwortenden_port(monkeypatch, client: TestClient) -> None:
    async def fake_probe(url, api_key):  # noqa: ANN001 - test double
        if url.rstrip("/") == "http://127.0.0.1:30000/v1":
            return True, ["demo-model"], "", "ok"
        return False, [], "abgelehnt", "unreachable"

    monkeypatch.setattr(
        "server.routes.model_provider._probe_openai_compatible", fake_probe, raising=True
    )
    body = client.get("/api/setup/detect").json()
    hits = {d["url"]: d for d in body["detected"]}
    assert hits["http://127.0.0.1:30000/v1"]["reachable"] is True
    assert hits["http://127.0.0.1:30000/v1"]["models"] == ["demo-model"]
    assert hits["http://127.0.0.1:8000/v1"]["reachable"] is False
    assert body["first_reachable"] >= 0


@pytest.mark.asyncio
async def test_sweep_kandidaten_verschmelzen_nicht(monkeypatch, client: TestClient) -> None:
    """I4-1 regression: only :8000 answers, but every candidate has to keep its
    own URL — otherwise the sibling fallback had thrown all seven onto :8000 and
    given each one the wrong product hint."""
    async def fake_probe(url, api_key):  # noqa: ANN001
        if url == "http://127.0.0.1:8000/v1":
            return True, ["demo-7b"], "", "ok"
        return False, [], "abgelehnt", "unreachable"

    monkeypatch.setattr(
        "server.routes.model_provider._probe_openai_compatible", fake_probe, raising=True
    )
    body = client.get("/api/setup/detect").json()
    sweep = [d for d in body["detected"] if (d.get("url") or "").startswith("http://127.0.0.1:")]
    urls = {d["url"] for d in sweep}
    assert len(sweep) == len(urls), [d["url"] for d in sweep]
    hit = next(d for d in sweep if d["reachable"])
    assert hit["url"] == "http://127.0.0.1:8000/v1"
    assert hit["hint_code"] == "vllm", hit
    assert "vLLM" in (hit.get("hint") or ""), hit
    assert sum(1 for d in sweep if d["reachable"]) == 1


@pytest.mark.asyncio
async def test_scan_schreibt_nichts_nach_persist(monkeypatch, client: TestClient, tmp_path) -> None:
    """A finding is not a decision: engine.json stays untouched."""
    async def fake_probe(url, api_key):  # noqa: ANN001
        return True, ["demo-model"], "", "ok"

    monkeypatch.setattr(
        "server.routes.model_provider._probe_openai_compatible", fake_probe, raising=True
    )
    client.get("/api/setup/detect")
    assert not (tmp_path / "engine.json").exists()


@pytest.mark.asyncio
async def test_falscher_port_an_bekanntem_host_wird_gefunden(
    monkeypatch, client: TestClient, tmp_path
) -> None:
    """The owner's case: the DGX host is known, but qwen runs on :8888.

    A stored URL with the wrong port is not a dead end — the same host is
    probed across the usual engine ports, and the answer names the URL that
    really serves.
    """
    (tmp_path / "engine.json").write_text(
        json.dumps({"provider": "openai_compatible", "model": "qwen",
                    "api_url": "http://192.168.1.50:8000/v1"}),
        encoding="utf-8",
    )

    async def fake_probe(url, api_key):  # noqa: ANN001
        if url == "http://192.168.1.50:8888/v1":
            return True, ["qwen3.8-flash"], "", "ok"
        return False, [], "abgelehnt", "unreachable"

    monkeypatch.setattr(
        "server.routes.model_provider._probe_openai_compatible", fake_probe, raising=True
    )
    body = client.get("/api/setup/detect").json()
    hit = next(
        d for d in body["detected"]
        if d["provider"] == "openai_compatible" and d["reachable"] and d["url"]
    )
    assert hit["url"] == "http://192.168.1.50:8888/v1", hit
    assert "qwen3.8-flash" in hit["models"], hit
    # The hit found via the detour carries the port hint too.
    assert hit["hint_code"] == "vllm_dgx", hit
    assert "vLLM" in (hit.get("hint") or ""), hit


def test_eine_portliste_fuer_sweep_und_geschwister() -> None:
    """One source: what the loopback scan knows, the sibling fallback has to know
    too — otherwise two lists drift apart (8888 was only in one of them)."""
    sweep = {port for port, _code, _hint in settings_route._ENGINE_PORTS}
    assert sweep == {int(p) for p in settings_route._VLLM_STD_PORTS}
    assert 8888 in sweep and 30000 in sweep and 1234 in sweep


# The known machine host (DGX Spark)

def test_ephe_dgx_host_ist_kandidat(monkeypatch) -> None:
    """EPHE_DGX_HOST is known to the router and to the health check — setup knew
    nothing about it. Whoever set the Spark address once must not have to type it
    again."""
    monkeypatch.setenv("EPHE_DGX_HOST", "192.168.1.50:8888")
    urls = {c["url"] for c in settings_route._setup_candidates()}
    assert "http://192.168.1.50:8888/v1" in urls, sorted(u for u in urls if u)


def test_ephe_dgx_host_ohne_port(monkeypatch) -> None:
    monkeypatch.setenv("EPHE_DGX_HOST", "dgx-spark.local")
    urls = {c["url"] for c in settings_route._setup_candidates()}
    assert "http://dgx-spark.local/v1" in urls, sorted(u for u in urls if u)


def test_ephe_dgx_host_volle_url_nimmt_keine_zweite(monkeypatch) -> None:
    """An already complete URL is not built again with a scheme."""
    monkeypatch.setenv("EPHE_DGX_HOST", "https://dgx.example:8888/v1")
    cand = [c for c in settings_route._setup_candidates() if "dgx.example" in (c.get("url") or "")]
    assert len(cand) == 1, cand
    assert cand[0]["url"] == "https://dgx.example:8888/v1"


@pytest.mark.asyncio
async def test_dgx_host_ohne_port_findet_qwen_auf_8888(
    monkeypatch, client: TestClient
) -> None:
    """The owner's case: only the host is known, qwen runs on 8888."""
    monkeypatch.setenv("EPHE_DGX_HOST", "192.168.1.50")

    async def fake_probe(url, api_key):  # noqa: ANN001
        if url == "http://192.168.1.50:8888/v1":
            return True, ["qwen3.8-flash"], "", "ok"
        return False, [], "abgelehnt", "unreachable"

    monkeypatch.setattr(
        "server.routes.model_provider._probe_openai_compatible", fake_probe, raising=True
    )
    body = client.get("/api/setup/detect").json()
    hit = next(
        d for d in body["detected"]
        if d["reachable"] and (d.get("url") or "").startswith("http://192.168.1.50")
    )
    assert hit["url"] == "http://192.168.1.50:8888/v1", hit
    assert hit["models"] == ["qwen3.8-flash"], hit


def test_status_liefert_kandidaten_ohne_netzwerk(client: TestClient) -> None:
    """GET /setup/status runs on every app start — it must not scan."""
    body = client.get("/api/setup/status").json()
    assert "candidates" in body
    assert body["configured"] is False
