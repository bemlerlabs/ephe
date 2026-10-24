"""server/routes/proxy.py – GET /api/proxy/{port}/{full_path} (W17 P1-3, Wave I1-4).

Narrow reverse proxy onto loopback dev servers (Vite :5173, Next :3000, …)
for the preview panel. Only 127.0.0.1, short timeout — no general
SSRF valve (external URLs run through the web tools).

The reach is the number the user can see:
- Port 1024..65535, everything below is privileged (ssh 22, rpcbind 111, SMB 445,
  cups 631) and is never opened as a preview.
- Excepted are named local services whose API would be a data channel, not
  a web page: Docker (2375/2376/4243), databases (5432/3306/1433/5432/27017),
  cache and search services (6379/11211/9200/9300/5984), etcd (2379/2380), Kubelet
  (10250/10255) and Ephe's own engine (11434).
- Whoever really wants to preview one of these services names it explicitly:
  `EPHE_PROXY_PORTS=6379,11434`. The default never loosens.

The amount is capped: `PROXY_MAX_BODY_BYTES` = `core.net_guard.MAX_DOWNLOAD_BYTES`
(2 MB, measured at the same cap as fetch_url). The WebSocket tunnel (HMR) is
a stream, not a response — it shares the port wall, but no size cap.
"""
from __future__ import annotations

import asyncio
import contextlib
import os

import httpx
from fastapi import APIRouter, HTTPException, Request, WebSocket
from pydantic import BaseModel

from core.net_guard import MAX_DOWNLOAD_BYTES
from server.refusals import Refused
from server.middleware import ws_client_authorized

router = APIRouter(tags=["Proxy"])

#: Short and hard — dev servers answer locally in the millisecond range.
PROXY_TIMEOUT_S = 5.0

#: Lower bound of the dev-server space: below it lie privileged services.
PROXY_MIN_PORT = 1024
PROXY_MAX_PORT = 65_535

#: Local services whose answer is data, not a web page. The name stands in the
#: refusal — "port 6379 refused" without a reason leaves the reader guessing.
BLOCKED_SERVICE_PORTS: dict[int, str] = {
    2375: "docker",
    2376: "docker (tls)",
    4243: "docker",
    5432: "postgres",
    3306: "mysql",
    1433: "mssql",
    6379: "redis",
    11211: "memcached",
    27017: "mongodb",
    9200: "elasticsearch",
    9300: "elasticsearch",
    5984: "couchdb",
    2379: "etcd",
    2380: "etcd",
    10250: "kubelet",
    10255: "kubelet (read-only)",
    11434: "ollama (ephes eigene engine)",
}

#: Explicit extension, no default: only the named service ports are
#: released, the privileged boundary (1024) stays what it is.
ENV_PROXY_PORTS = "EPHE_PROXY_PORTS"

#: The same cap fetch_url already has — two numbers for one cap drift apart.
PROXY_MAX_BODY_BYTES = MAX_DOWNLOAD_BYTES
#: Size of the capping hint; the answer therefore stays <= cap + marker.
PROXY_CAP_MARKER_BYTES = 256


class ProxyResponse(BaseModel):
    ok: bool
    status: int
    body: str
    url: str


@router.get("/proxy/{port}", response_model=ProxyResponse)
async def proxy_root(port: str, request: Request) -> ProxyResponse:
    return await _proxy(port, "", query=request.url.query)


@router.get("/proxy/{port}/{full_path:path}", response_model=ProxyResponse)
async def proxy_get(port: str, full_path: str = "", request: Request = None) -> ProxyResponse:
    return await _proxy(port, full_path, query=request.url.query if request else "")


