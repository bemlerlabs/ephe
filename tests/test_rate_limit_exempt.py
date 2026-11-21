"""Poller endpoints must not eat up the rate-limit budget of the expensive routes."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.middleware import RateLimitMiddleware, LAN_AUTH_TOKEN
import server.middleware as mw


def test_poller_endpoints_are_exempt_from_rate_limit():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, max_requests=5, window=60)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/chat/stream")
    def stream():
        return {"ok": True}

    mw.LAN_AUTH_TOKEN = "x"  # the general budget applies in LAN mode (cost routes always)
    try:
        c = TestClient(app)
        # 50 health polls: thanks to the exemption, never a 429
        for _ in range(50):
            assert c.get("/api/health").status_code == 200
        # expensive route: after max_requests=5 a 429 arrives
        codes = [c.get("/api/chat/stream").status_code for _ in range(6)]
        assert 429 in codes
    finally:
        mw.LAN_AUTH_TOKEN = LAN_AUTH_TOKEN
