"""server/routes/mobile.py – GET /api/mobile/qr"""

import io
import base64
import time
import os
import urllib.request
from urllib.parse import urlparse
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Literal

from utils.network import get_local_ip
from utils.tunnel import tunnel_manager

router = APIRouter(tags=["Mobile"])

# Global state for connection tracking
_device_connected = False

class MobileQRResponse(BaseModel):
    url: str
    qr_base64: str
    mode: str = "auto"
    is_public: bool = False
    requires_internet: bool = False
    lan_reachable: bool = True
    message: str = ""


def _is_loopback_host(host: str | None) -> bool:
    normalized = (host or "").strip().lower()
    return normalized in {"127.0.0.1", "localhost", "::1"}


def _server_allows_lan(request: Request) -> bool:
    bound_host = os.environ.get("EPHE_HOST") or request.url.hostname
    return not _is_loopback_host(bound_host)


def _is_docker_runtime() -> bool:
    return (os.environ.get("EPHE_DOCKER")) == "1" or os.path.exists("/.dockerenv")


def _split_host_port(host: str) -> tuple[str, str] | None:
    """(host, port | "") for a scheme-less authority, or None when it is not one.

    A colon without a numeric port is the shape of another scheme written without
    its slashes (`data:text/html,x`, `javascript:alert(1)`), and handing that to
    `urlopen` as `http://…` is the same escape the scheme check above closes.
    """
    if host.startswith("["):
        end = host.find("]")
        if end < 0:
            return None
        rest = host[end + 1 :]
        if rest == "":
            return host[: end + 1], ""
        if rest.startswith(":") and rest[1:].isdigit():
            return host[: end + 1], rest[1:]
        return None
    if ":" not in host:
        return host, ""
    name, _, own_port = host.rpartition(":")
    if not name or not own_port.isdigit():
        return None
    return name, own_port


def _configured_mobile_base_url(port: int) -> str | None:
    host = (os.environ.get("EPHE_MOBILE_HOST") or "").strip()
    if not host:
        return None
    if "://" in host:
        parsed = urlparse(host)
        # The probe below calls urllib.request.urlopen with what this returns, so
        # a host written as ftp:// or file:// would be fetched on that protocol
        # while the QR still says http. Only the family the surface advertises.
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        return None
    authority = _split_host_port(host)
    if authority is None:
        return None
    name, own_port = authority
    return f"http://{name}:{own_port or port}".rstrip("/")


def _lan_probe_succeeds(base_url: str) -> bool:
    if (os.environ.get("EPHE_SKIP_LAN_PROBE")) == "1":
        return True
    try:
        with urllib.request.urlopen(f"{base_url}/api/health", timeout=0.75) as response:
            return 200 <= response.status < 500
    except Exception:
        return False

def _start_public_tunnel(port: int) -> str | None:
    # Root-Cause F1 (first-user QA 2026-09-04): the ssh/localhost.run tunnel raises
    # "[Errno 32] Broken pipe" on network/daemon problems. Uncaught that 500'd the
    # whole /api/mobile/qr endpoint → the first user saw a red "API 500" instead of a QR.
    # A guard HERE covers both callers (mode=public + auto fallback): no tunnel
    # reachable == None, the caller then falls back to the LAN URL + user hint.
    try:
        tunnel_manager.start_tunnel(port)
        first_seen_at = None
        # ponytail: blocks up to 25s on the very first cold start (ssh handshake from localhost.run);
        # after that the ssh daemon keeps running => warm => instant. Upgrade path: QR immediately with
        # a "tunnel is being built" status + poll, if the cold-start user count rises.
        for _ in range(250):
            if tunnel_manager.public_url and first_seen_at is None:
                first_seen_at = time.time()
            if first_seen_at is not None and time.time() - first_seen_at >= 2.0:
                break
            time.sleep(0.1)
        return tunnel_manager.public_url
    except Exception:
        return None


@router.get("/mobile/qr", response_model=MobileQRResponse)
def get_mobile_qr(request: Request, mode: Literal["auto", "lan", "public"] = "auto") -> MobileQRResponse:
    """Returns the local or public URL and a base64 encoded QR code for mobile pairing."""
    global _device_connected
    _device_connected = False  # Reset on new pairing request
    port = request.url.port or 8765
    requested_mode = mode  # 'auto' may fall back to the public tunnel when LAN is dead

    target_url = None
    is_public = False
    lan_reachable = _server_allows_lan(request)
    message = ""

    if mode == "public":
        target_url = _start_public_tunnel(port)
        is_public = bool(target_url)

    if not target_url:
        configured_mobile_base_url = _configured_mobile_base_url(port)
        docker_without_mobile_host = _is_docker_runtime() and configured_mobile_base_url is None
        ip = get_local_ip()
        target_url = configured_mobile_base_url or f"http://{ip}:{port}"
        if docker_without_mobile_host:
            lan_reachable = False
        if not lan_reachable:
            mode = "lan"
            if docker_without_mobile_host:
                message = (
                    "Docker cannot expose its internal network address to your phone. "
                    "Set EPHE_MOBILE_HOST to your Mac Wi-Fi IP or choose public QR mode explicitly."
                )
            else:
                message = (
                    "Mobile LAN pairing needs Ephe started with LAN access. "
                    "Run: ephe start --lan"
                )
        elif not _lan_probe_succeeds(target_url):
            lan_reachable = False
            mode = "lan"
            message = (
                "Ephe is in LAN mode, but this Mac is not answering on the Wi-Fi address. "
                "Allow Python/Terminal in macOS Firewall or Local Network permissions, then reopen the QR. "
                "Public QR is available only when you choose public mode explicitly."
            )
        else:
            mode = "lan"
        # auto + LAN dead (firewall/no LAN bind) => outgoing public tunnel.
        # Outgoing (outbound-only) => macOS firewall irrelevant, no port forward, zero-config.
        if requested_mode == "auto" and not lan_reachable and not docker_without_mobile_host:
            tunnel_url = _start_public_tunnel(port)
            if tunnel_url:
                target_url = tunnel_url
                is_public = True
                lan_reachable = True
                mode = "public"
                message = ""
    else:
        lan_reachable = True

    # Mobile users get the clean chat-only page
    mobile_url = f"{target_url}/mobile.html"

    # Embed the auth token in the URL (only in LAN mode)
    from server.middleware import LAN_AUTH_TOKEN
    if LAN_AUTH_TOKEN:
        separator = "&" if "?" in mobile_url else "?"
        mobile_url = f"{mobile_url}{separator}token={LAN_AUTH_TOKEN}"

    import qrcode

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(mobile_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    return MobileQRResponse(
        url=mobile_url,
        qr_base64=qr_base64,
        mode=mode,
        is_public=is_public,
        requires_internet=is_public,
        lan_reachable=lan_reachable,
        message=message,
    )


@router.post("/mobile/ping")
def mobile_ping():
    """Triggered by the PWA when it opens on a smartphone."""
    global _device_connected
    _device_connected = True
    return {"status": "ok"}


@router.get("/mobile/status")
def mobile_status():
    """Polled by the Desktop UI while the QR code is open."""
    global _device_connected
    return {"connected": _device_connected}