@router.websocket("/proxy/{port}/{full_path:path}")
async def proxy_ws(websocket: WebSocket, port: str, full_path: str = "") -> None:
    """P1-6: WebSocket tunnel for HMR (Vite/Next dev servers). The GET proxy
    is one-sided (no upgrade); HMR needs a bidirectional channel on
    the same port. The frames are passed through in both directions.

    P1-5: BaseHTTPMiddleware does not cover the websocket scope — without this
    explicit gate this loopback tunnel would be unauthenticated in LAN mode
    (SSRF valve). Same trust logic as the rest of the API."""
    if not ws_client_authorized(websocket):
        from server.middleware import audit_ws_refusal

        audit_ws_refusal(websocket, "ws_refused", path=f"/proxy/{port}")
        await websocket.close(code=1008)
        return
    number = _validate_port(port)
    url = f"ws://127.0.0.1:{number}/" + (full_path or "").lstrip("/")
    import websockets

    await websocket.accept()
    try:
        async with websockets.connect(url) as upstream:

            async def client_to_upstream() -> None:
                while True:
                    msg = await websocket.receive()
                    if msg.get("type") == "websocket.disconnect":
                        break
                    if (text := msg.get("text")) is not None:
                        await upstream.send(text)
                    elif (blob := msg.get("bytes")) is not None:
                        await upstream.send(blob)

            async def upstream_to_client() -> None:
                while True:
                    msg = await upstream.recv()
                    if isinstance(msg, str):
                        await websocket.send_text(msg)
                    else:
                        await websocket.send_bytes(msg)

            _, pending = await asyncio.wait(
                [
                    asyncio.create_task(client_to_upstream()),
                    asyncio.create_task(upstream_to_client()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
    except Exception:  # noqa: BLE001 — upstream or client gone → close the tunnel
        pass
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()


def _extra_allowed_ports() -> set[int]:
    """`EPHE_PROXY_PORTS` — explicit release, naming port for port."""
    raw = os.environ.get(ENV_PROXY_PORTS, "")
    allowed: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            allowed.add(int(part))
    return allowed


def _validate_port(port: str) -> int:
    if not port.isdigit():
        raise HTTPException(status_code=400, detail=f"port '{port}' is not numeric.")
    number = int(port)
    if not PROXY_MIN_PORT <= number <= PROXY_MAX_PORT:
        raise Refused(
            "proxy_port_out_of_range",
            port=number, min_port=PROXY_MIN_PORT, max_port=PROXY_MAX_PORT,
        )
    service = BLOCKED_SERVICE_PORTS.get(number)
    if service and number not in _extra_allowed_ports():
        raise Refused(
            "proxy_port_is_service", port=number, service=service, env=ENV_PROXY_PORTS
        )
    return number


async def _proxy(port: str, full_path: str, query: str = "") -> ProxyResponse:
    number = _validate_port(port)
    url = f"http://127.0.0.1:{number}/" + (full_path or "").lstrip("/")
    # F-P: query strings (?path=...) have to travel to the target — otherwise the
    # preview loses its parameters (e.g. /api/file?path=… → "path required").
    if query:
        url += ("&" if "?" in url else "?") + query
    try:
        async with httpx.AsyncClient(timeout=PROXY_TIMEOUT_S) as client:
            resp = await client.get(url)
    except Exception as exc:  # noqa: BLE001 — an honest 502 instead of a stack trace
        raise HTTPException(
            status_code=502, detail=f"upstream unreachable: {exc}"
        )
    # Bytes, not text: resp.text decodes the whole amount before anyone asks.
    payload = resp.content[:PROXY_MAX_BODY_BYTES]
    body = payload.decode("utf-8", errors="replace")
    if len(resp.content) > PROXY_MAX_BODY_BYTES:
        lost = len(resp.content) - PROXY_MAX_BODY_BYTES
        body += f"\n[… {lost} Byte nicht uebergeben — Koerper gedeckelt auf {PROXY_MAX_BODY_BYTES}]"
    return ProxyResponse(
        ok=resp.status_code == 200,
        status=resp.status_code,
        body=body,
        url=url,
    )
