"""
server/middleware.py – security middleware for LAN mode.
Generates a random auth token and protects every API endpoint.
"""
from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlsplit
import hmac
import re
import secrets
import threading
import time
from collections import defaultdict
from collections.abc import Mapping

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from core.observability import REQUEST_ID_HEADER, ErrorCode, error_payload
from server import plugin_surface_nonce

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
    token = offered_token(request.headers)
    if token is None or not tokens_match(str(token), LAN_AUTH_TOKEN):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized — invalid or missing token (X-Auth-Token or Authorization: Bearer)",
        )


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


#: GET routes that do more than read stored state. Measured with the route
#: table on 2026-11-07. A null-origin document on loopback would otherwise run
#: them with the desktop's authority and never see the body. The method guard
#: below still refuses mutations. These prefixes are the GET half of that class:
#: the image proxy writes a cache file, the pairing QR resets the connected
#: flag and may open a tunnel, the update check stores an answer and contacts
#: the release source, and the preview proxy opens another local port.
AUTHORITY_GET_PREFIXES = (
    "/api/artifacts/proxy",
    "/api/mobile/qr",
    "/api/update/check",
    "/api/proxy/",
)


def get_spends_local_authority(path: str) -> bool:
    """True when a GET of `path` writes state or opens another service."""
    raw = path or ""
    for prefix in AUTHORITY_GET_PREFIXES:
        if prefix.endswith("/"):
            if raw.startswith(prefix):
                return True
        elif raw == prefix or raw.startswith(prefix + "/"):
            return True
    return False


def origin_allowed(origin: str | None) -> bool:
    """True when `origin` is one this server serves.

    A browser sends Origin on a fetch and on every WebSocket handshake. A page
    from another site cannot make its origin look like ours. A missing or blank
    header is a non-browser client, and `caller_holds_app_authority` is where
    that client is decided. After DNS rebinding the page is same-origin, so it
    can set any header it likes. The Origin value itself is what this check
    compares.
    """
    if not origin or not str(origin).strip():
        return False
    return origin.strip().lower() in {value.lower() for value in _app_origins()}


def _suite_host(host: str | None) -> bool:
    """The synthetic host the suite uses. A packaged server has no such marker."""
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return _host_without_port(host or "").lower() == "testserver"


def same_origin_proof(request: "Request") -> bool:
    """Whether the request proves it came from a page this server serves.

    A browser omits `Origin` on a same-origin GET, so the origin rule refused the app's own
    fetch of an authority route (the Settings update check answered 403 in the PWA and in the
    desktop webview). Two headers name the same caller without being forgeable by another site:
    `Sec-Fetch-Site: same-origin` is set by the browser, and a `Referer` whose origin is one this
    server serves. A cross-site page gets neither.
    """
    site = (request.headers.get("sec-fetch-site") or "").strip().lower()
    if site == "same-origin":
        return True
    referer = (request.headers.get("referer") or "").strip()
    if not referer:
        return False
    parts = urlsplit(referer)
    if not parts.scheme or not parts.netloc:
        return False
    return origin_allowed(f"{parts.scheme}://{parts.netloc}")


def caller_holds_app_authority(
    origin: str | None,
    host: str | None,
    offered_token: str | None,
    *,
    same_origin: bool = False,
) -> bool:
    """Whether this caller may mutate, open a socket, or spend a GET's authority.

    An origin this server serves is the desktop app and the PWA, and those
    calls stay token-free. The suite's synthetic host stands in for that app,
    and only when the request brought no Origin of its own: a disallowed
    Origin stays disallowed there too. Anyone else presents the LAN token.
    With LAN mode off there is no token. A read-only GET does not ask this
    question. A program can type the app's Origin. That limit is named in
    `docs/SECURITY_AND_PRIVACY.md`.
    """
    if origin is not None and str(origin).strip():
        return origin_allowed(origin)
    if same_origin and host_allowed(host):
        return True
    if _suite_host(host):
        return True
    if (
        offered_token
        and LAN_AUTH_TOKEN is not None
        and tokens_match(str(offered_token), LAN_AUTH_TOKEN)
    ):
        return True
    return False


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


#: `Authorization: Bearer <token>` — the spelling every OpenAI-compatible client uses.
_BEARER_CREDENTIAL = re.compile(r"bearer[ \t]+", re.IGNORECASE)


def bearer_token(value: str | None) -> str | None:
    """The credential an `Authorization: Bearer <token>` value carries, or None.

    RFC 9110 makes the scheme case-insensitive, so `bearer` and `Bearer` are the same
    credential. Anything else (`Basic …`, a bare token without a scheme) is not a
    bearer value and grants nothing.
    """
    if not value:
        return None
    text = str(value).strip()
    match = _BEARER_CREDENTIAL.match(text)
    if match is None:
        return None
    token = text[match.end():].strip()
    return token or None


