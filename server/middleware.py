"""
server/middleware.py – security middleware for LAN mode.
Generates a random auth token and protects every API endpoint.
"""
from __future__ import annotations

import ipaddress
import os
import hmac
import re
import secrets
import threading
import time
from collections import defaultdict

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from core.observability import REQUEST_ID_HEADER, ErrorCode, error_payload

LAN_AUTH_TOKEN: str | None = None


def init_auth(lan_mode: bool = False) -> str | None:
    global LAN_AUTH_TOKEN
    if lan_mode:
        LAN_AUTH_TOKEN = secrets.token_urlsafe(32)
        print(f"  🔑 LAN Auth Token generated — embedded in QR code")
        return LAN_AUTH_TOKEN
    LAN_AUTH_TOKEN = None
    return None


async def verify_auth(request: Request) -> None:
    if LAN_AUTH_TOKEN is None:
        return
    token = request.headers.get("X-Auth-Token")
    if token != LAN_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized — invalid or missing X-Auth-Token")


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

_TAURI_ORIGINS = frozenset({"tauri://localhost", "http://tauri.localhost"})


def _host_without_port(host: str) -> str:
    """Host header without the port, IPv6-aware: '[::1]:8765' -> '::1', 'localhost:8765' -> 'localhost'."""
    if host.startswith("["):  # IPv6 bracket notation
        return host.split("]", 1)[0].lstrip("[")
    return host.rsplit(":", 1)[0] if ":" in host else host


def _app_origins() -> set[str]:
    """Origins this server serves, plus the operator's named dev origins.

    The same list the CORS layer grants. `EPHE_PORT` is the port the product
    started on; an unset value keeps the desktop default.
    """
    port = os.environ.get("EPHE_PORT") or "8765"
    origins = {
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        f"http://[::1]:{port}",
        *_TAURI_ORIGINS,
    }
    origins.update(
        origin.strip()
        for origin in os.environ.get("EPHE_DEV_ORIGINS", "").split(",")
        if origin.strip()
    )
    return origins


def origin_allowed(origin: str | None) -> bool:
    """True for an absent origin (non-browser client) or one this app serves.

    A browser sends Origin on every WebSocket handshake and on every mutation;
    a page from another site cannot make its origin look like ours. This is the
    control the XHR marker only pretended to be: after DNS rebinding the page is
    same-origin, so it can set any header it likes.
    """
    if not origin:
        return True
    return origin.strip().lower() in {value.lower() for value in _app_origins()}


def host_allowed(host: str | None) -> bool:
    """Loopback authorities only, with the test client's synthetic host as a test seam."""
    raw = (host or "").strip()
    name = (
        raw.lower()
        if raw.count(":") > 1 and not raw.startswith("[")
        else _host_without_port(raw).lower()
    )
    if not name:
        return False
    if name in _LOOPBACK_HOSTS:
        return True
    if name == "testserver" and os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        # A DNS name can begin with "127."; only a loopback address is trusted.
        return False


def _is_loopback_client(request: Request) -> bool:
    """The machine itself (the desktop app) is trusted — only external LAN clients need the token.
    The QR link carries the authorization for the phone; localhost needs none.

    Root-cause fix: an outgoing tunnel (ssh -R 80:localhost:PORT via localhost.run)
    delivers EVERY public request with client.host=127.0.0.1 — trusting client.host
    alone would then be worthless. That is why the Host header is checked too: a real
    desktop browser addresses localhost/127.0.0.1; a tunneled request carries the public
    hostname (*.lhr.life), because the tunnel would not route it otherwise.
    Provider-independent and header-injection-safe (an attacker cannot send a local Host
    header through the tunnel — lhr discards it)."""
    if (request.client.host if request.client else "") not in _LOOPBACK_HOSTS:
        return False
    host = _host_without_port(request.headers.get("host", "")).lower()
    return host in _LOOPBACK_HOSTS or host.startswith("127.")


