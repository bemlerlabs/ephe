"""A 405 names every method the path answers, not just the first route it found.

Issue #200. `GET /api/chat` answered 405 saying the path answers `GET, HEAD` while
`POST /api/chat` was the route — the SPA mount at `/` matched the refused request before
the API router could answer. That half is fixed by `SPAMount` (`server/spa.py`), and this
file keeps it pinned with the frontend build mounted.

What survived was the general form of the same defect: a path whose methods are declared
by *two* routes (`GET /api/settings` and `POST /api/settings`, `GET /api/settings/image`
and `PUT /api/settings/image`, …). Starlette hands a refused method to the **first**
partial match and that route's `Allow` set travels into the envelope, so
`OPTIONS /api/settings` said "it answers GET" while it answers POST too — a client never
learnt the method it needed. The fix unions the methods of every route that matches the
path, from the route table, so one path gives one answer.

The expectation in `TestEveryMultiMethodPath` is derived from the app's own route table,
not written per route: every path that declares more than one method must name all of
them back.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.main import create_app


def _make_dist(tmp_path: Path) -> Path:
    """A minimal real dist tree, so the SPA mount (`/`) is in the stack as in production."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!DOCTYPE html>\n<html lang=\"en\"><head><title>Ephe</title></head>"
        "<body>Test PWA</body></html>\n",
        encoding="utf-8",
    )
    return dist


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_FRONTEND_DIR", str(_make_dist(tmp_path)))
    with TestClient(create_app()) as c:
        yield c


def _declared_methods(app) -> dict[str, set[str]]:
    """path -> the union of methods every route declares for it.

    Included routers keep their routes behind `_IncludedRouter`, so the prefix has to be
    joined here as well; the caller skips a path that carries a parameter.
    """
    declared: dict[str, set[str]] = {}

    def walk(routes, prefix: str) -> None:
        for route in routes:
            context = getattr(route, "include_context", None)
            inner = getattr(route, "original_router", None)
            if context is not None and inner is not None:
                walk(inner.routes, prefix + (context.prefix or ""))
                continue
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if path and methods:
                declared.setdefault(prefix + path, set()).update(m.upper() for m in methods)

    walk(app.router.routes, "")
    return {
        path: methods
        for path, methods in declared.items()
        if path.startswith("/api/") and "{" not in path and len(methods) > 1
    }


class TestTheReportedPath:
    """`/api/chat` takes POST; a refused method has to say so."""

    def test_get_names_post(self, client):
        """GIVEN POST is the only method of /api/chat WHEN GET is refused
        THEN 405 and `Allow` names POST."""
        response = client.get("/api/chat")

        assert response.status_code == 405, response.text
        assert set(response.headers["allow"].split(", ")) == {"POST"}, response.headers
        assert "answers POST" in response.json()["error"]["message"]

    def test_options_names_post(self, client):
        """GIVEN a cross-origin client asks OPTIONS WHEN it is refused
        THEN 405 and `Allow` names POST — the method it may retry with."""
        response = client.options("/api/chat")

        assert response.status_code == 405, response.text
        assert set(response.headers["allow"].split(", ")) == {"POST"}, response.headers

    def test_delete_names_post(self, client):
        """GIVEN DELETE from the app's origin WHEN it is refused
        THEN 405 and `Allow` names POST."""
        response = client.request(
            "DELETE", "/api/chat", headers={"Origin": "tauri://localhost"}
        )

        assert response.status_code == 405, response.text
        assert set(response.headers["allow"].split(", ")) == {"POST"}, response.headers


class TestTheSecondRouteOfOnePath:
    """The method declared by the *second* route of a path is named too."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/settings",
            "/api/settings/image",
            "/api/settings/voice",
            "/api/settings/security",
            "/api/settings/persona",
            "/api/settings/mcp",
        ],
    )
    def test_options_names_the_post_or_put_twin(self, client, path):
        """GIVEN a path with GET and POST/PUT declared by two routes
        WHEN OPTIONS is refused THEN `Allow` names both."""
        response = client.options(path)

        assert response.status_code == 405, response.text
        allowed = set(response.headers["allow"].split(", "))
        assert allowed == _declared_methods(client.app)[path], (path, allowed)
        assert {"GET"} < allowed, (path, allowed)


class TestEveryMultiMethodPath:
    """One rule, read off the route table — no route is patched by name."""

    def test_a_refused_method_names_every_declared_method(self, client):
        """GIVEN any /api path that declares more than one method
        WHEN a method it does not declare is requested
        THEN `Allow` is exactly the set the route table declares."""
        wrong: list[tuple[str, str, set[str]]] = []
        for path, methods in _declared_methods(client.app).items():
            refused = "OPTIONS" if "OPTIONS" not in methods else "TRACE"
            response = client.request(refused, path)
            if response.status_code != 405:
                wrong.append((path, response.status_code, methods))
                continue
            allowed = set(response.headers.get("allow", "").split(", "))
            if allowed != methods:
                wrong.append((path, response.headers.get("allow"), methods))

        assert not wrong, wrong

    def test_the_sentence_names_the_same_set_as_the_header(self, client):
        """GIVEN the refusal on a two-route path WHEN its sentence is read
        THEN it names the same methods the header carries."""
        response = client.options("/api/settings")

        allowed = response.headers["allow"]
        assert f"answers {allowed}" in response.json()["error"]["message"]

    def test_a_get_only_route_still_names_only_get(self, client):
        """GIVEN a path with one declared method WHEN POST is refused
        THEN the union invents no verb — the earlier pins stay valid."""
        response = client.post("/api/health")

        assert response.status_code == 405, response.text
        assert set(response.headers["allow"].split(", ")) == {"GET"}, response.headers