def offered_token(headers: Mapping[str, str]) -> str | None:
    """The credential a request presents, in either accepted spelling.

    `X-Auth-Token` is this product's own header; the QR link, the PWA and the desktop
    send it. An OpenAI-compatible client sets only a base URL and an API key and sends
    the key as `Authorization: Bearer <key>` — it cannot add a custom header, so that
    value is the same credential (issue #201). `X-Auth-Token` wins when both are present.
    """
    token = headers.get("X-Auth-Token") or headers.get("x-auth-token")
    if token:
        return str(token)
    authorization = headers.get("Authorization") or headers.get("authorization")
    return bearer_token(authorization)


def health_may_name_the_host(request: Request) -> bool:
    """Whether a `/api/health` answer may carry the host's identity.

    The identity is the absolute checkout path, the pid, the git sha and the instance id
    — the values that name this machine and this process (issue #196). On `--lan` they
    travel only to a caller the token admits, and to the desktop on the machine: the
    loopback peer *and* loopback `Host` pair `_is_loopback_client` trusts for `/api/chat`
    (a tunnel reuses the loopback peer but not the `Host`, so the token stays its gate).
    Without a token there is nothing to gate; the full answer stays.
    """
    token = LAN_AUTH_TOKEN
    if token is None:
        return True
    if _is_loopback_client(request):
        return True
    offered = offered_token(request.headers)
    return bool(offered) and tokens_match(str(offered), token)


def tokens_match(offered: str, expected: str) -> bool:
    """Compare two tokens without letting an attacker turn the check into a server error.

    `hmac.compare_digest` refuses non-ASCII text outright — measured here: comparing
    "ä" against a token raises `TypeError: comparing strings with non-ASCII characters is
    not supported`. Both of this file's call sites compare a value that came off the wire:
    a phone's `?token=` in a query string and the same parameter on a WebSocket handshake.
    A percent-encoded non-ASCII byte therefore produced a 500 where the answer is 401, and
    on the WS path an exception where the answer is a closed handshake. Encoding both sides
    first makes the comparison total: matching strings still match, everything else is a
    plain mismatch, and nothing the client sends can raise inside the gate.

    The `errors="replace"` on the offered value is deliberate. A token this server issued is
    `secrets.token_urlsafe` and therefore ASCII; anything unrepresentable on the way in is
    not that token and must not match it.
    """
    return hmac.compare_digest(
        offered.encode("utf-8", errors="replace"),
        expected.encode("utf-8", errors="strict"),
    )


def ws_client_authorized(websocket) -> bool:
    """Auth gate for WebSocket handshakes (P1-5).

    BaseHTTPMiddleware (AuthMiddleware) does NOT cover the 'websocket' scope —
    a WS upgrade bypasses the HTTP middleware completely. Without this explicit
    gate, every WS route would be reachable unauthenticated in LAN mode
    (that also held for the proxy_ws HMR tunnel).

    The app's handshake carries an Origin this server serves, and that call
    stays token-free. A handshake with no Origin is a local process: it needs
    the LAN token, and with LAN mode off the handshake is refused. The suite's
    synthetic host stands in for the app. A rebinding page presents a foreign
    Host and Origin even though the TCP peer is loopback, and it cannot guess
    the LAN token; both paths fail closed.
    """
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host", "")

    if LAN_AUTH_TOKEN is None:
        if not host_allowed(host):
            return False
        return caller_holds_app_authority(origin, host, None)

    client_host = websocket.client.host if getattr(websocket, "client", None) else ""
    loopback = client_host in _LOOPBACK_HOSTS and host_allowed(host)
    if loopback and caller_holds_app_authority(origin, host, None):
        return True
    offered = websocket.query_params.get("token") or ""
    return bool(offered) and tokens_match(str(offered), LAN_AUTH_TOKEN)