def ws_client_authorized(websocket) -> bool:
    """Auth gate for WebSocket handshakes (P1-5).

    BaseHTTPMiddleware (AuthMiddleware) does NOT cover the 'websocket' scope —
    a WS upgrade bypasses the HTTP middleware completely. Without this explicit
    gate, every WS route would be reachable unauthenticated in LAN mode
    (that also held for the proxy_ws HMR tunnel).

    The handshake carries an Origin; it is checked before the loopback shortcut.
    The shortcut without a token is desktop-only. A rebinding page presents a
    foreign Host and Origin even though the TCP peer is loopback, and it cannot
    guess the LAN token; both paths fail closed.
    """
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host", "")

    if LAN_AUTH_TOKEN is None:
        return host_allowed(host) and origin_allowed(origin)

    client_host = websocket.client.host if getattr(websocket, "client", None) else ""
    loopback = client_host in _LOOPBACK_HOSTS and host_allowed(host)
    if loopback and origin_allowed(origin):
        return True
    offered = websocket.query_params.get("token") or ""
    return hmac.compare_digest(offered, LAN_AUTH_TOKEN)


class LocalRequestGuardMiddleware(BaseHTTPMiddleware):
    """Rejects a request that reached the loopback port under a foreign Host.

    A DNS-rebinding page is same-origin with the address it typed, so its Host
    and Origin name the attacker's domain while the TCP peer stays 127.0.0.1.
    The peer address alone is therefore not a boundary. In LAN mode a
    non-loopback client is authenticated by the token; that path is left to
    AuthMiddleware.
    """

    async def dispatch(self, request: Request, call_next):
        client_host = request.client.host if request.client else ""
        loopback = client_host in _LOOPBACK_HOSTS
        host = request.headers.get("host", "")
        if LAN_AUTH_TOKEN is None:
            if not host_allowed(host):
                return self._refusal(request, "untrusted_host", host)
        elif not loopback or not host_allowed(host):
            # A tunnel forwards a public request with a loopback TCP peer but a
            # public Host; that client authenticates with the token in
            # AuthMiddleware. A genuine loopback client keeps the host check.
            return await call_next(request)
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin is not None
            and not origin_allowed(origin)
        ):
            return self._refusal(request, "untrusted_origin", host)
        return await call_next(request)

    def _refusal(self, request: Request, reason: str, host: str) -> JSONResponse:
        origin = request.headers.get("origin")
        self._audit(request, reason, host, origin)
        rid = getattr(request.state, "rid", None)
        body = error_payload(ErrorCode.AUTH, "request origin is not this application", rid)
        body["error"]["detail"] = {"code": reason}
        return JSONResponse(
            body,
            status_code=403,
            headers={REQUEST_ID_HEADER: rid or ""},
        )

    @staticmethod
    def _audit(request: Request, reason: str, host: str, origin: str | None) -> None:
        try:
            from core.audit_log import audit_event

            audit_event(
                "security",
                tool="request",
                decision=reason,
                status="denied",
                detail=(
                    f"path={request.url.path} host={host or 'none'} "
                    f"origin={origin or 'none'}"
                ),
            )
        except Exception:
            pass


#: One refusal line per client+Host+reason per 60 s. Every audit append is an
#: fsync, so an unauthenticated client on the LAN could otherwise turn a
#: brute-force run into a disk-sync flood while the 240/min limiter still lets
#: 240 of those through.
_REFUSAL_AUDIT_WINDOW = 60.0
_REFUSAL_AUDIT: dict[tuple[str, str, str], float] = {}
_refusal_lock = threading.Lock()


def _refusal_allowed(key: tuple[str, str, str]) -> bool:
    """True at most once per key and window. The caller records the attempt
    after the append call returns; a thrown write is retried, while a silent
    write failure is not something `audit_event` reports."""
    now = time.monotonic()
    with _refusal_lock:
        for stale in [
            k for k, seen in _REFUSAL_AUDIT.items()
            if now - seen >= _REFUSAL_AUDIT_WINDOW
        ]:
            _REFUSAL_AUDIT.pop(stale, None)
        last = _REFUSAL_AUDIT.get(key)
        return last is None or now - last >= _REFUSAL_AUDIT_WINDOW


