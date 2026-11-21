"""A loopback HTTP server for the web intake tests.

Every route is scripted in the test, the port comes from the kernel, and the
handler records the headers each request carried. No test reaches a real host:
the crawl is pointed at ``127.0.0.1`` and ``EPHE_FETCH_ALLOW_PRIVATE=1`` is the
only reason that address is reachable at all.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class FixtureServer:
    def __init__(self) -> None:
        self.routes: dict[str, dict] = {}
        self.requests: list[tuple[str, dict]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.fixture = self
        self._thread = threading.Thread(
            target=lambda: self._server.serve_forever(poll_interval=0.01), daemon=True
        )

    @property
    def base(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def url(self, path: str) -> str:
        return f"{self.base}{path}"

    def route(
        self,
        path: str,
        body: str = "",
        *,
        status: int = 200,
        content_type: str = "text/html; charset=utf-8",
        etag: str = "",
        headers: dict[str, str] | None = None,
    ) -> str:
        self.routes[path] = {
            "status": status,
            "body": body,
            "content_type": content_type,
            "etag": etag,
            "headers": headers or {},
        }
        return self.url(path)

    def json(self, path: str, payload: object, *, status: int = 200) -> str:
        return self.route(
            path,
            json.dumps(payload),
            status=status,
            content_type="application/json",
        )

    def requests_for(self, path: str) -> list[dict]:
        return [headers for seen, headers in self.requests if urlsplit(seen).path == path]

    def __enter__(self) -> "FixtureServer":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 — http.server's spelling
        fixture: FixtureServer = self.server.fixture
        fixture.requests.append(
            (self.path, {key.lower(): value for key, value in self.headers.items()})
        )
        route = fixture.routes.get(urlsplit(self.path).path)
        if route is None:
            self._send(404, "text/plain", b"not found")
            return
        etag = route.get("etag") or ""
        if etag and self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = route["body"]
        if isinstance(body, str):
            body = body.encode("utf-8")
        self._send(route["status"], route["content_type"], body, etag, route["headers"])

    def _send(
        self,
        status: int,
        content_type: str,
        body: bytes,
        etag: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        if content_type:
            self.send_header("Content-Type", content_type)
        if etag:
            self.send_header("ETag", etag)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        return
