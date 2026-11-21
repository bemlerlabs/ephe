"""Costly routes stay rate-limited — even where no access token applies.

The desktop app does not set LAN_AUTH_TOKEN. That used to mean: limiter off. A local
process could then start an unlimited number of chat runs, and every one of them costs
provider time, power and money. The answer is not the token (loopback knows
no peer) but a separate, small boundary for the expensive paths.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

import server.middleware as mw
from server.middleware import RateLimitMiddleware


def _app(**limit):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, **limit)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.post("/api/chat/stream")
    def stream():
        return {"ok": True}

    @app.get("/api/system/metrics")
    def metrics():
        return {"ok": True}

    return app


def test_costly_route_is_limited_without_any_token(monkeypatch):
    monkeypatch.setattr(mw, "LAN_AUTH_TOKEN", None)
    client = TestClient(_app(costly_max_requests=3))

    assert [client.post("/api/chat/stream").status_code for _ in range(3)] == [200, 200, 200]
    assert client.post("/api/chat/stream").status_code == 429


def test_cheap_pollers_stay_free_when_there_is_no_token(monkeypatch):
    monkeypatch.setattr(mw, "LAN_AUTH_TOKEN", None)
    client = TestClient(_app(costly_max_requests=2))
    for _ in range(200):
        assert client.get("/api/health").status_code == 200
    assert client.get("/api/system/metrics").status_code == 200


def test_window_reopens_and_a_rejected_request_wastes_nothing(monkeypatch):
    """A rejected request must not consume the budget — otherwise an external
    429 loop would be a way to keep the app blocked for the user until the window
    happened to roll over."""
    monkeypatch.setattr(mw, "LAN_AUTH_TOKEN", None)
    clock = {"now": 1_000.0}
    monkeypatch.setattr(mw.time, "time", lambda: clock["now"])
    client = TestClient(_app(costly_max_requests=2, window=60))

    assert client.post("/api/chat/stream").status_code == 200
    assert client.post("/api/chat/stream").status_code == 200
    for _ in range(30):  # thirty attempts, all of them rejected
        assert client.post("/api/chat/stream").status_code == 429

    clock["now"] += 61
    assert client.post("/api/chat/stream").status_code == 200


def test_lan_mode_still_keeps_the_general_budget(monkeypatch):
    monkeypatch.setattr(mw, "LAN_AUTH_TOKEN", "token-fuer-den-test")
    client = TestClient(_app(max_requests=4, costly_max_requests=100))
    codes = [client.get("/api/health").status_code for _ in range(5)]
    assert codes[:4] == [200] * 4 and codes[4] == 200  # health is exempt
    streamed = [client.post("/api/chat/stream").status_code for _ in range(6)]
    assert 429 in streamed