class LocalRequestGuardMiddleware(BaseHTTPMiddleware):
    """Rejects a request that reached the loopback port under a foreign Host.

    A DNS-rebinding page is same-origin with the address it typed, so its Host
    and Origin name the attacker's domain while the TCP peer stays 127.0.0.1.
    The peer address alone is therefore not a boundary. In LAN mode a
    non-loopback client is authenticated by the token; that path is left to
    AuthMiddleware.

    A mutation and a GET that spends authority also require an origin this
    server serves, or the LAN token. A missing Origin on those routes is a
    local process. Read-only GETs stay open for the app's own token-free fetch.
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
        spends = request.method not in {"GET", "HEAD", "OPTIONS"} or (
            request.method in {"GET", "HEAD"}
            and get_spends_local_authority(request.url.path)
        )
        if spends and not caller_holds_app_authority(
            origin,
            host,
            offered_token(request.headers),
            same_origin=same_origin_proof(request),
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


#: Paths a LAN caller may only reach with the token. `/api/health` is the one
#: exception and answers its liveness-only form. Every non-frontend static mount
#: belongs here: a mount is a second door onto bytes the routes already gate.
AUTH_PREFIXES = ("/api/", "/charts", "/audio", "/images")

#: The subset a media element can request. `<img>`, `<audio>` and `<iframe>` cannot
#: send a header, so the token the QR link already carries is accepted as `?token=`.
MEDIA_TOKEN_PREFIXES = ("/api/file", "/charts", "/audio", "/images")


class AuthMiddleware(BaseHTTPMiddleware):
    """Protects every /api/* endpoint in LAN mode — except loopback (the desktop app itself)."""
    async def dispatch(self, request: Request, call_next):
        if LAN_AUTH_TOKEN is not None and not _is_loopback_client(request):
            path = request.url.path
            if path.startswith(AUTH_PREFIXES) and path != "/api/health":
                token = offered_token(request.headers)
                if token is None and path.startswith(MEDIA_TOKEN_PREFIXES):
                    # Media elements (img/audio/iframe) cannot send headers —
                    # token fallback via query string only for the file-read routes.
                    token = request.query_params.get("token")
                if token is None or not tokens_match(str(token), LAN_AUTH_TOKEN):
                    # R21 (2026-11-04): a plugin surface is an iframe or a native
                    # webview, and neither can send a header. The long-lived LAN token
                    # stays out of URLs — logs, history and screenshots all keep a
                    # query string — so the surface carries its per-mount nonce in a
                    # *path segment*: `/api/plugins/ui/{plugin_id}/{nonce}/…`, one
                    # prefix the browser hands to every sub-resource the document
                    # derives. Here only the shape is read, and only for GET and
                    # HEAD: a mutation wearing a nonce-shaped segment is not a
                    # surface load and still faces the token. The route decides the
                    # value, the plugin binding and the expiry, and a refused
                    # segment is audited there, so guessing surfaces at the same
                    # throttle a guessed token gets. That throttle covers the audit
                    # line, and the line is a smaller cost than the request: a caller
                    # holding no token was handed the route's 401 off loopback as often
                    # as the shared 400-a-minute budget allowed. The family therefore
                    # rides its own budget below, keyed on the prefix read here.
                    if request.method in ("GET", "HEAD") and (
                        plugin_surface_nonce.surface_nonce_candidate(path) is not None
                    ):
                        return await call_next(request)
                    rid = getattr(request.state, "rid", None)
                    _audit_token_refusal(request, "token_missing" if token is None else "token_invalid")
                    return JSONResponse(
                        error_payload(
                            ErrorCode.AUTH,
                            "Unauthorized — invalid or missing token "
                            "(X-Auth-Token or Authorization: Bearer)",
                            rid,
                        ),
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

#: The plugin surface family, off loopback: `AuthMiddleware` hands a GET or HEAD
#: whose path *shape* carries a nonce segment straight to the route, which owns the
#: value. The audit line behind a guessed nonce is throttled to one per client per
#: minute, and a sweep of guesses costs only the shared 400-a-minute budget — the
#: limit the whole API shares, which a guessing run spends at will. The family gets
#: its own per-client budget instead, separate because a mount is a burst of
#: one-page-plus-its-assets: charged to the costly bucket at 20 a minute, a real
#: surface would be denied to its own user. The loopback desktop path stays outside
#: this bucket. The route still requires the nonce there.
_SURFACE_FAMILY_PREFIX = plugin_surface_nonce.SURFACE_PATH_ROOT
SURFACE_FAMILY_MAX_REQUESTS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self, app, max_requests: int = 240, window: int = 60, costly_max_requests: int = 20,
        surface_max_requests: int = SURFACE_FAMILY_MAX_REQUESTS,
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window
        self.costly_max_requests = costly_max_requests
        self.surface_max_requests = surface_max_requests
        self.requests: dict[str, list[float]] = defaultdict(list)
        self.costly: dict[str, list[float]] = defaultdict(list)
        self.surface: dict[str, list[float]] = defaultdict(list)

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

        # The surface family off loopback: the token check above handed a
        # nonce-shaped GET to the route on its shape alone, so a guess costs this
        # client a budget of its own before the route answers. Loopback and a server
        # without a token never entered the bypass, and never enter this bucket.
        if (
            path.startswith(_SURFACE_FAMILY_PREFIX)
            and LAN_AUTH_TOKEN is not None
            and not _is_loopback_client(request)
            and self._over(self.surface, client_ip, self.surface_max_requests)
        ):
            return Response(
                f"Rate limit exceeded for {path}. Try again later.",
                status_code=429,
                headers={"Retry-After": str(self.window)},
            )

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
