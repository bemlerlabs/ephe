"""
The 405 that names its methods without an `Allow` header to read them from.

`server/main.py` `_allowed_verbs` prefers the header the router built. A 405 raised
*inside a route* (FastAPI's `HTTPException` carries no headers by default) arrives
without one, and the fallback reads the request's own route table instead: the
included router's prefix plus the route's path, matched against the request path,
and the verbs the matched route declares. Two answers are pinned here — the route
the table carries (the `Allow` header names its verbs) and a path the table does
not carry (no header, and the sentence says the answer is unknown). The header
path, where the router already built `Allow`, is `tests/test_method_refusal.py`.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request


def _app_with_a_headerless_refusal(tmp_path, monkeypatch) -> FastAPI:
    """The PWA app plus one GET route and one header-less 405 raised for the same path.

    The GET half is included through `include_router`, the way `create_app` includes
    every route family, so the fallback meets the `_IncludedRouter` shape it was
    written for and has to join the prefix and the route path itself.
    """
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    from server.main import create_app

    app = create_app()
    inner = APIRouter()

    @inner.get("/fallback-probe")
    def _read() -> dict:
        return {"read": True}

    app.include_router(inner, prefix="/api")

    @app.put("/api/fallback-probe")
    def _put() -> dict:
        # The quirk the fallback exists for: no headers, so nothing but the route
        # table can say which verbs this path answers.
        raise HTTPException(status_code=405, detail="refused")

    return app


def test_a_405_without_an_allow_header_names_the_verbs_the_route_table_carries(
    tmp_path, monkeypatch
):
    """GIVEN a route that refuses a method with a header-less 405
    WHEN the path is requested with that method
    THEN the answer is the method refusal, its `Allow` header names the verbs the
    route table declares for that path, and the sentence names them too."""
    client = TestClient(_app_with_a_headerless_refusal(tmp_path, monkeypatch))

    response = client.put("/api/fallback-probe")

    assert response.status_code == 405, response.text
    error = response.json()["error"]
    assert error["code"] == "method_not_allowed"
    assert response.headers["allow"] == "GET", response.headers
    assert "answers GET" in error["message"], error["message"]


def test_a_405_on_a_path_the_route_table_does_not_carry_says_the_answer_is_unknown(
    tmp_path, monkeypatch
):
    """GIVEN a 405 whose path no route declares
    WHEN the handler answers it
    THEN no `Allow` header is invented and the sentence says the table named nothing."""
    app = _app_with_a_headerless_refusal(tmp_path, monkeypatch)
    handler = app.exception_handlers[StarletteHTTPException]
    scope = {
        "type": "http",
        "method": "PUT",
        "path": "/api/fallback-probe-nowhere",
        "headers": [],
        "query_string": b"",
        "router": app.router,
    }

    response = asyncio.run(handler(Request(scope), HTTPException(status_code=405)))

    assert response.status_code == 405
    assert "allow" not in {name.lower() for name in response.headers}
    error = json.loads(response.body)["error"]
    assert error["code"] == "method_not_allowed"
    assert "named no methods" in error["message"], error["message"]