def _refusal_recorded(key: tuple[str, str, str]) -> None:
    with _refusal_lock:
        _REFUSAL_AUDIT[key] = time.monotonic()


def _audit_token_refusal(request: Request, reason: str) -> None:
    """A LAN token refusal is a line: without one, a brute-force run leaves the
    log as quiet as a machine nobody touched."""
    client = request.client.host if request.client else "unknown"
    host = request.headers.get("host", "none")
    # The Host belongs in the key: a tunnel delivers every client as 127.0.0.1.
    key = (client, host, reason)
    if not _refusal_allowed(key):
        return
    try:
        from core.audit_log import audit_event

        audit_event(
            "security",
            tool="request",
            decision=reason,
            status="denied",
            detail=f"path={request.url.path} client={client} host={host}",
        )
    except Exception:
        return
    _refusal_recorded(key)


def audit_ws_refusal(websocket, marker: str, *, path: str = "") -> None:
    """One throttled line for a refused WebSocket handshake (no HTTP middleware
    covers the websocket scope, and every append fsyncs)."""
    client = (
        websocket.client.host
        if getattr(websocket, "client", None)
        else "unknown"
    )
    host = websocket.headers.get("host") or "none"
    origin = websocket.headers.get("origin") or "none"
    key = (client, host, marker)
    if not _refusal_allowed(key):
        return
    try:
        from core.audit_log import audit_event

        audit_event(
            "security",
            tool="websocket",
            decision=marker,
            status="denied",
            detail=f"path={path or 'none'} client={client} host={host} origin={origin}",
        )
    except Exception:
        return
    _refusal_recorded(key)


class AuthMiddleware(BaseHTTPMiddleware):
    """Protects every /api/* endpoint in LAN mode — except loopback (the desktop app itself)."""
    async def dispatch(self, request: Request, call_next):
        if LAN_AUTH_TOKEN is not None and not _is_loopback_client(request):
            path = request.url.path
            # `/charts` is not under /api and was therefore never checked: the mount
            # served the whole system temp directory to anyone who could reach the port.
            if path.startswith(("/api/", "/charts")) and path != "/api/health":
                token = request.headers.get("X-Auth-Token")
                if token is None and path.startswith(("/api/file", "/charts")):
                    # Media elements (img/iframe) cannot send headers —
                    # token fallback via query string only for the file-read routes.
                    token = request.query_params.get("token")
                if token is None or not hmac.compare_digest(str(token), LAN_AUTH_TOKEN):
                    rid = getattr(request.state, "rid", None)
                    _audit_token_refusal(request, "token_missing" if token is None else "token_invalid")
                    return JSONResponse(
                        error_payload(ErrorCode.AUTH, "Unauthorized — invalid or missing X-Auth-Token", rid),
                        status_code=401,
                        headers={REQUEST_ID_HEADER: rid or ""},
                    )
        return await call_next(request)


# Isolation on the response, not in the client: a file a browser can run as a
# document gets its opaque origin here — every surface embedding it today or
# tomorrow inherits it. The sandbox attribute on the frame stays as a second
# line of defense, but until now it was the only one.
#
# Dead formats (pdf, image, audio, video) are deliberately absent here: their
# viewer is a browser extension, and an extension runs in no sandboxed frame.
# Measured in real Chrome — a PDF frame with allow-same-origin kept showing the
# sad document, and only with no directive at all did the page render. So: dead
# format without isolation (it executes nothing), script-capable format with it,
# and imposed from here.
_FRAMED_FILE_ROUTES = re.compile(r"^/api/(?:file|artifacts/(?:[^/]+/file|proxy))$")
_SCRIPT_CAPABLE_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "image/svg+xml",
    "text/xml",
    "application/xml",
)


