"""The research surface: evidence as data, and one explicit run.

The provider and the pages are loopback fixtures; the key travels in a header and
no test opens a host. The evidence list is the ledger's own answer, so a run made
through the tool and one made through the route appear in the same list.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import core.web_intake.crawl as crawl_module
from core.tools.web_research import run_research
from core.web_intake import policy
from core.web_intake.crawl import PageCache, clear_robots_cache
from core.web_intake.evidence import EvidenceStore
from core.web_intake.ledger import default_ledger
from core.web_intake.verify import Verification, annotate_unverified, verify_answer
from core.web_intake.workspace_scope import WorkspaceHit
from server.main import create_app
from tests.web_intake_fixture import FixtureServer

ALLOW_ROBOTS = "User-agent: *\nAllow: /\n"
XHR = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("EPHE_FETCH_ALLOW_PRIVATE", "1")
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("EPHE_SEARCH_CONFIG", str(tmp_path / "missing-web-search.json"))
    monkeypatch.setattr(crawl_module, "PAGE_CACHE", PageCache(tmp_path / "pages"))
    limiter_class = policy.RateLimiter

    def no_delay(**kwargs) -> policy.RateLimiter:
        kwargs.pop("delay", None)
        return limiter_class(delay=0.0, **kwargs)

    monkeypatch.setattr(policy, "RateLimiter", no_delay)
    default_ledger().clear()
    clear_robots_cache()
    yield
    clear_robots_cache()
    default_ledger().clear()


@pytest.fixture()
def client():
    return TestClient(create_app())


def _provider(monkeypatch, server: FixtureServer, rows: list[dict]) -> None:
    server.json("/search", {"results": rows})
    monkeypatch.setenv("EPHE_SEARCH_API_URL", server.url("/search"))
    monkeypatch.setenv("EPHE_SEARCH_API_KEY", "test-key")


def _moon_page(server: FixtureServer) -> str:
    server.route("/robots.txt", ALLOW_ROBOTS, content_type="text/plain")
    return server.route(
        "/moon",
        "<title>Moon drift</title><p>The moon drifts away from Earth at about "
        "3.8 cm per year, a rate measured by laser ranging.</p>",
    )


def test_the_evidence_list_is_empty_before_a_run(client):
    answer = client.get("/api/research/evidence").json()
    assert answer == {
        "ok": True, "runs": [], "sources": [], "workspace": [], "total": 0,
    }


def test_a_tool_run_lands_in_the_list_with_its_fields(client, monkeypatch):
    with FixtureServer() as server:
        page = _moon_page(server)
        _provider(monkeypatch, server, [{"title": "Moon drift", "url": page}])
        asyncio.run(run_research("How fast does the moon drift away?", max_pages=1))

    answer = client.get("/api/research/evidence").json()
    assert answer["ok"] is True
    assert answer["total"] == 1
    source = answer["sources"][0]
    assert set(source) == {
        "source_id", "url", "title", "fetched_at", "sha256", "excerpt", "query", "run_id",
    }
    assert source["url"] == page
    assert source["title"] == "Moon drift"
    assert source["query"] == "How fast does the moon drift away?"
    assert len(source["sha256"]) == 64
    assert "3.8 cm" in source["excerpt"]
    assert answer["runs"][0]["run_id"] == source["run_id"]


def test_the_list_filters_by_query_and_run_id(client, monkeypatch):
    with FixtureServer() as server:
        moon = _moon_page(server)
        tides = server.route(
            "/tides", "<title>Tides</title><p>The tides follow the moon and the sun.</p>"
        )
        _provider(monkeypatch, server, [
            {"title": "Moon drift", "url": moon},
            {"title": "Tides", "url": tides},
        ])
        first = asyncio.run(run_research("moon drift", max_pages=2))
        second = asyncio.run(run_research("tide cycle", max_pages=2))

    assert first.run is not None and second.run is not None
    by_query = client.get("/api/research/evidence", params={"query": "tide"}).json()
    assert [run["query"] for run in by_query["runs"]] == ["tide cycle"]
    by_id = client.get(
        "/api/research/evidence", params={"run_id": first.run.run_id}
    ).json()
    assert by_id["runs"][0]["query"] == "moon drift"
    assert all(source["run_id"] == first.run.run_id for source in by_id["sources"])
    assert client.get(
        "/api/research/evidence", params={"limit": 1}
    ).json()["total"] == 1


def test_the_run_route_refuses_without_a_provider(client, monkeypatch):
    monkeypatch.delenv("EPHE_SEARCH_API_URL", raising=False)
    monkeypatch.delenv("EPHE_SEARCH_API_KEY", raising=False)
    answer = client.post(
        "/api/research/run", json={"query": "anything"}, headers=XHR
    ).json()
    assert answer["ok"] is False
    assert answer["status"] == "refused"
    assert answer["reason_code"] == "web_search_not_configured"
    assert "EPHE_SEARCH_API_URL" in answer["next"]
    assert answer["run"] is None
    assert answer["text"].startswith("[research refused]")


def test_the_run_route_needs_the_xhr_marker(client):
    refused = client.post("/api/research/run", json={"query": "anything"})
    assert refused.status_code == 403
    body = refused.text
    assert "X-Requested-With" in body
    assert "HTTPException" not in body and "Traceback" not in body


def test_the_run_route_answers_with_text_and_evidence(client, monkeypatch):
    with FixtureServer() as server:
        page = _moon_page(server)
        _provider(monkeypatch, server, [{"title": "Moon drift", "url": page}])
        answer = client.post(
            "/api/research/run",
            json={"query": "moon drift", "max_pages": 1},
            headers=XHR,
        ).json()

    assert answer["ok"] is True and answer["status"] == "ok"
    assert answer["text"].startswith("[web_research]")
    assert "Citation check:" in answer["text"]
    assert answer["run"]["query"] == "moon drift"
    assert answer["run"]["sources"] == 1
    assert answer["verification"]["checked"] >= 1
    assert answer["verification"]["verified"] >= 1
    assert answer["run"]["sources"] == len(
        client.get("/api/research/evidence").json()["sources"]
    )


def test_the_run_route_refuses_an_empty_query(client):
    answer = client.post("/api/research/run", json={"query": ""}, headers=XHR).json()
    assert answer["ok"] is False
    assert answer["reason_code"] == "web_query_empty"
    assert answer["next"]


def test_an_unknown_freshness_is_refused_by_code(client, monkeypatch):
    monkeypatch.setenv("EPHE_SEARCH_API_URL", "https://search.test/find")
    monkeypatch.setenv("EPHE_SEARCH_API_KEY", "test-key")
    answer = client.post(
        "/api/research/run", json={"query": "moon", "freshness": "hour"}, headers=XHR
    ).json()
    assert answer["ok"] is False
    assert answer["reason_code"] == "web_freshness_unknown"
    assert "day" in answer["next"]


def test_workspace_scope_mixes_file_lines_into_the_run(client, monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "moon.md").write_text(
        "# Drift\n\nThe moon drifts away from Earth at about 3.8 cm per year.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    with FixtureServer() as server:
        page = _moon_page(server)
        _provider(monkeypatch, server, [{"title": "Moon drift", "url": page}])
        answer = client.post(
            "/api/research/run",
            json={"query": "moon drifts away", "max_pages": 1, "workspace_scope": "src"},
            headers=XHR,
        ).json()

    assert answer["ok"] is True
    assert any(hit["reference"] == "src/moon.md:3" for hit in answer["run"]["workspace_hits"])
    assert "[src/moon.md:3]" in answer["text"]
    listed = client.get("/api/research/evidence", params={"query": "moon"}).json()
    assert any(hit["reference"] == "src/moon.md:3" for hit in listed["workspace"])
    assert listed["workspace"][0]["query"] == "moon drifts away"


def test_a_model_summary_is_marked_where_no_source_carries_it():
    store = EvidenceStore()
    source = store.add(
        url="https://example.org/moon",
        title="Moon drift",
        fetched_at="2026-11-12T00:00:00Z",
        content_type="text/html",
        extract="The moon drifts away from Earth at about 3.8 cm per year.",
    )
    workspace = {
        "src/drift.py:4": WorkspaceHit(
            path="src/drift.py", line=4, text="RATE_CM_PER_YEAR = 3.8"
        )
    }
    answer = (
        f"{source.extract} [{source.source_id}] "
        "The moon is made of cheese. "
        f"RATE_CM_PER_YEAR = 3.8 [src/drift.py:4]"
    )
    marked, report = annotate_unverified(answer, store, workspace)
    assert "[unverified]" in marked
    assert "cheese. [unverified]" in marked
    assert report.checked == 3
    assert report.verified == 2
    assert any("no source named" in issue for issue in report.issues)
    assert verify_answer(answer, store, workspace).verified == 2


async def _drive(monkeypatch, chat_impl) -> str:
    from server.routes import chat as chat_route

    monkeypatch.setattr(chat_route, "chat_with_tools", chat_impl)

    async def no_revision(**_kwargs):
        from core.react import ReflexionResult

        return ReflexionResult(needs_revision=False)

    monkeypatch.setattr(chat_route, "reflect", no_revision)
    request = chat_route.StreamRequest(message="moon drift", session_id="s-research")
    response = await chat_route.chat_stream(request)
    generator = response.body_iterator
    chunks: list[str] = []
    while True:
        try:
            chunks.append(await asyncio.wait_for(generator.__anext__(), 10.0))  # type: ignore[attr-defined]
        except StopAsyncIteration:
            break
    return "".join(chunks)


def _events(raw: str) -> list[dict]:
    return [
        json.loads(part[len("data: "):])
        for part in raw.split("\n\n")
        if part.strip().startswith("data: ")
    ]


@pytest.mark.asyncio
async def test_a_research_turn_marks_the_claims_its_sources_do_not_carry(monkeypatch):
    backed = "The moon drifts away from Earth at about 3.8 cm per year."
    citation: list[str] = []

    async def fake_turn(**kwargs):
        from core.web_intake.ledger import current_turn, note_run

        store = EvidenceStore()
        source = store.add(
            url="https://example.org/moon",
            title="Moon drift",
            fetched_at="2026-11-12T00:00:00Z",
            content_type="text/html",
            extract=backed,
        )
        citation.append(source.source_id)
        note_run(
            query="moon drift",
            turn_id=current_turn(),
            sources=list(store.sources()),
            store=store,
            verification=Verification(checked=2, verified=1),
        )
        kwargs["on_chunk"](f"{backed} [{source.source_id}] The moon is made of cheese.")
        return ""

    raw = await _drive(monkeypatch, fake_turn)
    frames = [event for event in _events(raw) if event.get("type") == "citation_check"]
    assert len(frames) == 1, [event.get("type") for event in _events(raw)]
    frame = frames[0]
    assert frame["checked"] == 2
    assert frame["verified"] == 1
    assert any("cheese" in claim for claim in frame["unverified"])
    assert all(citation)


@pytest.mark.asyncio
async def test_a_turn_without_a_research_run_adds_no_citation_frame(monkeypatch):
    async def plain_turn(**kwargs):
        kwargs["on_chunk"]("A plain answer without a research call.")
        return ""

    raw = await _drive(monkeypatch, plain_turn)
    assert not [event for event in _events(raw) if event.get("type") == "citation_check"]