def _is_framed_document(path: str, response: Response) -> bool:
    if not _FRAMED_FILE_ROUTES.match(path or ""):
        return False
    media = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    return media in _SCRIPT_CAPABLE_TYPES


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # frame-ancestors 'self' instead of X-Frame-Options DENY: our own preview
        # (AgentPanel iframe on /api/file) has to be allowed to frame, foreign
        # origins still must not be. XFO DENY blanked out every image/PDF preview
        # (repo hygiene audit 2026-09-06).
        if LAN_AUTH_TOKEN:
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "connect-src 'self' ws://localhost:* http://localhost:*; "
                "img-src 'self' data:; "
                "font-src 'self' data:; "
                "frame-ancestors 'self'"
            )
        else:
            csp = "frame-ancestors 'self'"
        if _is_framed_document(request.url.path, response):
            csp += "; sandbox allow-popups"
        existing = response.headers.get("Content-Security-Policy")
        if existing:
            # A route that already narrowed its own response keeps that policy;
            # the global layer only adds the framing rule.
            csp = existing if "frame-ancestors" in existing else existing + "; " + csp
        response.headers["Content-Security-Policy"] = csp
        return response


# Costly routes: every call creates provider work (time, power, money) or
# process work on the machine. They are ALWAYS rate limited — also on desktop,
# where there is no access token. Prefix, not exact path: /api/chat/stream
# has no subpaths, /api/skills/install does.
_COSTLY_PATHS = (
    "/api/chat/stream",
    "/api/shell",
    "/api/skills/install",
    "/api/vision/",
)

# Polling endpoints: called every second by the frontend, they must not eat up
# the budget for expensive routes (chat/stream). Complete inventory of the
# shell pollers (MetricsGauges/StatusBar/ChatLayout/AgentStatus/Scheduler/Settings),
# otherwise 429s appear in the Dev Tools and the readouts stay stale.
_RATE_LIMIT_EXEMPT_PATHS = {
    "/api/health",    "/api/mobile/status",
    "/api/mobile/ping",
    "/api/setup/status",
    "/api/system/metrics",
    "/api/tasks",
    "/api/schedule",
    "/api/settings",
    "/api/skills",
    "/api/git/info",
    "/api/context/budget",
    "/api/model/providers",
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 240, window: int = 60, costly_max_requests: int = 20):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window
        self.costly_max_requests = costly_max_requests
        self.requests: dict[str, list[float]] = defaultdict(list)
        self.costly: dict[str, list[float]] = defaultdict(list)

    def _over(self, bucket: dict[str, list[float]], key: str, limit: int) -> bool:
        """One time window per client: drop the old entries, count, add the new entry
        only on approval — a rejected request consumes no budget."""
        now = time.time()
        kept = [t for t in bucket[key] if t > now - self.window]
        if len(kept) >= limit:
            bucket[key] = kept
            return True
        kept.append(now)
        bucket[key] = kept
        return False

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        # Costly routes apply ALWAYS, even without an access token. Desktop sets
        # none: here the case is not the stranger on the network but the local
        # process that kicks off a thousand chat runs — each one costs provider
        # time, power and money. The cheap pollers are on the allowlist and never
        # reach this branch.
        if path.startswith(_COSTLY_PATHS) and self._over(self.costly, client_ip, self.costly_max_requests):
            return Response(
                f"Rate limit exceeded for {path}. Try again later.",
                status_code=429,
                headers={"Retry-After": str(self.window)},
            )

        if LAN_AUTH_TOKEN is None:
            return await call_next(request)

        # Cheap status/health/ping polls must not eat the budget for expensive
        # endpoints (chat/stream) — the frontend polls them every second.
        # ponytail: blacklist of the pollers; switch it to an allowlist (limit
        # only costly routes) when new expensive endpoints are added.
        if path in _RATE_LIMIT_EXEMPT_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        window_start = now - self.window
        self.requests[client_ip] = [t for t in self.requests[client_ip] if t > window_start]

        if len(self.requests[client_ip]) >= self.max_requests:
            return Response(
                "Rate limit exceeded. Try again later.",
                status_code=429,
                headers={"Retry-After": str(self.window)},
            )

        self.requests[client_ip].append(now)
        return await call_next(request)
